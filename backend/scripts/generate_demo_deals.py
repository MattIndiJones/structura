#!/usr/bin/env python3
"""Générateur paramétrable de deals de démonstration pour l'espace de booking.

Idempotent par construction : chaque lancement PURGE d'abord tous les deals
dont la référence commence par le préfixe demo (voir --ref-prefix, défaut
"DEMO"), tous utilisateurs confondus, puis en regénère un nouveau lot — on
peut donc relancer librement en ajustant les options pour affiner le jeu de
données, sans jamais accumuler de doublons. Utiliser --no-purge pour
désactiver ce comportement et empiler les lots.

Couvre tous les grands types de produits structurés (autocall Athena,
Athena dégressif, Phoenix mémoire, autocall gear put, Barrier Reverse
Convertible, Reverse Convertible, Capital Garanti, Twin Win, Shark,
Booster, options vanille call/put/spread/digital) et toutes les maturités
(bornées par --maturity-min/--maturity-max), sur des statuts actif / callé /
échu (final ou KI) tirés aléatoirement (--status-mix) mais toujours
mécaniquement cohérents avec la formule du payoff — le classement
final/KI est dérivé du même seuil (paiement à maturité < 99.5% du nominal)
que celui utilisé par l'app en production (voir api/deals.py:_evaluate_lifecycle),
pas choisi à la main.

Usage (depuis la racine du repo) :
    .venv\\Scripts\\python.exe backend\\scripts\\generate_demo_deals.py
    .venv\\Scripts\\python.exe backend\\scripts\\generate_demo_deals.py --help
    .venv\\Scripts\\python.exe backend\\scripts\\generate_demo_deals.py --count 100 --users test --seed 7
    .venv\\Scripts\\python.exe backend\\scripts\\generate_demo_deals.py --types athena,phoenix,shark --status-mix actif:70,calle:15,echu_final:10,echu_ki:5
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlmodel import Session, select, delete

from backend.app.db.database import engine, init_db
from backend.app.db.models import (
    Deal, DealEvent, User, Alert, ShockRun, Document,
    KidRecord, EmtRecord, Counterparty,
)
from backend.app.api.portfolios import get_or_create_default_portfolio


# ══════════════════════════════════════════════════════════════════════════
# Sous-jacents
# ══════════════════════════════════════════════════════════════════════════

def ul(name, ticker, s0, sigma, q=1.5, ccy="USD"):
    return {"name": name, "ticker": ticker, "ccy": ccy, "sigma": sigma, "q": q,
            "s0": s0, "sigma_fx": 0, "rho_sfx": 0, "model": "GBM", "v0": 0.04,
            "kappa": 2.0, "theta_h": 0.04, "xi": 0.4, "rho_h": -0.7,
            "alpha": 0.3, "beta": 0.5, "rho_s": -0.3, "nu": 0.3, "lv_surface": []}


UNDERLYINGS = [
    ul("S&P 500",      "^GSPC",     5600,  16, 1.5),
    ul("Nvidia",       "NVDA",      140,   45, 0.0),
    ul("Apple",        "AAPL",      225,   22, 0.5),
    ul("Microsoft",    "MSFT",      430,   20, 0.8),
    ul("Amazon",       "AMZN",      205,   28, 0.0),
    ul("Alphabet",     "GOOGL",     170,   24, 0.0),
    ul("Meta",         "META",      560,   35, 0.4),
    ul("Tesla",        "TSLA",      250,   55, 0.0),
    ul("Nike",         "NKE",       80,    25, 1.8),
    ul("Pfizer",       "PFE",       28,    20, 4.5),
    ul("Alibaba",      "BABA",      85,    38, 0.0),
    ul("EuroStoxx 50", "^STOXX50E", 4950,  18, 2.5, ccy="EUR"),
    ul("DAX",          "^GDAXI",    18800, 19, 2.8, ccy="EUR"),
    ul("Nasdaq 100",   "^NDX",      19500, 20, 0.6),
    ul("LVMH",         "MC.PA",     650,   26, 2.0, ccy="EUR"),
    ul("ASML",         "ASML.AS",   700,   33, 0.9, ccy="EUR"),
]

FALLBACK_CPTYS = [
    "BNP Paribas", "Société Générale", "UBS", "Barclays", "Goldman Sachs",
    "JP Morgan", "Deutsche Bank", "Natixis", "Morgan Stanley", "Citigroup",
    "HSBC", "Nomura", "Santander", "Crédit Agricole CIB", "Mizuho", "Bank of America",
]


# ══════════════════════════════════════════════════════════════════════════
# Templates de payoff (PayScript) — un par type de produit
# ══════════════════════════════════════════════════════════════════════════

def _obs_str(dates: list[float]) -> str:
    return ", ".join(f"{d:g}" for d in dates)


def script_athena(obs, coupon, ac_bar, ki_bar):
    return (
        f"PARAM COUPON = {coupon}%\nPARAM M_AC_BAR = {ac_bar}%\nPARAM M_KI_BAR = {ki_bar}%\n\n"
        f"AT {_obs_str(obs)}:\n  SET CALL = INDIC(WOF >= M_AC_BAR)\n"
        f"  PAY CALL * COUPON * INDEX\n  PAY CALL * 1\n  IF CALL = 1:\n    STOP\n\n"
        f"AT MATURITY:\n  SET KI = INDIC(WOF < M_KI_BAR)\n  PAY (1 - KI) * 1\n  PAY KI * WOF"
    )


def script_athena_degr(obs, coupon, ac_bar_seed, ki_bar):
    return (
        f"PARAM COUPON = {coupon}%\nPARAM() M_AC_BAR = {ac_bar_seed}%\nPARAM M_KI_BAR = {ki_bar}%\n\n"
        f"AT {_obs_str(obs)}:\n  SET CALL = INDIC(WOF >= M_AC_BAR)\n"
        f"  PAY CALL * COUPON * INDEX\n  PAY CALL * 1\n  IF CALL = 1:\n    STOP\n\n"
        f"AT MATURITY:\n  SET KI = INDIC(WOF < M_KI_BAR)\n  PAY (1 - KI) * 1\n  PAY KI * WOF"
    )


def script_phoenix(obs, coupon, cpn_bar, ki_bar):
    return (
        f"PARAM COUPON = {coupon}%\nPARAM M_AC_BAR = 100%\nPARAM M_CPN_BAR = {cpn_bar}%\n"
        f"PARAM M_KI_BAR = {ki_bar}%\n\n"
        f"AT {_obs_str(obs)}:\n  SET CALL = INDIC(WOF >= M_AC_BAR)\n  SET CPN  = INDIC(WOF >= M_CPN_BAR)\n"
        f"  PAY CPN * COUPON\n  PAY CALL * 1\n  IF CALL = 1:\n    STOP\n\n"
        f"AT MATURITY:\n  SET KI = INDIC(WOF < M_KI_BAR)\n  PAY (1 - KI) * 1\n  PAY KI * WOF"
    )


def script_gear_put(obs, coupon, ac_bar, put_strike, gearing):
    return (
        f"PARAM COUPON = {coupon}%\nPARAM M_AC_BAR = {ac_bar}%\nPARAM M_PUT_STRIKE = {put_strike}%\n"
        f"PARAM GEARING = {gearing}%\n\n"
        f"AT {_obs_str(obs)}:\n  SET CALL = INDIC(WOF >= M_AC_BAR)\n"
        f"  PAY CALL * COUPON\n  PAY CALL * 1\n  IF CALL = 1:\n    STOP\n\n"
        f"AT MATURITY:\n  SET LOSS = MIN(1, GEARING * MAX(0, 1 - WOF/M_PUT_STRIKE))\n"
        f'  PAY 1 "Remboursement nominal"\n  PAY -1 * LOSS "Put vendu à effet de levier"'
    )


def script_brc(coupon, ki_bar):
    return (
        f"PARAM COUPON = {coupon}%\nPARAM M_KI_BAR = {ki_bar}%\n\n"
        f"AT MATURITY:\n  PAY COUPON\n  SET KI = INDIC(WOF < M_KI_BAR)\n"
        f"  PAY (1 - KI) * 1\n  PAY KI * WOF"
    )


def script_rc(coupon, put_strike):
    return (
        f"PARAM COUPON = {coupon}%\nPARAM M_PUT_STRIKE = {put_strike}%\n\n"
        f"AT MATURITY:\n  PAY COUPON\n  SET PROTECTED = INDIC(WOF >= M_PUT_STRIKE)\n"
        f"  PAY PROTECTED * 1\n  PAY (1 - PROTECTED) * WOF"
    )


def script_cg(parti):
    return f"PARAM M_PARTI = {parti}%\n\nAT MATURITY:\n  PAY 1\n  PAY MAX(0, WOF - 1) * M_PARTI"


def script_twin_win(ki_bar, cap):
    return (
        f"PARAM M_KI_BAR = {ki_bar}%\nPARAM M_CAP = {cap}%\n\n"
        f"AT MATURITY:\n  SET BREACHED = INDIC(WOF_MIN < M_KI_BAR)\n"
        f"  SET UPS = MIN(M_CAP, MAX(1, WOF))\n  SET DNS = MIN(M_CAP, MAX(1, 2 - WOF))\n"
        f"  PAY (1 - BREACHED) * MAX(UPS, DNS)\n  PAY BREACHED * WOF"
    )


def script_shark(ko_bar, coupon, parti):
    return (
        f"PARAM M_KO_BAR = {ko_bar}%\nPARAM COUPON = {coupon}%\nPARAM M_PARTI = {parti}%\n\n"
        f"AT MATURITY:\n  SET KO = INDIC(BOF_MAX >= M_KO_BAR)\n"
        f"  PAY KO * (1 + COUPON)\n  PAY (1 - KO) * (1 + MAX(0, WOF - 1) * M_PARTI)"
    )


def script_booster(parti, cap):
    return (
        f"PARAM M_PARTI = {parti}%\nPARAM M_CAP = {cap}%\nPARAM M_FLOOR = 100%\n\n"
        f"AT MATURITY:\n  SET IS_UP = INDIC(WOF >= 1)\n"
        f"  SET BOOSTED = MIN(M_CAP, M_FLOOR + (WOF - 1) * M_PARTI)\n"
        f"  PAY IS_UP * BOOSTED\n  PAY (1 - IS_UP) * MIN(1, WOF)"
    )


def script_call(strike):
    return f"PARAM STRIKE = {strike}%\n\nAT MATURITY:\n  PAY MAX(0, WOF - STRIKE)"


def script_put(strike):
    return f"PARAM STRIKE = {strike}%\n\nAT MATURITY:\n  PAY MAX(0, STRIKE - WOF)"


def script_call_spread(k1, k2):
    return f"PARAM K1 = {k1}%\nPARAM K2 = {k2}%\n\nAT MATURITY:\n  PAY MAX(0, MIN(WOF - K1, K2 - K1))"


def script_digital(strike, rebate):
    return (
        f"PARAM STRIKE = {strike}%\nPARAM REBATE = {rebate}%\n\n"
        f"AT MATURITY:\n  SET ITM = INDIC(WOF >= STRIKE)\n  PAY ITM * REBATE"
    )


# ══════════════════════════════════════════════════════════════════════════
# Tirage des paramètres + résolution du payout — un couple par template
# ══════════════════════════════════════════════════════════════════════════

def _pct(rng, lo, hi, step=1):
    n = round(rng.uniform(lo, hi) / step) * step
    return int(n) if float(n).is_integer() else round(n, 2)


def _draw_perf(rng, target, bar, lo=0.30, hi=1.45):
    """target: 'ki' (viser un breach, sous 'bar') ou 'final' (viser une
    protection, au-dessus de 'bar'). bar est une fraction (0.60 = 60%)."""
    if target == "ki":
        return round(rng.uniform(lo, max(lo + 0.01, bar - 0.02)), 4)
    return round(rng.uniform(min(bar + 0.03, hi - 0.05), hi), 4)


@dataclass
class Outcome:
    obs: list             # dates AT (year-fractions), toujours >= 1 élément (le dernier = maturité)
    freq_label: str
    user_params: dict      # PARAM overrides — valeurs FRACTIONNAIRES (déjà /100), y compris listes
    display_params: dict    # mêmes clés, valeurs affichables en % (pour info/print)
    realized_payout: Optional[float]
    resolution_outcome: Optional[str]     # None | 'callé' | 'ki' | 'final'
    res_obs_index: Optional[int]          # index (1-based) de l'obs de call, si callé


ALLOWED_STATUSES = {
    "athena":       ["actif", "calle", "echu_final", "echu_ki"],
    "athena_degr":  ["actif", "calle", "echu_final", "echu_ki"],
    "phoenix":      ["actif", "calle", "echu_final", "echu_ki"],
    "gear_put":     ["actif", "calle", "echu_final", "echu_ki"],
    "brc":          ["actif", "echu_final", "echu_ki"],
    "rc":           ["actif", "echu_final", "echu_ki"],
    "twin_win":     ["actif", "echu_final", "echu_ki"],
    "booster":      ["actif", "echu_final", "echu_ki"],
    "cg":           ["actif", "echu_final"],           # capital garanti : jamais de KI possible
    "shark":        ["actif", "echu_final"],           # capital garanti : jamais de KI possible
    "call":         ["actif", "echu_final"],
    "put":          ["actif", "echu_final"],
    "call_spread":  ["actif", "echu_final"],
    "digital":      ["actif", "echu_final"],
}


def build_deal_terms(key: str, rng: random.Random, status: str, obs_dates: list, freq_label: str) -> Outcome:
    n = len(obs_dates)

    if key in ("athena", "athena_degr"):
        coupon_pct = _pct(rng, 6, 14, 0.5)
        ac_bar_pct = _pct(rng, 95, 105, 5) if key == "athena" else _pct(rng, 100, 110, 5)
        ki_bar_pct = _pct(rng, 50, 70, 5)
        coupon, ki_bar = coupon_pct / 100, ki_bar_pct / 100
        up = {"COUPON": coupon}
        disp = {"COUPON": coupon_pct, "M_KI_BAR": ki_bar_pct}
        if key == "athena":
            up["M_AC_BAR"] = ac_bar_pct / 100
            disp["M_AC_BAR"] = ac_bar_pct
        else:
            # Barrière dégressive : part du seed puis décroît de 5pt par obs, plancher 80%.
            up["M_AC_BAR"] = [round(max(80, ac_bar_pct - 5 * i) / 100, 4) for i in range(n)]
            disp["M_AC_BAR"] = up["M_AC_BAR"]
        up["M_KI_BAR"] = ki_bar
        if status == "actif":
            return Outcome(obs_dates, freq_label, up, disp, None, None, None)
        if status == "calle":
            idx = rng.randint(1, n)
            payout = round(1 + coupon * idx, 4)
            return Outcome(obs_dates, freq_label, up, disp, payout, "callé", idx)
        target = "ki" if status == "echu_ki" else "final"
        wof = _draw_perf(rng, target, ki_bar)
        payout = 1.0 if wof >= ki_bar else wof
        outcome = "ki" if payout < 0.995 else "final"
        return Outcome(obs_dates, freq_label, up, disp, round(payout, 4), outcome, None)

    if key == "phoenix":
        coupon_pct = _pct(rng, 1.5, 3.5, 0.25)
        cpn_bar_pct = _pct(rng, 65, 80, 5)
        ki_bar_pct = _pct(rng, 50, 70, 5)
        coupon, cpn_bar, ki_bar = coupon_pct / 100, cpn_bar_pct / 100, ki_bar_pct / 100
        up = {"COUPON": coupon, "M_CPN_BAR": cpn_bar, "M_KI_BAR": ki_bar}
        disp = {"COUPON": coupon_pct, "M_CPN_BAR": cpn_bar_pct, "M_KI_BAR": ki_bar_pct}
        if status == "actif":
            return Outcome(obs_dates, freq_label, up, disp, None, None, None)
        if status == "calle":
            idx = rng.randint(1, n)
            missed = rng.randint(0, min(3, idx - 1)) if idx > 1 else 0
            payout = round(1 + coupon + missed * coupon, 4)
            return Outcome(obs_dates, freq_label, up, disp, payout, "callé", idx)
        target = "ki" if status == "echu_ki" else "final"
        wof = _draw_perf(rng, target, ki_bar)
        maturity_component = 1.0 if wof >= ki_bar else wof
        paid_periods = rng.randint(0, max(0, n - 1))
        total = round(paid_periods * coupon + maturity_component, 4)
        outcome = "ki" if maturity_component < 0.995 else "final"
        return Outcome(obs_dates, freq_label, up, disp, total, outcome, None)

    if key == "gear_put":
        coupon_pct = _pct(rng, 8, 14, 0.5)
        ac_bar_pct = _pct(rng, 95, 105, 5)
        put_strike_pct = _pct(rng, 85, 100, 5)
        gearing_pct = _pct(rng, 120, 180, 10)
        coupon, put_strike, gearing = coupon_pct / 100, put_strike_pct / 100, gearing_pct / 100
        up = {"COUPON": coupon, "M_AC_BAR": ac_bar_pct / 100, "M_PUT_STRIKE": put_strike, "GEARING": gearing}
        disp = {"COUPON": coupon_pct, "M_AC_BAR": ac_bar_pct, "M_PUT_STRIKE": put_strike_pct, "GEARING": gearing_pct}
        if status == "actif":
            return Outcome(obs_dates, freq_label, up, disp, None, None, None)
        if status == "calle":
            idx = rng.randint(1, n)
            return Outcome(obs_dates, freq_label, up, disp, round(1 + coupon, 4), "callé", idx)
        target = "ki" if status == "echu_ki" else "final"
        wof = _draw_perf(rng, target, put_strike)
        loss = min(1.0, gearing * max(0.0, 1 - wof / put_strike))
        payout = round(1 - loss, 4)
        outcome = "ki" if payout < 0.995 else "final"
        return Outcome(obs_dates, freq_label, up, disp, payout, outcome, None)

    if key in ("brc", "rc"):
        coupon_pct = _pct(rng, 8, 16, 0.5)
        bar_pct = _pct(rng, 55, 70, 5) if key == "brc" else _pct(rng, 85, 100, 5)
        bar_name = "M_KI_BAR" if key == "brc" else "M_PUT_STRIKE"
        coupon, bar = coupon_pct / 100, bar_pct / 100
        up = {"COUPON": coupon, bar_name: bar}
        disp = {"COUPON": coupon_pct, bar_name: bar_pct}
        if status == "actif":
            return Outcome(obs_dates, freq_label, up, disp, None, None, None)
        target = "ki" if status == "echu_ki" else "final"
        wof = _draw_perf(rng, target, bar)
        capital = 1.0 if wof >= bar else wof
        payout = round(coupon + capital, 4)
        outcome = "ki" if payout < 0.995 else "final"
        return Outcome(obs_dates, freq_label, up, disp, payout, outcome, None)

    if key == "cg":
        parti_pct = _pct(rng, 60, 130, 5)
        parti = parti_pct / 100
        up = {"M_PARTI": parti}
        disp = {"M_PARTI": parti_pct}
        if status == "actif":
            return Outcome(obs_dates, freq_label, up, disp, None, None, None)
        wof = round(rng.uniform(0.70, 1.60), 4)
        payout = round(1 + max(0.0, wof - 1) * parti, 4)
        return Outcome(obs_dates, freq_label, up, disp, payout, "final", None)

    if key == "twin_win":
        ki_bar_pct = _pct(rng, 55, 75, 5)
        cap_pct = _pct(rng, 130, 160, 5)
        ki_bar, cap = ki_bar_pct / 100, cap_pct / 100
        up = {"M_KI_BAR": ki_bar, "M_CAP": cap}
        disp = {"M_KI_BAR": ki_bar_pct, "M_CAP": cap_pct}
        if status == "actif":
            return Outcome(obs_dates, freq_label, up, disp, None, None, None)
        target = "ki" if status == "echu_ki" else "final"
        wof = _draw_perf(rng, target, ki_bar, lo=0.30, hi=1.60)
        if wof < ki_bar:
            payout = wof
        else:
            payout = max(min(cap, max(1.0, wof)), min(cap, max(1.0, 2 - wof)))
        outcome = "ki" if payout < 0.995 else "final"
        return Outcome(obs_dates, freq_label, up, disp, round(payout, 4), outcome, None)

    if key == "shark":
        ko_bar_pct = _pct(rng, 120, 140, 5)
        coupon_pct = _pct(rng, 10, 20, 1)
        parti_pct = _pct(rng, 80, 120, 5)
        ko_bar, coupon, parti = ko_bar_pct / 100, coupon_pct / 100, parti_pct / 100
        up = {"M_KO_BAR": ko_bar, "COUPON": coupon, "M_PARTI": parti}
        disp = {"M_KO_BAR": ko_bar_pct, "COUPON": coupon_pct, "M_PARTI": parti_pct}
        if status == "actif":
            return Outcome(obs_dates, freq_label, up, disp, None, None, None)
        wof = round(rng.uniform(0.60, 1.50), 4)
        bof_max = max(wof, round(rng.uniform(0.90, 1.50), 4))
        ko = bof_max >= ko_bar
        payout = round((1 + coupon) if ko else (1 + max(0.0, wof - 1) * parti), 4)
        return Outcome(obs_dates, freq_label, up, disp, payout, "final", None)

    if key == "booster":
        parti_pct = _pct(rng, 150, 250, 10)
        cap_pct = _pct(rng, 130, 170, 5)
        parti, cap = parti_pct / 100, cap_pct / 100
        up = {"M_PARTI": parti, "M_CAP": cap}
        disp = {"M_PARTI": parti_pct, "M_CAP": cap_pct}
        if status == "actif":
            return Outcome(obs_dates, freq_label, up, disp, None, None, None)
        target = "ki" if status == "echu_ki" else "final"
        if target == "ki":
            wof = round(rng.uniform(0.50, 0.94), 4)
            payout = min(1.0, wof)
        else:
            wof = round(rng.uniform(1.0, 1.40), 4)
            payout = min(cap, 1 + (wof - 1) * parti)
        outcome = "ki" if payout < 0.995 else "final"
        return Outcome(obs_dates, freq_label, up, disp, round(payout, 4), outcome, None)

    if key in ("call", "put"):
        strike_pct = _pct(rng, 90, 110, 5)
        strike = strike_pct / 100
        up, disp = {"STRIKE": strike}, {"STRIKE": strike_pct}
        if status == "actif":
            return Outcome(obs_dates, freq_label, up, disp, None, None, None)
        wof = round(rng.uniform(0.60, 1.60), 4)
        payout = round(max(0.0, wof - strike) if key == "call" else max(0.0, strike - wof), 4)
        outcome = "ki" if payout < 0.995 else "final"
        return Outcome(obs_dates, freq_label, up, disp, payout, outcome, None)

    if key == "call_spread":
        k1_pct = _pct(rng, 95, 105, 5)
        k2_pct = _pct(rng, 115, 135, 5)
        k1, k2 = k1_pct / 100, k2_pct / 100
        up, disp = {"K1": k1, "K2": k2}, {"K1": k1_pct, "K2": k2_pct}
        if status == "actif":
            return Outcome(obs_dates, freq_label, up, disp, None, None, None)
        wof = round(rng.uniform(0.80, 1.60), 4)
        payout = round(max(0.0, min(wof - k1, k2 - k1)), 4)
        outcome = "ki" if payout < 0.995 else "final"
        return Outcome(obs_dates, freq_label, up, disp, payout, outcome, None)

    if key == "digital":
        strike_pct = _pct(rng, 90, 110, 5)
        rebate_pct = _pct(rng, 5, 15, 1)
        strike, rebate = strike_pct / 100, rebate_pct / 100
        up, disp = {"STRIKE": strike, "REBATE": rebate}, {"STRIKE": strike_pct, "REBATE": rebate_pct}
        if status == "actif":
            return Outcome(obs_dates, freq_label, up, disp, None, None, None)
        wof = round(rng.uniform(0.70, 1.30), 4)
        payout = round(rebate if wof >= strike else 0.0, 4)
        outcome = "ki" if payout < 0.995 else "final"
        return Outcome(obs_dates, freq_label, up, disp, payout, outcome, None)

    raise ValueError(f"Template inconnu: {key}")


def build_script_text(key: str, obs: list, disp: dict) -> str:
    if key == "athena":
        return script_athena(obs, disp["COUPON"], disp["M_AC_BAR"], disp["M_KI_BAR"])
    if key == "athena_degr":
        seed = round(disp["M_AC_BAR"][0] * 100)
        return script_athena_degr(obs, disp["COUPON"], seed, disp["M_KI_BAR"])
    if key == "phoenix":
        return script_phoenix(obs, disp["COUPON"], disp["M_CPN_BAR"], disp["M_KI_BAR"])
    if key == "gear_put":
        return script_gear_put(obs, disp["COUPON"], disp["M_AC_BAR"], disp["M_PUT_STRIKE"], disp["GEARING"])
    if key == "brc":
        return script_brc(disp["COUPON"], disp["M_KI_BAR"])
    if key == "rc":
        return script_rc(disp["COUPON"], disp["M_PUT_STRIKE"])
    if key == "cg":
        return script_cg(disp["M_PARTI"])
    if key == "twin_win":
        return script_twin_win(disp["M_KI_BAR"], disp["M_CAP"])
    if key == "shark":
        return script_shark(disp["M_KO_BAR"], disp["COUPON"], disp["M_PARTI"])
    if key == "booster":
        return script_booster(disp["M_PARTI"], disp["M_CAP"])
    if key == "call":
        return script_call(disp["STRIKE"])
    if key == "put":
        return script_put(disp["STRIKE"])
    if key == "call_spread":
        return script_call_spread(disp["K1"], disp["K2"])
    if key == "digital":
        return script_digital(disp["STRIKE"], disp["REBATE"])
    raise ValueError(f"Template inconnu: {key}")


PRODUCT_LABELS = {
    "athena": "Autocall Athena", "athena_degr": "Autocall Athena Dégressif",
    "phoenix": "Phoenix Mémoire", "gear_put": "Autocall Gear Put",
    "brc": "Barrier RC", "rc": "Reverse Convertible", "cg": "Capital Garanti",
    "twin_win": "Twin Win", "shark": "Shark", "booster": "Booster",
    "call": "Call Vanille", "put": "Put Vanille", "call_spread": "Call Spread",
    "digital": "Digital",
}

# Marge (fair_value vs 100%) typique par famille — cohérence des MtM affichés.
FV_MARGIN = {
    "athena": 2.5, "athena_degr": 2.7, "phoenix": 1.8, "gear_put": 2.2,
    "brc": 2.0, "rc": 1.5, "cg": 3.8, "twin_win": 3.0, "shark": 3.5,
    "booster": 2.8, "call": 1.0, "put": 1.0, "call_spread": 1.2, "digital": 1.5,
}

# Familles : "periodic" (obs répétées + call possible) vs "maturity" (une seule obs).
PERIODIC_KEYS = {"athena", "athena_degr", "phoenix", "gear_put"}

# Bornes de maturité typiques (années), intersectées avec --maturity-min/max.
FAMILY_T_RANGE = {
    "athena": (1, 5), "athena_degr": (2, 5), "phoenix": (1.5, 4), "gear_put": (1.5, 4),
    "brc": (0.5, 2), "rc": (0.5, 1.5), "cg": (3, 8), "twin_win": (1, 3),
    "shark": (1, 3), "booster": (1, 3),
    "call": (0.25, 2), "put": (0.25, 2), "call_spread": (0.25, 2), "digital": (0.25, 1.5),
}

DEFAULT_WEIGHTS = {
    "athena": 5, "athena_degr": 2, "phoenix": 3, "gear_put": 2,
    "brc": 2, "rc": 2, "cg": 2, "twin_win": 1.5, "shark": 1.5, "booster": 1,
    "call": 0.5, "put": 0.5, "call_spread": 0.5, "digital": 0.5,
}

DEFAULT_STATUS_MIX = {"actif": 45, "calle": 25, "echu_final": 18, "echu_ki": 12}

FREQ_CHOICES = [("quarterly", 0.25, 0.50), ("semiannual", 0.5, 0.35), ("annual", 1.0, 0.15)]


# ══════════════════════════════════════════════════════════════════════════
# Helpers date / calendrier
# ══════════════════════════════════════════════════════════════════════════

def dy(d: str, yrs: float) -> str:
    return (date.fromisoformat(d) + timedelta(days=round(yrs * 365.25))).isoformat()


def obs_schedule(T: float, step: float) -> list[float]:
    n = max(1, round(T / step))
    return [round(step * i, 4) for i in range(1, n + 1)]


def pick_weighted(rng: random.Random, weights: dict) -> str:
    keys = list(weights.keys())
    w = [max(0.0001, weights[k]) for k in keys]
    return rng.choices(keys, weights=w, k=1)[0]


def sample_T(rng: random.Random, key: str, cli_min: float, cli_max: float) -> float:
    fam_lo, fam_hi = FAMILY_T_RANGE[key]
    lo, hi = max(fam_lo, cli_min), min(fam_hi, cli_max)
    if lo > hi:
        lo, hi = cli_min, cli_max
    T = rng.uniform(lo, hi)
    return round(round(T / 0.25) * 0.25, 2) or 0.25


def sample_strike_date(rng: random.Random, today: date, status: str, T: float,
                        n_obs: int, res_obs_index: Optional[int]) -> str:
    if status == "actif":
        if rng.random() < 0.15:
            sd = today + timedelta(days=rng.randint(1, 30))          # forward-start, pas encore démarré
        else:
            elapsed = rng.uniform(0, T * 0.9)
            sd = today - timedelta(days=round(elapsed * 365.25))
        return sd.isoformat()
    if status == "calle":
        since_call = rng.uniform(2, 400)
        call_t_years = (res_obs_index / n_obs) * T if n_obs else T
        sd = today - timedelta(days=round((since_call / 365.25 + call_t_years) * 365.25))
        return sd.isoformat()
    # échu (final ou ki)
    since_maturity = rng.uniform(5, 500)
    sd = today - timedelta(days=round(since_maturity)) - timedelta(days=round(T * 365.25))
    return sd.isoformat()


# ══════════════════════════════════════════════════════════════════════════
# Construction d'un deal
# ══════════════════════════════════════════════════════════════════════════

def build_one_deal(rng: random.Random, idx: int, today: date, args, cptys: list[str],
                    type_weights: dict, status_weights: dict) -> dict:
    key = pick_weighted(rng, type_weights)
    allowed = [s for s in ALLOWED_STATUSES[key] if s in status_weights or s == "actif"]
    local_weights = {s: status_weights.get(s, 0.0001) for s in allowed}
    status = pick_weighted(rng, local_weights)

    T = sample_T(rng, key, args.maturity_min, args.maturity_max)

    if key in PERIODIC_KEYS:
        _, step, _ = pick_weighted_freq(rng)
        obs = obs_schedule(T, step)
        freq_label = {0.25: "trimestrielle", 0.5: "semestrielle", 1.0: "annuelle"}[step]
    else:
        obs = [T]
        freq_label = "à maturité"

    n_underlyings = rng.choices([1, 2, 3], weights=[0.60, 0.28, 0.12], k=1)[0]
    uls = rng.sample(UNDERLYINGS, n_underlyings)

    outcome = build_deal_terms(key, rng, status, obs, freq_label)
    script_text = build_script_text(key, obs, outcome.display_params)

    strike_date = sample_strike_date(rng, today, status, T, len(obs), outcome.res_obs_index)
    maturity_date = dy(strike_date, obs[-1])

    devise = "EUR" if rng.random() < 0.65 else "USD"
    nominal = rng.choice([100_000, 150_000, 200_000, 250_000, 300_000, 500_000,
                          750_000, 1_000_000, 1_500_000, 2_000_000, 3_000_000])
    margin = FV_MARGIN[key] + rng.uniform(-0.6, 0.6)
    fair_value = round(100 - margin, 2)
    price_traded = round(100 + rng.uniform(-0.3, 0.3), 2)
    sens = "achat" if rng.random() < 0.08 else "vente"

    corr = None
    if n_underlyings > 1:
        corr = [[1.0 if i == j else round(rng.uniform(0.2, 0.7), 2) for j in range(n_underlyings)]
                for i in range(n_underlyings)]

    market_snapshot = {
        "underlyings": uls, "r": round(rng.uniform(2.5, 4.5), 2), "T": T, "model": "GBM",
        "n_paths": 5000, "antithetic": True, "barrier_monitoring": "weekly",
        "user_params": outcome.user_params, "constats": [],
    }
    if corr:
        market_snapshot["corr"] = corr

    s0_abs = [u["s0"] * rng.uniform(0.85, 1.15) for u in uls]

    return dict(
        idx=idx, key=key, ptype=PRODUCT_LABELS[key], uls=uls, s0=s0_abs,
        obs=outcome.obs, strike_date=strike_date, maturity_date=maturity_date,
        T=obs[-1], devise=devise, nominal=nominal, fair_value=fair_value,
        price_traded=price_traded, sens=sens, contrepartie=rng.choice(cptys),
        script=script_text, market_snapshot=market_snapshot,
        status="actif" if status == "actif" else ("callé" if status == "calle" else "échu"),
        res_obs_index=outcome.res_obs_index, realized_payout=outcome.realized_payout,
        resolution_outcome=outcome.resolution_outcome, freq_label=outcome.freq_label,
    )


def pick_weighted_freq(rng: random.Random):
    labels = [f[0] for f in FREQ_CHOICES]
    steps = [f[1] for f in FREQ_CHOICES]
    weights = [f[2] for f in FREQ_CHOICES]
    i = rng.choices(range(len(FREQ_CHOICES)), weights=weights, k=1)[0]
    return labels[i], steps[i], weights[i]


# ══════════════════════════════════════════════════════════════════════════
# Insertion en base
# ══════════════════════════════════════════════════════════════════════════

def insert_deal(session: Session, user_id: int, entity_id: Optional[int], portfolio_id: int,
                 ref_prefix: str, spec: dict, today: date) -> str:
    ref = f"{ref_prefix}-{today.strftime('%Y%m%d')}-{spec['idx']:04d}"
    obs = spec["obs"]

    deal = Deal(
        reference=ref, entity_id=entity_id, user_id=user_id, portfolio_id=portfolio_id,
        script_snapshot=spec["script"],
        sens=spec["sens"], contrepartie=spec["contrepartie"], devise=spec["devise"],
        product_type=spec["ptype"], nominal=float(spec["nominal"]),
        fair_value=spec["fair_value"], price_traded=spec["price_traded"],
        trade_date=spec["strike_date"], strike_date=spec["strike_date"],
        value_date=spec["strike_date"], maturity_date=spec["maturity_date"],
        payment_date=dy(spec["maturity_date"], 2 / 365),
        T=obs[-1], status=spec["status"],
        realized_payout=spec["realized_payout"], resolution_outcome=spec["resolution_outcome"],
        underlyings_json=json.dumps([
            {"name": u["name"], "ticker": u["ticker"], "s0_abs": round(spec["s0"][i], 4)}
            for i, u in enumerate(spec["uls"])
        ]),
        market_snapshot_json=json.dumps(spec["market_snapshot"]),
    )
    session.add(deal)
    session.flush()

    today_str = today.isoformat()
    s0_by_name = {u["name"]: round(spec["s0"][i], 4) for i, u in enumerate(spec["uls"])}
    session.add(DealEvent(
        deal_id=deal.id, event_index=0, event_date=spec["strike_date"], t_years=0.0,
        spots_json=json.dumps(s0_by_name), source="pending",
        status="observé" if spec["strike_date"] <= today_str else "futur",
        label="Strike / Fixing S₀",
    ))

    n = len(obs)
    res_idx = spec["res_obs_index"]
    outcome_label = spec["resolution_outcome"]
    for i, t in enumerate(obs):
        ed = dy(spec["strike_date"], t)
        is_mat = (i == n - 1)
        oi = i + 1
        if spec["status"] == "actif":
            ev_status = "observé" if ed <= today_str else "futur"
        elif spec["status"] == "callé":
            if oi == res_idx:
                ev_status = "callé"
            elif oi > res_idx:
                ev_status = "annulé"
            else:
                ev_status = "observé"
        else:  # échu
            ev_status = (outcome_label or "final") if is_mat else "observé"
        label = "Maturité" if is_mat else f"Obs. {oi} ({t:.2f}Y, {spec['freq_label']})"
        session.add(DealEvent(
            deal_id=deal.id, event_index=oi, event_date=ed, t_years=round(t, 4),
            spots_json="{}", source="pending", status=ev_status, label=label,
        ))

    return ref


def purge_demo_deals(session: Session, ref_prefix: str) -> int:
    ids = session.exec(select(Deal.id).where(Deal.reference.startswith(f"{ref_prefix}-"))).all()
    if not ids:
        return 0
    for model in (DealEvent, Alert, ShockRun, Document, KidRecord, EmtRecord):
        session.exec(delete(model).where(model.deal_id.in_(ids)))
    session.exec(delete(Deal).where(Deal.id.in_(ids)))
    session.commit()
    return len(ids)


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════

def parse_kv_weights(raw: str, valid_keys: set, label: str) -> dict:
    """Parse "key:weight,key:weight,..." -> {key: float}. Une clé sans poids
    (juste "key") vaut 1. Erreur si une clé n'existe pas."""
    out = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = float(v)
        else:
            out[part] = 1.0
    unknown = set(out) - valid_keys
    if unknown:
        raise argparse.ArgumentTypeError(f"{label} inconnu(s): {', '.join(sorted(unknown))}")
    return out


def parse_args():
    p = argparse.ArgumentParser(
        description="Génère un lot de deals de démonstration dans l'espace de booking.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""Types disponibles: {', '.join(sorted(PRODUCT_LABELS))}
Statuts disponibles: actif, calle, echu_final, echu_ki
""",
    )
    p.add_argument("--count", type=int, default=50, help="Nombre de deals à générer (défaut: 50)")
    p.add_argument("--users", default="test,admin",
                   help="Comptes destinataires, répartis en round-robin (défaut: test,admin)")
    p.add_argument("--seed", type=int, default=42, help="Graine RNG, pour reproductibilité (défaut: 42)")
    p.add_argument("--types", type=str, default=None,
                   help="Mix de types, ex: 'athena:3,phoenix:2,shark:1' (défaut: mix desk réaliste, tous types)")
    p.add_argument("--status-mix", type=str, default=None,
                   help="Mix de statuts, ex: 'actif:50,calle:20,echu_final:20,echu_ki:10' (défaut: 45/25/18/12)")
    p.add_argument("--maturity-min", type=float, default=0.25, help="Maturité minimale en années (défaut: 0.25)")
    p.add_argument("--maturity-max", type=float, default=8.0, help="Maturité maximale en années (défaut: 8)")
    p.add_argument("--ref-prefix", default="DEMO", help="Préfixe des références générées (défaut: DEMO)")
    p.add_argument("--no-purge", action="store_true",
                   help="Ne pas supprimer les deals du préfixe existants avant de regénérer (empile les lots)")
    p.add_argument("--dry-run", action="store_true", help="N'écrit rien en base, affiche juste le résumé")
    return p.parse_args()


def main():
    args = parse_args()
    if args.maturity_min <= 0 or args.maturity_max < args.maturity_min:
        print("❌  --maturity-min doit être > 0 et <= --maturity-max", file=sys.stderr)
        sys.exit(1)

    type_weights = parse_kv_weights(args.types, set(PRODUCT_LABELS), "type") if args.types else dict(DEFAULT_WEIGHTS)
    status_weights = parse_kv_weights(args.status_mix, {"actif", "calle", "echu_final", "echu_ki"}, "statut") \
        if args.status_mix else dict(DEFAULT_STATUS_MIX)

    init_db()
    today = date.today()
    rng = random.Random(args.seed)

    with Session(engine) as session:
        usernames = [u.strip() for u in args.users.split(",") if u.strip()]
        users = []
        for uname in usernames:
            user = session.exec(select(User).where(User.username == uname)).first()
            if not user:
                print(f"❌  Utilisateur '{uname}' introuvable.", file=sys.stderr)
                sys.exit(1)
            users.append(user)

        cptys = [c.name for c in session.exec(
            select(Counterparty).where(Counterparty.active == True)).all()]  # noqa: E712
        if not cptys:
            cptys = FALLBACK_CPTYS

        specs = [build_one_deal(rng, i + 1, today, args, cptys, type_weights, status_weights)
                 for i in range(args.count)]

        if args.dry_run:
            print(f"[dry-run] {len(specs)} deals seraient générés — aucune écriture en base.\n")
        else:
            purged = 0 if args.no_purge else purge_demo_deals(session, args.ref_prefix)
            if purged:
                print(f"Purge: {purged} ancien(s) deal(s) '{args.ref_prefix}-*' supprimé(s).")

            portfolios = {u.id: get_or_create_default_portfolio(session, u.id) for u in users}
            refs = []
            for i, spec in enumerate(specs):
                user = users[i % len(users)]
                ref = insert_deal(session, user.id, user.entity_id, portfolios[user.id].id,
                                   args.ref_prefix, spec, today)
                refs.append((ref, user.username, spec["ptype"], spec["status"]))
            session.commit()
            print(f"OK — {len(refs)} deals créés.\n")

        from collections import Counter
        by_type = Counter(s["ptype"] for s in specs)
        by_status = Counter(s["status"] for s in specs)
        by_user = Counter(usernames[i % len(usernames)] for i in range(len(specs)))
        print("Par type:")
        for k, v in sorted(by_type.items()):
            print(f"  {k:28s} {v}")
        print("Par statut:")
        for k, v in sorted(by_status.items()):
            print(f"  {k:10s} {v}")
        print("Par utilisateur:")
        for k, v in sorted(by_user.items()):
            print(f"  {k:10s} {v}")


if __name__ == "__main__":
    main()
