# Structura — reprise du socle SaaS hybride

Date : 13/10/2026, Europe/Berlin.

Statut : décisions et plan d'action validés dans la conversation avec Philippe ;
complément RFQ central intégré le 13/10/2026. La règle tarifaire reste une proposition
à valider avant activation de la facturation.
Le nouveau socle décrit ici n'est pas encore implémenté. Ce document accompagne
la livraison de la branche `codex/rfq-network-lot-0` vers `main` et prépare un
nouveau chat dédié à cette évolution.

## 1. Décisions à conserver

- Structura évolue vers un modèle SaaS hybride : portail commun, **base et
  traitements métier privés dans l'infrastructure de chaque organisation**,
  et registre central des échanges RFQ autorisés pour facturation et litiges.
- Chaque organisation possède son propre service Structura et sa propre base.
  Une infrastructure privée dans le cloud du client convient également.
- Les moteurs, API métier, calculs, jobs, documents internes et historiques privés
  restent chez le client. Le serveur central ne doit pas devenir un proxy recevant
  en clair les books, prix théoriques privés ou paramètres de calcul pour les traiter.
- Le portail central gère les accès à la plateforme, l'annuaire des installations,
  les abonnements et la distribution des versions. Il conserve également un
  **registre métier RFQ**, au périmètre explicite, distinct des journaux techniques.
- Les données quittent une installation uniquement selon un échange autorisé,
  notamment une demande RFQ, une cotation publiée ou une confirmation de traitement.
  Ces éléments d'échange sont aussi conservés chez Structura ; l'exception est
  documentée dans le périmètre du service, ses habilitations et sa conservation.
- Le navigateur accède au service de son organisation par un canal authentifié ;
  la base SQL du client n'est pas directement exposée sur Internet. L'installation
  métier doit contrôler elle-même les droits et les actions demandées.
- Les données actuelles sont fictives et peuvent être supprimées. **Aucune
  migration ni conservation historique obligatoire.** Le nettoyage doit rester
  limité aux données Structura identifiées ; les autres travaux et répertoires
  de la machine restent hors périmètre.
- Les questions de compilation commerciale, de protection contre l'analyse du
  programme et de calcul confidentiel sont différées. Ne pas les ajouter au
  premier chantier.
- Réutiliser le code existant : `Product`, moteurs, masques, référentiels et
  transport RFQ. Ne pas créer une variante métier de Structura par organisation.

## 2. Organisations de développement

Créer six installations fictives sur le poste de développement. Il s'agit de
six bases et de six services isolés, pas de six lignes dans une base métier commune.

| Organisation | Fonction dans le scénario |
| --- | --- |
| BNP Paribas | Banque fournisseur / répondant RFQ |
| Société Générale | Banque fournisseur / répondant RFQ |
| Citi | Banque fournisseur / répondant RFQ |
| UBS | Banque fournisseur / répondant RFQ |
| Leonteq | Institution distributrice / demandeur RFQ |
| Kepler Cheuvreux Solutions | Institution distributrice / demandeur RFQ |

Ces rôles servent au scénario de développement. Les capacités métier d'une
organisation doivent rester configurables : elles ne se déduisent pas de son nom.

Chaque installation isole sa base, ses documents, ses calculs, ses journaux,
ses identités, ses sessions et ses clés. Les identifiants locaux peuvent différer.
Un acteur présent dans un référentiel de contreparties n'est pas un compte utilisateur
et ne donne aucun accès à son installation.

Les bases et services des simulations sont encore distincts de ces six installations.
Les comptes d'agents sont créés par la simulation au lancement ; ne pas les créer
dans les bases destinées aux essais manuels.

## 3. Comptes et droits

L'accès métier principal doit être simple : **un super utilisateur par organisation**.
Il utilise l'application dans son entièreté au sein de son organisation, gère
les utilisateurs/desks/habilitations de ce périmètre et accède aux dossiers selon
les règles de confidentialité applicables. Le travail ordinaire ne doit pas
obliger à changer de profil à chaque étape.

Pour tester les permissions et préparer l'avenir, conserver les comptes secondaires :

| Compte dans chaque organisation | Profils / usage |
| --- | --- |
| Super utilisateur | Toutes les fonctions métier de son organisation et administration locale |
| Front | Sales, Structuration/Pricing, Risques/Consultation |
| Opérations | Préparation des opérations, booking et cycle de vie selon droits |
| Contrôleur | Contrôle et validations indépendantes selon la politique du parcours |

Cible : **4 comptes par organisation, soit 24 comptes locaux, et 1 admin central**.
Ces 25 comptes ne comprennent pas les comptes techniques éventuels ni ceux des
simulations. Toute identité technique supplémentaire doit être documentée et
limitée à sa fonction ; ne pas ajouter des comptes de démonstration silencieusement.

Prévoir Pricing et Opérations côté banques, Sales et Opérations côté distributeurs,
en réutilisant les desks et habilitations RFQ existants. Les profils sont des
ensembles de permissions ; ne pas modifier silencieusement un rôle persistant
pour simuler une bascule de session.

Le super utilisateur ne désactive pas les règles métier : termes figés, validité
des prix, confirmation du traitement, unicité du booking, contrôles de calendrier,
fixings et historique contractuel restent appliqués. Pour les cotations RFQ,
la validation par le même utilisateur habilité est le réglage initial ; la seconde
validation reste configurable. Une validation indépendante obligatoire requiert
une identité distincte, même si Philippe incarne les deux comptes pendant ses essais.

Les dossiers appartiennent à l'organisation. Leur créateur reste enregistré pour
l'audit ; il ne doit pas empêcher un collègue habilité de poursuivre le dossier.
Vérifier les consommateurs encore limités au créateur : créer des comptes ne
suffit pas à rendre tous les modules collectifs.

## 4. Accès rapides et changement de contexte

La page de login de développement présente sept cartes : quatre banques, deux
distributeurs et Admin Structura. Chaque carte métier ouvre le super utilisateur
par défaut ; les profils secondaires restent disponibles pour une recette précise.

Dans l'en-tête, afficher toujours l'organisation, le profil et l'identité actifs.
Le sélecteur développeur permet une bascule sans ressaisir les identifiants,
avec retour au super utilisateur et retour Admin.

- Conserver le dossier ouvert si le nouveau contexte peut le consulter ; sinon
  revenir à son accueil. Ne pas transporter un identifiant local de dossier vers
  une autre installation comme s'il désignait le même objet.
- Traiter les saisies non enregistrées avant la bascule.
- Recharger le contexte et éviter les données conservées d'un utilisateur précédent.
- Prévoir des sessions indépendantes entre onglets pour travailler, par exemple,
  sur Leonteq et BNP côte à côte.
- Contrôler l'installation et les permissions côté serveur, y compris en cas
  de modification manuelle d'une URL ou d'un identifiant d'organisation.
- Réserver les raccourcis privilégiés au mode développeur activé explicitement
  côté serveur. Ne pas livrer de mots de passe de test dans le frontend de production.
- Réutiliser les composants et styles actuels : écrans bornés à la fenêtre,
  scroll interne des contenus et modales, aucun allongement infini de la page.
- Afficher les nombres avec séparateurs de milliers, par exemple `1 000 000 EUR`.

Le portail local de développement prépare l'architecture SaaS ; sa présence
ne doit pas être présentée comme un déploiement SaaS de production déjà qualifié.

## 5. Admin et simulation

### Développement

L'admin développeur peut superviser et consulter les six installations fictives,
ouvrir un contexte métier de test et diagnostiquer les configurations et erreurs.
Conserver dans l'audit l'identité métier effective et l'origine développeur
lorsque l'admin ouvre cette session. La bascule n'accorde pas aux comptes métier
les pouvoirs de l'admin central.

### Production

L'admin central supervise techniquement les installations et la plateforme.
Il dispose aussi d'une vue habilitée sur le registre RFQ central, pour facturation
et instruction des litiges. Cet accès, ses consultations et ses exports sont tracés.
L'accès aux autres données métier privées du client exige une autorisation limitée
et tracée. Ne pas construire un accès permanent implicite de Structura à tous les books.
Le super utilisateur local reste limité à son organisation.

### Simulation avec agents

L'accès est **réservé à l'admin** dans les menus, routes et toutes les API : liste,
création, lancement, pause, reprise, arrêt, reset, consultation, export, captures
et diagnostic. Un utilisateur métier ne doit pas accéder au pilotage via une URL
directe. Dans un contexte métier de test, le pilotage reste inaccessible.

La simulation initialise ses propres utilisateurs et installations. Préserver
la compatibilité de son bootstrap lors du remplacement de l'initialisation
générique `Demo/admin/test`. Elle ne remplit pas les books des essais manuels.

## 6. Registre central RFQ, facturation et litiges

Philippe veut consulter les RFQ chez Structura pour facturer leur utilisation
et vérifier ce qui a été échangé en cas de litige. Cette décision remplace
l'hypothèse d'un stockage central exclusivement technique. Elle n'autorise pas
la centralisation des books ou du pricing privé.

### Périmètre de données

| Conservé dans le registre central | Conservé uniquement dans l'installation du client, sauf transfert distinct autorisé |
| --- | --- |
| Organisations demandeuse et destinataires, installations et références d'échange | CRM, identité du client final et documents internes |
| Demande envoyée : projection contractuelle Product figée, version et empreinte | Brouillons, recherches et versions internes non envoyées |
| Cotations commerciales publiées : valeur, convention, validité, révisions et retraits | Prix théoriques privés, hypothèses, modèles, calibrations, calculs et marges |
| Messages, accusés de réception et horodatages des événements d'échange | Historiques internes sans rapport avec cet échange |
| Acceptation, confirmation, références d'exécution et statut de booking communiqué | Positions et détail du booking, portefeuille, MtM, risques et P&L |
| Événements facturables, règle/version appliquée et statut de facturation | Autres données privées de l'organisation |

Conserver les contenus contractuels effectivement envoyés et les réponses
effectivement publiées, pas uniquement leurs empreintes. Inclure notamment nominal,
devise, sous-jacents, payoff/script contractuel, paramètres contractuels, calendrier,
conventions de prix, conditions de validité et confirmations nécessaires à la
reconstitution de l'échange. Ne pas copier le dossier Product complet avec ses
calculs ou blocs privés : réutiliser la projection d'échange appropriée.

Ne pas ajouter l'identité nominative du client final à cette projection par défaut.
Un identifiant de dossier interne peut servir au rapprochement sans transfert du CRM.
Les identités des intervenants nécessaires à la traçabilité font partie du périmètre
à documenter et à habiliter.

### Traçabilité et synchronisation

- Identifier sans ambiguïté l'organisation, l'installation, le dossier, le tour,
  la version des termes et chaque message ; un identifiant numérique local seul
  ne suffit pas pour rapprocher plusieurs installations.
- Conserver l'auteur, l'instant métier et l'instant de réception centrale,
  les contenus figés, empreintes, accusés et éléments d'authentification disponibles.
- Ajouter les révisions, retraits et corrections à l'historique ; ne pas écraser
  une version déjà échangée. Ne pas modifier une cotation depuis la console centrale.
- Prévoir une collecte durable avec reprise et dédoublonnage, en réutilisant
  les mécanismes de transport et d'outbox pertinents. Documenter les états en
  attente de synchronisation, rapprochés ou en écart entre les parties.
- Une réception centrale ne signifie pas automatiquement livraison à la banque,
  acceptation de la cotation ou booking : conserver ces faits et leurs preuves séparément.
- Une interruption centrale ne doit pas perdre les événements déjà conservés
  localement. Définir explicitement le comportement du parcours et de la facturation
  pendant l'interruption ; ne pas inventer un succès ou une unité à facturer.
- Les preuves de recette locales, le registre central et les traces techniques
  ont des fonctions distinctes. Un code HTTP 200 ou une empreinte seule ne suffit
  pas à instruire un litige sur le contenu accepté.

Le registre permet de reconstituer les faits techniques ; la portée probatoire,
les obligations de conservation et les modalités contractuelles du service sont
à définir pour le pilote. Ne pas présenter un accusé HMAC comme une signature
électronique qualifiée ou une garantie automatique de non-répudiation.

### Écrans et droits

Créer une vue centrale de recherche, chronologie et export du dossier d'échange,
avec suivi de facturation. Les accès sont limités à leur finalité et journalisés.

- Le demandeur consulte ses demandes et les réponses qui lui sont destinées.
- Une banque consulte les demandes qui lui sont adressées et ses propres réponses.
  Elle ne lit pas les cotations de ses concurrentes.
- L'admin central habilité consulte les échanges nécessaires à la facturation
  et aux litiges ; cela n'ouvre pas les bases privées des clients.
- Les consultations et exports sensibles sont eux-mêmes auditables.

Définir explicitement les informations collectées, les personnes habilitées,
les finalités, les sauvegardes, la durée de conservation et les règles de purge
ou de suspension de purge d'un dossier litigieux. Pour les données personnelles,
tenir compte de la [finalité et de la durée nécessaire à leur conservation](https://www.cnil.fr/fr/passer-laction/les-durees-de-conservation-des-donnees).
Ne pas fixer une durée réglementaire arbitraire dans le code.

### Règle de facturation proposée, à valider

Proposition initiale : **un tour RFQ effectivement livré à au moins une banque
constitue une unité facturable pour l'organisation demandeuse**, quel que soit
le nombre de banques sollicitées dans ce tour. Un nouveau tour constitue une
nouvelle unité. Cette règle est une proposition commerciale, pas un tarif déjà acté.

- Aucun supplément dû aux reprises réseau, doublons, accusés répétés ou révisions
  des réponses à ce tour.
- Une demande non livrée ne constitue pas cette unité ; identifier le fait de
  livraison attesté qui déclenche le comptage.
- Exclure explicitement les simulations, bases de recette et environnements de
  développement de toute facturation réelle, sans se fier à un préfixe de nom.
- La saisie manuelle seule ne satisfait pas ce déclencheur ; toute autre tarification
  de l'usage manuel serait une règle commerciale distincte.
- Conserver le contrat/règle tarifaire et leur version, le fait déclencheur et
  une clé stable d'unicité. Rejouer un événement ne refacture pas le même tour.
- Ne pas activer une émission de factures réelles, fixer un montant ou débiter
  un client avant validation de l'unité, du tarif et des règles commerciales.

La tarification par banque consultée reste une alternative à arbitrer si nécessaire.

## 7. Relations RFQ à initialiser

| Demandeur | BNP | Société Générale | Citi | UBS |
| --- | --- | --- | --- | --- |
| Leonteq | Autorisé | Autorisé | Interdit | Autorisé |
| Kepler Cheuvreux | Autorisé | Interdit | Autorisé | Autorisé |

Configurer les reconnaissances bilatérales, rapprochements juridiques locaux,
accords fictifs de traitement et canaux de transport cohérents. Déclarer explicitement
les produits, devises, bornes de nominal et politiques de publication. EUR/CHF
constitue le périmètre initial proposé ; documenter les valeurs effectivement retenues.
La documentation fictive doit être identifiable comme telle.

Conserver le parcours livré : Product figé dans le tour, réception par desk,
prise en charge bancaire, pricing privé avec les moteurs actuels, prix commercial
validé puis publié, retour automatique, retrait/révision, confirmation avant booking,
reprise des livraisons et prévention des doublons. La saisie manuelle coexiste avec
les cotations réseau. Ne pas substituer le prototype RFQ navigateur au transport réel.

## 8. Plan de réalisation

| Étape | Travail | Critère de sortie |
| --- | --- | --- |
| 1. Installations | Six services avec leurs répertoires, bases, identités et paramètres isolés ; socle central distinguant annuaire et futur registre RFQ | Démarrage indépendant, aucune lecture croisée des données privées |
| 2. Initialisation et droits | Six organisations, super utilisateurs, comptes secondaires, desks et permissions ; remplacer les seeds génériques | Initialisation reproductible et idempotente, sans doublons ni comptes cachés |
| 3. Remise à zéro | Retirer les anciens jeux fictifs identifiés, créer les bases avec schéma complet et seuls les référentiels/configurations ; invalider les anciennes sessions | Zéro dossier métier, calcul conservé, portefeuille, étude ou campagne active |
| 4. Accès commun | Sept cartes de login, sélecteur de contexte, sessions par onglet, nettoyage des états précédents | Leonteq et BNP côte à côte, changement de profil fiable et scroll interne |
| 5. Supervision et partage | Admin développeur, droits locaux, travail collectif des utilisateurs habilités ; simulation admin seulement | Dossier poursuivi par un collègue habilité, refus direct des accès interdits |
| 6. RFQ entre bases | Relations autorisées, accords de test, appairage et canaux ; préserver le manuel | RFQ Leonteq vers BNP, prix privé puis publié revenant au demandeur, traitement et bookings locaux |
| 7. Registre RFQ central | Collecte des demandes et réponses échangées, accusés, états et confirmations ; chronologie admin, export litige et comptage simulé | Échange reconstituable, aucun calcul privé exporté, aucun doublon de comptage et refus des accès concurrents |
| 8. Qualification et exploitation | Parcours des autres modules, vue d'état, reset métier préservant comptes/configuration, reprise centrale et mise à jour de l'atlas | Résultats et écarts explicites, environnement réinitialisable et exploitable |

Commencer par les étapes 1 et 2. Les accès rapides seront la première livraison
visible. Préparer l'initialisation avant d'effacer les jeux actuels pour éviter
une base sans parcours exploitable. Aucun besoin d'archiver ou de migrer les anciens
dossiers ; la suppression doit néanmoins cibler des chemins contrôlés.

Le pilote chez un véritable client et l'hébergement effectif du SaaS suivent cette
qualification locale : connectivité, authentification, mises à jour compatibles,
sauvegardes/restaurations côté client et moteur de base supporté sont à qualifier.
Ne pas annoncer la connexion à n'importe quelle base existante : Structura requiert
son propre schéma, et les imports d'autres systèmes sont un sujet distinct.

## 9. État du code à reprendre et documentation

Les lots RFQ 0 à 8 sont présents dans la branche livrée ; le nouveau socle hybride,
les six installations permanentes, les super utilisateurs, les accès rapides
et le registre central RFQ ne le sont pas. Ne pas recommencer les lots RFQ.

Références à lire après `CLAUDE.md` et `docs/README.md` :

- [Atlas de l'application et des comptes](../projects/platform/STRUCTURA_APPLICATION_OVERVIEW_2026-10-13.md)
  et [présentation HTML](../projects/platform/application-map-2026-10-13/index.html).
- [Plan RFQ](../projects/platform/RFQ_NETWORK_ACTION_PLAN_2026-10-12.md),
  [spécification lot 0](../projects/platform/RFQ_NETWORK_LOT_0_SPECIFICATION_2026-10-12.md)
  et [spécification lot 1](../projects/platform/RFQ_NETWORK_LOT_1_SPECIFICATION_2026-10-12.md).
- [Transport entre installations](../projects/platform/RFQ_NETWORK_LOT_6_IMPLEMENTATION_2026-10-12.md),
  [confirmation et booking](../projects/platform/RFQ_NETWORK_LOT_7_IMPLEMENTATION_2026-10-12.md),
  [recette lot 8](../projects/platform/RFQ_NETWORK_LOT_8_ACCEPTANCE_2026-10-13.md)
  et [procédure d'exploitation](../projects/platform/RFQ_NETWORK_OPERATIONS_2026-10-12.md).
- [Organisations et accès](../projects/platform/ORGANIZATION_ACCESS_DESIGN_2026-09-24.md)
  et [ancien cadrage on-premise](../projects/platform/DEPLOIEMENT_ONPREM.md).
  Le présent document fixe la cible plus récente ; les constats des anciennes
  notes doivent être vérifiés dans le code.
- [Dossier canonique Product](../projects/platform/PLAN_IMPLEMENTATION_OBJET_PRODUCT.md).

Points connus à vérifier, sans les présenter comme une photographie éternelle :

- La configuration d'instance utilise `STRUCTURA_DATA_DIR`; l'engine de base est
  défini au démarrage dans `backend/app/db/database.py`.
- Le bootstrap courant crée `Demo`, `admin` et `test`. Les instances de simulation
  s'appuient sur cette initialisation : une modification nécessite une compatibilité
  explicite pour elles.
- La route utilisateur `/agent-workshop` et l'API `/api/agent-workshop` existent
  en plus des entrées admin ; le verrouillage admin reste à réaliser.
- Le compte utilisateur porte un rôle global et une organisation. L'isolation des
  bases ne remplace pas les habilitations ni le partage collectif dans une organisation.
- L'authentification frontend conserve le jeton dans `localStorage`; les sessions
  par onglet restent à construire.
- L'atlas décrit la base principale avant remise à zéro : dix comptes, trois
  organisations, 53 bases secondaires. Il devient une référence historique dès reset.
- Les dernières preuves RFQ sont une qualification sur installations fictives
  isolées, pas une ouverture réelle chez BNP ni une qualification SaaS de production.

Le dépôt GitHub `MattIndiJones/structura` est public au contrôle du 13/10/2026.
Ce document ne change pas sa visibilité. Les bases runtime, clés et secrets ne
doivent jamais être ajoutés à Git, même si les données métier actuelles sont fictives.

## 10. Méthode et validations

- Français pour l'interface, les échanges et les documents ; anglais pour le code
  et les identifiants. Utiliser les skills Structura correspondant au domaine.
- Modifier les masques existants, conserver le scroll interne et les séparateurs
  numériques. Ne pas reconstruire des moteurs ou objets concurrents de Product.
- Ne pas lancer les tests à chaque petite étape. Choisir les tests ciblés nécessaires
  pour le lot effectivement modifié et réutiliser les preuves pertinentes.
- Ne jamais lancer la suite backend complète sans demande explicite de Philippe.
  Respecter le build frontend obligatoire après les changements Vue terminés.
- Ne pas utiliser une base active comme fixture de test. Les bases métier fictives
  explicitement réinitialisées et les bases temporaires de validation ont des usages distincts.
- Réutiliser une instance existante lorsque possible. Ne pas arrêter un processus
  préexistant sans autorisation ; suivre PID, heure et commande des processus démarrés
  pour la recette, puis les arrêter et vérifier la libération des ports.
- Tenir à jour les documents et leur index ; distinguer code livré, configuration,
  recette réussie, limites connues et travaux restants.
- Aucun commit, push ou merge dans le nouveau chat sans instruction explicite
  dans le message courant. La demande de livraison du chat précédent ne vaut pas
  autorisation permanente pour le prochain chantier.

## 11. Prompt à copier dans le nouveau chat

```text
Tu travailles dans C:\Users\admin\GitHub\structura.

Lis AGENTS.md, CLAUDE.md, docs/README.md puis
docs/handoffs/HYBRID_SAAS_HANDOFF_2026-10-13.md.
Vérifie l'état Git et les références documentaires avant de modifier le projet.
Les lots RFQ 0 à 8 sont livrés ; il faut poursuivre à partir de l'existant.

Je veux maintenant commencer à coder le socle SaaS hybride décrit dans ce document.
Travaille sur une nouvelle branche dédiée depuis main à jour, sans écraser des
changements locaux ni modifier la branche d'un autre travail.

Décisions confirmées :
- Base, stockage, moteurs et traitements métier privés chez chaque organisation.
- Portail commun pour les fonctions de plateforme et l'accès aux installations,
  avec un registre central des échanges RFQ pour facturation et litiges.
- Le registre conserve les demandes envoyées aux termes Product figés, cotations
  commerciales publiées, révisions/retraits, accusés, horodatages, acceptations,
  confirmations et références d'exécution. Le contenu doit permettre de relire
  l'échange ; conserver seulement une empreinte ne suffit pas.
- Les books, clients finaux, prix théoriques, calculs, modèles, hypothèses, marges
  et documents internes ne sont pas copiés dans le registre central. Réutilise
  une projection d'échange, sans exporter le dossier Product privé complet.
- L'admin central dispose d'une vue habilitée et tracée du registre pour facturation
  et litiges ; une banque ne voit pas les cotations concurrentes. Collecte durable,
  reprise, rapprochement et dédoublonnage sont nécessaires.
- L'unité proposée est un tour RFQ livré à au moins une banque, facturable au
  demandeur une seule fois, indépendamment du nombre de banques et des retries.
  Cette règle commerciale reste à valider : n'active aucune facturation réelle,
  aucun tarif ni débit client sans validation. Exclus les simulations et essais.
- Six installations isolées de développement : BNP Paribas, Société Générale,
  Citi, UBS, Leonteq et Kepler Cheuvreux Solutions, chacune avec son service et sa base.
- Un super utilisateur métier par organisation comme accès principal, plus les
  comptes Front, Opérations et Contrôleur pour tester les profils spécialisés.
- Un admin central de développement pour tout vérifier dans ces environnements fictifs.
- En production, pas d'accès permanent implicite de l'admin central aux books clients ;
  l'accès autorisé au registre RFQ central constitue un périmètre distinct.
- Simulation avec agents accessible seulement à l'admin ; elle crée ses propres
  comptes et bases et reste séparée des essais manuels.
- Les données actuelles sont fictives : leur remise à zéro est autorisée, sans
  migration et sans obligation de conservation. Cible uniquement les données
  Structura identifiées et prépare l'initialisation avant le nettoyage.
- Aucun chantier de compilation commerciale ou de calcul confidentiel pour le moment.

Commence par les étapes 1 et 2 du plan : installations isolées puis initialisation
reproductible des comptes, desks et droits. La prochaine livraison visible sera
le login commun avec sept cartes et le sélecteur d'organisation/profil, avec des
sessions indépendantes par onglet. Ne considère pas les étapes suivantes comme
déjà faites ; consigne l'avancement et les points à reprendre.

Réutilise Product, les moteurs, les masques et le transport RFQ actuels. Préserve
le manuel, les contrôles de validité, la confirmation avant booking, la prévention
des doubles bookings et la seconde validation configurable. Les données métier
privées restent dans l'installation de leur organisation ; les échanges autorisés
sont conservés chez leurs participants et dans le registre RFQ central.
Définis les accès, durées de conservation et états de synchronisation explicitement.

Garde les écrans et modales bornés à la fenêtre, avec scroll interne ; affiche les
séparateurs de milliers. Les profils secondaires ne doivent pas compliquer le
parcours normal du super utilisateur.

Ne relance pas les tests à chaque modification ni la suite backend complète.
Fais les vérifications ciblées nécessaires à la fin de chaque lot et respecte
le build frontend requis après les modifications Vue. Suis et nettoie les processus
que tu lances pour la recette. Aucun commit, push ou merge sans nouvelle demande
explicite de ma part. Informe-moi des résultats concrets et des limites restantes.
```
