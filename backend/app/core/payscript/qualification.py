"""Versioned catalogue approvals backed by independent deterministic cashflows.

This panel checks payoff branches on a synthetic observation grid. It does not
certify contractual terms, production calendars or a stochastic pricing model.
Changing a source requires explicit review of its approval and reference panel.
"""
from copy import deepcopy
from datetime import date
from functools import lru_cache
import hashlib
import json

import numpy as np

from .parser import parse_script, resolve_constats, script_source_hash


PANEL_VERSION = "C09-v1"
APPROVED_SOURCES = {
    "autocall_athena": "e072633239f8e58d37ee96ec7bd716a76c7152fff8d5de7f141a6d97a104f9eb",
    "phoenix": "f7e3ef898dd55e1491279e486714bb8e10c3007e118e3acc1989de9c85a2ccab",
    "phoenix_memoire": "8a33f01e5db1a6824ccb57e427f7797da294b4050435f152c673569633af6d60",
    "autocall_barriere_degressive": "0b50f698da4235ee42159b9b874bb79dcecdb78d918ccca1242dfef6c1615474",
    "reverse_convertible": "0f7b287e28377314587981c7fd5eea6f6d7621812ecc789ab3a6c2c04ad2ec7e",
    "capital_garanti": "8e6b78e68e0789ca8b9d1b3ad0c440f57201405aeafdd0ab82f25ab5828cf651",
    "booster": "2ee5adb2581170bc3f4949cc55576e6dc89e61bfbacb980c9303e1380460e787",
    "autocall_gear_put": "24eab56a2f920661dc44c1cbae44f3356c09916c1065313f526b2e7736003e3b",
}
SCOPE = ("Logique des flux sur trajectoires de référence et grille synthétique ; "
         "ne valide ni les termes du produit, ni les calendriers de production, "
         "ni le modèle de pricing.")


def reference_cases(key):
    """Inputs in engine units; boundary, missed coupon, reset and worst-of cases."""
    scheduled = key not in {"reverse_convertible", "capital_garanti", "booster"}
    levels = [
        ("early_call", [1., .5, .5, .5]),
        ("second_call", [.8, 1., .5, .5]),
        ("third_call", [.8, .8, 1., .5]),
        ("late_call", [.6, .8, .6, 1.]),
        ("miss_catchup_reset", [.6, .8, .6, .8]),
        ("unpaid_memory", [.8, .6, .6, .6]),
        ("never_paid", [.5]*4),
        ("step_down", [.96]*4),
    ] if scheduled else []
    for barrier in (.6, .7, .85, 1., 1.15):
        for delta, suffix in ((-1e-7, "below"), (0., "equal"), (1e-7, "above")):
            levels.append((f"boundary_{barrier}_{suffix}", [barrier+delta]*(4 if scheduled else 1)))
    levels.extend((f"extreme_{x}", [x]*(4 if scheduled else 1)) for x in (0., .3, 2.))
    for name, path in levels:
        for quantity in (0., .02, .08) if scheduled or key == "reverse_convertible" else (.5, 2., 4.):
            params = dict(COUPON=quantity, PART=quantity, STRIKE=1., CAP=1.3,
                          M_AC_BAR=[1., .95, .9, .85] if key == "autocall_barriere_degressive" else 1.,
                          M_CPN_BAR=.7, M_KI_BAR=.6, M_PUT_STRIKE=.6, GEARING=2.)
            # The worst performer switches identity at each observation.
            basket = [[x, x+.1] if i % 2 == 0 else [x+.1, x] for i, x in enumerate(path)]
            yield dict(name=f"{name}_q{quantity}", levels=basket, params=params)


def expected_cashflows(key, levels, p):
    """Independent contractual formulas, with observation rank as the clock."""
    perf = [min(row) for row in levels]
    flows = []
    def pay(rank, amount, label):
        if amount != 0:
            flows.append([rank, float(amount), label])
    scheduled = key not in {"reverse_convertible", "capital_garanti", "booster"}
    memo = 0
    if scheduled:
        for rank, level in enumerate(perf, 1):
            if key in {"phoenix", "phoenix_memoire"} and level >= p["M_CPN_BAR"]:
                pay(rank, p["COUPON"]*(rank-memo if key == "phoenix_memoire" else 1),
                    "Coupon et rattrapage" if key == "phoenix_memoire" else "Coupon conditionnel")
                memo = rank
            trigger = p["M_AC_BAR"][rank-1] if isinstance(p["M_AC_BAR"], list) else p["M_AC_BAR"]
            if level >= trigger:
                if key in {"autocall_athena", "autocall_barriere_degressive", "autocall_gear_put"}:
                    pay(rank, p["COUPON"]*(1 if key == "autocall_gear_put" else rank),
                        "Coupon" if key == "autocall_gear_put" else "Coupons cumulés")
                pay(rank, 1., "Remboursement anticipé" if key == "phoenix_memoire" else "Capital — remboursement au rappel")
                return flows, rank
    rank, level = len(perf), perf[-1]
    if key == "capital_garanti":
        pay(rank, 1., "Capital garanti")
        pay(rank, max(0., level-p["STRIKE"])*p["PART"], "Participation à la hausse")
    elif key == "booster":
        pay(rank, 1., "Capital — remboursement à maturité")
        pay(rank, min(p["CAP"]-1., (level-1.)*p["PART"]) if level >= 1. else 0., "Participation plafonnée")
        pay(rank, -max(1.-level, 0.), "Put vendu — perte en capital")
    elif key == "autocall_gear_put":
        pay(rank, 1., "Remboursement nominal")
        pay(rank, -min(1., p["GEARING"]*(1.-level/p["M_PUT_STRIKE"])) if level < p["M_PUT_STRIKE"] else 0.,
            "Put vendu avec levier, perte plafonnée au capital")
    else:
        if key == "reverse_convertible":
            pay(rank, p["COUPON"], "Coupon")
        pay(rank, 1., "Capital — remboursement à maturité")
        pay(rank, -max(1.-level, 0.) if level < p["M_KI_BAR"] else 0., "Put vendu — perte en capital")
    return flows, rank


@lru_cache(maxsize=8)
def _run_panel(key, source, version):
    from .engine import _eval_paths

    scheduled = key not in {"reverse_convertible", "capital_garanti", "booster"}
    calendar = {"STARTDATE": "2026-01-02"}
    if scheduled:
        calendar["OBSERVATIONDATES"] = dict(first_observation_date="2026-04-02", end_date="2027-01-02",
                                            roll_date="2026-01-02", frequency="3M", stub="short_last",
                                            convention="none", settlement_lag=0)
    else:
        calendar["MATURITYDATE"] = dict(date="2027-01-02", convention="none", settlement_lag=0)
    script = resolve_constats(parse_script(source), calendar, anchor=date(2026, 1, 2), currency="EUR")
    dates = sorted({t for event in script.events for t in event.dates})
    expected_count = 4 if scheduled else 1
    if len(dates) != expected_count:
        raise ValueError(f"Panel {key} : calendrier de référence inattendu.")
    steps = {i+1: [event for event in script.events if t in event.dates] for i, t in enumerate(dates)}
    cases = []
    for case in reference_cases(key):
        params = {p.name: case["params"][p.name] for p in script.params}
        paths = np.asarray([[1., 1.], *case["levels"]]).reshape(expected_count+1, 2, 1)
        flows, labels, stops = [], [], []
        pv, _ = _eval_paths(script, paths, expected_count, 2, 1, 1/expected_count, 0., params,
                            steps, [], {}, False, flows_out=flows, flow_labels_out=labels, stop_times_out=stops)
        actual = [[round(t*expected_count), float(amount), label] for (t, amount), label in zip(flows[0], labels[0])]
        expected, stop = expected_cashflows(key, case["levels"], case["params"])
        same = len(actual) == len(expected) and all(
            a[0] == e[0] and a[2] == e[2] and abs(a[1]-e[1]) <= 1e-12 for a, e in zip(actual, expected))
        if (not same or not np.isfinite(pv[0]) or not np.isfinite(stops[0])
                or abs(float(pv[0])-sum(e[1] for e in expected)) > 1e-12
                or abs(stops[0]*expected_count-stop) > 1e-12):
            raise ValueError(f"Panel {key} : échec de la trajectoire {case['name']} ; qualification requise.")
        cases.append({**case, "expected": expected, "actual": actual, "stop_rank": stop})
    digest = hashlib.sha256(json.dumps(dict(version=version, calendar=calendar, cases=cases),
                                       sort_keys=True, allow_nan=False).encode()).hexdigest()
    affinity = {"participation": "PIECEWISE_AFFINE", "redemption_cap": "PIECEWISE_AFFINE"} if key == "booster" else {
        "participation" if key == "capital_garanti" else "coupon": "AFFINE"}
    return dict(status="REFERENCE_PATHS_PASSED", family=key, source_hash=script_source_hash(source),
                panel_version=version, reference_panel_hash=digest, case_count=len(cases),
                parameter_affinity=affinity, scope=SCOPE), cases


def qualify_payoff(key, source, *, include_cases=False):
    if script_source_hash(source) != APPROVED_SOURCES.get(key):
        raise ValueError(f"Script {key} modifié ou non approuvé ; qualification du payoff requise.")
    try:
        proof, cases = _run_panel(key, source, PANEL_VERSION)
    except Exception as exc:
        raise ValueError(f"Panel {key} indisponible ou en échec ; qualification du payoff requise : {exc}") from exc
    return deepcopy({**proof, "cases": cases} if include_cases else proof)


def recognize_payoff(source):
    source_hash = script_source_hash(source)
    key = next((k for k, value in APPROVED_SOURCES.items() if value == source_hash), None)
    if key is not None:
        try:
            return qualify_payoff(key, source)
        except ValueError as exc:
            return dict(status="UNQUALIFIED", source_hash=source_hash, scope=SCOPE, reason=str(exc))
    return dict(status="STRUCTURAL_ONLY", source_hash=source_hash, scope=SCOPE)
