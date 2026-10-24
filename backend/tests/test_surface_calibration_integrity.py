"""C17: material targets, numerical references, admission and durable evidence."""
from copy import deepcopy
import json
import math

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from scipy.integrate import solve_ivp
from scipy.special import ndtr

from backend.app.core import smile_calibration as calibration
from backend.app.core.schemas import PricingRequest, UnderlyingParams, VolatilitySurfaceParams
from backend.app.core.payscript import engine
from backend.app.core.payscript.parser import parse_script
from backend.app.core.valuation_context import build_pricing_receipt
from backend.app.api.inlife import _snapshot_underlying
from backend.app.core.inlife_valuation import _engine_underlyings
from backend.app.services.calibration_evidence import (
    sign_calibration, verify_calibration, validate_pricing_calibrations,
)
from backend.app.services.product_receipts import signed_receipt, verify_server_receipt
from backend.tests.test_products import product_client, _create

SECRET = 'c17-isolated-test-key'


def target(vol=.2, eta=0.):
    return VolatilitySurfaceParams(rho=-.75, eta=eta, atm_nodes=[
        [t, vol] for t in (.25, .5, 1., 2., 3., 5., 7., 10.)]).model_dump()


@pytest.fixture(scope='module')
def flat_fit():
    return calibration.calibrate_surface(target(), 'heston', 2.)


def request_for(fit):
    return PricingRequest(script='AT MATURITY:\n  PAY MAX(S[1]-1,0)', model='heston',
        T=2, N=1000, corr_matrix=[[1]], underlyings=[dict(
            name='S1', sigma=.2, q=.02, vol_surface=target(), **fit['parameters'],
            calibration_evidence=sign_calibration(fit['dossier'], secret=SECRET))])


@pytest.mark.parametrize('vanilla,digital,success,expected', [
    (5, 10, True, True), (5.00001, 0, True, False),
    (0, 10.00001, True, False), (0, 0, False, False),
    (float('nan'), 0, True, False), (0, float('inf'), True, False),
])
def test_qualification_is_distinct_from_optimizer_success(vanilla, digital, success, expected):
    assert calibration.qualification(success, vanilla, digital)['qualified'] is expected


def test_material_seven_year_pillar_changes_objective_and_fit():
    a = calibration.calibrate_surface(target(.3, .85), 'heston', 10.)
    p = target(.3, .85)
    p['atm_nodes'][-2][1] = .35
    b = calibration.calibrate_surface(p, 'heston', 10.)
    i = a['dossier']['grid']['expiries'].index(7.)
    assert a['dossier']['grid']['expiries'] == [.25, .5, 1., 2., 3., 4., 5., 7., 10.]
    assert abs(a['dossier']['controls']['target_calls'][i][2]-b['dossier']['controls']['target_calls'][i][2])*10000 > 400
    assert a['parameters'] != b['parameters']
    assert a['dossier']['grid']['excluded_pillars'] == []


def test_full_dossier_and_unqualified_exclusions(flat_fit):
    d = flat_fit['dossier']
    assert flat_fit['qualified'] and flat_fit['success']
    assert d['qualification']['thresholds_bp'] == {'vanilla': 5, 'digital': 10}
    assert d['grid']['weights'] and d['optimizer']['nfev'] > 0
    assert d['optimizer']['lower_bounds']['v0'] == .0001
    assert d['optimizer']['max_nfev'] == 65
    assert len(d['implementation_sha256']) == 64 and d['libraries']['scipy']
    assert d['controls']['model_put_digitals']
    fit = calibration.calibrate_surface(target(), 'heston', 12.)
    assert fit['dossier']['context']['requested_horizon'] == 12
    assert fit['dossier']['context']['fit_horizon'] == 10
    assert not fit['qualified']


@pytest.mark.parametrize('t', [.01, 1., 10.])
@pytest.mark.parametrize('sigma', [.01, .2])
def test_deterministic_variance_heston_matches_independent_black_scholes(t, sigma):
    strikes = np.array([.6, .8, 1., 1.2, 1.5])
    p = dict(v0=sigma*sigma, theta=sigma*sigma, kappa=1., xi=0., rho_h=-.7)
    c, d, diagnostics = calibration.heston_prices(p, [t], strikes, .03, .02)
    root = sigma*math.sqrt(t)
    d1 = (-np.log(strikes)+.01*t)/root+root/2
    d2 = d1-root
    np.testing.assert_allclose(c[0], math.exp(-.02*t)*ndtr(d1)-strikes*math.exp(-.03*t)*ndtr(d2), atol=1e-14)
    np.testing.assert_allclose(d[0], math.exp(-.03*t)*ndtr(-d2), atol=1e-14)
    assert diagnostics['evaluations'] == 0


def test_low_variance_wings_converge_without_negative_or_spurious_calls():
    p = dict(v0=.0001, theta=.0001, kappa=1., xi=.01, rho_h=-.7)
    k = np.linspace(.6, 1.5, 31)
    c, d, info = calibration.heston_prices(p, [1.], k, .03, .02)
    strict, strict_d, _ = calibration.heston_prices(p, [1.], k, .03, .02, tolerance=1e-10)
    assert np.all(c >= 0) and np.all(c <= math.exp(-.02))
    assert np.max(c[0, k >= 1.2])*10000 < .00001
    np.testing.assert_allclose(c, strict, atol=2e-8)
    np.testing.assert_allclose(d, strict_d, atol=2e-8)
    assert np.all(np.diff(c[0]) <= 2e-8)
    assert np.all(np.diff(c[0], 2) >= -2e-8)
    assert info['integration_error_estimate'] < 1e-8


def test_heston_against_independent_riccati_ode_and_extended_fourier_domain():
    # This reference solves the Riccati ODE, without the production closed-form
    # characteristic function or its adaptive integration/control variate.
    p = dict(v0=.04, theta=.05, kappa=1.2, xi=.4, rho_h=-.65)
    strikes = np.array([.6, .8, 1., 1.2, 1.5])
    references = []
    for cutoff, order in ((120., 384), (240., 768)):
        nodes, weights = np.polynomial.legendre.leggauss(order)
        u, weights = (nodes+1)*cutoff/2, weights*cutoff/2
        z = np.r_[u-1j, u]
        def rhs(t, state):
            d = state[:len(z)]
            return np.r_[.5*p['xi']**2*d*d+(p['rho_h']*p['xi']*1j*z-p['kappa'])*d-.5*(z*z+1j*z),
                         p['kappa']*p['theta']*d+1j*z*.01]
        solution = solve_ivp(rhs, [0, 2.], np.zeros(2*len(z), dtype=complex), rtol=2e-10, atol=2e-12)
        assert solution.success
        cf = np.exp(solution.y[len(z):, -1]+solution.y[:len(z), -1]*p['v0'])
        phase = np.exp(-1j*np.log(strikes[:, None])*u)/(1j*u)
        p1 = .5+np.real(phase*cf[:len(u)]/math.exp(.02))@weights/math.pi
        p2 = .5+np.real(phase*cf[len(u):])@weights/math.pi
        references.append(math.exp(-.04)*p1-strikes*math.exp(-.06)*p2)
    np.testing.assert_allclose(references[0], references[1], atol=2e-8)
    actual = calibration.heston_calls(p, [2.], strikes, .03, .02)[0]
    np.testing.assert_allclose(actual, references[1], atol=2e-8)


@pytest.mark.parametrize('model', ['localvol', 'lsv'])
def test_invalid_legacy_smile_refuses_pricing_without_mutating_old_inputs(model):
    u = dict(name='S1', sigma=.2, q=.02, skew=-.2, curvature=.1)
    previous = deepcopy(u)
    with pytest.raises(ValueError, match='legacy'):
        engine.run_mc(parse_script('AT MATURITY:\n  PAY MAX(1-S[1],0)'),
                      [u], [[1]], .03, 4, 1000, model)
    assert u == previous


def test_legacy_flat_short_tenor_and_admissible_skew_are_not_replaced():
    assert engine._dupire_vol(1.5, .001, .2, 0, 0, .03, .02) == pytest.approx(.2)
    assert engine._dupire_vol(.8, 1, .2, -.3, 0, .03, .03) > .2
    assert engine._dupire_vol(1.2, 1, .2, -.3, 0, .03, .03) < .2
    with pytest.raises(ValueError, match='legacy'):
        engine._dupire_vol(.2, 4, .2, -.2, .1, .03, .02)


@pytest.mark.parametrize('model', ['lsv', 'sabr'])
def test_component_or_training_mc_fit_is_explicitly_exploratory(model):
    fit = calibration.calibrate_surface(target(), model, .25)
    assert not fit['qualified'] and fit['qualification']['reasons']
    assert fit['dossier']['controls']['model_put_digitals']


def test_legacy_valid_nonflat_smile_still_prices():
    u = dict(name='S1', sigma=.3, q=.02, skew=-.01, curvature=.01)
    result = engine.run_mc(parse_script('AT MATURITY:\n  PAY MAX(1-S[1],0)'),
                           [u], [[1]], .03, 1, 1000, 'localvol')
    assert math.isfinite(result['price'])


@pytest.mark.parametrize('change', ['rate', 'dividend', 'parameter', 'horizon', 'target', 'level',
                                     'signature', 'missing', 'yield_curve', 'stochastic', 'quanto', 'dividend_curve'])
def test_automatic_application_rejects_stale_or_unsupported_context(flat_fit, change):
    req = request_for(flat_fit)
    u = req.underlyings[0]
    if change == 'rate': req.r = .04
    if change == 'dividend': u.q = .03
    if change == 'parameter': u.kappa += 1
    if change == 'target': u.vol_surface.eta = .1
    if change == 'level': u.sigma = .21
    if change == 'signature': u.calibration_evidence['dossier']['parameters']['xi'] += .1
    if change == 'missing': u.calibration_evidence = None
    if change == 'yield_curve': req.yield_curve = [[1, .03]]
    if change == 'stochastic': req.sigma_r = .01
    if change == 'quanto': u.ccyh = .001
    if change == 'dividend_curve': u.dividend_curve = [[1, .02]]
    with pytest.raises(ValueError):
        validate_pricing_calibrations(req, 3 if change == 'horizon' else 2, secret=SECRET)


def test_signed_dossier_survives_disk_price_receipt_and_residual_snapshot(flat_fit, tmp_path):
    req = request_for(flat_fit)
    validate_pricing_calibrations(req, 2, secret=SECRET)
    receipt = signed_receipt(build_pricing_receipt(req, .1), secret=SECRET)
    path = tmp_path/'retained-price.json'
    path.write_text(json.dumps(receipt), encoding='utf-8')
    restored = json.loads(path.read_text(encoding='utf-8'))
    verify_server_receipt(restored, secret=SECRET)
    retained = restored['pricing_input']['underlyings'][0]['calibration_evidence']
    assert verify_calibration(retained, secret=SECRET) == flat_fit['dossier']
    snapshot = _snapshot_underlying(req.underlyings[0])
    residual = _engine_underlyings({'underlyings': [snapshot]}, [{'name':'S1'}])[0]
    assert residual['calibration_evidence'] == retained
    assert restored['market_snapshot']['underlyings'][0]['calibration_evidence'] == retained


@pytest.mark.parametrize('success,vanilla,digital', [(False,0,0),(True,5.1,0),(True,0,10.1)])
def test_even_authentic_server_proof_cannot_apply_unqualified_fit(flat_fit, success, vanilla, digital):
    fit = deepcopy(flat_fit)
    d = fit['dossier']
    d['optimizer']['success'] = success
    d['controls']['max_vanilla_error_bp'] = vanilla
    d['controls']['max_digital_error_bp'] = digital
    # Even inconsistent claims from an old issuer cannot bypass current policy.
    d['qualification']['qualified'] = True
    req = request_for(fit)
    with pytest.raises(ValueError, match='qualifiée'):
        validate_pricing_calibrations(req, 2, secret=SECRET)


def test_api_blocks_unsigned_automatic_fit_before_simulation_and_keeps_manual_mode(flat_fit, monkeypatch):
    from backend.app.api import pricing
    from backend.app.api.auth import get_current_pricer
    app = FastAPI()
    app.include_router(pricing.router)
    app.dependency_overrides[get_current_pricer] = lambda: object()
    monkeypatch.setattr(pricing, 'receipt_signing_secret', lambda: SECRET)
    req = request_for(flat_fit)
    with TestClient(app) as client:
        body = req.model_dump(mode='json')
        body['underlyings'][0].pop('calibration_evidence')
        denied = client.post('/api/price', json=body)
        assert denied.status_code == 422 and 'Preuve' in denied.json()['detail']
        accepted = client.post('/api/price', json=req.model_dump(mode='json'))
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()['pricing_receipt']['pricing_input']['underlyings'][0]['calibration_evidence']
        body['underlyings'][0]['smile_parameter_mode'] = 'manual'
        assert client.post('/api/price', json=body).status_code == 200


def test_calibration_api_issues_complete_signed_dossier_and_preserves_long_horizon(flat_fit, monkeypatch):
    from backend.app.api import volatility
    from backend.app.api.auth import get_current_user
    seen = []
    def fit(surface, model, horizon, rate, dividend):
        seen.append(horizon)
        return deepcopy(flat_fit)
    monkeypatch.setattr(volatility, 'calibrate_surface', fit)
    monkeypatch.setattr(volatility, 'receipt_signing_secret', lambda: SECRET)
    app = FastAPI()
    app.include_router(volatility.router)
    app.dependency_overrides[get_current_user] = lambda: object()
    with TestClient(app) as client:
        response = client.post('/api/volatility/calibrate', json=dict(
            surface=target(), model='heston', horizon=12, rate=.03, dividend=.02))
    assert response.status_code == 200
    result = response.json()
    assert verify_calibration(result['calibration_evidence'], secret=SECRET) == result['dossier']
    assert seen == [12]


def test_retained_product_calculation_reloads_full_dossier_from_sqlite(flat_fit, product_client, monkeypatch):
    from datetime import date
    from sqlmodel import select
    from backend.app.api import products
    from backend.app.db.models import ProductCalculationRun
    monkeypatch.setattr(products, 'receipt_signing_secret', lambda: SECRET)
    req = request_for(flat_fit).model_copy(update=dict(
        strike_date=date(2026,9,14), value_date=date(2026,9,14),
        maturity_date=date(2028,9,14), payment_date=date(2028,9,14), settlement_ccy='EUR'))
    receipt = signed_receipt(build_pricing_receipt(req, .1), secret=SECRET)
    product = _create(product_client, key='retain-c17-proof', receipt=receipt,
                      pricing_input=req.model_dump(mode='json'))
    product_client.session.expire_all()
    saved = product_client.session.exec(select(ProductCalculationRun)).one()
    retained = json.loads(saved.input_json)['underlyings'][0]['calibration_evidence']
    assert verify_calibration(retained, secret=SECRET) == flat_fit['dossier']
    response = product_client.get(f"/api/products/{product['product_id']}/calculations/{saved.id}")
    assert response.status_code == 200
    assert response.json()['market_snapshot']['underlyings'][0]['calibration_evidence'] == retained
