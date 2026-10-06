# Notes du projet Structura

Toutes les notes de travail du dépôt, rangées par nature. Chaque note garde son nom
d'origine : seul son dossier a changé, le 14/09/2026. **Revue documentaire du
05/10/2026**, sur `main`, commit `15d7ccf` : les points revérifiés et leurs preuves
figurent dans [la revue de reprise](audits/REVUE_DOCUMENTAIRE_2026-10-05.md).
Il s'agit d'une lecture du code et des tests, sans nouvelle exécution ni recette UI.
Les autres états restent ceux des notes datées ; « vérifié » sans date désigne
le contrôle historique du 14/09, pas une validation actuelle.

**Une nouvelle note va dans le dossier de sa nature et entre dans cet index.** Rien à la
racine du dépôt, à part `CLAUDE.md`.

## Arborescence

```text
docs/
├── README.md        cet index
├── audits/          constats datés et journal de recette client
├── projects/        chantiers : conception, plan, rapport d'implémentation
│   ├── pricing/     PayScript, éditeur, modèles de produits, assistant IA
│   ├── lifecycle/   booking, fixings, MtM, notes de valorisation, déclinaisons
│   ├── clients/     module Clients, lots 0 à 3
│   ├── platform/    objet Product, accueil, déploiement, sources de données
│   └── studies/     études AMC, moteurs en feuille de route
├── reference/       documentation tenue à jour
├── lessons/         retours d'expérience et post-mortem
├── handoffs/        points de reprise de fin de session
└── archive/         documents périmés, conservés pour l'historique
```

Hors de `docs/` : `CLAUDE.md` (racine, lu à chaque session),
`.claude/agents/client-tester.md` (agent de recette, qui écrit dans
`audits/TESTING_JOURNAL.md`) et `demo-video/` (storyboard, rangé avec la vidéo).

**États.** *Fait* : livré. *En cours* : livré en partie. *À faire* : rien de codé.
*Clos* : tous les constats de l'audit sont traités ou arbitrés. *Suivi* : des constats
restent ouverts. *Dépassé* : repris par une note plus récente. *Référence* : tenu à jour.
*Historique* : à lire pour le contexte. *Archivé* : ne pas s'y fier.

## Ce qui reste à faire

PayScript : [UNDERLYING, StartDate et paramètres Economics](projects/pricing/PAYSCRIPT_STARTDATE_UNDERLYING_DESIGN_2026-10-06.md)
— **Audit et proposition au 06/10, sans implémentation** : panier lié à Economics,
fixing initial explicite, première observation distincte, masques Pricer/RFQ/Booking,
PARAM sans défaut obligatoire et flux séparés. Pas de migration des deals de test.
Revue transversale ajoutée : Risk/CCR, workers, variantes, KID/EMT, Clients,
assistants, génération UAT et dépendances des scripts à supprimer (§7–8).
[Deuxième revue systématique](audits/AUDIT_TRANSVERSAL_PAYSCRIPT_2026-10-06.md) :
brouillons incomplets, Réinvestissement/backtests, contrôles de chemin, preuves de
calcul et inventaire SQLite en lecture seule. 0 script sauvegardé mais 42 deals,
41 RFQ et 42 Products ; aucune suppression ni implémentation effectuée.

Product Optimizer : [V1 — architecture, capacités et recette](PRODUCT_OPTIMIZER_V1.md)
— **Implémenté localement le 05/10** : Athena mono-actif / worst-of sous GBM,
résolution du coupon, contraintes avec IC95, classement, comparaison et Pareto.
Hypothèses manuelles ; convergence, marché qualifié et extensions restent à faire.
Note placée à ce chemin sur demande explicite de Philippe.

CCR : [Intégration du risque de contrepartie](projects/pricing/CCR_IMPLEMENTATION_2026-09-28.md)
— **Socle et extensions CCR 1.2 présents dans le code au 05/10** : référentiel
juridique/crédit, préparation des MtM, marché commun, exposition GBM, CVA simple,
contrôles Pricing/RFQ/deal booké et limites au booking. Taux commun provisoire
de 3 % lors de la préparation, explicitement qualifié comme hypothèse.
Recette visuelle complète et convergence restent ouvertes selon le rapport.

SA-CCR : [Portefeuille mixte notes / OTC](projects/pricing/SA_CCR_PORTEFEUILLE_MIXTE_ROADMAP_2026-09-29.md)
— **Cadrage seulement, confirmé au 05/10** : l'EAD réglementaire reste absente
du moteur ; ne pas la confondre avec la PFE économique du CCR.

Organisations et accès : [Cadrage de l'admission et des habilitations](projects/platform/ORGANIZATION_ACCESS_DESIGN_2026-09-24.md)
— **À faire, développement différé, confirmé au 05/10**. L'existant conserve
`User.entity_id` et un rôle global ; invitations, approbations, propriété stable
des données par organisation et habilitations par desk restent à construire.

Dernière correction Pricing : [Authentification des appels et erreurs de validation](projects/pricing/PRICING_AUTHENTIFICATION_2026-09-24.md)
— 30 appels harmonisés ; 217 tests frontend et build réussis ; pricing initial et profil de payoff vérifiés dans le navigateur.

Studies : [Audit métier et technique du 20/09/2026](audits/AUDIT_STUDIES_2026-09-20.md)
— constats initiaux ; corrections et contrôles décrits dans le [processus Studies](projects/studies/STUDIES_PROCESS_ET_CORRECTIONS_2026-09-20.md), avec limites de données et extensions restantes.
[Pitch de partenariat consulting](projects/studies/STUDIES_CONSULTING_PITCH_2026-09-20.md)
— préparation du rendez-vous du 23/09 : argumentaire, démonstration et pilote accompagné.
La [recette UI du 22/09](projects/studies/COMPTE_RENDU_RECETTE_UI_2026-09-22.md)
et ses [corrections en méthode 2.5](projects/studies/CORRECTIONS_RECETTE_2026-09-22.md)
prolongent les notes du 21/09 : elles consignent une exécution, une réouverture
et les comparaisons du jeu long-only. `studies-2.5` est confirmé dans le code
au 05/10 ; ces résultats historiques n'ont pas été réexécutés lors de cette revue.

IA : [Socle commun aux cinq assistants](projects/platform/IA_COMMUNE_2026-09-17.md)
— implémenté selon la note du 17/09/2026 ; catalogue, éditeur de prompt et suivi partagés. L'état du serveur local n'est pas vérifié par cet index.

Nouveau module Life Cycle : [Valo Explain — édition, comparaison et PDF figés](projects/lifecycle/VALO_EXPLAIN_2026-09-17.md)
— implémenté selon la note du 17/09/2026 ; l'état du serveur local n'est pas vérifié par cet index.

Dernière correction Booking : [MtM quotidien et progression du calcul](projects/lifecycle/BOOKING_MTM_QUOTIDIEN_2026-09-17.md)
— implémenté selon la note du 17/09/2026 ; l'état du serveur local n'est pas vérifié par cet index.

### Avant toute ouverture hors du poste local

- **Revérifié au 05/10** : les routeurs Pricing, Simulation et Scénarios imposent
  `get_current_user`. Les **quatre routes Schedule** restent sans dépendance
  d'authentification. Ce contrôle ne constitue pas un inventaire de toutes les API.
- CORS limité par défaut aux origines locales 5173/8000 ; surcharge possible par
  `STRUCTURA_CORS_ORIGINS`, avec credentials. Configuration déployée non inspectée.
- Inscription publique désactivée par défaut (`STRUCTURA_ALLOW_REGISTRATION`).
  Si activée, une entité non renseignée retombe encore sur « Demo », sans admission
  contrôlée par organisation.
- Aucun middleware global de durcissement HTTP identifié dans `main.py`
  (CSP, `X-Frame-Options`…). Un `nosniff` local existe dans `api/deals.py`.

Sources : audit de production du 31/07, audit du 02/08, contre-expertise du 11/09 (F01).

### Risque et portefeuille

- **Revérifié au 05/10** : les chemins historiques `portfolios.py`, `shocks.py`
  et `var.py` n'appliquent pas de filtre `uat_batch_id`. En revanche, le **CCR**
  sépare explicitement Production / Recette UAT dans son API et son service.
- Aucun branchement au Mode Démo identifié dans BookingView, EventsTab, RfqView
  et RiskManagementView au 05/10 ; comportement visuel non recetté dans cette revue.
- La sensibilité au spread émetteur n'est pas agrégée dans `api/portfolios.py`
  au 05/10.
- La reprise du 27/07 demandait une recette VaR réelle. Ne pas transformer ce
  constat daté en « jamais testé » : la couverture et les évolutions ultérieures
  doivent être examinées avant un nouveau verdict méthodologique.

### Moteur

- Monitoring continu par pont brownien : l'écart de −14,3 % est une mesure historique
  des audits du 01/08 et du 02/08, **non reproduite au 05/10**. Le moteur expose
  aujourd'hui une note sur les limites de l'interpolation ; le défaut chiffré reste
  à requalifier par une mesure, sans le déclarer corrigé ni encore reproduit.
- Vega Heston : la couverture est annoncée par `vega_scope`, sans vega sur les paramètres
  calibrés.
- Mark-to-Future du Pricer : `n_outer` à 200 et grille uniforme par défaut, confirmés
  au 05/10. Le moteur accepte aussi des dates explicites ; le CCR enrichit sa grille.
  `run_mc_proba` conserve des quantiles sans interpolation ; ceux du MTF utilisent
  `np.quantile`. Ces chemins ne doivent pas être confondus.
- Pas de champ repo distinct du rendement de dividende `q`. Vérifié.
- Constatations sur période : `_age_compiled_script` conserve désormais fenêtres,
  rangs, relevés passés et paiements. Le theta refuse explicitement les transitions
  de fenêtre/observation non résolues ; tests dédiés présents. P&L explain, KID et
  `REALVOL` à fenêtre de départ ouverte restent à recetter selon les cas du §24.
- Règle A7 : quatre tests dédiés existent dans `test_inlife_pricing.py` (horizon
  résiduel, flux depuis la valorisation, passé depuis le strike, déplacement de la
  frontière). Présence et assertions lues au 05/10 ; aucune nouvelle mesure ici.

### Éditeur, Economics et modèles

- EMT corrigé dans le code au 05/10 : levier sur `user_params`, export des
  `effective_parameters`, priorité à ces valeurs dans la synthèse. Les défauts du
  script ne servent que de repli ; les autres lecteurs du 11/09 restent à contrôler.
- Changement de forme d'un CONSTAT (P2 du 11/09) : conversion single → schedule
  toujours à traiter. `_buildUserParams` refuse les chaînes vides et les tableaux
  vides/non numériques ; `null`/`undefined` utilisent encore le défaut via `??`.
  Ne plus affirmer globalement qu'un champ vidé ne bloque jamais le calcul.
- Modèles de produits : questions ouvertes du §6.2 et vérification à l'écran après
  redémarrage du backend.
- Mode debug : dernière priorité, à redemander avant de le coder.

### Cycle de vie et RFQ

- Source officielle de chemin pour les produits path-dependent, annulation et
  remplacement d'un deal, propagation aval (confirmations, comptabilité), file Checker
  dédiée, identifiant de corrélation (rapports du 31/07).
- Déclinaisons : coût de débouclage, gel d'une proposition client, traçabilité. Aucune
  trace dans l'API des variantes. Vérifié.
- Les constructeurs locaux de calendriers de `RfqView.vue` omettent toujours les
  champs de fenêtre. En revanche, une RFQ liée à un Product reprend ses termes
  côté serveur. Le risque concerne les parcours locaux de saisie/restauration ;
  un refus systématique de toute RFQ à fenêtre n'est pas établi.
- Mineurs RFQ du 30/07 : nom d'AO vide et script non compilable acceptés par le serveur,
  mode Expert détecté par la seule chaîne `CONSTAT`, devise de cotation morte,
  numérotation globale des références, conversion indicatif → to trade sans lien avec
  l'AO d'origine, cotation ajoutable après booking. Non revérifiés.

### Chantiers non commencés ou à poursuivre

- Objet Product : RFQ, indicatif, booking, lifecycle, MtM/VaR et documents sont
  reliés dans le code au 05/10. Création interne lors d'un geste métier durable ;
  « Conserver » contrôle la visibilité dans la bibliothèque. Restent la reprise
  historique et la consolidation des consommateurs secondaires. Les anciens deals
  sans Product sont refusés par MtM/VaR, sans repli automatique.
- Déploiement on-premise : installeur, service Windows, sauvegarde de la base, mises à
  jour, journaux.
- Données de marché : FRED, taux officiels, données d'options.
- Études AMC : quatre moteurs en feuille de route ; FIFO, décomposition prix/FX du lot T0.

### Travaux sans fichier dans le dépôt

Pages publiées : contre-expertise de l'audit externe du 11/09 (P0 retenus F01, F03, F06,
F14, F20, F28 ; arbitrages A0 à A10 en attente), audit qualité du 30/08, analyse SaaS du
11/09, étude de l'objet Product du 13/09, plan Client Intelligence du 31/08.

## Historique des travaux des 14 et 15/09

Les puces suivantes décrivent la session de septembre. **Elles ne sont plus un état
Git actuel** : au début de la revue du 05/10, `main` pointe sur `15d7ccf` et aucun
fichier suivi n'est modifié. Product et les modèles sont présents sur cette branche.

- Modèles de produits, lots 1 à 4 : `projects/pricing/MODELES_PRODUITS_DESIGN.md`, §9.
- Booking d'une RFQ à échéancier CONSTAT, refusé depuis le 10/09 (« termes contractuels
  figés : T, constats ») : le contrôle compare désormais le contrat et non son écriture,
  T en jours et constats sans leurs clés vides (`core/rfq_controls.py`,
  `booking_terms_differences`). Un vrai changement reste refusé ; tests dans
  `test_rfq.py`, §18.
- Forward start : fenêtre de calibration réalisée indépendante de l'âge du deal
  (`core/calibration.py`), prix du Pricer avant la date de strike égal au MtM de Booking
  (`api/inlife.py`), date de valorisation proposée à la réouverture du deal.
- Objet Product sur la branche `codex/product-workflow` : modifications d'une autre
  session.
- Ce classement : notes déplacées sans `git mv`, chemin de la référence PayScript mis à
  jour dans `services/llm/prompt.py` et dans son test.

Le besoin de redémarrage était celui de cette session ; aucun état de processus
local n'a été contrôlé lors de la revue documentaire du 05/10.

## Détail par dossier

### `audits/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `AUDIT_PRICING_2026-07.md` | 17/07 | Moteur Monte Carlo : 9 défauts corrigés le jour même, puis barrières continues, Heston/SABR vectorisés, backtest intra-période | Clos | Mémoire non bornée à N élevé ; transpileur fondé sur `exec` (assumé) |
| `AUDIT_RFQ_2026-07-29.md` | 29/07 | Module RFQ, 6 constats | Clos le 30/07 | Voir les mineurs de l'audit du 30/07 |
| `TESTING_JOURNAL.md` | 29/07 | Journal de l'agent client-tester : pricing, booking, cycle de vie, RFQ | Clos | Sélecteur d'exemples sans confirmation visuelle, jugé mineur |
| `AUDIT_CHAINE_RFQ_2026-07-30.md` | 30/07 | Chaîne RFQ → pricing → booking, 9 constats | Clos | Mineurs du §10 ; ténor du Pricer contre calendrier, à revoir avec la règle de maturité du 14/09 |
| `AUDIT_COMPLET_PRICING_RFQ_LIFECYCLE_2026-07-31.md` | 31/07 | Audit fonctionnel et quantitatif, 11 P0, NO-GO | Dépassé | Repris par les audits du 01/08, du 02/08 et du 07/08 |
| `AUDIT_PRODUCTION_COMPLET_HORS_AMC_2026-07-31.md` | 31/07 | Production : sécurité, performance, pricing, lifecycle, KID, NO-GO historique | Suivi | Revue 05/10 : Pricing/Simulation/Scénarios authentifiés, CORS restreint par défaut, inscription désactivée par défaut ; Schedule public et durcissement global restent ouverts. Budget de calcul présent |
| `AUDIT_QUANTITATIF_COMPLET_HORS_AMC_2026-07-31.md` | 31/07 | 40 constats quantitatifs, dont 12 critiques | Dépassé | Repris par la vague 1 du 31/07 et l'audit du 01/08 |
| `AUDIT_QUANTITATIF_2026-08-01.md` | 01/08 | Revérification : 6 bloquants sur 12 fermés | Dépassé | Repris par l'audit du 02/08 |
| `AUDIT_COMPLET_2026-08-02.md` | 02/08 | 20 constats rejoués ; lots 1 et 2 corrigés selon le rapport | Suivi | Revue 05/10 : CORS restreint par défaut ; pont brownien à remesurer, vega Heston partiel, grille hebdomadaire et durcissement HTTP global restent ouverts ; vol locale non revalidée |
| `AUDIT_MTF_2026-08-03.md` | 03/08 | Mark-to-Future : 5 défauts corrigés (double comptage, STRIKE_FIX, courbe, quantile, date proche) | Suivi | `n_outer` par défaut, grille de dates, quantile de `run_mc_proba` (vérifié) ; valorisation risque-neutre ou projection client |
| `AUDIT_FRONT_TO_RISK_2026-08-07.md` | 07/08 | RFQ → booking → MtM → Greeks → risque : 6 P1, 13 P2, 6 P3 | Suivi | Revue 05/10 : CORS restreint par défaut ; UAT filtré dans CCR, pas dans les agrégats historiques ; Mode Démo non branché dans les vues inspectées. Autres P2/P3 non revérifiés |
| `AUDIT_CONVENTIONS_PRICING_2026-09-08.md` | 08/09 | Conventions de `CLAUDE.md` mesurées : code conforme, 4 écarts de documentation | Clos selon le rapport | Revue 05/10 : quatre tests A7 existent ; assertions lues, sans nouvelle exécution |
| [REVUE_DOCUMENTAIRE_2026-10-05.md](audits/REVUE_DOCUMENTAIRE_2026-10-05.md) | 05/10 | Confrontation des points de reprise au code et aux tests présents | Lecture statique terminée | Recettes et mesures restant ouvertes distinguées des corrections implémentées |

### `projects/pricing/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `PAYSCRIPT_PARAM_PAR_OBSERVATION.md` | 18/07 | `PARAM()` à une valeur par observation, convention `M_` ; valeur initiale obligatoire depuis le 14/09 | Fait | — |
| `SCRIPTING_IA_DESIGN.md` | 03/08 | Assistant de scripting : référence sous test, fournisseurs (Ollama par défaut), fiche de contrôle, écho d'intention ; phases 0 à 4 codées | Fait | Choisir le modèle local (`backend/scripts/eval_script_assistant.py`) ; aligner le corpus sur le catalogue de modèles |
| `CONSTATATIONS_PERIODE_DESIGN.md` | 10-11/09, suivi 05/10 | MIN/MAX/AVG, PERIOD, INDEX, calendriers et fixings ; theta conserve désormais les métadonnées | En cours | Recette P&L explain/KID et REALVOL à fenêtre de départ ouverte ; theta indisponible sur transitions non résolues |
| `EDITEUR_ECONOMICS_DESIGN.md` | 11/09, suivi 05/10 | Règle « Economics fait foi », validation explicite, EMT effectif et contrôles de PARAM implémentés | En cours | P2 single → schedule, cas null/undefined, autres consommateurs et mode debug différé |
| `MODELES_PRODUITS_DESIGN.md` | 14/09, suivi 05/10 | Ctrl+S, « Valider », maturité et catalogue présents sur main | En cours | Questions du §6.2 et recette UI ; état complet du lot 5 non revérifié |
| [CCR_IMPLEMENTATION_2026-09-28.md](projects/pricing/CCR_IMPLEMENTATION_2026-09-28.md) | 28/09, suivi 05/10 | CCR économique et extensions de préparation MtM / marché commun / deal booké | Code présent | Recette visuelle complète, convergence, taux du jour ; aucune EAD SA-CCR |
| [CCR_UAT_TEST_CLIENT_2026-09-29.md](projects/pricing/CCR_UAT_TEST_CLIENT_2026-09-29.md) | 29/09 | Hypothèses fictives de recette partagées au niveau de Demo ; notes exclues des sets OTC simulés | État de données historique | Base réelle non relue au 05/10 |
| [SA_CCR_PORTEFEUILLE_MIXTE_ROADMAP_2026-09-29.md](projects/pricing/SA_CCR_PORTEFEUILLE_MIXTE_ROADMAP_2026-09-29.md) | 29/09 | Projet futur : classement notes/OTC, portefeuille mixte et SA-CCR equity sans produits de taux | À faire | Lots 0 à 5 ; juridiction, premier produit OTC et qualification des historiques à décider |

### `projects/lifecycle/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `DEAL_LIFECYCLE_2026-07.md` | 17/07 | État des lieux initial : booking, events, repricing | Dépassé | Plan réalisé : MtM résiduel, job quotidien, alertes, preuves de valorisation (`ValuationRun`) |
| `MTM_RESIDUEL_DESIGN.md` | 19/07 | MtM d'un deal vivant : rejeu du passé et Monte Carlo résiduel | Fait | — Prolongé depuis : état complet au Mark-to-Future (01/08), deal non striké (03/09), Pricer avant strike (14/09) |
| `NOTE_VALO_DESIGN.md` | 19/07 | Note de valorisation client en PDF, v1.2 | Fait | v2 : version anglaise, envoi par e-mail |
| `EXPLICATION_VALO_DESIGN.md` | 19/07 | P&L explain entre deux dates, waterfall en PDF | Fait | v2 : effet spot par sous-jacent, ligne rho |
| `SPECIFICATION_REMEDIATION_VAGUE_1_LIFECYCLE_HORS_AMC_2026-07-31.md` | 31/07 | Spécification : quatre yeux sur les fixings, registre officiel, rejeu borné, application atomique | Fait | Réalisée par les trois rapports suivants |
| `IMPLEMENTATION_RFQ_BOOKING_LIFECYCLE_PHASE_0_1_2026-07-31.md` | 31/07 | Contrôles RFQ, booking gate, statuts de fixing, audit persistant | Fait | Risques résiduels repris par la phase 2 |
| `RAPPORT_IMPLEMENTATION_LOT_1_FIXING_LIFECYCLE_HORS_AMC_2026-07-31.md` | 31/07 | Registre immuable des fixings, pièces sources, décision Checker, application atomique | Fait | Durcissement (§5) : stockage chiffré des pièces, référentiel fournisseurs, migrations versionnées, tests E2E, identifiant de corrélation |
| `IMPLEMENTATION_RFQ_BOOKING_LIFECYCLE_PHASE_2_2026-07-31.md` | 31/07 | Rejeu officiel, sémantique KI/final, amendements maker-checker, consultation de l'audit | Fait | Source officielle de chemin, annulation/remplacement, propagation aval, file Checker |
| `DECLINAISONS_POINTS_OUVERTS.md` | 29/08 | Trois manques autour des variantes (avenant, roll) | À faire | Coût de débouclage, gel d'une proposition, traçabilité ; deux questions à trancher. Rien de codé (vérifié) |

### `projects/clients/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `CLIENTS_LOT_0_DOCTRINE_METIER.md` | 01/09 | Doctrine métier, vocabulaire, règles d'autorité | Fait | — |
| `CLIENTS_LOT_1_CHAINE_COMMERCIALE.md` | 02/09 | Contexte Client facultatif dans Produit → RFQ → Deal, recette acceptée | Fait | — |
| `CLIENTS_LOT_2_HABITUDES_TRADING.md` | 02/09 | Habitudes de trading et sélection des fournisseurs ; implémenté le 03/09 | Fait | L'en-tête dit encore « à valider avant codage » : le §18 fait foi |
| `CLIENTS_LOT_3_INTEGRATION_LIFECYCLE.md` | 05/09 | Événements des deals exploitables depuis le module Clients | Fait | — |

### `projects/platform/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `PLAN_IMPLEMENTATION_OBJET_PRODUCT.md` | 14/09, suivi 05/10 | Dossier canonique présent sur main : RFQ/indicatif/booking/lifecycle/MtM/VaR/documents ; création interne aux gestes durables | En cours | Reprise historique et consolidation des consommateurs secondaires ; aucun repli MtM/VaR pour un deal sans Product |
| [ORGANIZATION_ACCESS_DESIGN_2026-09-24.md](projects/platform/ORGANIZATION_ACCESS_DESIGN_2026-09-24.md) | 24/09, suivi 05/10 | Admission, propriété par organisation, habilitations et desks | Cadrage, non implémenté | Invitations, approbations, migration, isolation et recette |
| `HOME_REDESIGN_DESIGN.md` | 19/07 | Accueil en quatre catégories, drill-down | Fait | — |
| `DEPLOIEMENT_ONPREM.md` | 25/07 | Un serveur par client, sous Windows | À faire | Installeur, service Windows, sauvegarde de la base, mises à jour, journaux, cinq questions ouvertes. Fait depuis : secret JWT propre à chaque machine (02/08) |
| `FRED_INTEGRATION_ROADMAP.md` | 29/08 | Données FRED pour la VaR, les scénarios, les régimes et les backtests | À faire | Décisions du §11 ; rien de codé (vérifié) |
| `SOURCES_DONNEES_TAUX_OPTIONS.md` | 29/08 | Sources gratuites de taux et d'options | À faire | Feuille de route en quatre phases |

### `projects/studies/`

Les états du 21/09 ci-dessous sont historiques : la recette UI et les corrections
du 22/09 les prolongent. Ils ne signifient pas qu'aucune recette n'a eu lieu depuis.

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| [COMPTE_RENDU_RECETTE_UI_2026-09-22.md](projects/studies/COMPTE_RENDU_RECETTE_UI_2026-09-22.md) | 22/09 | Recette A–K du jeu long-only, sauvegarde et contrôles financiers | Exécution historique consignée | Constats repris dans les corrections suivantes |
| [CORRECTIONS_RECETTE_2026-09-22.md](projects/studies/CORRECTIONS_RECETTE_2026-09-22.md) | 22/09 | Méthode 2.5 : IA, PDF, turnover, affichage et frais/HWM | Code 2.5 confirmé au 05/10 ; résultats de septembre non rejoués | Limites des autres jeux et annexes PDF non intégralement inspectées |
| [STUDIES_DIVIDENDS_2026-09-21.md](projects/studies/STUDIES_DIVIDENDS_2026-09-21.md) | 21/09 | Studies 2.2 : dividendes par titre, créances, fiscalité, réinvestissement et contrôles | Livré ; 79 tests backend ciblés, 194 frontend et build réussis | Recette UI ; distributions investisseurs et calendriers contractuels étendus ultérieurs |
| [STUDIES_INTERFACE_2026-09-21.md](projects/studies/STUDIES_INTERFACE_2026-09-21.md) | 21/09 | Configuration en pleine largeur, tableaux et indicateurs harmonisés | 194 tests frontend ; build réussi | Recette visuelle dans le navigateur utilisateur |
| [STUDIES_EXISTING_FIXES_2026-09-21.md](projects/studies/STUDIES_EXISTING_FIXES_2026-09-21.md) | 21/09 | Méthode 2.4 : calculs, sources et restitution des blocs existants | Tests ciblés et recette indépendante | Guide des corrections et résultats attendus |
| [STUDIES_SETUP_COMPLET_2026-09-21.md](projects/studies/STUDIES_SETUP_COMPLET_2026-09-21.md) | 21/09 | Un dossier autonome : scan et lancement A à K, référence E/G séparée | Blocs calculés hors réseau ; 85 comparaisons | Recette utilisateur ; 85/85 comparaisons conformes en méthode 2.4 |
| [STUDIES_EXTENDED_REFERENCE_2026-09-21.md](projects/studies/STUDIES_EXTENDED_REFERENCE_2026-09-21.md) | 21/09 | Référence indépendante A–K, TS et import isolé E, benchmark synthétique | Banc isolé : 82/85 contrôles conformes | Recette E dans l’UI ; trois écarts F/J ; import de marchés complet |
| [STUDIES_RECONCILIATION_AND_FEES_2026-09-21.md](projects/studies/STUDIES_RECONCILIATION_AND_FEES_2026-09-21.md) | 21/09 | Studies 2.1 : frais paramétrables, dividendes, valorisation sur relevé, FIFO et recette indépendante | Corrigé ; 55 tests backend ciblés, 194 frontend et build réussis | Redémarrage utilisateur et nouvelle recette UI ; frais complexes/égalisation ultérieurs |
| [INDEPENDENT_LONG_ONLY_DATASET_2026-09-21.md](projects/studies/INDEPENDENT_LONG_ONLY_DATASET_2026-09-21.md) | 21/09 | Fonds fictif 2020–2025, CSV, FX BCE et comptabilité indépendante | Données générées et contrôlées | Test Studies par Philippe, comparaison puis diagnostic ; flux investisseurs et long/short ultérieurs |
| `DECISION_ANALYSIS_ENGINE.md` | 26/06 | Qualité des décisions d'un gérant AMC | À faire | Idée validée ; fichier non versionné (`.gitignore`) |
| `MANAGER_DNA_ENGINE.md` | 26/06 | Empreinte quantitative du style de gestion | À faire | Idée validée ; fichier non versionné |
| `SKILL_VS_LUCK_ENGINE.md` | 16/07 | Talent ou hasard, par bootstrap et Monte Carlo | À faire | Idée validée ; fichier non versionné |
| `STUDY_COMPARISON_ENGINE.md` | 16/07 | Comparer deux études du même AMC | À faire | Trois points à trancher |

### `reference/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `PAYSCRIPT_REFERENCE.md` | 03/08, revue le 14/09 | Référence du langage ; corps du prompt de l'assistant IA, lu par `services/llm/prompt.py` ; vocabulaire comparé au parser par `test_payscript_reference.py` | Référence | À mettre à jour à chaque évolution du langage |
| `GOUVERNANCE_AMENDEMENTS.md` | 07/08 | Amendement d'un deal booké : machine à états, garanties, seconde signature désarmée par défaut | Référence | Procédure de réarmement au §4 |
| `FIFO_MODULE.md` | 16/07 | Reconstruction FIFO d'un carnet d'ordres AMC | Référence | Décomposition prix/FX du lot T0 non corrigée ; écart de +23 % contre la NAV à expliquer ; autres AMC non testés |

### `lessons/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `PORTFOLIO_RECONCILIATION_LESSONS.md` | 16/07 | Pièges de la réconciliation FIFO contre NAV, avec checklist | Historique | Défaut prix/FX du lot T0 (§8) |
| `POSTMORTEM_2026-07-16_CH1352587724_PNL_RECONCILIATION.md` | 16/07 | Post-mortem de la réconciliation de CH1352587724 | Historique | Positions fantômes non résolues (§5) ; vérifier les études livrées avant le correctif de pricing des déficits |

### `handoffs/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `REPRISE_BOOKING_2026-07-19.md` | 18/07 | Booking, cycle de vie automatique, `PARAM()` | Historique | Traité depuis : sous-jacents complétés à la réouverture, `reload=False`, job quotidien, MtM résiduel |
| `REPRISE_2026-07-21.md` | 21/07 | Données de marché en administration, onglets Booking | Historique | — |
| `REPRISE_2026-07-27.md` | 27/07 | Deals de démo, exposition, VaR/ES, calcul parallèle | Historique | Écran VaR à tester en réel, méthodologie à challenger, calibration paramétrique recalculée à chaque étude ; bornes du formulaire ajoutées depuis (vérifié) |
| `REPRISE_2026-07-30.md` | 30/07 | Audits RFQ, défauts de booking | Historique | Arbitrage du ténor du Pricer, mineurs RFQ, module Réinvestissement non reconfirmé ; nettoyage des deals sans objet, la base ne contient que des tests |
| `REPRISE_2026-08-27.md` | 26-27/08 | Appels d'offres, conventions de dates, cours nus, dividendes, funding, note Marex | Historique | Champ repo et agrégation du spread au book (vérifié absents) ; deux conventions de maturité RFQ et Deal ; liste « À vérifier ». Fait depuis : calibration datée (`load_hist_vol(asof=…)`) |

### `archive/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `OLD_AVANCEMENT.md` | 27/06 | État du projet AMC | Archivé le 16/07 | Ne pas s'y fier |
| `OLD_REPRISE_TRAVAIL.md` | 26/06 | Fiche technique AMC, blocs A à J | Archivé le 16/07 | Deux formules fausses, signalées en tête |
