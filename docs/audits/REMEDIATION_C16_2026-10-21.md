# C16 — Dépendance des extrema et barrières

Livraison locale du 21 octobre 2026, sans commit ni push. M06-03 est corrigé sur
un domaine explicite, avec refus des configurations panier non qualifiées.
Le prérequis C14 est conservé et les invariants voisins C15, C13 et C01 repassent.
T07 reste partiel jusqu'à la recette de contexte C18 ; aucune qualification
générale de production n'est prononcée.

## Résultat métier et décisions

Dupliquer un actif GBM équivalent, corrélé à 1, ne crée plus un deuxième tirage
indépendant d'extremum. Le minimum, le maximum et le payoff complet retrouvent
ceux du mono lorsque les facteurs et aléas conditionnels sont les mêmes.

Philippe a choisi d'autoriser une **approximation explicitement signalée après
validation de sa méthode et de sa tolérance**, puis a fixé le seuil à **10 points
de base du nominal sur le panel GBM à deux actifs**. Ce choix ne qualifie pas
implicitement les autres modèles ou tous les produits.

| Domaine | Comportement local |
|---|---|
| Mono | Tirages marginaux analytiques conservés ; loi jointe min/max et modèles hors GBM déterministe toujours approximatifs et signalés. |
| Copies GBM équivalentes, corrélation +1 | Facteurs parfaits conservés ; extrema conditionnels communs, avec prise en compte d'une échelle initiale différente. La réduction au mono reste valable avec les taux C15, sans qualifier leur interpolation marginale. |
| GBM à deux actifs, taux déterministes, −99 % <= rho <= +99 % | Approximation par ponts corrélés, contrôlée sur les panels ci-dessous et annoncée dans les sorties. |
| Autres paniers : davantage d'actifs non équivalents, Heston/SABR/Local Vol/LSV, taux stochastiques avec corrélation imparfaite, ou |rho| > 99 % | Refus explicite avant simulation ; aucun basculement automatique en hebdomadaire. Qualification complémentaire nécessaire. |

Le domaine ci-dessus résulte des mesures locales ; la confirmation utilisateur
porte sur le principe d'approximation et son seuil, pas sur une approbation de
production. Une corrélation 99,99 % n'a pas satisfait le panel rapproché au
raffinement testé : elle n'est pas admise par simple assimilation à 100 %.

## Corrections et interactions

- **Dépendance conditionnelle** : les milieux des ponts lognormaux utilisent une
  même matrice de corrélation entre actifs. Sur le dernier sous-intervalle, les
  lois marginales analytiques sont utilisées ; leur dépendance résiduelle reste
  approximative. Les copies parfaitement équivalentes partagent directement le
  tirage mono. Les facteurs opposés échangent les excursions haute et basse.
- **Facteurs singuliers** : une matrice réellement semi-définie positive utilise
  une racine PSD, au lieu d'un bruit diagonal inventé. La même règle s'applique
  au bloc résiduel taux/actions de C15. Les réparations matérielles de matrices
  incohérentes et leurs refus restent distincts. Les contrôles vérifient que deux
  trajectoires GBM identiques restent identiques avec et sans couplage aux taux.
- **Raffinement identifiable** : 64 sous-pas lorsque la plus forte corrélation
  absolue est au plus 50 %, 256 jusqu'à 90 %, puis 1 024. Les copies équivalentes
  prennent le chemin marginal commun, sans subdivision. Les sorties indiquent
  le chemin effectivement utilisé. Le seuil nul de volatilité n'ajoute plus
  artificiellement une excursion.
- **Greeks et budget C07** : la famille de repricings du Greek de corrélation
  utilise un raffinement commun, y compris si son bump franchit un seuil de
  la politique. Un bump qui quitte le domaine qualifié est refusé. Les coûts de
  reconstruction et les buffers de récursion entrent dans le budget ; le parcours
  est effectué pas par pas, sans conserver toute la grille fine. Les prévisions
  sans matrice disponible utilisent un coût conservateur.
- **C14** : horizon exact, pas effectif, chronologie et paiements conservés.
  Le correctif n'ajoute pas de dates contractuelles et ne transforme pas une
  barrière hebdomadaire en barrière continue. Le monitoring hebdomadaire garde
  son comportement ; les cas parfaitement singuliers reçoivent désormais le
  facteur mathématiquement dégénéré demandé, également sur cette grille.
- **Consommateurs et archives** : prix, probabilités et trajectoires utilisent
  le même reconstructeur et les mêmes admissions. Le message et les paramètres
  numériques traversent l'API de prix, le pricing en vie et `market_used` du MtM.
  `bridge.py` entre dans l'empreinte moteur des ValuationRun. Les archives,
  contrats et fixings C13 ne sont pas réécrits. Le contexte complet commun C18
  demeure un chantier distinct.

## Preuves quantitatives

### Copies conditionnelles

Deux actifs, extrémités toutes égales à 1, sigma 20 %, intervalle d'un an,
barrière basse 80 %, 65 536 tirages, seed 17 :

| Mesure | Avant C16 | Après C16 |
|---|---:|---:|
| Franchissement par au moins une copie | 16,0324 % | 8,4030 % |
| Minimum identique entre copies | Non | Oui, exactement |
| Maximum identique entre copies | Non | Oui, exactement |

La probabilité conditionnelle analytique est
`exp(-2 log(0,8)^2 / 0,2^2) = 8,29388 %`. L'écart après correction est compatible
avec le bruit Monte Carlo. Les payoffs complets de digitales basse/haute et d'un
paiement anticipé avec STOP sont aussi comparés chemin par chemin, sur une banque
commune d'extrémités et d'aléas de pont, avec égalité des flux datés.

### Approximation à corrélation imparfaite

La méthode ne remplace pas les extrema indépendants par une copule supposée
exacte. Elle raffine des ponts gaussiens corrélés et limite l'indépendance
résiduelle aux feuilles. La difficulté de la loi jointe et l'usage de bornes de
Fréchet sont décrits dans le
[travail de Shevchenko](https://arxiv.org/abs/0904.1157).
La variante de reconstruction et la politique de raffinement de cette livraison
sont celles de Structura ; elles ne sont pas présentées comme un algorithme
exact tiré de cette publication.

Sur une feuille, si `p_i` est la probabilité marginale de franchissement,
`max(p_i) <= P(au moins un franchissement) <= min(1, sum(p_i))`.
Les bornes de survie sont multipliées sur les sous-intervalles conditionnels,
puis moyennées. Leur largeur mesure l'incertitude résiduelle de dépendance,
séparément de l'erreur Monte Carlo du niveau de prix.

- **21 configurations conditionnelles** : extrémités à 1 ; sigma 20 % ; couples
  (horizon, barrière) = (1 an, 80 %), (1 an, 90 %), (1/52 an, 98 %) ; rho =
  −99 %, 0 %, 50 %, 70 %, 90 %, 95 % et 99 %. Chaque cas utilise 32 768 tirages.
  La largeur moyenne des bornes, majorée de trois erreurs standards de cette
  largeur, atteint au maximum **8,6512 pb**, sous le plafond choisi de 10 pb.
- **Cinq payoffs complets à un an** : 52 pas, sigma 20 %, taux 3 %, q 1 %,
  funding 2 %, barrière basse 80 %, rho = −99 %, 0 %, 50 %, 90 % et 99 %,
  32 768 trajectoires par cas. Le maximum du même critère sur le prix actualisé
  de la digitale est **0,00409 pb**. Le calcul de bornes est indépendant du
  pricer : factorisation Cholesky, probabilités marginales et conditionnement
  adaptatif ; les branches arrêtées conservent leurs bornes, sans prétendre
  connaître leur dépendance.

Ces valeurs ne sont **pas** une garantie d'erreur totale inférieure à 10 pb pour
tout prix. Le bruit Monte Carlo du niveau, la couverture finie du panel et le
risque de modèle restent à traiter séparément. Aucun intervalle d'erreur propre
à chaque valorisation n'est calculé : `per_run_error_bound` est `null`.

## Tests et préservation

**319 cas backend distincts sur 14 fichiers réussis**, dont **43 nouveaux cas C16**,
et **7 tests frontend** de l'utilitaire de barrières. Les 26 configurations
quantitatives ci-dessus constituent des mesures complémentaires, sans être
ajoutées au total pytest. Les références du harnais nominal, y compris les deux
cas mono de monitoring continu, n'ont pas été changées.

Les six premières acceptations C16 échouaient avant correction : extrema des
copies, trois payoffs complets, volatilité nulle et provenance de l'approximation.
Quatre tests de portefeuille échouaient aussi, leur acteur n'ayant aucun rôle
métier depuis C01. La fixture utilise désormais un utilisateur Front explicite ;
un nouveau test confirme le refus de l'acteur sans rôle. Aucune permission
applicative n'a été assouplie. Les tests concernés repassent tous.

Les panels C14 et C15, les tests de courbes, budgets, Greeks avec état,
fixings/archives C13, worker VaR et consommateurs passent sur le périmètre ciblé.
La suite backend complète n'a pas été lancée. Aucun fichier Vue n'a changé ;
aucun build frontend n'était requis. Aucun serveur n'a été démarré.
Les tests utilisent des données synthétiques, des bases temporaires et un garde
HTTP. La base métier n'a été ni ouverte ni créée.

Les cas individuels, commandes, mesures et empreintes sont dans
[C16_VALIDATION.json](remediation-lot-0-2026-10-20/C16_VALIDATION.json).
Les journaux et scripts de mesure sont dans
`.runtime/diagnostic-acceptance/c16-2026-10-21/`. La baseline C16 conserve
l'état local précédent ; les modifications préexistantes et preuves C11 à C15
sont contrôlées par empreintes.

## Restant

- **T07** : validé localement pour les copies et le panel imparfait décrit ; le
  rapprochement complet des contextes et consommateurs C18 reste ouvert.
- **D04** : arbitrage partiel sur l'approximation et le seuil C16, pas une
  qualification de production. Restent notamment les autres modèles/paniers,
  taux stochastiques imparfaitement corrélés, doubles barrières et sensibilités.
- Des demandes de monitoring continu auparavant acceptées avec une dépendance
  incorrecte sont désormais refusées hors domaine. Aucun contrat sauvegardé
  n'est modifié. Il faut conserver le refus explicite jusqu'à qualification ou
  choisir volontairement une autre convention contractuellement adaptée.
- Pas de recalcul, backfill ou réécriture des données réelles. Les rapprochements
  avec d'anciens résultats doivent tenir compte de l'empreinte moteur.
