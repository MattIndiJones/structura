"""Trois fournisseurs de modèles, une seule interface.

Ollama, OpenAI et Anthropic exposent la même chose — un message système, un
message utilisateur, du texte en retour — sous trois enveloppes JSON
différentes. Trois adaptateurs `httpx` suffisent ; installer trois SDK
reviendrait à porter trois arbres de dépendances et trois cycles de versions
pour trois requêtes HTTP identiques.

Ollama est le défaut : local, sans clé, et surtout la description du produit ne
quitte pas la machine.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from .keys import load_key, missing_key_message

# Délai généreux : un modèle local de 14 à 32 milliards de paramètres met
# facilement 30 à 90 s sur un CPU, et l'échec par expiration est le plus
# décourageant de tous — l'utilisateur ne sait pas si c'est lui ou l'outil.
TIMEOUT_S = 180.0

OLLAMA_URL = "http://localhost:11434"


@dataclass(frozen=True)
class ProviderInfo:
    key: str
    label: str
    needs_key: bool
    default_model: str
    # Modèles proposés dans l'interface. Liste indicative : n'importe quel nom
    # accepté par le fournisseur passe.
    models: tuple[str, ...]


PROVIDERS = {
    "ollama": ProviderInfo(
        key="ollama", label="Ollama (local)", needs_key=False,
        # Un modèle orienté code suit mieux une grammaire imposée qu'un modèle
        # généraliste de taille comparable. À départager avec le jeu
        # d'évaluation (backend/tests/test_llm_eval.py).
        default_model="qwen2.5-coder:14b",
        models=("qwen2.5-coder:14b", "qwen2.5-coder:32b", "llama3.3:70b",
                "mistral-small:24b", "codellama:13b"),
    ),
    "openai": ProviderInfo(
        key="openai", label="ChatGPT (OpenAI)", needs_key=True,
        default_model="gpt-4o",
        models=("gpt-4o", "gpt-4o-mini", "gpt-4.1"),
    ),
    "anthropic": ProviderInfo(
        key="anthropic", label="Claude (Anthropic)", needs_key=True,
        # Famille Claude 5 (rafraîchie le 08/09/2026). L'identifiant du Haiku
        # porte sa date de version, contrairement aux deux autres.
        default_model="claude-sonnet-5",
        models=("claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001"),
    ),
}

DEFAULT_PROVIDER = "ollama"


class LlmError(RuntimeError):
    """Échec côté fournisseur — remonté tel quel à l'utilisateur, en français."""


def ollama_models() -> list[str] | None:
    """Modèles réellement INSTALLÉS localement, ou None si Ollama ne répond pas.

    La liste indicative de PROVIDERS ne sert qu'à documenter des choix
    raisonnables : proposer dans le sélecteur un modèle que la machine n'a pas
    conduit tout droit à « Modèle inconnu d'Ollama » après une génération
    lancée pour rien. Un sélecteur doit lister ce qui existe."""
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2.5)
        if r.status_code >= 400:
            return None
        noms = [m.get("name", "") for m in (r.json().get("models") or [])]
        return sorted(n for n in noms if n)
    except Exception:
        return None                      # éteint, injoignable, format inattendu


def available_providers() -> list[dict]:
    """Ce que l'interface affiche dans le sélecteur, avec l'état de chaque
    moteur. Ollama est sondé (2,5 s au pire) pour lister ses modèles installés :
    l'alternative — une liste figée — fait choisir un modèle absent et n'échoue
    qu'après la génération."""
    installed = ollama_models()
    out = []
    for info in PROVIDERS.values():
        ready = (not info.needs_key) or bool(load_key(info.key))
        models = list(info.models)
        default = info.default_model
        hint = None if ready else missing_key_message(info.key)

        if info.key == "ollama":
            if installed is None:
                ready = False
                hint = ("Ollama ne répond pas sur localhost:11434. Lancez "
                        "`ollama serve`, puis rouvrez cette fenêtre.")
            elif not installed:
                ready = False
                hint = ("Ollama tourne mais aucun modèle n'est installé. "
                        "Suggestion : `ollama pull qwen2.5-coder:14b`.")
            else:
                models = installed
                # Le défaut recommandé s'il est là, sinon le premier installé —
                # jamais un nom absent de la machine.
                default = (info.default_model if info.default_model in installed
                           else installed[0])

        out.append({
            "key": info.key, "label": info.label, "ready": ready,
            "needs_key": info.needs_key,
            "default_model": default, "models": models,
            "hint": hint,
            "recommended": info.default_model,
        })
    return out


def _post(url: str, payload: dict, headers: dict | None = None) -> dict:
    try:
        r = httpx.post(url, json=payload, headers=headers or {}, timeout=TIMEOUT_S)
    except httpx.ConnectError as e:
        if "11434" in url:
            raise LlmError(
                "Ollama ne répond pas sur localhost:11434. Démarrez-le "
                "(`ollama serve`) et vérifiez que le modèle est installé "
                "(`ollama pull <modèle>`)."
            ) from e
        raise LlmError(f"Connexion impossible au fournisseur : {e}") from e
    except httpx.TimeoutException as e:
        raise LlmError(
            f"Le modèle n'a pas répondu en {TIMEOUT_S:.0f} s. Un modèle local "
            f"volumineux sur CPU peut dépasser ce délai — essayez un modèle "
            f"plus petit."
        ) from e
    if r.status_code >= 400:
        detail = r.text[:400]
        if r.status_code in (401, 403):
            raise LlmError(f"Clé d'API refusée par le fournisseur ({r.status_code}).")
        if r.status_code == 404 and "11434" in url:
            raise LlmError(
                f"Modèle inconnu d'Ollama. Installez-le avec "
                f"`ollama pull {payload.get('model', '<modèle>')}`."
            )
        if r.status_code == 429:
            raise LlmError("Quota du fournisseur atteint (429). Réessayez plus tard.")
        raise LlmError(f"Erreur du fournisseur ({r.status_code}) : {detail}")
    return r.json()


def _complete_ollama(model: str, system: str, user: str, temperature: float,
                     max_tokens: int) -> str:
    data = _post(f"{OLLAMA_URL}/api/chat", {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    })
    return (data.get("message") or {}).get("content", "")


def _complete_openai(model: str, system: str, user: str, temperature: float,
                     max_tokens: int) -> str:
    key = load_key("openai")
    if not key:
        raise LlmError(missing_key_message("openai"))
    data = _post("https://api.openai.com/v1/chat/completions", {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }, {"Authorization": f"Bearer {key}"})
    choices = data.get("choices") or []
    return choices[0]["message"]["content"] if choices else ""


def _complete_anthropic(model: str, system: str, user: str, temperature: float,
                        max_tokens: int) -> str:
    key = load_key("anthropic")
    if not key:
        raise LlmError(missing_key_message("anthropic"))
    data = _post("https://api.anthropic.com/v1/messages", {
        "model": model,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }, {"x-api-key": key, "anthropic-version": "2023-06-01"})
    blocks = data.get("content") or []
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


_DISPATCH = {
    "ollama": _complete_ollama,
    "openai": _complete_openai,
    "anthropic": _complete_anthropic,
}


def _modele_effectif(info: ProviderInfo, model: str | None) -> str:
    """Le modèle à appeler réellement, jamais un nom absent de la machine.

    Le défaut de PROVIDERS est celui de l'assistant de SCRIPTING — un modèle de
    code. Il n'a aucune raison d'être installé sur une machine qui se sert de
    l'application pour autre chose, et l'échec arrivait après coup, sous la
    forme d'un « Modèle inconnu d'Ollama » que rien n'annonçait dans l'écran.

    Pour Ollama on sait ce qui est installé : on s'y tient. Demander un modèle
    absent est une erreur qu'on peut éviter au lieu de la reporter.
    """
    demande = model or info.default_model
    if info.key != "ollama":
        return demande
    installes = ollama_models()
    if not installes or demande in installes:
        return demande
    # Le défaut recommandé s'il est là, sinon le premier installé.
    return info.default_model if info.default_model in installes else installes[0]


def complete(provider: str, model: str | None, system: str, user: str, *,
             temperature: float = 0.1, max_tokens: int = 2000) -> str:
    """Une réponse texte. `temperature` bas par défaut : écrire un payoff dans
    une grammaire imposée n'est pas un exercice de création."""
    info = PROVIDERS.get(provider)
    if info is None:
        raise LlmError(
            f"Moteur inconnu : {provider!r} — valeurs admises : "
            f"{', '.join(PROVIDERS)}.")
    out = _DISPATCH[provider](_modele_effectif(info, model), system, user,
                              temperature, max_tokens)
    if not (out or "").strip():
        raise LlmError("Le modèle a renvoyé une réponse vide.")
    return out
