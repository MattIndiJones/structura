# Optimizer — capital protégé, booster et gear put

État au 08/10/2026 : extension locale des adaptateurs qualifiés sous GBM constant.
Les scripts du catalogue sont réutilisés tels quels. Le smile actions reste dans
la note urgente dédiée ; aucune conversion de prix entre modèles n'est introduite.

## Paramètres et conventions contractuelles

| Script | Objectif | Axes de recherche | Quantité résolue |
|---|---|---|---|
| Capital garanti avec participation | Participation maximale | Maturité, strike de participation | `PART`, participation |
| Booster | Participation maximale | Maturité, cap de remboursement | `PART` |
| Booster | Cap maximal | Maturité ; participation imposée | `CAP`, niveau de remboursement |
| Autocall gear put | Coupon maximal ou coupon cible avec perte moyenne minimale | Maturité, fréquence, rappel, strike du put, gearing | `COUPON`, montant unique au rappel |

Le capital protégé paie `1 + PART × max(performance − STRIKE, 0)` à maturité,
hors défaut émetteur. Le booster paie la hausse démultipliée et plafonnée,
avec baisse subie une pour une. **CAP = 130 % signifie remboursement maximal
130 %, soit gain maximal 30 %.** Le gear put paie un coupon unique au rappel,
quelle que soit la date du rappel : son script n'utilise pas `INDEX`.
Sans rappel, la perte sous le strike du put vaut
`min(1, GEARING × (1 − performance / strike))` ; elle est plafonnée au nominal.
La barrière/strike de perte est européen dans ces adaptateurs.

Stockage et moteur : pourcentages en fractions (`PART=1.5` = 150 %,
`CAP=1.3` = 130 %). Le gearing est affiché comme un multiple (`2 ×`), envoyé
comme `GEARING=2` ; la déclaration PayScript reste un pourcentage (200 %).
Le coupon gear put est conservé tel quel, sans multiplication par fréquence/12.
Les cinq familles précédentes gardent leur convention de coupon annuel nominal.

Bornes : maturité 12–60 mois ; strike de participation 50–150 % ; participation
résolue 0–500 % ; cap exploré/résolu 100–300 % ; participation imposée booster
0,5–500 % ; strike du put 30–120 % ; gearing 1–5 × ; rappel initial 80–120 %.
Le strike du put ne peut pas dépasser le rappel dans cette recherche.

## Champs dynamiques

Le serveur publie les modes et leurs paramètres à partir des déclarations du
script, avec un adaptateur explicitement qualifié. L'interface sélectionne les
axes, réglages fixes, bornes de résolution et objectifs applicables. Une modification
incompatible du script désactive sa capacité plutôt que d'ignorer un paramètre.

En passant du booster « participation » au booster « cap », le cap disparaît des
axes et devient la quantité résolue ; la participation devient une valeur imposée.
Le capital protégé n'affiche ni coupon, ni protection conditionnelle, ni fréquence
ou contrainte de rappel. Le gear put affiche strike et gearing, sans `M_KI_BAR`.
Les tableaux, le tri, la recommandation et la frontière utilisent les métadonnées
du résultat conservé, même si la saisie change ensuite.

## Pricing et contrôle du risque

Chaque candidat conserve le calcul direct et la dichotomie sur ses bornes.
Coûts initiaux déduits du budget, courbes et funding appliqués comme dans le lot
marché précédent. Jusqu'à cinq candidats sont sélectionnés une fois ; leur
quantité résolue reste fixe sur les tirages indépendants N/2N.

Un plateau du booster peut rendre plusieurs participations/caps équivalents.
Si la borne haute finance aussi exactement le budget sur l'échantillon
d'exploration, elle est retenue ; le maximum reste limité aux bornes définies.
Une cible hors de l'intervalle de prix aux bornes est rejetée. Aucun taux de
participation artificiel n'est proposé pour financer un nominal protégé trop cher.

Pour booster et gear put, les jambes « Put vendu » donnent trois métriques Q,
non actualisées et avant coupon : probabilité de perte en capital, perte moyenne
en fraction du nominal et sévérité moyenne conditionnelle à cette perte.
La probabilité de perte investisseur existante compare toujours tous les flux
au prix d'émission brut. Ces deux notions ne doivent pas être confondues.

Le plafond facultatif de perte en capital moyenne filtre sur sa borne haute.
Les deux métriques élémentaires supplémentaires entrent dans l'allocation
Bonferroni (13 contrôles par candidat). L'intervalle de sévérité est dérivé des
bornes conjointes de la moyenne et de la probabilité ; sans perte observée,
l'estimation conditionnelle est indisponible et l'intervalle reste [0, 100 %].

Le diagnostic de quantité équitable est affine pour coupon/capital protégé et
seulement local pour le booster, dont les trajectoires peuvent changer de statut
plafonné. Il ne certifie pas le classement du booster. Une exposition nulle rend
le diagnostic indisponible. La convergence de la grille temporelle hebdomadaire
reste à qualifier séparément ; ces contrôles ne qualifient pas le smile.

## Vérifications

Tests ciblés : branches contractuelles aux seuils, protection nominale, cap,
gearing et plancher de remboursement ; coupon gear identique au premier et
dernier rappel ; formule indépendante de Black-Scholes pour le capital protégé ;
solveur et holdout avec courbes/funding/coûts ; bornes et plateau ; égalité réelle
entre exécution séquentielle et processus Windows pour les nouvelles quantités.
Les régressions des cinq familles précédentes et la fixture serveur/frontend
sont conservées. Le build frontend inclut les tests unitaires.

Recette navigateur réalisée sur l'application construite, avec une base SQLite
isolée et scheduler désactivé. Deux défauts repérés puis corrigés : réinitialisation
des bornes lors du changement de quantité, et pas HTML de la participation imposée.
164 tests backend ciblés distincts et 308 tests frontend passent ; `npm run build`
réussit. Recette à un an, Euro Stoxx 50, hypothèses synthétiques vol 20 %,
dividende 2 %, taux 3 %, N=1 000, tolérance prix 3 points : quatre modes
produisent chacun un candidat confirmé. Participation du capital protégé 36,34 %,
booster participation 206,20 % avec cap 130 %, booster cap 139,12 % avec
participation 150 %, gear put coupon unique 2,51 % avec strike 60 % / gearing 2 ×.
Ces valeurs sont des résultats de recette, pas des cotations de marché.
Le changement de formulaire conserve les métadonnées du résultat précédent.

Recette en largeur 390 px : formulaire en une colonne, champs contractuels
accessibles ; espacement des saisies de grille réduit pour lire les seuils.
Le bandeau global de navigation déborde à cette largeur ; ce défaut partagé
à l’application reste hors du lot Optimizer. Aucun défaut console observé.
