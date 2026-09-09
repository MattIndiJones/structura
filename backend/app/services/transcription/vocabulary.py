"""Vocabulaire de desk soufflé au moteur de dictée.

Whisper accepte un `initial_prompt` : un texte qui n'est pas transcrit, mais qui
conditionne le registre et l'orthographe attendus. C'est le seul vrai levier de
qualité disponible — et la raison principale d'avoir écarté l'API vocale du
navigateur, qui n'offre aucun équivalent.

Sans amorçage, la dictée rend « autocall » en « auto-call » ou « oto call »,
« worst-of » en « worse of », et surtout « soixante pour cent » en « 60 » sans
le signe. Le pourcentage compte : un niveau de barrière mal transcrit produit
une description plausible d'un autre produit.

Contrainte dure : Whisper ne retient que les ~224 derniers jetons du prompt.
Un vocabulaire qui grossit ne fait donc pas mieux, il **remplace par la fin** —
tenir cette liste courte et la ranger du plus général au plus spécifique, pour
que ce soit le générique qui saute en cas de dépassement.
"""
from __future__ import annotations

VOCABULAIRE_FR = (
    "Produits structurés : autocall, Athena, Phoenix, worst-of, reverse "
    "convertible, twin win, shark, capital garanti, capital protégé. "
    "Barrière désactivante, barrière de protection, knock-in, knock-out, "
    "coupon conditionnel, coupon à mémoire, rappel anticipé, date de "
    "constatation, observation continue, à tout moment, niveau initial, "
    "strike, maturité, sous-jacent, panier, nominal, participation, digitale. "
    "Sous-jacents : Nikkei, Euro Stoxx 50, S&P 500, CAC 40, Stellantis, "
    "UniCredit, STMicroelectronics, Intesa. "
    "Niveaux : barrière à 60 %, rappel à 100 %, coupon de 8 % par an."
)
