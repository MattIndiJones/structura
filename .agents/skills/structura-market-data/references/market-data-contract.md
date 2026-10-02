# Structura market-data contract

## Five layers

Keep these layers distinct in code, API responses, snapshots, and UI:

1. **Raw observation**: provider field, ticker, timestamp, currency, adjustment convention.
2. **Derived measure**: realized volatility, correlation, dividend yield, normalized spot.
3. **User assumption**: editable value selected for pricing.
4. **Value used**: exact engine input after units, fallback, and model mapping.
5. **Frozen snapshot**: auditable copy stored with a booked deal or generated report.

Never overwrite layer 1 when layer 3 changes. Never describe layer 3 or 4 as provider data unless it is unchanged from layer 1/2.

## Minimal provenance

For material data, retain or return as applicable:

- provider;
- ticker or instrument identifier;
- field or methodology;
- observation/as-of timestamp;
- fetch timestamp;
- period and number of observations;
- currency;
- adjusted/unadjusted convention;
- source value and unit;
- override value, author/time if persisted;
- fallback reason;
- final value and engine unit.

## Current repository routing

- provider services: `backend/app/services/market_data.py`
- HTTP endpoints: `backend/app/api/market_data.py`
- Pricer loading and unit conversion: `frontend/src/stores/pricing.js`
- RFQ market inputs: `frontend/src/views/RfqView.vue`
- booking snapshot and residual calibration: `backend/app/api/deals.py`
- market-data administration/cache: `frontend/src/views/AdminMarketDataView.vue`

Inspect the current implementation before relying on historical documentation.

## Yahoo conventions and caveats

- Realized volatility is a derived historical statistic, not implied volatility.
- Yahoo dividend yield metadata can be absent, stale, trailing, or economically different from a forward dividend assumption.
- Adjusted closes are suitable for total-return history and many backtests; contractual fixing closes require a separate unadjusted, timestamped feed.
- Stock splits and extraordinary dividends require explicit treatment.
- Yahoo end dates can be exclusive; verify boundary handling.
- Timezone normalization must not create or shift contractual dates.
- Historical dividend estimates come from `dividend_profile(ticker, asof)`: retain both `yield_declared` and `yield_implied`, with the `suspect` diagnostic when they diverge. Neither is a guaranteed forward cash-dividend schedule.

## Alignment rules

- Forward-fill only after a real observation and only where the workflow permits it.
- Never backward-fill a leading gap.
- For a basket history, start on the first date where every required constituent has a genuine or legitimate forward-filled observation.
- Report an effective start date when it differs from the requested start.
- Keep missing-ticker details in the payload.

## Fallback rules

Define priority per workflow. A valid example for residual MtM may be:

1. explicit manual override;
2. requested current realized calibration;
3. frozen booking assumption.

Do not reuse this priority blindly for contractual fixing or initial pricing. Contractual data needs a separate policy and audit path.

Every fallback must:

- preserve units;
- record the rejected source and reason;
- remain visible to the user;
- avoid mutating the frozen booking snapshot;
- be covered by a deterministic test.

## Select relevant tests

Choose cases that exercise the changed source, convention, or consumer:

- complete provider response;
- missing dividend metadata;
- unknown ticker;
- one ticker with shorter listing history;
- different exchange calendars;
- timezone-aware indices;
- split inside the window;
- adjusted versus unadjusted divergence;
- provider outage and stale cache;
- source value followed by manual override;
- booking/reload preserves the used value exactly.
