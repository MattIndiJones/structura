"""Construction du prompt de l'assistant de scripting.

Le corps du prompt système est `docs/PAYSCRIPT_REFERENCE.md`, lu à l'exécution.
Recopier la grammaire ici en ferait une seconde source de vérité qui dériverait
en silence : le prompt promettrait au modèle une syntaxe que le parser refuse,
et l'assistant échouerait à chaque appel sans que rien n'explique pourquoi.
`test_payscript_reference.py` verrouille l'accord entre la référence et le
parser ; ce module se contente de la servir.
"""
from __future__ import annotations

import re
from pathlib import Path

from .examples_extra import all_examples

# backend/app/services/llm/prompt.py -> parents[4] == racine du dépôt
REFERENCE_PATH = (Path(__file__).resolve().parents[4]
                  / "docs" / "PAYSCRIPT_REFERENCE.md")

SCRIPT_MARK = "===SCRIPT==="
EXPLAIN_MARK = "===EXPLICATION==="

# Familles de produits -> mots de la demande qui les désignent. Sert à choisir
# les exemples : montrer un call vanille à qui demande un phoenix dilue le
# signal et fait payer des jetons pour rien.
_FAMILY_HINTS = {
    "Autocall": ("autocall", "athena", "phoenix", "rappel", "rappelable",
                 "callable", "worst-of", "worst of", "coupon conditionnel",
                 "memoire", "mémoire"),
    "Produits à capital": ("capital garanti", "capital protégé", "capital protege",
                           "reverse convertible", "twin win", "booster",
                           "participation", "protection"),
    "Sharks": ("shark", "knock-out", "knock out", "ko", "rebate", "rebond"),
    "Options": ("call", "put", "spread", "digital", "binaire", "option",
                "vanille", "strike"),
}

_MAX_EXAMPLES = 5

# Idiomes que le prompt IMPOSE dans ses règles : chacun doit être montré par au
# moins un exemple envoyé, sinon la règle est énoncée sans jamais être vue. La
# bibliothèque de l'éditeur n'illustre ni le coupon mémoire ni les `PARAM()` —
# d'où examples_extra.py.
_REQUIRED_IDIOMS = ("stop", "memoire")


def _read_reference() -> str:
    try:
        return REFERENCE_PATH.read_text(encoding="utf-8")
    except OSError as e:                                   # pragma: no cover
        raise RuntimeError(
            f"Référence de langage introuvable ({REFERENCE_PATH}) — l'assistant "
            f"ne peut pas décrire PayScript sans elle.") from e


def select_examples(description: str, limit: int = _MAX_EXAMPLES) -> list[str]:
    """Clés des exemples à montrer, du plus pertinent au moins.

    Deux critères se cumulent : la proximité avec la demande (montrer un call
    vanille à qui demande un phoenix dilue le signal), et la couverture des
    idiomes que les règles du prompt imposent. Un modèle applique mal une règle
    qu'il n'a jamais vue appliquée."""
    lib = all_examples()
    d = (description or "").lower()
    scores: dict[str, int] = {}
    for key, tpl in lib.items():
        famille = tpl.get("group", "")
        hits = sum(1 for mot in _FAMILY_HINTS.get(famille, ()) if mot in d)
        # Un mot du libellé cité tel quel dans la demande vaut un point de plus.
        hits += sum(1 for mot in re.findall(r"\w{4,}", tpl.get("label", "").lower())
                    if mot in d)
        if hits:
            scores[key] = hits

    ordered = sorted(scores, key=lambda k: (-scores[k], k))
    if not ordered:
        # Demande non classée : partir de l'autocall, de très loin la famille
        # la plus fréquente sur un desk.
        ordered = sorted(k for k, t in lib.items() if t.get("group") == "Autocall")

    chosen = ordered[:limit]
    for idiome in _REQUIRED_IDIOMS:
        if any(idiome in lib[k].get("idioms", ()) for k in chosen):
            continue
        porteur = next((k for k in lib if idiome in lib[k].get("idioms", ())), None)
        if porteur is None:                      # pragma: no cover — test_llm_prompt
            continue
        if porteur in chosen:
            continue
        if len(chosen) >= limit:
            chosen.pop()                          # le moins pertinent cède la place
        chosen.append(porteur)
    return chosen


def build_system_prompt(description: str = "") -> str:
    """Rôle, grammaire, règles dures, contrat de sortie, exemples."""
    lib = all_examples()
    exemples = "\n\n".join(
        f"--- Exemple : {lib[k]['label']} ---\n{lib[k]['script']}"
        for k in select_examples(description)
    )
    return f"""Tu es un structureur senior de produits dérivés. Tu écris des payoffs \
dans un langage interne appelé PayScript, et RIEN D'AUTRE.

Ta seule tâche : traduire une description en français d'un produit structuré en \
un script PayScript correct. Tu n'inventes pas de niveaux que l'utilisateur n'a \
pas donnés, tu ne pricees rien, tu ne commentes pas le marché.

═══════════════════════════════════════════════════════════════════
RÉFÉRENCE DU LANGAGE — fais-y strictement autorité
═══════════════════════════════════════════════════════════════════
{_read_reference()}

═══════════════════════════════════════════════════════════════════
EXEMPLES DE SCRIPTS QUI FONCTIONNENT RÉELLEMENT ICI
═══════════════════════════════════════════════════════════════════
{exemples}

═══════════════════════════════════════════════════════════════════
RÈGLES IMPÉRATIVES
═══════════════════════════════════════════════════════════════════
1. N'utilise QUE le vocabulaire de la référence. Aucun mot inventé.
2. Tout script comporte un bloc `AT MATURITY` qui solde le produit.
3. Tout rappel anticipé se termine par `STOP`. Sans `STOP`, ce n'est pas un rappel.
4. Barrière observée à la date de constatation -> `WOF`. Barrière franchie à un
   moment quelconque de la vie du produit (knock-in de termsheet) -> `WOF_MIN`.
   En cas de doute sur une barrière de perte en capital, c'est `WOF_MIN`.
5. Ne rembourse jamais le nominal deux fois.
6. Un coupon à mémoire exige `SET MEMO = INDEX` après le versement.
7. Préfixe `M_` les paramètres de barrière (rappel, knock-in).
8. Déclare en `PARAM` tout niveau chiffré, avec sa valeur par défaut. N'écris
   jamais un niveau en dur dans une expression.
9. Un nom de PARAM ou de SET ne peut pas être un mot du langage (§ Noms réservés).
10. Les dates `AT` sont en années depuis aujourd'hui, strictement positives.

═══════════════════════════════════════════════════════════════════
FORMAT DE RÉPONSE — impératif
═══════════════════════════════════════════════════════════════════
Réponds EXACTEMENT dans ce format, sans aucun texte avant ni après, et sans
balises de code markdown :

{SCRIPT_MARK}
<le script PayScript, rien d'autre>
{EXPLAIN_MARK}
<en français, 4 à 8 lignes : ce que paie le produit, à quelles dates, sous
quelles conditions, et ce qui se passe à maturité. Écris-le pour qu'un
structureur puisse vérifier ton intention SANS relire le script.>
"""


def build_user_prompt(description: str, *, n_underlyings: int = 1,
                      maturity: float | None = None,
                      observation_hint: str = "") -> str:
    """La demande, plus le contexte que l'application connaît déjà — sans quoi
    le modèle invente un calendrier et un nombre de sous-jacents."""
    lignes = [f"Nombre de sous-jacents configurés : {n_underlyings}"]
    if maturity:
        lignes.append(f"Maturité configurée : {maturity:g} ans")
    if observation_hint:
        lignes.append(f"Calendrier d'observation : {observation_hint}")
    contexte = "\n".join(lignes)
    return (f"CONTEXTE DU PRICING (à respecter)\n{contexte}\n\n"
            f"PRODUIT DEMANDÉ\n{description.strip()}")


def build_repair_prompt(script: str, erreur: str) -> str:
    """Second tour après refus du parser. On renvoie l'erreur EXACTE — elle
    porte le numéro de ligne et elle est déjà en français."""
    return (
        "Le script que tu viens d'écrire est refusé par le parser PayScript.\n\n"
        f"SCRIPT REFUSÉ\n{script}\n\n"
        f"ERREUR DU PARSER\n{erreur}\n\n"
        "Corrige uniquement ce qui est en cause, en conservant le produit décrit "
        "et le même format de réponse. N'explique pas la correction dans le "
        "bloc script."
    )


def build_refine_prompt(script: str, demande: str) -> str:
    """Affinage à la demande de l'utilisateur, script courant à l'appui."""
    return (
        f"SCRIPT ACTUEL\n{script}\n\n"
        f"MODIFICATION DEMANDÉE\n{demande.strip()}\n\n"
        "Renvoie le script complet modifié, dans le même format de réponse."
    )
