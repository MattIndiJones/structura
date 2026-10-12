# Simulation entre agents — pilotage des campagnes

Date : 12/10/2026. Première livraison de consolidation du jeu de simulation.
Prolonge le [cadrage multi-Structura](MULTI_STRUCTURA_AGENT_ACTION_PLAN_2026-10-08.md)
et le [rapport de livraison initial](MULTI_STRUCTURA_AGENT_IMPLEMENTATION_2026-10-09.md).

## Finalité

Hector, banques et client restent des utilisateurs de leurs Structura distincts.
Le pilote organise le temps et conserve les preuves ; les décisions commerciales
restent celles des IA. Le résultat commercial, les erreurs et les fonctions
utilisées sont présentés séparément. Une période terminée ne qualifie pas toutes
les fonctions de Structura.

## Parcours utilisateur

Accès : **Administration → Simulation entre agents**, ou la carte de l’accueil.
Les routes existantes `/admin/agent-workshop` et `/agent-workshop` sont conservées.
Les campagnes restent privées à leur propriétaire, y compris depuis l’entrée admin.

- Créer une campagne, puis démarrer explicitement les IA.
- Suivre le bloc Maintenant sur tous les onglets : acteur, décision, requête,
  date du jeu, mois parcourus, durée réelle cumulée et budget restant.
- Pause/Reprendre conserve les installations et les opérations ; Arrêter les ferme.
- Dans **Gérer cet essai**, Recommencer crée une référence DRAFT aux mêmes paramètres,
  avec comptes, contrats et books vierges. L’ancien essai reste dans la liste et
  `replay_of` relie le nouvel essai à sa source. Aucun démarrage automatique.
- Supprimer retire l’essai de la liste avec sa sauvegarde locale sous `_archive/`.
  Recommencer et Supprimer exigent un contrôleur arrêté ; les contrôles de fermeture
  et verrous entre processus sont conservés. L’ancien POST reset reste compatible.
- Rechercher les campagnes par nom/référence et état. Sur mobile, le bouton
  Campagnes ouvre leur sélection sans repousser le suivi en bas d’une longue liste.
- Rechercher toutes les actions/conversations par texte, acteur et dossier ;
  pagination par 25, numéro original de l’action préservé. Aucun ancien événement
  n’est rendu inaccessible par les anciens seuils de 120/160 entrées.

La durée réelle inclut préparation et pauses pendant les sessions. Le temps
entre deux sessions arrêtées n’est pas compté. Les anciens historiques utilisent
uniquement leur durée enregistrée ; la graine ne garantit pas les mêmes décisions IA.

## Erreurs et diagnostics

Le registre conserve le constat original. Le propriétaire peut qualifier un point,
le mettre en cours d’analyse, le clore ou le rouvrir avec un diagnostic. Une
qualification ou clôture exige un motif. L’historique des décisions est conservé.
Une clôture humaine ne signifie pas une correction du code ou une recette automatique.

Les annotations sont écrites atomiquement dans `issue_reviews.json`, séparément
du journal du contrôleur : une campagne CLI active ne peut pas les écraser.
Elles figurent dans l’export JSON et l’export texte. Authentification, propriété et
interdiction du pilotage depuis une installation acteur s’appliquent aussi au PATCH.

Une pause distingue demande utilisateur, erreurs répétées, attente sans dossier
clos et rapprochement en défaut. Un budget épuisé propose de préparer une campagne
avec un budget éditable ; aucune augmentation ni reprise ne se fait implicitement.

## Faits natifs et rapprochement

Après reconnexion, écriture API libre ou clic navigateur, les relations et le
journal d’exécutions sont relus via les API authentifiées. Les exécutions liées
aux références de dossiers connues rejoignent le suivi. Les autres sont identifiées
UNMAPPED ; aucune nouvelle demande ou acceptation n’est inventée à partir d’elles.
Une relecture échouée conserve les faits précédents et marque l’incertitude.

Le contrôle vérifie unicité des jambes, acteur, rôle bancaire, parties, sens,
instrument, nominal, devise, prix, dates et empreinte contractuelle entre books.
Si un accord est présent, il vérifie aussi banque/émetteur et prix accepté.
Une preuve matérielle absente donne UNVERIFIED, un écart donne MISMATCH ; seul
COMPLETE contribue au volume client et aux parts bancaires rapprochées.
Un dénominateur nul donne une part non calculable. Un booking après refus est un écart.

Un rapprochement incohérent suspend la campagne et conserve un incident lié au
dossier. Books et risques présente écritures, écarts attendus/observés, dernières
positions et fonctions utilisées ; les données natives détaillées restent accessibles.
Les banques ne reçoivent plus les refus concurrents ni les références internes RFQ/CRM
d’Hector dans le contexte partagé du dossier.

## Qualification

- 47 tests backend ciblés : workshop, gestion et rapprochement, bases temporaires.
- `npm run build` : 379 tests frontend, compilation Vite réussie.
- `scripts/check_workshop_management_ui.py` : création d’essais temporaires,
  champs/filtres, confirmation, reprise vierge conservant l’historique, suppression
  jusqu’au dernier essai, refus sur contrôleur actif, sauvegarde et largeur 390 px.
- `scripts/check_workshop_pilot_ui.py` : journal de 201 actions/messages,
  recherche de l’ancien incident, pagination, diagnostic persistant/export,
  rapprochement et doublon, états exécution/pause/reprise/arrêt, budget et mobile.
  Les phases affichées sont des fixtures explicites. Aucun modèle n’est lancé par ces scripts.
- `scripts/check_agent_workshop.py --template phoenix --with-sg` : cinq installations
  privées, inscription écran, contrats, refus CA, choix motivé de SG plus chère,
  CCR hypothétique, CRM, quatre écritures, règlements, fixings et clôture à échéance.
  Campagne de recette `64b211f7d1d94d5db24c77d4b41650bc`, répertoire temporaire
  `structura-adapter-check-jdo3ccl9`. Ce parcours impose les décisions.
- Court essai avec le modèle réel `qwen2.5-coder:7b`, campagne
  `5a42003fb54147e2aacb204ebe06d993` sous le répertoire temporaire
  `structura-pilot-ai-i7s2gb5r` : 31 décisions, 32 appels modèle, inscriptions,
  relations, besoin client, CRM et idée commerciale. Arrêt à la limite de huit
  minutes, fermeture comprise en 501,69 s : zéro booking, zéro volume. Un timeout
  initial et deux signalements IA répétés sont conservés. Ce contrôle limité ne
  qualifie pas une campagne commerciale autonome complète. Le message utilisateur
  des timeouts a ensuite été explicité, avec détail original et test ciblé.

Exécution depuis la racine du dépôt, Python de `.venv`. Les recettes UI peuvent
utiliser `STRUCTURA_TEST_OUTPUT` pour déposer leurs captures hors du dépôt.
Playwright 1.63 et son Chromium ont été installés dans l’environnement local.
La suite backend complète n’a pas été lancée.
L’empreinte de la base principale avant/après les recettes finales est identique :
`AFEEF093C4AC7ED1D8A97A4C9DB9084B270561DD84BA5B0633ABED70842B5F78`.

## Limites et suite

Cette livraison couvre le pilotage, les diagnostics, le journal et la consolidation
du rapprochement. Elle n’ajoute pas d’horloge événementielle, de nouveaux clients,
de couverture OTC bookée, de défaut/collatéral, ni de rejeu déterministe de décisions.
La synchronisation libre couvre relations et exécutions des dossiers connus ;
l’import de RFQ et structures arbitraires reste à spécifier. Les contrôles de prix
numériques indépendants et le rapprochement des flux de vie restent à développer.
La fonction utilisée n’est pas une assertion quantitative passée.

## Consolidation de l’autonomie après lancement réel

La demande suivante est de terminer une campagne avec les vrais agents, jusqu’au
booking et au suivi de vie. Les premiers essais ont montré deux défauts du pilote :
un ancien conseil sur un timeout était réinjecté comme obstacle après rétablissement,
et une exploration client appelait une route inventée `/api/ccr`. Le superviseur
présentait ensuite ce 404 comme une indisponibilité à attendre.

Corrections mises en place :

- Chargement préalable du modèle Ollama, séparé des décisions utilisateurs. La
  réponse de préparation n’exécute aucune action et ne remplace aucune décision IA.
- Conseils d’erreur présentés seulement tant que la dernière opération reste en
  échec ; les corrections commerciales restent disponibles et l’historique complet
  est conservé. Un timeout du modèle n’est pas une tâche métier envoyée au superviseur.
- Avancement calculé sur les faits de workflow modifiés, plutôt que sur un message,
  un signalement ou une consultation réussie. Après deux opérations passives sans
  avancement alors qu’une tâche est prête, une décision métier est requise ; banque,
  marges, refus et acceptations restent libres. Une nouvelle erreur permet le diagnostic.
- Acteurs en attente sans nouvelle tâche ni nouveau message laissés au repos.
- Appels API libres proposés après découverte via l’OpenAPI de l’installation.
  Leur schéma borne méthode et chemin aux opérations découvertes ; les contrôles
  de droits et de préconditions restent ceux des API natives.
- Contexte plus compact : les reçus complets restent dans le journal, les termes
  contractuels et identifiants utiles restent visibles pour la décision. Les pièces
  pricing volumineuses ne sont plus dupliquées dans chaque message.
- Le superviseur distingue un chemin absent de l’OpenAPI d’un serveur indisponible.
- Une consultation OpenAPI du superviseur ne charge pas les capacités de l’acteur.
  Les pièces sans rapport avec la revue commerciale ne sont pas dupliquées dans
  son contexte ; les détails originaux restent conservés dans l’installation.
- Les coupons et barrières du contexte sont projetés en pourcentage, dans les
  mêmes unités que request/propose. Le moteur et les contrats figés gardent leurs
  fractions. Une observation à 8 % ne devient plus un nouvel argument 0,08 % à
  cause de l’exposition d’un COUPON moteur 0,08. Aucune décision existante n’est corrigée.
  Le contexte rappelle aussi que la barrière ne plafonne pas la perte de capital.

Les 57 tests backend ciblés passent après ces corrections. Aucun fichier Vue
n’a été modifié pendant cette consolidation ; le build précédent reste applicable.
Le CLI accepte le propriétaire, le nom, le timeout et une racine de campagnes
isolée via `STRUCTURA_WORKSHOP_ROOT`, sans ouvrir la base utilisateur.

`scripts/check_workshop_campaign.py` qualifie en lecture seule les bases natives
d’un essai terminé : quatre jambes et empreintes contractuelles, règlements,
liaisons Product, valorisations archivées, fixings sourcés, résolutions appliquées,
suivi à la dernière date, provenance modèle de chaque décision, stabilité des
sources et absence de reprise humaine. Il peut comparer l’empreinte de la base
principale à celle relevée avant l’essai.

L’essai de diagnostic `6006f0db80d947ddb9e68477b3e6f1d1` est conservé avec son
404 et son arrêt explicite avant booking. Ses cinq installations ont été fermées
et leurs ports vérifiés libres. Il n’est pas présenté comme une recette autonome
terminée.

L’essai `52d4087a34e74074b805e992af5e5aa0` a permis de mesurer le chargement
involontaire des schémas via le superviseur ; il est conservé arrêté avec zéro
échec opérationnel et zéro booking. L’essai `f6d2d6e4e3e14e62bcbefd70c7ce7417`
a atteint automatiquement le deuxième mois : un dossier de 10 M€, quatre jambes
rapprochées, règlements et valorisations natives. Il a ensuite révélé la dérive
d’unité du coupon entre le premier et le deuxième besoin. Arrêté pour cette
correction, il ne qualifie pas l’année complète ; ses contrats sont conservés.
Les installations de ces deux diagnostics ont été fermées et leurs ports vérifiés libres.

Les listes de résultats API volumineuses conservent également leur bornage à
2 600 caractères dans le contexte, avec indication de la preuve complète sauvegardée.
Le test de non-régression vérifie que le reçu original n’est pas tronqué dans le journal.
L’essai préparatoire `1aaff58632464e2295ca1d4139522ccc` a été fermé avant booking
pour inclure cette vérification dans la version figée de la campagne annuelle.

L’essai `8c6376d9ae5a432586e362f54512cdb7` a atteint automatiquement le troisième
mois, avec deux dossiers (reverse convertible et Phoenix), 20 M€ rapprochés,
huit écritures et zéro échec opérationnel. Les deux coupons moteur étaient bien
0,08, confirmant la correction d’unité en situation réelle. Il a aussi montré
des confirmations répétées après clôture d’une tâche et un contexte plus volumineux
au fil des dossiers ; il est conservé arrêté, sans qualification annuelle.

Le pilote conserve désormais le propre refus de la banque dans `my_declined`,
sans lui divulguer les refus concurrents. Après deux opérations passives sans
avancement, sans tâche prête ni nouveau message, seul wait reste proposé. Un
nouveau message, une tâche ou une erreur permet de reprendre le travail.
Le contexte présente les dossiers du mois et les bookings incomplets ; à défaut,
le dernier dossier aide à préparer le besoin suivant. Les revues lisent toujours
tout le book natif, et l’historique complet reste sauvegardé et consultable.

Le CLI accepte `--deadline-minutes 0` pour attendre la fin de la période, un
budget épuisé ou un blocage réel, plutôt que d’arrêter un essai à cause de la durée
réelle des appels modèle. Les garde-fous d’erreur, d’attente et de rapprochement
restent inchangés. Les cinq ports de cet essai de diagnostic sont vérifiés libres.

Le vérificateur a également été exercé sur la recette aux décisions imposées
`64b211f7d1d94d5db24c77d4b41650bc` : ses bases natives sont lisibles, ses preuves
de valorisation/fixing/résolution sont retrouvées, mais la qualification autonome
est rejetée pour absence de décisions modèle et d’exécution annuelle vierge.

Pour utiliser le lot : redémarrer le backend habituel et recharger la page.
Les installations de qualification sont fermées ; la base principale ne sert pas
aux essais et aucune campagne utilisateur existante n’est réinitialisée ou supprimée.
