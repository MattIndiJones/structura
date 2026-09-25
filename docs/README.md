# Notes du projet Structura

Toutes les notes de travail du dépôt, rangées par nature. Chaque note garde son nom
d'origine : seul son dossier a changé, le 14/09/2026. Les états ci-dessous datent de ce
jour. Quand une ligne porte « vérifié », le point a été contrôlé dans le code le 14/09 ;
sinon, l'état est celui que rapporte la note ou celle qui l'a prolongée.

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

Organisations et accès : [Cadrage de l'admission et des habilitations](projects/platform/ORGANIZATION_ACCESS_DESIGN_2026-09-24.md)
— **À faire, développement différé**. Plateforme commune et installation client ; propriété des données par l'organisation actée ; invitations, approbations, migration et recette à préparer.

Dernière correction Pricing : [Authentification des appels et erreurs de validation](projects/pricing/PRICING_AUTHENTIFICATION_2026-09-24.md)
— 30 appels harmonisés ; 217 tests frontend et build réussis ; pricing initial et profil de payoff vérifiés dans le navigateur.

Studies : [Audit métier et technique du 20/09/2026](audits/AUDIT_STUDIES_2026-09-20.md)
— constats initiaux ; corrections et contrôles décrits dans le [processus Studies](projects/studies/STUDIES_PROCESS_ET_CORRECTIONS_2026-09-20.md), avec limites de données et extensions restantes.
[Pitch de partenariat consulting](projects/studies/STUDIES_CONSULTING_PITCH_2026-09-20.md)
— préparation du rendez-vous du 23/09 : argumentaire, démonstration et pilote accompagné.

IA : [Socle commun aux cinq assistants](projects/platform/IA_COMMUNE_2026-09-17.md)
— implémenté le 17/09/2026 ; catalogue, éditeur de prompt et suivi partagés ; activation après redémarrage du backend.

Nouveau module Life Cycle : [Valo Explain — édition, comparaison et PDF figés](projects/lifecycle/VALO_EXPLAIN_2026-09-17.md)
— implémenté le 17/09/2026 ; activation au prochain démarrage du backend local.

Dernière correction Booking : [MtM quotidien et progression du calcul](projects/lifecycle/BOOKING_MTM_QUOTIDIEN_2026-09-17.md)
— implémenté le 17/09/2026 ; activation serveur après redémarrage du backend local.

### Avant toute ouverture hors du poste local

- 25 routes répondent sans authentification : `api/pricing.py` (18), `api/schedule.py`
  (4), `api/simulation.py` (2), `api/scenarios.py` (1). Vérifié.
- CORS ouvert à toute origine, avec credentials (`main.py`). Vérifié.
- L'inscription rattache par défaut à l'entité « Demo », celle des comptes réels
  (`api/auth.py`). Vérifié.
- Aucun en-tête de durcissement HTTP global (CSP, `X-Frame-Options`…). Vérifié.

Sources : audit de production du 31/07, audit du 02/08, contre-expertise du 11/09 (F01).

### Risque et portefeuille

- Les deals UAT entrent dans l'exposition, les limites et les agrégats : `uat_batch_id`
  n'est lu ni par `portfolios.py`, ni par `shocks.py`, ni par `var.py`. Vérifié.
- Le Mode Démo ne masque rien sur Booking, Events, RFQ et Risk Management. Vérifié.
- La sensibilité au spread émetteur n'est pas agrégée au niveau du book. Vérifié.
- L'écran VaR n'a jamais été testé en conditions réelles et sa méthodologie n'a jamais
  été challengée (reprise du 27/07).

### Moteur

- Monitoring continu par pont brownien : −14,3 % sur une barrière proche, signalé à
  l'écran, non corrigé (audits du 01/08 et du 02/08).
- Vega Heston : la couverture est annoncée par `vega_scope`, sans vega sur les paramètres
  calibrés.
- Mark-to-Future : `n_outer` à 200 par défaut, grille de dates uniforme non calée sur les
  observations, quantiles de `run_mc_proba` sans interpolation. Vérifié.
- Pas de champ repo distinct du rendement de dividende `q`. Vérifié.
- Constatations sur période : theta (`_respan` perd fenêtres, rangs et paiements), P&L
  explain et KID ; `REALVOL` d'un deal vivant à fenêtre de départ ouverte, non sondé.
- Mesurer par un test l'origine des temps en cours de vie (règle A7, audit du 08/09).

### Éditeur, Economics et modèles

- L'EMT lit encore la valeur du script : levier sur `stored_val` (`api/emt.py`), texte sur
  `raw_default` (`core/emt_synthesize.py`), contrairement à « Economics fait foi ».
  Vérifié. Les autres lecteurs relevés le 11/09 sont à revérifier.
- Changement de forme d'un CONSTAT (P2 du 11/09) ; un champ vidé ne bloque pas le calcul.
- Modèles de produits : questions ouvertes du §6.2 et vérification à l'écran après
  redémarrage du backend.
- Mode debug : dernière priorité, à redemander avant de le coder.

### Cycle de vie et RFQ

- Source officielle de chemin pour les produits path-dependent, annulation et
  remplacement d'un deal, propagation aval (confirmations, comptabilité), file Checker
  dédiée, identifiant de corrélation (rapports du 31/07).
- Déclinaisons : coût de débouclage, gel d'une proposition client, traçabilité. Aucune
  trace dans l'API des variantes. Vérifié.
- L'écran RFQ ne saisit aucune fenêtre de constatation (MIN/MAX/AVG) : une RFQ sur un tel
  script ne peut pas la figer, et le booking la refusera dès que le Pricer en envoie une.
  Vérifié : aucune gestion de fenêtre dans `RfqView.vue`.
- Mineurs RFQ du 30/07 : nom d'AO vide et script non compilable acceptés par le serveur,
  mode Expert détecté par la seule chaîne `CONSTAT`, devise de cotation morte,
  numérotation globale des références, conversion indicatif → to trade sans lien avec
  l'AO d'origine, cotation ajoutable après booking. Non revérifiés.

### Chantiers non commencés ou à poursuivre

- Objet Product : lots RFQ, booking et portefeuille, cycle de vie, risk et documents,
  reprise historique.
- Déploiement on-premise : installeur, service Windows, sauvegarde de la base, mises à
  jour, journaux.
- Données de marché : FRED, taux officiels, données d'options.
- Études AMC : quatre moteurs en feuille de route ; FIFO, décomposition prix/FX du lot T0.

### Travaux sans fichier dans le dépôt

Pages publiées : contre-expertise de l'audit externe du 11/09 (P0 retenus F01, F03, F06,
F14, F20, F28 ; arbitrages A0 à A10 en attente), audit qualité du 30/08, analyse SaaS du
11/09, étude de l'objet Product du 13/09, plan Client Intelligence du 31/08.

## En cours, non commité (14 et 15/09)

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

Le backend doit être redémarré pour que ces changements soient actifs.

## Détail par dossier

### `audits/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `AUDIT_PRICING_2026-07.md` | 17/07 | Moteur Monte Carlo : 9 défauts corrigés le jour même, puis barrières continues, Heston/SABR vectorisés, backtest intra-période | Clos | Mémoire non bornée à N élevé ; transpileur fondé sur `exec` (assumé) |
| `AUDIT_RFQ_2026-07-29.md` | 29/07 | Module RFQ, 6 constats | Clos le 30/07 | Voir les mineurs de l'audit du 30/07 |
| `TESTING_JOURNAL.md` | 29/07 | Journal de l'agent client-tester : pricing, booking, cycle de vie, RFQ | Clos | Sélecteur d'exemples sans confirmation visuelle, jugé mineur |
| `AUDIT_CHAINE_RFQ_2026-07-30.md` | 30/07 | Chaîne RFQ → pricing → booking, 9 constats | Clos | Mineurs du §10 ; ténor du Pricer contre calendrier, à revoir avec la règle de maturité du 14/09 |
| `AUDIT_COMPLET_PRICING_RFQ_LIFECYCLE_2026-07-31.md` | 31/07 | Audit fonctionnel et quantitatif, 11 P0, NO-GO | Dépassé | Repris par les audits du 01/08, du 02/08 et du 07/08 |
| `AUDIT_PRODUCTION_COMPLET_HORS_AMC_2026-07-31.md` | 31/07 | Production : sécurité, performance, pricing, lifecycle, KID, NO-GO | Suivi | Routes publiques, CORS, inscription, en-têtes de durcissement HTTP absents (vérifié). Existe depuis : budget de calcul par requête (`core/compute_budget.py`) |
| `AUDIT_QUANTITATIF_COMPLET_HORS_AMC_2026-07-31.md` | 31/07 | 40 constats quantitatifs, dont 12 critiques | Dépassé | Repris par la vague 1 du 31/07 et l'audit du 01/08 |
| `AUDIT_QUANTITATIF_2026-08-01.md` | 01/08 | Revérification : 6 bloquants sur 12 fermés | Dépassé | Repris par l'audit du 02/08 |
| `AUDIT_COMPLET_2026-08-02.md` | 02/08 | 20 constats rejoués ; lots 1 et 2 corrigés : secret JWT, FX manquant, backward fill, horizons et rendement du KID, facteur de taux, IRR, VaR | Suivi | Lots 3 et 4 : pont brownien, vega Heston, grille hebdomadaire du Monte Carlo, en-têtes HTTP et CORS ; saturation de la vol locale à revérifier depuis la reformulation de Dupire du 03/09 |
| `AUDIT_MTF_2026-08-03.md` | 03/08 | Mark-to-Future : 5 défauts corrigés (double comptage, STRIKE_FIX, courbe, quantile, date proche) | Suivi | `n_outer` par défaut, grille de dates, quantile de `run_mc_proba` (vérifié) ; valorisation risque-neutre ou projection client |
| `AUDIT_FRONT_TO_RISK_2026-08-07.md` | 07/08 | RFQ → booking → MtM → Greeks → risque : 6 P1, 13 P2, 6 P3 | Suivi | Fermés : taux figé à 0, exposition entre maturité et règlement, reprise du job quotidien, politique de fixing FOUR_EYES, alerte de rappel unique. Ouverts : deals UAT dans le risque, Mode Démo, CORS (vérifié) ; P2 et P3 restants non revérifiés |
| `AUDIT_CONVENTIONS_PRICING_2026-09-08.md` | 08/09 | Conventions de `CLAUDE.md` mesurées : code conforme, 4 écarts de documentation | Clos | Recommandations 1 et 2 appliquées dans `CLAUDE.md` ; mesure de la règle A7 |

### `projects/pricing/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
| `PAYSCRIPT_PARAM_PAR_OBSERVATION.md` | 18/07 | `PARAM()` à une valeur par observation, convention `M_` ; valeur initiale obligatoire depuis le 14/09 | Fait | — |
| `SCRIPTING_IA_DESIGN.md` | 03/08 | Assistant de scripting : référence sous test, fournisseurs (Ollama par défaut), fiche de contrôle, écho d'intention ; phases 0 à 4 codées | Fait | Choisir le modèle local (`backend/scripts/eval_script_assistant.py`) ; aligner le corpus sur le catalogue de modèles |
| `CONSTATATIONS_PERIODE_DESIGN.md` | 10-11/09 | MIN/MAX/AVG par sous-jacent, `PERIOD`, `INDEX` par échéancier, échéancier contractuel, fixings des relevés, lecture par date, Mark-to-Future ; §1 à §24 commités | En cours | Theta, P&L explain, KID (§14) ; `REALVOL` à fenêtre de départ ouverte (§24) |
| `EDITEUR_ECONOMICS_DESIGN.md` | 11/09 | Règle « Economics fait foi », décisions D1 à D8, lots 0 à 3 | En cours | Lot 1 codé le 14/09 (note suivante). Restent P2, champ vidé bloquant, lot 2 (EMT vérifié), lot 3 en attente |
| `MODELES_PRODUITS_DESIGN.md` | 14/09 | Ctrl+S et « Valider », maturité = dernière constatation, catalogue de 19 fiches, module « Modèles de produits » ; lots 1 à 4 codés | En cours | Non commité ; questions du §6.2 ; lot 5 : exemples Normal et Expert, scripts UAT, corpus de l'assistant, guide d'ajout d'un payoff |

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
| `PLAN_IMPLEMENTATION_OBJET_PRODUCT.md` | 14/09 | Objet `Product` transverse ; première tranche livrée sur `codex/product-workflow` : conservation explicite, bibliothèque « Mes Produits », reçus de calcul signés | En cours | Lots du §9 : RFQ, booking et portefeuille, cycle de vie, risk et documents, reprise historique ; sauvegarde automatique aux gestes engageants non tranchée |
| `HOME_REDESIGN_DESIGN.md` | 19/07 | Accueil en quatre catégories, drill-down | Fait | — |
| `DEPLOIEMENT_ONPREM.md` | 25/07 | Un serveur par client, sous Windows | À faire | Installeur, service Windows, sauvegarde de la base, mises à jour, journaux, cinq questions ouvertes. Fait depuis : secret JWT propre à chaque machine (02/08) |
| `FRED_INTEGRATION_ROADMAP.md` | 29/08 | Données FRED pour la VaR, les scénarios, les régimes et les backtests | À faire | Décisions du §11 ; rien de codé (vérifié) |
| `SOURCES_DONNEES_TAUX_OPTIONS.md` | 29/08 | Sources gratuites de taux et d'options | À faire | Feuille de route en quatre phases |

### `projects/studies/`

| Note | Date | Objet | État | Reste à faire |
|---|---|---|---|---|
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
