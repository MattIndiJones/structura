"""Jeu de données fictives pour éprouver le module Client.

Le volume n'est pas l'objectif : la COUVERTURE l'est. Chaque société existe
pour mettre un comportement précis à l'épreuve, et `test_client_demo_seed.py`
vérifie qu'elle le produit bien — sans quoi « le jeu couvre les cas » serait une
affirmation plutôt qu'un fait.

    ┌────────────────────────┬──────────────────────────────────────────────┐
    │ Société                │ Ce qu'elle met à l'épreuve                   │
    ├────────────────────────┼──────────────────────────────────────────────┤
    │ Rhône AM               │ le cas riche : confiance haute, fenêtre de   │
    │                        │ contact OUVERTE, 2 anomalies d'émetteur,     │
    │                        │ mixte booké/importé, journées à 2 lignes     │
    │ Jura Assurances        │ historique pauvre : 2 transactions, tiret    │
    │                        │ gris, points au lieu d'une bande, relance    │
    │                        │ échue comme seule action                     │
    │ Fondation Lémanique    │ zéro transaction, politique complète — le    │
    │                        │ déclaré porte tout l'écran                   │
    │ Alpes Institutionnel   │ dormance RELATIVE à sa propre cadence        │
    │ Genève Privée          │ cadence irrégulière malgré le volume :       │
    │                        │ le nombre seul ne fait pas la confiance      │
    │ Valais Distribution    │ AUCUNE politique déclarée → aucune anomalie  │
    │                        │ possible (le faux positif qu'on refuse)      │
    │ Léman Family Office    │ deux contacts opposés — l'agrégat mentirait  │
    │ Bank Helvetia          │ ┐ changement de société : l'historique reste │
    │ Zurich Partners        │ ┘ chez l'employeur de l'époque               │
    └────────────────────────┴──────────────────────────────────────────────┘

**Toutes les dates sont relatives à aujourd'hui.** Des dates absolues rendraient
le jeu inerte dans six mois : la fenêtre de contact ne s'ouvrirait plus, la
dormance ne se déclencherait plus, et les écrans paraîtraient cassés alors que
ce serait le jeu qui aurait vieilli.

Usage — depuis la RACINE du dépôt :

    python backend/scripts/seed_client_demo.py            # semer
    python backend/scripts/seed_client_demo.py --purge    # tout retirer
    python backend/scripts/seed_client_demo.py --emit-import fichier.json

Le retrait n'identifie que les sociétés de ce fichier, par leur nom exact : il
ne peut pas emporter de données réelles.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from sqlmodel import Session, select  # noqa: E402

from backend.app.db.database import engine, init_db  # noqa: E402
from backend.app.db.models import (  # noqa: E402
    Affiliation, Client, ClientCoverage, ClientImportBatch, ClientTradeHistory,
    Deal, Interaction, InteractionParticipant, Opportunity,
    OpportunityParticipant, Person, RfqRequest, User,
)

AUJOURDHUI = date.today()


def j(decalage: int) -> str:
    """Une date, exprimée en jours depuis aujourd'hui (négatif = passé)."""
    return (AUJOURDHUI + timedelta(days=decalage)).isoformat()


# Les noms servent aussi de clé de retrait : ne jamais les faire varier.
SOCIETES = [
    "Rhône Asset Management", "Jura Assurances", "Fondation Lémanique",
    "Alpes Institutionnel", "Genève Privée", "Valais Distribution",
    "Léman Family Office", "Bank Helvetia", "Zurich Partners",
]

POLITIQUE_COMPLETE = {
    # Leonteq y figure délibérément : il est utilisé dans la rotation des
    # transactions, et l'omettre produisait une anomalie « hors liste » non
    # voulue qui noyait les deux vraies. Une démonstration doit montrer
    # exactement ce qu'elle annonce — un signal de trop décrédibilise les autres.
    "allowed_issuers": [{"id": None, "label": n} for n in
                        ("BNP Paribas", "Société Générale", "UBS", "Vontobel",
                         "Citi", "Leonteq")],
    "excluded_issuers": [{"id": None, "label": "Marex"}],
    "currencies": ["EUR", "CHF", "USD"],
    "asset_classes": ["equity", "credit"],
    "product_types": ["autocall", "phoenix", "reverse_convertible",
                      "capital_protected"],
    # Les tickers du catalogue, pas des noms d'usage : « SX5E » ne rencontre
    # jamais « ^STOXX50E », et l'écran conclurait que ce client n'a jamais
    # traité son propre univers. C'est précisément la saisie que le référentiel
    # existe pour empêcher — le jeu de démonstration ne doit pas la reproduire.
    "underlying_universe": ["^STOXX50E", "^GSPC", "^SSMI",
                            "MC.PA", "OR.PA", "KER.PA"],
    "internal_constraints": "Comité produit mensuel, validation à J+5.",
}


def _client(session, nom, *, type_client="asset_manager", pays="Suisse",
            statut="active", contraintes=POLITIQUE_COMPLETE,
            ticket=(500_000, 5_000_000), maturite=(12, 60), rating="A-",
            entity_id=None, user_id=1) -> Client:
    client = Client(
        entity_id=entity_id, name=nom, client_type=type_client, country=pays,
        status=statut, constraints_json=json.dumps(contraintes, ensure_ascii=False),
        data_origin="demo",
        ticket_min=ticket[0], ticket_max=ticket[1], ticket_currency="EUR",
        maturity_min_months=maturite[0], maturity_max_months=maturite[1],
        min_rating=rating, max_concentration_pct=25.0,
        created_by_user_id=user_id)
    session.add(client)
    session.flush()
    session.add(ClientCoverage(user_id=user_id, client_id=client.id,
                               coverage_role="primary"))
    return client


def _personne(session, prenom, nom, email, *, entity_id=None, user_id=1) -> Person:
    personne = Person(entity_id=entity_id, first_name=prenom, last_name=nom,
                      email=email, created_by_user_id=user_id)
    session.add(personne)
    session.flush()
    return personne


def _affilie(session, personne, client, *, debut, fin=None,
             poste="Gérant", role="portfolio_manager") -> Affiliation:
    affiliation = Affiliation(person_id=personne.id, client_id=client.id,
                              job_title=poste, commercial_role=role,
                              start_date=debut, end_date=fin)
    session.add(affiliation)
    session.flush()
    return affiliation


def _histo(session, client, affiliation, jour, *, emetteur="BNP Paribas",
           produit="Autocall Athena", nominal=1_500_000.0, devise="EUR",
           sous_jacent="^STOXX50E", maturite_mois=36, lot=None, entity_id=None,
           coupon=None, protection=None, prix=None, avec_nous=None):
    """Une transaction d'HISTORIQUE — pas une position que nous portons.

    Les tickers sont ceux du catalogue `underlyings` (conventions Yahoo) : un
    sous-jacent hors catalogue ressort « nature inconnue » dans l'onglet
    technique, ce qui est le comportement voulu mais ferait ici passer tout le
    jeu de démonstration pour un jeu défectueux.

    Un panier tient dans la même cellule, séparé par « / ».

    `avec_nous` reste à None sur une partie des lignes — délibérément. C'est
    l'état le plus fréquent d'un historique réellement versé par un client, et
    un jeu d'essai où tout serait renseigné ne testerait jamais l'affichage du
    cas majoritaire.
    """
    debut = date.fromisoformat(jour)
    ligne = ClientTradeHistory(
        entity_id=entity_id, import_batch_id=lot,
        client_id=client.id,
        affiliation_id=affiliation.id if affiliation else None,
        trade_date=jour,
        maturity_date=(debut + timedelta(days=int(maturite_mois * 30.44))).isoformat(),
        product_type=produit, underlying=sous_jacent, issuer=emetteur,
        currency=devise, notional=nominal,
        coupon_pct=coupon, barrier_pct=protection,
        price_pct=prix, traded_with_us=avec_nous,
        external_ref=f"DEMO-{client.id}-{jour}-{emetteur[:3]}-{int(nominal)}")
    session.add(ligne)
    return ligne


# Paniers de démonstration. Les tickers viennent du catalogue `underlyings`
# (conventions Yahoo) — un ticker inventé ressortirait « nature inconnue »,
# comportement correct du module mais qui ferait passer le jeu d'essai pour
# cassé. Un panier tient dans une cellule, séparé par « / ».
PANIER_LUXE = "MC.PA / OR.PA / KER.PA"
PANIER_BANQUES = "BNP.PA / GLE.PA / UBSG.SW"
PANIER_INDICES = "^STOXX50E / ^GSPC"
PANIER_SUISSE = "^SSMI / ^STOXX50E"

_compteur_deal = {"n": 0}


def _deal(session, client, affiliation, jour, *, emetteur="BNP Paribas",
          produit="Autocall Athena", nominal=1_500_000.0, devise="EUR",
          maturite_mois=36, opportunite=None, entity_id=None, user_id=1,
          statut="actif"):
    """Un deal réellement booké — celui-là entre dans le book et le risque."""
    _compteur_deal["n"] += 1
    debut = date.fromisoformat(jour)
    maturite = (debut + timedelta(days=int(maturite_mois * 30.44))).isoformat()
    deal = Deal(
        reference=f"DEMO-{AUJOURDHUI.strftime('%Y%m%d')}-{_compteur_deal['n']:03d}",
        entity_id=entity_id, user_id=user_id, client_id=client.id,
        primary_affiliation_id=affiliation.id if affiliation else None,
        opportunity_id=opportunite.id if opportunite else None,
        client_provenance_json=json.dumps(
            {"captured_at": datetime.utcnow().isoformat(),
             "client": {"id": client.id, "name": client.name}},
            ensure_ascii=False),
        sens="vente", contrepartie=emetteur, devise=devise, nominal=nominal,
        fair_value=98.5, price_traded=98.5, product_type=produit,
        trade_date=jour, strike_date=jour, value_date=jour,
        maturity_date=maturite, payment_date=maturite, T=maturite_mois / 12.0,
        status=statut, script_snapshot="AT MATURITY\n  PAY 1\n",
        underlyings_json=json.dumps([{"ticker": "^STOXX50E", "name": "Euro Stoxx 50"}]),
        market_snapshot_json=json.dumps({"r": 2.5}))
    session.add(deal)
    session.flush()
    return deal


_compteur_opp = {"n": 0}


def _opportunite(session, client, affiliation, *, titre, statut="client_interest",
                 montant=2_000_000.0, motif=None, activite_il_y_a=3,
                 entity_id=None, user_id=1) -> Opportunity:
    _compteur_opp["n"] += 1
    opportunite = Opportunity(
        reference=f"OPP-DEMO-{_compteur_opp['n']:03d}",
        entity_id=entity_id, owner_user_id=user_id, client_id=client.id,
        primary_affiliation_id=affiliation.id if affiliation else None,
        title=titre, amount=montant, currency="EUR", status=statut,
        lost_reason=motif, priority="medium",
        last_activity_at=datetime.utcnow() - timedelta(days=activite_il_y_a))
    session.add(opportunite)
    session.flush()
    return opportunite


def _interaction(session, client, jour, *, resume, type_="meeting",
                 action=None, action_le=None, opportunite=None,
                 affiliation=None, entity_id=None, user_id=1):
    interaction = Interaction(
        entity_id=entity_id, user_id=user_id, client_id=client.id,
        opportunity_id=opportunite.id if opportunite else None,
        interaction_date=jour, interaction_type=type_, summary=resume,
        next_action=action, next_action_date=action_le)
    session.add(interaction)
    session.flush()
    if affiliation is not None:
        session.add(InteractionParticipant(interaction_id=interaction.id,
                                           affiliation_id=affiliation.id))
    return interaction


# ══════════════════════════════════════════════════════════════════════
#  Le jeu
# ══════════════════════════════════════════════════════════════════════

def entite_du_compte(session: Session, user_id: int):
    """L'entité du compte pour lequel on sème.

    Tout le module filtre par `entity_id` : semer sur une autre entité que celle
    du compte produit des données parfaitement écrites et parfaitement
    invisibles. C'est arrivé au premier semis — neuf sociétés en base, un écran
    vide, et rien pour comprendre pourquoi.

    L'entité se déduit donc du compte au lieu de valoir `None` par défaut. Le
    drapeau `--entity-id` reste disponible pour forcer, mais il ne se subit plus.
    """
    utilisateur = session.get(User, user_id)
    if utilisateur is None:
        raise SystemExit(
            f"Compte id={user_id} introuvable. Précisez --user-id : c'est lui "
            f"qui donne l'entité sur laquelle semer.")
    return utilisateur.entity_id, utilisateur.username


def semer(session: Session, *, entity_id=None, user_id=1) -> dict:
    lot = ClientImportBatch(
        entity_id=entity_id, user_id=user_id,
        filename="jeu de démonstration (script)", source_format="json",
        status="applied")
    session.add(lot)
    session.flush()

    resume = {}
    K = dict(entity_id=entity_id, user_id=user_id)

    # ── 1. Rhône AM — le cas riche ───────────────────────────────────
    # Cadence ~88 j, dernière transaction il y a 74 jours : la fenêtre de
    # contact (attendu − 14 j de délai de discussion) englobe AUJOURD'HUI.
    # C'est ce qui fait apparaître la bande d'action bleue.
    rhone = _client(session, "Rhône Asset Management", **K)
    jean = _personne(session, "Jean", "Dupont", "jean.dupont@rhone-am.ch", **K)
    sophie = _personne(session, "Sophie", "Martin", "sophie.martin@rhone-am.ch", **K)
    aff_jean = _affilie(session, jean, rhone, debut=j(-1500))
    aff_sophie = _affilie(session, sophie, rhone, debut=j(-900),
                          poste="CIO", role="cio")

    # 17 journées, dont 6 portant deux lignes → 23 transactions.
    # C'est ce qui distingue n_trades de n_trading_days à l'écran.
    jours_rhone = [-1490, -1402, -1315, -1226, -1138, -1050, -962, -874,
                   -786, -698, -610, -522, -434, -338, -250, -162, -74]
    emetteurs = ["BNP Paribas", "Société Générale", "UBS", "Leonteq"]
    for index, decalage in enumerate(jours_rhone):
        emetteur = emetteurs[index % len(emetteurs)]
        produit = "Autocall Athena" if index % 3 else "Phoenix Memory"
        affiliation = aff_jean if index % 2 else aff_sophie
        # Les six dernières journées portent une seconde ligne — un panier
        # alloué en deux fois reste UN épisode d'investissement.
        # Le coupon suit la famille : un mono-indice ne paie pas ce que paie
        # un panier d'actions. Sans cet écart, les moyennes par famille
        # existeraient sans rien distinguer.
        indiciel = produit == "Autocall Athena"
        # Une transaction sur quatre est passée par un concurrent ; une sur
        # sept reste sans information d'exécution, cas majoritaire d'un
        # historique réellement versé.
        ailleurs, inconnu = index % 4 == 3, index % 7 == 5
        niveaux = dict(
            sous_jacent="^STOXX50E" if indiciel else PANIER_LUXE,
            coupon=(6.80 + (index % 3) * 0.35) if indiciel
                   else (11.90 + (index % 3) * 0.60),
            protection=60.0 if indiciel else 55.0,
            avec_nous=None if inconnu else not ailleurs,
            prix=None if inconnu else
                 (99.10 + (index % 3) * 0.25 if ailleurs else 100.00),
        )
        _histo(session, rhone, affiliation, j(decalage), emetteur=emetteur,
               produit=produit, nominal=1_200_000.0 + (index % 4) * 400_000,
               lot=lot.id, entity_id=entity_id, **niveaux)
        if index >= 11:
            _histo(session, rhone, affiliation, j(decalage), emetteur=emetteur,
                   produit=produit, nominal=900_000.0, lot=lot.id,
                   entity_id=entity_id, **niveaux)

    # Les deux anomalies d'émetteur, chacune de nature différente. Posées sur
    # des journées DÉJÀ traitées : une ligne de plus le même jour est le cas
    # courant, et surtout elle n'introduit pas d'intervalle parasite qui
    # dégraderait artificiellement la cadence de ce client — dont tout
    # l'intérêt est justement d'être régulière.
    _histo(session, rhone, aff_jean, j(-1226), emetteur="Marex",
           produit="Reverse Convertible", nominal=800_000.0, lot=lot.id,
           sous_jacent="STMPA.PA", coupon=9.50, protection=70.0,
           avec_nous=False, prix=98.60,
           entity_id=entity_id)          # exclu, pourtant traité
    _histo(session, rhone, aff_sophie, j(-338), emetteur="Natixis",
           produit="Reverse Convertible", nominal=1_700_000.0, lot=lot.id,
           sous_jacent="UCG.MI", coupon=10.25, protection=70.0,
           avec_nous=False, prix=99.40,
           entity_id=entity_id)          # ni autorisé, ni exclu

    gagnee = _opportunite(session, rhone, aff_jean, titre="Phoenix worst-of 3Y",
                          statut="won", **K)
    _opportunite(session, rhone, aff_jean, titre="Athena 5Y capital protégé",
                 statut="won", **K)
    _opportunite(session, rhone, aff_sophie, titre="Autocall mémoire 4Y",
                 statut="lost", motif="coupon_too_low", **K)
    _opportunite(session, rhone, aff_sophie, titre="Reverse convertible 2Y",
                 statut="lost", motif="issuer_rejected", **K)
    ouverte = _opportunite(session, rhone, aff_jean,
                           titre="Phoenix mémoire 3Y — septembre",
                           statut="rfq", activite_il_y_a=2, **K)

    # Deux deals réellement bookés : c'est ce qui fait apparaître la
    # distinction « bookées ici / importées » à l'écran.
    _deal(session, rhone, aff_jean, j(-74), opportunite=gagnee, **K)
    # Sur une journée déjà traitée, pour la même raison que les anomalies
    # ci-dessus. Maturité calée dans ~40 jours → alimente le signal
    # « maturité proche » de l'écran Cycles & Signaux.
    _deal(session, rhone, aff_sophie, j(-1050), maturite_mois=35.8,
          produit="Capital garanti", emetteur="UBS", **K)

    session.add(RfqRequest(
        reference=f"RFQ-DEMO-{AUJOURDHUI.strftime('%Y%m%d')}-001",
        entity_id=entity_id, user_id=user_id, opportunity_id=ouverte.id,
        name="Consultation Phoenix 3Y", ao_date=j(-5), kind="to_trade",
        sens="achat", script_snapshot="CONSTAT() Cal\nAT Cal:\n  PAY 0\n",
        params_json="{}", status="quote", model_price=97.4))

    _interaction(session, rhone, j(-6), resume="Revue de book trimestrielle",
                 opportunite=ouverte, affiliation=aff_jean, **K)
    resume["Rhône Asset Management"] = "cas riche, fenêtre de contact ouverte"

    # ── 2. Jura Assurances — historique pauvre ───────────────────────
    jura = _client(session, "Jura Assurances", type_client="insurance",
                   ticket=(1_000_000, 10_000_000), maturite=(24, 84),
                   rating="A", **K)
    marc = _personne(session, "Marc", "Berger", "m.berger@jura-ass.ch", **K)
    aff_marc = _affilie(session, marc, jura, debut=j(-240), poste="Responsable ALM")
    # Un capital garanti ne paie pas de coupon : `coupon` reste à None, et
    # l'écran doit afficher « — » et non « 0 % ». C'est le cas qui distingue
    # une absence de donnée d'un niveau nul.
    _histo(session, jura, aff_marc, j(-200), emetteur="Société Générale",
           produit="Capital garanti", nominal=2_000_000.0, maturite_mois=60,
           sous_jacent="^STOXX50E", protection=100.0, avec_nous=True,
           prix=100.00, lot=lot.id, entity_id=entity_id)
    _histo(session, jura, aff_marc, j(-103), emetteur="BNP Paribas",
           produit="Autocall Athena", nominal=1_800_000.0, maturite_mois=36,
           sous_jacent="^STOXX50E", coupon=7.20, protection=60.0,
           lot=lot.id, entity_id=entity_id)
    _opportunite(session, jura, aff_marc, titre="Capital garanti 7Y",
                 statut="won", **K)
    _opportunite(session, jura, aff_marc, titre="Phoenix 5Y CHF", statut="won", **K)
    _opportunite(session, jura, aff_marc, titre="Autocall 3Y",
                 statut="lost", motif="internal_approval", **K)
    # Relance échue depuis 6 jours : c'est la SEULE action possible sur un
    # client dont la cadence est inconnue.
    _interaction(session, jura, j(-19), resume="Comité produit",
                 action="Envoyer l'indicatif 5 ans en CHF", action_le=j(-6),
                 affiliation=aff_marc, **K)
    resume["Jura Assurances"] = "2 transactions, relance échue"

    # ── 3. Fondation Lémanique — zéro transaction ────────────────────
    fondation = _client(session, "Fondation Lémanique", type_client="family_office",
                        statut="prospect", **K)
    claire = _personne(session, "Claire", "Rochat", "c.rochat@fondation-leman.ch", **K)
    aff_claire = _affilie(session, claire, fondation, debut=j(-120), poste="CIO",
                          role="cio")
    _opportunite(session, fondation, aff_claire, titre="Première allocation",
                 statut="need_identified", activite_il_y_a=4, **K)
    _interaction(session, fondation, j(-30), resume="Présentation de la maison",
                 type_="meeting", affiliation=aff_claire, **K)
    _interaction(session, fondation, j(-12), resume="Envoi de trois idées",
                 type_="idea_sent", affiliation=aff_claire, **K)
    resume["Fondation Lémanique"] = "aucune transaction, politique complète"

    # ── 4. Alpes Institutionnel — dormant ────────────────────────────
    # Cadence ~62 j, silence de 210 jours : trois fois son rythme habituel.
    # Le seuil est RELATIF, un trimestriel muet depuis 210 j ne le serait pas.
    alpes = _client(session, "Alpes Institutionnel", type_client="institutional",
                    statut="active", **K)
    pierre = _personne(session, "Pierre", "Girard", "p.girard@alpes-inst.ch", **K)
    aff_pierre = _affilie(session, pierre, alpes, debut=j(-1200))
    for decalage in (-644, -582, -520, -458, -396, -334, -272, -210):
        _histo(session, alpes, aff_pierre, j(decalage), emetteur="UBS",
               produit="Phoenix Memory", nominal=3_000_000.0, lot=lot.id,
               sous_jacent=PANIER_INDICES, coupon=8.10, protection=60.0,
               avec_nous=True, prix=100.00, entity_id=entity_id)
    resume["Alpes Institutionnel"] = "dormant (210 j pour une cadence de 62)"

    # ── 5. Genève Privée — irrégulier malgré le volume ───────────────
    geneve = _client(session, "Genève Privée", type_client="private_bank", **K)
    laure = _personne(session, "Laure", "Chappuis", "l.chappuis@geneve-privee.ch", **K)
    aff_laure = _affilie(session, laure, geneve, debut=j(-1400))
    for decalage in (-1000, -980, -780, -765, -465, -440, -260, -230, -50):
        _histo(session, geneve, aff_laure, j(decalage), emetteur="Vontobel",
               produit="Twin Win", nominal=900_000.0, lot=lot.id,
               sous_jacent="MC.PA", coupon=9.40, protection=65.0,
               entity_id=entity_id)
    # Le seul mono-ETF du jeu : la famille existe dans le catalogue, elle doit
    # aussi exister dans les données, sans quoi rien ne l'aurait jamais rendue.
    _histo(session, geneve, aff_laure, j(-600), emetteur="Natixis",
           produit="Shark", nominal=700_000.0, lot=lot.id,
           sous_jacent="GLD", protection=90.0, avec_nous=False, prix=98.75,
           entity_id=entity_id)
    resume["Genève Privée"] = "9 transactions mais cadence irrégulière"

    # ── 6. Valais Distribution — aucune politique ────────────────────
    # Sans liste autorisée, rien ne peut être qualifié d'écart : c'est le faux
    # positif que le module refuse de produire.
    valais = _client(session, "Valais Distribution", type_client="distributor",
                     contraintes={}, ticket=(None, None), maturite=(None, None),
                     rating=None, **K)
    olivier = _personne(session, "Olivier", "Roux", "o.roux@valais-dist.ch", **K)
    aff_olivier = _affilie(session, olivier, valais, debut=j(-800))
    for index, decalage in enumerate((-500, -469, -438, -407, -376, -345)):
        _histo(session, valais, aff_olivier, j(decalage),
               emetteur=["Natixis", "Marex", "Crédit Agricole"][index % 3],
               produit="Reverse Convertible", nominal=400_000.0, lot=lot.id,
               sous_jacent=["STMPA.PA", "UCG.MI", "TTE.PA"][index % 3],
               coupon=9.00 + (index % 3) * 0.75, protection=70.0,
               avec_nous=index % 2 == 0, prix=99.50 if index % 2 else 100.00,
               entity_id=entity_id)
    resume["Valais Distribution"] = "sans politique déclarée"

    # ── 7. Léman Family Office — deux comportements opposés ──────────
    # L'agrégat dirait « risque moyen » et ne décrirait personne : c'est le
    # détail par contact qui porte la vérité.
    leman = _client(session, "Léman Family Office", type_client="family_office",
                    ticket=(200_000, 8_000_000), **K)
    prudent = _personne(session, "Henri", "Favre", "h.favre@leman-fo.ch", **K)
    agressif = _personne(session, "Nadia", "Silva", "n.silva@leman-fo.ch", **K)
    aff_prudent = _affilie(session, prudent, leman, debut=j(-1100))
    aff_agressif = _affilie(session, agressif, leman, debut=j(-1100),
                            poste="Gérante", role="portfolio_manager")
    for decalage in (-900, -720, -540, -360, -180):
        _histo(session, leman, aff_prudent, j(decalage), emetteur="UBS",
               produit="Capital garanti", nominal=5_000_000.0,
               maturite_mois=60, sous_jacent="^SSMI", protection=100.0,
               avec_nous=True, prix=100.00, lot=lot.id, entity_id=entity_id)
    # La gérante agressive traite jusqu'à récemment : sans cela la maison
    # ressortait « dormante », ce qui aurait masqué le point de cette société —
    # deux profils opposés sous un même toit, pas un problème d'activité.
    for decalage in (-240, -210, -180, -150, -120, -90, -60, -28):
        _histo(session, leman, aff_agressif, j(decalage), emetteur="Leonteq",
               produit="Phoenix Memory", nominal=350_000.0, maturite_mois=18,
               sous_jacent=PANIER_BANQUES, coupon=13.50, protection=50.0,
               avec_nous=True, prix=100.00, lot=lot.id, entity_id=entity_id)
    resume["Léman Family Office"] = "deux contacts aux profils opposés"

    # ── 8 et 9. Le changement de société ─────────────────────────────
    # Anne traite chez Helvetia, puis rejoint Zurich Partners. Ses
    # transactions d'avant RESTENT chez Helvetia : c'est la garantie que tout
    # le modèle existe pour tenir.
    helvetia = _client(session, "Bank Helvetia", type_client="bank", **K)
    zurich = _client(session, "Zurich Partners", type_client="asset_manager", **K)
    anne = _personne(session, "Anne", "Keller", "a.keller@zurich-partners.ch", **K)
    aff_avant = _affilie(session, anne, helvetia, debut=j(-1600), fin=j(-400),
                         poste="Gérante")
    aff_apres = _affilie(session, anne, zurich, debut=j(-390), poste="CIO",
                         role="cio")
    for decalage in (-1400, -1310, -1220, -1130, -1040):
        _histo(session, helvetia, aff_avant, j(decalage), emetteur="Citi",
               produit="Autocall Athena", nominal=2_500_000.0, lot=lot.id,
               sous_jacent=PANIER_SUISSE, coupon=7.60, protection=60.0,
               avec_nous=True, prix=100.00, entity_id=entity_id)
    # Anne garde son rythme de 90 jours chez son nouvel employeur — c'est ce
    # que la comparaison doit faire ressortir : une cadence personnelle qui
    # résiste au changement de maison.
    for decalage in (-360, -270, -180, -90):
        _histo(session, zurich, aff_apres, j(decalage), emetteur="Citi",
               produit="Autocall Athena", nominal=2_500_000.0, lot=lot.id,
               sous_jacent=PANIER_SUISSE, coupon=7.60, protection=60.0,
               avec_nous=True, prix=100.00, entity_id=entity_id)
    # Un autre contact chez Zurich, à cadence bien plus rapide : c'est lui qui
    # rend la comparaison « elle / la maison » possible. Il traite jusqu'à
    # récemment, pour que la société ne ressorte pas dormante — ce qui n'est
    # pas le sujet de ces deux fiches.
    thomas = _personne(session, "Thomas", "Blanc", "t.blanc@zurich-partners.ch", **K)
    aff_thomas = _affilie(session, thomas, zurich, debut=j(-700))
    for decalage in (-210, -180, -150, -120, -90, -60, -30, -8):
        # Un ticker volontairement hors catalogue : la fiche doit dire « nature
        # inconnue » plutôt que de le ranger au hasard dans une famille.
        _histo(session, zurich, aff_thomas, j(decalage), emetteur="UBS",
               produit="Phoenix Memory", nominal=1_000_000.0, lot=lot.id,
               sous_jacent="NESN.SW", coupon=12.30, protection=55.0,
               avec_nous=False, prix=99.25, entity_id=entity_id)
    resume["Bank Helvetia → Zurich Partners"] = "changement de société d'Anne Keller"

    lot.rows_created = len(session.new)
    session.add(lot)
    session.commit()
    return resume


# ══════════════════════════════════════════════════════════════════════
#  Retrait
# ══════════════════════════════════════════════════════════════════════

def purger(session: Session) -> dict:
    """Retire ce que ce script a créé, et rien d'autre.

    Identifie par le nom EXACT des sociétés du jeu. Une société réelle qui
    porterait le même nom serait emportée — d'où des noms volontairement
    fictifs et reconnaissables.
    """
    clients = list(session.exec(
        select(Client).where(Client.name.in_(SOCIETES))).all())
    if not clients:
        return {"clients": 0}

    ids = [c.id for c in clients]
    affiliations = list(session.exec(
        select(Affiliation).where(Affiliation.client_id.in_(ids))).all())
    aff_ids = [a.id for a in affiliations]
    person_ids = {a.person_id for a in affiliations}
    opportunites = list(session.exec(
        select(Opportunity).where(Opportunity.client_id.in_(ids))).all())
    opp_ids = [o.id for o in opportunites]
    interactions = list(session.exec(
        select(Interaction).where(Interaction.client_id.in_(ids))).all())
    inter_ids = [i.id for i in interactions]
    compte = {}

    # Tout est LU d'abord, puis supprimé par vagues, la plus dépendante en
    # premier, avec un flush entre chaque.
    #
    # Entrelacer lectures et suppressions ne marchait pas : une requête
    # déclenche un autoflush de SQLAlchemy, qui envoyait le DELETE d'une
    # interaction avant celui de ses participants — « FOREIGN KEY constraint
    # failed » sur la vraie base. Invisible en test, où le moteur créé à la
    # main n'a pas le PRAGMA foreign_keys=ON que `database.py` pose sur le sien.
    def _vague(lignes, cle=None):
        for ligne in lignes:
            session.delete(ligne)
        session.flush()
        if cle:
            compte[cle] = len(lignes)

    _vague(session.exec(select(InteractionParticipant).where(
        InteractionParticipant.interaction_id.in_(inter_ids or [-1]))).all())
    _vague(session.exec(select(OpportunityParticipant).where(
        OpportunityParticipant.opportunity_id.in_(opp_ids or [-1]))).all())
    _vague(session.exec(select(RfqRequest).where(
        RfqRequest.opportunity_id.in_(opp_ids or [-1]))).all(), "rfqs")
    _vague(session.exec(select(Deal).where(Deal.client_id.in_(ids))).all(), "deals")
    _vague(session.exec(select(ClientTradeHistory).where(
        ClientTradeHistory.client_id.in_(ids))).all(), "transactions")
    _vague(interactions, "interactions")
    _vague(opportunites, "opportunites")
    _vague(session.exec(select(ClientCoverage).where(
        ClientCoverage.client_id.in_(ids))).all())
    _vague(affiliations, "affiliations")
    _vague(list(session.exec(select(Person).where(
        Person.id.in_(person_ids or {-1}))).all()), "personnes")
    _vague(clients, "clients")

    for lot in session.exec(
            select(ClientImportBatch).where(
                ClientImportBatch.filename == "jeu de démonstration (script)")).all():
        session.delete(lot)
    session.commit()
    return compte


# ══════════════════════════════════════════════════════════════════════
#  Fichier d'import, pour éprouver l'écran d'import lui-même
# ══════════════════════════════════════════════════════════════════════

def fichier_import() -> dict:
    """Un jeu au FORMAT D'IMPORT, distinct du jeu semé en base.

    Sert à éprouver l'écran d'import de bout en bout : deux sociétés, un
    parcours professionnel complet, des transactions — et volontairement
    quelques lignes fautives, pour voir le rapport d'anomalies faire son
    travail plutôt que de découvrir son comportement en production.
    """
    return {
        "clients": [
            {"name": "Neuchâtel Prévoyance", "client_type": "insurance",
             "country": "Suisse", "status": "active",
             "external_ref": "LEI-DEMO-001"},
            {"name": "Ticino Wealth", "client_type": "private_bank",
             "country": "Suisse", "status": "prospect"},
            {"name": "", "client_type": "asset_manager"},          # ⚠ nom vide
            {"name": "Fribourg Capital", "client_type": "hedge_fund"},  # ⚠ type inconnu
        ],
        "contacts": [
            {"first_name": "Isabelle", "last_name": "Meyer",
             "email": "i.meyer@ne-prevoyance.ch"},
            {"first_name": "Paolo", "last_name": "Conti",
             "email": "p.conti@ticino-wealth.ch"},
        ],
        "affiliations": [
            {"person_email_or_name": "i.meyer@ne-prevoyance.ch",
             "client_name": "Neuchâtel Prévoyance", "job_title": "Directrice ALM",
             "commercial_role": "decision_maker", "start_date": "2021-03-01"},
            {"person_email_or_name": "p.conti@ticino-wealth.ch",
             "client_name": "Ticino Wealth", "job_title": "Gérant",
             "commercial_role": "portfolio_manager", "start_date": "01/09/2023"},
            {"person_email_or_name": "inconnu@nulle-part.ch",   # ⚠ personne absente
             "client_name": "Ticino Wealth", "start_date": "2024-01-01"},
        ],
        "transactions": [
            {"client_name": "Neuchâtel Prévoyance",
             "person_email_or_name": "i.meyer@ne-prevoyance.ch",
             "trade_date": "2023-02-14", "maturity_date": "2028-02-14",
             "product_type": "Capital garanti", "underlying": "^SSMI",
             "issuer": "UBS", "currency": "CHF", "notional": 5000000,
             "barrier_pct": 100, "traded_with_us": "oui", "price_pct": 100,
             "external_ref": "XS-DEMO-01"},
            {"client_name": "Neuchâtel Prévoyance",
             "person_email_or_name": "i.meyer@ne-prevoyance.ch",
             "trade_date": "15/09/2023", "product_type": "Autocall Athena",
             "issuer": "BNP Paribas", "notional": 4000000,
             "underlying": "^STOXX50E", "coupon_pct": 7.4, "barrier_pct": 60,
             # Traitée ailleurs, et à quel prix : le renseignement que ce
             # module existe pour capter.
             "traded_with_us": "non", "price_pct": 99.2,
             "external_ref": "XS-DEMO-02"},
            {"client_name": "Neuchâtel Prévoyance",
             "person_email_or_name": "i.meyer@ne-prevoyance.ch",
             "trade_date": "2024-04-22", "product_type": "Phoenix Memory",
             "issuer": "Société Générale", "notional": 4500000,
             # Un panier dans une seule cellule — c'est ainsi qu'un client
             # écrit son historique.
             "underlying": "MC.PA / OR.PA / KER.PA",
             "coupon_pct": 12.5, "barrier_pct": 55,
             "external_ref": "XS-DEMO-03"},          # exécution non renseignée
            {"client_name": "Ticino Wealth",
             "person_email_or_name": "p.conti@ticino-wealth.ch",
             "trade_date": "2020-01-01",          # ⚠ antérieur à son arrivée
             "product_type": "Autocall", "issuer": "Citi", "notional": 1000000},
            {"client_name": "Société inexistante",  # ⚠ société absente
             "trade_date": "2024-01-01", "product_type": "Autocall"},
        ],
        "interactions": [
            {"client_name": "Neuchâtel Prévoyance", "interaction_date": "2024-01-18",
             "interaction_type": "meeting", "summary": "Revue annuelle"},
            {"client_name": "Ticino Wealth", "interaction_date": "demain",  # ⚠
             "interaction_type": "call", "summary": "Prise de contact"},
        ],
    }


def principal() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--purge", action="store_true",
                           help="retirer le jeu au lieu de le semer")
    analyseur.add_argument("--emit-import", metavar="FICHIER",
                           help="écrire un fichier d'import de démonstration")
    analyseur.add_argument(
        "--entity-id", type=int, default=None,
        help="forcer l'entité ; par défaut, celle du compte --user-id")
    analyseur.add_argument(
        "--user-id", type=int, default=1,
        help="compte propriétaire du jeu — c'est lui qui donne l'entité")
    options = analyseur.parse_args()

    if options.emit_import:
        chemin = Path(options.emit_import)
        chemin.write_text(
            json.dumps(fichier_import(), ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"Fichier d'import écrit : {chemin}")
        print("Il contient volontairement 6 lignes fautives, pour voir le "
              "rapport d'anomalies travailler.")
        return 0

    init_db()
    with Session(engine) as session:
        if options.purge:
            compte = purger(session)
            if not compte.get("clients"):
                print("Rien à retirer : le jeu n'est pas en base.")
                return 0
            print("Retiré :")
            for cle, valeur in sorted(compte.items()):
                print(f"  {valeur:4d}  {cle}")
            return 0

        existants = session.exec(
            select(Client).where(Client.name.in_(SOCIETES))).all()
        if existants:
            print(f"{len(existants)} société(s) du jeu sont déjà en base. "
                  f"Lancez --purge d'abord si vous voulez repartir à neuf.")
            return 1

        entite_compte, nom_compte = entite_du_compte(session, options.user_id)
        entity_id = (options.entity_id if options.entity_id is not None
                     else entite_compte)
        resume = semer(session, entity_id=entity_id, user_id=options.user_id)

    print(f"Jeu semé pour « {nom_compte} » (entity_id={entity_id}), "
          f"dates calées sur le {AUJOURDHUI.isoformat()} :")
    for nom, quoi in resume.items():
        print(f"  · {nom:32s} {quoi}")
    print("\nPour tout retirer :  "
          "python backend/scripts/seed_client_demo.py --purge")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
