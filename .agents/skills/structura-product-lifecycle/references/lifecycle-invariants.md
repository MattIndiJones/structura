# Structura product lifecycle invariants

## Authoritative routing

- Product domain object and terms: `backend/app/core/product/models.py`
- Product identity, terms versions, revisions, and Deal row: `backend/app/db/models.py`
- workflow values and derived statuses: `backend/app/core/workflow.py`
- persisted entities: `backend/app/db/models.py`
- RFQ endpoints and controls: `backend/app/api/rfq.py`, `backend/app/core/rfq_controls.py`
- booking, events, lifecycle, residual MtM: `backend/app/api/deals.py`
- market snapshot and residual valuation: `backend/app/core/market_snapshot.py`, `backend/app/core/deal_valuation.py`
- lifecycle alerts: `backend/app/services/lifecycle_alerts.py`
- frontend stores/views: `frontend/src/stores/rfq.js`, `deals.js`, `pricing.js`, `views/RfqView.vue`, `views/BookingView.vue`
- valuation reports: `backend/app/core/deal_valuation_pdf.py`

## End-to-end chain

1. Define and price a PayScript with explicit market assumptions and calendar.
2. If the RFQ route is used, create an indicative or executable RFQ with frozen pricing input, receive quotes, and select an eligible quote while preserving provider/counterparty semantics.
3. Book once from the selected RFQ or directly from the pricer.
4. Freeze economics, script, calendars, effective PARAM values, underlyings, market assumptions, and fixing policy.
5. Monitor observations without turning indicative data into official contractual facts.
6. Capture or validate official fixings under the booked policy.
7. Create, validate, and apply lifecycle proposals with explicit status transitions.
8. While active, price the residual product, explain P&L, and generate reports from the applicable stored valuation inputs.
9. Resolve recalled or matured products and persist realized cash flows; use resolution reporting after the active MtM path ends.

## Product and Deal ownership

`Product` is the frozen business object used to read a coherent dossier: identity, versioned contractual terms, commercial context, RFQ references, execution, lifecycle facts, documents, and calculation references. Its persistence uses `ProductRecord`, `ProductTermsVersion`, and `ProductRevision`. Current market observations and model assumptions remain outside contractual terms.

Route product information in both directions through this canonical dossier: Pricer, RFQ, Booking, lifecycle, Risk, and document workflows consume `Product` (or a projection created by its core) and add only their owned facts through explicit versioned operations. Carry the same identity and applicable terms version across handoffs; return a coherent Product revision after a change. Do not let a module recreate terms from Deal/RFQ/script/market snapshots or independently edit another module's block. This is the architectural target; inspect a touched service for legacy paths rather than assuming every consumer has migrated.

`Deal` is the SQLModel execution and portfolio-position object created by booking. It has its own business reference, traded economics, contract snapshot, fixing policy, contract version, and operational lifecycle state. For a linked Deal, `product_id` and `product_terms_version` identify the Product and contractual version executed. The Product's execution/lifecycle view projects the authoritative Deal and versioned lifecycle facts; do not maintain an independent competing copy through the browser.

Assign a material change to its owner before editing: intrinsic contract terms to a Product terms version; executed trade and position facts to Deal and governed amendments; official fixings and resolutions to their versioned lifecycle records; valuation market inputs to a dated calculation or booking snapshot. Keep the Product revision consistent with the underlying business transaction. An unbooked Product has no Deal; a newly booked Deal must link to the Product and executed terms version.

## Frozen booking contract

A booked deal must remain reproducible if:

- the source script is edited;
- the RFQ is edited or quotes are removed;
- Yahoo values change;
- UI defaults change;
- model defaults change;
- a counterparty label changes.

Preserve the original RFQ/selected quote relationship when applicable, direction convention, fair value, traded price, script snapshot, market snapshot, schedule, and effective user parameters.

Display units and engine units must not be mixed in the snapshot. Read current serialization and reload code before changing it.

## Status and authority

- Derive ordinary RFQ business status from persisted facts where the workflow already does so.
- Treat booking as idempotent: one RFQ must not create multiple deals.
- Freeze fixing policy at booking.
- Keep indicative Yahoo monitoring separate from official fixing versions.
- Under four-eyes control, separate proposal, validation, and application actors/states.
- Reject stale or conflicting proposals explicitly.
- Use audit events for material state changes.
- Never let a UI-only selection become contractual state without server validation.

## Residual valuation

Residual MtM must combine:

- frozen product definition;
- elapsed calendar and remaining events;
- realized path-dependent state;
- realized cash flows;
- normalized current spots;
- selected market mode and explicit overrides;
- reproducible seed and path count.

For a recomputed valuation report, the same body and seed must reproduce the on-screen value. A note built from an archived valuation run must use that run's frozen inputs and outputs. A product already resolved should enter resolution/reporting logic, not active MtM.

For the earlier between-dates MtM waterfall, preserve its telescoping identity: `MtM(d2) - MtM(d1) = time + spot + volatility + optional correlation + residual`. Detached cash flows are separate; period P&L includes them.

For the Valo Explain module comparing two archived runs, first reproduce both stored prices. Attribute the difference only when contractual versions, model, and numerical settings are compatible. Its factor sequence can also include dividends, rates, funding, and remaining receivables; preserve the declared order and leave unattributed effects in the residual. See `docs/projects/lifecycle/VALO_EXPLAIN_2026-09-17.md`.

## Select relevant tests

Choose cases that cover the changed phase and adjacent invariants; do not run this entire matrix for every lifecycle edit:

- direct booking and booking from RFQ;
- duplicate booking request;
- selected quote outside the RFQ;
- provider without eligible booking counterparty;
- script or RFQ edited after booking;
- reload exact frozen market state;
- auto-fixing and four-eyes fixing paths;
- duplicate, stale, unauthorized, and conflicting lifecycle proposals;
- recalled, matured, cancelled, and active products;
- Yahoo outage during indicative monitoring;
- residual MtM with path-dependent knock-in state;
- report equals screen value when they use the same frozen run or identical repricing inputs;
- portfolio sign and cash-flow identities;
- isolated temporary database with no mutation of real `structura.db`.
