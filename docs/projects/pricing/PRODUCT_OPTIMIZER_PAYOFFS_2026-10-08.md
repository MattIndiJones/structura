# Product Optimizer — payoffs et champs dynamiques, 08/10/2026

État : **implémenté localement, tests ciblés et build réussis**, sans commit ni
push. Suite du [lot marché et économie](PRODUCT_OPTIMIZER_MARKET_ECONOMICS_2026-10-08.md).
Philippe a demandé de poursuivre les payoffs et de vérifier que les champs suivent
le script choisi. Le lot ajoute Phoenix, Phoenix mémoire, Athena dégressif et
reverse convertible européenne à l’Athena existant. Le modèle demeure GBM,
avec le même marché figé, les mêmes coûts et la validation indépendante N/2N.

## Champs affichés selon le script

| Script | Paramètres PayScript | Champs supplémentaires / retirés |
|---|---|---|
| Athena | `COUPON`, `M_AC_BAR`, `M_KI_BAR` | Coupon résolu, rappel et protection ; fréquence d’observation |
| Phoenix | Athena + `M_CPN_BAR` | Barrière coupon explorée, affichée dans les résultats |
| Phoenix mémoire | Même déclaration que Phoenix | Même barrière coupon ; mémoire portée par le script, sans interrupteur à ajouter |
| Athena dégressif | `COUPON`, **`PARAM() M_AC_BAR`**, `M_KI_BAR` | Seuil initial, baisse par observation, plancher et rang de première baisse ; série effective affichée dans les résultats |
| Reverse convertible | `COUPON`, `M_KI_BAR` | Aucun seuil de rappel, aucune fréquence ni contrainte de probabilité de rappel |

Les champs du formulaire proviennent de `/api/product-optimizer/capabilities`.
Le serveur parse les scripts du catalogue avec le compilateur PayScript, puis
expose les paramètres déclarés, leurs types, unités, caractères requis et rôles
de recherche. L’adaptateur métier définit les bornes et la grandeur résolue.
Le frontend ne possède pas une seconde liste de paramètres par famille.

Le sélecteur **Famille / script** remplace la famille Athena précédemment fixe.
Le bloc **Script utilisé et paramètres requis** permet d’examiner le script exact,
les paramètres et le rôle de chaque champ. La barrière coupon apparaît uniquement
sur Phoenix ; les réglages de dégressivité uniquement sur `PARAM() M_AC_BAR`.

À chaque changement de famille, les champs devenus inapplicables sont retirés
de l’état actif et de la requête. Les nouveaux champs sont initialisés à des
hypothèses visibles. Les axes communs, notamment maturité et protection, sont
conservés ; le marché et l’économie d’émission restent ceux saisis. Les réglages
spécifiques sont réinitialisés lors d’un nouveau choix de famille. Le comptage
de grille inclut la barrière coupon Phoenix et n’inclut aucun rappel sur RC.

Le backend refuse les champs étrangers à la famille, les paramètres requis
absents, les réglages incomplets et une contrainte de rappel sur RC. Si les
déclarations ou les calendriers d’un script divergent de l’adaptateur qualifié,
la famille devient indisponible ; aucun paramètre nouveau n’est ignoré. Les
libellés de coupon utilisés pour les analytics sont aussi vérifiés.

Ce mécanisme concerne les **scripts catalogue qualifiés**. L’Optimizer ne propose
pas l’optimisation libre d’un script arbitraire : un nouvel objectif ou paramètre
demande un adaptateur et une qualification économique avant activation.

## Payoffs et conventions de recherche

| Famille / événement | Flux et état |
|---|---|
| Athena, rappel | Coupon par période × rang + nominal ; `STOP` |
| Phoenix, barrière coupon tenue | Coupon de la période ; pas d’arrêt sauf rappel |
| Phoenix, coupon manqué | Coupon définitivement perdu |
| Phoenix mémoire, coupon payé | Coupon par période × `(INDEX − MEMO)` ; `MEMO = INDEX` |
| Phoenix / mémoire, rappel | Coupon éventuel traité avant nominal ; `STOP` |
| Phoenix mémoire, maturité sous barrière coupon | Mémoire résiduelle non payée ; remboursement du capital selon protection |
| RC, maturité | Coupon unique + nominal, moins la perte du put vendu si protection franchie |
| Toutes, protection européenne | À égalité sur la barrière, protection conservée ; en dessous, remboursement du niveau final, hors coupon |

Les scripts catalogue existants sont réutilisés sans modification. La recherche
Phoenix impose barrière coupon ≤ seuil de rappel, afin d’assurer le paiement du
coupon au rappel dans ce périmètre ; les candidats incompatibles sont rejetés
avant pricing. Elle n’impose pas de relation supplémentaire entre protection et
barrière coupon. Les maturités sont 12 à 60 mois, avec fréquences 1/3/6/12 mois
pour les autocalls, sans stubs. La protection se recherche entre 30 et 100 %,
la barrière coupon entre 30 et 100 %, le rappel initial entre 80 et 120 %.

Le coupon annuel nominal est converti en montant PayScript :

- Autocalls : `COUPON = coupon_annuel × fréquence_en_mois / 12`.
- RC : `COUPON = coupon_annuel × maturité_en_mois / 12`, paiement unique.

La RC utilise `CONSTAT MaturityDate`, avec convention et règlement explicites.
Son coupon ne constitue pas un revenu périodique ou un TRI. Sa durée moyenne est
la maturité observée ; les métriques de rappel sont nulles et retirées de l’interface.

Pour l’Athena dégressif, la série est générée pour chaque observation :

`seuil(rang) = max(plancher, seuil_initial − baisse × max(0, rang − premier_rang_de_baisse + 1))`.

Exemple : initial 100 %, baisse 5 points, premier rang 2 et plancher 80 % donnent
100/95/90/85 % sur quatre constatations. Une première baisse située après la dernière
observation garde le seuil plat sur cette structure. Le plancher ne peut dépasser
le seuil initial minimal ; la protection ne peut dépasser le plus bas seuil utilisé.
La série entière est envoyée dans `user_params.M_AC_BAR` et exportée avec le candidat.

## Analytics et validation quantitative

Phoenix verse des coupons à plusieurs dates. Le moteur expose en option les
libellés des flux par trajectoire et les dates de terminaison contractuelle,
avec le même ordre base/antithétique que les flux. Le prix, la diffusion et les
règles de paiement ne changent pas. Les analytics utilisent la terminaison
contractuelle, plutôt que de déduire un rappel d’un paiement intermédiaire.

Le diagnostic de coupon reconstruit désormais chaque flux à sa propre date de
paiement, avec les courbes de taux et de funding du pricing. Les jambes identifiées
comme coupons fournissent la pente du PV par rapport au coupon annuel. Il ne suppose
plus que tous les flux arrivent à la dernière date ou que tout montant au-dessus
du nominal est un coupon. Le diagnostic ne modifie jamais le coupon proposé.

Phoenix et mémoire ajoutent deux métriques Q : **coupons cumulés payés** et
**coupons cumulés non payés**, en points de nominal, non actualisés, jusqu’à
terminaison. Sur Phoenix, le second montant désigne les coupons perdus ; sur
mémoire, la mémoire restant non payée. Les coupons futurs après rappel ne sont
pas comptés comme manqués. Les deux métriques utilisent les paires antithétiques
et des bornes de Bernstein dans la validation indépendante.

La sélection reste figée à cinq candidats au maximum, sans résolution du coupon
sur les holdouts ni remplacement adaptatif après rejet. La correction de confiance
Phoenix utilise `alpha = 0,05 / (13 × taille_sélection)` : six métriques finales,
six comparaisons N/2N et un diagnostic de coupon. Les autres familles conservent
l’allocation conservatrice de neuf contrôles. Le classement et Pareto restent
fondés sur coupon et protection ; Pareto ne certifie pas une dominance sur la
barrière coupon, les échéances ou toutes les dimensions de risque.

Le budget mémoire ajoute une réserve pour les listes de flux libellés et les
buffers statistiques au pic du moteur. Le nombre de processus est réduit avant
refus quand cette mémoire concurrente dépasse le plafond de 256 Mio. Les chemins
Phoenix avec paiements répétés sont provisionnés selon le nombre de constatations.

## Vérifications

**142 tests backend ciblés distincts réussis** : 89 tests Optimizer existants,
40 tests payoffs/champs dynamiques et 13 prix de référence du moteur partagé.
Les cinq derniers tests (garde des libellés et worst-of) ont été lancés après ajout.
**305 tests frontend réussis et build réussi** via `npm run build`.
Aucune suite backend complète, aucun serveur applicatif lancé, aucune base réelle
modifiée ni téléchargement de marché pendant ce lot.

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_product_optimizer.py backend/tests/test_product_optimizer_parallel.py backend/tests/test_product_optimizer_validation.py backend/tests/test_product_optimizer_market.py backend/tests/test_product_optimizer_payoffs.py -q
.venv/Scripts/python.exe -m pytest backend/tests/test_product_optimizer_payoffs.py -q -k 'coupon_label_changes or two_asset'
.venv/Scripts/python.exe -m pytest backend/tests/test_engine_golden.py -q -k 'prix_inchanges_sans_courbe_tous_modeles or prix_inchange_autocall or prix_inchange_produit_a_barriere'
```

Couverture effective : flux déterministes aux barrières et à égalité ; coupon
simultané au rappel et arrêt ; mémoire rattrapée, remise à zéro et non payée à
maturité ; perte du put vendu ; vraie série dégressive qui avance le rappel ;
coupon RC annualisé sur trois ans ; effets de la barrière coupon et de la mémoire
sur les prix à tirages communs ; résolution mono-actif et worst-of à deux actifs ;
holdouts et diagnostic de coupon disponibles sous courbes, funding et coûts.

Les processus Windows reproduisent les candidats et recommandations séquentiels
sur mémoire, dégressif et RC. Leurs champs, flux et métriques sont exportés.
Les prix de référence des modèles et des barrières du moteur restent inchangés.
La sortie optionnelle de libellés est aussi testée avec et sans antithétiques.

Le rendu serveur du composant de champs vérifie Phoenix, mémoire, Athena,
dégressif et RC. Les tests de construction de requête vérifient retrait des
champs cachés, conversions %/fractions, rang conservé en entier et données requises
manquantes. Le fixture frontend est comparé aux métadonnées serveur actuelles.
Il peut être régénéré depuis les capabilities si le catalogue évolue.

La recette visuelle interactive complète n’a pas été exécutée pour ce lot.
La qualification de la grille temporelle à quelques bps et des données de marché
externes demeure ouverte. Le [smile actions URGENT](SMILE_ACTIONS_URGENT_2026-10-08.md)
reste différé ; les payoffs à barrières américaines ou fenêtres restent hors périmètre.
Les prochaines familles de la feuille de route sont capital protégé, booster et
gear put, avec objectifs et unités propres, avant monitoring continu et fenêtres.

## Fichiers

`backend/app/core/product_optimizer/families.py` porte les adaptateurs et le schéma
issu des scripts. `contracts.py`, `service.py`, `statistics.py` et `validation.py`
font appliquer champs, calendriers, métriques et confiance. `payscript/engine.py`
ajoute uniquement la sortie optionnelle de labels/terminaison dans ce lot.
`frontend/src/components/OptimizerPayoffFields.vue` et `utils/optimizerPayoff.js`
pilotent le formulaire de `ProductOptimizerView.vue`. Les bundles `frontend/dist/`
sont régénérés par le build ; aucun bundle modifié manuellement.
