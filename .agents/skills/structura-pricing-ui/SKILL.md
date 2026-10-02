---
name: structura-pricing-ui
description: Design or refine Structura Vue interfaces for the Pricer, market parameters, RFQ, Booking, valuation, and related product workflows. Use for forms, tables, states, warnings, and model-aware controls. Use structura-product-lifecycle for contractual transitions and structura-payscript-scripting for payoff-script logic.
---

# Structura Pricing UI

## Objective

Create compact institutional interfaces that make the pricing workflow faster while keeping financial meaning, data provenance, editability, and the value used by the engine unambiguous.

## Workflow

1. Follow the project `AGENTS.md` and `CLAUDE.md`. Inspect the current Vue component, Pinia store, API contract, and neighboring workflow; trace the engine consumer when the edit changes a pricing input.
2. Identify the user's operational decision and the primary action for the zone, if one is appropriate.
3. Separate visually, where the workflow uses them:
   - source observation;
   - editable assumption;
   - manual override state;
   - final value used by pricing;
   - advanced model parameters.
4. Choose compact tables or multi-column forms when they improve scanning at the available width. Avoid duplicate controls bound to the same value.
5. Make model-specific behavior explicit. If a displayed volatility does not drive the active model, label it as a reference or show the exact mapping.
6. For PayScript parameters, show the effective Economics value and its unit. The script declares payoff logic and initial values; an Economics override is the value to send to pricing. Do not imply that a displayed script default remains authoritative after an override.
7. Keep units in labels, validation messages, snapshots, and results consistent.
8. Verify keyboard focus, disabled/loading states, narrow viewport behavior, and sensitive/demo-mode rendering where affected.
9. Run `npm run build` from `frontend/` after every Vue change, as required by `CLAUDE.md`.

## Design rules

- Keep the existing restrained light institutional design and reuse shared classes from `frontend/src/style.css`.
- Prefer stable card hierarchy, compact spacing, aligned numeric inputs, tabular numerals, and restrained badges.
- Use badges for provenance and status, not decoration.
- Put warnings next to the value or action they qualify.
- Keep destructive or sensitive actions behind the existing modal pattern.
- Use existing `HelpTip`, `SensitiveValue`, loading, alert, and modal components.
- Do not hide a material pricing assumption behind automatic synchronization.
- Preserve a clear path from input to price, booking, or lifecycle action. Use `structura-product-lifecycle` when the change alters an authoritative state transition; use `structura-payscript-scripting` when it alters the payoff language or contract logic.

## References

- Read [pricing-ui-conventions.md](references/pricing-ui-conventions.md) for component routing, market-parameter patterns, Economics display, and relevant verification.
- Inspect `frontend/src/components/MarketParams.vue`, `DealTab.vue`, `EventsTab.vue`, `frontend/src/stores/pricing.js`, and the affected view.

Follow `CLAUDE.md` for repository-wide operational rules. Preserve unrelated frontend work and generated `dist` files.
