"""Dictée de la description produit — transcription locale.

L'utilisateur décrit son produit à voix haute plutôt qu'au clavier. Le texte
transcrit atterrit dans le champ de saisie, éditable, et rien ne part au modèle
de langage tant qu'il n'a pas cliqué : une transcription qui avale « à tout
moment » décrit un autre produit, et l'aide de l'écran dit elle-même que c'est
la différence entre deux produits qui ne valent pas le même prix.
"""
from __future__ import annotations

from .engines import (ENGINES, DEFAULT_ENGINE, MAX_UPLOAD_MB, TranscriptionError,
                      available_engines, transcribe, warmup)

__all__ = ["ENGINES", "DEFAULT_ENGINE", "MAX_UPLOAD_MB", "TranscriptionError",
           "available_engines", "transcribe", "warmup"]
