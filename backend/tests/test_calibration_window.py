"""La recalibration « marché actuel » lit sa propre fenêtre, pas celle du rejeu.

Le MtM résiduel chargeait l'historique statistique sur la fenêtre du rejeu du
cycle de vie : du strike moins sept jours jusqu'à la date de valorisation. Deux
conséquences, observées le 14/09/2026 sur un Capital Garanti forward start
(strike au 11/12/2026) :

- avant le strike, la fenêtre se réduisait à la dernière semaine — 4 rendements,
  sous le minimum de 20 : « Recalibration réalisée impossible », MtM refusé ;
- sur tout deal de moins d'un an, la vol « réalisée sur un an » était en fait
  une vol depuis le strike, sans que rien ne le signale.

Le chargeur simulé ne rend que les séances postérieures au début demandé : une
fenêtre trop courte se voit donc dans le nombre de rendements, comme en réel.
"""
from __future__ import annotations

import json
import math
from datetime import date, timedelta

from sqlmodel import Session, SQLModel, create_engine

from backend.app.core.calibration import calibration_history_start, realized_market
from backend.app.core.deal_valuation import MtmRequest, mtm_core
from backend.app.db.models import Deal, DealEvent
from backend.tests.product_helpers import attach_product_to_deal

TODAY = date.today()


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _deal(session: Session, strike: date, maturity: date, *, with_strike_event: bool) -> Deal:
    deal = Deal(
        reference=f"CALIB-{strike.isoformat()}", user_id=1, entity_id=1,
        script_snapshot="AT MATURITY\n  PAY 1 + 0.5 * MAX(0, WOF - 1)\n", sens="vente",
        contrepartie="Bank", devise="EUR", nominal=1_000_000,
        strike_date=strike.isoformat(), value_date=strike.isoformat(),
        maturity_date=maturity.isoformat(),
        payment_date=(maturity + timedelta(days=5)).isoformat(),
        T=(maturity - strike).days / 365.25,
        underlyings_json=json.dumps([
            {"name": "UL1", "ticker": "TK1"}, {"name": "UL2", "ticker": "TK2"}]),
        market_snapshot_json=json.dumps({
            "r": 3.0, "model": "constant",
            "underlyings": [{"name": "UL1", "sigma": 20.0, "q": 0.0},
                            {"name": "UL2", "sigma": 25.0, "q": 0.0}],
        }),
        status="actif",
    )
    attach_product_to_deal(session, deal)
    session.add(deal)
    session.flush()
    if with_strike_event:
        session.add(DealEvent(
            deal_id=deal.id, event_index=0, event_date=strike.isoformat(),
            t_years=0.0, spots_json=json.dumps({"UL1": 100.0, "UL2": 100.0}),
            label="Strike"))
    session.commit()
    session.refresh(deal)
    return deal


def _weekdays(start: date, end: date) -> list[date]:
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _loader(calls: list):
    """Deux ans de séances ; ne rend que celles postérieures au début demandé."""
    history = _weekdays(TODAY - timedelta(days=730), TODAY)

    def load(tickers, start, end=None, adjusted=False):
        calls.append({"start": start, "adjusted": adjusted})
        days = [d for d in history if d >= date.fromisoformat(start)]
        # Rendements alternés ±1 % et ±1,5 % : vols non nulles et distinctes.
        first = [100.0 * math.exp(0.01 * (i % 2)) for i in range(len(days))]
        second = [100.0 * math.exp(0.015 * ((i + 1) % 2)) for i in range(len(days))]
        return {"dates": [d.isoformat() for d in days],
                "prices": {"TK1": first, "TK2": second},
                "provider": "YAHOO_FINANCE", "adjusted": adjusted,
                "price_type": "ADJUSTED_CLOSE" if adjusted else "UNADJUSTED_CLOSE"}
    return load


def _mtm(deal, session, calls):
    return mtm_core(
        deal, session, 1000, MtmRequest(recalibrate="realized"),
        load_prices=_loader(calls), realized_loader=realized_market,
        dividend_loader=lambda *_: {"ok": False})


def test_un_forward_start_se_recalibre_sur_un_an_de_marche():
    """Le cas du 14/09 : strike dans trois mois, historique du rejeu d'une
    semaine. La calibration ne doit plus en dépendre."""
    session = _session()
    deal = _deal(session, TODAY + timedelta(days=88), TODAY + timedelta(days=635),
                 with_strike_event=False)
    calls = []

    payload, _ = _mtm(deal, session, calls)

    assert payload["pre_strike"] is True
    assert payload["market_used"]["source"] == "realized"
    assert payload["market_used"]["window_returns"] == 252
    raw = [c for c in calls if not c["adjusted"]]
    statistical = [c for c in calls if c["adjusted"]]
    # Le rejeu garde sa fenêtre : sept jours avant la date de valorisation.
    assert raw[0]["start"] == (TODAY - timedelta(days=7)).isoformat()
    # La calibration lit la sienne, ancrée sur la date de valorisation.
    assert statistical[0]["start"] == calibration_history_start(TODAY, 252).isoformat()
    assert payload["market_used"]["data"]["statistical_history"]["price_type"] == "ADJUSTED_CLOSE"


def test_un_deal_jeune_ne_prend_plus_une_vol_depuis_le_strike():
    """Striké il y a trente jours : l'ancienne fenêtre donnait environ vingt-cinq
    rendements, présentés comme une vol réalisée sur un an."""
    session = _session()
    deal = _deal(session, TODAY - timedelta(days=30), TODAY + timedelta(days=700),
                 with_strike_event=True)
    calls = []

    payload, _ = _mtm(deal, session, calls)

    assert payload["pre_strike"] is False
    assert payload["market_used"]["window_returns"] == 252
    # ±1 % en alternance : σ = √(252 · 1e-4) — la fenêtre complète, pas un bout.
    assert payload["market_used"]["sigma"]["UL1"] == round(math.sqrt(252 * 1e-4) * 100, 2)
    raw = [c for c in calls if not c["adjusted"]]
    assert raw[0]["start"] == (TODAY - timedelta(days=37)).isoformat()


def test_la_fenetre_suit_la_date_de_valorisation_et_sa_longueur():
    """L'explication de P&L valorise à deux dates : chacune lit la fenêtre qui
    précède SA date. Et une fenêtre plus longue remonte plus loin."""
    asof = date(2026, 6, 30)
    assert calibration_history_start(asof, 252) == asof - timedelta(days=504)
    assert calibration_history_start(asof, 60) == asof - timedelta(days=365)
    assert calibration_history_start(asof, 756) == asof - timedelta(days=1512)
