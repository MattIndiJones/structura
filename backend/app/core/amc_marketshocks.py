"""Block K — Réactivité aux Chocs de Marché.

Juxtapose l'activité de trading du gérant avec un calendrier d'événements de
marché majeurs (subprimes, COVID, chocs chinois, etc.) pour évaluer si la
gestion a sur-réagi, sous-réagi, ou réagi de façon disciplinée pendant ces
épisodes de stress.

Principe
--------
Pour chaque événement dont la fenêtre chevauche l'historique réel du fonds
(entre la première NAV et l'as_of) :
  1. Activité  : volume brut tradé pendant la fenêtre vs volume brut "normal"
                 du fonds (moyenne journalière hors fenêtres d'événements) →
                 activity_ratio. >1 = plus actif que d'habitude, <1 = moins.
  2. Direction : flux net acheteur ou vendeur pendant la fenêtre (a-t-on
                 renforcé ou réduit l'exposition pendant le choc ?).
  3. Timing    : si le Bloc H (Timing Score) est disponible, moyenne des
                 scores d'entrée/sortie des trades exécutés dans la fenêtre —
                 ces trades ont-ils été bien ou mal placés dans le range de
                 prix local ?

Ces trois signaux sont combinés en une étiquette qualitative (sur-réaction,
sous-réaction, réaction opportuniste, réaction disciplinée...).

Limites connues
----------------
- Le calendrier est une liste statique, non exhaustive, à enrichir au besoin
  (voir MARKET_EVENTS ci-dessous — ajouter une entrée suffit).
- Les fonds récents (émis après 2023) ne recoupent souvent aucun des grands
  chocs historiques (subprimes, COVID) — le bloc le signale explicitement
  plutôt que d'afficher des lignes vides ou trompeuses.
- Échantillon parfois très faible (fenêtre courte, fonds peu actif) — chaque
  événement rapporte son propre n_trades pour que le lecteur juge la
  significativité lui-même.
"""
from __future__ import annotations

import datetime
from typing import Optional

import numpy as np
import pandas as pd

# ── Calendrier des chocs de marché ──────────────────────────────────────
# Fenêtres larges mais délimitées (peak-to-trough ou épisode aigu reconnu).
# Ajouter une entrée ici suffit à l'intégrer au Bloc K — aucun autre code à
# toucher.

MARKET_EVENTS: list[dict] = [
    {"id": "gfc_2008", "label": "Crise des subprimes (Lehman Brothers)",
     "category": "Crise financière", "start": "2008-09-15", "end": "2009-03-09"},
    {"id": "eu_debt_2011", "label": "Crise de la dette souveraine européenne",
     "category": "Crise financière", "start": "2011-07-01", "end": "2011-10-03"},
    {"id": "china_2015", "label": "Chine — Black Monday / dévaluation du yuan",
     "category": "Choc Chine", "start": "2015-08-18", "end": "2015-08-26"},
    {"id": "brexit_2016", "label": "Référendum Brexit",
     "category": "Choc politique", "start": "2016-06-23", "end": "2016-06-27"},
    {"id": "selloff_2018q4", "label": "Correction T4 2018 (resserrement Fed)",
     "category": "Correction de marché", "start": "2018-10-01", "end": "2018-12-24"},
    {"id": "covid_2020", "label": "Krach COVID-19",
     "category": "Pandémie", "start": "2020-02-19", "end": "2020-03-23"},
    {"id": "china_2021", "label": "Chine — répression réglementaire tech / Evergrande",
     "category": "Choc Chine", "start": "2021-07-01", "end": "2021-10-31"},
    {"id": "bear_2022", "label": "Marché baissier 2022 (hausse des taux)",
     "category": "Correction de marché", "start": "2022-01-03", "end": "2022-10-13"},
    {"id": "svb_2023", "label": "Crise des banques régionales US (SVB)",
     "category": "Crise financière", "start": "2023-03-08", "end": "2023-03-20"},
    {"id": "china_property_2023", "label": "Chine — crise immobilière (Country Garden)",
     "category": "Choc Chine", "start": "2023-08-01", "end": "2023-10-31"},
]


def _parse(d: str) -> datetime.date:
    return datetime.datetime.strptime(d, "%Y-%m-%d").date()


def _as_date(v) -> Optional[datetime.date]:
    if v is None:
        return None
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    try:
        return datetime.datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _label(activity_ratio: Optional[float], net_flow: float, n_trades: int,
          timing_delta: Optional[float]) -> str:
    if n_trades == 0:
        return "Aucune réaction — aucun ordre pendant la période"
    if activity_ratio is None:
        base = "Activité présente mais non quantifiable (historique de référence insuffisant)"
    elif activity_ratio < 0.4:
        base = "Sous-réaction — activité nettement inférieure à la normale"
    elif activity_ratio > 1.8:
        if net_flow < 0:
            base = "Sur-réaction — désengagement marqué, au-delà de l'activité habituelle"
        else:
            base = "Réaction opportuniste — renforcement marqué pendant l'épisode"
    else:
        base = "Réaction proportionnée — activité proche de la normale du fonds"

    if timing_delta is not None and abs(timing_delta) >= 0.15:
        if timing_delta <= -0.15:
            base += " ; trades mal placés dans le range de prix local (timing sous l'aléatoire)"
        else:
            base += " ; trades bien placés dans le range de prix local (timing au-dessus de l'aléatoire)"
    return base


def compute_market_shocks(
    orders: list[dict],
    meta: dict,
    block_h: Optional[dict] = None,
) -> dict:
    """Bloc K — Réactivité aux chocs de marché.

    Parameters
    ----------
    orders   : liste normalisée d'ordres (amc_orderbook.load_orders / load_study_data —
               déjà corrigés des splits). Utilise state, date, side, notional_prod.
    meta     : result["meta"] du run_study courant (nav_start_date, as_of).
    block_h  : result["block_h"] si disponible — réutilise les scores de timing
               par trade pour juger la qualité d'exécution pendant chaque fenêtre.
    """
    done = [o for o in orders if o.get("state") == "Done" and o.get("date") is not None]
    if not done:
        return {"available": False, "error": "Aucun ordre exécuté disponible."}

    fund_start = _as_date(meta.get("nav_start_date")) or min(_as_date(o["date"]) for o in done)
    fund_end   = _as_date(meta.get("as_of")) or max(_as_date(o["date"]) for o in done)
    if fund_start is None or fund_end is None or fund_start > fund_end:
        return {"available": False, "error": "Période d'activité du fonds indéterminée."}

    applicable = [
        {**e, "start_d": _parse(e["start"]), "end_d": _parse(e["end"])}
        for e in MARKET_EVENTS
    ]
    applicable = [
        e for e in applicable
        if e["start_d"] <= fund_end and e["end_d"] >= fund_start
    ]
    n_skipped = len(MARKET_EVENTS) - len(applicable)

    if not applicable:
        return {
            "available": True,
            "n_events_applicable": 0,
            "n_events_total": len(MARKET_EVENTS),
            "fund_start": fund_start.isoformat(),
            "fund_end": fund_end.isoformat(),
            "events": [],
            "interpretation": (
                f"Aucun des {len(MARKET_EVENTS)} chocs de marché du calendrier ne chevauche "
                f"l'historique de ce fonds ({fund_start.isoformat()} → {fund_end.isoformat()}). "
                "Fonds trop récent pour ce type d'analyse — pertinent surtout pour des "
                "historiques couvrant au moins un épisode de stress (COVID, 2022, SVB...)."
            ),
        }

    # ── Baseline d'activité "normale" : notional brut / jour, hors fenêtres d'événements ──
    event_ranges = [(e["start_d"], e["end_d"]) for e in applicable]

    def _in_any_event(d: datetime.date) -> bool:
        return any(s <= d <= e for s, e in event_ranges)

    per_order = []
    for o in done:
        d = _as_date(o["date"])
        if d is None or d < fund_start or d > fund_end:
            continue
        notional = float(o.get("notional_prod") or 0.0)
        signed = notional if str(o.get("side", "")).upper() == "BUY" else -notional
        per_order.append((d, notional, signed))

    baseline_orders = [p for p in per_order if not _in_any_event(p[0])]
    baseline_days = max((fund_end - fund_start).days -
                        sum((e - s).days + 1 for s, e in event_ranges), 1)
    baseline_gross = sum(p[1] for p in baseline_orders)
    baseline_daily_notional = baseline_gross / baseline_days if baseline_days > 0 else 0.0

    # per-trade timing scores (Bloc H), indexé par (isin ou nom, date) pour recoupement
    h_by_key: dict[tuple, float] = {}
    h_global_mean = None
    if block_h and block_h.get("available"):
        h_global_mean = block_h.get("global_score_mean")
        for t in block_h.get("trades") or []:
            if t.get("available") and t.get("score") is not None:
                key = (t.get("isin") or t.get("name"), t.get("date"))
                h_by_key[key] = t["score"]

    events_out = []
    for e in applicable:
        s, en = e["start_d"], e["end_d"]
        window_days = (en - s).days + 1
        window_orders = [p for p in per_order if s <= p[0] <= en]
        n_trades = len(window_orders)
        gross = sum(p[1] for p in window_orders)
        net_flow = sum(p[2] for p in window_orders)
        expected = baseline_daily_notional * window_days
        activity_ratio = round(gross / expected, 2) if expected > 1e-9 else None

        # timing quality of trades executed inside the window (needs isin+date match to Bloc H)
        window_dates = {p[0].isoformat() for p in window_orders}
        matched_scores = [
            score for (isin_or_name, date_str), score in h_by_key.items()
            if date_str in window_dates
        ]
        avg_timing = round(float(np.mean(matched_scores)), 3) if matched_scores else None
        timing_delta = (round(avg_timing - 0.5, 3) if avg_timing is not None else None)

        events_out.append({
            "id": e["id"],
            "label": e["label"],
            "category": e["category"],
            "start": e["start"],
            "end": e["end"],
            "window_days": window_days,
            "n_trades": n_trades,
            "gross_notional": round(gross, 0),
            "net_flow": round(net_flow, 0),
            "expected_notional": round(expected, 0) if expected else None,
            "activity_ratio": activity_ratio,
            "avg_timing_score": avg_timing,
            "timing_delta_vs_random": timing_delta,
            "n_trades_with_timing_data": len(matched_scores),
            "reaction_label": _label(activity_ratio, net_flow, n_trades, timing_delta),
        })

    events_out.sort(key=lambda x: x["start"])
    n_with_trades = sum(1 for e in events_out if e["n_trades"] > 0)

    interpretation = (
        f"{len(applicable)} des {len(MARKET_EVENTS)} chocs de marché du calendrier chevauchent "
        f"l'historique de ce fonds ({fund_start.isoformat()} → {fund_end.isoformat()}) ; "
        f"{n_with_trades} montrent une activité de trading pendant la fenêtre. "
        f"Volume journalier de référence (hors fenêtres de choc) : "
        f"{baseline_daily_notional:,.0f} par jour."
    )
    if n_skipped:
        interpretation += (
            f" {n_skipped} événement(s) du calendrier tombent hors de l'historique du fonds "
            "et ne sont pas montrés."
        )

    return {
        "available": True,
        "n_events_applicable": len(applicable),
        "n_events_total": len(MARKET_EVENTS),
        "fund_start": fund_start.isoformat(),
        "fund_end": fund_end.isoformat(),
        "baseline_daily_notional": round(baseline_daily_notional, 0),
        "events": events_out,
        "interpretation": interpretation,
        "warning": (
            "Bloc H (Timing Score) indisponible — la dimension qualité d'exécution "
            "(bien/mal timé pendant le choc) n'est pas incluse, seule l'activité/direction l'est."
            if not (block_h and block_h.get("available")) else None
        ),
    }
