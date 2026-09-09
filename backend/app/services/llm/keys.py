"""Clés d'API des fournisseurs de modèles.

Même politique que la clé de signature JWT (`api/auth.py`) : l'environnement
d'abord, puis un fichier dans `backend/data/` — le répertoire qui héberge la
base. Attention : `backend/data/` n'est **pas** ignoré en bloc par git, seuls
certains motifs le sont ; les deux fichiers ci-dessous ont donc leur ligne
nommément dans `.gitignore`, comme `.jwt_secret`. Jamais dans le dépôt, jamais
en base, et **jamais dans le bundle frontend** : c'est pour cela que l'appel au modèle part du serveur. Un
appel navigateur → OpenAI expédierait la clé à chaque utilisateur de
l'application.

Ollama ne demande aucune clé : c'est ce qui en fait le choix par défaut ici.
Une description de produit structuré envoyée à un tiers, c'est une idée de
structuration qui sort du desk.
"""
from __future__ import annotations

import os
from pathlib import Path

# backend/app/services/llm/keys.py -> parents[3] == backend/
_KEY_DIR = Path(__file__).resolve().parents[3] / "data"

# Fournisseur -> (variable d'environnement, fichier de repli)
_SOURCES = {
    "openai": ("OPENAI_API_KEY", ".openai_key"),
    "anthropic": ("ANTHROPIC_API_KEY", ".anthropic_key"),
}


def load_key(provider: str) -> str | None:
    """Clé du fournisseur, ou None s'il n'en demande pas / n'en a pas.

    Renvoyer None plutôt que lever : l'interface doit pouvoir afficher quels
    moteurs sont disponibles sans faire tomber la page pour ceux qui ne le sont
    pas."""
    src = _SOURCES.get(provider)
    if src is None:
        return None                      # ollama : pas de clé
    env_name, filename = src
    from_env = os.environ.get(env_name, "").strip()
    if from_env:
        return from_env
    path = _KEY_DIR / filename
    try:
        if path.exists():
            stored = path.read_text(encoding="utf-8").strip()
            if stored:
                return stored
    except OSError:
        pass
    return None


def missing_key_message(provider: str) -> str:
    env_name, filename = _SOURCES[provider]
    return (
        f"Aucune clé d'API pour {provider}. Renseignez la variable "
        f"d'environnement {env_name}, ou déposez la clé dans "
        f"backend/data/{filename} (fichier non versionné). "
        f"Vous pouvez aussi utiliser Ollama, qui tourne en local sans clé."
    )
