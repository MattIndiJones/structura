"""Le sens économique d'une position doit traverser toute l'agrégation de risque.

`Deal.sens` existait depuis le booking et n'était lu par aucun calcul : les
Greeks, les chocs et la VaR sommaient les expositions en valeur absolue. Un
livre entièrement vendeur — le cas dominant — restait cohérent en relatif, ce
qui est exactement pourquoi personne ne l'a vu ; mais le premier deal de sens
opposé, typiquement une couverture, s'ajoutait au risque qu'il était censé
annuler.

Convention, établie par le reste du code (DealTab.vue, RfqRequest.sens) :
`Deal.sens` est écrit du point de vue de la banque. « vente » = la banque vend,
donc nous détenons le produit, position longue.
"""
import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlmodel import SQLModel, Session, create_engine

from backend.app.api import portfolios as portfolios_api
from backend.app.db.models import Deal, Portfolio, position_sign

USER = SimpleNamespace(id=1)

GREEKS = {
    "per_underlying": {"Amazon": {"delta": 0.55, "gamma": 1.90, "vega": 0.38}},
    "scalar": {"theta": -0.02, "rho": 0.45},
    "corr_pairs": {},
}


def _make_session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng)


def _add_deal(s: Session, reference: str, sens: str, portfolio_id=None,
              nominal: float = 1_000_000.0) -> Deal:
    deal = Deal(
        reference=reference, user_id=1, script_snapshot="AT MATURITY:\n  PAY 1.0",
        underlyings_json=json.dumps([{"name": "Amazon", "ticker": "AMZN",
                                      "s0_abs": 100.0}]),
        market_snapshot_json="{}", sens=sens,
        strike_date="2020-01-01", value_date="2020-01-01",
        maturity_date="2030-01-01", T=3.0, devise="EUR",
        nominal=nominal, price_traded=98.0, status="actif",
        portfolio_id=portfolio_id,
        greeks_json=json.dumps(GREEKS), greeks_computed_at=datetime.utcnow(),
    )
    s.add(deal)
    s.commit()
    s.refresh(deal)
    return deal


def test_convention_de_signe():
    """« vente » = la banque vend = nous achetons = long. L'inverse pour
    « achat ». C'est la convention opposée à celle de la RFQ, et l'inversion se
    fait au booking."""
    assert position_sign(SimpleNamespace(sens="vente", reference="X")) == 1.0
    assert position_sign(SimpleNamespace(sens="achat", reference="X")) == -1.0


def test_un_sens_inconnu_leve_plutot_que_de_choisir():
    """Un `sens` inattendu doit faire échouer le calcul, pas retomber sur une
    branche par défaut. Un risque simplement inversé reste parfaitement
    plausible à l'œil — c'est précisément ainsi que le module RFQ avait fini
    par lire toutes ses cotations à l'envers."""
    with pytest.raises(ValueError, match="Sens de position inconnu"):
        position_sign(SimpleNamespace(sens="Vente", reference="DEAL-1"))


def test_long_et_short_identiques_donnent_un_risque_nul(monkeypatch):
    """Deux fois le même produit, même nominal, sens opposés : le livre ne
    porte aucun risque. Chaque sensibilité agrégée doit valoir exactement zéro.

    Sans le signe, elles doublaient."""
    monkeypatch.setattr(portfolios_api, "_TICKER_TO_KEY", {})
    monkeypatch.setattr(portfolios_api, "_TICKER_TO_LABEL", {})
    s = _make_session()
    p = Portfolio(name="Book couvert", user_id=1)
    s.add(p); s.commit(); s.refresh(p)
    _add_deal(s, "LONG-1", "vente", portfolio_id=p.id)
    _add_deal(s, "SHORT-1", "achat", portfolio_id=p.id)
    try:
        res = portfolios_api.portfolio_risk(p.id, USER, s)
        bucket = next(iter(res["per_underlying"].values()))
        assert bucket["delta_eur"] == pytest.approx(0.0, abs=1e-6)
        assert bucket["gamma_eur"] == pytest.approx(0.0, abs=1e-6)
        assert bucket["vega_eur"] == pytest.approx(0.0, abs=1e-6)
        assert res["scalar"]["theta"] == pytest.approx(0.0, abs=1e-6)
        assert res["scalar"]["rho"] == pytest.approx(0.0, abs=1e-6)
        # La taille brute du livre, elle, ne se compense pas : deux positions
        # à financer restent deux positions à financer.
        assert res["nominal_total_eur"] == pytest.approx(2_000_000.0, abs=0.01)
    finally:
        s.close()


def test_une_position_vendue_inverse_ses_sensibilites(monkeypatch):
    """Cas isolé : le même deal vendu porte l'exposition opposée, au signe
    près et à l'identique en valeur absolue."""
    monkeypatch.setattr(portfolios_api, "_TICKER_TO_KEY", {})
    monkeypatch.setattr(portfolios_api, "_TICKER_TO_LABEL", {})
    s = _make_session()
    long_p = Portfolio(name="Long", user_id=1)
    short_p = Portfolio(name="Short", user_id=1)
    s.add(long_p); s.add(short_p); s.commit()
    s.refresh(long_p); s.refresh(short_p)
    _add_deal(s, "L", "vente", portfolio_id=long_p.id)
    _add_deal(s, "S", "achat", portfolio_id=short_p.id)
    try:
        d_long = next(iter(portfolios_api.portfolio_risk(long_p.id, USER, s)
                           ["per_underlying"].values()))["delta_eur"]
        d_short = next(iter(portfolios_api.portfolio_risk(short_p.id, USER, s)
                            ["per_underlying"].values()))["delta_eur"]
        assert d_long == pytest.approx(0.55 * 1_000_000.0, abs=0.01)
        assert d_short == pytest.approx(-d_long, abs=0.01)
    finally:
        s.close()
