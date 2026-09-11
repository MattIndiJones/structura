"""Le rejeu lit chaque date à sa date — §23.

Il lisait une date à `round(t × 252)` séances de son départ. Sur une fenêtre
quotidienne, deux relevés partageaient une séance : un même cours compté deux
fois, un autre jamais (§22). Au rejeu officiel, les fixings de ces deux relevés
s'écrasaient sur la grille synthétique. Et les temps rendus n'étaient plus ceux
du contrat : un rappel pouvait être attribué au relevé de la veille, et le
remboursement d'une maturité calendaire ne se retrouvait plus.

Rien de lourd ici : des rejeux sur quelques centaines de séances, aucun
Monte-Carlo.
"""
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.app.api import deals as deals_api
from backend.app.core.inlife_valuation import InLifeProduct, build_residual
from backend.app.core.lifecycle_controls import replay_official_fixings
from backend.app.core.payscript.engine import (
    _ajouter_jours_de_semaine, _jours_de_semaine_entre, derniere_fenetre,
    eval_script_on_history, seances_jusqu_a,
)
from backend.app.core.payscript.parser import parse_script, resolve_constats

STRIKE = date(2026, 9, 14)            # un lundi
TICKER = "^STOXX50E"

CALL_S0_MOYEN = """PARAM STRIKE = 100%
CONSTAT STRIKE_FIX  AVG
CONSTAT MATURITE

AT MATURITE:
  PAY MAX(WOF - STRIKE, 0) "call"
"""

CONSTATS_S0_MOYEN = {
    "STRIKE_FIX": {"date": STRIKE.isoformat(), "window_length": "10D",
                   "window_frequency": "1D"},
    "MATURITE": "2027-09-14",
}

# Les dix relevés de la fenêtre de départ : dix jours ouvrés TARGET.
RELEVES_DEPART = [date(2026, 9, d) for d in (14, 15, 16, 17, 18, 21, 22, 23, 24, 25)]

AUTOCALL_MOYENNE = """CONSTAT RAPPEL AVG
CONSTAT MATURITE

AT RAPPEL:
  IF WOF >= 1:
    PAY WOF "rappel"
    STOP

AT MATURITE:
  PAY WOF "remboursement"
"""

# Le rappel du 15/12/2026 moyenne deux clôtures : le 14 et le 15.
CONSTATS_AUTOCALL = {
    "RAPPEL": {"date": "2026-12-15", "window_length": "2D", "window_frequency": "1D"},
    "MATURITE": "2027-09-14",
}

KI_A_MATURITE = """PARAM M_KI_BAR = 60%
CONSTAT MATURITE

AT MATURITE:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""


def _jours_de_semaine(debut: date, n: int) -> list[date]:
    jours, jour = [], debut
    while len(jours) < n:
        if jour.weekday() < 5:
            jours.append(jour)
        jour += timedelta(days=1)
    return jours


def _compile(script, constats):
    return resolve_constats(parse_script(script), constats, anchor=STRIKE, currency="EUR")


def _deal(script, constats, *, T=1.0, maturite="2027-09-14"):
    return SimpleNamespace(
        id=1, script_snapshot=script, devise="EUR", T=T,
        strike_date=STRIKE.isoformat(),
        value_date=(STRIKE + timedelta(days=2)).isoformat(),
        maturity_date=maturite, schedule_json="",
        underlyings_json=json.dumps([{"name": "SX5E", "ticker": TICKER}]),
        market_snapshot_json=json.dumps({"r": 0.0, "user_params": {},
                                         "constats": constats}),
    )


def _evenement(ident, jour, spot, parent=None):
    """Une ligne d'événement telle que le booking la crée : `t_years` arrondi à
    quatre décimales, depuis le strike."""
    return SimpleNamespace(
        id=ident, event_index=ident, event_date=jour.isoformat(),
        t_years=round((jour - STRIKE).days / 365.25, 4),
        spots_json=json.dumps({"SX5E": spot}), parent_event_id=parent)


def _evenements_du_rappel(releve, constatation):
    return [_evenement(1, STRIKE, 100.0),
            _evenement(2, date(2026, 12, 14), releve, parent=3),
            _evenement(3, date(2026, 12, 15), constatation)]


# ── L'arithmétique des jours de semaine ───────────────────────────────

@pytest.mark.parametrize("depart", [STRIKE + timedelta(days=k) for k in range(7)])
def test_avancer_puis_compter_les_jours_de_semaine_se_compensent(depart):
    """La translation d'un calendrier repose sur ces deux opérations : l'une
    doit défaire l'autre, depuis n'importe quel jour de la semaine."""
    for n in range(-12, 13):
        arrivee = _ajouter_jours_de_semaine(depart, n)
        assert _jours_de_semaine_entre(depart, arrivee) == n, (depart, n, arrivee)
        if n:
            assert arrivee.weekday() < 5, (depart, n, arrivee)


# ── Backtest glissant : le calendrier se translate en jours de semaine ─

@pytest.mark.parametrize("depart", range(5))
def test_une_fenetre_quotidienne_lit_dix_seances_quel_que_soit_le_jour_de_depart(depart):
    """Un backtest glissant translate le calendrier du contrat sur chaque jour
    de départ. Transposée à 252 séances par an, une fenêtre de dix jours ouvrés
    lisait les séances 0, 1, 1, 2, 3, 5, 6, 6, 7, 8 ; translatée en jours
    calendaires, démarrée un mercredi, elle tomberait sur deux week-ends. En
    jours de semaine, ce sont dix séances consécutives, du lundi au vendredi.

    Le cours vaut 100 + son rang de séance : la moyenne attendue est exacte."""
    compiled = _compile(CALL_S0_MOYEN, CONSTATS_S0_MOYEN)
    jours = _jours_de_semaine(date(2020, 1, 6), 400)      # depuis un lundi
    px = [100.0 + i for i in range(len(jours))]
    res = eval_script_on_history(compiled, [j.isoformat() for j in jours], {TICKER: px},
                                 depart, 1.0, {}, [TICKER], 0.0)
    assert res["niveaux_initiaux"][TICKER] == pytest.approx(100.0 + depart + 4.5)
    assert res["releves_reportes"] == []


def test_la_derniere_fenetre_garde_tout_son_horizon_dans_l_historique():
    """Un an lu à sa date couvre 261 séances, pas 252. Garder le décompte à 252
    séances par an laissait les dernières fenêtres finir au-delà de
    l'historique : un rendement sans remboursement, compté dans les
    statistiques comme les autres."""
    compiled = _compile(CALL_S0_MOYEN, CONSTATS_S0_MOYEN)
    jours = [j.isoformat() for j in _jours_de_semaine(date(2020, 1, 6), 400)]
    px = {TICKER: [100.0] * len(jours)}
    derniere = derniere_fenetre(compiled, jours, 1.0)
    assert derniere > 0
    lue = eval_script_on_history(compiled, jours, px, derniere, 1.0, {}, [TICKER], 0.0)
    assert len(lue["cash_flows"]) == 1                     # la maturité est lue
    assert seances_jusqu_a(compiled, jours, derniere + 1, 1.0) is None

    ancienne = len(jours) - round(1.0 * 252) - 1
    assert ancienne > derniere
    sans_maturite = eval_script_on_history(compiled, jours, px, ancienne, 1.0, {},
                                           [TICKER], 0.0)
    assert sans_maturite["cash_flows"] == []


# ── Rejeu d'un contrat : un jour sans cotation est un report ────────────

def test_un_releve_sans_cotation_est_reporte_et_signale():
    """Un jour ouvré du contrat où la place n'a pas coté : la dernière clôture
    à cette date ou avant est reprise, et le rejeu le dit. La transposition en
    séances ne pouvait pas le voir — elle ne regardait jamais les dates."""
    compiled = _compile(CALL_S0_MOYEN, CONSTATS_S0_MOYEN)
    jours = [j for j in _jours_de_semaine(STRIKE - timedelta(days=7), 45)
             if j != date(2026, 9, 16)]
    px = [100.0 + max((j - STRIKE).days, 0) for j in jours]
    res = eval_script_on_history(compiled, [j.isoformat() for j in jours], {TICKER: px},
                                 jours.index(STRIKE), 1.0, {}, [TICKER], 0.0,
                                 origine=STRIKE)
    # 100, 101, 101 (le 16 reporté du 15), 103, 104, 107, 108, 109, 110, 111.
    assert res["niveaux_initiaux"][TICKER] == pytest.approx(105.4)
    assert res["releves_reportes"] == [round(2 / 365.25, 6)]


# ── Rejeu officiel : un cours par date ────────────────────────────────

def test_le_rejeu_officiel_lit_chacun_des_dix_fixings_de_la_fenetre_de_depart():
    """Dix fixings officiels, dix cours distincts. Sur la grille à 252 pas, les
    relevés du 15 et du 16 partageaient un pas, comme ceux du 22 et du 23 : le
    second fixing écrasait le premier, S0 valait 104,7 au lieu de 104,5, et
    deux fixings validés ne comptaient pour rien."""
    evenements = [_evenement(1, STRIKE, 100.0)]
    for j, jour in enumerate(RELEVES_DEPART[1:], start=2):
        evenements.append(_evenement(j, jour, 100.0 + (j - 1), parent=1))
    evenements.append(_evenement(20, date(2027, 9, 14), 115.0))
    resultat, echecs = replay_official_fixings(
        _deal(CALL_S0_MOYEN, CONSTATS_S0_MOYEN), evenements)
    assert echecs == []
    assert resultat["outcome"] == "final"
    assert resultat["realized_payout"] == pytest.approx(115.0 / 104.5 - 1.0, abs=1e-8)


def test_deux_fixings_differents_a_la_meme_date_ne_se_departagent_pas_en_silence():
    """Deux lignes à la même date — deux fenêtres qui se chevauchent — portent
    une seule clôture. Si leurs fixings diffèrent, le rejeu refuse plutôt que
    d'en garder un."""
    evenements = [_evenement(1, STRIKE, 100.0),
                  _evenement(2, date(2026, 9, 15), 101.0, parent=1),
                  _evenement(3, date(2026, 9, 15), 101.5, parent=1)]
    resultat, echecs = replay_official_fixings(
        _deal(CALL_S0_MOYEN, CONSTATS_S0_MOYEN), evenements)
    assert resultat is None
    assert echecs[0]["code"] == "OFFICIAL_REPLAY_FIXING_CONFLICT"
    assert echecs[0]["event_date"] == "2026-09-15"


def test_un_rappel_se_decide_sur_ses_deux_fixings_et_se_date_a_sa_constatation():
    """Le rappel du 15/12 moyenne le 14 et le 15. Sur la grille à 252 pas, les
    deux tombaient au pas 63 : le fixing du 15 écrasait celui du 14, et le
    niveau valait 1,06 au lieu de 1,05. Le temps rendu était celui du pas,
    0,25 — plus proche du relevé du 14 que de la constatation du 15 : le rappel
    était attribué au relevé."""
    resultat, echecs = replay_official_fixings(
        _deal(AUTOCALL_MOYENNE, CONSTATS_AUTOCALL), _evenements_du_rappel(104.0, 106.0))
    assert echecs == []
    assert resultat["outcome"] == "callé"
    assert resultat["realized_payout"] == pytest.approx(1.05)
    assert resultat["event_id"] == 3
    assert resultat["event_date"] == "2026-12-15"


def test_le_remboursement_d_une_maturite_calendaire_se_retrouve():
    """Le formulaire garde un tenor rond, 3 ans ; le calendrier finit le
    07/09/2029, à 2,98 ans. Les flux de maturité se reconnaissaient à un temps
    égal au tenor : sur la grille à 252 pas, le temps rendu était celui du pas
    751, et le knock-in se présentait avec 0 % remboursé. L'horizon est celui
    de la date de maturité du deal, comme au booking."""
    evenements = [_evenement(1, STRIKE, 100.0), _evenement(2, date(2029, 9, 7), 50.0)]
    resultat, echecs = replay_official_fixings(
        _deal(KI_A_MATURITE, {"MATURITE": "2029-09-07"}, T=3.0, maturite="2029-09-07"),
        evenements)
    assert echecs == []
    assert resultat["outcome"] == "ki"
    assert resultat["maturity_payout"] == pytest.approx(0.5)
    assert resultat["realized_payout"] == pytest.approx(0.5)


# ── Surveillance sur historique Yahoo ─────────────────────────────────

def test_la_surveillance_decide_le_rappel_sur_les_cours_de_ses_dates():
    """Le rejeu sur historique — celui qui propose une résolution — lisait la
    constatation du 15/12/2026 à 63 séances du strike, soit le 10/12. Le
    sous-jacent passe de 100 à 110 le 14/12 : le rappel se décidait à 1,00 au
    lieu de 1,10, et s'attribuait au relevé du 14."""
    jours = _jours_de_semaine(STRIKE - timedelta(days=7), 90)
    px = [110.0 if j >= date(2026, 12, 14) else 100.0 for j in jours]
    evenements = _evenements_du_rappel(0.0, 0.0) + [_evenement(4, date(2027, 9, 14), 0.0)]
    evaluation = deals_api._evaluate_lifecycle(
        _deal(AUTOCALL_MOYENNE, CONSTATS_AUTOCALL), evenements,
        [j.isoformat() for j in jours], {TICKER: px}, [TICKER])
    assert evaluation["outcome"] == "callé"
    assert evaluation["realized_payout"] == pytest.approx(1.1)
    assert evaluation["event_id"] == 3


# ── Vie résiduelle : la coupe entre le passé et l'avenir ──────────────

PHOENIX_MEMOIRE = """PARAM COUPON = 2%
PARAM M_CPN_BAR = 50%

CONSTAT() OBS

AT OBS:
  SET DUE = DUE + COUPON
  SET CPN = INDIC(WOF >= M_CPN_BAR)
  PAY CPN * DUE
  SET DUE = (1 - CPN) * DUE
"""

CALENDRIER_TRIMESTRIEL = {"OBS": {"start_date": "2024-06-14", "end_date": "2027-06-14",
                                  "roll_date": "2024-09-14", "frequency": "3M",
                                  "stub": "short_last", "convention": "following"}}


@pytest.mark.parametrize("valo", [date(2026, 6, 14), date(2026, 6, 5)])
def test_une_constatation_posterieure_a_la_derniere_cloture_reste_a_simuler(valo):
    """La constatation du lundi 15/06/2026 n'a pas de cours à la valorisation.

    Le dimanche 14, dernière clôture le vendredi 12 : transposée à 252 séances
    par an, elle se rejouait sur la clôture du 21/05. Lue à sa date, elle n'est
    pas passée — mais la coupe au pas hebdomadaire la rangeait avec le passé :
    sans une coupe à la même date que le rejeu, ni rejouée ni simulée, elle
    disparaissait du produit.

    Le vendredi 5, dix jours avant : l'ancien rejeu la lisait déjà, et le script
    résiduel la gardait aussi — son coupon mémoire comptait deux fois."""
    strike = date(2024, 6, 14)
    jours = [j for j in _jours_de_semaine(strike - timedelta(days=7), 540) if j <= valo]
    produit = InLifeProduct(
        script_snapshot=PHOENIX_MEMOIRE,
        underlyings=[{"name": "U1", "ticker": "UL.PA", "ccy": "EUR"}],
        strike_levels={"U1": 100.0}, strike_date=strike,
        value_date=strike + timedelta(days=4),
        tenor=(date(2027, 6, 14) - strike).days / 365.25, currency="EUR",
        payment_date=date(2027, 6, 23),
        market={"constats": CALENDRIER_TRIMESTRIEL, "r": 3.0, "model": "constant"},
    )
    px = {"UL.PA": [100.0 if j <= strike else 40.0 for j in jours]}
    res = build_residual(produit, px, [j.isoformat() for j in jours],
                         (valo - strike).days / 365.25, valo)

    # Sept constatations rejouées, sept coupons de 2 % en mémoire.
    assert res.state["index"] == 7
    assert res.state["memo"]["DUE"] == pytest.approx(0.14)
    # Et la huitième ouvre la vie restante, à sa date comptée depuis la
    # valorisation.
    prochaines = sorted(d for ev in res.residual_script.events if ev.type == "AT"
                        for d in ev.dates)
    assert prochaines[0] == pytest.approx((date(2026, 6, 15) - valo).days / 365.25, abs=1e-6)
