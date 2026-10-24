# Lot 1 — C02 : sessions, portail et identité des installations

**20 octobre 2026 — livraison locale, sans commit ni push.**

Les sept constats M01-06 à M01-12 sont traités sur le périmètre local. Le
[registre](remediation-lot-0-2026-10-20/REGISTER.json) et les
[preuves ciblées](remediation-lot-0-2026-10-20/C02_VALIDATION.json) distinguent cette
validation de la clôture transverse et de la qualification en production.

## Règles de session et de mot de passe

- Chaque nouveau JWT porte un identifiant unique et la version de session du compte.
  La signature, l'expiration, l'activité, la version et la révocation sont vérifiées
  côté serveur. Les installations gérées et le workspace Admin vérifient aussi
  l'émetteur et le destinataire liés à leur manifeste.
- La déconnexion révoque le jeton courant. « Révoquer toutes mes sessions » et
  l'action administrateur incrémentent atomiquement la version du compte.
  Un changement de rôle, d'organisation ou d'état actif fait de même. Réactiver
  un compte ne réhabilite aucun ancien jeton.
- Création manuelle, inscription autorisée, changement personnel et réinitialisation
  appliquent la même règle : **12 caractères minimum, 72 octets UTF-8 maximum**.
  Les mots de passe existants ne sont pas réécrits. Les nouveaux mots de passe
  administrés sont provisoires : seules l'identité, la déconnexion et la définition
  du mot de passe personnel restent accessibles avant leur changement.
- Le changement personnel vérifie le mot de passe actuel et ferme toutes les
  sessions. Une réinitialisation administrateur a le même effet et impose le
  changement personnel ; elle reste dans son périmètre d'organisation.
- Les connexions métier ordinaires réussies, refusées et limitées sont auditées avec
  compte connu ou identifiant saisi, installation, IP, date et corrélation. Les
  audits ne conservent ni mot de passe ni JWT. Les accès développeur gardent leur
  circuit explicite et leur audit.
- La plateforme centrale utilise ses propres versions et révocations dans
  `platform.db`, sans importer le schéma métier.

Le navigateur efface immédiatement le contexte local et demande la révocation
serveur. La déconnexion explicite révoque aussi le jeton central éventuellement
conservé pour les changements de contexte développeur. Si un serveur est
injoignable, l'écran de connexion indique que sa révocation n'est pas confirmée.

## Portail normal et identité de destination

L'annuaire de connexion par mot de passe est distinct des raccourcis développeur
et disponible lorsque ceux-ci sont désactivés. Il expose uniquement les identités,
noms, types et adresses locales nécessaires au choix. L'annuaire administratif
existant reste protégé.

La sélection est obligatoire sur le portail. Un annuaire indisponible ou une
sélection inconnue bloque l'envoi ; aucun repli implicite vers la plateforme
centrale. Avant transmission du mot de passe, le navigateur compare les identités
d'installation, d'organisation et le type annoncés par la destination avec le
choix effectué. Le retour `/me` est contrôlé de nouveau avant activation.
Les origines CORS du portail configuré sont autorisées indépendamment du mode
développeur ; les origines étrangères restent refusées. La connexion directe
au workspace autonome reste disponible.

Cette vérification protège le routage et les incohérences de configuration ; elle
ne constitue pas une attestation cryptographique indépendante d'un serveur local
compromis.

## Organisation canonique et workspace Admin

**Décision explicite de Philippe, enregistrée en D13 :** « Verrouiller le nom
canonique localement ; renommage via provisionnement ».

Dans une installation métier gérée, la liste est limitée à son organisation ;
création d'une seconde entité, renommage local et accès aux entités étrangères
sont refusés. Les refus de changement d'identité sont audités. Un nom divergent
du manifeste est refusé au démarrage avant migration, sans réparation implicite.
Le provisionnement doit maintenir ensemble le manifeste, l'identité locale et
sa référence de configuration. Le renommage autonome demeure disponible.

Le workspace Admin possède désormais un marqueur d'identité lié à son manifeste
et à son organisation initiale. Le chemin du moteur et l'identité sont contrôlés
**avant `create_all`, migrations et seed**. Une base étrangère, une identité
incompatible ou une base peuplée non marquée est refusée. Une identité correcte
permet le redémarrage sans restaurer un compte désactivé ni ses sessions révoquées.
Le contrôle préalable du schéma central refuse également une identité étrangère
avant toute création de table.

## Prévisualisation des calendriers

Les quatre routes demandent une session et `business.price`, en cohérence avec
C01 pour le calcul libre. Elles contrôlent les entrées avant les générateurs et
les boucles d'ajustement : années **1900 à 2200**, horizon et ancrage **50 ans**,
budget prévisionnel **500 constatations / 5 000 points**, tenors et fenêtres bornés.
L'estimation est conservatrice, notamment pour les mois et les sous-fréquences.
Un dépassement renvoie une erreur explicite. Les algorithmes et conventions des
calendriers contractuels ne sont pas modifiés ; leur qualification relève de C05.

## Books en consultation

Les livres sauvegardés restent strictement en lecture seule. Authentification,
audit et révocation du viewer utilisent `sessions.db` dans le dossier privé de
verrouillage de consultation. La projection d'identité fonctionne aussi sans les
nouvelles colonnes utilisateur dans une archive ancienne. Un test compare le
fichier d'archive octet par octet après connexion et révocations ; la recette
native contrôle aussi la fermeture de son processus et l'indisponibilité du port.
Le changement de mot de passe du livre reste interdit dans ce mode.

## Validation et limites

Le passage consolidé réussit **138 tests backend ciblés** sur onze fichiers et
**455 tests frontend** sur 59 fichiers. Le build Vite réussit en sortie temporaire.

Les commandes, fichiers, résultats et empreintes des journaux sont consignés dans
[C02_VALIDATION.json](remediation-lot-0-2026-10-20/C02_VALIDATION.json). Les tests
utilisent des données temporaires isolées et une clé de test. Le build frontend
est écrit dans un répertoire temporaire ; le `dist` préexistant est conservé.

Les assertions couvrent les anciens jetons, la désactivation/réactivation, les
mots de passe provisoires et personnels, la portée administrateur, les audits
sans secrets, le portail hors mode développeur, CORS, les contrôles avant migration,
les archives et les refus de calendriers avant appel des générateurs. Les
régressions incluent les permissions C01, les installations, les tickets développeur,
le reset, le lanceur et les calendriers existants.

La première reprise de consultation a révélé une attente de nom devenue obsolète
dans sa fixture : le test fixe maintenant explicitement « Maison Hector » dans
son scénario et son book. Le premier lancement frontend nécessitait `npm.cmd`
pour transmettre `--outDir` sous PowerShell ; le test Vue utilise un mock de son
image publique. Ces reprises sont conservées dans les journaux locaux.

La recette graphique manuelle et la chaîne T01 complète restent à exécuter.
Aucune migration ou relance d'installation métier existante n'a été effectuée.
C19 reste ouvert pour les formats, migrations et rejouabilité des archives ; le
contrôle préalable d'identité et la conservation du livre sont ses interfaces
validées ici.

## Conditions de mise en service

1. Les JWT antérieurs à C02 seront refusés : reconnexion nécessaire après mise à jour.
2. Les migrations additives créent les états de session et ajoutent deux colonnes
   utilisateur, sans réinitialiser les comptes ni leurs mots de passe.
3. Un ancien workspace Admin peuplé sans marqueur ne sera **pas adopté
   automatiquement** sur la seule présence d'un compte `admin`. Sa reprise doit
   attester explicitement l'identité dans le provisionnement avant son démarrage.
   Aucun outil d'adoption ni marquage d'une base réelle n'a été exécuté ici.
4. Les fichiers de révocation et d'audit suivent la conservation du runtime ;
   aucune purge implicite n'a été ajoutée.

Les travaux C01 et les changements antérieurs du checkout ont été conservés.
La livraison reste locale et reviewable ; aucune publication Git ni déploiement.
