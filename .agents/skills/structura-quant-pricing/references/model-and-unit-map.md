# Structura pricing model and unit map

## Read current code first

Use this map as a routing aid, not as a substitute for the repository:

- frontend state and display conversion: `frontend/src/stores/pricing.js`
- pricing form: `frontend/src/components/MarketParams.vue`
- request contracts: `backend/app/core/schemas.py`
- API orchestration: `backend/app/api/pricing.py`
- simulation and Greeks: `backend/app/core/payscript/engine.py`
- parser and calendar resolution: `backend/app/core/payscript/parser.py`
- residual pricing: `backend/app/api/deals.py::_mtm_core`
- tests: `backend/tests/test_engine.py`, `test_engine_golden.py`, `test_curve_consistency.py`, `test_greeks_stateful.py`, `test_mtm_explain.py`

## Unit boundary

The Vue store generally keeps human display units and `_buildUls()` converts them to engine units:

| Quantity | Typical display | Engine/API |
|---|---:|---:|
| spot volatility `sigma` | 20 (%) | 0.20 |
| dividend yield `q` | 2 (%) | 0.02 |
| Heston `v0`, `theta` | 4 (% variance) | 0.04 variance |
| Heston `xi` | 35 (%) | 0.35 |
| correlations | -70 (%) or matrix decimal depending control | -0.70 |
| SABR `alpha`, `nu` | 20, 40 (%) | 0.20, 0.40 |
| SABR `beta` | 50 (%) | 0.50 |
| FX volatility | 10 (%) | 0.10 |
| cross-currency basis | basis points | decimal rate |
| scalar rate | 3 (%) in UI | 0.03 in request |

Verify every boundary in current code. Do not infer units from a variable name.

## Parameters consumed by model

- Constant/GBM: `sigma`, `q`, quanto fields, rates, correlations.
- Heston: `v0`, `kappa`, `theta`, `xi`, `rho_h`, `q`; `sigma` is not the Heston initial diffusion level.
- SABR: `alpha`, `beta`, `rho`, `nu`, `q`.
- Local Vol: `sigma`, `skew`, `curvature`, `q`, and the same rate term used for pricing.
- LSV: Local Vol target fields plus the Heston variance process fields.
- Stochastic rates: `sigma_r`, `a_r`, and per-underlying `rho_rS`.
- Quanto: `sigma_fx`, `rho_sfx`, and `ccyh`; verify the sign convention in the drift.

If one UI volatility control must seed several models, define the mapping explicitly. In particular, a displayed volatility `x%` maps to Heston variance display `x²/100`, not `x`. Decide whether only `v0` or also `theta` changes; never hide that decision.

## Change-impact checklist

For a new or changed input, inspect the applicable consumers. Do not assume every change touches every surface:

1. default underlying object;
2. Vue control and validation;
3. store conversion;
4. Pydantic schema and bounds;
5. every simulator branch;
6. Greeks and shock vocabulary;
7. paths, profile, backtest, MTF, scenarios, KID, EMT, RFQ;
8. booking snapshot and reload;
9. residual MtM and valuation explain;
10. PDFs and API response metadata.

## Select relevant quantitative tests

Choose from these checks according to the changed calculation and its failure modes:

- fixed seed reproducibility and Common Random Numbers for repricing comparisons;
- antithetic on/off sanity when changing path generation;
- flat-curve backward compatibility when changing term structures;
- monotonicity only where the payoff and model make it economically valid;
- evidence that a changed parameter actually affects price or paths;
- explicit rejection of invalid model domains;
- one-asset and multi-asset cases when changing correlations;
- retained path-dependent state when changing residual pricing;
- frontend-to-engine unit round trip when changing a displayed input;
- a golden regression when unchanged legacy inputs should remain stable.

Use Common Random Numbers for comparisons. Assert economic identities in addition to numeric snapshots.
