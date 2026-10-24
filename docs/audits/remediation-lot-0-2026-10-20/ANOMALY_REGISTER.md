# Registre des anomalies des modules 1 à 17

**Accès du launcher et changement de compte — 24/10/2026 :** six organisations/24 profils, console et simulation vérifiés ; cas Admin seul ajouté après la capture de Philippe. **LA01–LA04 corrigées**, **53 tests backend ciblés distincts**, **779 tests frontend et build**, **28 jalons navigateur**. Sélecteur Admin actif, profil explicite, démarrage à la demande et retours après panne ; aucune IA démarrée. Services de recette arrêtés, nouvelle instance utilisateur préservée ; **relance du portail utilisateur nécessaire** pour charger le contrat serveur modifié. 132 constats/27 chantiers/180 cas F01–F21 inchangés. [Rapport](../ADMIN_ACCOUNT_SWITCH_2026-10-24.md) · [preuves](LAUNCHER_ACCESS_VALIDATION.json).

**Launcher — 24/10/2026 :** reprise explicite du workspace Admin historique sans marqueur C02, avec sauvegarde identique, identité et audit transactionnels. **31 tests ciblés réussis**, démarrage réel du launcher et connexion Admin validés sur copie isolée puis sur le workspace du raccourci ; comptes, secrets et dossiers conservés. Services de contrôle arrêtés et ports libres vérifiés. La garde C02 reste active ; autres adoptions et qualification déployée distinctes. Les 132 constats, 27 chantiers et 180 cas F01–F21 ne sont pas renumérotés. [Rapport](../LAUNCHER_RECOVERY_2026-10-24.md) · [preuves](LAUNCHER_RECOVERY_VALIDATION.json).

**Rapprochement RFQ — 24/10/2026 :** états réciproques authentifiés et datés, inventaire habilité et écarts par champ. Panne bancaire, booking local conservé, reprise de la jambe bancaire après clôture, déclaration négative à 99 % puis retour à 98,50 % sans modification des Deals exercés sur deux installations isolées. **RC01–RC03 traités**, **282 tests backend ciblés distincts**, **764 tests frontend/build**, 15 jalons graphiques et 36 contrôles de rapprochement en lecture seule. Un Deal par livre et deux états finaux `MATCHED` ; services arrêtés et ports libres vérifiés. Les 132 constats, 27 chantiers et 180 cas F01–F21 restent inchangés ; T02/T12 restent partiels, TLS et qualification déployée ouverts. [Rapport](../RFQ_RECONCILIATION_2026-10-24.md) · [preuves](RFQ_RECONCILIATION_VALIDATION.json).

**Confirmation électronique RFQ — 24/10/2026 :** demande et décision bancaire natives, reprises après arrêt de chaque destinataire, enveloppes originales et accusés conservés. Une exécution commune et un Deal par base, 1 M EUR à 98,50 %, sens opposés ; 28 contrôles de rapprochement en lecture seule. E01 corrigée (ordre de flush inbox/preuve), 252 tests backend ciblés distincts, 756 tests frontend/build et 15 jalons graphiques. Bookings et replays par API native puis contrôle à l’écran. Services arrêtés ; TLS/déploiement et matrice complète T02/T12 restent ouverts. Les 132 constats et 180 cas F01–F21 restent inchangés. [Rapport](../ELECTRONIC_RFQ_EXECUTION_2026-10-24.md) · [preuves](ELECTRONIC_RFQ_VALIDATION.json).

**Recette RFQ bilatérale — 24/10/2026 :** demande et deux révisions transmises par les workers natifs entre deux bases isolées ; reprise après indisponibilité puis **deux Deals concordants de 1 M EUR à 98,50 %**, sens opposés, calculs privés distincts, clôture reçue des deux côtés. **R01–R04 corrigées**, 138 tests backend et 149 tests frontend ciblés distincts, build final et 29 jalons graphiques ; services arrêtés. Accord externe fictif consigné, sans message natif de confirmation d’exécution ni qualification TLS. T02/T12 restent partiels ; les 132 constats et 180 cas F01–F21 sont inchangés. [Rapport](../BILATERAL_RFQ_ACCEPTANCE_2026-10-24.md) · [preuves](BILATERAL_RFQ_VALIDATION.json).

**Recette graphique — 23/10/2026 :** chaîne Product → RFQ → booking → fixing → MtM/PDF, risque, CRM, Optimizer, profils et séparation Production/UAT exercés sur installations isolées. **Neuf anomalies G01–G09 corrigées**, **151 tests backend ciblés distincts**, **737 tests frontend et build réussis** ; 48 jalons DOM/capture conservés. Réseau bilatéral, cycle cash complet, risque positif complet, roll positif, modèles avancés et qualification déployée restent distincts. Les 132 constats et 180 cas historiques ne sont pas renumérotés. [Rapport](../GRAPHICAL_ACCEPTANCE_2026-10-23.md) · [preuves](GRAPHICAL_VALIDATION.json).

Constitution initiale : **20 octobre 2026** ; actualisation documentaire : **24 octobre 2026**. Sources : audits de cette conversation du **19 octobre 2026**. [Synthèse du lot 0](../REMEDIATION_LOT_0_2026-10-20.md) · [Dépendances et validation](DEPENDENCIES_AND_VALIDATION.md) · [Rapports sources](AUDIT_SOURCES.md) · [Registre structuré](REGISTER.json).

Les **132 entrées** correspondent aux constats numérotés des audits : **49 P1, 81 P2 et 2 P3**. Les priorités d'origine sont conservées ; elles ne sont pas additionnées pour mesurer un nombre de défauts indépendants. Chaque entrée appartient à un seul chantier principal parmi les **27 chantiers**, avec dépendances et consommateurs transversaux.

**Statut commun initial : Ouvert — à revalider avant correction.** Aucun correctif ni nouveau test métier exécuté au lot 0. Les critères ci-dessous sont des résultats attendus, pas des résultats obtenus.

Les preuves **L** renvoient à une lecture ou analyse décrite dans le rapport source ; **R** à une reproduction isolée rapportée. Ces niveaux indiquent la preuve antérieure, pas une qualification actuelle en production. Les détails, limites et conditions des reproductions sont conservés dans les rapports sources. Les chemins et lignes sont des points d'entrée datés à revérifier avant intervention.

Une même cause peut apparaître dans plusieurs modules. Le couple **M02-07 / M15-06**, concernant la concentration par nom, reste deux observations d'un même défaut du même consommateur. La finalité des cours **M03-01 / M12-01** et la consommation officielle **M13-01** appartiennent au chantier C13, mais couvrent des étapes distinctes et doivent chacune être vérifiées.

Le point métier M02-14 est une décision, reprise sous **D01** dans la matrice ; il n'est pas compté comme une 133e anomalie. Les limites non numérotées restent dans **Q01 à Q16**.

**Suivi historique C01 — 20/10/2026 :** sept constats corrigés localement et validés par tests ciblés. [Livraison du lot 1](../REMEDIATION_C01_2026-10-20.md) et [preuves](C01_VALIDATION.json). Les autres constats et les recettes transverses restent ouverts.

**Suivi historique C02 — 20/10/2026 :** sept constats corrigés et validés localement ; décision D13 confirmée. [Livraison](../REMEDIATION_C02_2026-10-20.md) et [preuves](C02_VALIDATION.json). Recette graphique/transverse et reprise explicite des anciens workspaces Admin restantes.

**Suivi historique C03 — 20/10/2026 :** neuf constats traités et validés localement. [Rapport](../REMEDIATION_C03_2026-10-20.md), [preuves](C03_VALIDATION.json). D01 confirmée avec exception administrateur explicite, motivée et auditée ; T04/T05/T12 partiels.

**Suivi historique C04 — 20/10/2026 :** trois constats corrigés et validés localement. [Rapport](../REMEDIATION_C04_2026-10-20.md), [preuves](C04_VALIDATION.json). C01/C03 préservés ; T05 complet, qualification C21 et recette graphique/production ouverts.

**Suivi historique C05 — 20/10/2026 :** huit constats corrigés et validés localement ; arbitrages D02 confirmés. [Rapport](../REMEDIATION_C05_2026-10-20.md), [preuves](C05_VALIDATION.json). Dates contractuelles figées conservées ; T03/T04/T16 restent partiels.

**Suivi historique C06 — 20/10/2026 :** cinq constats corrigés et validés localement : versions RFQ épinglées, contexte conservé, dossier booké protégé et références SQL qualifiées. [Rapport](../REMEDIATION_C06_2026-10-20.md), [preuves](C06_VALIDATION.json). C01 à C05 préservés ; T02/T12/T13 et reprise historique non clôturés.

**Suivi historique C07 — 21/10/2026 :** douze constats traités localement ; 303 cas backend distincts, 541 tests frontend et build réussis. [Rapport](../REMEDIATION_C07_2026-10-21.md), [preuves](C07_VALIDATION.json). C06 préservé ; budget de volumétrie M04-10, T11/T15 et recette graphique/production restants.

**Suivi historique C11 — 21/10/2026 :** sept constats traités et validés localement ; seuils EOD/FX de 3 jours calendaires confirmés par Philippe. [Rapport](../REMEDIATION_C11_2026-10-21.md), [preuves](C11_VALIDATION.json). Finalité C13, T04/T10 et qualification production restent ouverts.

**Suivi historique C12 — 21/10/2026 :** deux constats traités et validés localement : imports stricts, publication groupée atomique, lecteurs cohérents et caches indépendants. [Rapport](../REMEDIATION_C12_2026-10-21.md), [preuves](C12_VALIDATION.json). T04 combiné validé localement ; règle C11 de 3 jours conservée, sans qualification production.

**Suivi historique C15 — 21/10/2026 :** trois constats corrigés et validés localement ; funding hors taux stochastiques et drift, variance mono préservée et Hull-White stable près de zéro. [Rapport](../REMEDIATION_C15_2026-10-21.md), [preuves](C15_VALIDATION.json). 231 cas backend distincts réussis ; T06 partiel, C18 et D04 ouverts.

**Suivi historique C16 — 21/10/2026 :** copies équivalentes cohérentes avec le mono ; approximation corrélée qualifiée localement sur un panel GBM à deux actifs, seuil de 10 pb confirmé. 319 cas backend et 7 tests frontend réussis. [Rapport](../REMEDIATION_C16_2026-10-21.md), [preuves](C16_VALIDATION.json). Configurations hors domaine admis refusées ; T07 et qualification de production restent ouverts.

## Référence courante — actualisée le 24 octobre 2026

**Suite backend complète — 23/10/2026 :** premier passage : 3 883 succès, 48 échecs, 11 erreurs et 3 ignorés. Les **59 cas** sont corrigés dans **14 suivis F08-F21** ; **817 tests ciblés distincts réussis**. Passage complet final : **3 943 succès, 3 ignorés conditionnels inchangés, aucun échec ni erreur**. Les 121 résolutions historiques et les 59 supplémentaires passent dans ce même passage final ; solde courant **0 cas ouvert sur 180 documentés**. Référence figée et preuves antérieures conservées ; recette graphique et qualification déployée distinctes. [Rapport](../BACKEND_FULL_VALIDATION_2026-10-23.md) · [preuves](BACKEND_FULL_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F01 — 23/10/2026 :** échec reproduit avant le contrôle d’ouverture : mot de passe de fixture de 11 caractères, refusé par C02. Demande conforme, contexte autonome et motif 403 précis ; **21 tests ciblés distincts réussis** (15 inscription + 6 voisins), dont 14 nouveaux cas HTTP. Ouverture explicite, refus géré, limites de mot de passe, persistance et sessions vérifiés sans changement applicatif. Aucun appel HTTP externe ni arbitrage nouveau. Solde après F01 : **0 cas historique ouvert**, soit **121 cas résolus localement dans 7 groupes** sur preuves ciblées datées. Les autres groupes ne sont pas relancés ; aucune qualification globale ou de production. [Rapport](../REMEDIATION_F01_2026-10-23.md) · [preuves](F01_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F07 — 23/10/2026 :** échec du faux utilisateur sans rôle reproduit puis résolu par une fixture persistée conforme, avec contrepartie active et gardes FK/Product. Dix dates de départ sans doublon au strike et neuf relevés enfants vérifiés ; droits JWT contrôlés en autonome et installation gérée, priorité du registre officiel réexercée par des tests voisins. **20 tests ciblés distincts réussis** (11 relevés + 9 voisins), dont deux nouveaux cas HTTP. Aucun changement applicatif, appel HTTP externe ni arbitrage nouveau. Solde après F07 : **1 cas documenté dans 1 groupe ouvert** (F01), non relancé. [Rapport](../REMEDIATION_F07_2026-10-23.md) · [preuves](F07_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F06 — 23/10/2026 :** 14 échecs reproduits puis résolus par des fixtures JWT/desks/identité juridique conformes, sous clés étrangères et gardes Product. Créations vérifiées avant lecture ; deux faux positifs négatifs renforcés ; chaîne RFQ-Deal exécutée sur le même Product/version avec calcul réel hors ligne. **32 tests ciblés distincts réussis** (19 chaîne CRM + 13 voisins), dont trois nouveaux refus atomiques et rejouables. Aucun changement applicatif, appel HTTP externe ni arbitrage nouveau. Solde après F06 : **2 cas documentés dans 2 groupes ouverts** (F01/F07), non relancés. [Rapport](../REMEDIATION_F06_2026-10-23.md) · [preuves](F06_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F05 — 23/10/2026 :** cinq refus 403 reproduits puis résolus par une fixture authentifiée réelle, sans modification applicative ni élargissement des permissions. **58 tests ciblés distincts réussis**, dont les cinq identités initiales inchangées et 34 nouveaux contrôles : refus 401/403, droits relus, aperçu/envoi/provenance en autonome et installation gérée. Aucun appel HTTP externe ou LLM réel. Solde après F05 : **16 cas documentés dans 3 groupes ouverts** (F01/F06/F07), non relancés. [Rapport](../REMEDIATION_F05_2026-10-23.md) · [preuves](F05_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F03 — 23/10/2026 :** 90 échecs reproduits puis couverts ; fixtures avec utilisateurs/desks réels, motifs et identifiants juridiques explicites. Deux défauts RFQ corrigés : suppression du last look sous clés étrangères et interdiction de supprimer une réponse d’un tour clos. **212 tests ciblés distincts réussis** (127 RFQ, 2 CCR dépendants, 83 voisins), sans appel HTTP externe. Trois tests renommés avec correspondance conservée. Solde après F03 : **21 cas documentés dans 4 groupes ouverts** (F01/F05/F06/F07), non relancés. [Rapport](../REMEDIATION_F03_2026-10-23.md) · [preuves](F03_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F04 — 23/10/2026 :** neuf échecs initiaux résolus : fixture Product conforme et cours datés simulés dans les tests. Générateur corrigé pour conserver le calendrier booké, annuler les écritures d’un refresh en échec et auditer la couverture réelle. **55 cas ciblés distincts réussis**, dont 37 du générateur et 18 voisins ; aucun cours synthétique introduit dans le générateur. Solde après F04 : **111 cas documentés dans 5 groupes ouverts**. [Rapport](../REMEDIATION_F04_2026-10-23.md) · [preuves](F04_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json).

**Suivi F02 — 23/10/2026 :** fixture de migration corrigée pour respecter la création préalable des tables du démarrage normal. Deux démarrages réels sur base isolée et protections Product vérifiés ; **7 tests ciblés réussis**, aucune migration applicative modifiée. Solde après F02 : **120 cas documentés dans 6 groupes ouverts**. [Rapport F02](../REMEDIATION_F02_2026-10-23.md) · [preuves](F02_VALIDATION.json) · [registre courant](FAILURE_REGISTER.json). Les inventaires figés de l’étape 1 conservent leur situation initiale de 121 cas.

Les **27 chantiers ont une livraison locale et des preuves ciblées datées**. Les 132 constats et leurs critères restent conservés ; aucune clôture de production n’est prononcée. La consolidation initiale était documentaire ; les suivis F02/F04/F03/F05/F06/F07/F01 ci-dessus conservent séparément leurs modifications et tests ciblés.

La [consolidation de référence](../REFERENCE_CONSOLIDATION_2026-10-23.md) remplace les mentions de dépendances encore ouvertes qui ont été livrées ultérieurement. L’[inventaire figé des échecs avant F02](../reference-consolidation-2026-10-23/REMAINING_FAILURES.md) distingue **121 cas sans succès ultérieur conservé en 7 groupes**, les reproductions initiales suivies d’un succès et les tests renommés. Les résultats historiques ne constituent pas un passage sur la référence consolidée.

| Chantier | État local et solde au 23/10/2026 |
|---|---|
| [C01](DEPENDENCIES_AND_VALIDATION.md#c01) | Revue métier D05 ; recette graphique et transverse complète, puis qualification déployée. |
| [C02](DEPENDENCIES_AND_VALIDATION.md#c02) | Recette graphique/transverse ; adoption attestée des anciens workspaces Admin et procédure de reconnexion. |
| [C03](DEPENDENCIES_AND_VALIDATION.md#c03) | D01 confirmée ; recette graphique/transverse et reprise des identités historiques non qualifiées. |
| [C04](DEPENDENCIES_AND_VALIDATION.md#c04) | Requalification C21 des limites raccordée localement ; recette transverse intégrale et qualification déployée. |
| [C05](DEPENDENCIES_AND_VALIDATION.md#c05) | D02 confirmée ; recette graphique/transverse et qualification déployée ; calendriers bookés conservés. |
| [C06](DEPENDENCIES_AND_VALIDATION.md#c06) | Versions et reprises C08 raccordées localement ; reprise historique, recette graphique/transverse et qualification déployée. |
| [C07](DEPENDENCIES_AND_VALIDATION.md#c07) | T11/T15 couverts sur leurs composantes locales ; budget de volumétrie/SLA à fixer, recette graphique et qualification déployée. |
| [C08](DEPENDENCIES_AND_VALIDATION.md#c08) | Commandes et filiation validées localement, raccord C20/C23 exercé ; recette graphique/transverse et qualification déployée. |
| [C09](DEPENDENCIES_AND_VALIDATION.md#c09) | T03/T15 couverts localement ; recette graphique/transverse et qualification déployée. |
| [C10](DEPENDENCIES_AND_VALIDATION.md#c10) | C17/T11 raccordés localement ; recette graphique de chaîne et qualification déployée. |
| [C11](DEPENDENCIES_AND_VALIDATION.md#c11) | T04 combiné validé localement, T10 complété par C21/C24/C27 ; qualification graphique/transverse et déployée. |
| [C12](DEPENDENCIES_AND_VALIDATION.md#c12) | T04 combiné validé localement ; recette graphique/déployée et politique de rétention des générations à préciser. |
| [C13](DEPENDENCIES_AND_VALIDATION.md#c13) | T08 enrichi par C18/C19/C21/C22/C26 ; D06 et chaîne déployée complète restantes ; F02 résolu localement par correction de fixture, migration applicative inchangée. |
| [C14](DEPENDENCIES_AND_VALIDATION.md#c14) | T03 et composantes T09 raccordés localement ; recette transverse et qualification déployée. |
| [C15](DEPENDENCIES_AND_VALIDATION.md#c15) | C18/T06 raccordés localement ; funding hors taux stochastiques et drift ; domaine D04 et qualification déployée restants. |
| [C16](DEPENDENCIES_AND_VALIDATION.md#c16) | C18/T07 raccordés localement dans le domaine restreint C16, seuil de panel 10 pb ; extensions de domaine et qualification déployée restantes. |
| [C17](DEPENDENCIES_AND_VALIDATION.md#c17) | Points publiés et garde asynchrone C10 raccordés localement, seuils 5/10 pb ; domaine élargi et qualification déployée restants. |
| [C18](DEPENDENCIES_AND_VALIDATION.md#c18) | Raccords locaux C13/C15/C16/C17, puis C19/C21/C22/C25 livrés ; recette transverse/graphique et qualification déployée restantes. |
| [C19](DEPENDENCIES_AND_VALIDATION.md#c19) | D10/D11 confirmées ; garde d’identité locale disponible ; adoption/migration réelle et recette graphique/déployée restantes. |
| [C20](DEPENDENCIES_AND_VALIDATION.md#c20) | Reprises C08 et T15 raccordées localement ; D12/budget souple explicite, recette graphique et qualification déployée restantes. |
| [C21](DEPENDENCIES_AND_VALIDATION.md#c21) | Prérequis C27 soldé localement ; composantes T05/T08/T09/T10 exercées ; D08, recette transverse et qualification déployée restantes. |
| [C22](DEPENDENCIES_AND_VALIDATION.md#c22) | Composantes T08/T09 raccordées localement ; D07 et recette transverse/graphique/déployée restantes. |
| [C23](DEPENDENCIES_AND_VALIDATION.md#c23) | C08 et limites résultantes C04 réexercés ; réseau applicatif simulé localement ; recette réelle bilatérale et qualification déployée restantes. |
| [C24](DEPENDENCIES_AND_VALIDATION.md#c24) | Prérequis C27 soldé localement ; restitution par devise sans FX ; chaîne CRM historique F06, recette graphique/déployée restantes. |
| [C25](DEPENDENCIES_AND_VALIDATION.md#c25) | D09 confirmée ; C26/C27 livrés localement ; composantes T16 couvertes, recette graphique et qualification déployée restantes. |
| [C26](DEPENDENCIES_AND_VALIDATION.md#c26) | Consommation officielle et retries C27 exercés ; fixture F07, D07 et recette graphique/déployée restantes. |
| [C27](DEPENDENCIES_AND_VALIDATION.md#c27) | Solde Production/UAT, historiques et Demo livré localement ; recette transverse/graphique et qualification déployée restantes. |

Les sections de suivi ci-dessous et les validations individuelles conservent leur portée **à la date de leur livraison**. Le tableau ci-dessus et `workstreams[].current_review` dans REGISTER.json donnent les résiduels actuels. Les champs initiaux du lot 0 restent historiques.

## Couverture

| Module | Domaine | P1 | P2 | P3 | Total |
|---|---|---:|---:|---:|---:|
| [M01](#m01) | Accès, organisations et installations | 5 | 7 | 0 | 12 |
| [M02](#m02) | Référentiels et calendriers | 7 | 6 | 0 | 13 |
| [M03](#m03) | Données de marché | 5 | 5 | 1 | 11 |
| [M04](#m04) | Product et bibliothèque | 2 | 8 | 0 | 10 |
| [M05](#m05) | PayScript, Economics et modèles | 1 | 7 | 0 | 8 |
| [M06](#m06) | Pricer et moteur quantitatif | 5 | 4 | 0 | 9 |
| [M07](#m07) | Surfaces et calibration | 3 | 4 | 0 | 7 |
| [M08](#m08) | Product Optimizer | 1 | 5 | 1 | 7 |
| [M09](#m09) | RFQ fournisseurs et cotations | 1 | 8 | 0 | 9 |
| [M10](#m10) | RFQ reçues, réseau et exécutions | 2 | 3 | 0 | 5 |
| [M11](#m11) | Booking | 4 | 2 | 0 | 6 |
| [M12](#m12) | Fixings, événements et alertes | 2 | 4 | 0 | 6 |
| [M13](#m13) | MtM résiduel et historique | 2 | 5 | 0 | 7 |
| [M14](#m14) | Valo Explain et P&L | 1 | 4 | 0 | 5 |
| [M15](#m15) | Risques portefeuille et CCR | 4 | 3 | 0 | 7 |
| [M16](#m16) | Clients / CRM | 1 | 4 | 0 | 5 |
| [M17](#m17) | Réinvestissement et déclinaisons | 3 | 2 | 0 | 5 |

## M01

**Accès, organisations et installations**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M01-01](#m01-01) | P1 | [C01](DEPENDENCIES_AND_VALIDATION.md#c01) | La gestion des relations de trading ne demande aucune permission spécifique |
| [M01-02](#m01-02) | P1 | [C01](DEPENDENCIES_AND_VALIDATION.md#c01) | Tout profil connecté peut déclarer un règlement |
| [M01-03](#m01-03) | P1 | [C01](DEPENDENCIES_AND_VALIDATION.md#c01) | L’interdiction de pricing des profils secondaires est partielle |
| [M01-04](#m01-04) | P1 | [C01](DEPENDENCIES_AND_VALIDATION.md#c01) | Le parcours de booking Opérations est bloqué par l’interface |
| [M01-05](#m01-05) | P1 | [C01](DEPENDENCIES_AND_VALIDATION.md#c01) | La propriété organisationnelle n’est pas appliquée uniformément |
| [M01-06](#m01-06) | P2 | [C02](DEPENDENCIES_AND_VALIDATION.md#c02) | Les sessions ne disposent pas de révocation serveur |
| [M01-07](#m01-07) | P2 | [C02](DEPENDENCIES_AND_VALIDATION.md#c02) | Le portail commun perd le choix de l’installation hors mode développeur |
| [M01-08](#m01-08) | P2 | [C02](DEPENDENCIES_AND_VALIDATION.md#c02) | Les comptes créés manuellement ont une politique de mot de passe insuffisante |
| [M01-09](#m01-09) | P2 | [C02](DEPENDENCIES_AND_VALIDATION.md#c02) | Les connexions métier ordinaires ne sont pas auditées comme les accès développeur |
| [M01-10](#m01-10) | P2 | [C02](DEPENDENCIES_AND_VALIDATION.md#c02) | L’administration des entités contredit le modèle mono-organisation |
| [M01-11](#m01-11) | P2 | [C02](DEPENDENCIES_AND_VALIDATION.md#c02) | Le workspace Admin ne bénéficie pas du même contrôle préalable d’identité de base |
| [M01-12](#m01-12) | P2 | [C02](DEPENDENCIES_AND_VALIDATION.md#c02) | Quatre routes de calendrier restent accessibles sans connexion |

### M01-01

**La gestion des relations de trading ne demande aucune permission spécifique**

- Priorité d'audit : **P1** ; chantier principal : **[C01](DEPENDENCIES_AND_VALIDATION.md#c01)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m01-01).
- Validation : **V-M01-01 — réussie localement sur le périmètre C01** ; [résultats et limites](../REMEDIATION_C01_2026-10-20.md), [preuve structurée](C01_VALIDATION.json).

**Critère de validation :** Appeler création et modification d'accords avec Front, Contrôleur, Opérations, administrateur et habilité explicite ; seuls les acteurs autorisés réussissent ; les refus ne changent aucune limite et sont audités.

**Points d'entrée de l'audit :** [Création et modification des relations](C:/Users/admin/GitHub/structura/backend/app/api/trading.py:97).

### M01-02

**Tout profil connecté peut déclarer un règlement**

- Priorité d'audit : **P1** ; chantier principal : **[C01](DEPENDENCIES_AND_VALIDATION.md#c01)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m01-02).
- Validation : **V-M01-02 — réussie localement sur le périmètre C01** ; [résultats et limites](../REMEDIATION_C01_2026-10-20.md), [preuve structurée](C01_VALIDATION.json).

**Critère de validation :** Une référence de règlement fournie par Front sans permission est refusée ; l'acteur autorisé peut déclarer le règlement ; date prévue et confirmation effective restent distinctes.

**Points d'entrée de l'audit :** [Enregistrement du règlement](C:/Users/admin/GitHub/structura/backend/app/api/trading.py:248).

### M01-03

**L’interdiction de pricing des profils secondaires est partielle**

- Priorité d'audit : **P1** ; chantier principal : **[C01](DEPENDENCIES_AND_VALIDATION.md#c01)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m01-03).
- Validation : **V-M01-03 — réussie localement sur le périmètre C01** ; [résultats et limites](../REMEDIATION_C01_2026-10-20.md), [preuve structurée](C01_VALIDATION.json).

**Critère de validation :** Tester chaque entrée de calcul, dont in-life, Optimizer, solveur, grilles et batches ; l'accès reflète la permission de structuration ou de valorisation opérationnelle explicitement retenue.

**Points d'entrée de l'audit :** [Pricing en cours de vie](C:/Users/admin/GitHub/structura/backend/app/api/inlife.py:405) · [Optimizer](C:/Users/admin/GitHub/structura/backend/app/api/product_optimizer.py:25) · [batches](C:/Users/admin/GitHub/structura/backend/app/api/compute.py:73).

### M01-04

**Le parcours de booking Opérations est bloqué par l’interface**

- Priorité d'audit : **P1** ; chantier principal : **[C01](DEPENDENCIES_AND_VALIDATION.md#c01)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m01-04).
- Validation : **V-M01-04 — réussie localement sur le périmètre C01** ; [résultats et limites](../REMEDIATION_C01_2026-10-20.md), [preuve structurée](C01_VALIDATION.json).

**Critère de validation :** Depuis une RFQ valide, Opérations ouvre un contrôle de booking accessible, consulte le contrat et la preuve retenus puis booke une fois sans accès au pricing privé non autorisé.

**Points d'entrée de l'audit :** [Action de booking RFQ](C:/Users/admin/GitHub/structura/frontend/src/views/RfqView.vue:2751) · [restriction du Pricer](C:/Users/admin/GitHub/structura/frontend/src/router/index.js:258).

### M01-05

**La propriété organisationnelle n’est pas appliquée uniformément**

- Priorité d'audit : **P1** ; chantier principal : **[C01](DEPENDENCIES_AND_VALIDATION.md#c01)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m01-05).
- Validation : **V-M01-05 — réussie localement sur le périmètre C01** ; [résultats et limites](../REMEDIATION_C01_2026-10-20.md), [preuve structurée](C01_VALIDATION.json).

**Critère de validation :** Un Front crée un Product/RFQ repris par un collègue habilité puis booké par Opérations et suivi par Contrôleur ; listes, liens directs, alertes et projections appliquent la même politique ; les calculs privés restent protégés.

**Points d'entrée de l'audit :** [Accès Product](C:/Users/admin/GitHub/structura/backend/app/services/product_repository.py:29) · [accès Deal](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:1063) · [alertes](C:/Users/admin/GitHub/structura/backend/app/api/alerts.py:20).

### M01-06

**Les sessions ne disposent pas de révocation serveur**

- Priorité d'audit : **P2** ; chantier principal : **[C02](DEPENDENCIES_AND_VALIDATION.md#c02)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m01-06).
- Validation : **V-M01-06 — validée localement sur le périmètre C02**.

**Critère de validation :** Après révocation ou réinitialisation, rejouer l'ancien jeton échoue, y compris après réactivation du compte ; un nouveau jeton autorisé fonctionne ; une installation étrangère reste inaccessible.

**Points d'entrée de l'audit :** [Émission des jetons](C:/Users/admin/GitHub/structura/backend/app/api/auth.py:156) · [déconnexion locale](C:/Users/admin/GitHub/structura/frontend/src/stores/auth.js:112).

- Livraison locale : [rapport C02](../REMEDIATION_C02_2026-10-20.md) et [preuves](C02_VALIDATION.json). Recette graphique/transverse et qualification production restantes.

### M01-07

**Le portail commun perd le choix de l’installation hors mode développeur**

- Priorité d'audit : **P2** ; chantier principal : **[C02](DEPENDENCIES_AND_VALIDATION.md#c02)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m01-07).
- Validation : **V-M01-07 — validée localement sur le périmètre C02**.

**Critère de validation :** Hors mode développeur, choisir l'installation puis se connecter par le parcours normal atteint l'organisation demandée ; l'erreur d'installation ne transmet pas les identifiants à une autre base.

**Points d'entrée de l'audit :** [Catalogue désactivé](C:/Users/admin/GitHub/structura/backend/app/hybrid/platform.py:153) · [soumission du formulaire](C:/Users/admin/GitHub/structura/frontend/src/views/LoginView.vue:104).

- Livraison locale : [rapport C02](../REMEDIATION_C02_2026-10-20.md) et [preuves](C02_VALIDATION.json). Recette graphique/transverse et qualification production restantes.

### M01-08

**Les comptes créés manuellement ont une politique de mot de passe insuffisante**

- Priorité d'audit : **P2** ; chantier principal : **[C02](DEPENDENCIES_AND_VALIDATION.md#c02)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m01-08).
- Validation : **V-M01-08 — validée localement sur le périmètre C02**.

**Critère de validation :** Une création avec un mot de passe d'un caractère est refusée ; activation, changement personnel et réinitialisation autorisés fonctionnent et invalident les anciens jetons selon la politique retenue.

**Points d'entrée de l'audit :** [Création des utilisateurs](C:/Users/admin/GitHub/structura/backend/app/api/admin.py:451).

- Livraison locale : [rapport C02](../REMEDIATION_C02_2026-10-20.md) et [preuves](C02_VALIDATION.json). Recette graphique/transverse et qualification production restantes.

### M01-09

**Les connexions métier ordinaires ne sont pas auditées comme les accès développeur**

- Priorité d'audit : **P2** ; chantier principal : **[C02](DEPENDENCIES_AND_VALIDATION.md#c02)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m01-09).
- Validation : **V-M01-09 — validée localement sur le périmètre C02**.

**Critère de validation :** Succès et échec de connexion créent des événements corrélables au compte, à l'installation et à l'heure, sans secret ni jeton dans les traces ; vérifier aussi le flux développeur.

**Points d'entrée de l'audit :** [Connexion métier](C:/Users/admin/GitHub/structura/backend/app/api/auth.py:235).

- Livraison locale : [rapport C02](../REMEDIATION_C02_2026-10-20.md) et [preuves](C02_VALIDATION.json). Recette graphique/transverse et qualification production restantes.

### M01-10

**L’administration des entités contredit le modèle mono-organisation**

- Priorité d'audit : **P2** ; chantier principal : **[C02](DEPENDENCIES_AND_VALIDATION.md#c02)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m01-10).
- Validation : **V-M01-10 — validée localement sur le périmètre C02**.

**Critère de validation :** Un acteur local ne crée pas une seconde organisation inutilisable ; un renommage autorisé reste cohérent avec le manifeste ; le provisionnement d'une nouvelle installation demeure distinct.

**Points d'entrée de l'audit :** [Administration des entités](C:/Users/admin/GitHub/structura/backend/app/api/admin.py:558).

- Livraison locale : [rapport C02](../REMEDIATION_C02_2026-10-20.md) et [preuves](C02_VALIDATION.json). Recette graphique/transverse et qualification production restantes.

### M01-11

**Le workspace Admin ne bénéficie pas du même contrôle préalable d’identité de base**

- Priorité d'audit : **P2** ; chantier principal : **[C02](DEPENDENCIES_AND_VALIDATION.md#c02)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m01-11).
- Validation : **V-M01-11 — validée localement sur le périmètre C02**.

**Critère de validation :** Une base incompatible présentée au workspace Admin est refusée avant création, migration ou seed ; son empreinte de schéma et de contenu demeure inchangée ; une base Admin valide démarre.

**Points d'entrée de l'audit :** [Lancement du workspace](C:/Users/admin/GitHub/structura/backend/run.py:23) · [initialisation spécifique](C:/Users/admin/GitHub/structura/backend/app/hybrid/admin_workbench.py:28).

- Livraison locale : [rapport C02](../REMEDIATION_C02_2026-10-20.md) et [preuves](C02_VALIDATION.json). Recette graphique/transverse et qualification production restantes.

### M01-12

**Quatre routes de calendrier restent accessibles sans connexion**

- Priorité d'audit : **P2** ; chantier principal : **[C02](DEPENDENCIES_AND_VALIDATION.md#c02)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m01-12).
- Validation : **V-M01-12 — validée localement sur le périmètre C02**.

**Critère de validation :** Sans session, les quatre routes de calendrier refusent le calcul ; une session habilitée et une demande bornée réussissent ; une demande dépassant les bornes est rejetée avant travail coûteux.

**Points d'entrée de l'audit :** [Routes de calendrier](C:/Users/admin/GitHub/structura/backend/app/api/schedule.py:14).

- Livraison locale : [rapport C02](../REMEDIATION_C02_2026-10-20.md) et [preuves](C02_VALIDATION.json). Recette graphique/transverse et qualification production restantes.

## M02

**Référentiels et calendriers**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M02-01](#m02-01) | P1 | [C05](DEPENDENCIES_AND_VALIDATION.md#c05) | Un échéancier mensuel perd son ancrage après un mois court |
| [M02-02](#m02-02) | P1 | [C05](DEPENDENCIES_AND_VALIDATION.md#c05) | Les paramètres de règlement ne sont pas validés uniformément |
| [M02-03](#m02-03) | P1 | [C05](DEPENDENCIES_AND_VALIDATION.md#c05) | Le Pricer propose silencieusement une date de paiement avec un calendrier dégradé |
| [M02-04](#m02-04) | P1 | [C05](DEPENDENCIES_AND_VALIDATION.md#c05) | Les calendriers d’observation et de règlement sont confondus |
| [M02-05](#m02-05) | P1 | [C03](DEPENDENCIES_AND_VALIDATION.md#c03) | Choisir un sous-jacent dans le Pricer ne reprend pas sa devise |
| [M02-06](#m02-06) | P1 | [C03](DEPENDENCIES_AND_VALIDATION.md#c03) | Un lien juridique explicite invalide peut provoquer une substitution de contrepartie |
| [M02-07](#m02-07) | P1 | [C04](DEPENDENCIES_AND_VALIDATION.md#c04) | Renommer une contrepartie fait disparaître son contrôle historique de concentration |
| [M02-08](#m02-08) | P2 | [C03](DEPENDENCIES_AND_VALIDATION.md#c03) | Les cotations manuelles restent dépendantes de libellés et de rattachements courants |
| [M02-09](#m02-09) | P2 | [C05](DEPENDENCIES_AND_VALIDATION.md#c05) | L’aperçu et le contrat ont des conventions par défaut différentes |
| [M02-10](#m02-10) | P2 | [C05](DEPENDENCIES_AND_VALIDATION.md#c05) | « Stub long » applique une heuristique insuffisamment visible |
| [M02-11](#m02-11) | P2 | [C03](DEPENDENCIES_AND_VALIDATION.md#c03) | La qualification des métadonnées reste trop permissive |
| [M02-12](#m02-12) | P2 | [C03](DEPENDENCIES_AND_VALIDATION.md#c03) | Les modifications du référentiel ne suivent pas un cycle de gouvernance complet |
| [M02-13](#m02-13) | P2 | [C03](DEPENDENCIES_AND_VALIDATION.md#c03) | Ajouter un groupe à un titre connu dépend encore d’un appel externe |

### M02-01

**Un échéancier mensuel perd son ancrage après un mois court**

- Priorité d'audit : **P1** ; chantier principal : **[C05](DEPENDENCIES_AND_VALIDATION.md#c05)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m02-01).
- Validation : **V-M02-01 — validée localement sur le périmètre C05**.

**Critère de validation :** Ancre 31/01/2026, fréquence mensuelle jusqu'au 31/05 : grille brute 31/01, 28/02, 31/03, 30/04, 31/05, sans sixième date ; couvrir aussi année bissextile et ajustement ouvré.

**Points d'entrée de l'audit :** [Génération principale](C:/Users/admin/GitHub/structura/backend/app/core/schedule.py:87).

Livraison : [rapport C05](../REMEDIATION_C05_2026-10-20.md), [preuves ciblées](C05_VALIDATION.json). Qualification transverse et production encore ouvertes.


### M02-02

**Les paramètres de règlement ne sont pas validés uniformément**

- Priorité d'audit : **P1** ; chantier principal : **[C05](DEPENDENCIES_AND_VALIDATION.md#c05)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m02-02).
- Validation : **V-M02-02 — validée localement sur le périmètre C05**.

**Critère de validation :** Les mêmes entrées de règlement sont validées en aperçu, Product, pricing et booking : -3 et 1,8 ne sont jamais tronqués/acceptés ; 100 suit une borne commune explicite ; aucun paiement avant observation.

**Points d'entrée de l'audit :** [Résolution du délai](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:1163).

Livraison : [rapport C05](../REMEDIATION_C05_2026-10-20.md), [preuves ciblées](C05_VALIDATION.json). Qualification transverse et production encore ouvertes.


### M02-03

**Le Pricer propose silencieusement une date de paiement avec un calendrier dégradé**

- Priorité d'audit : **P1** ; chantier principal : **[C05](DEPENDENCIES_AND_VALIDATION.md#c05)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m02-03).
- Validation : **V-M02-03 — validée localement sur le périmètre C05**.

**Critère de validation :** Simuler une panne de calendrier : aucun J+3 week-ends-seuls n'est proposé comme date qualifiée ; dans le cas TARGET 02/04/2026, J+3 résout 09/04/2026 ou requiert une saisie explicitement signalée.

**Points d'entrée de l'audit :** [Proposition de paiement](C:/Users/admin/GitHub/structura/frontend/src/components/EconomicsTab.vue:409).

Livraison : [rapport C05](../REMEDIATION_C05_2026-10-20.md), [preuves ciblées](C05_VALIDATION.json). Qualification transverse et production encore ouvertes.


### M02-04

**Les calendriers d’observation et de règlement sont confondus**

- Priorité d'audit : **P1** ; chantier principal : **[C05](DEPENDENCIES_AND_VALIDATION.md#c05)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m02-04).
- Validation : **V-M02-04 — validée localement sur le périmètre C05**.

**Critère de validation :** Choisir séparément places d'observation et centres de règlement ; démontrer une observation NYSE fermée alors que le centre de paiement diffère ; figer les règles de combinaison pour les paniers.

**Points d'entrée de l'audit :** [Référentiel actuel](C:/Users/admin/GitHub/structura/backend/app/core/calendars.py:25) · [utilisation dans PayScript](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:1196).

Livraison : [rapport C05](../REMEDIATION_C05_2026-10-20.md), [preuves ciblées](C05_VALIDATION.json). Qualification transverse et production encore ouvertes.


### M02-05

**Choisir un sous-jacent dans le Pricer ne reprend pas sa devise**

- Priorité d'audit : **P1** ; chantier principal : **[C03](DEPENDENCIES_AND_VALIDATION.md#c03)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m02-05).
- Validation : **V-M02-05 — validée localement sur le périmètre C03**.

**Critère de validation :** Sélectionner AAPL depuis une ligne BNP EUR change ensemble ticker, nom et devise selon le référentiel ; toute surcharge conservée est visible ; Pricer et RFQ sont cohérents.

**Points d'entrée de l'audit :** [Sélection dans le Pricer](C:/Users/admin/GitHub/structura/frontend/src/components/EconomicsTab.vue:469).

- Livraison locale : [rapport C03](../REMEDIATION_C03_2026-10-20.md) et [preuves](C03_VALIDATION.json). D01 confirmée ; recettes graphique/transverse et qualification production restantes.

### M02-06

**Un lien juridique explicite invalide peut provoquer une substitution de contrepartie**

- Priorité d'audit : **P1** ; chantier principal : **[C03](DEPENDENCIES_AND_VALIDATION.md#c03)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m02-06).
- Validation : **V-M02-06 — validée localement sur le périmètre C03**.

**Critère de validation :** Un fournisseur lié explicitement à une contrepartie désactivée est refusé ou passe par une exception autorisée ; aucune substitution à une autre banque homonyme n'est effectuée.

**Points d'entrée de l'audit :** [Résolution fournisseur–contrepartie](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:384).

- Livraison locale : [rapport C03](../REMEDIATION_C03_2026-10-20.md) et [preuves](C03_VALIDATION.json). D01 confirmée ; recettes graphique/transverse et qualification production restantes.

### M02-07

**Renommer une contrepartie fait disparaître son contrôle historique de concentration**

- Priorité d'audit : **P1** ; chantier principal : **[C04](DEPENDENCIES_AND_VALIDATION.md#c04)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m02-07).
- Validation : **V-M02-07 — validée localement sur le périmètre C04**.

**Critère de validation :** Après renommage de la banque, mêmes Deals, identifiant, exposition, limite et dépassement ; la restitution peut conserver le libellé historique. Couvre aussi M15-06.

**Points d'entrée de l'audit :** [Agrégation concernée](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:680).

- Livraison locale : [rapport C04](../REMEDIATION_C04_2026-10-20.md) et [preuves](C04_VALIDATION.json). T05 complet et qualification C21 encore ouverts.

### M02-08

**Les cotations manuelles restent dépendantes de libellés et de rattachements courants**

- Priorité d'audit : **P2** ; chantier principal : **[C03](DEPENDENCIES_AND_VALIDATION.md#c03)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m02-08).
- Validation : **V-M02-08 — validée localement sur le périmètre C03**.

**Critère de validation :** Renommer ou rerattacher un fournisseur ne réattribue aucune cotation historique ; identifiant et banque figée sont conservés ; une nouvelle cotation utilise la nouvelle relation explicite.

**Points d'entrée de l'audit :** [Construction des réponses](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:421).

- Livraison locale : [rapport C03](../REMEDIATION_C03_2026-10-20.md) et [preuves](C03_VALIDATION.json). D01 confirmée ; recettes graphique/transverse et qualification production restantes.

### M02-09

**L’aperçu et le contrat ont des conventions par défaut différentes**

- Priorité d'audit : **P2** ; chantier principal : **[C05](DEPENDENCIES_AND_VALIDATION.md#c05)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m02-09).
- Validation : **V-M02-09 — validée localement sur le périmètre C05**.

**Critère de validation :** Omettre une convention produit le même refus ou la même règle explicitement documentée dans aperçu et contrat ; une convention choisie donne la même liste de dates sur les deux chemins.

**Points d'entrée de l'audit :** [Schéma de l’aperçu](C:/Users/admin/GitHub/structura/backend/app/core/schemas.py:583) · [résolveur](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:1121).

Livraison : [rapport C05](../REMEDIATION_C05_2026-10-20.md), [preuves ciblées](C05_VALIDATION.json). Qualification transverse et production encore ouvertes.


### M02-10

**« Stub long » applique une heuristique insuffisamment visible**

- Priorité d'audit : **P2** ; chantier principal : **[C05](DEPENDENCIES_AND_VALIDATION.md#c05)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m02-10).
- Validation : **V-M02-10 — validée localement sur le périmètre C05**.

**Critère de validation :** Le cas 15/01–05/03/2026 mensuel restitue des stubs conformes à la définition métier retenue ; aucune heuristique de fusion ne reste dissimulée derrière le libellé Long.

**Points d'entrée de l'audit :** [Traitement des stubs](C:/Users/admin/GitHub/structura/backend/app/core/schedule.py:111).

Livraison : [rapport C05](../REMEDIATION_C05_2026-10-20.md), [preuves ciblées](C05_VALIDATION.json). Qualification transverse et production encore ouvertes.


### M02-11

**La qualification des métadonnées reste trop permissive**

- Priorité d'audit : **P2** ; chantier principal : **[C03](DEPENDENCIES_AND_VALIDATION.md#c03)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m02-11).
- Validation : **V-M02-11 — validée localement sur le périmètre C03**.

**Critère de validation :** Rejeter noms vides, devise inconnue et limite négative ; deux groupes du même instrument ne peuvent diverger silencieusement sur sa devise ; l'absence de métadonnée reste à qualifier.

**Points d'entrée de l'audit :** [Ajout et modification des sous-jacents](C:/Users/admin/GitHub/structura/backend/app/api/admin.py:780).

- Livraison locale : [rapport C03](../REMEDIATION_C03_2026-10-20.md) et [preuves](C03_VALIDATION.json). D01 confirmée ; recettes graphique/transverse et qualification production restantes.

### M02-12

**Les modifications du référentiel ne suivent pas un cycle de gouvernance complet**

- Priorité d'audit : **P2** ; chantier principal : **[C03](DEPENDENCIES_AND_VALIDATION.md#c03)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m02-12).
- Validation : **V-M02-12 — validée localement sur le périmètre C03**.

**Critère de validation :** Modifier puis désactiver/déplacer une entrée, redémarrer sur base isolée et rafraîchir les catalogues : la décision reste appliquée ; auteur, avant/après et motif sont retrouvés ; pas de réinsertion automatique non annoncée.

**Points d'entrée de l'audit :** [Seed](C:/Users/admin/GitHub/structura/backend/app/db/database.py:896) · [cache frontend](C:/Users/admin/GitHub/structura/frontend/src/data/commonUnderlyings.js:20).

- Livraison locale : [rapport C03](../REMEDIATION_C03_2026-10-20.md) et [preuves](C03_VALIDATION.json). D01 confirmée ; recettes graphique/transverse et qualification production restantes.

### M02-13

**Ajouter un groupe à un titre connu dépend encore d’un appel externe**

- Priorité d'audit : **P2** ; chantier principal : **[C03](DEPENDENCIES_AND_VALIDATION.md#c03)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m02-13).
- Validation : **V-M02-13 — validée localement sur le périmètre C03**.

**Critère de validation :** Ajouter un groupe à un ticker local connu réussit avec tout accès réseau rendu indisponible ; les métadonnées existantes sont réutilisées ; la revalidation externe reste une action distincte.

**Points d'entrée de l'audit :** [Création d’une entrée](C:/Users/admin/GitHub/structura/backend/app/api/admin.py:780).

- Livraison locale : [rapport C03](../REMEDIATION_C03_2026-10-20.md) et [preuves](C03_VALIDATION.json). D01 confirmée ; recettes graphique/transverse et qualification production restantes.

## M03

**Données de marché**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M03-01](#m03-01) | P1 | [C13](DEPENDENCIES_AND_VALIDATION.md#c13) | La clôture du jour n’est pas qualifiée comme définitive |
| [M03-02](#m03-02) | P1 | [C11](DEPENDENCIES_AND_VALIDATION.md#c11) | La RFQ peut remplacer un dividende inconnu par zéro |
| [M03-03](#m03-03) | P1 | [C10](DEPENDENCIES_AND_VALIDATION.md#c10) | Une réponse peut alimenter le mauvais sous-jacent après un changement de ticker |
| [M03-04](#m03-04) | P1 | [C11](DEPENDENCIES_AND_VALIDATION.md#c11) | Un cours interrompu peut être prolongé sans limite dans l’historique |
| [M03-05](#m03-05) | P1 | [C11](DEPENDENCIES_AND_VALIDATION.md#c11) | Les conversions de reporting acceptent un change arbitrairement ancien |
| [M03-06](#m03-06) | P2 | [C11](DEPENDENCIES_AND_VALIDATION.md#c11) | Deux définitions différentes de la volatilité « réalisée » coexistent |
| [M03-07](#m03-07) | P2 | [C11](DEPENDENCIES_AND_VALIDATION.md#c11) | Le contrat de réponse est incomplet pour les historiques partiels |
| [M03-08](#m03-08) | P2 | [C11](DEPENDENCIES_AND_VALIDATION.md#c11) | Le booking conserve mieux les valeurs que leur origine |
| [M03-09](#m03-09) | P2 | [C12](DEPENDENCIES_AND_VALIDATION.md#c12) | Le stockage de prix accepte des imports insuffisamment contrôlés |
| [M03-10](#m03-10) | P2 | [C11](DEPENDENCIES_AND_VALIDATION.md#c11) | L’administration ne supervise pas toute la chaîne de marché |
| [M03-11](#m03-11) | P3 | [C12](DEPENDENCIES_AND_VALIDATION.md#c12) | Le cache mémoire peut être modifié par un appelant |

### M03-01

**La clôture du jour n’est pas qualifiée comme définitive**

- Priorité d'audit : **P1** ; chantier principal : **[C13](DEPENDENCIES_AND_VALIDATION.md#c13)** ; lot principal : **3**.
- Statut : **Ouvert — à revalider avant correction**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m03-01).
- Validation : **V-M03-01 — à préparer, non exécutée au lot 0**.

**Critère de validation :** Une barre intrajournalière datée du jour ne peut devenir un fixing définitif ; une clôture finale conforme est admissible après la séance et le délai de publication retenu ; vérifier fuseau et jour férié.

**Points d'entrée de l'audit :** [Contrôle de publication](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:4564).

### M03-02

**La RFQ peut remplacer un dividende inconnu par zéro**

- Priorité d'audit : **P1** ; chantier principal : **[C11](DEPENDENCIES_AND_VALIDATION.md#c11)** ; lot principal : **3**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m03-02).
- Validation : **V-M03-02 — validé localement le 21/10/2026 avec seuil EOD/FX de 3 jours calendaires confirmé**.

**Critère de validation :** Faire échouer ou omettre la métadonnée dividende : RFQ et réinvestissement ne publient pas q=0 comme chargement réussi ; un vrai zéro sourcé reste admissible ; les profils datés conservent origine et diagnostic.

**Points d'entrée de l'audit :** [Valeur de repli backend](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:138) · [chargement RFQ](C:/Users/admin/GitHub/structura/frontend/src/views/RfqView.vue:2141).

**Remédiation C11 :** [rapport](../REMEDIATION_C11_2026-10-21.md) et [preuves ciblées](C11_VALIDATION.json). D03/C11 confirmé : reports EOD/FX de 3 jours calendaires maximum, J+3 inclus. Aucune finalité officielle ni qualification production déduite.

### M03-03

**Une réponse peut alimenter le mauvais sous-jacent après un changement de ticker**

- Priorité d'audit : **P1** ; chantier principal : **[C10](DEPENDENCIES_AND_VALIDATION.md#c10)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m03-03).
- Validation : **V-M03-03 — validé localement le 21/10/2026**.

**Critère de validation :** Lancer un chargement sur A, choisir B ou saisir un override avant réponse : aucune donnée de A n'écrase B ni la saisie ; le chargement encore courant peut s'appliquer.

**Points d'entrée de l'audit :** [Application de la réponse](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:2037).

**Remédiation C10 :** [rapport](../REMEDIATION_C10_2026-10-21.md) et [preuves ciblées](C10_VALIDATION.json). T11/C17 et recette graphique/production restent ouverts.

### M03-04

**Un cours interrompu peut être prolongé sans limite dans l’historique**

- Priorité d'audit : **P1** ; chantier principal : **[C11](DEPENDENCIES_AND_VALIDATION.md#c11)** ; lot principal : **3**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m03-04).
- Validation : **V-M03-04 — validé localement le 21/10/2026 avec seuil EOD/FX de 3 jours calendaires confirmé**.

**Critère de validation :** Une série arrêtée pendant 60 jours ne devient pas une série de rendements nuls qualifiée ; reports légitimes de fermeture restent bornés et visibles à chaque consommateur.

**Points d'entrée de l'audit :** [Alignement et ancienneté](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:324).

**Remédiation C11 :** [rapport](../REMEDIATION_C11_2026-10-21.md) et [preuves ciblées](C11_VALIDATION.json). D03/C11 confirmé : reports EOD/FX de 3 jours calendaires maximum, J+3 inclus. Aucune finalité officielle ni qualification production déduite.

### M03-05

**Les conversions de reporting acceptent un change arbitrairement ancien**

- Priorité d'audit : **P1** ; chantier principal : **[C11](DEPENDENCIES_AND_VALIDATION.md#c11)** ; lot principal : **3**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m03-05).
- Validation : **V-M03-05 — validé localement le 21/10/2026 avec seuil EOD/FX de 3 jours calendaires confirmé**.

**Critère de validation :** Un FX vieux de plusieurs années est signalé hors politique et n'alimente pas un agrégat qualifié ; retourner date effective, ancienneté et couverture ; valider un FX récent et un FX absent.

**Points d'entrée de l'audit :** [Conversion de reporting](C:/Users/admin/GitHub/structura/backend/app/core/amc_prices.py:320).

**Remédiation C11 :** [rapport](../REMEDIATION_C11_2026-10-21.md) et [preuves ciblées](C11_VALIDATION.json). D03/C11 confirmé : reports EOD/FX de 3 jours calendaires maximum, J+3 inclus. Aucune finalité officielle ni qualification production déduite.

### M03-06

**Deux définitions différentes de la volatilité « réalisée » coexistent**

- Priorité d'audit : **P2** ; chantier principal : **[C11](DEPENDENCIES_AND_VALIDATION.md#c11)** ; lot principal : **3**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m03-06).
- Validation : **V-M03-06 — validé localement le 21/10/2026 avec seuil EOD/FX de 3 jours calendaires confirmé**.

**Critère de validation :** À série, date et méthode identiques, les entrées datées et non datées produisent le même estimateur déclaré ; les corrélations reposent sur un échantillon cohérent et leur matrice est contrôlée.

**Points d'entrée de l'audit :** [Ancienne voie](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:111) · [protection du moteur](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:85).

**Remédiation C11 :** [rapport](../REMEDIATION_C11_2026-10-21.md) et [preuves ciblées](C11_VALIDATION.json). D03/C11 confirmé : reports EOD/FX de 3 jours calendaires maximum, J+3 inclus. Aucune finalité officielle ni qualification production déduite.

### M03-07

**Le contrat de réponse est incomplet pour les historiques partiels**

- Priorité d'audit : **P2** ; chantier principal : **[C11](DEPENDENCIES_AND_VALIDATION.md#c11)** ; lot principal : **3**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m03-07).
- Validation : **V-M03-07 — validé localement le 21/10/2026 avec seuil EOD/FX de 3 jours calendaires confirmé**.

**Critère de validation :** Demander A et B et ne fournir que A : les manquants et leur motif sont exposés ; un calcul exigeant le panier complet refuse ; une exploration réduite conserve le périmètre exclu.

**Points d'entrée de l'audit :** [Réponse historique](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:346) · [réduction de l’univers](C:/Users/admin/GitHub/structura/backend/app/api/pricing.py:995).

**Remédiation C11 :** [rapport](../REMEDIATION_C11_2026-10-21.md) et [preuves ciblées](C11_VALIDATION.json). D03/C11 confirmé : reports EOD/FX de 3 jours calendaires maximum, J+3 inclus. Aucune finalité officielle ni qualification production déduite.

### M03-08

**Le booking conserve mieux les valeurs que leur origine**

- Priorité d'audit : **P2** ; chantier principal : **[C11](DEPENDENCIES_AND_VALIDATION.md#c11)** ; lot principal : **3**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m03-08).
- Validation : **V-M03-08 — validé localement le 21/10/2026 avec seuil EOD/FX de 3 jours calendaires confirmé**.

**Critère de validation :** Charger une référence puis la surcharger ; booking, calcul et réouverture conservent séparément source/date/diagnostic, override et valeur moteur exacte ; aucun override n'est présenté comme donnée fournisseur.

**Points d'entrée de l'audit :** [Construction des entrées du Pricer](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:588).

**Remédiation C11 :** [rapport](../REMEDIATION_C11_2026-10-21.md) et [preuves ciblées](C11_VALIDATION.json). D03/C11 confirmé : reports EOD/FX de 3 jours calendaires maximum, J+3 inclus. Aucune finalité officielle ni qualification production déduite.

### M03-09

**Le stockage de prix accepte des imports insuffisamment contrôlés**

- Priorité d'audit : **P2** ; chantier principal : **[C12](DEPENDENCIES_AND_VALIDATION.md#c12)** ; lot principal : **3**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m03-09).
- Validation : **V-M03-09 — validé localement le 21/10/2026 ; recette graphique/production restante**.

**Critère de validation :** Dates dupliquées, infini et conventions absentes sont rejetés avant remplacement ; A/B et A B ne collisionnent pas ; un téléchargement échoué ne change ni série ni association instrument.

**Points d'entrée de l'audit :** [Import](C:/Users/admin/GitHub/structura/backend/app/core/amc_prices.py:176) · [ordre de mise à jour](C:/Users/admin/GitHub/structura/backend/app/core/amc_prices.py:129).

**Remédiation C12 :** [rapport](../REMEDIATION_C12_2026-10-21.md) et [preuves ciblées](C12_VALIDATION.json). T04 combiné validé localement ; aucun autre chantier clos.

### M03-10

**L’administration ne supervise pas toute la chaîne de marché**

- Priorité d'audit : **P2** ; chantier principal : **[C11](DEPENDENCIES_AND_VALIDATION.md#c11)** ; lot principal : **3**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m03-10).
- Validation : **V-M03-10 — validé localement le 21/10/2026 avec seuil EOD/FX de 3 jours calendaires confirmé**.

**Critère de validation :** Une disponibilité affichée en administration désigne le stockage réellement utilisable par le consommateur ; la reprise locale est démontrée réseau coupé ; ancienneté et qualité remplacent un OK fondé sur le seul âge.

**Points d'entrée de l'audit :** [Catalogue administré](C:/Users/admin/GitHub/structura/backend/app/api/admin.py:679).

**Remédiation C11 :** [rapport](../REMEDIATION_C11_2026-10-21.md) et [preuves ciblées](C11_VALIDATION.json). D03/C11 confirmé : reports EOD/FX de 3 jours calendaires maximum, J+3 inclus. Aucune finalité officielle ni qualification production déduite.

### M03-11

**Le cache mémoire peut être modifié par un appelant**

- Priorité d'audit : **P3** ; chantier principal : **[C12](DEPENDENCIES_AND_VALIDATION.md#c12)** ; lot principal : **3**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m03-11).
- Validation : **V-M03-11 — validé localement le 21/10/2026 ; recette graphique/production restante**.

**Critère de validation :** Modifier une liste de prix retournée ne modifie aucun résultat de la requête suivante ; tester aussi les listes imbriquées et les réponses simultanées.

**Points d'entrée de l'audit :** [Lecture du cache](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:284).

**Remédiation C12 :** [rapport](../REMEDIATION_C12_2026-10-21.md) et [preuves ciblées](C12_VALIDATION.json). T04 combiné validé localement ; aucun autre chantier clos.

## M04

**Product et bibliothèque**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M04-01](#m04-01) | P1 | [C06](DEPENDENCIES_AND_VALIDATION.md#c06) | Une ancienne RFQ peut faire régresser la version courante du Product |
| [M04-02](#m04-02) | P1 | [C06](DEPENDENCIES_AND_VALIDATION.md#c06) | Product → RFQ perd le sens et plusieurs informations commerciales |
| [M04-03](#m04-03) | P2 | [C06](DEPENDENCIES_AND_VALIDATION.md#c06) | Le contexte d’un Product booké reste modifiable par l’API générique |
| [M04-04](#m04-04) | P2 | [C07](DEPENDENCIES_AND_VALIDATION.md#c07) | Le dernier prix peut appartenir à une ancienne version, puis empêcher la réouverture |
| [M04-05](#m04-05) | P2 | [C07](DEPENDENCIES_AND_VALIDATION.md#c07) | Un brouillon incomplet peut être conservé, mais reste difficile à compléter |
| [M04-06](#m04-06) | P2 | [C08](DEPENDENCIES_AND_VALIDATION.md#c08) | L’idempotence backend n’est pas conservée lors d’une nouvelle tentative frontend |
| [M04-07](#m04-07) | P2 | [C06](DEPENDENCIES_AND_VALIDATION.md#c06) | Les protections SQL exigent un Product, mais pas une version contractuelle valide |
| [M04-08](#m04-08) | P2 | [C07](DEPENDENCIES_AND_VALIDATION.md#c07) | La comparaison omet certains paramètres matériels de calcul |
| [M04-09](#m04-09) | P2 | [C19](DEPENDENCIES_AND_VALIDATION.md#c19) | La version du moteur n’est pas conservée avec le calcul |
| [M04-10](#m04-10) | P2 | [C07](DEPENDENCIES_AND_VALIDATION.md#c07) | La bibliothèque reste surtout une liste de produits et de calculs |

### M04-01

**Une ancienne RFQ peut faire régresser la version courante du Product**

- Priorité d'audit : **P1** ; chantier principal : **[C06](DEPENDENCIES_AND_VALIDATION.md#c06)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m04-01).
- Validation : **V-M04-01 — validée localement sur le périmètre C06**.

**Critère de validation :** Créer Product v1 avec RFQ v1, passer Product v2 puis synchroniser l'ancienne RFQ : termes courants restent v2 ; RFQ reste v1 ; nouvelle révision de dossier cohérente et conflit explicite si promotion demandée.

**Points d'entrée de l'audit :** [Chargement de la version RFQ](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1603) · [synchronisation du Product](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:332).

Livraison : [rapport C06](../REMEDIATION_C06_2026-10-20.md), [preuves ciblées](C06_VALIDATION.json). Qualification transverse et production restantes.

### M04-02

**Product → RFQ perd le sens et plusieurs informations commerciales**

- Priorité d'audit : **P1** ; chantier principal : **[C06](DEPENDENCIES_AND_VALIDATION.md#c06)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m04-02).
- Validation : **V-M04-02 — validée localement sur le périmètre C06**.

**Critère de validation :** Partir d'un Product SELL, 2 M, client et format OTC ; la RFQ reprend sens, montant et contexte ; aucun défaut achat/vide ne réécrit le Product lors de la conservation.

**Points d'entrée de l'audit :** [Préremplissage RFQ](C:/Users/admin/GitHub/structura/frontend/src/views/RfqView.vue:1782) · [réécriture du contexte](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1008).

Livraison : [rapport C06](../REMEDIATION_C06_2026-10-20.md), [preuves ciblées](C06_VALIDATION.json). Qualification transverse et production restantes.

### M04-03

**Le contexte d’un Product booké reste modifiable par l’API générique**

- Priorité d'audit : **P2** ; chantier principal : **[C06](DEPENDENCIES_AND_VALIDATION.md#c06)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m04-03).
- Validation : **V-M04-03 — validée localement sur le périmètre C06**.

**Critère de validation :** Sur Product exécuté, une mutation générique de nominal ou client ne crée pas une seconde vérité ; seuls les champs autorisés restent éditables ; une rectification gouvernée conserve le snapshot initial.

**Points d'entrée de l'audit :** [Modification du contexte Product](C:/Users/admin/GitHub/structura/backend/app/api/products.py:233).

Livraison : [rapport C06](../REMEDIATION_C06_2026-10-20.md), [preuves ciblées](C06_VALIDATION.json). Qualification transverse et production restantes.

### M04-04

**Le dernier prix peut appartenir à une ancienne version, puis empêcher la réouverture**

- Priorité d'audit : **P2** ; chantier principal : **[C07](DEPENDENCIES_AND_VALIDATION.md#c07)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m04-04).
- Validation : **V-M04-04 — validée localement sur le périmètre C07**.

**Critère de validation :** Après passage v1→v2, le prix v1 est identifié historique ; ouvrir v2 sans prix compatible charge ses termes et explique l'absence de calcul ; aucun retour silencieux à un Pricer vide.

**Points d'entrée de l'audit :** [Prix de la bibliothèque](C:/Users/admin/GitHub/structura/backend/app/api/products.py:120) · [sélection automatique du calcul](C:/Users/admin/GitHub/structura/frontend/src/stores/products.js:62) · [réinitialisation après échec](C:/Users/admin/GitHub/structura/frontend/src/views/PricerView.vue:111).

- Livraison locale : [rapport C07](../REMEDIATION_C07_2026-10-21.md) et [preuves](C07_VALIDATION.json). T11/T15 et recette graphique/production restent ouverts.

### M04-05

**Un brouillon incomplet peut être conservé, mais reste difficile à compléter**

- Priorité d'audit : **P2** ; chantier principal : **[C07](DEPENDENCIES_AND_VALIDATION.md#c07)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m04-05).
- Validation : **V-M04-05 — validée localement sur le périmètre C07**.

**Critère de validation :** Conserver un brouillon sans date puis le compléter par le parcours prévu ; les valeurs présentes survivent ; les étapes exigeant un contrat complet restent refusées jusqu'à complétude.

**Points d'entrée de l'audit :** [Gestion des brouillons](C:/Users/admin/GitHub/structura/backend/app/core/product/inputs.py:21) · [verrouillage global](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:439).

- Livraison locale : [rapport C07](../REMEDIATION_C07_2026-10-21.md) et [preuves](C07_VALIDATION.json). T11/T15 et recette graphique/production restent ouverts.

### M04-06

**L’idempotence backend n’est pas conservée lors d’une nouvelle tentative frontend**

- Priorité d'audit : **P2** ; chantier principal : **[C08](DEPENDENCIES_AND_VALIDATION.md#c08)** ; lot principal : **6**.
- Statut : **Corrigé localement — commandes et filiation C08 validées**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m04-06).
- Validation : **V-M04-06 — réussie localement** ; [rapport et limites](../REMEDIATION_C08_2026-10-22.md), [preuves](C08_VALIDATION.json).

**Critère de validation :** Simuler succès serveur puis réponse perdue ; la reprise conserve la clé d'intention et retrouve le même Product ; deux créations intentionnellement distinctes utilisent deux clés.

**Points d'entrée de l'audit :** [Création de la commande frontend](C:/Users/admin/GitHub/structura/frontend/src/stores/products.js:90).

### M04-07

**Les protections SQL exigent un Product, mais pas une version contractuelle valide**

- Priorité d'audit : **P2** ; chantier principal : **[C06](DEPENDENCIES_AND_VALIDATION.md#c06)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m04-07).
- Validation : **V-M04-07 — validée localement sur le périmètre C06**.

**Critère de validation :** Avec clés étrangères et protections actives, Product/version NULL ou inexistante 999 sont refusés pour les écritures durables ; une version historique valide reste acceptée selon le contexte.

**Points d'entrée de l'audit :** [Protections des liens](C:/Users/admin/GitHub/structura/backend/app/db/product_migrations.py:47).

Livraison : [rapport C06](../REMEDIATION_C06_2026-10-20.md), [preuves ciblées](C06_VALIDATION.json). Qualification transverse et production restantes.

### M04-08

**La comparaison omet certains paramètres matériels de calcul**

- Priorité d'audit : **P2** ; chantier principal : **[C07](DEPENDENCIES_AND_VALIDATION.md#c07)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m04-08).
- Validation : **V-M04-08 — validée localement sur le périmètre C07**.

**Critère de validation :** Changer uniquement eta de la surface ou un paramètre de taux actif fait apparaître l'écart ; un paramètre inactif est identifié comme tel ; le sens des unités est affiché.

**Points d'entrée de l'audit :** [Comparaison des hypothèses](C:/Users/admin/GitHub/structura/frontend/src/utils/productCalculations.js:32).

- Livraison locale : [rapport C07](../REMEDIATION_C07_2026-10-21.md) et [preuves](C07_VALIDATION.json). T11/T15 et recette graphique/production restent ouverts.

### M04-09

**La version du moteur n’est pas conservée avec le calcul**

- Priorité d'audit : **P2** ; chantier principal : **[C19](DEPENDENCIES_AND_VALIDATION.md#c19)** ; lot principal : **5**.
- Statut : **Corrigé localement — archives et rejeu C19 validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m04-09).
- Validation : **V-M04-09 — validé localement le 21/10/2026**.

**Critère de validation :** Une nouvelle preuve de calcul conserve une version de moteur/compilateur/conventions ; restitution historique et nouveau pricing sont distincts ; les anciennes preuves sans version sont signalées, sans version inventée.

**Points d'entrée de l'audit :** [Enregistrement des calculs](C:/Users/admin/GitHub/structura/backend/app/services/product_repository.py:236).

**Remédiation C19 :** [rapport](../REMEDIATION_C19_2026-10-21.md), [preuves](C19_VALIDATION.json). D10/D11 confirmées ; aucune qualification de production.

### M04-10

**La bibliothèque reste surtout une liste de produits et de calculs**

- Priorité d'audit : **P2** ; chantier principal : **[C07](DEPENDENCIES_AND_VALIDATION.md#c07)** ; lot principal : **2**.
- Statut : **Implémenté localement — pagination validée ; budget de production à définir**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m04-10).
- Validation : **V-M04-10 — validée localement sur le périmètre C07**.

**Critère de validation :** La bibliothèque ouvre un dossier cohérent avec liens RFQ, exécution, documents et versions ; listes et calculs sont paginés ; un jeu synthétique volumineux respecte un budget convenu sans charger tous les dossiers.

**Points d'entrée de l'audit :** [Liste serveur](C:/Users/admin/GitHub/structura/backend/app/api/products.py:193) · [bibliothèque](C:/Users/admin/GitHub/structura/frontend/src/views/ProductsView.vue:31).

- Livraison locale : [rapport C07](../REMEDIATION_C07_2026-10-21.md) et [preuves](C07_VALIDATION.json). T11/T15 et recette graphique/production restent ouverts. Budget de volumétrie à convenir.

## M05

**PayScript, Economics et modèles**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M05-01](#m05-01) | P1 | [C09](DEPENDENCIES_AND_VALIDATION.md#c09) | Une surindentation peut supprimer silencieusement un paiement ou un arrêt |
| [M05-02](#m05-02) | P2 | [C07](DEPENDENCIES_AND_VALIDATION.md#c07) | Les changements de type de déclaration ne préservent pas correctement les termes |
| [M05-03](#m05-03) | P2 | [C07](DEPENDENCIES_AND_VALIDATION.md#c07) | Une série partiellement renseignée perd ses valeurs lors de la préparation d’un brouillon Product |
| [M05-04](#m05-04) | P2 | [C07](DEPENDENCIES_AND_VALIDATION.md#c07) | Le chargement d’une configuration peut laisser une session partiellement remplacée |
| [M05-05](#m05-05) | P2 | [C07](DEPENDENCIES_AND_VALIDATION.md#c07) | L’application d’une configuration remplace davantage d’hypothèses que ne le montre l’aperçu |
| [M05-06](#m05-06) | P2 | [C05](DEPENDENCIES_AND_VALIDATION.md#c05) | Les dates affichées à côté des paramètres par observation peuvent correspondre au mauvais calendrier |
| [M05-07](#m05-07) | P2 | [C10](DEPENDENCIES_AND_VALIDATION.md#c10) | L’aperçu des observations peut revenir à un ancien calendrier |
| [M05-08](#m05-08) | P2 | [C09](DEPENDENCIES_AND_VALIDATION.md#c09) | Certains contrôles de l’assistant affichent une assurance économique excessive |

### M05-01

**Une surindentation peut supprimer silencieusement un paiement ou un arrêt**

- Priorité d'audit : **P1** ; chantier principal : **[C09](DEPENDENCIES_AND_VALIDATION.md#c09)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m05-01).
- Validation : **V-M05-01 — validé localement le 21/10/2026**.

**Critère de validation :** Une ligne PAY ou STOP surindentée sans bloc parent provoque une erreur de ligne, jamais un succès partiel ; script valide capital+coupon paie 108 % à r=0 ; un rappel avec STOP valide ne paie plus à maturité.

**Points d'entrée de l'audit :** [Instructions actuellement ignorées](C:/Users/admin/GitHub/structura/backend/app/core/payscript/parser.py:458).

**Remédiation C09 :** [rapport](../REMEDIATION_C09_2026-10-21.md) et [preuves ciblées](C09_VALIDATION.json). Les recettes T03/C14 et T15/C19/C20 restent partielles.

### M05-02

**Les changements de type de déclaration ne préservent pas correctement les termes**

- Priorité d'audit : **P2** ; chantier principal : **[C07](DEPENDENCIES_AND_VALIDATION.md#c07)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m05-02).
- Validation : **V-M05-02 — validée localement sur le périmètre C07**.

**Critère de validation :** Convertir PARAM() [8,10,12] en scalaire requiert une conversion explicite et conserve les éléments non abandonnés ; passer date unique→échéancier reconstruit un objet valide sans crash.

**Points d'entrée de l'audit :** [Conversion des paramètres](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:64) · [synchronisation des calendriers](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:187).

- Livraison locale : [rapport C07](../REMEDIATION_C07_2026-10-21.md) et [preuves](C07_VALIDATION.json). T11/T15 et recette graphique/production restent ouverts.

### M05-03

**Une série partiellement renseignée perd ses valeurs lors de la préparation d’un brouillon Product**

- Priorité d'audit : **P2** ; chantier principal : **[C07](DEPENDENCIES_AND_VALIDATION.md#c07)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m05-03).
- Validation : **V-M05-03 — validée localement sur le périmètre C07**.

**Critère de validation :** Préparer un brouillon avec [8,vide,12] conserve 8 et 12 et identifie la cellule absente ; aucune conversion globale en null ; le booking incomplet est refusé.

**Points d'entrée de l'audit :** [Préparation des paramètres](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:553) · [construction des termes](C:/Users/admin/GitHub/structura/backend/app/core/product/inputs.py:22).

- Livraison locale : [rapport C07](../REMEDIATION_C07_2026-10-21.md) et [preuves](C07_VALIDATION.json). T11/T15 et recette graphique/production restent ouverts.

### M05-04

**Le chargement d’une configuration peut laisser une session partiellement remplacée**

- Priorité d'audit : **P2** ; chantier principal : **[C07](DEPENDENCIES_AND_VALIDATION.md#c07)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m05-04).
- Validation : **V-M05-04 — validée localement sur le périmètre C07**.

**Critère de validation :** Un JSON invalide ou un parsing négatif laisse la session antérieure intacte ; seule une configuration validée remplace atomiquement script, dates, panier et hypothèses.

**Points d'entrée de l'audit :** [Chargement](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:2871) · [application depuis l’interface](C:/Users/admin/GitHub/structura/frontend/src/components/PayScriptConfigurations.vue:64).

- Livraison locale : [rapport C07](../REMEDIATION_C07_2026-10-21.md) et [preuves](C07_VALIDATION.json). T11/T15 et recette graphique/production restent ouverts.

### M05-05

**L’application d’une configuration remplace davantage d’hypothèses que ne le montre l’aperçu**

- Priorité d'audit : **P2** ; chantier principal : **[C07](DEPENDENCIES_AND_VALIDATION.md#c07)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m05-05).
- Validation : **V-M05-05 — validée localement sur le périmètre C07**.

**Critère de validation :** L'aperçu annonce tous les changements de devise, taux, courbes, funding et modèle ; appliquer seulement les termes ne remplace pas le marché si cette portée n'est pas choisie.

**Points d'entrée de l'audit :** [Contenu sauvegardé](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:2936) · [aperçu présenté](C:/Users/admin/GitHub/structura/frontend/src/components/PayScriptConfigurations.vue:14).

- Livraison locale : [rapport C07](../REMEDIATION_C07_2026-10-21.md) et [preuves](C07_VALIDATION.json). T11/T15 et recette graphique/production restent ouverts.

### M05-06

**Les dates affichées à côté des paramètres par observation peuvent correspondre au mauvais calendrier**

- Priorité d'audit : **P2** ; chantier principal : **[C05](DEPENDENCIES_AND_VALIDATION.md#c05)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m05-06).
- Validation : **V-M05-06 — validée localement sur le périmètre C05**.

**Critère de validation :** Coupons trimestriels et rappels annuels : chaque série PARAM() affiche les dates de son calendrier d'utilisation, sans mélanger la première observation trimestrielle et la première annuelle.

**Points d'entrée de l'audit :** [Annotation des lignes](C:/Users/admin/GitHub/structura/frontend/src/components/EconomicsTab.vue:136) · [agrégation des dates](C:/Users/admin/GitHub/structura/frontend/src/composables/useObservationPreview.js:43).

Livraison : [rapport C05](../REMEDIATION_C05_2026-10-20.md), [preuves ciblées](C05_VALIDATION.json). Qualification transverse et production encore ouvertes.


### M05-07

**L’aperçu des observations peut revenir à un ancien calendrier**

- Priorité d'audit : **P2** ; chantier principal : **[C10](DEPENDENCIES_AND_VALIDATION.md#c10)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m05-07).
- Validation : **V-M05-07 — validé localement le 21/10/2026**.

**Critère de validation :** Retarder l'ancienne réponse puis changer dates ou devise : seul le calendrier courant s'affiche ; un échec ne reprend pas les flux d'un ancien prix comme calendrier valide.

**Points d'entrée de l'audit :** [Chargement et dépendances de l’aperçu](C:/Users/admin/GitHub/structura/frontend/src/composables/useObservationPreview.js:43).

**Remédiation C10 :** [rapport](../REMEDIATION_C10_2026-10-21.md) et [preuves ciblées](C10_VALIDATION.json). T11/C17 et recette graphique/production restent ouverts.

### M05-08

**Certains contrôles de l’assistant affichent une assurance économique excessive**

- Priorité d'audit : **P2** ; chantier principal : **[C09](DEPENDENCIES_AND_VALIDATION.md#c09)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m05-08).
- Validation : **V-M05-08 — validé localement le 21/10/2026**.

**Critère de validation :** Une variable MEMO inutilisée ne suffit pas à qualifier la mémoire ; trajectoires coupon manqué/rattrapé/remise à zéro/rappel/maturité vérifient le payoff reconnu, sinon l'interface annonce un indice structurel.

**Points d'entrée de l'audit :** [Contrôles structurels](C:/Users/admin/GitHub/structura/backend/app/services/llm/validate.py:130).

**Remédiation C09 :** [rapport](../REMEDIATION_C09_2026-10-21.md) et [preuves ciblées](C09_VALIDATION.json). Les recettes T03/C14 et T15/C19/C20 restent partielles.

## M06

**Pricer et moteur quantitatif**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M06-01](#m06-01) | P1 | [C15](DEPENDENCIES_AND_VALIDATION.md#c15) | Sous taux stochastiques, le funding contamine le drift et est compté deux fois dans l’actualisation |
| [M06-02](#m06-02) | P1 | [C15](DEPENDENCIES_AND_VALIDATION.md#c15) | En mono-sous-jacent, la corrélation taux/action gonfle la variance du spot |
| [M06-03](#m06-03) | P1 | [C16](DEPENDENCIES_AND_VALIDATION.md#c16) | Le pont brownien ne conserve pas la dépendance des extrema entre actifs |
| [M06-04](#m06-04) | P1 | [C15](DEPENDENCIES_AND_VALIDATION.md#c15) | Hull-White devient numériquement instable lorsque le retour à la moyenne approche zéro |
| [M06-05](#m06-05) | P1 | [C14](DEPENDENCIES_AND_VALIDATION.md#c14) | Deux dates contractuelles rapprochées peuvent être exécutées hors ordre chronologique |
| [M06-06](#m06-06) | P2 | [C14](DEPENDENCIES_AND_VALIDATION.md#c14) | Les analyses annexes n’utilisent pas toujours le même horizon que le prix |
| [M06-07](#m06-07) | P2 | [C18](DEPENDENCIES_AND_VALIDATION.md#c18) | Les probabilités et les trajectoires peuvent décrire d’autres hypothèses que celles du prix affiché |
| [M06-08](#m06-08) | P2 | [C18](DEPENDENCIES_AND_VALIDATION.md#c18) | Plusieurs conventions des Greeks restent incohérentes |
| [M06-09](#m06-09) | P2 | [C18](DEPENDENCIES_AND_VALIDATION.md#c18) | Certaines statistiques sont affichées avec une interprétation économique incorrecte |

### M06-01

**Sous taux stochastiques, le funding contamine le drift et est compté deux fois dans l’actualisation**

- Priorité d'audit : **P1** ; chantier principal : **[C15](DEPENDENCIES_AND_VALIDATION.md#c15)** ; lot principal : **4**.
- Statut : **Corrigé localement — tests ciblés validés, 21/10/2026**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m06-01).
- Validation : **V-M06-01 — réussie sur le périmètre C15** ; [rapport](../REMEDIATION_C15_2026-10-21.md), [preuves](C15_VALIDATION.json). T06 partiel et qualification D04 restante.

**Critère de validation :** Sur PAY 1 à un an, r=3 % et funding=2 %, la limite de volatilité des taux vers zéro rejoint exp(-0,05)=0,951229 ; funding appliqué une fois et absent du drift ; couvrir courbes et branches supportées.

**Points d'entrée de l'audit :** [Branche concernée](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2333).

### M06-02

**En mono-sous-jacent, la corrélation taux/action gonfle la variance du spot**

- Priorité d'audit : **P1** ; chantier principal : **[C15](DEPENDENCIES_AND_VALIDATION.md#c15)** ; lot principal : **4**.
- Statut : **Corrigé localement — tests ciblés validés, 21/10/2026**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m06-02).
- Validation : **V-M06-02 — réussie sur le périmètre C15** ; [rapport](../REMEDIATION_C15_2026-10-21.md), [preuves](C15_VALIDATION.json). T06 partiel et qualification D04 restante.

**Critère de validation :** En mono, modifier rho_rS conserve la variance demandée et produit la corrélation réalisée attendue ; un forward prépayé reste compatible avec sa martingale sur réplications indépendantes.

**Points d'entrée de l'audit :** [Traitement mono-sous-jacent](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:429).

### M06-03

**Le pont brownien ne conserve pas la dépendance des extrema entre actifs**

- Priorité d'audit : **P1** ; chantier principal : **[C16](DEPENDENCIES_AND_VALIDATION.md#c16)** ; lot principal : **4**.
- Statut : **Corrigé localement — domaine qualifié restreint et refus explicites, 21/10/2026**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m06-03).
- Validation : **V-M06-03 — réussie sur le domaine local C16** ; [rapport](../REMEDIATION_C16_2026-10-21.md), [preuves](C16_VALIDATION.json). T07 partiel et extension D04/C18 restante.

**Critère de validation :** Deux actifs identiques corrélés à 1 produisent le même franchissement que le mono ; vérifier extrema et payoff complet, puis qualifier le cas de corrélation imparfaite.

**Points d'entrée de l'audit :** [Pont brownien](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:857).

### M06-04

**Hull-White devient numériquement instable lorsque le retour à la moyenne approche zéro**

- Priorité d'audit : **P1** ; chantier principal : **[C15](DEPENDENCIES_AND_VALIDATION.md#c15)** ; lot principal : **4**.
- Statut : **Corrigé localement — tests ciblés validés, 21/10/2026**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m06-04).
- Validation : **V-M06-04 — réussie sur le périmètre C15** ; [rapport](../REMEDIATION_C15_2026-10-21.md), [preuves](C15_VALIDATION.json). T06 partiel et qualification D04 restante.

**Critère de validation :** Tester a_r=0, 1e-4, 1e-6 et 1e-8 : facteurs et résultats finis et continus vers la limite analytique ; couvrir une maturité courte et longue sans prix arbitrairement explosif.

**Points d'entrée de l'audit :** [Correction de convexité](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:984).

### M06-05

**Deux dates contractuelles rapprochées peuvent être exécutées hors ordre chronologique**

- Priorité d'audit : **P1** ; chantier principal : **[C14](DEPENDENCIES_AND_VALIDATION.md#c14)** ; lot principal : **4**.
- Statut : **Ouvert — à revalider avant correction**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m06-05).
- Validation : **V-M06-05 — à préparer, non exécutée au lot 0**.

**Critère de validation :** Événements 31/01 et 01/02 exécutés selon leurs dates même sur le même pas de diffusion ; inverser l'ordre des blocs ne change ni mémoire ni paiement ; convention de simultanéité explicite.

**Points d'entrée de l'audit :** [Regroupement sur la grille](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2231).

### M06-06

**Les analyses annexes n’utilisent pas toujours le même horizon que le prix**

- Priorité d'audit : **P2** ; chantier principal : **[C14](DEPENDENCIES_AND_VALIDATION.md#c14)** ; lot principal : **4**.
- Statut : **Ouvert — à revalider avant correction**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m06-06).
- Validation : **V-M06-06 — à préparer, non exécutée au lot 0**.

**Critère de validation :** Sur un horizon d'un jour, prix/probabilités/trajectoires s'arrêtent au jour demandé ; le digital déterministe garde la même décision ; REALVOL utilise une annualisation cohérente.

**Points d'entrée de l'audit :** [Trajectoires](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:3070) · [probabilités](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:3208) · [REALVOL terminal](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:1838).

### M06-07

**Les probabilités et les trajectoires peuvent décrire d’autres hypothèses que celles du prix affiché**

- Priorité d'audit : **P2** ; chantier principal : **[C18](DEPENDENCIES_AND_VALIDATION.md#c18)** ; lot principal : **5**.
- Statut : **Corrigé localement — contexte partagé, conventions et sources explicites**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m06-07).
- Validation : **V-M06-07 — validée localement sur le périmètre C18**.

**Critère de validation :** Mêmes inputs actifs et conventions donnent le même centre de valorisation pour prix et probabilités ; courbes transportées aux trajectoires ; toute simplification supportée est visible et référencée.

**Points d'entrée de l'audit :** [Appel des trajectoires](C:/Users/admin/GitHub/structura/backend/app/api/pricing.py:342) · [appel des probabilités](C:/Users/admin/GitHub/structura/backend/app/api/pricing.py:398).

Livraison : [rapport C18](../REMEDIATION_C18_2026-10-21.md), [preuves ciblées](C18_VALIDATION.json). Domaines C15–C17 conservés ; recette graphique et scénarios transverses dépendants restants.


### M06-08

**Plusieurs conventions des Greeks restent incohérentes**

- Priorité d'audit : **P2** ; chantier principal : **[C18](DEPENDENCIES_AND_VALIDATION.md#c18)** ; lot principal : **5**.
- Statut : **Corrigé localement — contexte partagé, conventions et sources explicites**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m06-08).
- Validation : **V-M06-08 — validée localement sur le périmètre C18**.

**Critère de validation :** Près de rho=1, utiliser amplitude et sens de bump réellement admissibles ; antithétiques identiques à la base ; vega LSV porte une définition et une couverture conformes à son effet effectif.

**Points d'entrée de l'audit :** [Greeks et métadonnées](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2693) · [appel API](C:/Users/admin/GitHub/structura/backend/app/api/pricing.py:182).

Livraison : [rapport C18](../REMEDIATION_C18_2026-10-21.md), [preuves ciblées](C18_VALIDATION.json). Domaines C15–C17 conservés ; recette graphique et scénarios transverses dépendants restants.


### M06-09

**Certaines statistiques sont affichées avec une interprétation économique incorrecte**

- Priorité d'audit : **P2** ; chantier principal : **[C18](DEPENDENCIES_AND_VALIDATION.md#c18)** ; lot principal : **5**.
- Statut : **Corrigé localement — contexte partagé, conventions et sources explicites**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m06-09).
- Validation : **V-M06-09 — validée localement sur le périmètre C18**.

**Critère de validation :** Une option certainement payante à 10 % n'est pas annoncée 100 % OTM ; sous-pair, ITM, perte et quantile actualisé sont distincts ; la valeur numérique et son aide décrivent la même métrique.

**Points d'entrée de l'audit :** [Classification affichée](C:/Users/admin/GitHub/structura/frontend/src/components/ProbaTab.vue:155) · [tuile de quantile](C:/Users/admin/GitHub/structura/frontend/src/components/ResultsPanel.vue:111).

## M07

**Surfaces et calibration**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M07-01](#m07-01) | P1 | [C17](DEPENDENCIES_AND_VALIDATION.md#c17) | Une modification matérielle de la matrice peut être complètement invisible pour la calibration |
| [M07-02](#m07-02) | P1 | [C10](DEPENDENCIES_AND_VALIDATION.md#c10) | Une calibration peut être acceptée alors que le contexte de pricing a changé |
| [M07-03](#m07-03) | P1 | [C17](DEPENDENCIES_AND_VALIDATION.md#c17) | L’ancien chemin Local Vol accepte encore des smiles invalides et utilise une valeur de repli |
| [M07-04](#m07-04) | P2 | [C17](DEPENDENCIES_AND_VALIDATION.md#c17) | « Optimisation terminée » et « calibration acceptable » restent insuffisamment séparées |
| [M07-05](#m07-05) | P2 | [C17](DEPENDENCIES_AND_VALIDATION.md#c17) | L’intégration Fourier Heston manque de contrôles dans certains régimes |
| [M07-06](#m07-06) | P2 | [C17](DEPENDENCIES_AND_VALIDATION.md#c17) | La preuve de pricing ne conserve pas le dossier de calibration |
| [M07-07](#m07-07) | P2 | [C07](DEPENDENCIES_AND_VALIDATION.md#c07) | Vider un champ de forme peut modifier matériellement le smile |

Livraison : [rapport C18](../REMEDIATION_C18_2026-10-21.md), [preuves ciblées](C18_VALIDATION.json). Domaines C15–C17 conservés ; recette graphique et scénarios transverses dépendants restants.


### M07-01

**Une modification matérielle de la matrice peut être complètement invisible pour la calibration**

- Priorité d'audit : **P1** ; chantier principal : **[C17](DEPENDENCIES_AND_VALIDATION.md#c17)** ; lot principal : **4**.
- Statut : **Corrigé localement — contrôles, traçabilité et refus explicites**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m07-01).
- Validation : **V-M07-01 — validée localement sur le périmètre C17**.

**Critère de validation :** Modifier un pilier ATM 7 ans matériel sur cible 10 ans change l'objectif ou est déclaré hors couverture ; paramètres et résidus ne restent pas faussement identiques ; publier grille et points hors ajustement.

**Points d'entrée de l'audit :** [Grille de calibration](C:/Users/admin/GitHub/structura/backend/app/core/smile_calibration.py:37).

Livraison : [rapport C17](../REMEDIATION_C17_2026-10-21.md), [preuves ciblées](C17_VALIDATION.json). Qualification aux points publiés, domaines hors couverture refusés ; recette graphique et production restantes.


### M07-02

**Une calibration peut être acceptée alors que le contexte de pricing a changé**

- Priorité d'audit : **P1** ; chantier principal : **[C10](DEPENDENCIES_AND_VALIDATION.md#c10)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m07-02).
- Validation : **V-M07-02 — validé localement le 21/10/2026**.

**Critère de validation :** Lancer calibration à 3 %, passer à 4 % pendant l'attente : ancienne réponse ignorée ; deux demandes chevauchées ne rejettent pas la dernière à cause de la première ; contexte vérifié avant pricing.

**Points d'entrée de l'audit :** [Application des résultats](C:/Users/admin/GitHub/structura/frontend/src/utils/smileCalibration.js:5) · [préparation du pricing](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:1003).

**Remédiation C10 :** [rapport](../REMEDIATION_C10_2026-10-21.md) et [preuves ciblées](C10_VALIDATION.json). T11/C17 et recette graphique/production restent ouverts.

### M07-03

**L’ancien chemin Local Vol accepte encore des smiles invalides et utilise une valeur de repli**

- Priorité d'audit : **P1** ; chantier principal : **[C17](DEPENDENCIES_AND_VALIDATION.md#c17)** ; lot principal : **4**.
- Statut : **Corrigé localement — contrôles, traçabilité et refus explicites**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m07-03).
- Validation : **V-M07-03 — validée localement sur le périmètre C17**.

**Critère de validation :** Un smile historique de densité invalide est refusé ou explicitement limité sans substitution silencieuse d'IV ; les anciens dossiers restent lisibles sans migration cachée de leurs hypothèses.

**Points d'entrée de l'audit :** [Inversion historique et replis](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:238).

Livraison : [rapport C17](../REMEDIATION_C17_2026-10-21.md), [preuves ciblées](C17_VALIDATION.json). Qualification aux points publiés, domaines hors couverture refusés ; recette graphique et production restantes.


### M07-04

**« Optimisation terminée » et « calibration acceptable » restent insuffisamment séparées**

- Priorité d'audit : **P2** ; chantier principal : **[C17](DEPENDENCIES_AND_VALIDATION.md#c17)** ; lot principal : **4**.
- Statut : **Corrigé localement — contrôles, traçabilité et refus explicites**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m07-04).
- Validation : **V-M07-04 — validée localement sur le périmètre C17**.

**Critère de validation :** success=false ne donne pas un statut qualifié ; success=true avec résidu matériel reste soumis aux seuils de vanilles et digitaux définis par usage ; exploration et exploitation sont distinguées.

**Points d'entrée de l'audit :** [Résultat d’optimisation](C:/Users/admin/GitHub/structura/backend/app/core/smile_calibration.py:85) · [statut frontend](C:/Users/admin/GitHub/structura/frontend/src/utils/smileCalibration.js:24).

Livraison : [rapport C17](../REMEDIATION_C17_2026-10-21.md), [preuves ciblées](C17_VALIDATION.json). Qualification aux points publiés, domaines hors couverture refusés ; recette graphique et production restantes.


### M07-05

**L’intégration Fourier Heston manque de contrôles dans certains régimes**

- Priorité d'audit : **P2** ; chantier principal : **[C17](DEPENDENCIES_AND_VALIDATION.md#c17)** ; lot principal : **4**.
- Statut : **Corrigé localement — contrôles, traçabilité et refus explicites**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m07-05).
- Validation : **V-M07-05 — validée localement sur le périmètre C17**.

**Critère de validation :** En faible variance et ailes lointaines, prix Heston non négatifs, bornés et stables à l'extension du domaine et à la précision ; comparer une référence indépendante et contrôler monotonie/convexité.

**Points d'entrée de l'audit :** [Évaluation Fourier](C:/Users/admin/GitHub/structura/backend/app/core/smile_calibration.py:13).

Livraison : [rapport C17](../REMEDIATION_C17_2026-10-21.md), [preuves ciblées](C17_VALIDATION.json). Qualification aux points publiés, domaines hors couverture refusés ; recette graphique et production restantes.


### M07-06

**La preuve de pricing ne conserve pas le dossier de calibration**

- Priorité d'audit : **P2** ; chantier principal : **[C17](DEPENDENCIES_AND_VALIDATION.md#c17)** ; lot principal : **4**.
- Statut : **Corrigé localement — contrôles, traçabilité et refus explicites**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m07-06).
- Validation : **V-M07-06 — validée localement sur le périmètre C17**.

**Critère de validation :** Le calcul conservé référence cible, inputs, grille, pondérations, méthode/version, paramètres, convergence et résidus ; sa preuve serveur survit à la fermeture du navigateur.

**Points d'entrée de l'audit :** [Paramètres transmis au moteur](C:/Users/admin/GitHub/structura/frontend/src/stores/pricing.js:613) · [preuve de pricing](C:/Users/admin/GitHub/structura/backend/app/core/valuation_context.py:301).

Livraison : [rapport C17](../REMEDIATION_C17_2026-10-21.md), [preuves ciblées](C17_VALIDATION.json). Qualification aux points publiés, domaines hors couverture refusés ; recette graphique et production restantes.


### M07-07

**Vider un champ de forme peut modifier matériellement le smile**

- Priorité d'audit : **P2** ; chantier principal : **[C07](DEPENDENCIES_AND_VALIDATION.md#c07)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m07-07).
- Validation : **V-M07-07 — validée localement sur le périmètre C07**.

**Critère de validation :** Vider un champ d'intensité ou d'asymétrie ne devient pas un zéro appliqué ; saisir explicitement zéro reste possible s'il est valide ; conserver la dernière valeur ou bloquer clairement.

**Points d'entrée de l'audit :** [Conversion des champs](C:/Users/admin/GitHub/structura/frontend/src/components/VolSurfaceEditor.vue:24).

- Livraison locale : [rapport C07](../REMEDIATION_C07_2026-10-21.md) et [preuves](C07_VALIDATION.json). T11/T15 et recette graphique/production restent ouverts.

## M08

**Product Optimizer**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M08-01](#m08-01) | P1 | [C20](DEPENDENCIES_AND_VALIDATION.md#c20) | Deux modes ne peuvent pas être lancés depuis le parcours sauvegardé |
| [M08-02](#m08-02) | P2 | [C20](DEPENDENCIES_AND_VALIDATION.md#c20) | Le plafond du solveur écarte des structures finançables |
| [M08-03](#m08-03) | P2 | [C09](DEPENDENCIES_AND_VALIDATION.md#c09) | La qualification d’une famille ne protège pas suffisamment ses hypothèses économiques |
| [M08-04](#m08-04) | P2 | [C19](DEPENDENCIES_AND_VALIDATION.md#c19) | L’immutabilité SQL des résultats terminaux est contournable |
| [M08-05](#m08-05) | P2 | [C20](DEPENDENCIES_AND_VALIDATION.md#c20) | Le budget temps maximal n’est pas garanti en séquentiel |
| [M08-06](#m08-06) | P2 | [C07](DEPENDENCIES_AND_VALIDATION.md#c07) | La reprise peut rendre invalide un dossier initialement valide |
| [M08-07](#m08-07) | P3 | [C20](DEPENDENCIES_AND_VALIDATION.md#c20) | Un avertissement contredit la sauvegarde automatique |

### M08-01

**Deux modes ne peuvent pas être lancés depuis le parcours sauvegardé**

- Priorité d'audit : **P1** ; chantier principal : **[C20](DEPENDENCIES_AND_VALIDATION.md#c20)** ; lot principal : **7**.
- Statut : **Corrigé localement — C20 validé, budget souple explicite**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m08-01).
- Validation : **V-M08-01 — validé localement le 22/10/2026**.

**Critère de validation :** Sauvegarder puis lancer chaque famille/objectif proposé, dont Athena dégressif et booster cap maximal ; aucun AttributeError ; résumé et réglages conservés correspondent à la demande.

**Points d'entrée de l'audit :** [Ligne concernée](C:/Users/admin/GitHub/structura/backend/app/services/optimizer_research.py:90).

**Remédiation C20 :** [rapport](../REMEDIATION_C20_2026-10-22.md), [preuves](C20_VALIDATION.json). Aucun seuil économique ni archive ancienne modifiés.

### M08-02

**Le plafond du solveur écarte des structures finançables**

- Priorité d'audit : **P2** ; chantier principal : **[C20](DEPENDENCIES_AND_VALIDATION.md#c20)** ; lot principal : **7**.
- Statut : **Corrigé localement — C20 validé, budget souple explicite**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m08-02).
- Validation : **V-M08-02 — validé localement le 22/10/2026**.

**Critère de validation :** Le cas RC 48 mois publié ne doit pas être exclu pour une itération manquante quand le résidu économique est admissible ; dimensionner la résolution selon bornes/tolérance et vérifier le prix après arrondi.

**Points d'entrée de l'audit :** [Appel du solveur](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/service.py:150).

**Remédiation C20 :** [rapport](../REMEDIATION_C20_2026-10-22.md), [preuves](C20_VALIDATION.json). Aucun seuil économique ni archive ancienne modifiés.

### M08-03

**La qualification d’une famille ne protège pas suffisamment ses hypothèses économiques**

- Priorité d'audit : **P2** ; chantier principal : **[C09](DEPENDENCIES_AND_VALIDATION.md#c09)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m08-03).
- Validation : **V-M08-03 — validé localement le 21/10/2026**.

**Critère de validation :** Changer le coupon approuvé en expression non linéaire invalide l'adaptateur affine ou change sa qualification ; les trajectoires de référence et l'empreinte du payoff sont liées au diagnostic.

**Points d'entrée de l'audit :** [Qualification](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/families.py:70) · [diagnostic du paramètre](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/validation.py:17).

**Remédiation C09 :** [rapport](../REMEDIATION_C09_2026-10-21.md) et [preuves ciblées](C09_VALIDATION.json). Les recettes T03/C14 et T15/C19/C20 restent partielles.

### M08-04

**L’immutabilité SQL des résultats terminaux est contournable**

- Priorité d'audit : **P2** ; chantier principal : **[C19](DEPENDENCIES_AND_VALIDATION.md#c19)** ; lot principal : **5**.
- Statut : **Corrigé localement — archives et rejeu C19 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m08-04).
- Validation : **V-M08-04 — validé localement le 21/10/2026**.

**Critère de validation :** Sur une recherche terminale, UPDATE direct, passage à NULL puis remplacement et suppression de preuve sont refusés selon la politique ; migration et nouveau schéma installent les mêmes protections.

**Points d'entrée de l'audit :** [Déclencheur](C:/Users/admin/GitHub/structura/backend/app/services/optimizer_research.py:26) · [colonnes](C:/Users/admin/GitHub/structura/backend/app/db/models.py:95).

**Remédiation C19 :** [rapport](../REMEDIATION_C19_2026-10-21.md), [preuves](C19_VALIDATION.json). D10/D11 confirmées ; aucune qualification de production.

### M08-05

**Le budget temps maximal n’est pas garanti en séquentiel**

- Priorité d'audit : **P2** ; chantier principal : **[C20](DEPENDENCIES_AND_VALIDATION.md#c20)** ; lot principal : **7**.
- Statut : **Corrigé localement — C20 validé, budget souple explicite**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m08-05).
- Validation : **V-M08-05 — validé localement le 22/10/2026**.

**Critère de validation :** Un calcul franchissant le budget est interrompu ou déclaré explicitement dépassement/partiel ; le résultat ne reste pas complete=true sans motif ; couvrir exécution séquentielle et multiprocessus.

**Points d'entrée de l'audit :** [Contrôles d’arrêt](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/service.py:274) · [statut final](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/service.py:385).

**Remédiation C20 :** [rapport](../REMEDIATION_C20_2026-10-22.md), [preuves](C20_VALIDATION.json). Aucun seuil économique ni archive ancienne modifiés.

### M08-06

**La reprise peut rendre invalide un dossier initialement valide**

- Priorité d'audit : **P2** ; chantier principal : **[C07](DEPENDENCIES_AND_VALIDATION.md#c07)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m08-06).
- Validation : **V-M08-06 — validée localement sur le périmètre C07**.

**Critère de validation :** Reprendre q=2,001 % et premier bucket=2,001 % conserve la précision envoyée ; l'arrondi affiché ne crée pas une divergence ou un rejet ; distinguer une vraie modification utilisateur.

**Points d'entrée de l'audit :** [Reprise](C:/Users/admin/GitHub/structura/frontend/src/utils/optimizerResume.js:6).

- Livraison locale : [rapport C07](../REMEDIATION_C07_2026-10-21.md) et [preuves](C07_VALIDATION.json). T11/T15 et recette graphique/production restent ouverts.

### M08-07

**Un avertissement contredit la sauvegarde automatique**

- Priorité d'audit : **P3** ; chantier principal : **[C20](DEPENDENCIES_AND_VALIDATION.md#c20)** ; lot principal : **7**.
- Statut : **Corrigé localement — C20 validé, budget souple explicite**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m08-07).
- Validation : **V-M08-07 — validé localement le 22/10/2026**.

**Critère de validation :** Les messages des capacités, de la page et des résultats sauvegardés décrivent correctement la persistance, la reprise et leurs limites ; aucun conseil d'export ne prétend la sauvegarde inexistante.

**Points d'entrée de l'audit :** [Avertissement](C:/Users/admin/GitHub/structura/backend/app/core/product_optimizer/capabilities.py:29).

## M09

**RFQ fournisseurs et cotations**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M09-01](#m09-01) | P1 | [C06](DEPENDENCIES_AND_VALIDATION.md#c06) | Le gel contractuel peut être contourné dans la copie RFQ par `pricing_params` |
| [M09-02](#m09-02) | P2 | [C23](DEPENDENCIES_AND_VALIDATION.md#c23) | L’analyse historique écarte les réponses réseau après leur traitement |
| [M09-03](#m09-03) | P2 | [C23](DEPENDENCIES_AND_VALIDATION.md#c23) | Les modifications des réponses manuelles ne réévaluent pas suffisamment la décision |
| [M09-04](#m09-04) | P2 | [C23](DEPENDENCIES_AND_VALIDATION.md#c23) | Une réponse dans une autre devise peut être comparable et sélectionnée |
| [M09-05](#m09-05) | P2 | [C19](DEPENDENCIES_AND_VALIDATION.md#c19) | La référence modèle historique reste mutable et insuffisamment documentée |
| [M09-06](#m09-06) | P2 | [C10](DEPENDENCIES_AND_VALIDATION.md#c10) | Le panneau de contrôle peut afficher un ancien calcul face au nouveau prix serveur |
| [M09-07](#m09-07) | P2 | [C23](DEPENDENCIES_AND_VALIDATION.md#c23) | Le graphique écrase les cotations d’un même fournisseur le même jour |
| [M09-08](#m09-08) | P2 | [C23](DEPENDENCIES_AND_VALIDATION.md#c23) | La cohérence des horaires n’est contrôlée que dans un sens |
| [M09-09](#m09-09) | P2 | [C10](DEPENDENCIES_AND_VALIDATION.md#c10) | Plusieurs refus de mise à jour ne sont pas restitués dans l’écran |

**Remédiation C20 :** [rapport](../REMEDIATION_C20_2026-10-22.md), [preuves](C20_VALIDATION.json). Aucun seuil économique ni archive ancienne modifiés.

### M09-01

**Le gel contractuel peut être contourné dans la copie RFQ par `pricing_params`**

- Priorité d'audit : **P1** ; chantier principal : **[C06](DEPENDENCIES_AND_VALIDATION.md#c06)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m09-01).
- Validation : **V-M09-01 — validée localement sur le périmètre C06**.

**Critère de validation :** Après sollicitation, tenter payment_date, maturity_date et frozen_schedule via pricing_params est refusé sans mutation de la copie RFQ ni du Product ; les seules hypothèses de marché autorisées restent modifiables.

**Points d'entrée de l'audit :** [Fusion concernée](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:591).

Livraison : [rapport C06](../REMEDIATION_C06_2026-10-20.md), [preuves ciblées](C06_VALIDATION.json). Qualification transverse et production restantes.

### M09-02

**L’analyse historique écarte les réponses réseau après leur traitement**

- Priorité d'audit : **P2** ; chantier principal : **[C23](DEPENDENCIES_AND_VALIDATION.md#c23)** ; lot principal : **6**.
- Statut : **Corrigé localement — cotations et tours C23 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m09-02).
- Validation : **V-M09-02 — validé localement le 22/10/2026**.

**Critère de validation :** Une quote réseau gagnante RESERVED/ROUND_CLOSED reste dans les statistiques historiques de son tour ; les quotes actuellement sélectionnables restent filtrées séparément.

**Points d'entrée de l'audit :** [Filtre historique](C:/Users/admin/GitHub/structura/frontend/src/views/RfqAnalysisView.vue:160) · [états de publication](C:/Users/admin/GitHub/structura/backend/app/services/rfq_publication.py:110).

**Remédiation C23 :** [rapport](../REMEDIATION_C23_2026-10-22.md), [preuves](C23_VALIDATION.json). C08 global, recette graphique et qualification déployée restent ouverts.

### M09-03

**Les modifications des réponses manuelles ne réévaluent pas suffisamment la décision**

- Priorité d'audit : **P2** ; chantier principal : **[C23](DEPENDENCIES_AND_VALIDATION.md#c23)** ; lot principal : **6**.
- Statut : **Corrigé localement — cotations et tours C23 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m09-03).
- Validation : **V-M09-03 — validé localement le 22/10/2026**.

**Critère de validation :** Modifier une réponse retenue crée une révision et invalide la décision attachée à l'ancienne révision ; améliorer l'originale remplace/requalifie son last look de façon cohérente.

**Points d'entrée de l'audit :** [Mise à jour des cotations](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1959).

**Remédiation C23 :** [rapport](../REMEDIATION_C23_2026-10-22.md), [preuves](C23_VALIDATION.json). C08 global, recette graphique et qualification déployée restent ouverts.

### M09-04

**Une réponse dans une autre devise peut être comparable et sélectionnée**

- Priorité d'audit : **P2** ; chantier principal : **[C23](DEPENDENCIES_AND_VALIDATION.md#c23)** ; lot principal : **6**.
- Statut : **Corrigé localement — cotations et tours C23 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m09-04).
- Validation : **V-M09-04 — validé localement le 22/10/2026**.

**Critère de validation :** RFQ EUR et réponse USD ne sont pas sélectionnables comme termes identiques ; absence de devise reprend explicitement EUR ; une contre-proposition change les termes selon le workflow retenu.

**Points d'entrée de l'audit :** [Comparabilité](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:411).

**Remédiation C23 :** [rapport](../REMEDIATION_C23_2026-10-22.md), [preuves](C23_VALIDATION.json). C08 global, recette graphique et qualification déployée restent ouverts.

### M09-05

**La référence modèle historique reste mutable et insuffisamment documentée**

- Priorité d'audit : **P2** ; chantier principal : **[C19](DEPENDENCIES_AND_VALIDATION.md#c19)** ; lot principal : **5**.
- Statut : **Corrigé localement — archives et rejeu C19 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m09-05).
- Validation : **V-M09-05 — validé localement le 21/10/2026**.

**Critère de validation :** Chaque écart historique référence le modèle daté retenu à cet instant ; changer un modèle courant ne réécrit pas le passé ; un prix scalaire non prouvé n'est pas marqué calcul moteur vérifié.

**Points d'entrée de l'audit :** [Historique](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1100) · [enregistrement du prix](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1723).

**Remédiation C19 :** [rapport](../REMEDIATION_C19_2026-10-21.md), [preuves](C19_VALIDATION.json). D10/D11 confirmées ; aucune qualification de production.

### M09-06

**Le panneau de contrôle peut afficher un ancien calcul face au nouveau prix serveur**

- Priorité d'audit : **P2** ; chantier principal : **[C10](DEPENDENCIES_AND_VALIDATION.md#c10)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m09-06).
- Validation : **V-M09-06 — validé localement le 21/10/2026**.

**Critère de validation :** Recharger la même RFQ avec prix 105 invalide un détail à 100 ; référence de calcul, empreinte et intervalle de confiance appartiennent au même résultat.

**Points d'entrée de l'audit :** [Rechargement du dossier](C:/Users/admin/GitHub/structura/frontend/src/stores/rfq.js:50).

**Remédiation C10 :** [rapport](../REMEDIATION_C10_2026-10-21.md) et [preuves ciblées](C10_VALIDATION.json). T11/C17 et recette graphique/production restent ouverts.

### M09-07

**Le graphique écrase les cotations d’un même fournisseur le même jour**

- Priorité d'audit : **P2** ; chantier principal : **[C23](DEPENDENCIES_AND_VALIDATION.md#c23)** ; lot principal : **6**.
- Statut : **Corrigé localement — cotations et tours C23 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m09-07).
- Validation : **V-M09-07 — validé localement le 22/10/2026**.

**Critère de validation :** Deux écarts +100/-300 bps du même fournisseur le même jour restent deux observations ou donnent une agrégation explicite -100 bps ; inverser l'ordre des lignes ne change pas le graphique.

**Points d'entrée de l'audit :** [Construction du graphique](C:/Users/admin/GitHub/structura/frontend/src/views/RfqAnalysisView.vue:238).

**Remédiation C23 :** [rapport](../REMEDIATION_C23_2026-10-22.md), [preuves](C23_VALIDATION.json). C08 global, recette graphique et qualification déployée restent ouverts.

### M09-08

**La cohérence des horaires n’est contrôlée que dans un sens**

- Priorité d'audit : **P2** ; chantier principal : **[C23](DEPENDENCIES_AND_VALIDATION.md#c23)** ; lot principal : **6**.
- Statut : **Corrigé localement — cotations et tours C23 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m09-08).
- Validation : **V-M09-08 — validé localement le 22/10/2026**.

**Critère de validation :** Modifier seulement quoted_at après valid_until est refusé ; fusionner puis valider l'état final pour chaque chemin de mise à jour ; heure de quote et heure de saisie restent distinctes.

**Points d'entrée de l'audit :** [Contrôle chronologique](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:2001).

**Remédiation C23 :** [rapport](../REMEDIATION_C23_2026-10-22.md), [preuves](C23_VALIDATION.json). C08 global, recette graphique et qualification déployée restent ouverts.

### M09-09

**Plusieurs refus de mise à jour ne sont pas restitués dans l’écran**

- Priorité d'audit : **P2** ; chantier principal : **[C10](DEPENDENCIES_AND_VALIDATION.md#c10)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m09-09).
- Validation : **V-M09-09 — validé localement le 21/10/2026**.

**Critère de validation :** Provoquer refus de modification, ajout, suppression et sélection : message métier visible, état enregistré restauré et saisie refusée identifiable ; aucune promesse non traitée ni succès visuel indu.

**Points d'entrée de l'audit :** [Gestionnaires concernés](C:/Users/admin/GitHub/structura/frontend/src/views/RfqView.vue:2538).

**Remédiation C10 :** [rapport](../REMEDIATION_C10_2026-10-21.md) et [preuves ciblées](C10_VALIDATION.json). T11/C17 et recette graphique/production restent ouverts.

## M10

**RFQ reçues, réseau et exécutions**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M10-01](#m10-01) | P1 | [C23](DEPENDENCIES_AND_VALIDATION.md#c23) | Une réouverture locale peut réactiver une cotation alors que la banque conserve le tour fermé |
| [M10-02](#m10-02) | P1 | [C03](DEPENDENCIES_AND_VALIDATION.md#c03) | Le traitement réseau dépend du nom juridique exact fourni par la banque |
| [M10-03](#m10-03) | P2 | [C10](DEPENDENCIES_AND_VALIDATION.md#c10) | Les preuves saisies pour une RFQ restent présentes lors du passage à une autre |
| [M10-04](#m10-04) | P2 | [C10](DEPENDENCIES_AND_VALIDATION.md#c10) | Une réponse tardive de réaffectation peut remplacer le dossier actuellement affiché |
| [M10-05](#m10-05) | P2 | [C01](DEPENDENCIES_AND_VALIDATION.md#c01) | Une validation reste annoncée comme actuelle après révocation du valideur |

### M10-01

**Une réouverture locale peut réactiver une cotation alors que la banque conserve le tour fermé**

- Priorité d'audit : **P1** ; chantier principal : **[C23](DEPENDENCIES_AND_VALIDATION.md#c23)** ; lot principal : **6**.
- Statut : **Corrigé localement — cotations et tours C23 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m10-01).
- Validation : **V-M10-01 — validé localement le 22/10/2026**.

**Critère de validation :** Sur deux bases indépendantes, clore et transmettre la clôture puis rouvrir localement ne réactive aucune ancienne quote ; un nouveau tour suit un échange explicite et les deux parties convergent.

**Points d'entrée de l'audit :** [Réouverture](C:/Users/admin/GitHub/structura/backend/app/api/rfq.py:1793) · [propagation de clôture](C:/Users/admin/GitHub/structura/backend/app/services/rfq_transport.py:518) · [état des publications](C:/Users/admin/GitHub/structura/backend/app/services/rfq_publication.py:110).

**Remédiation C23 :** [rapport](../REMEDIATION_C23_2026-10-22.md), [preuves](C23_VALIDATION.json). C08 global, recette graphique et qualification déployée restent ouverts.

### M10-02

**Le traitement réseau dépend du nom juridique exact fourni par la banque**

- Priorité d'audit : **P1** ; chantier principal : **[C03](DEPENDENCIES_AND_VALIDATION.md#c03)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m10-02).
- Validation : **V-M10-02 — validée localement sur le périmètre C03**.

**Critère de validation :** Deux libellés légaux différents mais même mapping juridique local conduisent à la bonne contrepartie ; mapping absent/inactif produit un refus, sans rapprochement de nom substitutif.

**Points d'entrée de l'audit :** [Résolution juridique](C:/Users/admin/GitHub/structura/backend/app/services/rfq_execution.py:85).

- Livraison locale : [rapport C03](../REMEDIATION_C03_2026-10-20.md) et [preuves](C03_VALIDATION.json). D01 confirmée ; recettes graphique/transverse et qualification production restantes.

### M10-03

**Les preuves saisies pour une RFQ restent présentes lors du passage à une autre**

- Priorité d'audit : **P2** ; chantier principal : **[C10](DEPENDENCIES_AND_VALIDATION.md#c10)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m10-03).
- Validation : **V-M10-03 — validé localement le 21/10/2026**.

**Critère de validation :** Saisir des références et preuves sur A puis ouvrir B réinitialise le formulaire et son indicateur de complétude ; aucune preuve A ne peut confirmer B.

**Points d'entrée de l'audit :** [État du formulaire](C:/Users/admin/GitHub/structura/frontend/src/components/RfqExecutionPanel.vue:20).

**Remédiation C10 :** [rapport](../REMEDIATION_C10_2026-10-21.md) et [preuves ciblées](C10_VALIDATION.json). T11/C17 et recette graphique/production restent ouverts.

### M10-04

**Une réponse tardive de réaffectation peut remplacer le dossier actuellement affiché**

- Priorité d'audit : **P2** ; chantier principal : **[C10](DEPENDENCIES_AND_VALIDATION.md#c10)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m10-04).
- Validation : **V-M10-04 — validé localement le 21/10/2026**.

**Critère de validation :** Réaffecter A, ouvrir B et recevoir la réponse A laisse B affiché ; une réponse du contexte courant s'applique ; erreur et fermeture ne réouvrent pas le dossier précédent.

**Points d'entrée de l'audit :** [Réaffectation](C:/Users/admin/GitHub/structura/frontend/src/views/RfqInboxView.vue:82) · [application de la réponse](C:/Users/admin/GitHub/structura/frontend/src/views/RfqInboxView.vue:62).

**Remédiation C10 :** [rapport](../REMEDIATION_C10_2026-10-21.md) et [preuves ciblées](C10_VALIDATION.json). T11/C17 et recette graphique/production restent ouverts.

### M10-05

**Une validation reste annoncée comme actuelle après révocation du valideur**

- Priorité d'audit : **P2** ; chantier principal : **[C01](DEPENDENCIES_AND_VALIDATION.md#c01)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m10-05).
- Validation : **V-M10-05 — réussie localement sur le périmètre C01** ; [résultats et limites](../REMEDIATION_C01_2026-10-20.md), [preuve structurée](C01_VALIDATION.json).

**Critère de validation :** Révoquer le valideur fait perdre l'indicateur de validation actuelle selon la même règle qui bloque la publication ; une nouvelle validation habilitée fonctionne et conserve l'historique.

**Points d'entrée de l'audit :** [Indicateur exposé](C:/Users/admin/GitHub/structura/backend/app/services/rfq_publication.py:370) · [contrôle effectif](C:/Users/admin/GitHub/structura/backend/app/services/rfq_publication.py:294).

## M11

**Booking**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M11-01](#m11-01) | P1 | [C03](DEPENDENCIES_AND_VALIDATION.md#c03) | Un libellé de contrepartie non reconnu permet d’éviter le contrôle des limites |
| [M11-02](#m11-02) | P1 | [C04](DEPENDENCIES_AND_VALIDATION.md#c04) | Un amendement de nominal peut dépasser une limite bloquante |
| [M11-03](#m11-03) | P1 | [C03](DEPENDENCIES_AND_VALIDATION.md#c03) | Un amendement de contrepartie conserve l’identifiant de l’ancienne banque |
| [M11-04](#m11-04) | P1 | [C08](DEPENDENCIES_AND_VALIDATION.md#c08) | Le booking direct sans Product préexistant n’est pas idempotent |
| [M11-05](#m11-05) | P2 | [C08](DEPENDENCIES_AND_VALIDATION.md#c08) | « Booker un autre deal à partir de ce pricing » conserve le dossier déjà exécuté |
| [M11-06](#m11-06) | P2 | [C07](DEPENDENCIES_AND_VALIDATION.md#c07) | Une valeur numérique non finie provoque une exception technique |

### M11-01

**Un libellé de contrepartie non reconnu permet d’éviter le contrôle des limites**

- Priorité d'audit : **P1** ; chantier principal : **[C03](DEPENDENCIES_AND_VALIDATION.md#c03)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m11-01).
- Validation : **V-M11-01 — validée localement sur le périmètre C03**.

**Critère de validation :** Un nom inconnu, un espace final ou une banque inactive ne contourne aucune limite ; nouveau booking exige ID juridique actif ou exception explicitement autorisée et tracée, jamais une sortie silencieuse du contrôle.

**Points d'entrée de l'audit :** [Sortie du contrôle CCR](C:/Users/admin/GitHub/structura/backend/app/core/ccr/service.py:770) · [Liste proposée à l’écran](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2537) · [rattachement du Deal](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2126).

- Livraison locale : [rapport C03](../REMEDIATION_C03_2026-10-20.md) et [preuves](C03_VALIDATION.json). D01 confirmée ; recettes graphique/transverse et qualification production restantes.

### M11-02

**Un amendement de nominal peut dépasser une limite bloquante**

- Priorité d'audit : **P1** ; chantier principal : **[C04](DEPENDENCIES_AND_VALIDATION.md#c04)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m11-02).
- Validation : **V-M11-02 — validée localement sur le périmètre C04**.

**Critère de validation :** Limite nominale 1,5 M : amender 1 M à 2 M est refusé atomiquement ; autoriser 1,4 M conserve décision et nouvelle version ; couvrir aussi les limites fondées sur la mesure après requalification.

**Points d'entrée de l'audit :** [Validation de la valeur](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:990) · [application](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:3272).

- Livraison locale : [rapport C04](../REMEDIATION_C04_2026-10-20.md) et [preuves](C04_VALIDATION.json). T05 complet et qualification C21 encore ouverts.

### M11-03

**Un amendement de contrepartie conserve l’identifiant de l’ancienne banque**

- Priorité d'audit : **P1** ; chantier principal : **[C03](DEPENDENCIES_AND_VALIDATION.md#c03)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m11-03).
- Validation : **V-M11-03 — validée localement sur le périmètre C03**.

**Critère de validation :** Amender BNP→SG actualise ensemble ID juridique, libellé, Product et rattachements compatibles ; l'exposition courante suit SG et l'ancien snapshot demeure BNP ; échec de limite laisse tout inchangé.

**Points d'entrée de l'audit :** [Mise à jour du Deal](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:3331) · [projection dans le Product](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:3369).

- Livraison locale : [rapport C03](../REMEDIATION_C03_2026-10-20.md) et [preuves](C03_VALIDATION.json). D01 confirmée ; recettes graphique/transverse et qualification production restantes.

### M11-04

**Le booking direct sans Product préexistant n’est pas idempotent**

- Priorité d'audit : **P1** ; chantier principal : **[C08](DEPENDENCIES_AND_VALIDATION.md#c08)** ; lot principal : **6**.
- Statut : **Corrigé localement — commandes et filiation C08 validées**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m11-04).
- Validation : **V-M11-04 — réussie localement** ; [rapport et limites](../REMEDIATION_C08_2026-10-22.md), [preuves](C08_VALIDATION.json).

**Critère de validation :** Répéter le même booking direct sans Product préalable et le même reçu, y compris après réponse perdue, crée un seul Deal et un seul Product ; couvrir deux requêtes concurrentes.

**Points d'entrée de l'audit :** [Création interne du Product](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2044) · [entrée du booking](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2396).

### M11-05

**« Booker un autre deal à partir de ce pricing » conserve le dossier déjà exécuté**

- Priorité d'audit : **P2** ; chantier principal : **[C08](DEPENDENCIES_AND_VALIDATION.md#c08)** ; lot principal : **6**.
- Statut : **Corrigé localement — commandes et filiation C08 validées**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m11-05).
- Validation : **V-M11-05 — réussie localement** ; [rapport et limites](../REMEDIATION_C08_2026-10-22.md), [preuves](C08_VALIDATION.json).

**Critère de validation :** Booker une autre opération depuis un calcul crée un nouveau dossier sans exécution, relié à l'origine ; aucun Product déjà exécuté n'est réutilisé ; les liens RFQ/indicatif sont explicitement traités.

**Points d'entrée de l'audit :** [Réarmement](C:/Users/admin/GitHub/structura/frontend/src/components/DealTab.vue:607) · [construction de la demande](C:/Users/admin/GitHub/structura/frontend/src/components/DealTab.vue:751).

### M11-06

**Une valeur numérique non finie provoque une exception technique**

- Priorité d'audit : **P2** ; chantier principal : **[C07](DEPENDENCIES_AND_VALIDATION.md#c07)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m11-06).
- Validation : **V-M11-06 — validée localement sur le périmètre C07**.

**Critère de validation :** Nominal Infinity, NaN et valeurs non finies sont refusés avant sérialisation ; aucun Deal/Product partiel ; retour métier contrôlé et BOOKING_REJECTED pertinent conservé.

**Points d'entrée de l'audit :** [Schéma](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:83) · [contrôles économiques](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:246).

- Livraison locale : [rapport C07](../REMEDIATION_C07_2026-10-21.md) et [preuves](C07_VALIDATION.json). T11/T15 et recette graphique/production restent ouverts.

## M12

**Fixings, événements et alertes**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M12-01](#m12-01) | P1 | [C13](DEPENDENCIES_AND_VALIDATION.md#c13) | Une barre du jour peut devenir officielle avant la clôture de séance |
| [M12-02](#m12-02) | P1 | [C13](DEPENDENCIES_AND_VALIDATION.md#c13) | Une lacune du fournisseur peut déclasser un fixing déjà officiel |
| [M12-03](#m12-03) | P2 | [C26](DEPENDENCIES_AND_VALIDATION.md#c26) | La surveillance des barrières peut utiliser le mauvais observable |
| [M12-04](#m12-04) | P2 | [C26](DEPENDENCIES_AND_VALIDATION.md#c26) | Un traitement quotidien en erreur peut être journalisé comme réussi |
| [M12-05](#m12-05) | P2 | [C13](DEPENDENCIES_AND_VALIDATION.md#c13) | Une décision de fixing peut être enregistrée malgré une réponse d’échec |
| [M12-06](#m12-06) | P2 | [C10](DEPENDENCIES_AND_VALIDATION.md#c10) | Une alerte disparaît de l’écran même si son acquittement échoue |

### M12-01

**Une barre du jour peut devenir officielle avant la clôture de séance**

- Priorité d'audit : **P1** ; chantier principal : **[C13](DEPENDENCIES_AND_VALIDATION.md#c13)** ; lot principal : **3**.
- Statut : **Ouvert — à revalider avant correction**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m12-01).
- Validation : **V-M12-01 — à préparer, non exécutée au lot 0**.

**Critère de validation :** Une barre quotidienne reçue avant la fin de séance n'est pas officialisée et ne déclenche aucun rappel/coupon ; après clôture qualifiée la même date est admissible ; couvrir fuseaux et jours fériés.

**Points d'entrée de l'audit :** [Chargement](C:/Users/admin/GitHub/structura/backend/app/services/market_data.py:427) · [officialisation](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:5220) · [Ouverture du dossier](C:/Users/admin/GitHub/structura/frontend/src/components/EventsTab.vue:810).

### M12-02

**Une lacune du fournisseur peut déclasser un fixing déjà officiel**

- Priorité d'audit : **P1** ; chantier principal : **[C13](DEPENDENCIES_AND_VALIDATION.md#c13)** ; lot principal : **3**.
- Statut : **Ouvert — à revalider avant correction**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m12-02).
- Validation : **V-M12-02 — à préparer, non exécutée au lot 0**.

**Critère de validation :** Après fixing officiel validé, une panne d'historique ne change ni son autorité ni son statut contractuel ; le diagnostic de source est distinct et le lifecycle conserve ses faits.

**Points d'entrée de l'audit :** [Ordre des contrôles](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:5228).

### M12-03

**La surveillance des barrières peut utiliser le mauvais observable**

- Priorité d'audit : **P2** ; chantier principal : **[C26](DEPENDENCIES_AND_VALIDATION.md#c26)** ; lot principal : **3**.
- Statut : **Corrigé localement — surveillance et comptes rendus C26 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m12-03).
- Validation : **V-M12-03 — validé localement le 22/10/2026**.

**Critère de validation :** Panier avec UL1 manquant et UL2 présent : aucune compression ne transforme S1 en S2 ; S_MIN/S_MAX sont calculés sur la fenêtre historique définie ou annoncés indisponibles.

**Points d'entrée de l'audit :** [Calcul des performances](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2663) · [résolution des observables](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:2702).

**Remédiation C26 :** [rapport](../REMEDIATION_C26_2026-10-22.md), [preuves](C26_VALIDATION.json). 101 tests backend distincts réussis, 44 nouveaux ; un échec de fixture antérieur conservé. 720 tests frontend et build temporaire réussis ; qualification graphique et déployée restante.

### M12-04

**Un traitement quotidien en erreur peut être journalisé comme réussi**

- Priorité d'audit : **P2** ; chantier principal : **[C26](DEPENDENCIES_AND_VALIDATION.md#c26)** ; lot principal : **3**.
- Statut : **Corrigé localement — surveillance et comptes rendus C26 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m12-04).
- Validation : **V-M12-04 — validé localement le 22/10/2026**.

**Critère de validation :** Tous les deals en erreur donnent un traitement FAILED explicite ; un succès partiel donne détail et couverture ; une reprise n'est pas silencieusement SKIPPED parce qu'un SUCCESS trompeur a été enregistré.

**Points d'entrée de l'audit :** [Résultat du scheduler](C:/Users/admin/GitHub/structura/backend/app/services/lifecycle_alerts.py:220) · [Restitution du refresh](C:/Users/admin/GitHub/structura/frontend/src/views/BookingView.vue:1567).

**Remédiation C26 :** [rapport](../REMEDIATION_C26_2026-10-22.md), [preuves](C26_VALIDATION.json). 101 tests backend distincts réussis, 44 nouveaux ; un échec de fixture antérieur conservé. 720 tests frontend et build temporaire réussis ; qualification graphique et déployée restante.

### M12-05

**Une décision de fixing peut être enregistrée malgré une réponse d’échec**

- Priorité d'audit : **P2** ; chantier principal : **[C13](DEPENDENCIES_AND_VALIDATION.md#c13)** ; lot principal : **3**.
- Statut : **Ouvert — à revalider avant correction**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m12-05).
- Validation : **V-M12-05 — à préparer, non exécutée au lot 0**.

**Critère de validation :** Injecter un échec d'application après décision de fixing : rollback complet ou état intermédiaire explicite récupérable ; une nouvelle tentative retrouve l'intention sans conflit 409 irréparable.

**Points d'entrée de l'audit :** [Premier commit](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:5124) · [traitement suivant](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:5132).

### M12-06

**Une alerte disparaît de l’écran même si son acquittement échoue**

- Priorité d'audit : **P2** ; chantier principal : **[C10](DEPENDENCIES_AND_VALIDATION.md#c10)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m12-06).
- Validation : **V-M12-06 — validé localement le 21/10/2026**.

**Critère de validation :** Simuler HTTP500 à l'acquittement : l'alerte reste visible/non lue et l'erreur apparaît ; un acquittement réussi seul change l'état persistant et local.

**Points d'entrée de l'audit :** [Acquittement](C:/Users/admin/GitHub/structura/frontend/src/views/BookingView.vue:1557).

**Remédiation C10 :** [rapport](../REMEDIATION_C10_2026-10-21.md) et [preuves ciblées](C10_VALIDATION.json). T11/C17 et recette graphique/production restent ouverts.

## M13

**MtM résiduel et historique**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M13-01](#m13-01) | P1 | [C13](DEPENDENCIES_AND_VALIDATION.md#c13) | Le passé du MtM peut contredire les fixings officiels |
| [M13-02](#m13-02) | P1 | [C14](DEPENDENCIES_AND_VALIDATION.md#c14) | À moins d’une semaine de maturité, le résiduel simule trop longtemps |
| [M13-03](#m13-03) | P2 | [C19](DEPENDENCIES_AND_VALIDATION.md#c19) | Une créance historique devient impossible à recalculer après le solde du deal |
| [M13-04](#m13-04) | P2 | [C07](DEPENDENCIES_AND_VALIDATION.md#c07) | Un funding personnalisé passe le filtre de restauration du booking standard |
| [M13-05](#m13-05) | P2 | [C19](DEPENDENCIES_AND_VALIDATION.md#c19) | Le rejeu d’un run ne réutilise pas entièrement son calendrier figé |
| [M13-06](#m13-06) | P2 | [C19](DEPENDENCIES_AND_VALIDATION.md#c19) | Pour une créance certaine, le « rejeu identique » ne vérifie pas l’actualisation |
| [M13-07](#m13-07) | P2 | [C18](DEPENDENCIES_AND_VALIDATION.md#c18) | L’historique peut étiqueter un calcul booking comme « Marché actualisé » |

### M13-01

**Le passé du MtM peut contredire les fixings officiels**

- Priorité d'audit : **P1** ; chantier principal : **[C13](DEPENDENCIES_AND_VALIDATION.md#c13)** ; lot principal : **3**.
- Statut : **Ouvert — à revalider avant correction**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m13-01).
- Validation : **V-M13-01 — à préparer, non exécutée au lot 0**.

**Critère de validation :** Officialiser strike puis coupon à 90 avec barrière 80, alors que le flux fournit 40 : le MtM reprend le coupon officiel et sa mémoire, sans contradiction ; une vraie correction versionnée invalide le courant.

**Points d'entrée de l'audit :** [Lecture du fixing initial](C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py:251) · [reconstruction du passé](C:/Users/admin/GitHub/structura/backend/app/core/inlife_valuation.py:425) · [archivage des références](C:/Users/admin/GitHub/structura/backend/app/core/valuation_runs.py:85).

### M13-02

**À moins d’une semaine de maturité, le résiduel simule trop longtemps**

- Priorité d'audit : **P1** ; chantier principal : **[C14](DEPENDENCIES_AND_VALIDATION.md#c14)** ; lot principal : **4**.
- Statut : **Ouvert — à revalider avant correction**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m13-02).
- Validation : **V-M13-02 — à préparer, non exécutée au lot 0**.

**Critère de validation :** À un jour de maturité, le résiduel diffuse exactement un jour ; l'option ATM sigma50 % au cas audité se rapproche de la référence un jour, sans horizon artificiel d'environ sept jours ; convergence documentée.

**Points d'entrée de l'audit :** [Plancher de durée](C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py:244) · [construction du pas moteur](C:/Users/admin/GitHub/structura/backend/app/core/payscript/engine.py:2221).

### M13-03

**Une créance historique devient impossible à recalculer après le solde du deal**

- Priorité d'audit : **P2** ; chantier principal : **[C19](DEPENDENCIES_AND_VALIDATION.md#c19)** ; lot principal : **5**.
- Statut : **Corrigé localement — archives et rejeu C19 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m13-03).
- Validation : **V-M13-03 — validé localement le 21/10/2026**.

**Critère de validation :** Recalculer une créance à une date historique avant son paiement reste possible après passage actuel du Deal à échu ; les nouveaux prix utilisent l'état à la date demandée.

**Points d'entrée de l'audit :** [Branche dépendante du statut courant](C:/Users/admin/GitHub/structura/backend/app/core/deal_valuation.py:151) · [exclusion après événement terminal](C:/Users/admin/GitHub/structura/backend/app/core/risk_lifecycle.py:38).

**Remédiation C19 :** [rapport](../REMEDIATION_C19_2026-10-21.md), [preuves](C19_VALIDATION.json). D10/D11 confirmées ; aucune qualification de production.

### M13-04

**Un funding personnalisé passe le filtre de restauration du booking standard**

- Priorité d'audit : **P2** ; chantier principal : **[C07](DEPENDENCIES_AND_VALIDATION.md#c07)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m13-04).
- Validation : **V-M13-04 — validée localement sur le périmètre C07**.

**Critère de validation :** Une valorisation avec funding personnalisé n'est pas restaurée comme booking standard ; serveur et client comparent tous les inputs matériels et gardent la provenance exacte.

**Points d'entrée de l'audit :** [Filtre serveur](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:7614) · [filtre navigateur](C:/Users/admin/GitHub/structura/frontend/src/composables/useBookingMtm.js:125).

- Livraison locale : [rapport C07](../REMEDIATION_C07_2026-10-21.md) et [preuves](C07_VALIDATION.json). T11/T15 et recette graphique/production restent ouverts.

### M13-05

**Le rejeu d’un run ne réutilise pas entièrement son calendrier figé**

- Priorité d'audit : **P2** ; chantier principal : **[C19](DEPENDENCIES_AND_VALIDATION.md#c19)** ; lot principal : **5**.
- Statut : **Corrigé localement — archives et rejeu C19 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m13-05).
- Validation : **V-M13-05 — validé localement le 21/10/2026**.

**Critère de validation :** Archiver un calendrier puis changer la résolution courante : le rejeu du run utilise ses dates figées ; un nouveau calcul peut utiliser de nouvelles conventions explicitement versionnées.

**Points d'entrée de l'audit :** [Calendrier figé du MtM](C:/Users/admin/GitHub/structura/backend/app/core/inlife_valuation.py:358) · [reconstruction du rejeu](C:/Users/admin/GitHub/structura/backend/app/core/compute/pricers/var_scenario.py:41).

**Remédiation C19 :** [rapport](../REMEDIATION_C19_2026-10-21.md), [preuves](C19_VALIDATION.json). D10/D11 confirmées ; aucune qualification de production.

### M13-06

**Pour une créance certaine, le « rejeu identique » ne vérifie pas l’actualisation**

- Priorité d'audit : **P2** ; chantier principal : **[C19](DEPENDENCIES_AND_VALIDATION.md#c19)** ; lot principal : **5**.
- Statut : **Corrigé localement — archives et rejeu C19 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m13-06).
- Validation : **V-M13-06 — validé localement le 21/10/2026**.

**Critère de validation :** Une créance certaine est rejouée depuis montant, date de paiement, courbes, funding et date de valeur ; modifier un facteur dans une sonde change le prix ; le contrôle ne retourne pas seulement fixed_price.

**Points d'entrée de l'audit :** [Contexte archivé](C:/Users/admin/GitHub/structura/backend/app/core/valuation_runs.py:48) · [retour direct du prix](C:/Users/admin/GitHub/structura/backend/app/core/compute/pricers/var_scenario.py:80).

**Remédiation C19 :** [rapport](../REMEDIATION_C19_2026-10-21.md), [preuves](C19_VALIDATION.json). D10/D11 confirmées ; aucune qualification de production.

### M13-07

**L’historique peut étiqueter un calcul booking comme « Marché actualisé »**

- Priorité d'audit : **P2** ; chantier principal : **[C18](DEPENDENCIES_AND_VALIDATION.md#c18)** ; lot principal : **5**.
- Statut : **Corrigé localement — contexte partagé, conventions et sources explicites**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m13-07).
- Validation : **V-M13-07 — validée localement sur le périmètre C18**.

**Critère de validation :** Une requête absente ou vide valorisée en mode booking est étiquetée booking selon la source effective retournée ; override et créance connue ont leurs libellés propres.

**Points d'entrée de l'audit :** [Archivage de la requête](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:6915) · [qualification dans l’historique](C:/Users/admin/GitHub/structura/frontend/src/views/DealValuationsView.vue:264).

## M14

**Valo Explain et P&L**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M14-01](#m14-01) | P1 | [C22](DEPENDENCIES_AND_VALIDATION.md#c22) | Le P&L du parcours Booking confond constatation et paiement des coupons |
| [M14-02](#m14-02) | P2 | [C22](DEPENDENCIES_AND_VALIDATION.md#c22) | Un changement de dividende peut être présenté comme un effet véga |
| [M14-03](#m14-03) | P2 | [C19](DEPENDENCIES_AND_VALIDATION.md#c19) | Le PDF d’explication Booking peut différer du résultat affiché |
| [M14-04](#m14-04) | P2 | [C19](DEPENDENCIES_AND_VALIDATION.md#c19) | Une exception de rejeu bloque toute la note au lieu de conserver l’écart observé |
| [M14-05](#m14-05) | P2 | [C18](DEPENDENCIES_AND_VALIDATION.md#c18) | Certaines bases de calcul sont mal qualifiées dans Valo Explain |

Livraison : [rapport C18](../REMEDIATION_C18_2026-10-21.md), [preuves ciblées](C18_VALIDATION.json). Domaines C15–C17 conservés ; recette graphique et scénarios transverses dépendants restants.


### M14-01

**Le P&L du parcours Booking confond constatation et paiement des coupons**

- Priorité d'audit : **P1** ; chantier principal : **[C22](DEPENDENCIES_AND_VALIDATION.md#c22)** ; lot principal : **5**.
- Statut : **Corrigé localement — cash à échéance, créances cohérentes et dividendes séparés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m14-01).
- Validation : **V-M14-01 — validé localement le 22/10/2026**.

**Critère de validation :** Coupon observé le 15 et payé le 22, marché et taux constants : 14→16 donne P&L total nul ; 21→23 réconcilie baisse de créance et cash ; aucun ±10 points artificiel ni compensation temps/résiduel.

**Points d'entrée de l'audit :** [Sélection des flux](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:7292) · [agrégation portefeuille](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:553).

**Remédiation C22 :** [rapport](../REMEDIATION_C22_2026-10-22.md), [preuves](C22_VALIDATION.json). Cash selon les dates contractuelles ; anciens résultats conservés, aucune qualification production.

### M14-02

**Un changement de dividende peut être présenté comme un effet véga**

- Priorité d'audit : **P2** ; chantier principal : **[C22](DEPENDENCIES_AND_VALIDATION.md#c22)** ; lot principal : **5**.
- Statut : **Corrigé localement — cash à échéance, créances cohérentes et dividendes séparés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m14-02).
- Validation : **V-M14-02 — validé localement le 22/10/2026**.

**Critère de validation :** À sigma constant, changer uniquement q attribue l'écart au dividende, sans effet véga fabriqué ; les facteurs restants et le résiduel réconcilient la différence totale.

**Points d'entrée de l'audit :** [Ancienne étape volatilité](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:7266) · [séparation dans Valo Explain](C:/Users/admin/GitHub/structura/backend/app/core/valuation_notes.py:164).

**Remédiation C22 :** [rapport](../REMEDIATION_C22_2026-10-22.md), [preuves](C22_VALIDATION.json). Cash selon les dates contractuelles ; anciens résultats conservés, aucune qualification production.

### M14-03

**Le PDF d’explication Booking peut différer du résultat affiché**

- Priorité d'audit : **P2** ; chantier principal : **[C19](DEPENDENCIES_AND_VALIDATION.md#c19)** ; lot principal : **5**.
- Statut : **Corrigé localement — archives et rejeu C19 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m14-03).
- Validation : **V-M14-03 — validé localement le 21/10/2026**.

**Critère de validation :** Le PDF sélectionne le même run et les mêmes chiffres que l'écran ; réviser les données du fournisseur après affichage ne modifie pas ce document ; un nouveau run reste une action explicite.

**Points d'entrée de l'audit :** [Recalcul lors de l’export](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:7386) · [paramètres utilisés par le bouton](C:/Users/admin/GitHub/structura/frontend/src/views/BookingView.vue:1775).

**Remédiation C19 :** [rapport](../REMEDIATION_C19_2026-10-21.md), [preuves](C19_VALIDATION.json). D10/D11 confirmées ; aucune qualification de production.

### M14-04

**Une exception de rejeu bloque toute la note au lieu de conserver l’écart observé**

- Priorité d'audit : **P2** ; chantier principal : **[C19](DEPENDENCIES_AND_VALIDATION.md#c19)** ; lot principal : **5**.
- Statut : **Corrigé localement — archives et rejeu C19 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m14-04).
- Validation : **V-M14-04 — validé localement le 21/10/2026**.

**Critère de validation :** Injecter une erreur de rejeu compatible avec un écart observé disponible : la note peut conserver les deux valeurs et leur différence sans attribution trompeuse, avec diagnostic ; les erreurs contractuelles bloquantes restent refusées.

**Points d'entrée de l'audit :** [Recalcul des sensibilités](C:/Users/admin/GitHub/structura/backend/app/core/valuation_notes.py:71) · [reproduction des références](C:/Users/admin/GitHub/structura/backend/app/core/valuation_notes.py:130) · [traitement API](C:/Users/admin/GitHub/structura/backend/app/api/valuation_notes.py:108).

**Remédiation C19 :** [rapport](../REMEDIATION_C19_2026-10-21.md), [preuves](C19_VALIDATION.json). D10/D11 confirmées ; aucune qualification de production.

### M14-05

**Certaines bases de calcul sont mal qualifiées dans Valo Explain**

- Priorité d'audit : **P2** ; chantier principal : **[C18](DEPENDENCIES_AND_VALIDATION.md#c18)** ; lot principal : **5**.
- Statut : **Corrigé localement — contexte partagé, conventions et sources explicites**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m14-05).
- Validation : **V-M14-05 — validée localement sur le périmètre C18**.

**Critère de validation :** booking, booking+overrides, réalisé et known_settlement ne sont pas regroupés sous Marché actualisé ; le libellé provient du run effectif conservé.

**Points d'entrée de l'audit :** [Qualification actuelle](C:/Users/admin/GitHub/structura/frontend/src/views/ValoExplainView.vue:148) · [Source](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:7227).

## M15

**Risques portefeuille et CCR**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M15-01](#m15-01) | P1 | [C21](DEPENDENCIES_AND_VALIDATION.md#c21) | La VaR peut annoncer 100 % de couverture avec un facteur totalement absent |
| [M15-02](#m15-02) | P1 | [C21](DEPENDENCIES_AND_VALIDATION.md#c21) | Un calcul partiel peut faire disparaître gamma et rho sans signalement adapté |
| [M15-03](#m15-03) | P1 | [C27](DEPENDENCIES_AND_VALIDATION.md#c27) | Les agrégats historiques mélangent Production et Recette UAT |
| [M15-04](#m15-04) | P1 | [C21](DEPENDENCIES_AND_VALIDATION.md#c21) | La grille CCR peut produire une CVA nulle avant un paiement proche |
| [M15-05](#m15-05) | P2 | [C21](DEPENDENCIES_AND_VALIDATION.md#c21) | Le moniteur CCR peut conserver un résultat comme actuel après changement de fixing |
| [M15-06](#m15-06) | P2 | [C04](DEPENDENCIES_AND_VALIDATION.md#c04) | Un renommage de contrepartie fait disparaître une alerte de concentration |
| [M15-07](#m15-07) | P2 | [C18](DEPENDENCIES_AND_VALIDATION.md#c18) | Le choc de taux ne réactualise pas les coupons détachés restant à recevoir |

Livraison : [rapport C18](../REMEDIATION_C18_2026-10-21.md), [preuves ciblées](C18_VALIDATION.json). Domaines C15–C17 conservés ; recette graphique et scénarios transverses dépendants restants.


### M15-01

**La VaR peut annoncer 100 % de couverture avec un facteur totalement absent**

- Priorité d'audit : **P1** ; chantier principal : **[C21](DEPENDENCIES_AND_VALIDATION.md#c21)** ; lot principal : **5**.
- Statut : **Corrigé localement — couverture explicite, CVA des créances et fraîcheur validées dans le domaine déclaré**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m15-01).
- Validation : **V-M15-01 — validé localement le 22/10/2026 dans le domaine déclaré**.

**Critère de validation :** Deux positions TK1/TK2, scénario historique ne couvrant que TK1 : pas de résultat global qualifié à 100 % ; facteurs manquants exclus explicitement ou lancement refusé ; aucun choc neutre implicite.

**Points d'entrée de l'audit :** [Filtrage des tickers](C:/Users/admin/GitHub/structura/backend/app/core/var_engine.py:184) · [choc nul par défaut](C:/Users/admin/GitHub/structura/backend/app/core/var_engine.py:168).

**Remédiation C21 :** [rapport](../REMEDIATION_C21_2026-10-22.md), [preuves](C21_VALIDATION.json). C27 partiel, bornes CCR explicites et qualification production restante.

### M15-02

**Un calcul partiel peut faire disparaître gamma et rho sans signalement adapté**

- Priorité d'audit : **P1** ; chantier principal : **[C21](DEPENDENCIES_AND_VALIDATION.md#c21)** ; lot principal : **5**.
- Statut : **Corrigé localement — couverture explicite, CVA des créances et fraîcheur validées dans le domaine déclaré**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m15-02).
- Validation : **V-M15-02 — validé localement le 22/10/2026 dans le domaine déclaré**.

**Critère de validation :** Calcul complet puis delta seul : gamma et rho ne deviennent pas zéro ; disponibilité/couverture par métrique et référence de run sont explicites ; une donnée ancienne n'est pas promue actuelle.

**Points d'entrée de l'audit :** [Choix du snapshot](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:261) · [initialisation des agrégats](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:338).

**Remédiation C21 :** [rapport](../REMEDIATION_C21_2026-10-22.md), [preuves](C21_VALIDATION.json). C27 partiel, bornes CCR explicites et qualification production restante.

### M15-03

**Les agrégats historiques mélangent Production et Recette UAT**

- Priorité d'audit : **P1** ; chantier principal : **[C27](DEPENDENCIES_AND_VALIDATION.md#c27)** ; lot principal : **1**.
- Statut : **Corrigé localement — Production/UAT et historiques C27 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m15-03).
- Validation : **V-M15-03 — validé localement le 22/10/2026**.

**Critère de validation :** Production 1 M et UAT 1 M : risque, chocs, VaR et historiques Production ne comptent que 1 M ; le scope UAT ou mixte est explicite et conservé.

**Points d'entrée de l'audit :** [Sélection globale des positions](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:87) · [lancement VaR](C:/Users/admin/GitHub/structura/backend/app/api/var.py:421).

**Solde C27 — 22/10 :** [rapport](../REMEDIATION_C27_2026-10-22.md), [preuves](C27_VALIDATION.json). 65 cas backend ciblés réussis, dont 26 nouveaux C27 ; imports Demo et chaîne C24 réexercés. 731 tests frontend et build temporaire réussis. Recette graphique et qualification déployée restantes.

### M15-04

**La grille CCR peut produire une CVA nulle avant un paiement proche**

- Priorité d'audit : **P1** ; chantier principal : **[C21](DEPENDENCIES_AND_VALIDATION.md#c21)** ; lot principal : **5**.
- Statut : **Corrigé localement — couverture explicite, CVA des créances et fraîcheur validées dans le domaine déclaré**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m15-04).
- Validation : **V-M15-04 — validé localement le 22/10/2026 dans le domaine déclaré**.

**Critère de validation :** Créance 1 M payable dans deux jours, r=0, récupération40 %, PD cumulée linéaire20 %/an : CVA rejoint 1e6*0,6*0,2*2/365,25 ≈657,084 EUR ; une limite100 ne donne pas OK/booking_allowed ; préserver l'exposition avant paiement.

**Points d'entrée de l'audit :** [Construction de la grille](C:/Users/admin/GitHub/structura/backend/app/core/ccr/service.py:496) · [intégration CVA](C:/Users/admin/GitHub/structura/backend/app/core/ccr/exposure.py:110).

**Remédiation C21 :** [rapport](../REMEDIATION_C21_2026-10-22.md), [preuves](C21_VALIDATION.json). C27 partiel, bornes CCR explicites et qualification production restante.

### M15-05

**Le moniteur CCR peut conserver un résultat comme actuel après changement de fixing**

- Priorité d'audit : **P2** ; chantier principal : **[C21](DEPENDENCIES_AND_VALIDATION.md#c21)** ; lot principal : **5**.
- Statut : **Corrigé localement — couverture explicite, CVA des créances et fraîcheur validées dans le domaine déclaré**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m15-05).
- Validation : **V-M15-05 — validé localement le 22/10/2026 dans le domaine déclaré**.

**Critère de validation :** Corriger un fixing officiel sans changer contract_version invalide le moniteur ; même empreinte de dépendances que la préparation ; anciens runs restent consultables comme historiques.

**Points d'entrée de l'audit :** [Contrôle du moniteur](C:/Users/admin/GitHub/structura/backend/app/api/ccr.py:158) · [empreinte de préparation](C:/Users/admin/GitHub/structura/backend/app/core/ccr/cache.py:13).

**Remédiation C21 :** [rapport](../REMEDIATION_C21_2026-10-22.md), [preuves](C21_VALIDATION.json). C27 partiel, bornes CCR explicites et qualification production restante.

### M15-06

**Un renommage de contrepartie fait disparaître une alerte de concentration**

- Priorité d'audit : **P2** ; chantier principal : **[C04](DEPENDENCIES_AND_VALIDATION.md#c04)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m15-06).
- Validation : **V-M15-06 — validée localement sur le périmètre C04**.

**Critère de validation :** Renommer une contrepartie conserve exposition, limite et dépassement par ID ; ne pas généraliser ce cas de concentration historique à un contournement démontré des limites CCR.

**Points d'entrée de l'audit :** [Regroupement et recherche des limites](C:/Users/admin/GitHub/structura/backend/app/api/portfolios.py:700).

- Livraison locale : [rapport C04](../REMEDIATION_C04_2026-10-20.md) et [preuves](C04_VALIDATION.json). T05 complet et qualification C21 encore ouverts.

### M15-07

**Le choc de taux ne réactualise pas les coupons détachés restant à recevoir**

- Priorité d'audit : **P2** ; chantier principal : **[C18](DEPENDENCIES_AND_VALIDATION.md#c18)** ; lot principal : **5**.
- Statut : **Corrigé localement — contexte partagé, conventions et sources explicites**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m15-07).
- Validation : **V-M15-07 — validée localement sur le périmètre C18**.

**Critère de validation :** Coupon détaché encore impayé sur Deal actif : choc de taux actualise aussi la créance à sa date réelle ; +100 bp sur 100 kEUR à six jours donne la variation déterministe attendue, séparée de l'optionalité.

**Points d'entrée de l'audit :** [Réinjection de la PV initiale](C:/Users/admin/GitHub/structura/backend/app/api/shocks.py:192).

## M16

**Clients / CRM**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M16-01](#m16-01) | P1 | [C01](DEPENDENCIES_AND_VALIDATION.md#c01) | le CRM restitue des détails de Deals interdits en consultation directe |
| [M16-02](#m16-02) | P2 | [C24](DEPENDENCIES_AND_VALIDATION.md#c24) | changer le client d’une opportunité peut casser ses rattachements |
| [M16-03](#m16-03) | P2 | [C24](DEPENDENCIES_AND_VALIDATION.md#c24) | une analyse historique inclut des transactions futures |
| [M16-04](#m16-04) | P2 | [C24](DEPENDENCIES_AND_VALIDATION.md#c24) | les montants de devises différentes sont agrégés sans conversion |
| [M16-05](#m16-05) | P2 | [C27](DEPENDENCIES_AND_VALIDATION.md#c27) | un historique importé sur un mandat fictif entre dans le profil réel |

Livraison : [rapport C18](../REMEDIATION_C18_2026-10-21.md), [preuves ciblées](C18_VALIDATION.json). Domaines C15–C17 conservés ; recette graphique et scénarios transverses dépendants restants.


### M16-01

**le CRM restitue des détails de Deals interdits en consultation directe**

- Priorité d'audit : **P1** ; chantier principal : **[C01](DEPENDENCIES_AND_VALIDATION.md#c01)** ; lot principal : **1**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m16-01).
- Validation : **V-M16-01 — réussie localement sur le périmètre C01** ; [résultats et limites](../REMEDIATION_C01_2026-10-20.md), [preuve structurée](C01_VALIDATION.json).

**Critère de validation :** Un utilisateur refusé en accès direct au Deal n'obtient pas par CRM son nominal, prix ou autres détails non autorisés ; les agrégats et liens respectent la politique explicite de projection.

**Points d'entrée de l'audit :** [autorisation Deal](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:1063) · [entrée CRM](C:/Users/admin/GitHub/structura/backend/app/api/client_intelligence.py:51) · [chargement des transactions](C:/Users/admin/GitHub/structura/backend/app/core/client_intelligence.py:325).

### M16-02

**changer le client d’une opportunité peut casser ses rattachements**

- Priorité d'audit : **P2** ; chantier principal : **[C24](DEPENDENCIES_AND_VALIDATION.md#c24)** ; lot principal : **7**.
- Statut : **Corrigé localement — CRM C24 validé**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m16-02).
- Validation : **V-M16-02 — validé localement le 22/10/2026**.

**Critère de validation :** Déplacer une opportunité A→B revalide tous les participants persistés ; avec Deal/RFQ attaché, refuser ou utiliser une rectification gouvernée ; aucune chaîne Deal A/opportunité B incohérente.

**Points d'entrée de l'audit :** [changement de client de l’opportunité](C:/Users/admin/GitHub/structura/backend/app/api/opportunities.py:410).

**Remédiation C24 :** [rapport](../REMEDIATION_C24_2026-10-22.md), [preuves](C24_VALIDATION.json). Le prérequis CRM de C27 est exercé ; C27 global et qualification déployée restent ouverts.

### M16-03

**une analyse historique inclut des transactions futures**

- Priorité d'audit : **P2** ; chantier principal : **[C24](DEPENDENCIES_AND_VALIDATION.md#c24)** ; lot principal : **7**.
- Statut : **Corrigé localement — CRM C24 validé**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m16-03).
- Validation : **V-M16-03 — validé localement le 22/10/2026**.

**Critère de validation :** Au 01/02/2026, une transaction du 15/01/2027 n'entre ni dans les habitudes, ni dans le cycle ; aucune durée négative ; état des opportunités historiques distingué de l'état courant.

**Points d'entrée de l'audit :** [sélection des transactions](C:/Users/admin/GitHub/structura/backend/app/core/client_intelligence.py:1493) · [calcul du cycle](C:/Users/admin/GitHub/structura/backend/app/core/client_cycle.py:175).

**Remédiation C24 :** [rapport](../REMEDIATION_C24_2026-10-22.md), [preuves](C24_VALIDATION.json). Le prérequis CRM de C27 est exercé ; C27 global et qualification déployée restent ouverts.

### M16-04

**les montants de devises différentes sont agrégés sans conversion**

- Priorité d'audit : **P2** ; chantier principal : **[C24](DEPENDENCIES_AND_VALIDATION.md#c24)** ; lot principal : **7**.
- Statut : **Corrigé localement — CRM C24 validé**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m16-04).
- Validation : **V-M16-04 — validé localement le 22/10/2026**.

**Critère de validation :** 1 M EUR et 100 M JPY donnent deux montants par devise, ou un agrégat converti avec date/source/FX ; aucun pipeline101 M ni médiane50,5 M sans unité commune.

**Points d'entrée de l'audit :** [pipeline](C:/Users/admin/GitHub/structura/backend/app/api/client_intelligence.py:227) · [ticket médian](C:/Users/admin/GitHub/structura/backend/app/core/client_intelligence.py:456).

**Remédiation C24 :** [rapport](../REMEDIATION_C24_2026-10-22.md), [preuves](C24_VALIDATION.json). Le prérequis CRM de C27 est exercé ; C27 global et qualification déployée restent ouverts.

### M16-05

**un historique importé sur un mandat fictif entre dans le profil réel**

- Priorité d'audit : **P2** ; chantier principal : **[C27](DEPENDENCIES_AND_VALIDATION.md#c27)** ; lot principal : **1**.
- Statut : **Corrigé localement — CRM C24 validé**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m16-05).
- Validation : **V-M16-05 — validé localement le 22/10/2026**.

**Critère de validation :** Importer via le vrai moteur une transaction sur mandat Demo d'un client natif ne l'inclut pas dans le profil réel ; origine et exclusion sont cohérentes avec les Deals natifs et le scope choisi.

**Points d'entrée de l'audit :** [normalisation des provenances](C:/Users/admin/GitHub/structura/backend/app/core/client_intelligence.py:282).

**Remédiation C24 :** [rapport](../REMEDIATION_C24_2026-10-22.md), [preuves](C24_VALIDATION.json). Le prérequis CRM de C27 est exercé ; C27 global et qualification déployée restent ouverts.

**Solde C27 — 22/10 :** [rapport](../REMEDIATION_C27_2026-10-22.md), [preuves](C27_VALIDATION.json). 65 cas backend ciblés réussis, dont 26 nouveaux C27 ; imports Demo et chaîne C24 réexercés. 731 tests frontend et build temporaire réussis. Recette graphique et qualification déployée restantes.

## M17

**Réinvestissement et déclinaisons**

| Identifiant | Priorité | Chantier | Constat |
|---|---|---|---|
| [M17-01](#m17-01) | P1 | [C18](DEPENDENCIES_AND_VALIDATION.md#c18) | le scan abandonne des hypothèses matérielles de valorisation |
| [M17-02](#m17-02) | P1 | [C25](DEPENDENCIES_AND_VALIDATION.md#c25) | le roll est financé au prix modèle, sans coût de sortie ni marge d’entrée |
| [M17-03](#m17-03) | P1 | [C25](DEPENDENCIES_AND_VALIDATION.md#c25) | le « plafond de récupération » n’est pas un plafond |
| [M17-04](#m17-04) | P2 | [C05](DEPENDENCIES_AND_VALIDATION.md#c05) | modifier la maturité ne redimensionne pas toujours les observations |
| [M17-05](#m17-05) | P2 | [C19](DEPENDENCIES_AND_VALIDATION.md#c19) | les propositions ne sont pas figées et le PDF peut différer de l’écran |

### M17-01

**le scan abandonne des hypothèses matérielles de valorisation**

- Priorité d'audit : **P1** ; chantier principal : **[C18](DEPENDENCIES_AND_VALIDATION.md#c18)** ; lot principal : **5**.
- Statut : **Corrigé localement — contexte partagé, conventions et sources explicites**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m17-01).
- Validation : **V-M17-01 — validée localement sur le périmètre C18**.

**Critère de validation :** À inputs et calendrier communs, scan/solveur/probabilités utilisent modèle, taux, funding et conventions actifs ; le PAY1 trois ans avec funding10 % vaut exp(-0,3)≈0,740818 et non1 ; toute simplification est explicite.

**Points d'entrée de l'audit :** [appels du solveur et des probabilités](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:6593) · [modèle par défaut](C:/Users/admin/GitHub/structura/backend/app/core/schemas.py:496) · [requête de l’écran](C:/Users/admin/GitHub/structura/frontend/src/views/ReinvestView.vue:505).

Livraison : [rapport C18](../REMEDIATION_C18_2026-10-21.md), [preuves ciblées](C18_VALIDATION.json). Domaines C15–C17 conservés ; recette graphique et scénarios transverses dépendants restants.


### M17-02

**le roll est financé au prix modèle, sans coût de sortie ni marge d’entrée**

- Priorité d'audit : **P1** ; chantier principal : **[C25](DEPENDENCIES_AND_VALIDATION.md#c25)** ; lot principal : **7**.
- Statut : **Corrigé localement — financement et récupération C25 validés**.
- Preuve antérieure : **L — lecture ou analyse décrite dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m17-02).
- Validation : **V-M17-02 — réussie localement** ; [rapport et limites](../REMEDIATION_C25_2026-10-22.md), [preuves](C25_VALIDATION.json).

**Critère de validation :** Donner un bid deux points sous le modèle ou des coûts d'entrée modifie effectivement quantité et récupération ; origine du bid/hypothèse et horodatage sont affichés ; sans bid la restitution indique l'hypothèse modèle.

**Points d'entrée de l'audit :** [financement du roll](C:/Users/admin/GitHub/structura/backend/app/api/variants.py:250) · [point ouvert documenté](C:/Users/admin/GitHub/structura/docs/projects/lifecycle/DECLINAISONS_POINTS_OUVERTS.md:102).

### M17-03

**le « plafond de récupération » n’est pas un plafond**

- Priorité d'audit : **P1** ; chantier principal : **[C25](DEPENDENCIES_AND_VALIDATION.md#c25)** ; lot principal : **7**.
- Statut : **Corrigé localement — financement et récupération C25 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m17-03).
- Validation : **V-M17-03 — réussie localement** ; [rapport et limites](../REMEDIATION_C25_2026-10-22.md), [preuves](C25_VALIDATION.json).

**Critère de validation :** Roll déterministe PAY1,2 du cas audité : quantité≈0,956635 et récupération≈1,147961 sont distinctes ; aucun plafond95,66 % en contradiction avec probabilité du pair100 % ; plafond absent si non démontrable.

**Points d'entrée de l'audit :** [calcul du champ](C:/Users/admin/GitHub/structura/backend/app/api/variants.py:248) · [définition affichée](C:/Users/admin/GitHub/structura/frontend/src/components/VariantCompareTab.vue:75).

### M17-04

**modifier la maturité ne redimensionne pas toujours les observations**

- Priorité d'audit : **P2** ; chantier principal : **[C05](DEPENDENCIES_AND_VALIDATION.md#c05)** ; lot principal : **2**.
- Statut : **Corrigé localement — tests ciblés validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m17-04).
- Validation : **V-M17-04 — validée localement sur le périmètre C05**.

**Critère de validation :** Demander un an ou cinq ans sur calendrier trois ans reconstruit toutes les observations et paiements ou refuse explicitement ; les douze dates initiales ne subsistent pas sous une maturité annoncée différente.

**Points d'entrée de l'audit :** [adaptation du calendrier](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:6641).

Livraison : [rapport C05](../REMEDIATION_C05_2026-10-20.md), [preuves ciblées](C05_VALIDATION.json). Qualification transverse et production encore ouvertes.


### M17-05

**les propositions ne sont pas figées et le PDF peut différer de l’écran**

- Priorité d'audit : **P2** ; chantier principal : **[C19](DEPENDENCIES_AND_VALIDATION.md#c19)** ; lot principal : **5**.
- Statut : **Corrigé localement — archives et rejeu C19 validés**.
- Preuve antérieure : **R — reproduction isolée rapportée dans l'audit**, 19 octobre 2026 ; [constat source](AUDIT_SOURCES.md#s-m17-05).
- Validation : **V-M17-05 — validé localement le 21/10/2026**.

**Critère de validation :** Figer la proposition affichant coupon14,1602 % puis changer la source de vol10→60 % : PDF et preuve figée gardent14,1602 % ; nouvelle proposition séparée ; l'étude conserve alternatives, inputs, auteur et filiation.

**Points d'entrée de l'audit :** [recalcul lors du PDF](C:/Users/admin/GitHub/structura/backend/app/api/deals.py:6844) · [modification d’une variante](C:/Users/admin/GitHub/structura/backend/app/api/scripts_db.py:470).

**Remédiation C19 :** [rapport](../REMEDIATION_C19_2026-10-21.md), [preuves](C19_VALIDATION.json). D10/D11 confirmées ; aucune qualification de production.

**Suivi historique C19 — 21/10/2026 :** neuf constats traités et validés localement ; 444 cas backend et 55 tests frontend réussis. 104 échecs antérieurs reproduits à l’identique, conservés séparément. [Rapport](../REMEDIATION_C19_2026-10-21.md), [preuves](C19_VALIDATION.json). D10/D11 confirmées ; D06 et les consommateurs dépendants restent ouverts.

**Suivi historique C20 — 22/10/2026 :** quatre constats traités, 219 cas backend et 28 tests frontend réussis. Interaction Phoenix/C14 corrigée et protections C19 conservées. [Rapport](../REMEDIATION_C20_2026-10-22.md), [preuves](C20_VALIDATION.json). Budget séquentiel souple explicite ; qualification production restante.

**Suivi historique C21 — 22/10/2026 :** quatre constats traités localement ; 226 cas backend distincts, 660 tests frontend et build temporaire réussis. [Rapport](../REMEDIATION_C21_2026-10-22.md), [preuves](C21_VALIDATION.json). T05/T08/T09/T10 restent partiels ; C27 et production non clos.

**Suivi historique C22 — 22/10/2026 :** deux constats traités localement ; 161 cas backend distincts, dont 22 nouveaux, 662 tests frontend et build temporaire réussis. [Rapport](../REMEDIATION_C22_2026-10-22.md), [preuves](C22_VALIDATION.json). Deux PDF synthétiques inspectés visuellement ; T08/T09 et production restent partiels.
