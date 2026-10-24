# Dépendances des correctifs et critères de validation

**Accès du launcher et changement de compte — 24/10/2026 :** six organisations/24 profils, console et simulation vérifiés ; cas Admin seul ajouté après la capture de Philippe. **LA01–LA04 corrigées**, **53 tests backend ciblés distincts**, **779 tests frontend et build**, **28 jalons navigateur**. Sélecteur Admin actif, profil explicite, démarrage à la demande et retours après panne ; aucune IA démarrée. Services de recette arrêtés, nouvelle instance utilisateur préservée ; **relance du portail utilisateur nécessaire** pour charger le contrat serveur modifié. 132 constats/27 chantiers/180 cas F01–F21 inchangés. [Rapport](../ADMIN_ACCOUNT_SWITCH_2026-10-24.md) · [preuves](LAUNCHER_ACCESS_VALIDATION.json).

**Launcher — 24/10/2026 :** reprise explicite du workspace Admin historique sans marqueur C02, avec sauvegarde identique, identité et audit transactionnels. **31 tests ciblés réussis**, démarrage réel du launcher et connexion Admin validés sur copie isolée puis sur le workspace du raccourci ; comptes, secrets et dossiers conservés. Services de contrôle arrêtés et ports libres vérifiés. La garde C02 reste active ; autres adoptions et qualification déployée distinctes. Les 132 constats, 27 chantiers et 180 cas F01–F21 ne sont pas renumérotés. [Rapport](../LAUNCHER_RECOVERY_2026-10-24.md) · [preuves](LAUNCHER_RECOVERY_VALIDATION.json).

**Rapprochement RFQ — 24/10/2026 :** états réciproques authentifiés et datés, inventaire habilité et écarts par champ. Panne bancaire, booking local conservé, reprise de la jambe bancaire après clôture, déclaration négative à 99 % puis retour à 98,50 % sans modification des Deals exercés sur deux installations isolées. **RC01–RC03 traités**, **282 tests backend ciblés distincts**, **764 tests frontend/build**, 15 jalons graphiques et 36 contrôles de rapprochement en lecture seule. Un Deal par livre et deux états finaux `MATCHED` ; services arrêtés et ports libres vérifiés. Les 132 constats, 27 chantiers et 180 cas F01–F21 restent inchangés ; T02/T12 restent partiels, TLS et qualification déployée ouverts. [Rapport](../RFQ_RECONCILIATION_2026-10-24.md) · [preuves](RFQ_RECONCILIATION_VALIDATION.json).

**Confirmation électronique RFQ — 24/10/2026 :** demande et décision bancaire natives, reprises après arrêt de chaque destinataire, enveloppes originales et accusés conservés. Une exécution commune et un Deal par base, 1 M EUR à 98,50 %, sens opposés ; 28 contrôles de rapprochement en lecture seule. E01 corrigée (ordre de flush inbox/preuve), 252 tests backend ciblés distincts, 756 tests frontend/build et 15 jalons graphiques. Bookings et replays par API native puis contrôle à l’écran. Services arrêtés ; TLS/déploiement et matrice complète T02/T12 restent ouverts. Les 132 constats et 180 cas F01–F21 restent inchangés. [Rapport](../ELECTRONIC_RFQ_EXECUTION_2026-10-24.md) · [preuves](ELECTRONIC_RFQ_VALIDATION.json).

**Recette RFQ bilatérale — 24/10/2026 :** C01/C02/C03 préparent identité, accès et mappings juridiques ; C05/C06 fixent le contrat ; C10 isole les retours de préparation/validation/publication ; C18 conserve les calculs privés ; C08/C23 assurent livraison, révisions, accord local et unicité des bookings. Le scénario natif entre deux services isolés aboutit aux Deals **LEON-20261024-001 / BNPX-20261024-001**, 1 M EUR à 98,50 %, puis à la clôture reçue des deux côtés. R01–R04 corrigées, 138 tests backend et 149 tests frontend ciblés distincts, build et rapprochement réussis. Critères obtenus : même contrat v1, prix/nominal/dates concordants, sens opposés, un Deal par livre, ancienne quote non sélectionnable, hypothèses privées absentes des payloads contrôlés. T02/T12 restent partiels : pas de nouvelle recette graphique complète de réouverture, devise divergente, révocation en vol ou concurrence de booking sur réseau déployé. Accord externe fictif, TLS et protocole natif d’acceptation non qualifiés ; D05 et les autres arbitrages restent ouverts selon le registre. [Rapport](../BILATERAL_RFQ_ACCEPTANCE_2026-10-24.md) · [preuves](BILATERAL_RFQ_VALIDATION.json).

**Recette graphique — 23/10/2026 :** chaîne Product → RFQ → booking → fixing → MtM/PDF, risque, CRM, Optimizer, profils et séparation Production/UAT exercés sur installations isolées. **Neuf anomalies G01–G09 corrigées**, **151 tests backend ciblés distincts**, **737 tests frontend et build réussis** ; 48 jalons DOM/capture conservés. Réseau bilatéral, cycle cash complet, risque positif complet, roll positif, modèles avancés et qualification déployée restent distincts. Les 132 constats et 180 cas historiques ne sont pas renumérotés. [Rapport](../GRAPHICAL_ACCEPTANCE_2026-10-23.md) · [preuves](GRAPHICAL_VALIDATION.json).

## Actualisation de référence — 24 octobre 2026

**Suite backend complète — 23/10/2026 :** premier passage : 3 883 succès, 48 échecs, 11 erreurs et 3 ignorés. Les **59 cas** sont corrigés dans **14 suivis F08-F21** ; **817 tests ciblés distincts réussis**. Passage complet final : **3 943 succès, 3 ignorés conditionnels inchangés, aucun échec ni erreur**. Les 121 résolutions historiques et les 59 supplémentaires passent dans ce même passage final ; solde courant **0 cas ouvert sur 180 documentés**. Référence figée et preuves antérieures conservées ; recette graphique et qualification déployée distinctes. [Rapport](../BACKEND_FULL_VALIDATION_2026-10-23.md) · [preuves](BACKEND_FULL_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F01 — 23/10/2026 :** échec reproduit avant le contrôle d’ouverture : mot de passe de fixture de 11 caractères, refusé par C02. Demande conforme, contexte autonome et motif 403 précis ; **21 tests ciblés distincts réussis** (15 inscription + 6 voisins), dont 14 nouveaux cas HTTP. Ouverture explicite, refus géré, limites de mot de passe, persistance et sessions vérifiés sans changement applicatif. Aucun appel HTTP externe ni arbitrage nouveau. Solde après F01 : **0 cas historique ouvert**, soit **121 cas résolus localement dans 7 groupes** sur preuves ciblées datées. Les autres groupes ne sont pas relancés ; aucune qualification globale ou de production. [Rapport](../REMEDIATION_F01_2026-10-23.md) · [preuves](F01_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F07 — 23/10/2026 :** échec du faux utilisateur sans rôle reproduit puis résolu par une fixture persistée conforme, avec contrepartie active et gardes FK/Product. Dix dates de départ sans doublon au strike et neuf relevés enfants vérifiés ; droits JWT contrôlés en autonome et installation gérée, priorité du registre officiel réexercée par des tests voisins. **20 tests ciblés distincts réussis** (11 relevés + 9 voisins), dont deux nouveaux cas HTTP. Aucun changement applicatif, appel HTTP externe ni arbitrage nouveau. Solde après F07 : **1 cas documenté dans 1 groupe ouvert** (F01), non relancé. [Rapport](../REMEDIATION_F07_2026-10-23.md) · [preuves](F07_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F06 — 23/10/2026 :** 14 échecs reproduits puis résolus par des fixtures JWT/desks/identité juridique conformes, sous clés étrangères et gardes Product. Créations vérifiées avant lecture ; deux faux positifs négatifs renforcés ; chaîne RFQ-Deal exécutée sur le même Product/version avec calcul réel hors ligne. **32 tests ciblés distincts réussis** (19 chaîne CRM + 13 voisins), dont trois nouveaux refus atomiques et rejouables. Aucun changement applicatif, appel HTTP externe ni arbitrage nouveau. Solde après F06 : **2 cas documentés dans 2 groupes ouverts** (F01/F07), non relancés. [Rapport](../REMEDIATION_F06_2026-10-23.md) · [preuves](F06_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F05 — 23/10/2026 :** cinq refus 403 reproduits puis résolus par une fixture authentifiée réelle, sans modification applicative ni élargissement des permissions. **58 tests ciblés distincts réussis**, dont les cinq identités initiales inchangées et 34 nouveaux contrôles : refus 401/403, droits relus, aperçu/envoi/provenance en autonome et installation gérée. Aucun appel HTTP externe ou LLM réel. Solde après F05 : **16 cas documentés dans 3 groupes ouverts** (F01/F06/F07), non relancés. [Rapport](../REMEDIATION_F05_2026-10-23.md) · [preuves](F05_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F03 — 23/10/2026 :** 90 échecs reproduits puis couverts ; fixtures avec utilisateurs/desks réels, motifs et identifiants juridiques explicites. Deux défauts RFQ corrigés : suppression du last look sous clés étrangères et interdiction de supprimer une réponse d’un tour clos. **212 tests ciblés distincts réussis** (127 RFQ, 2 CCR dépendants, 83 voisins), sans appel HTTP externe. Trois tests renommés avec correspondance conservée. Solde après F03 : **21 cas documentés dans 4 groupes ouverts** (F01/F05/F06/F07), non relancés. [Rapport](../REMEDIATION_F03_2026-10-23.md) · [preuves](F03_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F04 — 23/10/2026 :** neuf échecs initiaux résolus : fixture Product conforme et cours datés simulés dans les tests. Générateur corrigé pour conserver le calendrier booké, annuler les écritures d’un refresh en échec et auditer la couverture réelle. **55 cas ciblés distincts réussis**, dont 37 du générateur et 18 voisins ; aucun cours synthétique introduit dans le générateur. Solde après F04 : **111 cas documentés dans 5 groupes ouverts**. [Rapport](../REMEDIATION_F04_2026-10-23.md) · [preuves](F04_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F02 — 23/10/2026 :** fixture de migration corrigée pour respecter la création préalable des tables du démarrage normal. Deux démarrages réels sur base isolée et protections Product vérifiés ; **7 tests ciblés réussis**, aucune migration applicative modifiée. Solde après F02 : **120 cas documentés dans 6 groupes ouverts**. [Rapport F02](../REMEDIATION_F02_2026-10-23.md) · [preuves](F02_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json). Les inventaires figés de l’étape 1 conservent leur situation initiale de 121 cas.

[Consolidation et méthode de déduplication](../REFERENCE_CONSOLIDATION_2026-10-23.md) · [Échecs documentés](../reference-consolidation-2026-10-23/REMAINING_FAILURES.md).

Les 27 livraisons locales sont présentes. Les statuts C01-C27 et T01-T16 ci-dessous sont alignés sur le registre structuré ; leurs preuves restent celles des campagnes datées, sans nouvelle exécution. Les commentaires de livraison conservés sont historiques. Le graphe de dépendances et les 132 critères attendus sont inchangés ; recette graphique/transverse, exploitation et qualification déployée restent distinctes de la validation locale.

[Lot 0](../REMEDIATION_LOT_0_2026-10-20.md) · [Registre](ANOMALY_REGISTER.md) · [Sources](AUDIT_SOURCES.md).

Les liens ci-dessous organisent la **qualification de la chaîne**. Ils n'obligent pas à attendre la fin de tous les chantiers pour préparer un correctif unitaire. Les dépendances conditionnelles ne valent que pour l'usage indiqué : un GBM explicite n'attend pas une calibration Heston, une limite nominale n'attend pas la correction complète de la CVA.

Les rôles mentionnés sont des responsabilités proposées, sans personne désignée. Au lot 0, tous les chantiers et scénarios étaient **à préparer**. Le suivi C01 ci-dessous distingue désormais validation locale et clôture transverse.

Un prérequis signifie **interface stabilisée et invariant ciblé validé**, sans exiger le statut Clos du chantier amont. Une recette transverse partagée peut ensuite clôturer plusieurs chantiers ensemble. Le graphe de préparation reste ainsi distinct des rapprochements de preuves entre consommateurs ; il ne crée pas d'attente circulaire de clôture.

## Chantiers

| ID | Chantier | Lot principal | Prérequis de clôture du périmètre commun | Entrées |
|---|---|---:|---|---:|
| [C01](#c01) | Permissions métier et confidentialité | 1 | Aucun | 7 |
| [C02](#c02) | Sessions portail et identité des installations | 1 | Aucun | 7 |
| [C03](#c03) | Identifiants juridiques et gouvernance des référentiels | 1 | Aucun | 9 |
| [C04](#c04) | Limites et amendements économiques | 1 | C01, C03 | 3 |
| [C05](#c05) | Calendriers contractuels et règlement | 2 | Aucun | 8 |
| [C06](#c06) | Versions Product et intégrité des transitions | 2 | C01 | 5 |
| [C07](#c07) | Conservation et reprise des saisies | 2 | C06 | 12 |
| [C08](#c08) | Idempotence des commandes et filiation | 6 | C01, C06 | 3 |
| [C09](#c09) | Compilation PayScript et qualification du payoff | 2 | Aucun | 3 |
| [C10](#c10) | Réponses tardives et erreurs dans les interfaces | 2 | Aucun | 8 |
| [C11](#c11) | Données de marché datées et couverture | 3 | C03 | 7 |
| [C12](#c12) | Stockage atomique des séries et caches | 3 | C03 | 2 |
| [C13](#c13) | Finalité des cours et registre officiel | 3 | C05, C11 | 5 |
| [C14](#c14) | Axe temporel et ordre des événements | 4 | C05, C09 | 3 |
| [C15](#c15) | Taux stochastiques funding et corrélations | 4 | C14 | 3 |
| [C16](#c16) | Dépendance des extrema et barrières | 4 | C14 | 1 |
| [C17](#c17) | Surfaces calibration et diagnostics | 4 | C11, C14 | 5 |
| [C18](#c18) | Contexte commun de valorisation et sémantique | 5 | C06, C14 | 7 |
| [C19](#c19) | Archives rejeu et documents figés | 5 | C06, C18 | 9 |
| [C20](#c20) | Recherche Optimizer et budgets | 7 | C09, C18 | 4 |
| [C21](#c21) | Couverture des risques CVA et fraîcheur | 5 | C03, C14, C18, C27 | 4 |
| [C22](#c22) | P&L cash et attribution | 5 | C13, C18, C19 | 2 |
| [C23](#c23) | Cotations tours RFQ et exécutions réseau | 6 | C01, C03, C06, C08 | 6 |
| [C24](#c24) | Attribution CRM analyses datées et devises | 7 | C01, C03, C06, C27 | 3 |
| [C25](#c25) | Économie du roll et récupération | 7 | C18, C19 | 2 |
| [C26](#c26) | Surveillance lifecycle et comptes rendus | 3 | C01, C11, C13 | 2 |
| [C27](#c27) | Périmètres Production UAT et démonstration | 1 | Aucun | 2 |

## Dépendances conditionnelles et interfaces

Les dépendances communes et conditionnelles forment un graphe acyclique ; les liens d'interface ne sont pas des barrières de livraison.

| Amont | Aval | Nature | Condition et interaction |
|---|---|---|---|
| [C15](#c15) | [C18](#c18) | Qualification | Si taux stochastiques : corriger le moteur avant de raccorder funding et facteurs aux consommateurs.  **Au 23/10 : Raccord validé localement ; qualification de production D04 restante.** |
| [C16](#c16) | [C18](#c18) | Qualification | Si monitoring continu de panier : qualifier les extrema avant d'élargir la capacité.  **Au 23/10 : Raccord validé localement dans le domaine C16 ; aucune extension de domaine.** |
| [C17](#c17) | [C18](#c18) | Qualification | Si modèle calibré : conserver preuve et domaine ; un GBM explicite n'attend pas la qualification Heston.  **Au 23/10 : Preuve et domaine raccordés localement ; pas de qualification générale des modèles.** |
| [C13](#c13) | [C18](#c18) | Qualification | Pour les valorisations en vie : reprendre les faits officiels cohérents.  **Au 23/10 : Consommation des faits officiels validée localement ; chaîne déployée restante.** |
| [C21](#c21) | [C04](#c04) | Qualification | Pour les limites PFE/CVA : requalifier la décision après correction des mesures ; le contrôle nominal se sécurise plus tôt.  **Au 23/10 : Requalification locale des mesures/limites, créance courte bloquée sans mutation ; recette intégrale restante.** |
| [C04](#c04) | [C23](#c23) | Qualification | Pour confirmer booking et amendement : contrôler les limites sur la position résultante.  **Au 23/10 : Contrôle de la position résultante réexercé localement ; qualification déployée restante.** |
| [C11](#c11) | [C24](#c24) | Conditionnelle | Seulement si conversion : FX datés et couverture ; une restitution par devise reste indépendante.  **Au 23/10 : Non activée : restitution par devise sans conversion ; FX daté requis si conversion future.** |
| [C06](#c06) | [C13](#c13) | Interface | Une correction de fixing fait évoluer les faits et la révision du dossier sans changer artificiellement les termes.  **Au 23/10 : Faits/révision et termes contractuels distingués localement ; D06 reste ouvert.** |
| [C02](#c02) | [C19](#c19) | Conditionnelle | Avant migration des archives : vérifier l'identité de base ; les formats se préparent indépendamment.  **Au 23/10 : Garde d’identité validée localement ; aucune adoption ni migration réelle exécutée.** |
| [C13](#c13) | [C21](#c21) | Qualification | Une correction de fixing invalide le courant sans effacer les runs historiques.  **Au 23/10 : Invalide le courant sans réécrire les archives : validé localement.** |
| [C10](#c10) | [C17](#c17) | Qualification | Protéger l'application asynchrone avant d'annoncer une calibration actuelle.  **Au 23/10 : Protection asynchrone validée localement ; recette graphique restante.** |
| [C08](#c08) | [C20](#c20) | Conditionnelle | La répétition d'une conservation de recherche ne crée pas de dossier supplémentaire.  **Au 23/10 : Reprises de recherche et commandes raccordées localement ; ancienne réserve C20 sur C08 dépassée.** |

## Contrats d’interface — invariants à préserver

| Interface | Champs et invariants matériels | Consommateurs à vérifier |
|---|---|---|
| Identité et autorité | Organisation, desk, acteur, permission, identité juridique stable ; libellé descriptif séparé ; projection CRM explicitement autorisée | Product, RFQ, Deal, limites, portefeuilles, CRM, alertes |
| Termes contractuels | Product ID, terms_version, révision de dossier, sens, paramètres effectifs, panier, calendriers figés, paiement | Economics, RFQ, booking, cycle de vie, valorisation |
| Données et provenance | Instrument, champ, source, observation/asof, finalité, convention nu/ajusté, unité, couverture, surcharge, valeur moteur | Pricer, RFQ, replay, calibration, risque, réinvestissement |
| Faits de cycle de vie | IDs et versions officielles de fixing/résolution, état réalisé et créances ; distincts de terms_version | MtM, P&L, CCR, moniteur, documents |
| Calcul conservé | Entrées actives exactes, modèle et conventions versionnés, schéma, réglages numériques, empreintes, résultat, diagnostic, périmètre Production/UAT | Bibliothèque, archives, scénarios, Greeks, proposition, PDF |
| Commande durable | Clé d'intention stable, acteur, cible et résultat ; empreinte de payload ; conflit si même clé avec autre intention | Conservation Product, booking direct, traitement RFQ, reprises |
| Fraîcheur | Références des termes, faits, marché effectif, calibration et moteur nécessaires au résultat ; courant valide/périmé séparé de l'historique | Caches UI, MtM, Greeks, Explain, VaR, CCR et propositions |

Une correction de fixing peut changer les faits sans changer les termes. Une nouvelle politique, méthode de calcul ou source de marché ne réécrit pas le contrat booké. Les empreintes peuvent partager un format, mais chaque consommateur déclare ses dépendances matérielles ; on ne lui attribue pas artificiellement des inputs inactifs.

## C01

**Permissions métier et confidentialité**

- Lot principal : **1** ; responsabilité proposée : **Métier et plateforme — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — Revue métier D05 ; recette graphique et transverse complète, puis qualification déployée.**.
- Livraison : [rapport C01](../REMEDIATION_C01_2026-10-20.md) et [validation structurée](C01_VALIDATION.json).
- Constats : [M01-01](ANOMALY_REGISTER.md#m01-01), [M01-02](ANOMALY_REGISTER.md#m01-02), [M01-03](ANOMALY_REGISTER.md#m01-03), [M01-04](ANOMALY_REGISTER.md#m01-04), [M01-05](ANOMALY_REGISTER.md#m01-05), [M10-05](ANOMALY_REGISTER.md#m10-05), [M16-01](ANOMALY_REGISTER.md#m16-01).
- Prérequis communs : aucun.
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T01](#t01), [T12](#t12), [T14](#t14) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d’entrée de tests exercés dans la campagne ciblée C01 :**

- [backend/tests/test_rfq_desk_access.py](../../../backend/tests/test_rfq_desk_access.py)
- [backend/tests/test_client_api.py](../../../backend/tests/test_client_api.py)
- [frontend/src/stores/auth.test.js](../../../frontend/src/stores/auth.test.js)

Le périmètre exécuté, les tests supplémentaires et les limites figurent dans le rapport C01. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/api/trading.py:97](C:/Users/admin/GitHub/structura/backend/app/api/trading.py:97)
- [backend/app/api/trading.py:248](C:/Users/admin/GitHub/structura/backend/app/api/trading.py:248)
- [backend/app/api/inlife.py:405](C:/Users/admin/GitHub/structura/backend/app/api/inlife.py:405)
- [backend/app/api/product_optimizer.py:25](C:/Users/admin/GitHub/structura/backend/app/api/product_optimizer.py:25)
- [backend/app/api/compute.py:73](C:/Users/admin/GitHub/structura/backend/app/api/compute.py:73)
- [frontend/src/views/RfqView.vue:2751](C:/Users/admin/GitHub/structura/frontend/src/views/RfqView.vue:2751)
- [frontend/src/router/index.js:258](C:/Users/admin/GitHub/structura/frontend/src/router/index.js:258)
- [backend/app/services/product_repository.py:29](C:/Users/admin/GitHub/structura/backend/app/services/product_repository.py:29)

## C02

**Sessions portail et identité des installations**

- Lot principal : **1** ; responsabilité proposée : **Métier et plateforme — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement — accès du launcher et changement de compte depuis Admin, y compris à froid ; relance du portail utilisateur requise.**.
- Livraison : [rapport C02](../REMEDIATION_C02_2026-10-20.md) et [preuves](C02_VALIDATION.json).
- Décision D13 confirmée : nom canonique géré verrouillé localement ; renommage via provisionnement.
- Constats : [M01-06](ANOMALY_REGISTER.md#m01-06), [M01-07](ANOMALY_REGISTER.md#m01-07), [M01-08](ANOMALY_REGISTER.md#m01-08), [M01-09](ANOMALY_REGISTER.md#m01-09), [M01-10](ANOMALY_REGISTER.md#m01-10), [M01-11](ANOMALY_REGISTER.md#m01-11), [M01-12](ANOMALY_REGISTER.md#m01-12).
- Prérequis communs : aucun.
- Conditions et interfaces complémentaires : T01 avec C01 ; contrôle d’identité préalable pour C19. Les conventions contractuelles de C05 restent distinctes des bornes de prévisualisation.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T01](#t01) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée exercés, complétés par les tests de sessions, d'identité et de portail indiqués dans les preuves C02 :**

- [backend/tests/test_hybrid_reset.py](../../../backend/tests/test_hybrid_reset.py)
- [backend/tests/test_hybrid_installations.py](../../../backend/tests/test_hybrid_installations.py)
- [backend/tests/test_hybrid_development.py](../../../backend/tests/test_hybrid_development.py)
- [backend/tests/test_hybrid_bootstrap.py](../../../backend/tests/test_hybrid_bootstrap.py)
- [frontend/src/stores/auth.test.js](../../../frontend/src/stores/auth.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/api/auth.py:156](C:/Users/admin/GitHub/structura/backend/app/api/auth.py:156)
- [frontend/src/stores/auth.js:112](C:/Users/admin/GitHub/structura/frontend/src/stores/auth.js:112)
- [backend/app/hybrid/platform.py:153](C:/Users/admin/GitHub/structura/backend/app/hybrid/platform.py:153)
- [frontend/src/views/LoginView.vue:104](C:/Users/admin/GitHub/structura/frontend/src/views/LoginView.vue:104)
- [backend/app/api/admin.py:451](C:/Users/admin/GitHub/structura/backend/app/api/admin.py:451)
- [backend/app/api/auth.py:235](C:/Users/admin/GitHub/structura/backend/app/api/auth.py:235)
- [backend/app/api/admin.py:558](C:/Users/admin/GitHub/structura/backend/app/api/admin.py:558)
- [backend/run.py:23](C:/Users/admin/GitHub/structura/backend/run.py:23)

## C03

**Identifiants juridiques et gouvernance des référentiels**

- Lot principal : **1** ; responsabilité proposée : **Métier et plateforme — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — D01 confirmée ; recette graphique/transverse et reprise des identités historiques non qualifiées.**.
- Livraison : [rapport C03](../REMEDIATION_C03_2026-10-20.md) et [preuves](C03_VALIDATION.json).
- Complément D01 : [preuves des exceptions](C03_D01_VALIDATION.json). ID actif par défaut ; booking direct hors référentiel réservé à l’administrateur, motivé, audité, crédit non évalué. Régularisation par amendement et contrôle crédit destination. Suivi consolidé des dossiers non qualifiés à compléter dans C04/C21.
- Constats : [M02-05](ANOMALY_REGISTER.md#m02-05), [M02-06](ANOMALY_REGISTER.md#m02-06), [M02-08](ANOMALY_REGISTER.md#m02-08), [M02-11](ANOMALY_REGISTER.md#m02-11), [M02-12](ANOMALY_REGISTER.md#m02-12), [M02-13](ANOMALY_REGISTER.md#m02-13), [M10-02](ANOMALY_REGISTER.md#m10-02), [M11-01](ANOMALY_REGISTER.md#m11-01), [M11-03](ANOMALY_REGISTER.md#m11-03).
- Prérequis communs : aucun.
- Conditions et interfaces complémentaires : Identité stable transmise à C04 ; référentiel local pour C11 ; contrôle CCR existant sans clôture numérique de C21.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T04](#t04), [T05](#t05), [T12](#t12) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée exercés, complétés par les tests de gouvernance et d'identité détaillés dans les preuves C03 :**

- [backend/tests/test_rfq_transport.py](../../../backend/tests/test_rfq_transport.py)
- [backend/tests/test_rfq_relationships.py](../../../backend/tests/test_rfq_relationships.py)
- [backend/tests/test_rfq_product_exchange.py](../../../backend/tests/test_rfq_product_exchange.py)
- [backend/tests/test_rfq_network_delivery.py](../../../backend/tests/test_rfq_network_delivery.py)
- [frontend/src/views/RfqNetworkPrototypeView.test.js](../../../frontend/src/views/RfqNetworkPrototypeView.test.js)
- [frontend/src/utils/rfqNetworkPrototype.test.js](../../../frontend/src/utils/rfqNetworkPrototype.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [frontend/src/components/EconomicsTab.vue:469](C:/Users/admin/GitHub/structura/frontend/src/components/EconomicsTab.vue:469)
- [backend/app/api/rfq.py:384](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:384)
- [backend/app/api/rfq.py:421](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:421)
- [backend/app/api/admin.py:780](C:/Users/admin/GitHub/structura/backend/app/api/admin.py:780)
- [backend/app/db/database.py:896](C:/Users/admin/GitHub/structura/backend/app/db/database.py:896)
- [frontend/src/data/commonUnderlyings.js:20](C:/Users/admin/GitHub/structura/frontend/src/data/commonUnderlyings.js:20)
- [backend/app/services/rfq_execution.py:85](C:/Users/admin/GitHub/structura/backend/app/services/rfq_execution.py:85)
- [backend/app/core/ccr/service.py:770](C:/Users/admin/GitHub/structura/backend/app/core/ccr/service.py:770)

## C04

**Limites et amendements économiques**

- Lot principal : **1** ; responsabilité proposée : **Métier et plateforme — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — Requalification C21 des limites raccordée localement ; recette transverse intégrale et qualification déployée.**.
- Constats : [M02-07](ANOMALY_REGISTER.md#m02-07), [M11-02](ANOMALY_REGISTER.md#m11-02), [M15-06](ANOMALY_REGISTER.md#m15-06).
- Livraison : [rapport C04](../REMEDIATION_C04_2026-10-20.md), [preuves](C04_VALIDATION.json).
- Résultat : concentration par ID ; amendement évalué comme remplacement sous politique courante, preuve versionnée ; exceptions D01 à qualifier avant nouvel amendement.
- Prérequis communs : [C01](#c01), [C03](#c03).
- Conditions et interfaces complémentaires : C21 (qualification) : Pour les limites PFE/CVA : requalifier la décision après correction des mesures ; le contrôle nominal se sécurise plus tôt..
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T05](#t05) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée de validation ciblée :**

- [backend/tests/test_risk_dates.py](../../../backend/tests/test_risk_dates.py)
- [backend/tests/test_portfolios_crud.py](../../../backend/tests/test_portfolios_crud.py)
- [backend/tests/test_ccr_api.py](../../../backend/tests/test_ccr_api.py)
- [frontend/src/stores/portfolios.test.js](../../../frontend/src/stores/portfolios.test.js)

- [backend/tests/test_economic_amendments.py](../../../backend/tests/test_economic_amendments.py) — 30 cas C04.
- [frontend/src/components/EventsTab.test.js](../../../frontend/src/components/EventsTab.test.js) et [rendu concentration](../../../frontend/src/views/RiskManagementView.test.js).

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/api/portfolios.py:680](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:680)
- [backend/app/api/deals.py:990](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:990)
- [backend/app/api/deals.py:3272](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:3272)
- [backend/app/api/portfolios.py:700](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:700)

## C05

**Calendriers contractuels et règlement**

- Lot principal : **2** ; responsabilité proposée : **Structuration et développement — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — D02 confirmée ; recette graphique/transverse et qualification déployée ; calendriers bookés conservés.**.
- Constats : [M02-01](ANOMALY_REGISTER.md#m02-01), [M02-02](ANOMALY_REGISTER.md#m02-02), [M02-03](ANOMALY_REGISTER.md#m02-03), [M02-04](ANOMALY_REGISTER.md#m02-04), [M02-09](ANOMALY_REGISTER.md#m02-09), [M02-10](ANOMALY_REGISTER.md#m02-10), [M05-06](ANOMALY_REGISTER.md#m05-06), [M17-04](ANOMALY_REGISTER.md#m17-04).
- Prérequis communs : aucun. Contrôles C01/C02/C03/C04 préservés et exercés sur les consommateurs modifiés.
- Livraison : [rapport C05](../REMEDIATION_C05_2026-10-20.md), [preuves](C05_VALIDATION.json).
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T03](#t03), [T04](#t04), [T16](#t16) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Tests ciblés exécutés sur le périmètre annoncé :**

- [backend/tests/test_schedule_settlement.py](../../../backend/tests/test_schedule_settlement.py)
- [backend/tests/test_schedule_model.py](../../../backend/tests/test_schedule_model.py)
- [backend/tests/test_schedule.py](../../../backend/tests/test_schedule.py)
- [backend/tests/test_payscript_binding.py](../../../backend/tests/test_payscript_binding.py)

Les 46 cas de [test_contractual_calendars.py](../../../backend/tests/test_contractual_calendars.py) et les 16 cas de [EconomicsCalendars.test.js](../../../frontend/src/components/EconomicsCalendars.test.js) complètent ces points d’entrée. Les recettes T03/T04/T16 restent partielles ; aucune qualification globale n’est déduite des seuls succès HTTP.

**Implémentations citées par les audits :**

- [backend/app/core/schedule.py:87](C:/Users/admin/GitHub/structura/backend/app/core/schedule.py:87)
- [backend/app/core/payscript/parser.py:1163](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:1163)
- [frontend/src/components/EconomicsTab.vue:409](C:/Users/admin/GitHub/structura/frontend/src/components/EconomicsTab.vue:409)
- [backend/app/core/calendars.py:25](C:/Users/admin/GitHub/structura/backend/app/core/calendars.py:25)
- [backend/app/core/payscript/parser.py:1196](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:1196)
- [backend/app/core/schemas.py:583](C:/Users/admin/GitHub/structura/backend/app/core/schemas.py:583)
- [backend/app/core/payscript/parser.py:1121](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:1121)
- [backend/app/core/schedule.py:111](C:/Users/admin/GitHub/structura/backend/app/core/schedule.py:111)

## C06

**Versions Product et intégrité des transitions**

- Lot principal : **2** ; responsabilité proposée : **Structuration et développement — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — Versions et reprises C08 raccordées localement ; reprise historique, recette graphique/transverse et qualification déployée.**.
- Constats : [M04-01](ANOMALY_REGISTER.md#m04-01), [M04-02](ANOMALY_REGISTER.md#m04-02), [M04-03](ANOMALY_REGISTER.md#m04-03), [M04-07](ANOMALY_REGISTER.md#m04-07), [M09-01](ANOMALY_REGISTER.md#m09-01).
- Livraison : [rapport C06](../REMEDIATION_C06_2026-10-20.md), [preuves](C06_VALIDATION.json). C01 à C05 préservés.
- Prérequis communs : [C01](#c01).
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T02](#t02), [T12](#t12), [T13](#t13) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d’entrée et qualification ciblée :**

- [backend/tests/test_rfq_product_exchange.py](../../../backend/tests/test_rfq_product_exchange.py)
- [backend/tests/test_product_optimizer_workflow.py](../../../backend/tests/test_product_optimizer_workflow.py)
- [backend/tests/test_product_optimizer_validation.py](../../../backend/tests/test_product_optimizer_validation.py)
- [backend/tests/test_product_optimizer_payoffs.py](../../../backend/tests/test_product_optimizer_payoffs.py)
- [frontend/src/views/ProductOptimizerView.test.js](../../../frontend/src/views/ProductOptimizerView.test.js)
- [frontend/src/utils/productOptimizer.test.js](../../../frontend/src/utils/productOptimizer.test.js)

La sélection exécutée comprend notamment 72 cas de [test_product_transition_integrity.py](../../../backend/tests/test_product_transition_integrity.py) et 3 cas de [RfqProductTransition.test.js](../../../frontend/src/views/RfqProductTransition.test.js). [Rapport de validation](../REMEDIATION_C06_2026-10-20.md#validation-et-limites) : 307 cas backend distincts et 494 tests frontend ; seuls les consommateurs annoncés sont qualifiés localement. Les autres points d’entrée de cette liste ne constituent pas une couverture globale.

**Implémentations citées par les audits :**

- [backend/app/api/rfq.py:1603](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1603)
- [backend/app/api/rfq.py:332](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:332)
- [frontend/src/views/RfqView.vue:1782](C:/Users/admin/GitHub/structura/frontend/src/views/RfqView.vue:1782)
- [backend/app/api/rfq.py:1008](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1008)
- [backend/app/api/products.py:233](C:/Users/admin/GitHub/structura/backend/app/api/products.py:233)
- [backend/app/db/product_migrations.py:47](C:/Users/admin/GitHub/structura/backend/app/db/product_migrations.py:47)
- [backend/app/api/rfq.py:591](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:591)

## C07

**Conservation et reprise des saisies**

- Lot principal : **2** ; responsabilité proposée : **Structuration et développement — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — T11/T15 couverts sur leurs composantes locales ; budget de volumétrie/SLA à fixer, recette graphique et qualification déployée.**.
- Constats : [M04-04](ANOMALY_REGISTER.md#m04-04), [M04-05](ANOMALY_REGISTER.md#m04-05), [M04-08](ANOMALY_REGISTER.md#m04-08), [M04-10](ANOMALY_REGISTER.md#m04-10), [M05-02](ANOMALY_REGISTER.md#m05-02), [M05-03](ANOMALY_REGISTER.md#m05-03), [M05-04](ANOMALY_REGISTER.md#m05-04), [M05-05](ANOMALY_REGISTER.md#m05-05), [M07-07](ANOMALY_REGISTER.md#m07-07), [M08-06](ANOMALY_REGISTER.md#m08-06), [M11-06](ANOMALY_REGISTER.md#m11-06), [M13-04](ANOMALY_REGISTER.md#m13-04).
- Prérequis communs : [C06](#c06).
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T11](#t11), [T15](#t15) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée initiaux ; résultats exécutés détaillés dans C07_VALIDATION.json :**

- [backend/tests/test_rfq_product_exchange.py](../../../backend/tests/test_rfq_product_exchange.py)
- [backend/tests/test_rfq_bank_pricing.py](../../../backend/tests/test_rfq_bank_pricing.py)
- [backend/tests/test_product_optimizer_workflow.py](../../../backend/tests/test_product_optimizer_workflow.py)
- [backend/tests/test_product_optimizer_validation.py](../../../backend/tests/test_product_optimizer_validation.py)
- [frontend/src/views/ProductOptimizerView.test.js](../../../frontend/src/views/ProductOptimizerView.test.js)
- [frontend/src/utils/productOptimizer.test.js](../../../frontend/src/utils/productOptimizer.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/api/products.py:120](C:/Users/admin/GitHub/structura/backend/app/api/products.py:120)
- [frontend/src/stores/products.js:62](C:/Users/admin/GitHub/structura/frontend/src/stores/products.js:62)
- [frontend/src/views/PricerView.vue:111](C:/Users/admin/GitHub/structura/frontend/src/views/PricerView.vue:111)
- [backend/app/core/product/inputs.py:21](C:/Users/admin/GitHub/structura/backend/app/core/product/inputs.py:21)
- [frontend/src/stores/pricing.js:439](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:439)
- [frontend/src/utils/productCalculations.js:32](C:/Users/admin/GitHub/structura/frontend/src/utils/productCalculations.js:32)
- [backend/app/api/products.py:193](C:/Users/admin/GitHub/structura/backend/app/api/products.py:193)
- [frontend/src/views/ProductsView.vue:31](C:/Users/admin/GitHub/structura/frontend/src/views/ProductsView.vue:31)

**Validation locale C07 — 21/10 :** [rapport](../REMEDIATION_C07_2026-10-21.md) et [preuves](C07_VALIDATION.json). 303 cas backend distincts sur 10 fichiers, dont 47 C07 ; 541 tests frontend et build, dont 47 C07. Les tests ciblés maintiennent C01/C03/C04/C05/C06. Pagination mesurée sur 220 dossiers ; budget de production à définir.

Nouveaux tests : [backend](../../../backend/tests/test_input_retention.py), [store et frontières](../../../frontend/src/stores/inputRetention.test.js), [interfaces](../../../frontend/src/components/InputRetentionUi.test.js).

## C08

**Idempotence des commandes et filiation**

- Lot principal : **6** ; responsabilité proposée : **Exécution et opérations — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — Commandes et filiation validées localement, raccord C20/C23 exercé ; recette graphique/transverse et qualification déployée.**.
- Constats : [M04-06](ANOMALY_REGISTER.md#m04-06), [M11-04](ANOMALY_REGISTER.md#m11-04), [M11-05](ANOMALY_REGISTER.md#m11-05).
- Prérequis communs : [C01](#c01), [C06](#c06).
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T02](#t02), [T12](#t12) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée existants de tests à examiner, non exécutés :**

- [backend/tests/test_rfq_transport.py](../../../backend/tests/test_rfq_transport.py)
- [backend/tests/test_rfq_relationships.py](../../../backend/tests/test_rfq_relationships.py)
- [backend/tests/test_rfq_product_exchange.py](../../../backend/tests/test_rfq_product_exchange.py)
- [backend/tests/test_rfq_network_delivery.py](../../../backend/tests/test_rfq_network_delivery.py)
- [frontend/src/views/RfqNetworkPrototypeView.test.js](../../../frontend/src/views/RfqNetworkPrototypeView.test.js)
- [frontend/src/views/ProductOptimizerView.test.js](../../../frontend/src/views/ProductOptimizerView.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [frontend/src/stores/products.js:90](C:/Users/admin/GitHub/structura/frontend/src/stores/products.js:90)
- [backend/app/api/deals.py:2044](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2044)
- [backend/app/api/deals.py:2396](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2396)
- [frontend/src/components/DealTab.vue:607](C:/Users/admin/GitHub/structura/frontend/src/components/DealTab.vue:607)
- [frontend/src/components/DealTab.vue:751](C:/Users/admin/GitHub/structura/frontend/src/components/DealTab.vue:751)

**Complément C08 — 22/10 :** [rapport](../REMEDIATION_C08_2026-10-22.md), [preuves](C08_VALIDATION.json). 317 cas backend distincts (31 nouveaux), 697 tests frontend et build temporaire réussis. Reprises et filiation qualifiées localement ; les mentions antérieures « C08 global ouvert » sont historiques. Recette graphique interactive et qualification déployée restantes.

## C09

**Compilation PayScript et qualification du payoff**

- Lot principal : **2** ; responsabilité proposée : **Structuration et développement — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — T03/T15 couverts localement ; recette graphique/transverse et qualification déployée.**.
- Constats : [M05-01](ANOMALY_REGISTER.md#m05-01), [M05-08](ANOMALY_REGISTER.md#m05-08), [M08-03](ANOMALY_REGISTER.md#m08-03).
- Prérequis communs : aucun.
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T03](#t03), [T15](#t15) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée de tests validés localement :**

- [backend/tests/test_product_optimizer_workflow.py](../../../backend/tests/test_product_optimizer_workflow.py)
- [backend/tests/test_product_optimizer_validation.py](../../../backend/tests/test_product_optimizer_validation.py)
- [backend/tests/test_product_optimizer_payoffs.py](../../../backend/tests/test_product_optimizer_payoffs.py)
- [backend/tests/test_product_optimizer_participation.py](../../../backend/tests/test_product_optimizer_participation.py)
- [frontend/src/views/ProductOptimizerView.test.js](../../../frontend/src/views/ProductOptimizerView.test.js)
- [frontend/src/views/OptimizerResultsView.test.js](../../../frontend/src/views/OptimizerResultsView.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/core/payscript/parser.py:458](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:458)
- [backend/app/services/llm/validate.py:130](C:/Users/admin/GitHub/structura/backend/app/services/llm/validate.py:130)
- [backend/app/core/product_optimizer/families.py:70](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/families.py:70)
- [backend/app/core/product_optimizer/validation.py:17](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/validation.py:17)

**Livraison C09 :** [rapport](../REMEDIATION_C09_2026-10-21.md), [preuves](C09_VALIDATION.json), 48 nouveaux cas dans `backend/tests/test_payoff_qualification.py` et 5 cas dans `frontend/src/components/ScriptAssistantModal.test.js`. Le panel versionné couvre 552 trajectoires sur les huit sources approuvées. C05 à C07 restent exercés ; la chronologie C14, les archives C19 et les budgets C20 restent ouverts.

## C10

**Réponses tardives et erreurs dans les interfaces**

- Lot principal : **2** ; responsabilité proposée : **Structuration et développement — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — C17/T11 raccordés localement ; recette graphique de chaîne et qualification déployée.**.
- Constats : [M03-03](ANOMALY_REGISTER.md#m03-03), [M05-07](ANOMALY_REGISTER.md#m05-07), [M07-02](ANOMALY_REGISTER.md#m07-02), [M09-06](ANOMALY_REGISTER.md#m09-06), [M09-09](ANOMALY_REGISTER.md#m09-09), [M10-03](ANOMALY_REGISTER.md#m10-03), [M10-04](ANOMALY_REGISTER.md#m10-04), [M12-06](ANOMALY_REGISTER.md#m12-06).
- Prérequis communs : aucun.
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T11](#t11) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée existants de tests à examiner, non exécutés :**

- [backend/tests/test_rfq_transport.py](../../../backend/tests/test_rfq_transport.py)
- [backend/tests/test_rfq_relationships.py](../../../backend/tests/test_rfq_relationships.py)
- [backend/tests/test_rfq_product_exchange.py](../../../backend/tests/test_rfq_product_exchange.py)
- [backend/tests/test_rfq_network_delivery.py](../../../backend/tests/test_rfq_network_delivery.py)
- [frontend/src/views/RfqNetworkPrototypeView.test.js](../../../frontend/src/views/RfqNetworkPrototypeView.test.js)
- [frontend/src/utils/smileCalibration.test.js](../../../frontend/src/utils/smileCalibration.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [frontend/src/stores/pricing.js:2037](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:2037)
- [frontend/src/composables/useObservationPreview.js:43](C:/Users/admin/GitHub/structura/frontend/src/composables/useObservationPreview.js:43)
- [frontend/src/utils/smileCalibration.js:5](C:/Users/admin/GitHub/structura/frontend/src/utils/smileCalibration.js:5)
- [frontend/src/stores/pricing.js:1003](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:1003)
- [frontend/src/stores/rfq.js:50](C:/Users/admin/GitHub/structura/frontend/src/stores/rfq.js:50)
- [frontend/src/views/RfqView.vue:2538](C:/Users/admin/GitHub/structura/frontend/src/views/RfqView.vue:2538)
- [frontend/src/components/RfqExecutionPanel.vue:20](C:/Users/admin/GitHub/structura/frontend/src/components/RfqExecutionPanel.vue:20)
- [frontend/src/views/RfqInboxView.vue:82](C:/Users/admin/GitHub/structura/frontend/src/views/RfqInboxView.vue:82)

**Livraison C10 :** [rapport](../REMEDIATION_C10_2026-10-21.md), [preuves](C10_VALIDATION.json), 69 nouveaux cas frontend, 615 tests frontend et build, 37 tests backend ciblés. Les réponses de marché, calendriers, calibration et RFQ restent liées à leur contexte ; les refus ne produisent pas de succès local. La qualification quantitative reste C17. Les points de départ ci-dessus conservent leur statut documentaire ; seuls les fichiers annoncés dans la preuve ont été exécutés pour C10.

## C11

**Données de marché datées et couverture**

- Lot principal : **3** ; responsabilité proposée : **Données et opérations — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — T04 combiné validé localement, T10 complété par C21/C24/C27 ; qualification graphique/transverse et déployée.**.
- Constats : [M03-02](ANOMALY_REGISTER.md#m03-02), [M03-04](ANOMALY_REGISTER.md#m03-04), [M03-05](ANOMALY_REGISTER.md#m03-05), [M03-06](ANOMALY_REGISTER.md#m03-06), [M03-07](ANOMALY_REGISTER.md#m03-07), [M03-08](ANOMALY_REGISTER.md#m03-08), [M03-10](ANOMALY_REGISTER.md#m03-10).
- Prérequis communs : [C03](#c03).
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T04](#t04), [T10](#t10) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée de validation ciblée :**

- [backend/tests/test_studies_dividends.py](../../../backend/tests/test_studies_dividends.py)
- [backend/tests/test_market_data_lot4.py](../../../backend/tests/test_market_data_lot4.py)
- [backend/tests/test_dividend_profile.py](../../../backend/tests/test_dividend_profile.py)
- [backend/tests/test_dividend_curve.py](../../../backend/tests/test_dividend_curve.py)

Les résultats et limites sont décrits dans les preuves C11.

**Implémentations citées par les audits :**

- [backend/app/services/market_data.py:138](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:138)
- [frontend/src/views/RfqView.vue:2141](C:/Users/admin/GitHub/structura/frontend/src/views/RfqView.vue:2141)
- [backend/app/services/market_data.py:324](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:324)
- [backend/app/core/amc_prices.py:320](C:/Users/admin/GitHub/structura/backend/app/core/amc_prices.py:320)
- [backend/app/services/market_data.py:111](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:111)
- [backend/app/core/payscript/engine.py:85](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:85)
- [backend/app/services/market_data.py:346](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:346)
- [backend/app/api/pricing.py:995](C:/Users/admin/GitHub/structura/backend/app/api/pricing.py:995)

**Livraison C11 — 21/10/2026 :** [rapport](../REMEDIATION_C11_2026-10-21.md), [preuves](C11_VALIDATION.json). Les 33 cas de `test_market_data_governance.py` et 16 cas de `marketDataGovernance.test.js` complètent les points d’entrée. D03/C11 confirmé par Philippe : 3 jours calendaires pour les cours EOD et le FX de reporting, borne incluse. L’import C12, la finalité C13, les métriques C21 et le profil C27 restent ouverts.

## C12

**Stockage atomique des séries et caches**

- Lot principal : **3** ; responsabilité proposée : **Données et opérations — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — T04 combiné validé localement ; recette graphique/déployée et politique de rétention des générations à préciser.**.
- Constats : [M03-09](ANOMALY_REGISTER.md#m03-09), [M03-11](ANOMALY_REGISTER.md#m03-11).
- Prérequis communs : [C03](#c03).
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T04](#t04) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée de validation ciblée :**

- [backend/tests/test_market_data_lot4.py](../../../backend/tests/test_market_data_lot4.py)

Les résultats, cas exécutés et limites sont décrits dans les preuves C12.

**Implémentations citées par les audits :**

- [backend/app/core/amc_prices.py:176](C:/Users/admin/GitHub/structura/backend/app/core/amc_prices.py:176)
- [backend/app/core/amc_prices.py:129](C:/Users/admin/GitHub/structura/backend/app/core/amc_prices.py:129)
- [backend/app/services/market_data.py:284](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:284)

**Livraison C12 — 21/10/2026 :** [rapport](../REMEDIATION_C12_2026-10-21.md), [preuves](C12_VALIDATION.json). 57 nouveaux cas backend et six cas frontend complètent ces points d’entrée. Les imports, associations et copies C11 se publient ensemble ; les réponses et vues locales restent indépendantes. D03/C11 reste à 3 jours calendaires. Les anciens fichiers ne sont pas migrés ; la qualification production et la finalité C13 restent ouvertes.

## C13

**Finalité des cours et registre officiel**

- Lot principal : **3** ; responsabilité proposée : **Données et opérations — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — T08 enrichi par C18/C19/C21/C22/C26 ; D06 et chaîne déployée complète restantes ; F02 résolu localement par correction de fixture, migration applicative inchangée.**.
- Constats : [M03-01](ANOMALY_REGISTER.md#m03-01), [M12-01](ANOMALY_REGISTER.md#m12-01), [M12-02](ANOMALY_REGISTER.md#m12-02), [M12-05](ANOMALY_REGISTER.md#m12-05), [M13-01](ANOMALY_REGISTER.md#m13-01).
- Prérequis communs : [C05](#c05), [C11](#c11).
- Conditions et interfaces complémentaires : C06 (interface) : Une correction de fixing fait évoluer les faits et la révision du dossier sans changer artificiellement les termes..
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T08](#t08) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée existants de tests à examiner, non exécutés :**

- [backend/tests/test_prestrike_mtm.py](../../../backend/tests/test_prestrike_mtm.py)
- [backend/tests/test_mtm_explain.py](../../../backend/tests/test_mtm_explain.py)
- [backend/tests/test_lifecycle_fenetres.py](../../../backend/tests/test_lifecycle_fenetres.py)
- [backend/tests/test_lifecycle_alerts.py](../../../backend/tests/test_lifecycle_alerts.py)
- [frontend/src/composables/useBookingMtm.test.js](../../../frontend/src/composables/useBookingMtm.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/api/deals.py:4564](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:4564)
- [backend/app/services/market_data.py:427](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:427)
- [backend/app/api/deals.py:5220](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:5220)
- [frontend/src/components/EventsTab.vue:810](C:/Users/admin/GitHub/structura/frontend/src/components/EventsTab.vue:810)
- [backend/app/api/deals.py:5228](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:5228)
- [backend/app/api/deals.py:5124](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:5124)
- [backend/app/api/deals.py:5132](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:5132)
- [backend/app/core/deal_valuation.py:251](C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py:251)

## C14

**Axe temporel et ordre des événements**

- Lot principal : **4** ; responsabilité proposée : **Quant et valorisation — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — T03 et composantes T09 raccordés localement ; recette transverse et qualification déployée.**.
- Constats : [M06-05](ANOMALY_REGISTER.md#m06-05), [M06-06](ANOMALY_REGISTER.md#m06-06), [M13-02](ANOMALY_REGISTER.md#m13-02).
- Prérequis communs : [C05](#c05), [C09](#c09).
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T03](#t03), [T06](#t06), [T07](#t07), [T09](#t09) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée existants de tests à examiner, non exécutés :**

- [backend/tests/test_var_engine.py](../../../backend/tests/test_var_engine.py)
- [backend/tests/test_prestrike_mtm.py](../../../backend/tests/test_prestrike_mtm.py)
- [backend/tests/test_payscript_binding.py](../../../backend/tests/test_payscript_binding.py)
- [backend/tests/test_mtm_explain.py](../../../backend/tests/test_mtm_explain.py)
- [frontend/src/composables/useBookingMtm.test.js](../../../frontend/src/composables/useBookingMtm.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/core/payscript/engine.py:2231](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2231)
- [backend/app/core/payscript/engine.py:3070](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:3070)
- [backend/app/core/payscript/engine.py:3208](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:3208)
- [backend/app/core/payscript/engine.py:1838](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:1838)
- [backend/app/core/deal_valuation.py:244](C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py:244)
- [backend/app/core/payscript/engine.py:2221](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2221)

## C15

**Taux stochastiques funding et corrélations**

- Lot principal : **4** ; responsabilité proposée : **Quant et valorisation — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — C18/T06 raccordés localement ; funding hors taux stochastiques et drift ; domaine D04 et qualification déployée restants.**.
- Constats : [M06-01](ANOMALY_REGISTER.md#m06-01), [M06-02](ANOMALY_REGISTER.md#m06-02), [M06-04](ANOMALY_REGISTER.md#m06-04).
- Prérequis communs : [C14](#c14).
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T06](#t06) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée du lot 0, exercés localement sur le périmètre C15 :**

- [backend/tests/test_var_engine.py](../../../backend/tests/test_var_engine.py)
- [backend/tests/test_market_snapshot_rate.py](../../../backend/tests/test_market_snapshot_rate.py)
- [backend/tests/test_engine_golden.py](../../../backend/tests/test_engine_golden.py)
- [backend/tests/test_engine.py](../../../backend/tests/test_engine.py)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/core/payscript/engine.py:2333](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2333)
- [backend/app/core/payscript/engine.py:429](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:429)
- [backend/app/core/payscript/engine.py:984](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:984)

**Complément C15 :** 105 cas spécifiques et 126 contrôles voisins réussis. [Panel numérique](../../../backend/tests/test_stochastic_rate_integrity.py). La dépendance C15 vers C18 pour le raccordement du funding stochastique est satisfaite au niveau du moteur ; la recette du consommateur reste requise.

## C16

**Dépendance des extrema et barrières**

- Lot principal : **4** ; responsabilité proposée : **Quant et valorisation — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — C18/T07 raccordés localement dans le domaine restreint C16, seuil de panel 10 pb ; extensions de domaine et qualification déployée restantes.**.
- Constats : [M06-03](ANOMALY_REGISTER.md#m06-03).
- Prérequis communs : [C14](#c14).
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T07](#t07) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée du lot 0, exercés localement sur le périmètre C16 :**

- [backend/tests/test_var_engine.py](../../../backend/tests/test_var_engine.py)
- [backend/tests/test_portfolio_barriers.py](../../../backend/tests/test_portfolio_barriers.py)
- [backend/tests/test_engine_golden.py](../../../backend/tests/test_engine_golden.py)
- [backend/tests/test_engine.py](../../../backend/tests/test_engine.py)
- [frontend/src/utils/barriers.test.js](../../../frontend/src/utils/barriers.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/core/payscript/engine.py:857](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:857)

## C17

**Surfaces calibration et diagnostics**

- Lot principal : **4** ; responsabilité proposée : **Quant et valorisation — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — Points publiés et garde asynchrone C10 raccordés localement, seuils 5/10 pb ; domaine élargi et qualification déployée restants.**.
- Constats : [M07-01](ANOMALY_REGISTER.md#m07-01), [M07-03](ANOMALY_REGISTER.md#m07-03), [M07-04](ANOMALY_REGISTER.md#m07-04), [M07-05](ANOMALY_REGISTER.md#m07-05), [M07-06](ANOMALY_REGISTER.md#m07-06).
- Prérequis communs : [C11](#c11), [C14](#c14).
- Conditions et interfaces complémentaires : C10 (qualification) : Protéger l'application asynchrone avant d'annoncer une calibration actuelle..
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T11](#t11) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points de départ du registre ; exécutions effectives dans la preuve C17 :**

- [backend/tests/test_realized_calibration.py](../../../backend/tests/test_realized_calibration.py)
- [backend/tests/test_editable_vol_surface.py](../../../backend/tests/test_editable_vol_surface.py)
- [backend/tests/test_dupire_calibration.py](../../../backend/tests/test_dupire_calibration.py)
- [backend/tests/test_common_surface.py](../../../backend/tests/test_common_surface.py)
- [frontend/src/utils/volSurface.test.js](../../../frontend/src/utils/volSurface.test.js)
- [frontend/src/utils/smileCalibration.test.js](../../../frontend/src/utils/smileCalibration.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/core/smile_calibration.py:37](C:/Users/admin/GitHub/structura/backend/app/core/smile_calibration.py:37)
- [backend/app/core/payscript/engine.py:238](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:238)
- [backend/app/core/smile_calibration.py:85](C:/Users/admin/GitHub/structura/backend/app/core/smile_calibration.py:85)
- [frontend/src/utils/smileCalibration.js:24](C:/Users/admin/GitHub/structura/frontend/src/utils/smileCalibration.js:24)
- [backend/app/core/smile_calibration.py:13](C:/Users/admin/GitHub/structura/backend/app/core/smile_calibration.py:13)
- [frontend/src/stores/pricing.js:613](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:613)
- [backend/app/core/valuation_context.py:301](C:/Users/admin/GitHub/structura/backend/app/core/valuation_context.py:301)

**Complément C17 :** tous les piliers matériels dans l’horizon sont contrôlés ; convergence distincte de la qualification, seuils de 5 pb vanilles et 10 pb digitales. Preuve serveur conservée avec le prix et rechargée du Product. Local Vol legacy invalide refusé. SABR exploratoire et composante Heston du LSV sans application automatique ; C18 reste nécessaire pour les consommateurs et contextes élargis.

## C18

**Contexte commun de valorisation et sémantique**

- Lot principal : **5** ; responsabilité proposée : **Quant et valorisation — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — Raccords locaux C13/C15/C16/C17, puis C19/C21/C22/C25 livrés ; recette transverse/graphique et qualification déployée restantes.**.
- Constats : [M06-07](ANOMALY_REGISTER.md#m06-07), [M06-08](ANOMALY_REGISTER.md#m06-08), [M06-09](ANOMALY_REGISTER.md#m06-09), [M13-07](ANOMALY_REGISTER.md#m13-07), [M14-05](ANOMALY_REGISTER.md#m14-05), [M15-07](ANOMALY_REGISTER.md#m15-07), [M17-01](ANOMALY_REGISTER.md#m17-01).
- Prérequis communs : [C06](#c06), [C14](#c14).
- Conditions et interfaces complémentaires : C15 (qualification) : Si taux stochastiques : corriger le moteur avant de raccorder funding et facteurs aux consommateurs. C16 (qualification) : Si monitoring continu de panier : qualifier les extrema avant d'élargir la capacité. C17 (qualification) : Si modèle calibré : conserver preuve et domaine ; un GBM explicite n'attend pas la qualification Heston. C13 (qualification) : Pour les valorisations en vie : reprendre les faits officiels cohérents..
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T06](#t06), [T07](#t07), [T08](#t08), [T09](#t09), [T13](#t13), [T16](#t16) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points de départ du registre ; exécutions effectives dans la preuve C18 :**

- [backend/tests/test_var_engine.py](../../../backend/tests/test_var_engine.py)
- [backend/tests/test_valuation_context.py](../../../backend/tests/test_valuation_context.py)
- [backend/tests/test_prestrike_mtm.py](../../../backend/tests/test_prestrike_mtm.py)
- [backend/tests/test_mtm_explain.py](../../../backend/tests/test_mtm_explain.py)
- [frontend/src/composables/useBookingMtm.test.js](../../../frontend/src/composables/useBookingMtm.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/api/pricing.py:342](C:/Users/admin/GitHub/structura/backend/app/api/pricing.py:342)
- [backend/app/api/pricing.py:398](C:/Users/admin/GitHub/structura/backend/app/api/pricing.py:398)
- [backend/app/core/payscript/engine.py:2693](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2693)
- [backend/app/api/pricing.py:182](C:/Users/admin/GitHub/structura/backend/app/api/pricing.py:182)
- [frontend/src/components/ProbaTab.vue:155](C:/Users/admin/GitHub/structura/frontend/src/components/ProbaTab.vue:155)
- [frontend/src/components/ResultsPanel.vue:111](C:/Users/admin/GitHub/structura/frontend/src/components/ResultsPanel.vue:111)
- [backend/app/api/deals.py:6915](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:6915)
- [frontend/src/views/DealValuationsView.vue:264](C:/Users/admin/GitHub/structura/frontend/src/views/DealValuationsView.vue:264)

**Complément C18 :** prix et analyses réutilisent le même Monte Carlo et un contexte daté, y compris avant strike. Greeks avec antithétiques de la base, bump de corrélation effectif publié, vega LSV inchangé numériquement et correctement qualifié. Source effective partagée par historique/Explain, créances détachées réactualisées, scan raccordé au contexte de booking ; solveur et grille du Pricer raccordés au contexte actif. Aucune extension implicite de qualification C15–C17.

## C19

**Archives rejeu et documents figés**

- Lot principal : **5** ; responsabilité proposée : **Quant et valorisation — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — D10/D11 confirmées ; garde d’identité locale disponible ; adoption/migration réelle et recette graphique/déployée restantes.**.
- Constats : [M04-09](ANOMALY_REGISTER.md#m04-09), [M08-04](ANOMALY_REGISTER.md#m08-04), [M09-05](ANOMALY_REGISTER.md#m09-05), [M13-03](ANOMALY_REGISTER.md#m13-03), [M13-05](ANOMALY_REGISTER.md#m13-05), [M13-06](ANOMALY_REGISTER.md#m13-06), [M14-03](ANOMALY_REGISTER.md#m14-03), [M14-04](ANOMALY_REGISTER.md#m14-04), [M17-05](ANOMALY_REGISTER.md#m17-05).
- Prérequis communs : [C06](#c06), [C18](#c18).
- Conditions et interfaces complémentaires : C02 (conditionnelle) : Avant migration des archives : vérifier l'identité de base ; les formats se préparent indépendamment..
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T08](#t08), [T13](#t13), [T15](#t15), [T16](#t16) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Tests ciblés exécutés ; voir les preuves et limites dans le rapport C19 :**

- [backend/tests/test_valuation_pdf.py](../../../backend/tests/test_valuation_pdf.py)
- [backend/tests/test_valuation_notes.py](../../../backend/tests/test_valuation_notes.py)
- [backend/tests/test_rfq_product_exchange.py](../../../backend/tests/test_rfq_product_exchange.py)
- [backend/tests/test_product_optimizer_workflow.py](../../../backend/tests/test_product_optimizer_workflow.py)
- [frontend/src/views/ProductOptimizerView.test.js](../../../frontend/src/views/ProductOptimizerView.test.js)
- [frontend/src/utils/productOptimizer.test.js](../../../frontend/src/utils/productOptimizer.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/services/product_repository.py:236](C:/Users/admin/GitHub/structura/backend/app/services/product_repository.py:236)
- [backend/app/services/optimizer_research.py:26](C:/Users/admin/GitHub/structura/backend/app/services/optimizer_research.py:26)
- [backend/app/db/models.py:95](C:/Users/admin/GitHub/structura/backend/app/db/models.py:95)
- [backend/app/api/rfq.py:1100](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1100)
- [backend/app/api/rfq.py:1723](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1723)
- [backend/app/core/deal_valuation.py:151](C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py:151)
- [backend/app/core/risk_lifecycle.py:38](C:/Users/admin/GitHub/structura/backend/app/core/risk_lifecycle.py:38)
- [backend/app/core/inlife_valuation.py:358](C:/Users/admin/GitHub/structura/backend/app/core/inlife_valuation.py:358)

**Livraison C19 :** [rapport](../REMEDIATION_C19_2026-10-21.md), [preuves](C19_VALIDATION.json). 444 cas backend et 55 tests frontend réussis ; compilation temporaire validée. 104 échecs préexistants reproduits, sans affaiblissement des contrôles.

## C20

**Recherche Optimizer et budgets**

- Lot principal : **7** ; responsabilité proposée : **Structuration et commercial — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — Reprises C08 et T15 raccordées localement ; D12/budget souple explicite, recette graphique et qualification déployée restantes.**.
- Constats : [M08-01](ANOMALY_REGISTER.md#m08-01), [M08-02](ANOMALY_REGISTER.md#m08-02), [M08-05](ANOMALY_REGISTER.md#m08-05), [M08-07](ANOMALY_REGISTER.md#m08-07).
- Prérequis communs : [C09](#c09), [C18](#c18).
- Conditions et interfaces complémentaires : C08 (conditionnelle) : La répétition d'une conservation de recherche ne crée pas de dossier supplémentaire..
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T15](#t15) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Tests ciblés exécutés ; voir le rapport et les preuves C20 :**

- [backend/tests/test_product_optimizer_workflow.py](../../../backend/tests/test_product_optimizer_workflow.py)
- [backend/tests/test_product_optimizer_validation.py](../../../backend/tests/test_product_optimizer_validation.py)
- [backend/tests/test_product_optimizer_payoffs.py](../../../backend/tests/test_product_optimizer_payoffs.py)
- [backend/tests/test_product_optimizer_participation.py](../../../backend/tests/test_product_optimizer_participation.py)
- [frontend/src/views/ProductOptimizerView.test.js](../../../frontend/src/views/ProductOptimizerView.test.js)
- [frontend/src/views/OptimizerResultsView.test.js](../../../frontend/src/views/OptimizerResultsView.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/services/optimizer_research.py:90](C:/Users/admin/GitHub/structura/backend/app/services/optimizer_research.py:90)
- [backend/app/core/product_optimizer/service.py:150](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/service.py:150)
- [backend/app/core/product_optimizer/service.py:274](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/service.py:274)
- [backend/app/core/product_optimizer/service.py:385](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/service.py:385)
- [backend/app/core/product_optimizer/capabilities.py:29](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/capabilities.py:29)

**Livraison C20 :** [rapport](../REMEDIATION_C20_2026-10-22.md), [preuves](C20_VALIDATION.json). 219 cas backend et 28 tests frontend réussis ; build temporaire validé. C08 conditionnelle vérifiée pour les retries ; C08 global reste ouvert.

## C21

**Couverture des risques CVA et fraîcheur**

- Lot principal : **5** ; responsabilité proposée : **Quant et valorisation — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — Prérequis C27 soldé localement ; composantes T05/T08/T09/T10 exercées ; D08, recette transverse et qualification déployée restantes.**.
- Constats : [M15-01](ANOMALY_REGISTER.md#m15-01), [M15-02](ANOMALY_REGISTER.md#m15-02), [M15-04](ANOMALY_REGISTER.md#m15-04), [M15-05](ANOMALY_REGISTER.md#m15-05).
- Prérequis communs : [C03](#c03), [C14](#c14), [C18](#c18), [C27](#c27).
- Conditions et interfaces complémentaires : C13 (qualification) : Une correction de fixing invalide le courant sans effacer les runs historiques..
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T05](#t05), [T08](#t08), [T09](#t09), [T10](#t10) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée du lot 0, complétés par les preuves C21 :**

- [backend/tests/test_var_engine.py](../../../backend/tests/test_var_engine.py)
- [backend/tests/test_shocks.py](../../../backend/tests/test_shocks.py)
- [backend/tests/test_seed_ccr_test_client.py](../../../backend/tests/test_seed_ccr_test_client.py)
- [backend/tests/test_risk_dates.py](../../../backend/tests/test_risk_dates.py)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/core/var_engine.py:184](C:/Users/admin/GitHub/structura/backend/app/core/var_engine.py:184)
- [backend/app/core/var_engine.py:168](C:/Users/admin/GitHub/structura/backend/app/core/var_engine.py:168)
- [backend/app/api/portfolios.py:261](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:261)
- [backend/app/api/portfolios.py:338](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:338)
- [backend/app/core/ccr/service.py:496](C:/Users/admin/GitHub/structura/backend/app/core/ccr/service.py:496)
- [backend/app/core/ccr/exposure.py:110](C:/Users/admin/GitHub/structura/backend/app/core/ccr/exposure.py:110)
- [backend/app/api/ccr.py:158](C:/Users/admin/GitHub/structura/backend/app/api/ccr.py:158)
- [backend/app/core/ccr/cache.py:13](C:/Users/admin/GitHub/structura/backend/app/core/ccr/cache.py:13)

**Livraison C21 :** [rapport](../REMEDIATION_C21_2026-10-22.md), [preuves](C21_VALIDATION.json). 226 cas backend, 660 tests frontend et build temporaire réussis. C03/C04/C13/C14/C18/C19 exercés ; défaut Production et UAT explicite sur Greeks/VaR. C27 global reste ouvert.

**Solde C27 — 22/10 :** [rapport](../REMEDIATION_C27_2026-10-22.md), [preuves](C27_VALIDATION.json). Production par défaut, UAT explicite sur les agrégats, calculs et historiques ; anciens résultats non qualifiés consultables, vues archivées conservées, réponses tardives exclues. C21/C24/C26 réexercés : 65 tests backend ciblés, 731 tests frontend et build réussis. Recette transverse, graphique et qualification déployée restantes.

## C22

**P&L cash et attribution**

- Lot principal : **5** ; responsabilité proposée : **Quant et valorisation — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — Composantes T08/T09 raccordées localement ; D07 et recette transverse/graphique/déployée restantes.**.
- Constats : [M14-01](ANOMALY_REGISTER.md#m14-01), [M14-02](ANOMALY_REGISTER.md#m14-02).
- Prérequis communs : [C13](#c13), [C18](#c18), [C19](#c19).
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T08](#t08), [T09](#t09) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée du lot 0, complétés par les preuves C22 :**

- [backend/tests/test_valuation_notes.py](../../../backend/tests/test_valuation_notes.py)
- [backend/tests/test_portfolio_pnl.py](../../../backend/tests/test_portfolio_pnl.py)
- [backend/tests/test_mtm_explain.py](../../../backend/tests/test_mtm_explain.py)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/api/deals.py:7292](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:7292)
- [backend/app/api/portfolios.py:553](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:553)
- [backend/app/api/deals.py:7266](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:7266)
- [backend/app/core/valuation_notes.py:164](C:/Users/admin/GitHub/structura/backend/app/core/valuation_notes.py:164)

**Livraison C22 :** [rapport](../REMEDIATION_C22_2026-10-22.md), [preuves](C22_VALIDATION.json). 161 cas backend et 662 tests frontend réussis ; PDF et build temporaire validés. C13/C18/C19/C21 préservés, cash contractuel distingué de la preuve de paiement bancaire.

## C23

**Cotations tours RFQ et exécutions réseau**

- Lot principal : **6** ; responsabilité proposée : **Exécution et opérations — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — C08 et limites résultantes C04 réexercés ; réseau applicatif simulé localement ; recette réelle bilatérale et qualification déployée restantes.**.
- Constats : [M09-02](ANOMALY_REGISTER.md#m09-02), [M09-03](ANOMALY_REGISTER.md#m09-03), [M09-04](ANOMALY_REGISTER.md#m09-04), [M09-07](ANOMALY_REGISTER.md#m09-07), [M09-08](ANOMALY_REGISTER.md#m09-08), [M10-01](ANOMALY_REGISTER.md#m10-01).
- Prérequis communs : [C01](#c01), [C03](#c03), [C06](#c06), [C08](#c08).
- Conditions et interfaces complémentaires : C04 (qualification) : Pour confirmer booking et amendement : contrôler les limites sur la position résultante..
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T12](#t12) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d’entrée RFQ examinés et exécutés sur le périmètre ciblé :**

- [backend/tests/test_rfq_transport.py](../../../backend/tests/test_rfq_transport.py)
- [backend/tests/test_rfq_relationships.py](../../../backend/tests/test_rfq_relationships.py)
- [backend/tests/test_rfq_product_exchange.py](../../../backend/tests/test_rfq_product_exchange.py)
- [backend/tests/test_rfq_network_delivery.py](../../../backend/tests/test_rfq_network_delivery.py)
- [frontend/src/views/RfqNetworkPrototypeView.test.js](../../../frontend/src/views/RfqNetworkPrototypeView.test.js)
- [frontend/src/utils/rfqNetworkPrototype.test.js](../../../frontend/src/utils/rfqNetworkPrototype.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [frontend/src/views/RfqAnalysisView.vue:160](C:/Users/admin/GitHub/structura/frontend/src/views/RfqAnalysisView.vue:160)
- [backend/app/services/rfq_publication.py:110](C:/Users/admin/GitHub/structura/backend/app/services/rfq_publication.py:110)
- [backend/app/api/rfq.py:1959](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1959)
- [backend/app/api/rfq.py:411](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:411)
- [frontend/src/views/RfqAnalysisView.vue:238](C:/Users/admin/GitHub/structura/frontend/src/views/RfqAnalysisView.vue:238)
- [backend/app/api/rfq.py:2001](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:2001)
- [backend/app/api/rfq.py:1793](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1793)
- [backend/app/services/rfq_transport.py:518](C:/Users/admin/GitHub/structura/backend/app/services/rfq_transport.py:518)

**Livraison C23 :** [rapport](../REMEDIATION_C23_2026-10-22.md), [preuves](C23_VALIDATION.json). Six constats corrigés ; 271 cas backend distincts (32 nouveaux), 674 tests frontend et build temporaire réussis. Prérequis C08 exercé pour les reprises des échanges RFQ ; les trois constats C08 restent ouverts. Condition C04 réexercée ; T12 reste partiel pour la qualification déployée.

## C24

**Attribution CRM analyses datées et devises**

- Lot principal : **7** ; responsabilité proposée : **Structuration et commercial — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — Prérequis C27 soldé localement ; restitution par devise sans FX ; chaîne CRM historique F06, recette graphique/déployée restantes.**.
- Constats : [M16-02](ANOMALY_REGISTER.md#m16-02), [M16-03](ANOMALY_REGISTER.md#m16-03), [M16-04](ANOMALY_REGISTER.md#m16-04).
- Prérequis communs : [C01](#c01), [C03](#c03), [C06](#c06), [C27](#c27).
- Conditions et interfaces complémentaires : C11 (conditionnelle) : Seulement si conversion : FX datés et couverture ; une restitution par devise reste indépendante..
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T14](#t14) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d’entrée examinés ; validation qualifiée et anciens échecs distingués dans le rapport :**

- [backend/tests/test_client_intelligence.py](../../../backend/tests/test_client_intelligence.py)
- [backend/tests/test_client_chain.py](../../../backend/tests/test_client_chain.py)
- [backend/tests/test_client_analytics.py](../../../backend/tests/test_client_analytics.py)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/api/opportunities.py:410](C:/Users/admin/GitHub/structura/backend/app/api/opportunities.py:410)
- [backend/app/core/client_intelligence.py:1493](C:/Users/admin/GitHub/structura/backend/app/core/client_intelligence.py:1493)
- [backend/app/core/client_cycle.py:175](C:/Users/admin/GitHub/structura/backend/app/core/client_cycle.py:175)
- [backend/app/api/client_intelligence.py:227](C:/Users/admin/GitHub/structura/backend/app/api/client_intelligence.py:227)
- [backend/app/core/client_intelligence.py:456](C:/Users/admin/GitHub/structura/backend/app/core/client_intelligence.py:456)

**Livraison C24 :** [rapport](../REMEDIATION_C24_2026-10-22.md), [preuves](C24_VALIDATION.json). Trois constats C24 et M16-05/C27 traités localement. 342 cas backend qualifiés (29 nouveaux), 681 tests frontend et build temporaire réussis. Les 14 échecs anciens de test_client_chain.py sont inchangés, mêmes nœuds et messages. La condition FX C11 n’est pas activée : restitution par devise.

**Solde C27 — 22/10 :** [rapport](../REMEDIATION_C27_2026-10-22.md), [preuves](C27_VALIDATION.json). Production par défaut, UAT explicite sur les agrégats, calculs et historiques ; anciens résultats non qualifiés consultables, vues archivées conservées, réponses tardives exclues. C21/C24/C26 réexercés : 65 tests backend ciblés, 731 tests frontend et build réussis. Recette transverse, graphique et qualification déployée restantes.

## C25

**Économie du roll et récupération**

- Lot principal : **7** ; responsabilité proposée : **Structuration et commercial — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — D09 confirmée ; C26/C27 livrés localement ; composantes T16 couvertes, recette graphique et qualification déployée restantes.**.
- Constats : [M17-02](ANOMALY_REGISTER.md#m17-02), [M17-03](ANOMALY_REGISTER.md#m17-03).
- Prérequis communs : [C18](#c18), [C19](#c19).
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T16](#t16) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée existants de tests à examiner, non exécutés :**

- [backend/tests/test_variantes_roll.py](../../../backend/tests/test_variantes_roll.py)
- [backend/tests/test_variantes_filiation.py](../../../backend/tests/test_variantes_filiation.py)
- [backend/tests/test_variantes_comparaison.py](../../../backend/tests/test_variantes_comparaison.py)
- [backend/tests/test_variantes_avenant.py](../../../backend/tests/test_variantes_avenant.py)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/api/variants.py:250](C:/Users/admin/GitHub/structura/backend/app/api/variants.py:250)
- [docs/projects/lifecycle/DECLINAISONS_POINTS_OUVERTS.md:102](C:/Users/admin/GitHub/structura/docs/projects/lifecycle/DECLINAISONS_POINTS_OUVERTS.md:102)
- [backend/app/api/variants.py:248](C:/Users/admin/GitHub/structura/backend/app/api/variants.py:248)
- [frontend/src/components/VariantCompareTab.vue:75](C:/Users/admin/GitHub/structura/frontend/src/components/VariantCompareTab.vue:75)

**Livraison C25 — 22/10 :** [rapport](../REMEDIATION_C25_2026-10-22.md), [preuves](C25_VALIDATION.json). 182 cas backend distincts (34 nouveaux), 712 tests frontend et build temporaire réussis. Prix nets et quantité, récupération et plafond démontré séparés ; bid manuel daté ou hypothèse modèle explicite. Calendriers/funding à 1 et 5 ans et gel conservé ; export du PDF C19 réexercé séparément. Qualification graphique et déployée restante.

## C26

**Surveillance lifecycle et comptes rendus**

- Lot principal : **3** ; responsabilité proposée : **Données et opérations — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — Consommation officielle et retries C27 exercés ; fixture F07, D07 et recette graphique/déployée restantes.**.
- Constats : [M12-03](ANOMALY_REGISTER.md#m12-03), [M12-04](ANOMALY_REGISTER.md#m12-04).
- Prérequis communs : [C01](#c01), [C11](#c11), [C13](#c13).
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T08](#t08) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée existants de tests à examiner, non exécutés :**

- [backend/tests/test_portfolio_barriers.py](../../../backend/tests/test_portfolio_barriers.py)
- [backend/tests/test_lifecycle_fenetres.py](../../../backend/tests/test_lifecycle_fenetres.py)
- [backend/tests/test_lifecycle_alerts.py](../../../backend/tests/test_lifecycle_alerts.py)
- [backend/tests/test_fixings_releves.py](../../../backend/tests/test_fixings_releves.py)
- [frontend/src/utils/barriers.test.js](../../../frontend/src/utils/barriers.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/api/deals.py:2663](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2663)
- [backend/app/api/deals.py:2702](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2702)
- [backend/app/services/lifecycle_alerts.py:220](C:/Users/admin/GitHub/structura/backend/app/services/lifecycle_alerts.py:220)
- [frontend/src/views/BookingView.vue:1567](C:/Users/admin/GitHub/structura/frontend/src/views/BookingView.vue:1567)

**Livraison C26 — 22/10 :** [rapport](../REMEDIATION_C26_2026-10-22.md), [preuves](C26_VALIDATION.json). Indices de sous-jacents stables, extrema sur clôtures indicatives depuis le strike, registre officiel prioritaire ; SUCCESS/PARTIAL/FAILED, couverture et reprise sans doublons. C01/C11/C13 réexercés ; D07 et convention de règlement existante conservés. 101 cas backend distincts réussis et un échec ancien de fixture ; 720 tests frontend et build réussis. Recette graphique et qualification déployée restantes.

## C27

**Périmètres Production UAT et démonstration**

- Lot principal : **1** ; responsabilité proposée : **Métier et plateforme — rôle proposé, personne non désignée**.
- Statut : **Livré et validé localement sur preuves datées — Solde Production/UAT, historiques et Demo livré localement ; recette transverse/graphique et qualification déployée restantes.**.
- Constats : [M15-03](ANOMALY_REGISTER.md#m15-03), [M16-05](ANOMALY_REGISTER.md#m16-05).
- Prérequis communs : aucun.
- Conditions et interfaces complémentaires : aucune dépendance complémentaire déclarée.
- Validation de sortie : tous les critères V des constats rattachés, les consommateurs affectés et [T10](#t10), [T14](#t14) sur le périmètre annoncé ; aucune clôture sur un simple succès HTTP.

**Points d'entrée du registre, complétés par la validation C27 ci-dessous :**

- [backend/tests/test_risk_dates.py](../../../backend/tests/test_risk_dates.py)
- [backend/tests/test_portfolios_crud.py](../../../backend/tests/test_portfolios_crud.py)
- [backend/tests/test_client_lot2.py](../../../backend/tests/test_client_lot2.py)
- [backend/tests/test_ccr_scope.py](../../../backend/tests/test_ccr_scope.py)
- [frontend/src/stores/portfolios.test.js](../../../frontend/src/stores/portfolios.test.js)

Ces fichiers sont des points de départ, pas une affirmation de couverture. Ajouter ou adapter les scénarios nécessaires lors de la remédiation ; garder les contrôles d'autorisation réels pour la recette de chaîne.

**Implémentations citées par les audits :**

- [backend/app/api/portfolios.py:87](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:87)
- [backend/app/api/var.py:421](C:/Users/admin/GitHub/structura/backend/app/api/var.py:421)
- [backend/app/core/client_intelligence.py:282](C:/Users/admin/GitHub/structura/backend/app/core/client_intelligence.py:282)

**Complément historique CRM C24 :** [preuves](C24_VALIDATION.json). M16-05 corrigé et reproduit via le moteur réel d’import ; la réserve sur M15-03 a ensuite été soldée localement par C27. La qualification déployée reste ouverte.

**Solde C27 — 22/10 :** [rapport](../REMEDIATION_C27_2026-10-22.md), [preuves](C27_VALIDATION.json). Production par défaut, UAT explicite sur les agrégats, calculs et historiques ; anciens résultats non qualifiés consultables, vues archivées conservées, réponses tardives exclues. C21/C24/C26 réexercés : 65 tests backend ciblés, 731 tests frontend et build réussis. Recette transverse, graphique et qualification déployée restantes.

## Scénarios transversaux

Les scénarios suivants sont des **spécifications de recette**, tous non exécutés au lot 0. Ils complètent les **132 critères individuels** du registre et couvrent les 27 chantiers. Utiliser marchés synthétiques, dates figées et bases isolées ; ne pas initialiser la base métier par un import applicatif.

### T01

**Droits et reprise collective**

- Chantiers : [C01](#c01), [C02](#c02).
- Constats de référence : [M01-01](ANOMALY_REGISTER.md#m01-01), [M01-04](ANOMALY_REGISTER.md#m01-04), [M01-05](ANOMALY_REGISTER.md#m01-05), [M10-05](ANOMALY_REGISTER.md#m10-05), [M16-01](ANOMALY_REGISTER.md#m16-01).
- Statut : **Partiel — permissions C01 et sessions C02 validées localement ; recette graphique/transverse complète restante**.
- Preuve C01 : [résultats et limites](../REMEDIATION_C01_2026-10-20.md).

**Mise en place :** Deux utilisateurs même desk, Opérations, Contrôleur et un utilisateur étranger ; dossier créé puis repris et consultation CRM.

**Résultat attendu :** Lecture et actions sont cohérentes partout ; pricing privé non divulgué ; révocation reflétée dans le statut et l'action ; aucun jeton étranger accepté.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

### T02

**Versions et commande répétée**

- Chantiers : [C06](#c06), [C08](#c08).
- Constats de référence : [M04-01](ANOMALY_REGISTER.md#m04-01), [M04-06](ANOMALY_REGISTER.md#m04-06), [M09-01](ANOMALY_REGISTER.md#m09-01), [M11-04](ANOMALY_REGISTER.md#m11-04).
- Statut : **Partiel — C06/C08 versions, reprises et concurrence validés localement ; recette graphique et qualification déployée restantes**.

**Mise en place :** Product v1/RFQ v1, Product v2, synchronisation ancienne RFQ ; réponse de conservation ou booking perdue puis retry concurrent.

**Résultat attendu :** Version courante reste v2 ; RFQ reste v1 ; aucun terme changé par marché ; une seule création par intention et jambe locale.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C06 :** [preuves ciblées](C06_VALIDATION.json), avec limites dans le [rapport C06](../REMEDIATION_C06_2026-10-20.md). Le scénario complet reste à qualifier.

**Complément C23 :** [preuves](C23_VALIDATION.json). Clôture durable sur deux bases, révisions et décisions exactes, devises non interchangeables, reprise des messages et formulaire hors dossier vérifiés. Les échanges HTTP sont simulés et signés : ni TLS, ni deux services déployés, ni recette graphique qualifiés. C08 reste ouvert pour les créations Product et bookings directs.

**Complément C08 — 22/10 :** [rapport](../REMEDIATION_C08_2026-10-22.md), [preuves](C08_VALIDATION.json). 317 cas backend distincts (31 nouveaux), 697 tests frontend et build temporaire réussis. Reprises et filiation qualifiées localement ; les mentions antérieures « C08 global ouvert » sont historiques. Recette graphique interactive et qualification déployée restantes.

### T03

**Payoff mémoire et chronologie**

- Chantiers : [C05](#c05), [C09](#c09), [C14](#c14).
- Constats de référence : [M05-01](ANOMALY_REGISTER.md#m05-01), [M05-06](ANOMALY_REGISTER.md#m05-06), [M06-05](ANOMALY_REGISTER.md#m06-05).
- Statut : **Validé localement sur C05/C09/C14 — dates, rangs, indentation, mémoire, ordre inter-dates et STOP ; recette graphique/production restante**.

**Mise en place :** Coupon mémoire, rappel puis maturité ; deux observations distinctes dans le même pas ; blocs inversés et indentation invalide.

**Résultat attendu :** Dates et rangs corrects ; résultat invariant à l'ordre de déclaration hors simultanéité explicitement définie ; aucune instruction ignorée ; STOP empêche les flux ultérieurs.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C05 :** [preuves ciblées](C05_VALIDATION.json). Le périmètre validé est décrit au [rapport C05](../REMEDIATION_C05_2026-10-20.md) ; les autres consommateurs restent à qualifier.

**Complément C09 :** [preuves ciblées](C09_VALIDATION.json) et [portée du panel](../REMEDIATION_C09_2026-10-21.md). Le scénario complet reste à qualifier.

### T04

**Calendrier et fraîcheur du marché**

- Chantiers : [C03](#c03), [C05](#c05), [C11](#c11), [C12](#c12).
- Constats de référence : [M02-01](ANOMALY_REGISTER.md#m02-01), [M02-03](ANOMALY_REGISTER.md#m02-03), [M03-04](ANOMALY_REGISTER.md#m03-04), [M03-05](ANOMALY_REGISTER.md#m03-05), [M03-09](ANOMALY_REGISTER.md#m03-09).
- Statut : **Validé localement — scénario combiné C03/C05/C11/C12 exécuté ; recette graphique et qualification production restantes**.

**Mise en place :** Ancre31/01, fêtes TARGET, panier avec un historique suspendu, FX ancien et import échoué ; réseau indisponible après stockage local.

**Résultat attendu :** Pas de dérive d'ancre ni calendrier dégradé invisible ; couverture/fraîcheur explicites ; aucune mutation partielle ; réutilisation du stock local lorsque valide.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C05 :** [preuves ciblées](C05_VALIDATION.json). Le périmètre validé est décrit au [rapport C05](../REMEDIATION_C05_2026-10-20.md) ; les autres consommateurs restent à qualifier.

**Complément C11 :** [preuves ciblées](C11_VALIDATION.json). Fraîcheur, exclusions et reprise locale vérifiées avec la politique confirmée de 3 jours calendaires ; les périmètres C12/C21/C27 et la recette transverse complète ne sont pas clos.


**Complément C12 :** [preuves](C12_VALIDATION.json), cas `test_T04_calendar_freshness_failed_import_and_offline_recovery`. Le même scénario vérifie ancre du 31 janvier, fêtes TARGET, série suspendue, change ancien, import refusé sans mutation et reprise locale fournisseur désactivé. Les autres recettes transverses ne sont pas closes.

### T05

**Limite et changement de banque**

- Chantiers : [C03](#c03), [C04](#c04), [C21](#c21).
- Constats de référence : [M02-06](ANOMALY_REGISTER.md#m02-06), [M02-07](ANOMALY_REGISTER.md#m02-07), [M11-01](ANOMALY_REGISTER.md#m11-01), [M11-02](ANOMALY_REGISTER.md#m11-02), [M11-03](ANOMALY_REGISTER.md#m11-03), [M15-06](ANOMALY_REGISTER.md#m15-06).
- Statut : **Partiel — C03/C04 et requalification C21 des limites PFE/CVA validés localement ; amendement de créance courte bloqué sans mutation ; recette transverse et production restantes**.

**Mise en place :** Deal1 M, limite1,5 M ; renommer la banque puis demander nominal2 M et transfert vers une autre banque.

**Résultat attendu :** Renommage conserve le dépassement ; amendement refusé sans mutation ; identité Product/Deal/limites cohérente ; décision stockée et contrôles dépendant de CVA rejoués.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C04 :** [preuves ciblées](C04_VALIDATION.json) : renommage, refus 2 M€, acceptation 1,4 M€, remplacement sans double compte, relecture des mesures et concurrence. T05 reste partiel avec C03/C04 validés localement ; qualification numérique C21 et recette transverse complète restantes.

### T06

**Taux funding et continuité**

- Chantiers : [C14](#c14), [C15](#c15), [C18](#c18).
- Constats de référence : [M06-01](ANOMALY_REGISTER.md#m06-01), [M06-02](ANOMALY_REGISTER.md#m06-02), [M06-04](ANOMALY_REGISTER.md#m06-04), [M06-07](ANOMALY_REGISTER.md#m06-07), [M17-01](ANOMALY_REGISTER.md#m17-01).
- Statut : **Contexte prix/probabilités/trajectoires/solveur raccordé et validé localement ; qualification de production D04 restante**.

**Mise en place :** PAY1 un an r3 % funding2 %, volatilité des taux tendant vers zéro ; rho_rS mono ; a_r proche de zéro.

**Résultat attendu :** Valeur rejoint exp(-0,05), drift sans funding, covariance correcte, résultats finis ; prix/probabilités/solveur partagent le contexte retenu.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C18 :** Funding unique hors drift, taux stochastiques et antithétiques transportés, centre commun et scan PAY1 trois ans à 10 %.


### T07

**Barrière mono et panier dupliqué**

- Chantiers : [C14](#c14), [C16](#c16), [C18](#c18).
- Constats de référence : [M06-03](ANOMALY_REGISTER.md#m06-03).
- Statut : **Copies et contexte commun C14/C16/C18 validés localement ; extensions de domaine et production restantes**.

**Mise en place :** Deux copies du même actif avec mêmes facteurs et corrélation1, mêmes extrémités intra-pas ; monitoring continu.

**Résultat attendu :** Même franchissement et même payoff que le mono sous les mêmes aléas ; quantifier séparément le cas de corrélation imparfaite et ses limites.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C18 :** Même payoff continu sur les consommateurs, domaine C16 préservé, refus des paniers hors domaine.


### T08

**Fixing officiel vers MtM P&L et risque**

- Chantiers : [C13](#c13), [C18](#c18), [C19](#c19), [C21](#c21), [C22](#c22), [C26](#c26).
- Constats de référence : [M12-02](ANOMALY_REGISTER.md#m12-02), [M12-05](ANOMALY_REGISTER.md#m12-05), [M13-01](ANOMALY_REGISTER.md#m13-01), [M14-01](ANOMALY_REGISTER.md#m14-01), [M15-05](ANOMALY_REGISTER.md#m15-05).
- Statut : **Partiel — C13/C18/C19/C21 et cash/attribution C22 validés localement ; surveillance C26 consomme les versions officielles et leurs corrections ; anciens résultats conservés ; recette complète et qualification déployée restantes**.

**Mise en place :** Officialiser coupon puis provoquer panne du flux, correction versionnée et échec d'application ; créer un nouveau MtM/Explain/CCR.

**Résultat attendu :** Le registre conserve son autorité ; transaction sans moitié appliquée ; nouveaux calculs consomment la correction ; moniteur devient périmé ; historique conservé.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C18 :** Régressions du registre officiel, état des MtM/chocs conservé ; aucune mutation des faits.

**Livraison C26 — 22/10 :** [rapport](../REMEDIATION_C26_2026-10-22.md), [preuves](C26_VALIDATION.json). Indices de sous-jacents stables, extrema sur clôtures indicatives depuis le strike, registre officiel prioritaire ; SUCCESS/PARTIAL/FAILED, couverture et reprise sans doublons. C01/C11/C13 réexercés ; D07 et convention de règlement existante conservés. 101 cas backend distincts réussis et un échec ancien de fixture ; 720 tests frontend et build réussis. Recette graphique et qualification déployée restantes.

### T09

**Créance courte et paiement**

- Chantiers : [C14](#c14), [C18](#c18), [C21](#c21), [C22](#c22).
- Constats de référence : [M13-02](ANOMALY_REGISTER.md#m13-02), [M13-03](ANOMALY_REGISTER.md#m13-03), [M15-04](ANOMALY_REGISTER.md#m15-04), [M15-07](ANOMALY_REGISTER.md#m15-07).
- Statut : **Partiel — contrôles déterministes C14/C18/C21/C22 validés localement : CVA 657,084 EUR, limite 100 bloquante, coupon observé le 15 payé le 22, P&L réconcilié ; recette transverse intégrale et production restantes**.

**Mise en place :** Créance1 M à deux jours, PD linéaire20 %/an, récupération40 %, r0 ; puis coupon observé le15 payé le22.

**Résultat attendu :** CVA≈657,084 EUR et limite100 dépassée ; exposition couverte avant paiement ; cash au22 réconcilie le P&L ; aucun horizon hebdomadaire artificiel.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C18 :** Coupons détachés sur produit actif réactualisés à leur paiement réel sous choc de taux, contribution séparée.


### T10

**Production et couverture des risques**

- Chantiers : [C11](#c11), [C21](#c21), [C27](#c27).
- Constats de référence : [M15-01](ANOMALY_REGISTER.md#m15-01), [M15-02](ANOMALY_REGISTER.md#m15-02), [M15-03](ANOMALY_REGISTER.md#m15-03), [M16-05](ANOMALY_REGISTER.md#m16-05).
- Statut : **Partiel — composantes C11/C21/C24/C27 validées localement : Production/UAT, facteurs et métriques, historiques et import Demo ; recette transverse graphique et déployée restante**.

**Mise en place :** Un Deal Production et un UAT ; TK2 absent des scénarios ; calcul delta seul après calcul complet ; import sur mandat Demo.

**Résultat attendu :** Production seul par défaut ; couverture des facteurs et métriques exacte ; gamma/rho indisponibles plutôt que zéro ; historique Demo exclu du profil réel.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C11 :** [preuves ciblées](C11_VALIDATION.json). Fraîcheur, exclusions et reprise locale vérifiées avec la politique confirmée de 3 jours calendaires ; les périmètres C12/C21/C27 et la recette transverse complète ne sont pas clos.

**Solde C27 — 22/10 :** [rapport](../REMEDIATION_C27_2026-10-22.md), [preuves](C27_VALIDATION.json). Production par défaut, UAT explicite sur les agrégats, calculs et historiques ; anciens résultats non qualifiés consultables, vues archivées conservées, réponses tardives exclues. C21/C24/C26 réexercés : 65 tests backend ciblés, 731 tests frontend et build réussis. Recette transverse, graphique et qualification déployée restantes.

### T11

**Calibration et réponses hors contexte**

- Chantiers : [C07](#c07), [C10](#c10), [C17](#c17).
- Constats de référence : [M03-03](ANOMALY_REGISTER.md#m03-03), [M05-07](ANOMALY_REGISTER.md#m05-07), [M07-01](ANOMALY_REGISTER.md#m07-01), [M07-02](ANOMALY_REGISTER.md#m07-02), [M07-04](ANOMALY_REGISTER.md#m07-04), [M07-07](ANOMALY_REGISTER.md#m07-07).
- Statut : **Contrôles C07/C10/C17 validés localement ; recette graphique de chaîne et production restantes**.

**Mise en place :** Modifier pilier ATM7 ans puis taux3→4 % et lancer deux calibrations ; vider un champ ; retarder les réponses.

**Résultat attendu :** Pilier matériel contrôlé ; seule la dernière révision s'applique ; champ vide non transformé en zéro ; convergence et qualification séparées.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C07 :** [preuves ciblées](C07_VALIDATION.json) et [limites](../REMEDIATION_C07_2026-10-21.md). Le scénario complet reste à qualifier.

**Complément C10 :** [preuves ciblées](C10_VALIDATION.json) et [portée](../REMEDIATION_C10_2026-10-21.md). Les réponses hors contexte sont exercées. C17 ajoute la qualification explicite et la conservation de sa preuve.

### T12

**RFQ bilatérale clôture et révisions**

- Chantiers : [C01](#c01), [C03](#c03), [C06](#c06), [C08](#c08), [C23](#c23).
- Constats de référence : [M09-02](ANOMALY_REGISTER.md#m09-02), [M09-03](ANOMALY_REGISTER.md#m09-03), [M09-04](ANOMALY_REGISTER.md#m09-04), [M10-01](ANOMALY_REGISTER.md#m10-01), [M10-02](ANOMALY_REGISTER.md#m10-02), [M10-03](ANOMALY_REGISTER.md#m10-03).
- Statut : **Partiel — chaîne applicative C01/C03/C06/C08/C10/C23 validée localement ; qualification déployée restante**.
- Preuve C01 : [résultats et limites](../REMEDIATION_C01_2026-10-20.md).

**Mise en place :** Deux bases : publication, quote retenue, clôture transmise puis réouverture ; nouvelle révision de prix ; devise divergente ; autre dossier ouvert.

**Résultat attendu :** Aucune ancienne quote ressuscitée ; sélection liée à sa révision ; historique conservé ; mappings stables ; aucun transfert de preuve entre dossiers.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C06 :** [preuves ciblées](C06_VALIDATION.json), avec limites dans le [rapport C06](../REMEDIATION_C06_2026-10-20.md). Le scénario complet reste à qualifier.

**Complément C23 :** [preuves](C23_VALIDATION.json). Clôture durable sur deux bases, révisions et décisions exactes, devises non interchangeables, reprise des messages et formulaire hors dossier vérifiés. Les échanges HTTP sont simulés et signés : ni TLS, ni deux services déployés, ni recette graphique qualifiés. C08 reste ouvert pour les créations Product et bookings directs.

**Complément C08 — 22/10 :** [rapport](../REMEDIATION_C08_2026-10-22.md), [preuves](C08_VALIDATION.json). 317 cas backend distincts (31 nouveaux), 697 tests frontend et build temporaire réussis. Reprises et filiation qualifiées localement ; les mentions antérieures « C08 global ouvert » sont historiques. Recette graphique interactive et qualification déployée restantes.

### T13

**Rejeu archive et PDF**

- Chantiers : [C06](#c06), [C18](#c18), [C19](#c19).
- Constats de référence : [M04-09](ANOMALY_REGISTER.md#m04-09), [M13-05](ANOMALY_REGISTER.md#m13-05), [M13-06](ANOMALY_REGISTER.md#m13-06), [M14-03](ANOMALY_REGISTER.md#m14-03), [M14-04](ANOMALY_REGISTER.md#m14-04), [M17-05](ANOMALY_REGISTER.md#m17-05).
- Statut : **Validé localement sur le périmètre C06/C18/C19 — archives, sondes, créances et PDF ; recette graphique et production restantes**.

**Mise en place :** Sauver run et calendrier puis changer résolveur/moteur/fournisseur ; ouvrir écran et exporter PDF ; provoquer exception de rejeu.

**Résultat attendu :** PDF et écran conservent les chiffres du run ; nouvelle méthode crée un autre run ; écart observé conservé quand permis ; créance réellement réactualisée au rejeu.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C06 :** [preuves ciblées](C06_VALIDATION.json), avec limites dans le [rapport C06](../REMEDIATION_C06_2026-10-20.md). Le scénario complet reste à qualifier.

**Complément C23 :** [preuves](C23_VALIDATION.json). Clôture durable sur deux bases, révisions et décisions exactes, devises non interchangeables, reprise des messages et formulaire hors dossier vérifiés. Les échanges HTTP sont simulés et signés : ni TLS, ni deux services déployés, ni recette graphique qualifiés. C08 reste ouvert pour les créations Product et bookings directs.

**Complément C18 :** Dossier de calibration C17 conservé, source effective archivée et étiquetage partagé.


### T14

**CRM daté attribution et devises**

- Chantiers : [C01](#c01), [C24](#c24), [C27](#c27).
- Constats de référence : [M16-01](ANOMALY_REGISTER.md#m16-01), [M16-02](ANOMALY_REGISTER.md#m16-02), [M16-03](ANOMALY_REGISTER.md#m16-03), [M16-04](ANOMALY_REGISTER.md#m16-04), [M16-05](ANOMALY_REGISTER.md#m16-05).
- Statut : **Partiel — scénario combiné C01/C24 et prérequis CRM C27 validés localement ; recette graphique et qualification déployée restantes**.
- Preuve C01 : [résultats et limites](../REMEDIATION_C01_2026-10-20.md).

**Mise en place :** OpportunitéA avec participants et Deal puis déplacementB ; asof01/02/2026 avec trade2027 ; 1 M EUR/100 M JPY ; mandat Demo.

**Résultat attendu :** Pas de rattachement incohérent ni fuite ; aucun futur dans le profil ; montants séparés ou convertis avec preuve ; Demo hors profil réel.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C24 :** [rapport](../REMEDIATION_C24_2026-10-22.md), [preuves](C24_VALIDATION.json). Le test T14 combiné couvre les rattachements persistés, les dates, les devises et le mandat Demo. Les statuts commerciaux restent explicitement courants ; aucun passé non historisé n’est inventé.

**Solde C27 — 22/10 :** [rapport](../REMEDIATION_C27_2026-10-22.md), [preuves](C27_VALIDATION.json). Production par défaut, UAT explicite sur les agrégats, calculs et historiques ; anciens résultats non qualifiés consultables, vues archivées conservées, réponses tardives exclues. C21/C24/C26 réexercés : 65 tests backend ciblés, 731 tests frontend et build réussis. Recette transverse, graphique et qualification déployée restantes.

### T15

**Recherche sauvegardée et reprise**

- Chantiers : [C07](#c07), [C09](#c09), [C19](#c19), [C20](#c20).
- Constats de référence : [M08-01](ANOMALY_REGISTER.md#m08-01), [M08-02](ANOMALY_REGISTER.md#m08-02), [M08-03](ANOMALY_REGISTER.md#m08-03), [M08-04](ANOMALY_REGISTER.md#m08-04), [M08-05](ANOMALY_REGISTER.md#m08-05), [M08-06](ANOMALY_REGISTER.md#m08-06).
- Statut : **Validé localement sur le périmètre cumulé C07/C09/C19/C20 — modes, précision, reprise, budgets et immutabilité ; recette graphique/production restantes**.

**Mise en place :** Athena dégressif et booster cap ; RC limite d'itérations ; q2,001 % ; payoff modifié ; budget dépassé ; tentative NULL sur résultat terminal.

**Résultat attendu :** Demandes conservées/lancées ; précision et qualification exactes ; dépassement explicite ; pas de perte à la reprise ni modification de preuve.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C07 :** [preuves ciblées](C07_VALIDATION.json) et [limites](../REMEDIATION_C07_2026-10-21.md). Le scénario complet reste à qualifier.

**Complément C09 :** [preuves ciblées](C09_VALIDATION.json) et [portée du panel](../REMEDIATION_C09_2026-10-21.md). Le scénario complet reste à qualifier.

### T16

**Roll financement récupération et proposition**

- Chantiers : [C05](#c05), [C18](#c18), [C19](#c19), [C25](#c25).
- Constats de référence : [M17-01](ANOMALY_REGISTER.md#m17-01), [M17-02](ANOMALY_REGISTER.md#m17-02), [M17-03](ANOMALY_REGISTER.md#m17-03), [M17-04](ANOMALY_REGISTER.md#m17-04), [M17-05](ANOMALY_REGISTER.md#m17-05).
- Statut : **Partiel — C05/C18/C19/C25 validés sur les composantes locales ; recette graphique et qualification déployée restantes**.

**Mise en place :** Roll PAY1,2, bid modèle-2 points, tenor1 ou5 ans, funding explicite ; figer la proposition puis changer sigma10→60 %.

**Résultat attendu :** Coûts changent quantité et récupération ; plafond contractuel correct ; calendrier cohérent ou refus ; PDF reprend la proposition figée et non un nouveau calcul.

**Preuve à joindre :** entrées et versions, acteur et périmètre, résultat avant/après, erreurs attendues, états persistés et absence d'effets de bord. Pour le réseau, preuves sur les deux installations ; pour les risques, couverture et décision de limite ; pour le PDF, rapprochement avec le run ou la proposition retenue.

**Complément C05 :** [preuves ciblées](C05_VALIDATION.json). Le périmètre validé est décrit au [rapport C05](../REMEDIATION_C05_2026-10-20.md) ; les autres consommateurs restent à qualifier.

**Livraison C25 — 22/10 :** [rapport](../REMEDIATION_C25_2026-10-22.md), [preuves](C25_VALIDATION.json). 182 cas backend distincts (34 nouveaux), 712 tests frontend et build temporaire réussis. Prix nets et quantité, récupération et plafond démontré séparés ; bid manuel daté ou hypothèse modèle explicite. Calendriers/funding à 1 et 5 ans et gel conservé ; export du PDF C19 réexercé séparément. Qualification graphique et déployée restante.

## Règles de mesure et de clôture

- **Cas déterministes :** comparer au montant/date/formule contractuel indépendant. Pour une valeur publiée arrondie à six décimales du nominal, l'écart à la référence déterministe doit être au plus de l'ordre d'une unité du dernier chiffre publié, sauf tolérance plus stricte du test. Ne pas utiliser un arrondi monétaire pour cacher un écart économique.
- **Monte-Carlo :** fixer seeds et aléas communs pour les comparaisons ; définir avant exécution réplications indépendantes, référence, tolérance économique, précision de temps et règle statistique. Un seul IC contenant la référence ne qualifie pas la méthode. Les seuils par modèle/usage de D04 restent à arrêter.
- **Barrières et corrélations :** séparer erreur d'échantillonnage, approximation temporelle et dépendance des extrema ; le test d'actif dupliqué utilise les mêmes facteurs, pas seulement deux seeds supposées équivalentes.
- **CVA courte :** conserver les dates exactes et l'exposition **avant** paiement dans l'intégration. Ajouter uniquement une date de paiement puis lire l'exposition après paiement ne corrige pas le cas.
- **API et persistance :** couvrir refus, retry, concurrence, panne entre étapes et rollback ; les montages de suppression/migration activent les contraintes et protections nécessaires.
- **UI :** prouver qu'une réponse tardive et un refus serveur ne changent pas le mauvais contexte ; conserver les valeurs exactes derrière l'affichage arrondi.
- **Validation ciblée :** pytest depuis la racine, groupes touchés seulement ; tests frontend correspondants et build depuis frontend après modification Vue. La suite backend complète exige une demande explicite.
- **Fixtures :** une erreur de desk pilote absent, de stub auth/migration ou d'entrée obligatoire arrête la preuve avant l'invariant ; remettre la fixture en conformité plutôt que neutraliser le garde pour revendiquer une recette complète.
- **Historique :** tout changement de méthode conserve l'ancien résultat et crée un nouveau run. Ne jamais régénérer silencieusement les calendriers ni fabriquer une version de moteur pour les anciennes preuves.

Pour clôturer un constat, conserver **ID, référence du correctif, baseline, reproduction initiale ou preuve de disparition, validations individuelles et transversales, migrations/compatibilité, réserves et date**. Une référence Git ne suppose pas qu'un commit ou push a été autorisé. Si un constat n'est pas reproductible, documenter pourquoi et garder le lien source ; ne pas le marquer corrigé sans preuve.

Statuts proposés : **Ouvert → Reproduit → Correctif en revue → Validé sur périmètre ciblé → Validé chez les consommateurs → Clos**. Une décision métier ou une limite acceptée possède son arbitrage explicite ; elle ne suit pas artificiellement le statut d'un bug corrigé.

## Décisions métier

Les décisions ci-dessous sont des propositions à préciser au bon moment, sans validation implicite par la création de ce registre. Elles n'empêchent pas les correctifs indépendants ou les refus conservatoires documentés.

| ID | Sujet | Références | Décision à préciser | Échéance de décision |
|---|---|---|---|---|
| D01 | Contrepartie hors catalogue — décision confirmée par Philippe le 20/10/2026, implémentée et testée localement | M11-01 C03 C04 | ID actif par défaut ; exception administrateur explicite, motivée et auditée pour un booking direct hors référentiel, sans netting set ni substitution d’une RFQ ; crédit non évalué et dossier à régulariser par amendement. | Arbitrage reçu ; recette graphique/transverse et qualification de production restantes |
| D02 | Observation et règlement | M02-04 C05 | **Confirmée le 20/10/2026** : choix explicite par produit de la combinaison des places/centres ; stub long à fusion systématique ; dates figées conservées. [Rapport C05](../REMEDIATION_C05_2026-10-20.md). | Implémentée localement ; recette transverse restante |
| D03 | Fraîcheur et finalité par usage | M03-01 M03-04 M03-05 C11 C13 | Confirmé le 21/10 : 3 jours calendaires maximum pour les cours EOD et le FX de reporting, J+3 inclus et J+4 exclu. Horaires, fuseaux, délai après clôture et finalité officielle restent ouverts dans C13. | C11 confirmé ; C13 avant publication officielle |
| D04 | Qualification des modèles et calibrations | M06-03 M07-04 C15 C16 C17 | Confirmation partielle C16 le 21/10 : approximation explicitement signalée après validation ; seuil de 10 pb du nominal sur le panel GBM à deux actifs. [Rapport C16](../REMEDIATION_C16_2026-10-21.md). Les autres domaines, tolérances et usages de production restent à préciser ; un solveur terminé n'est pas une qualification. | C16 local confirmé ; extension avant élargissement des capacités |
| D05 | Droits collectifs et calculs privés | M01-05 M16-01 C01 | Préciser lecture des dossiers et agrégats par organisation/desk et actions Opérations. Maintenir la confidentialité des calculs bancaires privés et rendre toute projection CRM élargie explicite. | Avant clôture de l'harmonisation des accès |
| D06 | Correction après consommation d'un fixing | M12-05 M13-01 C13 C19 | Définir correction des faits, invalidation des résultats courants et éventuel circuit d'annulation/remplacement ; conserver événements, paiements et versions historiques. | Avant application à un dossier déjà consommé |
| D07 | Paiement prévu et confirmé | M01-02 C26 | Distinguer échéance, déclaration de règlement, paiement confirmé, retard et impayé ; conserver la convention calendaire existante comme telle tant qu'une autre politique n'est pas actée. | Avant qualification d'un état SETTLED comme preuve de cash |
| D08 | VaR et CCR annoncés | M15-01 M15-04 C21 | Conserver explicitement les capacités actuelles : VaR sur photo résiduelle, limites FX/ageing/funding ; CCR économique à capacités bornées. SA-CCR, modèle joint WWR et perfectionnement IM/MPOR ne sont pas des correctifs implicites du lot 0. | Avant qualifier un indicateur au-delà de son domaine |
| D09 | Prix de sortie et coûts du roll — confirmé le 22/10/2026 | M17-02 C25 | Bid saisi ou hypothèse modèle/décote explicite ; frais de sortie sur le nominal d’origine, marge/frais d’entrée sur le nouveau nominal. Sans bid : hypothèse modèle. [Rapport C25](../REMEDIATION_C25_2026-10-22.md). | Implémenté et testé localement ; qualification graphique et déployée restante |
| D10 | Décision confirmée par Philippe le 21/10/2026 | C19 | Gel manuel explicite avant export ; proposition et étude immuables distinctes des brouillons vivants. | Implémentée localement ; qualification production distincte |
| D11 | Décision confirmée par Philippe le 21/10/2026 | C19 | Anciens résultats consultables ; rejeu qualifié uniquement à identité de moteur/conventions identique, avec contrôle numérique ; autre recalcul en sonde distincte, sans écrasement ni version inventée. | Implémentée localement ; qualification production distincte |
| D12 | Budget et métriques | M06-08 M08-05 C18 C20 | Préciser bumps admissibles, définition du vega LSV, métriques de payoff et limites temps du calcul. Les choix actuels documentés sont conservés jusqu'à évolution explicite. | Avant publication des nouveaux diagnostics |
| D13 | Nom canonique de l’organisation gérée | M01-10 C02 | Décision confirmée par Philippe : verrouillage local du nom canonique ; renommage via provisionnement. Le workspace autonome conserve son périmètre. | Appliquée à C02 le 20/10/2026 |

## Limites de qualification conservées

**Complément C18 :** Modèle hérité ou GBM explicite, taux/funding/conventions communs au solveur et aux probabilités.


### Q01

**Portée des audits** — Les 132 entrées reprennent les conclusions des modules 1–17 du 19 octobre ; la baseline est celle du 20 octobre. Leur présence ne constitue pas une nouvelle reproduction sur cette baseline.

### Q02

**Modèles quantitatifs** — L'IC Monte-Carlo ne mesure pas le biais de temps, la calibration ou le risque de dynamique. LSV exige une qualification par réplications indépendantes ; toutes les combinaisons proposées ne sont pas certifiées.

### Q03

**Surface et calibration** — Représentation des ailes restrictive, absence de pilier50 %, maturités bornées et calibration sous taux/dividendes plats doivent rester visibles. Extension de représentation et absence d'arbitrage sont des questions distinctes.

### Q04

**Optimizer** — Recherche sur grille finie, validation d'au plus cinq candidats et hypothèses GBM : aucune promesse d'optimum global ou de cotation exécutable ; perturbations de marché et convergence restent à qualifier.

### Q05

**Paiement** — La transition calendaire et une référence saisie ne démontrent pas un virement bancaire. Le registre ne rapporte aucune preuve de cash réelle.

### Q06

**VaR** — Le choc appliqué à la photo résiduelle ne déroule pas tous les événements/cash jusqu'à l'horizon ; le risque de traduction FX et le funding portefeuille ne sont pas exhaustivement couverts.

### Q07

**CCR** — GBM compatible, collatéral sur grille, IM fixe et indépendance du défaut sont des capacités déclarées ; pas de SA-CCR ni de modèle joint WWR. Le taux commun de 3 % surchargeable est une convention déjà arbitrée.

### Q08

**Historique et P&L** — Le Valo Explain entre deux runs attribue une variation de MtM ; le P&L total ajoute le cash. Ne pas changer cette définition pour masquer une rupture de réconciliation.

### Q09

**Gouvernance déjà arbitrée** — Le parcours courant de fixing automatique et la seconde signature des amendements désactivée par défaut ne sont pas des anomalies en eux-mêmes. Ne pas réintroduire un maker-checker général par défaut.

### Q10

**Sens et risques** — La convention de sens est côté banque : vente signifie position longue pour Structura ; ne pas inverser les signes à partir des seuls libellés. La CVA économique et la concentration historique restent des contrôles distincts.

### Q11

**Annulation et remplacement** — Le circuit de remplacement de certaines erreurs contractuelles demeure incomplet ; une demande de rebooking doit avoir une sortie opérationnelle définie avant utilisation réelle.

### Q12

**Données de marché** — Volatilité réalisée, hypothèse forward de dividende et volatilité implicite sont distinctes. Les opérations sur titres et proxys exigent leur diagnostic ; l'administration des caches ne prouve pas à elle seule la qualité consommée.

### Q13

**Preuves d'audit automatisées** — Suite backend complète explicitement demandée et exécutée sur données isolées le 23/10/2026 : 3 943 succès, 3 ignorés conditionnels inchangés, aucun échec ni erreur. Les 59 cas du premier passage complet sont corrigés dans 14 suivis F08-F21 ; 817 succès ciblés distincts préparent le passage final. Les 121 cas historiques et ces 59 cas supplémentaires ont tous leur cible de résolution réussie dans le passage final ; solde courant 0 sur 180 cas documentés. Aucun cas initial supprimé ou renommé. La référence figée conserve ses 121 cas initiaux. Recette graphique, scénarios transverses non couverts et qualification déployée restent distincts.

### Q14

**Périmètre restant** — Les modules 18 AMC/FIFO, 19 Studies, 20 Documents, 21 IA/simulation et 22 Exploitation n'ont pas reçu cet audit complet. Les PDF examinés aux modules 14 et 17 ne valent pas audit du module 20.

### Q15

**Exploration et exécution** — Le scan mono-sous-jacent et les variantes sont des études internes sans booking automatique ; leur limitation annoncée ne doit pas devenir une anomalie artificielle.

### Q16

**Données historiques** — Aucune exposition réelle ni ampleur en portefeuille n'a été mesurée pour le lot0. La liste des dossiers affectés sera établie par une démarche distincte, autorisée et conservant les snapshots.



**Suivi D05 — 20/10/2026 :** la [règle d’accès C01](../REMEDIATION_C01_2026-10-20.md#règle-daccès-explicitée-pour-d05) est explicitée et implémentée localement pour revue. Cette précision ne vaut pas approbation métier implicite.

**Suivi D04 — 21/10/2026, C17 :** Philippe a retenu **5 pb du nominal pour les vanilles et 10 pb pour les digitales**, sur les points de contrôle publiés. Un résultat non convergé ou hors seuil reste exploratoire, sans application automatique. Ce choix ne modifie pas le seuil du panel de barrières C16 et ne vaut pas qualification de production. [Rapport C17](../REMEDIATION_C17_2026-10-21.md).

**Suivi D12 — 21/10/2026 :** C18 documente les conventions existantes et corrige leur transport/libellé : amplitude signée réellement admissible de corrélation, vega LSV local effectif sans recalibration, métriques nominales et actualisées distinctes. Aucun nouveau vega de marché ni budget temps global n’est approuvé implicitement. [Rapport](../REMEDIATION_C18_2026-10-21.md).

**Suivi D10/D11 — 21/10/2026 :** gel manuel explicite et rejeu à identité compatible confirmés par Philippe. [Rapport C19](../REMEDIATION_C19_2026-10-21.md). Aucun événement consommé ni ancien résultat n’est réécrit ; D06 reste ouvert.

**Suivi D12 — 22/10/2026 :** C20 conserve défaut 120 s et bornes 30–3 600 s. Limite séquentielle souple, dépassement enregistré et résultat partiel explicites. Aucun nouveau plafond métier approuvé. [Rapport C20](../REMEDIATION_C20_2026-10-22.md).

**Suivi D08 — 22/10/2026 :** capacités conservées et bornées ; créances certaines à dates exactes, intégration CVA/EPE à gauche, projections optionnelles courtes ou mixtes hors grille indisponibles. Aucune extension réglementaire ou approbation métier implicite. [Rapport C21](../REMEDIATION_C21_2026-10-22.md).
