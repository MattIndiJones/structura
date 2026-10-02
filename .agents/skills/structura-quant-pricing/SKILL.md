---
name: structura-quant-pricing
description: "Design, implement, diagnose, or review Structura pricing models and numerical calculations: Monte Carlo, GBM, Heston, SABR, Local Vol, LSV, rates in the engine, quanto, correlations, Greeks, calibration, parameter units, and numerical invariants. Use structura-payscript-scripting for authoring payoff scripts and structura-market-data for sourcing market inputs."
---

# Structura Quant Pricing

## Objective

Preserve the product's financial meaning, parameter traceability, reproducibility, and model-specific correctness before optimizing code.

## Workflow

1. Follow the project `AGENTS.md` and `CLAUDE.md`. Read the current implementation and relevant tests before proposing a design; verify dated notes against code.
3. State the product, payoff feature, risk driver, model, market input, calendar convention, and expected output affected by the change.
4. Trace each changed material parameter through the applicable parts of its path:
   - display unit in Vue;
   - Pinia/store representation;
   - request payload and Pydantic schema;
   - engine unit and actual model consumer;
   - booking snapshot, reload, MtM, Greeks, shocks, reports, and RFQ reuse when they consume it.
5. Distinguish a market observation, a calibration result, a user assumption, and the final value used by the engine. Never silently synchronize materially different model parameters.
6. Define invariants and failure behavior before editing. Reject invalid model domains rather than falling back silently.
7. Implement the smallest coherent change across every affected call path.
8. Validate proportionately with the smallest relevant deterministic tests: model-specific invariants, economic monotonicity, boundary cases, and targeted regressions.
9. Select the smallest relevant deterministic tests and follow the repository test and build rules in `CLAUDE.md`.

## Quantitative rules

- Use explicit units. Frontend percentages are generally display values; engine inputs are generally fractions. Verify rather than assume.
- Keep one seed and Common Random Numbers when comparing repricings, Greeks, or P&L explain components.
- Keep discounting, drift, forward construction, smile calibration, and stochastic-rate logic on the same rate/dividend conventions.
- Verify that a UI field affects the active model. A generic volatility field is not automatically the Heston initial variance or the SABR alpha.
- Preserve correlation symmetry, unit diagonal, domain bounds, and positive-semidefinite handling.
- Preserve path-dependent state when repricing a live product.
- Prefer a transparent conservative model to an implicit calibration or fallback that produces a plausible but mislabelled price.
- When affected, verify the strike or valuation date used as the simulation origin, discounting at payment dates, funding excluded from underlying drift, and raw prices for historical fixings. `CLAUDE.md` defines these conventions.

## References

- Read [model-and-unit-map.md](references/model-and-unit-map.md) for model parameter ownership, unit boundaries, repository routing, and test expectations.
- Read `docs/projects/lifecycle/EXPLICATION_VALO_DESIGN.md` before changing residual MtM or valuation explain.
- Read `docs/projects/pricing/PAYSCRIPT_PARAM_PAR_OBSERVATION.md` before changing observation-dependent parameters; check its implementation status against current code.
- Inspect `backend/app/core/payscript/engine.py`, `backend/app/core/schemas.py`, `frontend/src/stores/pricing.js`, and the relevant API endpoint for the current truth.

Use deterministic synthetic market data in quantitative unit tests, rather than live external calls.
