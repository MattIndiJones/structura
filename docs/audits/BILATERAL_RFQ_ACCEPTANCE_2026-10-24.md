# Recette RFQ bilatérale — 24 octobre 2026

**Résultat : deux installations isolées ont échangé une demande et deux révisions de prix par leur transport natif, puis chacune a booké son propre Deal. Quatre anomalies d’interface ont été corrigées et revérifiées.** Aucun commit ni push.

[Preuve structurée](remediation-lot-0-2026-10-20/BILATERAL_RFQ_VALIDATION.json) · [registre courant](remediation-lot-0-2026-10-20/REGISTER.json) · [recette graphique antérieure](GRAPHICAL_ACCEPTANCE_2026-10-23.md).

## Conditions et portée

Deux bases métier neuves, Leonteq et BNP Paribas, sous `.runtime/hybrid-saas/bilateral-2026-10-24/`, avec le portail natif sur `18200`, BNP sur `18201` et Leonteq sur `18205`. Provisionnement, identité des installations, authentification et arrêt passent par les mécanismes hybrides existants. L’adaptateur local remplace uniquement le répertoire statique du frontend ; aucune API ni transition métier n’est simulée. Aucun Product, RFQ ou Deal n’a été précréé par SQL. Les références initiales sont fictives et auditées ; les données métier sont créées dans l’interface.

Le transport HTTPX et ses workers utilisent de vraies connexions loopback et des enveloppes HMAC natives. L’option native d’autorisation HTTP loopback est limitée aux services de recette. **Cette preuve ne qualifie pas TLS, un réseau distant ni la confidentialité du transport en production.** Les identifiants et versions de relations diffèrent volontairement entre bases : RFQ 101/v2 chez Leonteq, 201/v5 chez BNP ; les termes d’appairage concordent.

Le marché est le scénario synthétique natif, seed 42, AIR.PA. Les appels externes `requests`/`curl_cffi` sont bloqués dans les services. Ce garde n’est pas une preuve d’isolation de tout le navigateur ou de toutes les bibliothèques. Les hypothèses de pricing sont explicites et ne constituent pas une calibration de marché.

**L’accord est une déclaration externe fictive consignée localement.** Le protocole RFQ V1 ne transmet pas d’acceptation/confirmation électronique d’exécution. Leonteq consigne une demande puis un accord téléphonique déclaré, référence `BILAT-20261024-001`, avec preuves de recette et mention « confirmation écrite à suivre ». BNP inscrit séparément sa note dans son journal natif. Aucun accusé de transport n’est présenté comme un accord bancaire. Aucun paiement ni règlement n’est déclaré réalisé.

## Parcours obtenu

1. Leonteq crée la RFQ `RFQ-20261024-001`, son Product `PRD-20261024-001` v1, un Athena AIR.PA de 1 M EUR, coupon accumulé 10 %, rappel 100 %, protection européenne 60 %. Strike/valeur le 26/10/2026 ; observations les 26/10/2027, 26/10/2028 et 26/10/2029 ; règlements TARGET J+3 les 29/10/2027, 31/10/2028 et 31/10/2029. Jointures et conventions sont choisies explicitement.
2. Le calcul privé Leonteq au 24/10/2026, avant strike, utilise GBM, σ 20 %, q 1 %, r 3 %, 5 000 trajectoires, antithétiques, seed 42, grille hebdomadaire. Prix conservé : **100,5976 %** ; reçu serveur RFQ conservé.
3. BNP est arrêté avant l’envoi. La demande reste dans l’outbox, avec trois tentatives en attente/reprise. Après redémarrage natif, la quatrième tentative livre **la même demande**, sans nouveau tour ni duplication. L’accusé signé est conservé.
4. BNP reçoit puis prend en charge la demande. Le Product bancaire privé `PRD-20261024-002` v1 reprend exactement les termes reçus, avec le sens opposé. Son calcul à σ 30 %, autres hypothèses identiques, donne **94,1256 %**. Ce calcul et ses hypothèses restent privés.
5. BNP prépare, valide puis publie 99 %, ferme jusqu’à 14 h locales. Leonteq sélectionne la réponse. Une nouvelle préparation/validation/publication à **98,50 %** remplace la première : l’ancienne reste historisée et non sélectionnable ; la sélection est révoquée. Leonteq sélectionne explicitement la v2. La politique de recette v1 autorise le même validateur et impose un calcul de moins de 60 minutes ; aucune politique n’a été assouplie pour la recette.
6. Leonteq consigne l’accord fictif après la publication et avant son expiration. Le statut « traitement demandé » ne crée aucun Deal ; la confirmation est un geste distinct, sourcé et horodaté.
7. BNP booke sa vente locale depuis le Product reçu, avec calcul local frais, relation Leonteq active et revue des hypothèses. Leonteq booke ensuite depuis la revue opérationnelle RFQ avec son reçu conservé, sa quote v2 et son accord confirmé. Chaque confirmation est explicite dans l’interface.
8. Le booking Leonteq émet un `CLOSE` signé, livré à BNP. Le tour est fermé dans les deux bases ; l’historique bancaire reste consultable, les nouvelles publications et l’ouverture du Pricer bancaire depuis ce tour sont désactivées. Le rechargement des livres conserve un unique Deal de chaque côté.

## Rapprochement des deux livres

Relecture SQLite en `mode=ro` et `PRAGMA query_only=ON`, sans violation de clé étrangère. Égalité vérifiée des JSON contractuels complets, de leur empreinte recalculée, du script, des dates et des quatre événements contractuels. Les variantes de casse `Note`/`NOTE` sont normalisées pour comparer les libellés d’instrument.

| Contrôle | Leonteq | BNP Paribas |
|---|---|---|
| Deal local | **LEON-20261024-001**, ID 1 | **BNPX-20261024-001**, ID 1 |
| Product exécuté | ID 1 / termes v1 | ID 2 / termes v1 |
| Notre sens | BUY, position longue ; `Deal.sens=vente` | SELL, position courte ; `Deal.sens=achat` |
| Contrepartie juridique locale | BNP Paribas, ID 10 | Leonteq, ID 17 |
| Nominal / prix traité | 1 000 000 EUR / 98,50 % | 1 000 000 EUR / 98,50 % |
| Date de traitement | 24/10/2026 | 24/10/2026 |
| Strike / valeur | 26/10/2026 | 26/10/2026 |
| Maturité / paiement final | 26/10/2029 / 31/10/2029 | 26/10/2029 / 31/10/2029 |
| Fair value privée | 100,5976 %, σ 20 % | 94,1256 %, σ 30 % |
| Référence de rapprochement | Accord RFQ `BILAT-20261024-001` | Transaction du journal `BILAT-20261024-001` |
| Trace de booking | `RfqExecutionBooking` 1, RFQ 1 | `TradingExecution` 1, Product bancaire 2 |

Empreinte commune : `5c08020fb7c4aeadb6a4720b078039d094785e705c7b94a1cf4897d3cacba067`.

Le journal BNP porte l’émetteur **BNP Paribas** et l’instrument fictif `QA-ATHENA-AIR-EUR-20261024`. Son nominal net est −1 M EUR et son cash à recevoir théorique 985 000 EUR ; règlement **PENDING**. Le booking RFQ Leonteq n’alimente pas automatiquement le journal optionnel des notes : il est rapproché par son accord et son Deal, sans inventer une seconde ligne `TradingExecution`. L’instrument commun n’est donc pas qualifié comme référence de journal présente des deux côtés.

Les cinq messages applicatifs — REQUEST, READ, QUOTE v1, QUOTE v2, CLOSE — sont livrés ; les empreintes outbox/inbox concordent et les HMAC des accusés sauvegardés sont revérifiés hors ligne. Les payloads transportés ne portent aucun des champs de marchés, fair value, marge, Greeks ou reçus privés contrôlés. Les entrées exactes et résultats des calculs restent dans les bases locales. Le reçu signé de pricing reste conservé dans l’evidence RFQ Leonteq ; côté banque, le booking vérifie le reçu serveur puis conserve les entrées, empreintes et résultats du calcul, sans archiver une enveloppe signée de pricing supplémentaire dans le Deal.

## Anomalies corrigées

R01–R04 constituent un suivi distinct des G01–G09 et des F01–F21 ; aucun inventaire historique n’est renuméroté.

| ID | Priorité | Anomalie et correction | Dépendances et validation |
|---|---|---|---|
| R01 | P1 | La préparation bancaire était enregistrée côté serveur, mais son retour n’actualisait pas le parent : les actions de validation/publication n’apparaissaient pas. Transmission du contexte capturé à l’ouverture et application uniquement dans ce contexte ; une réponse tardive, y compris après fermeture/réouverture du même dossier, est écartée. | C10/C23 ; six nouveaux cas ciblés et préparation, validation, publication puis nouvelle révision obtenues dans l’interface. |
| R02 | P2 | Les dates de flux RFQ étaient décalées : origine strike utilisée pour un calcul daté avant strike, et addition locale traversant un changement d’heure. Origine issue de la date effective de valorisation et arithmétique calendaire UTC. Aucun prix ni échéancier moteur modifié. | C05/C18 ; deux nouveaux cas ; tableau revérifié à l’écran : constatation 26/10/2027, règlement 29/10/2027, prix inchangé. |
| R03 | P1 | Un Product conservé ne reprenait pas son intention dans Deal et verrouillait aussi les champs nécessaires à sa première exécution. Reprise du sens, des références et du contexte canonique ; champs d’exécution accessibles avant booking ; termes conservés figés. Les références d’une exécution précédente sont effacées ; un Product déjà exécuté pointe vers son Deal et ne propose pas un premier booking supplémentaire. | C03/C06/C07/C08 ; trois nouveaux cas ciblés ; Product bancaire exécuté sans duplication ni copie contractuelle. |
| R04 | P3 | Le bouton Ouvrir devenait désactivé pendant le chargement et perdait le focus avant l’ouverture de la modale. Il reste accessible ; les gardes C10 continuent d’isoler les ouvertures concurrentes. | C10/C27 ; 44 cas de réponses tardives réexécutés ; Tab reste dans la modale, Escape ferme et le focus revient à Ouvrir sur les assets finaux. |

Les corrections applicatives sont limitées au frontend. Les tests backend vérifient les contrôles métier existants. Deux erreurs de préparation de la recette — signature d’appel du générateur de marché et JSON initial de relation de notes incomplet — ont été corrigées dans l’outillage ignoré. Les relations ont été requalifiées par `PUT` natif authentifié avant tout booking, version 2 ; elles n’ont pas été contournées. Les ajustements d’assertions du script de rapprochement sont également des incidents d’outillage, pas des défauts applicatifs.

## Validation et préservation

- **138 tests backend ciblés distincts réussis**, huit sélections : transport, livraison réseau, accord/booking, publication bancaire, pricing bancaire, intégrité Product, idempotence et contrôles du booking de notes. Aucun échec ni ignoré. Pas de suite backend complète relancée.
- **149 tests frontend ciblés distincts réussis** dans quatre fichiers, dont **11 nouveaux cas**. Les 44 cas du fichier des interfaces asynchrones ont ensuite été réexécutés après R04 ; ils sont inclus dans les 149, sans double comptage. Les huit reproductions R01/R02 échouaient avant correction. Le passage frontend complet intermédiaire à 745 succès précède R03/R04 et ne remplace pas cette preuve finale ciblée.
- Build Vite final réussi sous `.runtime/diagnostic-acceptance/bilateral-2026-10-24/build-final/` ; script `/assets/index-BWVfEvHt.js` contrôlé dans le DOM. **29 jalons graphiques** conservent DOM, capture et note, dont les reproductions et les deux livres relus sur les assets finaux. Ces jalons ne sont pas 29 scénarios indépendants. Aucune erreur console sur les deux pages finales.
- Contrôles de rapprochement et de transport réussis, un Deal et quatre événements par installation. Les deux Products exécutés gardent leurs termes v1. Les états CLOSED et les deux révisions restent conservés.
- Arrêt natif des trois services ; sortie des processus et libération des ports vérifiées. Les bases et preuves ignorées restent disponibles localement. `backend/data/structura.db`, absent au départ, reste absent ; `frontend/dist`, le marqueur de retrait hybride, le HEAD et la branche sont préservés.
- Les preuves du 23/10 et la référence figée sont conservées. Le passage backend historique **3 943 succès / 3 ignorés** reste daté d’avant les recettes graphiques ; les **180 cas F01–F21 restent résolus, zéro ouvert**, sans nouvelle certification globale.

Les pièces détaillées, manifestes et JUnit sont sous `.runtime/diagnostic-acceptance/bilateral-2026-10-24/` ; la preuve structurée suivie par Git en conserve les synthèses et les empreintes utiles, sans secret de canal, JWT, mot de passe ni export complet de base.

## Compléments de qualification

La recette demandée, jusqu’aux deux bookings locaux, est obtenue. T12 reste partiel au regard de sa matrice complète : réouverture/nouveau tour, devise divergente et révocation de droits en vol ne sont pas tous rejoués graphiquement ici. T02 garde ses compléments de concurrence/perte d’accusé de booking en situation déployée ; l’indisponibilité provoquée ici concerne la livraison de la demande.

Avant une exploitation distante, restent prioritaires : qualifier le même trajet sur TLS et réseau représentatifs ; valider la matrice D05 et la politique de publication par desk ; définir le canal de confirmation d’exécution et la réconciliation opérationnelle des bookings asymétriques. Un éventuel accusé d’exécution natif ou l’alimentation automatique des deux journaux serait un chantier explicite, avec unicité par jambe, accord sur une révision exacte, reprise sur panne et conservation des preuves privées. La recette actuelle n’implémente pas ce protocole supplémentaire.

Les autres arbitrages et compléments des 27 correctifs restent dans le registre ; cette livraison ne clôt ni tous les scénarios transverses ni la qualification de production.
