"""Les lignes de relevé face à leurs consommateurs — §21.

Le booking crée, sous chaque constatation moyennée, une ligne `DealEvent` par
relevé (§19). Tout le code écrit quand « une ligne = une constatation » était
vrai lit désormais ces lignes comme des observations : la prochaine date
annoncée devient un relevé, et `event_index`, que les relevés décalent, cesse
d'être un rang.

Ces tests fixent la lecture correcte, consommateur par consommateur. Chacun
échouait avant la correction.
"""
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.api import deals as deals_api
from backend.app.db.models import AuditEvent, Deal, DealEvent

TODAY = date.today()
STRIKE = TODAY - timedelta(days=400)

SCRIPT_DEGRESSIF = """CONSTAT() OBS AVG PERIOD
PARAM() M_AC_BAR = 100% "barrière de rappel dégressive"
AT OBS:
  IF WOF >= M_AC_BAR:
    PAY 1 + 0.05 * INDEX
    STOP
AT MATURITY:
  PAY WOF
"""


def _session():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng)


def _prix_plats(niveau):
    def fake(tickers, start, end):
        d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
        jours = [d0 + timedelta(days=k) for k in range((d1 - d0).days + 1)]
        return {"dates": [d.isoformat() for d in jours],
                "prices": {tk: [niveau] * len(jours) for tk in tickers}}
    return fake


def _deal_moyenne(s, *, avec_releves=True):
    """Trois constatations annuelles moyennées sur quatre relevés trimestriels,
    rangées comme le booking les crée : la constatation, puis ses relevés.

    La première constatation est passée ; la prochaine est dans 330 jours, et
    son premier relevé dans 56. Sans relevés, c'est le même calendrier en
    constatations ponctuelles — la lecture historique."""
    deal = Deal(
        reference="AVG-001", user_id=1, status="actif",
        script_snapshot=SCRIPT_DEGRESSIF,
        underlyings_json=json.dumps([{"name": "UL1", "ticker": "TK1"}]),
        market_snapshot_json=json.dumps(
            {"user_params": {"M_AC_BAR": [1.0, 0.95, 0.90]}}),
        strike_date=STRIKE.isoformat(), value_date=STRIKE.isoformat(),
        maturity_date=(STRIKE + timedelta(days=1096)).isoformat(),
        T=3.0, devise="EUR")
    s.add(deal)
    s.commit()
    s.refresh(deal)

    index = 0

    def ligne(jours, t, label, *, parent=None, reduction="", spots=None):
        nonlocal index
        date_ev = STRIKE + timedelta(days=jours)
        ev = DealEvent(deal_id=deal.id, event_index=index,
                       event_date=date_ev.isoformat(), t_years=t,
                       spots_json=json.dumps(spots or {}),
                       status="observé" if date_ev <= TODAY else "futur",
                       label=label, parent_event_id=parent, reduction=reduction)
        s.add(ev)
        s.flush()
        index += 1
        return ev

    ligne(0, 0.0, "Strike / Fixing S₀", spots={"UL1": 100.0})
    for k, (jours, label) in enumerate(
            [(365, "Obs. 1 (1.00Y)"), (730, "Obs. 2 (2.00Y)"), (1096, "Maturité")],
            start=1):
        constatation = ligne(jours, float(k), label,
                             reduction="AVG" if avec_releves else "")
        if avec_releves:
            for j in (1, 2, 3):
                ligne(jours - 365 + 91 * j, k - 1 + 0.25 * j,
                      f"{label} · relevé {j}/4", parent=constatation.id)
    s.commit()
    return deal


# ── Watchlist : prochaine observation, et ligne de PARAM() lue ─────────

@pytest.mark.parametrize("avec_releves", [True, False],
                         ids=["releves_bookes", "sans_releves"])
def test_la_watchlist_vise_la_prochaine_constatation(monkeypatch, avec_releves):
    """La barrière d'un autocall dégressif se lit à la ligne de la PROCHAINE
    CONSTATATION. Avec les relevés, `event_index` valait 6 là où le rang vaut
    2 : la watchlist affichait la barrière de maturité (90 %) au lieu de 95 %,
    et le planificateur d'alertes en tirait ses franchissements.

    Le cas sans relevés garde la lecture historique — même rang, même date."""
    s = _session()
    deal = _deal_moyenne(s, avec_releves=avec_releves)
    monkeypatch.setattr(deals_api, "load_hist_prices", _prix_plats(97.0))

    row = deals_api.build_watchlist_row(deal, s, TODAY)

    assert row["next_event"]["label"] == "Obs. 2 (2.00Y)"
    assert row["days_to_next"] == 330
    (barriere,) = row["barriers"]
    assert barriere["level"] == pytest.approx(0.95)
    assert barriere["gap_pts"] == pytest.approx(2.0, abs=0.05)


def test_l_alerte_de_rappel_compte_les_jours_jusqu_a_la_constatation(monkeypatch):
    """`lifecycle_alerts` écrit « rappel probable à l'observation dans N j » à
    partir de `days_to_next`. Compté jusqu'au premier relevé, N annonçait un
    rappel dans 56 jours sur un produit qui ne peut rappeler que dans 330."""
    s = _session()
    deal = _deal_moyenne(s)
    monkeypatch.setattr(deals_api, "load_hist_prices", _prix_plats(97.0))
    assert deals_api.build_watchlist_row(deal, s, TODAY)["days_to_next"] == 330


# ── Note de valorisation client ────────────────────────────────────────

def _echeancier_fige():
    return json.dumps({"constatations": [
        {"calendrier": "OBS", "rang": k, "t": float(k), "date": None,
         "reduction": "AVG", "blocs": [0],
         "releves": [{"t": k - 1 + 0.25 * j, "date": None, "evenement": j == 4}
                     for j in (1, 2, 3, 4)]}
        for k in (1, 2, 3)], "depart": None, "blocs_maturite": []})


def test_la_note_de_valorisation_ne_liste_que_les_constatations():
    """Document client : sa table s'intitule « Constatation » et sa phrase dit
    « Prochaine date d'observation ». Un relevé n'est ni l'un ni l'autre. La
    fenêtre n'est pas passée sous silence pour autant — elle qualifie la
    constatation qu'elle alimente."""
    s = _session()
    deal = _deal_moyenne(s)
    events = deals_api._get_events(deal.id, s)

    lignes, prochaine = deals_api._evenements_pour_la_note(events, _echeancier_fige())

    assert [l["label"] for l in lignes] == [
        "Strike / Fixing S₀",
        "Obs. 1 (1.00Y) — moyenne de 4 relevés",
        "Obs. 2 (2.00Y) — moyenne de 4 relevés",
        "Maturité — moyenne de 4 relevés",
    ]
    assert prochaine == (STRIKE + timedelta(days=730)).isoformat()


def test_la_note_d_un_produit_ponctuel_est_inchangee():
    s = _session()
    deal = _deal_moyenne(s, avec_releves=False)
    events = deals_api._get_events(deal.id, s)

    lignes, prochaine = deals_api._evenements_pour_la_note(events, "")

    assert [l["label"] for l in lignes] == [
        "Strike / Fixing S₀", "Obs. 1 (1.00Y)", "Obs. 2 (2.00Y)", "Maturité"]
    assert prochaine == (STRIKE + timedelta(days=730)).isoformat()


# ── Piste d'audit ──────────────────────────────────────────────────────

def test_l_audit_d_une_modification_refusee_cite_les_vrais_temps_d_observation():
    """Une modification post-booking refusée enregistre la valeur « avant » du
    champ visé. Pour `observation_times`, elle listait douze temps sur un
    contrat qui en a trois : l'auditeur aurait lu une divergence qui n'existe
    pas entre le booking et le deal."""
    s = _session()
    deal = _deal_moyenne(s)
    with pytest.raises(HTTPException):
        deals_api.update_deal(
            deal.id, deals_api.DealUpdate(observation_times=[0.5]),
            SimpleNamespace(id=1, entity_id=None, role="user"), s)

    audit = s.exec(select(AuditEvent).where(
        AuditEvent.action == "POST_BOOKING_MODIFICATION_REJECTED")).one()
    assert json.loads(audit.before_json)["observation_times"] == [1.0, 2.0, 3.0]


# ── Watchlist : S0 d'une fenêtre de départ ─────────────────────────────

SCRIPT_DEPART = """PARAM M_KI_BAR = 60% "barrière de protection"
CONSTAT STRIKE_FIX  AVG
CONSTAT MATURITE

AT MATURITE:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) + KI * WOF
"""


def _deal_depart(s, *, releve_manquant=False):
    """S0 moyenné sur dix relevés : le fixing du jour de strike (100) puis
    101 … 109. S0 contractuel = 104,5 ; le cours du strike seul = 100."""
    jours = [STRIKE + timedelta(days=k) for k in range(10)]
    deal = Deal(
        reference="DEP-001", user_id=1, status="actif",
        script_snapshot=SCRIPT_DEPART,
        underlyings_json=json.dumps([{"name": "UL1", "ticker": "TK1"}]),
        market_snapshot_json=json.dumps({"user_params": {}}),
        strike_date=STRIKE.isoformat(), value_date=STRIKE.isoformat(),
        maturity_date=(STRIKE + timedelta(days=1096)).isoformat(),
        T=3.0, devise="EUR",
        schedule_json=json.dumps({
            "depart": {"reduction": "AVG", "releves": [
                {"t": round(k / 365.25, 6), "date": j.isoformat(), "evenement": False}
                for k, j in enumerate(jours)]},
            "constatations": [], "blocs_maturite": [0]}))
    s.add(deal)
    s.commit()
    s.refresh(deal)
    strike = DealEvent(deal_id=deal.id, event_index=0, event_date=STRIKE.isoformat(),
                       t_years=0.0, spots_json=json.dumps({"UL1": 100.0}),
                       status="observé", label="Strike / Fixing S₀", reduction="AVG")
    s.add(strike)
    s.flush()
    for k, j in enumerate(jours[1:], start=1):
        spots = {} if (releve_manquant and k == 5) else {"UL1": 100.0 + k}
        s.add(DealEvent(deal_id=deal.id, event_index=k, event_date=j.isoformat(),
                        t_years=round(k / 365.25, 4), spots_json=json.dumps(spots),
                        status="observé", parent_event_id=strike.id,
                        label=f"Strike / Fixing S₀ · relevé {k + 1}/10"))
    s.add(DealEvent(deal_id=deal.id, event_index=10,
                    event_date=(STRIKE + timedelta(days=1096)).isoformat(),
                    t_years=3.0, spots_json="{}", status="futur", label="Maturité"))
    s.commit()
    return deal


def test_la_watchlist_mesure_contre_le_s0_de_la_fenetre_de_depart(monkeypatch):
    """Spot à 61,5 sous une barrière à 60 % : contre le cours du strike (100)
    la barrière tient à +1,5 pt ; contre S0 = 104,5 elle est FRANCHIE à
    −1,1 pt. La watchlist, et le planificateur d'alertes derrière elle,
    lisaient la première version."""
    s = _session()
    deal = _deal_depart(s)
    monkeypatch.setattr(deals_api, "load_hist_prices", _prix_plats(61.5))

    row = deals_api.build_watchlist_row(deal, s, TODAY)

    (ul,) = row["underlyings"]
    assert ul["s0"] == pytest.approx(104.5)
    (barriere,) = row["barriers"]
    assert barriere["kind"] == "ki"
    # 61,5 / 104,5 − 60 % = −1,148 pt, arrondi au dixième par la watchlist.
    assert barriere["gap_pts"] == pytest.approx(-1.1)


def test_tant_qu_un_releve_de_depart_manque_s0_n_est_pas_defini(monkeypatch):
    """Neuf relevés sur dix ne font pas S0. Une moyenne partielle présentée
    comme S0 déplacerait toutes les barrières sans le dire : l'écart reste
    None — « pas encore mesurable » —, jamais une valeur plausible."""
    s = _session()
    deal = _deal_depart(s, releve_manquant=True)
    monkeypatch.setattr(deals_api, "load_hist_prices", _prix_plats(61.5))

    row = deals_api.build_watchlist_row(deal, s, TODAY)

    assert row["underlyings"][0]["s0"] is None
    assert row["barriers"][0]["gap_pts"] is None
