"""Assistant de scripting IA — tout ce qui se teste sans appeler un modèle.

Le modèle est hors du périmètre d'un test unitaire : il est lent, non
déterministe et externe. Tout le reste — le prompt qu'on lui envoie,
l'assainissement de ce qu'il renvoie, et surtout la fiche de contrôle qui décide
si son script est relisible — se teste, et c'est là qu'est le risque.

Le cas dangereux n'est jamais le script qui ne compile pas : c'est celui qui
compile, price, et décrit un autre produit.
"""
import re

import pytest

from backend.app.core.payscript.parser import parse_script, effective_T_max
from backend.app.services.llm.examples_extra import EXTRA_EXAMPLES, all_examples
from backend.app.services.llm.prompt import (
    build_system_prompt, build_user_prompt, build_repair_prompt,
    select_examples, SCRIPT_MARK, EXPLAIN_MARK, _REQUIRED_IDIOMS,
)
from backend.app.services.llm.providers import PROVIDERS, DEFAULT_PROVIDER, available_providers
from backend.app.services.llm.validate import split_response, validate

UL = [dict(name="S1", ticker="", ccy="EUR", sigma=0.22, q=0.02, v0=0.0484,
           kappa=2.0, theta=0.0484, xi=0.35, rho_h=-0.70, alpha=0.22, beta=1.0,
           rho=-0.30, nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)]
C1 = [[1.0]]


def _validate(reponse, description="", uls=None, T=3.0):
    return validate(reponse, description=description, underlyings=uls or UL,
                    corr=C1, r=0.03, T=T, user_params={})


def _levels(v):
    return {c.label: c.level for c in v.checks}


# ── Exemples complémentaires ────────────────────────────────────────

@pytest.mark.parametrize("key", sorted(EXTRA_EXAMPLES))
def test_les_exemples_complementaires_compilent_et_pricent(key):
    """Ils ne passent pas par la bibliothèque de l'éditeur, donc pas par ses
    tests. Un exemple cassé enseignerait une idiome fausse au modèle."""
    from backend.app.core.payscript.engine import run_mc
    compiled = parse_script(EXTRA_EXAMPLES[key]["script"])
    T = effective_T_max(compiled, 1.0)
    prix = run_mc(compiled, UL, C1, r=0.03, T_max=T, N=2000, model="constant",
                  seed=7)["price"] * 100
    assert 40.0 < prix < 200.0, f"{key} : {prix:.2f} %"


def test_le_prompt_montre_tout_idiome_qu_il_impose():
    """La bibliothèque de l'éditeur n'illustre NI le coupon mémoire NI les
    PARAM() — vérifié : 0 exemple sur 16. Une règle énoncée sans exemple est une
    règle que le modèle applique mal ; c'est la raison d'être d'examples_extra."""
    lib = all_examples()
    for idiome in _REQUIRED_IDIOMS:
        porteurs = [k for k, t in lib.items() if idiome in t.get("idioms", ())]
        assert porteurs, f"aucun exemple ne porte l'idiome imposé : {idiome}"
    for demande in ("autocall phoenix", "call spread", "shark note",
                    "je veux un produit", ""):
        choisis = select_examples(demande)
        for idiome in _REQUIRED_IDIOMS:
            assert any(idiome in lib[k].get("idioms", ()) for k in choisis), (
                f"demande {demande!r} : aucun exemple n'illustre {idiome}")


def test_la_selection_est_pertinente_et_bornee():
    assert "call_spread" in select_examples("un call spread 100/120")
    assert any("shark" in k for k in select_examples("shark note avec rebate"))
    assert any("autocall" in k or "phoenix" in k
               for k in select_examples("autocall athena 3 ans"))
    for demande in ("", "autocall", "call", "n'importe quoi"):
        assert len(select_examples(demande)) <= 6


# ── Prompt ──────────────────────────────────────────────────────────

def test_le_prompt_systeme_porte_la_reference_et_le_contrat_de_sortie():
    p = build_system_prompt("autocall phoenix 3 ans")
    # La grammaire vient du fichier de référence, pas d'une copie.
    assert "Référence du langage PayScript" in p or "RÉFÉRENCE DU LANGAGE" in p
    assert "WOF_MIN" in p and "STOP" in p and "AT MATURITY" in p
    assert SCRIPT_MARK in p and EXPLAIN_MARK in p
    # Les règles qui protègent du cas « compile mais faux ».
    for regle in ("STOP", "WOF_MIN", "nominal deux fois", "SET MEMO = INDEX"):
        assert regle in p, f"règle absente du prompt : {regle}"
    assert len(p) > 5000


def test_le_prompt_utilisateur_transmet_le_contexte_connu():
    """Sans le contexte, le modèle invente un calendrier et un panier."""
    u = build_user_prompt("un autocall", n_underlyings=3, maturity=5.0)
    assert "3" in u and "5" in u
    assert "un autocall" in u


def test_le_prompt_de_reparation_porte_l_erreur_exacte():
    r = build_repair_prompt("PARAM X = 1", 'Ligne 3: instruction inconnue: "FOO"')
    assert 'Ligne 3' in r and "FOO" in r and "PARAM X = 1" in r


# ── Assainissement ──────────────────────────────────────────────────

@pytest.mark.parametrize("brut", [
    "```payscript\nPARAM A = 1.0\nAT MATURITY:\n  PAY A\n```",
    "Voici le script :\n```\nPARAM A = 1.0\nAT MATURITY:\n  PAY A\n```\nBonne journée !",
    f"{SCRIPT_MARK}\nPARAM A = 1.0\nAT MATURITY:\n  PAY A\n{EXPLAIN_MARK}\nPaie A.",
    f"{SCRIPT_MARK}\n```\nPARAM A = 1.0\nAT MATURITY:\n  PAY A\n```\n{EXPLAIN_MARK}\nPaie A.",
    "Bien sûr ! Le produit se traduit ainsi.\n\nPARAM A = 1.0\nAT MATURITY:\n  PAY A",
    "PARAM A = 1.0\nAT MATURITY:\n  PAY A",
])
def test_les_reponses_decorees_sont_nettoyees(brut):
    """Tous les modèles ajoutent des balises et de la prose malgré la consigne.
    Refuser ferait échouer un script correct pour une décoration."""
    script, _ = split_response(brut)
    assert script.startswith("PARAM A")
    assert "```" not in script
    assert "Voici" not in script and "Bien sûr" not in script
    parse_script(script)


def test_l_explication_est_recuperee_quand_elle_existe():
    _, expl = split_response(
        f"{SCRIPT_MARK}\nAT MATURITY:\n  PAY 1\n{EXPLAIN_MARK}\nRembourse le pair.")
    assert expl == "Rembourse le pair."


def test_une_reponse_vide_ne_leve_pas():
    v = _validate("")
    assert v.ok is False and v.parse_error


# ── Fiche de contrôle : le cas « compile mais faux » ─────────────────

_AUTOCALL_OK = f"""{SCRIPT_MARK}
PARAM COUPON = 8%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 60%

AT 1, 2, 3:
  IF WOF >= M_AC_BAR:
    PAY 1 + COUPON * INDEX "rappel"
    STOP

AT MATURITY:
  IF WOF_MIN >= M_KI_BAR:
    PAY 1
  ELSE:
    PAY WOF
{EXPLAIN_MARK}
Autocall 3 ans, coupon 8 % cumulé, protection à 60 % observée en continu.
"""


def test_un_bon_script_ne_leve_aucune_alerte():
    v = _validate(_AUTOCALL_OK,
                  "autocall 3 ans, coupon 8%, barrière de protection 60% "
                  "franchie à tout moment")
    assert v.ok and v.has_stop
    assert v.explanation.startswith("Autocall")
    assert "attention" not in _levels(v).values()
    assert 55 < v.price_pct < 165


def test_un_rappel_sans_stop_est_signale():
    """Le défaut le plus fréquent, et parfaitement muet : le produit continue
    d'observer après avoir été rappelé, et encaisse aussi à maturité."""
    sans_stop = _AUTOCALL_OK.replace("    STOP\n", "")
    v = _validate(sans_stop, "autocall 3 ans avec rappel anticipé")
    assert v.ok and not v.has_stop
    assert _levels(v)["Rappel anticipé"] == "attention"
    # Et le prix le trahit : le nominal est versé plusieurs fois.
    assert v.price_pct > 165
    assert _levels(v)["Pricing de contrôle"] == "attention"


def test_une_barriere_europeenne_la_ou_l_americaine_est_demandee_est_signalee():
    """WOF au lieu de WOF_MIN : plusieurs points de nominal, aucun symptôme."""
    europeenne = _AUTOCALL_OK.replace("WOF_MIN >=", "WOF >=")
    v = _validate(europeenne,
                  "autocall avec barrière de protection franchie à tout moment")
    assert v.ok
    assert _levels(v)["Nature de la barrière"] == "attention"
    # Et l'inverse ne doit pas crier au loup.
    v2 = _validate(europeenne, "autocall avec barrière constatée à maturité")
    assert _levels(v2)["Nature de la barrière"] == "info"


def test_un_coupon_memoire_sans_memoire_est_signale():
    script = f"""{SCRIPT_MARK}
PARAM COUPON = 8%
PARAM M_CPN_BAR = 70%
AT 1, 2, 3:
  IF WOF >= M_CPN_BAR:
    PAY COUPON
AT MATURITY:
  PAY 1
{EXPLAIN_MARK}
x
"""
    v = _validate(script, "phoenix avec coupon à mémoire")
    assert _levels(v)["Coupon à mémoire"] == "attention"


def test_un_parametre_jamais_lu_est_signale():
    v = _validate(_AUTOCALL_OK.replace("PARAM COUPON = 8%",
                                       "PARAM COUPON = 8%\nPARAM ORPHELIN = 5%"),
                  "autocall")
    assert _levels(v)["Paramètres inutilisés"] == "attention"
    assert "ORPHELIN" in next(c.detail for c in v.checks
                              if c.label == "Paramètres inutilisés")


def test_un_indice_hors_du_panier_est_signale():
    script = f"{SCRIPT_MARK}\nAT MATURITY:\n  PAY S[3]\n{EXPLAIN_MARK}\nx"
    v = _validate(script, "produit sur un actif")          # 1 sous-jacent configuré
    assert _levels(v)["Sous-jacents référencés"] == "attention"


def test_un_bloc_de_maturite_absent_est_signale():
    script = f"{SCRIPT_MARK}\nAT 1:\n  PAY 1\n{EXPLAIN_MARK}\nx"
    v = _validate(script, "produit 1 an")
    assert _levels(v)["Bloc de maturité"] == "attention"


def test_un_script_qui_ne_compile_pas_remonte_l_erreur_du_parser():
    """C'est ce message, avec son numéro de ligne, qui repart au modèle pour la
    tentative de réparation."""
    v = _validate(f"{SCRIPT_MARK}\nPARAM FLOOR = 1.0\nAT MATURITY:\n  PAY FLOOR\n")
    assert not v.ok
    assert "mot réservé" in v.parse_error and "FLOOR" in v.parse_error


def test_un_script_a_constat_ne_declenche_pas_de_pricing():
    """Ses dates vivent dans l'interface : le pricer ne peut pas le résoudre
    seul, et échouer ici serait un faux négatif."""
    script = (f"{SCRIPT_MARK}\nCONSTAT() Obs\nAT Obs:\n  PAY 0.02\n"
              f"AT MATURITY:\n  PAY 1\n")
    v = _validate(script, "produit à calendrier")
    assert v.ok
    assert v.price_pct is None
    assert _levels(v)["Pricing de contrôle"] == "info"


def test_une_option_n_est_pas_jugee_comme_une_note():
    """Une option vaut légitimement 12 % du nominal. Le contrôle de pair ne
    s'applique qu'aux produits qui remboursent un nominal."""
    script = (f"{SCRIPT_MARK}\nPARAM K = 100%\nAT MATURITY:\n"
              f"  PAY MAX(WOF - K, 0)\n{EXPLAIN_MARK}\nCall.")
    v = _validate(script, "un call vanille strike 100%", T=1.0)
    assert v.ok and v.price_pct < 55
    assert _levels(v)["Pricing de contrôle"] == "ok"


# ── Fournisseurs ────────────────────────────────────────────────────

def test_ollama_est_le_defaut_et_ne_demande_aucune_cle():
    """Décision de conception : une description de produit envoyée à un tiers,
    c'est une idée de structuration qui sort du desk."""
    assert DEFAULT_PROVIDER == "ollama"
    assert PROVIDERS["ollama"].needs_key is False
    assert PROVIDERS["openai"].needs_key and PROVIDERS["anthropic"].needs_key


def test_les_moteurs_sont_annonces_avec_leur_disponibilite(monkeypatch):
    """Sonde d'Ollama simulée : sans cela le test dépendrait du fait qu'Ollama
    tourne ou non sur la machine de build."""
    import backend.app.services.llm.providers as P
    monkeypatch.setattr(P.httpx, "get", lambda *a, **k: _Rep(
        {"models": [{"name": "mistral:latest"}]}))
    provs = {p["key"]: p for p in available_providers()}
    assert set(provs) == {"ollama", "openai", "anthropic"}
    assert provs["ollama"]["ready"] is True
    for p in provs.values():
        # Ne jamais proposer par défaut un modèle absent de la liste affichée.
        assert p["default_model"] in p["models"]
        if not p["ready"]:
            assert p["hint"]


def test_un_moteur_inconnu_est_refuse():
    from backend.app.services.llm.providers import complete, LlmError
    with pytest.raises(LlmError, match="Moteur inconnu"):
        complete("gemini", None, "s", "u")


# ── Découverte des modèles Ollama installés ─────────────────────────

class _Rep:
    def __init__(self, payload, code=200):
        self._p, self.status_code = payload, code

    def json(self):
        return self._p


def test_le_selecteur_liste_les_modeles_reellement_installes(monkeypatch):
    """La liste figée de PROVIDERS faisait choisir un modèle absent de la
    machine, et l'échec n'arrivait qu'APRÈS une génération lancée pour rien
    (« Modèle inconnu d'Ollama »). Un sélecteur doit lister ce qui existe."""
    import backend.app.services.llm.providers as P
    monkeypatch.setattr(P.httpx, "get", lambda *a, **k: _Rep(
        {"models": [{"name": "mistral:latest"}, {"name": "gemma3:4b"}]}))
    ollama = next(p for p in P.available_providers() if p["key"] == "ollama")
    assert ollama["ready"] is True
    assert ollama["models"] == ["gemma3:4b", "mistral:latest"]
    # Le défaut recommandé n'étant pas installé, on retombe sur un modèle présent.
    assert ollama["default_model"] in ollama["models"]
    assert ollama["recommended"] == P.PROVIDERS["ollama"].default_model


def test_le_modele_recommande_est_retenu_s_il_est_installe(monkeypatch):
    import backend.app.services.llm.providers as P
    reco = P.PROVIDERS["ollama"].default_model
    monkeypatch.setattr(P.httpx, "get", lambda *a, **k: _Rep(
        {"models": [{"name": "gemma3:4b"}, {"name": reco}]}))
    ollama = next(p for p in P.available_providers() if p["key"] == "ollama")
    assert ollama["default_model"] == reco


@pytest.mark.parametrize("reponse,motif", [
    (None, "ne répond pas"),                      # Ollama éteint
    ({"models": []}, "aucun modèle n'est installé"),
])
def test_ollama_indisponible_est_annonce_avec_la_marche_a_suivre(monkeypatch, reponse, motif):
    import backend.app.services.llm.providers as P

    def _get(*a, **k):
        if reponse is None:
            raise P.httpx.ConnectError("refused")
        return _Rep(reponse)

    monkeypatch.setattr(P.httpx, "get", _get)
    ollama = next(p for p in P.available_providers() if p["key"] == "ollama")
    assert ollama["ready"] is False
    assert motif in ollama["hint"]


def test_ollama_models_ne_leve_jamais(monkeypatch):
    """Sonder un service local ne doit pas pouvoir faire tomber la page."""
    import backend.app.services.llm.providers as P
    for panne in (lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
                  lambda *a, **k: _Rep({}, code=500),
                  lambda *a, **k: _Rep({"models": "pas une liste"})):
        monkeypatch.setattr(P.httpx, "get", panne)
        assert P.ollama_models() in (None, [])


# ── Prompt consultable ──────────────────────────────────────────────

def test_le_prompt_est_consultable_sans_appeler_de_modele():
    """Les exemples joints dépendent de la demande : sans pouvoir les lire, on
    ne peut ni comprendre une génération ratée, ni ajuster sa description."""
    from backend.app.services.llm import preview_prompt
    p = preview_prompt("un autocall 3 ans barrière PDI -40%", n_underlyings=1,
                       maturity=3.0)
    assert set(p) == {"system", "user", "examples", "chars", "approx_tokens"}
    assert p["chars"] == len(p["system"]) + len(p["user"])
    assert p["approx_tokens"] > 500
    assert p["examples"] and all(isinstance(e, str) for e in p["examples"])
    # Le prompt consulté doit être CELUI qui partirait, pas une approximation.
    assert p["system"] == build_system_prompt("un autocall 3 ans barrière PDI -40%")


def test_le_prompt_change_avec_la_description():
    from backend.app.services.llm import preview_prompt
    a = preview_prompt("un call spread")
    b = preview_prompt("un shark note capital garanti")
    assert a["examples"] != b["examples"]
    assert a["system"] != b["system"]
