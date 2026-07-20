"""P&L explain waterfall (POST /deals/{id}/mtm/explain) — offline: in-memory
SQLite + monkeypatched Yahoo history. Synthetic daily closes, deterministic
scenarios (flat market → only the time effect; spot ramp → spot effect
dominates), plus the exact telescoping identity of the chain."""
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine

from backend.app.api import deals as deals_api
from backend.app.db.models import Deal, DealEvent

SCRIPT = """
PARAM AC_BAR = 105%
PARAM CPN = 8%
PARAM KI_BAR = 60%

AT 1, 2, 3:
  IF WOF >= AC_BAR
    PAY 1 + CPN * INDEX "rappel"
    STOP

AT MATURITY:
  SET KI = INDIC(WOF_MIN < KI_BAR)
  PAY (1 - KI) * 1 + KI * WOF "final"
"""

TODAY = date.today()
VALUE_D = TODAY - timedelta(days=400)
MATURITY = VALUE_D + timedelta(days=1096)


def _make_session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    s = Session(eng)
    deal = Deal(
        reference="EXPL-1", user_id=1, script_snapshot=SCRIPT,
        underlyings_json=json.dumps([{"name": "UL1", "ticker": "TK1", "s0_abs": 100.0}]),
        market_snapshot_json=json.dumps({
            "underlyings": [{"name": "UL1", "ticker": "TK1", "ccy": "USD",
                             "sigma": 20.0, "q": 0.0}],
            "corrMatrix": [[1.0]], "r": 3.0, "model": "constant",
            "antithetic": True, "user_params": {},
        }),
        strike_date=VALUE_D.isoformat(), value_date=VALUE_D.isoformat(),
        maturity_date=MATURITY.isoformat(), T=3.0,
        nominal=1_000_000.0, price_traded=98.0, status="actif",
    )
    s.add(deal)
    s.commit()
    s.refresh(deal)
    s.add(DealEvent(deal_id=deal.id, event_index=0,
                    event_date=VALUE_D.isoformat(), t_years=0.0,
                    spots_json=json.dumps({"UL1": 100.0}),
                    status="observé", label="Strike"))
    s.commit()
    return s, deal


def _fake_prices(price_at):
    """load_hist_prices stand-in: one close per calendar day, price_at(date)."""
    def fake(tickers, start, end):
        d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
        days = [d0 + timedelta(days=k) for k in range((d1 - d0).days + 1)]
        return {"dates": [d.isoformat() for d in days],
                "prices": {tk: [price_at(d) for d in days] for tk in tickers}}
    return fake


USER = SimpleNamespace(id=1)
BODY = deals_api.MtmExplainRequest(recalibrate="none")   # σ booking aux 2 dates


def _explain(monkeypatch, price_at, body=BODY):
    s, deal = _make_session()
    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices(price_at))
    try:
        return deals_api.deal_mtm_explain(deal.id, USER, s, n_paths=4000, body=body)
    finally:
        s.close()


def test_explain_flat_market_only_time_effect(monkeypatch):
    """Spots et σ identiques aux deux dates → tout est dans l'effet temps,
    spot/véga strictement nuls (mêmes arguments, même seed), résidu nul."""
    res = _explain(monkeypatch, lambda d: 100.0)
    by = {st["label"]: st["delta_pts"] for st in res["steps"]}
    assert by["Effet spot"] == 0.0
    assert by["Effet volatilité"] == 0.0
    assert res["residual_pts"] == 0.0
    assert by["Effet temps"] == pytest.approx(res["delta_pts"], abs=0.011)
    assert "Effet corrélation" not in by          # mono sous-jacent
    assert res["flows_detached"] == []            # aucun coupon détaché


def test_explain_spot_ramp_spot_effect_dominates(monkeypatch):
    """Spot 100 → 130 sur les 60 derniers jours (σ inchangé) : l'effet spot
    est positif (autocall se rapproche du rappel) et domine, véga nul."""
    ramp_start = TODAY - timedelta(days=60)

    def price_at(d):
        if d <= ramp_start:
            return 100.0
        frac = (d - ramp_start).days / 60.0
        return 100.0 + 30.0 * min(1.0, frac)

    res = _explain(monkeypatch, price_at)
    by = {st["label"]: st["delta_pts"] for st in res["steps"]}
    assert by["Effet volatilité"] == 0.0
    assert by["Effet spot"] > 1.0
    assert by["Effet spot"] > abs(by["Effet temps"])
    assert res["residual_pts"] == 0.0


def test_explain_chain_telescopes_exactly(monkeypatch):
    """Identité du waterfall : Σ effets + résidu == ΔMtM (aux arrondis 2dp)."""
    res = _explain(monkeypatch, lambda d: 100.0 + (0.01 * (d.toordinal() % 7)))
    total = sum(st["delta_pts"] for st in res["steps"]) + res["residual_pts"]
    assert total == pytest.approx(res["delta_pts"], abs=0.05)
    assert res["pnl_total_pts"] == pytest.approx(
        res["delta_pts"] + res["flows_total_pts"], abs=0.05)


def test_explain_guards(monkeypatch):
    s, deal = _make_session()
    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices(lambda d: 100.0))
    with pytest.raises(HTTPException) as e:
        deals_api.deal_mtm_explain(
            deal.id, USER, s, n_paths=4000,
            body=deals_api.MtmExplainRequest(date1=TODAY.isoformat(),
                                             date2=VALUE_D.isoformat()))
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e2:
        deals_api.deal_mtm_explain(
            deal.id, USER, s, n_paths=4000,
            body=deals_api.MtmExplainRequest(
                date2=(TODAY + timedelta(days=30)).isoformat()))
    assert e2.value.status_code == 422 and "futur" in e2.value.detail
    s.close()


def test_explain_phrases_present(monkeypatch):
    res = _explain(monkeypatch, lambda d: 100.0)
    txt = " ".join(res["phrases"])
    assert "écoulement du temps" in txt
    assert "delta/gamma" in txt
    assert "véga" in txt
    assert "taux d'actualisation est maintenu constant" in txt


def test_payloads_are_json_serializable(monkeypatch):
    """Régression : un numpy.bool_/float64 qui fuit dans le payload (best_case
    « capped » l'a fait) crashe l'encodeur FastAPI en production alors que les
    appels directs des tests passent — on force ici la sérialisation stricte."""
    def _assert_plain_json(obj, path="$"):
        if isinstance(obj, dict):
            for k, v in obj.items():
                _assert_plain_json(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _assert_plain_json(v, f"{path}[{i}]")
        else:
            assert obj is None or type(obj) in (bool, int, float, str), \
                f"{path}: type non-JSON {type(obj)} ({obj!r})"

    s, deal = _make_session()
    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices(lambda d: 100.0))
    try:
        mtm = deals_api.deal_mtm(deal.id, USER, s, n_paths=4000,
                                 body=deals_api.MtmRequest(recalibrate="none"))
        _assert_plain_json(mtm)
        json.dumps(mtm)
        exp = deals_api.deal_mtm_explain(deal.id, USER, s, n_paths=4000, body=BODY)
        _assert_plain_json(exp)
        json.dumps(exp)
    finally:
        s.close()


def test_explain_report_returns_pdf(monkeypatch):
    """Smoke : la note PDF d'explication se génère de bout en bout (waterfall,
    sensibilités résiduelles incluses) et l'endpoint renvoie bien un PDF."""
    s, deal = _make_session()
    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices(lambda d: 100.0))
    try:
        resp = deals_api.deal_mtm_explain_report(deal.id, USER, s, n_paths=4000,
                                                 body=BODY)
        assert resp.media_type == "application/pdf"
        assert "Explication_valo_EXPL-1" in resp.headers["content-disposition"]
    finally:
        s.close()


def test_residual_greeks_sane(monkeypatch):
    """Sensibilités résiduelles sur l'autocall synthétique (spot 100%, barrière
    105%) : delta positif (plus de spot → rappel plus probable), véga présent
    en GBM."""
    s, deal = _make_session()
    monkeypatch.setattr(deals_api, "load_hist_prices", _fake_prices(lambda d: 100.0))
    try:
        _p, ctx = deals_api._mtm_core(deal, s, n_paths=4000,
                                      body=deals_api.MtmRequest(recalibrate="none"))
        gks = deals_api._residual_greeks(ctx, 4000)
        assert len(gks) == 1 and gks[0]["name"] == "UL1"
        assert gks[0]["delta_pts"] > 0
        assert gks[0]["vega_pts"] is not None
    finally:
        s.close()