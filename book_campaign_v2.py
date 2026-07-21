#!/usr/bin/env python3
"""
50 deals pour user 'test' — tous types/statuts.
NON-IDEMPOTENT — lancer UNE SEULE FOIS depuis la racine du repo :
    .venv\\Scripts\\python.exe book_campaign_v2.py
"""
import json, sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlmodel import Session, select
from backend.app.db.database import engine, init_db
from backend.app.db.models import Deal, DealEvent, User, Entity

init_db()
TODAY = date(2026, 7, 21)

# ── PayScript helpers ─────────────────────────────────────────────────────────

Q2  = "0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2"
Q3  = "0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.25, 2.5, 2.75, 3"
SA3 = "0.5, 1, 1.5, 2, 2.5, 3"

def athena(obs_str, coupon=8, ki=60):
    return (
        f"PARAM M_AC_BAR = 100%\nPARAM M_KI_BAR = {ki}%\nPARAM COUPON = {coupon}%\n\n"
        f"AT {obs_str}:\n  IF WOF >= M_AC_BAR:\n    PAY 1 + COUPON * INDEX\n    STOP\n\n"
        f"AT MATURITY:\n  IF WOF_MIN >= M_KI_BAR:\n    PAY 1\n  ELSE:\n    PAY WOF"
    )

def athena_degr(obs_str, coupon=8, ki=60):
    return (
        f"PARAM() M_AC_BAR = 105%\nPARAM M_KI_BAR = {ki}%\nPARAM COUPON = {coupon}%\n\n"
        f"AT {obs_str}:\n  IF WOF >= M_AC_BAR:\n    PAY 1 + COUPON * INDEX\n    STOP\n\n"
        f"AT MATURITY:\n  IF WOF_MIN >= M_KI_BAR:\n    PAY 1\n  ELSE:\n    PAY WOF"
    )

def phoenix(obs_str, ki=60, cpn_bar=70, coupon=2):
    return (
        f"PARAM M_KI_BAR = {ki}%\nPARAM M_CPN_BAR = {cpn_bar}%\nPARAM COUPON = {coupon}%\n\n"
        f"SET MEM = 0\n\nAT {obs_str}:\n"
        f"  IF WOF >= 1:\n    PAY 1 + MEM + COUPON\n    STOP\n"
        f"  IF WOF >= M_CPN_BAR:\n    PAY MEM + COUPON\n    SET MEM = 0\n"
        f"  ELSE:\n    SET MEM = MEM + COUPON\n\n"
        f"AT MATURITY:\n  IF WOF_MIN >= M_KI_BAR:\n    PAY 1\n  ELSE:\n    PAY WOF"
    )

BRC = (
    "PARAM M_KI_BAR = 65%\nPARAM M_PUT_STRIKE = 100%\nPARAM COUPON = 10%\n\n"
    "AT MATURITY:\n  PAY COUPON\n  IF WOF_MIN >= M_KI_BAR:\n    PAY 1\n  ELSE:\n    PAY WOF"
)
RC = (
    "PARAM M_PUT_STRIKE = 100%\nPARAM COUPON = 12%\n\n"
    "AT MATURITY:\n  PAY COUPON\n  IF WOF >= M_PUT_STRIKE:\n    PAY 1\n  ELSE:\n    PAY WOF"
)
def cg(parti=100):
    return (
        f"PARAM M_PARTI = {parti}%\n\n"
        f"AT MATURITY:\n  PAY 1\n  PAY MAX(0, WOF - 1) * M_PARTI"
    )
CG90 = (
    "PARAM M_PARTI = 120%\n\n"
    "AT MATURITY:\n  PAY 0.9\n  PAY MAX(0, WOF - 1) * M_PARTI"
)
TWIN_WIN = (
    "PARAM M_KI_BAR = 60%\nPARAM M_CAP = 140%\n\n"
    "AT MATURITY:\n  IF WOF_MIN >= M_KI_BAR:\n    PAY MIN(1 + ABS(WOF - 1), M_CAP)\n  ELSE:\n    PAY WOF"
)
SHARK = (
    "PARAM M_KO_BAR = 130%\nPARAM COUPON = 15%\nPARAM M_PARTI = 100%\n\n"
    "AT MATURITY:\n  IF BOF_MAX >= M_KO_BAR:\n    PAY 1 + COUPON\n  ELSE:\n    PAY 1 + MAX(0, WOF - 1) * M_PARTI"
)

# ── Underlyings ────────────────────────────────────────────────────────────────

def ul(name, ticker, sigma, q=1.5, ccy="USD"):
    return {"name": name, "ticker": ticker, "ccy": ccy, "sigma": sigma, "q": q,
            "sigma_fx": 0, "rho_sfx": 0, "model": "GBM", "v0": 0.04,
            "kappa": 2.0, "theta_h": 0.04, "xi": 0.4, "rho_h": -0.7,
            "alpha": 0.3, "beta": 0.5, "rho_s": -0.3, "nu": 0.3, "lv_surface": []}

SPX   = ul("S&P 500",      "^GSPC",     16, 1.5)
NVDA  = ul("Nvidia",       "NVDA",      45, 0.0)
AAPL  = ul("Apple",        "AAPL",      22, 0.5)
MSFT  = ul("Microsoft",    "MSFT",      20, 0.8)
AMZN  = ul("Amazon",       "AMZN",      28, 0.0)
GOOGL = ul("Alphabet",     "GOOGL",     24, 0.0)
META  = ul("Meta",         "META",      35, 0.4)
TSLA  = ul("Tesla",        "TSLA",      55, 0.0)
NKE   = ul("Nike",         "NKE",       25, 1.8)
PFE   = ul("Pfizer",       "PFE",       20, 4.5)
BABA  = ul("Alibaba",      "BABA",      38, 0.0)
ESTX  = ul("EuroStoxx 50", "^STOXX50E", 18, 2.5, ccy="EUR")
DAX   = ul("DAX",          "^GDAXI",    19, 2.8, ccy="EUR")
NDX   = ul("Nasdaq 100",   "^NDX",      20, 0.6)

CPTYS = [
    "BNP Paribas", "Société Générale", "UBS", "Barclays", "Goldman Sachs",
    "JP Morgan", "Deutsche Bank", "Natixis", "Morgan Stanley", "Citigroup",
    "HSBC", "Nomura", "Santander", "Crédit Agricole CIB", "Mizuho", "Bank of America",
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def dy(d: str, yrs: float) -> str:
    return (date.fromisoformat(d) + timedelta(days=round(yrs * 365.25))).isoformat()

def qtly(T): return [round(i * 0.25, 4) for i in range(1, round(T / 0.25) + 1)]
def sann(T): return [round(i * 0.5,  4) for i in range(1, round(T / 0.5)  + 1)]
def mat(T):  return [float(T)]

def _pct_to_frac(up):
    """PayScript engine stores PARAM % values as fractions (100% → 1.0).
    user_params must match that scale — divide integer-percent inputs here."""
    out = {}
    for k, v in up.items():
        if isinstance(v, list):
            out[k] = [round(x / 100, 6) for x in v]
        else:
            out[k] = round(v / 100, 6)
    return out

def snap(uls, r, T, up=None, corr=None):
    s = {"underlyings": uls, "r": r, "T": T, "model": "GBM",
         "n_paths": 5000, "antithetic": True, "barrier_monitoring": "weekly",
         "user_params": _pct_to_frac(up) if up else {}, "constats": []}
    if corr: s["corr"] = corr
    return s

# ── 50 deal specs ──────────────────────────────────────────────────────────────
# Keys: script, ptype, uls, strike, obs, s0, snap, nom, [sens, ccy, fv, pt,
#        status, res_obs, payout, outcome]

DEALS = [

    # ══ ACTIFS (1–20) ═══════════════════════════════════════════════════════

    # 1. Athena SPX 2Y Q — mi-vie (1.5Y écoulé)
    dict(script=athena(Q2), ptype="Autocall Athena", uls=[SPX],
         strike="2025-01-15", obs=qtly(2), s0=[4890],
         snap=snap([SPX], 3.5, 2.0, {"M_AC_BAR":100,"M_KI_BAR":60,"COUPON":8}),
         nom=1_000_000),

    # 2. Athena NVDA 2Y Q coupon 10% — 1Y écoulé
    dict(script=athena(Q2, coupon=10, ki=55), ptype="Autocall Athena", uls=[NVDA],
         strike="2025-07-01", obs=qtly(2), s0=[120],
         snap=snap([NVDA], 4.0, 2.0, {"M_AC_BAR":100,"M_KI_BAR":55,"COUPON":10}),
         nom=300_000),

    # 3. Athena AAPL 2Y Q — 1.25Y écoulé
    dict(script=athena(Q2), ptype="Autocall Athena", uls=[AAPL],
         strike="2025-04-01", obs=qtly(2), s0=[175],
         snap=snap([AAPL], 3.5, 2.0, {"M_AC_BAR":100,"M_KI_BAR":60,"COUPON":8}),
         nom=500_000),

    # 4. Athena Dégressif SPX 2Y Q — 9 mois écoulés
    dict(script=athena_degr(Q2), ptype="Autocall Athena", uls=[SPX],
         strike="2025-10-01", obs=qtly(2), s0=[5700],
         snap=snap([SPX], 3.5, 2.0,
                   {"M_AC_BAR":[105,100,95,90,85,80,80,80],"M_KI_BAR":60,"COUPON":8}),
         nom=2_000_000),

    # 5. Athena Dégressif EuroStoxx 3Y Q — mi-vie
    dict(script=athena_degr(Q3, coupon=7), ptype="Autocall Athena", uls=[ESTX],
         strike="2025-01-15", obs=qtly(3), s0=[5050], ccy="EUR",
         snap=snap([ESTX], 3.2, 3.0,
                   {"M_AC_BAR":[110,105,100,100,95,95,90,90,85,85,80,80],"M_KI_BAR":60,"COUPON":7}),
         nom=1_500_000),

    # 6. Phoenix Mémoire AAPL 2Y Q — 1Y écoulé, coupons en mémoire
    dict(script=phoenix(Q2), ptype="Phoenix Mémoire", uls=[AAPL],
         strike="2025-07-01", obs=qtly(2), s0=[210],
         snap=snap([AAPL], 3.5, 2.0, {"M_KI_BAR":60,"M_CPN_BAR":70,"COUPON":2}),
         nom=500_000),

    # 7. Phoenix Mémoire META 2Y Q — 6 mois écoulés
    dict(script=phoenix(Q2, ki=60, cpn_bar=75, coupon=2.5), ptype="Phoenix Mémoire", uls=[META],
         strike="2026-01-15", obs=qtly(2), s0=[620],
         snap=snap([META], 4.0, 2.0, {"M_KI_BAR":60,"M_CPN_BAR":75,"COUPON":2.5}),
         nom=400_000),

    # 8. WOF Athena AAPL+MSFT+AMZN 3Y Q — 2Y écoulés, proche maturité
    dict(script=athena(Q3, coupon=9, ki=55), ptype="Autocall Athena",
         uls=[AAPL, MSFT, AMZN], strike="2024-07-01", obs=qtly(3), s0=[220, 420, 190],
         snap=snap([AAPL, MSFT, AMZN], 3.5, 3.0,
                   {"M_AC_BAR":100,"M_KI_BAR":55,"COUPON":9},
                   corr=[[1,.55,.45],[.55,1,.50],[.45,.50,1]]),
         nom=1_000_000),

    # 9. WOF Athena NKE+SPX 2Y Q — WOF proche barrière KI
    dict(script=athena(Q2, coupon=10, ki=60), ptype="Autocall Athena",
         uls=[NKE, SPX], strike="2025-10-01", obs=qtly(2), s0=[82, 5700],
         snap=snap([NKE, SPX], 3.5, 2.0,
                   {"M_AC_BAR":100,"M_KI_BAR":60,"COUPON":10},
                   corr=[[1,.4],[.4,1]]),
         nom=750_000),

    # 10. WOF Athena NKE+PFE+BABA 2Y Q — WOF très bas, situation critique
    dict(script=athena(Q2, coupon=12, ki=55), ptype="Autocall Athena",
         uls=[NKE, PFE, BABA], strike="2025-07-01", obs=qtly(2), s0=[85, 28, 85],
         snap=snap([NKE, PFE, BABA], 3.5, 2.0,
                   {"M_AC_BAR":100,"M_KI_BAR":55,"COUPON":12},
                   corr=[[1,.3,.25],[.3,1,.2],[.25,.2,1]]),
         nom=500_000),

    # 11. Barrier RC MSFT 1Y — barrière non touchée
    dict(script=BRC, ptype="Barrier RC", uls=[MSFT],
         strike="2025-10-01", obs=mat(1.0), s0=[430],
         snap=snap([MSFT], 3.5, 1.0, {"M_KI_BAR":65,"M_PUT_STRIKE":100,"COUPON":10}),
         nom=500_000),

    # 12. Barrier RC TSLA 1.5Y — récent, vol élevée
    dict(script=BRC, ptype="Barrier RC", uls=[TSLA],
         strike="2026-01-15", obs=mat(1.5), s0=[390],
         snap=snap([TSLA], 4.0, 1.5, {"M_KI_BAR":60,"M_PUT_STRIKE":100,"COUPON":14}),
         nom=200_000),

    # 13. Reverse Convertible AMZN 1Y — sans barrière KI
    dict(script=RC, ptype="Reverse Convertible", uls=[AMZN],
         strike="2026-01-15", obs=mat(1.0), s0=[225],
         snap=snap([AMZN], 4.0, 1.0, {"M_PUT_STRIKE":100,"COUPON":12}),
         nom=300_000),

    # 14. Capital Garanti SPX 5Y — participation 100%, actif mi-vie
    dict(script=cg(100), ptype="Capital Garanti", uls=[SPX],
         strike="2024-07-01", obs=mat(5.0), s0=[5475],
         snap=snap([SPX], 3.5, 5.0, {"M_PARTI":100}),
         nom=2_000_000, fv=96.20, pt=100.0),

    # 15. Capital Garanti 90% Nasdaq 3Y — récent
    dict(script=CG90, ptype="Capital Garanti", uls=[NDX],
         strike="2026-01-15", obs=mat(3.0), s0=[21500],
         snap=snap([NDX], 4.0, 3.0, {"M_PARTI":120}),
         nom=1_000_000, fv=95.50, pt=100.0),

    # 16. Twin Win EuroStoxx 3Y — indice en légère baisse depuis strike
    dict(script=TWIN_WIN, ptype="Twin Win", uls=[ESTX],
         strike="2024-07-01", obs=mat(3.0), s0=[4970], ccy="EUR",
         snap=snap([ESTX], 3.2, 3.0, {"M_KI_BAR":60,"M_CAP":140}),
         nom=1_000_000, fv=97.00, pt=100.0),

    # 17. Shark SPX 2Y — WOF se rapproche du cap
    dict(script=SHARK, ptype="Shark", uls=[SPX],
         strike="2025-07-01", obs=mat(2.0), s0=[5440],
         snap=snap([SPX], 3.5, 2.0, {"M_KO_BAR":130,"COUPON":15,"M_PARTI":100}),
         nom=750_000, fv=96.50, pt=100.0),

    # 18. Athena DAX 2Y Q — proche maturité (19 mois écoulés), en perte latente
    dict(script=athena(Q2, coupon=7, ki=65), ptype="Autocall Athena", uls=[DAX],
         strike="2024-10-01", obs=qtly(2), s0=[19200], ccy="EUR",
         snap=snap([DAX], 3.2, 2.0, {"M_AC_BAR":100,"M_KI_BAR":65,"COUPON":7}),
         nom=800_000),

    # 19. Phoenix Mémoire WOF NKE+SPX 2Y Q — mémoire accumulée
    dict(script=phoenix(Q2, ki=60, cpn_bar=70, coupon=2.5), ptype="Phoenix Mémoire",
         uls=[NKE, SPX], strike="2025-10-01", obs=qtly(2), s0=[85, 5700],
         snap=snap([NKE, SPX], 3.5, 2.0,
                   {"M_KI_BAR":60,"M_CPN_BAR":70,"COUPON":2.5},
                   corr=[[1,.4],[.4,1]]),
         nom=500_000),

    # 20. Barrier RC SPX 1Y — sens ACHAT (cas rare)
    dict(script=BRC, ptype="Barrier RC", uls=[SPX],
         strike="2026-04-01", obs=mat(1.0), s0=[5670], sens="achat",
         snap=snap([SPX], 3.5, 1.0, {"M_KI_BAR":65,"M_PUT_STRIKE":100,"COUPON":10}),
         nom=500_000),

    # ══ CALLÉS (21–35) ══════════════════════════════════════════════════════

    # 21. Athena SPX 2Y Q — callé obs 1 (0.25Y = Oct 2023)
    dict(script=athena(Q2), ptype="Autocall Athena", uls=[SPX],
         strike="2023-07-01", obs=qtly(2), s0=[4450],
         snap=snap([SPX], 4.5, 2.0, {"M_AC_BAR":100,"M_KI_BAR":60,"COUPON":8}),
         nom=1_000_000, status="callé", res_obs=1, payout=1.08, outcome="callé"),

    # 22. Athena AAPL 2Y Q — callé obs 2 (Apr 2024)
    dict(script=athena(Q2), ptype="Autocall Athena", uls=[AAPL],
         strike="2023-10-01", obs=qtly(2), s0=[171],
         snap=snap([AAPL], 4.5, 2.0, {"M_AC_BAR":100,"M_KI_BAR":60,"COUPON":8}),
         nom=500_000, status="callé", res_obs=2, payout=1.16, outcome="callé"),

    # 23. Athena NVDA coupon 9% 2Y Q — callé obs 3
    dict(script=athena(Q2, coupon=9, ki=55), ptype="Autocall Athena", uls=[NVDA],
         strike="2023-04-01", obs=qtly(2), s0=[275],
         snap=snap([NVDA], 4.5, 2.0, {"M_AC_BAR":100,"M_KI_BAR":55,"COUPON":9}),
         nom=300_000, status="callé", res_obs=3, payout=1.27, outcome="callé"),

    # 24. Athena Dégressif SPX 2Y Q — callé obs 4 (barrière = 90%)
    dict(script=athena_degr(Q2), ptype="Autocall Athena", uls=[SPX],
         strike="2024-01-15", obs=qtly(2), s0=[4750],
         snap=snap([SPX], 4.0, 2.0,
                   {"M_AC_BAR":[105,100,95,90,85,80,80,80],"M_KI_BAR":60,"COUPON":8}),
         nom=2_000_000, status="callé", res_obs=4, payout=1.32, outcome="callé"),

    # 25. Athena EuroStoxx 2Y Q — callé obs 1
    dict(script=athena(Q2, coupon=7, ki=60), ptype="Autocall Athena", uls=[ESTX],
         strike="2023-01-15", obs=qtly(2), s0=[4050], ccy="EUR",
         snap=snap([ESTX], 3.5, 2.0, {"M_AC_BAR":100,"M_KI_BAR":60,"COUPON":7}),
         nom=1_000_000, status="callé", res_obs=1, payout=1.07, outcome="callé"),

    # 26. Athena GOOGL 3Y semi-annuel — callé obs 3 (1.5Y = Jan 2024)
    dict(script=athena(SA3, coupon=4, ki=65), ptype="Autocall Athena", uls=[GOOGL],
         strike="2022-07-01", obs=sann(3), s0=[115],
         snap=snap([GOOGL], 3.0, 3.0, {"M_AC_BAR":100,"M_KI_BAR":65,"COUPON":4}),
         nom=750_000, status="callé", res_obs=3, payout=1.12, outcome="callé"),

    # 27. Athena AMZN 2Y Q — callé obs 8 (dernier, long wait)
    dict(script=athena(Q2), ptype="Autocall Athena", uls=[AMZN],
         strike="2022-07-01", obs=qtly(2), s0=[120],
         snap=snap([AMZN], 3.0, 2.0, {"M_AC_BAR":100,"M_KI_BAR":60,"COUPON":8}),
         nom=500_000, status="callé", res_obs=8, payout=1.64, outcome="callé"),

    # 28. Phoenix Mémoire MSFT 2Y Q — callé obs 4 avec mémoire payée
    dict(script=phoenix(Q2), ptype="Phoenix Mémoire", uls=[MSFT],
         strike="2023-07-01", obs=qtly(2), s0=[340],
         snap=snap([MSFT], 4.5, 2.0, {"M_KI_BAR":60,"M_CPN_BAR":70,"COUPON":2}),
         nom=500_000, status="callé", res_obs=4, payout=1.10, outcome="callé"),

    # 29. Phoenix Mémoire TSLA coupon 3% 2Y Q — callé obs 3
    dict(script=phoenix(Q2, ki=55, cpn_bar=70, coupon=3), ptype="Phoenix Mémoire", uls=[TSLA],
         strike="2024-01-15", obs=qtly(2), s0=[245],
         snap=snap([TSLA], 4.5, 2.0, {"M_KI_BAR":55,"M_CPN_BAR":70,"COUPON":3}),
         nom=200_000, status="callé", res_obs=3, payout=1.06, outcome="callé"),

    # 30. Phoenix Mémoire WOF NKE+SPX 2Y Q — callé obs 4 avec mémoire
    dict(script=phoenix(Q2, ki=60, cpn_bar=70, coupon=2.5), ptype="Phoenix Mémoire",
         uls=[NKE, SPX], strike="2023-10-01", obs=qtly(2), s0=[100, 4300],
         snap=snap([NKE, SPX], 4.0, 2.0,
                   {"M_KI_BAR":60,"M_CPN_BAR":70,"COUPON":2.5},
                   corr=[[1,.4],[.4,1]]),
         nom=750_000, status="callé", res_obs=4, payout=1.10, outcome="callé"),

    # 31. WOF Athena AAPL+SPX 2Y Q — callé obs 2
    dict(script=athena(Q2, coupon=9, ki=55), ptype="Autocall Athena",
         uls=[AAPL, SPX], strike="2023-04-01", obs=qtly(2), s0=[165, 4110],
         snap=snap([AAPL, SPX], 4.0, 2.0,
                   {"M_AC_BAR":100,"M_KI_BAR":55,"COUPON":9},
                   corr=[[1,.6],[.6,1]]),
         nom=1_000_000, status="callé", res_obs=2, payout=1.18, outcome="callé"),

    # 32. WOF Athena AAPL+MSFT+GOOGL 2Y Q — callé obs 1 (marché haussier)
    dict(script=athena(Q2, coupon=7, ki=60), ptype="Autocall Athena",
         uls=[AAPL, MSFT, GOOGL], strike="2023-07-01", obs=qtly(2), s0=[190, 330, 127],
         snap=snap([AAPL, MSFT, GOOGL], 4.5, 2.0,
                   {"M_AC_BAR":100,"M_KI_BAR":60,"COUPON":7},
                   corr=[[1,.65,.6],[.65,1,.7],[.6,.7,1]]),
         nom=1_000_000, status="callé", res_obs=1, payout=1.07, outcome="callé"),

    # 33. Athena SPX 3Y semi-annuel — callé obs 2 (1Y = Jul 2024)
    dict(script=athena(SA3, coupon=4, ki=65), ptype="Autocall Athena", uls=[SPX],
         strike="2023-07-01", obs=sann(3), s0=[4540],
         snap=snap([SPX], 4.5, 3.0, {"M_AC_BAR":100,"M_KI_BAR":65,"COUPON":4}),
         nom=2_000_000, status="callé", res_obs=2, payout=1.08, outcome="callé"),

    # 34. Athena META 3Y Q coupon 8% — callé obs 4 (1Y = Jan 2023)
    dict(script=athena(Q3, coupon=8, ki=55), ptype="Autocall Athena", uls=[META],
         strike="2022-01-15", obs=qtly(3), s0=[335],
         snap=snap([META], 3.0, 3.0, {"M_AC_BAR":100,"M_KI_BAR":55,"COUPON":8}),
         nom=500_000, status="callé", res_obs=4, payout=1.32, outcome="callé"),

    # 35. Athena META 2Y Q — callé obs 1 très tôt (0.25Y = Jul 2024)
    dict(script=athena(Q2), ptype="Autocall Athena", uls=[META],
         strike="2024-04-01", obs=qtly(2), s0=[495],
         snap=snap([META], 4.5, 2.0, {"M_AC_BAR":100,"M_KI_BAR":60,"COUPON":8}),
         nom=500_000, status="callé", res_obs=1, payout=1.08, outcome="callé"),

    # ══ ÉCHUS FINAL (36–43) ══════════════════════════════════════════════════

    # 36. Athena SPX 2Y Q — tous obs ratés, barrière KI tenue, PAY 1
    dict(script=athena(Q2), ptype="Autocall Athena", uls=[SPX],
         strike="2022-07-01", obs=qtly(2), s0=[3820],
         snap=snap([SPX], 3.0, 2.0, {"M_AC_BAR":100,"M_KI_BAR":60,"COUPON":8}),
         nom=1_000_000, status="échu", payout=1.00, outcome="final"),

    # 37. Capital Garanti SPX 3Y — participation 100%, SPX +40%
    dict(script=cg(100), ptype="Capital Garanti", uls=[SPX],
         strike="2021-07-01", obs=mat(3.0), s0=[4280],
         snap=snap([SPX], 1.5, 3.0, {"M_PARTI":100}),
         nom=2_000_000, fv=96.20, pt=100.0, status="échu", payout=1.40, outcome="final"),

    # 38. Capital Garanti AAPL 3Y — participation 80%, AAPL +35%
    dict(script=cg(80), ptype="Capital Garanti", uls=[AAPL],
         strike="2021-07-01", obs=mat(3.0), s0=[145],
         snap=snap([AAPL], 1.5, 3.0, {"M_PARTI":80}),
         nom=1_000_000, fv=95.50, pt=100.0, status="échu", payout=1.28, outcome="final"),

    # 39. Shark SPX 2Y — BOF_MAX >= 130%, PAY 1 + 15% = 1.15
    dict(script=SHARK, ptype="Shark", uls=[SPX],
         strike="2022-01-15", obs=mat(2.0), s0=[4570],
         snap=snap([SPX], 2.5, 2.0, {"M_KO_BAR":130,"COUPON":15,"M_PARTI":100}),
         nom=750_000, fv=96.50, pt=100.0, status="échu", payout=1.15, outcome="final"),

    # 40. Twin Win EuroStoxx 3Y — indice -10% → Twin Win +10%
    dict(script=TWIN_WIN, ptype="Twin Win", uls=[ESTX],
         strike="2021-07-01", obs=mat(3.0), s0=[3950], ccy="EUR",
         snap=snap([ESTX], 1.5, 3.0, {"M_KI_BAR":60,"M_CAP":140}),
         nom=1_000_000, fv=97.00, pt=100.0, status="échu", payout=1.10, outcome="final"),

    # 41. Barrier RC MSFT 1Y — barrière jamais touchée, PAY 10% + 100% = 1.10
    dict(script=BRC, ptype="Barrier RC", uls=[MSFT],
         strike="2023-01-15", obs=mat(1.0), s0=[242],
         snap=snap([MSFT], 3.5, 1.0, {"M_KI_BAR":65,"M_PUT_STRIKE":100,"COUPON":10}),
         nom=500_000, status="échu", payout=1.10, outcome="final"),

    # 42. Phoenix SPX 2Y Q — toutes obs, coupons + PAY 1 maturité
    dict(script=phoenix(Q2), ptype="Phoenix Mémoire", uls=[SPX],
         strike="2022-07-01", obs=qtly(2), s0=[3830],
         snap=snap([SPX], 3.0, 2.0, {"M_KI_BAR":60,"M_CPN_BAR":70,"COUPON":2}),
         nom=1_000_000, status="échu", payout=1.16, outcome="final"),

    # 43. Reverse Convertible NVDA 1Y — NVDA > strike, PAY 12% + 100% = 1.12
    dict(script=RC, ptype="Reverse Convertible", uls=[NVDA],
         strike="2023-01-15", obs=mat(1.0), s0=[165],
         snap=snap([NVDA], 4.0, 1.0, {"M_PUT_STRIKE":100,"COUPON":12}),
         nom=300_000, status="échu", payout=1.12, outcome="final"),

    # ══ ÉCHUS KI (44–50) ═════════════════════════════════════════════════════

    # 44. Barrier RC BABA 1Y — KI touché, BABA 62% → 10% + 62% = 0.72
    dict(script=BRC, ptype="Barrier RC", uls=[BABA],
         strike="2023-01-15", obs=mat(1.0), s0=[92],
         snap=snap([BABA], 4.5, 1.0, {"M_KI_BAR":65,"M_PUT_STRIKE":100,"COUPON":10}),
         nom=300_000, status="échu", payout=0.72, outcome="ki"),

    # 45. Barrier RC PFE 1Y — KI touché, PFE 50% → 10% + 50% = 0.60
    dict(script=BRC, ptype="Barrier RC", uls=[PFE],
         strike="2022-07-01", obs=mat(1.0), s0=[52],
         snap=snap([PFE], 3.5, 1.0, {"M_KI_BAR":65,"M_PUT_STRIKE":100,"COUPON":10}),
         nom=500_000, status="échu", payout=0.60, outcome="ki"),

    # 46. WOF Barrier RC NKE+SPX 1Y — KI touché, WOF 48% → 10% + 48% = 0.58
    dict(script=BRC, ptype="Barrier RC", uls=[NKE, SPX],
         strike="2022-07-01", obs=mat(1.0), s0=[115, 3820],
         snap=snap([NKE, SPX], 3.5, 1.0,
                   {"M_KI_BAR":65,"M_PUT_STRIKE":100,"COUPON":10},
                   corr=[[1,.4],[.4,1]]),
         nom=750_000, status="échu", payout=0.58, outcome="ki"),

    # 47. WOF Barrier RC BABA+NKE+PFE 1Y — KI touché, WOF 45% → 10% + 45% = 0.55
    dict(script=BRC, ptype="Barrier RC", uls=[BABA, NKE, PFE],
         strike="2022-01-15", obs=mat(1.0), s0=[115, 150, 55],
         snap=snap([BABA, NKE, PFE], 2.5, 1.0,
                   {"M_KI_BAR":65,"M_PUT_STRIKE":100,"COUPON":10},
                   corr=[[1,.25,.3],[.25,1,.35],[.3,.35,1]]),
         nom=500_000, status="échu", payout=0.55, outcome="ki"),

    # 48. Phoenix Mémoire TSLA 2Y Q — KI touché, TSLA 70% à maturité → 0.74
    dict(script=phoenix(Q2, ki=55, cpn_bar=70, coupon=2), ptype="Phoenix Mémoire", uls=[TSLA],
         strike="2022-07-01", obs=qtly(2), s0=[310],
         snap=snap([TSLA], 3.0, 2.0, {"M_KI_BAR":55,"M_CPN_BAR":70,"COUPON":2}),
         nom=200_000, status="échu", payout=0.74, outcome="ki"),

    # 49. Barrier RC AMZN 1Y — KI touché mais AMZN récupère à 95% → 10% + 95% = 1.05
    dict(script=BRC, ptype="Barrier RC", uls=[AMZN],
         strike="2022-01-15", obs=mat(1.0), s0=[170],
         snap=snap([AMZN], 3.0, 1.0, {"M_KI_BAR":65,"M_PUT_STRIKE":100,"COUPON":10}),
         nom=300_000, status="échu", payout=1.05, outcome="ki"),

    # 50. Athena META 2Y Q — KI touché, pas rappelé, META 58% → 0.58
    dict(script=athena(Q2, coupon=8, ki=55), ptype="Autocall Athena", uls=[META],
         strike="2022-07-01", obs=qtly(2), s0=[175],
         snap=snap([META], 3.0, 2.0, {"M_AC_BAR":100,"M_KI_BAR":55,"COUPON":8}),
         nom=500_000, status="échu", payout=0.58, outcome="ki"),
]

# ── Insertion ─────────────────────────────────────────────────────────────────

# Realistic fair values at booking (% of nominal, before mark-up to 100).
# These reflect typical Monte Carlo prices in 2022-2025 market conditions
# (SPX vol ~15-20%, rates 3.5-5%).
_FV_BY_TYPE = {
    "Autocall Athena":     97.50,  # 2.5% margin — 8% cpn, 60% KI, 2Y
    "Phoenix Mémoire":     98.20,  # 1.8% margin — memoire effect reduces gap vs Athena
    "Barrier RC":          98.00,  # 2.0% margin — single or worst-of barrier
    "Reverse Convertible": 98.50,  # 1.5% margin — 1Y, no memory, simple structure
    "Capital Garanti":     96.20,  # 3.8% margin — cost of capital guarantee is high
    "Twin Win":            97.00,  # 3.0% margin — two-direction participation
    "Shark":               96.50,  # 3.5% margin — KO barrier + participation
}

def book(session, user_id, entity_id, idx, spec):
    sd = spec["strike"]
    vd = sd
    obs = spec["obs"]
    mat_date = dy(vd, obs[-1])
    status   = spec.get("status", "actif")
    res_obs  = spec.get("res_obs")
    payout   = spec.get("payout")
    outcome  = spec.get("outcome")

    ref = f"DEMO-{TODAY.strftime('%Y%m%d')}-{idx:03d}"

    deal = Deal(
        reference=ref, entity_id=entity_id, user_id=user_id,
        script_snapshot=spec["script"],
        sens=spec.get("sens", "vente"),
        contrepartie=CPTYS[(idx - 1) % len(CPTYS)],
        devise=spec.get("ccy", "EUR"),
        product_type=spec["ptype"],
        nominal=float(spec.get("nom", 500_000)),
        fair_value=spec.get("fv", _FV_BY_TYPE.get(spec["ptype"], 97.50)),
        price_traded=spec.get("pt", 100.0),
        trade_date=sd, strike_date=sd, value_date=vd,
        maturity_date=mat_date,
        payment_date=dy(mat_date, 2 / 365),
        T=obs[-1], status=status,
        realized_payout=payout,
        resolution_outcome=outcome,
        underlyings_json=json.dumps([
            {"name": u["name"], "ticker": u["ticker"], "s0_abs": spec["s0"][i]}
            for i, u in enumerate(spec["uls"])
        ]),
        market_snapshot_json=json.dumps(spec["snap"]),
    )
    session.add(deal)
    session.flush()

    # Strike event — spots_json must hold {name: s0} so build_watchlist_row
    # can compute perf = spot / s0 for each underlying.
    s0_by_name = {u["name"]: spec["s0"][i] for i, u in enumerate(spec["uls"])}
    session.add(DealEvent(
        deal_id=deal.id, event_index=0, event_date=sd, t_years=0.0,
        spots_json=json.dumps(s0_by_name), source="pending",
        status="observé" if sd <= TODAY.isoformat() else "futur",
        label="Strike / Fixing S₀",
    ))

    # Observation events
    n = len(obs)
    for i, t in enumerate(obs):
        ed   = dy(vd, t)
        is_mat = (i == n - 1)
        oi   = i + 1  # 1-based

        if status == "actif":
            ev_s = "observé" if ed <= TODAY.isoformat() else "futur"
        elif status == "callé":
            if oi == res_obs:       ev_s = "callé"
            elif oi > res_obs:      ev_s = "annulé"
            else:                   ev_s = "observé"
        else:  # échu
            if is_mat:
                ev_s = outcome if outcome in ("ki", "final") else "final"
            else:
                ev_s = "observé"

        lbl = "Maturité" if is_mat else f"Obs. {oi} ({t:.2f}Y)"
        session.add(DealEvent(
            deal_id=deal.id, event_index=oi, event_date=ed,
            t_years=round(t, 4), spots_json="{}", source="pending",
            status=ev_s, label=lbl,
        ))

    return ref


with Session(engine) as session:
    user = session.exec(select(User).where(User.username == "test")).first()
    if not user:
        print("❌  User 'test' introuvable — vérifie la base.")
        sys.exit(1)
    entity = session.get(Entity, user.entity_id) if user.entity_id else None
    username = user.username  # capture before session closes

    refs = []
    for idx, spec in enumerate(DEALS, start=1):
        ref = book(session, user.id, entity.id if entity else None, idx, spec)
        refs.append((idx, ref, spec.get("status", "actif")))

    session.commit()

print(f"\nOK — {len(refs)} deals crees pour '{username}'\n")
counts = {}
for _, _, s in refs: counts[s] = counts.get(s, 0) + 1
for s, c in sorted(counts.items()): print(f"  {s:10s} {c}")
print()
for i, ref, st in refs:
    print(f"  {i:2d}. {ref}  [{st}]")
