# Vérification des corrections — pilote du 13/10/2026

Campagne : `b6587833a2ee4e3a8ea11f269e20644f`.
Branche : `codex/hybrid-saas-foundation`, HEAD `7dce302` et modifications locales.
État final : **STOPPED**, contrôleur inactif. Qualification : **BLOQUÉ avant connexion**.

## Exécution et résultat

Nouvelle campagne isolée, mêmes paramètres métier et modèle Qwen2.5-Coder 7B
que le premier pilote, avec une limite de dix minutes réelles. Les services
Admin et plateforme ont été démarrés pour cette recette ; les six installations
d'essais manuels n'ont pas été lancées.

Le contrôleur a duré **105,39 s** ; le lancement, la surveillance et le nettoyage
ont pris **128,891 s** au total. Le chargement Ollama a pris **51,547 s**.
Les cinq installations acteurs ont démarré. Ensuite les décisions ont échoué
immédiatement avec :

`asyncio.run() cannot be called from a running event loop`

La surveillance a demandé l'arrêt dès sa première observation de l'erreur.
La boucle du contrôleur avait déjà enregistré **16 tentatives en échec**, sans
exécuter de décision commerciale, et 17 incidents. Le compteur `model_calls=16`
compte ces tentatives ; il ne prouve pas 16 réponses du modèle. Aucun des cinq
comptes agents n'a été inscrit ou connecté. Les bases contiennent zéro desk,
membership, opportunité, RFQ, Product et Deal.

## Cause et correction limitée

**PILOT-06 — P1, défaut du pilote** : le correctif d'annulation HTTP Ollama utilisait
`asyncio.run()` dans le thread où l'interface synchrone Playwright maintient déjà
une boucle asynchrone. Le préchargement du modèle, effectué avant Playwright,
réussissait ; les appels de décision après ouverture de Playwright échouaient.

Le code détecte désormais la boucle existante et exécute uniquement l'attente
HTTP Ollama dans un thread séparé. Les opérations navigateur restent dans leur
thread initial. Aucun changement de payoff, de calcul ou de contrôle RFQ.

Diagnostic ponctuel après correction, **sans acteurs et sans nouvelle campagne** :
un appel réel de préchargement Ollama avec Playwright actif réussit en **0,140 s** ;
une requête déjà annulée est refusée en **0,016 s**. La syntaxe Python et les
espaces du diff sont corrects. Ces vérifications ne démontrent pas encore une
décision commerciale ni l'annulation d'une inférence déjà engagée.

## Arrêt et couverture restante

Demande d'arrêt le 13/10 à 16:26:36 UTC ; état final confirmé après **5,719 s**.
La phase publiée était `THINKING`, mais l'erreur empêchait l'appel de décision
Ollama : ce délai mesure la fermeture du pilote, pas une inférence annulée.
Les services Admin et plateforme ont ensuite fermé en parallèle en **4,765 s**.

Vérification système : **zéro processus de cette recette restant**, zéro écoute
sur les sept ports utilisés. Les serveurs, leurs lanceurs, le script de pilotage
et celui du diagnostic ont quitté. Aucun processus préexistant n'a été arrêté.

| Objectif | Qualification |
| --- | --- |
| Démarrage des cinq installations privées | Exercé |
| Connexion, desks et droits | Non exercés, blocage avant `register` |
| Création RFQ avec desk/client/mandat | Non exercée |
| Rejeu sans opportunité/RFQ dupliquée | Non exercé |
| Fermeture parallèle des instances actives | Exercée ; 5,719 s pour le pilote |
| Annulation pendant une inférence Ollama | À vérifier ; annulation préalable seulement vérifiée |
| Cotation, acceptation, confirmation, booking et paiement final | Non exercés |
| Transport RFQ natif entre installations et registre central | Toujours à raccorder et qualifier |

Prochaine reprise : nouvelle campagne courte avec ce correctif, création de la
première RFQ, pause, rejeu dirigé par UI/API sans nouvelle écriture métier, puis
arrêt pendant une vraie décision IA. Ne pas relancer la campagne arrêtée ni
effacer ses preuves. Les incidents restent ouverts jusqu'à cette qualification.

Preuves conservées dans le runtime privé : `campaign.json`,
`corrections-session.json`, `corrections-before-stop.json`,
`corrections-export.json`, `corrections-db-summary.json`,
`corrections-result.json`, `corrections-process-verification.json`,
`corrections-loop-diagnosis.json` et journaux serveurs, sous :

`.runtime/hybrid-saas/admin-workbench/campaigns/b6587833a2ee4e3a8ea11f269e20644f/`

Les scripts ponctuels restent dans le runtime ignoré. Les suites backend et
frontend restent suspendues. Aucun commit, push ou merge.

## Réutilisation du catalogue existant

Règle confirmée par Philippe : avant de créer une contrepartie, relire le
catalogue de l'installation et réutiliser l'objet existant avec son identifiant
local. Ne pas réinitialiser ni remplacer le catalogue lors d'une reprise.

Lecture seule des bases Admin et Hector du premier pilote : BNP Paribas,
Société Générale et Crédit Agricole CIB sont déjà présentes, aux identifiants
locaux 10, 11 et 12. Le démarrage les réutilise ; seuls Hector et le client
fictif, absents du catalogue initial, sont ajoutés dans les bases acteurs.
Ces identifiants restent propres à chaque installation et ne constituent
pas des identifiants globaux entre organisations.

Le démarrage refuse désormais toute lecture de catalogue en échec avant une
création ; il ajoute immédiatement les noms créés à son index et évite les
PATCH de fournisseurs RFQ lorsque leur contrepartie et leur mode sont déjà
corrects. Syntaxe vérifiée uniquement ; aucune nouvelle simulation lancée
pour cette modification. Une nouvelle campagne crée toujours ses propres
bases isolées : réutilisation du catalogue et reprise d'une installation
existante sont deux opérations distinctes.
