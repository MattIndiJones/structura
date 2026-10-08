# PayScript payoff authoring checklist

Use this checklist for designing or reviewing a product script. The exact accepted grammar and its full examples are in `docs/reference/PAYSCRIPT_REFERENCE.md`; verify unfamiliar forms there and against `backend/app/core/payscript/parser.py`.

## Contract-to-language decisions

| Contract question | PayScript decision | What to prove |
|---|---|---|
| What fixes `S0`? | Strike date or `CONSTAT STRIKE_FIX` with a reduction such as `AVG` | The initial reference exists before dependent observations; a forward strike window is handled explicitly. |
| What is observed? | `WOF`, `BOF`, `BASKET`, `S[i]`, or a path extremum | Basket aggregation and European versus American monitoring match the term sheet. |
| When is it observed? | Literal `AT` offsets or named `CONSTAT`/`CONSTAT()` schedules | Dates are anchored on the strike, occur in order, and do not exceed maturity. |
| Is a window reduced? | `MIN`, `MAX`, `AVG`, optionally `PERIOD` | Each underlying is reduced first; Economics supplies window length and sampling. |
| Is each subdate a separate observation? | `CONSTAT()()` | The fine grid resets at each parent interval; do not use it merely to calculate an average. |
| Does a terminal raw fixing coexist with an average? | A qualified subdate such as `AT OBS.last.last:` | Both readings share one date source but use the intended raw or reduced value. |
| Is a threshold editable? | `PARAM` or `PARAM()` (required percentage unless an explicit default supplies a unit) | Economics has the effective value; `PARAM()` belongs to one observation schedule. |
| Is a threshold monitored after booking? | `M_` parameter when appropriate | The monitored observable and comparison direction are unambiguous. |
| Does an amount accumulate or depend on history? | Top-level `SET`, event-level `SET`, `ACCRUE`, or an explicit `INDEX` formula | Memory changes only at the defined event; `INDEX` is not confused with a payment count. |
| Does the product terminate early? | Redemption `PAY` plus conditional `STOP` | Called paths have no later flows, including at maturity. |
| What happens without a call? | `AT MATURITY` | Every surviving path has its contractual final payment; nominal is neither missing nor duplicated. |
| When does cash settle? | Economics/payment schedule and flow `t_pay` | Observation and payment dates stay distinct. |

## Payoff patterns to check

- **Athena / autocall:** determine the first callable observation, coupon amount at a call, redemption amount, and whether the last observation shares the maturity date. On an early call, verify `STOP`; on no call, verify the terminal protection or loss branch.
- **Phoenix:** separate conditional coupon from autocall. A missed coupon does not necessarily stop the product. If coupon memory exists, carry the missed entitlement and clear it only on payment. Check the order when coupon and call conditions are both true.
- **Reverse convertible / barrier reverse convertible:** distinguish a terminal European barrier from an American knock-in. Use current terminal level for the final amount even when a past path minimum controls whether protection was lost.
- **Capital protected, call spread, digital, twin win, booster, shark:** define the payoff formula and all cap, floor, participation, and barrier boundary equalities before writing `PAY`. Check the payout at exactly 0%, 100%, each barrier, and maturity. Do not infer the contractual payoff from a product-family name.
- **Averaging, lookback, or window products:** specify which instrument is reduced, over which dates, and whether the contract needs a raw fixing on the same day. Check start and end inclusion, `STRIKE_FIX`, and the availability of `S0` during an open initial window.

## Scenario matrix

For each material threshold, test a level just below, exactly at, and just above it when equality changes the payoff. Add the smallest set of complete paths that covers:

1. first eligible autocall;
2. a later autocall after missed observations;
3. no call and a protected maturity;
4. no call and a loss at maturity;
5. a breached American barrier that has recovered by maturity;
6. unpaid then caught-up memory coupon, and unpaid memory at maturity if relevant;
7. simultaneous coupon and call conditions;
8. a reduced fixing versus the raw fixing on the same date when both are used.

Compare the dates, labels, undiscounted amounts, and stop state with the contract event table. Add scenarios only for features the product actually has.

## Validation routes

- **A new or edited script:** `backend/app/core/payscript/parser.py::parse_script`, calendar resolution, and deterministic payoff cases. Inspect the effective `user_params` and `constat_overrides` when using the Pricer.
- **A language or parser change:** `backend/tests/test_parser.py`, `backend/tests/test_payscript_reference.py`, and focused tests of the changed syntax. Update the reference and any editor guidance that advertises the language.
- **A calendar or window change:** `backend/tests/test_schedule_model.py`, `backend/tests/test_constatations_periode.py`, and focused settlement tests.
- **A catalogue or template change:** `backend/tests/test_payscript_templates.py` and the relevant frontend catalogue or template checks.
- **A booked product change:** consult lifecycle tests for booking snapshot, fixings, events, and residual valuation; do not mutate a real deal or production database merely to test a script.

Run pytest from the repository root and only on relevant files, following `CLAUDE.md`. The full backend suite requires Philippe's explicit request. Documentation-only skill edits do not call for pytest.
