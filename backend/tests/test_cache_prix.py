"""Cache d'historique — un appel réseau par panier, pas un par valorisation.

Une valorisation en cours de vie reconstruit son contexte résiduel, donc
retélécharge tout l'historique depuis le strike. Chaque analytique le refait, et
le comparateur de déclinaisons le refait UNE FOIS PAR LIGNE.

Mesuré sur le dossier de référence : quatre tickers, sept déclinaisons, soit
trente-deux requêtes Yahoo séquentielles pour un historique rigoureusement
identique. Plusieurs minutes d'attente, et le régime où Yahoo se met à limiter
les appels.

Ces tests comptent les appels RÉELS. Vérifier que le prix est juste ne dirait
rien du nombre de fois qu'on est allé le chercher.
"""
import pandas as pd
import pytest

import backend.app.services.market_data as md


@pytest.fixture
def source(monkeypatch):
    """Une source qui compte ses interrogations."""
    compteur = {"n": 0}
    index = pd.to_datetime(["2024-06-14", "2024-06-17", "2024-06-18"])

    class _Hist:
        empty = False
        columns = ["Close"]
        def __init__(self): self._i = index
        def __getitem__(self, k): return pd.Series([100.0, 101.0, 99.0], index=self._i)
        @property
        def index(self): return self._i
        @index.setter
        def index(self, v): self._i = v

    class _Ticker:
        def __init__(self, tk): compteur["n"] += 1
        def history(self, **kw): return _Hist()

    monkeypatch.setattr(md, "yf", type("YF", (), {"Ticker": _Ticker}))
    monkeypatch.setattr(md, "_HAS_YF", True)
    md.vider_cache_prix()
    yield compteur
    md.vider_cache_prix()


def test_le_meme_historique_n_est_telecharge_qu_une_fois(source):
    """Le cas du comparateur : huit valorisations du même panier."""
    for _ in range(8):
        md.load_hist_prices(["A.PA", "B.MI"], "2024-06-14", "2026-06-14")
    assert source["n"] == 2, "deux tickers, un seul téléchargement chacun"


def test_l_ordre_des_tickers_ne_cree_pas_deux_entrees(source):
    """Deux appels au même panier dans un ordre différent décrivent le même
    historique — la clé les rapproche."""
    md.load_hist_prices(["A.PA", "B.MI"], "2024-06-14", "2026-06-14")
    md.load_hist_prices(["B.MI", "A.PA"], "2024-06-14", "2026-06-14")
    assert source["n"] == 2


@pytest.mark.parametrize("variation", [
    {"tickers": ["A.PA", "C.PA"]},
    {"start": "2024-01-01"},
    {"end": "2025-01-01"},
    {"adjusted": True},
])
def test_une_demande_differente_retelecharge(source, variation):
    """Le cache ne doit jamais rendre l'historique d'une AUTRE demande. Un cours
    ajusté n'est pas un cours nu, et une fenêtre plus longue n'est pas la même
    série — les confondre donnerait des fixings faux."""
    base = dict(tickers=["A.PA", "B.MI"], start="2024-06-14", end="2026-06-14")
    md.load_hist_prices(**base)
    avant = source["n"]
    md.load_hist_prices(**{**base, **variation})
    assert source["n"] > avant


def test_le_cache_expire(source, monkeypatch):
    """TTL court plutôt que cache de session : en séance, un cours doit pouvoir
    bouger."""
    md.load_hist_prices(["A.PA"], "2024-06-14", "2026-06-14")
    assert source["n"] == 1
    faux_temps = md.time.monotonic() + md._TTL_PRIX + 1
    monkeypatch.setattr(md.time, "monotonic", lambda: faux_temps)
    md.load_hist_prices(["A.PA"], "2024-06-14", "2026-06-14")
    assert source["n"] == 2


def test_l_appelant_ne_peut_pas_muter_le_cache(source):
    """Le payload est partagé entre appels : si un appelant y écrivait, le
    suivant lirait sa modification."""
    a = md.load_hist_prices(["A.PA"], "2024-06-14", "2026-06-14")
    a["dates"] = []
    a["injecte"] = True
    b = md.load_hist_prices(["A.PA"], "2024-06-14", "2026-06-14")
    assert b["dates"] and "injecte" not in b


def test_une_erreur_n_est_pas_mise_en_cache(monkeypatch):
    """Figer une panne réseau la rejouerait deux minutes durant, alors qu'un
    simple réessai passerait."""
    appels = {"n": 0}

    class _Casse:
        def __init__(self, tk): appels["n"] += 1
        def history(self, **kw): raise RuntimeError("réseau")

    monkeypatch.setattr(md, "yf", type("YF", (), {"Ticker": _Casse}))
    monkeypatch.setattr(md, "_HAS_YF", True)
    md.vider_cache_prix()
    for _ in range(3):
        assert "error" in md.load_hist_prices(["A.PA"], "2024-06-14", "2026-06-14")
    assert appels["n"] == 3, "chaque tentative doit réellement réessayer"
    md.vider_cache_prix()
