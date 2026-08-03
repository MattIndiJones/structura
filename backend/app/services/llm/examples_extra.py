"""Exemples complémentaires, propres à l'assistant.

La bibliothèque de l'éditeur (`core/payscript/templates.py`) couvre les familles
de produits, pas tous les idiomes du langage. Vérification faite, elle
n'illustre **jamais** le coupon à mémoire, les `PARAM()` par observation, ni un
`ELSE` — alors que le prompt en impose l'usage.

Un modèle imite bien plus fidèlement ce qu'il voit que ce qu'on lui décrit : une
règle énoncée sans exemple est une règle qu'il applique mal. Ces scripts comblent
l'écart. Ils ne sont pas proposés dans l'éditeur (ce n'est pas leur rôle) mais
`test_llm_prompt.py` vérifie qu'ils compilent et pricent, exactement comme ceux
de la bibliothèque.
"""

EXTRA_EXAMPLES: dict[str, dict] = {
    "phoenix_memoire": {
        "label": "Phoenix à coupon mémoire",
        "group": "Autocall",
        "idioms": ("memoire", "stop"),
        "script": """# Phoenix 3 ans à coupon mémoire — les coupons manqués sont rattrapés
PARAM COUPON = 8%
PARAM M_AC_BAR = 100%
PARAM M_CPN_BAR = 70%
PARAM M_KI_BAR = 60%

AT 1, 2, 3:
  IF WOF >= M_CPN_BAR:
    PAY COUPON * (INDEX - MEMO) "coupon + rattrapage"
    SET MEMO = INDEX
  IF WOF >= M_AC_BAR:
    PAY 1 "remboursement anticipé"
    STOP

AT MATURITY:
  SET KI = INDIC(WOF_MIN < M_KI_BAR)
  PAY (1 - KI) * 1 "capital protégé"
  PAY KI * WOF "perte en capital\"""",
    },
    "autocall_barriere_degressive": {
        "label": "Autocall à barrière de rappel dégressive",
        "group": "Autocall",
        "idioms": ("param_array", "stop"),
        "script": """# Autocall 3 ans — barrière de rappel dégressive (105%, 100%, 95%)
# PARAM() : une valeur par observation, saisie dans l'interface.
PARAM COUPON = 8%
PARAM() M_AC_BAR = 105%
PARAM M_KI_BAR = 60%

AT 1, 2, 3:
  IF WOF >= M_AC_BAR:
    PAY 1 + COUPON * INDEX "rappel + coupons cumulés"
    STOP

AT MATURITY:
  IF WOF_MIN >= M_KI_BAR:
    PAY 1 "capital protégé"
  ELSE:
    PAY WOF "perte en capital\"""",
    },
    "reverse_convertible_ki_americain": {
        "label": "Reverse convertible à knock-in américain",
        "group": "Produits à capital",
        "idioms": ("wof_min", "else"),
        "script": """# Reverse convertible 2 ans — coupon inconditionnel, KI observé en continu
# WOF_MIN : la barrière est franchie si le sous-jacent PASSE sous le niveau
# à un moment quelconque, pas seulement à la date de constatation.
PARAM COUPON = 9%
PARAM M_KI_BAR = 65%

AT 1, 2:
  PAY COUPON "coupon fixe"

AT MATURITY:
  IF WOF_MIN >= M_KI_BAR:
    PAY 1 "capital remboursé au pair"
  ELSE:
    PAY WOF "livraison en titres (perte en capital)\"""",
    },
}


def all_examples() -> dict[str, dict]:
    """Bibliothèque de l'éditeur + compléments, sous une clé unique."""
    from ...core.payscript.templates import TEMPLATES
    merged = {k: dict(v, idioms=()) for k, v in TEMPLATES.items()}
    merged.update(EXTRA_EXAMPLES)
    return merged
