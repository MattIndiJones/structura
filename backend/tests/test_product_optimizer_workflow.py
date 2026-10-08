"""Dated references, full search budgets, cancellation and financial diagnosis."""
from copy import deepcopy
from datetime import date, timedelta
import json
import threading

import pytest
from pydantic import ValidationError
from sqlmodel import Session
from sqlalchemy import text
from sqlmodel import create_engine

from backend.app.api import product_optimizer as api
from backend.app.core.product_optimizer import service
from backend.app.core.product_optimizer.contracts import OptimizationRequest
from backend.app.db.models import Underlying, User
from backend.app.db.underlyings_seed import seeded_asset_class
from backend.app.services import optimizer_market as market
from backend.tests.test_product_optimizer import payload, request, evaluated, api_client


@pytest.fixture
def source(monkeypatch):
    market._cache.clear()
    calls=[]
    def vol(tickers, **kwargs):
        calls.append((list(tickers),kwargs))
        return {"vols":{ticker:.31 for ticker in tickers},"corr":{a:{b:1 if a==b else .4 for b in tickers} for a in tickers},
                "asof_effective":"2026-10-02","provider":"yahoo","n_obs":252,"warnings":[]}
    def div(ticker, **kwargs):
        calls.append((ticker,kwargs))
        return {"ok":True,"asof_effective":"2026-10-02","yield_declared":.004,"yield_implied":.004,
                "price":25.,"dividends":[],"suspect":False}
    monkeypatch.setattr(market,"load_hist_vol",vol)
    monkeypatch.setattr(market,"dividend_profile",div)
    yield calls
    market._cache.clear()


def test_automatic_reference_uses_requested_date_effective_close_and_basket_order(source):
    result=market.load_optimizer_references(["B","A"],"2026-10-04")
    assert [u["ticker"] for u in result["underlyings"]]==["B","A"]
    assert result["underlyings"][0]["sigma"]==.31
    assert result["correlation"]==[[1,.4],[.4,1]]
    assert result["provenance"]["underlyings.B.sigma"]["as_of"]=="2026-10-02"
    assert all(kwargs["asof"]=="2026-10-04" for _,kwargs in source)
    result["underlyings"][0]["sigma"]=99
    assert market.load_optimizer_references(["B","A"],"2026-10-04")["underlyings"][0]["sigma"]==.31
    assert len(source)==3
    market.load_optimizer_references(["B","A"],"2026-10-05")
    assert len(source)==6


def test_missing_data_is_not_zero_or_generic_defaults(monkeypatch,source):
    monkeypatch.setattr(market,"load_hist_vol",lambda *a,**k:{"error":"Source absente"})
    monkeypatch.setattr(market,"dividend_profile",lambda *a,**k:{"ok":False,"error":"Dividendes absents"})
    result=market.load_optimizer_references(["A"],"2026-10-04")
    assert result["underlyings"][0]["sigma"] is None
    assert result["underlyings"][0]["q"] is None
    assert result["correlation"] is None and not result["provenance"]
    assert result["warnings"] and result["underlyings"][0]["warnings"]


def test_future_references_are_never_used_and_suspect_dividends_remain_visible(monkeypatch,source):
    monkeypatch.setattr(market,"load_hist_vol",lambda *a,**k:{"vols":{"A":.8},"asof_effective":"2026-10-06"})
    monkeypatch.setattr(market,"dividend_profile",lambda *a,**k:{"ok":True,"asof_effective":"2026-10-02","yield_declared":.02,"suspect":True})
    result=market.load_optimizer_references(["A"],"2026-10-04")
    assert result["underlyings"][0]["sigma"] is None
    assert result["underlyings"][0]["q"]==.02
    assert "suspects" in result["underlyings"][0]["warnings"][-1]


def test_automatic_endpoint_uses_its_own_catalogue_selection(api_client,source):
    client,_,_=api_client
    data=client.post('/api/product-optimizer/market-reference',json={"tickers":["TEST"],"currency":"EUR","pricing_date":"2026-10-04"})
    assert data.status_code==200 and data.json()["underlyings"][0]["sigma"]==.31
    assert data.json()["underlyings"][0]["asset_type"] is None
    assert client.post('/api/product-optimizer/market-reference',json={"tickers":["MISSING"],"currency":"EUR","pricing_date":"2026-10-04"}).status_code==422
    assert client.post('/api/product-optimizer/market-reference',json={"tickers":["TEST","TEST"],"currency":"EUR","pricing_date":"2026-10-04"}).status_code==422
    assert seeded_asset_class("STMPA.PA")=="equity"
    assert seeded_asset_class("000300.SS")=="index"
    assert seeded_asset_class("^UNKNOWN")=="unknown"


def test_historical_pricing_date_and_issuance_date_roles_are_explicit():
    data=payload();data["pricing_date"]="2026-10-05"
    assert OptimizationRequest.model_validate(data).pricing_date.isoformat()=="2026-10-05"
    data["pricing_date"]="2026-10-04"
    with pytest.raises(ValidationError): OptimizationRequest.model_validate(data)
    with pytest.raises(ValidationError):
        market.MarketReferenceRequest(tickers=["A"],currency="EUR",pricing_date=date.today()+timedelta(days=1))


def test_existing_catalogue_migration_is_additive_and_idempotent():
    from backend.app.db.database import _migrate_underlying_classes
    engine=create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE underlyings (id INTEGER PRIMARY KEY, ticker TEXT, label TEXT)'))
        connection.execute(text("INSERT INTO underlyings VALUES (1,'STMPA.PA','Titre conservé')"))
        _migrate_underlying_classes(connection);_migrate_underlying_classes(connection)
        row=connection.execute(text('SELECT * FROM underlyings')).mappings().one()
        assert dict(row)=={'id':1,'ticker':'STMPA.PA','label':'Titre conservé','asset_class':'unknown'}


def test_catalogue_type_overrides_the_form_and_invalid_classification_is_rejected(api_client,source):
    from backend.app.db.database import get_session
    client,app,_=api_client
    with app.dependency_overrides[get_session]() as session:
        session.add(Underlying(ticker='STMPA.PA',label='STMicro',ccy='EUR',asset_class='equity'))
        session.commit()
    response=client.post('/api/product-optimizer/market-reference',json={'tickers':['STMPA.PA'],'currency':'EUR','pricing_date':'2026-10-04'})
    assert response.json()['underlyings'][0]['asset_type']=='equity'
    data=payload();data['market']['underlyings'][0].update(ticker='STMPA.PA',asset_type='index')
    response=client.post('/api/product-optimizer/estimate-search',json=data)
    assert response.status_code==422 and 'Type action/indice' in response.json()['detail']


def phoenix_grid():
    data=payload();data["product_family"]="phoenix"
    data["ranges"].update(maturity_months={"minimum":36,"maximum":60,"step":12},protection_barrier={"minimum":.5,"maximum":.6,"step":.05},
                          autocall_trigger={"minimum":.8,"maximum":1,"step":.05},coupon_barrier={"minimum":.6,"maximum":.7,"step":.05})
    data["search"].update(simulations=4000,max_candidates=256,max_seconds=1800,parallel_workers=4)
    return OptimizationRequest.model_validate(data)


def test_screenshot_135_structures_are_admitted_without_changing_paths_or_grid():
    req=phoenix_grid();estimate=service.estimate_search(req)
    assert estimate["candidate_count"]==135
    assert estimate["allowed"],estimate["reasons"]
    assert estimate["contractually_excluded"]==0 and estimate["pricing_count"]==135
    assert estimate["execution"]["queue_window"]==estimate["execution"]["workers"]
    assert req.search.simulations==4000
    assert len(list(service.generate_candidates(req)))==135
    short=req.model_copy(deep=True);short.search.max_seconds=120
    assert service.estimate_search(short)["allowed"]
    assert service.estimate_search(short)["warnings"]


def test_contractually_excluded_candidates_are_counted_before_any_pricing():
    data=payload();data["ranges"]["maturity_months"]={"minimum":13,"maximum":14,"step":1}
    estimate=service.estimate_search(OptimizationRequest.model_validate(data))
    assert estimate["candidate_count"]==2 and estimate["contractually_excluded"]==2 and estimate["pricing_count"]==0


def test_manual_stop_keeps_already_confirmed_candidates():
    data=payload();data["ranges"]["maturity_months"]={"minimum":12,"maximum":24,"step":12}
    req=OptimizationRequest.model_validate(data);stop=threading.Event()
    def exploration(_,candidate):
        result=evaluated(req);result.candidate_id=candidate.candidate_id;return result
    def validate(_,candidate,shortlist_size):
        candidate.validation_status="PASSED";return candidate
    events=service.run_events(req,adapter=exploration,validation_adapter=validate,should_cancel=stop.is_set)
    observed=[]
    for event in events:
        observed.append(event)
        if event["type"]=="validation_progress":stop.set()
    result=observed[-1]["result"]
    assert result["interruption"]=="USER_STOP" and not result["complete"]
    assert result["validation"]["passed"]==1 and result["recommended_id"]=="C0001"
    assert result["validation"]["not_evaluated"]==1


def test_cancellation_token_is_owned_and_cleaned_even_on_initialization_error(api_client,monkeypatch):
    client,_,current=api_client
    waiting=threading.Event();entered=threading.Event()
    def paused(req,should_cancel):
        entered.set();waiting.wait(5)
        yield {"type":"result","result":{"cancelled":should_cancel()}}
    monkeypatch.setattr(api,"run_events",paused)
    responses=[]
    thread=threading.Thread(target=lambda:responses.append(client.post('/api/product-optimizer/run',json=payload())))
    thread.start()
    try:
        assert entered.wait(5)
        with api._cancellation_lock:run_id=next(iter(api._cancellations))
        owner=current['user']
        current['user']=User(id=2,username="other",email="o@t",password_hash="x")
        assert client.post(f'/api/product-optimizer/cancel/{run_id}').status_code==404
        current['user']=owner
        assert client.post(f'/api/product-optimizer/cancel/{run_id}').json()=={"stopping":True}
    finally:
        waiting.set();thread.join(5)
    assert not thread.is_alive()
    assert json.loads(responses[0].text.splitlines()[-1])["result"]["cancelled"]
    assert not api._cancellations
    def broken(*a,**k):raise RuntimeError("private init error")
    monkeypatch.setattr(api,"run_events",broken)
    result=client.post('/api/product-optimizer/run',json=payload())
    assert json.loads(result.text.splitlines()[-1])["type"]=="error"
    assert "private init" not in result.text and not api._cancellations
    assert api._capacity.acquire(blocking=False);api._capacity.release()


def test_risk_failure_distinguishes_central_excess_from_uncertainty():
    req=request(constraints={"price_tolerance":.03,"max_probability_loss":.2})
    candidate=evaluated(req);candidate.probability_loss=.19;candidate.probability_loss_ic95=[.17,.21]
    service.filter_candidate(req,candidate)
    detail=next(d for d in candidate.rejection_details if d.get("metric")=="probability_loss")
    assert detail["category"]=="MC_UNCERTAINTY" and detail["gap"]==pytest.approx(.01)
    candidate=evaluated(req);candidate.probability_loss=.21;candidate.probability_loss_ic95=[.19,.23]
    service.filter_candidate(req,candidate)
    assert candidate.rejection_details[0]["category"]=="HARD_CONSTRAINT"
