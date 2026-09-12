"""A future observation just beyond the replay cut remains simulated."""
from backend.app.core.compute.pricers import scenario_grid, var_scenario
from backend.app.core.payscript import engine


SCRIPT = "AT 0.5\n  PAY 1\n"


def test_var_worker_keeps_event_after_exact_replay_cut(monkeypatch):
    captured = {}

    def fake_run(script, _context, **_overrides):
        captured["dates"] = [d for event in script.events for d in event.dates]
        return {"price": 1.0}

    monkeypatch.setattr(var_scenario, "run_valuation", fake_run)
    result = var_scenario.price_var_scenario_job({
        "script_text": SCRIPT, "value_date": "2026-01-01",
        "T_elapsed": 0.49, "passe_jusqu_a": 0.49,
        "state": {}, "norm_spots": [1.0], "corr": [[1.0]],
        "valuation_context": {"version": 1},
    })

    assert result["price"] == 1.0
    assert captured["dates"] == [0.01]


def test_scenario_grid_worker_keeps_event_after_exact_replay_cut(monkeypatch):
    captured = {}

    def fake_mc(script, *_args, **_kwargs):
        captured["dates"] = [d for event in script.events for d in event.dates]
        return {"price": 1.0}

    monkeypatch.setattr(engine, "run_mc", fake_mc)
    result = scenario_grid.price_scenario_grid_job({
        "script_text": SCRIPT, "underlyings": [{"name": "UL1", "sigma": 0.2}],
        "corr": [[1.0]], "r": 0.03, "T": 0.01, "n_paths": 1000,
        "model": "constant", "seed": 42, "residual_elapsed": 0.49,
        "residual_passe": 0.49, "state_spots": [1.0], "residual_state": {},
    })

    assert result["price"] == 1.0
    assert captured["dates"] == [0.01]
