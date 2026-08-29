"""Variantes — étape 3 : la note neuve (roll).

Un roll n'est pas un avenant paramétré autrement, c'est un autre produit. Le
détenteur vend sa note à sa valeur du jour et en achète une neuve : la première
constatation est aujourd'hui, les cours du jour deviennent le nouveau 100 %, et
il n'y a plus de passé à rejouer. Tout redevient libre — panier, calendrier,
payoff — précisément parce que rien n'est hérité de l'histoire.

Le risque propre à ce mode est le symétrique de celui de l'avenant. Là-bas, le
danger était de rejouer le passé avec les termes nouveaux ; ici, c'est de
pricer la note neuve sur l'axe des temps de l'ancienne. Les niveaux initiaux du
term sheet d'origine sont le piège précis : les laisser passer ferait démarrer
les barrières d'un strike vieux de deux ans, et un worst-of réellement à 34 %
serait pris pour un worst-of à 100 %. Le prix resterait plausible.
"""
from datetime import date, timedelta

import pytest

from backend.app.core.variants import (
    MODE_AVENANT, MODE_ROLL, VariantError, deriver_roll, lire, resoudre,
)

STRIKE = date(2024, 6, 14)
VALORISATION = date(2026, 5, 8)
ECART = (VALORISATION - STRIKE).days

PARENT = {
    "script_text": "PARAM M_KI_BAR = 50%\nCONSTAT() OBS\nAT OBS.last:\n  PAY 1\n",
    "params": {"M_KI_BAR": 0.50},
    "constats": {"OBS": {"start_date": "2024-06-14", "roll_date": "2024-07-14",
                         "end_date": "2027-06-14", "frequency": "1M",
                         "convention": "following", "settlement_lag": 7}},
    "global": {
        "r": 2.5, "T": 3.0, "model": "constant",
        "trade_date": "2024-06-12", "strike_date": "2024-06-14",
        "value_date": "2024-06-18", "payment_date": "2027-06-23",
        "valuation_date": "2026-05-08",
        "strike_levels": {"GLE.PA": 22.150, "STLAM.MI": 18.820},
        "underlyings": [{"name": "GLE.PA", "sigma": 34.27, "q": 2.46},
                        {"name": "STLAM.MI", "sigma": 53.15, "q": 0.0}],
        "corr_matrix": [[1.0, 0.29], [0.29, 1.0]],
    },
}


# ── Le recalage de l'axe des temps ──────────────────────────────────

@pytest.mark.parametrize("chemin, avant", [
    ("global.trade_date", "2024-06-12"),
    ("global.strike_date", "2024-06-14"),
    ("global.value_date", "2024-06-18"),
    ("global.payment_date", "2027-06-23"),
    ("constats[OBS].start_date", "2024-06-14"),
    ("constats[OBS].roll_date", "2024-07-14"),
    ("constats[OBS].end_date", "2027-06-14"),
])
def test_toutes_les_dates_glissent_du_meme_ecart(chemin, avant):
    """Un décalage partiel produirait un calendrier incohérent — une maturité
    avant sa première constatation, par exemple — et la cohérence d'un
    calendrier ne se voit pas sur un prix."""
    ctx = resoudre(PARENT, {}, MODE_ROLL)
    attendu = (date.fromisoformat(avant) + timedelta(days=ECART)).isoformat()
    assert lire(ctx, chemin) == attendu


def test_le_tenor_est_preserve():
    """Une note de trois ans se roule en trois ans à partir d'aujourd'hui. Une
    autre durée se demande explicitement."""
    ctx = resoudre(PARENT, {}, MODE_ROLL)
    debut = date.fromisoformat(ctx["constats"]["OBS"]["start_date"])
    fin = date.fromisoformat(ctx["constats"]["OBS"]["end_date"])
    assert (fin - debut).days == (date(2027, 6, 14) - STRIKE).days


def test_la_note_neuve_est_strikee_a_la_date_de_valorisation():
    ctx = resoudre(PARENT, {}, MODE_ROLL)
    assert ctx["global"]["strike_date"] == VALORISATION.isoformat()
    # Valorisation = strike : le mode se déduit des dates, et c'est bien un
    # pricing à l'émission qu'on veut.
    assert ctx["global"]["valuation_date"] == ctx["global"]["strike_date"]


def test_les_niveaux_du_term_sheet_d_origine_sont_purges():
    """LE piège de ce mode.

    Les laisser passer ferait repartir les barrières d'un strike vieux de deux
    ans : un worst-of réellement à 34 % serait pris pour un worst-of à 100 %,
    et le prix resterait parfaitement plausible."""
    ctx = resoudre(PARENT, {}, MODE_ROLL)
    assert "strike_levels" not in ctx["global"]
    assert PARENT["global"]["strike_levels"], "le parent, lui, les garde"


# ── Ce que l'utilisateur fixe ne bouge pas ──────────────────────────

def test_une_date_fixee_par_le_delta_n_est_pas_decalee():
    """L'ordre compte : on applique le delta d'ABORD, puis on décale ce qu'il
    n'a pas fixé. L'inverse décalerait une maturité que l'utilisateur venait
    de saisir — le genre d'erreur qu'on ne remarque qu'en relisant un term
    sheet."""
    ctx = resoudre(PARENT, {"set": {"constats[OBS].end_date": "2031-05-08"}}, MODE_ROLL)

    assert ctx["constats"]["OBS"]["end_date"] == "2031-05-08"
    # Les autres, elles, ont bien glissé.
    assert ctx["constats"]["OBS"]["start_date"] == VALORISATION.isoformat()


def test_un_roll_peut_changer_le_panier():
    """Ce que l'avenant refuse : il n'y a plus de passé dont les extrema
    décriraient l'ancien panier."""
    ctx = resoudre(PARENT, {"removed": ["underlyings[STLAM.MI]"]}, MODE_ROLL)
    assert [u["name"] for u in ctx["global"]["underlyings"]] == ["GLE.PA"]
    assert ctx["global"]["corr_matrix"] == [[1.0]]


# ── Les refus ───────────────────────────────────────────────────────

def test_rouler_une_note_pas_encore_emise_est_refuse():
    sans = {**PARENT, "global": {k: v for k, v in PARENT["global"].items()
                                 if k != "valuation_date"}}
    sans["global"]["strike_date"] = None
    with pytest.raises(VariantError) as e:
        deriver_roll(sans, set())
    assert "date de valorisation" in str(e.value)


def test_une_valorisation_anterieure_au_strike_est_refusee():
    tordu = {**PARENT, "global": {**PARENT["global"], "valuation_date": "2023-01-01"}}
    with pytest.raises(VariantError) as e:
        resoudre(tordu, {}, MODE_ROLL)
    assert "précède" in str(e.value)


def test_un_avenant_ne_decale_rien():
    """La garantie symétrique : le mode avenant laisse l'axe des temps
    exactement où il est, puisque le passé s'y trouve."""
    ctx = resoudre(PARENT, {}, MODE_AVENANT)
    assert ctx["global"]["strike_date"] == "2024-06-14"
    assert ctx["global"]["strike_levels"] == PARENT["global"]["strike_levels"]
    assert ctx == PARENT


# ── Bout en bout : la note neuve price bien à l'émission ────────────

PHOENIX = """PARAM COUPON = 2%
PARAM M_AC_BAR = 100%
PARAM M_CPN_BAR = 50%
PARAM M_KI_BAR = 50%

CONSTAT() OBS

AT OBS:
  SET DUE = DUE + COUPON
  SET CPN = INDIC(WOF >= M_CPN_BAR)
  PAY CPN * DUE
  SET DUE = (1 - CPN) * DUE
  SET CALL = INDIC(INDEX >= 3) * INDIC(WOF >= M_AC_BAR)
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT OBS.last:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
"""


def test_la_note_neuve_price_au_voisinage_du_pair():
    """La preuve que le rebasage a eu lieu.

    Une note fraîchement strikée démarre à 100 % de son propre strike, quelle
    qu'ait été la déroute de la précédente. Son prix doit donc tourner autour du
    pair. S'il ressortait vers 40 %, c'est que les niveaux d'origine ont fui et
    qu'on price un worst-of déjà effondré sous des barrières qui le croient
    intact — avec un chiffre parfaitement plausible."""
    from backend.app.core.payscript.engine import run_mc
    from backend.app.core.payscript.parser import parse_script, resolve_constats

    parent = {**PARENT, "script_text": PHOENIX}
    ctx = resoudre(parent, {}, MODE_ROLL)

    compile_ = resolve_constats(
        parse_script(ctx["script_text"]), ctx["constats"],
        anchor=date.fromisoformat(ctx["global"]["strike_date"]), currency="EUR")
    uls = [{"name": u["name"], "sigma": u["sigma"] / 100, "q": u["q"] / 100}
           for u in ctx["global"]["underlyings"]]

    res = run_mc(compile_, uls, ctx["global"]["corr_matrix"],
                 ctx["global"]["r"] / 100, ctx["global"]["T"],
                 N=4000, model="constant", seed=42)

    assert 0.80 < res["price"] < 1.25, res["price"]


def test_la_note_neuve_ne_reprend_aucun_etat_du_passe():
    """Pas de mémoire reprise, pas d'extrema, pas de compteur d'observations :
    il n'y a pas de passé. Le contexte dérivé ne doit rien porter de tel."""
    ctx = resoudre({**PARENT, "script_text": PHOENIX}, {}, MODE_ROLL)
    assert "strike_levels" not in ctx["global"]
    assert ctx["global"]["valuation_date"] == ctx["global"]["strike_date"]


# ── Le panier : ce qu'une déclinaison peut en faire ─────────────────
#
# Trois règles, tranchées à l'étape 5 du plan d'audit :
#
#   retirer un titre    → oui, en note neuve seulement
#   ajouter un titre    → oui, en note neuve seulement, avec sa définition
#                         ENTIÈRE et ses corrélations
#   modifier un titre   → jamais. La calibration d'un nom hérité est une
#                         hypothèse de MARCHÉ, commune à toute la famille.
#
# La troisième est la moins évidente et la plus importante : la lever ferait
# mesurer à l'écart de prix un changement d'hypothèse au lieu de la
# restructuration, et le tableau comparatif perdrait tout sens.

NEUF = {"ticker": "SAN.PA", "ccy": "EUR", "sigma": 28.0, "q": 3.1,
        "correlations": {"GLE.PA": 0.62, "STLAM.MI": 0.24}}


def test_on_ajoute_un_titre_avec_sa_definition_entiere():
    """Un nom ajouté n'a aucun parent dont hériter : sa fiche arrive complète.
    Ce n'est pas une exception à « la calibration ne se modifie pas », c'est le
    cas où cette règle n'a rien à quoi s'appliquer."""
    ctx = resoudre(PARENT, {"set": {"underlyings[SAN.PA]": NEUF}}, MODE_ROLL)
    assert [u["name"] for u in ctx["global"]["underlyings"]] == ["GLE.PA", "STLAM.MI", "SAN.PA"]
    assert ctx["global"]["underlyings"][-1]["sigma"] == 28.0
    # La fiche ne garde pas les corrélations : elles vivent dans la matrice, et
    # les laisser en double les ferait diverger.
    assert "correlations" not in ctx["global"]["underlyings"][-1]


def test_l_ajout_etend_la_matrice_de_correlation():
    """Le titre et sa ligne ne se séparent pas — une matrice 2×2 pour trois noms
    serait soit refusée par le moteur, soit complétée d'office."""
    m = resoudre(PARENT, {"set": {"underlyings[SAN.PA]": NEUF}}, MODE_ROLL)["global"]["corr_matrix"]
    assert len(m) == 3 and all(len(l) == 3 for l in m)
    assert m[0][2] == 0.62 and m[1][2] == 0.24
    assert m[2][0] == 0.62 and m[2][2] == 1.0


def test_un_ajout_sans_correlation_est_refuse():
    """Un panier dont une corrélation n'est pas saisie n'est pas valorisable :
    la matrice serait complétée d'office, et personne n'aurait choisi la valeur
    qui price."""
    partiel = {**NEUF, "correlations": {"GLE.PA": 0.62}}
    with pytest.raises(VariantError) as e:
        resoudre(PARENT, {"set": {"underlyings[SAN.PA]": partiel}}, MODE_ROLL)
    assert "STLAM.MI" in str(e.value)


def test_modifier_la_calibration_d_un_titre_herite_est_refuse():
    """LA règle de l'étape 5.

    La volatilité d'un nom du panier est une hypothèse de marché, partagée par
    toute la famille de déclinaisons. La changer sur une seule ferait mesurer à
    l'écart de prix un changement d'hypothèse au lieu de la restructuration —
    et le tableau classerait des produits pricés sur des marchés différents,
    sans que rien ne le signale."""
    with pytest.raises(VariantError) as e:
        resoudre(PARENT, {"set": {"underlyings[GLE.PA].sigma": 60.0}}, MODE_ROLL)
    detail = str(e.value)
    assert "MARCHÉ" in detail and "scénario" in detail


def test_remplacer_un_titre_en_bloc_est_refuse():
    """Retirer puis ajouter dit la même chose et se VOIT à l'écran : le titre
    sortant reste affiché en grisé, l'entrant en ambre."""
    with pytest.raises(VariantError) as e:
        resoudre(PARENT, {"set": {"underlyings[GLE.PA]": NEUF}}, MODE_ROLL)
    assert "retirez-le" in str(e.value)


def test_remplacer_un_titre_se_dit_en_un_retrait_et_un_ajout():
    """Le chemin légitime : « je sors le nom qui bloque et j'en mets un autre »."""
    ctx = resoudre(PARENT, {
        "set": {"underlyings[SAN.PA]": {**NEUF, "correlations": {"GLE.PA": 0.62}}},
        "removed": ["underlyings[STLAM.MI]"]}, MODE_ROLL)
    assert [u["name"] for u in ctx["global"]["underlyings"]] == ["GLE.PA", "SAN.PA"]
    assert ctx["global"]["corr_matrix"] == [[1.0, 0.62], [0.62, 1.0]]


@pytest.mark.parametrize("delta", [
    {"set": {"underlyings[SAN.PA]": NEUF}},
    {"removed": ["underlyings[STLAM.MI]"]},
])
def test_un_avenant_ne_touche_toujours_pas_au_panier(delta):
    """Ni retrait ni ajout : les extrema repris du rejeu décrivent le panier
    d'origine, et rien ne dit ce qu'ils deviennent sur un autre."""
    with pytest.raises(VariantError) as e:
        resoudre(PARENT, delta, MODE_AVENANT)
    assert "roll" in str(e.value)


def test_un_titre_ajoute_garde_son_dividende_et_son_quanto():
    """Régression (audit A3).

    La conversion des unités d'un titre ajouté était une SECONDE voie, écrite à
    côté de celle qui existait déjà. Elle divisait naïvement une liste de champs
    par 100 — et perdait `ccyh`, qui se divise par 10 000, ainsi que toute la
    courbe de dividende. Pydantic ignorant les champs inconnus, rien n'échouait :
    le titre arrivait au moteur sans dividende, avec un prix plausible.

    On délègue désormais au convertisseur du chemin en cours de vie. Deux voies
    pour une seule conversion finissent toujours par diverger sur le champ que
    l'une des deux n'a pas vu."""
    from backend.app.api.variants import _ajoute_en_unites_moteur

    fiche = {"name": "SAN.PA", "ticker": "SAN.PA", "ccy": "EUR",
             "sigma": 28.0, "q": 3.1, "ccyh": 50.0, "dividendDecay": 10.0,
             "dividendCurve": [{"T": 1, "rate": 3.1}, {"T": 2, "rate": 2.79}],
             "correlations": {"GLE.PA": 0.3}}
    u = _ajoute_en_unites_moteur(fiche)

    assert u["sigma"] == pytest.approx(0.28)
    # Le piège : ccyh se divise par 10 000, pas par 100.
    assert u["ccyh"] == pytest.approx(0.005)
    assert u["dividend_curve"] == [[1.0, 0.031], [2.0, 0.0279]]
    assert u["dividend_decay"] == pytest.approx(0.10)
    # Les corrélations ont servi à étendre la matrice ; le moteur les lit là.
    assert "correlations" not in u


def test_un_script_ancien_dit_ce_qu_il_faut_faire():
    """Régression (audit A4).

    Un script enregistré avant que les dates soient persistées n'en porte
    aucune. Le refus parlait d'une date de valorisation manquante — vraie dans
    le contexte stocké, mais bien présente à l'écran. L'utilisateur cherchait un
    champ à remplir quand le remède est de réenregistrer."""
    ancien = {"script_text": "x", "params": {}, "constats": {},
              "global": {"r": 3.0, "T": 3.0}}
    with pytest.raises(VariantError) as e:
        resoudre(ancien, {}, MODE_ROLL)
    detail = str(e.value)
    assert "réenregistrez" in detail and "avenant" in detail.lower()


def test_une_date_de_valorisation_reellement_absente_le_dit_autrement():
    """Le cas symétrique : le contexte porte des dates, mais pas celle-là. Le
    geste attendu n'est pas le même, le message non plus."""
    partiel = {"script_text": "x", "params": {}, "constats": {},
               "global": {"value_date": "2024-06-18", "T": 3.0}}
    with pytest.raises(VariantError) as e:
        resoudre(partiel, {}, MODE_ROLL)
    assert "onglet Deal" in str(e.value)
