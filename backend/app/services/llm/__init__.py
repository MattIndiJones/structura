"""Assistant de scripting PayScript adossé à un modèle de langage.

Le modèle écrit une STRUCTURE ; il ne price pas et ne fixe aucun niveau que
l'utilisateur n'a pas donné. Le moteur Monte-Carlo reste seul juge du prix.

Enchaînement : `generate()` construit le prompt (prompt.py), appelle le
fournisseur (providers.py), assainit et contrôle la réponse (validate.py), et
réessaie une fois si le parser refuse — en lui renvoyant son propre message
d'erreur.
"""
from __future__ import annotations

import time

from .prompt import (build_system_prompt, build_user_prompt, build_repair_prompt,
                     build_refine_prompt)
from .providers import (PROVIDERS, DEFAULT_PROVIDER, LlmError, complete,
                        available_providers)
from .validate import Validation, validate

__all__ = ["generate", "preview_prompt", "available_providers", "PROVIDERS",
           "DEFAULT_PROVIDER", "LlmError", "Validation"]

# Une seule reprise. Un modèle qui échoue deux fois sur la même erreur échouera
# la troisième : au-delà, on triple le coût et l'attente pour rien, et mieux
# vaut rendre la main avec l'erreur du parser que l'utilisateur peut lire.
MAX_REPAIRS = 1


def generate(description: str, *, provider: str = DEFAULT_PROVIDER,
             model: str | None = None, underlyings, corr, r: float, T: float,
             user_params: dict | None = None, current_script: str = "",
             refine: bool = False) -> dict:
    """Produit un script, sa reformulation en français et sa fiche de contrôle.

    `refine` reprend `current_script` au lieu de repartir de zéro : « non, la
    barrière doit être observée en continu » doit affiner, pas tout réécrire."""
    user_params = user_params or {}
    t0 = time.perf_counter()

    system = build_system_prompt(description)
    if refine and current_script.strip():
        user = build_refine_prompt(current_script, description)
    else:
        user = build_user_prompt(description, n_underlyings=len(underlyings),
                                 maturity=T)

    attempts: list[dict] = []
    raw = complete(provider, model, system, user)
    v = validate(raw, description=description, underlyings=underlyings, corr=corr,
                 r=r, T=T, user_params=user_params)
    attempts.append({"parse_error": v.parse_error})

    repairs = 0
    while v.parse_error and repairs < MAX_REPAIRS:
        repairs += 1
        raw = complete(provider, model, system,
                       build_repair_prompt(v.script, v.parse_error))
        v = validate(raw, description=description, underlyings=underlyings,
                     corr=corr, r=r, T=T, user_params=user_params)
        attempts.append({"parse_error": v.parse_error})

    out = v.as_dict()
    out.update({
        "provider": provider,
        "model": model or PROVIDERS[provider].default_model,
        "repairs": repairs,
        "attempts": attempts,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        # Le prompt exact qui a produit ce script. Les exemples envoyés
        # dépendent de la demande : sans le voir, on ne peut ni comprendre une
        # génération ratée, ni ajuster sa description en connaissance de cause.
        "prompt": {"system": system, "user": user},
    })
    return out


def preview_prompt(description: str, *, n_underlyings: int = 1,
                   maturity: float | None = None) -> dict:
    """Le prompt tel qu'il partirait, sans rien dépenser ni attendre."""
    from .prompt import select_examples
    system = build_system_prompt(description)
    user = build_user_prompt(description, n_underlyings=n_underlyings,
                             maturity=maturity)
    return {
        "system": system,
        "user": user,
        "examples": select_examples(description),
        "chars": len(system) + len(user),
        # Approximation usuelle : ~4 caractères par jeton en français.
        "approx_tokens": (len(system) + len(user)) // 4,
    }
