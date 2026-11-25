# API de recherche · indices Athena SX5E

Structura calcule le prix d'émission, le coupon, les constats contractuels, le MTM résiduel et les créances. QISTRA fournit les instantanés de marché et les fixings datés, tient les poches et le cash et chaîne le niveau dans l'ordre des séances. L'API traite des millésimes de recherche avec des hypothèses figées.

## Réinstaller le service Athena sur un poste QISTRA

Le backend de calcul et le worker sont livrés ensemble sur la branche `codex/structured-product-index-pricing` de Structura. Depuis le dossier qui héberge les dépôts, créer un checkout dédié au service.

```powershell
git clone --branch codex/structured-product-index-pricing https://github.com/MattIndiJones/structura.git structura-athena-indices
```

Si ce checkout existe déjà, utiliser `git pull --ff-only` depuis sa branche Athena. Préparer un environnement Python avec le `requirements.txt` de Structura ou réutiliser un environnement Structura compatible.

Depuis la racine de QISTRA, démarrer le service avec le compte Windows qui utilise le lanceur QISTRA. Adapter les deux chemins au poste.

```powershell
& .\.venv\Scripts\python.exe -B scripts/manage_athena_structura.py start `
  --checkout 'C:\chemin\structura-athena-indices' `
  --python 'C:\chemin\structura\.venv\Scripts\python.exe'
& .\.venv\Scripts\python.exe -B scripts/manage_athena_structura.py status
```

Le gestionnaire crée le profil de connexion Windows et démarre l’API et le worker sur la même base isolée. Quand `status` indique `running`, ouvrir le lanceur QISTRA habituel, puis **Structured Product Indices → Athena → Calculer avec Structura**. Charger **Exemple synthétique**, choisir le coupon déterminé au prix cible et lancer le backtest. Le statut **Terminé**, les coupons résolus, les constats et les MTM vérifient le parcours jusqu’au worker.

## Parcours d'un backtest

| Appel | Entrée et sortie |
|---|---|
| `GET /api/v1/structured-indices/athena/pricing-models` | Catalogue versionné des modèles disponibles à l’émission et en cours de vie. Fournit le modèle par défaut, les réglages numériques et les hypothèses de marché du Pricer avec bornes, unités et valeurs initiales. |
| `POST /api/v1/structured-indices/athena/issue-batches` | Un job par émission au roll. Retourne un ticket `202`. Chaque résultat donne un reçu, un prix par 100 et le millésime à conserver avec son coupon annuel et sa référence de termes. |
| `POST /api/v1/structured-indices/athena/lifecycle` | Reçoit le millésime, `as_of` et les fixings contractuels échus. Retourne l'état `active`, `called` ou `matured`, les contrôles de barrières et l'éventuel remboursement déterminé. Un fixing requis et absent produit `422`. |
| `POST /api/v1/structured-indices/athena/mtm-batches` | Un job par couple `(millésime, séance)` avec le marché de cette séance et les fixings acquis. Retourne un ticket `202`. Chaque résultat donne `residual_pv` hors créances, `claims`, les `barriers` de la séance et un reçu. |
| `GET /api/compute/batches/{id}` | Polling du `results_path` communiqué dans le ticket. Les jobs conservent l'ordre de soumission, avec leur statut, `result`, `error` et numéro de tentative. Lire les résultats seulement pour les jobs `done`. |

L'identité Structura portant le droit `business.price` soumet les calculs et lit ses lots avec son jeton de session. Chaque soumission contient `request_key`, `jobs`, et éventuellement `label` et `max_workers`. Réutiliser la même clé et le même corps après une perte de réponse retrouve le même lot. Un changement sous la même clé reçoit `409`. Une relance métier ou un nouveau calcul utilise une clé distincte. Un lot contient de 1 à 128 jobs et demande jusqu'à quatre processus. Le worker applique aussi son propre plafond serveur. La file enregistre les résultats au fil de l'eau et le worker garde un pool par lot Athena. Après interruption du worker, le bail permet de reprendre les jobs restants.

Pour un backtest, résoudre le coupon à chaque nouveau roll, puis soumettre en parallèle les MTM des millésimes connus sur une fenêtre de séances. Un rappel transforme l'optionalité en créance. QISTRA peut écarter les valorisations futures d'une note après son règlement. Un job en échec bloque l'utilisation de sa séance jusqu'à résolution. Les dates de roll et les mouvements du portefeuille restent séquentiels.

## Termes, marché et conventions

- Le catalogue `athena-pricing-v1` expose le GBM à volatilité constante, identifiant `constant`. Les nouvelles demandes peuvent fournir `model`, `n_paths`, `seed`, `steps_per_year` et `antithetic`. Les valeurs initiales de la simulation viennent du Pricer, soit 20 000 tirages, la graine 42, 52 pas/an et les variantes antithétiques actives. `n_paths` compte les tirages indépendants, soit le nombre de paires avec les antithétiques activées. Le budget Athena limite le produit du nombre de tirages et du nombre estimé de pas à huit millions par valorisation.
- Produit pilote en EUR sur SX5E Price, nominal normalisé à 100. Les observations et règlements sont datés dans les termes, avec la référence du calendrier source. Structura contrôle le règlement TARGET à J+`settlement_lag`. Au rappel, le coupon annualisé est multiplié par `observation_months / 12` et par le rang du constat. Les seuils `call_barrier` et `protection_barrier` sont en ratios du fixing initial et déclenchent au seuil inclus. Au dernier constat, le test de rappel précède celui de protection.
- Chaque job de calcul reçoit la date et la référence de son instantané, le spot, le taux, le dividende, la volatilité et le spread de funding. Les taux, volatilités et coupons sont décimaux. Le modèle pilote est le GBM à paramètres plats. Le funding affecte l'actualisation et les dividendes entrent dans le drift. Les réglages Monte Carlo et la graine figurent dans le reçu. Les fixings historiques ont chacun leur référence, indépendamment du spot de simulation. Aucun chargement de marché ni remplacement automatique de fixing n'intervient dans ce parcours.
- Le mode `fixed` demande `fixed_coupon`. Le mode `solve_to_target` demande `target_price`, `min_coupon`, `max_coupon` et accepte une tolérance jusqu'à 0,01 EUR par 100. Le moteur exploite la dépendance affine du prix au coupon sur les mêmes trajectoires et vérifie le coupon publié au repricing. Une cible hors bornes retourne `no_coupon_in_bounds` et son reçu. Un résultat qui échoue au contrôle de tolérance produit un job en échec.
- Le prix, les montants et les valeurs actuelles sont exprimés en EUR par 100 de nominal. Une créance porte un identifiant stable, le constat, le règlement, le montant et sa valeur actuelle. Elle est actualisée sur le temps restant jusqu'au paiement et apparaît lors du constat, y compris pour un règlement le jour même. Le MTM d'une note terminée vaut zéro hors créances et ne déclenche plus de Monte Carlo.
- Conserver la demande, le reçu et les références de termes et de marché dans le run QISTRA. Les reçus sont des empreintes du calcul de recherche et de ses entrées. Le connecteur QISTRA devra projeter les champs économiques du résultat Structura dans le contrat de lot QISTRA et reprendre les champs supplémentaires dans les éléments d'audit.

## Reverse Convertible à barrière européenne

Le catalogue publie le payoff `reverse-convertible-sx5e` en version `reverse-convertible-sx5e-v1` avec le modèle `constant` à l’émission et au MTM. Les mêmes routes traitent l’émission, les constats et la valorisation de ce millésime.

- Envoyer `reverse_convertible: true`, `maturity_years` entier de 1 à 10 et une seule observation datée à maturité. Cette observation contient le fixing effectif et son jour de paiement TARGET. Les champs communs `observation_months: 12` et `call_barrier: 1` ont une valeur conventionnelle. La `protection_barrier` est un ratio du fixing initial, au plus égal à 1.
- À maturité, le coupon par 100 est égal à `100 × annual_coupon × maturity_years` quel que soit le fixing. Au seuil de protection inclus, le remboursement est de 100. En dessous du seuil, il vaut `100 × fixing_final / fixing_initial`. Il n’y a aucun constat intermédiaire.
- Sur le constat, le statut passe à `matured` et le contrôle de barrière a pour type `capital`. Le cycle de vie expose le remboursement via `redemption` et le coupon positif via `coupon_claims`. Le MTM expose les créances de type `coupon` et `redemption` séparément, y compris un remboursement à zéro. Le diagnostic `next_call` est absent.

## Capital garanti, Booster et Autocall Gear Put

Le catalogue expose `capital-guaranteed-sx5e-v1`, `booster-sx5e-v1` et `autocall-gear-put-sx5e-v1` avec le GBM (`constant`) à l’émission et au MTM. Les termes incluent un objet `payoff` identifié par le code du catalogue, sans le suffixe de version.

| `payoff.id` | Termes | Quantité à résoudre |
|---|---|---|
| `capital-guaranteed-sx5e` | `participation_strike` de 0,50 à 1,50 et `participation` de 0 à 5. | `participation` à strike fixé. |
| `booster-sx5e` | `participation` de 0 à 5 et `redemption_cap` de 1 à 3. Un cap de 1,30 représente un remboursement total maximal de 130 par 100. | `participation` à cap fixé ou `redemption_cap` à participation fixée d’au moins 0,005. |
| `autocall-gear-put-sx5e` | `put_strike` de 0,30 à 1,20 et au plus égal au seuil de rappel, `gearing` de 1 à 5 en multiple, `single_coupon` de 0 à 0,50. Seuil de rappel constant de 0,80 à 1,20. Constats trimestriels, semestriels ou annuels. | `single_coupon` en fraction du nominal, payé en une fois au rappel. |

Fournir `quote: {mode: "fixed"}` avec les termes complets pour un prix ferme. Pour résoudre une quantité, fournir `quote` avec `mode: "solve_to_target"`, `quantity`, `target_price`, `minimum`, `maximum` et éventuellement `price_tolerance` (0,01 EUR par 100 par défaut). Omettre la seule quantité à résoudre dans `terms.payoff`. Le solveur utilise la même graine, la même grille et le même marché pour toutes les valorisations. La participation du Capital garanti et le coupon du Gear Put ont un prix affine. Le Booster utilise une dichotomie et retient la borne haute si son prix est déjà dans la tolérance. Une cible inaccessible renvoie `no_parameter_in_bounds` avec les prix aux bornes. Une résolution réussie fige la valeur dans `vintage.terms.payoff` et la renvoie dans `quote_result` avec sa quantité économique et son unité.

Le Capital garanti et le Booster ont un seul constat à maturité. Utiliser les valeurs communes `observation_months: 12`, `call_barrier: 1` et `protection_barrier: .60` pour ces deux payoffs. Le Gear Put utilise sa propre grille de rappel, et `protection_barrier: .60` reste conventionnel. Toutes les dates effectives de paiement sont contrôlées selon TARGET, avec `settlement_lag` ouvrés.

Les flux suivants sont exprimés par 100 de nominal, avec `x = fixing_final / fixing_initial` pour les produits restés en vie jusqu’à maturité.

- Capital garanti. Remboursement de 100 et participation de `100 × max(x − participation_strike, 0) × participation`.
- Booster. Remboursement de `100 × min(x, 1)` et participation de `100 × min(redemption_cap − 1, participation × max(x − 1, 0))`.
- Gear Put. Au rappel, remboursement de 100 et coupon de `100 × single_coupon` quel que soit le rang du constat. Sans rappel, remboursement de `100 × [1 − min(1, gearing × max(1 − x / put_strike, 0))]` à maturité. Le diagnostic `next_call` porte sur le prochain constat et son montant brut inclut le coupon unique.

Le cycle de vie fournit le principal dans `redemption` et les gains positifs via `participation_claims` pour le Capital garanti et le Booster, ou `coupon_claims` pour le Gear Put. Le MTM expose les mêmes identifiants de flux et valeurs actuelles jusqu’au règlement. Le remboursement existe même à zéro. Les deux payoffs à échéance ont une liste de barrières vide et conservent la référence du fixing de maturité. Le Gear Put produit un contrôle de rappel à chaque constat échu jusqu’à sortie et un contrôle du strike du put à maturité en l’absence de rappel.

## Options européennes SX5E

Le catalogue expose `european-put-sx5e-v1` et `european-call-sx5e-v1` avec le GBM (`constant`). Fournir `payoff: {id, strike_ratio: K / S0}` avec l’identifiant du produit souhaité sans suffixe de version, `quote: {mode: "fixed"}` et un seul constat européen avec sa date de règlement TARGET. Les valeurs communes `observation_months: 12`, `call_barrier: 1` et `protection_barrier: .60` servent à la compatibilité du transport.

Le prix d’émission et le MTM représentent une position longue en EUR par 100 de référence au fixing initial. La prime peut être nulle. À maturité, le flux `option_payoff` est `100 × max(0, strike_ratio − fixing_final / fixing_initial)` pour le put, ou `100 × max(0, fixing_final / fixing_initial − strike_ratio)` pour le call. Le reçu de cycle de vie le conserve dans `option_settlement`, y compris à zéro, avec `redemption: null` et la référence du fixing. Le MTM expose ce même flux et sa valeur actuelle jusqu’au règlement. QISTRA applique le signe des positions et tient le collatéral dans son portefeuille.

## Mesure sur le poste Windows

Le témoin utilise quatre Athena de deux ans sur seize séances, soit 64 MTM actifs, avec `n_paths=4096`, `seed=42` et `steps_per_year=52`. La mesure inclut le démarrage des processus. Elle isole le calcul du transport HTTP et de la persistance SQLite.

| Processus | Temps | Accélération |
|---:|---:|---:|
| 1 | 24,90 s | 1,00× |
| 2 | 15,30 s | 1,63× |
| 4 | 10,72 s | 2,32× |

Les 64 résultats et reçus sont identiques pour les trois exécutions. Le débit d'un backtest QISTRA complet dépendra aussi des rolls, des données, des attentes en file et des écritures.
