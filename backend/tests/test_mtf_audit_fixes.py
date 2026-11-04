"""Independent settlement oracles for the November MTF audit regressions."""
import math

import pytest

from backend.app.core.payscript.engine import run_mark_to_future, run_mtf_drilldown, run_mc
from backend.app.core.payscript.parser import parse_script

UL = [dict(name='Test', sigma=.2, q=0.)]


@pytest.mark.parametrize('rate', [0., .03])
@pytest.mark.parametrize('dates', [[1.05, 1.15, 1.2], [1.15, 1.2]])
def test_maturity_cash_is_preserved_when_no_mark_falls_on_maturity(rate, dates):
    script = parse_script('AT 1:\n  PAY 0.01\nAT MATURITY:\n  PAY 1')
    options = dict(n_outer=20, n_inner=50, mtm_dates=dates, maturity_payment_t=1.2)
    fan = run_mark_to_future(script, UL, [[1.]], rate, 1.105, 100., **options)
    p0 = math.exp(-rate) + 100 * math.exp(-rate * 1.2)
    for row in fan['results']:
        mark = row['t']
        expected = 100 * math.exp(-rate * (1.2-mark)) if mark < 1.2 else 0.
        assert row['pvs'] == pytest.approx([expected]*20, abs=5.1e-5)
        assert row['n_alive'] == (20 if mark < 1.105 else 0)
        assert row['n_pending_settlement'] == (20 if 1.105 <= mark < 1.2 else 0)
        assert row['n_outstanding'] == (20 if mark < 1.2 else 0)
        cash = sum(f['amount']*100*math.exp(-rate*f['payment_t']) for f in row['settled_flows'][0])
        assert expected*math.exp(-rate*mark)+cash == pytest.approx(p0)
        detail = run_mtf_drilldown(script, UL, [[1.]], rate, 1.105, 100., mark, [0, 19], **options)
        for scenario in detail['scenarios']:
            assert scenario['mtf'] == pytest.approx(expected, abs=5.1e-7)
            assert scenario['sum_pv'] == pytest.approx(expected, abs=1e-5)
            assert scenario['realized_cash'] == (101 if mark >= 1.2 else 1)
            assert scenario['status'] == ('PAYOFF_ACTIVE' if mark < 1.105 else
                                          'PENDING_SETTLEMENT' if mark < 1.2 else 'SETTLED')


@pytest.mark.parametrize('model', ['heston', 'sabr', 'localvol', 'lsv'])
def test_fan_and_drilldown_reject_models_without_matching_outer_dynamics(model):
    script = parse_script('AT MATURITY:\n  PAY 1')
    options = dict(model=model, n_outer=20, n_inner=50, mtm_dates=[.5, 1.])
    with pytest.raises(ValueError, match='Constant.*GBM'):
        run_mark_to_future(script, UL, [[1.]], .03, 1., 100., **options)
    with pytest.raises(ValueError, match='Constant.*GBM'):
        run_mtf_drilldown(script, UL, [[1.]], .03, 1., 100., .5, [0], **options)


@pytest.mark.parametrize('model', ['heston', 'sabr', 'localvol'])
def test_mtf_guard_does_not_disable_the_initial_pricer(model):
    result = run_mc(parse_script('AT MATURITY:\n  PAY 1'), UL, [[1.]], .03, 1., 100,
                    model=model, seed=42)
    assert result['price'] == pytest.approx(math.exp(-.03), abs=5.1e-7)


def test_api_and_drilldown_preserve_final_claim_without_maturity_mark():
    from backend.app.api.pricing import mtf_endpoint, mtf_drilldown_endpoint
    from backend.app.core.schemas import MtfRequest, MtfDrilldownRequest
    from datetime import date
    base = dict(script='AT 1:\n  PAY 0.01\nAT MATURITY:\n  PAY 1',
                underlyings=UL, corr_matrix=[[1.]], r=.03, T=1.105,
                strike_date='2026-11-03', value_date='2026-11-03', payment_date='2028-01-14',
                main_price=97.4448, n_outer=20, n_inner=50, mtm_dates=[1.05, 1.15, 1.2])
    fan = mtf_endpoint(MtfRequest(**base))
    payment = round((date(2028, 1, 14)-date(2026, 11, 3)).days/365.25, 6)
    expected = 100*math.exp(-.03*(payment-1.15))
    assert fan['results'][1]['pvs'] == pytest.approx([expected]*20, abs=5.1e-5)
    detail = mtf_drilldown_endpoint(MtfDrilldownRequest(**base, t=1.15, scenario_ids=[0],
                                    context_fingerprint=fan['context_fingerprint']))
    assert detail['scenarios'][0]['mtf'] == pytest.approx(expected, abs=5.1e-7)
    assert detail['scenarios'][0]['status'] == 'PENDING_SETTLEMENT'
    assert fan['results'][-1]['n_outstanding'] == 0
