---
name: structura-product-lifecycle
description: Design, implement, diagnose, or review Structura workflows from RFQ and booking through fixings, lifecycle events, residual MtM, valuation explain, and reporting. Use for contractual state transitions, immutable snapshots, four-eyes controls, audit events, and portfolio P&L. Use structura-quant-pricing for pricing-model changes.
---

# Structura Product Lifecycle

## Objective

Preserve a deterministic, auditable chain around the canonical `Product` dossier, from pricing and RFQ to the booked Deal, contractual fixings, lifecycle resolution, residual valuation, and reporting.

## Workflow

1. Follow the project `AGENTS.md` and `CLAUDE.md`. Read the current Product and Deal models, workflow enums, API endpoint, UI state handling, and relevant tests before changing an object, status, or transition.
2. Draw the affected state transition and identify:
   - actor and authorization;
   - preconditions;
   - immutable inputs;
   - persisted outputs;
   - audit event;
   - idempotency or deduplication key;
   - rollback or manual-review path.
3. Identify which object owns each changed fact. Trace the same Product identity, terms version, and revision through every affected module and back into the coherent dossier; trace frozen booking data into the Deal snapshot and downstream consumers.
4. Distinguish contractual truth from derived display status. Do not let the frontend invent authoritative state.
5. Keep proposals, validation, and application separate when four-eyes control applies.
6. Preserve path-dependent state and realized cash flows in residual MtM.
7. Make automated fallbacks and manual exceptions explicit and auditable.
8. Test the affected transition and its adjacent invariants. Choose duplicate-request, stale-proposal, authorization, market-data, and resolved-product cases when the change can affect them; follow `CLAUDE.md` for targeted test scope.

## Canonical Product and module routing

- `Product` is the common business object for Pricer, RFQ, Booking, lifecycle, Risk, documents, and secondary consumers. For product information, each module receives `Product` or a projection produced by the Product core. Do not reconstruct a competing product definition by decoding a Deal, RFQ, market snapshot, or script locally.
- Use the frozen `backend/app/core/product/models.py::Product` shape as the canonical dossier: stable identity and reference; revision and contractual terms version; `terms`; trade `intent`; `commercial` context; `indicatives` and `rfqs`; optional `execution` and `lifecycle`; `documents` and `calculations` references. The dossier may be built in memory before the user explicitly retains it; a persisted Product does not imply a booked Deal.
- Preserve round trips between modules. A module reads the same Product definition, contributes only the facts it owns through an explicit, validated, versioned operation, and returns a coherent updated Product/projection. Preserve other modules' facts; never mutate a shared instance, silently rewrite terms, or apply module-local defaults to a loaded product.
- Keep authoritative facts in their owning records: contractual terms in Product terms versions; booked position and execution in Deal; official fixings and resolutions in versioned lifecycle records. Product revisions assemble the coherent dossier. Link a booked Deal to the Product identity and executed terms version.
- Supply current market observations, curves, volatilities, model settings, and calculation context separately. Product may hold calculation references or summaries; detailed effective inputs and results belong to their dated calculation records, not to current contractual terms.
- When changing a consumer, check whether it still uses a legacy Deal-based or local decoding path. The architecture plan describes the target; verify the current implementation before claiming the whole flow already complies.

## Lifecycle rules

- Treat `Product` as the versioned business dossier and `Deal` as the booked execution/position object. A Product can exist before booking; a Deal must represent an actual booking. Do not use a Deal as a placeholder for exploration or RFQ.
- For linked deals, keep `product_id`, the executed `product_terms_version`, and the Deal's frozen contract consistent. The Product's execution and lifecycle blocks project booked facts; they are not a second independent editor of the Deal.
- In new booking flows, require an explicit Product link and the executed terms version; do not create an orphan Deal.
- Freeze script, calendars, effective user parameters, market assumptions, economic terms, and fixing policy at booking. Preserve selected quote linkage when booking from an RFQ.
- Do not rebuild a booked deal from a subsequently edited RFQ or current pricer state.
- Derive ordinary RFQ statuses from facts where the existing workflow does so; reserve explicit terminal or user decisions for the defined transitions.
- Keep official fixings versioned and separate from indicative monitoring values.
- Never overwrite contractual history to make a current view look consistent.
- A recalled or matured product must follow resolution/reporting logic, not an active-product MtM path.
- Generate documents from the selected frozen valuation run when that workflow archives one. For a recomputed report, preserve the same valuation inputs and seed as the displayed run.
- Preserve P&L identities and surface residuals rather than burying them.

## References

- Read [lifecycle-invariants.md](references/lifecycle-invariants.md) for the end-to-end chain, authoritative files, and test matrix.
- Read `docs/projects/platform/PLAN_IMPLEMENTATION_OBJET_PRODUCT.md` when changing Product/Deal ownership, linking, or versioning; its implementation status is dated, so verify against `backend/app/core/product/models.py`, `backend/app/db/models.py`, and the current services.
- Use `docs/README.md` to find the current note for the affected phase. For daily MtM and Valo Explain, start with `docs/projects/lifecycle/BOOKING_MTM_QUOTIDIEN_2026-09-17.md` and `docs/projects/lifecycle/VALO_EXPLAIN_2026-09-17.md`; read `docs/projects/lifecycle/EXPLICATION_VALO_DESIGN.md` when changing the earlier between-dates P&L waterfall. Verify dated claims against code.
- Inspect `backend/app/core/workflow.py`, `backend/app/db/models.py`, `backend/app/api/rfq.py`, `backend/app/api/deals.py`, and the corresponding Pinia stores/views.

## Operational constraints

- Treat `backend/data/structura.db` as real user data. Never modify, replace, or version it for tests.
- Use isolated in-memory or temporary databases for automated tests.
- Follow `CLAUDE.md` for repository-wide operational rules.
