# Product Optimizer V1

État au **05/10/2026** : implémenté localement, tests ciblés et recette navigateur
effectués. Aucun commit ni déploiement. Cette note est placée à ce chemin à la
demande explicite de Philippe.

**Suite du 08/10/2026 : calcul direct et parallélisation.** Le sujet
[smile actions est URGENT mais différé](projects/pricing/SMILE_ACTIONS_URGENT_2026-10-08.md).
Le lot conserve Athena européen sous GBM et la dichotomie existante,
sans conversion de prix entre modèles. Les candidats peuvent être valorisés
dans des processus séparés ; modalités et validation ci-dessous.

**Validation quantitative du 08/10 :** [lot indépendant, estimateurs, recette et limites](projects/pricing/PRODUCT_OPTIMIZER_QUANT_VALIDATION_2026-10-08.md). Les recommandations passent désormais une validation à coupon conservé sur deux nouveaux échantillons ; la sélection multiple et l’incertitude du classement sont explicites.

**Marché et économie d’émission du 08/10 :** [copie explicite du Pricer, courbes, funding et coûts](projects/pricing/PRODUCT_OPTIMIZER_MARKET_ECONOMICS_2026-10-08.md). Les hypothèses sont figées et tracées par champ ; le coupon finance le prix d’émission diminué des frais initiaux et de la marge. Ces capacités sont disponibles localement ; les recettes du 05/10 ci-dessous restent historiques.

**Payoffs et champs dynamiques du 08/10 :** [qualification et vérifications](projects/pricing/PRODUCT_OPTIMIZER_PAYOFFS_2026-10-08.md). Phoenix, Phoenix mémoire, Athena dégressif et reverse convertible européenne sont désormais disponibles. Les champs suivent les paramètres du script catalogue sélectionné ; 142 tests backend ciblés et 305 tests frontend réussis.

**Participation, cap et gear put du 08/10 :** [conventions, champs, risque et vérifications](projects/pricing/PRODUCT_OPTIMIZER_PARTICIPATION_GEAR_2026-10-08.md). Capital protégé, booster et gear put complètent les huit familles. La quantité résolue et les axes deviennent propres à l’objectif ; le gear put conserve un coupon unique au rappel.

**Dossiers et page de résultats du 08/10 :** [parcours, sauvegarde et recette](projects/pricing/PRODUCT_OPTIMIZER_RESEARCH_WORKSPACE_2026-10-08.md). Philippe a désormais demandé cette conservation : intention/résumé, hypothèses et résultats sont sauvegardés dans une bibliothèque propriétaire ; les reprises créent de nouveaux calculs liés. Résultats séparés du formulaire, radar, panneaux repliables avec défilement interne et aides `?`. Calcul côté serveur indépendant de la page ; les décisions de report ci-dessous restent historiques.

## Évaluation de l'existant et choix de périmètre

**Marché automatique et recherche complète du 08/10 :** [conventions et vérifications](projects/pricing/PRODUCT_OPTIMIZER_AUTOMATIC_MARKET_SEARCH_2026-10-08.md). Le panier de l’Optimizer charge ses références datées indépendamment du Pricer. Classification du référentiel, surcharges tracées, champs fixes / explorés, plafond 256, budget temps configurable et résultat partiel après arrêt sont désormais disponibles.

Le frontend utilise Vue 3, Vue Router, Tailwind et Chart.js. Le backend expose des
routeurs FastAPI authentifiés avec `get_current_user`, des contrats Pydantic et un
référentiel SQLModel de sous-jacents. Le moteur PayScript possède déjà un catalogue,
un compilateur de calendriers, le Monte-Carlo et un solveur de paramètres.

La présence de GBM, Heston, SABR, Local Vol et LSV dans le moteur ne constitue pas
une qualification de toutes leurs combinaisons pour l'optimisation. La V1 retient
**huit familles sous GBM, avec protection nominale ou perte européenne selon le script**, mono-actif ou worst-of, sur hypothèses
explicites. Elle réutilise leurs scripts catalogue dans `PRODUCTS`,
`resolve_constats`, `solve_for_param` et `run_mc`. Aucun second moteur de pricing
n'est créé.

Phoenix et mémoire sont qualifiés localement pour l’Optimizer depuis le lot
payoffs du 08/10. Les autres familles du catalogue général restent hors périmètre
tant que leur adaptateur, leurs objectifs et leurs métriques ne sont pas qualifiés.

## Disponible maintenant

| Élément | Périmètre |
|---|---|
| Navigation | Structuring Intelligence → Product Optimizer ; Copilot « À venir », sans lien |
| Produit | Athena, Phoenix, Phoenix mémoire, Athena dégressif, reverse convertible européenne, capital protégé, booster, gear put |
| Sous-jacents | 1 à 3 actions/indices du référentiel, qualification manuelle seulement si inconnue |
| Panier | Mono-actif ou worst-of ; panier fixé par l'utilisateur pour toute la recherche |
| Modèle | `constant` = GBM ; `auto` choisit explicitement ce seul modèle autorisé |
| Devises | EUR, USD, GBP, CHF, JPY, SGD ; tous les actifs dans la devise de règlement |
| Objectifs | Selon le script : coupon maximal/cible, protection, participation maximale, cap maximal à participation imposée |
| Recherche | Grille déterministe et dichotomie du paramètre applicable pour chaque structure |
| Champs | Métadonnées des PARAM du script qualifié ; barrière coupon Phoenix, réglages de série dégressive, absence de rappel sur RC |
| Marché | Références historiques automatiques par panier et date ; vol réalisée, dividendes et corrélations modifiables ; taux et funding manuels |
| Économie | Funding plat ou courbe dans l’actualisation ; frais initiaux et marge déduits du budget du payoff |
| Traçabilité | Snapshot figé, empreinte, date et origine par champ, référence importée et modifications visibles |
| Décision | Recommandation explicable, alternatives triables, comparaison de 2 à 5 candidats |
| Graphique | Axes propres au payoff et à son objectif, candidats confirmés, Pareto et sélection |
| Conservation | Résultat temporaire dans la page, export JSON complet |

Le type connu action/indice vient du référentiel et est contrôlé côté API.
Une identité non qualifiée demande une saisie explicite. La V1 ne génère pas de
combinaisons de paniers à partir d’une liste de tickers autorisés.

### Paramètres explorés et paramètre résolu

Les champs sont propres à la famille : barrière coupon pour Phoenix ; seuils de
rappel et fréquences pour les autocalls ; maturité et protection seules pour RC.
La [note payoffs](projects/pricing/PRODUCT_OPTIMIZER_PAYOFFS_2026-10-08.md) détaille
les règles de série dégressive et les unités. Les bornes communes suivantes
s’appliquent lorsque le paramètre appartient au script sélectionné.

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

Pour Athena, au rang `k`, le script catalogue paie le nominal et `k × COUPON` si le worst-of
atteint le seuil de rappel, puis s'arrête. Sans rappel, aucun coupon n'est payé ; à
maturité, le nominal est restitué si la protection européenne tient, sinon le
worst-of est remboursé. Le rappel à maturité existe contractuellement mais ne
compte pas comme rappel **anticipé**.

Le coupon annuel affiché est nominal :
`COUPON PayScript = coupon_annuel × fréquence_en_mois / 12`.
Il ne constitue ni un TRI ni une promesse de rendement annuel réalisé.

Phoenix paie un coupon conditionnel par période ; mémoire rattrape les coupons
manqués et ne paie pas la mémoire restante si la barrière coupon ne tient plus.
La RC paie un coupon unique à maturité : `COUPON = coupon_annuel × maturité_en_mois / 12`.
Les branches, égalités et paramètres de chaque script sont qualifiés dans la note payoffs.

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
| `backend/app/core/product_optimizer/families.py` | Adaptateurs qualifiés, métadonnées des paramètres des scripts et série de rappel |
| `backend/app/core/product_optimizer/capabilities.py` | Liste explicite des capacités, exclusions et plafonds |
| `backend/app/core/product_optimizer/service.py` | Budget, génération, adaptation PayScript, analytics, filtre, classement, événements |
| `backend/app/core/product_optimizer/market.py` | Snapshot d’hypothèses, références par champ et entrées de courbes du moteur |
| `backend/app/core/product_optimizer/validation.py` | Holdouts indépendants et diagnostic du coupon à conventions financières identiques |
| `backend/app/core/product_optimizer/__init__.py` | Paquet métier |
| `backend/app/core/product_optimizer/parallel.py` | Pont de streaming vers l'exécuteur parallèle commun et nettoyage à la fermeture |
| `backend/app/core/compute/pricers/product_optimizer.py` | Adaptateur candidat en données JSON, compilé et pricé dans le processus de calcul |
| `backend/app/api/product_optimizer.py` | Authentification, référentiel, admission et streaming |
| `frontend/src/views/StructuringView.vue` | Entrée du module et Copilot indisponible |
| `frontend/src/views/ProductOptimizerView.vue` | Contraintes, progression, résultats, comparaison et Chart.js |
| `frontend/src/utils/productOptimizer.js` | Appels authentifiés, lecture NDJSON, taille de grille |
| `frontend/src/utils/optimizerMarket.js` | Copie du Pricer, références, unités des courbes et corrélations par paire de tickers |
| `frontend/src/components/OptimizerCurveInput.vue` | Saisie des nœuds de courbe en années et pourcentages |
| `frontend/src/components/OptimizerPayoffFields.vue`, `frontend/src/utils/optimizerPayoff.js` | Champs dynamiques et requête limitée aux paramètres de la famille |
| `backend/tests/test_product_optimizer_market.py` | Courbes, funding, coûts, snapshots et équivalence des processus |
| `backend/tests/test_product_optimizer.py` | Contrats, cas économiques, orchestration et API |
| `backend/tests/test_product_optimizer_parallel.py` | Équivalence réelle séquentiel/processus, ressources, arrêt et streaming |
| `frontend/src/utils/productOptimizer.test.js` | Grilles, candidats admissibles et streaming |

Fichiers existants modifiés pour l'intégration : `backend/app/main.py`,
`frontend/src/router/index.js`, `frontend/src/components/AppHeader.vue` et
`docs/README.md`, ainsi que les bundles versionnés de `frontend/dist/` régénérés
par le build. Le moteur PayScript et le solveur existants sont réutilisés ; le
solveur accepte désormais les paramètres de funding optionnels. La session Pricer
expose une copie de ses entrées de marché. Aucune table de données ni transition
de booking n’est ajoutée par le lot marché.

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

Depuis le lot marché du 08/10, `market` accepte `yield_curve`, `funding_curve`,
`funding_spread` et `underlyings[].dividend_curve`. Les courbes sont des couples
`[années, taux en fraction]`, avec au plus 30 nœuds. Les dividendes sont des buckets
annuels consécutifs dégressifs, dont le premier rendement égale `q` ; le dernier
bucket est prolongé. Un funding plat non nul et une courbe de funding sont exclusifs.
Les taux plats servent de repli en l’absence de courbe.

`economics` contient `upfront_fees` et `structuring_margin`, chacun nul par défaut
et borné à 10 % du nominal. Ce sont des fractions du nominal, pas du prix : à
100 % d’émission, 0,5 point de frais et 0,5 point de marge donnent un budget payoff
de 99 %. `constraints.target_price` demeure le prix d’émission brut ; le solveur,
les filtres de prix et le classement utilisent le budget net. Les coûts ne sont
pas soustraits des paiements investisseurs.

L’origine `PRICER_SESSION` exige une référence par champ, la devise, les tickers
du panier initial et un timestamp avec fuseau. Les modifications conservent ces
références ; un changement de devise exige une nouvelle copie. Cette origine
désigne des hypothèses de session, sans certifier un fournisseur ou une cotation.

Depuis le 08/10, `search.parallel_workers` accepte 1 à 4 (défaut 2). L'estimation
retourne `execution.mode`, `requested_workers`, `workers`, `cpu_limit` et
`memory_limit`. Le nombre retenu tient compte du nombre de candidats, laisse un
CPU logique disponible lorsque possible et réduit la concurrence pour rester
dans le plafond de mémoire de travail estimée de 256 Mio. Ce budget couvre les
tableaux du moteur ; il ne mesure pas la mémoire totale des interpréteurs ni les
autres applications. La charge totale est désormais un avertissement ; le délai
maximal configurable et la taille de grille restent contraignants.

| Route | Comportement |
|---|---|
| `GET /api/product-optimizer/capabilities` | Capacités et limites, authentifié |
| `POST /api/product-optimizer/market-reference` | Références historiques du panier à la date de pricing, classification du catalogue |
| `POST /api/product-optimizer/cancel/{run_id}` | Signal d’arrêt du propriétaire ; connexion maintenue pour le résultat partiel |
| `POST /api/product-optimizer/estimate-search` | Validation du référentiel, nombre de candidats, mémoire/travail estimés, motifs de refus |
| `POST /api/product-optimizer/run` | Même validation puis flux NDJSON : `run_registered`, `started`, `progress`, `validation_started`, `validation_progress`, `heartbeat`, `result` ou `error` |

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
modèle, les paramètres structurels, le coupon annualisé, le prix d'émission brut,
le budget net `pricing_target`, la
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
évalués. Le lot marché ajoute `market_snapshot` et la décomposition `economics`.
Le lot payoffs ajoute `payoff` (script, paramètres et empreinte de source).
La version courante `optimizer-v1-payoffs` est une version de méthode, pas une empreinte
complète du code de pricing installé.

## Analytics, incertitude et classement

Les probabilités sont sous **mesure risque-neutre Q**, avec taux et dividendes plats
ou leurs courbes explicites, volatilités constantes et corrélations saisies ou
copiées du Pricer. Aucun téléchargement ou fallback
de marché n'est caché derrière ces hypothèses.

| Métrique | Définition et filtre |
|---|---|
| Juste valeur / intervalle | Prix direct à coupon conservé sur le second holdout ; intervalle simultané entier dans budget net du payoff ± tolérance |
| Perte Q | Somme des flux non actualisés inférieure au prix d'émission ; plafond appliqué à la borne haute de Bernstein corrigée pour la sélection |
| Rappel anticipé Q | Dernier flux avant la maturité ; minimum appliqué à la borne basse de Bernstein corrigée pour la sélection |
| Durée moyenne | Moyenne des temps de dernier flux sur la grille d'observation ; plafond appliqué à la borne haute de Bernstein corrigée pour la sélection |
| Coupons payés / non payés Q — Phoenix | Montants cumulés non actualisés jusqu’à terminaison, en fractions de nominal ; bornes de Bernstein sur les holdouts |

Depuis le lot payoffs, la durée et le rappel utilisent les dates de terminaison
contractuelle exposées par le moteur. La RC ne possède pas de métrique de rappel.

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

Depuis le lot quantitatif du 08/10, les métriques utilisent les deux jambes,
moyennées par paire. L'exploration garde des intervalles normaux ponctuels ;
la sélection figée des cinq meilleurs candidats au maximum passe ensuite deux
pricings directs indépendants à N et 2N paires, sans modifier les coupons.
Les contraintes finales utilisent le second échantillon et une correction de
Bonferroni : approximation normale pour le prix, bornes de Bernstein pour les
probabilités et la durée. Les diagnostics N/2N et de coupon sont approximatifs.
Les intervalles ne couvrent pas l'erreur de modèle, de marché ou de grille.
La [note quantitative](projects/pricing/PRODUCT_OPTIMIZER_QUANT_VALIDATION_2026-10-08.md)
précise l'allocation de confiance, le diagnostic du classement et la recette
indépendante. Aucun test de convergence global n'est revendiqué.

### Classement transparent

Classement exploratoire avant sélection, puis classement final parmi les seuls candidats confirmés :

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

Plafonds : 256 candidats, 20 000 paires pour l’exploration et jusqu’à 40 000 pour le second holdout, 1 000 valeurs par axe,
256 Mio de mémoire de travail estimée. Le travail total est indicatif. Le budget
réutilise `estimate_mc_batch` et provisionne 18 itérations de solveur, les deux
bornes et une revalorisation par candidat, plus N et 2N paires pour les cinq candidats sélectionnés au maximum. La mémoire est réservée sur le plus grand calcul à 2N. L'interface démarre avec 4 000 paires,
un plafond utilisateur de 256 candidats, 1 800 secondes et une grille de trois maturités.

En séquentiel, le délai configurable (30–3 600 secondes, défaut API 120) est vérifié **entre candidats** et
l'annulation attend la fin du candidat courant. Depuis le 08/10, le mode
parallèle vérifie le délai pendant le calcul et arrête les processus du pool
lorsqu'il est atteint ou lorsque le flux est fermé. Il s'appuie sur
`core.compute.executor.run_batch`, avec au plus un job soumis par processus
disponible. Un événement `heartbeat` maintient le flux réactif pendant l'attente.
L'admission n'est libérée qu'après le nettoyage du pool. Au délai, seuls les
candidats effectivement reçus sont classés, avec `complete=false` ; les travaux
interrompus sont non évalués, pas des échecs de pricing. Les résultats partiels
d’un arrêt demandé par son propriétaire sont renvoyés dans la page et exportables,
avec seulement les confirmations terminées recommandables. Aucun job persistant n’est créé.

Chaque candidat reste un calcul direct avec sa résolution et son repricing.
Seules la planification et l'exécution changent ; aucun ratio entre modèles,
surrogate ni nouvelle règle de coupon n'est utilisé. Les scripts sont compilés
dans les workers à partir des données JSON, sans session SQLite transférée.
La graine reste 42 ; la progression suit l'arrivée des résultats, puis les
candidats sont remis dans l'ordre de leurs identifiants avant classement.
Les adaptateurs injectés pour les tests restent exécutés séquentiellement.

Un sémaphore autorise un Optimizer à la fois **par processus**. Il correspond à
l'usage local mono-worker actuel ; il ne remplace pas une admission distribuée ni
une réservation globale des ressources face aux autres calculs Structura.

Limites fonctionnelles : pas de smile, calibration, modèle de défaut émetteur,
FX/quanto, stubs, optimisation des paniers, step-down, barrière continue,
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

## Priorités confirmées avec Philippe — 08/10/2026

**Construire d'abord l'Optimizer, puis le Copilot.** Le chantier actuel se
concentre sur trois axes : validation quantitative, enrichissement du marché et
extension des payoffs. La conservation et l'exploitation des recherches sont
reportées à un second temps ; elles ne sont pas urgentes. Ce cadrage ne constitue
pas une nouvelle livraison ni une nouvelle validation quantitative.

**Arbitrage de calcul du même jour :** continuer en pricing direct classique et
paralléliser les candidats. La note [URGENT smile actions](projects/pricing/SMILE_ACTIONS_URGENT_2026-10-08.md)
conserve la matrice cible à définir, les limites des ailes actuelles et le plan
de contrôle du put/digital/rappel. Ce sujet est différé ; aucun nouveau modèle
à smile n'est activé implicitement dans l'Optimizer.

### 1. Renforcer la validation quantitative

Validation finale sur tirages indépendants, convergence et traitement explicite
de la sélection multiple ; exploiter les paires pour les analytics avec une
variance adaptée. L'objectif est de vérifier la stabilité des prix, des métriques
et de la sélection des candidats avant d'élargir les capacités de recherche.

### 2. Enrichir le marché

**Premier lot livré le 08/10 :** copie de session Pricer, références par champ,
courbes, funding et frais/marge ; [rapport de validation](projects/pricing/PRODUCT_OPTIMIZER_MARKET_ECONOMICS_2026-10-08.md).
La qualification externe des données et la classification des actifs restent ouvertes.

Snapshots de marché qualifiés et provenance par champ ; funding, coûts et
classification des actifs dans le référentiel. Conserver la distinction entre
données observées, estimations ou calibrations, hypothèses de structuration et
valeurs effectivement utilisées. Aucun nouveau fournisseur ni téléchargement
automatique n'est décidé par ce cadrage.

### 3. Étendre les payoffs

**Premier lot livré le 08/10 :** Phoenix, Phoenix mémoire, Athena dégressif et
reverse convertible européenne, avec champs dynamiques et métriques propres.
La [note payoffs](projects/pricing/PRODUCT_OPTIMIZER_PAYOFFS_2026-10-08.md) précise
la qualification effective et les extensions restantes.

Qualification Phoenix/mémoire et nouveaux adaptateurs de familles, puis modèles
à smile avec matrice de capacités testée ; jamais de repli silencieux. La revue
ci-dessous fournit l'ordre proposé des familles et leurs points de qualification.
L'extension des payoffs est retenue ; son ordre détaillé reste une proposition
technique à affiner au démarrage de chaque lot.

### Second temps : conserver et exploiter les recherches

Conservation des runs avec propriétaire et empreinte de code, reprise et
transfert contrôlé vers Pricer/RFQ ; admission distribuée si plusieurs workers.
L'export JSON actuel reste disponible pendant les premiers lots.

### Extensions ultérieures

L'exploration des paniers et les stratégies de recherche plus efficaces restent
des pistes dont la priorité n'a pas été arbitrée le 08/10. Le Copilot viendra
après l'Optimizer : il pourra produire une requête normalisée et restera séparé
du calcul et des contrôles métier.

## Livraison du calcul parallèle — 08/10/2026

Implémenté localement, sans commit ni push. Réglage « Calculs simultanés » de
1 à 4, défaut 2 ; nombre retenu affiché dans le budget. Le backend réutilise
l'exécuteur de processus commun et un adaptateur de candidat. La résolution
du coupon reste la dichotomie et le repricing directs existants sous GBM.
Ce lot n'active pas Phoenix, Heston, Local Vol ou LSV dans l'Optimizer et ne
constitue pas une nouvelle qualification de convergence ou de marché.

### Validation ciblée

- Depuis la racine : `pytest backend/tests/test_product_optimizer.py
  backend/tests/test_product_optimizer_parallel.py -q` : **48 réussis**.
- Exécuteur partagé : `pytest backend/tests/test_compute.py -q -k run_batch` :
  **5 réussis**, 17 non sélectionnés. Aucune suite backend complète.
- `npm run build` depuis `frontend/` : **287 tests frontend réussis**, build réussi.

Les processus Windows réels reproduisent exactement les candidats et le
classement séquentiels en mono et worst-of à deux actifs. Le streaming API
parallèle, l'admission, la mémoire concurrente, le plafond CPU, les erreurs
privées, la remise en ordre des résultats et l'arrêt sont couverts. À la
fermeture d'un vrai pool, aucun processus enfant créé par le test ne reste actif.
Le test de délai vérifie que les candidats interrompus restent non évalués,
sans gonfler le nombre d'échecs.

### Mesure de performance

Benchmark hors serveur, sans accès à la base réelle ni au réseau : quatre
Athena trois ans mono-actif, constatations trimestrielles, protection
55/60/65/70 %, rappel 100 %, taux 3 %, dividende 2 %, vol constante 20 %,
2 000 paires par pricing, graine 42, tolérance prix ±3 points. Hypothèses
synthétiques destinées à mesurer l'exécution, pas à produire une cotation.

| Exécution | Temps total, démarrage inclus |
|---|---:|
| Séquentiel | 26,347 s |
| Deux processus | 15,445 s |

Gain mesuré : **1,706 fois**, soit environ **41 % de temps en moins** sur cette
unique passe, avec prix, coupons, métriques et recommandation strictement
identiques. Machine : huit CPU logiques, Python 3.11.9. Aucun processus enfant
du benchmark encore actif. Le gain varie selon la grille et la charge machine ;
les petits calculs peuvent être pénalisés par le démarrage des processus.

Reproduction depuis la racine :

```powershell
.venv/Scripts/python.exe -X utf8 backend/scripts/benchmark_product_optimizer.py --output output/optimizer-parallel-20261008/benchmark.json
```

[Résultats complets de la mesure](../output/optimizer-parallel-20261008/benchmark.json).
Les mises à jour de source sont compilées dans de nouveaux workers ; le backend
préexistant n'a pas été arrêté ni redémarré. Son redémarrage manuel est nécessaire
pour charger ce nouveau contrat API. La recette visuelle n'a pas pu être
effectuée : le navigateur disponible bloque l'accès à `127.0.0.1:8000`.

La [note URGENT smile actions](projects/pricing/SMILE_ACTIONS_URGENT_2026-10-08.md)
conserve le diagnostic, les exemples d'ailes demandés et la méthode de reprise.

## Tour des payoffs candidats à l'extension — 05/10/2026

Cette revue est historique. Le premier lot décrit ci-dessous est maintenant
livré selon la note payoffs du 08/10 ; les lots suivants restent des propositions.

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
