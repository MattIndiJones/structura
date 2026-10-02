---
name: structura-market-data
description: Design, implement, diagnose, or review Structura market-data sourcing and use. Apply to prices, contractual fixings, volatility estimates, dividends, rates, FX, correlations, caches, provenance, overrides, fallbacks, and market snapshots. Use structura-quant-pricing for pricing-model mathematics.
---

# Structura Market Data

## Objective

Make every market input in Structura explainable from source observation to value used by pricing. Prefer existing stored data, explicit provenance, and safe degradation over hidden refetches or silent substitutions.

## Workflow

1. Follow the project `AGENTS.md` and `CLAUDE.md`. Classify the requested datum: contractual fixing, raw market observation, adjusted history, derived calibration, forward assumption, or manual override.
2. Inspect the existing service, API, store, snapshot, and consumers before introducing a source or schema.
3. Reuse database or cache data already in scope before considering an external fetch.
4. Define:
   - provider and field;
   - observation timestamp and as-of date;
   - adjusted/unadjusted and price/dividend convention;
   - display and engine units;
   - missing-data and stale-data behavior;
   - override priority and audit trail;
   - persistence and reproducibility requirements.
5. Keep source values separate from editable assumptions and final used values.
6. Ensure every fallback is visible in the response and UI. Never label a fallback or override as provider data.
7. Select deterministic tests for the affected source and consumer; use mocked provider responses for missing data, stale data, timezones, corporate actions, or basket alignment when relevant.

## Source rules

- Do not call realized volatility implied volatility.
- Do not call a trailing Yahoo dividend yield a known forward dividend.
- For historical dividend estimation, use `dividend_profile(ticker, asof)`: `yield_declared` is the pricing convention, while `yield_implied` checks the adjusted/unadjusted price gap. Surface `suspect` rather than hiding a divergence.
- Keep adjusted total-return histories separate from unadjusted contractual closes.
- Never backfill dates before a security's first genuine observation.
- For baskets, do not replay a worst-of before all constituents have valid simultaneous observations.
- Freeze the exact market assumptions used at booking; do not reconstruct them later from the current provider response.
- Allow manual overrides where the workflow requires judgment, but retain the provider reference separately.

## References

- Read [market-data-contract.md](references/market-data-contract.md) for the source/value/override contract and current repository routing.
- Read [dividend-curves.md](references/dividend-curves.md) when changing dividend assumptions or term structures. It distinguishes the implemented declining-yield curve from future cash-dividend possibilities.
- Inspect `backend/app/services/market_data.py`, `backend/app/api/market_data.py`, `frontend/src/stores/pricing.js`, and booking/MtM consumers before changing behavior.

Avoid real network calls in automated tests; inject deterministic provider data. Follow `CLAUDE.md` for repository-wide operational rules.
