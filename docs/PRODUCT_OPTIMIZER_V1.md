# Product Optimizer V1

État au **05/10/2026** : implémenté localement, tests ciblés et recette navigateur
effectués. Aucun commit ni déploiement. Cette note est placée à ce chemin à la
demande explicite de Philippe.

## Évaluation de l'existant et choix de périmètre

Le frontend utilise Vue 3, Vue Router, Tailwind et Chart.js. Le backend expose des
routeurs FastAPI authentifiés avec `get_current_user`, des contrats Pydantic et un
référentiel SQLModel de sous-jacents. Le moteur PayScript possède déjà un catalogue,
un compilateur de calendriers, le Monte-Carlo et un solveur de paramètres.

La présence de GBM, Heston, SABR, Local Vol et LSV dans le moteur ne constitue pas
une qualification de toutes leurs combinaisons pour l'optimisation. La V1 retient
**Athena à barrière européenne sous GBM**, mono-actif ou worst-of, sur hypothèses
explicites. Elle réutilise le script `PRODUCTS['autocall_athena']`,
`resolve_constats`, `solve_for_param` et `run_mc`. Aucun second moteur de pricing
n'est créé.

Phoenix existe dans le catalogue général, mais sa qualification pour l'Optimizer
(mémoire, coupon conditionnel et interprétation des métriques) est différée. Son
statut `UNSUPPORTED` concerne ce module ; il ne signifie pas que Phoenix est
inutilisable dans le Pricer.

## Disponible maintenant

| Élément | Périmètre |
|---|---|
| Navigation | Structuring Intelligence → Product Optimizer ; Copilot « À venir », sans lien |
| Produit | Athena, protection conditionnelle européenne, coupon accumulé payé au rappel |
| Sous-jacents | 1 à 3 actions/indices déclarés par l'utilisateur, présents et actifs au référentiel |
| Panier | Mono-actif ou worst-of ; panier fixé par l'utilisateur pour toute la recherche |
| Modèle | `constant` = GBM ; `auto` choisit explicitement ce seul modèle autorisé |
| Devises | EUR, USD, GBP, CHF, JPY, SGD ; tous les actifs dans la devise de règlement |
| Objectifs | Coupon maximal ; barrière minimale ; coupon cible avec meilleure protection |
| Recherche | Grille déterministe et dichotomie du coupon pour chaque structure |
| Décision | Recommandation explicable, alternatives triables, comparaison de 2 à 5 candidats |
| Graphique | Coupon / barrière, candidats admissibles, Pareto et sélection |
| Conservation | Résultat temporaire dans la page, export JSON complet |

Le type action/indice est **déclaratif** : le référentiel existant ne porte pas de
classification métier permettant de le certifier automatiquement. La V1 ne génère
pas de combinaisons de paniers à partir d'une liste de tickers autorisés.

### Paramètres explorés et paramètre résolu

- Maturité : 12 à 60 mois entiers, minimum/maximum/pas.
- Barrière de protection : 30 % à 100 %, minimum/maximum/pas.
- Seuil de rappel : 80 % à 120 %, minimum/maximum/pas.
- Fréquences : ensemble choisi parmi 1, 3, 6 et 12 mois.
- Coupon : **résolu**, entre deux bornes annuelles de 0 % à 50 %, pour atteindre
  un prix cible entre 80 % et 120 %. Ce n'est pas un axe de grille.

Les grilles utilisent une arithmétique décimale : la borne haute entre dans la
grille seulement si le pas l'atteint. Une maturité non multiple de la fréquence ou
une protection supérieure au seuil de rappel est rejetée avant pricing.

### Payoff et dates

Au rang `k`, le script catalogue paie le nominal et `k × COUPON` si le worst-of
atteint le seuil de rappel, puis s'arrête. Sans rappel, aucun coupon n'est payé ; à
maturité, le nominal est restitué si la protection européenne tient, sinon le
worst-of est remboursé. Le rappel à maturité existe contractuellement mais ne
compte pas comme rappel **anticipé**.

Le coupon annuel affiché est nominal :
`COUPON PayScript = coupon_annuel × fréquence_en_mois / 12`.
Il ne constitue ni un TRI ni une promesse de rendement annuel réalisé.

La date des hypothèses, le strike et la valeur sont identiques en V1. Le calendrier
est ancré sur le strike ; la convention de jour ouvré doit être choisie. Le
règlement vaut J+3 ouvrés par défaut, modifiable de 0 à 10 jours. Les paiements
contractuels du calendrier sont utilisés pour l'actualisation. Les observations
sont projetées sur la grille approximativement hebdomadaire du moteur ; son pas
vaut `T / round(T × 52)` et son dernier nœud est exactement `T`.

## Architecture et fichiers

| Fichiers | Responsabilité |
|---|---|
| `backend/app/core/product_optimizer/contracts.py` | Requête, plages, contraintes, candidat et validations |
| `backend/app/core/product_optimizer/capabilities.py` | Liste explicite des capacités, exclusions et plafonds |
| `backend/app/core/product_optimizer/service.py` | Budget, génération, adaptation PayScript, analytics, filtre, classement, événements |
| `backend/app/core/product_optimizer/__init__.py` | Paquet métier |
| `backend/app/api/product_optimizer.py` | Authentification, référentiel, admission et streaming |
| `frontend/src/views/StructuringView.vue` | Entrée du module et Copilot indisponible |
| `frontend/src/views/ProductOptimizerView.vue` | Contraintes, progression, résultats, comparaison et Chart.js |
| `frontend/src/utils/productOptimizer.js` | Appels authentifiés, lecture NDJSON, taille de grille |
| `backend/tests/test_product_optimizer.py` | Contrats, cas économiques, orchestration et API |
| `frontend/src/utils/productOptimizer.test.js` | Grilles, candidats admissibles et streaming |

Fichiers existants modifiés pour l'intégration : `backend/app/main.py`,
`frontend/src/router/index.js`, `frontend/src/components/AppHeader.vue` et
`docs/README.md`, ainsi que les bundles versionnés de `frontend/dist/` régénérés
par le build. Le moteur PayScript, le solveur, les tables de données et les
workflows de booking restent ceux de l'existant.

Flux : requête validée → budget → candidats → calendrier catalogue → solveur
existant → revalorisation → analytics → contraintes → classement → résultat.
Le service métier peut être appelé directement sans interface web ni LLM ;
`run_events` accepte un adaptateur de pricing injecté pour les tests et extensions.

## Contrats et API

Tous les objets d'entrée refusent les champs inconnus et les valeurs non finies.
Les pourcentages sont des **fractions dans l'API** ; les maturités structurelles
sont des mois entiers, les durées estimées sont des années.

Exemple pour un ticker présent dans le référentiel :

```json
{
  "schema_version": 1,
  "objective": "maximize_coupon",
  "product_family": "autocall_athena",
  "model": "auto",
  "currency": "EUR",
  "strike_date": "2026-10-05",
  "convention": "modified_following",
  "settlement_lag": 3,
  "market": {
    "as_of": "2026-10-05",
    "source": "USER_ASSUMPTION",
    "rate": 0.03,
    "underlyings": [{
      "ticker": "^STOXX50E", "name": "Euro Stoxx 50",
      "asset_type": "index", "currency": "EUR", "sigma": 0.20, "q": 0.02
    }],
    "correlation": [[1]]
  },
  "ranges": {
    "maturity_months": {"minimum": 36, "maximum": 60, "step": 12},
    "protection_barrier": {"minimum": 0.60, "maximum": 0.60, "step": 0.05},
    "autocall_trigger": {"minimum": 1, "maximum": 1, "step": 0.05},
    "observation_months": [3]
  },
  "constraints": {
    "target_price": 1,
    "price_tolerance": 0.03,
    "coupon_minimum": 0,
    "coupon_maximum": 0.30,
    "max_probability_loss": 0.15
  },
  "search": {"strategy": "grid", "simulations": 1000, "max_candidates": 32, "seed": 42}
}
```

Contraintes facultatives supplémentaires : `target_coupon`, `coupon_tolerance`,
`min_probability_autocall`, `max_expected_maturity`. Le coupon cible est obligatoire
pour l'objectif `target_coupon`. La matrice doit avoir la bonne dimension, être
symétrique, de diagonale unité et définie positive ; aucune réparation implicite.

| Route | Comportement |
|---|---|
| `GET /api/product-optimizer/capabilities` | Capacités et limites, authentifié |
| `POST /api/product-optimizer/estimate-search` | Validation du référentiel, nombre de candidats, mémoire/travail estimés, motifs de refus |
| `POST /api/product-optimizer/run` | Même validation puis flux NDJSON : `started`, `progress`, `result` ou `error` |

Un budget dépassé produit HTTP 422 avant tout pricing ; un Optimizer déjà occupé
produit HTTP 429. Les erreurs d'entrée détaillées sont affichées ; une exception
interne d'un candidat devient `FAILED`, avec message public générique et traceback
dans le journal serveur. Les autres candidats continuent. Une erreur globale de
streaming n'est jamais présentée comme un résultat final valide.

Il n'existe pas de route de récupération par identifiant, de cache de résultats ni
de table de runs en V1. Les résultats restent locaux à la requête et au composant
Vue ; les réponses de calcul portent `Cache-Control: no-store`. L'authentification
utilise les comptes et jetons existants. Un utilisateur ne peut pas consulter les
résultats d'un autre par un identifiant de run. Le sémaphore partagé contient
uniquement un droit de calcul, jamais des données utilisateur.

En Mode Démo, les saisies et résultats sont entièrement masqués ; désactiver le
mode restaure la page. Il n'existe pas de jeu de résultats fictifs pour ce module.

### Candidat et résultat

`OptimizationCandidate` contient l'identifiant stable `C0001…`, la famille, le
modèle, les paramètres structurels, le coupon annualisé, le prix d'émission, la
juste valeur, les IC95, les probabilités et la durée moyenne. Trois états séparés :

- `pricing_status` : `PENDING`, `PRICED`, `SKIPPED`, `FAILED` ;
- `analytics_status` : `UNAVAILABLE`, `AVAILABLE`, `FAILED` ;
- `constraint_status` : `PENDING`, `PASS`, `REJECTED`.

S'ajoutent `rank`, `pareto_efficient`, `warnings`, `errors`, `rejection_reasons` et
`pricing_input` pour les candidats effectivement valorisés. Ce dernier contient le
script catalogue, le calendrier et les entrées normalisées du Pricer. Les
sous-jacents communs figurent dans la requête du résultat et dans `pricing_input`.
Les métriques manquantes restent nulles et ne peuvent pas faire passer un filtre.

Le résultat contient la requête sérialisée, son SHA-256, la version de schéma et
méthode, la graine, la provenance/date des hypothèses, les candidats, les compteurs,
l'identifiant recommandé, l'explication et la durée. `complete=false` signale une
exploration interrompue ; la recommandation porte alors sur les seuls candidats
évalués. La version `optimizer-v1` est une version de méthode, pas une empreinte
complète du code de pricing installé.

## Analytics, incertitude et classement

Les probabilités sont sous **mesure risque-neutre Q**, avec taux et dividendes plats,
volatilités constantes et corrélations saisies. Aucun téléchargement ou fallback
de marché n'est caché derrière ces hypothèses.

| Métrique | Définition et filtre |
|---|---|
| Juste valeur / IC95 | Sorties du moteur ; IC95 entier à l'intérieur de prix cible ± tolérance |
| Perte Q | Somme des flux non actualisés inférieure au prix d'émission ; plafond appliqué à la borne haute Wilson 95 % |
| Rappel anticipé Q | Dernier flux avant la maturité ; minimum appliqué à la borne basse Wilson 95 % |
| Durée moyenne | Moyenne des temps de dernier flux sur la grille d'observation ; plafond appliqué à moyenne + 1,96 erreurs-types |

La perte définie ici inclut les coupons éventuels et ne se confond ni avec une
perte sur le seul nominal ni avec une probabilité de franchissement de barrière.
La durée moyenne mesure la terminaison économique observée, sans ajouter le délai
de règlement. Il ne s'agit pas d'une duration de taux.

### Pourquoi conserver les antithétiques

Le moteur valorise `N` paires `(Z, -Z)`. Son prix est la moyenne des moyennes de
paires ; son erreur-type est estimée sur ces `N` observations indépendantes.
Ce traitement est correct. Les `2N` trajectoires individuelles ne sont pas
indépendantes, donc leur appliquer directement un intervalle binomial conçu pour
`2N` tirages indépendants serait incorrect.

La V1 conserve les antithétiques pour le prix, et calcule les probabilités et leur
intervalle de Wilson sur les `N` jambes de base indépendantes. Elle pourrait
ultérieurement exploiter les deux jambes avec une variance estimée par paire.

Le coupon arrondi retourné par le solveur est repricé pour vérifier son prix et son
incertitude, avec les **mêmes tirages**. Ce contrôle n'est pas une validation sur
un échantillon indépendant. Les IC sont ponctuels, approximatifs, sans correction
pour sélection multiple parmi les candidats. Ils ne couvrent ni le risque de
modèle ni l'incertitude des hypothèses de marché. Aucun test de convergence global
n'est revendiqué.

### Classement transparent

Après élimination des candidats non admissibles :

- **Coupon maximal** : coupon décroissant, perte Q croissante, barrière croissante,
  écart au prix cible croissant, puis identifiant stable.
- **Protection maximale** : barrière croissante, perte Q croissante, coupon
  décroissant, écart au prix cible, puis identifiant.
- **Coupon cible** : le coupon doit être dans sa tolérance, puis même ordre que
  protection maximale.

La frontière de Pareto porte uniquement sur coupon et barrière, parmi les
candidats admissibles. Elle n'affirme pas une dominance sur toutes les dimensions
de risque ou sur des maturités comparables. Aucun score « équilibré » arbitraire,
aucun appel LLM et aucune optimalité globale ne sont présentés.

## Protection des ressources et limites connues

Plafonds : 64 candidats, 20 000 paires par valorisation, 1 000 valeurs par axe,
250 millions d'unités de travail estimées et 256 Mio de mémoire estimée. Le budget
réutilise `estimate_mc_batch` et provisionne 18 itérations de solveur, les deux
bornes et une revalorisation par candidat. L'interface démarre avec 4 000 paires,
un plafond utilisateur de 32 candidats et une grille de trois maturités.

Le délai de 120 secondes est vérifié **entre candidats** : il n'interrompt pas un
calcul numérique déjà lancé. L'annulation ferme le flux client et arrête la
recherche après le candidat courant ; elle ne libère pas prématurément sa capacité
de calcul. Les résultats partiels d'une annulation utilisateur ne sont pas sauvés.
Le calcul tourne dans un thread pour préserver la boucle HTTP ; il ne constitue
pas une infrastructure de jobs persistants.

Un sémaphore autorise un Optimizer à la fois **par processus**. Il correspond à
l'usage local mono-worker actuel ; il ne remplace pas une admission distribuée ni
une réservation globale des ressources face aux autres calculs Structura.

Limites fonctionnelles : pas de smile, calibration, funding, crédit émetteur,
frais, FX/quanto, stubs, optimisation des paniers, step-down, barrière continue,
produit en cours de vie, Greeks, VaR/ES, rendement espéré ou probabilités physiques.
L'interface permet l'export, sans création automatique de RFQ, Product ou Deal.
Une proposition client exige une validation de marché, de modèle et de convergence
au-delà de cette exploration.

### Défaut préexistant observé

`run_mc(..., antithetic=False, per_path_flows=True)` lève un `UnboundLocalError` :
`flows_anti` n'est initialisé que dans la branche antithétique, puis lu lors du
retour des flux. Ce défaut concerne cette combinaison d'options et **ne remet pas
en cause la méthode antithétique**. Le moteur partagé n'a pas été modifié dans ce
chantier ; l'Optimizer utilise le chemin antithétique testé.

## Validation exécutée

Le 05/10/2026, depuis la racine pour pytest :

- `pytest backend/tests/test_product_optimizer.py -q` : **36 réussis**, puis le
  test ajouté de transmission/sensibilité au dividende : **1 réussi**.
- `pytest backend/tests/test_simulation.py backend/tests/test_product_catalogue.py -q` :
  **66 réussis**. La suite backend complète n'a pas été lancée.
- Dans `frontend/`, `npm run build` : **231 tests réussis**, build Vite réussi.

Couverture : champs/modèles/familles non autorisés, bornes et pas, matrices,
ancrage et paiements, budget préalable, stubs, conversion coupon/période, IC dans
les contraintes, coupon cible, analytics absentes, classement/Pareto, échec isolé,
budget temps partiel, résolution réelle déterministe, worst-of, rappel avant/à
maturité, protection/perte terminale, impact du dividende, authentification,
référentiel, absence de partage de résultats, admission 429 et libération après
erreur. Frontend : grille décimale, exclusion des candidats rejetés, auth et flux
UTF-8 fragmenté/interrompu.

Recette navigateur sur instance isolée avec base SQLite temporaire et compte test :
navigation et carte Copilot inactive ; saisie catalogue/convention ; budget ;
calcul réel de trois maturités 36/48/60 mois ; trois admissibles, aucun échec ;
recommandation, comparaison de deux structures, graphique Pareto et réserves.
Avec vol 20 %, dividende 2 %, taux 3 %, protection 60 %, rappel 100 %, trimestriel,
1 000 paires, tolérance prix ±3 points : calcul en **14,562 s**, coupons résolus
12,21 %, 12,47 % et 13,17 %. Ce sont des mesures de recette sur hypothèses, pas des
cotations de marché. Modification de saisie : ancien résultat explicitement marqué.
La recette d'un plafond de perte nul vérifie le cas sans solution et les motifs.
Une plage inversée bloque le lancement ; une annulation affiche l'arrêt du flux.
Le Mode Démo masque le formulaire et restaure la saisie lorsqu'il est désactivé.
Aucune erreur JavaScript lors de la recette du calcul et de la comparaison.

Avertissements des outils : dépréciation préexistante TestClient/httpx et imports
dynamiques déjà importés statiquement dans le build. Ces avertissements n'ont pas
fait échouer les validations. La recette locale ne vaut pas homologation de
production ou audit exhaustif de tous les modules Structura.

## À prévoir ensuite

1. Validation finale sur tirages indépendants, convergence et traitement explicite
   de la sélection multiple ; exploiter les paires pour les analytics avec une
   variance adaptée.
2. Snapshots de marché qualifiés et provenance par champ ; funding, coûts et
   classification des actifs dans le référentiel.
3. Qualification Phoenix/mémoire et nouveaux adaptateurs de familles, puis modèles
   à smile avec matrice de capacités testée ; jamais de repli silencieux.
4. Conservation des runs avec propriétaire et empreinte de code, reprise et
   transfert contrôlé vers Pricer/RFQ ; admission distribuée si plusieurs workers.
5. Exploration des paniers et stratégies plus efficaces. Le Copilot pourra produire
   une requête normalisée ; il restera séparé du calcul et des contrôles métier.

## Tour des payoffs candidats à l'extension — 05/10/2026

Revue du catalogue source `frontend/src/data/productCatalogue.json`, de sa copie
serveur, du solveur, des analytics de l'Optimizer et des tests correspondants.
**19 fiches de catalogue, dont une seule activée dans l'Optimizer : Athena
européen.** Les déclinaisons mono-actif/worst-of ne sont pas comptées comme des
payoffs supplémentaires. Cette revue prépare les extensions ; elle n'en active
aucune. Les appréciations d'effort sont relatives, pas des estimations de délai.

### Premier lot proposé : cinq fiches avec l'Athena existant

| Fiche à ajouter | Intérêt de recherche | Paramètre à résoudre / axes à explorer | Qualification nécessaire |
|---|---|---|---|
| `phoenix` | Revenu conditionnel payé périodiquement | Coupon par période ; barrière coupon, protection, rappel, maturité, fréquence | Séparer paiement de coupon et rappel ; contrôler la relation entre barrières ; vérifier coupon et nominal lors d'un rappel simultané |
| `phoenix_memoire` | Arbitrage coupon / chance de rattrapage | Même recherche, mémoire définie contractuellement | Coupons manqués, rattrapage, remise à zéro et mémoire restant impayée à maturité ; `MEMO` est le dernier rang payé dans ce script |
| `autocall_barriere_degressive` | Faciliter le rappel au fil du temps | Coupon résolu ; seuil initial, décrément, plancher et première date de baisse | Générer la liste `PARAM()` par observation ; la valeur initiale de 100 % seule ne crée aucune dégressivité |
| `reverse_convertible` | Coupon certain dans le payoff et protection conditionnelle sans rappel | Coupon total résolu ; maturité et barrière européenne | Le catalogue verse un coupon unique à maturité : définir son annualisation, ne pas reprendre la conversion coupon trimestriel de l'Athena |

Le terme « certain » décrit ici la règle de payoff, hors défaut de l'émetteur.
Les quatre scripts existent déjà ; l'effort porte sur leur adaptation à
l'Optimizer, les contraintes, l'affichage et les tests économiques. Phoenix ne
nécessite pas de nouveau modèle de diffusion pour cette première extension GBM.

### Deuxième lot : participation et exposition directionnelle

| Fiche existante | Ce que l'Optimizer chercherait | Point de vigilance |
|---|---|---|
| `capital_garanti` | Participation maximale à prix cible, en explorant maturité et strike | Résoudre `PART`, pas un coupon ; protection nominale à échéance hors crédit ; aucune participation positive finançable n'est garantie pour toutes les hypothèses |
| `booster` | Participation maximale pour un cap fixé, ou meilleur cap à participation imposée | Baisse subie une pour une ; participation et cap sont deux dimensions distinctes, leur classement doit rester explicite |
| `autocall_gear_put` | Coupon contre strike de put et gearing | Le script verse `COUPON` une seule fois au rappel, sans `INDEX` : ce n'est pas le coupon cumulé Athena. La sévérité de perte doit accompagner sa probabilité |

Ces fiches disposent de formules terminales exploitables. Leur intérêt métier
demande cependant de nouveaux objectifs et unités d'affichage : comparer un coupon,
une participation et un gearing dans un score unique serait trompeur.

### Troisième lot : dépendance au chemin et fenêtres de constatation

| Fiche existante | Extension possible | Travail avant activation |
|---|---|---|
| `autocall_athena_ki_americaine` | Athena avec knock-in pendant la vie | Choix explicite du monitoring et validation de la barrière, y compris franchissement puis récupération |
| `brc_ki_americaine` | Reverse convertible à knock-in pendant la vie | Même validation ; après KI, la fiche rembourse `WOF`, même s'il dépasse 100 %. Décider explicitement si cette variante ou un remboursement plafonné est souhaité |
| `twin_win` | Cap / barrière contre participation à la performance absolue | Formule actuelle spécifique : après KI, remboursement `WOF`, sans formule générique de Twin Win présumée ; tester récupération et plafonds |
| `shark_note` | Participation / barrière KO / rebate | Dans le catalogue, le KO porte sur `BOF_MAX` et la participation sur `WOF`. Vérifier que cette combinaison est bien voulue pour un panier |
| `autocall_coupon_moyenne_periode` | Fréquence et fenêtres, avec coupon résolu | Le rappel aussi lit la moyenne ; la protection finale lit le cours brut. Conserver ces deux observables et dimensionner le budget de sous-dates |
| `call_panier_moyenne` | Strike, fenêtre initiale et finale, budget de prime | Fenêtres moyennées par actif, puis panier équipondéré ; origine du strike à adapter à l'Optimizer |
| `call_lookback` | Strike / fenêtre initiale / budget de prime | Strike de chaque actif fixé sur son minimum de fenêtre ; état initial et granularité à qualifier |

Le monitoring continu par pont brownien existe déjà dans `run_mc` et traverse le
solveur. Ce n'est donc pas une fonctionnalité absente du moteur. Néanmoins,
`_bridge_extrema` tire des uniformes indépendantes par actif : la validation
mono-actif ne certifie pas la loi jointe des extrema d'un panier corrélé.
Une extension continue worst-of nécessite cette analyse supplémentaire. Le défaut
de monitoring actuel du solveur est `weekly` ; un libellé « américaine » ne suffit
pas à sélectionner automatiquement le mode continu.

### Options terminales : quatre autres fiches

`call`, `put`, `call_spread` et `digitale` sont déjà au catalogue. Elles peuvent
servir à une recherche de strike, spread ou montant digital sous budget de prime.
Elles réclament un univers d'optimisation distinct de la note émise autour du pair :
le prix d'une option ne doit pas être forcé dans l'intervalle 80–120 % du nominal.
Les deux options à fenêtres du tableau précédent appartiennent également à cet
univers, soit **six fiches d'options au total**.

Un chemin sans aucun paiement est normal pour une option hors de la monnaie.
L'adaptateur Athena actuel le traite comme une anomalie et déduit la terminaison
du dernier flux non nul : il faut séparer **date de terminaison contractuelle** et
**date du dernier paiement** avant de réutiliser ces analytics. Cette distinction
est aussi nécessaire pour certains produits à capital entièrement perdu.

### Extensions à écrire, absentes du catalogue générique

Parmi les variantes à spécifier ensuite : Phoenix dégressif, autocall à coupons
inconditionnels, coupons progressifs, période initiale sans rappel, bonus/capped
bonus, airbag, range accrual et cliquet. Plusieurs briques de langage existent
(`PARAM()`, mémoire, `ACCRUE`, sous-calendriers), mais elles ne constituent pas une
fiche de produit validée. Pour chaque variante, définir le payoff exact, le
calendrier et les branches de remboursement avant d'estimer l'intégration.

### Socle commun à faire évoluer

1. Un adaptateur par famille : script, calendrier, paramètres admissibles,
   grandeur résolue et règles d'unités. Élargir explicitement les contrats Pydantic
   aujourd'hui limités à Athena, pas seulement la liste du menu.
2. Des métriques propres à la famille : coupon payé/manqué/rattrapé pour Phoenix,
   participation pour capital protégé, sévérité de perte pour gear put. Les
   statistiques de rappel doivent être non applicables sur un produit sans rappel.
3. Des filtres conditionnels : impossible d'exiger une barrière coupon sur Athena
   ou un minimum de rappel sur une reverse convertible sans autocall.
4. Des comparaisons cohérentes : même devise, hypothèses et conventions ; séparer
   coupon affiché, revenu effectivement versé et performance totale. La perte sur
   le nominal et la perte coupons inclus ne répondent pas à la même question.
5. Des scénarios déterministes aux barrières, coupons et mémoires, puis des tests
   de résolution et de convergence. Les tests catalogue existants compilent et
   pricent les fiches à 300 chemins sur leur ténor court ; cela ne qualifie pas
   toutes leurs branches économiques ni une recherche automatique sur leurs bornes.

**Ordre proposé : Phoenix → Phoenix mémoire → Athena dégressif → reverse
convertible européen → capital protégé → booster / gear put → produits à
monitoring continu et fenêtres.** Les options peuvent constituer un chantier
distinct orienté budget de couverture. Cette revue est une lecture de code et de
tests ; aucun nouveau test ni calcul de marché n'a été exécuté pour l'établir.
