"""Client Intelligence — les trois niveaux de lecture, et les signaux.

Le scénario central du §85 est ici en entier : une personne travaille chez
Bank A, y traite à un certain rythme, rejoint Bank B, et continue. On doit
pouvoir lire séparément son historique complet, son comportement chez A, son
comportement chez B, et celui des autres contacts de B — puis comparer, sans
que le module ne conclue à une cause.

Les signaux sont testés avec un `asof` explicite. Un test de dormance qui
dépend du jour où il tourne est un test qui échouera un mardi de novembre.
"""
from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from backend.app.core.client_intelligence import (
    client_intelligence, deals_of_client, evidence_level, observed_behaviour,
    person_intelligence, recency_level,
)
from backend.app.core.client_signals import (
    CONTACT_SOON, DORMANT, FOLLOW_UP_DUE, OPPORTUNITY_STALE, UPCOMING_MATURITY,
    build_signals,
)
from backend.app.db.models import (
    Affiliation, Client, ClientTradeHistory, Deal, DealEvent, Interaction,
    Opportunity, Person,
)


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _client(session, nom):
    c = Client(name=nom, entity_id=1, status="active")
    session.add(c); session.commit(); session.refresh(c)
    return c


def _personne(session, prenom, nom):
    p = Person(first_name=prenom, last_name=nom, entity_id=1)
    session.add(p); session.commit(); session.refresh(p)
    return p


def _affiliation(session, personne, client, debut, fin=None):
    a = Affiliation(person_id=personne.id, client_id=client.id,
                    start_date=debut, end_date=fin, job_title="Gérant")
    session.add(a); session.commit(); session.refresh(a)
    return a


def _trade(session, client, affiliation, trade_date, *, ref=None,
           produit="Autocall Athena", nominal=1_000_000.0, devise="EUR",
           contrepartie="BNP Paribas", maturite="2028-01-15", statut="actif"):
    d = Deal(reference=ref or f"D-{trade_date}-{affiliation.id if affiliation else 0}",
             user_id=1, entity_id=1, client_id=client.id,
             primary_affiliation_id=affiliation.id if affiliation else None,
             trade_date=trade_date, strike_date=trade_date,
             maturity_date=maturite, nominal=nominal, devise=devise,
             product_type=produit, contrepartie=contrepartie, status=statut,
             underlyings_json='[{"ticker": "^STOXX50E"}]')
    session.add(d); session.commit()
    return d


# ── §85 — les quatre lectures d'une même personne ────────────────────

def test_les_trois_niveaux_se_lisent_separement():
    """Jean traite tous les 90 jours chez Bank A, puis chez Bank B, où les
    autres traitent tous les 30. Chaque niveau doit rendre SON chiffre."""
    session = _session()
    bank_a, bank_b = _client(session, "Bank A"), _client(session, "Bank B")
    jean = _personne(session, "Jean", "Dupont")
    sophie = _personne(session, "Sophie", "Martin")

    chez_a = _affiliation(session, jean, bank_a, "2022-01-01", fin="2025-12-31")
    chez_b = _affiliation(session, jean, bank_b, "2026-01-01")
    sophie_b = _affiliation(session, sophie, bank_b, "2024-01-01")

    for jour in ("2024-01-01", "2024-04-01", "2024-06-30", "2024-09-28"):
        _trade(session, bank_a, chez_a, jour)
    for jour in ("2026-01-15", "2026-04-15", "2026-07-14"):
        _trade(session, bank_b, chez_b, jour)
    for jour in ("2026-02-01", "2026-03-03", "2026-04-02", "2026-05-02"):
        _trade(session, bank_b, sophie_b, jour)

    lecture = person_intelligence(session, jean.id, asof=date(2026, 8, 1))
    cycles = lecture["cycles"]

    # Personnel : les deux périodes réunies.
    assert cycles["personal"]["n_trades"] == 7
    # Chez B seulement.
    assert cycles["current_affiliation"]["n_trades"] == 3
    assert round(cycles["current_affiliation"]["median_interval_days"]) == 90
    # La maison, SANS Jean — sinon on se comparerait en partie à soi-même.
    assert cycles["organization"]["n_trades"] == 4
    assert round(cycles["organization"]["median_interval_days"]) == 30


def test_la_comparaison_dit_ressemblance_pas_causalite():
    session = _session()
    bank_a, bank_b = _client(session, "Bank A"), _client(session, "Bank B")
    jean = _personne(session, "Jean", "Dupont")
    sophie = _personne(session, "Sophie", "Martin")
    chez_a = _affiliation(session, jean, bank_a, "2022-01-01", fin="2025-12-31")
    chez_b = _affiliation(session, jean, bank_b, "2026-01-01")
    sophie_b = _affiliation(session, sophie, bank_b, "2024-01-01")

    for jour in ("2024-01-01", "2024-04-01", "2024-06-30", "2024-09-28"):
        _trade(session, bank_a, chez_a, jour)
    for jour in ("2026-01-15", "2026-04-15", "2026-07-14"):
        _trade(session, bank_b, chez_b, jour)
    for jour in ("2026-02-01", "2026-03-03", "2026-04-02", "2026-05-02"):
        _trade(session, bank_b, sophie_b, jour)

    comparaison = person_intelligence(
        session, jean.id, asof=date(2026, 8, 1))["comparison"]
    assert comparaison["comparable"] is True
    assert comparaison["closer_to"] == "personal"
    assert "observation, pas explication" in " ".join(comparaison["explanation"])


def test_le_comportement_observe_compte_sans_interpreter():
    """Pas de profil de risque synthétique : des comptages vérifiables."""
    session = _session()
    client = _client(session, "ABC AM")
    jean = _personne(session, "Jean", "Dupont")
    affiliation = _affiliation(session, jean, client, "2022-01-01")

    for jour in ("2025-01-15", "2025-04-15", "2025-07-15"):
        _trade(session, client, affiliation, jour, produit="Autocall Athena")
    _trade(session, client, affiliation, "2025-10-15", produit="Phoenix Memory")

    lecture = observed_behaviour(deals_of_client(session, client.id))
    assert lecture["n_trades"] == 4
    assert lecture["n_imported"] == 0
    assert lecture["product_types"][0] == ("Autocall Athena", 3)
    assert lecture["median_ticket"] == 1_000_000.0
    assert lecture["evidence"]["code"] == "emerging"
    assert "Autocall Athena" in " ".join(lecture["explanation"])


@pytest.mark.parametrize("n, attendu", [
    (1, "isolated"), (2, "repeated"), (3, "emerging"), (4, "emerging"),
    (5, "observed"), (9, "observed"), (10, "well_documented"),
])
def test_les_seuils_d_habitude_restent_explicites(n, attendu):
    assert evidence_level(n)["code"] == attendu


def test_la_recence_ne_supprime_pas_une_habitude_ancienne():
    assert recency_level("2026-01-01", asof=date(2026, 8, 1))["code"] == "current"
    assert recency_level("2025-01-01", asof=date(2026, 8, 1))["code"] == "to_confirm"
    assert recency_level("2023-01-01", asof=date(2026, 8, 1))["code"] == "historical"


def test_declare_et_observe_cohabitent_sans_s_ecraser():
    """§11 — leur divergence est une information commerciale, pas une erreur."""
    session = _session()
    client = _client(session, "XYZ AM")
    client.constraints_json = '{"product_types": ["capital_protected"]}'
    session.add(client); session.commit()

    jean = _personne(session, "Jean", "Dupont")
    affiliation = _affiliation(session, jean, client, "2022-01-01")
    for jour in ("2025-01-15", "2025-04-15", "2025-07-15"):
        _trade(session, client, affiliation, jour, produit="Autocall Athena")

    lecture = client_intelligence(session, client.id, asof=date(2025, 10, 1))
    # Le déclaré dit « capital protégé », l'observé dit « autocall ». Les deux
    # restent lisibles côte à côte.
    assert lecture["declared"]["client"]["product_types"] == ["capital_protected"]
    assert lecture["behaviour"]["product_types"][0][0] == "Autocall Athena"


def test_une_societe_n_est_pas_reduite_a_sa_moyenne():
    """§40 — un gérant prudent et un gérant agressif ne font pas un client
    « risque moyen ». Le détail par contact vient à côté de l'agrégat."""
    session = _session()
    client = _client(session, "Deux têtes AM")
    jean, sophie = _personne(session, "Jean", "D"), _personne(session, "Sophie", "M")
    a_jean = _affiliation(session, jean, client, "2022-01-01")
    a_sophie = _affiliation(session, sophie, client, "2022-01-01")

    for jour in ("2026-01-01", "2026-04-01", "2026-07-01"):
        _trade(session, client, a_jean, jour, produit="Capital garanti")
    for jour in ("2026-01-15", "2026-02-15", "2026-03-15"):
        _trade(session, client, a_sophie, jour, produit="Phoenix agressif")

    lecture = client_intelligence(session, client.id, asof=date(2026, 8, 1))
    profils = {c["name"]: c for c in lecture["per_contact"]}
    assert len(profils) == 2
    assert profils["Jean D"]["behaviour"]["product_types"][0][0] == "Capital garanti"
    assert profils["Sophie M"]["behaviour"]["product_types"][0][0] == "Phoenix agressif"
    # Et leurs cadences diffèrent aussi — l'agrégat seul les aurait fondues.
    assert (profils["Jean D"]["cycle"]["median_interval_days"]
            != profils["Sophie M"]["cycle"]["median_interval_days"])


def test_une_personne_sans_transaction_ne_recoit_aucune_prediction():
    session = _session()
    client = _client(session, "ABC AM")
    jean = _personne(session, "Jean", "Dupont")
    _affiliation(session, jean, client, "2026-01-01")

    lecture = person_intelligence(session, jean.id, asof=date(2026, 8, 1))
    assert lecture["cycles"]["personal"]["confidence"] == "insufficient_history"
    assert lecture["contact_window"]["start"] is None
    assert lecture["comparison"]["comparable"] is False


# ── Signaux ──────────────────────────────────────────────────────────

def test_une_relance_echue_leve_un_signal():
    session = _session()
    client = _client(session, "ABC AM")
    session.add(Interaction(
        entity_id=1, user_id=1, client_id=client.id,
        interaction_date="2026-08-01", interaction_type="call",
        summary="Revue", next_action="Renvoyer un indicatif 3Y",
        next_action_date="2026-08-20"))
    session.commit()

    signaux = build_signals(session, entity_id=1, user_id=1,
                            asof=date(2026, 8, 31))
    relances = [s for s in signaux if s.kind == FOLLOW_UP_DUE]
    assert len(relances) == 1
    assert relances[0].severity == "urgent"      # 11 jours de retard
    assert "11 jour" in relances[0].reason


def test_un_client_dormant_est_signale_relativement_a_sa_cadence():
    """§51 — le seuil n'est pas absolu. Un mensuel muet depuis 100 jours est
    signalé, un trimestriel non."""
    session = _session()
    mensuel = _client(session, "Mensuel SA")
    trimestriel = _client(session, "Trimestriel SA")
    p1, p2 = _personne(session, "A", "Un"), _personne(session, "B", "Deux")
    a1 = _affiliation(session, p1, mensuel, "2024-01-01")
    a2 = _affiliation(session, p2, trimestriel, "2024-01-01")

    for jour in ("2026-01-01", "2026-01-31", "2026-03-02", "2026-04-01"):
        _trade(session, mensuel, a1, jour)
    for jour in ("2025-08-01", "2025-10-30", "2026-01-28", "2026-04-28"):
        _trade(session, trimestriel, a2, jour)

    signaux = build_signals(session, entity_id=1, user_id=None,
                            asof=date(2026, 7, 10))
    dormants = {s.client_name for s in signaux if s.kind == DORMANT}
    assert "Mensuel SA" in dormants          # 100 jours pour une cadence de 30
    assert "Trimestriel SA" not in dormants  # 73 jours pour une cadence de 90


def test_une_opportunite_sans_activite_est_signalee(monkeypatch):
    monkeypatch.setenv("STRUCTURA_OPPORTUNITY_STALE_DAYS", "21")
    from datetime import datetime
    session = _session()
    client = _client(session, "ABC AM")
    opportunite = Opportunity(
        reference="OPP-1", entity_id=1, owner_user_id=1, client_id=client.id,
        title="Phoenix 3Y", status="client_interest",
        last_activity_at=datetime(2026, 7, 1))
    session.add(opportunite); session.commit()

    signaux = build_signals(session, entity_id=1, user_id=1,
                            asof=date(2026, 8, 31))
    sommeil = [s for s in signaux if s.kind == OPPORTUNITY_STALE]
    assert len(sommeil) == 1
    assert "61 jours" in sommeil[0].reason
    assert "seuil 21" in sommeil[0].reason


def test_une_opportunite_close_ne_dort_pas():
    from datetime import datetime
    session = _session()
    client = _client(session, "ABC AM")
    session.add(Opportunity(
        reference="OPP-1", entity_id=1, owner_user_id=1, client_id=client.id,
        title="Perdue", status="lost", lost_reason="timing",
        last_activity_at=datetime(2026, 1, 1)))
    session.commit()
    signaux = build_signals(session, entity_id=1, user_id=1,
                            asof=date(2026, 8, 31))
    assert not [s for s in signaux if s.kind == OPPORTUNITY_STALE]


def test_une_maturite_proche_est_signalee_sans_prediction_de_rappel():
    """§52 — la maturité est un fait contractuel. Aucune probabilité d'autocall
    n'est calculée, et le message ne doit rien laisser croire de tel."""
    session = _session()
    client = _client(session, "ABC AM")
    jean = _personne(session, "Jean", "D")
    affiliation = _affiliation(session, jean, client, "2024-01-01")
    deal = _trade(
        session, client, affiliation, "2024-10-15", maturite="2026-10-15")
    event = DealEvent(
        deal_id=deal.id, event_index=3, event_date="2026-10-15",
        t_years=2.0, status="futur", label="Maturité")
    session.add(event); session.commit(); session.refresh(event)

    signaux = build_signals(session, entity_id=1, user_id=None,
                            asof=date(2026, 9, 1))
    maturites = [s for s in signaux if s.kind == UPCOMING_MATURITY]
    assert len(maturites) == 1
    assert "44 jours" in maturites[0].reason
    assert maturites[0].deal_id == deal.id
    assert maturites[0].deal_event_id == event.id
    assert maturites[0].origin == "life_cycle"
    for interdit in ("probable", "probabilité", "autocall attendu"):
        assert interdit not in maturites[0].reason.lower()


def test_la_prochaine_constatation_lifecycle_remplace_la_maturite_lointaine():
    """Le commercial voit le prochain fait du calendrier existant, pas une
    seconde échéance recalculée depuis le Deal."""
    session = _session()
    client = _client(session, "ABC AM")
    jean = _personne(session, "Jean", "D")
    affiliation = _affiliation(session, jean, client, "2024-01-01")
    deal = _trade(
        session, client, affiliation, "2024-10-15", maturite="2027-10-15")
    event = DealEvent(
        deal_id=deal.id, event_index=2, event_date="2026-09-20",
        t_years=2.0, status="futur", label="Obs. 2 (2.00Y)")
    session.add(event); session.commit(); session.refresh(event)

    signaux = build_signals(session, entity_id=1, user_id=1,
                            asof=date(2026, 9, 1))
    lifecycle = [s for s in signaux if s.kind == UPCOMING_MATURITY]

    assert len(lifecycle) == 1
    assert lifecycle[0].due_date == "2026-09-20"
    assert lifecycle[0].deal_event_id == event.id
    assert "coupon ou le rappel éventuel" in lifecycle[0].reason
    assert "probable" not in lifecycle[0].reason.lower()


def test_une_maturite_importee_reste_commerciale_et_sans_lien_lifecycle():
    session = _session()
    client = _client(session, "ABC AM")
    session.add(ClientTradeHistory(
        entity_id=1, client_id=client.id, trade_date="2024-01-15",
        maturity_date="2026-09-25", product_type="Phoenix importé"))
    session.commit()

    signaux = build_signals(session, entity_id=1, user_id=1,
                            asof=date(2026, 9, 1))
    importes = [s for s in signaux if s.kind == UPCOMING_MATURITY]

    assert len(importes) == 1
    assert importes[0].origin == "imported_history"
    assert importes[0].deal_id is None
    assert "ce n'est pas une position" in importes[0].reason


def test_evenement_annule_non_projete_et_mes_dossiers_respecte():
    session = _session()
    client = _client(session, "ABC AM")
    jean = _personne(session, "Jean", "D")
    affiliation = _affiliation(session, jean, client, "2024-01-01")
    mien = _trade(
        session, client, affiliation, "2024-01-15", ref="D-MIEN",
        maturite="2027-01-15")
    autre = _trade(
        session, client, affiliation, "2024-02-15", ref="D-AUTRE",
        maturite="2027-02-15")
    autre.user_id = 2
    annule = _trade(
        session, client, affiliation, "2024-03-15", ref="D-ANNULE",
        maturite="2027-03-15")
    annule.user_id = 1
    session.add(autre); session.add(annule); session.flush()
    for deal, statut in ((mien, "futur"), (autre, "futur"), (annule, "annulé")):
        session.add(DealEvent(
            deal_id=deal.id, event_index=1, event_date="2026-09-20",
            t_years=1.0, status=statut, label="Obs. 1 (1.00Y)"))
    session.commit()

    signaux = build_signals(session, entity_id=1, user_id=1,
                            asof=date(2026, 9, 1))
    projetes = [s.deal_id for s in signaux if s.kind == UPCOMING_MATURITY]

    assert projetes == [mien.id]


def test_un_deal_sans_client_ne_produit_aucun_signal():
    """Les deals non rattachés — tout l'historique existant — restent hors du
    module commercial par construction."""
    session = _session()
    client = _client(session, "ABC AM")
    session.add(Deal(reference="D-ORPHELIN", user_id=1, entity_id=1,
                     trade_date="2024-10-15", maturity_date="2026-10-15",
                     nominal=1.0, status="actif"))
    session.commit()
    signaux = build_signals(session, entity_id=1, user_id=None,
                            asof=date(2026, 9, 1))
    assert not [s for s in signaux if s.kind == UPCOMING_MATURITY]


def test_les_signaux_sortent_du_plus_urgent_au_plus_lointain():
    session = _session()
    client = _client(session, "ABC AM")
    jean = _personne(session, "Jean", "D")
    affiliation = _affiliation(session, jean, client, "2024-01-01")
    _trade(session, client, affiliation, "2024-10-15", maturite="2026-10-15")
    session.add(Interaction(
        entity_id=1, user_id=1, client_id=client.id,
        interaction_date="2026-08-01", interaction_type="call", summary="X",
        next_action="Rappeler", next_action_date="2026-08-10"))
    session.commit()

    signaux = build_signals(session, entity_id=1, user_id=1,
                            asof=date(2026, 9, 1))
    severites = [s.severity for s in signaux]
    ordre = {"urgent": 0, "warning": 1, "info": 2}
    assert severites == sorted(severites, key=lambda s: ordre[s])
