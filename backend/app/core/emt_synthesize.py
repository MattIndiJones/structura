"""AI-assisted payoff description for the EMT / Target Market tab.

Mirrors the AMC study synthesis pattern (amc_synthesize.py): a payload
builder that turns computed results into structured human-readable text,
a dedicated editorial system prompt, and the same LLM callers reused as-is
(call_ollama / call_claude / call_openai) so there is one implementation of
"talk to the configured provider", not one per feature.

Unlike the AMC payload tab (data only), get_synthesis_payload() below also
returns a "copy block" — system prompt + data concatenated into one text —
because a plain external AI chat (ChatGPT/Claude/Gemini web UI) has no
separate system-role field to paste the charter into.
"""
from __future__ import annotations

from .amc_synthesize import call_ollama, call_claude, call_openai  # noqa: F401 — re-exported for emt.py

EMT_SYSTEM_PROMPT_FR = """\
Tu es un structurer senior avec 20 ans d'expérience en produits structurés, habitué à rédiger \
les descriptions produit qui accompagnent le dossier de gouvernance MiFID II (EMT / Target Market) \
et les fiches de présentation aux distributeurs. Tu rédiges ici la description du mécanisme du \
produit — le texte qui explique à un conseiller ou un compliance officer, qui n'a pas écrit le \
script de pricing, ce que fait réellement le produit.

═══ CHARTE ÉDITORIALE ═══

1. Commence par une phrase de nature du produit (type de structure, sous-jacent(s), maturité).
2. Décris le mécanisme de rappel anticipé s'il existe (fréquence d'observation, barrière, coupon).
3. Décris le mécanisme à l'échéance (protection du capital, barrière de perte, effet de levier).
4. Utilise uniquement les valeurs numériques fournies dans les données — n'invente jamais un chiffre.
5. Description factuelle et neutre, sans jugement de valeur sur la qualité du produit — ce n'est \
   pas une recommandation d'investissement, c'est un descriptif technique.
6. Français clair, sans jargon inutile ni anglicisme évitable.
7. Longueur cible : 4 à 8 phrases, un seul paragraphe (ou deux courts si le produit est complexe).

═══ FORMAT DE SORTIE ═══

Un paragraphe de description prêt à être copié tel quel dans le champ "Description du produit" \
de l'EMT. Pas de titre, pas de liste à puces, pas de préambule ("Voici la description…", \
"Ce produit est…" est acceptable comme ouverture mais pas de méta-commentaire sur la tâche).
"""


def _fmt_pct(v) -> str:
    try:
        return f"{float(v):g}%"
    except Exception:
        return str(v)


def build_emt_payload(
    product_title: str,
    emt_result: dict,
    script_params: list[dict],
    underlyings: list[dict],
) -> str:
    """Serialize the EMT computation + script params into structured text for an LLM."""
    lines: list[str] = []
    add = lines.append

    add("=" * 60)
    add("  DESCRIPTION PRODUIT — EMT / MARCHÉ CIBLE — STRUCTURA")
    add("=" * 60)
    add(f"Produit : {product_title}")

    uls = ", ".join(f"{u.get('name') or u.get('ticker') or '—'}" for u in underlyings) or "—"
    add(f"Sous-jacent(s) : {uls}")
    add(f"Durée de détention recommandée : {emt_result.get('T_rhp', '—')} an(s)")
    add("")

    add("── Paramètres du produit ──")
    if script_params:
        for p in script_params:
            val = p.get("raw_default")
            unit = "%" if p.get("is_pct") else ""
            desc = p.get("desc") or p.get("name")
            add(f"  {p.get('name')} = {val}{unit}  ({desc})")
    else:
        add("  (aucun PARAM dans le script)")
    add("")

    features = emt_result.get("features") or {}
    add("── Caractéristiques détectées ──")
    add(f"  Rappel anticipé (autocall) : {'oui' if features.get('has_autocall') else 'non'}")
    add(f"  Multi-actifs (worst-of) : {'oui' if features.get('has_worst_of') else 'non'} "
        f"({features.get('n_underlyings', '—')} sous-jacent(s))")
    add(f"  Effet de levier : {'oui' if features.get('has_leverage') else 'non'}")
    add(f"  Barrière : {'oui' if features.get('has_barrier') else 'non'}")
    add("")

    cap = emt_result.get("capital_protection") or {}
    add("── Profil de risque (repris du KID) ──")
    add(f"  SRI : {emt_result.get('sri', '—')}/7")
    add(f"  Capacité à supporter des pertes : {cap.get('label', '—')}")
    add(f"  Tolérance au risque : {emt_result.get('risk_tolerance', '—')}")
    add(f"  Objectifs : {emt_result.get('objective', '—')}")
    add("=" * 60)

    return "\n".join(lines)


def build_copy_block(payload: str, system_prompt: str = EMT_SYSTEM_PROMPT_FR) -> str:
    """Persona + charter + data in one block, ready to paste into any AI chat
    that has no separate system-role field (ChatGPT/Claude/Gemini web UI)."""
    return (
        f"{system_prompt}\n\n"
        f"{payload}\n\n"
        "Rédige maintenant la description du produit selon la charte éditoriale ci-dessus, "
        "à partir des données fournies."
    )
