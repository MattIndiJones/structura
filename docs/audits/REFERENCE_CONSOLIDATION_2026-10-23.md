# Consolidation de référence — étape 1 — 23 octobre 2026

Les **27 correctifs disposent d’une livraison locale et de preuves ciblées datées**. Le registre est maintenant aligné sur les correctifs livrés ultérieurement. Le solde documenté comporte **121 cas en échec répartis en 7 groupes**, sans succès ultérieur conservé de même identité. Cette consolidation ne clôture pas la qualification de production.

Cette étape a uniquement modifié la documentation et les fichiers de suivi. Aucun code applicatif ou test modifié, aucun test collecté ou exécuté, aucun build/service lancé, aucun commit ni push. La base métier n’a pas été ouverte ; son absence a seulement été vérifiée.

## Référence retenue

| Élément | Référence |
|---|---|
| Date | 23/10/2026, Europe/Berlin |
| Branche | `codex/hybrid-saas-foundation` |
| HEAD | `7dce3021a88feb4f0021ca3de8f3596277bc72a5` |
| État réel | Copie de travail non committée ; 572 entrées de statut avant cette étape |
| Empreintes avant actualisation documentaire | 1 282 fichiers suivis ou non ignorés, dont 1 043 hors `docs/` |
| Livraisons conservées | 27 rapports C01-C27 et 28 preuves JSON, dont le complément D01 de C03 |
| Preuves runtime | 784 fichiers conservés dans les 28 dossiers C01-C27/D01 |
| Périmètre initial | 132 constats : 49 P1, 81 P2, 2 P3 ; 27 chantiers, 16 cas transversaux, 13 décisions, 16 limites |

Le HEAD seul ne désigne pas les corrections locales. [REFERENCE.json](reference-consolidation-2026-10-23/REFERENCE.json) conserve l’état Git, les SHA-256 et une empreinte déterministe des fichiers hors documentation. Les fichiers ignorés hors des preuves C01-C27, les bases SQLite, `.git` et les caches ne font pas partie de cette empreinte de travail. Ce manifeste n’est donc pas une sauvegarde d’installation ni une référence de déploiement.

Les anciens champs `scope.code_changes_authorized`, `business_data_mutations_authorized` et `new_business_tests_executed` restent ceux de la préparation du lot 0. Leur portée temporelle est explicitée ; ils ne décrivent pas les livraisons C01-C27. Les preuves datées et les rapports de livraison ne sont pas réécrits.

**Rapprochement des empreintes disponibles :** 146 comparaisons explicites de hash d’artefact runtime correspondent. Sur 231 comparaisons de fichiers source/test disposant d’une empreinte de livraison explicite, 166 correspondent et 65 diffèrent après les correctifs suivants ; ces comparaisons peuvent concerner plusieurs fois un même fichier. Les 12 empreintes de la livraison C27 correspondent. Ce contrôle établit l’identité de fichiers, pas leur bon fonctionnement ; les anciens passages ne sont pas transformés en résultats sur la référence consolidée.

## Registre actualisé

Le [registre structuré](remediation-lot-0-2026-10-20/REGISTER.json), le [registre lisible](remediation-lot-0-2026-10-20/ANOMALY_REGISTER.md) et la [matrice des dépendances/validations](remediation-lot-0-2026-10-20/DEPENDENCIES_AND_VALIDATION.md) portent désormais la même lecture courante. Les conditions métier, priorités d’origine, critères V, scénarios attendus T, décisions et dépendances formelles restent inchangés.

- Les 27 statuts de chantier et 16 statuts transversaux sont rapprochés des preuves datées ; les 132 constats portent une annotation de portée courante. Les statuts antérieurs des chantiers sont conservés.
- C04 n’attend plus l’implémentation locale C21 ; le test de limite sur créance courte existe. La recette transverse/déployée reste ouverte.
- C07/C09 n’attendent plus les composantes locales T11/T15/T03 ; le budget de volumétrie de C07 reste à décider et la recette graphique reste nécessaire.
- C10 n’attend plus C17 ; C11 a son scénario combiné T04 et les compléments locaux T10 de C21/C24/C27.
- C15/C16 n’attendent plus le raccord C18 ; le funding reste séparé des taux stochastiques et du drift. Les restrictions quantitatives approuvées ne sont pas élargies.
- C18 a ses consommateurs C19/C21/C22/C25 livrés ; C21 et C24 ont leur prérequis C27 soldé localement.
- La réserve ancienne de C20 sur C08 est explicitement dépassée ; les commandes/reprises et les raccords C20/C23 ont leur preuve locale C08.
- C25 n’attend plus l’implémentation locale C26/C27. Ces livraisons ne remplacent pas une recette graphique ou opérationnelle du roll.

### Interfaces conditionnelles

| Interface | Lecture courante et limite |
|---|---|
| C15 → C18 | Raccord local des taux/funding ; domaine de production D04 ouvert. |
| C16 → C18 | Raccord local dans le domaine restreint ; aucune qualification de panier hors domaine. |
| C17 → C18 | Transport de preuve et domaine ; convergence seule insuffisante. |
| C13 → C18 | Consommation locale des faits officiels ; chaîne déployée complète restante. |
| C21 → C04 | Mesures et limites raccordées localement ; position résultante et créance courte contrôlées. |
| C04 → C23 | Limites résultantes réexercées localement avec C23/C08. |
| C11 → C24 | Condition non activée : restitution par devise ; conversion future soumise au FX daté. |
| C06 → C13 | Faits/révisions et versions de termes distincts ; D06 sur faits consommés reste ouvert. |
| C02 → C19 | Garde d’identité disponible localement ; aucune migration/adoption de base ancienne exécutée. |
| C13 → C21 | Correction de fixing invalide le courant, sans effacer les historiques. |
| C10 → C17 | Garde asynchrone locale ; recette graphique de chaîne restante. |
| C08 → C20 | Reprise de conservation de recherche validée localement ; réserve antérieure dépassée. |

Les statuts T01-T16 décrivent une couverture locale ou partielle. T03/T04/T13/T15 ont leurs validations locales documentées ; T06/T07 ont leurs raccords locaux bornés. Aucun des 16 cas n’est déclaré intégralement qualifié en environnement déployé. T12 reste une chaîne applicative avec bases séparées et transport simulé : TLS, DNS, horloges, services et interactions UI réelles ne sont pas qualifiés par ces tests.

## Déduplication des tests

[TEST_INVENTORY.json](reference-consolidation-2026-10-23/TEST_INVENTORY.json) conserve une entrée par identité et son historique. [EVIDENCE_INVENTORY.json](reference-consolidation-2026-10-23/EVIDENCE_INVENTORY.json) relie les preuves, journaux, empreintes et classifications de passages.

| Mesure | Résultat et portée |
|---|---|
| XML dépouillés | 190 : 146 observations sur copie de travail, 37 baselines/reproductions, 7 unions dérivées |
| Occurrences de cas dans ces XML | 14 304 ; ce nombre inclut les unions dérivées et ne désigne pas autant d’exécutions |
| Identités XML distinctes | 3 046, après normalisation de chemins et 4 alias explicites de reproductions copiées |
| Occurrences répétées non additionnées | 11 258 |
| Identités backend inventoriées, toutes preuves | 3 106, dont 60 sans résultat XML individuel |
| Dernière observation XML par identité | 2 923 succès historiques, 122 échecs historiques, 1 ignoré ; ce n’est pas une campagne unique |
| Échecs XML après retrait d’un ancien nom remplacé | 121 cas toujours présents dans la source ; inventaire F01-F07 ci-dessous |
| Frontend | Dernière preuve C27 : 731 succès / 82 fichiers et build Vite réussi ; retenue une seule fois |

Règles appliquées :

1. Identité = fichier de test + classe éventuelle + nom exact, en conservant la paramétrisation. Les séparateurs de chemin sont normalisés uniquement avant `::` ; les séquences dans les paramètres ne sont pas altérées.
2. Le dernier résultat XML utilise l’horodatage du passage sur copie de travail. Une baseline exécutée plus tard, une reproduction RED ou une union XML dérivée ne remplace pas un résultat final. Les tentatives intermédiaires restent consultables.
3. Quatre reproductions copiées C13/C18 sont reliées explicitement aux identités d’origine, avec fichier et fonction. Les migrations C13 et C21 restent deux tests différents.
4. Un renommage n’est pas traité comme un succès de l’ancienne identité. Cinq identités historiques sont retirées/renommées, dont trois avaient un échec ; les remplaçants restent distincts.
5. Les 60 identités sans XML individuel restent séparées : 40 appartiennent à des unions de succès déclarées C03, 16 sont seulement collectées individuellement dans les preuves, 2 ont un échec ancien résolu au niveau fichier, 2 sont d’anciens noms retirés. Les 16 identités collectées ont aussi des passages globaux de fichier dans les journaux C01/C02, sans détail machine individuel ; aucun succès individuel n’est inventé.
6. Le cas ignoré est `test_llm_scripting.py::test_les_exemples_complementaires_compilent_et_pricent[NOTSET]` : paramétrisation vide, pas une qualification du pricing de ces exemples.
7. Les journaux frontend ne donnent pas toutes les identités de succès. Aucun total unique cumulé frontend n’est calculé à partir des totaux successifs des lots. Dix libellés historiques d’échec/collection sont conservés avec la preuve globale ultérieure, sans prétendre disposer d’un résultat individuel pour chacun.

Ces inventaires ne mesurent pas la couverture totale du dépôt. La présence d’une fonction dans la source est contrôlée statiquement, sans import applicatif ni collecte pytest ; ses paramètres exécutables actuels n’ont pas été recalculés.

## Solde des échecs documentés

L’[inventaire lisible des cas](reference-consolidation-2026-10-23/REMAINING_FAILURES.md) donne les 121 identités et leurs messages ; [FAILURE_INVENTORY.json](reference-consolidation-2026-10-23/FAILURE_INVENTORY.json) conserve les détails et l’historique des résolutions.

| Groupe | Cas | Observation conservée | Suite et dépendances |
|---|---:|---|---|
| F01 — auth / AMC | 1 | Mot de passe de fixture de 11 caractères rejeté, signalé en C11 ; pas de succès ultérieur. | Aligner la fixture sur C02, puis atteindre l’assertion d’interdiction d’inscription publique. |
| F02 — migration minimale | 1 | `no such table: main.products`, reproduit avant C13. | Définir le domaine de schémas historiques supportés ; migration idempotente et gardes Product C06/C19. Distinct du test CCR corrigé en C21. |
| F03 — RFQ historiques | 90 | Habilitations, rôle absent, motifs requis et attentes juridiques ; reproduits avant C19. | Acteurs/desks C01, référentiel/exception D01-C03, versions C06, commandes C08 et règles C23. Réviser les attentes obsolètes sans affaiblir les contrôles. |
| F04 — générateur UAT | 9 | Liens Product canoniques, S0/clôtures et dépendances terminales ; reproduction Windows corrigée conservée. | Isoler fixture ou défaut générateur ; préserver C05/C06/C13 et séparation C27. Ne pas classer ces neuf cas comme de simples fixtures sans diagnostic. |
| F05 — analyse produit | 5 | HTTP 403 empêche les assertions 200/422 ; reproduits avant C19. | Acteur autorisé C01, maintien des cas de refus ; contrats PayScript C09. |
| F06 — chaîne CRM | 14 | Desk pilote/contrepartie absents, erreurs en cascade ; mêmes échecs avant/après C24. | Contexte C01/C03/C06 valide, invariants de rattachement C24, périmètre C27 ; ne pas convertir un échec de création en succès de suppression. |
| F07 — relevés lifecycle | 1 | `SimpleNamespace` sans `role`, même échec avant/après C26. | Acteur C01 qualifié ; relevés sous strike et priorité du registre C13/C26. |
| **Total** | **121** | **7 groupes, pas 121 causes indépendantes** | **Aucune nouvelle reproduction dans cette étape** |

Le bilan précédent des gros blocs C19/C24/C26 donnait 104 + 14 + 1 = 119. La consolidation ajoute explicitement F01 et F02, signalés auparavant mais sans reprise réussie conservée. Le 122e dernier échec XML correspond à l’ancien test qui attendait un choc nul implicite ; C21 le remplace par un refus explicite de facteur manquant, dont le test possède son succès distinct. Il ne s’ajoute pas aux 121 cas du solde.

L’historique complet des échecs, journaux inclus, contient 337 identités avec succès XML ultérieur, 10 avec résolution documentée au niveau fichier/union, 3 identités retirées/remplacées et les 121 cas du solde. Les RED initiaux, les erreurs d’assertion corrigées et les lanceurs invalides restent tracés, sans être présentés comme des défauts actuels. Le premier baseline UAT C19 sans garde Windows est exclu pour ce périmètre ; les neuf reproductions valides de `baseline-uat-final.xml` font foi.

## Arbitrages métier : état préservé

| Décision | Statut au 23/10 et garde à conserver |
|---|---|
| D01 | Confirmée : identifiant juridique actif par défaut ; exception de booking administrateur explicite, motivée et auditée. Aucun contournement RFQ/accord/limites. |
| D02 | Confirmée : choix explicite de règle de panier par produit, places d’observation séparées des centres de règlement, stub long fusionné ; dates bookées figées. |
| D03 | EOD/FX : 3 jours calendaires, J+4 exclu. Cours nu disponible après clôture utilisé dès disponibilité, **aucun délai supplémentaire ni attente du lendemain** ; exceptions de place/fuseau/calendrier explicites. Autres usages à qualifier. |
| D04 | Partielle : C16 approximation signalée, 10 pb du nominal sur le panel ; C17 5 pb vanilles/10 pb digitales sur les points publiés. Aucun élargissement de domaine ni qualification générale du modèle. |
| D05 | Règle d’accès implémentée pour revue ; validation métier encore à formaliser. |
| D06 | Annulation/remplacement d’un fixing déjà consommé à définir ; les gardes de refus restent en place, aucun fait consommé réécrit. |
| D07 | Distinguer échéance contractuelle, déclaration et confirmation du paiement, retard/défaut. Le moniteur et le cash contractuel ne prouvent pas un virement bancaire. |
| D08 | Domaine VaR/CCR à formaliser ; limites de photo résiduelle, FX/funding et grille conservées. Aucun SA-CCR ni WWR qualifié implicitement. |
| D09 | Confirmée : bid observé ou hypothèse modèle décotée identifiée, frais de sortie sur nominal d’origine ; nouveau prix modèle + marge/frais d’entrée sur nouveau nominal. |
| D10 | Confirmée : gel manuel explicite de proposition avant export. |
| D11 | Confirmée : archives consultables ; rejeu qualifié à identité moteur/conventions compatible et contrôle numérique, sinon sonde séparée sans écrasement. |
| D12 | Partielle : conventions de sensibilités explicites ; budget Optimizer souple 120 s par défaut, 30–3 600 s, dépassement enregistré. Pas de nouveau plafond métier approuvé. |
| D13 | Confirmée : nom canonique verrouillé localement, renommage par provisionnement. |

Aucune décision utilisateur n’est réouverte ni remplacée. La recette quantitative doit conserver le funding hors drift/taux stochastiques, les seuils C16/C17, les domaines restreints et la distinction exploration/qualification.

## Ordre proposé pour l’étape suivante

| Ordre | Travail à autoriser séparément | Dépendances et critère de sortie |
|---|---|---|
| 1 | Préparer une qualification ciblée des fixtures communes et de la migration F02. | Acteurs, sessions, desks, motifs, identités et versions conformes à C01/C02/C03/C06 ; domaine des anciennes bases explicite ; aucune désactivation de garde ni accès à la base métier. |
| 2 | Isoler et traiter les 9 cas du générateur UAT F04. | Liens Product/S0 corrects, huit profils, cleanup isolé et séparation Production/UAT conservés ; distinguer défaut du générateur et défaut de fixture. |
| 3 | Requalifier les RFQ F03 et la chaîne CRM F06 avec le socle commun. | Préconditions valides, refus réellement visés atteints, confidentialité, versions, idempotence et rattachements préservés. Couvrir ensuite F01/F05/F07 sur leurs acteurs qualifiés. |
| 4 | Faire une seule sélection transverse déterministe sur une référence source figée. | IDs uniques, données isolées, réseau borné, preuves reliées aux SHA de cette référence ; ne pas additionner les reprises ni élargir automatiquement à la suite complète. |
| 5 | Préparer la recette graphique/bilatérale et la qualification d’exploitation. | Arbitrages D05-D08, domaines D04 et budgets/D12 explicites ; identité des installations, sauvegarde/restauration, migrations, observabilité et scénarios T prioritaires. |

Les étapes 2–3 peuvent partager la qualification des fixtures, mais aucune conclusion sur le générateur UAT ou les migrations ne doit être obtenue en contournant un contrôle métier. Les besoins de recette graphique, reprise historique et exploitation restent ouverts même si tous les échecs ciblés sont ensuite résolus.

## Critères de validation de cette étape documentaire

- Une référence de copie de travail identifiable, distincte du seul HEAD ; empreintes des sources, tests, configurations et preuves conservées.
- 27 livraisons/28 preuves accessibles ; 132 constats, critères, priorités et 13 décisions préservés ; graphe inchangé et statuts C/T cohérents entre JSON et Markdown.
- Identités exactes conservées, paramétrisations non fusionnées, XML dérivés séparés des passages ; totaux reproductibles à partir des inventaires.
- 121 cas ouverts identifiés individuellement, somme des 7 groupes vérifiable ; baselines valides, échecs résolus, noms retirés et preuves frontend limitées explicitement séparés.
- Aucun fichier hors du périmètre documentaire autorisé modifié ; anciennes preuves de livraison et runtime intactes ; HEAD/branche inchangés, base métier toujours absente.

Le [contrôle de préservation](reference-consolidation-2026-10-23/PRESERVATION_CHECKS.json) contient les contrôles documentaires réellement effectués. Aucun résultat de test supplémentaire n’est revendiqué.

## Documents produits

| Fichier | Usage |
|---|---|
| [REFERENCE.json](reference-consolidation-2026-10-23/REFERENCE.json) | Référence de copie de travail, empreintes et écarts avec les empreintes de livraison disponibles. |
| [EVIDENCE_INVENTORY.json](reference-consolidation-2026-10-23/EVIDENCE_INVENTORY.json) | 28 preuves, 27 rapports, 784 artefacts runtime, XML et limites des journaux frontend. |
| [TEST_INVENTORY.json](reference-consolidation-2026-10-23/TEST_INVENTORY.json) | 3 106 identités backend, provenance et historique dédupliqués. |
| [REMAINING_FAILURES.md](reference-consolidation-2026-10-23/REMAINING_FAILURES.md) | Lecture des 121 cas par groupe avec messages et preuves. |
| [FAILURE_INVENTORY.json](reference-consolidation-2026-10-23/FAILURE_INVENTORY.json) | Historique des échecs, reproductions, résolutions, noms remplacés et critères futurs. |
| [PRESERVATION_CHECKS.json](reference-consolidation-2026-10-23/PRESERVATION_CHECKS.json) | Préservation des fichiers et cohérence des documents ; sans exécution de tests. |
| [ARTIFACT_MANIFEST.json](reference-consolidation-2026-10-23/ARTIFACT_MANIFEST.json) | Hash des livrables finaux, hors lui-même ; les empreintes source restent dans REFERENCE.json. |
