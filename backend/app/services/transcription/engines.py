"""Dictée : un registre de moteurs, un seul livré — et il est local.

Même parti pris que `services/llm/providers.py`, pour la même raison, en plus
fort. Ollama y est le défaut parce qu'« une description de produit structuré
envoyée à un tiers, c'est une idée de structuration qui sort du desk » ; à la
dictée on en dit davantage qu'au clavier — le nom du client, la contrepartie,
le niveau visé sortent sans qu'on y pense. L'audio ne quitte donc pas la
machine, et aucun moteur distant n'est branché ici.

Rien de tout cela ne s'exécute DANS le serveur : la transcription part dans un
processus séparé (`worker.py`), qui explique pourquoi. En résumé, ctranslate2 et
numpy embarquent chacun un runtime OpenMP, et les deux dans un même processus
Windows tuent celui-ci d'une violation d'accès au chargement du modèle — sans
exception Python, donc sans rien dans les journaux. Ce module ne charge donc
aucune bibliothèque native ; il se contente de lancer le worker et de lire sa
réponse.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .vocabulary import VOCABULAIRE_FR

# backend/app/services/transcription/engines.py -> parents[3] == backend/
# Les poids vivent avec le reste des données de l'app plutôt que dans le cache
# HuggingFace de l'utilisateur : même répertoire que la base et les caches de
# prix, donc un seul endroit à connaître — et à exclure de git.
MODEL_DIR = Path(__file__).resolve().parents[3] / "data" / "whisper_models"
WORKER = Path(__file__).resolve().parent / "worker.py"

# `small` quantifié int8 : ~480 Mo, plusieurs fois le temps réel sur CPU, ce qui
# rend une dictée de 60 s relisable tout de suite. `medium` transcrit
# sensiblement mieux le vocabulaire de desk mais tourne autour du temps réel —
# on attendrait alors aussi longtemps qu'on a parlé. À rebasculer ici si la
# machine change.
MODEL_SIZE = "small"
COMPUTE_TYPE = "int8"

# Un enregistrement de dictée réaliste pèse quelques centaines de kilo-octets en
# Opus. La borne n'est pas là pour économiser le disque mais pour qu'un onglet
# resté à enregistrer toute une nuit ne bloque pas une requête pendant des
# minutes.
MAX_UPLOAD_MB = 25

# Une dictée d'une minute se transcrit en une vingtaine de secondes sur CPU,
# rechargement du modèle compris. La marge sert aux machines lentes ; au-delà,
# quelque chose est bloqué et il vaut mieux rendre la main.
TIMEOUT_S = 300.0
# Préparation : le premier appel télécharge ~480 Mo. C'est une action explicite
# de l'utilisateur, avec un indicateur d'attente à l'écran.
WARMUP_TIMEOUT_S = 1800.0


@dataclass(frozen=True)
class EngineInfo:
    key: str
    label: str
    local: bool
    model: str


ENGINES = {
    "whisper-local": EngineInfo(
        key="whisper-local", label="Whisper (local)", local=True, model=MODEL_SIZE,
    ),
}

DEFAULT_ENGINE = "whisper-local"

INSTALL_HINT = (
    "Le moteur de dictée n'est pas installé. Depuis la racine du dépôt : "
    "`pip install faster-whisper`, puis redémarrez le serveur."
)


class TranscriptionError(RuntimeError):
    """Échec de la dictée — remonté tel quel à l'utilisateur, en français."""


def _faster_whisper_disponible() -> bool:
    """Présence du paquet, SANS l'importer.

    `find_spec` regarde le système de fichiers ; un `import faster_whisper`
    chargerait les DLL de ctranslate2 dans le processus du serveur, ce que tout
    ce module s'emploie à éviter."""
    try:
        return importlib.util.find_spec("faster_whisper") is not None
    except (ImportError, ValueError):
        return False


def modele_telecharge() -> bool:
    """Les poids sont-ils déjà sur le disque ?

    Heuristique volontairement lâche sur la disposition interne du cache
    HuggingFace : on cherche un répertoire qui porte le nom du modèle. Se
    tromper ici ne casse rien — au pire l'écran annonce un téléchargement qui
    n'aura pas lieu, ce qui est moins fâcheux que l'inverse : un premier clic
    sur le micro qui part chercher 480 Mo sans prévenir."""
    try:
        return any(MODEL_SIZE in p.name for p in MODEL_DIR.iterdir() if p.is_dir())
    except OSError:
        return False


def available_engines() -> list[dict]:
    """Ce que l'écran affiche pour décider si le micro est cliquable."""
    installe = _faster_whisper_disponible()
    telecharge = modele_telecharge() if installe else False
    out = []
    for info in ENGINES.values():
        hint = None
        if not installe:
            hint = INSTALL_HINT
        elif not telecharge:
            hint = (f"Premier usage : les poids du modèle « {info.model} » "
                    f"(environ 480 Mo) seront téléchargés une seule fois. "
                    f"Cette première dictée sera donc longue.")
        out.append({
            "key": info.key, "label": info.label, "local": info.local,
            "model": info.model, "ready": installe,
            "model_downloaded": telecharge, "hint": hint,
        })
    return out


def _run_worker(cfg: dict, timeout: float) -> dict:
    """Lance le worker, rend son JSON. Seul point de contact avec le natif.

    Un code de sortie négatif ou 139 signifie que le processus a été tué par le
    système — typiquement la violation d'accès d'OpenMP. C'est justement le cas
    qui, sans cette isolation, emportait le serveur entier : ici il ne coûte
    qu'un message d'erreur."""
    if not _faster_whisper_disponible():
        raise TranscriptionError(INSTALL_HINT)

    # Le résultat transite par un FICHIER, pas par stdout : selon
    # l'interpréteur qui porte le serveur (`pythonw.exe` n'a aucune sortie
    # standard), selon ce qu'une bibliothèque native écrit après nous, ou selon
    # l'encodage de la console, le JSON de stdout peut disparaître — le worker
    # sort alors à 0 en paraissant n'avoir rien fait, et le message d'erreur
    # n'apprend rien à personne. C'est exactement ce qui est arrivé.
    fd, out_path = tempfile.mkstemp(suffix=".json", prefix="dictee_")
    os.close(fd)
    cfg = dict(cfg, out=out_path)
    try:
        try:
            proc = subprocess.run(
                [sys.executable, str(WORKER)],
                input=json.dumps(cfg), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise TranscriptionError(
                f"Le moteur de dictée n'a pas répondu en {timeout:.0f} s.") from None
        except OSError as e:
            raise TranscriptionError(
                f"Moteur de dictée impossible à lancer : {e}") from e

        data = {}
        try:
            brut = Path(out_path).read_text(encoding="utf-8").strip()
            if brut:
                data = json.loads(brut)
        except (OSError, ValueError):
            data = {}
        if "text" not in data and not data.get("error"):
            # Repli sur stdout : un worker d'une version antérieure, ou un
            # disque qui refuse le fichier temporaire.
            sortie = (proc.stdout or "").strip()
            for ligne in reversed(sortie.splitlines()):
                try:
                    data = json.loads(ligne)
                    break
                except ValueError:
                    continue

        if data.get("error"):
            raise TranscriptionError(data["error"])
        if proc.returncode != 0 or "text" not in data:
            raise TranscriptionError(_diagnostic(proc))
        return data
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def _diagnostic(proc) -> str:
    """Message d'échec qui porte les preuves.

    « aucun détail » a coûté un aller-retour complet : quand le worker meurt de
    façon inattendue, le seul message utile est ce qu'il a réellement écrit."""
    bouts = [f"Le moteur de dictée s'est arrêté (code {proc.returncode})"]
    err = (proc.stderr or "").strip()
    out = (proc.stdout or "").strip()
    if err:
        bouts.append("stderr : " + " | ".join(err.splitlines()[-3:])[:300])
    if out:
        bouts.append("stdout : " + " | ".join(out.splitlines()[-3:])[:300])
    if not err and not out:
        bouts.append("il n'a rien écrit — vérifiez que le serveur tourne sous "
                     "python.exe et non pythonw.exe")
    return ". ".join(bouts)


def warmup() -> dict:
    """Charge le moteur — et télécharge ses poids si besoin — hors dictée."""
    _run_worker({
        "model_size": MODEL_SIZE, "compute_type": COMPUTE_TYPE,
        "model_dir": str(MODEL_DIR), "audio": None,
    }, WARMUP_TIMEOUT_S)
    return {"ready": True, "model_downloaded": modele_telecharge()}


def _normalise(t: str) -> str:
    return re.sub(r"[^a-z0-9%]+", " ", (t or "").lower()).strip()


def _echo_du_vocabulaire(texte: str) -> bool:
    """Whisper recrache son `initial_prompt` quand il n'a rien entendu.

    C'est le mode de panne le plus vicieux de l'amorçage : sur un micro muet ou
    coupé, la « transcription » est un fragment du vocabulaire de desk — donc
    parfaitement crédible dans le champ de description, et parfaitement
    inventée. Le rendre vide est la seule réponse honnête ; l'écran dira que
    rien n'a été entendu."""
    n = _normalise(texte)
    return len(n) > 15 and n in _normalise(VOCABULAIRE_FR)


def transcribe(audio_path: str | Path, *, engine: str = DEFAULT_ENGINE,
               language: str = "fr") -> dict:
    """Transcrit un fichier audio. Texte vide si rien n'a été entendu.

    Le texte est rendu BRUT, sans reformulation. Faire relire la dictée par un
    modèle de langage produirait une description plus jolie et parfois d'un
    autre produit : c'est à l'utilisateur de corriger dans le champ, où il voit
    ce qu'il corrige."""
    info = ENGINES.get(engine)
    if info is None:
        raise TranscriptionError(
            f"Moteur de dictée inconnu : {engine!r} — valeurs admises : "
            f"{', '.join(ENGINES)}.")

    t0 = time.perf_counter()
    data = _run_worker({
        "model_size": MODEL_SIZE, "compute_type": COMPUTE_TYPE,
        "model_dir": str(MODEL_DIR), "audio": str(audio_path),
        "language": language, "initial_prompt": VOCABULAIRE_FR,
        # Coupe les silences avant transcription : une dictée comporte des
        # pauses de réflexion, et Whisper hallucine volontiers dans le
        # silence — typiquement une formule de politesse jamais prononcée.
        "vad_filter": True,
    }, TIMEOUT_S)

    texte = (data.get("text") or "").strip()
    if _echo_du_vocabulaire(texte):
        texte = ""

    return {
        "text": texte,
        "engine": info.key,
        "model": info.model,
        "language": language,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
