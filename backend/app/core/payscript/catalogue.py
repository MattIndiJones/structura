"""Catalogue des produits génériques — module « Modèles de produits ».

GÉNÉRÉ : ne pas éditer à la main. Source :
`frontend/src/data/productCatalogue.json` (liste du module « Modèles de
produits » du Pricer).

Régénérer avec `backend/scripts/sync_product_catalogue.py`.
`backend/tests/test_product_catalogue.py` vérifie que les deux restent
identiques, que chaque fiche compile et qu'elle price sur un calendrier généré.

Une fiche porte un script générique — PARAM avec unité et valeur initiale,
CONSTAT sans date — et le rôle de chaque CONSTAT : `observations` (échéancier
du strike à la maturité), `maturity` (date unique à maturité), `strike_window`
(fenêtre de départ STRIKE_FIX). Les dates viennent du Pricer, jamais du script.
"""

CATALOGUE_VERSION = '2.0'

TENORS: dict[str, dict] = {'6M': {'months': 6, 'label': '6 mois'},
 '1Y': {'months': 12, 'label': '1 an'},
 '18M': {'months': 18, 'label': '18 mois'},
 '2Y': {'months': 24, 'label': '2 ans'},
 '3Y': {'months': 36, 'label': '3 ans'},
 '4Y': {'months': 48, 'label': '4 ans'},
 '5Y': {'months': 60, 'label': '5 ans'},
 '7Y': {'months': 84, 'label': '7 ans'},
 '10Y': {'months': 120, 'label': '10 ans'}}

FAMILIES: dict[str, str] = {'autocalls': 'Autocalls', 'capital': 'Produits à capital', 'options': 'Options'}

PRODUCTS: dict[str, dict] = {'autocall_athena': {'label': 'Autocall Athena (barrière à maturité)',
                     'family': 'autocalls',
                     'description': 'Rappel au pair avec coupons cumulés dès que le worst-of '
                                    'atteint la barrière de rappel. À défaut, la protection du '
                                    'capital se juge à la dernière constatation.',
                     'underlyings': {'min': 1, 'max': 5},
                     'tenors': ['1Y', '2Y', '3Y', '4Y', '5Y', '7Y', '10Y'],
                     'constats': {'OBSERVATIONDATES': {'role': 'observations', 'frequency': '1Y'},
                                  'STARTDATE': {'role': 'initial_fixing'}},
                     'version': '2.0',
                     'script': 'UNDERLYING Basket\n'
                               '\n'
                               '# Autocall Athena — barrière de protection observée à maturité\n'
                               'PARAM COUPON\n'
                               'PARAM M_AC_BAR\n'
                               'PARAM M_KI_BAR\n'
                               '\n'
                               'CONSTAT StartDate\n'
                               'CONSTAT() ObservationDates\n'
                               '\n'
                               'AT StartDate:\n'
                               '  Basket.spot0 = Basket.spot@StartDate\n'
                               '\n'
                               'AT Date FROM ObservationDates:\n'
                               '  SET PERF = WORSTOF(Basket.yield)\n'
                               '  IF PERF >= M_AC_BAR:\n'
                               '    PAY COUPON * INDEX "Coupons cumulés"\n'
                               '    PAY 1 "Capital — remboursement au rappel"\n'
                               '    STOP\n'
                               '\n'
                               'AT ObservationDates.last:\n'
                               '  SET KI = INDIC(WORSTOF(Basket.yield) < M_KI_BAR)\n'
                               '  PAY 1 "Capital — remboursement à maturité"\n'
                               '  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte '
                               'en capital"'},
 'autocall_athena_ki_americaine': {'label': 'Autocall Athena à barrière américaine',
                                   'family': 'autocalls',
                                   'description': 'Rappel au pair avec coupons cumulés dès que le '
                                                  'worst-of atteint la barrière de rappel. La '
                                                  'protection du capital est perdue si le worst-of '
                                                  'franchit la barrière à un moment quelconque de '
                                                  'la vie du produit.',
                                   'underlyings': {'min': 1, 'max': 5},
                                   'tenors': ['1Y', '2Y', '3Y', '4Y', '5Y', '7Y', '10Y'],
                                   'constats': {'OBSERVATIONDATES': {'role': 'observations',
                                                                     'frequency': '1Y'},
                                                'STARTDATE': {'role': 'initial_fixing'}},
                                   'version': '2.0',
                                   'script': 'UNDERLYING Basket\n'
                                             '\n'
                                             '# Autocall Athena — barrière de protection '
                                             'américaine\n'
                                             'PARAM COUPON\n'
                                             'PARAM M_AC_BAR\n'
                                             'PARAM M_KI_BAR\n'
                                             '\n'
                                             'CONSTAT StartDate\n'
                                             'CONSTAT() ObservationDates\n'
                                             '\n'
                                             'AT StartDate:\n'
                                             '  Basket.spot0 = Basket.spot@StartDate\n'
                                             '\n'
                                             'AT Date FROM ObservationDates:\n'
                                             '  SET PERF = WORSTOF(Basket.yield)\n'
                                             '  IF PERF >= M_AC_BAR:\n'
                                             '    PAY COUPON * INDEX "Coupons cumulés"\n'
                                             '    PAY 1 "Capital — remboursement au rappel"\n'
                                             '    STOP\n'
                                             '\n'
                                             'AT ObservationDates.last:\n'
                                             '  SET KI = INDIC(WOF_MIN < M_KI_BAR)\n'
                                             '  PAY 1 "Capital — remboursement à maturité"\n'
                                             '  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put '
                                             'vendu — perte en capital"'},
 'phoenix': {'label': 'Phoenix',
             'family': 'autocalls',
             'description': 'Coupon versé à chaque constatation où le worst-of dépasse la barrière '
                            'de coupon, rappel au pair au-dessus de la barrière de rappel. '
                            'Protection du capital jugée à la dernière constatation.',
             'underlyings': {'min': 1, 'max': 5},
             'tenors': ['1Y', '2Y', '3Y', '4Y', '5Y', '7Y', '10Y'],
             'constats': {'OBSERVATIONDATES': {'role': 'observations', 'frequency': '1Y'},
                          'STARTDATE': {'role': 'initial_fixing'}},
             'version': '2.0',
             'script': 'UNDERLYING Basket\n'
                       '\n'
                       '# Phoenix — coupon conditionnel, barrière de protection observée à '
                       'maturité\n'
                       'PARAM COUPON\n'
                       'PARAM M_AC_BAR\n'
                       'PARAM M_CPN_BAR\n'
                       'PARAM M_KI_BAR\n'
                       '\n'
                       'CONSTAT StartDate\n'
                       'CONSTAT() ObservationDates\n'
                       '\n'
                       'AT StartDate:\n'
                       '  Basket.spot0 = Basket.spot@StartDate\n'
                       '\n'
                       'AT Date FROM ObservationDates:\n'
                       '  SET CALL = INDIC(WORSTOF(Basket.yield) >= M_AC_BAR)\n'
                       '  SET CPN = INDIC(WORSTOF(Basket.yield) >= M_CPN_BAR)\n'
                       '  PAY CPN * COUPON "Coupon conditionnel"\n'
                       '  IF CALL = 1:\n'
                       '    PAY 1 "Capital — remboursement au rappel"\n'
                       '    STOP\n'
                       '\n'
                       'AT ObservationDates.last:\n'
                       '  SET KI = INDIC(WORSTOF(Basket.yield) < M_KI_BAR)\n'
                       '  PAY 1 "Capital — remboursement à maturité"\n'
                       '  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte en '
                       'capital"'},
 'phoenix_memoire': {'label': 'Phoenix à coupon mémoire',
                     'family': 'autocalls',
                     'description': 'Phoenix dont les coupons manqués sont rattrapés à la première '
                                    'constatation où le worst-of repasse la barrière de coupon. '
                                    'Protection du capital jugée à la dernière constatation.',
                     'underlyings': {'min': 1, 'max': 5},
                     'tenors': ['1Y', '2Y', '3Y', '4Y', '5Y', '7Y', '10Y'],
                     'constats': {'OBSERVATIONDATES': {'role': 'observations', 'frequency': '1Y'},
                                  'STARTDATE': {'role': 'initial_fixing'}},
                     'version': '2.0',
                     'script': 'UNDERLYING Basket\n'
                               '\n'
                               '# Phoenix à coupon mémoire — les coupons manqués sont rattrapés\n'
                               'PARAM COUPON\n'
                               'PARAM M_AC_BAR\n'
                               'PARAM M_CPN_BAR\n'
                               'PARAM M_KI_BAR\n'
                               '\n'
                               'CONSTAT StartDate\n'
                               'CONSTAT() ObservationDates\n'
                               '\n'
                               'AT StartDate:\n'
                               '  Basket.spot0 = Basket.spot@StartDate\n'
                               '\n'
                               'AT Date FROM ObservationDates:\n'
                               '  IF WORSTOF(Basket.yield) >= M_CPN_BAR:\n'
                               '    PAY COUPON * (INDEX - MEMO) "Coupon et rattrapage"\n'
                               '    SET MEMO = INDEX\n'
                               '  IF WORSTOF(Basket.yield) >= M_AC_BAR:\n'
                               '    PAY 1 "Remboursement anticipé"\n'
                               '    STOP\n'
                               '\n'
                               'AT ObservationDates.last:\n'
                               '  SET KI = INDIC(WORSTOF(Basket.yield) < M_KI_BAR)\n'
                               '  PAY 1 "Capital — remboursement à maturité"\n'
                               '  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte '
                               'en capital"'},
 'autocall_barriere_degressive': {'label': 'Autocall à barrière de rappel dégressive',
                                  'family': 'autocalls',
                                  'description': 'Athena dont la barrière de rappel change à '
                                                 'chaque constatation : une ligne par constatation '
                                                 "dans Economics, la dernière s'étend aux "
                                                 'suivantes.',
                                  'underlyings': {'min': 1, 'max': 5},
                                  'tenors': ['1Y', '2Y', '3Y', '4Y', '5Y', '7Y', '10Y'],
                                  'constats': {'OBSERVATIONDATES': {'role': 'observations',
                                                                    'frequency': '1Y'},
                                               'STARTDATE': {'role': 'initial_fixing'}},
                                  'version': '2.0',
                                  'script': 'UNDERLYING Basket\n'
                                            '\n'
                                            '# Autocall à barrière de rappel dégressive — une '
                                            'barrière par constatation\n'
                                            'PARAM COUPON\n'
                                            'PARAM() M_AC_BAR\n'
                                            'PARAM M_KI_BAR\n'
                                            '\n'
                                            'CONSTAT StartDate\n'
                                            'CONSTAT() ObservationDates\n'
                                            '\n'
                                            'AT StartDate:\n'
                                            '  Basket.spot0 = Basket.spot@StartDate\n'
                                            '\n'
                                            'AT Date FROM ObservationDates:\n'
                                            '  SET PERF = WORSTOF(Basket.yield)\n'
                                            '  IF PERF >= M_AC_BAR:\n'
                                            '    PAY COUPON * INDEX "Coupons cumulés"\n'
                                            '    PAY 1 "Capital — remboursement au rappel"\n'
                                            '    STOP\n'
                                            '\n'
                                            'AT ObservationDates.last:\n'
                                            '  SET KI = INDIC(WORSTOF(Basket.yield) < M_KI_BAR)\n'
                                            '  PAY 1 "Capital — remboursement à maturité"\n'
                                            '  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put '
                                            'vendu — perte en capital"'},
 'autocall_gear_put': {'label': 'Autocall à put leveragé (gear put)',
                       'family': 'autocalls',
                       'description': 'Rappel au pair avec coupon au-dessus de la barrière de '
                                      'rappel. Sans rappel, perte démultipliée sous le strike du '
                                      'put, plafonnée au capital.',
                       'underlyings': {'min': 1, 'max': 5},
                       'tenors': ['1Y', '2Y', '3Y', '4Y', '5Y', '7Y', '10Y'],
                       'constats': {'OBSERVATIONDATES': {'role': 'observations', 'frequency': '1Y'},
                                    'STARTDATE': {'role': 'initial_fixing'}},
                       'version': '2.0',
                       'script': 'UNDERLYING Basket\n'
                                 '\n'
                                 '# Autocall gear put — perte avec levier sous le strike du put\n'
                                 'PARAM COUPON\n'
                                 'PARAM M_AC_BAR\n'
                                 'PARAM M_PUT_STRIKE\n'
                                 'PARAM GEARING\n'
                                 '\n'
                                 'CONSTAT StartDate\n'
                                 'CONSTAT() ObservationDates\n'
                                 '\n'
                                 'AT StartDate:\n'
                                 '  Basket.spot0 = Basket.spot@StartDate\n'
                                 '\n'
                                 'AT Date FROM ObservationDates:\n'
                                 '  SET PERF = WORSTOF(Basket.yield)\n'
                                 '  IF PERF >= M_AC_BAR:\n'
                                 '    PAY COUPON "Coupon"\n'
                                 '    PAY 1 "Capital — remboursement au rappel"\n'
                                 '    STOP\n'
                                 '\n'
                                 'AT ObservationDates.last:\n'
                                 '  SET KI = INDIC(WORSTOF(Basket.yield) < M_PUT_STRIKE)\n'
                                 '  PAY 1 "Remboursement nominal"\n'
                                 '  PAY -1 * KI * MIN(1, GEARING * (1 - WORSTOF(Basket.yield) / '
                                 'M_PUT_STRIKE)) "Put vendu avec levier, perte plafonnée au '
                                 'capital"'},
 'autocall_coupon_moyenne_periode': {'label': 'Autocall à coupon constaté sur la moyenne de la '
                                              'période',
                                     'family': 'autocalls',
                                     'description': 'Chaque constatation moyenne les relevés de la '
                                                    'période écoulée, par sous-jacent, avant '
                                                    "l'agrégation worst-of. La protection finale "
                                                    'lit le cours de clôture.',
                                     'underlyings': {'min': 1, 'max': 5},
                                     'tenors': ['1Y', '2Y', '3Y', '4Y', '5Y'],
                                     'constats': {'OBSERVATIONDATES': {'role': 'observations',
                                                                       'frequency': '1Y',
                                                                       'window_frequency': '3M'},
                                                  'STARTDATE': {'role': 'initial_fixing'}},
                                     'version': '2.0',
                                     'script': 'UNDERLYING Basket\n'
                                               '\n'
                                               '# Autocall — rappel et coupon constatés sur la '
                                               'moyenne de la période\n'
                                               '# Chaque constatation moyenne ses relevés sur la '
                                               'période écoulée, par\n'
                                               '# sous-jacent, avant que WORSTOF(Basket.yield) '
                                               "n'agrège. La protection finale lit le cours de\n"
                                               '# clôture : .last.last descend de la constatation '
                                               'à son dernier relevé.\n'
                                               'PARAM COUPON\n'
                                               'PARAM M_AC_BAR\n'
                                               'PARAM M_PDI_BAR\n'
                                               '\n'
                                               'CONSTAT StartDate\n'
                                               'CONSTAT() ObservationDates AVG PERIOD\n'
                                               '\n'
                                               'AT StartDate:\n'
                                               '  Basket.spot0 = Basket.spot@StartDate\n'
                                               '\n'
                                               'AT Date FROM ObservationDates:\n'
                                               '  SET CALL = INDIC(WORSTOF(Basket.yield) >= '
                                               'M_AC_BAR)\n'
                                               '  IF CALL = 1:\n'
                                               '    PAY COUPON * INDEX "Coupons cumulés sur '
                                               'moyenne de période"\n'
                                               '    PAY 1 "Capital — remboursement au rappel"\n'
                                               '    STOP\n'
                                               '\n'
                                               'AT ObservationDates.last.last:\n'
                                               '  SET KI = INDIC(WORSTOF(Basket.yield) < '
                                               'M_PDI_BAR)\n'
                                               '  PAY 1 "Capital — remboursement à maturité"\n'
                                               '  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put '
                                               'vendu — perte en capital"'},
 'reverse_convertible': {'label': 'Reverse convertible à barrière (observée à maturité)',
                         'family': 'capital',
                         'description': 'Coupon garanti. Le capital est remboursé au pair si le '
                                        'worst-of est au-dessus de la barrière à la date de '
                                        'maturité, sinon il suit sa performance.',
                         'underlyings': {'min': 1, 'max': 5},
                         'tenors': ['6M', '1Y', '18M', '2Y', '3Y'],
                         'constats': {'MATURITYDATE': {'role': 'maturity'},
                                      'STARTDATE': {'role': 'initial_fixing'}},
                         'version': '2.0',
                         'script': 'UNDERLYING Basket\n'
                                   '\n'
                                   '# Reverse convertible à barrière — coupon garanti, barrière '
                                   'observée à maturité\n'
                                   'PARAM COUPON\n'
                                   'PARAM M_KI_BAR\n'
                                   '\n'
                                   'CONSTAT StartDate\n'
                                   'CONSTAT MaturityDate\n'
                                   '\n'
                                   'AT StartDate:\n'
                                   '  Basket.spot0 = Basket.spot@StartDate\n'
                                   '\n'
                                   'AT MaturityDate:\n'
                                   '  PAY COUPON "Coupon"\n'
                                   '  SET KI = INDIC(WORSTOF(Basket.yield) < M_KI_BAR)\n'
                                   '  PAY 1 "Capital — remboursement à maturité"\n'
                                   '  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — '
                                   'perte en capital"'},
 'brc_ki_americaine': {'label': 'Barrier reverse convertible à barrière américaine',
                       'family': 'capital',
                       'description': 'Coupon garanti. Le capital suit la performance du worst-of '
                                      'si celui-ci a franchi la barrière à un moment quelconque de '
                                      'la vie du produit, sinon il est remboursé au pair.',
                       'underlyings': {'min': 1, 'max': 5},
                       'tenors': ['6M', '1Y', '18M', '2Y', '3Y'],
                       'constats': {'MATURITYDATE': {'role': 'maturity'},
                                    'STARTDATE': {'role': 'initial_fixing'}},
                       'version': '2.0',
                       'script': 'UNDERLYING Basket\n'
                                 '\n'
                                 '# Barrier reverse convertible — coupon garanti, barrière '
                                 'américaine\n'
                                 'PARAM COUPON\n'
                                 'PARAM M_KI_BAR\n'
                                 '\n'
                                 'CONSTAT StartDate\n'
                                 'CONSTAT MaturityDate\n'
                                 '\n'
                                 'AT StartDate:\n'
                                 '  Basket.spot0 = Basket.spot@StartDate\n'
                                 '\n'
                                 'AT MaturityDate:\n'
                                 '  PAY COUPON "Coupon"\n'
                                 '  SET KI = INDIC(WOF_MIN < M_KI_BAR)\n'
                                 '  PAY 1 "Capital — remboursement à maturité"\n'
                                 '  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte '
                                 'en capital"'},
 'capital_garanti': {'label': 'Capital garanti avec participation',
                     'family': 'capital',
                     'description': 'Capital remboursé au pair à maturité, plus une participation '
                                    'à la hausse du worst-of au-dessus du strike.',
                     'underlyings': {'min': 1, 'max': 5},
                     'tenors': ['1Y', '18M', '2Y', '3Y', '4Y', '5Y', '7Y', '10Y'],
                     'constats': {'MATURITYDATE': {'role': 'maturity'},
                                  'STARTDATE': {'role': 'initial_fixing'}},
                     'version': '2.0',
                     'script': 'UNDERLYING Basket\n'
                               '\n'
                               '# Capital garanti — participation à la hausse au-dessus du strike\n'
                               'PARAM PART\n'
                               'PARAM STRIKE\n'
                               '\n'
                               'CONSTAT StartDate\n'
                               'CONSTAT MaturityDate\n'
                               '\n'
                               'AT StartDate:\n'
                               '  Basket.spot0 = Basket.spot@StartDate\n'
                               '\n'
                               'AT MaturityDate:\n'
                               '  PAY 1 "Capital garanti"\n'
                               '  PAY MAX(0, WORSTOF(Basket.yield) - STRIKE) * PART "Participation '
                               'à la hausse"'},
 'twin_win': {'label': 'Twin Win',
              'family': 'capital',
              'description': 'Gain sur la valeur absolue de la performance, plafonné, tant que la '
                             "barrière américaine n'est pas franchie. Barrière franchie : le "
                             'capital suit le worst-of.',
              'underlyings': {'min': 1, 'max': 5},
              'tenors': ['1Y', '18M', '2Y', '3Y', '4Y', '5Y'],
              'constats': {'MATURITYDATE': {'role': 'maturity'},
                           'STARTDATE': {'role': 'initial_fixing'}},
              'version': '2.0',
              'script': 'UNDERLYING Basket\n'
                        '\n'
                        "# Twin Win — performance absolue plafonnée tant que la barrière n'est pas "
                        'franchie\n'
                        'PARAM CAP\n'
                        'PARAM M_KI_BAR\n'
                        '\n'
                        'CONSTAT StartDate\n'
                        'CONSTAT MaturityDate\n'
                        '\n'
                        'AT StartDate:\n'
                        '  Basket.spot0 = Basket.spot@StartDate\n'
                        '\n'
                        'AT MaturityDate:\n'
                        '  SET BREACHED = INDIC(WOF_MIN < M_KI_BAR)\n'
                        '  SET UPS = MIN(CAP, MAX(1, WORSTOF(Basket.yield)))\n'
                        '  SET DNS = MIN(CAP, MAX(1, 2 - WORSTOF(Basket.yield)))\n'
                        '  PAY 1 "Capital — remboursement à maturité"\n'
                        '  PAY (1 - BREACHED) * (MAX(UPS, DNS) - 1) "Performance absolue '
                        'plafonnée"\n'
                        '  PAY BREACHED * MAX(WORSTOF(Basket.yield) - 1, 0) "Hausse après '
                        'franchissement"\n'
                        '  PAY -BREACHED * MAX(1 - WORSTOF(Basket.yield), 0) "Put vendu — perte en '
                        'capital"'},
 'booster': {'label': 'Booster',
             'family': 'capital',
             'description': 'Hausse du worst-of démultipliée et plafonnée ; baisse subie une pour '
                            'une, sans protection.',
             'underlyings': {'min': 1, 'max': 5},
             'tenors': ['1Y', '18M', '2Y', '3Y', '4Y', '5Y'],
             'constats': {'MATURITYDATE': {'role': 'maturity'},
                          'STARTDATE': {'role': 'initial_fixing'}},
             'version': '2.0',
             'script': 'UNDERLYING Basket\n'
                       '\n'
                       '# Booster — hausse démultipliée et plafonnée, baisse subie une pour une\n'
                       'PARAM PART\n'
                       'PARAM CAP\n'
                       '\n'
                       'CONSTAT StartDate\n'
                       'CONSTAT MaturityDate\n'
                       '\n'
                       'AT StartDate:\n'
                       '  Basket.spot0 = Basket.spot@StartDate\n'
                       '\n'
                       'AT MaturityDate:\n'
                       '  SET PERF = WORSTOF(Basket.yield)\n'
                       '  PAY 1 "Capital — remboursement à maturité"\n'
                       '  PAY INDIC(PERF >= 1) * (MIN(CAP, 1 + (PERF - 1) * PART) - 1) '
                       '"Participation plafonnée"\n'
                       '  PAY -MAX(1 - PERF, 0) "Put vendu — perte en capital"'},
 'shark_note': {'label': 'Shark note',
                'family': 'capital',
                'description': 'Capital garanti et participation à la hausse, remplacée par un '
                               'rebate si le best-of a touché la barrière désactivante pendant la '
                               'vie du produit.',
                'underlyings': {'min': 1, 'max': 5},
                'tenors': ['1Y', '18M', '2Y', '3Y', '4Y', '5Y'],
                'constats': {'MATURITYDATE': {'role': 'maturity'},
                             'STARTDATE': {'role': 'initial_fixing'}},
                'version': '2.0',
                'script': 'UNDERLYING Basket\n'
                          '\n'
                          '# Shark note — capital garanti, participation perdue au-delà de la '
                          'barrière\n'
                          'PARAM PART\n'
                          'PARAM STRIKE\n'
                          'PARAM M_KO_BAR\n'
                          'PARAM REBATE\n'
                          '\n'
                          'CONSTAT StartDate\n'
                          'CONSTAT MaturityDate\n'
                          '\n'
                          'AT StartDate:\n'
                          '  Basket.spot0 = Basket.spot@StartDate\n'
                          '\n'
                          'AT MaturityDate:\n'
                          '  SET KO = INDIC(BOF_MAX >= M_KO_BAR)\n'
                          '  SET CALL = PART * MAX(0, WORSTOF(Basket.yield) - STRIKE)\n'
                          '  PAY 1 "Remboursement nominal"\n'
                          '  PAY CALL "Participation à la hausse"\n'
                          '  PAY -1 * KO * (CALL - REBATE) "Barrière touchée : rebate à la place '
                          'de la participation"'},
 'call': {'label': 'Call',
          'family': 'options',
          'description': 'Call européen sur le worst-of, payé à maturité.',
          'underlyings': {'min': 1, 'max': 5},
          'tenors': ['6M', '1Y', '18M', '2Y', '3Y', '4Y', '5Y'],
          'constats': {'MATURITYDATE': {'role': 'maturity'},
                       'STARTDATE': {'role': 'initial_fixing'}},
          'version': '2.0',
          'script': 'UNDERLYING Basket\n'
                    '\n'
                    '# Call — sur le worst-of\n'
                    'PARAM STRIKE\n'
                    '\n'
                    'CONSTAT StartDate\n'
                    'CONSTAT MaturityDate\n'
                    '\n'
                    'AT StartDate:\n'
                    '  Basket.spot0 = Basket.spot@StartDate\n'
                    '\n'
                    'AT MaturityDate:\n'
                    '  PAY MAX(0, WORSTOF(Basket.yield) - STRIKE) "Call"'},
 'put': {'label': 'Put',
         'family': 'options',
         'description': 'Put européen sur le worst-of, payé à maturité.',
         'underlyings': {'min': 1, 'max': 5},
         'tenors': ['6M', '1Y', '18M', '2Y', '3Y', '4Y', '5Y'],
         'constats': {'MATURITYDATE': {'role': 'maturity'},
                      'STARTDATE': {'role': 'initial_fixing'}},
         'version': '2.0',
         'script': 'UNDERLYING Basket\n'
                   '\n'
                   '# Put — sur le worst-of\n'
                   'PARAM STRIKE\n'
                   '\n'
                   'CONSTAT StartDate\n'
                   'CONSTAT MaturityDate\n'
                   '\n'
                   'AT StartDate:\n'
                   '  Basket.spot0 = Basket.spot@StartDate\n'
                   '\n'
                   'AT MaturityDate:\n'
                   '  PAY MAX(0, STRIKE - WORSTOF(Basket.yield)) "Put"'},
 'call_spread': {'label': 'Call spread',
                 'family': 'options',
                 'description': 'Call acheté au strike bas et vendu au strike haut : hausse du '
                                'worst-of captée entre les deux strikes.',
                 'underlyings': {'min': 1, 'max': 5},
                 'tenors': ['6M', '1Y', '18M', '2Y', '3Y', '4Y', '5Y'],
                 'constats': {'MATURITYDATE': {'role': 'maturity'},
                              'STARTDATE': {'role': 'initial_fixing'}},
                 'version': '2.0',
                 'script': 'UNDERLYING Basket\n'
                           '\n'
                           '# Call spread — hausse captée entre deux strikes\n'
                           'PARAM K1\n'
                           'PARAM K2\n'
                           '\n'
                           'CONSTAT StartDate\n'
                           'CONSTAT MaturityDate\n'
                           '\n'
                           'AT StartDate:\n'
                           '  Basket.spot0 = Basket.spot@StartDate\n'
                           '\n'
                           'AT MaturityDate:\n'
                           '  PAY MAX(0, MIN(WORSTOF(Basket.yield) - K1, K2 - K1)) "Call spread"'},
 'digitale': {'label': 'Digitale',
              'family': 'options',
              'description': 'Coupon fixe versé à maturité si le worst-of est au-dessus du strike, '
                             'rien sinon.',
              'underlyings': {'min': 1, 'max': 5},
              'tenors': ['6M', '1Y', '18M', '2Y', '3Y', '4Y', '5Y'],
              'constats': {'MATURITYDATE': {'role': 'maturity'},
                           'STARTDATE': {'role': 'initial_fixing'}},
              'version': '2.0',
              'script': 'UNDERLYING Basket\n'
                        '\n'
                        '# Digitale — coupon fixe si le worst-of termine au-dessus du strike\n'
                        'PARAM STRIKE\n'
                        'PARAM COUPON\n'
                        '\n'
                        'CONSTAT StartDate\n'
                        'CONSTAT MaturityDate\n'
                        '\n'
                        'AT StartDate:\n'
                        '  Basket.spot0 = Basket.spot@StartDate\n'
                        '\n'
                        'AT MaturityDate:\n'
                        '  PAY INDIC(WORSTOF(Basket.yield) >= STRIKE) * COUPON "Coupon digital"'},
 'call_panier_moyenne': {'label': 'Call panier à strike et niveau final moyennés',
                         'family': 'options',
                         'description': 'Call sur un panier équipondéré ; niveau initial et niveau '
                                        'final de chaque sous-jacent moyennés sur leur fenêtre '
                                        "avant l'agrégation.",
                         'underlyings': {'min': 2, 'max': 5},
                         'tenors': ['6M', '1Y', '18M', '2Y', '3Y'],
                         'constats': {'STARTDATE': {'role': 'initial_fixing',
                                                    'window_length': '10D',
                                                    'window_frequency': '1D'},
                                      'MATURITYDATE': {'role': 'maturity',
                                                       'window_length': '30D',
                                                       'window_frequency': '1D'}},
                         'version': '2.0',
                         'script': 'UNDERLYING Basket\n'
                                   '\n'
                                   '# Call panier — strike et niveau final moyennés\n'
                                   '# Chaque sous-jacent est moyenné sur sa fenêtre, au départ '
                                   'comme à\n'
                                   "# l'arrivée, avant que AVG(Basket.yield) n'agrège.\n"
                                   'PARAM STRIKE\n'
                                   '\n'
                                   'CONSTAT StartDate AVG\n'
                                   'CONSTAT MaturityDate AVG\n'
                                   '\n'
                                   'AT StartDate:\n'
                                   '  Basket.spot0 = Basket.spot@StartDate\n'
                                   '\n'
                                   'AT MaturityDate:\n'
                                   '  PAY MAX(0, AVG(Basket.yield) - STRIKE) "Call panier '
                                   'moyenné"'},
 'call_lookback': {'label': 'Call à strike lookback',
                   'family': 'options',
                   'description': 'Call sur le worst-of dont le niveau initial de chaque '
                                  'sous-jacent est son plus bas sur la fenêtre de départ.',
                   'underlyings': {'min': 1, 'max': 5},
                   'tenors': ['6M', '1Y', '18M', '2Y', '3Y'],
                   'constats': {'STARTDATE': {'role': 'initial_fixing',
                                              'window_length': '10D',
                                              'window_frequency': '1D'},
                                'MATURITYDATE': {'role': 'maturity'}},
                   'version': '2.0',
                   'script': 'UNDERLYING Basket\n'
                             '\n'
                             '# Call à strike lookback — strike au plus bas de la fenêtre de '
                             'départ\n'
                             'PARAM STRIKE\n'
                             '\n'
                             'CONSTAT StartDate MIN\n'
                             'CONSTAT MaturityDate\n'
                             '\n'
                             'AT StartDate:\n'
                             '  Basket.spot0 = Basket.spot@StartDate\n'
                             '\n'
                             'AT MaturityDate:\n'
                             '  PAY MAX(0, WORSTOF(Basket.yield) - STRIKE) "Call sur la '
                             'performance depuis le plus bas de départ"'}}


def by_family() -> dict[str, list[str]]:
    """Clés de fiche par famille, dans l'ordre du catalogue."""
    groups: dict[str, list[str]] = {}
    for key, product in PRODUCTS.items():
        groups.setdefault(product["family"], []).append(key)
    return groups
