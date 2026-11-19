"""Parcours 2 à 5 — pricer, booker, suivre en risque, consulter le marché.

Chaque parcours passe par l'écran, comme un structureur, et prépare par l'API
seulement ce qui n'est pas l'objet du parcours (un script enregistré). Les
données de marché sont saisies : aucun parcours ne dépend d'un téléchargement.
"""
import re

from playwright.sync_api import expect

from conftest import book_from_pricer, price_in_pricer, settle


def test_parcours_pricer_price_par_la_file_et_annule(signed_in, instance, saved_script):
    """Parcours 2 — un prix passe par la file de calcul ; un calcul long s'annule."""
    page = signed_in
    price_in_pricer(page, instance, saved_script("Parcours pricer"))
    expect(page.get_by_text(re.compile(r"^\d{2,3}\.\d{2}%$")).first).to_be_visible()
    page.get_by_role("button", name="📊 Résultats", exact=True).click()
    expect(page.get_by_text("Prix équitable", exact=False).first).to_be_visible()

    # 200 000 trajectoires : assez long pour être annulé en cours de route,
    # sous le seuil qui demande une confirmation de calcul lourd.
    page.goto(f"{instance.url}/#/pricer/{saved_script('Parcours pricer long', paths=200_000)}")
    settle(page)
    with page.expect_response(lambda r: r.url.endswith("/api/price/jobs/price") and r.request.method == "POST") as submitted:
        page.get_by_role("button", name="▶ Pricer", exact=True).click()
    assert submitted.value.status == 202, submitted.value.text()
    with page.expect_response(lambda r: "/api/price/jobs/" in r.url and r.request.method == "DELETE") as cancelled:
        page.get_by_role("button", name="Annuler", exact=True).click()
    assert cancelled.value.status == 200, cancelled.value.text()
    expect(page.get_by_role("button", name="▶ Pricer", exact=True)).to_be_enabled(timeout=30_000)


def test_parcours_booking_du_pricer_a_la_fiche(signed_in, instance, saved_script, dates):
    """Parcours 3 — booker depuis le Pricer, retrouver le deal, ouvrir sa fiche et son choc."""
    page = signed_in
    price_in_pricer(page, instance, saved_script("Parcours booking"))
    deal = book_from_pricer(page, dates["strike"])

    page.goto(f"{instance.url}/#/booking")
    expect(page.get_by_role("heading", name="Booking — produits bookés")).to_be_visible()
    page.get_by_role("button", name=re.compile(r"^Deals \(\d+\)$")).click()
    card = page.locator(f"#deal-{deal['id']}")
    expect(card).to_contain_text(deal["reference"])
    expect(card).to_contain_text("BNP Paribas")

    card.locator(".deal-card__header").click()
    expect(card.get_by_text("Chargement du détail…")).to_have_count(0, timeout=30_000)
    card.get_by_role("button", name="⚡ Choc").click()
    expect(card.get_by_role("button", name=re.compile("Lancer|Appliquer"))).to_be_visible()

    # Le lien profond de Risk Management rouvre la même fiche.
    page.goto(f"{instance.url}/#/booking?deal={deal['id']}")
    expect(page.locator(f"#deal-{deal['id']}").locator(".deal-overview-grid")).to_be_visible()


def test_parcours_risque_portefeuille_et_choc(signed_in, instance, structureur, saved_script, dates):
    """Parcours 4 — créer un portefeuille, y ranger un deal, le choquer."""
    page = signed_in
    price_in_pricer(page, instance, saved_script("Parcours risque"))
    deal = book_from_pricer(page, dates["strike"])

    page.goto(f"{instance.url}/#/risk?tab=portfolios")
    page.get_by_label("Nom du portefeuille").fill("Parcours — book EUR")
    page.get_by_role("button", name="＋ Créer").click()
    expect(page.get_by_text("Portefeuille « Parcours — book EUR » créé", exact=False)).to_be_visible()

    # Affectation par le menu de la ligne du deal, qui dit « Non classé ».
    row = page.locator("tr").filter(has_text=deal["reference"])
    row.locator("summary", has_text="Non classé").click()
    with page.expect_response(lambda r: r.url.endswith(f"/api/deals/{deal['id']}/portfolios")):
        row.get_by_label("Parcours — book EUR").check()
    expect(page.get_by_text(f"{deal['reference']} ajouté à « Parcours — book EUR »", exact=False)).to_be_visible()

    page.goto(f"{instance.url}/#/risk?tab=chocs")
    page.get_by_role("button", name=re.compile("Parcours — book EUR")).first.click()
    with page.expect_response(lambda r: "/shock" in r.url and r.request.method == "POST", timeout=120_000) as shocked:
        page.get_by_role("button", name="Lancer le choc").click()
    assert shocked.value.status < 500, shocked.value.text()
    for tab in ("greeks", "contreparties", "var", "pnl", "smile", "barrieres"):
        page.goto(f"{instance.url}/#/risk?tab={tab}")
        expect(page.get_by_role("heading", name="Risk Management")).to_be_visible()


def test_parcours_rfq_depuis_le_pricer(signed_in, instance, structureur, saved_script):
    """Parcours 5 — ouvrir une RFQ sur le produit pricé, la créer, la retrouver."""
    page = signed_in
    price_in_pricer(page, instance, saved_script("Parcours RFQ"))
    page.get_by_role("button", name="Ouvrir une RFQ").click()
    expect(page.get_by_role("heading", name="Nouvelle RFQ")).to_be_visible()

    page.get_by_placeholder("Autocall Athena USD 3Y — Client X").fill("RFQ parcours — RC AIR.PA 1Y")
    page.locator("label", has_text="Desk pilote").locator("..").locator("select").select_option(str(structureur.desk_id))
    with page.expect_response(lambda r: r.url.endswith("/api/rfq") and r.request.method == "POST") as created:
        page.get_by_role("button", name="Créer la RFQ").click()
    assert created.value.status == 201, created.value.text()
    rfq = created.value.json()

    expect(page.locator("aside")).to_contain_text("RFQ parcours — RC AIR.PA 1Y")
    expect(page.get_by_text("Fournisseurs sollicités")).to_be_visible()
    page.goto(f"{instance.url}/#/rfq")
    page.locator("aside").get_by_text("RFQ parcours — RC AIR.PA 1Y").click()
    expect(page.get_by_text(rfq["reference"]).first).to_be_visible()
