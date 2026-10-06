# Revue documentaire de reprise — 5 octobre 2026

## Périmètre et niveau de preuve

Relecture de `AGENTS.md`, `CLAUDE.md`, de l'index et des notes de chantier,
confrontée au code de `main`, commit `15d7ccf` du 02/10/2026. L'objectif est de
corriger les états documentaires périmés, sans modifier le comportement applicatif.
Les chemins ci-dessous sont relatifs à la racine du dépôt.

**Preuve : lecture statique des implémentations, des appels et des assertions de
tests concernés.** Aucun pytest, build, serveur, navigateur, calcul financier ou
accès à `backend/data/structura.db` n'a été lancé. Les tests cités existent ; leur
réussite actuelle n'est pas revendiquée. Les résultats chiffrés de septembre
restent des résultats historiques consignés dans les notes.

Cette revue couvre les points de reprise et les contradictions identifiées dans
l'index. Elle ne remplace ni un audit exhaustif de sécurité, ni une validation
quantitative, ni la recette de l'ensemble des modules. Les audits anciens sont
conservés comme constats datés ; les conclusions actuelles sont précisées ici.

## Corrections confirmées

| Sujet | État constaté au 05/10 | Preuve dans le dépôt |
|---|---|---|
| État Git | Product, modèles et CCR présents sur `main` ; les mentions « non commité » de septembre ne décrivent plus le dépôt. Aucun fichier suivi modifié avant cette revue. | Historique Git, HEAD `15d7ccf` ; `core/product/`, `api/products.py`, `ProductModelsView.vue`, `core/ccr/` |
| Product : intégrations | RFQ, indicatif, booking, lifecycle, MtM/VaR, KID, EMT et documents utilisent ou enrichissent le dossier. Ces lots ne sont plus tous « à faire ». | `backend/app/api/{rfq,indicatives,deals,kid,emt,documents}.py`, `services/product_lifecycle.py`, `core/{deal_valuation,var_engine}.py` |
| Product : création | Exploration temporaire ; création interne lors d'un geste métier durable si nécessaire. `listed=False` distingue ce dossier de la conservation visible en bibliothèque. | `services/product_repository.py::stage_internal_product`, appels depuis RFQ/indicatif/booking ; `api/products.py` ; `test_products.py` |
| Product : historiques | Pas de repli automatique pour un deal sans Product : MtM refuse, VaR exclut avec `DEAL_PRODUCT_MISSING`. La migration des dossiers historiques reste nécessaire. | `core/deal_valuation.py::mtm_core`, `core/var_engine.py::build_deal_scenario_base` |
| Product : immutabilité | Triggers de lien obligatoire et immuable ; versions/révisions/calculs protégés. Exception de suppression des preuves pour les Products explicitement UAT. | `db/product_migrations.py::migrate_product_links`, tests des triggers dans `test_products.py` |
| Authentification | Les routeurs Pricing, Simulation et Scénarios portent `Depends(get_current_user)`. Les quatre routes Schedule n'en portent pas. L'ancien total de 25 routes publiques est périmé. | `api/{pricing,simulation,scenarios,schedule}.py`, inclusions dans `main.py` |
| CORS et inscription | Origines locales par défaut, surcharge `STRUCTURA_CORS_ORIGINS`. Inscription publique fermée par défaut ; si activée, le repli Demo et le choix/création d'entité persistent. | `main.py`, `api/auth.py::register` |
| EMT / Economics | Le levier lit les paramètres effectifs ; la réponse inclut `effective_parameters`, prioritaires dans le texte de synthèse. | `api/emt.py::_detect_features`, `emt_compute`, `core/emt_synthesize.py`, `test_emt.py::test_le_levier_emt_lit_la_valeur_economique_saisie` |
| PARAM vidé | `_buildUserParams` refuse chaînes vides, tableaux vides et valeurs non numériques ; `null`/`undefined` peuvent encore reprendre le défaut via `??`. Le constat « aucun champ vidé ne bloque » était trop large. | `frontend/src/stores/pricing.js::_buildUserParams` |
| Theta / fenêtres | `_age_compiled_script` conserve paiements, fenêtres, rangs et relevés passés. Une transition d'observation/fenêtre non résolue rend le theta indisponible avec motif. | `core/payscript/engine.py::_age_compiled_script`, `_theta_and_event` ; `test_greeks_stateful.py`, `test_settlement_discounting.py` |
| Origine des temps A7 | Quatre fonctions de test, certaines paramétrées, couvrent horizon résiduel, dates des flux, passé depuis le strike et évolution de la frontière. Le test n'est plus à écrire. | `backend/tests/test_inlife_pricing.py::test_A7_*`, assertions lues |
| RFQ à fenêtre | Les helpers locaux de `RfqView.vue` omettent les champs de fenêtre, mais l'API reprend les termes du Product lorsqu'il est fourni. Pas de preuve d'un refus systématique de toutes les RFQ à fenêtre. | `RfqView.vue::{buildConstatsPayload,restoreConstatOverrides}`, `api/rfq.py::create_rfq` |
| CCR / UAT | L'API et le service CCR filtrent explicitement Production/UAT ; les routes historiques Portfolios/Shocks/VaR ne portent pas ce filtre. | `api/ccr.py`, `core/ccr/service.py`, lecture des sélections de `api/{portfolios,shocks,var}.py` |
| CCR livré | Socle et extensions de préparation MtM, marché commun, cache/progression et contrôle du deal booké présents ; contrôle serveur appelé au booking. | `core/ccr/{service,preparation,common_market,cache}.py`, `api/ccr.py`, `api/deals.py`, `CcrCreditCheck.vue`, route `/risk/ccr` |
| CCR : hypothèses | Projection jointe GBM ; préparation avec taux commun provisoire de 3 %, qualifié, remplaçable. Le panneau du deal booké transmet explicitement `.03`. | `core/ccr/service.py`, `core/ccr/contracts.py`, `CcrCreditCheck.vue`, sections CCR 1.2 du rapport du 28/09 |
| SA-CCR | Aucun calcul réglementaire livré : réponse `regulatory.ead=None`, statut `NOT_APPLICABLE`. Une métrique de limite `ead` existe, sans moteur SA-CCR. | `core/ccr/service.py`, `contracts.py`, `exposure.py` |
| Organisations | `User.entity_id` et rôle global ; contrôle Product encore fondé sur propriétaire utilisateur/admin. Les scripts partagés dépendent encore de l'entité actuelle de leur auteur. Le modèle d'admission/habilitations cible reste à faire. | `db/models.py::{Entity,User}`, `services/product_repository.py::owned_record`, `api/scripts_db.py`, `api/auth.py` |
| Studies | Méthode active `studies-2.5`. Une recette UI et ses corrections existent au 22/09 ; l'index arrêté aux recettes restantes du 21/09 les omettait. | `core/amc_controls.py::METHOD_VERSION`, notes `COMPTE_RENDU_RECETTE_UI_2026-09-22.md` et `CORRECTIONS_RECETTE_2026-09-22.md` |

## Points restant ouverts ou à requalifier

| Point | Conclusion et limite |
|---|---|
| Durcissement HTTP | Pas de middleware global CSP/X-Frame-Options identifié dans `main.py`. Un `nosniff` local existe dans `api/deals.py`. Aucune configuration de reverse proxy inspectée. |
| Mode Démo | Pas de branchement identifié dans BookingView, EventsTab, RfqView, RiskManagementView. Aucune recette visuelle réalisée ici. |
| Spread au book | Pas d'agrégation du greek crédit dans `api/portfolios.py`, alors qu'il existe au niveau moteur. |
| Vega Heston/LSV | `vega_scope` annonce toujours `leg_independante` et sa couverture ; aucun vega de recalibration démontré. |
| Mark-to-Future | Pricer : 200 scénarios extérieurs par défaut et grille uniforme via `build_mtf_dates`. Dates explicites possibles pour d'autres consommateurs ; CCR enrichit sa grille. Quantiles MTF interpolés avec `np.quantile`, quantiles de `run_mc_proba` toujours indexés dans la liste triée. |
| Pont brownien | Le chiffre −14,3 % vient des audits d'août. Le moteur porte une note d'approximation ; cette lecture ne reproduit ni ne clôture l'écart historique. Une mesure comparable est nécessaire. |
| Repo / FRED | Aucun champ dédié de coût d'emprunt repéré dans les entrées moteur/UI, ni intégration FRED dans `backend/app` / `frontend/src`. Les feuilles de route restent ouvertes. |
| CONSTAT / Economics | `_syncConstatOverrides` traite les changements de réduction et le retour à single ; la promotion single → schedule reste incomplète. Recette requise avant correction. |
| Fenêtres / analyses | Pas de validation nouvelle de P&L explain, KID ou REALVOL en cours de vie avec fenêtre de départ ouverte. Ne pas étendre la correction du theta à ces chemins. |
| Déclinaisons | Les API/core de variantes inspectés n'ajoutent pas le coût de débouclage ni le gel d'une proposition client décrits dans la note. L'existence de filiation/tests de variantes ne clôture pas ces trois demandes métier. |
| VaR | La formule « jamais testé/challengé » n'est pas soutenable depuis la seule reprise de juillet. Les évolutions et tests actuels demandent une revue propre ; aucune homologation implicite. |
| CCR | Recette visuelle complète, convergence et raccordement du taux courant restent ouverts. Les chiffres UAT et l'état de migration de la base réelle n'ont pas été revérifiés. |
| Autres lots | Les mineurs RFQ du 30/07, le déploiement, les sources de taux/options, les quatre moteurs Studies et les questions métier des catalogues ne sont pas clôturés par cette revue. |

## Documents mis à jour et vérification

L'index, la note Product, les notes Economics/modèles/fenêtres, les états
CCR/SA-CCR/organisations et l'audit A7 renvoient désormais à cette revue ou portent
un état daté. Les notes de recette Studies du 22/09 sont ajoutées à l'index.
Les anciens rapports conservent leurs mesures et leur contexte de session.

Validation documentaire : revue du diff, contrôle des liens relatifs introduits
et `git diff --check`. Aucun fichier applicatif modifié, aucune donnée métier
ouverte ou changée, aucun commit/push. Aucun test applicatif requis pour cette
modification exclusivement documentaire, conformément à `CLAUDE.md`.
