# Recette PayScript — Basket, StartDate et modèles génériques

Date : 06/10/2026. Branche : `codex/payscript-basket-startdate`.
Recette exécutée après accord de Philippe sur la livraison décrite dans le
[rapport d’implémentation](../projects/pricing/PAYSCRIPT_STARTDATE_IMPLEMENTATION_2026-10-06.md).
Les modifications restent locales, sans commit ni push pendant cette recette.

## Verdict

**Recette validée sur le périmètre ci-dessous, après trois corrections.**
514 cas backend distincts passent, ainsi que les 233 tests frontend et le build
Vite. Les parcours navigateur comprennent désormais un booking effectif dans
une base isolée, la conversion de RFQ et la sauvegarde de modèles/configurations.
La suite backend complète n’a pas été lancée.

Cette recette ne constitue pas une validation exhaustive des 19 payoffs sous
chaque modèle de diffusion, ni de chaque écran de l’application. La disponibilité
du fournisseur de cours réels n’est pas validée : Yahoo n’a pas fourni la clôture
AXA demandée ; le statut de fixing manquant reste explicite.

## Anomalies trouvées et corrigées

| Anomalie | Conséquence | Correction et preuve |
|---|---|---|
| Construction de la requête de pricing hors du traitement d’erreur | Un `PARAM` obligatoire vide provoquait une erreur sans message utilisateur | `pricing.js` affiche l’erreur avant l’appel réseau, en émission et en cours de vie. Deux tests frontend et vérification navigateur de « Le paramètre COUPON est requis. » |
| Ancre d’une fenêtre de constatation sur jour fermé passée par l’ajustement de paiement J+0 | Une moyenne finissant un samedi pouvait inclure le lundi suivant | `observation_window` conserve l’ancre avant application de sa convention explicite. Tests de fenêtre 1D, absence de fixing futur, inclusion du dernier fixing et 59 tests ciblés de calendriers/fenêtres/MtF. L’ajustement des dates de paiement reste inchangé. |
| Changement Indicatif/To trade réinitialisant les paramètres ; conversion d’une RFQ abandonnant son script figé | Perte des valeurs requises et impossibilité de reprendre certains scripts personnalisés | Le changement de type conserve les saisies. La conversion réutilise le chemin de duplication, reprend le snapshot, les paramètres et les calendriers, et retire un éventuel contexte Product précédent. Vérification navigateur et comparaison des enregistrements SQLite des trois RFQ. |

Une nouvelle consultation issue d’une duplication/conversion demande toujours
la date de valeur et la date de paiement. Elle conserve le fixing initial et
les observations explicites du script source. C’est une nouvelle RFQ et un
nouveau dossier Product ; la RFQ source et son deal restent inchangés.

## Couverture automatisée exécutée

Chaque groupe a été lancé depuis la racine du dépôt, avec un `--basetemp` propre
sous `tmp/`. Les bases de tests sont temporaires ou en mémoire.

| Groupe | Fichiers ou contrôles principaux | Résultat |
|---|---|---:|
| Langage et catalogue | `test_parser`, `test_payscript_binding`, `test_product_catalogue`, `test_payscript_reference` | 149 passent |
| Cycle de vie UAT | `test_uat_generation` : Product, RFQ, booking, fixings, états de vie et valorisations sur données contrôlées | 33 passent |
| Consommateurs de dates | `test_product_optimizer`, `test_analytics_calendrier`, `test_risk_dates` | 62 passent |
| Documents | `test_emt`, `test_valuation_pdf`, `test_kid_mrm` | 37 passent |
| Historique et résiduel | `test_backtest_oracle`, `test_mtf_fenetres`, `test_variantes_roll` | 49 passent |
| Calendriers après correction | `test_schedule`, `test_schedule_settlement`, `test_constatations_periode`, `test_fenetre_de_depart_vie`, `test_mtf_fenetres` | 59 passent |
| Nouveaux oracles métier | `test_payscript_acceptance` | 133 cas distincts passent |
| Frontend | Vitest, dont validation des paramètres manquants | 233 passent |
| Construction | `npm run build` : Vitest puis Vite | Réussie |

Les groupes se recouvrent. Le décompte de **514 cas backend distincts** est issu
des identifiants `(classname, name)` des rapports JUnit, et non de leur somme.
Les 133 nouveaux cas comprennent une exécution du fichier à 132 cas, puis le
test supplémentaire du dernier fixing. Aucun échec ni test ignoré dans ces
rapports. Des avertissements de dépréciation Python et de découpage Vite
subsistent ; ils n’ont pas fait échouer les contrôles.

Les nouveaux oracles contrôlent notamment :

- les 19 payoffs à six niveaux de marché (40 %, 60 %, 90 %, 100 %, 115 %, 140 %),
  avec remboursement attendu calculé indépendamment du moteur ;
- les coupons Phoenix avec et sans mémoire, le rappel final sans double
  remboursement et le franchissement intermédiaire d’une barrière américaine ;
- le rapprochement des lignes de flux et du prix, avec et sans antithétiques ;
- le passage d’un contrat explicite Basket/StartDate dans le véritable moteur
  CCR, avec compensation exacte de deux positions opposées ;
- l’injection par le solveur et la grille des paramètres qu’ils font varier,
  même lorsqu’ils sont déclarés requis et absents des paramètres saisis ;
- une moyenne terminale de trois fixings 90/120/150 sur un initial de 100 :
  le call verse exactement 20 %, sans lecture au-delà de sa date de constatation.

La syntaxe des 35 fichiers Python modifiés/nouveaux contrôlés et
`git diff --check` sont également valides.

## Recette navigateur et persistance

Serveur temporaire `127.0.0.1:8011`, base
`tmp/payscript-acceptance-1006.db`, scheduler désactivé. Les références ci-dessous
sont exclusivement celles de cette base de recette.

### Athena : de l’éditeur au deal

Scénario : AXA.PA, nominal 1 000 000 EUR, coupon 8 %, rappel 100 %, protection
60 %. StartDate et valeur 06/10/2026 ; observations annuelles du 06/10/2027 au
06/10/2029 ; paiement final 10/10/2029. Hypothèses manuelles GBM : volatilité
20 %, dividende 2 %, taux 3 %, N=20 000, seed=42.

- Modèles génériques sans paramètres ni dates préremplis ; erreur explicite sur
  coupon absent ; même texte en Normal et Expert.
- Prix observé **97,90 %**, IC95 **[97,76 ; 98,05]**. Trois observations de payoff,
  dont la première au rang 1 en 2027. Capital, coupons et put séparés à l’écran.
- Conservation dans `PRD-20261006-001`, termes v1, puis création de
  `RFQ-20261006-001` en To trade sans perte de paramètres.
- Prix de contrôle RFQ **97,90 %** ; cotation fictive retenue à **97,20 %**,
  recalcul dans le Pricer, puis booking `DEMO-20261006-001`.
- Dans Events : un fixing initial au 06/10/2026, séparé des trois observations
  2027/2028/2029. Le fixing initial reste attendu, avec erreur de source visible
  lorsque Yahoo ne fournit pas de clôture. Aucune donnée n’a été inventée.
- Vérification SQLite : même Product et termes v1 entre RFQ et deal, scripts
  identiques, paramètres moteur 0,08 / 1 / 0,6, calendriers identiques, trois
  dates de payoff attendues et aucune violation de clé étrangère.

### Reprise RFQ et modèles

- Duplication de la RFQ précédente en `RFQ-20261006-002` indicative, puis
  conversion en `RFQ-20261006-003` To trade. Les trois scripts figés, paramètres
  et calendriers sont identiques en base, même sans `script_id` de bibliothèque.
- Configuration « RECETTE Call strike 110 » enregistrée sans panier. Après
  passage au Put, son aperçu affiche Call, version 2.0, strike 110 % et les
  dates 06/10/2026–06/10/2027. Application : retour au Call, strike 110 et dates
  restaurés ; le panier courant est conservé.
- Sauvegarde séparée « RECETTE Modèle Call générique » : `params_json`,
  `constats_json` et `global_params_json` sont tous `{}`. La configuration
  préremplie et le modèle vide restent deux objets distincts.

## Limites et clôture technique

### Retour utilisateur après recette : dates manquantes et cours en devise

La capture de Philippe a révélé un cas absent du premier contrôle : les PARAM
étaient remplis, mais StartDate était vide. Le serveur recevait une durée nulle
et des dates vides ; son tableau de validation JSON était affiché tel quel.
La validation précédente ne couvrait que les paramètres requis.

Correction complémentaire : avant le pricing initial ou en cours de vie,
StartDate et les dates des calendriers explicites sont contrôlées ; le message
« Renseignez la StartDate (date de strike) dans Economics. » ouvre Economics.
Les erreurs structurées du serveur sont traduites en français, avec dédoublonnage
des champs équivalents et affichage sur plusieurs lignes dans le bandeau.

Le champ « Cours de référence pour Basket.spot / spot0 » prêtait à confusion :
le ratio ne demande aucun cours en devise pour un pricing initial. Le champ est
désormais dans une section Expert repliée « Cours en devise — scripts spécifiques »,
avec sa devise, sa nature d’hypothèse de simulation et l’explication du ratio.
Les fixings contractuels restent gérés dans Events.

Vérification complémentaire : **243 tests frontend passent** (10 cas ajoutés),
build Vite réussi. Les tests rejouent StartDate absente puis complétée sans
cours absolus, les dates invalides et les réponses HTTP 422 structurées. Le
message StartDate a aussi été constaté dans le navigateur sur une session de
pricing éphémère du serveur préexistant, sans sauvegarde de produit ni booking.
Le serveur préexistant n’a pas été arrêté.

### Limites de la recette initiale

- Fixings et valorisations résiduelles sont couverts par les tests UAT et les
  tests métier ciblés. Le navigateur ne prouve pas une récupération Yahoo
  réussie ni une valorisation résiduelle du deal fraîchement booké.
- Les oracles couvrent des scénarios déterministes, pas toutes les combinaisons
  panier/modèle de diffusion/calendrier. La recette navigateur financière porte
  sur Athena sous GBM ; Risk, CCR et documents disposent ici de tests ciblés,
  pas d’une recette de tous leurs écrans.
- Les sauvegardes avec panier ont été vérifiées lors de l’implémentation ; cette
  recette complémentaire vérifie le cas sans panier et la séparation du modèle.
- Le serveur temporaire et son processus parent ont été arrêtés après contrôle
  des PID, heures de création et commandes. Port 8011 libéré, onglet fermé.
- L’empreinte SHA-256 de `backend/data/structura.db` est identique avant et après
  cette recette. Aucun nettoyage ou changement de la base réelle pendant celle-ci.

Preuves locales non versionnées : `tmp/recette-payscript-*.xml`,
`tmp/recette-payscript-ui-proof.json`, journaux `tmp/recette-ui.*.log` et
`tmp/recette-ui-processes.json`. Les tests reproductibles et les corrections
figurent dans le dépôt ; la base isolée est conservée sous `tmp/`.
