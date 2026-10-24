# C27 — Solde des périmètres Production, UAT et démonstration

Livraison locale du 22 octobre 2026, sans commit ni push.

**M15-03 est corrigé et validé localement.** La séparation Greeks/VaR apportée
par C21 est étendue aux chocs, scénarios de smile, P&L explain, expositions,
barrières, compteurs et historiques. **M16-05 reste couvert par C24**, dont les
tests du véritable import CRM et du scénario combiné T14 sont réexécutés.

Les 27 chantiers du registre disposent désormais de leur livraison locale.
La recette graphique, les scénarios transverses encore partiels, les décisions
métier restées ouvertes et la qualification déployée demeurent distincts.

## Règle de sélection

Production est le défaut. Un deal Production n'a pas de `uat_batch_id` ; un deal
UAT appartient explicitement à un lot. Cette règle existante de C21/CCR est
conservée : aucun classement ne dépend du nom du deal, du portefeuille ou du
mode d'anonymisation de l'interface. Le CRM conserve sa gouvernance des origines
Demo, importées et natives définie par C24.

| Périmètre | Calculs et positions | Historique |
|---|---|---|
| Production | Positions Production visibles selon C01 | Études dont Production et la vue sont enregistrés |
| Recette UAT | Positions explicitement rattachées à un lot UAT | Études dont UAT et la vue sont enregistrés |
| Historique non qualifié | Aucun nouveau calcul dans ce périmètre | Anciennes études dont l'origine ou la vue n'est pas établie |

La visibilité C01 est appliquée avant la sélection d'origine. Les chocs et le
smile reprennent le même book collectif visible que les autres consommateurs ;
ils ne reconstruisent plus une sélection divergente fondée sur le seul propriétaire.
Les historiques de calcul restent privés à leur auteur.

Un produit Production de **1 M€** et un produit UAT de **1 M€** donnent **1 M€**
dans chaque sélection correspondante, jamais un total par défaut de 2 M€.
Un portefeuille peut conserver les deux appartenances : le périmètre de lecture
sépare les positions sans déplacer ni réécrire les contrats.

Le choc d'un deal sélectionné reprend son origine propre. Une origine explicitement
contradictoire dans la requête est refusée. Aucun mode mixte implicite n'est ajouté.

## Calculs et archives

Les nouvelles études de chocs et de smile figent l'origine, les identifiants des
deals, les lots UAT, les nominaux, les devises et les versions contractuelles.
La vue, l'identité et le nom du portefeuille sont conservés dans les paramètres.
Les nouvelles VaR figent aussi la vue globale/portefeuille et son identifiant,
en complément de l'origine et de l'univers déjà enregistrés par C21.

La classification des historiques lit ces paramètres enregistrés. Elle ne relit
pas les appartenances ou les origines actuelles des deals pour requalifier une
étude ancienne. Le filtre est appliqué avant la limite du nombre de résultats.
Les paramètres et résultats archivés ne sont pas modifiés pour leur attribuer
une qualification absente.

Une ancienne VaR portant une origine C21 mais sans vue enregistrée demeure dans
l'historique non qualifié ; son origine initiale reste lisible dans ses paramètres.
Les anciens résultats restent consultables. Aucun prix, seed, moteur ou convention
de rejeu C19 n'est remplacé par cette classification.

La consultation « toutes vues et archives » permet de retrouver les études d'un
portefeuille supprimé. Le détachement de la clé étrangère SQL conserve le JSON
d'origine, son nom de portefeuille et son résultat. Cette consultation ne change
pas le périmètre utilisé pour un nouveau calcul.

## Interface et réponses tardives

La vue Risk présente un choix commun Production/UAT et un choix distinct des
historiques : vue sélectionnée, toutes vues et archives, ou historique non qualifié.
Les compteurs, membres et recalculs de Greeks suivent le même choix que les agrégats.
Les requêtes de chocs, smile, P&L et VaR transmettent ce périmètre.

Les changements de sélection invalident les résultats affichés et le polling VaR.
Une génération de contexte empêche une ancienne réponse de revenir dans une autre
sélection, y compris après un aller-retour Production → UAT → Production. Les
caches d'historique sont séparés par origine et par vue. Les refus HTTP restent
des erreurs visibles, pas des résultats de risque.

Les études de VaR et les lignes d'historique affichent leur qualification. Le
Booking conserve aussi les anciens chocs du deal explicitement sélectionné,
avec leur mention d'historique non qualifié.

## Validation

- Quatre reproductions isolées échouaient avant correction : agrégat par défaut
  mélangé, sélection UAT ignorée, origine/univers non figés et ancienne étude
  présentée dans l'historique Production.
- Baseline des cinq fichiers existants concernés : **27 tests réussis**.
- Validation finale : **65 tests backend distincts réussis sur dix fichiers**,
  dont **26 nouveaux cas C27**, sans échec ni test ignoré dans ce périmètre.
- Les nouvelles fixtures utilisent SQLite en mémoire avec les clés étrangères
  actives. Les routes HTTP et la persistance réelles sont exercées ; les frontières
  quantitatives coûteuses sont simulées dans les nouveaux tests de sélection.
  Les tests économiques existants de chocs/P&L restent également réussis.
- C21 réexercé : défaut Production, UAT explicite, visibilité C01 et refus des
  facteurs VaR incomplets avant soumission. CCR : séparation et nettoyage des lots.
- C24/T14 réexercés : véritable import sur mandat Demo exclu du profil réel,
  rattachements, dates et devises cohérents. C26 : correction officielle et chaîne
  surveillance/alerte/reprise conservées.
- **731 tests frontend réussis**, dont **11 nouveaux**, et `npm run build` réussi
  dans un répertoire temporaire. Les fichiers `frontend/dist` existants sont préservés.
- Les tests backend bloquent requests/curl externes : aucune tentative constatée.
  Aucun serveur ni worker n'a été démarré ; aucune utilisation de la base réelle.

T10 et T14 disposent des preuves locales complémentaires, sans clôture de leur
recette graphique et déployée. Aucun nouveau test de convergence quantitatif,
benchmark de volumétrie ou parcours graphique interactif n'est revendiqué.
La suite backend complète n'a pas été lancée.

Preuves : [C27_VALIDATION.json](remediation-lot-0-2026-10-20/C27_VALIDATION.json).
Sorties brutes, baseline et contrôle de préservation :
`.runtime/diagnostic-acceptance/c27-2026-10-22/`.
