# F04 — générateur UAT, calendrier et fixings — 23 octobre 2026

**Les neuf échecs documentés F04 sont résolus localement.** La sélection finale passe **55 cas distincts : 37 tests du générateur, dont 4 nouveaux, et 18 tests voisins**. Le solde courant devient **111 cas documentés dans 5 groupes ouverts** ; les autres groupes n’ont pas été relancés.

Le diagnostic distingue les fixtures invalides des défauts applicatifs mis en évidence lors de leur requalification. [Preuve structurée](remediation-lot-0-2026-10-20/F04_VALIDATION.json) · [Registre courant des échecs](remediation-lot-0-2026-10-20/FAILURE_REGISTER.json).

## Diagnostic des neuf cas initiaux

Les neuf cas sont reproduits sur la source initiale dans un environnement isolé, avec les HTTP externes bloqués : [baseline XML](../../.runtime/diagnostic-acceptance/f04-2026-10-23/baseline.xml).

| Cas initiaux | Cause observée | Correction |
|---|---|---|
| 1 — chaîne complète et préservation du Deal hors lot | La fixture crée un Product puis un Deal avec version 1, sans créer cette version. Le garde C06 refuse avant tout appel au générateur. | Construction d’un Product canonique avec termes réellement persistés, sous-jacent et contrepartie valides. Garde SQL conservé. |
| 7 — observations et S0, suivant le profil | Les tests attendent des cours Yahoo réels sans simuler le fournisseur. En environnement hors réseau, aucune clôture ne peut être officialisée. | Injection de barres datées et de métadonnées de séance au seul point d’entrée fournisseur ; horloge fixée. Le pricing, les contrôles C13 et le rejeu restent réels. |
| 1 — mélange des huit profils et dépendances terminales | Même dépendance à un flux réel ; le test exige des versions officielles et résolutions qui ne peuvent pas exister sans données qualifiées. | Même flux déterministe, puis génération et nettoyage des huit profils avec clés étrangères actives. |

La baseline contient **23 tentatives HTTP bloquées**, sans récupération externe effective. Après correction des fixtures, ces cas passent sans tentative HTTP. Aucun cours synthétique, S0 par défaut ou valeur zéro n’est ajouté au générateur en fonctionnement.

Le test de cours compare maintenant chaque valeur persistée à la barre datée fournie pour le bon sous-jacent, vérifie la version officielle associée et exclut les événements annulés après résolution. Il ne se contente plus de constater qu’un dictionnaire de spots est non vide.

## Défauts applicatifs supplémentaires reproduits et corrigés

Quatre nouveaux tests sont écrits après la requalification des fixtures et exécutés sur le générateur initial : **4 échecs valides** dans [reproductions.xml](../../.runtime/diagnostic-acceptance/f04-2026-10-23/reproductions.xml). Ils passent ensuite dans [core-final.xml](../../.runtime/diagnostic-acceptance/f04-2026-10-23/core-final.xml) et dans la sélection finale du générateur.

| Défaillance reproduite | Comportement corrigé | Interaction préservée |
|---|---|---|
| Panne totale : une observation due, mais `missing_fixings=0`, audit SUCCESS et source déclarée officielle. | Comptage de la couverture officielle effective, statut FAILED et audit ERROR sans données annoncées officielles. Aucun S0 inventé. | C11/C13, provenance et finalité. |
| Historique réduit au strike : le préfixe est officiel, mais les observations suivantes manquantes sont annoncées à zéro. | Le préfixe officiel est conservé ; disponibilité, manquants et statut PARTIAL sont explicites. | C13, autorité du registre et conservation des faits acquis. |
| Erreur injectée après préparation d’un fixing : l’appel direct au corps privé de refresh est intercepté puis le lot valide les écritures préparées. | Appel au `refresh_deal_core` public, qui rollback, publie l’erreur et conserve le Deal booké. Aucun fixing partiellement officialisé ne subsiste après cette erreur technique. | C13/C26, transaction et diagnostics. |
| Date USD du 29/03/2027, lundi de Pâques TARGET : après booking, l’ancien helper EUR déplace l’événement au 25/03 malgré le calendrier figé au 29/03. | Suppression du réalignement après booking. Le calendrier C05, sa devise, les dates et paiements issus du contrat restent l’autorité. | C05/C06, calendrier figé et identité des termes. |

Le code applicatif modifié se limite à [uat_generation.py](../../backend/app/services/uat_generation.py). Les autres changements de code sont dans [test_uat_generation.py](../../backend/tests/test_uat_generation.py). Le moteur quantitatif, les règles de finalité, les limites de crédit, les permissions et les migrations ne sont pas modifiés.

## Sémantique des résultats

Le statut COMPLETED du lot conserve sa signification : **les objets demandés ont été créés**. La disponibilité des fixings est distincte et apparaît dans chaque scénario :

| État de fixing | Signification |
|---|---|
| NOT_DUE | Aucune observation contractuelle atteinte ; aucun chargement inutile. |
| SUCCESS | Toutes les observations dues sont officiellement qualifiées, sans erreur signalée. |
| PARTIAL | Préfixe officiel disponible ou observations encore non qualifiées ; lacunes/erreurs explicites. |
| FAILED | Erreur de refresh sans observation officielle disponible. Le dossier créé reste consultable. |

`official_fixings` conserve le nombre de nouvelles officialisations de ce refresh. `available_fixings` mesure les événements dus possédant une version officielle validée/appliquée ; `missing_fixings` mesure les autres. Les événements annulés après rappel/résolution ne sont plus comptés comme attendus. L’audit reprend l’état et les compteurs ; une absence totale de faits officiels n’est pas étiquetée FIXING_OFFICIAL.

Les profils règlent la chronologie de l’étude ; le payoff évalué sur les fixings qualifiés décide de l’issue réelle. Aucun scénario CALLED ou MATURED_KI ne force artificiellement un résultat. Les cours disponibles restent ceux de la chaîne de données existante, qui conserve sa priorité de cache et ses contrôles C13 : clôture publiée sans délai ajouté, places/fuseaux établis et report borné à trois jours calendaires.

## Validation ciblée exécutée

| Sélection finale | Résultat |
|---|---|
| [Fichier du générateur](../../.runtime/diagnostic-acceptance/f04-2026-10-23/generator-final.xml) | **37 succès**, 0 échec/erreur/ignoré ; durée affichée 124,02 s. |
| [Voisins C05/C06/C08/C13](../../.runtime/diagnostic-acceptance/f04-2026-10-23/dependencies-final.xml) | **18 succès**, 0 échec/erreur/ignoré ; durée affichée 8,57 s. |
| [Union dédupliquée](../../.runtime/diagnostic-acceptance/f04-2026-10-23/qualified-distinct.xml) | **55 identités distinctes** ; manifeste dérivé, pas une exécution supplémentaire. |

Les 37 tests couvrent les modes d’entrée, les quatre familles du catalogue, le Product unique et ses calculs, les huit profils, les cours/S0, les cas RFQ de contrôle, les jours de semaine et week-end, les historiques/Greeks demandés ainsi que les nouvelles régressions. Les adaptations de fournisseur restent au niveau du test : ni prix, ni statut de fixing, ni résultat de rejeu ne sont remplacés par une réponse préfabriquée dans les cas de fixing qualifié.

Les deux nettoyages principaux fonctionnent avec **foreign_keys=ON** et contrôlent l’absence de violations référentielles. Ils vérifient les versions/fixings/propositions et le pointeur de valorisation terminal ; le Deal et le Product natifs hors lot restent identiques. Le test voisin C08 confirme le nettoyage d’une filiation UAT et la conservation du tombstone d’une commande réussie, sans réutiliser le booking supprimé.

Les voisins C05 vérifient la cohérence aperçu/Product/pricing/booking et la restitution inchangée d’un calendrier ancien. C06 conserve une RFQ historique non qualifiée sans inventer de version. C13 revalide les séances, l’absence de délai ajouté, la limite de report J+3/J+4, la conservation des fixings officiels en panne et le rollback/retry des décisions.

Toutes les sélections finales ont leurs HTTP externes bloqués et **zéro tentative**. Les tests partent de la racine, avec `STRUCTURA_*` hérité retiré, un répertoire de données temporaire et un secret JWT de test. Les workers de pricing utilisent le lanceur Windows protégé par `__main__`. Aucun serveur ni service d’IA n’est lancé. La suite backend complète et le frontend ne sont pas relancés ; aucune interface Vue ne change.

## Suivi, préservation et limites

Le registre courant clôture F04 pour ses **9 identités initiales**, conserve F02 résolu et laisse **111 cas ouverts dans 5 groupes**. Les quatre nouvelles régressions qualifient cette correction ; elles ne sont pas ajoutées artificiellement au nombre de défauts du registre initial.

Les [inventaires figés de l’étape 1](REFERENCE_CONSOLIDATION_2026-10-23.md), les preuves C01-C27 et le [rapport F02](REMEDIATION_F02_2026-10-23.md) restent inchangés. Le registre structuré et ses vues courantes renvoient au nouveau suivi. La référence technique est la copie de travail identifiée par les empreintes de F04, sur la même branche et le même HEAD ; aucun commit ni push.

Cette validation utilise des données simulées dans des bases isolées. Elle ne qualifie ni Yahoo en réel, ni le parcours graphique, ni un déploiement, ni tous les modèles quantitatifs. Aucun portefeuille utilisateur ni base métier réelle n’est ouvert ou modifié. Les autres 111 échecs documentés restent à instruire séparément.
