"""Le corpus d'exemples doit rester synchrone avec l'éditeur, et rester juste.

Les 19 scripts de référence servent d'exemples few-shot à l'assistant IA. Un
modèle imite ce qu'on lui montre : lui montrer un script qui ne compile plus, ou
une version périmée de celui que l'utilisateur voit dans l'éditeur, produit des
générations fausses de façon reproductible et inexplicable.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.payscript.catalogue import PRODUCTS
from backend.tests.test_product_catalogue import generated_constats, STRIKE
from backend.app.core.payscript.templates import TEMPLATES, by_group

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "backend" / "scripts" / "sync_payscript_templates.py"
TARGET = ROOT / "backend" / "app" / "core" / "payscript" / "templates.py"

UL = [dict(name="S1", ticker="", ccy="EUR", sigma=0.22, q=0.02, v0=0.0484,
           kappa=2.0, theta=0.0484, xi=0.35, rho_h=-0.70, alpha=0.22, beta=1.0,
           rho=-0.30, nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)]


def test_le_corpus_est_synchrone_avec_le_frontend():
    """Rejoue l'extraction et compare. Un exemple modifié dans l'éditeur sans
    régénération laisserait l'assistant enseigner l'ancienne version."""
    sys.path.insert(0, str(SYNC.parent))
    try:
        import sync_payscript_templates as sync
    finally:
        sys.path.pop(0)
    attendu = sync.build()
    actuel = TARGET.read_text(encoding="utf-8")
    assert actuel == attendu, (
        "Le corpus backend a divergé du fichier JS. Régénérer avec :\n"
        "  .venv\\Scripts\\python.exe backend\\scripts\\sync_payscript_templates.py")


def test_le_corpus_n_est_pas_vide_et_couvre_les_familles():
    assert len(TEMPLATES) >= 15
    familles = by_group()
    # Les familles qui portent les idiomes que le modèle doit savoir écrire.
    for f in ("Autocalls", "Options", "Produits à capital"):
        assert familles.get(f), f"famille absente du corpus : {f}"


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_chaque_exemple_compile(key):
    compiled = parse_script(TEMPLATES[key]["script"])
    assert compiled.events, f"{key} : aucun événement"
    assert any((e.constat_qualifier and all(q == ("last",) for q in e.constat_qualifier)) or e.constat_ref == "MATURITYDATE" for e in compiled.events), (
        f"{key} : pas de constatation terminale — le produit ne se solde jamais")


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_chaque_exemple_price(key):
    """Compiler ne suffit pas : un exemple qui lève à l'exécution ou sort un
    prix absurde enseignerait une idiome cassée au modèle."""
    from backend.app.core.payscript.engine import run_mc
    compiled = resolve_constats(parse_script(TEMPLATES[key]["script"]), generated_constats(PRODUCTS[key], "3Y"), anchor=STRIKE, currency="EUR")
    n = max(1, max((len(e.dates) and max(e.dates)) or 0 for e in compiled.events))
    res = run_mc(compiled, UL, [[1.0]], r=0.03, T_max=max(1.0, n), N=800,
                 model="constant", seed=7, user_params={p.name: {
                     'COUPON': .08, 'M_AC_BAR': 1., 'M_KI_BAR': .6, 'M_CPN_BAR': .8,
                     'M_PDI_BAR': .6, 'M_PUT_STRIKE': .8, 'GEARING': 1.5, 'CAP': 1.5,
                     'PART': 1., 'STRIKE': 1., 'K1': 1., 'K2': 1.2, 'M_KO_BAR': 1.3,
                     'REBATE': .03,
                 }[p.name] for p in compiled.params})
    prix = res["price"] * 100
    assert prix == prix, f"{key} : prix NaN"          # NaN != NaN
    assert -50.0 < prix < 400.0, f"{key} : prix hors de toute plausibilité ({prix:.2f}%)"


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_les_exemples_avec_rappel_declarent_leur_rappel(key):
    """Cohérence interne : un script contenant STOP doit ressortir has_stop, et
    un script sans STOP ne doit pas se déclarer rappelable."""
    src = TEMPLATES[key]["script"]
    compiled = parse_script(src)
    ecrit = any(l.strip().split("#")[0].strip().upper() == "STOP"
                for l in src.splitlines())
    assert compiled.has_stop == ecrit, f"{key} : has_stop={compiled.has_stop}, STOP écrit={ecrit}"


def test_le_corpus_illustre_les_idiomes_cles_du_prompt():
    """Le modèle imite ce qu'il voit. Ces idiomes doivent figurer dans au moins
    un exemple, sinon le prompt les décrit sans jamais les montrer."""
    tous = "\n".join(t["script"] for t in TEMPLATES.values())
    for idiome, quoi in [
        ("STOP", "rappel anticipé"),
        ("INDIC(", "indicatrice (payoff sans IF)"),
        (".last:", "bloc de maturité"),
        ("WORSTOF(Basket.yield)", "worst-of"),
        ("M_", "convention de surveillance M_"),
        ("INDEX", "compteur d'observations"),
    ]:
        assert idiome in tous, f"aucun exemple n'illustre : {quoi} ({idiome})"
