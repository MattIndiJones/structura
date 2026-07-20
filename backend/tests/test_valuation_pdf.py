"""Client valuation note (core/deal_valuation_pdf.py) — offline, synthetic
data, no network. The builders are pure functions of plain dicts."""
import pytest

from backend.app.core.deal_valuation_pdf import (
    generate_valuation_pdf, generate_explain_pdf, build_explanation,
)


def _data(n_uls=1, monitors=True, wof_min=0.9258):
    names = ["SPX", "NKE", "BABA"][:n_uls]
    spots = [1.0884, 0.95, 0.82][:n_uls]
    hist_dates = [f"2025-{m:02d}-{d:02d}" for m in range(1, 13) for d in (1, 15)]
    series = {n: [s * (1 + 0.001 * k) for k in range(len(hist_dates))]
              for n, s in zip(names, [1.0, 0.9, 0.85])}
    return {
        "deal": {"reference": "TEST-001", "product_type": "Autocall", "sens": "vente",
                 "contrepartie": "BNP Paribas", "nominal": 1_000_000.0, "devise": "EUR",
                 "price_traded": 98.5, "trade_date": "2024-07-01",
                 "strike_date": "2024-07-05", "value_date": "2024-07-12",
                 "maturity_date": "2027-07-12"},
        "mtm": {"mtm": 1.0478, "ic95": [1.0451, 1.0505], "prob_gt100": 0.8673,
                "fugit": 0.73, "T_elapsed": 2.0, "T_remaining": 1.0,
                "obs_passees": 2, "wof_min_realized": wof_min,
                "realized_cash_flows": [{"t": 1.0, "cf": 0.08}],
                "realized_total": 0.08, "n_paths": 20000,
                "best_case": {"pv_max": 1.0851, "pv_p95": 1.0851, "capped": True,
                              "capture_ratio": 0.9656, "upside_pts": 3.73,
                              "upside_annualized_pct": 5.11, "horizon_years": 0.73,
                              "exit_signal": False},
                "market_used": {"source": "booking", "model": "constant", "r": 3.0,
                                "flat_curve": True, "window_returns": None,
                                "sigma": {n: 22.0 for n in names},
                                "q": {n: 2.0 for n in names},
                                "corr": [[1.0 if i == j else 0.6
                                          for j in range(n_uls)] for i in range(n_uls)]}},
        "underlyings": [{"name": n, "ticker": n, "spot_pct": s}
                        for n, s in zip(names, spots)],
        "monitors": ([{"name": "M_AC_BAR", "observable": "WOF",
                       "direction": "up", "level": 1.0},
                      {"name": "M_KI_BAR", "observable": "WOF_MIN",
                       "direction": "down", "level": 0.6}] if monitors else []),
        "events": [
            {"date": "2024-07-05", "label": "Strike / Fixing S0",
             "status": "observé", "t_years": 0.0},
            {"date": "2025-07-12", "label": "Obs. 1 (t 1.0)",
             "status": "observé", "t_years": 1.0},
            {"date": "2026-07-12", "label": "Obs. 2 (t 2.0)",
             "status": "observé", "t_years": 2.0},
            {"date": "2027-07-12", "label": "Maturité",
             "status": "futur", "t_years": 3.0},
        ],
        "next_obs_date": "2027-07-12",
        "history": {"dates": hist_dates, "series": series},
        "greeks": [{"name": n, "delta_pts": 0.42, "gamma_pts": -0.013,
                    "vega_pts": -0.15} for n in names],
    }


def test_pdf_generates_single_underlying():
    pdf = generate_valuation_pdf(_data())
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 20_000    # header + tables + chart, not an empty shell


def test_pdf_multi_underlying_legacy_no_monitors():
    """3 sous-jacents, script legacy sans contrat M_ : la note se génère quand
    même (phrases barrières simplement absentes)."""
    pdf = generate_valuation_pdf(_data(n_uls=3, monitors=False))
    assert pdf.startswith(b"%PDF")


def test_pdf_no_history_still_generates():
    d = _data()
    d["history"] = {"dates": [], "series": {}}
    pdf = generate_valuation_pdf(d)
    assert pdf.startswith(b"%PDF")


def test_explanation_ki_untouched_and_conclusion():
    lines = " ".join(build_explanation(_data()))
    assert "n'a jamais été touchée" in lines
    assert "92.6%" in lines                      # plus bas réalisé
    assert "104.78% du nominal" in lines         # le chiffre du MtM
    assert "au-dessus du pair" in lines
    assert "+6.28 point(s)" in lines             # 104.78 - 98.5


def test_explanation_ki_touched():
    lines = " ".join(build_explanation(_data(wof_min=0.55)))
    assert "a été touchée" in lines
    assert "désactivée" in lines


def test_explanation_best_case_capped():
    lines = " ".join(build_explanation(_data()))
    assert "meilleur dénouement" in lines
    assert "108.51%" in lines
    assert "96.6%" in lines            # capture ratio
    assert "mark-to-market" in lines   # conclusion renommée


def test_explanation_best_case_uncapped_no_signal():
    d = _data()
    d["mtm"]["best_case"] = {"pv_max": 1.85, "pv_p95": 1.42, "capped": False,
                             "capture_ratio": 0.57, "upside_pts": 80.2,
                             "upside_annualized_pct": 40.0, "horizon_years": 2.0,
                             "exit_signal": False}
    lines = " ".join(build_explanation(d))
    assert "scénario favorable" in lines
    assert "142.00%" in lines          # quantile 95
    assert "meilleur dénouement" not in lines   # pas de claim de cap ni de signal


def test_pdf_with_exit_signal_callout():
    d = _data()
    d["mtm"]["best_case"].update({"capture_ratio": 0.995, "upside_pts": 0.5,
                                  "upside_annualized_pct": 1.0, "exit_signal": True})
    pdf = generate_valuation_pdf(d)
    assert pdf.startswith(b"%PDF")


def _explain_data(n_uls=1):
    base = _data(n_uls=n_uls)
    return {
        "deal": base["deal"],
        "underlyings": base["underlyings"],
        "greeks": base["greeks"],
        "res": {
            "date1": "2024-07-12", "date2": "2026-07-19",
            "mtm1": 0.9616, "mtm2": 1.0656, "delta_pts": 10.40,
            "steps": [
                {"label": "Effet temps", "delta_pts": 4.97, "mtm_after": 1.0113},
                {"label": "Effet spot", "delta_pts": 3.66, "mtm_after": 1.0479},
                {"label": "Effet volatilité", "delta_pts": 1.78, "mtm_after": 1.0656},
            ],
            "residual_pts": 0.0,
            "flows_detached": [{"t": 1.0, "cf": 0.08}],
            "flows_total_pts": 8.0, "pnl_total_pts": 18.40,
            "market1": {"source": "booking", "model": "constant", "r": 3.0,
                        "sigma": {u["name"]: 22.0 for u in base["underlyings"]},
                        "q": {u["name"]: 2.0 for u in base["underlyings"]}},
            "market2": {"source": "realized", "model": "constant", "r": 3.0,
                        "window_returns": 180,
                        "sigma": {u["name"]: 13.32 for u in base["underlyings"]},
                        "q": {u["name"]: 2.0 for u in base["underlyings"]}},
            "phrases": ["Entre le 2024-07-12 et le 2026-07-19, la valeur est passée "
                        "de 96.16% à 106.56%."],
        },
    }


def test_explain_pdf_generates():
    pdf = generate_explain_pdf(_explain_data())
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 20_000    # waterfall chart + tables


def test_explain_pdf_negative_effects_and_no_greeks():
    d = _explain_data(n_uls=2)
    d["res"]["steps"][1]["delta_pts"] = -6.2      # effet spot négatif
    d["res"]["residual_pts"] = -0.03
    d["greeks"] = None                            # modèle non-GBM : pas de véga
    pdf = generate_explain_pdf(d)
    assert pdf.startswith(b"%PDF")
