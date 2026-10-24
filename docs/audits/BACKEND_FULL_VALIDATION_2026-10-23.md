# Suite backend complète — correction et validation consolidée

**23 octobre 2026 — exécution expressément demandée, sans commit ni push.**

Le passage final donne **3 943 tests réussis, 3 ignorés conditionnels,
aucun échec ni erreur**, sur 3 946 identités distinctes. Le premier passage
complet avait donné 3 883 succès, 48 échecs, 11 erreurs et les mêmes 3 ignorés.

Les **59 cas supplémentaires** sont résolus et répartis dans **14 suivis
F08–F21**. Les 121 résolutions historiques F01–F07 passent également dans ce
passage final. Le [registre courant](remediation-lot-0-2026-10-20/FAILURE_REGISTER.json)
comporte donc **180 cas documentés résolus localement et 0 ouvert**. Ces nombres
comptent des cas de test, pas 180 défauts métier indépendants ni de nouvelles
entrées parmi les 132 constats de l’audit.

Les [preuves structurées](remediation-lot-0-2026-10-20/BACKEND_FULL_VALIDATION.json)
conservent les résultats, identifiants, dépendances, critères et empreintes.

## Changements applicatifs

**Précision des temps — C14/C18.** Les temps des trajectoires sont retournés à
12 décimales, ainsi que la vie résiduelle publiée par les analyses. L’arrondi
de présentation précédent faisait diverger l’horizon annoncé de celui réellement
simulé, particulièrement sur les maturités d’un ou deux jours. Les prix, tirages,
formules, actualisations et règles de cut restent identiques. Une comparaison
des sources vérifie que le seul changement du moteur concerne la précision
de ces temps retournés.

**Signaux issus de transactions Demo — C24/C27.** Un choix explicite
`include_demo`, désactivé par défaut, traverse désormais les signaux et l’aperçu.
Il pilote la cadence et les événements issus des transactions ; les relances
opérationnelles conservent leur périmètre existant. Le résultat identifie le mode
`real` ou `demo_included`. Le test HTTP sème une organisation isolée et vérifie
l’absence des signaux de dormance/événement Demo en mode réel, puis leur présence
en inclusion explicite. Les droits du viewer et le filtrage d’organisation
restent appliqués.

**Dépendances des services — C06/C08/C19/C23.** Les treize imports inverses
détectés vers les routes sont supprimés. Le chargement de clé est partagé dans
[`instance_signing.py`](../../backend/app/core/instance_signing.py), le contrat
de booking dans [`booking_contract.py`](../../backend/app/core/booking_contract.py),
et les faits/projections/compositions RFQ dans
[`rfq_state.py`](../../backend/app/services/rfq_state.py). Les chemins API restent
disponibles par alias ou délégation. La couche applicative fournit explicitement
la commande native de booking au service de revue RFQ.

Les corps des quatorze définitions RFQ partagées sont identiques à ceux d’avant
extraction. Le contrôle d’architecture couvre aussi les imports absolus. Un
test voisin d’expiration a nécessité d’étendre son horloge simulée au nouveau
service propriétaire ; ses 14 cas d’exécution passent après cette adaptation.

## Fixtures et attentes remises en conformité

- Les scénarios d’atelier, CRM, pricing, dictée et aperçu utilisent les rôles
  autorisés. Les parcours HTTP corrigés passent par des JWT réels et des
  utilisateurs persistés ; aucun remplacement par un objet sans identité.
- Les bookings concernés désignent une contrepartie active avec son identifiant
  juridique. Les refus de rattachement étranger sont atteints après satisfaction
  de ce prérequis. Les contrôles C01/C03 restent appliqués.
- Les migrations de test créent les tables manquantes avant l’upgrade des
  colonnes/gardes, comme le démarrage normal et la correction F02. Aucune migration
  applicative n’a été changée.
- Les calendriers allant du 10/09/2026 au 10/09/2029 utilisent leur horizon
  ACT/365,25 réel. Les derniers blocs étaient légitimement hors du précédent
  `T=3`. Les tests vérifient maintenant leurs trois observations, l’ordre et STOP,
  ainsi que les deux niveaux d’une même date, en conservant le cut strict.
- Les fixtures Local Vol emploient un smile non plat admissible. Les domaines
  C17 et leurs refus restent inchangés ; aucun écrêtage ni fallback n’a été ajouté.
- Le diagnostic de réparation de corrélation utilise un cas légèrement non PSD
  qui nécessite réellement une réparation. Les copies exactement corrélées
  restent sans jitter, conformément à C16.
- Les contextes d’archive portent un calendrier résolu ; le worker reçoit son
  taux explicite. Les mocks d’historiques acceptent et contrôlent la convention
  non ajustée et les données partielles demandées par la watchlist.
- Une requête de repricing contradictoire exige maintenant le refus précis
  `RFQ_PRICING_FIELDS_FORBIDDEN`, avec absence de modification partielle.
  La fixture Product/RFQ réutilise l’organisation et le desk déjà provisionnés,
  avec retrait de son bypass de création de desk.

Les seuils métier précédemment arbitrés, les règles de finalité des fixings,
la séparation funding/drift, les calendriers bookés et les archives existantes
restent conservés. Aucun nouvel arbitrage métier n’a été requis.

## Registre des suivis supplémentaires

| ID | Cause principale | Cas initiaux | Dépendances |
|---|---|---:|---|
| F08 | Atelier : profils et objets de fixing | 6 | C01, C03, C06, C08, C13, C26 |
| F09 | Calendriers de test et horizon ACT/365,25 | 10 | C05, C09, C14 |
| F10 | Précision des temps retournés | 3 | C14, C18 |
| F11 | Fixtures Local Vol admissibles | 2 | C01, C03, C06, C17, C18 |
| F12 | Fixtures CRM et risque : identité et accès | 4 | C01, C03, C24, C27 |
| F13 | Signaux Demo sur inclusion explicite | 2 | C24, C27 |
| F14 | Fixtures de migration CRM historique | 4 | C03, C06, C24 |
| F15 | Fixtures HTTP des aperçus, pricing et dictée | 8 | C01, C02, C05, C16 |
| F16 | Diagnostic d'une réparation réellement nécessaire | 1 | C16 |
| F17 | Contexte des tests d'archive et worker VaR | 2 | C05, C18, C19 |
| F18 | Dépendances inverses services/routes | 1 | C01, C06, C08, C19, C23 |
| F19 | Fixture d'échange Product/RFQ | 11 | C01, C03, C06, C23 |
| F20 | Refus atomique d'une modification contractuelle | 1 | C06, C08, C23 |
| F21 | Mocks des historiques de watchlist | 4 | C11, C13, C26 |

Les critères détaillés figurent dans les preuves et le registre. Les 121 cas
initiaux de l’étape 1 restent identifiables séparément des 59 cas découverts ici.

## Exécutions et déduplication

| Passage | Résultat | Durée |
|---|---|---:|
| Suite complète initiale | 3 883 succès, 48 échecs, 11 erreurs, 3 ignorés | 1566.59 s |
| Préparation ciblée distincte | **817 succès**, dont les 59 cas initiaux et le nouveau test HTTP | Union de passages ciblés |
| Suite complète finale | **3 943 succès, 3 ignorés, 0 échec/erreur** | 1500.08 s |

Les 817 succès ciblés sont dédupliqués : 800 cas hors du fichier d’exécution RFQ
dans `targeted-second.xml`, les 14 cas de ce fichier dans `execution-final.xml`,
et les 3 contrôles de précision dans `failures-second.xml`. L’union
`targeted-distinct.xml` n’est pas une nouvelle exécution. Les diagnostics
intermédiaires et le brouillon d’atelier ne sont pas additionnés à ce total.

Les artefacts sont dans `.runtime/diagnostic-acceptance/backend-full-2026-10-23/`.
Aucun des 3 945 cas initiaux n’a été supprimé ou renommé. Un nouveau cas HTTP
d’inclusion Demo porte la collection finale à 3 946 cas.

Les trois ignorés sont préexistants : le panel complémentaire LLM vide et deux
tests dépendant du jeu local optionnel fund 2A. Les avertissements de dépréciation
et de métadonnées sont conservés dans les journaux ; ils ne sont pas des échecs.

## Isolation, conservation et portée

Chaque passage assainit `STRUCTURA_*` avant import et utilise son propre dossier
de données isolé. Le garde requests/curl est actif ; les transports mockés et
les consultations natives en localhost restent disponibles. Quatre tentatives
FX ont été interceptées avant envoi dans le premier passage ; le test correspondant
utilise désormais une réponse fournisseur déterministe. Le passage final ne
présente aucune tentative interceptée par ce garde.

Les services temporaires prévus par les tests de consultation font partie de
la recette ; leur fermeture est contrôlée. Les processus et ports sont aussi
inventoriés après validation. La base métier `backend/data/structura.db`, absente
avant le travail, n’a pas été créée ni ouverte.

Les empreintes des 443 sources Python backend sont figées avant le passage final.
Les autres modifications locales, les rapports et preuves C01–C27/F01–F07,
les anciens artefacts et la consolidation figée de l’étape 1 sont préservés.
Les décisions, le graphe des chantiers et les critères d’audit n’ont pas été
réécrits. Aucun fichier Vue n’a changé ; aucun build frontend n’a été lancé.

Cette validation qualifie la suite backend locale sur cet état des sources.
La recette graphique, les scénarios transverses non couverts et la qualification
déployée restent distincts. Les archives gardent leur identité d’origine : une
empreinte moteur antérieure demeure soumise à la règle C19 de rejeu qualifié
ou de sonde distincte, sans réécriture d’archive. Aucun commit ni push.
