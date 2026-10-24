# SaaS hybride — remise à zéro et accès commun

Date : 13/10/2026. Branche : `codex/hybrid-saas-foundation`, depuis `origin/main`
`7dce302`. Changements locaux, sans commit, push ni merge.

## Livraison

Les étapes **3 et 4** du [handoff](../../handoffs/HYBRID_SAAS_HANDOFF_2026-10-13.md)
succèdent au [socle des étapes 1 et 2](HYBRID_SAAS_FOUNDATION_2026-10-13.md).
Le portail central sert désormais le frontend commun. Le navigateur appelle
directement l'API de l'installation sélectionnée pour le métier ; la plateforme
ne reçoit ni book, ni calcul, ni dossier Product privé.

Le login développeur présente sept cartes : BNP Paribas, Société Générale, Citi,
UBS, Leonteq, Kepler Cheuvreux Solutions et Admin Structura. Les six cartes métier
ouvrent le super utilisateur. Le sélecteur d'en-tête donne accès aux quatre comptes
locaux, au retour super utilisateur et au retour Admin. Il ouvre une identité
existante ; il ne modifie pas son rôle persistant.

L'organisation, le profil et l'identifiant sont visibles dans l'en-tête.
Depuis le [correctif du lanceur et de l'Admin complet](STRUCTURA_LAUNCHER_2026-10-13.md),
la carte Admin ouvre l'application habituelle, avec ses modules, son administration
et sa simulation, dans un workspace de développement séparé des six organisations.
L'écran d'annuaire reste disponible dans la console SaaS distincte ; registre RFQ
non configuré et facturation désactivée. La supervision complète reste à réaliser.

## Remise à zéro effectivement exécutée

Après initialisation des sept nouvelles bases et vérification de leur absence
de dossiers, le retrait ciblé a supprimé **88 bases SQLite et 430 fichiers**,
environ **335 Mo**. Le périmètre comprend l'ancienne base `backend/data/structura.db`,
son archive CCR, les trente bases d'acteurs des six simulations arrêtées et les
bases RFQ/CCR/hybrides de recette identifiées, ainsi que les clés et contenus de
runtime associés. Les anciennes sessions des installations retirées sont invalidées.

Les six nouvelles bases métier et la base centrale sous `.runtime/hybrid-saas`
sont préservées : **25 comptes, 12 desks**, mêmes identités et signatures locales.
Aucune migration des dossiers fictifs n'a été effectuée. Les fichiers Fama-French
versionnés et les caches de marché existants restent disponibles.

L'outil utilise un inventaire de chemins absolus, tailles et empreintes, puis
revérifie cet inventaire avant suppression. Il refuse chemins sortants, liens,
points de réanalyse, fichiers versionnés, installations actives et bases manuelles
déjà remplies. Il préserve les autres checkouts, y compris dans `tmp`.
**121 bases hors périmètre ou non reconnues** ont été préservées, principalement
les dépôts temporaires des tests de nettoyage et quelques fixtures vides/étrangères.
Les rapports historiques, scripts de diagnostic et captures sous `tmp` restent
des preuves statiques ; ils ne constituent pas des installations actives.

Preuves privées : `.runtime/hybrid-saas/cleanup-inventory.json` et
`cleanup-result.json`. Le marqueur `backend/data/.hybrid-retired.json` empêche
le redémarrage de l'ancien environnement et la recréation des seeds Demo/admin/test.
Le bootstrap séparé des acteurs de simulation reste disponible dans ses propres
répertoires ; il n'est pas remplacé par des comptes manuels.

## Accès et durées explicites

Les raccourcis exigent **`--developer-access` au lancement**, dans les services
centraux et destinataires. Sans ce réglage, les cartes privilégiées et l'émission
d'accès développeur sont désactivées ; la connexion par mot de passe reste disponible.
Cette configuration ne permet que `DEVELOPMENT`, pas une activation de production.
La session de l'admin ne donne aucun accès permanent aux books en production.

La plateforme ne lit pas les mots de passe ou clés JWT des organisations. Elle
émet un ticket RSA signé, destiné à une seule installation, organisation et
identité, valable **60 secondes**. L'organisation vérifie la clé publique centrale,
l'émetteur, l'audience, l'expiration, le compte actif et son rôle attendu, puis
consomme le ticket **une seule fois** et signe sa propre session locale.
Les sessions locales et centrales restent valables **sept jours**.

Les accès rapides sont limités au poste local, avec origines du portail et de Vite
explicitement autorisées et en-tête développeur obligatoire. Aucun mot de passe de
test n'est livré dans le frontend. Les identifiants privés restent dans les fichiers
de bootstrap ignorés par Git.

Les émissions centrales et connexions locales sont auditées : identifiant du ticket,
identité métier effective, rôle et origine `DEVELOPMENT_PORTAL` ou `CENTRAL_ADMIN`.
La dernière origine précise l'identité centrale quand un admin authentifié ouvre
un contexte fictif. Les utilisateurs métier conservent uniquement leurs droits
locaux et ne peuvent pas piloter la simulation.

Les audits et reçus de consommation du ticket suivent **`UNTIL_EXPLICIT_RESET`**,
comme les autres données fictives. Aucune durée réglementaire arbitraire, purge
automatique, facturation ou synchronisation RFQ centrale n'est activée.
`registry_state=NOT_CONFIGURED`, `billing_enabled=false` restent explicites.

## Sessions et bascules

Le jeton et l'installation active sont dans **`sessionStorage`**, propre à chaque
onglet. Les anciens jetons partagés dans `localStorage` ne sont pas importés.
Les appels métier ne peuvent injecter le jeton dans une URL externe arbitraire.
Les requêtes en cours sont annulées lors du remplacement de la session ; une
réponse tardive d'un ancien contexte est rejetée.

Une bascule prépare et vérifie la nouvelle session avant de remplacer l'ancienne.
Elle traite les saisies modifiées par la confirmation commune. Annuler conserve
le contexte et le brouillon. Les stores de pricing existants et un suivi conservateur
des contrôles édités couvrent les modifications ; ce suivi peut encore demander
confirmation après une sauvegarde dans certains formulaires sans état de brouillon
explicite. Leur raccordement fin est à poursuivre, sans promettre un autosave universel.

Après confirmation, un rechargement complet détruit tous les stores, composants,
timers et états du contexte précédent. Il évite qu'une nouvelle identité hérite
des données privées gardées en mémoire. Les avertissements natifs de fermeture
ne peuvent pas laisser l'ancien document actif sur la nouvelle session une fois
la bascule explicitement confirmée.

Entre organisations, retour systématique à l'accueil : aucun identifiant local de
dossier n'est transporté. Dans la même installation, les routes de dossier prises
en charge sont conservées uniquement après un contrôle serveur avec le nouveau
compte. Les identifiants/paramètres non reconnus reviennent à l'accueil. Les
profils sans pricing reviennent à l'accueil depuis le Pricer ; leurs projections
de booking restent à construire à l'étape 5.

Login, annuaire et sélecteur sont bornés à la fenêtre, avec scroll interne et
modale `BaseModal` existante. Le contexte métier utilise aussi un conteneur de
fenêtre avec scroll interne. Les formats numériques existants sont préservés.

## Utilisation locale

Depuis la racine :

```powershell
.venv/Scripts/python.exe scripts/manage_hybrid_dev.py start --developer-access
```

Ouvrir **http://127.0.0.1:8100/#/login**, puis choisir une carte. Un second onglet
sur la même URL ouvre une session indépendante. Après les essais :

```powershell
.venv/Scripts/python.exe scripts/manage_hybrid_dev.py stop
```

Le lancement sans `--developer-access` conserve uniquement les connexions normales.
`start` refuse de changer le mode d'un service déjà actif. Le mode Vite utilise
le portail central sur le port 8100 ; pour une autre plage de ports, utiliser le
frontend servi par le portail concerné ou adapter explicitement le proxy Vite.

Les commandes `scripts/reset_hybrid_legacy.py inventory` puis `apply` concernent
le retrait initial des anciens jeux identifiés. Elles ne réinitialisent pas les
books du nouveau runtime ; le reset opérationnel complet appartient à l'étape 8.

## Preuves et limites

- **28 tests backend ciblés réussis** : installations, bootstrap et accès développeur.
  Complément de nettoyage : **5 tests ciblés réussis**, incluant modifications
  d'inventaire, fichiers versionnés, autre checkout et service actif. Aucun
  lancement de la suite backend complète.
  Revue finale des origines navigateur : les quatre tests d'accès développeur
  repassent, avec couverture explicite du portail `localhost` vers les services
  `127.0.0.1` ; cette passe recouvre les précédentes, elle ne s'additionne pas.
- **434 tests frontend et build Vite réussis**, après les dernières modifications Vue.
  Tests ajoutés : sessions indépendantes, routage direct, annulation des réponses
  tardives et reprise du dossier seulement après autorisation.
- Recette native des **sept services et 25 identités** réussie : accès développeur,
  origine centrale auditée, usage unique, refus de jetons croisés, CORS explicite,
  frontend central servi et absence de Products, calculs conservés, Deals, RFQ,
  études, portefeuilles, notes, jobs et traitements dans les bases manuelles.
  Preuve : `.runtime/hybrid-saas/access-acceptance.json`.
- Recette navigateur réussie : sept cartes, Leonteq et BNP simultanément,
  rechargement BNP sans changement de compte, bascule Front puis Opérations,
  annulation conservant un brouillon, abandon confirmé, retour Admin et retour
  super utilisateur. Capture : `tmp/hybrid-access-uat/login.jpg`.
- Recette visuelle observée en **1280 × 720** : login et modale dans la fenêtre,
  accueil avec scroll interne. La demande de petit viewport n'a pas été appliquée
  par le navigateur de recette ; petits formats à vérifier séparément.

Les services lancés pour cette recette sont arrêtés ensuite avec suivi des
identités de processus et vérification des ports. Les services ne restent pas
actifs sans demande explicite de Philippe.
**Arrêt confirmé : sept serveurs quittés, sept ports libérés**, sans processus
`backend/run.py` restant. Le frontend et les preuves restent disponibles sur disque.

| Étape | État à la reprise |
| --- | --- |
| 1–2 | Socle et initialisation livrés, conservés |
| 3 | Retrait initial ciblé exécuté ; preuves statiques/hors périmètre préservées |
| 4 | Login commun, sélecteur, accès de développement audités et sessions par onglet livrés |
| 5 | Partiel : lanceur, Admin complet, supervision locale et accès simulation raccordés ; partage collectif, granularité exhaustive, projection Opérations et supervision complète à réaliser |
| 6 | Relations, accords et canaux RFQ des six installations à configurer |
| 7 | Registre central, reprise/rapprochement et comptage simulé à réaliser ; facturation réelle désactivée |
| 8 | Qualification complète, sauvegarde/restauration, reset des books manuels et atlas actuel à réaliser |

Le prochain lot recommandé est l'étape **5**, en commençant par la reprise d'un
dossier par un collègue habilité et le parcours Opérations. Les contrôles métier
RFQ/booking livrés restent appliqués ; leur présence ne vaut pas recette complète
des nouveaux profils dans tous les modules.
