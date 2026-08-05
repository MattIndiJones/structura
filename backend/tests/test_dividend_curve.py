"""Courbe de dividende : convention, cohérence économique et non-régression."""
import math

import pytest
from pydantic import ValidationError

from backend.app.api.deals import _engine_underlyings, _shift_dividend_curve
from backend.app.core.payscript.engine import (
    SY,
    _build_dividend_step_matrix,
    _mtf_reject_unsupported,
    run_mc,
)
from backend.app.core.payscript.parser import parse_script
from backend.app.core.schemas import UnderlyingParams


FORWARD = 'AT MATURITY\n  PAY S[1] "forward prépayé"'
CORR = [[1.0]]


def _underlying(*, curve=None, q=0.04):
    return {
        "name": "S1", "ticker": "", "ccy": "EUR",
        "sigma": 0.01, "q": q,
        "dividend_curve": curve or [], "dividend_decay": 0.10,
        "v0": 0.0001, "kappa": 2.0, "theta": 0.0001,
        "xi": 0.05, "rho_h": -0.30,
        "alpha": 0.01, "beta": 1.0, "rho": -0.20, "nu": 0.10,
        "skew": 0.0, "curvature": 0.0,
        "sigma_fx": 0.0, "rho_sfx": 0.0, "ccyh": 0.0,
    }


CURVE = [[1.0, 0.04], [2.0, 0.036], [3.0, 0.0324]]


def _price(underlying, *, maturity=2.5, model="constant"):
    return run_mc(
        parse_script(FORWARD), [underlying], CORR,
        r=0.03, T_max=maturity, N=6000, model=model, seed=42,
        antithetic=True, user_params={},
    )["price"]


def test_buckets_annuels_et_derniere_annee_partielle():
    steps = _build_dividend_step_matrix([_underlying(curve=CURVE)], 130, 1 / SY)
    assert steps is not None
    assert steps[0, 0] == pytest.approx(0.04)
    assert steps[51, 0] == pytest.approx(0.04)    # t = 1A inclus
    assert steps[52, 0] == pytest.approx(0.036)
    assert steps[103, 0] == pytest.approx(0.036)  # t = 2A inclus
    assert steps[104, 0] == pytest.approx(0.0324)
    integrated = float(steps[:, 0].sum()) / SY
    assert integrated == pytest.approx(0.04 + 0.036 + 0.5 * 0.0324, abs=1e-12)


def test_forward_prepaye_reproduit_integrale_de_la_courbe():
    expected = math.exp(-(0.04 + 0.036 + 0.5 * 0.0324))
    assert _price(_underlying(curve=CURVE)) == pytest.approx(expected, abs=5e-4)


def test_courbe_plate_reproduit_exactement_le_q_legacy():
    flat = _price(_underlying(q=0.04, curve=[]), maturity=2.5)
    curve = _price(
        _underlying(q=0.04, curve=[[1.0, 0.04], [2.0, 0.04], [3.0, 0.04]]),
        maturity=2.5,
    )
    assert curve == flat


@pytest.mark.parametrize("model", ["constant", "heston", "sabr", "localvol", "lsv"])
def test_tous_les_modeles_consument_la_meme_courbe(model):
    expected = math.exp(-(0.04 + 0.036))
    price = _price(_underlying(curve=CURVE), maturity=2.0, model=model)
    tolerance = 8e-4 if model == "constant" else 8e-3
    assert price == pytest.approx(expected, abs=tolerance), f"{model}: {price:.6f}"


def test_schema_refuse_une_courbe_croissante_ou_non_annuelle():
    with pytest.raises(ValidationError, match="non croissante"):
        UnderlyingParams(q=0.04, dividend_curve=[[1.0, 0.04], [2.0, 0.05]])
    with pytest.raises(ValidationError, match="buckets annuels"):
        UnderlyingParams(q=0.04, dividend_curve=[[0.5, 0.04]])
    with pytest.raises(ValidationError):
        UnderlyingParams(q=0.04, dividend_decay=1.01)


def test_snapshot_booking_restitue_les_noeuds_exacts_en_unites_moteur():
    market = {
        "underlyings": [{
            "name": "S1", "ccy": "EUR", "sigma": 20.0, "q": 4.0,
            "dividendCurveEnabled": True, "dividendDecay": 10.0,
            "dividendCurve": [
                {"label": "A1", "T": 1, "rate": 4.0},
                {"label": "A2", "T": 2, "rate": 3.6},
                {"label": "A3", "T": 3, "rate": 3.24},
            ],
        }],
    }
    [underlying] = _engine_underlyings(
        market, [{"name": "S1", "ticker": "SX5E", "ccy": "EUR"}])
    assert underlying["q"] == pytest.approx(0.04)
    assert underlying["dividend_decay"] == pytest.approx(0.10)
    assert underlying["dividend_curve"][0] == pytest.approx([1.0, 0.04])
    assert underlying["dividend_curve"][1] == pytest.approx([2.0, 0.036])
    assert underlying["dividend_curve"][2] == pytest.approx([3.0, 0.0324])


def test_mark_to_future_refuse_la_courbe_plutot_que_de_la_reappliquer():
    with pytest.raises(ValueError, match="courbe de dividende"):
        _mtf_reject_unsupported(
            "constant", "weekly", [], 0.0, [_underlying(curve=CURVE)])


def test_mtm_residuel_decale_les_buckets_sans_repartir_de_l_an_un():
    underlying = _underlying(curve=CURVE)
    _shift_dividend_curve(underlying, 1.25)
    assert underlying["q"] == pytest.approx(0.036)
    assert len(underlying["dividend_curve"]) == 2
    assert underlying["dividend_curve"][0] == pytest.approx([0.75, 0.036])
    assert underlying["dividend_curve"][1] == pytest.approx([1.75, 0.0324])


def test_mtm_apres_dernier_noeud_prolonge_le_dernier_bucket_a_plat():
    underlying = _underlying(curve=CURVE)
    _shift_dividend_curve(underlying, 3.2)
    assert underlying["q"] == pytest.approx(0.0324)
    assert underlying["dividend_curve"] == []
