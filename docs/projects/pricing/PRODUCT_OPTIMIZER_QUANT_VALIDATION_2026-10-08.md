# Product Optimizer — validation quantitative du 08/10/2026

État : **implémenté localement et validé par tests ciblés**, sans commit ni push.
Périmètre : Athena à protection européenne, mono-actif / worst-of, GBM à
volatilité constante, mêmes hypothèses manuelles et mêmes conventions de dates.
Le [smile urgent](SMILE_ACTIONS_URGENT_2026-10-08.md) reste différé. Le marché,
Phoenix et le Copilot restent les lots suivants.

**Suite livrée le même jour :** [marché et économie d’émission](PRODUCT_OPTIMIZER_MARKET_ECONOMICS_2026-10-08.md).
Les hypothèses copiées du Pricer, courbes et funding sont désormais utilisés dans
toutes les phases ; les chiffres et la recette ci-dessous décrivent le lot quantitatif initial.

## Problème traité

La résolution du coupon et son repricing utilisaient la graine 42. Ce repricing
vérifiait le résultat numérique du solveur, mais ne validait pas le coupon sur
un échantillon indépendant. Les probabilités et la durée ne prenaient que les
jambes de base des paires antithétiques. Les intervalles étaient ponctuels,
sans tenir compte de la sélection parmi plusieurs structures.

Un coupon donnant exactement le pair sur cet échantillon peut donner un autre
prix sur de nouveaux tirages. L'admissibilité et la précision du classement
doivent donc être contrôlées avant recommandation.

## Fonctionnement livré

1. Exploration inchangée : grille, dichotomie et repricing direct à graine 42.
2. Calcul des métriques sur **les deux jambes**, moyennées par paire. L'unité
   indépendante demeure la paire, soit N observations et non 2N.
3. Classement exploratoire, puis sélection figée des cinq meilleurs candidats
   admissibles au maximum. Le nombre effectivement retenu fixe la correction
   statistique. Aucun remplacement après observation d'un échec de validation.
4. Pour chaque candidat, **coupon proposé conservé** et deux nouveaux pricings
   directs : N paires à graine 100042, puis 2N paires à graine 200042. Les graines
   communes entre candidats facilitent les comparaisons ; les deux échantillons
   sont distincts de l'exploration et l'un de l'autre.
5. Contrôle de compatibilité N/2N du prix, de la perte Q, du rappel anticipé Q et
   de la durée moyenne. Un écart dépassant le seuil empêche la confirmation.
6. Application des contraintes aux métriques et intervalles du **second jeu de
   tirages**, sans réajuster le coupon au nouveau prix.
7. Classement final et Pareto limités aux candidats confirmés. Les autres restent
   consultables avec leur statut. L'export conserve les métriques exploratoires,
   les graines, tailles, intervalles et contrôles des deux validations.

Le `recommended_id` ne peut désigner un candidat `PENDING`, `NOT_SELECTED`,
`REJECTED` ou `FAILED`. Si le budget est atteint avant sa confirmation, un
candidat exploratoire ne devient pas recommandable. Une validation partielle
peut recommander les seuls candidats déjà confirmés, avec `complete=false`.

## Estimateurs et niveau de confiance

La moyenne et la variance des indicatrices de perte/rappel et des durées se
calculent sur les moyennes de paires. La corrélation antithétique est donc prise
en compte, sans prétendre doubler le nombre d'observations indépendantes.

Pour une sélection de K candidats, l'allocation est `alpha = 0,05 / (9 × K)` :
quatre intervalles finaux, quatre diagnostics N/2N et un intervalle de coupon
équitable. C'est une allocation de Bonferroni conditionnelle à une sélection
figée avant les tirages de validation. Elle ne requiert pas d'indépendance entre
les candidats. [Méthode de Bonferroni, NIST](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm).

- **Prix** : approximation normale, avec erreur-type du moteur fondée sur N
  payoffs actualisés moyennés par paire. Les endpoints moteur sont arrondis à
  six décimales ; la récupération de l'erreur-type est arrondie vers le haut.
- **Perte, rappel, durée** : bornes empiriques de Bernstein à deux queues. Pour
  des observations dans `[a,b]`, rayon
  `sqrt(2 × variance × log(4/alpha) / N) + 7 × (b-a) × log(4/alpha) / (3 × (N-1))`.
  Les probabilités sont dans `[0,1]` et la durée dans `[0,T]`. Le terme non nul
  subsiste même sans événement observé : zéro perte observée ne certifie pas une
  probabilité de perte nulle.
  [Maurer et Pontil, théorème 4](https://www.cs.mcgill.ca/~colt2009/papers/012.pdf).
- **Compatibilité N/2N** : différence des moyennes comparée à un quantile normal
  multiplié par la racine de la somme des variances d'estimation. Les jeux de
  tirages sont distincts. C'est un diagnostic approximatif, pas une preuve de
  convergence.

Les champs historiques `price_ic95` et `probability_*_ic95` restent présents pour
les consommateurs existants. Après confirmation, ils portent des intervalles
élargis pour la sélection, et non des IC ponctuels à 95 %. La méthode et
`per_check_alpha` sont explicités dans `candidate.validation` ; l'interface les
appelle intervalles simultanés.

Le niveau familial de 95 % est **approximatif pour l'ensemble**, puisque le prix,
la compatibilité et le diagnostic de coupon utilisent des approximations
normales. Il ne couvre ni une erreur de modèle, ni une donnée de marché inexacte,
ni le biais de grille temporelle. Les bornes de Bernstein sont plus prudentes
que les anciens filtres ; certaines recherches peuvent avoir moins de solutions.

## Incertitude du classement des coupons

Un diagnostic estime le coupon équitable sur les flux indépendants, en utilisant
l'affinité du payoff Athena au coupon. Il reconstitue le PV avec les paiements
contractuels et vérifie son accord avec le moteur avant de calculer un intervalle
normal par méthode delta pour le ratio. Il **ne modifie jamais** le coupon
proposé ou son prix : les pricings et contraintes portent sur le coupon conservé.

Pour l'objectif coupon maximal, l'interface distingue : intervalle du premier
candidat séparé de ceux des autres candidats confirmés, intervalles qui se
recouvrent, diagnostic indisponible ou comparaison insuffisante. Comparer les
intervalles marginaux est conservateur : cela n'exploite pas la covariance entre
différences de coupons sur les tirages communs. Un recouvrement ne prouve pas une
égalité et ne certifie pas une inversion du classement.

Le classement demeure limité à la sélection, avec les tie-breaks métier
existants. Une optimalité globale ou un classement certifié de toute la grille
ne sont pas revendiqués. Les objectifs protection/coupon cible conservent leur
ordre structurel ; leurs coupons doivent aussi passer le contrôle indépendant.

## Budget et processus

Le budget de travail inclut, par candidat exploré, les 18 itérations, les deux
bornes et le repricing, plus `3N × min(5, nombre de candidats)` pour la validation.
La mémoire réserve le plus grand calcul individuel, **2N paires**, et le nombre
de workers simultanés. Jusqu'à 20 000 paires sont saisissables pour l'exploration,
soit 40 000 pour le second holdout si le budget mémoire/travail le permet.

Les processus existants exécutent les deux phases. Le délai global reste 120 s,
sans remise à zéro entre phases. La fermeture du flux arrête et nettoie le pool
de validation comme celui d'exploration. En séquentiel, l'arrêt attend la fin du
candidat courant, qui peut comprendre ses deux pricings de validation.

## Recette quantitative indépendante

Script reproductible hors serveur, réseau et base réelle :

```powershell
.venv/Scripts/python.exe -X utf8 backend/scripts/validate_product_optimizer.py --output output/optimizer-quant-20261008/validation.json
```

Une référence NumPy simule directement le GBM corrélé **aux dates contractuelles**,
puis applique un payoff Athena vectorisé indépendant de l'évaluateur PayScript.
Elle conserve l'actualisation aux dates de paiement, le rappel à maturité et la
perte terminale. Un test contrôle cette référence contre la formule fermée d'un
Athena mono-actif à observation unique.

Trois scénarios synthétiques : mono trois ans trimestriel vol 20 %, worst-of
deux actifs trois ans trimestriel vols 25/30 % et corrélation 40 %, mono un an
mensuel vol 40 %. Taux 3 %, dividendes 2 %, protection 60 %, rappel 100 %,
convention Modified Following, paiement J+3. Les coupons sont résolus sur 1 000
paires puis conservés. Bornes de coupon jusqu'à 50 % dans ce panel : certains
scénarios ne sont pas finançables sous la borne habituelle de 30 %.

Référence : 80 000 paires à graine 314159. Moteur : 1 000 / 4 000 / 12 000 paires
à 52 pas/an et 4 000 paires à 104 / 208 pas/an, avec graines distinctes.
Seuils fixés avant mesure : écart inférieur à quatre erreurs-types combinées,
plus 10 bps pour le prix ou 0,01 pour les autres métriques. Ce sont les seuils
de ce panel, pas une borne globale sur l'erreur de discrétisation.

**Les 60 comparaisons aux références passent**, en 33,45 s. Les erreurs-types du
prix à 52 pas/an sont :

| Scénario | 1 000 paires | 4 000 paires | 12 000 paires |
|---|---:|---:|---:|
| Mono trois ans, 20 % | 30,10 bps | 15,74 bps | 8,91 bps |
| Worst-of deux actifs | 76,60 bps | 37,14 bps | 21,40 bps |
| Mono un an, 40 % | 37,99 bps | 18,98 bps | 10,79 bps |

La décroissance est cohérente avec l'erreur Monte-Carlo. Le coupon résolu sur le
petit échantillon donne dans la référence des prix de 100,3723 %, 101,1250 % et
100,1014 % : il serait incorrect de supposer que la résolution initiale garantit
le pair sur des tirages indépendants.

Les différences entre 52/104/208 pas ne sont pas monotones avec ces graines.
Cette recette contrôle leur compatibilité avec une référence, mais n'isole pas
un biais temporel à quelques bps. Un panel plus précis et couplé, ainsi que la
qualification des observations exactes dans le moteur, restent à traiter avant
de revendiquer une précision de booking. Le moteur en production reste à 52 pas.

[Rapport complet](../../../output/optimizer-quant-20261008/validation.json).

## Recette de recherche et performance

Le benchmark des quatre protections 55/60/65/70 %, Athena mono trois ans
trimestriel, N=2 000, tolérance de prix ±3 points, a été rejoué avec la validation
activée. Les quatre candidats passent. C0004 reste premier, mais ses intervalles
de coupon et ceux de C0003 se recouvrent : état `OVERLAPPING` affiché.

Séquentiel **31,362 s**, deux processus **17,914 s**, démarrages et deux phases
inclus. Prix, coupons, analytics, diagnostics et classement identiques ; aucun
processus enfant du benchmark restant. Cette mesure unique, réalisée sur huit
CPU logiques, ne garantit pas un gain universel.

[Dossier complet des deux recherches](../../../output/optimizer-quant-20261008/run-comparison.json).

## Vérifications et limites restantes

65 tests backend ciblés distincts passent : 61 dans le groupe Optimizer, puis
16 dans le groupe validation/annulation, dont quatre nouveaux et douze déjà
comptés. Pas de suite backend complète. Couverture : paires, événements rares,
coupon conservé, graines distinctes, N/2N, correction multiple, rejet holdout,
sélection sans remplacement, échéance entre phases, classement et incertitude,
formule fermée indépendante, équivalence séquentielle/processus et nettoyage du
vrai pool pendant la validation. Avertissement TestClient/httpx préexistant.

Frontend : `npm run build`, **288 tests réussis**, build Vite réussi. La recette
visuelle n'a pas été refaite ; l'accès localhost du navigateur disponible était
bloqué lors du lot précédent. Aucun backend n’a été lancé ou arrêté par l’assistant. Le contrôle final ne
trouve plus de serveur sur localhost:8000 ni de processus Python actif ; il
faut lancer le backend pour utiliser ce lot dans l’application.

Suites métier : convergence temporelle plus précise, couverture empirique des
intervalles/préselection sur davantage de régimes et tailles, différence de
coupons exploitant les tirages communs, puis marché qualifié/funding/coûts et
extension Phoenix. Aucun modèle à smile ni calcul sous mesure physique ajouté.
