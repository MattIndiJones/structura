"""Constatations sur période — la réduction est PAR SOUS-JACENT.

Une constatation n'est pas forcément un point : `CONSTAT Nom MIN|MAX|AVG` en
fait le min, le max ou la moyenne des cours de CHAQUE sous-jacent sur une
fenêtre, et `WOF`/`BOF`/`BASKET` n'agrègent qu'ensuite.

Ces tests exigent surtout que le prix **bouge**. Une hypothèse de marché
saisissable sans le moindre effet sur le prix est le défaut qui est passé
plusieurs fois — courbe de taux, courbe de dividende, calibration — et qu'un
test vérifiant une seule valeur ne voit jamais. Voir
CONSTATATIONS_PERIODE_DESIGN.md §9.
"""
from datetime import date

import pytest

from backend.app.core.payscript.parser import parse_script, resolve_constats
from backend.app.core.payscript.engine import run_mc
from backend.app.core.schedule import observation_window, parse_tenor

TODAY = date(2026, 9, 10)
MATURITY = "2027-09-10"
CORR3 = [[1.0 if i == j else 0.5 for j in range(3)] for i in range(3)]


def _ul(name):
    return dict(name=name, ticker="", ccy="EUR", sigma=0.25, q=0.0,
                v0=0.0625, kappa=2.0, theta=0.0625, xi=0.35, rho_h=-0.7,
                alpha=0.25, beta=0.5, rho=-0.3, nu=0.4,
                sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)


def _script(agg="BASKET", red0="AVG", red1="AVG"):
    fix = f"CONSTAT STRIKE_FIX  {red0}" if red0 else ""
    mat = f"CONSTAT MATURITE    {red1}" if red1 else "CONSTAT MATURITE"
    return f"""
PARAM STRIKE = 100%
{fix}
{mat}

AT MATURITE:
  PAY MAX(0, {agg} - STRIKE) "call"
"""


def _price(agg="BASKET", red0="AVG", red1="AVG", w0="10D", w1="30D",
           n_assets=3, freq="1D", N=12000, full=False):
    cs = parse_script(_script(agg, red0, red1))
    vals = {}
    if any(c.name == "MATURITE" for c in cs.constats):
        c = next(c for c in cs.constats if c.name == "MATURITE")
        vals["MATURITE"] = ({"date": MATURITY, "window_length": w1,
                             "window_frequency": freq} if c.reduction else MATURITY)
    if any(c.name == "STRIKE_FIX" for c in cs.constats):
        vals["STRIKE_FIX"] = {"date": "2026-09-10", "window_length": w0,
                              "window_frequency": freq}
    compiled = resolve_constats(cs, vals, anchor=TODAY, currency="EUR")
    uls = [_ul(f"S{i}") for i in range(n_assets)]
    corr = [[1.0 if i == j else 0.5 for j in range(n_assets)] for i in range(n_assets)]
    res = run_mc(compiled, uls, corr, r=0.03, T_max=1.0, N=N, model="constant",
                 seed=7, antithetic=True, user_params={})
    return res if full else res["price"]


# ── 1. Les trois réductions donnent trois prix, dans le bon ordre ──────

def test_les_trois_reductions_donnent_trois_prix_distincts():
    """Sur la seule fenêtre de DÉPART, le strike le plus bas vaut le call le
    plus cher : MIN > AVG > MAX. Un test qui ne vérifierait qu'une valeur
    laisserait passer une réduction débranchée."""
    mn = _price(red0="MIN", red1=None)
    av = _price(red0="AVG", red1=None)
    mx = _price(red0="MAX", red1=None)
    assert mn > av > mx, f"MIN={mn:.4f} AVG={av:.4f} MAX={mx:.4f}"
    # Et l'écart est du niveau d'un vrai effet de structuration, pas du bruit MC.
    # Sur 10 jours ouvrés la fenêtre ne pèse que 2 pas de grille, ce qui borne
    # l'écart : mesuré à ~165 bps ici, contre quelques bps d'erreur MC.
    assert (mn - mx) > 0.01, f"écart MIN-MAX de seulement {(mn - mx) * 1e4:.0f} bps"


def test_allonger_la_fenetre_deplace_le_prix():
    """Le prix doit BOUGER quand la fenêtre s'allonge, et dans le bon sens : une
    moyenne sur plus de points est moins dispersée, donc le call vaut moins."""
    courte = _price(red0=None, red1="AVG", w1="10D")
    longue = _price(red0=None, red1="AVG", w1="60D")
    assert longue < courte, f"60j={longue:.4f} vs 10j={courte:.4f}"
    assert (courte - longue) > 0.001, (
        f"allonger la fenêtre n'a déplacé le prix que de "
        f"{(courte - longue) * 1e4:.1f} bps — hypothèse probablement débranchée")


# ── 2. Le cas dégénéré reproduit le comportement historique ────────────

def test_fenetre_d_un_point_est_le_comportement_ponctuel():
    """Une fenêtre qui se réduit à un seul pas de grille doit rendre EXACTEMENT
    le prix d'une constatation ponctuelle : le comportement actuel est le cas
    dégénéré de la règle, pas un régime à part."""
    ponctuel = _price(red0=None, red1=None)
    degenere = _price(red0=None, red1="AVG", w1="1D")
    assert degenere == pytest.approx(ponctuel, abs=1e-12), (
        f"dégénéré={degenere:.8f} vs ponctuel={ponctuel:.8f}")


def test_le_decompte_de_points_signale_une_fenetre_degeneree():
    """Le message n'est pas « attention, fenêtre courte » — qui se clique sans
    lire — mais le nombre de points RÉELLEMENT retenus."""
    res = _price(red0="AVG", red1="AVG", w0="10D", w1="30D", full=True)
    rows = {r["constatation"]: r for r in res["constatation_windows"]}
    assert rows["STRIKE_FIX"]["points_demandes"] == 10
    assert rows["STRIKE_FIX"]["points_retenus"] == 2      # grille hebdomadaire
    assert rows["observation"]["points_demandes"] == 30
    assert not any(r["degeneree"] for r in res["constatation_windows"])

    court = _price(red0="AVG", red1="AVG", w0="3D", w1="3D", full=True)
    assert all(r["degeneree"] for r in court["constatation_windows"])
    assert all(r["points_retenus"] == 1 for r in court["constatation_windows"])


# ── 3. Non-commutativité : le cœur de la conception ────────────────────

def test_reduire_par_actif_puis_agreger_n_est_pas_l_inverse_sur_un_worst_of():
    """`moyenne(min)` et `min(moyennes)` ne sont pas la même chose, et l'écart
    n'est pas du bruit : c'est le défaut que toute la conception ferme.

    La convention du moteur (par actif, puis agrégation) donne un niveau de
    référence PLUS HAUT que la convention fautive, puisque
    moyenne(min) <= min(moyennes) toujours. Un strike de référence plus haut
    vaut un call moins cher — le test lit donc le signe autant que l'écart.
    """
    wof_fenetre = _price(agg="WOF", red0="AVG", red1="AVG")
    wof_ponctuel = _price(agg="WOF", red0=None, red1=None)
    assert wof_fenetre != wof_ponctuel
    # L'ordre de grandeur qui compte : sur un worst-of, moyenner change le prix
    # de plusieurs dizaines de bps — c'est ce que la mauvaise convention
    # déplaçait silencieusement.
    assert abs(wof_fenetre - wof_ponctuel) > 0.002


def test_la_commutativite_protege_le_panier_pas_le_worst_of():
    """Sur un panier, moyenner puis agréger ou l'inverse revient au même à
    quelques points de base ; sur un worst-of, non. C'est pourquoi la
    convention par actif est gratuite ici et critique là-bas.

    Mesuré sur les mêmes tirages : l'effet du moyennage est bien plus petit sur
    le panier (les deux moyennes commutent presque) que l'écart d'agrégation.
    """
    panier = _price(agg="BASKET", red0="AVG", red1="AVG")
    wof = _price(agg="WOF", red0="AVG", red1="AVG")
    bof = _price(agg="BOF", red0="AVG", red1="AVG")
    # Le choix d'agrégation est du PREMIER ordre : facteur ~2 de part et d'autre.
    assert wof < panier < bof
    assert bof > 2 * panier and panier > 2 * wof, f"{wof:.4f} {panier:.4f} {bof:.4f}"


# ── 4. Sans S0, rien n'est observable ──────────────────────────────────

BARRIERE = """
PARAM KI = 95%
CONSTAT STRIKE_FIX  AVG
CONSTAT MATURITE

AT MATURITE:
  PAY INDIC(WOF_MIN < KI) "barrière touchée"
"""


def test_aucune_observation_americaine_avant_que_s0_existe():
    """Une barrière américaine ne court pas tant que le niveau initial n'est pas
    constaté : il n'y a rien dont elle puisse être le pourcentage. Une fenêtre
    de départ plus longue ne doit donc PAS augmenter la probabilité de toucher
    — au contraire, elle retarde le départ du compteur."""
    def px(w0):
        cs = parse_script(BARRIERE)
        compiled = resolve_constats(cs, {
            "STRIKE_FIX": {"date": "2026-09-10", "window_length": w0,
                           "window_frequency": "1D"},
            "MATURITE": MATURITY,
        }, anchor=TODAY, currency="EUR")
        return run_mc(compiled, [_ul("S1")], [[1.0]], r=0.03, T_max=1.0,
                      N=12000, model="constant", seed=11, antithetic=True,
                      user_params={})["price"]

    courte, longue = px("10D"), px("120D")
    assert longue < courte, (
        f"fenêtre de 120j : {longue:.4f} vs 10j : {courte:.4f} — les extrema "
        f"semblent accumuler pendant la fenêtre de départ")


# ── 5. La fenêtre elle-même, en dates ──────────────────────────────────

def test_la_fenetre_de_depart_part_de_sa_date_les_autres_y_arrivent():
    """On regarde en avant au départ, en arrière à l'arrivée."""
    d = date(2027, 9, 10)
    arrivee = observation_window(d, parse_tenor("30D"), parse_tenor("1D"),
                                 currency="EUR")
    assert arrivee[-1] == d and arrivee[0] < d and len(arrivee) == 30

    depart = observation_window(date(2026, 9, 10), parse_tenor("10D"),
                                parse_tenor("1D"), forward=True, currency="EUR")
    assert depart[0] == date(2026, 9, 10) and depart[-1] > depart[0]
    assert len(depart) == 10


def test_la_longueur_en_jours_compte_les_observations_pas_les_jours_calendaires():
    """« 30D » à la fréquence 1D fait 30 fixings, la date comprise — et ce sont
    des jours OUVRÉS : une lecture calendaire en aurait silencieusement perdu
    un tiers dans les week-ends."""
    w = observation_window(date(2027, 9, 10), parse_tenor("30D"),
                           parse_tenor("1D"), currency="EUR")
    assert len(w) == 30
    assert (w[-1] - w[0]).days > 30, "les week-ends n'ont pas été sautés"


def test_les_unites_calendaires_restent_des_durees():
    """D compte des observations, W/M/Y décrivent une durée : les deux lectures
    coexistent sans ambiguïté parce que longueur et fréquence sont deux champs
    distincts."""
    mensuel = observation_window(date(2027, 9, 10), parse_tenor("3M"),
                                 parse_tenor("1M"), currency="EUR")
    assert len(mensuel) == 4                      # bornes incluses
    quotidien = observation_window(date(2027, 9, 10), parse_tenor("3M"),
                                   parse_tenor("1D"), currency="EUR")
    assert len(quotidien) > 60                    # même durée, autre produit


# ── 6. Ce qui atteint vraiment le moteur ───────────────────────────────

def test_la_frequence_de_releve_atteint_le_moteur():
    """Deux produits distincts : « les 3 derniers mois relevés chaque jour » et
    « relevés chaque mois ». Si la fréquence ne descendait pas jusqu'au moteur,
    les deux rendraient le même prix."""
    quotidien = _price(red0=None, red1="AVG", w1="3M", freq="1D")
    mensuel = _price(red0=None, red1="AVG", w1="3M", freq="1M")
    assert quotidien != mensuel
    assert abs(quotidien - mensuel) > 2e-4, (
        f"écart de {(abs(quotidien - mensuel)) * 1e4:.1f} bps seulement — la "
        f"fréquence de relevé n'atteint peut-être pas la réduction")


def test_le_produit_du_chantier_price_et_coute_moins_qu_un_ponctuel():
    """Le call panier 3 sous-jacents, strike moyenné 10 jours et niveau final
    moyenné 30 jours : le produit qui a lancé le chantier. Le double moyennage
    réduit la dispersion, donc le call vaut moins qu'avec des constatations
    ponctuelles."""
    ponctuel = _price(red0=None, red1=None)
    produit = _price(red0="AVG", red1="AVG", w0="10D", w1="30D")
    assert 0 < produit < ponctuel
    assert (ponctuel - produit) > 0.002, (
        f"le double moyennage ne vaut que {(ponctuel - produit) * 1e4:.0f} bps")


# ── 7. Fenêtre de PÉRIODE ──────────────────────────────────────────────

PERIODE = """
PARAM COUPON    = 8%
PARAM M_AC_BAR   = 100%
PARAM M_PDI_BAR  = 60%

CONSTAT() OBSERVATIONS AVG PERIOD

AT OBSERVATIONS:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * (1 + COUPON * INDEX)
  IF CALL = 1:
    STOP

AT {FINAL}:
  SET KI = INDIC(WOF < M_PDI_BAR)
  PAY 1 - KI * (1 - WOF)
"""

CAL_PERIODE = {"OBSERVATIONS": {
    "start_date": "2026-09-10", "end_date": "2029-09-10", "roll_date": "2029-09-10",
    "frequency": "1Y", "stub": "short_last", "window_frequency": "3M"}}


def _autocall(final, n_assets=2, N=8000, full=False):
    cs = parse_script(PERIODE.replace("{FINAL}", final))
    compiled = resolve_constats(cs, CAL_PERIODE, anchor=TODAY, currency="EUR")
    uls = [_ul(f"S{i}") for i in range(n_assets)]
    corr = [[1.0 if i == j else 0.5 for j in range(n_assets)] for i in range(n_assets)]
    res = run_mc(compiled, uls, corr, r=0.03, T_max=3.0, N=N, model="constant",
                 seed=7, antithetic=True, user_params={})
    return res if full else res["price"]


def test_la_periode_donne_une_constatation_par_date_du_calendrier():
    """La sous-fréquence de relevé ne crée PAS d'observations : un calendrier
    annuel relevé trimestriellement, ce sont 3 constatations de 4 relevés, pas
    12 observations. Sans quoi le produit paierait douze coupons au lieu de
    trois, et `INDEX` compterait jusqu'à 12."""
    compiled = resolve_constats(parse_script(PERIODE.replace("{FINAL}", "OBSERVATIONS.last")),
                                CAL_PERIODE, anchor=TODAY, currency="EUR")
    principal = compiled.events[0]
    assert len(principal.dates) == 3, principal.dates
    assert [len(w) for w in principal.window_dates] == [4, 4, 4]


def test_les_periodes_ne_se_recouvrent_pas():
    """Bornes ouvertes à gauche, fermées à droite : une date de roll appartient
    à la période qui s'achève, jamais aux deux. Un relevé compté deux fois
    pèserait double dans une moyenne."""
    compiled = resolve_constats(parse_script(PERIODE.replace("{FINAL}", "OBSERVATIONS.last")),
                                CAL_PERIODE, anchor=TODAY, currency="EUR")
    fenetres = compiled.events[0].window_dates
    plat = [d for w in fenetres for d in w]
    assert len(plat) == len(set(plat)), "un relevé appartient à deux périodes"
    for w, suivante in zip(fenetres, fenetres[1:]):
        assert w[-1] < suivante[0]


def test_periode_sur_une_date_unique_est_refusee():
    """`PERIOD` court d'une constatation à la suivante : sur une date unique il
    n'y en a pas de précédente. Refusé plutôt que traité en silence."""
    with pytest.raises(ValueError, match="PÉRIODE"):
        resolve_constats(parse_script("CONSTAT MAT AVG PERIOD\nAT MAT:\n  PAY 1"),
                         {"MAT": {"date": "2027-09-10", "window_frequency": "1D"}},
                         anchor=TODAY)


# ── 8. Deux lectures d'une même date ───────────────────────────────────

def test_deux_blocs_au_meme_jour_lisent_deux_niveaux_differents():
    """Le cœur du dispositif : un coupon constaté sur la moyenne et une
    protection constatée sur le cours de clôture tombent le même jour et
    doivent lire deux choses différentes.

    Le PDI sur clôture est plus risqué que le PDI sur moyenne — rien ne lisse
    le niveau final — donc le produit vaut MOINS. Un prix identique voudrait
    dire que le second niveau de qualificateur n'atteint pas le moteur."""
    sur_moyenne = _autocall("OBSERVATIONS.last")
    sur_cloture = _autocall("OBSERVATIONS.last.last")
    assert sur_cloture < sur_moyenne, f"{sur_cloture:.4f} vs {sur_moyenne:.4f}"
    assert (sur_moyenne - sur_cloture) > 0.005, (
        f"écart de {(sur_moyenne - sur_cloture) * 1e4:.0f} bps seulement — le "
        f"second niveau de qualificateur n'atteint peut-être pas le moteur")


def test_le_bloc_de_releve_ne_porte_aucune_reduction():
    """`.last.last` désigne un relevé : il lit le cours brut, sans réduction,
    et tombe le même jour que la constatation qu'il détaille."""
    compiled = resolve_constats(parse_script(PERIODE.replace("{FINAL}", "OBSERVATIONS.last.last")),
                                CAL_PERIODE, anchor=TODAY, currency="EUR")
    principal, releve = compiled.events[0], compiled.events[1]
    assert releve.reduction is None and releve.window_dates is None
    assert releve.dates == [principal.dates[-1]], (releve.dates, principal.dates)


def test_second_niveau_sans_fenetre_est_refuse():
    """Descendre dans une fenêtre qui n'existe pas n'a pas de sens."""
    with pytest.raises(ValueError, match="second qualificateur"):
        resolve_constats(parse_script("CONSTAT() OBS\nAT OBS.last.last:\n  PAY 1"),
                         {"OBS": {"start_date": "2026-09-10", "end_date": "2029-09-10",
                                  "roll_date": "2029-09-10", "frequency": "1Y",
                                  "stub": "short_last"}}, anchor=TODAY)


def test_trois_niveaux_sont_refuses_a_la_compilation():
    with pytest.raises(ValueError, match="deux niveaux"):
        parse_script("CONSTAT() OBS AVG\nAT OBS.last.last.last:\n  PAY 1")


def test_periode_et_sous_frequence_se_contredisent():
    """`CONSTAT()()` produit des OBSERVATIONS à sa sous-fréquence ; `PERIOD`
    produit des RELEVÉS moyennés à la fréquence de fenêtre. Les deux ensemble,
    c'est deux grilles fines pour un calendrier — l'une serait ignorée sans
    rien dire, et un moyennage saisi sans effet est précisément le défaut que
    la règle A7 demande de rendre visible."""
    with pytest.raises(ValueError, match="se contredisent"):
        resolve_constats(
            parse_script("CONSTAT()() OBS AVG PERIOD\nAT OBS:\n  PAY 1"),
            {"OBS": {"start_date": "2026-09-10", "end_date": "2029-09-10",
                     "roll_date": "2029-09-10", "frequency": "1Y", "stub": "short_last",
                     "sub_frequency": "3M", "window_frequency": "3M"}}, anchor=TODAY)


def test_la_sous_frequence_se_recale_sur_chaque_date_principale():
    """La propriété propre de `CONSTAT()()`, et la seule : sa sous-grille
    repart de chaque date principale au lieu de courir en continu. Invisible
    quand la sous-fréquence divise la fréquence (3M dans 1Y donne le même
    résultat qu'un 3M direct) ; c'est sur une fréquence non divisible qu'elle
    se voit, et qu'elle évite aux observations de dériver d'année en année."""
    from backend.app.core.schedule import generate_schedule, StubConvention
    base = dict(start=date(2026, 9, 10), end=date(2029, 11, 10),
                roll_date=date(2029, 11, 10), stub=StubConvention.SHORT_LAST)
    imbrique = generate_schedule(frequency=parse_tenor("1Y"),
                                 sub_frequency=parse_tenor("5M"), **base)["dates"]
    plat = generate_schedule(frequency=parse_tenor("5M"), **base)["dates"]
    assert imbrique != plat
    # La grille imbriquée repasse par chaque anniversaire annuel ; la plate dérive.
    anniversaires = {date(2027, 9, 10), date(2028, 9, 10), date(2029, 9, 10)}
    assert anniversaires <= set(imbrique)
    assert not (anniversaires & set(plat))


# ── 9. L'aperçu ne doit jamais déverser ────────────────────────────────

def test_l_apercu_refuse_un_calendrier_absurde():
    """Une année tapée « 0026 » au lieu de « 2026 » produit deux mille
    constatations. L'aperçu les refuse au lieu de les rendre : un panneau qui
    déverse des milliers de lignes est illisible, et la cause est presque
    toujours une date, jamais une intention."""
    from fastapi.testclient import TestClient
    from backend.app.main import app

    c = TestClient(app)
    base = {"end_date": "2029-09-10", "roll_date": "2029-09-10", "frequency": "1Y",
            "window_frequency": "3M", "currency": "EUR"}

    ok = c.post("/api/schedule/period-window", json={**base, "start_date": "2026-09-10"})
    assert ok.status_code == 200
    d = ok.json()
    assert d["count"] == 3 and d["releves_min"] == d["releves_max"] == 4
    # TOUTES les constatations, avec leurs relevés : c'est ce que l'échéancier
    # affiche sous chaque date, et le seul moyen de vérifier qu'un calendrier
    # annuel relevé trimestriellement fait 3 × 4 et non 12 × 1.
    assert [f["n"] for f in d["fenetres"]] == [4, 4, 4]
    assert d["fenetres"][0]["dates"] == ["2026-12-10", "2027-03-10",
                                          "2027-06-10", "2027-09-10"]
    assert not any(f["tronque"] for f in d["fenetres"])

    # Une fenêtre quotidienne compte des centaines de dates : le compte reste
    # exact, la liste est bornée aux deux bouts.
    fine = c.post("/api/schedule/period-window",
                  json={**base, "start_date": "2026-09-10", "window_frequency": "1D"}).json()
    assert fine["releves_min"] > 200
    assert all(f["tronque"] and len(f["dates"]) == 9 for f in fine["fenetres"])

    absurde = c.post("/api/schedule/period-window", json={**base, "start_date": "0026-09-10"})
    assert absurde.status_code == 422
    assert "dates de début" in absurde.json()["detail"]


def test_l_apercu_d_une_fenetre_de_longueur_dit_les_vraies_dates():
    """« 10 jours ouvrés à partir du 10/09 » ne va pas au 20 mais au 23 : deux
    week-ends sautés. C'est exactement ce que l'aperçu existe pour montrer."""
    from fastapi.testclient import TestClient
    from backend.app.main import app

    d = TestClient(app).post("/api/schedule/window", json={
        "date": "2026-09-10", "window_length": "10D", "window_frequency": "1D",
        "forward": True, "currency": "EUR"}).json()
    assert d["first"] == "2026-09-10" and d["last"] == "2026-09-23"
    assert d["count"] == 10
