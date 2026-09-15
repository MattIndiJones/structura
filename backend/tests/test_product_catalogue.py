"""Le catalogue des « Modèles de produits » : des fiches qui tiennent debout.

Une fiche ouvre le Pricer complété — script générique, sous-jacents, calendriers
générés depuis la date de strike. Ajouter un payoff, c'est ajouter une fiche et
passer ces tests, sans toucher aux écrans (décision M10 du 14/09/2026). Ils
vérifient donc tout ce que l'écran suppose sans le contrôler : la fiche compile,
elle price sur un calendrier généré court, elle possède une constatation
terminale, et ses bornes restent dans ce que le module sait proposer.

Pricing volontairement léger — 300 chemins sur le ténor le plus court : on
cherche un script qui lève ou un prix absurde, pas une précision.
"""
import re
import sys
from datetime import date
from pathlib import Path

import pytest
from dateutil.relativedelta import relativedelta

from backend.app.core.payscript.catalogue import FAMILIES, PRODUCTS, TENORS, by_family
from backend.app.core.payscript.parser import parse_script, resolve_constats

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "backend" / "scripts" / "sync_product_catalogue.py"
TARGET = ROOT / "backend" / "app" / "core" / "payscript" / "catalogue.py"

# M9 : les ténors que le module propose, filtrés ensuite par fiche.
TENORS_M9 = ["6M", "1Y", "18M", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y"]
ROLES = {"observations", "maturity", "strike_window"}
STRIKE = date(2026, 9, 14)
UL = dict(name="S1", ticker="", ccy="EUR", sigma=0.22, q=0.02, v0=0.0484,
          kappa=2.0, theta=0.0484, xi=0.35, rho_h=-0.70, alpha=0.22, beta=1.0,
          rho=-0.30, nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)


def generated_constats(product: dict, tenor: str, strike: date = STRIKE) -> dict:
    """Les valeurs de CONSTAT que le module écrit dans le Pricer, sous la forme
    que la requête de pricing envoie : échéancier du strike à strike + ténor,
    roll ancré sur le strike, sans convention de jour ouvré ; date unique à
    maturité ; fenêtre de départ au strike."""
    maturity = strike + relativedelta(months=TENORS[tenor]["months"])
    values = {}
    for name, spec in product["constats"].items():
        role = spec["role"]
        if role == "observations":
            value = {"start_date": strike.isoformat(), "end_date": maturity.isoformat(),
                     "roll_date": strike.isoformat(), "frequency": spec["frequency"],
                     "stub": "short_last"}
            for key in ("window_length", "window_frequency"):
                if spec.get(key):
                    value[key] = spec[key]
        elif role == "maturity":
            value = maturity.isoformat()
            if spec.get("window_length"):
                value = {"date": maturity.isoformat(), "window_length": spec["window_length"],
                         "window_frequency": spec.get("window_frequency", "1D")}
        else:
            value = {"date": strike.isoformat(), "window_length": spec["window_length"],
                     "window_frequency": spec.get("window_frequency", "1D")}
        values[name] = value
    return values


def test_la_copie_serveur_est_synchrone_avec_le_catalogue():
    sys.path.insert(0, str(SYNC.parent))
    try:
        import sync_product_catalogue as sync
    finally:
        sys.path.pop(0)
    assert TARGET.read_text(encoding="utf-8") == sync.build(), (
        "La copie serveur du catalogue a divergé du JSON. Régénérer avec :\n"
        "  .venv\\Scripts\\python.exe backend\\scripts\\sync_product_catalogue.py")


def test_le_catalogue_couvre_les_familles_et_les_tenors_m9():
    assert list(TENORS) == TENORS_M9
    assert set(by_family()) == set(FAMILIES)
    assert len(PRODUCTS) >= 15


@pytest.mark.parametrize("key", list(PRODUCTS))
def test_chaque_fiche_est_generique_et_bornee(key):
    product = PRODUCTS[key]
    assert product["family"] in FAMILIES
    # Un libellé sans durée ni nombre d'actifs : le ténor et le panier se
    # choisissent à l'ouverture, un « 3 ans » ou « 2 actifs » y mentirait.
    assert not re.search(r"\d", product["label"]), f"{key} : libellé daté ou dénombré"
    assert product["description"].strip()
    bounds = product["underlyings"]
    assert 1 <= bounds["min"] <= bounds["max"] <= 12
    assert product["tenors"] and all(t in TENORS_M9 for t in product["tenors"])
    assert product["tenors"] == [t for t in TENORS_M9 if t in product["tenors"]], (
        f"{key} : ténors hors de l'ordre M9")


@pytest.mark.parametrize("key", list(PRODUCTS))
def test_chaque_fiche_compile_et_declare_ses_roles(key):
    product = PRODUCTS[key]
    compiled = parse_script(product["script"])
    assert compiled.events, f"{key} : aucun événement"
    declared = {c.name: c for c in compiled.constats}
    assert set(declared) == set(product["constats"]), (
        f"{key} : CONSTAT déclarés {sorted(declared)} ≠ rôles {sorted(product['constats'])}")
    for name, spec in product["constats"].items():
        assert spec["role"] in ROLES, f"{key} : rôle inconnu {spec['role']!r}"
        kind = declared[name].kind
        if spec["role"] == "observations":
            assert kind in ("schedule", "nested_schedule") and spec.get("frequency")
        else:
            assert kind == "single", f"{key} : {name} doit être une date unique"
        assert (spec["role"] == "strike_window") == (name == "STRIKE_FIX")
        if declared[name].reduction and declared[name].window_scope != "period":
            assert spec.get("window_length"), f"{key} : fenêtre de {name} sans longueur"
    # Une constatation terminale : sans elle, rien ne date la maturité.
    assert any(spec["role"] in ("observations", "maturity")
               for spec in product["constats"].values()), f"{key} : aucune constatation terminale"
    # Aucune date écrite dans le script : elles viennent du Pricer.
    assert not any(e.dates for e in compiled.events), f"{key} : dates AT écrites en dur"


@pytest.mark.parametrize("key", list(PRODUCTS))
def test_chaque_fiche_price_sur_un_calendrier_genere(key):
    from backend.app.core.payscript.engine import run_mc
    product = PRODUCTS[key]
    tenor = product["tenors"][0]
    n = product["underlyings"]["min"]
    compiled = resolve_constats(parse_script(product["script"]),
                                generated_constats(product, tenor),
                                anchor=STRIKE, currency="EUR")
    maturity = (STRIKE + relativedelta(months=TENORS[tenor]["months"]) - STRIKE).days / 365.25
    last = max(d for e in compiled.events for d in e.dates)
    assert last == pytest.approx(maturity, abs=1e-6), (
        f"{key} : la dernière constatation ({last:.4f}) n'est pas la maturité ({maturity:.4f})")
    corr = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    res = run_mc(compiled, [dict(UL, name=f"S{i + 1}") for i in range(n)], corr,
                 r=0.03, T_max=maturity, N=300, model="constant", seed=7)
    price = res["price"] * 100
    assert price == price, f"{key} : prix NaN"
    assert -50.0 < price < 400.0, f"{key} : prix hors de toute plausibilité ({price:.2f}%)"


def test_le_calendrier_genere_part_du_strike_et_finit_a_maturite():
    """Le cas de référence du module : un Athena 3 ans annuel, trois
    constatations aux anniversaires du strike, la dernière à maturité."""
    product = PRODUCTS["autocall_athena"]
    compiled = resolve_constats(parse_script(product["script"]),
                                generated_constats(product, "3Y"),
                                anchor=STRIKE, currency="EUR")
    event = next(e for e in compiled.events if e.constat_ref == "OBSERVATIONS"
                 and not e.constat_qualifier)
    assert [round(d * 365.25) for d in event.dates] == [
        (date(2027, 9, 14) - STRIKE).days, (date(2028, 9, 14) - STRIKE).days,
        (date(2029, 9, 14) - STRIKE).days]
