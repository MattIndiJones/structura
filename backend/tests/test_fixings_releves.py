"""Les relevés d'une constatation moyennée ont leur propre fixing — §14, point 6.

Une constatation sur période n'est pas observable : elle se calcule depuis les
cours de sa fenêtre. Ces cours doivent donc exister comme lignes à part entière
au booking, sinon ils n'ont ni fixing officiel, ni provenance, ni preuve — et
l'agrégat n'a rien à lire.

L'invariant qui compte : **un cours servant deux usages ne fait qu'une ligne**.
Le dernier relevé d'une fenêtre EST la constatation ; le dédoubler donnerait deux
fixings officiels pour un seul cours de bourse, et donc deux vérités possibles.
"""
from datetime import date, timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.db.models import Deal, DealEvent


SCRIPT_MOYENNE = """PARAM COUPON = 8%
CONSTAT() OBS AVG PERIOD
AT OBS:
  PAY COUPON * INDEX "coupon"
"""

SCRIPT_PONCTUEL = """PARAM COUPON = 8%
CONSTAT() OBS
AT OBS:
  PAY COUPON * INDEX "coupon"
"""


def _cal(debut, fin):
    return {"OBS": {"start_date": debut, "end_date": fin, "roll_date": fin,
                    "frequency": "1Y", "stub": "short_last",
                    "window_frequency": "3M"}}


def _corps(script, constats, strike):
    """Le minimum que le figement et la création d'événements lisent."""
    class _B:
        script_snapshot = script
        market_snapshot = {"constats": constats}
        strike_date = strike
        value_date = strike
        devise = "EUR"
    return _B()


def _echeancier(script, constats, strike):
    from backend.app.api.deals import _figer_echeancier
    import json
    return json.loads(_figer_echeancier(_corps(script, constats, strike)))


DEBUT = date.today().isoformat()
FIN = (date.today() + timedelta(days=1096)).isoformat()


def test_une_constatation_moyennee_declare_ses_releves():
    """L'échéancier figé porte les relevés : c'est lui que le booking lit pour
    savoir quels cours devront être collectés."""
    ech = _echeancier(SCRIPT_MOYENNE, _cal(DEBUT, FIN), DEBUT)
    assert len(ech["constatations"]) == 3
    for c in ech["constatations"]:
        assert c["reduction"] == "AVG"
        assert len(c["releves"]) == 4


def test_le_dernier_releve_est_la_constatation_elle_meme():
    """C'est ce qui permet de n'enregistrer qu'un seul fixing officiel pour un
    cours servant deux usages — l'invariant « aucun fixing compté deux fois »,
    tenu par construction plutôt que par vérification."""
    ech = _echeancier(SCRIPT_MOYENNE, _cal(DEBUT, FIN), DEBUT)
    for c in ech["constatations"]:
        assert c["releves"][-1]["date"] == c["date"]


def test_un_produit_ponctuel_ne_declare_aucun_releve():
    """Garde-fou : l'immense majorité des produits n'a pas de fenêtre, et rien
    ne doit changer pour eux."""
    ech = _echeancier(SCRIPT_PONCTUEL, _cal(DEBUT, FIN), DEBUT)
    assert all(not c["releves"] and not c["reduction"]
               for c in ech["constatations"])


def test_les_fenetres_se_relisent_depuis_l_echeancier_fige():
    """`_fenetres_par_date` est ce que le booking consulte pour créer les
    lignes de relevé. Il lit l'échéancier FIGÉ, pas un recalcul : une fois le
    deal booké, c'est lui qui fait foi."""
    from backend.app.api.deals import _fenetres_par_date, _figer_echeancier
    fenetres = _fenetres_par_date(_figer_echeancier(
        _corps(SCRIPT_MOYENNE, _cal(DEBUT, FIN), DEBUT)))
    assert len(fenetres) == 3
    for f in fenetres.values():
        assert f["reduction"] == "AVG" and len(f["releves"]) == 4

    # Un produit ponctuel n'en déclare aucune : aucune ligne de relevé créée.
    assert _fenetres_par_date(_figer_echeancier(
        _corps(SCRIPT_PONCTUEL, _cal(DEBUT, FIN), DEBUT))) == {}


def test_un_echeancier_absent_ne_fait_pas_planter_la_relecture():
    """Un deal booké avant ce champ — ou dont le script n'était pas résoluble —
    a un échéancier vide. La relecture doit rendre « aucune fenêtre », pas
    lever : ces deals continuent de vivre."""
    from backend.app.api.deals import _fenetres_par_date
    assert _fenetres_par_date("") == {}
    assert _fenetres_par_date("{}") == {}
    assert _fenetres_par_date("pas du json") == {}


def test_le_modele_porte_le_lien_releve_constatation():
    """Sur une base neuve, la colonne existe et un relevé pointe sa
    constatation. Sans ce lien, rien ne dit quels cours alimentent quel
    agrégat."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        parent = DealEvent(deal_id=1, event_index=1, event_date="2027-09-10",
                           t_years=1.0, reduction="AVG", label="Obs. 1")
        s.add(parent)
        s.flush()
        s.add(DealEvent(deal_id=1, event_index=2, event_date="2026-12-10",
                        t_years=0.25, parent_event_id=parent.id,
                        label="Obs. 1 · relevé 1/4"))
        s.commit()

        releves = s.exec(select(DealEvent)
                         .where(DealEvent.parent_event_id == parent.id)).all()
        assert len(releves) == 1
        assert releves[0].reduction == "", "un relevé ne porte pas de règle d'agrégation"
        assert parent.reduction == "AVG"
