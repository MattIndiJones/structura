"""L'écran d'erreur global remplace la page blanche (P1-10, U1).

Le cas réel : `npm run build` supprime les fragments à empreinte de l'ancienne
version, et un onglet resté ouvert les demande encore. Ici le fragment de
l'écran FIFO est refusé par le réseau : la page doit se recharger une fois sur
la route demandée, puis, le fragment manquant toujours, l'expliquer.
"""
from playwright.sync_api import expect


def test_un_fragment_introuvable_recharge_une_fois_puis_explique(signed_in, instance, request):
    request.node.expects_error_screen = True
    page = signed_in
    page.route("**/assets/FifoView-*.js", lambda route: route.abort())
    loads = []
    page.on("load", lambda _: loads.append(page.url))

    page.evaluate("window.location.hash = '#/fifo'")
    screen = page.locator("#app-error")
    expect(screen).to_be_visible()
    expect(screen).to_contain_text("Une nouvelle version de Structura est installée")
    assert len(loads) == 1, f"un seul rechargement attendu, vus : {loads}"
    assert loads[0].endswith("#/fifo"), loads
    expect(screen.get_by_role("button", name="Recharger la page")).to_be_visible()

    # Le fragment revient (nouvelle version servie) : recharger suffit.
    page.unroute("**/assets/FifoView-*.js")
    page.evaluate("sessionStorage.removeItem('structura_fragment_reload_at')")
    screen.get_by_role("button", name="Recharger la page").click()
    expect(page.get_by_role("heading", name="Carnet d'ordres — FIFO")).to_be_visible()
    expect(page.locator("#app-error")).to_have_count(0)
