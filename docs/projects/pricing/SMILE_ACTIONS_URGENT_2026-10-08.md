# URGENT — reprendre le smile actions et les ailes basses

**Priorité : URGENT. État : à reprendre ; développement différé le 08/10/2026
à la demande de Philippe pour concentrer le travail sur le Product Optimizer.**

Cette note conserve le diagnostic et la méthode de reprise. Elle ne modifie ni
les profils ni les moteurs. Les résultats historiques du 07/10 restent des
mesures sur hypothèses synthétiques, pas des cotations de desk.

## Problème à reprendre

Le profil Actions utilise une surface SSVI indicative, avec deux paramètres de
forme communs aux maturités. À un an, il donne au strike 60 % du forward
30,10 % de vol implicite pour une ATM à 20 %, et 42,25 % pour une ATM à 30 %.
Ces ailes sont plus modérées que les matrices décrites par Philippe : exemples
de vol à 50 % au strike 60 %, et 60–70 % au strike 50 %. Ces exemples restent
à rattacher à un sous-jacent, une maturité, une date et un niveau ATM ; ils ne
sont pas un défaut universel à appliquer aux actions.

L'éditeur affiche les strikes 60/80/100/120/140 % du forward, sans 50 %.
Une cellule d'aile ajuste un paramètre global : la matrice n'est pas libre,
et son édition peut déplacer d'autres strikes et plusieurs maturités.
Changer le niveau ATM modifie aussi la forme relative du smile ; les scénarios
20 % et 30 % ne sont ni une translation uniforme ni une homothétie de toute la
surface. La maturité intervient aussi dans l'atténuation du skew.

## Limites des comparatifs

Sur l'Athena quatre ans étudié, l'écart Local Vol moins GBM vaut environ
−0,97 point en mono à 20 % ATM et −0,08 point à 30 %. Le prix total résulte
de compensations entre capital, coupons et put vendu. Une décomposition
réconciliée identifie les contributions ; elle ne suffit pas à prouver que le
profil représente le marché ni à qualifier chaque probabilité de rappel.

Un skew actions asymétrique peut agir sur les digitaux de rappel via la pente
au seuil. Une hausse limitée aux ailes basses, conservant les prix et la pente
au seuil, conserve la probabilité du premier rappel mono-actif ; les rappels
ultérieurs dépendent aussi de la dynamique conditionnelle. En worst-of,
il faut en plus qualifier la dépendance entre actifs. Ne pas présenter la
hausse mesurée des rappels comme un effet universel du smile actions, ni
forcer un écart de prix attendu par un correctif.

## Méthode de reprise souhaitée

1. **Fixer une matrice cible explicite** : sous-jacent, date, maturités, ATM,
   strikes incluant 50 % et 60 %, ailes gauche/droite et unités. Distinguer
   hypothèses de desk et cotations observées. Préciser strike/spot initial ou
   strike/forward ; le rappel à 100 % du fixing n'est pas l'ATM forward avec carry.
2. **Qualifier sa représentation** : mesurer l'écart de chaque cellule cible
   à la surface effectivement utilisée. Si la famille actuelle est trop
   restrictive, étudier une représentation plus souple par maturité, avec
   interpolation/extrapolation explicites. Ne pas transformer un échec de
   paramétrisation en verdict d'arbitrage sur la matrice cible.
3. **Contrôler l'absence d'arbitrage** : prix décroissants et convexes en strike,
   cohérence calendaire en variance totale, densités/digitaux admissibles et
   domaine du moteur Local Vol. Distinguer conditions suffisantes et diagnostic
   effectif ; aucune réparation cachée ni repli vers constant.
4. **Isoler les effets** : relever seulement l'aile basse éloignée du seuil,
   puis modifier séparément la pente près du rappel et l'aile droite. Définir
   ce qui reste fixe aux ATM 20 %/30 % : écarts en points de vol ou ratios à
   l'ATM, sans supposer la cohérence d'une translation arbitraire.
5. **Valider hors payoff** : calls, puts et digitaux indépendants aux strikes
   de protection et de rappel, forward, convergence spatiale/temporelle et
   incertitude Monte Carlo. Vérifier que les ailes saisies atteignent la
   diffusion et ne sont pas écrêtées en silence.
6. **Reprendre l'Athena** : premier rappel, rappels conditionnels, non-rappel,
   décomposition capital/coupons/put, coupon résolu et perte. Séparer effet de
   surface, résidu de calibration et effet de dynamique LV/Heston/LSV ; mêmes
   contrats, marché, conventions et tirages couplés lorsque c'est pertinent.
7. **Étendre ensuite au worst-of** : corrélation de browniens, dépendance
   terminale/conditionnelle, convergence et limites des conclusions mono.

## Décision pour l'Optimizer en attendant

Continuer par des **calculs directs dans le modèle déclaré**, sans ratio de
conversion GBM → Dupire/Heston/LSV ni interpolation de prix entre modèles.
Le périmètre qualifié reste Athena européen sous GBM jusqu'à qualification
explicite des autres familles et modèles. L'accélération immédiate est la
parallélisation bornée des candidats, avec graines conservées, classement
déterministe, budget mémoire et arrêt des processus du calcul à l'annulation.
Le Copilot et la conservation des recherches restent différés.

## Références de reprise

- [Profils et éditeur de surface](VOL_SURFACE_EDITOR_2026-10-07.md).
- [Recette intégrée et décomposition des prix](../../audits/RECETTE_SMILE_INTEGRE_2026-10-07.md).
- [Benchmark de cible commune](../../audits/AUTOCALL_SURFACE_COMMUNE_2026-10-07.md).
- [Product Optimizer V1](../../PRODUCT_OPTIMIZER_V1.md).
- Code : `frontend/src/utils/volSurface.js`,
  `frontend/src/components/VolSurfaceEditor.vue`,
  `backend/app/core/volatility_surface.py`, `smile_calibration.py` et
  `backend/app/core/payscript/engine.py`.
