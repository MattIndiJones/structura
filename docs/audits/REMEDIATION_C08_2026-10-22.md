# C08 — Idempotence des commandes et filiation

Livraison locale du **22 octobre 2026**, sans commit ni push. Les trois constats
C08 sont corrigés sur le périmètre testé. Branche `codex/hybrid-saas-foundation`,
HEAD `7dce3021a88feb4f0021ca3de8f3596277bc72a5`. Aucun serveur lancé, aucune
migration de données d’exploitation exécutée, aucune lecture de la base réelle.

## Résultat métier

| Constat | Comportement obtenu | Validation |
|---|---|---|
| M04-06 | Une conservation Product garde sa clé après une erreur réseau, un remontage du store ou une réponse JSON tronquée. Deux clics simultanés partagent la même commande. Après confirmation, une nouvelle conservation intentionnelle reçoit une autre clé. | Réponse perdue après succès simulé, nouveau store, double clic, ordre JSON différent, reprise des calculs et des révisions de termes. |
| M11-04 | Le booking conserve atomiquement la commande et son Deal. Rejouer le même contenu retrouve le même Deal et le même Product, sans rejouer les limites, événements, versions et audits de création. Un contenu divergent sous la même clé est refusé et audité. | Deux sessions concurrentes sur SQLite temporaire avec clés étrangères ; un seul résultat. Échec injecté après les étapes métier : aucune position ni commande partielle, puis retry réussi. |
| M11-05 | « Booker un autre deal » crée explicitement un Product distinct relié à l’origine. Les termes choisis sont conservés ; exécution, lifecycle, RFQ, indicatifs, calculs et documents ne sont pas recopiés. Le contexte commercial et la contrepartie sont à confirmer et le prix à relancer. | Nouvelle opération bookée sur le Product dérivé ; source et archive inchangées. Échec de préparation : dossier exécuté conservé et même clé reprise. Réponse tardive ignorée si un autre dossier est ouvert. |

## Sémantique des commandes

Le navigateur conserve dans le stockage de session de l’onglet uniquement des
empreintes SHA-256 et des clés aléatoires. Il ne copie ni payoff, ni montants, ni
jeton dans ce registre. Les commandes sont séparées par utilisateur, installation,
opération et contenu. Le renouvellement du jeton du même utilisateur conserve la
reprise. Un changement de session interdit l’application d’une réponse tardive.
Un échec d’écriture du registre local empêche l’envoi.

La reprise concerne le **même contenu**. Modifier le contenu produit une nouvelle
commande ; après une réponse incertaine, il faut d’abord reprendre la demande
initiale ou vérifier son résultat avant d’émettre une opération différente.
La clé n’est retirée qu’après décodage et validation de l’identité retournée.
Les refus serveur conservent la demande disponible pour une reprise explicite.

Le serveur sérialise la recherche de commande par acteur dans la transaction
SQL. La contrainte d’unicité conserve un second garde-fou. Les commandes Product
existantes conservent leur format et leur révision de résultat ; aucune réécriture
de leurs preuves historiques. Le nouveau journal `booking_commands` est créé
additivement par le `create_all` du démarrage normal. Il n’a pas été créé sur une
base d’exploitation pendant cette livraison.

Les clients actuels envoient une clé explicite au booking. Les anciens appels
sans clé sont dédupliqués sur l’intégralité de leur demande, reçu compris et avec
le périmètre UAT éventuel. Ils doivent fournir deux clés explicites pour exprimer
deux opérations indépendantes strictement identiques. Le journal ne constitue
pas un rapprochement rétroactif des bookings antérieurs à son déploiement.

## Filiation, accès et interactions

- **C01 :** permission de booking et accès au Deal recontrôlés au retry ; commandes
  séparées par acteur et organisation. Les Products dérivés et leurs Deals gardent
  les restrictions de lecture de la source. Les opérations peuvent lire un contrat
  autorisé sans recevoir les droits de pricing. Un Product privé bancaire ne peut
  pas être transformé en dossier ordinaire par cette action.
- **C03/C04 :** les contrôles d’identité juridique, d’exception, de limite et
  d’amendement sont conservés. Un retry ne consomme pas une nouvelle capacité de
  crédit. Le wrapper travaille sur une copie de la demande pour préserver les
  appels natifs qui reprennent le même objet.
- **C06 / T02 :** Product courant v2 et RFQ figée v1 restent distincts. Le retry de
  la création v1 ne fait pas régresser la version courante. La filiation peut
  sélectionner explicitement les termes v1 sans changer le parent v2 ; la révision
  source attendue est contrôlée. L’audit garde origine, révision, version,
  empreinte et identifiants des liens détachés. L’interface permet d’ouvrir la source.
- **C07/C10 :** reprise après remontage du store ; aucun ancien accord RFQ ni
  préremplissage commercial conservé dans la nouvelle opération. Le nouveau prix
  peut alimenter la fair value d’un Product non exécuté dont les termes sont figés.
- **C19 :** les archives et calculs du dossier exécuté restent dans la source.
  Le Product dérivé repart sans ancien résultat qualifié.
- **C20 :** la reprise des recherches conservées reste validée pour les 20 modes
  famille/objectif du panel existant ; aucune modification du moteur Optimizer.
- **C23 / T12 :** une nouvelle clé ne permet pas de booker deux fois un même accord
  confirmé. Une clé de replay RFQ est elle aussi liée au résultat retrouvé.
  La clé technique est exclue de l’empreinte économique de l’accord. Les contrôles
  de révision, devise, clôture, transport signé et isolation des dossiers restent
  exercés par les tests ciblés.
- **C27 :** origine Demo/UAT et lot de recette sont transmis au descendant.
  La suppression explicite d’un lot laisse une commande de booking sans Deal,
  qui refuse toute recréation automatique au retry. Les agrégats historiques
  encore ouverts dans C27 ne sont pas déclarés corrigés par cette livraison.

## Validation et portée des preuves

**317 cas backend distincts, dans 14 fichiers, réussis**, dont **31 nouveaux cas
C08**. Aucun échec, erreur ou skip dans cet ensemble qualifié. Il couvre les
commandes, permissions, transitions Product, exceptions juridiques, amendements,
exécutions RFQ, transport, relations, échanges Product, livraison réseau, C23,
pricing bancaire privé et les 20 conservations de recherches Optimizer.

**697 tests frontend dans 78 fichiers réussis**, dont **16 nouveaux cas**, puis
compilation Vite réussie dans un répertoire temporaire. Le `frontend/dist` présent
au début de la tâche est conservé. Les logs et le manifeste des résultats sont
dans `.runtime/diagnostic-acceptance/c08-2026-10-22` ; les preuves structurées sont
dans [C08_VALIDATION.json](remediation-lot-0-2026-10-20/C08_VALIDATION.json).

Avant correction : 104 tests existants réussis ; la répétition du booking direct
et l’absence de création d’un dossier dérivé ont été reproduites sur deux
configurations d’accès. La perte de clé de conservation a été reproduite dans le
store. Le test du bouton a également été exécuté sur une copie isolée du frontend
initial : le Product exécuté y reste attaché, comme attendu avant correction.

Les appels externes `requests` et `curl_cffi` sont bloqués dans les tests backend
qualifiés : **aucune tentative bloquée** enregistrée. Le transport utilise les
dispositifs de simulation des tests existants, sans services distants réels.
Les bases de concurrence et de cleanup sont temporaires et activent les clés
étrangères. La suite backend complète n’a pas été lancée.

La qualification est **locale**. Elle ne vaut pas recette graphique interactive,
qualification TLS de deux installations déployées, test de charge ni preuve de
migration sur une copie des données d’exploitation. Le stockage de reprise suit
la durée de vie de l’onglet ; sa suppression manuelle ou la fermeture définitive
de celui-ci n’offre pas de restauration automatique de la clé. T02 et T12 restent
partiels au niveau de la qualification déployée. C25, C26 et le solde C27 restent ouverts.

## Conservation

Le manifeste compare tous les fichiers initiaux, les sources sauvegardées et les
preuves C01–C24. Les seuls changements existants admis sont les points de commande,
de filiation, d’accès des descendants, le nettoyage UAT, leurs tests et les quatre
documents de suivi. Aucun commit, push ou service persistant.
