"""Transcription dans un processus séparé — et pourquoi elle ne peut pas être ailleurs.

ctranslate2, le moteur de faster-whisper, embarque son propre runtime OpenMP
(`libiomp5md.dll`). numpy et scipy en ont déjà chargé un quand le serveur
démarre. Deux runtimes OpenMP dans le même processus Windows ne cohabitent pas :
le chargement du modèle part en violation d'accès, le processus meurt sur place,
sans exception Python et donc sans trace. Mesuré : `import app.main` puis
chargement du modèle = code de sortie 139, alors que le même chargement dans un
processus neuf passe sans rien dire.

Il existe une variable d'environnement qui fait taire le conflit
(`KMP_DUPLICATE_LIB_OK`), et sa propre documentation prévient qu'elle peut
« produire silencieusement des résultats incorrects ». Sur le processus qui
porte le moteur Monte-Carlo, un résultat faux et muet est précisément ce qu'on
ne veut pas — c'est la même règle que partout ailleurs ici : mieux vaut une
panne qui se voit qu'un chiffre faux qui ne se signale pas.

D'où ce module, exécuté par `subprocess` et RIEN d'autre. Il n'importe pas le
paquet `app` : aucune dépendance au sys.path du serveur, donc rien à ajuster
selon la façon dont il a été lancé. Il lit sa configuration en JSON sur stdin et
rend un JSON sur stdout.

Le prix payé : le modèle est rechargé à chaque dictée, environ 2 s pour `small`
en int8. Si cela devenait gênant, l'étape suivante est un worker persistant qui
garde le modèle en mémoire et lit ses demandes sur un tube — même isolation,
sans le rechargement. On ne l'a pas fait tant que le coût reste sous le temps de
transcription lui-même.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_cfg: dict = {}


def rendre(payload: dict) -> None:
    """Écrit le résultat dans le fichier demandé, et sur stdout par commodité.

    Le fichier est la voie qui fait foi. stdout paraissait suffisant : il ne
    l'est pas. Selon l'interpréteur qui lance le worker (`pythonw.exe` n'a pas
    de sortie standard du tout), selon ce qu'une bibliothèque native décide
    d'écrire après nous, ou selon l'encodage de la console, le JSON peut
    disparaître ou se retrouver noyé — et le worker sort alors à 0 en paraissant
    n'avoir rien fait. Un fichier ne dépend d'aucun de ces aléas.
    """
    chemin = _cfg.get("out")
    if chemin:
        try:
            Path(chemin).write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass
    try:
        print(json.dumps(payload))
    except Exception:                                       # pragma: no cover
        pass


def main() -> int:
    global _cfg
    try:
        _cfg = json.loads(sys.stdin.read())
    except Exception as e:                                  # pragma: no cover
        print(json.dumps({"error": f"Configuration illisible : {e}"}))
        return 2
    cfg = _cfg

    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        rendre({"error": f"faster-whisper absent : {e}"})
        return 3

    try:
        model = WhisperModel(
            cfg["model_size"],
            device="cpu",
            compute_type=cfg["compute_type"],
            download_root=cfg["model_dir"],
        )
    except Exception as e:
        rendre({"error": f"Chargement du modèle impossible : {e}"})
        return 4

    # Mode préparation : charger (donc télécharger si besoin) et s'arrêter là.
    # C'est ce que fait la route /prepare, pour que les ~480 Mo du premier usage
    # ne partent jamais au milieu d'une dictée.
    if not cfg.get("audio"):
        rendre({"text": "", "warmed": True})
        return 0

    try:
        segments, _ = model.transcribe(
            cfg["audio"],
            language=cfg.get("language", "fr"),
            initial_prompt=cfg.get("initial_prompt") or None,
            vad_filter=bool(cfg.get("vad_filter", True)),
        )
        texte = " ".join(s.text.strip() for s in segments).strip()
    except Exception as e:
        rendre({"error": f"Échec de la transcription : {e}"})
        return 5

    rendre({"text": texte})
    return 0


if __name__ == "__main__":
    sys.exit(main())
