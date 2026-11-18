# Découpage d'engine.py — 18/11/2026

Reprise du point P1-5 de l'[audit technique du 16/11](../../audits/AUDIT_GLOBAL_TECHNIQUE_2026-11-16.md),
qui laissait `core/payscript/engine.py` à 5 431 lignes après le découpage de `api/deals.py`.
Branche `refactor/split-engine`.

**Aucune ligne de calcul n'a changé.** Le code a été déplacé par plages de lignes, entre des
sections que le fichier délimitait déjà, par un script qui calcule les imports de chaque
module à partir de la table des symboles de Python et refuse tout nom non résolu ou tout
cycle d'imports. Les tests de référence figés du moteur (`test_engine_golden.py`), au sixième
chiffre près, et les 47 tests de validation du même jour passent inchangés.

## Les modules

| Module | Lignes | Contenu |
|---|---:|---|
| `engine.py` | ~190 | Façade : réexporte tous les noms d'avant (156 vérifiés) |
| `mc_axis.py` | 71 | Constante de grille, politique d'axe des temps, échéancier des événements sur les pas |
| `diffusion.py` | 704 | Cholesky, Heston QE, SABR, GBM, Local Vol, LSV, extrema du pont brownien |
| `local_vol.py` | 260 | Inversion de Dupire, pas de dividendes, ailes SSVI, grille de vol locale |
| `rates.py` | 322 | Actualisation par courbe, taux court stochastique, terme de taux, funding |
| `evaluation.py` | 981 | Évaluation du PayScript sur les trajectoires : fenêtres, niveau initial, état courant |
| `monte_carlo.py` | 675 | `run_mc` et son rapport de fenêtres |
| `greeks.py` | 334 | Greeks par bump et recalcul à tirages communs, theta par vieillissement |
| `analytics.py` | 195 | Profil de payoff, trajectoires affichées, probabilités |
| `mark_to_future.py` | 839 | Mark-to-Future : scénarios extérieurs, revalorisations intérieures, statistiques datées |
| `mtf_drilldown.py` | 437 | Détail d'une date du Mark-to-Future |
| `backtest.py` | 737 | Backtest historique et TRI des flux |

Dépendances, sans cycle : `diffusion` ← `local_vol`, `rates` ; `evaluation` ← `mc_axis` ;
`monte_carlo` ← `diffusion`, `evaluation`, `local_vol`, `mc_axis`, `rates` ; `greeks` ←
`monte_carlo` ; `mark_to_future` et `mtf_drilldown` ← simulateurs et évaluation ; `backtest`
← `evaluation`.

## Pour l'application : rien ne change

`from ..payscript.engine import run_mc` et `engine.run_mc(...)` fonctionnent comme avant,
y compris pour les noms privés (`engine._simulate_lv`, `engine._eval_paths`…). Les modules qui
lisent `engine.<nom>` au moment de l'appel (qualification des payoffs, grille de scénarios)
restent remplaçables par `engine`.

## Pour les tests : `patch_engine`

Un `monkeypatch.setattr(engine, nom, valeur)` ne touche plus que la façade : la fonction qui
appelle `nom` le lit dans **son** module. Le piège est double. Un remplacement qui n'atteint
plus sa cible fait échouer le test s'il capture quelque chose, mais il peut aussi le faire
**passer à vide** : la fixture qui bornait `MTF_MAX_BATCH` à 5 000 aurait laissé tourner les
tests du Mark-to-Future à la taille de production sans rien dire.

`backend/tests/engine_patch.patch_engine(monkeypatch, nom, valeur)` remplace le nom sur la
façade et dans chaque module du moteur qui le lie, comme `deals_patch.patch_deals` pour l'API
des deals. Tous les remplacements d'attributs du moteur dans les tests passent par lui ; la
liste des modules est `engine.SUBMODULES`.

## Ce qui reste

- `SY` (52) n'est plus qu'une valeur par défaut figée à la définition des fonctions : la grille
  réelle vient de `simulation_grid`. Deux scripts hors ligne (`validate_product_optimizer.py`,
  `study_integrated_smile.py`) écrivent encore `engine.SY`, ce qui était déjà sans effet avant
  le découpage.
- `evaluation.py` (981 lignes) tient l'interpréteur de trajectoires en deux fonctions longues
  (`_eval_paths`, `_eval_paths_detailed`) : leur découpage serait un vrai travail de conception,
  pas un déplacement.
- `core/amc_pdf.py`, `AmcView.vue` et `stores/pricing.js` restent à découper.
