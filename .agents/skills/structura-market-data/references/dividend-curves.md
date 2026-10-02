# Dividend term structures in Structura

## Implemented convention

Structura prices equity dividends through a scalar yield `q` or a piecewise-constant annual yield curve `q(t)`. The current engine does not implement dated cash-dividend jumps or a long-run yield floor. Do not present either as an available pricing mode or silently substitute one for the other.

For a historical as-of date, use `dividend_profile(ticker, asof)`. Its `yield_declared` is the pricing convention; `yield_implied` is a cross-check from adjusted versus raw prices. A `suspect` divergence needs investigation. A trailing Yahoo metadata field is not a dated forward-dividend observation, and a historical yield used as `q1` remains a pricing assumption.

## Recommended simple yield curve

Keep the first year flat at `q1`. For annual bucket `n >= 1`:

`q_n = q1 * (1 - decay)^(n - 1)`

Parameters:

- `q1`: first-year annualized yield;
- `decay`: relative annual decline, where 0 means flat;

Use piecewise-constant rolling tenor buckets:

- year 1: `(0, 1Y]`;
- year 2: `(1Y, 2Y]`;
- continue through effective maturity;
- apply the last relevant bucket pro rata to a partial final year.

Avoid implicit interpolation. If smoothing is later required, make the interpolation convention a named parameter.

## Pricing convention

The dividend term enters the equity drift in the models that consume it. Check the exact rate, repo, quanto, and currency terms in the active model rather than substituting a generic drift formula. In the simple deterministic domestic case without quanto or basis, the forward consistency condition is:

`F(0,T) = S0 * exp(integral_0^T (r(u) - q(u)) du)`

Discounting uses the applicable rate and funding conventions, not the dividend curve. When changing this input, trace it through Local Vol calibration, paths, Greeks, scenarios, MTF, booking, and residual MtM wherever those consumers apply. The funding curve must stay out of equity drift, as required by `CLAUDE.md`.

## Future cash-dividend work

A dated cash-dividend schedule would require an explicit product and model change, especially for single-stock barriers. Before proposing it, define ex-date jumps, tax and currency conventions, extraordinary dividends, corporate actions, and the interaction with historical fixings and calibration. It is not the current Structura pricing path.

## UI and audit expectations

Expose:

- mode: scalar yield or declining yield curve;
- source and as-of date for `q1`;
- editable `q1` and `decay`;
- generated annual nodes through maturity;
- source versus override versus used value;
- a compact table and curve preview;
- the exact nodes frozen at booking.

Store both the generating parameters and generated nodes when booking. The nodes provide replay determinism; the parameters explain the curve.

## Validation

- `q1 >= 0`;
- `0 <= decay <= 1` for a strictly declining mode;
- finite nodes through maturity;
- flat mode and `decay = 0` reproduce the legacy constant-`q` price;
- generated curve is non-increasing;
- higher dividend carry lowers forwards, all else equal;
- partial-year integration is exact;
- every model receives the same `q(t)`;
- booking and reload reproduce identical nodes and price.

`CLAUDE.md` notes that stock-borrow/repo cost currently enters through `q`; identify that component explicitly when it is material. Do not label it as an observed cash-dividend yield.
