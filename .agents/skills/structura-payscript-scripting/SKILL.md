---
name: structura-payscript-scripting
description: Design, write, review, or debug Structura PayScript payoff scripts and product templates from a term sheet. Use for PARAM, CONSTAT, AT, PAY, STOP, coupon memory, barriers, autocalls, maturity flows, and script validation. Use structura-quant-pricing when changing the Monte Carlo engine or pricing models.
---

# Structura PayScript scripting

Turn the contractual payoff into an explicit, executable PayScript and prove that it represents the intended product. A script that parses but pays the wrong cash flows is incomplete.

## Sources of truth

1. Follow the repository `AGENTS.md` and `CLAUDE.md` for role, pricing conventions, tests, and operational rules.
2. Read `docs/reference/PAYSCRIPT_REFERENCE.md` before authoring or changing a script. It is the maintained language manual and supplies the AI scripting prompt; `backend/tests/test_payscript_reference.py` checks its vocabulary against `backend/app/core/payscript/parser.py::language_vocabulary`. Search the relevant sections again when using a less familiar feature.
3. Use `backend/app/core/payscript/parser.py`, `schedule_model.py`, and the focused tests for actual compiler and schedule behavior. Resolve any disagreement between code and documentation explicitly; do not invent syntax or silently assume a proposal in a dated design note was implemented.
4. For existing product patterns, inspect `backend/app/core/payscript/catalogue.py`, `backend/app/core/payscript/templates.py`, and `frontend/src/data/payscriptTemplates.js`. A template is an example to verify, not proof that a different term sheet has identical economics.

## Translate the term sheet before writing code

Record the payoff from the relevant investor or issuer perspective, nominal, currency, underlyings and aggregation, initial fixing, observation and payment calendars, coupons, autocall, capital repayment, and all state carried between observations. Distinguish a point fixing, a window reduction, a period average, and monitoring between dates. Identify which levels are thresholds and whether their barriers are European or American.

Write a compact event and cash-flow table: at each contractual date, list the observed value, condition, cash flow as a fraction of nominal, state update, and whether the contract stops. Include the never-called maturity path. Resolve material ambiguities with Philippe before committing to a payoff interpretation; do not fill in a missing date, barrier type, memory rule, or settlement convention by guesswork.

Separate what belongs in the script from what belongs in Economics. The script declares payoff logic, `PARAM`/`PARAM()` names, units, and initial values, plus `CONSTAT` shapes and reduction types. Economics supplies effective parameter values, dates, windows, conventions, and payment settings. Check current code for the exact override behavior whenever a saved script, RFQ, or deal is involved. Keep material choices visible and named.

## Author the script

- Use only vocabulary and forms documented in `PAYSCRIPT_REFERENCE.md`. `PARAM` and `PARAM()` require an initial value; `%` changes the stored unit. Avoid reserved names. Use `M_` for contract barriers that need Booking monitoring.
- Express market levels relative to the initial fixing (`1` means 100% of `S0`) and `PAY` amounts as fractions of nominal. Use `S[i]` with one-based indices. Do not mix a percentage display number with its decimal payoff value.
- Choose `CONSTAT` for a single date, `CONSTAT()` for a schedule, and `CONSTAT()()` only when each parent interval needs its own fine observation grid. Use `MIN`, `MAX`, `AVG`, and `PERIOD` for contractual window reductions; leave window length and sampling frequency to Economics.
- Anchor literal `AT` dates on the strike. Prefer named `AT` calendars when the product's actual dates matter. `INDEX` is the rank in the named schedule, not a count of executed coupons or an index for `AT MATURITY`. `PARAM()` values follow that same observation schedule and cannot silently serve two different schedules.
- Distinguish current `WOF`/`BOF`/`S[i]` from path extrema such as `WOF_MIN`. A European terminal barrier and an American knock-in are different products. For windowed observations, reduction is per underlying before basket aggregation; a two-level `AT` qualifier reads the raw fixing of a subdate.
- Initialize contract memory with top-level `SET` and update it at the event that changes the entitlement. Use `ACCRUE` when value accumulates without payment. Couple an early redemption cash flow with `STOP`; ensure nominal is paid once. Finish with `AT MATURITY` for every surviving path, without `INDEX` in that block.
- Keep cash-flow labels useful for the flow table and valuation explain. Check strike, observation, maturity, value, and payment dates separately; discounting belongs to the payment date. Historical fixings use unadjusted prices.

For feature-to-language decisions, scenario coverage, and routing of validation, read [payoff-authoring-checklist.md](references/payoff-authoring-checklist.md). Consult the full language manual for exact syntax and examples; do not copy an approximate grammar into this skill.

## Validate the economics and implementation

1. Parse the exact script with `parse_script` or `/api/parse`, and inspect parameters, constats, event count, maturity, literal dates, and monitor metadata. Parsing validates syntax; it does not prove a payoff.
2. Resolve the actual Economics inputs and calendars. Check observation order, strike origin, last observation versus maturity, windows, rolls, and settlement dates. Never treat a date proposed by a template as a contractual date without checking it.
3. Evaluate deterministic paths representing the relevant branches: above and below each barrier, equality at boundaries, early call, no call, memory catch-up, and the terminal loss or protection case. Compare individual cash flows and stop behavior with the event table before relying on a Monte Carlo price.
4. Price with controlled market inputs if useful, then check magnitudes and economic sensitivities only where their direction is justified by this payoff. If a parameter is intended to matter, verify that changing its effective Economics value changes the relevant flows or price.
5. When changing language behavior, update the parser, `PAYSCRIPT_REFERENCE.md`, and focused parser/reference tests together. When changing a catalogue or template script, run its focused compile/pricing checks. For a script used in a live deal, assess booking snapshot, fixing policy, residual MtM, and downstream documents with `structura-product-lifecycle` where relevant.

Deliver the script together with its required Economics inputs, payoff decision table or representative scenarios, validation evidence, assumptions, and remaining contractual questions. Do not present a parser success or one plausible price as full product validation.
