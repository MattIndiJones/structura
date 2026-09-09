"""Dictée de la description produit — la plomberie, pas la qualité d'écoute.

Ce que ces tests couvrent : le registre du moteur, la façon dont l'indisponibilité
est annoncée à l'écran, le garde-fou contre l'écho du vocabulaire, l'insertion des
bornes de taille, et les codes de retour de l'endpoint.

Ce qu'ils ne couvrent PAS, et il faut le dire : la qualité de la transcription.
Un test qui reçoit 200 ne distingue pas un micro qui enregistre du silence d'un
micro qui marche. La seule vérification qui vaut est manuelle — dicter une phrase
contenant « à tout moment » et un pourcentage, et lire ce qui ressort. C'est le
même principe que pour les hypothèses de marché : un test qui ne lit qu'une
valeur ne voit pas un fil débranché.
"""
import ast
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
import backend.app.services.transcription.engines as E
from backend.app.services.transcription import (DEFAULT_ENGINE, ENGINES,
                                                TranscriptionError,
                                                available_engines, transcribe)
from backend.app.services.transcription.vocabulary import VOCABULAIRE_FR


@pytest.fixture
def client():
    return TestClient(app)


# ── Registre ────────────────────────────────────────────────────────

def test_le_moteur_par_defaut_est_local():
    """Décision de conception, la même que pour Ollama côté scripting : à la
    dictée on nomme le client et la contrepartie sans y penser, donc l'audio ne
    sort pas de la machine. Aucun moteur distant n'est branché."""
    assert DEFAULT_ENGINE == "whisper-local"
    assert all(info.local for info in ENGINES.values())


def test_moteur_absent_annonce_comment_l_installer(monkeypatch):
    """L'app doit démarrer sans faster-whisper et l'écran doit pouvoir griser le
    micro en disant pourquoi — plutôt que de laisser cliquer sur un bouton qui
    échouera après l'enregistrement."""
    monkeypatch.setattr(E, "_faster_whisper_disponible", lambda: False)
    (moteur,) = available_engines()
    assert moteur["ready"] is False
    assert "pip install faster-whisper" in moteur["hint"]


def test_poids_absents_previennent_du_telechargement(monkeypatch):
    """480 Mo qui partent au premier clic sans prévenir, c'est une dictée qu'on
    croit plantée."""
    monkeypatch.setattr(E, "_faster_whisper_disponible", lambda: True)
    monkeypatch.setattr(E, "modele_telecharge", lambda: False)
    (moteur,) = available_engines()
    assert moteur["ready"] is True                  # installé, donc cliquable
    assert moteur["model_downloaded"] is False
    assert "télécharg" in moteur["hint"].lower()


def test_moteur_pret_n_affiche_aucun_avertissement(monkeypatch):
    monkeypatch.setattr(E, "_faster_whisper_disponible", lambda: True)
    monkeypatch.setattr(E, "modele_telecharge", lambda: True)
    (moteur,) = available_engines()
    assert moteur["ready"] is True and moteur["hint"] is None


def test_un_moteur_inconnu_est_refuse():
    with pytest.raises(TranscriptionError, match="Moteur de dictée inconnu"):
        transcribe("peu-importe.webm", engine="whisper-cloud")


# ── Écho du vocabulaire ─────────────────────────────────────────────
# Le mode de panne le plus vicieux de l'amorçage : sur un micro muet, Whisper
# recrache son `initial_prompt`. La « transcription » est alors un fragment de
# vocabulaire de desk — parfaitement crédible dans un champ de description, et
# parfaitement inventé.

def test_un_fragment_du_vocabulaire_est_reconnu_comme_echo():
    fragment = "coupon conditionnel, coupon à mémoire, rappel anticipé"
    assert fragment in VOCABULAIRE_FR                # le test suit l'amorce
    assert E._echo_du_vocabulaire(fragment) is True


def test_une_vraie_description_n_est_pas_prise_pour_un_echo():
    """Elle emploie pourtant le même vocabulaire — c'est tout l'enjeu du
    garde-fou : il doit couper l'écho sans couper la dictée."""
    vraie = ("un autocall 3 ans sur le Nikkei, rappel anticipé si l'indice est "
             "au-dessus de 100 %, barrière de protection à 60 % observée à tout moment")
    assert E._echo_du_vocabulaire(vraie) is False


def test_un_echo_ressort_en_texte_vide(monkeypatch):
    """Rien vaut mieux qu'une phrase crédible et inventée : l'écran dira que
    rien n'a été entendu, et l'utilisateur redictera."""
    monkeypatch.setattr(E, "_run_worker", _WorkerBouchon(
        "coupon conditionnel, coupon à mémoire, rappel anticipé"))
    assert transcribe("x.webm")["text"] == ""


def test_une_dictee_normale_remonte_telle_quelle(monkeypatch):
    """Aucune reformulation côté serveur : le texte brut atterrit dans le champ,
    où l'utilisateur voit ce qu'il corrige."""
    dit = "autocall 3 ans, barrière à 60 % observée à tout moment"
    monkeypatch.setattr(E, "_run_worker", _WorkerBouchon(dit))
    out = transcribe("x.webm")
    assert out["text"] == dit
    assert out["engine"] == "whisper-local" and out["language"] == "fr"


def test_le_vocabulaire_est_bien_souffle_au_moteur(monkeypatch):
    """Sans amorçage la dictée rend « auto-call » et perd les signes %. Un test
    qui ne lit que le texte de sortie ne verrait pas l'amorce débranchée."""
    bouchon = _WorkerBouchon("peu importe")
    monkeypatch.setattr(E, "_run_worker", bouchon)
    transcribe("x.webm")
    assert bouchon.cfg["initial_prompt"] == VOCABULAIRE_FR
    # Les silences d'une dictée sont des pauses de réflexion, et Whisper
    # hallucine volontiers dedans.
    assert bouchon.cfg["vad_filter"] is True


# ── Isolation du moteur ─────────────────────────────────────────────

def test_un_worker_qui_meurt_ne_tue_pas_le_serveur(monkeypatch):
    """C'est LA raison d'être du processus séparé.

    ctranslate2 et numpy embarquent chacun un runtime OpenMP ; les deux dans un
    même processus Windows tuaient celui-ci d'une violation d'accès dès le
    chargement du modèle — mesuré, code de sortie 139, et le serveur entier
    partait avec, sans une ligne dans les journaux. Le symptôme côté écran était
    un « Failed to fetch » identique sur la dictée ET sur la génération de
    script, ce qui n'aidait pas à comprendre.

    Isolée, la même mort ne coûte qu'un message d'erreur lisible."""
    class _Mort:
        returncode = -1073741819            # 0xC0000005 : violation d'accès
        stdout = ""
        stderr = ""

    monkeypatch.setattr(E, "_faster_whisper_disponible", lambda: True)
    monkeypatch.setattr(E.subprocess, "run", lambda *a, **k: _Mort())
    with pytest.raises(TranscriptionError, match="s'est arrêté"):
        transcribe("x.webm")


def test_le_worker_ne_depend_pas_du_paquet_app():
    """Le worker est lancé par chemin de fichier, pas comme module : il doit
    donc vivre sans le sys.path du serveur. Un `import app...` qui s'y glisse le
    ferait échouer selon la façon dont le serveur a été lancé."""
    source = (Path(E.__file__).parent / "worker.py").read_text(encoding="utf-8")
    # Sur les nœuds d'import, pas sur le texte : la docstring du worker CITE
    # `import app.main` pour expliquer le crash, et une recherche naïve la
    # prendrait pour une dépendance.
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    assert "app" not in modules
    assert E.WORKER.exists()


# ── Endpoint ────────────────────────────────────────────────────────

def test_l_etat_du_moteur_est_exposé_a_l_ecran(client):
    r = client.get("/api/script/transcribe/engines")
    assert r.status_code == 200
    data = r.json()
    assert data["default"] == "whisper-local"
    assert data["engines"][0]["key"] == "whisper-local"


def test_enregistrement_vide_est_une_erreur_de_requete(client):
    r = client.post("/api/script/transcribe",
                    files={"audio": ("dictee.webm", io.BytesIO(b""), "audio/webm")})
    assert r.status_code == 400


def test_enregistrement_trop_long_est_refuse_avant_transcription(client):
    """Un onglet resté à enregistrer ne doit pas bloquer une requête pendant des
    minutes."""
    gros = b"\0" * ((E.MAX_UPLOAD_MB + 1) * 1024 * 1024)
    r = client.post("/api/script/transcribe",
                    files={"audio": ("dictee.webm", io.BytesIO(gros), "audio/webm")})
    assert r.status_code == 413


def test_un_moteur_en_panne_est_un_502_lisible(client, monkeypatch):
    """502 comme pour l'assistant : c'est le moteur qui est en cause, pas la
    requête, et le message part déjà rédigé pour l'utilisateur."""
    def _tombe(cfg, timeout):
        raise TranscriptionError(E.INSTALL_HINT)
    monkeypatch.setattr(E, "_run_worker", _tombe)
    r = client.post("/api/script/transcribe",
                    files={"audio": ("dictee.webm", io.BytesIO(b"xx"), "audio/webm")})
    assert r.status_code == 502
    assert "pip install faster-whisper" in r.json()["detail"]


class _WorkerBouchon:
    """Whisper est hors du périmètre d'un test unitaire — lent, non déterministe,
    et il tourne de toute façon dans un autre processus. On garde la
    configuration qu'il aurait reçue, seule chose vérifiable ici."""

    def __init__(self, texte):
        self._texte = texte
        self.cfg = None

    def __call__(self, cfg, timeout):
        self.cfg = cfg
        return {"text": self._texte}
