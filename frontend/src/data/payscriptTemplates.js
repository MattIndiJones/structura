// PayScript no-code templates — single source of truth shared by
// PayScriptEditor.vue (Normal/Expert example picker) and the RFQ module
// (product typology sent to counterparty banks).

export const templateMeta = [
  { key: 'autocall_athena',            label: 'Autocall Athena 3Y',                      group: 'Autocall' },
  { key: 'autocall_phoenix',           label: 'Phoenix 3Y (coupon conditionnel)',        group: 'Autocall' },
  { key: 'autocall_worst_of',          label: 'Worst-of Athena 2 actifs',                group: 'Autocall' },
  { key: 'autocall_gear_put',          label: 'Autocall Gear Put 3Y',                    group: 'Autocall' },
  { key: 'autocall_gear_put_worst_of', label: 'Autocall Gear Put worst-of 2 actifs',     group: 'Autocall' },
  { key: 'call_vanilla',               label: 'Call Vanille',                            group: 'Options' },
  { key: 'put_vanilla',                label: 'Put Vanille',                             group: 'Options' },
  { key: 'call_spread',                label: 'Call Spread',                             group: 'Options' },
  { key: 'digital',                    label: 'Digital (binaire)',                       group: 'Options' },
  { key: 'capital_garanti',            label: 'Capital Garanti 5Y',                      group: 'Produits à capital' },
  { key: 'reverse_convertible',        label: 'Reverse Convertible',                     group: 'Produits à capital' },
  { key: 'twin_win',                   label: 'Twin Win',                                group: 'Produits à capital' },
  { key: 'booster',                    label: 'Booster 3Y',                              group: 'Produits à capital' },
  { key: 'shark_note',                 label: 'Shark Note 3Y (capital garanti)',         group: 'Sharks' },
  { key: 'shark_note_worst_of',        label: 'Shark Note worst-of 2 actifs',            group: 'Sharks' },
  { key: 'zcb',                        label: 'ZCB (test actualisation)',                group: 'Validation' },
]

// ── Normal mode (dates AT écrites en dur) ──────────────────────────
export const examples = {
  autocall_athena: `# Autocall Athena 3 ans
PARAM COUPON = 8%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 60%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  autocall_phoenix: `# Phoenix 3 ans — coupon conditionnel
PARAM COUPON = 10%
PARAM M_AC_BAR = 100%
PARAM M_CPN_BAR = 80%
PARAM M_KI_BAR = 60%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  SET CPN  = INDIC(WOF >= M_CPN_BAR)
  PAY CPN * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  autocall_worst_of: `# Worst-of Athena 2 sous-jacents
PARAM COUPON = 12%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 55%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF_MIN < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  autocall_gear_put: `# Autocall 3 ans — gear put avec levier sur strike
PARAM COUPON     = 10%
PARAM M_AC_BAR     = 100%
PARAM M_PUT_STRIKE = 80%
PARAM GEARING    = 150%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET LOSS = MIN(1, GEARING * MAX(0, 1 - WOF/M_PUT_STRIKE))
  PAY 1 "Remboursement nominal"
  PAY -1 * LOSS "Put vendu à effet de levier (plafonné à 100% du capital)"`,

  autocall_gear_put_worst_of: `# Worst-of autocall 2 sous-jacents — gear put avec levier sur strike
PARAM COUPON     = 12%
PARAM M_AC_BAR     = 100%
PARAM M_PUT_STRIKE = 80%
PARAM GEARING    = 150%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET LOSS = MIN(1, GEARING * MAX(0, 1 - WOF/M_PUT_STRIKE))
  PAY 1 "Remboursement nominal"
  PAY -1 * LOSS "Put vendu à effet de levier (plafonné à 100% du capital)"`,

  call_vanilla: `# Call Vanille
PARAM STRIKE = 100%

AT MATURITY:
  PAY MAX(0, WOF - STRIKE)`,

  put_vanilla: `# Put Vanille
PARAM STRIKE = 100%

AT MATURITY:
  PAY MAX(0, STRIKE - WOF)`,

  call_spread: `# Call Spread 100%-120%
PARAM K1 = 100%
PARAM K2 = 120%

AT MATURITY:
  PAY MAX(0, MIN(WOF - K1, K2 - K1))`,

  digital: `# Digital (option binaire)
PARAM STRIKE = 100%
PARAM REBATE = 10%

AT MATURITY:
  SET ITM = INDIC(WOF >= STRIKE)
  PAY ITM * REBATE`,

  capital_garanti: `# Capital Garanti 5 ans
PARAM PART = 80%
PARAM STRIKE = 100%

AT MATURITY:
  PAY 1
  PAY MAX(0, WOF - STRIKE) * PART`,

  reverse_convertible: `# Reverse Convertible 1 an
PARAM COUPON = 10%
PARAM M_KI_BAR = 80%

AT MATURITY:
  PAY COUPON
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  twin_win: `# Twin Win 3 ans
PARAM CAP = 150%
PARAM M_KI_BAR = 70%

AT MATURITY:
  SET BREACHED = INDIC(WOF_MIN < M_KI_BAR)
  SET UPS = MIN(CAP, MAX(1, WOF))
  SET DNS = MIN(CAP, MAX(1, 2 - WOF))
  PAY (1 - BREACHED) * MAX(UPS, DNS)
  PAY BREACHED * WOF`,

  booster: `# Booster 3 ans (levier haussier)
PARAM PART = 200%
PARAM CAP = 140%
PARAM FLOOR = 100%

AT MATURITY:
  SET PERF = WOF
  SET BOOSTED = MIN(CAP, FLOOR + (PERF - 1) * PART)
  SET DOWN = MIN(1, PERF)
  SET IS_UP = INDIC(PERF >= 1)
  PAY IS_UP * BOOSTED
  PAY (1 - IS_UP) * DOWN`,

  zcb: `# ZCB — validation actualisation
# Prix théorique = exp(-r * T)
AT MATURITY:
  PAY 1`,

  shark_note: `# Shark Note 3 ans — capital garanti
PARAM PART   = 100%
PARAM STRIKE = 100%
PARAM M_KO_BAR = 130%
PARAM REBATE = 3%

AT MATURITY:
  SET KO = INDIC(BOF_MAX >= M_KO_BAR)
  SET CALL = PART * MAX(0, WOF - STRIKE)
  PAY 1 "Remboursement nominal"
  PAY CALL "Call acheté (participation à la hausse)"
  PAY -1 * KO * (CALL - REBATE) "Abandon de performance au-delà de la barrière KO"`,

  shark_note_worst_of: `# Shark Note worst-of 2 sous-jacents — capital garanti
PARAM PART   = 80%
PARAM STRIKE = 100%
PARAM M_KO_BAR = 130%
PARAM REBATE = 3%

AT MATURITY:
  SET KO = INDIC(BOF_MAX >= M_KO_BAR)
  SET CALL = PART * MAX(0, WOF - STRIKE)
  PAY 1 "Remboursement nominal"
  PAY CALL "Call acheté (participation à la hausse)"
  PAY -1 * KO * (CALL - REBATE) "Abandon de performance au-delà de la barrière KO"`,
}

// ── Expert mode (calendrier CONSTAT) ───────────────────────────────
export const expertExamples = {
  autocall_athena: `# Autocall Athena 3 ans — mode expert
PARAM COUPON = 8%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 60%

CONSTAT() OBSERVATIONS

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  autocall_phoenix: `# Phoenix 3 ans — mode expert
PARAM COUPON = 10%
PARAM M_AC_BAR = 100%
PARAM M_CPN_BAR = 80%
PARAM M_KI_BAR = 60%

CONSTAT() OBSERVATIONS

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  SET CPN  = INDIC(WOF >= M_CPN_BAR)
  PAY CPN * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  autocall_worst_of: `# Worst-of Athena 2 sous-jacents — mode expert
PARAM COUPON = 12%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 55%

CONSTAT() OBSERVATIONS

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET KI = INDIC(WOF_MIN < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  autocall_gear_put: `# Autocall 3 ans — gear put avec levier sur strike — mode expert
PARAM COUPON     = 10%
PARAM M_AC_BAR     = 100%
PARAM M_PUT_STRIKE = 80%
PARAM GEARING    = 150%

CONSTAT() STRIKE_FIX
CONSTAT() OBSERVATIONS

SET REF = FIX_AVG

AT OBSERVATIONS:
  SET PERF = WOF / REF
  SET CALL = INDIC(PERF >= M_AC_BAR)
  PAY CALL * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET PERF = WOF / REF
  SET LOSS = MIN(1, GEARING * MAX(0, 1 - PERF/M_PUT_STRIKE))
  PAY 1 "Remboursement nominal"
  PAY -1 * LOSS "Put vendu à effet de levier (plafonné à 100% du capital)"`,

  autocall_gear_put_worst_of: `# Worst-of autocall 2 sous-jacents — gear put avec levier sur strike — mode expert
PARAM COUPON     = 12%
PARAM M_AC_BAR     = 100%
PARAM M_PUT_STRIKE = 80%
PARAM GEARING    = 150%

CONSTAT() STRIKE_FIX
CONSTAT() OBSERVATIONS

SET REF = FIX_AVG

AT OBSERVATIONS:
  SET PERF = WOF / REF
  SET CALL = INDIC(PERF >= M_AC_BAR)
  PAY CALL * COUPON
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBSERVATIONS.last:
  SET PERF = WOF / REF
  SET LOSS = MIN(1, GEARING * MAX(0, 1 - PERF/M_PUT_STRIKE))
  PAY 1 "Remboursement nominal"
  PAY -1 * LOSS "Put vendu à effet de levier (plafonné à 100% du capital)"`,

  call_vanilla: `# Call Vanille — mode expert
PARAM STRIKE = 100%

CONSTAT MATURITE

AT MATURITE:
  PAY MAX(0, WOF - STRIKE)`,

  put_vanilla: `# Put Vanille — mode expert
PARAM STRIKE = 100%

CONSTAT MATURITE

AT MATURITE:
  PAY MAX(0, STRIKE - WOF)`,

  call_spread: `# Call Spread 100%-120% — mode expert
PARAM K1 = 100%
PARAM K2 = 120%

CONSTAT MATURITE

AT MATURITE:
  PAY MAX(0, MIN(WOF - K1, K2 - K1))`,

  digital: `# Digital (option binaire) — mode expert
PARAM STRIKE = 100%
PARAM REBATE = 10%

CONSTAT MATURITE

AT MATURITE:
  SET ITM = INDIC(WOF >= STRIKE)
  PAY ITM * REBATE`,

  capital_garanti: `# Capital Garanti 5 ans — mode expert
PARAM PART = 80%
PARAM STRIKE = 100%

CONSTAT MATURITE

AT MATURITE:
  PAY 1
  PAY MAX(0, WOF - STRIKE) * PART`,

  reverse_convertible: `# Reverse Convertible 1 an — mode expert
PARAM COUPON = 10%
PARAM M_KI_BAR = 80%

CONSTAT MATURITE

AT MATURITE:
  PAY COUPON
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF`,

  twin_win: `# Twin Win 3 ans — mode expert
PARAM CAP = 150%
PARAM M_KI_BAR = 70%

CONSTAT MATURITE

AT MATURITE:
  SET BREACHED = INDIC(WOF_MIN < M_KI_BAR)
  SET UPS = MIN(CAP, MAX(1, WOF))
  SET DNS = MIN(CAP, MAX(1, 2 - WOF))
  PAY (1 - BREACHED) * MAX(UPS, DNS)
  PAY BREACHED * WOF`,

  booster: `# Booster 3 ans — mode expert
PARAM PART = 200%
PARAM CAP = 140%
PARAM FLOOR = 100%

CONSTAT MATURITE

AT MATURITE:
  SET PERF = WOF
  SET BOOSTED = MIN(CAP, FLOOR + (PERF - 1) * PART)
  SET DOWN = MIN(1, PERF)
  SET IS_UP = INDIC(PERF >= 1)
  PAY IS_UP * BOOSTED
  PAY (1 - IS_UP) * DOWN`,

  zcb: `# ZCB — validation actualisation — mode expert
CONSTAT MATURITE

AT MATURITE:
  PAY 1`,

  shark_note: `# Shark Note 3 ans — capital garanti — mode expert
PARAM PART   = 100%
PARAM STRIKE = 100%
PARAM M_KO_BAR = 130%
PARAM REBATE = 3%

CONSTAT MATURITE

AT MATURITE:
  SET KO = INDIC(BOF_MAX >= M_KO_BAR)
  SET CALL = PART * MAX(0, WOF - STRIKE)
  PAY 1 "Remboursement nominal"
  PAY CALL "Call acheté (participation à la hausse)"
  PAY -1 * KO * (CALL - REBATE) "Abandon de performance au-delà de la barrière KO"`,

  shark_note_worst_of: `# Shark Note worst-of 2 sous-jacents — capital garanti — mode expert
PARAM PART   = 80%
PARAM STRIKE = 100%
PARAM M_KO_BAR = 130%
PARAM REBATE = 3%

CONSTAT MATURITE

AT MATURITE:
  SET KO = INDIC(BOF_MAX >= M_KO_BAR)
  SET CALL = PART * MAX(0, WOF - STRIKE)
  PAY 1 "Remboursement nominal"
  PAY CALL "Call acheté (participation à la hausse)"
  PAY -1 * KO * (CALL - REBATE) "Abandon de performance au-delà de la barrière KO"`,
}
