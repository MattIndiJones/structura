"""Persist owned research requests and run calculations independently of HTTP clients."""
from datetime import datetime
import hashlib
import json
import logging
import threading
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select
from sqlalchemy import DDL, event

from ..db.models import OptimizerResearch
from ..core.product_optimizer.contracts import OptimizationRequest
from ..core.product_optimizer.families import family_schema
from ..core.product_optimizer.market import freeze_market

logger = logging.getLogger(__name__)
_active = {}
_lock = threading.Lock()
TERMINAL = {"COMPLETED", "PARTIAL", "FAILED", "INTERRUPTED"}

# Requests and final calculation evidence are immutable even outside the API.
event.listen(OptimizerResearch.__table__, "after_create", DDL("""
CREATE TRIGGER optimizer_research_immutable BEFORE UPDATE ON optimizer_researches
WHEN NEW.user_id != OLD.user_id OR NEW.request_json != OLD.request_json
 OR NEW.request_hash != OLD.request_hash OR NEW.context_json != OLD.context_json
 OR NEW.summary != OLD.summary OR NEW.intention != OLD.intention
 OR NEW.parent_id IS NOT OLD.parent_id OR NEW.command_key != OLD.command_key
 OR NEW.title != OLD.title OR NEW.product_family != OLD.product_family
 OR NEW.pricing_date != OLD.pricing_date OR NEW.created_at != OLD.created_at
 OR (OLD.status IN ('COMPLETED','PARTIAL','FAILED','INTERRUPTED') AND
     (NEW.status != OLD.status OR NEW.result_json != OLD.result_json
      OR NEW.progress_json != OLD.progress_json OR NEW.error != OLD.error
      OR NEW.finished_at IS NOT OLD.finished_at))
BEGIN SELECT RAISE(ABORT, 'Optimizer research evidence is immutable'); END;
""").execute_if(dialect="sqlite"))

class ResearchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    optimization: OptimizationRequest
    title: str = Field(default="", max_length=160)
    intention: str = Field(default="", max_length=4000)
    parent_id: str | None = Field(default=None, max_length=40)
    command_key: str = Field(min_length=1, max_length=128)

class ArchiveChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archived: bool

def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)

def fingerprint(body):
    return hashlib.sha256(dump(body.model_dump(mode="json", exclude={"command_key"})).encode()).hexdigest()

def owned(session, research_id, user_id):
    row=session.get(OptimizerResearch, research_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(404, "Recherche introuvable.")
    return row

def existing(session, body, user_id):
    row=session.exec(select(OptimizerResearch).where(OptimizerResearch.user_id==user_id,
        OptimizerResearch.command_key==body.command_key)).first()
    if row and row.request_hash != fingerprint(body):
        raise HTTPException(409, "Cette clé de lancement désigne une autre demande. Relancez avec une nouvelle clé.")
    return row

def create(session, body, user_id):
    req=body.optimization
    if body.parent_id: owned(session, body.parent_id, user_id)
    family=family_schema(req.product_family, req.objective)
    title=body.title.strip() or f"{family['label']} · {' / '.join(u.name or u.ticker for u in req.market.underlyings)}"
    objectives={"maximize_coupon":"maximiser le coupon", "maximize_participation":"maximiser la participation",
        "maximize_cap":"maximiser le cap", "target_coupon":"privilégier la protection au coupon cible", "maximize_protection":"maximiser la protection"}
    axes=[]
    for field in family["range_fields"]:
        axis=getattr(req.ranges, field["key"])
        factor=100 if field["unit"]=="fraction" else 1
        suffix=" %" if factor==100 else " mois" if field["key"]=="maturity_months" else " ×"
        axes.append(f"{field['label']} : {axis.minimum*factor:g} à {axis.maximum*factor:g}{suffix}, pas {axis.step*factor:g}")
    summary=f"{family['label']} sur {' / '.join(u.ticker for u in req.market.underlyings)} en {req.currency} ; {objectives.get(req.objective,req.objective)} ; marché du {req.pricing_date}. "
    summary+=f"Prix d’émission {req.constraints.target_price*100:g} %, budget payoff {req.pricing_target*100:g} %, tolérance ±{req.constraints.price_tolerance*100:g} point(s). " + "; ".join(axes)+"."
    solved=family["solved_field"]
    summary+=f" {solved['label']} résolu entre {getattr(req.constraints,solved['minimum_key'])*100:g} et {getattr(req.constraints,solved['maximum_key'])*100:g} %. "
    if family['has_autocall']: summary+=f"Constatations tous les {' / '.join(str(n) for n in req.ranges.observation_months)} mois. "
    for field in family['fixed_fields']:
        value=getattr(req.payoff_settings,field['key']);factor=100 if field['unit']=='fraction' else 1
        summary+=f"{field['label']} : {value*factor:g}. "
    controls=[('max_probability_loss','Perte Q max.',100,'%'),('min_probability_autocall','Rappel Q min.',100,'%'),
        ('max_expected_capital_loss','Perte en capital moyenne Q max.',100,'%'),('max_expected_maturity','Durée moyenne Q max.',1,'ans'),
        ('target_coupon','Coupon cible',100,'%'),('coupon_tolerance','Tolérance coupon',100,'points')]
    summary+=' '.join(f"{label} : {value*factor:g} {unit}." for key,label,factor,unit in controls if (value:=getattr(req.constraints,key)) is not None)
    summary+=f" Frais {req.economics.upfront_fees*100:g} %, marge {req.economics.structuring_margin*100:g} % ; {req.search.simulations} paires indépendantes, budget {req.search.max_seconds:g} s."
    context={"payoff":family, "market_snapshot":freeze_market(req.market), "summary_schema":1}
    row=OptimizerResearch(id=str(uuid4()),user_id=user_id,parent_id=body.parent_id,command_key=body.command_key,
        title=title[:160],intention=body.intention.strip(),summary=summary,product_family=req.product_family,
        pricing_date=req.pricing_date.isoformat(),request_hash=fingerprint(body),request_json=dump(req.model_dump(mode="json")),context_json=dump(context))
    session.add(row);session.commit();session.refresh(row)
    return row

def projection(row, detail=False):
    result=json.loads(row.result_json or "{}")
    context=json.loads(row.context_json)
    data={"id":row.id,"parent_id":row.parent_id,"title":row.title,"intention":row.intention,"summary":row.summary,
        "product_family":row.product_family,"family_label":context["payoff"]["label"],"pricing_date":row.pricing_date,
        "status":row.status,"archived":row.archived,"created_at":row.created_at.isoformat()+"Z",
        "finished_at":row.finished_at.isoformat()+"Z" if row.finished_at else None,"progress":json.loads(row.progress_json),
        "statistics":result.get("statistics",{}),"error":row.error,"request_hash":row.request_hash}
    if detail: data.update(request=json.loads(row.request_json),context=context,result=result or None)
    return data

def partial_result(req, context, candidates, progress):
    values=list(candidates.values())
    confirmed=[c for c in values if c.get("constraint_status")=="PASS" and c.get("validation_status")=="PASSED"]
    return {"schema_version":1,"engine_version":"optimizer-v1-researches", "complete":False,
        "request":req.model_dump(mode="json"),"payoff":context["payoff"],"market_snapshot":context["market_snapshot"],
        "market_date":req.pricing_date.isoformat(),"simulations":req.search.simulations,"seed":req.search.seed,
        "economics":{"issue_price":req.constraints.target_price,**req.economics.model_dump(),"pricing_target":req.pricing_target},
        "candidates":values,"recommended_id":None,"warnings":["Calcul en cours ou interrompu ; couverture et validation potentiellement partielles."],
        "validation":{"selected":progress.get("validation_total",0),"passed":len(confirmed),"complete":False},
        "statistics":{"generated":progress.get("candidate_total",len(values)),"evaluated":len(values),
            "priced":sum(c.get("pricing_status")=="PRICED" for c in values),"valid":len(confirmed),
            "rejected":sum(c.get("constraint_status")=="REJECTED" for c in values),
            "failed":sum(c.get("pricing_status")=="FAILED" for c in values),
            "not_evaluated":max(0,progress.get("candidate_total",len(values))-len(values))}}

def start(engine, row, runner, release):
    stop=threading.Event()
    research_id=row.id
    def work():
        iterator=None
        try:
            with Session(engine) as session:
                saved=session.get(OptimizerResearch,research_id)
                req=OptimizationRequest.model_validate_json(saved.request_json)
                context=json.loads(saved.context_json)
            candidates={};progress={"phase":"exploration","completed":0,"total":0}
            iterator=runner(req,should_cancel=stop.is_set,include_candidate_events=True)
            received=False
            for item in iterator:
                kind=item["type"]
                if kind=="heartbeat": continue
                if kind=="started":
                    progress.update(total=item["estimate"]["candidate_count"],candidate_total=item["estimate"]["candidate_count"])
                if kind=="validation_started":
                    progress.update(phase="validation",completed=0,total=item["total"],validation_total=item["total"])
                    for key in item["candidate_ids"]:
                        if key in candidates: candidates[key]["validation_status"]="PENDING"
                if kind in ("progress","validation_progress"):
                    progress.update(completed=item["completed"],total=item["total"],candidate_id=item["candidate_id"])
                    if item.get("candidate"): candidates[item["candidate_id"]]=item["candidate"]
                with Session(engine) as session:
                    saved=session.get(OptimizerResearch,research_id)
                    saved.progress_json=dump(progress)
                    if kind=="result":
                        saved.result_json=dump(item["result"])
                        saved.status="COMPLETED" if item["result"]["complete"] else "PARTIAL"
                        saved.finished_at=datetime.utcnow();received=True
                    else: saved.result_json=dump(partial_result(req,context,candidates,progress))
                    session.add(saved);session.commit()
            if not received: raise RuntimeError("Missing final research result")
        except Exception:
            logger.exception("Optimizer research failed id=%s",research_id)
            with Session(engine) as session:
                saved=session.get(OptimizerResearch,research_id)
                if saved and saved.status not in TERMINAL:
                    saved.status="FAILED";saved.error="Calcul interrompu par une erreur serveur ; les résultats déjà reçus sont conservés. Consultez les journaux serveur."
                    saved.finished_at=datetime.utcnow();session.add(saved);session.commit()
        finally:
            try:
                if iterator is not None: iterator.close()
            finally:
                with _lock: _active.pop(research_id,None)
                release()
    thread=threading.Thread(target=work,name=f"optimizer-{research_id}",daemon=False)
    with _lock: _active[research_id]=(stop,thread)
    try: thread.start()
    except Exception:
        with _lock: _active.pop(research_id,None)
        raise

def cancel(research_id):
    with _lock:
        entry=_active.get(research_id)
        if entry: entry[0].set()
    return bool(entry)

def recover(engine):
    """A server restart does not silently rerun a historical pricing request."""
    with Session(engine) as session:
        for row in session.exec(select(OptimizerResearch).where(OptimizerResearch.status=="RUNNING")):
            row.status="INTERRUPTED";row.finished_at=datetime.utcnow()
            row.error="Serveur redémarré avant la fin du calcul ; résultats partiels conservés. Reprenez la demande pour un nouveau calcul."
            session.add(row)
        session.commit()

def shutdown():
    with _lock: entries=list(_active.values())
    for stop,_ in entries: stop.set()
    for _,thread in entries: thread.join()
