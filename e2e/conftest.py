"""End-to-end journeys (P1-10, U4/U5): the built interface, the real backend, a real browser.

Run from the repository root, after `npm run build` in frontend/:

    python -m pytest e2e -q --basetemp=<temporary folder>

One throwaway backend serves the whole session (structura_instance.py); each
journey arranges its own data, so the order does not matter. A journey fails
on any uncaught exception in the page and on the global error screen, which
is how a broken screen shows itself since U1.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

from structura_instance import running_instance

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend.app, for the templates

SCRIPT_TEMPLATE = "reverse_convertible"


def _business_day(day: date, step: int) -> date:
    while day.weekday() >= 5:
        day += timedelta(days=step)
    return day


@pytest.fixture(scope="session")
def instance(tmp_path_factory):
    with running_instance(tmp_path_factory.mktemp("instance")) as running:
        yield running


@pytest.fixture(scope="session")
def structureur(instance):
    return instance.business()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as playwright:
        launched = playwright.chromium.launch(headless=os.environ.get("STRUCTURA_E2E_HEADED") != "1")
        yield launched
        launched.close()


@pytest.fixture
def page(browser, request) -> Page:
    context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="fr-FR")
    opened = context.new_page()
    opened.set_default_timeout(20_000)
    failures: list[str] = []
    opened.on("pageerror", lambda error: failures.append(f"exception dans la page : {error}"))
    # A native dialog (confirm, alert) is a finding in itself: the interface
    # has its own confirmations (useConfirm). The one native prompt it keeps
    # on purpose is beforeunload, for an unsaved pricing session (App.vue).
    def on_dialog(dialog):
        if dialog.type == "beforeunload":
            dialog.accept()
            return
        failures.append(f"dialogue natif « {dialog.type} » : {dialog.message}")
        dialog.dismiss()
    opened.on("dialog", on_dialog)
    # Requests in flight, for settle(): wait_for_load_state("networkidle")
    # only covers the first page load, not what a screen fetches after a
    # hash navigation.
    # API calls only: a module preload the browser deduplicates never reports
    # its end, and fragments are not what a screen waits for.
    in_flight = set()
    opened.on("request", lambda r: "/api/" in r.url and in_flight.add(r))
    opened.on("requestfinished", lambda r: in_flight.discard(r))
    opened.on("requestfailed", lambda r: in_flight.discard(r))
    opened.in_flight = in_flight
    if os.environ.get("STRUCTURA_E2E_DEBUG") == "1":
        opened.on("console", lambda message: print(f"[console {message.type}] {message.text}"))
        opened.on("request", lambda r: "/api/" in r.url and print(f"[request] {r.method} {r.url}"))
    yield opened
    if not getattr(request.node, "expects_error_screen", False):
        screen = opened.locator("#app-error")
        if screen.count():
            failures.append("écran d'erreur affiché : " + screen.inner_text())
    context.close()
    assert not failures, "\n".join(failures)


def settle(page: Page, quiet_ms: int = 500, timeout_ms: int = 30_000) -> None:
    """Wait until the screen has fetched what it loads: no request in flight for quiet_ms."""
    waited = quiet = 0
    while quiet < quiet_ms:
        if waited > timeout_ms:
            pending = sorted(r.url for r in page.in_flight)
            raise AssertionError(f"requêtes toujours en cours après {timeout_ms} ms : {pending}")
        page.wait_for_timeout(100)
        waited += 100
        quiet = quiet + 100 if not page.in_flight else 0


def login(page: Page, instance, account) -> None:
    page.goto(instance.url + "/#/login")
    page.get_by_label("Identifiant").fill(account.username)
    page.get_by_label("Mot de passe").fill(account.password)
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("heading", name=f"Bonjour, {account.username}")).to_be_visible()


@pytest.fixture
def signed_in(page, instance, structureur) -> Page:
    login(page, instance, structureur)
    return page


@pytest.fixture
def dates():
    strike = _business_day(date.today() - timedelta(days=1), -1)
    maturity = _business_day(strike.replace(year=strike.year + 1), 1)
    payment = maturity
    for _ in range(3):
        payment = _business_day(payment + timedelta(days=1), 1)
    return {"strike": strike.isoformat(), "maturity": maturity.isoformat(), "payment": payment.isoformat()}


@pytest.fixture
def saved_script(structureur, dates):
    """A reverse convertible saved with explicit market inputs: no data download."""
    from backend.app.core.payscript.templates import TEMPLATES

    def create(name: str, paths: int = 2000) -> int:
        params = {"r": 2.5, "T": 1.0, "N": paths, "seed": 42, "model": "constant", "deal_ccy": "EUR",
                  "nominal": 1_000_000, "valuation_date": dates["strike"], "trade_date": dates["strike"],
                  "strike_date": dates["strike"], "value_date": dates["strike"], "maturity_date": dates["maturity"],
                  "payment_date": dates["payment"],
                  "underlyings": [{"name": "S1", "ticker": "AIR.PA", "ccy": "EUR", "spot0": 100, "sigma": 23, "q": 2}],
                  "corr_matrix": [[1]], "funding": {"enabled": False}, "yield_curve_enabled": False}
        saved = structureur.call("POST", "/api/db/scripts", {
            "name": name, "script_text": TEMPLATES[SCRIPT_TEMPLATE]["script"],
            "params_json": json.dumps({"COUPON": 8, "M_KI_BAR": 60}),
            "constats_json": json.dumps({"STARTDATE": {"date": dates["strike"]}, "MATURITYDATE": dates["maturity"]}),
            "global_params_json": json.dumps(params)})
        return saved["id"]

    return create


def price_in_pricer(page: Page, instance, script_id: int) -> None:
    """Open a saved script and price it through the job queue (P1-4).

    On opening, the Pricer reloads sigma, q and correlation from market history
    at the valuation date (stores/pricing/marketData.js) — when the network
    answers. A result computed before that reload lands is discarded as stale
    ("Les paramètres ont changé pendant le calcul"): the journey prices again,
    as a user would, once."""
    page.goto(f"{instance.url}/#/pricer/{script_id}")
    settle(page)
    priced = page.get_by_text(re.compile(r"IC 95% \[\d"))
    stale = page.get_by_text("Les paramètres ont changé pendant le calcul")
    for attempt in range(2):
        with page.expect_response(lambda r: r.url.endswith("/api/price/jobs/price") and r.request.method == "POST") as submitted:
            page.get_by_role("button", name="▶ Pricer", exact=True).click()
        assert submitted.value.status == 202, submitted.value.text()
        expect(priced.or_(stale).first).to_be_visible(timeout=120_000)
        if priced.count():
            return
    raise AssertionError("Le pricing reste écarté comme périmé après deux essais.")


def book_from_pricer(page: Page, trade_date: str, *, counterparty: str = "BNP Paribas (FR)") -> dict:
    page.get_by_role("button", name="📋 Deal", exact=True).click()

    def field(label, tag="input"):
        return page.locator("label").filter(has_text=label).locator("..").locator(tag).first

    page.get_by_role("button", name="↓ Achat — la banque achète, nous vendons", exact=True).click()
    field("Contrepartie", "select").select_option(label=counterparty)
    field("Famille de payoff", "select").select_option(label="Reverse convertible")
    field("Format juridique").fill("EMTN")
    field("Instrument").fill("Note")
    field("Trade date").fill(trade_date)
    field("Prix traité (%)").fill("101")
    page.get_by_role("button", name="📋 Vérifier les paramètres et booker", exact=True).click()
    with page.expect_response(lambda r: r.url.endswith("/api/deals") and r.request.method == "POST", timeout=60_000) as booked:
        page.get_by_role("dialog").get_by_role("button", name="Confirmer le booking", exact=True).click()
    assert booked.value.status in (200, 201), booked.value.text()
    return booked.value.json()
