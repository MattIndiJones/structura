"""Composite benchmark definitions and ISIN → benchmark mapping.

To add a new composite benchmark: append an entry to COMPOSITE_BENCHMARKS.
To map an ISIN to a default benchmark: add a line to ISIN_DEFAULT_BENCHMARK.
No code changes required anywhere else.
"""
from __future__ import annotations

COMPOSITE_BENCHMARKS: list[dict] = [
    {
        "id":          "uti_new_financials",
        "label":       "UTI - New Financials Benchmark",
        "description": "FinTech · Digital Payments · Crypto · Asset Servicing · AI for Finance",
        "category":    "UTI Benchmarks",
        "color":       "#6366f1",
        "components": [
            {"ticker": "QQQ",     "label": "Nasdaq 100",     "weight": 0.40},
            {"ticker": "XLF",     "label": "S&P Financials", "weight": 0.30},
            {"ticker": "BTC-USD", "label": "Bitcoin",        "weight": 0.30},
        ],
    },
    {
        "id":          "uti_infrastructure",
        "label":       "UTI - Infrastructure Benchmark",
        "description": "AI Infrastructure · Data Centers · Semiconductors · Energy Transition · Critical Infrastructure",
        "category":    "UTI Benchmarks",
        "color":       "#10b981",
        "components": [
            {"ticker": "SOXX", "label": "PHLX Semiconductors",      "weight": 0.50},
            {"ticker": "IGF",  "label": "S&P Global Infrastructure", "weight": 0.25},
            {"ticker": "ICLN", "label": "S&P Global Clean Energy",   "weight": 0.25},
        ],
    },
    {
        "id":          "uti_life",
        "label":       "UTI - Life Benchmark",
        "description": "Longevity · Healthcare · Medical Technology · Senior Housing · Wealth & Insurance",
        "category":    "UTI Benchmarks",
        "color":       "#f59e0b",
        "components": [
            {"ticker": "IXJ",  "label": "MSCI World Health Care",     "weight": 0.40},
            {"ticker": "REET", "label": "FTSE EPRA Nareit Developed", "weight": 0.30},
            {"ticker": "IXG",  "label": "MSCI World Financials",      "weight": 0.30},
        ],
    },
]

# Maps ISIN → composite benchmark id.  One entry per AMC product.
ISIN_DEFAULT_BENCHMARK: dict[str, str] = {
    # ── UTI New Financials ──────────────────────────────────────────────
    "CH1352587708": "uti_new_financials",
    "CH1352587716": "uti_new_financials",
    "CH1352587724": "uti_new_financials",
    # ── UTI Infrastructure ──────────────────────────────────────────────
    "CH1473733934": "uti_infrastructure",
    "CH1473733959": "uti_infrastructure",
    "CH1473736143": "uti_infrastructure",
    # ── UTI Life ────────────────────────────────────────────────────────
    # Benchmark officiel du produit: iShares Ageing Population UCITS ETF (IE00BYZK4669)
    "CH1473731680": "AGED.L",
}

# Fast lookup by id
_COMPOSITE_BY_ID: dict[str, dict] = {c["id"]: c for c in COMPOSITE_BENCHMARKS}


def get_composite(benchmark_id: str) -> dict | None:
    return _COMPOSITE_BY_ID.get(benchmark_id)


def is_composite(ticker: str) -> bool:
    return ticker in _COMPOSITE_BY_ID
