"""Niveau de départ des trajectoires vs bump de Greek — deux choses distinctes.

`run_mc` reçoit un `spot_mult` qui sert à deux usages incompatibles : semer les
trajectoires au spot courant d'un deal vivant (en % du strike), et choquer un
sous-jacent pour une différence finie. Le mécanisme de bump différé, qui protège
les strikes asiatiques (un bump appliqué avant la fenêtre de fixing se simplifie
dans PERF = WOF/REF et rend le delta nul), doit se déclencher sur le **second**
usage uniquement.

Il ne distinguait pas les deux : son test était « spot_mult ≠ 1 ». Un deal vivant
dont le spot a simplement bougé — sans le moindre bump — le déclenchait donc, et
son MtM était simulé depuis 1.0 au lieu du spot du jour. `spot_base` dit
explicitement ce que l'appelant considère comme non bumpé.
"""
import pytest

from backend.app.core.payscript.parser import parse_script, CompiledScript
from backend.app.core.payscript.engine import run_mc

UL = dict(name="S1", ticker="", ccy="EUR",
          sigma=0.20, q=0.00, v0=0.04, kappa=2.0, theta=0.04, xi=0.35, rho_h=-0.70,
          alpha=0.20, beta=0.5, rho=-0.30, nu=0.40, sigma_fx=0.0, rho_sfx=0.0, ccyh=0.0)
CORR = [[1.0]]

# Strike asiatique : le payoff est un RATIO entre le niveau final et le niveau
# fixé pendant la fenêtre. Le spot de départ se simplifie exactement — le prix
# est donc indépendant du niveau de seeding, ce qui en fait l'oracle idéal.
#
# Le ratio ne s'écrit plus dans le script : depuis la constatation sur période,
# c'est le MOTEUR qui rebase le tenseur sur S0_i (la réduction de la fenêtre de
# départ, par sous-jacent), et `WOF` EST la performance. L'oracle est le même —
# seul l'endroit où la division a lieu a changé.
ASIAN = """
AT MATURITY
  PAY WOF "perf vs strike moyen"
"""


def _asian(strike_fix=True):
    cs = parse_script(ASIAN)
    return CompiledScript(events=cs.events, init_fn=cs.init_fn, params=cs.params,
                          constats=cs.constats,
                          strike_fix_dates=[4 / 52] if strike_fix else None,
                          strike_fix_reduction='AVG' if strike_fix else None)


def _price(spot_mult, spot_base=None, strike_fix=True):
    return run_mc(_asian(strike_fix), [dict(UL)], CORR, r=0.03, T_max=1.0, N=2000,
                  model="constant", seed=42, antithetic=True, user_params={},
                  spot_mult=spot_mult, spot_base=spot_base)["price"]


def test_seeding_d_un_deal_vivant_ne_declenche_pas_le_bump_differe():
    """Un deal à 130 % du strike, avec une fenêtre de fixing encore ouverte,
    n'est pas un produit bumpé : c'est le même produit vu plus haut. Comme son
    payoff est un ratio, son prix doit être identique à celui du même deal vu à
    100 %.

    Sans `spot_base`, le moteur croyait à un bump de +30 %, semait à 1.0 et
    n'appliquait le 1,3 qu'après la fenêtre de fixing : le numérateur était
    multiplié par 1,3 mais pas le dénominateur, et le MtM ressortait ~30 % trop
    haut."""
    au_pair = _price([1.0], spot_base=[1.0])
    plus_haut = _price([1.3], spot_base=[1.3])
    assert plus_haut == pytest.approx(au_pair, abs=1e-6), (
        f"seeding à 130% : {plus_haut:.6f} vs {au_pair:.6f} au pair")

    # Ampleur de ce qui était faux : sans baseline, l'erreur valait exactement
    # le facteur de seeding — un deal à 130 % du strike voyait son MtM majoré
    # de 30 %. `spot_base=None` reproduit encore cette logique (c'est le
    # comportement attendu du pré-trade, où 1.0 EST la baseline), ce qui permet
    # de mesurer l'écart ici.
    ancien = _price([1.3])
    assert ancien == pytest.approx(au_pair * 1.3, rel=1e-6)


def test_le_bump_differe_applique_le_ratio_pas_le_niveau():
    """Sur ce même deal à 130 %, un vrai bump de +1 % doit déplacer le prix de
    +1 %, pas de +31 %. C'est ce que garantit la division par la baseline : le
    segment postérieur à la fenêtre est multiplié par m/b, pas par m."""
    base = _price([1.3], spot_base=[1.3])
    bumpe = _price([1.3 * 1.01], spot_base=[1.3])
    assert bumpe == pytest.approx(base * 1.01, rel=1e-6), (
        f"bump +1% : {bumpe:.6f}, attendu ~{base * 1.01:.6f}")


def test_le_bump_reste_actif_sans_baseline_explicite():
    """Le pré-trade n'a pas de baseline : `spot_base=None` doit continuer de se
    comporter comme avant, c'est-à-dire traiter tout écart à 1.0 comme un bump.
    Sans cette compatibilité, tous les Greeks pré-trade des produits à strike
    asiatique repartiraient à zéro."""
    base = _price([1.0])
    bumpe = _price([1.01])
    assert bumpe == pytest.approx(base * 1.01, rel=1e-6)


def test_seeding_sans_fenetre_de_fixing_est_inchange():
    """Garde-fou : sur un script sans `STRIKE_FIX`, le mécanisme ne s'active
    jamais et `spot_base` n'a aucun effet observable."""
    sans_base = _price([1.3], strike_fix=False)
    avec_base = _price([1.3], spot_base=[1.3], strike_fix=False)
    assert sans_base == avec_base
