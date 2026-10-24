# Recette des autres accès du launcher — 24/10/2026

Travail local sur `codex/hybrid-saas-foundation`, sans commit ni push.
Suite de la [reprise de l’Admin](LAUNCHER_RECOVERY_2026-10-24.md).

**Complément après la capture de Philippe :** le [changement de compte depuis
Admin seul](ADMIN_ACCOUNT_SWITCH_2026-10-24.md) corrige le démarrage à la demande,
le sélecteur Admin et les retours après erreur. Les résultats A01–A19 ci-dessous
portent sur des services déjà démarrés ; ils ne couvraient pas ce cas à froid.

## Résultat

Les destinations du launcher fonctionnent sur les copies isolées, puis sur les
installations permanentes utilisées par le raccourci. Aucune campagne ni aucun
agent IA n’a été créé ou démarré pendant cette intervention.

| Accès | Résultat obtenu |
| --- | --- |
| Les six organisations | Portail et six services démarrés ; BNP Paribas, Société Générale, Citi, UBS, Leonteq et Kepler Cheuvreux Solutions affichent chacun leur super utilisateur. |
| Une organisation | Les six raccourcis individuels ouvrent automatiquement la bonne identité sur le runtime permanent ; un service actif est réutilisé. |
| Console SaaS | Session `platform_admin`, annuaire de six organisations et état des services affichés. Aucun schéma métier dans la base centrale. |
| Simulation du launcher | Session Admin complète et route `/agent-workshop`, avec les campagnes historiques consultables et les IA arrêtées. |
| Simulation de la console | Contrôleur HTTP séparé, délégation signée et écran chargé ; ouvrir le service ne démarre aucune campagne. |

Les 24 profils métier ont été vérifiés par les API natives dans chacun des deux
environnements : super utilisateur, Front, Opérations et Contrôleur, pour chacune
des six organisations. Leur accès à la simulation est refusé ; un jeton métier
ne donne pas accès à la console ni à une autre installation. L’Admin complet et
l’Admin central gardent leurs périmètres distincts.

## Anomalie corrigée : script de recette périmé

`scripts/check_structura_launcher.py` référençait encore le service supprimé
`compatibility` dans son nettoyage. Une exception masquait ainsi le résultat et
empêchait le nettoyage prévu. Le workspace `admin-workbench`, réellement démarré,
était également absent de ce périmètre. Les assertions centrales attendaient
l’ancien schéma sans table de révocation ; seuls deux organismes étaient exercés.

Le script utilise maintenant les contrôleurs réellement présents, inclut l’Admin
complet et préserve les services préexistants. Il vérifie les six organisations,
les 24 profils, les raccourcis et les deux chemins de simulation. Il n’utilise
aucun endpoint de création, rejeu ou démarrage de campagne. Une option
`--evidence-file` conserve le rapport de cette recette séparément des anciennes
preuves du runtime.

Les tests couvrent chaque raccourci, la séparation console/Admin, l’absence de
campagne à l’ouverture et le nettoyage sur échec, avec conservation d’un portail
préexistant et écriture d’une preuve distincte. Aucun changement du comportement
applicatif, des droits ou des composants Vue n’avait été nécessaire pour ces accès
déjà démarrés. Le complément cité ci-dessus apporte les corrections applicatives
du cas Admin seul, avec de nouvelles preuves B01–B09.

## Validation

- **45 tests backend ciblés distincts réussis** : launcher, bootstrap, accès
  développeur et sécurité de l’identité. Parmi eux, les **14 tests du launcher**
  ont été repassés après l’ajout du chemin de preuve distinct, avec succès ; ils
  ne s’ajoutent pas aux 45. Neuf nouveaux cas couvrent les accès et le nettoyage.
- Deux recettes natives réelles : copies isolées sur les ports 18600–18607/18609,
  puis runtime permanent sur 8000/8100–8107. Neuf services dans chaque recette.
- **19 jalons navigateur** avec DOM et captures, dont les six raccourcis
  permanents, la console et les deux écrans de simulation. Aucune erreur console
  navigateur relevée sur les deux écrans permanents de simulation.
- Huit bases sauvegardées avant leur démarrage. Les huit bases opérationnelles
  sont restées identiques pendant la recette isolée. Après leur démarrage réel,
  les comptes, mots de passe, rôles, identités, desks, droits et dossiers contrôlés
  sont conservés. Migrations additives, états de référentiels, audits de connexion,
  reçus de tickets et journal du scheduler expliquent les différences techniques.
- Les **994 fichiers des campagnes Admin historiques sont identiques** avant et
  après ; le répertoire de campagnes du contrôleur reste vide. Les deux
  répertoires de campagnes isolés restent vides. Les compteurs IA affichés dans
  l’ancienne campagne sont historiques et n’ont pas été augmentés par la recette.
- Arrêt propre des neuf services de chaque recette, avec identité de lancement,
  sortie des processus et libération des ports vérifiées. Les onglets temporaires
  de cette intervention sont fermés. Un nouveau launcher a ensuite démarré ses
  propres services Admin et portail sur 8000/8100 : identités de lancement et PID
  différents, préservés sans arrêt. Les autres applications restent intactes.

La [preuve structurée](remediation-lot-0-2026-10-20/LAUNCHER_ACCESS_VALIDATION.json)
référence les tests, les captures, la conservation et les contrôles d’arrêt. Les
sauvegardes et journaux privés restent dans
`.runtime/diagnostic-acceptance/launcher-access-2026-10-24` ; les copies de recette
dans `.runtime/hybrid-saas/launcher-access-2026-10-24`.

## Portée et suite

Les commandes métier appelées par les boutons du launcher et leurs destinations
navigateur sont exercées réellement. La fenêtre Tkinter elle-même n’a pas été
manipulée par l’automatisation. Il s’agit d’une qualification locale des accès,
pas d’une nouvelle qualification des agents, des modèles, des anciennes campagnes
en diagnostic, des archives ou du déploiement TLS.

Aucune suite backend complète. Cette première phase ne modifiait que la recette
Python et ses tests ; le complément comporte les tests et la compilation Vue
obligatoires pour ses changements. Les preuves antérieures sont
conservées ; les 132 constats, 27 chantiers et 180 cas F01–F21 ne sont pas renumérotés.
