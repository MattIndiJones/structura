# Campagne de diagnostic Structura — pilote du 13/10/2026

Branche : `codex/hybrid-saas-foundation`, HEAD `7dce302` et modifications locales.
Campagne : `70ee3203fd42457a991a99a478932532`. État final : **STOPPED**.
Qualification du parcours métier : **BLOQUÉ avant création de la RFQ**.

## Résultat concret

Exécution réelle avec Qwen2.5-Coder 7B sur Ollama local, cinq installations privées
(Hector, BNP, Crédit Agricole, Société Générale, client) et supervision Achille.
Configuration : graine 42, début métier 13/10/2025, deux mois virtuels prévus,
objectif fictif de 20 000 000 €, tickets de 10 000 000 €, plafond de 120 tours et
surveillance limitée à vingt minutes réelles. Scénario contractuel `baseline`,
coaching actif. Ces paramètres ne constituent aucune facturation.

Le pilote a duré **740,97 secondes**, soit environ **12 min 21 s** : 39 tours,
45 appels modèle et 45 actions enregistrées, dont quatre actions en échec.
Le mois métier est resté à zéro ; une demande client reverse convertible a été
exprimée dans le pilote, sans Product ni RFQ persisté. Les cinq comptes agents
ont fini par être connectés. Les relations et le dossier CRM ont été créés.

Deux reprises de création RFQ ont reçu le même refus HTTP 422. La campagne a été
arrêtée sur ce blocage, avant répétition supplémentaire et avant l'année complète.
Les décisions commerciales des agents n'ont pas été remplacées par des résultats
imposés. Aucun code applicatif n'a été corrigé pendant cette campagne.

## Défauts constatés

| ID | Priorité | Constat et preuve | Qualification / suite |
| --- | --- | --- | --- |
| PILOT-01 | P1 | Les cinq bases acteurs contiennent zéro desk et zéro membership. L'outil `rfq` omet `pilot_desk_id`. Les deux POST `/api/rfq` sont refusés avec « Choisissez un desk pilote habilité pour votre organisation. » | Défaut du bootstrap et du raccordement du pilote aux RFQ actuelles. Le contrôle API fonctionne : il ne faut pas le contourner. Initialiser les desks/droits et transmettre le desk habilité. |
| PILOT-02 | P1 | Chaque tentative RFQ crée d'abord une opportunité. Deux POST `/api/opportunities` réussis, puis deux RFQ refusées. La base Hector conserve les opportunités 1 et 2 avec le même intitulé `CASE-001 — investissement` ; le pilote ne retient que l'ID 2. | Rejeu non idempotent de l'outil de simulation. Réutiliser l'opportunité liée au dossier et contrôler les prérequis avant une nouvelle écriture. |
| PILOT-03 | P2 | L'inscription d'Hector puis celle du client échouent avec `Page.evaluate: Execution context was destroyed, most likely because of a navigation`. Les comptes sont ensuite récupérés et les cinq agents finissent connectés. | Course entre navigation/rechargement et lecture de la session dans le pilote Playwright. Synchroniser la navigation, lire la session et reprendre le compte sans réinscription en double. |
| PILOT-04 | P2 | Les quatre actions en échec ne conservent dans `model` que `seconds` ; les autres métadonnées de la décision IA sont perdues, y compris lorsque c'est l'API qui rejette l'action. | Provenance des refus incomplète, conforme au point SIM-04 déjà ouvert. Garder les métadonnées de décision obtenues avant l'échec de l'outil. |
| PILOT-05 | P2 | 34,41 s entre la demande d'arrêt et l'état final STOPPED. Le modèle avait une décision en cours. Les cinq installations ont ensuite quitté. | Durée réellement observée sur une campagne active. Diagnostic à approfondir entre décision en cours et fermeture séquentielle des acteurs ; ne pas annoncer un arrêt instantané. |

Les quatre incidents natifs ont été annotés dans le registre avec qualification
`HARNESS`, statut `OPEN` et diagnostic. Les quatre PATCH ont réussi. Une action
en échec n'est pas comptée automatiquement comme un bug du moteur métier.

## Vérification des données et couverture

Lecture SQLite en mode lecture seule après arrêt : dans les cinq bases, **zéro
RFQ, cotation, Product, Deal, exécution, événement de deal et valorisation**.
Hector conserve un client et les deux opportunités citées ; les autres acteurs
ne possèdent aucune opportunité. Aucun booking ni flux financier n'a été réalisé.

| Périmètre | Résultat de cette campagne |
| --- | --- |
| Démarrage des acteurs / inscription | Exercé ; deux incidents de navigation récupérés |
| Relations et CRM | Exercés ; pas une qualification exhaustive |
| Création RFQ | Bloquée par les desks et le payload du pilote |
| Pricing, réponses bancaires, acceptation, confirmation, booking | Non exercés |
| Fixings, flux, maturité, MtM, risque produit et CCR | Non exercés |
| RFQ natif entre installations | Toujours déclaré `DEFERRED` par le pilote |
| Profils Front / Opérations / Contrôleur et six organisations manuelles | Pas qualifiés par cette simulation |

La période de deux mois ne démontre de toute façon pas le paiement final des
produits de six mois créés par l'outil actuel. Après réparation du pilote, prévoir
une recette dirigée jusqu'aux échéances, puis qualifier l'autonomie séparément.
L'année complète reste non lancée.

## Arrêt et preuves conservées

Les cinq ports acteurs **64399, 64414, 64423, 64432, 64444** sont libérés, les PIDs
serveurs et leurs lanceurs sont absents. Le contrôleur n'est plus actif.
Les services Admin 8000 et plateforme 8100 créés pour ce pilote ont été arrêtés
en parallèle en **4,27 s**, avec sortie des deux serveurs et libération des ports.
La vérification finale ne trouve aucun de ces sept services actif.
Ollama, préexistant, et le lanceur graphique ouvert précédemment ne sont pas arrêtés.

Les six installations d'essais manuels n'ont pas été démarrées pour la campagne.
Les bases acteurs restent conservées et séparées dans :

`.runtime/hybrid-saas/admin-workbench/campaigns/70ee3203fd42457a991a99a478932532/`

Preuves locales : `campaign.json`, `pilot-export.json`, `pilot-audit.json`,
`pilot-db-summary.json`, `pilot-before-stop.json`, `pilot-stop-reason.json`,
`pilot-services-stop.json`, captures d'écran et journaux propres à chaque acteur.
La configuration, le HEAD et les empreintes de sources du pilote sont conservés.
Les mots de passe, sessions et secrets de contrôle restent privés et exclus du Git.

## Recette à reprendre après les corrections

1. Rejouer ce pilote avec les mêmes paramètres dans une nouvelle campagne isolée.
2. Vérifier les desks/droits, la reprise de connexion et l'absence de nouveaux doublons.
3. Qualifier la provenance des refus et mesurer l'arrêt pendant une décision IA.
4. Exercer les contrôles RFQ prioritaires et le parcours acceptation/confirmation/booking.
5. Démontrer le cycle jusqu'au paiement final avant de lancer l'année complète.

Les suites de tests sont restées suspendues ; aucune suite backend ou frontend
n'a été relancée. Aucune correction du code métier, aucun commit, push ou merge.
Le script de surveillance ponctuel se trouve uniquement dans le runtime ignoré.

## Corrections du pilote après autorisation

Les cinq constats ci-dessus restent les résultats de la campagne arrêtée.
Les corrections suivantes sont implémentées, **sans nouveau lancement ni
qualification en exécution** :

| Constat | Correction livrée dans le code | Reste à vérifier |
| --- | --- | --- |
| PILOT-01 | Bootstrap reproductible par les API publiques : deux desks par acteur, compte de préparation dans son organisation privée, habilitations auditées et desk pilote explicite. L'outil RFQ relit ses droits avant toute création d'opportunité et transmet `pilot_desk_id`, le client, le mandat et l'opportunité. | Inscription puis création RFQ effective dans une nouvelle campagne. |
| PILOT-02 | Réutilisation de l'opportunité enregistrée ; rapprochement par référence stable de campagne/dossier si la réponse du POST a été perdue. Réutilisation de la RFQ liée, refus des doublons ambigus et des objets qui ne correspondent plus au dossier. | Rejeu après refus API et interruption entre écriture native et sauvegarde. Les deux anciennes opportunités restent conservées comme preuves. |
| PILOT-03 | Attente du chargement complet après connexion/inscription, marqueur de compte créé conservé avant la navigation, reprise de la session de l'onglet et contrôle de l'identité attendue. | Connexion, réinscription partiellement terminée et reprise après un échec de préparation. |
| PILOT-04 | Modèle, durée et compteurs de tokens reçus conservés lors des erreurs d'outil ou de validation de la réponse IA ; distinction décision/outil. Les valeurs indisponibles ne sont pas inventées. | Vérifier un refus API et une réponse IA invalide dans le journal/export. |
| PILOT-05 | Attente HTTP Ollama annulable par le contrôleur, arrêt des installations privées actives en parallèle et délai de fermeture Uvicorn de cinq secondes pour les acteurs. Une décision annulée n'est pas exécutée et ne devient pas un incident métier. | Mesurer l'arrêt réel pendant une décision IA et une action native. Une action HTTP métier déjà engagée peut encore attendre son propre délai ; aucun arrêt instantané garanti. |

Les acteurs banque et émetteur reçoivent les neuf droits RFQ existants dans leurs
desks de simulation ; le client reçoit uniquement `read`. Les droits sont sans
expiration automatique dans ces environnements fictifs et restent révocables.
Le marqueur de bootstrap empêche une reconnexion de rétablir des rôles ou droits
révoqués. Le compte de préparation n'obtient aucun membership RFQ et reste dans
la base privée de son acteur ; il n'est pas un compte d'accès central aux books.

Les bases et preuves de campagne sont conservées jusqu'à une suppression ou
remise à zéro explicite. Les nouveaux fichiers d'identifiants et de bootstrap
restent dans le runtime ignoré. Aucune base manuelle ou historique n'a été
modifiée pendant ces corrections. Le registre RFQ central et le transport RFQ
natif entre installations restent à raccorder et qualifier ; ce lot ne les
déclare pas livrés.

Vérifications limitées à la syntaxe Python et aux espaces du diff. Les suites de
tests et les campagnes restent suspendues. Les incidents du pilote restent
`OPEN` jusqu'au rejeu avec preuves. Aucun commit, push ou merge.
