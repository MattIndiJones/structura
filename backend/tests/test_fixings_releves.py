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


def test_l_api_expose_le_lien_releve_constatation():
    """L'écran Events doit pouvoir distinguer un relevé d'une constatation :
    sans ces deux champs, il les afficherait au même niveau et annoncerait douze
    observations là où le contrat en a trois."""
    import inspect
    from backend.app.api import deals as api

    src = inspect.getsource(api)
    # La sérialisation d'un événement de deal porte les deux champs.
    i = src.index('"event_index": e.event_index,')
    bloc = src[i:i + 900]
    assert '"parent_event_id": e.parent_event_id,' in bloc
    assert '"reduction": e.reduction or None,' in bloc


def test_un_releve_ne_porte_pas_de_regle_d_agregation():
    """La règle vit sur la constatation, jamais sur ses relevés : deux endroits
    pour une même information, ce sont deux endroits qui peuvent diverger."""
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        parent = DealEvent(deal_id=1, event_index=1, event_date="2027-09-10",
                           t_years=1.0, reduction="AVG", label="Obs. 1")
        s.add(parent)
        s.flush()
        releve = DealEvent(deal_id=1, event_index=2, event_date="2026-12-10",
                           t_years=0.25, parent_event_id=parent.id,
                           label="Obs. 1 · relevé 1/4")
        s.add(releve)
        s.commit()
        assert releve.reduction == ""
        assert releve.parent_event_id == parent.id


# ── La fenêtre de départ ───────────────────────────────────────────────

SCRIPT_DEPART = """PARAM STRIKE = 100%
CONSTAT STRIKE_FIX  AVG
CONSTAT MATURITE

AT MATURITE:
  PAY MAX(WOF - STRIKE, 0) "call"
"""


def test_la_fenetre_de_depart_a_ses_releves_bookes_sous_le_strike():
    """S0 d'un `STRIKE_FIX AVG 10D` se calcule sur dix cours. Le booking ne
    créait que l'événement du strike : les autres relevés n'avaient ni ligne,
    ni fixing, et le rejeu officiel reportait le cours du strike sur toute la
    fenêtre — S0 valait ce premier cours, pas la moyenne.

    Le fixing du jour de strike reste UNE ligne quand ce jour est un relevé :
    il en est le premier, pas un de plus."""
    import json
    from types import SimpleNamespace
    from backend.app.api import deals as deals_api
    from backend.app.api.auth import receipt_signing_secret
    from backend.app.core.schemas import PricingRequest
    from backend.app.core.valuation_context import build_pricing_receipt
    from backend.app.services.product_receipts import signed_receipt

    strike = date.today()
    maturite = strike + timedelta(days=364)
    while maturite.weekday() >= 5:
        maturite -= timedelta(days=1)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        constats = {
            "STRIKE_FIX": {"date": strike.isoformat(), "window_length": "10D",
                           "window_frequency": "1D"},
            "MATURITE": maturite.isoformat(),
        }
        tenor = round((maturite - strike).days / 365.25, 4)
        request = PricingRequest(
            script=SCRIPT_DEPART,
            underlyings=[{"name": "UL1", "ticker": "TK1", "ccy": "EUR"}],
            corr_matrix=[[1.0]], T=tenor, N=2000,
            user_params={"STRIKE": 1.0}, constats=constats,
            strike_date=strike,
            value_date=strike + timedelta(days=4),
            maturity_date=maturite,
            payment_date=maturite + timedelta(days=5),
            settlement_ccy="EUR",
        )
        receipt = signed_receipt(
            build_pricing_receipt(request, 0.979),
            secret=receipt_signing_secret(), result={"price": 0.979})
        deal = deals_api.book_deal(deals_api.DealCreate(
            contrepartie="BNP Paribas", nominal=1_000_000.0, fair_value=97.9,
            price_traded=98.0, trade_date=strike.isoformat(),
            strike_date=strike.isoformat(),
            value_date=(strike + timedelta(days=4)).isoformat(),
            maturity_date=maturite.isoformat(),
            payment_date=(maturite + timedelta(days=5)).isoformat(),
            T=tenor,
            underlyings=[{"name": "UL1", "ticker": "TK1", "ccy": "EUR", "s0_abs": 100.0}],
            observation_times=[], script_snapshot=SCRIPT_DEPART,
            market_snapshot={"constats": constats},
            pricing_receipt=receipt,
        ), SimpleNamespace(id=1, entity_id=1), s)

        depart = json.loads(s.get(Deal, deal["id"]).schedule_json)["depart"]
        attendues = [r["date"] for r in depart["releves"]]
        assert depart["reduction"] == "AVG" and len(attendues) == 10

        (strike_ev,) = [e for e in deal["events"] if e["t_years"] == 0.0]
        assert strike_ev["reduction"] == "AVG"
        releves = [e for e in deal["events"] if e["parent_event_id"] == strike_ev["id"]]
        lignes = sorted([strike_ev["event_date"]] + [e["event_date"] for e in releves])
        # Chaque date de la fenêtre a exactement une ligne, le strike compris.
        assert lignes == sorted(set(attendues) | {strike.isoformat()})
        assert len(lignes) == len(set(lignes))
        assert all(e["reduction"] is None for e in releves)
