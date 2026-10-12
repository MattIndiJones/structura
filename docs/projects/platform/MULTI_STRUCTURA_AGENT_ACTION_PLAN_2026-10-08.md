# Plan d'action — agents IA utilisateurs de plusieurs Structura

Date : 08/10/2026. Statut : cadrage initial, implémentation suivie dans le
[rapport de livraison du 09/10](MULTI_STRUCTURA_AGENT_IMPLEMENTATION_2026-10-09.md).
Branche de travail : `codex/desk-simulation-lab`.

## 1. Finalité et résultat attendu

Vérifier si Structura permet réellement à ses utilisateurs de préparer leurs
relations, structurer, négocier, traiter, suivre leurs clients et gérer la vie
des produits et les risques. Les agents doivent rencontrer les mêmes écrans,
droits, validations et difficultés que des utilisateurs de l'application.

La campagne produit des preuves des fonctions qui marchent, des bugs et des
fonctions absentes. Elle distingue le résultat commercial de la qualité de
l'application. Une conversation réussie ou un objectif commercial atteint ne
prouve pas que Structura fonctionne.

Ce plan remplace le premier plan de laboratoire comme référence de développement.
Le [flux RFQ natif entre entités](INTER_ENTITY_RFQ_BACKLOG_2026-10-08.md) reste un
chantier ultérieur. Les constats « actuels » ci-dessous décrivent l'état avant
développement ; se référer au rapport de livraison pour l'état exécuté.

## 2. Architecture retenue pour le développement

Un même code Structura est exécuté dans des instances locales distinctes pour
Hector et chaque banque. Chaque instance a sa base fictive, son identité, ses
secrets de session, ses fichiers métier, ses journaux et son port. Chaque agent
dispose d'un contexte navigateur séparé et d'un client HTTP authentifié propre.
Les données réelles de Philippe ne servent pas de base à cloner.

Les clients finaux ont une identité, des objectifs, une mémoire et une boîte de
messages propres. Hector utilise le véritable module Clients pour les gérer.
Un client professionnel utilisateur de Structura peut recevoir sa propre
instance ; l'absence actuelle d'un portail investisseur doit être qualifiée,
sans lui attribuer artificiellement des écrans de banque. Achille utilise la
supervision de recette et ne possède pas de book commercial.

Le banc de recette contient cinq éléments :

| Élément | Responsabilité |
|---|---|
| Instances Structura | Comptes, objets métier, calculs, contrats, exécutions et lifecycle |
| Agents IA | Lire, décider, agir avec leurs outils, vérifier, dialoguer et signaler |
| Messagerie | Conserver et distribuer les messages ; notifier le destinataire |
| Contrôleur de campagne | Démarrage, événements, horloge, budgets, reprise et conservation des preuves |
| Contrôles indépendants et Achille | Vérifier les résultats, expliquer les échecs et accompagner les utilisateurs |

Le contrôleur transporte les décisions ; il ne décide pas du prix ou de la
banque gagnante et ne remplit pas les books à la place des agents.

Les écritures métier des agents passent par les écrans ou les API publiques
authentifiées. Aucun appel direct à une fonction Python métier et aucune
insertion SQL ne remplacent un parcours utilisateur. Les fixtures techniques
et les lectures de preuve du banc restent identifiées séparément.

## 3. Points actuels vérifiés le 08/10

Lecture du code, sans lancement de serveur ni exécution de recette :

- `backend/app/db/database.py` : chemin de base fixe vers `backend/data/structura.db`.
- `backend/run.py` : lancement sur le port 8000 avec `reload=False`.
- `backend/app/api/auth.py` : inscription disponible seulement si
  `STRUCTURA_ALLOW_REGISTRATION` est activé ; le parcours crée ou rattache une
  entité sans processus complet d'admission d'organisation.
- `frontend/src/stores/auth.js` : session conservée dans le stockage local du
  navigateur ; il faut séparer les contextes de chaque acteur.
- `backend/app/api/ccr.py` et `backend/app/db/ccr_models.py` : configurations
  d'accords, CSA, sets, limites et collatéral disponibles ; leur intégration à
  chacun des scénarios et leur représentation dans les écrans restent à qualifier.
- `backend/app/services/llm/providers.py` : transport vers les fournisseurs IA
  présent ; cela ne constitue pas encore un agent capable d'utiliser le navigateur.
- RFQ, scheduler et lifecycle emploient des dates réelles : une horloge métier
  de recette doit atteindre leurs consommateurs concernés.

Une fonction présente dans le code n'est pas déclarée testée sur cette base.
Les capacités d'émission, de détention/revente de notes, de règlement et de
couverture OTC doivent être vérifiées avant de construire les scénarios associés.

## 4. Ordre de développement et critères de sortie

### Lot 0 — inventorier les parcours et fermer les choix techniques

Faire un essai manuel dans une instance fictive des parcours inscription,
contrats, Clients, Pricer, AO, booking et lifecycle. Pour chacun, relever ce qui
est disponible à l'écran, par API, absent ou incorrect, ainsi que les preuves.

Qualifier notamment le sens des positions selon chaque module, l'émetteur,
la contrepartie juridique, les opérations liées et les contrôles de crédit.
Choisir le pilote navigateur, le transport de messages et la configuration IA
après un essai court : navigation, calcul réel, lecture de résultat et réponse.
Mesurer latence, coût, erreurs et consommation mémoire ; le nombre d'agents
n'impose pas un modèle physique distinct chargé pour chacun.

**Sortie :** liste des tâches nécessaires dans Structura et dans le banc,
architecture de lancement arrêtée et premier scénario financièrement représentable.

### Lot 1 — créer plusieurs instances réellement isolées

Rendre les chemins de données et le port configurables ; inventorier aussi les
documents, clés, caches et processus annexes. Prévoir un manifeste de campagne,
la version du code et les adresses des instances. Partager seulement les données
de référence autorisées ; séparer les données privées et les fichiers modifiables.

Démarrer, vérifier, arrêter et reprendre uniquement les processus appartenant à
la campagne. La préparation technique crée des bases fictives et les moyens
d'administration ; elle ne précrée pas les comptes commerciaux testés.

**Sortie :** deux instances utilisables indépendamment, comptes et données sans
fuite, redémarrage conservant les données, arrêt libérant les ports.

### Lot 2 — rendre une IA capable d'utiliser Structura

Construire la boucle : observation autorisée → décision IA → action outil →
résultat réel → nouvelle observation. Fournir les actions navigateur usuelles
et les opérations HTTP authentifiées, avec description des droits et unités.

L'agent peut se tromper, demander de l'aide et reprendre. Les procédures métier
ne sont pas une séquence obligatoire de réponses rédigées à l'avance. Les prix,
fixings et preuves de booking proviennent de Structura. Les budgets de tours,
d'appels IA et de calcul empêchent une conversation infinie sans inventer un succès.

**Sortie :** Hector crée son compte par l'écran, se reconnecte, utilise un module
et vérifie son résultat. Une action API distincte est exécutée avec son identité.
Les preuves indiquent le canal utilisé et les éventuelles interventions humaines.

### Lot 3 — faire réellement dialoguer deux IA

Créer une boîte par agent, des messages au format mail, des fils et références
communes, les pièces jointes de recette et une notification du destinataire.
Conserver auteur, destinataire, date métier, date technique et contenu livré.

Le destinataire lit le message et choisit sa réponse. Gérer doublons, reprise,
absence de réponse et informations ambiguës. Une interruption ne doit pas
renvoyer silencieusement un ordre commercial déjà accepté. Les informations
internes d'une partie ne sont pas ajoutées au contexte de son interlocuteur.

**Sortie :** Hector et BNP échangent plusieurs messages de préparation de leur
relation et consultent chacun leur propre Structura. Les formulations et choix
proviennent de leurs IA. Les prix commerciaux attendent la préparation des
contrats au lot 4 ; la messagerie ne contourne pas cette précondition.

### Lot 4 — préparer les relations contractuelles dans Structura

Les agents constituent et vérifient les dossiers bilatéraux avant les premières
demandes de prix des relations utilisées. Ils identifient la documentation
applicable au produit, les dates, devises, limites et conditions de règlement.

Pour les scénarios OTC : accords, set de netting, CSA et paramètres de collatéral
applicables. Pour les notes : documentation d'émission/distribution et identité
de l'émetteur ; aucune application automatique d'un CSA au seul motif qu'il existe.

Les deux parties enregistrent leur vision du même accord et les incohérences
sont rapprochées. Une configuration CCR ne vaut pas, à elle seule, un workflow
de négociation/signature opérationnel : développer la fonction métier manquante
dans Structura si elle est nécessaire au scénario.

**Sortie :** relation BNP–Hector complète et cas CA–Hector incomplet visibles
dans leurs instances. Une restriction agit comme attendu ; les autres relations
continuent. Les tentatives négatives sont identifiées comme tests intentionnels.

### Lot 5 — traiter une opération commerciale complète

Hector crée Client, Contact, Mandat, Interaction et Opportunity pertinents.
Le client exprime son besoin ou répond à une proposition proactive d'Hector.
Les banques calculent, négocient et répondent ; Hector motive sa sélection,
y compris s'il choisit une banque plus chère. L'offre client et son acceptation
restent distinctes de l'accord avec la banque.

Chaque partie booke son opération après accord. Une référence de transaction
commune relie les identifiants locaux sans imposer des IDs de base identiques.
Garder l'instrument, l'émetteur, la version des termes, le prix traité, les
notionnels, devises et dates cohérents. Les calculs internes de prix et de MtM
peuvent différer ; ils ne modifient pas implicitement les termes exécutés.

Pour la distribution externe, les bookings BNP→Hector et Hector→BNP représentent
la même transaction ; la vente Hector→client en est une seconde. L'émission
propre et la couverture OTC constituent des scénarios distincts à développer
selon les lacunes constatées au lot 0. Un échec d'une jambe reste visible.

**Sortie :** une opération complète enregistrée par les agents et rapprochée,
sans double booking après reprise et sans contournement des contrôles métier.

### Lot 6 — intégrer la date virtuelle et le marché daté

Créer une horloge commune aux instances, avec départ et horizon configurables,
avancement vers le prochain événement et pause pendant les traitements requis.
Conserver le temps réel pour authentification, diagnostics et budgets d'exécution.
Les expirations commerciales utilisent le temps métier défini pour la campagne.

Un acteur peut attendre une réponse pendant que les autres agissent à la même
date. Le temps avance quand les actions nécessaires sont terminées ou qu'une
issue explicite d'attente/refus est enregistrée. Un délai simulé est un événement
prévu ; une lenteur de calcul ne fait pas expirer automatiquement une cotation.

Injecter uniquement les marchés connus à la date simulée, avec provenance,
fixings nus, devises et conventions de calendrier. Les scénarios synthétiques
sont étiquetés. L'absence de donnée historique ne devient pas un instantané actuel.

**Sortie :** mêmes dates métier dans les instances ; traitement long sans saut
de temps ; expiration et reprise correctes ; absence de données futures dans
les informations et calculs remis aux agents.

### Lot 7 — poursuivre lifecycle, clients, règlements et risques

Exercer observations, fixings, coupons, mémoire, rappel, maturité et paiements
sur des produits qualifiés. Distinguer flux dû et flux réglé. Suivre les positions
et créances encore vivantes à la fin de l'année. Mettre en place de vrais rôles
opérationnels distincts quand un contrôle quatre yeux le requiert.

Hector informe et relance les clients, explique les événements et propose un
réinvestissement. Les calculs de risque sont faits du point de vue de chaque
partie : notes, OTC, limites, netting, VM/IM, retards et contestations selon le
scénario. Ne pas présenter une mesure réglementaire absente comme disponible.

**Sortie :** au moins un événement de vie complet, ses flux et ses messages
client rapprochés ; cas contractuels et de crédit vérifiés sur leurs périmètres.

### Lot 8 — ajouter les acteurs, objectifs et campagne annuelle

Ajouter SG et des clients aux profils variés. Hector vise au moins 100 M€ de
ventes clients sur l'année ; BNP 15 %, CA 30 % et SG 40 % du volume bancaire
défini pour la campagne. Mesurer ventes clients une seule fois et distinguer
distribution, émission et couverture. Ces objectifs sont modifiables et non
bloquants ; ils ne garantissent pas une répartition de marché.

Associer des cas imposés à une exploration aléatoire reproductible. Les banques
peuvent refuser, perdre un AO, privilégier une marge ou adapter leur stratégie.
Des objectifs manqués ne déclenchent pas d'exécutions forcées.

**Sortie :** campagne annuelle avec couverture mesurée et bilan de tous les
acteurs. La cible d'une à deux heures est évaluée sur un nombre de demandes,
d'événements et de calculs annoncé, avec budget IA et concurrence contrôlée.

## 5. Achille et interface présents dès les premiers lots

Achille et la conservation des anomalies commencent au lot 2. L'interface
progresse dès le lot 1 et respecte le thème clair et les composants de Structura.

Vue de supervision prévue : date virtuelle et état de pause ; avatars et
activité des agents ; conversations ; accès aux vrais écrans de chaque instance ;
dossiers et rapprochements ; incidents ; couverture des tests ; objectifs commerciaux.
En préparation : acteurs, contrats à exercer, marchés, dates, modèles IA et budgets.
En exécution : pause, reprise, arrêt, détail d'une action et intervention tracée.
Au bilan : export des preuves, rejouer un incident et comparaison avant/après.

L'utilisateur doit pouvoir suivre : qui agit, ce qu'il voulait faire, l'action
réalisée dans Structura, le résultat et la difficulté rencontrée. Les avatars
sont accompagnés de noms et rôles. Un bilan vert exige les preuves applicables.

Achille utilise un catalogue versionné de capacités vérifiées. Il distingue bug
applicatif, mauvais usage, fonction absente, problème de données et incident du
banc. Ses procédures de coaching sont conservées, évaluées et privées par rôle
lorsqu'elles contiennent des informations commerciales. Il ne corrige pas le code
pendant une campagne ; une correction de Structura est suivie d'une nouvelle recette.

## 6. Vérifications et matrice de couverture

| Domaine | Cas à exercer |
|---|---|
| Comptes et accès | Inscription, doublon, connexion, session expirée, droits insuffisants, séparation des acteurs |
| Contrats | Relations complètes/incomplètes, dates, devises et produits hors périmètre, limites, CSA applicable ou absence autorisée |
| Clients | Besoin spontané, proposition proactive, modification/refus, mandat et préférence, rattachement au deal, relance lifecycle |
| Prix et AO | Paramètres et unités, hypothèses effectives, clarification, refus de coter, marge, validité, renégociation, choix plus cher justifié |
| Exécutions | Termes différents des termes acceptés, sens et montant, double clic/reprise, booking unilatéral, échec de la vente client |
| Vie et risques | Coupons, mémoire, barrières, rappel, maturité, flux impayé, positions, risque émetteur/OTC, netting, collatéral et limites |
| Robustesse | Message doublonné/perdu, résultat IA invalide, navigateur ou fournisseur indisponible, calcul long, crash et reprise |
| Utilisabilité | Action introuvable, erreur incompréhensible, unité ambiguë, saisie perdue, navigation, chargement, clavier et viewport étroit |

Les assertions sont fixées avant exécution, rattachées aux preuves et vérifiées
indépendamment des commentaires IA. Les prix de référence doivent être adaptés
au payoff ; recalculer avec le même moteur ne constitue pas un oracle indépendant.
Rapprocher les confirmations et flux entre parties ; ne pas imposer l'égalité
des valorisations internes quand leurs hypothèses diffèrent.

Rapporter séparément : réussite sans aide, après coaching, refus attendu, échec,
non exercé et capacité absente. Une API réussie ne qualifie pas l'écran. Une
campagne exploratoire seule ne garantit pas la couverture ; les cas imposés la
complètent. Le rejeu de décisions archivées vérifie une régression ; une nouvelle
discussion IA est une nouvelle exécution et peut produire d'autres décisions.

Chaque anomalie contient contexte, action, attendu/observé, version du code,
acteur, canal, objets concernés et preuves, sans secrets de session. Un échec
difficile à attribuer reste « à diagnostiquer », pas automatiquement un bug.

## 7. Premier résultat concret et façon de poursuivre

Première démonstration cible : Hector, BNP, CA, un client et Achille, période
courte à date fixe. Comptes créés par les acteurs, contrats préparés avant le
pricing, dialogue entre IA, demande client, prix calculé dans chaque Structura,
négociation libre, trois bookings locaux pour deux transactions et rapprochement.
Le scénario CA incomplet vérifie une restriction attendue sans arrêter les
autres acteurs. Les cas ISDA/CSA sont exercés avec un instrument auquel ils
s'appliquent ; ils ne sont pas artificiellement attachés à la seule note du pilote.

La première livraison exécutable couvre les lots 1 à 3 et prouve d'abord que
deux IA utilisent effectivement leurs instances et dialoguent. Le pilote métier
complet vient après les lots 4 et 5 et les fonctions Structura manquantes. La
date historique et l'année accélérée suivent les lots 6 à 8.

Développement incrémental sur la branche actuelle, avec documentation et preuves
à chaque lot. Tests backend ciblés uniquement, bases temporaires, build frontend
après modification Vue et recette des écrans concernés. Aucun commit ou push
sans instruction explicite dans le message courant. Aucun lancement persistant
d'instances sans suivi de leur identité et procédure d'arrêt.

Le passage au lot suivant dépend de preuves techniques ; un objectif commercial
manqué n'arrête jamais à lui seul la campagne. Un manque critique dans Structura
est un résultat du travail et une tâche priorisée, jamais un succès simulé.
