"""Second avis d'un modèle de langage sur un produit déjà pricé.

Distinct de l'assistant de scripting (`__init__.generate`) : celui-là ÉCRIT une
structure à partir d'une description, celui-ci COMMENTE une structure déjà
décrite et déjà pricée.

La règle qui gouverne tous les prompts : **le modèle ne valide jamais un
chiffre.** Un LLM ne peut pas vérifier un Monte-Carlo, et il produira une
réponse plausible et fausse avec aplomb. On lui pose des questions de structure
et d'économie ; le moteur reste seul juge du prix. Chaque prompt système le dit
explicitement, parce qu'un modèle à qui on tend un prix cherchera spontanément
à le commenter.

Le résumé du produit arrive déjà rédigé (composables/useProductSummary.js) : il
est produit une fois, affiché à l'écran et envoyé tel quel. L'utilisateur voit
donc exactement ce qui part.
"""
from __future__ import annotations

import time

from .providers import DEFAULT_PROVIDER, LlmError, complete

CADRE = """Tu es un structureur senior de produits structurés, interlocuteur d'un
pair du métier. Tu réponds en français, sans réexpliquer les bases de la finance
structurée ni de la simulation Monte-Carlo.

RÈGLE ABSOLUE : tu ne valides ni ne conteste aucun chiffre de prix, de grec ou de
probabilité. Ils viennent d'un moteur Monte-Carlo qui fait autorité, et tu n'as
aucun moyen de les recalculer. Si un chiffre te surprend, dis en quoi il est
surprenant et ce qu'il faudrait vérifier — ne propose jamais une valeur de
remplacement.

Tu raisonnes sur la STRUCTURE et l'ÉCONOMIE du produit : quel risque est porté
par qui, quelle sensibilité domine, quelle hypothèse est fragile, quel scénario
fait mal.

N'AFFIRME RIEN qui ne figure pas dans le résumé. Tu ne connais ni la
capitalisation, ni la liquidité, ni l'actualité des sous-jacents — si un
raisonnement en aurait besoin, dis qu'il faudrait le vérifier au lieu de
supposer. Une invention plausible est plus nuisible qu'un blanc assumé.

Compare les sensibilités par leur ORDRE DE GRANDEUR avant de désigner la
dominante : un delta de 0,60 pèse vingt fois un vega de 0,03. Ne qualifie pas de
dominante une sensibilité plus petite qu'une autre du même résumé.

Le payoff t'est donné en PayScript, un DSL dont la clé de lecture figure dans le
résumé. Prends-le comme la description faisant foi du produit."""

INTENTIONS = {
    "analyse": {
        "label": "Analyse du risque",
        "consigne": """Analyse le risque de ce produit du point de vue de son
DÉTENTEUR. Dans l'ordre : de quoi est-il réellement vendeur, quelle sensibilité
domine et pourquoi, quel scénario de marché lui fait le plus mal, et quelles
hypothèses du pricing sont les plus fragiles. Sois bref et hiérarchisé : ce qui
compte d'abord, le reste ensuite. Pas de généralités sur les autocalls.""",
    },
    "restructuration": {
        "label": "Pistes de restructuration",
        "consigne": """Une restructuration a UN but : dégager de la valeur pour
redonner au détenteur un chemin réaliste vers le pair. Ce n'est pas un exercice
de réduction de sensibilité — c'est la question « le client est assis sur une
note qui vaut 46 %, que peut-on lui proposer qui lui rende une chance de
récupérer ». Réponds à CETTE question.

Le levier est toujours le même : vendre de l'optionnalité que le détenteur ne
valorise plus, et racheter avec le produit de cette vente quelque chose qui le
rapproche du pair. Sur une note dont le worst-of a décroché très bas, les pistes
usuelles sont d'abaisser la barrière de capital, d'abaisser le seuil de rappel
pour rendre le rappel atteignable, d'allonger la maturité pour laisser au
sous-jacent le temps de revenir, de retirer du panier le sous-jacent qui a
décroché, ou d'échanger le coupon conditionnel contre de la participation à la
hausse. Choisis celles qui ont du sens ICI, pas une liste générique.

Propose deux ou trois pistes. Pour chacune : ce qu'elle coûte au détenteur (ce
qu'il abandonne), ce qu'elle lui rend (le chemin vers le pair qu'elle ouvre), et
dans quel scénario de marché elle paie.

Donne le payoff modifié en PayScript dans un bloc de code, en gardant EXACTEMENT
la grammaire de l'original — il sera repricé tel quel par le moteur. N'invente
aucune construction : les seuls blocs valides sont `AT <nom>:` et
`AT <nom>.last:`. Signale en une ligne ce que tu as changé par rapport au script
d'origine.""",
    },
    "argumentaire": {
        "label": "Argumentaire client",
        "consigne": """Explique ce produit à un investisseur non spécialiste, en
français simple et sans jargon. Dis ce qu'il touche et quand, à quelle condition,
et surtout ce qu'il risque de perdre et dans quel cas. Sois honnête sur les
scénarios défavorables : un argumentaire qui les masque ne tient pas une réunion.
Pas de superlatifs commerciaux.""",
    },
    "critique": {
        "label": "Revue critique",
        "consigne": """Joue le sceptique. Qu'est-ce qui cloche dans ce produit ou
dans la façon dont il est pricé ? Que reprocherait un comité des risques ? Quelle
hypothèse pourrait être fausse et avec quelle conséquence ? Qu'est-ce que le
structureur ne voit probablement pas ?

Sois direct et spécifique à CE produit. Si tu ne trouves rien de sérieux sur un
point, dis-le plutôt que de meubler.""",
    },
    "libre": {
        "label": "Question libre",
        "consigne": "",
    },
}


def construire_prompts(resume: str, intention: str, question: str = "") -> dict:
    """Les deux messages EXACTS qui partiront — système et utilisateur.

    Factorisé pour que l'aperçu à l'écran et l'appel réel ne puissent pas
    diverger : un aperçu qui montrerait autre chose que ce qui part serait pire
    que pas d'aperçu du tout. `analyse_produit` passe par ici."""
    if not (resume or "").strip():
        raise LlmError("Résumé vide : lancez un pricing avant de demander un avis.")

    conf = INTENTIONS.get(intention)
    if conf is None:
        raise LlmError(f"Intention inconnue : {intention!r} — "
                       f"valeurs admises : {', '.join(INTENTIONS)}.")

    consigne = conf["consigne"]
    if intention == "libre":
        if not (question or "").strip():
            raise LlmError("Question libre : précisez ce que vous voulez demander.")
        consigne = question.strip()
    elif question.strip():
        # Une précision de l'utilisateur complète l'intention, elle ne la
        # remplace pas — sinon le menu ne servirait à rien dès qu'on écrit.
        consigne = f"{consigne}\n\nPrécision de l'utilisateur : {question.strip()}"

    return {"system": CADRE, "user": f"{consigne}\n\n---\n\n{resume}",
            "intention": intention, "intention_label": conf["label"]}


def analyse_produit(resume: str, intention: str, *, question: str = "",
                    provider: str = DEFAULT_PROVIDER,
                    model: str | None = None) -> dict:
    """Un second avis, avec sa provenance.

    Rend toujours de quoi étiqueter la réponse — fournisseur, modèle, horodatage
    — parce qu'un avis de modèle qui traîne sans sa provenance finit par se lire
    comme une conclusion validée."""
    prompts = construire_prompts(resume, intention, question)

    t0 = time.perf_counter()
    texte = complete(provider, model, prompts["system"], prompts["user"],
                     temperature=0.4, max_tokens=2500)
    return {
        "texte": texte.strip(),
        "intention": intention,
        "intention_label": prompts["intention_label"],
        "provider": provider,
        "model": model or "",
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        # Le desk doit pouvoir dire d'où vient un avis, six mois plus tard.
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
