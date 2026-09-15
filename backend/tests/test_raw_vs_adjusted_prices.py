"""Chantier C — un payoff se lit sur le cours nu, jamais sur le cours ajusté.

Le cours ajusté de Yahoo déflate rétroactivement les prix passés de tous les
dividendes détachés depuis. Une barrière testée dessus est franchie plus tard
qu'en réalité, ou jamais. Le cas réel qui a révélé le défaut : le strike d'une
note Marex au 14/06/2024 sur Société Générale vaut 22,150 — le cours nu — là
où la série ajustée dit 21,105, soit 4,7 % d'écart.

Les tests ne touchent pas le réseau : ils vérifient la question posée à Yahoo,
pas la réponse qu'il renvoie.
"""
import pandas as pd
import pytest
import math

from backend.app.services import market_data


class _FakeHistory:
    """Enregistre les arguments reçus et rend deux séries distinctes selon
    auto_adjust, comme le vrai Yahoo."""

    appels: list[dict] = []

    def __init__(self, ticker):
        self.ticker = ticker

    def history(self, **kwargs):
        _FakeHistory.appels.append(dict(kwargs, ticker=self.ticker))
        # 22,150 nu / 21,105 ajusté : les valeurs réelles de GLE.PA au 14/06/2024.
        close = 21.105 if kwargs.get("auto_adjust") else 22.150
        return pd.DataFrame(
            {"Close": [close]},
            index=pd.DatetimeIndex(["2024-06-14"], tz="Europe/Paris"),
        )


@pytest.fixture(autouse=True)
def _yahoo_factice(monkeypatch):
    _FakeHistory.appels = []
    monkeypatch.setattr(market_data, "_HAS_YF", True)
    monkeypatch.setattr(market_data, "yf", type("yf", (), {"Ticker": _FakeHistory}))


def test_par_defaut_on_recoit_le_cours_nu():
    res = market_data.load_hist_prices(["GLE.PA"], "2024-06-14", "2024-06-15")
    assert _FakeHistory.appels[0]["auto_adjust"] is False
    assert res["prices"]["GLE.PA"] == [22.15]


def test_le_cours_ajuste_reste_accessible_mais_doit_etre_demande():
    res = market_data.load_hist_prices(["GLE.PA"], "2024-06-14", "2024-06-15",
                                       adjusted=True)
    assert _FakeHistory.appels[0]["auto_adjust"] is True
    assert res["prices"]["GLE.PA"] == [21.105]


def test_l_estimation_de_volatilite_garde_le_rendement_total():
    # L'autre chargeur, lui, veut bien la série ajustée : une volatilité se
    # mesure sur le rendement total, dividendes réinvestis.
    market_data.load_hist_vol(["GLE.PA"], period="1y")
    assert _FakeHistory.appels[0]["auto_adjust"] is True


def test_la_calibration_datee_utilise_la_meme_fenetre_que_le_mtm(monkeypatch):
    calls = []
    prices = [100.0 * math.exp(0.01 * i) for i in range(300)]

    def history_loader(tickers, start, end=None, adjusted=False, provider="YAHOO_FINANCE"):
        calls.append({"tickers": tickers, "start": start, "end": end,
                      "adjusted": adjusted, "provider": provider})
        return {
            "dates": [f"2025-01-{(i % 28) + 1:02d}" for i in range(300)],
            "prices": {ticker: prices for ticker in tickers},
            "provider": "YAHOO_FINANCE", "price_type": "ADJUSTED_CLOSE",
            "asof_effective": "2026-09-11",
            "effective_dates": {ticker: "2026-09-11" for ticker in tickers},
            "age_sessions": {ticker: 0 for ticker in tickers},
            "warnings": [], "fetched_at": "2026-09-13T10:00:00",
        }

    monkeypatch.setattr(market_data, "load_hist_prices", history_loader)
    res = market_data.load_hist_vol(
        ["GLE.PA"], asof="2026-09-13", window_days=252)

    assert calls[0]["end"] == "2026-09-13"
    # La fenêtre est celle du MtM résiduel au sens propre : le même calcul de
    # début, désormais partagé (il ne l'était pas avant le 14/09/2026).
    from backend.app.core.calibration import calibration_history_start
    from datetime import date
    assert calls[0]["start"] == calibration_history_start(date(2026, 9, 13), 252).isoformat()
    assert calls[0]["adjusted"] is True
    assert res["requested_asof"] == "2026-09-13"
    assert res["asof_effective"] == "2026-09-11"
    assert res["n_obs"] == 252
    assert res["vols"]["GLE.PA"] == pytest.approx(math.sqrt(252) * 0.01)


def test_les_fixings_contractuels_etaient_deja_sur_le_cours_nu():
    # Ce chargeur-là avait déjà la bonne doctrine ; le défaut portait sur
    # l'autre, ce qui faisait diverger le replay de ses propres fixings.
    market_data.load_yahoo_reference_closes(["GLE.PA"], "2024-06-14", "2024-06-14")
    assert all(appel["auto_adjust"] is False for appel in _FakeHistory.appels)


def test_la_borne_de_fin_est_inclusive_et_la_provenance_est_exposee():
    res = market_data.load_hist_prices(
        ["GLE.PA"], "2024-06-13", "2024-06-14")

    assert _FakeHistory.appels[0]["end"] == "2024-06-15"
    assert res["dates"] == ["2024-06-14"]
    assert res["provider"] == "YAHOO_FINANCE"
    assert res["price_type"] == "UNADJUSTED_CLOSE"
    assert res["asof_effective"] == "2024-06-14"
    assert res["effective_dates"] == {"GLE.PA": "2024-06-14"}
    assert res["age_sessions"] == {"GLE.PA": 0}
