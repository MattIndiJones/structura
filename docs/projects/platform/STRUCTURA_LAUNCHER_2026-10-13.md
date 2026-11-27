# Lanceur et retour de Structura Admin complet

Date : 13/10/2026. Branche : `codex/hybrid-saas-foundation`.
Changements locaux, sans commit, push ni merge.

## React unifié et ouverture dans Chrome — 27/11/2026

Le sélecteur propose **Ouvrir React** et **Ouvrir l’historique**. React assemble
le frontend et le backend de la branche courante et utilise son répertoire de
données habituel, `.runtime/launcher/data`, sur 18100–18108. L’entrée historique
ouvre Vue. L’espace local de recette 18208 est conservé sur disque. Les mises à
niveau SQLite du React habituel utilisent la sauvegarde du mécanisme de migration.
Si une version précédente de React est encore active, le lanceur demande de
l’arrêter et de rouvrir le menu pour charger le nouveau build.

Le lanceur ouvre la page dans un onglet Google Chrome ordinaire. **Arrêter
Structura** et la fermeture de la fenêtre du lanceur arrêtent les services de la
session. Windows récupère ses descendants à sa sortie. Chrome s’exécute hors de
ce groupe et la fermeture d’un onglet Chrome est gérée par le navigateur.
L’arrêt propre expose toute erreur et permet de confirmer la fermeture de la
session si nécessaire.

### Temps d’ouverture et d’arrêt du React unifié

**Mettre à jour React** prépare les sources locales des dépôts Structura et
Structura React. Cette action vérifie les sources, les dépendances et les
réglages de compilation. Elle exécute TypeScript et Vite lorsque le paquet doit
être reconstruit, puis publie le reçu atomiquement. Depuis la racine de
Structura, la même mise à jour est disponible avec
`.venv\Scripts\python.exe -B ..\structura-react\scripts\launch_versions.py --update-react`.

**Ouvrir React** compare les sources locales et le contenu du paquet déjà publié.
Si le paquet manque ou ne correspond plus aux sources, le menu indique l’action
**Mettre à jour React**. Le contrôle d’ouverture et celui qui précède le
lancement de Chrome utilisent les empreintes des fichiers et ne demandent ni
Node ni npm. Le paquet préparé fixe les dépendances et l’environnement de build
jusqu’à la prochaine mise à jour explicite.

`application.txt` identifie le paquet en service. Une mise à jour peut être
préparée pendant que les services tournent. Pour la charger, arrêter Structura
depuis le menu puis choisir **Ouvrir React**. Un deuxième clic sur **Ouvrir React**
restaure la fenêtre d’ouverture ou le menu déjà ouvert.

Pour **Structura Admin** et **Écran de simulation**, le lanceur React ouvre
Chrome dès qu’Admin répond. Le portail reste arrêté jusqu’à une action qui
en a besoin. Depuis Admin, **Choisir un autre compte** et **Accès aux six
organisations** demandent le démarrage du portail et attendent sa réponse
avant de changer de page. Les entrées **Console SaaS**, **Une organisation**
et **Les six organisations** continuent à démarrer le portail depuis le
lanceur. Le portail démarré depuis Admin est rattaché au même lanceur, qui
l’arrête avec les autres services de la session.
L’arrêt confirme la sortie des processus et la libération des ports. Un calcul
ou une campagne en cours peut prolonger la fermeture propre.

Sous Windows, la vérification du démarrage fait un test TCP court avant de
consulter `/health`. La réponse HTTP et l’identité du lancement restent requises.
Les dépendances de régression AMC, de génération PDF et de l’intervalle du Valo
Explain sont chargées au premier usage. Les contrôles SQLite restent synchrones.
Sur la même base de recette déjà initialisée, la médiane de deux démarrages par
version est passée de 8,73 s à 7,31 s jusqu’à la confirmation HTTP d’Admin. Cette
mesure exclut la vérification du paquet et le rendu de Chrome.

Avant la séparation de la mise à jour, la préparation à l’ouverture mesurait
32,0 s et le démarrage séquentiel 16,7 s. L’ancienne vérification du paquet
précompilé prenait 4,8 s.
Quand l’ouverture Admin démarrait deux services, la recette mesurait 16,9 s
en série et 10,9 s en parallèle. Un autre essai parallèle a pris 18,4 s.
Les fermetures à vide ont confirmé les PID sortis et les ports libérés en 1,3 à
2,2 s environ. Ces mesures excluent le rendu de l’onglet Chrome.

## Choix de la version Vue ou React — 25/11/2026

**Entrées.** Le raccourci « Structura » du menu Démarrer, `lancer_structura.bat` et
`backend/run.py` sans argument passent par `scripts/launch_structura.py`. Quand le clone
`structura-react` est à côté de `structura`, ce script ouvre son choix de version
(`structura-react/scripts/launch_versions.py`), avec l'interpréteur du `.venv` de
Structura, comme le fait `structura-react/lancer_structura.vbs`. Sans ce clone, le menu
Vue s'ouvre comme avant. `launch_structura.py --vue` ouvre directement le menu Vue.

**« Ouvrir Vue »** exécute `lancer_structura.vbs`, qui passe désormais `--vue` :
s'il passait par le `.bat`, le choix se rouvrirait en boucle. Le `.vbs` ne dépend plus
d'un chemin absolu `C:\Users\admin\…`. Le `.bat` transmet ses arguments.

**« Ouvrir React »** (`launch_versions.py --react`) copie le backend de Structura au
commit épinglé `fa7ff711` et le build `structura-react/dist` dans
`structura-react/.runtime/launcher/<commit>-<empreinte du build>`. Il ouvre ensuite le
même menu sur un runtime séparé : ports 18100–18108 (Admin sur 18108), données dans
`structura-react/.runtime/launcher/data`. Vue garde 8000 et 8100–8107 et ses données de
`.runtime/hybrid-saas` : les deux versions peuvent tourner ensemble. Un nouveau build
React n'est pris qu'après l'arrêt des services React encore actifs.

**Erreur visible.** Si le menu Vue ne peut pas importer ses modules, une boîte
« Structura — lancement impossible » donne l'erreur et la commande de mise à jour du
`.venv`. Sous `pythonw`, rien ne s'affichait jusque-là.

### Incident du 25/11 et remise en état du poste

- Après le pull de `fa7ff71`, le `.venv` n'avait pas suivi le commit `39aeb49` (PyJWT
  remplace python-jose) : `import jwt` échouait avant toute fenêtre, et le raccourci ne
  faisait rien. Correction : `.venv\Scripts\python.exe -m pip install --require-hashes -r
  requirements.lock.txt` (PyJWT 2.15.1, cryptography 50.0.2, pillow 13.0.0, pytest 9.2.0,
  entre autres). python-jose, ecdsa, rsa et pyasn1 restent installés, mais ne sont plus
  importés.
- Le clone `structura-react`, propriété du groupe Administrateurs, n'était accessible qu'en
  lecture au compte Philippe : ni build, ni `.runtime`. Philippe a accordé le même droit
  que sur `structura` (`icacls … /grant "PC-MAISON\Philippe:(OI)(CI)M"`) et ajouté le
  clone à `safe.directory`. Ensuite : `npm ci` puis `npm run build`. Le poste a Node 24.12
  et le projet déclare `^20.19.0` : simple avertissement. Ce build local n'est pas
  l'artefact qualifié du Lot 16.
- Reste ouvert : `npm run verify:legacy` échoue dans ce clone. Git for Windows
  (`core.autocrlf=true` au niveau système) a extrait `src/legacy-core` en CRLF, alors que
  le manifeste attend les octets commités. Ni le build ni le lanceur n'en dépendent.

### Vérifications du 25/11

- 23 tests de `backend/tests/test_structura_launcher.py`, dont 6 nouveaux : choix
  proposé, `--vue` conservé à la relance, absence de boucle, erreur d'import affichée.
- Ouvertures réelles sur le poste : le raccourci ouvre « Structura — Choix de la
  version » ; le `.vbs` ouvre le menu Vue, et `launcher-ui.json` le donne prêt ;
  `--react` ouvre « Structura React — Votre espace de travail » sur le vrai
  `.runtime/launcher`, avec neuf installations préparées, sans base ni service.
- Chemin React complet sur un état jetable : copie en 5,8 s, Admin et portail
  démarrés en 35,9 s, `/health/ready` à 200, `index.html` et bundle React servis, session
  Admin de développement délivrée. Arrêt en 4,7 s, processus terminés et ports libérés.
- Non exercés : le clic dans la fenêtre de choix (son bouton Vue exécute le `.vbs`, testé
  directement), une recette visuelle par capture et les services Vue réels, laissés
  arrêtés pour ne pas toucher au workspace Admin.

## Refonte visuelle du 03/11/2026

Le lanceur adopte un fond ivoire, une identité latérale bleu nuit et des accents
cuivrés. L'accès Admin est présenté horizontalement, avec son action principale
bien visible ; les quatre accès secondaires sont regroupés en cartes compactes.
Les boutons, aides, bordures, états de focus et détails techniques sont harmonisés.
La colonne de marque s'efface sous 1 000 pixels de largeur. Au format initial
1 100 × 820 sur le poste vérifié, les cinq accès tiennent sans défilement ; les
petites fenêtres conservent le défilement des cartes et les commandes en pied.

Vérification locale : 14 tests ciblés du lanceur réussis, compilation Python et
contrôle de disposition Tkinter à 1 100 × 820, 900 × 760 et 720 × 610, sans
débordement des contrôles ni erreur de callback. Le panneau de détails est exercé
ouvert et fermé. La capture native Windows n'a pas abouti ; ces mesures ne valent
pas une recette visuelle par capture. Le menu a été rouvert depuis le raccourci.
Aucun serveur métier ni agent n'est lancé par cette vérification. Les choix de
lancement, l'identité des installations et le périmètre d'arrêt sont conservés.

## Reprise du workspace historique — 24/10/2026

Le [correctif du changement de compte depuis Admin](../../audits/ADMIN_ACCOUNT_SWITCH_2026-10-24.md)
ajoute le choix explicite du profil, le démarrage de l’organisation à la demande
et les retours après erreur. Une instance du portail déjà active doit être
relancée pour charger ce nouveau contrat serveur ; aucun agent IA n’a été démarré.

La [recette des autres accès](../../audits/LAUNCHER_ACCESS_ACCEPTANCE_2026-10-24.md)
confirme les six organisations, les 24 profils, la console et les deux chemins
de simulation sur copies isolées puis sur le runtime permanent. Le script de
recette a été corrigé ; aucune IA démarrée et tous les services créés arrêtés.

Les anciens workspaces Admin créés avant C02 peuvent être refusés au démarrage
car leur identité n'était pas encore attestée. La [reprise du launcher](../../audits/LAUNCHER_RECOVERY_2026-10-24.md)
documente l'outil explicite, sa sauvegarde, ses contrôles et la validation native.
Le workspace du raccourci a été repris ; aucun marqueur de sécurité n'a été retiré.
Les états ci-dessous restent ceux de la note initiale et de ses ajouts datés.

## Utilisation

Double-cliquer sur `lancer_structura.bat`, ou exécuter `backend/run.py` sans
arguments depuis Python ou l'IDE. Le même menu Python s'ouvre, sans commande
PowerShell ni arguments à saisir.

- **Ouvrir Structura complet — Admin** : application habituelle sur
  `http://127.0.0.1:8000`, connecté au compte `admin`. Accueil, modules métier,
  administration complète et simulation sont présents.
- **Ouvrir la simulation avec agents** : même compte Admin, directement sur
  l'écran de simulation. Une campagne nécessite encore un lancement explicite.
- **Ouvrir le portail des six organisations** : démarre le portail et les six
  services privés ; chaque carte métier ouvre son super utilisateur.
- **Ouvrir la console SaaS** : annuaire et supervision centrale, périmètre distinct
  de l'application Admin complète.
- Le choix d'une organisation démarre seulement son service et le portail.
  Le menu propose également l'état des services et leur arrêt.

## Lanceur modernisé et arrêt ciblé

La fenêtre présente des cartes sobres, une description de chaque choix, un « ? »
avec explication au survol et au clic, et un indicateur d'activité. Le menu possède
son scroll interne ; les détails techniques sont repliés et consultables à la demande.
La carte **Simulation avec agents** ouvre l'écran de configuration et les résultats,
sans démarrer d'agents ; sa description et son aide « ? » l'indiquent explicitement.

Reprise visuelle : carte Admin bleu nuit mise en avant, quatre accès secondaires
en deux colonnes, pictogrammes vectoriels, surfaces et boutons arrondis, badge de
développement et états de survol/focus. La progression est masquée au repos ; le
scroll apparaît seulement lorsqu'il est nécessaire. Les textes s'adaptent à la
largeur. Les boutons sont utilisables au clavier. Ces widgets restent en Tkinter,
sans dépendance supplémentaire. Cette reprise ne modifie ni le lancement, ni
le périmètre d'arrêt. Contrôle de syntaxe seul, sans nouvelle exécution de tests
ni lancement de serveur ; rendu natif à confirmer à l'ouverture.
Correctif après ouverture : les dimensions du dessin arrondi utilisent désormais
`box_width` et `box_height`, pour éviter le conflit avec `width`, épaisseur du trait.
Le démarrage graphique écrit son état dans `launcher-ui.json` et les erreurs de
callbacks Tkinter dans `launcher-ui.log`, sans déclencher de service métier.

**Arrêter Structura** concerne uniquement les espaces ouverts depuis cette fenêtre
du lanceur, y compris les services démarrés depuis leur portail. Une installation
déjà active peut être reprise en l'ouvrant dans cette fenêtre. Les autres espaces
et les services inactifs sont ignorés. Un identifiant du lanceur est enregistré
dans le suivi privé des processus ; les contrôles d'identité et de lancement sont
conservés avant l'arrêt.

Les services concernés sont arrêtés en parallèle. La boucle de vérification des
ports utilise une attente réseau de 50 ms au maximum par passage, et les nouveaux
serveurs gérés limitent à cinq secondes l'attente Uvicorn des requêtes en cours.
Cette limite ne force pas la fin d'une campagne IA ou d'un calcul métier : leur
fermeture propre peut rester plus longue lorsqu'un traitement est effectivement actif.
Le temps réel de l'arrêt est affiché. Aucun arrêt forcé global ni suppression de données.

Rouvrir le lanceur charge cette nouvelle interface ; les services déjà actifs
reçoivent le nouveau réglage Uvicorn lors de leur prochain démarrage. Syntaxe Python
vérifiée, tests et recette graphique non relancés à la demande de Philippe.

La carte **Admin Structura** du login commun et le retour Admin du sélecteur
ouvrent désormais l'application complète. Le lanceur réutilise les services déjà
actifs, refuse de remplacer un occupant étranger et suit ses processus.
L'arrêt ignore les services jamais lancés et ceux dont la sortie est déjà
confirmée. Les vérifications restantes de ports inactifs sont courtes et réalisées
en parallèle ; seuls les services actifs apparaissent dans le journal d'arrêt.
La ligne « Simulation avec agents » de l'ancien lanceur désignait un service de
contrôle, pas le lancement d'une campagne IA. Les contrôles d'identité restent
obligatoires avant tout arrêt d'un service actif. Correctif sans nouvelle recette
ni exécution de tests ; rouvrir le lanceur pour charger la nouvelle version.

## Périmètres et conservation

Le workspace `.runtime/hybrid-saas/admin-workbench` possède sa propre base,
son secret de signature, son compte Admin et ses fichiers. Il réutilise
l'application existante ; les bases des six organisations ne sont ni attachées
ni copiées dans ce workspace. Les anciens jeux fictifs retirés ne sont pas restaurés.
La console centrale garde `platform.db`, sans schéma métier privé.

L'accès rapide Admin exige le manifeste de développement, l'activation explicite
du mode développeur, une requête locale avec en-tête dédié et une origine autorisée.
Il est audité. Le mot de passe bootstrap est aléatoire et privé ; la session dure
sept jours, dans `sessionStorage`, indépendamment des autres onglets. Un compte
désactivé ou dont le rôle a changé n'est pas rétabli implicitement.
Ce dispositif ne définit aucun accès permanent de production aux books clients.

Les campagnes du workspace Admin vivent dans `admin-workbench/campaigns` ; les
acteurs créent leurs propres comptes et bases. Elles sont distinctes des essais
manuels et du contrôleur de simulation de la console centrale (`simulation/campaigns`).
Les secrets de la plateforme et le manifeste Admin ne sont pas transmis aux acteurs
ou aux consultations. Les consultations conservent leur mode lecture seule.

Données et campagnes : conservation jusqu'à remise à zéro explicite.
Registre RFQ : `NOT_CONFIGURED`. Aucune synchronisation centrale des books ni
facturation réelle ; registre, rapprochement et comptage restent à développer.

## Vérifications et reprise

Avant la dernière demande d'arrêt des tests, les contrôles ciblés du lanceur,
des accès et du contrôleur de simulation ont été exécutés ; une recette isolée a
couvert réutilisation des services, refus des profils métier, création de brouillons
de campagne et inscription d'un acteur. Aucun agent IA n'a été lancé dans cette recette.
Ces résultats précèdent le rétablissement du workspace Admin complet et ne le
qualifient pas de bout en bout.

À la demande de Philippe, **aucun test n'est relancé après ce correctif Admin**.
Compilation frontend seule : `npm run build:skip-tests`, réussie.
Les serveurs et les onglets de recette temporaires sont arrêtés/fermés.
La recette du nouveau parcours complet est différée.
Le workspace permanent Admin a été initialisé avec son compte `admin` ; cette
initialisation ne lance ni serveur, ni campagne, ni suite de tests. Les attentes
des tests du lanceur ont été adaptées au nouvel accès, sans nouvelle exécution.

L'étape 5 est seulement amorcée : supervision locale et accès simulation raccordés.
Partage collectif, droits exhaustifs et parcours Opérations restent à reprendre.
Les étapes 6 à 8 (configuration RFQ des six organisations, registre durable,
rapprochement, comptage simulé, sauvegarde/restauration et qualification complète)
ne sont pas livrées. Product, moteurs et contrôles RFQ/booking existants sont réutilisés.
