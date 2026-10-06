# CCR — intégration STRUCTURA

> **Revue documentaire du 05/10/2026** : socle et extensions CCR 1.2 présents
> sur `main` (`15d7ccf`) : préparation MtM, marché commun, cache/progression et
> contrôle d'un deal booké. Les paragraphes initiaux décrivent la V1 du 28/09 ;
> les sections ultérieures précisent ses évolutions, notamment le taux provisoire
> commun de 3 % lors de la préparation. EAD SA-CCR toujours absente. La recette
> visuelle complète reste ouverte ; aucune nouvelle exécution ni consultation
> de la base réelle lors de cette revue. Voir les [preuves de lecture](../../audits/REVUE_DOCUMENTAIRE_2026-10-05.md).

## Architecture inspectée

FastAPI / SQLModel / SQLite (`db/models.py`, migrations additives dans
`db/database.py`), Vue / Pinia / Chart.js. Le référentiel `Counterparty` est
global et déjà distinct du CRM `Client` et de `RfqProvider`. Les données CCR
sont rattachées à ce référentiel et cloisonnées par `User.entity_id`.
`Counterparty.limit_eur` reste une limite historique de concentration nominale.

Le Product canonique et le Deal figent les termes. Le sens Deal est celui de
la banque : `vente` = position longue pour STRUCTURA ; RFQ porte notre sens.
Le moteur PayScript contient le Monte-Carlo et le Mark-to-Future. Le contexte
résiduel vient de `deal_valuation.mtm_core`, utilisé aussi en VaR. Les scénarios
sont dans `var_engine`, le workflow dans `workflow` / `rfq_controls`, l'audit
dans `core/audit`. Aucun moteur SA-CCR/XVA existant identifié.

## Invariants

- MtM positif = créance de STRUCTURA. Risques en montants, pricing en % nominal.
- Aucun netting par simple nom de contrepartie. Même entité, même accord actif,
  close-out enforceable et même set enforceable, périmètre produit admissible.
- Les scénarios sont communs aux deals avant agrégation et quantile.
- Exposition inconditionnelle : les contrats remboursés sortent à zéro après
  paiement ; un flux constaté et non payé reste une créance.
- Avant/après sur les mêmes trajectoires ; incrément signé, jamais tronqué.
- Recovery et mesure de PD explicites. Pas de CVA marchande à partir de PD
  historiques ; l'absence de données ne devient jamais zéro ou OK.
- Le pricing demeure libre. Les limites contraignantes sont réévaluées au
  booking, sans faire confiance à un résultat envoyé par le navigateur.
- Les données réelles ne sont pas utilisées comme fixtures de test.

## Références méthodologiques

[BIS CRE52 — SA-CCR](https://www.bis.org/committees/bcbs/basel-framework/standard/cre/52/inforce/2019-12-15/published/2020-06-05)
et [BIS MAR50 — CVA](https://www.bis.org/committees/bcbs/basel-framework/standard/mar/50/inforce/2023-01-01/published/2020-07-08).
Ces références encadrent la séparation économique/réglementaire ; cette V1
ne revendique pas une homologation réglementaire.

## État de livraison

Socle V1 intégré à STRUCTURA, accessible par Accueil / Risk Management → CCR,
route `/risk/ccr`, et par les panneaux de contrôle crédit de Pricing et RFQ.
Les entrées, calculs et décisions sont persistés et auditables. Le périmètre
de projection économique est volontairement restreint au GBM compatible avec
le Mark-to-Future existant. Les capacités absentes sont indiquées comme telles.
La recette visuelle reste à faire : le navigateur intégré a refusé la page
locale (`ERR_BLOCKED_BY_CLIENT`) ; aucun autre navigateur n'était disponible.
La validation n'est donc pas une homologation complète pour la production.

## Migration et nouveaux modèles

Au prochain démarrage du backend, `SQLModel.metadata.create_all` crée huit
tables, puis la migration additive et idempotente ajoute
`deals.ccr_netting_set_id`, nullable, avec référence à `ccr_netting_sets.id`.
La base réelle n'a pas été ouverte pour migration pendant ce développement.
Les tests utilisent SQLite isolé. Aucun historique n'est réécrit, aucun accord,
recouvrement, collateral ou netting set n'est déduit des anciennes contreparties.

| Modèle | Objet |
|---|---|
| CCRCreditProfile | Identité juridique complémentaire, ratings, recouvrement et provenance, courbe PD ou spreads, mesure de PD, indicateurs ISDA/CSA tri-état |
| CCRMasterAgreement | Référence et version ISDA, droit applicable, date d'effet, statut, avis juridique, opposabilité et autorisation inter-produits |
| CCRCSAAgreement | Bilatéralité, seuils, MTA, VM, IM fixe, IA, haircut, fréquence, règlement et MPOR |
| CCRNettingSet | Accord/CSA associés, entités juridiques, devise, périmètre produit, opposabilité |
| CCRCreditLimit | Métrique, montant, devise, dates, seuils d'alerte et dur, action |
| CCRCollateralPosition | Position datée : reçu, posté, IM reçue, éligibilité, reconnaissance et source |
| CCRCreditOverride | Demande de dérogation documentée ; aucune approbation activée |
| CCRExposureCalculation | Entrées et résultats figés, empreintes, version moteur, utilisateur, date d'arrêté et horodatage |

Les sept référentiels portent `entity_id`, `counterparty_id`, `version`,
`updated_by` et `updated_at`. Le détail est un payload JSON validé par des
contrats Pydantic stricts, sans champs supplémentaires. Les références internes
sont contrôlées dans la même organisation et contrepartie. Un seul profil
crédit est autorisé par couple organisation/contrepartie. Les écritures sont
réservées aux administrateurs et exigent la version attendue pour une mise à
jour. L'audit conserve les états avant/après. Il n'y a pas d'API de suppression
des calculs ni de modification de leurs résultats.

Un utilisateur sans organisation peut continuer un booking historique sans
CCR, tant qu'aucune limite n'est configurée sur la contrepartie et qu'aucun set
n'est demandé. Sinon le contrôle exige son rattachement à une organisation.
Les écrans et API CCR nécessitent toujours ce rattachement.

## Moteur économique et données

`contracts.py` sépare les contrats, `exposure.py` les règles juridiques,
collatéral et métriques, `service.py` l'orchestration, et `api/ccr.py` les routes
authentifiées. La préparation des MtM est décrite ci-dessous ; la projection et le rejeu ne téléchargent aucune donnée de marché.

Pour un deal vivant, le service cherche un `ValuationRun` figé à la date
d'arrêté et à la version contractuelle du deal. Il réutilise son contexte
résiduel, ses fixings réalisés et ses flux constatés non payés. Une valeur de
booking ne remplace jamais un MtM absent. Les deals UAT sont exclus du périmètre
Production et accessibles dans le périmètre explicite Recette UAT. Les deals
historiques liés seulement par nom sont signalés comme incomplets.

Pour une proposition, les entrées du Pricer sont revalorisées par le moteur
existant. Le strike doit coïncider avec la date d'arrêté dans cette V1. Le signe
est explicite : MtM positif = créance de STRUCTURA. Les résultats internes de
pricing en fraction du nominal et les résultats MTF en pourcentage sont
convertis séparément en montants monétaires.

Le mode FAST fournit uniquement les montants actuels ; EE/PFE/CVA restent
indisponibles. FULL construit des facteurs communs aux trades, réutilise les
mêmes trajectoires avant/après, puis revalorise chaque contrat avec un
Monte-Carlo imbriqué. Une corrélation inter-produits absente doit être fournie
explicitement sous la forme `AAPL|MSFT`; aucune indépendance ni réparation de
matrice n'est ajoutée automatiquement. Des hypothèses incompatibles sur un même
facteur ou sur les taux empêchent la projection.

La grille suit le pas hebdomadaire du MTF, enrichi des observations et paiements
puis arrondi à cette maille. La créance connue reste exposée jusqu'au paiement,
y compris après autocall ou maturité ; elle sort ensuite à zéro. Les quantiles
incluent tous les scénarios, sans conditionner sur la survie du produit.
La maille hebdomadaire reste une approximation des dates contractuelles.

À chaque horizon, les MtM sont d'abord agrégés dans chaque set éligible,
puis le collatéral est retranché, puis la partie positive est prise. Les
expositions des sets sont ensuite additionnées scénario par scénario. EE est
la moyenne des scénarios ; PFE95/99 sont les quantiles interpolés linéairement.
Les métriques de limite PFE sont les maxima sur les horizons. EPE est la moyenne
temporelle de l'EE par intégration trapézoïdale. Les incréments sont signés :
`après - avant`. Un hedge peut donc réduire PFE et CVA.

Le budget impose `nombre de dates × outer × inner × nombre de trades ≤ 10 000 000`.
Les valeurs par défaut sont 256 scénarios extérieurs, 128 intérieurs, 8 horizons
avant enrichissement, seed 42. Une alerte explicite signale moins de 1 000
scénarios pour PFE99. Ces valeurs servent à l'exploration ; elles ne constituent
pas une démonstration de convergence pour un usage de limites en production.

## Netting et collatéral

La présence d'un ISDA ne suffit pas. Le set doit être actif et opposable,
l'accord actif, effectif et close-out enforceable, le produit éligible et la
devise compatible. Sinon le trade reste dans son propre bucket. Les sets ne
se compensent jamais entre eux. Un set réunissant plusieurs types de produit
requiert une permission inter-produits explicite ; sinon le calcul est incomplet.

Un CSA collatéralisé exige une position reconnue à la date d'arrêté. Les
positions connues zéro doivent être saisies explicitement. La valeur reçue est
`held × (1-haircut)` ; celle postée est `posted / (1-haircut)` et accroît la
créance. L'IM reçue n'est déduite que si sa reconnaissance est explicite.
Une créance de collatéral posté hors set éligible n'est pas silencieusement
omise : le résultat courant devient indisponible et doit être analysé séparément.

Les appels VM utilisent les seuils bilatéraux, MTA et independent amount.
Les transferts futurs tiennent compte de la fréquence, du délai de règlement
et du gel MPOR en jours ouvrés, selon les calendriers existants de STRUCTURA.
Le moteur ne simule les appels qu'aux dates de valorisation : une fréquence
quotidienne saisie ne transforme pas la grille hebdomadaire en simulation
quotidienne. Cette approximation est affichée. L'IM est fixe ; le montant
contractuel saisi ne remplace pas une IM effectivement reçue.

## Crédit, CVA et stress

La CVA est unilatérale, sous indépendance marché/défaut, avec LGD explicite.
Elle intègre `LGD × DF(t) × EE(t) × ΔPD(t)` aux extrémités droites de la grille.
Les PD doivent être qualifiées risk-neutral. Une courbe historique ne produit
pas une CVA marchande. Le service n'extrapole pas au-delà du dernier point.
La conversion spread/intensité est l'approximation déclarée `spread/LGD`,
constante par bucket ; aucun bootstrap CDS n'est revendiqué.

Les contextes incluant du funding/spread émetteur ne peuvent pas alimenter un
CCR clean sans traitement dédié : la métrique devient manquante. Le module ne
soustrait pas une seconde CVA au prix du Pricer et ne modifie pas ce prix.

Les stress de spot, volatilité, taux et corrélation utilisent le moteur de
scénarios existant. Un multiplicateur d'intensité crédit est appliqué séparément.
Base et stress sont conservés côte à côte. Le libellé WWR décrit un stress
conjoint explicite, jamais un modèle stochastique joint de défaut.

## Limites et décision

Métriques : nominal brut, exposition courante, PFE95, PFE99, CVA, exposition
stressée et emplacement réservé pour EAD. L'EAD n'est pas calculée : une limite
EAD contraignante reçoit MISSING_DATA et ne peut être déclarée satisfaite.

| Situation avec seuils par défaut 80 % / 100 % | Statut |
|---|---|
| 70 % | OK |
| 80 % à moins de 100 % | WARNING |
| Exactement 100 % | LIMIT_REACHED |
| Plus de 100 % | BREACH |
| Aucune limite active | NO_LIMIT, jamais OK |
| Valeur ou conversion monétaire absente | MISSING_DATA |

INFORMATION_ONLY et WARNING n'interdisent pas le booking. HARD_BLOCK interdit
le dépassement et les données manquantes ; l'égalité au seuil dur reste
LIMIT_REACHED. REQUIRE_APPROVAL bloque dès WARNING, LIMIT_REACHED, BREACH ou
MISSING_DATA. Le circuit d'approbation n'étant pas activé, une demande enregistrée
ne lève pas le blocage. Les limites de contrepartie ne peuvent pas être validées
par une analyse restreinte à un deal, portefeuille ou netting set.

Le contrôle final est recalculé côté serveur dans `_book_deal`, à partir du
reçu de pricing vérifié. Une écriture neutre prend le verrou SQLite avant
lecture des politiques et du portefeuille ; le contrôle et le booking partagent
la transaction. Un résultat présenté par le client ne vaut pas autorisation.
Les refus suivent l'audit BOOKING_REJECTED ; les contrôles acceptés sont audités.

## Parcours Pricing et RFQ

Dans Pricing → Deal, le panneau CCR reprend le nominal, la devise, le sens,
les paramètres du pricing valide et la contrepartie du formulaire. Sans
contrepartie, il calcule une exposition standalone ; une hypothèse de crédit
facultative permet une CVA indicative, explicitement USER_ASSUMPTION. Aucune
limite n'est contrôlée dans ce cas. Avec contrepartie, l'utilisateur choisit
un set éligible et obtient avant / deal seul / après / incrément. Le set est
transmis au booking. Une modification des entrées invalide le résultat affiché.

Dans RFQ, la réponse sélectionnée expose le même panneau. La contrepartie est
résolue exclusivement par `RfqProvider.counterparty_id`, même si le nom légal
diffère du label commercial du fournisseur. Les termes figés de la RFQ sont
utilisés avec leurs unités moteur, leur nominal et le sens bancaire adapté.
Le set peut être choisi pour le contrôle RFQ. Ce choix analytique n'est pas
persisté dans la RFQ : il faut le confirmer dans le formulaire Deal au booking.
La sélection de réponse reste autorisée ; l'exécution finale crée le Deal et
rencontre le contrôle serveur décrit plus haut.

## Analyse, monitoring et replay

L'écran CCR permet les filtres contrepartie, portefeuille, set et deal, les
profils EE/PFE, les limites, la configuration juridique, le rattachement motivé
des trades, les stress et l'export JSON. Le monitor affiche le dernier calcul
de périmètre contrepartie sans proposition. Il signale une date ancienne, une
configuration modifiée ou un périmètre contractuel différent. Ce n'est pas un
service de surveillance en arrière-plan.

Chaque calcul sauvegardé inclut paramètres, seed, contexte marché, versions
contractuelles, règles juridiques et collatéral. L'empreinte CCR complète celle
du moteur de pricing. Le replay travaille sur ces seules entrées et compare le
résultat. Il n'installe pas automatiquement un ancien binaire du moteur : une
évolution du code peut donc produire une différence, signalée dans l'interface.

## Tests et vérifications du 28/09/2026

Deux fichiers nouveaux : `backend/tests/test_ccr.py` et `test_ccr_api.py`.
Ils couvrent les seize cas métier demandés : standalone, absence d'ISDA,
opposabilité, netting autorisé, sets distincts, VM, IM, MtM négatif, incréments
positifs/négatifs, seuils, dépassement, hard block réel au booking, NO_LIMIT et
données incomplètes. S'y ajoutent CVA analytique, PD historiques refusées,
répétabilité, authentification, séparation des organisations, audit/version,
migration idempotente, autocall non payé, maturité/paiement, stress, créances
de règlement, refus du double crédit, collatéral posté hors set et mapping RFQ.

- **171 tests ciblés passent** : CCR, API CCR, RFQ, Products et chaîne
  pricing → booking → MtM. Dont **27 nouveaux tests CCR** (paramétrisation incluse).
  Ces 27 tests ont été relancés après le dernier contrôle de funding des créances
  en règlement : **27 passés**.
- **228 tests frontend passent** dans 29 fichiers ; build Vite réussi.
- La suite backend complète a été lancée une fois : **2 005 passés, 7 échecs,
  2 ignorés** avant les dernières corrections. Cinq échecs concernaient le
  booking historique sans organisation ; ils ont été corrigés puis validés
  dans les tests ciblés. La suite complète n'a pas été relancée après correction.
- Deux échecs restants ont été reproduits en rechargeant en mémoire le moteur
  PayScript de HEAD antérieur au CCR, y compris dans les processus enfants :
  `test_preview_edit_and_generation_share_exact_prompt[amc]` rejette le faux texte
  « Réponse » comme synthèse inexploitable ;
  `test_la_grille_de_stress_et_la_grille_2d_concordent` constate 0.459539 contre
  0.4597. Les fichiers de ces fonctions hors CCR n'ont pas été modifiés.
- Recette navigateur tentée avec une base synthétique séparée : refus de
  navigation du navigateur intégré. **Aucune validation visuelle revendiquée**.
  L'instance QA et son processus enfant ont été arrêtés, port libéré.

Commandes de reproduction, depuis la racine pour pytest :

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_ccr.py backend/tests/test_ccr_api.py backend/tests/test_rfq.py backend/tests/test_products.py backend/tests/test_chaine_pricing_booking_mtm.py -q
```

Depuis `frontend/` : `npm run build` (inclut les tests frontend).
Les journaux de session se trouvent dans `tmp/ccr-targeted-final.log`,
`tmp/ccr-backend-tests.log`, `tmp/ccr-baseline-check.log` et
`tmp/ccr-frontend-build.log` ; `tmp/` reste hors livraison Git.

## Limitations connues et V2

Les limitations suivantes sont substantielles et empêchent de présenter cette
V1 comme couvrant tous les produits et toutes les exigences du cahier des charges.

1. Projection FULL : GBM, taux/dividendes compatibles avec le MTF, même devise.
   Heston/SABR/Local Vol/LSV, courbes non supportées, taux stochastiques et forward
   start sont refusés pour le futur ; aucune substitution GBM silencieuse.
2. Pas d'agrégation économique multi-devises ni de simulation FX jointe. Une
   devise différente rend la métrique manquante, y compris pour la limite.
3. Pas de SA-CCR/EAD réglementaire, pas de calibration CDS, pas de modèle WWR
   joint, de DVA/FVA/MVA ni de moteur IM dynamique. Les alternatives proxy,
   régression et interpolation sont des valeurs de contrat refusées par l'API.
4. Appels VM sur grille de valorisation et IM fixe. Pas de simulation quotidienne
   exacte du défaut/MPOR, pas de liquidation d'actifs de collatéral, pas de calcul
   autonome complet de créances de collatéral hors contrat.
5. Pré-trade exige des entrées datées du strike égal à l'arrêté. Les nouveaux
   produits à strike passé/futur doivent passer par un contexte résiduel dédié.
   Stress de marché d'une créance pure en règlement non disponible.
6. Pas d'approbation à quatre yeux des dérogations ni de limite groupe effective.
   Le groupe du profil est descriptif. Pas de décision réglementaire configurable.
7. Le calcul est synchrone et borné ; absence de queue, cache de scénarios,
   démonstration de convergence et benchmark de charge institutionnel.
8. Le monitor ne détecte pas toutes les mutations possibles d'un même
   `ValuationRun`/nouveau MtM intrajournalier. Le recalcul final au booking est
   obligatoire. Pas de scheduler, alertes distribuées ou invalidation automatique
   exhaustive des résultats précédemment sauvegardés.
9. Une analyse rétrospective utilise les valorisations datées mais le périmètre
   et le référentiel juridique actuels ; la reconstruction temporelle complète
   des appartenances, résiliations et versions juridiques reste à développer.
   Le replay d'un calcul déjà sauvegardé conserve en revanche son périmètre figé.
10. Les courbes et listes complexes se saisissent en JSON validé. L'ergonomie
    finale et les parcours complets restent à recetter visuellement.

Priorités V2 : recette visuelle des six parcours demandés, convergence et
validation quant indépendante, historique effectif du référentiel, traitement
multi-devises et facteurs joints, maille journalière de collateral/MPOR,
support des autres modèles, puis approbations et limites groupe. Le SA-CCR
devra être un moteur réglementaire distinct et versionné, jamais une
réutilisation du PFE économique.

## Inventaire des fichiers

### Périmètre de recette UAT

Le sélecteur Production / Recette UAT est maintenant disponible dans l'écran
CCR. Recette sélectionne uniquement les deals portant `uat_batch_id`, avec un
filtre facultatif de lot et les mêmes filtres portefeuille, contrepartie, set
et deal. La sélection reste limitée à l'organisation de l'utilisateur. Les
référentiels juridique, crédit et limites restent communs : le mode Recette
n'est pas une copie de configuration et l'écran le précise.

Le moteur et les formules sont identiques. Les contrôles de limites sur un
lot/portefeuille UAT sont des simulations explicitement marquées ; ils ne
valident jamais un booking réel. Le contrôle final de booking conserve son
périmètre Production, imposé côté serveur. Les résultats UAT ne sont jamais
sélectionnés par le monitor Production, même lorsqu'ils sont plus récents.
Le monitor Recette affiche séparément les calculs complets UAT tous lots.

Les champs `data_scope` et `uat_batch_id` sont archivés dans les entrées JSON,
les résultats, l'audit et les exports ; les anciennes archives sans ce champ
sont interprétées comme Production. Aucune migration de table ni changement
des étiquettes UAT des deals existants.

Avant calcul, le diagnostic en lecture seule affiche les deals retenus,
ceux exclus par le périmètre, les valorisations manquantes et les dernières
dates disponibles. Les dates communes proposées tiennent compte du périmètre
historique à cette date, pour ne pas oublier un deal aujourd'hui rappelé.
Chaque ligne offre un lien facultatif vers le détail Booking. Le calcul CCR prépare désormais ses propres MtM ; il ne substitue jamais une ancienne valorisation à celle de la date choisie. Un périmètre vide est refusé explicitement
avant simulation et ne crée plus de calcul sauvegardé avec une exposition zéro.

Vérifications après ajout : **31 tests CCR ciblés passent**, dont quatre tests
nouveaux dans `test_ccr_scope.py` ; **228 tests frontend et build réussis**.
Lecture et calculs ponctuels de la base existante via connexion SQLite `mode=ro`,
sans persistance : BNP compte cinq deals UAT actifs à la date courante ; le deal
56, lot 20, au 16/09/2026 fournit une exposition et une PFE avec 32 scénarios
extérieurs / 32 trajectoires intérieures / 3 horizons. Ce contrôle valide le
parcours, pas la convergence statistique. Les quatre deals BNP du lot 20 au
16/09 ont des MtM disponibles, mais leur projection jointe est refusée pour
hypothèses de taux incompatibles. Leurs contextes de marché doivent être
harmonisés explicitement avant une projection agrégée.

Activation : redémarrer le backend existant pour charger les routes et contrats
mis à jour, puis recharger le frontend. L'instance existante n'a pas été arrêtée
ni remplacée pendant ce développement.

### Ajustement d'affichage après retour utilisateur

La vue CCR occupe désormais la hauteur disponible sous le bandeau de navigation.
Les onglets restent visibles ; résultats, monitor, trades et champs des fiches
défilent dans leurs panneaux. L'enregistrement reste accessible en pied de fiche.
Les grilles de champs et de métriques sont alignées et se réorganisent aux petites
largeurs. Les tableaux ont leurs propres défilements et en-têtes fixes ; les
résultats intégrés à Pricing/RFQ ont une hauteur bornée. Le comportement du shell
à hauteur fixe est activé uniquement pour la route CCR.

Validation : 228 tests frontend et build Vite réussis ; `git diff --check` sans
erreur. Le serveur existant sur le port 8000 a été conservé. Le navigateur
intégré refuse toujours sa navigation (`ERR_BLOCKED_BY_CLIENT`) : rendu visuel
non validé dans cette session. Aucun changement du moteur ni des API pour cet
ajustement.

La liste exhaustive des sources créées/modifiées et des bundles générés,
y compris les anciens bundles remplacés, est dans
[CCR_FILES_2026-09-28.md](CCR_FILES_2026-09-28.md).
Aucun commit ni push n'a été effectué.


## Calcul intégré des MtM et progression — CCR 1.2

Dans Exposition / CVA, **Calculer MtM et CCR** enchaîne la sélection du périmètre,
la préparation de chaque MtM, la projection jointe, l'agrégation, la CVA,
les limites et l'enregistrement. Le stress utilise le même parcours puis une
seconde projection. Aucun aller-retour vers Booking n'est requis pour valoriser.
Les événements NDJSON signalent les étapes réellement atteintes, les deals
traités, les échecs et les horizons MTF terminés ; aucune durée estimée n'est inventée.
Le worker dispose de sa propre session SQLModel ; une déconnexion ne constitue
pas une annulation du travail. Vérifier le monitor avant de relancer un flux interrompu.

`prepare_mtm=true` réutilise un contexte résiduel à la même date et version de
contrat si les versions de fixings concordent. Le prix est recalculé lorsque
les paramètres, la seed, le nombre de trajectoires ou l'empreinte du moteur
ont changé. En l'absence de contexte compatible, `deal_valuation.mtm_core`
construit le résiduel sur une copie détachée du deal. Les paramètres effectifs
sont ensuite appliqués par le moteur de valorisation existant. Un historique
manuel impose la reconstruction du passé même si un contexte existe.
La préparation ne crée aucun `ValuationRun`, ne change pas `latest_valuation_run_id`
et ne modifie ni les fixings, ni le statut, ni le snapshot du booking.
Les nouveaux MtM et leurs preuves sont conservés dans le dossier CCR.

Les choix sont visibles dans l'écran : date, devise, trajectoires MtM,
scénarios extérieurs/intérieurs, horizons demandés, seed, taux commun facultatif,
surcharges sigma/q par ticker et corrélations explicites. Les taux de l'interface
sont en pourcentage ; les champs JSON de surcharge sont en fractions.
Un taux commun remplace explicitement les courbes de taux par un taux plat.
Une surcharge q remplace explicitement la courbe de dividendes du facteur.
Sigma plat est réservé au GBM ; aucun changement implicite de modèle.
Les MtM CCR sont clean (funding émetteur nul). Sans surcharge, modèle,
volatilités et dividendes viennent du contexte figé ou du booking, sans
recalibration implicite. Ces paramètres ne sont pas présentés comme un marché
fraîchement calibré. Les incompatibilités entre deals restent bloquantes pour
la projection et peuvent être corrigées dans ce même panneau.

Historique : clôtures brutes manuelles explicites, sinon stockage local brut,
cache du fournisseur configuré, puis récupération externe seulement si la case
correspondante est cochée (désactivée par défaut). Les clôtures ajustées ne sont
jamais utilisées comme substitut. Le stockage AMC des tickers londoniens n'est
pas repris automatiquement, car sa conversion pence/livres diffère du contrat
raw du chargeur MtM. Dates, valeurs positives finies et couverture sont contrôlées ;
les historiques manuels incomplets ne déclenchent aucun fallback externe.
Les sources et historiques effectivement utilisés sont archivés avec empreinte.
Une donnée de cycle de vie manquante ou un modèle de projection non pris en charge
reste une erreur explicite, sans exclusion silencieuse du deal.

Les résultats affichent un tableau des hypothèses effectives par deal
(source, modèle, taux, volatilités et dividendes) et un détail défilant avec
corrélations, paramètres complets et provenance. Le dossier exporté inclut
les contextes, surcharges et historiques ; son rejeu utilise uniquement les
entrées figées. Les panneaux pré-trade Pricer/RFQ et le contrôle final de booking
conservent leur contrat existant (`prepare_mtm=false` par défaut API).

Validation : 37 tests CCR ciblés, dont calcul résiduel réel depuis une série
synthétique, réutilisation d'un MtM compatible, non-modification de Booking,
stream de progression, échec partiel, priorité au brut local et rejeu hors ligne.
Build frontend et ses 228 tests réussis. Contrôle BNP en lecture seule, lot UAT
20 au 16/09/2026 : les quatre MtM sont recalculés avec un taux explicitement fixé
à 3 % pour cette vérification ; la projection exige ensuite la corrélation
AAPL/MSFT manquante. Aucune hypothèse ni aucun résultat de ce contrôle n'a été
persisté dans la base réelle. Le rendu navigateur reste non validé, l'accès local
étant bloqué dans cette session. Redémarrer le backend existant et recharger
la page pour activer les changements ; aucune instance préexistante n'a été arrêtée.


### Fenêtre de résultats et taux harmonisé (retour utilisateur)

Le lancement ouvre automatiquement une fenêtre presque plein écran utilisant
`BaseModal` en mode fullscreen. Le périmètre et la progression restent en tête,
les résultats défilent dans le corps ; retour aux paramètres, rejeu et export
restent accessibles en pied. Le panneau de paramètres dispose désormais de toute
la hauteur de sa section. La fermeture ne perd pas le résultat et n'annule pas
le calcul ; un bouton permet de rouvrir la fenêtre. Le mode standard des autres
modales est conservé.

À la demande du desk, les nouveaux calculs avec préparation MtM harmonisent
automatiquement le taux à **3 %**, en attendant le raccordement des taux du jour.
Ce taux plat remplace les taux et courbes du booking pour le drift et
l'actualisation des deals préparés. Il est affiché avant et après calcul comme
`TEMPORARY_ASSUMPTION`, puis archivé avec les inputs. Une saisie différente reste
possible (`USER_OVERRIDE`), y compris zéro ; un champ vide revient à 3 %.
Le défaut est appliqué côté serveur à l'entrée du nouveau calcul, jamais pendant
le rejeu d'une archive, et ne modifie pas les snapshots officiels de Booking.
Le taux n'est pas présenté comme une observation de marché.

Un calcul FULL bloqué affiche désormais « projection incomplète / PFE indisponible »
et porte la méthodologie `NESTED_MONTE_CARLO_INCOMPLETE`, au lieu du libellé
incorrect « contrôle rapide ». Le taux commun retire le blocage dû aux anciens
taux différents ; les corrélations absentes et autres données manquantes restent
explicitement bloquantes. La PFE 95 % / 99 % est calculée lorsque la projection
jointe dispose de tous ses paramètres.

Validation : 40 tests CCR ciblés passent, dont harmonisation de deux deals bookés
à 1 % et 6 %, présence des PFE 95/99, surcharge à zéro et à 4 %, conservation du
booking et rejeu identique. Build frontend et ses 228 tests réussis. Validation
visuelle dans le navigateur toujours indisponible dans cette session.


### Marché commun pour les facteurs et les corrélations

Le seul taux commun ne suffisait pas : le calcul BNP n° 8 portait deux hypothèses
AAPL différentes (sigma 23,1 % / 24,2 % et q 0,6 % / 0,7 %), puis des corrélations
inter-produits manquantes. Le panneau principal active désormais par défaut
`common_market=true`, avec une case explicite pour revenir au mode de paramètres
figés. Les autres appels API conservent leur défaut existant.

Après préparation des résiduels, `common_market.py` charge une seule matrice
historique ajustée pour tous les tickers, en priorité dans le stockage local et
le cache. Le fournisseur configuré peut compléter les séries seulement si
`allow_market_fetch=true`. Le chargeur distingue les historiques ajustés pour
la calibration des clôtures brutes pour les fixings ; un historique manuel brut
ne sert jamais de substitut à une série statistique ajustée.

La calibration réutilise `calibration.realized_market` : 252 derniers rendements
communs disponibles, minimum 20, volatilité RMS annualisée sur 252 séances et
corrélation de Pearson. La correction numérique spectrale 1e-10 de cet estimateur
est explicitement mentionnée dans la provenance. Les surcharges de corrélation
sont validées ensuite sans réparation d'une matrice devenue invalide.
Ces volatilités réalisées ne sont pas présentées comme des volatilités implicites.
La fenêtre effective, le nombre de rendements, les sources, les valeurs calculées
et la matrice finale sont affichés et archivés.

Pour q, le booking le plus récent du périmètre fournit une hypothèse unique par
ticker (date de trade, puis identifiant pour départager), avec référence au deal.
Si le champ q n'existe pas dans ce snapshot, le contexte du deal fournit une
hypothèse étiquetée séparément. Ce n'est pas une nouvelle observation fournisseur.
Les surcharges manuelles sigma/q/corr restent prioritaires. Aucun modèle non-GBM
n'est converti implicitement, aucune courbe de dividendes n'est aplatie sans
surcharge q explicite et aucune différence contractuelle quanto n'est supprimée.

Tous les MtM sont recalculés sur ce marché commun avant la projection des PFE.
Les contextes initiaux restent conservés pour l'audit ; les snapshots Booking ne
changent pas. La matrice complète commune est transmise aux trajectoires jointes,
y compris pour les paires absentes des paniers individuels. Le rejeu utilise
uniquement les entrées archivées, sans recalibration ni accès fournisseur.
En cas d'échec du marché commun, les MtM initiaux restent visibles avec le motif,
et aucune PFE partielle n'est publiée.

Validation : 44 tests CCR ciblés passent, incluant cohérence AAPL multi-deals,
priorité des surcharges (dont q nul), indépendance de l'ordre des deals,
séparation brut/ajusté, matrices partagées, non-mutation des sources et rejeu.
Build frontend et ses 228 tests réussis. Contrôle du dossier BNP n° 8 en lecture
seule avec 32 scénarios extérieurs/intérieurs : cinq deals, historique commun du
06/10/2025 au 28/09/2026, 252 rendements, PFE95/PFE99 calculées sans erreur.
La CVA reste indisponible pour recouvrement/LGD inconnu, indépendamment des PFE.


Contrôle final du parcours `calculate(..., persist=False)` sur les cinq deals BNP
avec les paramètres du calcul n° 8 (256 scénarios extérieurs, 128 trajectoires
intérieures, 8 horizons demandés, 10 000 trajectoires MtM) : aucune erreur,
MtM net 4 544 617,30 EUR, PFE95 5 079 237,34 EUR et PFE99 5 136 140,89 EUR.
Connexion SQLite `mode=ro`, aucun dossier enregistré ni snapshot modifié.
Ces résultats valident le parcours sur ces paramètres et ne constituent pas
une étude de convergence. La propagation du stress de corrélation est également
vérifiée sur les paires inter-produits du marché commun : 5 tests du nouveau
fichier passent après ce contrôle, en complément des 44 tests CCR précédents.


### Aides contextuelles et formatage français

Des aides « ? » expliquent les champs de périmètre, simulation, marché et stress,
les fiches crédit/juridiques/collatéral/limites, ainsi que les métriques, colonnes
de résultats et contrôles pré-trade. Le dictionnaire `ccrHelp.js` centralise les
explications en cohérence avec les capacités réellement implémentées.
`HelpTip` est accessible au survol, au clic et au clavier ; son panneau est
positionné dans le viewport et se ferme au défilement pour ne pas rester détaché
de son champ.

Le formatage CCR utilise des espaces insécables visibles entre groupes de trois
chiffres et une virgule décimale : 5 079 237,34 pour un montant, 3,0 % pour un taux.
Les montants gardent deux décimales dans les cartes, tableaux et infobulles du
graphique. Les axes, compteurs et nombres de simulations sont également groupés.
Des aperçus formatés accompagnent les principales saisies numériques ; les valeurs
techniques des inputs et le JSON exporté ne sont pas transformés. Une donnée
absente reste un tiret et ne devient pas zéro.

Modification de présentation uniquement : aucun test backend relancé. Build
frontend et ses tests automatiques réussis. Vérification directe du formateur
pour montant positif/négatif, pourcentage, compteur et valeur absente. Recharger
le frontend pour voir les changements ; aucun redémarrage backend nécessaire.


Alignement des masques CCR : les paramètres de simulation et de marché partagent des lignes de grille distinctes pour libellés, champs et aides. Les aides numériques ne décalent plus les saisies voisines. Le bouton de calcul et le lien catalogue ont la hauteur des contrôles. La disposition des simulations passe sur deux colonnes sur écran étroit. Changement de présentation uniquement, validé par le build frontend.

### Réutilisation de la base MtM pour les stress

Le parcours `prepare_mtm=true` recherche désormais un dossier CCR compatible
avant de préparer les valorisations. Sa clé couvre l'entité, le périmètre, la date,
les deals, produits et versions de termes, tous les événements/fixings, le
fournisseur configuré, les hypothèses de marché, les historiques manuels, la seed,
le nombre de trajectoires MtM et les empreintes des moteurs de pricing et CCR.
Un dossier avec préparation incomplète ou échec du marché commun est exclu.

Les chocs, le multiplicateur crédit et le dimensionnement des projections futures
ne changent pas la base. Les MtM, contextes résiduels, historiques et calibration
commune sont alors réutilisés. Les projections PFE, valorisations sous choc,
agrégations et décisions sont recalculées avec les accords et limites courants.
Un stress crédit seul conserve le MtM de base, sans bruit Monte Carlo additionnel.
Cette optimisation ne met pas les PFE ou décisions de crédit en cache.

La politique est un marché figé jusqu'à actualisation explicite, et non une
détection automatique des nouvelles données intrajournalières. Le résultat et
la progression indiquent le dossier source et la date de constitution de la base.
La case « Recalculer la base MtM » (`refresh_mtm=true`) désactive la reprise du
dossier CCR et du contexte Booking ainsi que celle des historiques archivés CCR.
Les données locales restent prioritaires ; l'accès fournisseur doit être autorisé
si elles ne suffisent pas. Ces commandes sont accessibles dans l'onglet stress.

Pour les anciens dossiers sans clé de compatibilité, les MtM ne sont pas repris
aveuglément : les historiques archivés du même arrêté, entité et périmètre
peuvent alimenter une nouvelle préparation. Le brut et l'ajusté restent séparés,
les historiques manuels restent prioritaires et le dossier source est tracé.
Le diagnostic de périmètre précise qu'il compte les valorisations Booking : leur
absence ne signifie pas qu'aucune base CCR réutilisable n'existe.

Validation : 51 tests CCR ciblés réussis, dont 6 tests de cache (réutilisation,
invalidation, isolation, limites actualisées, rejeu, historiques hors ligne et
stress d'un payoff résiduel). Après renforcement du cas actif avec calibration
commune, les 6 tests de cache passent également. Build frontend et 228 tests
frontend réussis.

Reproduction exacte de la requête BNP du dossier n° 14 en SQLite `mode=ro`,
`persist=False`, avec tout téléchargement interdit : cinq deals UAT, taux 3 %,
256 scénarios extérieurs, 128 trajectoires intérieures, 8 horizons demandés,
10 000 trajectoires MtM ; spot -20 %, volatilité +10 points et crédit ×2.
Préparation depuis les historiques déjà archivés, aucune erreur de base ou de
stress. Exposition courante stressée : 3 521 868,95 EUR ; PFE95 stressée :
4 602 617,48 EUR ; PFE99 stressée : 4 780 801,34 EUR. La CVA reste indisponible
pour recouvrement/LGD inconnu. Aucun dossier ou snapshot réel modifié.

### Présentation des montants dans les cartes CCR

Les grandes cartes de résultat affichent désormais des montants arrondis à
l'euro, avec un espacement des milliers lisible et le symbole de devise. Les
valeurs sont alignées à droite ; le montant à deux décimales est disponible
au survol. Les tableaux détaillés et les données exportées conservent leur
précision. Les valeurs absentes restent des tirets. Build frontend et ses
228 tests validés ; aucun changement du moteur de calcul.

Le même format en euros entiers s'applique aux comparatifs base/stress et
avant/deal/après, aux limites, aux deals et aux ensembles de netting. La valeur
exacte à deux décimales reste disponible au survol et dans les données du
calcul. Dans le contrôle pré-trade et la fenêtre CCR, les tableaux ne possèdent
plus de défilement vertical indépendant. Leur défilement horizontal reste
disponible ; la molette suit le conteneur vertical du résultat. La synthèse de
progression demeure visible en haut de la fenêtre CCR lors du défilement.
Le build frontend et ses 228 tests ont été validés après ces changements.

### Contrôle du risque sur un deal déjà booké

Dans l'onglet Deal du Pricer, le contrôle CCR d'un deal rouvert transmet
maintenant son identifiant officiel, sa contrepartie, sa devise, son périmètre
Production/UAT et sa date de valorisation au moteur. Il ne crée plus une
proposition fictive reprenant le strike historique. Le moteur prépare le MtM
résiduel avec les fixings et le contexte du contrat booké, au taux provisoire
CCR de 3 %, puis calcule l'exposition courante et les PFE. Le netting set
booké est affiché en lecture seule. La réponse API du deal et l'état de la
réouverture conservent désormais explicitement `counterparty_id`,
`ccr_netting_set_id` et `uat_batch_id` : la recette ne peut pas être confondue
avec la production après réouverture.

Contrôle réel en lecture seule (`persist=False`, SQLite `mode=ro`) du deal UAT
actif #76 du 29/09/2026, nominal 720 000 EUR, contrepartie Société Générale :
calcul complet sans erreur, MtM CCR 500 172,48 EUR et PFE95 751 677,23 EUR
avec 64 scénarios extérieurs et 32 trajectoires intérieures. Il s'agit d'une
vérification de parcours, pas d'une étude de convergence. Le prix du Pricer
utilise un taux de 2,2 % et le CCR le taux commun provisoire de 3 % ; les deux
MtM peuvent donc différer. Le profil de crédit, la courbe de défaut et le
recouvrement sont absents : CVA/risque de perte au défaut non chiffrables.
Le build frontend et ses 228 tests passent après l'aiguillage du deal booké.
