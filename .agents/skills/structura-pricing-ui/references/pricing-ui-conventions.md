# Structura pricing UI conventions

## Repository routing

- shared visual system: `frontend/src/style.css`
- pricing state and API bodies: `frontend/src/stores/pricing.js`
- market parameters: `frontend/src/components/MarketParams.vue`
- product identity and booking input: `frontend/src/components/DealTab.vue`
- event workflow: `frontend/src/components/EventsTab.vue`
- pricing output: `frontend/src/components/ResultsPanel.vue`
- RFQ and booking views: `frontend/src/views/RfqView.vue`, `BookingView.vue`
- privacy/demo rendering: `SensitiveValue.vue` and demo-mode store

## Market-parameter pattern

For each repeated underlying, prefer one compact row with:

- identity and ticker;
- provider reference;
- editable value used;
- source/override badge;
- optional reset-to-source action;
- advanced-model drill-down.

Do not place the only editable volatility or dividend control far below its provider status. Do not duplicate the same control in both a loader card and a calibration card.

Use labels such as:

- `Référence Yahoo`;
- `Valeur utilisée`;
- `Surcharge manuelle`;
- `Non disponible — hypothèse conservée`.

## Model-aware controls

A field must either drive the active model or be labelled as a reference only.

- GBM: display spot volatility.
- Heston: distinguish spot-volatility reference from initial variance `V0` and long-run variance `theta`.
- SABR: distinguish spot-volatility reference from `alpha`.
- Local Vol/LSV: identify the level used for the local-vol target and the stochastic-variance leg.

If one edit seeds several parameters, disclose the exact mapping in the UI and preserve independent advanced edits. Avoid silent two-way coupling.

## PayScript and Economics

The script declares payoff logic, each parameter's unit, and an initial value. Economics supplies the effective value when the user has entered an override. Display the source and effective value without confusing a script default with the number sent to pricing. Check the outgoing `user_params` and the downstream consumer when editing this flow; changing the label alone does not prove the engine received the value. See `docs/projects/pricing/EDITEUR_ECONOMICS_DESIGN.md` for Philippe's decision, and verify dated implementation notes against current code.

## Form and table rules

- Reuse `.card`, `.input`, `.select`, `.btn-*`, `.badge-*`, and `.table-shell`.
- Use multiple columns when they improve scanning without compressing labels or forcing horizontal overflow on narrow screens.
- Right-align financial numerics and include units in headers or labels.
- Keep one primary action per card.
- Use restrained semantic colors: positive, warning, negative, accent, muted.
- Keep status and error text close to the relevant action.
- Use existing modal patterns for destructive or sensitive actions.
- Preserve responsive overflow for dense tables rather than wrapping identifiers badly.

## Select relevant verification

Choose checks that cover the controls and states changed:

- loading, editing, reset, missing source, and provider-error states;
- an edited Economics value changes the outgoing pricing body when applicable;
- switching models does not display a misleading used value;
- adding/removing underlyings or changing tickers does not retain stale provenance;
- demo mode and sensitive values;
- keyboard focus and disabled/loading behavior.
- Run `npm run build` from `frontend/`.
- Visually inspect the affected screen at desktop and narrow widths when possible.

Do not edit `frontend/dist` manually. Let the required build regenerate it.
