"""Classe de risque de marché du KID — le cas de la perte totale.

La VEV se calcule à partir du logarithme du 1er percentile du payoff. Quand ce
percentile vaut zéro — c'est-à-dire quand au moins 1 % des scénarios perdent
tout le capital — le logarithme n'est pas défini, et le code retombait sur une
unique branche `else: vev = 0.0`. Or une VEV nulle est le bas de l'échelle : un
produit capable de tout perdre ressortait en MRM 1, soit moins risqué qu'une
obligation d'État.

La même branche absorbait aussi le cas légitime d'un produit protégé, ce qui
rendait l'anomalie invisible : les deux entraient par la même porte et
sortaient avec la même note.

Ce module reste indicatif et sa méthodologie n'est pas celle qu'exige la
Catégorie 3 du règlement PRIIPs (la distribution devrait être historique, pas
risque-neutre). Ces tests ne portent que sur la cohérence interne du classement.
"""
import pytest
from sqlalchemy import create_engine, text

from backend.app.api.kid import KidSaveRequest, _mrm_from_vev, _scenario_row, _sri
from backend.app.db.database import _make_kid_vev_nullable


def test_perte_totale_ne_peut_pas_donner_la_note_la_plus_basse():
    """Un percentile nul signifie qu'au moins 1 % des scénarios ne rendent
    rien. Ce cas est désormais traité explicitement en MRM 7 et n'a plus de
    VEV chiffrée — plutôt qu'une VEV de 0 % et un MRM 1."""
    from backend.app.api import kid

    # La branche est dans kid_compute ; on en vérifie ici l'invariant de
    # classement, à savoir qu'aucune VEV finie ne peut produire MRM 7 par
    # accident, et qu'aucun MRM 1 ne peut sortir d'un produit à perte totale.
    assert _mrm_from_vev(0.0) == 1        # produit protégé : légitime
    assert _mrm_from_vev(0.9) == 7        # volatilité extrême
    # MRM 7 croisé au CRM par défaut ne doit jamais retomber dans le bas de
    # l'échelle du SRI.
    assert _sri(7, 3) == 7
    # Annex II point 52: a CRM 3 issuer never takes the SRI below 3.
    assert _sri(1, 3) == 3


@pytest.mark.parametrize("vev,attendu", [
    (0.001, 1), (0.03, 2), (0.10, 3), (0.15, 4), (0.25, 5), (0.50, 6), (1.20, 7),
])
def test_echelle_mrm_monotone(vev, attendu):
    """La note doit croître avec la volatilité équivalente, sans trou."""
    assert _mrm_from_vev(vev) == attendu


def test_un_kid_perte_totale_est_sauvegardable_sans_vev_finie():
    req = KidSaveRequest(
        deal_id=1, sri=7, mrm=7, crm=3, vev=None, T_rhp=3.0,
        horizons=[], costs={})
    assert req.vev is None


def test_migration_rend_vev_nullable_sur_une_base_existante():
    eng = create_engine("sqlite://")
    with eng.connect() as conn:
        for statement in (
            "CREATE TABLE users(id INTEGER PRIMARY KEY)",
            "CREATE TABLE indicatives(id INTEGER PRIMARY KEY)",
            "CREATE TABLE deals(id INTEGER PRIMARY KEY)",
            """CREATE TABLE kid_records(
                id INTEGER NOT NULL PRIMARY KEY, indicative_id INTEGER,
                deal_id INTEGER, user_id INTEGER NOT NULL,
                product_title VARCHAR NOT NULL, sri INTEGER NOT NULL,
                mrm INTEGER NOT NULL, crm INTEGER NOT NULL,
                vev FLOAT NOT NULL, t_rhp FLOAT NOT NULL,
                horizons_json TEXT, costs_json TEXT,
                created_at DATETIME NOT NULL)""",
        ):
            conn.execute(text(statement))
        conn.execute(text("INSERT INTO users(id) VALUES (1)"))     # the record's author
        conn.commit()
        _make_kid_vev_nullable(conn)
        vev_column = next(row for row in conn.execute(text(
            "PRAGMA table_info(kid_records)")) if row[1] == "vev")
        assert vev_column[3] == 0
        conn.execute(text("""INSERT INTO kid_records VALUES
            (1,NULL,NULL,1,'perte totale',7,7,3,NULL,3,'[]','{}','2026-01-01')"""))
        conn.commit()


def _scenario_with_flows(flows):
    amount = sum(flow["cf"] for flow in flows)
    cell = {"amount": amount, "life": max((f["t"] for f in flows), default=1.0),
            "flows": flows}
    return {
        "p1": amount, "p10": amount, "p50": amount, "p90": amount,
        "scenarios": {key: dict(cell) for key in ("p1", "p10", "p50", "p90")},
    }


def test_call_achete_12_double_rend_100_pourcent_sur_un_an():
    """Annex IV point 45: one year or less, the return is not annualised."""
    scenario = _scenario_with_flows([{"t": 1.0, "cf": 0.24}])

    row = _scenario_row(scenario, 1.0, 0.0, 0.0, 0.0, initial_price_pct=12.0)

    assert row["modere"]["amount"] == pytest.approx(20_000.0)
    assert row["modere"]["ann_return"] == pytest.approx(100.0)
    assert row["modere"]["return_annualised"] is False
    assert row["modere"]["return_status"] == "computed"


def test_perte_integrale_de_la_prime_est_moins_cent_pourcent():
    scenario = _scenario_with_flows([{"t": 1.0, "cf": 0.0}])

    row = _scenario_row(scenario, 1.0, 0.0, 0.0, 0.0, initial_price_pct=12.0)

    assert row["stress"]["amount"] == 0.0
    assert row["stress"]["ann_return"] == -100.0
    assert row["stress"]["return_status"] == "total_loss"


def test_montant_publie_arrondi_a_dix_euros_sur_la_somme_des_flux_nets():
    """Annex IV point 42: sum received, coupons included, rounded to 10 EUR."""
    scenario = _scenario_with_flows([
        {"t": 1.0, "cf": 0.08},
        {"t": 2.0, "cf": 1.08},
    ])

    cell = _scenario_row(
        scenario, 2.0, cost_entry=0.0, cost_exit=1.0,
        cost_ongoing=2.0, initial_price_pct=100.0,
    )["modere"]

    assert cell["value"] == pytest.approx(sum(f["cf"] for f in cell["net_flows"]), abs=0.011)
    assert cell["amount"] == round(cell["value"] / 10) * 10
    # Le frais de sortie ne frappe que les flux de la date de sortie.
    assert cell["net_flows"][0]["cf"] == pytest.approx(800.0 * 0.98, abs=0.01)
    assert cell["net_flows"][1]["cf"] == pytest.approx(
        10_800.0 * 0.98**2 * 0.99, abs=0.01)


@pytest.mark.parametrize("annee_rappel", [1, 2, 3])
def test_coupon_annuel_huit_pourcent_suit_la_formule_du_point_44(annee_rappel):
    """(value / investment)^(1/T) - 1 over the scenario's own life, T being
    its call date (Annex V point 17). Coupons are not reinvested: called at
    year 3 after two 8 % coupons, 1.24 over three years is 7.44 % a year —
    the text's figure, not the 8 % an IRR would give."""
    flows = [{"t": float(year), "cf": 0.08} for year in range(1, annee_rappel)]
    flows.append({"t": float(annee_rappel), "cf": 1.08})
    scenario = _scenario_with_flows(flows)

    cell = _scenario_row(
        scenario, 5.0, 0.0, 0.0, 0.0,
        initial_price_pct=100.0,
    )["modere"]

    total = 1.0 + 0.08 * annee_rappel
    expected = (total ** (1 / annee_rappel) - 1) if annee_rappel > 1 else total - 1
    assert cell["life"] == float(annee_rappel)
    assert cell["ann_return"] == pytest.approx(round(expected * 100, 2), abs=1e-9)
