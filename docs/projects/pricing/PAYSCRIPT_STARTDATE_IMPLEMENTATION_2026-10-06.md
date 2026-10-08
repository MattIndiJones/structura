# PayScript — Basket / StartDate : implémentation du 06/10/2026

**État : implémenté et vérifié par tests ciblés et recette navigateur.**
Branche : `codex/payscript-basket-startdate`, issue du checkpoint `260ff8f`.
Les modifications de cette implémentation ne sont pas encore commitées.

Ce rapport remplace l'état « proposition » du
[cadrage](PAYSCRIPT_STARTDATE_UNDERLYING_DESIGN_2026-10-06.md) et de la
[revue transversale](../../audits/AUDIT_TRANSVERSAL_PAYSCRIPT_2026-10-06.md).
Ces deux documents conservent l'inventaire antérieur, à titre historique.

## Contrat implémenté

- `UNDERLYING Basket` désigne les actifs d'Economics, dans leur ordre contractuel.
  `Basket.yield` retourne leurs ratios spot / fixing initial ; 1,10 signifie
  110 % du niveau initial. `WORSTOF`, `BESTOF` et `AVG` agrègent ces ratios.
- `CONSTAT StartDate` et `AT StartDate: Basket.spot0 = Basket.spot@StartDate`
  initialisent les références une seule fois. L'initialisation n'est ni un flux
  ni l'observation de rang 1. La liaison est reconnue par les déclarations et
  l'affectation : les noms Basket et StartDate peuvent être personnalisés.
- La première date d'`ObservationDates` est **incluse**. Elle doit suivre le
  fixing initial ; une fenêtre initiale doit être terminée avant l'observation.
  `INDEX` commence à 1 à cette première observation. Pour un calendrier `PERIOD`,
  le début de la première période reste une borne distincte.
- `PARAM` / `PARAM()` sans défaut exige une saisie en pourcentage dans Economics.
  8 devient 0,08 au moteur. `= 1.5` garde un défaut brut ; `= 8%` un défaut en %.
  Les brouillons peuvent être incomplets, les calculs exigent leurs entrées.
- Chaque instruction `PAY` conserve sa jambe : coupon, capital et put vendu.
  Les jambes de valeur nulle figurent dans les flux, sans créer de paiement dans
  les probabilités ou les statistiques de durée. `STOP` empêche de payer la
  maturité après un rappel, y compris lorsque les deux blocs partagent une date.

## Modèles et interface

Le catalogue contient **19 modèles génériques** sans maturité, dates ou paramètres
préremplis. `frontend/src/data/productCatalogue.json` est la source commune ;
les copies Python et la bibliothèque de l'éditeur en dérivent. Les anciennes
variantes datées de l'éditeur sont remplacées.

Normal et Expert utilisent le même script et les mêmes Economics. Expert expose
les réglages détaillés ; changer de mode ne change pas le payoff. Le Pricer et la
RFQ partagent les champs de calendrier, leurs conversions et leurs aperçus.

« Sauvegarder » conserve un modèle générique. Le volet secondaire
« Configurations enregistrées… » conserve un jeu de valeurs/dates avec la version
du script et, au choix, le panier et ses hypothèses. Avant application, un aperçu
affiche le modèle, les unités, les dates et les données qui seront remplacées.
Les configurations personnalisées n'ont pas de version de catalogue inventée.

## Raccordement aux autres modules

| Domaine | Modification et contrôle |
|---|---|
| Parser et moteur | Traduction contrôlée des propriétés Basket, paramètres requis, référence initiale par actif et identification des jambes PAY. Pas d'accès Python arbitraire ajouté. |
| Calendriers | StartDate séparée, première observation incluse, fenêtres et périodes conservées, maturité dérivée des événements pour les nouveaux contrats datés. |
| Product / RFQ / Booking | Brouillons incomplets admis, contrôle avant exploitation, panier contractuel, valeurs effectives, calendrier figé v2 lié au hash du script et à l'origine. |
| Fixings / MtM / Greeks / Explain | Références initiales transportées dans le rejeu et l'état résiduel ; métadonnées techniques masquées dans la mémoire affichée. |
| Backtest / MTF | Calendriers décalés pour chaque fenêtre historique ; initialisation et références individuelles conservées dans les états transmis. |
| Solveur / grilles | Le paramètre recherché peut manquer avant résolution ; les autres valeurs requises et les bornes doivent être fournies. |
| Optimizer | Construction du nouveau contrat avec StartDate et première observation explicites, puis transfert au Pricer. |
| Roll / réinvestissement / avenants | Décalage conjoint des dates ; fixing historique verrouillé en avenant. Une nouvelle maturité déplace les calendriers terminaux et préserve les constats intermédiaires compatibles. |
| Monitoring / Risk / CCR | Analyse des observables Basket et des alias simples ; utilisation des valeurs bookées. Une expression non reconnue ne devient pas implicitement un worst-of. Les consommateurs résiduels partagent le contrat et le moteur. |
| EMT / documents / clients | Analyse du nouveau vocabulaire côté EMT ; documents et projections conservent le dossier Product et les résultats de calcul sélectionnés. Aucun nouvel objet produit concurrent ajouté. |
| Assistant IA | Manuel et exemples du catalogue actualisés ; aucun horizon de pricing inventé quand maturité ou dates manquent. |
| Génération UAT | Modèles génériques et nouveaux calendriers dans le parcours Product → RFQ → Booking → fixings/valorisation. |

La [revue UAT du 07/10](../../audits/AUDIT_GENERATEUR_UAT_2026-10-07.md)
complète cette adaptation : Phoenix Mémoire raccordé au script à mémoire et
capital garanti repris sans réécriture locale du catalogue. La couverture reste
limitée aux quatre familles du générateur et au modèle de vol constant.

L'ancien CLI `backend/scripts/generate_demo_deals.py` est retiré : son import de
portefeuille était déjà invalide et son écriture directe de Deal contournait le
Product canonique. Il affiche désormais l'accès au Générateur UAT et ne modifie
aucune donnée. Les anciennes formules du générateur ne sont plus une source active.

Les modèles de diffusion, les conventions de drift et le funding ne sont pas
modifiés par cette refonte. Les données AMC, utilisateurs, référentiels, clients
et portefeuilles ne sont pas reconstruits.

## Vérifications effectuées

Tests ciblés uniquement, depuis la racine du dépôt, avec bases temporaires :

- Parser, liaisons Basket et référence du langage : valeurs manquantes,
  pourcentages/tableaux, WORSTOF/BESTOF/AVG, ordre des actifs, cours bruts,
  conflit de strike, première observation, fenêtres initiales et sécurité des
  propriétés. Scénarios déterministes de rappel, capital et put à maturité.
- Catalogue : **60 tests passés** ; templates : **60 tests passés**.
- Optimizer : **37 tests passés** ; Product : **25 tests passés** lors de leur
  exécution ciblée, puis contrôles complémentaires de calendrier et de binding.
- In-life, fenêtres MTF, constatations de période, backtests, rolls et avenants :
  groupes ciblés exécutés ; les échecs identifiés ont été corrigés puis rejoués.
  Le nouveau cas de MtM à niveau 40 %, volatilité nulle, rembourse 40 % avec
  capital et put distincts. Les références initiales historiques restent à 100.
- UAT : parcours et scénarios ciblés sur les familles disponibles, y compris
  rappel et annulation des observations postérieures, rejoués après correction
  des attentes liées à l'ancienne première observation.
- Watchlist de portefeuille, EMT et assistant IA : contrôles ciblés passés.
  Assistant IA : **35 tests passés, 1 ignoré** (liste d'anciens exemples
  complémentaires désormais vide), puis test ajouté de maturité manquante passé.
- Réinvestissement : déplacement du fixing et de l'échéancier, horizon effectif,
  maintien du constat intermédiaire et lecture des barrières bookées vérifiés.
- Frontend : **231 tests passés**, build Vite réussi après les dernières
  modifications Vue ; `frontend/dist` régénéré. Avertissements de découpage des
  imports dynamiques conservés, sans échec de build.
- `git diff --check` et compilation syntaxique des fichiers Python modifiés : OK.

Ces exécutions se recouvrent : les nombres ne constituent pas un total de tests
distincts. **La suite backend complète n'a pas été lancée.** Risk/CCR, documents
et toutes les vues n'ont pas chacun fait l'objet d'une recette navigateur complète.

### Recette navigateur isolée

Réalisée sur le port 8011 avec `tmp/payscript-ui.db`, sans utiliser la base réelle
pour les essais. Athena : StartDate 06/10/2026, observations annuelles du
06/10/2027 au 06/10/2029, coupon 8 %, rappel 100 %, protection 60 %.

- Trois observations, rang 1 en 2027, fixing initial à part.
- Prix observé : **97,90 %**, IC95 **[97,76 ; 98,05]**, 20 000 trajectoires.
- Flux de coupons, capital au rappel, capital final et put affichés séparément.
- Configuration enregistrée puis appliquée ; seconde sauvegarde sans panier,
  aperçu visuel avec unités, modèle version 2.0 et dates vérifié.
- Conservation Product et transfert au masque RFQ : mêmes termes et calendriers.
  Le panier hypothétique de cette recette n'avait pas de ticker ; la création
  finale de cette RFQ n'a pas été soumise. Le parcours complet est couvert par
  les tests UAT avec actifs identifiés.

Le serveur isolé lancé pour la recette a été arrêté après vérification de ses
PID ; le port 8011 est libéré. L'instance préexistante n'a pas été arrêtée.

### Recette complémentaire après livraison

La [recette du 06/10](../../audits/RECETTE_PAYSCRIPT_2026-10-06.md), exécutée
ensuite sur une nouvelle base isolée, étend la preuve navigateur jusqu’au booking
d’un Athena avec ticker AXA.PA, puis à la duplication/conversion RFQ. Elle ajoute
133 oracles métier et recense 514 cas backend distincts et 233 tests frontend
passants. Les configurations sans panier et les modèles sauvegardés vides sont
également revérifiés.

Trois défauts trouvés et corrigés : erreur de paramètre requis masquée par le
store, fenêtre sur jour fermé incluant un fixing futur, et paramètres/snapshot
perdus lors d’un changement de type ou d’une conversion RFQ. Le rapport détaille
les limites, notamment l’absence de clôture Yahoo disponible dans la recette.
La base réelle est inchangée pendant cette phase ; son serveur temporaire a été
arrêté. Ces résultats complètent les contrôles initiaux ci-dessus.

## Nettoyage autorisé des anciens jeux de test

Sauvegarde SQLite cohérente avant modification :
`backend/data/structura-before-payscript-20261006.db` (non versionnée).
Essai intégral sur copie avant application transactionnelle à la base réelle.

Supprimés : 42 deals, 41 RFQ, 82 quotes, 42 Products et leurs 42 termes,
543 révisions, 122 calculs, 120 commandes, 316 événements, 115 fixings,
26 propositions lifecycle, 78 valorisations, 8 stress historiques, 2 notes,
29 alertes et 7 rattachements de deals aux portefeuilles. Il n'y avait aucun
script sauvegardé en base. Les deux lots UAT concernés sont marqués supprimés.

Les trois protections SQL de suppression de l'historique produit ont été
suspendues puis recréées à l'identique **dans la même transaction**, pour retirer
aussi les deux dossiers de test manuels non étiquetés UAT. Aucune protection n'est
désactivée après l'opération. Vérification des triggers, empreintes des lignes
préservées, clés étrangères et intégrité SQLite : OK. Utilisateurs, référentiels,
AMC, portefeuilles, journal d'audit et journal du scheduler conservés.
Le manifeste local est `tmp/payscript-cleanup-manifest.json`.

## Limites explicites et reprise

- Une seule déclaration UNDERLYING pour le panier Economics ; propriétés autorisées
  `yield`, `spot`, `spot0`. Pas de référence arbitraire à une date future.
- Le fixing initial sur fenêtre utilise `CONSTAT StartDate AVG/MIN/MAX`.
  `CONSTAT() StartDate` est refusé : aucune réinitialisation répétée des strikes.
- Saisir une StartDate effective ; une convention qui déplacerait l'origine
  provoque une erreur explicite. Les conventions d'observation et de paiement
  restent disponibles.
- Les lectures de cours absolus nécessitent les niveaux initiaux par actif.
  `Basket.yield` et `Basket.spot / Basket.spot0` fonctionnent directement en ratios.
- Les primitives historiques du langage restent reconnues pour les tests et
  scripts personnalisés ; les bibliothèques actives utilisent la nouvelle syntaxe.
- Le scan de réinvestissement conserve sa limite existante au mono-sous-jacent.
  Le Générateur UAT conserve ses familles disponibles ; ce n'est pas une recette
  automatique exhaustive des 19 payoffs et de tous les modèles de diffusion.

Pour charger le nouveau backend dans l'application habituelle, redémarrer
l'instance préexistante puis recharger le navigateur. Conformément à `CLAUDE.md`,
l'assistant ne l'a pas remplacée pendant cette session.
