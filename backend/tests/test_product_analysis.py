"""Second avis d'un modèle sur un produit pricé — tout sauf l'appel au modèle.

L'invariant qui porte cette fonctionnalité n'est pas la qualité de la réponse,
qui n'est ni testable ni garantie : c'est que **ce que l'écran montre est ce qui
part**. Le résumé arrive rédigé de l'écran et n'est pas reconstruit ici ;
l'aperçu du prompt sort du même constructeur que l'envoi. Un aperçu qui
divergerait de l'envoi serait pire que pas d'aperçu du tout — l'utilisateur
croirait relire sa demande alors qu'il lirait une fiction.

Le second risque testé est le garde-fou du cadre système : les consignes qui
interdisent au modèle de valider un chiffre ou d'inventer un fait absent du
résumé sont la seule chose qui distingue un second avis d'une hallucination
présentée comme un contrôle. Elles se sont perdues une fois ; qu'un test les
tienne.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.llm import LlmError
from backend.app.services.llm.analysis import (
    CADRE, INTENTIONS, analyse_produit, construire_prompts,
)

RESUME = """# Phoenix Mémoire — 4 sous-jacents

## Payoff
PARAM AC_BAR = 100 %

## Prix
- Prix : 46,17 %
"""


@pytest.fixture
def client():
    return TestClient(app)


# ── L'aperçu ne peut pas mentir sur l'envoi ─────────────────────────

@pytest.mark.parametrize("intention", sorted(INTENTIONS))
def test_l_apercu_est_exactement_ce_qui_part(monkeypatch, intention):
    """Le prompt affiché et le prompt envoyé sont le même objet, caractère pour
    caractère. C'est la raison d'être de `construire_prompts` : deux chemins de
    construction finiraient par diverger sans que rien ne le signale."""
    question = "concentre-toi sur Stellantis"
    envoye = {}

    def _capture(provider, model, system, user, **kw):
        envoye["system"], envoye["user"] = system, user
        return "réponse du modèle"

    monkeypatch.setattr("backend.app.services.llm.analysis.complete", _capture)

    apercu = construire_prompts(RESUME, intention, question)
    analyse_produit(RESUME, intention, question=question)

    assert envoye["system"] == apercu["system"]
    assert envoye["user"] == apercu["user"]


def test_l_apercu_n_appelle_pas_le_modele(monkeypatch, client):
    """Regarder ce qu'on s'apprête à demander ne doit rien coûter : ni jeton, ni
    attente. Sinon personne ne regardera."""
    def _interdit(*a, **kw):
        raise AssertionError("l'aperçu a appelé le modèle")

    monkeypatch.setattr("backend.app.services.llm.analysis.complete", _interdit)

    res = client.post("/api/product/analyse/prompt",
                      json={"resume": RESUME, "intention": "critique"})
    assert res.status_code == 200
    assert res.json()["intention_label"] == INTENTIONS["critique"]["label"]


def test_le_resume_part_tel_quel_sans_reconstruction():
    """Le texte lu à l'écran finit dans le prompt sans retouche. S'il était
    reformaté ici, l'utilisateur validerait un résumé et le modèle en lirait un
    autre."""
    prompts = construire_prompts(RESUME, "analyse")
    assert prompts["user"].endswith(RESUME)
    assert RESUME in prompts["user"]


# ── Le cadre système, qui distingue un avis d'un contrôle ───────────

@pytest.mark.parametrize("garde_fou", [
    # Un LLM ne peut pas recalculer un Monte-Carlo, mais il commentera un prix
    # avec aplomb si on ne le lui interdit pas.
    "ne valides ni ne conteste aucun chiffre",
    # Il a inventé une « faible capitalisation » qui ne figurait nulle part.
    "N'AFFIRME RIEN qui ne figure pas dans le résumé",
    # Il a désigné un vega de 0,03 comme dominant face à un delta de 0,60.
    "ORDRE DE GRANDEUR",
])
def test_le_cadre_porte_ses_garde_fous(garde_fou):
    assert garde_fou in CADRE


def test_toute_intention_herite_du_cadre():
    """Aucune intention ne doit pouvoir s'affranchir du cadre — c'est lui qui
    empêche la réponse de se lire comme une validation."""
    for intention in INTENTIONS:
        q = "une question" if intention == "libre" else ""
        assert construire_prompts(RESUME, intention, q)["system"] == CADRE


def test_la_restructuration_vise_la_reprise_de_valeur():
    """Une restructuration n'est pas un exercice de réduction de sensibilité :
    le détenteur assis sur une note à 46 % cherche un chemin vers le pair."""
    # Les consignes sont rédigées sur plusieurs lignes : chercher une phrase
    # sans replier les blancs testerait la mise en page, pas le contenu.
    consigne = " ".join(INTENTIONS["restructuration"]["consigne"].split())
    assert "dégager de la valeur" in consigne
    # Le modèle a inventé `AT OBS.last.last:`, qui ne parse pas.
    assert "N'invente aucune construction" in consigne


# ── Ce qui doit échouer, et échouer proprement ──────────────────────

@pytest.mark.parametrize("resume, intention, question, motif", [
    ("", "analyse", "", "Résumé vide"),
    ("   \n  ", "analyse", "", "Résumé vide"),
    (RESUME, "inexistante", "", "Intention inconnue"),
    (RESUME, "libre", "", "Question libre"),
    (RESUME, "libre", "   ", "Question libre"),
])
def test_les_demandes_impossibles_sont_refusees(resume, intention, question, motif):
    with pytest.raises(LlmError) as e:
        construire_prompts(resume, intention, question)
    assert motif in str(e.value)


@pytest.mark.parametrize("charge", [
    {"resume": "", "intention": "analyse"},
    {"resume": RESUME, "intention": "inexistante"},
    {"resume": RESUME, "intention": "libre", "question": ""},
])
def test_l_api_refuse_en_422_pas_en_500(client, charge):
    assert client.post("/api/product/analyse/prompt", json=charge).status_code == 422


# ── La précision complète l'intention, elle ne la remplace pas ──────

def test_une_precision_ne_remplace_pas_l_intention():
    """Écrire une précision ne doit pas vider le menu de son sens : la consigne
    d'intention reste, la précision s'y ajoute."""
    prompts = construire_prompts(RESUME, "critique", "regarde le funding")
    assert INTENTIONS["critique"]["consigne"] in prompts["user"]
    assert "regarde le funding" in prompts["user"]


def test_la_question_libre_remplace_bien_la_consigne():
    """Le cas symétrique : en mode libre, il n'y a pas d'autre consigne que la
    question — aucune consigne d'intention ne doit s'y glisser."""
    prompts = construire_prompts(RESUME, "libre", "ce produit est-il défensif ?")
    assert "ce produit est-il défensif ?" in prompts["user"]
    for autre in INTENTIONS:
        if autre != "libre":
            assert INTENTIONS[autre]["consigne"] not in prompts["user"]


# ── La provenance accompagne toujours l'avis ────────────────────────

def test_l_avis_arrive_avec_sa_provenance(monkeypatch):
    """Un texte de modèle qui traîne sans dire d'où il vient finit par se lire
    comme une conclusion validée, six mois plus tard."""
    monkeypatch.setattr("backend.app.services.llm.analysis.complete",
                        lambda *a, **kw: "  un avis  ")
    res = analyse_produit(RESUME, "analyse", provider="ollama", model="llama3")

    assert res["texte"] == "un avis"
    assert res["provider"] == "ollama"
    assert res["model"] == "llama3"
    assert res["intention_label"] == INTENTIONS["analyse"]["label"]
    assert res["generated_at"] and res["elapsed_ms"] >= 0


def test_les_intentions_exposees_sont_celles_qui_existent(client):
    """L'écran ne doit pas pouvoir proposer une intention que le serveur
    refusera ensuite."""
    res = client.get("/api/product/analyse/intentions")
    assert res.status_code == 200
    assert {i["id"] for i in res.json()["intentions"]} == set(INTENTIONS)
