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
        "label": 'Autocall Athena (barrière à maturité)',
        "group": 'Autocalls',
        "script": 'UNDERLYING Basket\n\n# Autocall Athena — barrière de protection observée à maturité\nPARAM COUPON\nPARAM M_AC_BAR\nPARAM M_KI_BAR\n\nCONSTAT StartDate\nCONSTAT() ObservationDates\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT Date FROM ObservationDates:\n  SET PERF = WORSTOF(Basket.yield)\n  IF PERF >= M_AC_BAR:\n    PAY COUPON * INDEX "Coupons cumulés"\n    PAY 1 "Capital — remboursement au rappel"\n    STOP\n\nAT ObservationDates.last:\n  SET KI = INDIC(WORSTOF(Basket.yield) < M_KI_BAR)\n  PAY 1 "Capital — remboursement à maturité"\n  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte en capital"',
    },
    'autocall_athena_ki_americaine': {
        "label": 'Autocall Athena à barrière américaine',
        "group": 'Autocalls',
        "script": 'UNDERLYING Basket\n\n# Autocall Athena — barrière de protection américaine\nPARAM COUPON\nPARAM M_AC_BAR\nPARAM M_KI_BAR\n\nCONSTAT StartDate\nCONSTAT() ObservationDates\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT Date FROM ObservationDates:\n  SET PERF = WORSTOF(Basket.yield)\n  IF PERF >= M_AC_BAR:\n    PAY COUPON * INDEX "Coupons cumulés"\n    PAY 1 "Capital — remboursement au rappel"\n    STOP\n\nAT ObservationDates.last:\n  SET KI = INDIC(WOF_MIN < M_KI_BAR)\n  PAY 1 "Capital — remboursement à maturité"\n  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte en capital"',
    },
    'phoenix': {
        "label": 'Phoenix',
        "group": 'Autocalls',
        "script": 'UNDERLYING Basket\n\n# Phoenix — coupon conditionnel, barrière de protection observée à maturité\nPARAM COUPON\nPARAM M_AC_BAR\nPARAM M_CPN_BAR\nPARAM M_KI_BAR\n\nCONSTAT StartDate\nCONSTAT() ObservationDates\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT Date FROM ObservationDates:\n  SET CALL = INDIC(WORSTOF(Basket.yield) >= M_AC_BAR)\n  SET CPN = INDIC(WORSTOF(Basket.yield) >= M_CPN_BAR)\n  PAY CPN * COUPON "Coupon conditionnel"\n  IF CALL = 1:\n    PAY 1 "Capital — remboursement au rappel"\n    STOP\n\nAT ObservationDates.last:\n  SET KI = INDIC(WORSTOF(Basket.yield) < M_KI_BAR)\n  PAY 1 "Capital — remboursement à maturité"\n  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte en capital"',
    },
    'phoenix_memoire': {
        "label": 'Phoenix à coupon mémoire',
        "group": 'Autocalls',
        "script": 'UNDERLYING Basket\n\n# Phoenix à coupon mémoire — les coupons manqués sont rattrapés\nPARAM COUPON\nPARAM M_AC_BAR\nPARAM M_CPN_BAR\nPARAM M_KI_BAR\n\nCONSTAT StartDate\nCONSTAT() ObservationDates\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT Date FROM ObservationDates:\n  IF WORSTOF(Basket.yield) >= M_CPN_BAR:\n    PAY COUPON * (INDEX - MEMO) "Coupon et rattrapage"\n    SET MEMO = INDEX\n  IF WORSTOF(Basket.yield) >= M_AC_BAR:\n    PAY 1 "Remboursement anticipé"\n    STOP\n\nAT ObservationDates.last:\n  SET KI = INDIC(WORSTOF(Basket.yield) < M_KI_BAR)\n  PAY 1 "Capital — remboursement à maturité"\n  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte en capital"',
    },
    'autocall_barriere_degressive': {
        "label": 'Autocall à barrière de rappel dégressive',
        "group": 'Autocalls',
        "script": 'UNDERLYING Basket\n\n# Autocall à barrière de rappel dégressive — une barrière par constatation\nPARAM COUPON\nPARAM() M_AC_BAR\nPARAM M_KI_BAR\n\nCONSTAT StartDate\nCONSTAT() ObservationDates\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT Date FROM ObservationDates:\n  SET PERF = WORSTOF(Basket.yield)\n  IF PERF >= M_AC_BAR:\n    PAY COUPON * INDEX "Coupons cumulés"\n    PAY 1 "Capital — remboursement au rappel"\n    STOP\n\nAT ObservationDates.last:\n  SET KI = INDIC(WORSTOF(Basket.yield) < M_KI_BAR)\n  PAY 1 "Capital — remboursement à maturité"\n  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte en capital"',
    },
    'autocall_gear_put': {
        "label": 'Autocall à put leveragé (gear put)',
        "group": 'Autocalls',
        "script": 'UNDERLYING Basket\n\n# Autocall gear put — perte avec levier sous le strike du put\nPARAM COUPON\nPARAM M_AC_BAR\nPARAM M_PUT_STRIKE\nPARAM GEARING\n\nCONSTAT StartDate\nCONSTAT() ObservationDates\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT Date FROM ObservationDates:\n  SET PERF = WORSTOF(Basket.yield)\n  IF PERF >= M_AC_BAR:\n    PAY COUPON "Coupon"\n    PAY 1 "Capital — remboursement au rappel"\n    STOP\n\nAT ObservationDates.last:\n  SET KI = INDIC(WORSTOF(Basket.yield) < M_PUT_STRIKE)\n  PAY 1 "Remboursement nominal"\n  PAY -1 * KI * MIN(1, GEARING * (1 - WORSTOF(Basket.yield) / M_PUT_STRIKE)) "Put vendu avec levier, perte plafonnée au capital"',
    },
    'autocall_coupon_moyenne_periode': {
        "label": 'Autocall à coupon constaté sur la moyenne de la période',
        "group": 'Autocalls',
        "script": 'UNDERLYING Basket\n\n# Autocall — rappel et coupon constatés sur la moyenne de la période\n# Chaque constatation moyenne ses relevés sur la période écoulée, par\n# sous-jacent, avant que WORSTOF(Basket.yield) n\'agrège. La protection finale lit le cours de\n# clôture : .last.last descend de la constatation à son dernier relevé.\nPARAM COUPON\nPARAM M_AC_BAR\nPARAM M_PDI_BAR\n\nCONSTAT StartDate\nCONSTAT() ObservationDates AVG PERIOD\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT Date FROM ObservationDates:\n  SET CALL = INDIC(WORSTOF(Basket.yield) >= M_AC_BAR)\n  IF CALL = 1:\n    PAY COUPON * INDEX "Coupons cumulés sur moyenne de période"\n    PAY 1 "Capital — remboursement au rappel"\n    STOP\n\nAT ObservationDates.last.last:\n  SET KI = INDIC(WORSTOF(Basket.yield) < M_PDI_BAR)\n  PAY 1 "Capital — remboursement à maturité"\n  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte en capital"',
    },
    'reverse_convertible': {
        "label": 'Reverse convertible à barrière (observée à maturité)',
        "group": 'Produits à capital',
        "script": 'UNDERLYING Basket\n\n# Reverse convertible à barrière — coupon garanti, barrière observée à maturité\nPARAM COUPON\nPARAM M_KI_BAR\n\nCONSTAT StartDate\nCONSTAT MaturityDate\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT MaturityDate:\n  PAY COUPON "Coupon"\n  SET KI = INDIC(WORSTOF(Basket.yield) < M_KI_BAR)\n  PAY 1 "Capital — remboursement à maturité"\n  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte en capital"',
    },
    'brc_ki_americaine': {
        "label": 'Barrier reverse convertible à barrière américaine',
        "group": 'Produits à capital',
        "script": 'UNDERLYING Basket\n\n# Barrier reverse convertible — coupon garanti, barrière américaine\nPARAM COUPON\nPARAM M_KI_BAR\n\nCONSTAT StartDate\nCONSTAT MaturityDate\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT MaturityDate:\n  PAY COUPON "Coupon"\n  SET KI = INDIC(WOF_MIN < M_KI_BAR)\n  PAY 1 "Capital — remboursement à maturité"\n  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte en capital"',
    },
    'capital_garanti': {
        "label": 'Capital garanti avec participation',
        "group": 'Produits à capital',
        "script": 'UNDERLYING Basket\n\n# Capital garanti — participation à la hausse au-dessus du strike\nPARAM PART\nPARAM STRIKE\n\nCONSTAT StartDate\nCONSTAT MaturityDate\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT MaturityDate:\n  PAY 1 "Capital garanti"\n  PAY MAX(0, WORSTOF(Basket.yield) - STRIKE) * PART "Participation à la hausse"',
    },
    'twin_win': {
        "label": 'Twin Win',
        "group": 'Produits à capital',
        "script": 'UNDERLYING Basket\n\n# Twin Win — performance absolue plafonnée tant que la barrière n\'est pas franchie\nPARAM CAP\nPARAM M_KI_BAR\n\nCONSTAT StartDate\nCONSTAT MaturityDate\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT MaturityDate:\n  SET BREACHED = INDIC(WOF_MIN < M_KI_BAR)\n  SET UPS = MIN(CAP, MAX(1, WORSTOF(Basket.yield)))\n  SET DNS = MIN(CAP, MAX(1, 2 - WORSTOF(Basket.yield)))\n  PAY 1 "Capital — remboursement à maturité"\n  PAY (1 - BREACHED) * (MAX(UPS, DNS) - 1) "Performance absolue plafonnée"\n  PAY BREACHED * MAX(WORSTOF(Basket.yield) - 1, 0) "Hausse après franchissement"\n  PAY -BREACHED * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte en capital"',
    },
    'booster': {
        "label": 'Booster',
        "group": 'Produits à capital',
        "script": 'UNDERLYING Basket\n\n# Booster — hausse démultipliée et plafonnée, baisse subie une pour une\nPARAM PART\nPARAM CAP\n\nCONSTAT StartDate\nCONSTAT MaturityDate\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT MaturityDate:\n  SET PERF = WORSTOF(Basket.yield)\n  PAY 1 "Capital — remboursement à maturité"\n  PAY INDIC(PERF >= 1) * (MIN(CAP, 1 + (PERF - 1) * PART) - 1) "Participation plafonnée"\n  PAY -MAX(1 - PERF, 0) "Put vendu — perte en capital"',
    },
    'shark_note': {
        "label": 'Shark note',
        "group": 'Produits à capital',
        "script": 'UNDERLYING Basket\n\n# Shark note — capital garanti, participation perdue au-delà de la barrière\nPARAM PART\nPARAM STRIKE\nPARAM M_KO_BAR\nPARAM REBATE\n\nCONSTAT StartDate\nCONSTAT MaturityDate\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT MaturityDate:\n  SET KO = INDIC(BOF_MAX >= M_KO_BAR)\n  SET CALL = PART * MAX(0, WORSTOF(Basket.yield) - STRIKE)\n  PAY 1 "Remboursement nominal"\n  PAY CALL "Participation à la hausse"\n  PAY -1 * KO * (CALL - REBATE) "Barrière touchée : rebate à la place de la participation"',
    },
    'call': {
        "label": 'Call',
        "group": 'Options',
        "script": 'UNDERLYING Basket\n\n# Call — sur le worst-of\nPARAM STRIKE\n\nCONSTAT StartDate\nCONSTAT MaturityDate\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT MaturityDate:\n  PAY MAX(0, WORSTOF(Basket.yield) - STRIKE) "Call"',
    },
    'put': {
        "label": 'Put',
        "group": 'Options',
        "script": 'UNDERLYING Basket\n\n# Put — sur le worst-of\nPARAM STRIKE\n\nCONSTAT StartDate\nCONSTAT MaturityDate\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT MaturityDate:\n  PAY MAX(0, STRIKE - WORSTOF(Basket.yield)) "Put"',
    },
    'call_spread': {
        "label": 'Call spread',
        "group": 'Options',
        "script": 'UNDERLYING Basket\n\n# Call spread — hausse captée entre deux strikes\nPARAM K1\nPARAM K2\n\nCONSTAT StartDate\nCONSTAT MaturityDate\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT MaturityDate:\n  PAY MAX(0, MIN(WORSTOF(Basket.yield) - K1, K2 - K1)) "Call spread"',
    },
    'digitale': {
        "label": 'Digitale',
        "group": 'Options',
        "script": 'UNDERLYING Basket\n\n# Digitale — coupon fixe si le worst-of termine au-dessus du strike\nPARAM STRIKE\nPARAM COUPON\n\nCONSTAT StartDate\nCONSTAT MaturityDate\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT MaturityDate:\n  PAY INDIC(WORSTOF(Basket.yield) >= STRIKE) * COUPON "Coupon digital"',
    },
    'call_panier_moyenne': {
        "label": 'Call panier à strike et niveau final moyennés',
        "group": 'Options',
        "script": 'UNDERLYING Basket\n\n# Call panier — strike et niveau final moyennés\n# Chaque sous-jacent est moyenné sur sa fenêtre, au départ comme à\n# l\'arrivée, avant que AVG(Basket.yield) n\'agrège.\nPARAM STRIKE\n\nCONSTAT StartDate AVG\nCONSTAT MaturityDate AVG\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT MaturityDate:\n  PAY MAX(0, AVG(Basket.yield) - STRIKE) "Call panier moyenné"',
    },
    'call_lookback': {
        "label": 'Call à strike lookback',
        "group": 'Options',
        "script": 'UNDERLYING Basket\n\n# Call à strike lookback — strike au plus bas de la fenêtre de départ\nPARAM STRIKE\n\nCONSTAT StartDate MIN\nCONSTAT MaturityDate\n\nAT StartDate:\n  Basket.spot0 = Basket.spot@StartDate\n\nAT MaturityDate:\n  PAY MAX(0, WORSTOF(Basket.yield) - STRIKE) "Call sur la performance depuis le plus bas de départ"',
    },
}


def by_group() -> dict[str, list[str]]:
    """Clés de template par famille de produit."""
    g: dict[str, list[str]] = {}
    for key, tpl in TEMPLATES.items():
        g.setdefault(tpl["group"], []).append(key)
    return g
