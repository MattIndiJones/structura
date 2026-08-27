"""Chantier D — le dividende devient vérifiable, et datable.

L'application lisait `trailingAnnualDividendYield`, un instantané du jour. Il
est juste pour pricer aujourd'hui, mais il ne sait rien dire d'une date passée
— or une valorisation au 8 mai doit voir le marché du 8 mai — et il tombe à
zéro sur un titre qui a suspendu son dividende, sans distinguer « ne verse
pas » de « donnée absente ».

Les tests fabriquent leurs séries : ce qui est vérifié, c'est l'arithmétique
des deux méthodes, pas la disponibilité de Yahoo.
"""
import math

import pandas as pd
import pytest

from backend.app.services import market_data


class _FauxTitre:
    """Un titre qui verse un dividende connu, avec ses deux séries de cours.

    La série ajustée est déflatée des dividendes postérieurs, exactement comme
    le fait Yahoo : avant le détachement, ratio = 1 − D/C ; après, ratio = 1.
    """

    cours = 100.0
    dividende = 4.0
    ex_date = pd.Timestamp("2026-03-15")

    def __init__(self, ticker):
        self.ticker = ticker
        self._jours = pd.date_range("2025-08-01", "2026-08-27", freq="D")

    def history(self, start=None, end=None, auto_adjust=True, **kw):
        idx = self._jours
        nus = pd.Series(self.cours, index=idx)
        facteur = pd.Series(
            [1.0 - self.dividende / self.cours if d <= self.ex_date else 1.0 for d in idx],
            index=idx)
        serie = nus * facteur if auto_adjust else nus
        fenetre = serie[(serie.index >= pd.Timestamp(start)) & (serie.index < pd.Timestamp(end))]
        return pd.DataFrame({"Close": fenetre.tz_localize("Europe/Paris")})

    @property
    def dividends(self):
        return pd.Series([self.dividende],
                         index=pd.DatetimeIndex([self.ex_date]).tz_localize("Europe/Paris"))


class _TitreSansDividende(_FauxTitre):
    dividende = 0.0

    @property
    def dividends(self):
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]).tz_localize("Europe/Paris"))


@pytest.fixture
def yahoo(monkeypatch):
    monkeypatch.setattr(market_data, "_HAS_YF", True)
    monkeypatch.setattr(market_data, "yf", type("yf", (), {"Ticker": _FauxTitre}))


@pytest.fixture
def yahoo_sans_dividende(monkeypatch):
    monkeypatch.setattr(market_data, "_HAS_YF", True)
    monkeypatch.setattr(market_data, "yf", type("yf", (), {"Ticker": _TitreSansDividende}))


def test_le_rendement_declare_rapporte_les_dividendes_au_cours(yahoo):
    res = market_data.dividend_profile("X.PA", asof="2026-08-27")
    assert res["ok"]
    # Un dividende de 4 sur un cours de 100 : 4 % sur un an.
    assert res["yield_declared"] == pytest.approx(0.04, abs=1e-6)
    assert [d["amount"] for d in res["dividends"]] == [4.0]


def test_le_rendement_implicite_se_lit_dans_l_ecart_des_deux_series(yahoo):
    res = market_data.dividend_profile("X.PA", asof="2026-08-27")
    # Le rapport passe de (1 − 4/100) à 1 : −ln(0,96) sur un an.
    assert res["yield_implied"] == pytest.approx(-math.log(0.96), abs=1e-4)


def test_les_deux_methodes_concordent_a_cours_stable(yahoo):
    res = market_data.dividend_profile("X.PA", asof="2026-08-27")
    # 4,00 % contre 4,08 % : l'écart de convention, pas une anomalie.
    assert res["discrepancy"] < 0.001
    assert res["suspect"] is False


def test_un_titre_qui_ne_verse_pas_est_dit_tel(yahoo_sans_dividende):
    res = market_data.dividend_profile("Y.PA", asof="2026-08-27")
    assert res["ok"] is True
    assert res["pays_dividends"] is False
    assert res["yield_declared"] == 0.0
    # La distinction qui manquait : zéro parce qu'il ne verse pas, et on le sait.


def test_une_divergence_forte_est_signalee(yahoo, monkeypatch):
    """Le flux de dividendes ampute d'une opération sur titre.

    C'est ce qui arrive réellement sur Stellantis : la série ajustée porte une
    correction que la liste des dividendes n'explique pas."""
    monkeypatch.setattr(_FauxTitre, "dividends",
                        property(lambda self: pd.Series(dtype=float,
                                                        index=pd.DatetimeIndex([]).tz_localize("Europe/Paris"))))
    res = market_data.dividend_profile("X.PA", asof="2026-08-27")
    assert res["yield_declared"] == 0.0
    assert res["yield_implied"] > 0.03      # les cours, eux, savent
    assert res["suspect"] is True


def test_le_rendement_se_calcule_a_une_date_passee(yahoo):
    """Ce que le champ instantané de Yahoo ne sait pas faire.

    Au 1er mars, le dividende du 15 n'est pas encore détaché : la fenêtre des
    douze mois précédents est vide."""
    res = market_data.dividend_profile("X.PA", asof="2026-03-01")
    assert res["yield_declared"] == 0.0
    res_apres = market_data.dividend_profile("X.PA", asof="2026-08-27")
    assert res_apres["yield_declared"] > 0.03


def test_un_ticker_muet_est_signale_sans_zero_silencieux(monkeypatch):
    class _Vide:
        def __init__(self, t): pass
        def history(self, **kw): return pd.DataFrame()
        dividends = pd.Series(dtype=float)

    monkeypatch.setattr(market_data, "_HAS_YF", True)
    monkeypatch.setattr(market_data, "yf", type("yf", (), {"Ticker": _Vide}))
    res = market_data.dividend_profile("ZZZZ.XX")
    assert res["ok"] is False
    assert "ZZZZ.XX" in res["error"]
