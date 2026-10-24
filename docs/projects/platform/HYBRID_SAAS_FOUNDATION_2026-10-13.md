# Socle SaaS hybride — installations et initialisation

Date : 13/10/2026. Branche : `codex/hybrid-saas-foundation`, depuis `origin/main`
`7dce302`. Changements locaux, sans commit, push ni merge.

**Suite livrée :** [remise à zéro et accès commun — étapes 3 et 4](HYBRID_SAAS_ACCESS_2026-10-13.md).
La présente note conserve les preuves et l'état de la livraison initiale 1–2 ;
les mentions « à faire » concernant nettoyage et login sont remplacées par cette suite.

## Livraison et périmètre

Les étapes **1 et 2** du [handoff hybride](../../handoffs/HYBRID_SAAS_HANDOFF_2026-10-13.md)
sont implémentées et le runtime permanent est initialisé. Les six installations
métiers utilisent le code Structura existant, avec leurs bases, identités,
signatures, documents, caches, temporaires, journaux et espaces Studies privés.
Le service central a un schéma SQLite indépendant : identité centrale,
administrateur, annuaire des installations et audit des accès à cet annuaire.
Il n'importe pas les moteurs ni le schéma métier et ne traite aucun calcul privé.

La cible de développement partage le poste et le code, pas les bases ou les
répertoires runtime. Elle ne qualifie pas une isolation OS entre comptes de service,
un déploiement SaaS de production, un SSO ni des connexions bancaires réelles.

| Installation | Clé | Port | Capacité du scénario | Desks |
| --- | --- | --- | --- | --- |
| Admin Structura | `platform` | 8100 | Annuaire central | Aucun desk métier |
| BNP Paribas | `bnp-paribas` | 8101 | Répondant RFQ | Pricing, Opérations |
| Société Générale | `societe-generale` | 8102 | Répondant RFQ | Pricing, Opérations |
| Citi | `citi` | 8103 | Répondant RFQ | Pricing, Opérations |
| UBS | `ubs` | 8104 | Répondant RFQ | Pricing, Opérations |
| Leonteq | `leonteq` | 8105 | Demandeur RFQ | Sales, Opérations |
| Kepler Cheuvreux Solutions | `kepler-cheuvreux-solutions` | 8106 | Demandeur RFQ | Sales, Opérations |

Les capacités sont explicites dans les manifests ; elles ne sont pas déduites du
nom par les services. Les relations, contreparties locales de traitement et canaux
entre ces six installations restent à configurer à l'étape 6.

Le registre RFQ central reste **`NOT_CONFIGURED`**. Le schéma central ne contient
aucune demande, cotation, exécution ou unité facturable. `billing_enabled=false`
est obligatoire dans ces manifests de développement. Aucune tarification,
émission de facture ou opération de débit n'est introduite.

## Comptes, desks et contrôles

Chaque base métier reçoit une seule organisation locale et les quatre identités
ci-dessous. Le service central reçoit seulement `admin`, de rôle `platform_admin`.
Total initial : **24 comptes métier, 1 compte central, 12 desks**, sans compte
technique de transport créé silencieusement et sans `Demo`, `admin123` ou `test123`
dans les installations manuelles.

| Identifiant local | Rôle persistant | Droits initiaux |
| --- | --- | --- |
| `superuser` | `organization_admin` | Administration locale et fonctions métier ; les neuf droits RFQ sur les deux desks |
| `front` | `user` | Profil Front polyvalent confirmé : lecture, préparation, pricing, sélection, sollicitation et organisation du desk Sales/Pricing ; validation/publication côté banque ; lecture seule sur Opérations |
| `operations` | `ops_maker` | Lecture et booking RFQ sur les deux desks ; préparation opérationnelle existante |
| `controller` | `checker` | Lecture RFQ sur les deux desks ; validation/publication sur Pricing bancaire ; contrôles opérationnels existants |

Les droits RFQ réutilisés sont `read`, `prepare`, `price`, `select`, `solicit`,
`organize`, `book`, `validate_quote` et `publish_quote`. Un rôle ou une appartenance
organisationnelle ne remplace pas les habilitations du desk. Le super utilisateur
reçoit ses droits par le bootstrap explicite, sans override universel de la RFQ.
L'auto-attribution de droits RFQ reste refusée.

La politique initiale des desks Pricing bancaires autorise la validation par le
même utilisateur habilité et limite l'âge du calcul à **60 minutes**, comme le
pilote RFQ précédent. La seconde validation reste configurable. Lorsqu'elle est
requise, changer de profil ne remplace pas une identité distincte.

Le super utilisateur est accepté par les contrôles locaux d'administration,
de relation/publication RFQ, de paramétrage CCR et par les contrôles de rôle
opérationnel. Les contrôles d'organisation, de contenu figé, de fraîcheur,
d'accord avant booking, d'unicité d'exécution et de séparation des personnes
restent appliqués. Les modifications de comptes locaux sont auditées.

Les comptes Front et Contrôleur ne peuvent pas appeler le booking natif ;
Opérations et Contrôleur ne peuvent pas appeler les routes du Pricer. Les droits
RFQ continuent à protéger le pricing bancaire privé. **La granularité de tous les
autres modules et les projections minimales pour chaque profil restent à qualifier
à l'étape 5** : ces vérifications ne constituent pas un audit exhaustif de leurs API.

Le navigateur SQL technique est exclu du super utilisateur métier. Le pilotage
des simulations est refusé aux profils métier, dans les deux préfixes API, les
routes navigateur et les cartes d'accueil/administration. L'admin technique de
l'ancien environnement peut encore piloter les simulations ; l'accès depuis le
nouvel admin central reste à connecter à l'étape 5.

## Initialisation et exploitation locale

Depuis la racine, avec le Python du projet :

```powershell
.venv/Scripts/python.exe scripts/manage_hybrid_dev.py prepare
.venv/Scripts/python.exe scripts/manage_hybrid_dev.py init
.venv/Scripts/python.exe scripts/manage_hybrid_dev.py start
.venv/Scripts/python.exe scripts/manage_hybrid_dev.py status
.venv/Scripts/python.exe scripts/manage_hybrid_dev.py stop
```

`--installation bnp-paribas` limite une commande à cette installation.
`--base-port` choisit une autre plage lors de la préparation initiale ; une plage
existante n'est pas changée implicitement. Un port occupé n'est jamais libéré en
arrêtant son occupant. Un lancement partiel échoué ferme seulement ses nouveaux
services ; les services déjà présents sont réutilisés.

Le runtime permanent est sous `.runtime/hybrid-saas/`, ignoré par Git. Chaque
installation possède `installation.json`, une identité UUID stable, `.jwt_secret`
et `.bootstrap_credentials.json`. Les mots de passe sont aléatoires, propres aux
installations et conservés uniquement dans ces fichiers privés ; ils ne figurent
ni dans les sources, ni dans le frontend, ni dans les rapports de recette.
Pour une connexion individuelle, utiliser le mot de passe du fichier privé de
l'installation concernée. Le portail de login commun reste à construire.

Le service refuse un manifeste contradictoire avec son répertoire, une base
appartenant à une autre identité ou une base préexistante sans bootstrap identifié.
Ce contrôle intervient **avant** les mises à jour de schéma et de politique métier.
Une base centrale contenant un schéma métier est également refusée avant son
initialisation ; une base privée sans identité doit être vide pour une reprise.
Le schéma complet et les référentiels sont initialisés séparément des identités.
Les comptes, desks, habilitations, politique et marqueur de bootstrap sont créés
dans une transaction unique. Une interruption permet une reprise sans doublons.
Une relance ne réinitialise pas les mots de passe, comptes désactivés, droits
révoqués ou politiques modifiées ; `configuration_drift` signale les écarts.

La signature JWT, son émetteur, son audience et l'organisation sont contrôlés
dans l'installation destinataire. L'état du compte et ses droits sont relus côté
serveur. La durée des jetons reste **sept jours**. `/api/auth/me` expose le profil,
les capacités et un descripteur d'installation sans chemin privé ni secret.
Les raccourcis développeur ne sont pas activés (`developer_access=false`).

L'outil suit le PID du lanceur et celui du serveur : le redirecteur du virtualenv
Windows peut créer deux processus. Un identifiant de lancement et un secret de
contrôle privé protègent l'arrêt. Les ports et la sortie du serveur sont vérifiés.
Les instances restent sans reloader et sans fenêtre supplémentaire.

Les fichiers Fama-French présents sont copiés dans les stockages privés avant
tout fetch ; leurs rafraîchissements et les poids Whisper restent locaux.
Les sous-processus héritent des chemins temporaires de leur installation.
Les simulations gardent leur bootstrap historique explicitement séparé, avec
leurs comptes techniques et agents, hors du décompte des 25 comptes manuels.
Elles et les consultations ne récupèrent pas le manifeste d'une installation par
héritage d'environnement. Leur remplacement par un bootstrap dédié sans seeds
historiques reste une évolution distincte de l'étape 5.

## Conservation et synchronisation

Pour ces environnements fictifs, la politique est **`UNTIL_EXPLICIT_RESET`** :
comptes, configuration, données éventuelles, audits et preuves restent conservés
jusqu'à une remise à zéro explicitement commandée. Aucun worker de purge automatique
et aucune durée réglementaire arbitraire ne sont ajoutés. Les sauvegardes et copies
de runtime doivent conserver les identités et clés ; aucun outil de sauvegarde
de production n'est qualifié par cette livraison.

La seule synchronisation centrale déclarée est `NOT_CONFIGURED` : aucune collecte,
aucun reçu central, aucun rapprochement. Le transport participant existant garde
ses états `PENDING`, `RETRY`, `BLOCKED`, `DELIVERED` et `CANCELLED`. Un accusé de
transport reste distinct d'une acceptation, d'une confirmation ou d'un booking.

À l'étape 7, définir séparément attente locale, réception centrale, rapprochement
entre participants et écart, avec reprise durable et dédoublonnage. Collecter les
contenus autorisés par la projection d'échange Product, jamais le dossier privé
complet. Avant un pilote de production, fixer les habilitations du registre,
finalités, durées explicites, sauvegardes, règles de purge et suspension pour litige.
La configuration actuelle n'accepte que `DEVELOPMENT` ; aucune activation de
production ou de facturation n'est possible par ce socle.

## Vérification et travaux restants

- Premier lot : six tests ciblés d'isolation réussis.
- Deuxième lot : 37 tests ciblés réussis (bootstrap, desks, publication, refus des
  simulations). Contrôle final : **52 tests réussis**, incluant les scénarios RFQ
  d'exécution, confirmation, validité, booking concurrent/unique et les contrôles
  voisins d'amendement/fixing. Les passes se recouvrent ; ne pas additionner leurs
  nombres comme des scénarios distincts.
- Revue finale : contrôles ciblés supplémentaires réussis du refus de schéma
  métier central, du démarrage central autorisé, du refus d'une identité étrangère
  avant migration et de la reprise d'un schéma vide interrompu.
- Recette native réussie sur **sept serveurs et 25 comptes**, double initialisation,
  clés/identités conservées, refus des jetons croisés, droits administratifs,
  refus de booking/pricing non habilité et des simulations, arrêt/redémarrage BNP
  sans interruption Citi, sessions conservées et zéro dossier métier/calcul/étude.
  Preuves privées : `tmp/hybrid-foundation/20261013-124843-504bc4/acceptance.json`.
  Les serveurs de cette recette ont été arrêtés et leurs ports libérés.
- Le runtime permanent a été initialisé : une base centrale, six bases métier,
  25 comptes et 12 desks. Ses services ne sont pas laissés actifs.
- `npm run build` réussi : **428 tests frontend réussis** et compilation Vite
  terminée. Les modifications Vue portent sur l'administration locale, les
  contrôles de rôle et les accès aux simulations ; pas sur le login commun.
  Les masques RFQ et formats numériques existants sont conservés ; aucune
  nouvelle recette visuelle des masques n'est revendiquée.
  Aucune suite backend complète n'a été lancée.

| Étape | État après cette livraison |
| --- | --- |
| 1. Installations | Implémentée et recettée localement |
| 2. Initialisation et droits | Implémentée et initialisée ; granularité exhaustive des modules à qualifier à l'étape 5 |
| 3. Remise à zéro | Non exécutée : anciennes bases/archives et anciens jetons inchangés |
| 4. Accès commun | À faire : sept cartes, sélecteur organisation/profil, origine développeur auditée, sessions par onglet, traitement des saisies et nettoyage complet des stores |
| 5. Supervision et partage | À faire : connexion de l'admin central aux environnements fictifs/simulations, travail collectif et revue des API de tous les modules |
| 6. RFQ entre bases | À faire pour les six installations : relations autorisées, accords fictifs et appairages ; transport existant réutilisé |
| 7. Registre RFQ central | À faire : collecte, contenus, chronologie, accès tracés, export, rapprochement et comptage simulé |
| 8. Qualification/exploitation | À faire : recette des autres modules, reset ciblé, sauvegardes, reprise et atlas actualisé |

Les consommateurs encore liés au créateur comprennent la bibliothèque Product
et ses accès privés, plusieurs collections de scripts/documents/études et les
portefeuilles. Les permissions RFQ par desk ne suffisent pas à rendre ces modules
collectifs. Le workflow Opérations passant par le Pricer doit être adapté par une
projection de booking habilitée à l'étape 5 ; ne pas lui donner silencieusement
le droit de lire ou calculer tout le pricing privé pour contourner cette limite.

Les anciens jeux de `backend/data/` et `tmp/` n'ont pas été nettoyés. L'atlas du
13/10 reste la photographie historique de cette ancienne base ; les nouvelles
installations décrites ici s'y ajoutent. Aucune migration de leur contenu n'est
requise pour la prochaine remise à zéro autorisée.
