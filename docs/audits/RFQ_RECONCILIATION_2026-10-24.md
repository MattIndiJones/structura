# Rapprochement des exécutions et bookings RFQ — 24 octobre 2026

Le rapprochement opérationnel est livré localement : chaque installation déclare l’état de son exécution et de son booking, compare le dernier état reçu au contrat accepté, affiche les écarts et permet de reprendre les échanges ou le booking manquant. La recette isolée aboutit à un seul Deal par livre, après panne bancaire et reprise d’une jambe incomplète malgré la consultation clôturée.

[Preuves structurées](remediation-lot-0-2026-10-20/RFQ_RECONCILIATION_VALIDATION.json) · [Registre](remediation-lot-0-2026-10-20/REGISTER.json) · [Dépendances et critères](remediation-lot-0-2026-10-20/DEPENDENCIES_AND_VALIDATION.md).

Cette étape suit la [confirmation électronique](ELECTRONIC_RFQ_EXECUTION_2026-10-24.md), figée séparément : 252 tests backend ciblés, 756 tests frontend, 15 jalons graphiques. Sa preuve, son rapport et son runtime restent conservés. La recette actuelle emploie de nouvelles bases et identités, sur les ports 18400/18401/18405. Aucune base réelle n’est utilisée, aucun commit ni push effectué.

## Ce qui est rapproché

La clé commune est l’UUID d’exécution, lié à l’empreinte de la demande et de la décision bancaire. Les identifiants locaux Product, Deal, organisation et contrepartie ne servent pas de clés entre installations. Les versions numériques locales peuvent différer ; l’empreinte contractuelle fait foi.

| Contrôle | Référence et règle |
| --- | --- |
| Exécution | Même UUID, demande exacte et empreinte de décision ; confirmation métier distincte de la remise technique |
| Booking de chaque livre | Présent ou absent, à partir du lien de booking local immuable ; aucune déduction à partir de la seule confirmation |
| Économie | Nominal, devise, prix traité exact et sens opposés conformes à la quote acceptée ; aucun seuil de tolérance implicite |
| Contrat | Empreinte des termes épinglés au Deal, strike, valeur, maturité, paiement et documentation conformes à la demande/quote |
| Classification | Format, instrument et famille de payoff ; comparaison sans différence de casse, notamment `Note`/`NOTE` |
| Identité juridique | Mapping local contrôlé ; seuls son résultat et les faits commerciaux partagés sont transmis, pas les identifiants juridiques locaux |
| Date de trade | Égalité entre les deux bookings. Aucune date métier n’est déduite automatiquement des horodatages UTC ou de la date de reprise |
| Disparition | Un booking précédemment déclaré puis absent est un écart explicite, conservé dans l’historique |

La date de trade divergente exige une revue de l’accord et un traitement contractuel gouverné. Cette livraison ne choisit pas une date à la place des opérateurs et ne réécrit aucun Deal pour faire disparaître un écart. Les changements de mappings et les amendements économiques peuvent également exiger une revue, même s’ils sont légitimes localement.

Les fair values, marges, modèles, marchés, Greeks, CRM et journaux privés restent locaux. Le prix rapproché est le **prix traité**, pas le résultat quantitatif interne. L’interface et l’API n’acceptent aucun prix de remplacement pour « corriger » un rapprochement.

## États et actions

| État | Lecture | Reprise |
| --- | --- | --- |
| `DECISION_PENDING` | Accord bancaire pas encore établi localement | Consulter la demande/décision et relancer leur message existant |
| `PEER_UNKNOWN` | Aucun état distant disponible | Demander un échange d’états ; aucune concordance conclue |
| `BOTH_BOOKINGS_MISSING` | Accord confirmé, aucune inscription déclarée | Bookings locaux explicites avec leurs contrôles |
| `LOCAL_BOOKING_MISSING` | Le pair est booké, notre jambe manque | Reprendre le booking local de l’accord confirmé |
| `PEER_BOOKING_MISSING` | Notre jambe est bookée, celle du pair manque | Relancer les états ; traiter la jambe chez le pair |
| `MISMATCH` | Champ divergent, décision contradictoire ou booking disparu | Examiner livre/champ/attendu/constaté ; conserver la preuve |
| `MATCHED_PENDING_DELIVERY` | Faits concordants, notre état courant pas encore remis ou modifié depuis sa publication | Reprendre la remise ou republier le livre courant |
| `MATCHED` | Deux bookings concordants au dernier échange et remise de notre état courant acquittée | Conserver les deux déclarations datées |
| `REJECTED` | Refus concordant sans booking | Conserver le refus ; nouveau tour pour renégocier |

`MATCHED` décrit les **derniers états déclarés**, avec date d’observation, date de réception et version. Il ne prouve pas une lecture en temps réel de la base distante. Un état ancien ou incomplet n’est pas certifié par absence d’erreur HTTP. Les écarts sont signalés dans le dossier et l’audit ; aucune notification externe n’est envoyée.

La file **RFQ reçues** affiche désormais le statut de rapprochement, y compris pour une consultation clôturée. L’inventaire `GET /api/rfq-reconciliation` applique les droits avant pagination et permet de retrouver les cas incomplets. Le détail et la reprise sont également disponibles par exécution. Les résultats d’une autre organisation ou d’un desk inaccessible ne sont pas exposés.

## Persistance et reprise

Le message natif `EXECUTION_STATUS` transporte une projection publique stricte, avec rôle, version croissante, heure d’observation, empreintes et booking. La table additive `rfq_reconciliation_statements` conserve les déclarations locales et distantes, leurs empreintes et leurs identités de message. Les triggers SQLite interdisent modification et suppression.

La réception et son éventuelle réponse sont atomiques avec l’inbox et l’enveloppe HMAC archivée. Une requête appelle au plus une réponse ; cette réponse n’appelle pas de nouvelle réponse. Les doublons sont reconnus par le transport existant ; réutilisation d’identité, version ancienne, rôle étranger, chronologie invalide et champs privés supplémentaires sont refusés. Une nouvelle déclaration correcte conserve les précédentes.

Le booking et sa déclaration sont dans la même transaction locale. Une panne avant commit ne laisse ni Deal ni fausse déclaration de booking. Après commit, l’outbox persistante reprend. Après accusé perdu, `STATUS` retrouve la réception sans rejouer le fait ni multiplier les réponses.

**Rapprocher et reprendre les échanges** utilise une clé de commande durable. Le serveur reprogramme les événements existants, y compris une clôture antérieure qui bloque la séquence, sans retirer les leases des workers. Une répétition de la même commande ne crée pas une nouvelle déclaration. La relance ne crée jamais de décision bancaire, Deal, règlement ou correction économique.

Pour une jambe bancaire **confirmée et non bookée**, la clôture ou l’expiration de la consultation ne bloque plus le calcul nécessaire à l’inscription locale. Le responsable conserve les droits de pricing ; une réaffectation reste explicite et contrôlée. Les dossiers non confirmés ou déjà bookés ne gagnent pas cette dérogation. Retrait, nouvelle publication et modification des termes ne sont pas réouverts par cette reprise.

Le schéma est additif ; les accords et bookings historiques ne sont pas réécrits. Un dossier existant sans déclaration de pair commence à `PEER_UNKNOWN`. Le test d’ajout de la table sur des faits métier déjà confirmés/bookés exige un nouvel échange avant de retrouver `MATCHED`.

## Anomalies traitées pendant cette étape

| Suivi | Défaut et correction | Validation |
| --- | --- | --- |
| RC01 | Une actualisation du même dossier recréait un tableau de dépendances et pouvait fermer la fenêtre de revue/effacer son motif. Les watchers comparent désormais les valeurs d’identité et d’ouverture | Deux tests frontend ; conservation d’une revue identique et rejet d’une réponse étrangère au contexte |
| RC02 | Une consultation clôturée empêchait d’ouvrir/repricer la jambe bancaire d’un accord déjà confirmé | Reprise limitée aux accords confirmés sans booking, UI explicite, réaffectation contrôlée ; tests des deux ordres de booking et recette réelle après `CLOSE` |
| RC03 | Relancer seulement le statut pouvait le laisser derrière une clôture en backoff dans la séquence | La reprise reprogramme aussi `CLOSE`, sans effacer les leases ; test ciblé |

Une fixture de test portait initialement une documentation différente entre quote et Product : le rapprochement l’a correctement signalée. La fixture positive a été rendue cohérente dans le nouveau module de test ; les anciens tests et leurs règles ne sont pas affaiblis. Les écarts de documentation restent des contrôles négatifs.

## Recette obtenue

Les références fictives sont initialisées et auditées. La RFQ, les calculs privés, la publication et la sélection sont préparés par API native authentifiée. La demande et la confirmation sont effectuées dans les interfaces. Les bookings et leur répétition utilisent les API natives, puis sont vérifiés à l’écran. Aucun Product/RFQ/accord/Deal n’est créé par insertion SQL de fixture.

1. Les deux installations confirment l’accord `EXE-BA8BC1A9-EF73-4251-8061-4C31DF0BB02E` et déclarent leurs deux bookings absents.
2. BNP est arrêtée. Leonteq booke localement 1 M EUR à 98,50 %. Le Deal et la file restent persistés ; le livre distant est signalé incomplet.
3. BNP redémarre. Les états et la clôture sont reçus. La file montre le booking local manquant et propose **Reprendre le booking confirmé**.
4. Un calcul natif bancaire frais est composé et exécuté après clôture ; le booking est réalisé puis sa répétition retrouve le même Deal. Les deux états deviennent concordants.
5. Une **fixture négative explicitement auditée** fait publier par le service une déclaration bancaire synthétique à 99 %, alors que le Deal reste à 98,50 %. Le vrai worker signe et livre ce statut. Le demandeur affiche le champ, l’attendu et le constaté ; aucun Deal n’est modifié.
6. L’écart reste visible après redémarrage. Une relance bancaire republie le livre intact, avec une nouvelle version. Les deux côtés retrouvent la concordance ; la déclaration erronée reste archivée.
7. Les déclarations finales complètes sont renouvelées après chargement du code final. Dates de trade, formats, champs économiques et états sont rapprochés sans correction des livres.

Les Deals sont `LEON-20261024-001` / `BNPX-20261024-001`, dans de nouvelles installations distinctes de la recette précédente malgré ces références locales identiques. Chacune contient un seul Deal, une seule exécution et un seul lien de booking électronique. Les calculs privés restent distincts, volatilités 20 % / 30 %. Les quatre événements contractuels concordent. Les bases sont contrôlées en lecture seule, clés étrangères valides, accusés et enveloppes HMAC vérifiés, anciennes déclarations conservées.

Le test négatif est une injection de **déclaration** dans le service isolé, pas une corruption de Deal ni une fonction accessible aux opérateurs de production. Il ne fabrique aucun accusé SQL et ne réécrit aucune preuve immuable.

## Validation et limites

**282 tests backend ciblés distincts réussis, dont 42 nouveaux cas ; 764 tests frontend dans 85 fichiers et `npm run build` réussis. Quinze jalons DOM/capture et 36 contrôles de rapprochement en lecture seule sont conservés.** Aucun nouveau test n’est relancé pendant l’archivage.

Les totaux dédupliqués, identités de tests, journaux, captures, empreintes, résultats de rapprochement et nettoyage figurent dans le JSON de preuve. Les passages intermédiaires en échec sont conservés comme diagnostics de développement et ne changent pas les 180 cas historiques F01–F21.

Les nouveaux tests couvrent les champs divergents, date de trade, perte d’accusé sur chaque jambe, commande concurrente, histoire immuable, chronologie/version/rôle, permissions et organisation étrangère, refus concordant, rollback de booking, reprise après clôture et réaffectation, ajout de table sur dossiers existants, inventaire et séquence bloquée par `CLOSE`. Les voisins réexercent les confirmations, bookings, transport, publications, C08, intégrité Product et permissions. La suite backend complète du 23/10 n’est pas relancée.

Les interfaces sont vérifiées à 1280 × 720, avec commandes clavier et erreurs visibles. L’affichage étroit, la volumétrie et une matrice complète de rôles déployés ne sont pas qualifiés.

Le transport reste authentifié par clé HMAC partagée, sans signature bancaire qualifiée. Le protocole conserve `STRUCTURA_RFQ_1` ; les deux pairs doivent être mis à jour ensemble pour `EXECUTION_STATUS`. La recette est sur HTTP loopback, sans qualification TLS/PKI, réseau distant, bascule machine ou restauration d’une sauvegarde d’exploitation.

Le périmètre est un accord électronique intégral mono EUR. Annulations contestées, amendements après confirmation, exécutions partielles, rapprochement des traitements manuels, règlements, cash et journaux titres restent distincts. Une incohérence persistante exige une revue gouvernée des livres et de l’accord, pas une action « aligner » automatique. Les déclarations datées et l’inventaire ne constituent pas un système de surveillance en temps réel.

Les 132 constats, 27 chantiers, 16 validations transverses et 13 décisions restent inchangés. T02/T12 progressent sur ce scénario mais restent partiels pour la matrice complète et la qualification déployée. D05 et les autres arbitrages antérieurs ne sont pas implicitement clôturés.

## Archivage et arrêt vérifiés

Les bases fictives et secrets restent dans les répertoires ignorés, avec leurs permissions existantes. Les preuves publiables sont indexées par empreinte dans le manifeste local ; aucun secret ni base n’est copié dans les documents suivis. Les services des deux recettes électronique/rapprochement sont arrêtés : ports 18300/18301/18305 et 18400/18401/18405 libres, aucun processus Python correspondant restant. Les 106 fichiers préexistants de `frontend/dist`, les anciens rapports et preuves, HEAD et branche sont préservés. Aucun commit ni push.
