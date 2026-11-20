"""Parcours 1 — connexion, puis chaque écran du menu s'ouvre.

40 vues sur 45 n'avaient aucun test d'écran (audit du 16/11, U4). Ce parcours
ne vérifie pas leur contenu : il vérifie que chacune se charge, rend son titre
et ne lève rien. C'est exactement ce qu'un fragment manquant ou une exception
de rendu cassaient sans bruit.
"""
import pytest
from playwright.sync_api import expect

from conftest import login, settle

# Route → titre principal attendu. Les écrans réservés à l'administration
# technique sont parcourus avec le compte technique, plus bas.
BUSINESS_SCREENS = [
    ("/scripts", "Mes Scripts"),
    ("/pricer", "PAYSCRIPT"),
    ("/products", "Mes Produits"),
    ("/product-models", "Modèles de produits"),
    ("/documentation", "Bibliothèque de documents"),
    ("/booking", "Booking — produits bookés"),
    ("/valo-explain", "Valo Explain"),
    ("/risk", "Risk Management"),
    ("/risk/ccr", "Risque de crédit de contrepartie — CCR"),
    ("/reinvest", "Réinvestissement — alternatives à un produit en vie"),
    ("/amc", "Analyse AMC"),
    ("/fifo", "Carnet d'ordres — FIFO"),
    ("/clients/apercu", "Vue d’ensemble"),
    ("/clients/liste", "Clients"),
    ("/clients/contacts", "Contacts"),
    ("/clients/opportunites", "Opportunités"),
    ("/clients/signaux", "Cycles & Signaux"),
    ("/clients/analytics", "Analytics"),
    ("/clients/import", "Import d’historique"),
    ("/rfq", "RFQ Fournisseurs"),
    ("/rfq/recues", "RFQ reçues"),
    ("/rfq/analyse", "Analyse Contreparties"),
    ("/rfq/prototype-reseau", "Parcours RFQ réseau"),
    ("/structuring", "Structuring Intelligence"),
    ("/structuring/optimizer", "Product Optimizer"),
    ("/structuring/researches", "Recherches & pricings"),
    ("/trading", "Relations et exécutions"),
    ("/account/security", "Sécurité du compte"),
]

ADMIN_SCREENS = [
    ("/admin", "Administration"),
    ("/admin/rfq-relations", "Relations RFQ"),
    ("/admin/rfq-providers", "Fournisseurs RFQ"),
    ("/admin/counterparties", "Contreparties deals"),
    ("/admin/browse", "Données de l'application"),
    ("/admin/users", "Utilisateurs"),
    ("/admin/entities", "Entités"),
    ("/admin/underlyings", "Sous-jacents"),
    ("/admin/market-data", "Données de marché"),
    ("/admin/compute", "Files de calcul"),
    ("/admin/uat-generator", "Générateur UAT"),
]


def _visit(page, instance, screens):
    for route, title in screens:
        page.goto(f"{instance.url}/#{route}")
        heading = page.get_by_role("heading", name=title, exact=False).first
        try:
            expect(heading).to_be_visible()
        except AssertionError as error:
            dialog = page.get_by_role("dialog")
            seen = dialog.first.inner_text() if dialog.count() else page.locator("h1").all_inner_texts()
            raise AssertionError(f"{route} : titre « {title} » absent ; adresse {page.url} ; vu : {seen}") from error
        # Leave a screen only once it has loaded. Valo Explain refuses to be
        # left while it is busy, even during its first, read-only load — and
        # says nothing: the address simply does not change.
        settle(page)


def test_un_structureur_ouvre_chaque_ecran_metier(signed_in, instance):
    expect(signed_in.get_by_role("heading", name="Bonjour, structureur")).to_be_visible()
    _visit(signed_in, instance, BUSINESS_SCREENS)


def test_l_administration_ouvre_ses_ecrans(page, instance):
    class Technical:
        username, password = instance.username, instance.password
    login(page, instance, Technical)
    _visit(page, instance, ADMIN_SCREENS)


def test_une_route_inconnue_ramene_a_l_accueil(signed_in, instance):
    signed_in.goto(f"{instance.url}/#/cette-page-n-existe-pas")
    expect(signed_in.get_by_role("heading", name="Bonjour, structureur")).to_be_visible()


def test_on_quitte_valo_explain_pendant_son_chargement(signed_in, instance):
    """Constat du 19/11 : pendant son chargement, qui ne fait que lire, Valo
    Explain refusait qu'on le quitte, sans rien dire. La liste des notes est
    retenue ici pour que l'écran reste en chargement le temps du départ."""
    page = signed_in
    held = []
    page.route("**/api/valuation-notes", lambda route: held.append(route))
    page.goto(f"{instance.url}/#/valo-explain")
    expect(page.get_by_text("Chargement de Valo Explain")).to_be_visible()
    page.goto(f"{instance.url}/#/risk")
    expect(page.get_by_role("heading", name="Risk Management")).to_be_visible()
    for route in held:
        route.abort()
