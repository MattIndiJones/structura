# Recette par utilisateurs IA — livraison et preuves

Développement des 08–09/10/2026, sur `codex/desk-simulation-lab`, à partir de
`c44efdd`. Travail local, sans commit ni push. Ce document donne l'état exécuté
du [plan multi-Structura](MULTI_STRUCTURA_AGENT_ACTION_PLAN_2026-10-08.md).

## Utiliser l'interface

Dans Structura : **Accueil → Recette par utilisateurs IA**,
`/#/agent-workshop`, accessible avec le compte utilisateur habituel. Les campagnes
sont privées à leur propriétaire. L'entrée **Administration → Recette par
utilisateurs IA**, `/#/admin/agent-workshop`, reste disponible aux administrateurs.
Le frontend de production est compilé dans
`frontend/dist`. Redémarrer le backend habituel pour charger les nouvelles routes.

1. Choisir le modèle local installé, la date initiale, la durée, le ticket,
   les objectifs et la graine. Le défaut commence un an avant la date réelle.
2. Choisir les contrats : BNP/SG documentés et CA incomplet, toutes les banques
   documentées, ou tirage reproductible par banque. Le tirage peut ne laisser
   aucune banque éligible ; les refus sont alors un résultat de partie valide.
3. Créer la campagne et **Démarrer les IA**. L'inscription intervient dans les
   vrais écrans ; les banques et Hector administrent ensuite leur documentation.
4. Lire Vue d'ensemble, Conversations, Actions et preuves, Books et risques,
   Bugs et améliorations.
   Cliquer une action pour voir son résultat, ses appels HTTP et sa capture,
   lorsqu'elle est disponible. Les refus et erreurs restent dans les preuves.
5. Pause/Reprendre suspend la partie entre actions. Arrêter ferme les instances
   privées. Une campagne arrêtée peut redémarrer avec ses données ; une campagne
   terminée est conservée et ne rejoue pas silencieusement ses opérations.

### Reprise du suivi visuel du 09/10 au matin

Après le retour de Philippe (« je ne sais pas ce qui se passe ni si les IA
utilisent l'application »), l'interface a été reprise : **Vue d'ensemble**
est l'entrée par défaut. Le bloc **Maintenant** distingue préparation des
installations, réflexion du modèle, exécution de la décision, appel HTTP en
traitement, pause, fermeture et fin de campagne. La durée réelle est distincte
de la date du jeu, qui reste suspendue. Le contrôleur publie la décision avant
son exécution et la requête avant de recevoir la réponse native ; le journal
conserve aussi les heures réelles et la durée totale des nouvelles actions.

Le parcours affiché se déduit des comptes, relations, besoins, réponses aux AO,
accords, quatre écritures et revues des books effectivement enregistrés.
Une relation PENDING reste signalée comme incomplète, même si le parcours
contractuel du scénario a été réalisé. Un refus terminal ne devient pas un
booking réussi. Le dossier courant ou un dossier historique peut être suivi.

Les actions portent désormais des libellés métier et leurs résultats lisibles.
**Actions et preuves** montre les appels natifs et leurs statuts HTTP, les
identifiants de deal et les captures réellement disponibles. L'interface
compte séparément parcours écran, actions API et échanges internes. Une
inscription peut comporter à la fois écran et vérification API ; les compteurs
ne constituent donc pas des catégories exclusives. Aucune capture d'écran
n'est inventée pour une action API. Les attentes sont consultables dans le
journal et peuvent être incluses dans le flux de la vue d'ensemble.

La liste des campagnes est synchronisée avec le dernier état publié. Un état
RUNNING enregistré ne suffit plus à annoncer une activité : le thread local
ou le verrou OS du contrôleur externe est vérifié. Si aucun contrôleur n'est
actif, l'interface propose une reprise et indique **Exécution non confirmée**.
Si elle ne reçoit plus de réponse depuis 15 secondes, elle signale que
l'activité actuelle n'est pas confirmée. La configuration d'une nouvelle
campagne est repliée pour donner la priorité au suivi. Les cartes acteurs
montrent leur dernière action et permettent d'en ouvrir directement la preuve.

Qualification de cette reprise : **24 tests backend workshop**, **366 tests
frontend et build Vite**, vérification navigateur des états terminée, réflexion,
exécution avec requête en attente, pause, absence de contrôleur, perte de suivi,
filtrage, preuve HTTP, formulaire et largeur 390 px. Cette recette d'affichage
intercepte les API avec des fixtures explicites et relit les actions de l'année
conservée ; elle ne compte pas comme une nouvelle campagne commerciale.
`scripts/check_workshop_observability_ui.py` sert le bundle via un serveur
statique temporaire fermé en fin de test, sans mutation d'une installation réelle.

Une courte recette **avec le vrai modèle IA** a aussi créé des comptes vierges
par les écrans et enregistré une relation native avec ISDA/CSA. Les phases
PREPARING, THINKING, EXECUTING et une requête native en attente ont été observées
avant la réponse. Campagne privée `7fe92452cdda4f69821e7003a7b7b5f2`, arrêtée
volontairement après le premier contrat, quatre ports vérifiés fermés.
Preuve : `output/agent-workshop-ui/live-activity-ea1a826ab1b34e29b31cfb2035f8a9da/visibility-proof.json`.
Ce contrôle limité ne rejoue pas l'année ni les scénarios de crédit non exercés.

Captures : `output/agent-workshop-ui/observability-completed-desktop.png`,
`observability-live-desktop.png`, `observability-mobile.png`. La capture live
illustre une fixture d'affichage ; la preuve du modèle réel est distincte.
Relancer le backend habituel pour charger les nouveaux champs de suivi,
puis recharger la page. Les historiques anciens restent consultables sans
réinventer les horodatages ou détails d'activité qu'ils n'avaient pas enregistrés.

Les installations des acteurs sont ouvertes seulement pendant une partie.
Le lien « Ouvrir son Structura » mène à son écran de connexion. Les identifiants
de l'agent sont dans son fichier privé `agent_credentials.json` ; ils ne sont
pas inclus dans les exports. Les captures et journaux permettent aussi
d'inspecter ses actions depuis la supervision.

### Aides de lecture et registre des problèmes — 09/10

Des aides **?**, accessibles au survol, au clic et au clavier, expliquent les
champs de configuration, commandes, onglets, compteurs et étapes du parcours.
Elles précisent notamment la différence entre mois virtuels et temps réel,
la graine de marché/contrats et les décisions IA non déterministes, le volume
client compté seulement après quatre écritures rapprochées, et les relations
enregistrées qui restent PENDING. « Comptes utilisés » décrit un fait historique,
sans prétendre que leurs installations fermées sont encore connectées.

Le bouton permanent **Voir les problèmes (N)** et le compteur cliquable
**Points à examiner** ouvrent directement le registre. Les onglets Conversations,
Actions et preuves, Books et risques et Bugs et améliorations affichent leur
contenu immédiatement ; la supervision et les cartes acteurs restent dans
Vue d'ensemble. Le registre classe les observations en appels Structura à
diagnostiquer, erreurs IA/usage, problèmes du pilote, bugs signalés par une IA,
améliorations/fonctions manquantes et autres points. Cette classification est
une aide de lecture des traces, pas une validation humaine ni un statut de
correction enregistré dans le backend.

Chaque fiche conserve le message original, l'acteur, la source, la date du jeu,
la décision et l'action liée lorsqu'elle peut être retrouvée. Elle indique
quoi vérifier avant de corriger. **Voir l'action et sa preuve** ouvre le reçu,
les appels HTTP ou la capture associés. **Télécharger les signalements** exporte
toutes les fiches de la campagne en texte, avec les arguments et réponses
conservés ; les filtres d'affichage ne réduisent pas cet export.

La campagne visible sur la capture de Philippe,
`6b0197fc9f0f439e9ade308c88f268ec`, contient 12 signalements : cinq échecs de
messagerie vers des destinataires inexistants, quatre réponses d'erreur natives
(un reçu de pricing invalide et trois appels à une route introuvable), et trois
problèmes du pilote/pauses. Ces 12 observations ne sont pas 12 bugs Structura
confirmés. Elles restent intactes, sans modification des historiques ni des
contrats ou deals. Les corrections de ces problèmes ne sont pas réalisées
par cette reprise de l'aide et du registre.

Validation : six tests de lecture/classification/export supplémentaires,
**372 tests frontend et build Vite**. Recette navigateur sur le journal conservé
avec API interceptées : ouverture des 12 fiches, filtre de quatre appels natifs,
lien vers la preuve HTTP 404, export texte complet, aides de champ et clavier,
largeur 390 px. Aucun appel d'écriture à une installation réelle, aucune nouvelle
campagne IA lancée, aucun pytest backend nécessaire pour cette modification
frontend. Recharger la page pour utiliser les nouvelles aides.

### Nettoyer la vue et recommencer les essais — 09/10

Quatre commandes permettent de se retrouver dans les campagnes accumulées :

- **Réinitialiser la vue** revient à Vue d'ensemble, enlève le filtre acteur,
  ferme la preuve et replie le formulaire, sans modifier la campagne.
- **Réinitialiser les champs**, dans Nouvelle campagne, remet les valeurs
  par défaut du formulaire. Cela ne crée ni ne modifie un essai existant.
- **Recommencer la campagne** demande confirmation, retire l'ancien essai et
  crée une nouvelle référence DRAFT aux mêmes paramètres : zéro décision,
  aucune inscription, contrat ou écriture repris. Les installations seront
  recréées lorsque Philippe cliquera Démarrer les IA.
- **Supprimer la campagne** demande confirmation et retire cet essai de la
  liste. La vue sélectionne le prochain essai disponible ou affiche le
  formulaire vide lorsqu'il n'en reste plus.

Le nombre d'essais et leurs références courtes sont affichés dans la liste.
Recommencer et Supprimer exigent un contrôleur arrêté, même en pause ou en
cours de fermeture. Un verrou distinct sous `_locks/` sérialise les démarrages
et ces opérations entre processus ; le verrou actif de la campagne est aussi
vérifié côté serveur. Les installations survivantes après un crash sont
fermées uniquement via leur identité et leur secret de contrôle existants.
Si leur fermeture ne réussit pas, l'opération est refusée.

La suppression est une mise à l'écart récupérable : le dossier complet de
l'ancien essai (bases privées, traces et captures incluses) est déplacé sous
`backend/data/agent_workshop/_archive/<ancien-id>-<suffixe>/`. Il disparaît de
l'API de consultation. Aucune purge définitive ni restauration via l'interface
n'est ajoutée. La base principale de Structura n'est pas concernée. En cas
d'échec d'écriture de la nouvelle campagne, l'ancien dossier est remis en place.
Un cache de contrôleur ne peut pas ressusciter une campagne retirée par un
autre processus. Les règles de propriétaire et d'interdiction du pilotage
depuis une installation acteur s'appliquent aux nouvelles routes POST reset et DELETE.

Validation : **36 tests backend ciblés** (workshop et gestion des campagnes),
**372 tests frontend et build Vite**, recette navigateur contre les vraies
routes de gestion avec données temporaires : filtres/champs, annulation,
reprise vierge, refus sur verrou actif, suppression du dernier essai, sauvegarde,
confirmation et largeur 390 px. Script :
`scripts/check_workshop_management_ui.py`. Aucun modèle IA ni backend privé
lancé ; aucune campagne de Philippe supprimée ou réinitialisée par la recette.
Captures : `output/agent-workshop-ui/management-reset-desktop.png` et
`management-delete-mobile.png`. Redémarrer le backend habituel pour charger
les routes de gestion, puis recharger la page avec Ctrl+F5.

Le module métier réutilisable **Relations et exécutions** est accessible depuis
l'accueil, rubrique Life Cycle, à `/#/trading`. Le booking normal
**Pricer → Deal** comporte l'option « Inscrire une exécution de note dans le
journal des relations », avec relation, émetteur et références communes.

### Prérequis

Ollama local sur `127.0.0.1:11434`, avec un modèle installé. Le modèle employé
dans les campagnes exécutées est `qwen2.5-coder:7b`, déjà présent sur ce poste.
Le modèle 14b a aussi été essayé : ses décisions prenaient souvent 19–60 s,
contre quelques secondes pour le 7b, avec variation selon le contexte et la charge.

Playwright et Chromium sont nécessaires aux parcours navigateur :

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m playwright install chromium
```

Pour lancer sans interface, depuis la racine :

```powershell
.venv/Scripts/python.exe scripts/run_agent_workshop.py --months 12 --deadline-minutes 120
.venv/Scripts/python.exe scripts/run_agent_workshop.py --months 1 --without-sg --contract-scenario all_complete
.venv/Scripts/python.exe scripts/run_agent_workshop.py --resume <identifiant>
```

## Ce qui est développé

### Des utilisateurs et des installations distincts

Hector, BNP, CA, SG et Élodie disposent chacun d'un backend Structura, d'une base
SQLite fictive, d'un compte, d'un contexte navigateur, d'une session HTTP et
de fichiers privés. Achille supervise sans book commercial. Chaque décision
provient réellement d'un appel au modèle ; les réponses commerciales, marges,
choix de banque, justifications et acceptations ne sont pas des réponses rédigées
à l'avance. Les outils limitent les opérations disponibles selon les droits
et les tâches courantes, comme des contrôles activés dans un écran.

Les opérations guidées regroupent des appels aux **API publiques authentifiées**
de Structura. Elles facilitent un usage autonome ; elles ne démontrent pas
à elles seules une navigation libre de bout en bout dans les formulaires.
L'inscription est systématiquement faite par l'écran. L'agent dispose aussi
des actions navigateur lire/ouvrir/cliquer/saisir, et peut explorer les API.
Le modèle local utilisé décide sur du texte et sur le DOM ; les captures
sont des preuves pour l'utilisateur, pas une qualification de vision IA.

La préparation technique peuple les catalogues fictifs et confère aux comptes
banques/émetteur le rôle natif requis pour administrer les contrats, via
l'API d'administration. Elle ne précrée pas leurs comptes commerciaux.
Les boîtes de messages sont privées dans le contexte de décision ; le superviseur
humain voit les échanges dans la page de recette.
Les installations acteurs ont aussi leur propre racine de campagnes et refusent
toutes les routes de supervision : un numéro de compte identique ne donne aucun
accès au contexte du contrôleur.

### Les parcours métier

- Relations de notes versionnées et auditées : état, dates, documentation,
  devise, limite brute, autorisations et règlement. Une note n'est pas ajoutée
  artificiellement à un netting set OTC.
- ISDA, CSA et netting sets dans le vrai module CCR, séparés des notes.
  Une relation existante peut être complétée ; une reprise ne duplique pas
  ses accords déjà enregistrés.
- Hector utilise Clients, Contacts, Mandats, Interactions et Opportunités.
  Les idées de structures sont enregistrées dans le CRM et adressées au client
  comme idées non cotées. Le client exprime son propre besoin et reste libre
  de sa décision. L'opportunité porte le mandat ; la vente client est reliée
  à cette opportunité et déclenche son passage natif en `partially_won`.
  L'achat externe n'est pas ajouté au portefeuille du client.
- Banques : calcul dans leur Pricer, marge choisie par l'IA, cotation ferme ou
  refus motivé. Hector : comparaison, proposition client, accord, sélection
  conservée dans sa RFQ native. Un prix plus élevé est autorisé avec justification.
- Quatre écritures sur deux transactions : banque SELL/Hector BUY,
  Hector SELL/client BUY. Chaque Deal est lié à son Product canonique et utilise
  le reçu de pricing de son installation. Contrôle des termes immuables,
  émetteur, nominal, devise, dates, sens et prix entre les deux books.
- Journal natif idempotent, contrôle du stock avant revente externe, émission
  de notes par notre entité, preuves fictives de règlement et positions par
  instrument/émetteur. Une preuve DVP ne déclenche aucun paiement bancaire.
- Lecture du book, fixings synthétiques déclarés par le workflow normal
  d'exception manuelle, replay des événements, MtM résiduel et fermeture après
  paiement. Hector consigne son suivi dans le CRM et adresse un message au client.
- CCR natif sur un **call OTC hypothétique** dans son périmètre ISDA/CSA,
  avec spread, recovery et position initiale de collatéral explicitement déclarés.
  Ce calcul n'est pas présenté comme le risque de crédit des notes ou comme
  une couverture OTC réellement traitée.

### Horloge, contrôles et conservation

L'horloge est fixe pendant les décisions, appels réseau, calculs et parcours
utilisateur. Elle avance de mois en mois après une opération rapprochée et ses
revues/règlements, ou après un refus commercial terminal. La revue native
traite les événements contractuels déjà atteints. Il ne s'agit pas encore
d'un ordonnanceur intrajournalier suivant chaque coupon à sa date exacte.

Les objectifs commerciaux ne conditionnent pas la fin de période. Les erreurs
techniques répétées, opérations incomplètes et budgets dépassés restent visibles
et peuvent conduire à une pause de diagnostic. Le contrôleur n'invente pas
un trade pour atteindre l'objectif. Les boucles de confirmation sont bornées.
Achille lit les capacités OpenAPI réellement disponibles et les signatures
des outils, puis conseille les utilisateurs ; ses conseils restent des réponses IA.
Il reçoit aussi les idées commerciales avec leur PayScript pour en examiner
les explications. Un signalement IA reste une hypothèse à examiner, même s'il
est classé BUG par son auteur ; il ne constitue pas une anomalie prouvée.

Les campagnes persistent sous `backend/data/agent_workshop/<id>/`, non versionné :
état, décisions, messages, incidents, captures, fichiers de pricing, bases des
acteurs et journaux serveur. Les reprises enregistrent des empreintes des
sources. Les secrets de connexion, signature et contrôle restent privés.
Un verrou de campagne évite deux contrôleurs simultanés sur les mêmes données.
Les commandes de l'interface atteignent aussi une campagne lancée par le CLI.

Le marché est **synthétique**, commun aux parties et identifié comme tel.
L'accès à une date postérieure à l'horloge est refusé ; aucun fixing synthétique
n'est rebaptisé Yahoo. Une campagne historique réelle reste à qualifier.

## Qualification exécutée

### Parcours HTTP/navigateur indépendants des décisions IA

Ces scripts utilisent les API et écrans normaux avec des choix explicites de
recette. Ils qualifient les adaptateurs ; leur succès ne remplace pas une
campagne autonome d'agents.

| Parcours | Résultat et preuves locales |
|---|---|
| Reverse convertible : inscription, contrats, refus CA, prix, quatre books, DVP, MtM, maturité et paiement | Réussi ; campagne `ae616de0db2f46a6a9d72e55f9d6e301`, sous `%TEMP%/structura-adapter-check-53s4628r/agent_workshop/` |
| Reverse convertible avec vente client liée au mandat et à l'opportunité CRM, conversion native `partially_won`, puis mêmes contrôles de maturité/paiement | Réussi ; `09f2e76a2f4443398967a63425b73d15`, sous `%TEMP%/structura-adapter-check-9kxnytf6/agent_workshop/` |
| Phoenix : mêmes contrôles, événements et remboursement | Réussi ; `3cf1ae2aec50420eb981ceb212a3429c`, sous `%TEMP%/structura-adapter-check-_wplvkwb/agent_workshop/` |
| Phoenix avec SG plus chère que BNP, justification dans la RFQ, quatre books, contrat NOTE puis ajout ISDA/CSA puis répétition sans doublon | Réussi ; `adc91605f4ef466ea089d57e20106a2d`, sous `%TEMP%/structura-adapter-check-ajg5eoi3/agent_workshop/` |
| Émission Hector par les écrans Relations → Pricer → Deal → journal → règlement | Réussi ; `bcfc23a6db55410080994fdfc4aec0c9`, sous `%TEMP%/structura-trading-ui-y9siyj2b/agent_workshop/` ; émission 1 M€, position émetteur −1 M€, cash restant nul |

Commandes de reproduction :

```powershell
.venv/Scripts/python.exe scripts/check_agent_workshop.py --template reverse_convertible
.venv/Scripts/python.exe scripts/check_agent_workshop.py --template phoenix --with-sg
.venv/Scripts/python.exe scripts/check_trading_ui.py
```

Les scripts créent et ferment leurs propres instances. Le script d'inspection
de la supervision utilise un coordinateur explicitement isolé sur 8054.
Il ne faut pas le pointer vers une installation réelle pour ses fixtures.

### Campagnes IA

Campagne annuelle conservée : `33a784216f0e4cf58bd48d33b3ce0347`.
Pilote « toutes les banques documentées » : `86ae49978e384434ad7e767b7084d5df`.
Pilote tiré au sort, aucune banque éligible : `b80e908a95694041a87659fede4d5c22`.
Nouvelle année lancée depuis les écrans avec comptes vierges :
`4181bbaf4ef7481dbc2131ed1f253236` (12 mois, graine 42, budget par défaut 800).
L'année de diagnostic a **terminé** le 08/10/2026 virtuel : 12 opérations,
**120 M€ clients**, 48 écritures natives et 12 rapprochements COMPLETE.
Hector détient 24 deals, BNP 12 et le client 12. Les revues finales des trois
books sont enregistrées. Durée cumulée d'exécution : **68 min 9 s**, 593 décisions
et 618 appels IA, avec correctifs/reprises de développement et huit incidents
conservés. Il ne s'agit donc pas d'une année passée sans assistance au banc.
BNP a gagné 100 % du volume, CA et SG 0 % : ces résultats n'ont pas empêché la fin
de la simulation. Six produits sont échus, un est en règlement à la date finale
et cinq restent actifs ; leur maturité dépasse encore l'horloge.
Toutes les instances de cette campagne sont fermées.

La nouvelle année a aussi **terminé**, du 09/10/2025 au 09/10/2026 virtuels :
**120 M€**, 12 opérations, 48 écritures, tous les rapprochements COMPLETE,
**57 min 25 s** d'exécution cumulée, 504 décisions et 560 appels au modèle.
Elle n'a nécessité **aucune pause, reprise ni intervention humaine sur les décisions**.
Achille a conseillé les agents pendant la partie. Les traces comptent 558 actions
SUCCESS, deux refus EXPECTED_REFUSAL et **zéro FAILED**. Quatre signalements AGENT
sont conservés : CA sur sa documentation volontairement incomplète, deux
IMPROVEMENT et un USAGE d'Hector sur ses explications des risques, dont un doublon.
Ces signalements ne sont pas des bugs techniques confirmés.

Les douze ventes d'Hector sont reliées aux douze opportunités CRM natives,
toutes en `partially_won` ; les achats externes n'ajoutent pas ce lien client.
Les trois books ont leur revue finale. Six produits sont échus, un en règlement
et cinq actifs. BNP a remporté le volume ; les objectifs CA/SG manqués sont restés
non bloquants. Les processus acteurs sont fermés.

Les quatre campagnes terminées de référence ont ensuite été rattachées au compte
**Philippe, id 3, rôle user**, pour qu'il puisse les consulter depuis l'accueil.
Le champ `reference_handover` conserve leur propriétaire technique d'origine
et la date de mise à disposition. Seuls ce rattachement et leurs titres ont changé ;
les décisions, prix, deals et journaux de partie sont conservés. La base réelle
et les droits du compte Philippe n'ont pas été modifiés.

La recette finale UI a vérifié ce profil utilisateur, les quatre références,
les douze lignes COMPLETE de l'année autonome, les 120 M€, l'export des preuves
et l'absence d'erreur JS/débordement à 390 px. Captures et export :
`output/agent-workshop-ui/final-autonomous-desktop.png`,
`final-autonomous-mobile.png` et `final-autonomous-export.json`.

Le pilote documenté a terminé sa période et sa revue finale : 10 M€, une
opération, quatre books rapprochés, 49 décisions et un incident historique
conservé. BNP et CA ont administré leurs ISDA/CSA et calculé leur prix ; Hector
a sélectionné BNP. Le pilote tiré au sort (graine 7, sans SG) a aussi terminé :
26 décisions, zéro volume, zéro incident ; les deux banques ont refusé le cas
documentairement inéligible. `NO_TRADE` est son résultat attendu.

Les campagnes de diagnostic précédentes sont aussi conservées : attentes
circulaires, mauvaises signatures d'outil et coaching ayant proposé une API
absente. Elles ont servi à corriger le contexte et le banc ; elles ne sont
pas comptées comme des campagnes réussies. Les reprises annuelles ont reçu
des correctifs du contrôleur et des instructions, sans choix manuel de banque,
de marge ou d'acceptation, ni insertion manuelle de deal.

### Tests ciblés et corrections observées

272 cas backend ciblés ont passé sur leurs dernières exécutions pertinentes :
20 workshop, 81 contrôles de workflow et 171 RFQ/booking/lifecycle/fixings/CCR.
Le build frontend exécute 357 tests sur 50 fichiers et compile le bundle Vite.
La suite backend complète n'a pas été lancée.

Deux erreurs natives du cycle de vie ont été reproduites puis corrigées :

1. Le rafraîchissement pouvait rouvrir un fixing officiel saisi par un utilisateur
   lorsque la donnée fournisseur était absente. La décision officielle est
   désormais préservée avant le traitement de l'absence fournisseur.
2. La maturité manuelle comparait un temps arrondi à quatre décimales avec la
   durée précise du Deal : un produit atteint pouvait rester actif. La résolution
   s'appuie désormais sur la date contractuelle de maturité.

La recette UI a aussi révélé et corrigé la course entre sélection manuelle
d'une campagne et sélection automatique au chargement, ainsi que le débordement
du bandeau de navigation sur mobile. Création/démarrage/arrêt par écran et
pause/reprise d'une campagne CLI depuis l'interface ont réussi ; l'horloge
et le compteur d'actions sont restés fixes pendant la pause, sans erreur JS.
Le parcours Accueil → Recette avec un compte de rôle `user` a aussi réussi :
création, démarrage puis arrêt, instances fermées et administration refusée.
Cette recette utilise un contrôleur séparé sur 8055 ; le compte réel Philippe
conserve son rôle et sa base.

La campagne a révélé un verrou de lecture Windows transitoire sur les fichiers
de preuves : l'écriture atomique utilise désormais des fichiers temporaires
distincts et une reprise bornée de deux secondes. Elle a aussi révélé une boucle
de risque BNP alors que SG restait à revoir : les choix de contrepartie de l'outil
de recette ne proposent désormais que les revues restant à faire ce jour.

Le lien de la vente à l'opportunité CRM a été complété après neuf opérations
annuelles : les anciennes preuves gardent leur état initial, sans migration
silencieuse. Un parcours natif dédié vérifie la conversion commerciale et le
mandat sur les nouveaux bookings. Le passage de minuit Europe/Paris pendant
pytest a nécessité de corriger une fixture de fixing qui fabriquait un horodatage
futur ; le refus de cet horodatage par l'application était correct.
La date initiale de la page de recette utilise aussi le calendrier local plutôt
qu'une conversion UTC, et ramène le 29 février au 28 février de l'année précédente.

## Ce qui n'est pas encore démontré

- Une couverture exhaustive de Structura : seuls les parcours et familles
  effectivement exercés sont qualifiés. Les agents peuvent encore se tromper
  dans leurs raisonnements et leurs explications commerciales.
- Une campagne IA d'émission propre Hector ou de couverture OTC réellement bookée :
  l'émission propre est qualifiée par le parcours UI indépendant ; la campagne
  commerciale principale distribue des notes achetées aux banques.
- Défaut émetteur/contrepartie, appels de marge, disputes, transfert de collatéral,
  réinvestissement, marchés historiques réels, portefeuille multi-devises et
  tous les payoffs. Ces lignes restent explicitement non exercées.
- Précision quantitative de production du calcul CCR de recette : 32 simulations
  externes/internes servent à éprouver le workflow. Les avertissements natifs
  sont conservés ; EAD/SA-CCR non disponible reste nul au sens « absent », pas zéro.
- Accès autonome exclusivement par écrans, email externe ou protocole inter-entités
  de production. Les messages actuels sont internes ; le
  [réseau RFQ natif](INTER_ENTITY_RFQ_BACKLOG_2026-10-08.md) reste différé.
- Déploiement distribué ou plusieurs workers d'un même backend de trading :
  le parcours qualifié lance un worker par instance locale.

La base réelle `backend/data/structura.db` a été exclue de tous ces tests.
Son empreinte initiale SHA-256 est
`F31251FBDDE23654B96AB80399CF8455628AE84908D2BF4CAE50E1A48B03E895`.
La vérification finale retrouve exactement cette empreinte. La lecture des
comptes destinée à préparer l'accès de Philippe s'est faite en SQLite `mode=ro`.
Les coordinateurs de recette 8054/8055 sont arrêtés ; aucun processus
`backend/run.py` lancé pour ces tests ne reste actif. Les 63 ports distincts
enregistrés dans les campagnes locales sont libres, et aucun manifeste ne
signale encore d'instance active. Ollama préexistant sur 11434 a été conservé.

Pour utiliser le résultat, relancer normalement `lancer_structura.bat`, se
connecter avec Philippe et ouvrir **Accueil → Recette par utilisateurs IA**.
La référence « Année autonome — 120 M€ en 57 minutes » est déjà conservée.
