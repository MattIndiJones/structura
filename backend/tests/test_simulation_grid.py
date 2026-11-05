"""Grid ownership from real pricing receipts through booking and dated MtM."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json

import pytest
from pydantic import ValidationError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api import deals as deals_api
from backend.app.api.pricing import price_endpoint
from backend.app.core.deal_valuation import MtmRequest
from backend.app.core.payscript.engine import run_mc
from backend.app.core.payscript.parser import parse_script
from backend.app.core.schemas import PricingRequest
from backend.app.core.simulation_grid import grid_frequency, simulation_grid
from backend.app.core.valuation_runs import replay_valuation_run, stage_valuation_run
from backend.app.db.models import Counterparty, Deal, DealEvent, User


ATHENA = '''UNDERLYING Basket
PARAM COUPON = 10%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 60%
CONSTAT StartDate
CONSTAT() ObservationDates
AT StartDate:
  Basket.spot0 = Basket.spot@StartDate
AT Date FROM ObservationDates:
  IF WORSTOF(Basket.yield) >= M_AC_BAR:
    PAY COUPON * INDEX "Coupons"
    PAY 1 "Capital au rappel"
    STOP
AT ObservationDates.last:
  PAY 1 "Capital à maturité"
  PAY -INDIC(WORSTOF(Basket.yield) < M_KI_BAR) * MAX(1 - WORSTOF(Basket.yield), 0) "Protection"
'''


def asset(name, ticker, sigma, q):
    return dict(name=name, ticker=ticker, ccy='EUR', sigma=sigma, q=q,
                v0=sigma**2, theta=sigma**2, kappa=2., xi=.35, rho_h=-.7,
                alpha=sigma, beta=1., rho=-.4, nu=.35,
                smile_parameter_mode='manual',
                vol_surface=dict(profile='equity', mode='manual', rho=-.75, eta=.85,
                                 shape_scale=.04, max_expiry=10.,
                                 atm_nodes=[[t,sigma] for t in range(1,11)]))


@pytest.mark.parametrize('frequency',[52,104,208])
@pytest.mark.parametrize('model',['constant','heston','sabr','localvol','lsv'])
def test_each_model_uses_the_requested_axis(frequency, model):
    u=asset('STM','STMPA.PA',.54646136,.007388)
    u['vol_surface']['eta']=0.
    result=run_mc(parse_script('AT MATURITY:\n  PAY 1'),[u],[[1.]],.03,.25,1000,
                  model=model,steps_per_year=frequency)
    assert result['time_axis']['steps_per_year']==frequency
    assert result['time_axis']['steps']==round(.25*frequency)
    assert result['steps_per_year']==frequency
    assert grid_frequency()==52


def test_concurrent_grids_and_exception_do_not_change_other_calculations():
    def price(f):
        return run_mc(parse_script('AT MATURITY:\n  PAY 1'),
                      [dict(name='S',sigma=.2,q=0.)],[[1]],.03,1.,1000,
                      steps_per_year=f)['time_axis']['steps']
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert list(workers.map(price,[52,208,104,52]))==[52,208,104,52]
    with pytest.raises(RuntimeError):
        with simulation_grid(208):
            raise RuntimeError('test')
    assert grid_frequency()==52
    with pytest.raises(ValueError): price(53)
    with pytest.raises(ValidationError): MtmRequest(steps_per_year=53)


@pytest.mark.parametrize('basket',[False,True],ids=['STM','SG-STM'])
@pytest.mark.parametrize('booked_grid',[52,104,208])
@pytest.mark.parametrize('model',['localvol','heston'])
def test_stm_pricing_booking_lifecycle_grid_override_and_replay(monkeypatch,basket,booked_grid,model):
    strike=date.today()-timedelta(days=3)
    maturity=strike+timedelta(days=1096)
    underlyings=[asset('STM','STMPA.PA',.54646136,.007388)]
    if basket: underlyings.insert(0,asset('SG','GLE.PA',.34952353,.028009))
    corr=[[1.,.32012317],[.32012317,1.]] if basket else [[1.]]
    request=PricingRequest(script=ATHENA,underlyings=underlyings,corr_matrix=corr,
        r=.03,T=3.,N=1000,model=model,steps_per_year=booked_grid,
        strike_date=strike,value_date=strike,maturity_date=maturity,
        payment_date=maturity+timedelta(days=3),settlement_ccy='EUR',
        constats={'StartDate':strike.isoformat(),'ObservationDates':dict(
            first_observation_date=(strike+timedelta(days=365)).isoformat(),end_date=maturity.isoformat(),
            frequency='1Y',convention='following',settlement_lag=3,
            observation_calendars=['XPAR'],settlement_calendars=['TARGET'])})
    quote=price_endpoint(request)
    assert quote.time_axis['steps_per_year']==booked_grid
    body=deals_api.DealCreate(contrepartie='Banque',counterparty_id=1,
        transaction_format='EMTN',instrument_family='NOTE',nominal=100000,
        fair_value=100*quote.price,price_traded=100*quote.price,
        trade_date=strike.isoformat(),strike_date=strike.isoformat(),value_date=strike.isoformat(),
        maturity_date=maturity.isoformat(),payment_date=(maturity+timedelta(days=3)).isoformat(),T=3.,devise='EUR',
        underlyings=[dict(name=u['name'],ticker=u['ticker'],ccy='EUR') for u in underlyings],
        observation_times=[1.,2.,3.],script_snapshot=ATHENA,pricing_receipt=quote.pricing_receipt)
    db=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    SQLModel.metadata.create_all(db)
    with Session(db) as session:
        actor=User(id=1,username='grid-fixture',email='grid@example.invalid',password_hash='test-only',role='user')
        session.add(actor);session.add(Counterparty(id=1,name='Banque',active=True));session.commit()
        booked=deals_api.book_deal(body,actor,session)
        deal=session.get(Deal,booked['id'])
        frozen=deal.market_snapshot_json
        snapshot=json.loads(frozen)
        assert snapshot['stepsPerYear']==booked_grid
        assert snapshot['pricing_input']['steps_per_year']==booked_grid
        event=next(e for e in session.exec(select(DealEvent).where(DealEvent.deal_id==deal.id)).all() if e.t_years==0.)
        event.spots_json=json.dumps({u['name']:100. for u in underlyings});event.source='fixture';event.status='observé'
        session.add(event);session.commit()
        monkeypatch.setattr(deals_api,'load_hist_prices',lambda *a,**kw:dict(
            dates=[strike.isoformat(),(strike+timedelta(days=1)).isoformat()],
            prices={u['ticker']:[100.,99.] for u in underlyings}))
        original,ctx=deals_api._mtm_core(deal,session,n_paths=1000,body=MtmRequest(),asof=strike)
        assert original['market_used']['steps_per_year']==booked_grid
        assert original['market_used']['grid_warning'] is None
        if model == 'localvol':
            assert original['mtm']==quote.price
        else:
            # Emission calendar times are rounded to six decimals; the live
            # horizon is ACT/365.25. A tiny extra interval changes variance
            # shock indexing in Heston, so compare within MC uncertainty.
            bound=(quote.ic95[1]-quote.ic95[0]+original['ic95'][1]-original['ic95'][0])/2
            assert abs(original['mtm']-quote.price) < bound
        for effective in (52,104,208):
            payload,ctx=deals_api._mtm_core(deal,session,n_paths=1000,
                body=MtmRequest(steps_per_year=effective),asof=strike+timedelta(days=1))
            market=payload['market_used']
            assert market['time_axis']['steps_per_year']==effective
            assert market['booked_steps_per_year']==booked_grid
            assert bool(market['grid_warning'])==(effective!=booked_grid)
            assert ctx['valuation_context']['steps_per_year']==effective
            row,archived=stage_valuation_run(session,deal,actor.id,'MTM',ctx,payload,
                diagnostics={'request':MtmRequest(steps_per_year=effective).model_dump(mode='json')})
            session.commit()
            assert replay_valuation_run(row)['within_tolerance']
            assert archived['market_used']['steps_per_year']==effective
            assert session.get(Deal,deal.id).market_snapshot_json==frozen
    db.dispose()


@pytest.mark.parametrize('frequency', [52, 104, 208])
@pytest.mark.parametrize('model', ['constant', 'localvol'])
def test_mtf_drilldown_inherits_grid_and_rejects_another_grid(frequency, model):
    from backend.app.api.pricing import mtf_endpoint, mtf_drilldown_endpoint
    from backend.app.core.schemas import MtfRequest, MtfDrilldownRequest
    from fastapi import HTTPException
    u = asset('STM', 'STMPA.PA', .54646136, .007388)
    req = MtfRequest(script='AT MATURITY:\n  PAY MAX(WOF - 1, 0)',
        underlyings=[u], corr_matrix=[[1.]], r=.03, T=.5, model=model,
        steps_per_year=frequency, main_price=0., reference_paths=1000, n_outer=20, n_inner=50,
        mtm_dates=[.241, .5], strike_date='2026-11-05', value_date='2026-11-05')
    fan = mtf_endpoint(req)
    assert fan['steps_per_year'] == frequency
    drill = MtfDrilldownRequest(**(req.model_dump() | dict(t=.241,
        scenario_ids=[0,19], main_price=fan['main_price'],
        context_fingerprint=fan['context_fingerprint'])))
    detail = mtf_drilldown_endpoint(drill)
    assert detail['steps_per_year'] == frequency
    for index, scenario in zip([0,19], detail['scenarios']):
        assert scenario['mtf'] == pytest.approx(fan['results'][0]['pvs'][index], abs=.000051)
    assert all(mark == 0 for mark in fan['results'][-1]['pvs'])
    with pytest.raises(HTTPException, match='contexte'):
        mtf_drilldown_endpoint(drill.model_copy(update={'steps_per_year':104 if frequency==52 else 52}))


def test_old_context_remains_52_inside_a_finer_request():
    from backend.app.core.valuation_context import valuation_context_from_dict
    old = dict(underlyings=[], corr_matrix=[], r=.03, T=1., N=1000, model='constant')
    with simulation_grid(208):
        assert valuation_context_from_dict(old).steps_per_year == 52


@pytest.mark.parametrize('frequency', [52,104,208])
def test_legacy_unanchored_lsv_keeps_its_explicit_extreme_wing_refusal(frequency):
    # Old archived numerical contexts have no explicit current-spot anchor.
    # Preserve their coordinate convention and refusal; never silently use GBM.
    with pytest.raises(ValueError,match='Plafond numérique : 300 %'):
        run_mc(parse_script('AT MATURITY:\n  PAY WOF'),
            [asset('STM','STMPA.PA',.54646136,.007388)],[[1.]],.03,3.,1000,
            model='lsv',spot_base=[.99],steps_per_year=frequency)
