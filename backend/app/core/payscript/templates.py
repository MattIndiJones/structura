"""Bibliothèque de scripts PayScript de référence — corpus d'exemples.

GÉNÉRÉ : ne pas éditer à la main. Source :
`frontend/src/data/payscriptTemplates.js` (sélecteur d'exemples de l'éditeur et
typologie produit du module RFQ).

Régénérer avec `backend/scripts/sync_payscript_templates.py`.
`backend/tests/test_payscript_templates.py` vérifie que les deux restent
identiques et que chaque script compile.

Ce sont les exemples few-shot envoyés au modèle par l'assistant IA : des
scripts qui pricent réellement ici, pas de la syntaxe plausible.
"""

TEMPLATES: dict[str, dict] = {
    'autocall_athena': {
        "label": 'Autocall Athena 3Y',
        "group": 'Autocall',
        "script": '# Autocall Athena 3 ans\nPARAM COUPON = 8%\nPARAM M_AC_BAR = 100%\nPARAM M_KI_BAR = 60%\n\nAT 1, 2, 3:\n  SET CALL = INDIC(WOF >= M_AC_BAR)\n  PAY CALL * COUPON * INDEX\n  PAY CALL * 1\n  IF CALL = 1:\n    STOP\n\nAT MATURITY:\n  SET KI = INDIC(WOF < M_KI_BAR)\n  PAY (1 - KI) * 1\n  PAY KI * WOF',
    },
    'autocall_phoenix': {
        "label": 'Phoenix 3Y (coupon conditionnel)',
        "group": 'Autocall',
        "script": '# Phoenix 3 ans — coupon conditionnel\nPARAM COUPON = 10%\nPARAM M_AC_BAR = 100%\nPARAM M_CPN_BAR = 80%\nPARAM M_KI_BAR = 60%\n\nAT 1, 2, 3:\n  SET CALL = INDIC(WOF >= M_AC_BAR)\n  SET CPN  = INDIC(WOF >= M_CPN_BAR)\n  PAY CPN * COUPON\n  PAY CALL * 1\n  IF CALL = 1:\n    STOP\n\nAT MATURITY:\n  SET KI = INDIC(WOF < M_KI_BAR)\n  PAY (1 - KI) * 1\n  PAY KI * WOF',
    },
    'autocall_worst_of': {
        "label": 'Worst-of Athena 2 actifs',
        "group": 'Autocall',
        "script": '# Worst-of Athena 2 sous-jacents\nPARAM COUPON = 12%\nPARAM M_AC_BAR = 100%\nPARAM M_KI_BAR = 55%\n\nAT 1, 2, 3:\n  SET CALL = INDIC(WOF >= M_AC_BAR)\n  PAY CALL * COUPON * INDEX\n  PAY CALL * 1\n  IF CALL = 1:\n    STOP\n\nAT MATURITY:\n  SET KI = INDIC(WOF_MIN < M_KI_BAR)\n  PAY (1 - KI) * 1\n  PAY KI * WOF',
    },
    'autocall_gear_put': {
        "label": 'Autocall Gear Put 3Y',
        "group": 'Autocall',
        "script": '# Autocall 3 ans — gear put avec levier sur strike\nPARAM COUPON     = 10%\nPARAM M_AC_BAR     = 100%\nPARAM M_PUT_STRIKE = 80%\nPARAM GEARING    = 150%\n\nAT 1, 2, 3:\n  SET CALL = INDIC(WOF >= M_AC_BAR)\n  PAY CALL * COUPON\n  PAY CALL * 1\n  IF CALL = 1:\n    STOP\n\nAT MATURITY:\n  SET LOSS = MIN(1, GEARING * MAX(0, 1 - WOF/M_PUT_STRIKE))\n  PAY 1 "Remboursement nominal"\n  PAY -1 * LOSS "Put vendu à effet de levier (plafonné à 100% du capital)"',
    },
    'autocall_gear_put_worst_of': {
        "label": 'Autocall Gear Put worst-of 2 actifs',
        "group": 'Autocall',
        "script": '# Worst-of autocall 2 sous-jacents — gear put avec levier sur strike\nPARAM COUPON     = 12%\nPARAM M_AC_BAR     = 100%\nPARAM M_PUT_STRIKE = 80%\nPARAM GEARING    = 150%\n\nAT 1, 2, 3:\n  SET CALL = INDIC(WOF >= M_AC_BAR)\n  PAY CALL * COUPON\n  PAY CALL * 1\n  IF CALL = 1:\n    STOP\n\nAT MATURITY:\n  SET LOSS = MIN(1, GEARING * MAX(0, 1 - WOF/M_PUT_STRIKE))\n  PAY 1 "Remboursement nominal"\n  PAY -1 * LOSS "Put vendu à effet de levier (plafonné à 100% du capital)"',
    },
    'call_vanilla': {
        "label": 'Call Vanille',
        "group": 'Options',
        "script": '# Call Vanille\nPARAM STRIKE = 100%\n\nAT MATURITY:\n  PAY MAX(0, WOF - STRIKE)',
    },
    'put_vanilla': {
        "label": 'Put Vanille',
        "group": 'Options',
        "script": '# Put Vanille\nPARAM STRIKE = 100%\n\nAT MATURITY:\n  PAY MAX(0, STRIKE - WOF)',
    },
    'call_spread': {
        "label": 'Call Spread',
        "group": 'Options',
        "script": '# Call Spread 100%-120%\nPARAM K1 = 100%\nPARAM K2 = 120%\n\nAT MATURITY:\n  PAY MAX(0, MIN(WOF - K1, K2 - K1))',
    },
    'digital': {
        "label": 'Digital (binaire)',
        "group": 'Options',
        "script": '# Digital (option binaire)\nPARAM STRIKE = 100%\nPARAM REBATE = 10%\n\nAT MATURITY:\n  SET ITM = INDIC(WOF >= STRIKE)\n  PAY ITM * REBATE',
    },
    'capital_garanti': {
        "label": 'Capital Garanti 5Y',
        "group": 'Produits à capital',
        "script": '# Capital Garanti 5 ans\nPARAM PART = 80%\nPARAM STRIKE = 100%\n\nAT MATURITY:\n  PAY 1\n  PAY MAX(0, WOF - STRIKE) * PART',
    },
    'reverse_convertible': {
        "label": 'Reverse Convertible',
        "group": 'Produits à capital',
        "script": '# Reverse Convertible 1 an\nPARAM COUPON = 10%\nPARAM M_KI_BAR = 80%\n\nAT MATURITY:\n  PAY COUPON\n  SET KI = INDIC(WOF < M_KI_BAR)\n  PAY (1 - KI) * 1\n  PAY KI * WOF',
    },
    'twin_win': {
        "label": 'Twin Win',
        "group": 'Produits à capital',
        "script": '# Twin Win 3 ans\nPARAM CAP = 150%\nPARAM M_KI_BAR = 70%\n\nAT MATURITY:\n  SET BREACHED = INDIC(WOF_MIN < M_KI_BAR)\n  SET UPS = MIN(CAP, MAX(1, WOF))\n  SET DNS = MIN(CAP, MAX(1, 2 - WOF))\n  PAY (1 - BREACHED) * MAX(UPS, DNS)\n  PAY BREACHED * WOF',
    },
    'booster': {
        "label": 'Booster 3Y',
        "group": 'Produits à capital',
        "script": '# Booster 3 ans (levier haussier)\nPARAM PART = 200%\nPARAM CAP = 140%\nPARAM PLANCHER = 100%\n\nAT MATURITY:\n  SET PERF = WOF\n  SET BOOSTED = MIN(CAP, PLANCHER + (PERF - 1) * PART)\n  SET DOWN = MIN(1, PERF)\n  SET IS_UP = INDIC(PERF >= 1)\n  PAY IS_UP * BOOSTED\n  PAY (1 - IS_UP) * DOWN',
    },
    'zcb': {
        "label": 'ZCB (test actualisation)',
        "group": 'Validation',
        "script": '# ZCB — validation actualisation\n# Prix théorique = exp(-r * T)\nAT MATURITY:\n  PAY 1',
    },
    'shark_note': {
        "label": 'Shark Note 3Y (capital garanti)',
        "group": 'Sharks',
        "script": '# Shark Note 3 ans — capital garanti\nPARAM PART   = 100%\nPARAM STRIKE = 100%\nPARAM M_KO_BAR = 130%\nPARAM REBATE = 3%\n\nAT MATURITY:\n  SET KO = INDIC(BOF_MAX >= M_KO_BAR)\n  SET CALL = PART * MAX(0, WOF - STRIKE)\n  PAY 1 "Remboursement nominal"\n  PAY CALL "Call acheté (participation à la hausse)"\n  PAY -1 * KO * (CALL - REBATE) "Abandon de performance au-delà de la barrière KO"',
    },
    'shark_note_worst_of': {
        "label": 'Shark Note worst-of 2 actifs',
        "group": 'Sharks',
        "script": '# Shark Note worst-of 2 sous-jacents — capital garanti\nPARAM PART   = 80%\nPARAM STRIKE = 100%\nPARAM M_KO_BAR = 130%\nPARAM REBATE = 3%\n\nAT MATURITY:\n  SET KO = INDIC(BOF_MAX >= M_KO_BAR)\n  SET CALL = PART * MAX(0, WOF - STRIKE)\n  PAY 1 "Remboursement nominal"\n  PAY CALL "Call acheté (participation à la hausse)"\n  PAY -1 * KO * (CALL - REBATE) "Abandon de performance au-delà de la barrière KO"',
    },
}


def by_group() -> dict[str, list[str]]:
    """Clés de template par famille de produit."""
    g: dict[str, list[str]] = {}
    for key, tpl in TEMPLATES.items():
        g.setdefault(tpl["group"], []).append(key)
    return g
