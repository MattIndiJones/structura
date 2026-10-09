from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import json
import hashlib
import os
import random
from typing import Literal
from pathlib import Path
from threading import RLock
from uuid import uuid4
from pydantic import BaseModel, Field
from ...runtime import data_path
from .persistence import atomic_write


class CampaignConfig(BaseModel):
    name: str = Field(default="Une année avec Hector", min_length=1, max_length=100)
    model: str = Field(default="qwen2.5-coder:7b", min_length=1, max_length=100)
    start_date: str = Field(default_factory=lambda:(date.today()-relativedelta(years=1)).isoformat())
    months: int = Field(default=12, ge=1, le=24)
    target_volume: float = Field(default=100_000_000, gt=0, le=1e10)
    ticket: float = Field(default=10_000_000, gt=0, le=1e9)
    max_turns: int = Field(default=800, ge=10, le=5000)
    timeout_seconds: int = Field(default=90, ge=10, le=180)
    seed: int = Field(default=42, ge=0, le=2147483647)
    coaching: bool = True
    include_sg: bool = True
    contract_scenario: Literal['baseline','all_complete','random'] = 'baseline'
    @classmethod
    def validate_start(cls, value):
        from datetime import date
        return date.fromisoformat(value).isoformat()


ACTORS = {
    "hector": {"name": "Hector", "entity": "Maison Hector", "role": "issuer", "goal": "100 M€ de ventes clients, satisfaction et marge maîtrisée", "colour": "#15375a"},
    "bnp": {"name": "BNP", "entity": "BNP Paribas", "role": "bank", "goal": "15 % du volume bancaire, marge positive", "colour": "#176447"},
    "ca": {"name": "Crédit Agricole", "entity": "Crédit Agricole CIB", "role": "bank", "goal": "30 % du volume bancaire, marge et documentation maîtrisées", "colour": "#008177"},
    "sg": {"name": "Société Générale", "entity": "Société Générale", "role": "bank", "goal": "40 % du volume bancaire, service et marge", "colour": "#b12d39"},
    "client": {"name": "Élodie", "entity": "Gestion Élodie", "role": "client", "goal": "Investir avec des termes compris et un interlocuteur réactif", "colour": "#7950a0"},
    "achille": {"name": "Achille", "entity": "Supervision", "role": "supervisor", "goal": "Identifier les bugs et améliorer les usages", "colour": "#9a6b27"},
}


class Store:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(os.environ.get("STRUCTURA_WORKSHOP_ROOT", data_path("agent_workshop")))
        self.lock = RLock()

    def path(self, key):
        if not isinstance(key, str) or len(key) != 32 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("Référence de campagne invalide.")
        return self.root / key

    def load(self, key):
        with self.lock:
            return json.loads((self.path(key) / "campaign.json").read_text(encoding="utf-8"))

    def save(self, state):
        with self.lock:
            state['updated_at']=datetime.utcnow().isoformat()
            directory = self.path(state["id"])
            directory.mkdir(parents=True, exist_ok=True)
            atomic_write(directory/'campaign.json',json.dumps(state, ensure_ascii=False, allow_nan=False, indent=2))

    def create(self, config, owner):
        state = self.initial_state(config, owner)
        self.save(state)
        return state

    def initial_state(self, config, owner):
        config.start_date = CampaignConfig.validate_start(config.start_date)
        actors = deepcopy(ACTORS)
        if not config.include_sg:
            actors.pop("sg")
        actors['hector']['goal']=f"{config.target_volume/1_000_000:g} M€ de ventes clients, satisfaction et marge maîtrisée"
        for key, actor in actors.items():
            actor.update(id=key, status="À préparer", registered=False, memory=[], history=[], relations={}, prices={}, deals=[], crm={})
        from ...core.calendars import adjust, BusinessDayConvention
        from datetime import date
        initial = adjust(date.fromisoformat(config.start_date), "EUR", BusinessDayConvention.FOLLOWING).isoformat()
        state = {"id": uuid4().hex, "owner": owner, "config": config.model_dump(),
            "status": "DRAFT", "created_at": datetime.utcnow().isoformat(),
            "business_date": initial, "month": 0, "turns": 0, "actors": actors,
            "messages": [], "actions": [], "incidents": [], "cases": {}, "quotes": [],
            "accepted": {}, "client_offers": {}, "client_acceptances": [], "coverage": {
                "registration_ui":"NOT_EXERCISED", "bilateral_isda_csa":"NOT_EXERCISED", "crm":"NOT_EXERCISED",
                "native_pricing":"NOT_EXERCISED", "notes_booking":"NOT_EXERCISED", "native_mtm":"NOT_EXERCISED",
                "sourced_manual_fixings":"NOT_EXERCISED", "otc_credit_risk":"NOT_EXERCISED", "margin_calls":"NOT_EXERCISED",
                "counterparty_default":"NOT_EXERCISED", "hector_own_issuance":"NOT_EXERCISED", "reinvestment":"NOT_EXERCISED",
                "historical_market":"NOT_EXERCISED", "inter_entity_rfq_network":"DEFERRED"},
            "milestones": [], "usage": {"duration_seconds": 0, "model_calls": 0}, "processes": []}
        return state

    @contextmanager
    def lifecycle_guard(self, key):
        """Serialize starts and resets across controllers, outside movable data."""
        from .lease import CampaignLease
        self.path(key)
        with self.lock:
            directory = self.root / '_locks' / key
            if directory.resolve() != self.root.resolve() / '_locks' / key:
                raise ValueError('Dossier de verrouillage invalide.')
            directory.mkdir(parents=True, exist_ok=True)
            lease = CampaignLease(directory)
            try:
                yield
            finally:
                lease.close()

    def archive(self, key):
        """Remove from the list while retaining all private files for recovery."""
        source = self.path(key)
        root = self.root.resolve()
        destination = self.root / '_archive' / f'{key}-{uuid4().hex}'
        if source.resolve() != root / key or destination.resolve().parent != root / '_archive':
            raise ValueError('Dossier de campagne invalide ; opération annulée.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        return destination

    def restart(self, key, owner):
        """Replace a stopped campaign with fresh installations and identical settings."""
        previous = self.load(key)
        fresh = self.initial_state(CampaignConfig(**previous['config']), owner)
        backup = self.archive(key)
        try:
            self.save(fresh)
        except Exception:
            # A partially written replacement must never hide the previous run.
            if self.path(fresh['id']).exists():
                self.archive(fresh['id'])
            backup.rename(self.path(key))
            raise
        return fresh

    def command(self, key, action):
        with self.lock:
            path=self.path(key)
            command={"id":uuid4().hex,"action":action}
            atomic_write(path/'control.json',json.dumps(command))
            return command

    def read_command(self, key):
        try:return json.loads((self.path(key)/'control.json').read_text(encoding='utf-8'))
        except FileNotFoundError:return None

    def list(self, owner):
        if not self.root.exists():
            return []
        rows = []
        for path in self.root.glob("*/campaign.json"):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
                if state["owner"] == owner:
                    rows.append({**{k: state[k] for k in ("id", "status", "created_at", "business_date", "config", "turns")},'updated_at':state.get('updated_at',state['created_at'])})
            except (ValueError, OSError, KeyError):
                continue
        return sorted(rows, key=lambda x: x["updated_at"], reverse=True)


store = Store()


def contract_mandate(state):
    """Reproducible contractual prerequisites; never commercial outcomes."""
    scenario=state['config'].get('contract_scenario','baseline')
    rng=random.Random(state['config']['seed'])
    banks=[k for k,a in state['actors'].items() if a['role']=='bank']
    result={k:{'note_ready':scenario=='all_complete' or (rng.choice([True,False]) if scenario=='random' else k!='ca'),
               'otc_ready':scenario=='all_complete' or (rng.choice([True,False]) if scenario=='random' else k!='ca')} for k in banks}
    result['client']={'note_ready':True,'otc_ready':False}
    return result


def source_manifest():
    root=Path(__file__).resolve().parents[4]
    sources=list((root/'backend/app/services/agent_workshop').glob('*.py'))
    sources += [root/p for p in ('backend/app/api/trading.py','backend/app/api/deals.py','backend/app/runtime.py','frontend/dist/index.html')]
    return {'captured_at':datetime.utcnow().isoformat(),'source_sha256':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources if p.exists()}}
