# Catalogue des modules

Inventaire de structure, pas attestation d'exécution ni lecture sémantique exhaustive.
Les descriptions ci-dessous proviennent des docstrings de la source et peuvent être historiques. Le rapport principal arbitre les points revérifiés.

## Backend applicatif

### backend/app/__init__.py

0 lignes ; SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

### backend/app/api/__init__.py

0 lignes ; SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

### backend/app/api/admin.py

1017 lignes ; SHA-256 `f576230c427582fcbfc89cf36939f3e81793aa6619e17d636b49f50d60e98a60`.

Generic administration endpoints — admin-only. Covers the RFQ provider catalog, the generic read-only+delete data browser (core/admin_registry.py), and Users/Entities CRUD, all gated by get_current_admin.

Fonctions : `_hash_pw:35`; `_contact_row:68`; `_row:75`; `_cpty_names:91`; `uat_generator_config:98`; `uat_generator_batches:106`; `uat_generator_preview:114`; `uat_generator_create:123`; `uat_generator_delete:132`; `list_rfq_providers:143`; `create_rfq_provider:153`; `update_rfq_provider:175`; `delete_rfq_provider:206`; `list_rfq_provider_contacts:224`; `create_rfq_provider_contact:237`; `update_rfq_provider_contact:260`; `_validate_reference_limit:304`; `_cpty_row:310`; `list_counterparties:323`; `create_counterparty:332`; `update_counterparty:353`; `delete_counterparty:400`; `browse_tables:420`; `browse_table_rows:425`; `_refuse_scoped_rfq_admin:436`; `browse_get_row:442`; `browse_delete_row:453`; `browse_delete_rows:468`; `browse_update_row:490`; `_user_row:519`; `list_users:529`; `create_user:541`; `update_user:569`; `_managed_user:609`; `revoke_sessions:617`; `reset_password:627`; `_entity_row:650`; `list_entities:655`; `create_entity:667`; `update_entity:688`; `market_data_catalog:792`; `market_data_fetch:816`; `_underlying_row:853`; `list_underlyings:863`; `search_underlyings:875`; `create_underlying:887`; `update_underlying:946`; `delete_underlying:988`; `revalidate_underlying:1006`

Classes : `RfqProviderCreate:41`; `RfqProviderUpdate:47`; `RfqContactCreate:57`; `RfqContactUpdate:62`; `CounterpartyCreate:291`; `CounterpartyUpdate:297`; `BrowseDelete:463`; `UserCreate:503`; `UserUpdate:512`; `PasswordReset:604`; `EntityCreate:642`; `EntityUpdate:646`; `MarketDataFetchRequest:810`; `UnderlyingCreate:836`; `UnderlyingUpdate:845`

### backend/app/api/agent_workshop.py

198 lignes ; SHA-256 `0674ad899b23e762be36426d50733368b76ca54036cdf68ad8ba4818eda3b696`.

Fonctions : `controller_only:15`; `owned:24`; `listing:34`; `models:44`; `create:69`; `defaults:75`; `preview_scenario:81`; `configure:88`; `detail:97`; `command:102`; `open_consultation:134`; `close_consultation:145`; `review_issue:156`; `delete:169`; `export:179`; `screenshot:186`

Classes : `IssueReview:116`

Variables d'environnement lues : `STRUCTURA_WORKSHOP_CHILD`

### backend/app/api/alerts.py

127 lignes ; SHA-256 `5f0a25c314ab6a5cc20fce5cdc89a76850c74685f59d59be2f4f12170826776e`.

Lifecycle/barrier alerts raised by the daily refresh — list, mark read, and manual whole-book refresh (the UI's 'Rafraîchir le book' button).

Fonctions : `_admin:17`; `_visible_alerts:21`; `_unread:27`; `_mark_read:34`; `_alert_row:42`; `list_scheduler_runs:55`; `list_alerts:76`; `mark_read:93`; `mark_all_read:108`; `refresh_whole_book:122`

### backend/app/api/amc.py

382 lignes ; SHA-256 `65d7f9722a1bd93cf8a339e0654f695bebabca58ea166273568e94fa582e94a9`.

AMC Fama-French analysis — REST endpoints.

Fonctions : `list_ff_series:39`; `get_ff_status:44`; `refresh_ff:50`; `list_benchmarks:66`; `upload_amc:71`; `analyze:104`; `export_pdf:130`; `get_synthesis_payload:170`; `synthesis_prompt:185`; `preview_synthesis:194`; `synthesize_study:199`; `get_ollama_models:211`; `study_doc:246`; `study_template:252`; `study_detect:258`; `compute_manager_skill:285`; `compute_market_shocks_endpoint:306`; `study_run:334`; `study_export_pdf:356`

Classes : `AnalyzeRequest:86`; `ExportPdfRequest:98`; `SynthesizeRequest:157`; `StudyRunRequest:226`; `StudyExportRequest:231`; `ManagerSkillRequest:279`; `MarketShocksRequest:300`

### backend/app/api/amc_access.py

44 lignes ; SHA-256 `48d2467ba893546eebee16385ccaca34887bb4617a812e0eadda5e68f381b9e5`.

Filesystem scope and bounded concurrency for Studies.

Fonctions : `study_folder:11`; `study_slot:38`

Variables d'environnement lues : `STRUCTURA_STUDIES_ROOT`

### backend/app/api/amc_prices.py

245 lignes ; SHA-256 `7398dbc0011f7f57a771e584cbf36777f6997fff35aef28adc91f2597b47f862`.

API endpoints for the underlying price store.

Fonctions : `get_price_status:26`; `get_spot_on_date:34`; `get_price_status_for_study:47`; `resolve_tickers_endpoint:65`; `fetch_underlying:94`; `upload_underlying:110`; `delete_underlying:137`; `_secondary_market_context:155`; `compute_attribution_endpoint:170`; `compute_brinson_endpoint:199`

Classes : `ResolveItem:58`; `FetchRequest:86`; `AttributionRequest:149`; `BrinsonRequest:190`

### backend/app/api/amc_studies.py

150 lignes ; SHA-256 `485ed240f11c295b9a060d84198096ae394daa8ebf375694b8b47033a0facb02`.

Server-side persistence for AMC study runs (manifest + result + synthèse).

Fonctions : `_summary_row:32`; `_detail_row:44`; `list_studies:54`; `get_study:67`; `create_study:79`; `delete_study:112`; `export_study_archive:126`; `compare_studies:137`

Classes : `AmcStudyCreate:22`

### backend/app/api/auth.py

415 lignes ; SHA-256 `35d6acc6ef7ce89dc58d7fc3e3400e5dc667eab7be4a4a464ad75e01b7edda0e`.

Fonctions : `_throttle_key:52`; `_check_not_locked:59`; `_record_failure:74`; `_record_success:84`; `_hash_pw:89`; `_verify_pw:93`; `_identity_config:100`; `_make_token:105`; `get_current_user:122`; `revoke_user_sessions:162`; `_session_audit:170`; `change_password:193`; `logout:210`; `logout_all:224`; `get_current_admin:234`; `get_current_pricer:242`; `get_current_simulation_admin:247`; `login_options:254`; `login_identity:262`; `development_admin_session:268`; `login:274`; `development_session:314`; `me:342`; `register:380`

Classes : `PasswordChange:186`; `RegisterRequest:371`

Variables d'environnement lues : `STRUCTURA_ALLOW_REGISTRATION`, `STRUCTURA_BOOTSTRAP_PROFILE`, `STRUCTURA_CONSULTATION_ENTITY`, `STRUCTURA_INSTANCE_ID`, `STRUCTURA_WORKSHOP_CHILD`

### backend/app/api/ccr.py

231 lignes ; SHA-256 `f1b6fb17bd26e0c85bd764855b0777954b82f9af2d3b0acdcc5091403a244701`.

Authenticated CCR configuration, saved analyses and pre-trade checks.

Fonctions : `schemas:23`; `counterparties:34`; `configuration:41`; `create_configuration:46`; `update_configuration:54`; `deals:62`; `uat_batches:77`; `diagnostic:84`; `portfolios:89`; `assign_deal:101`; `run_calculation:121`; `get_run:142`; `replay:151`; `monitor:158`; `rfq_context:189`; `rfq_credit_context:202`; `rfq_check:208`

Classes : `ConfigurationWrite:28`; `Assignment:95`

### backend/app/api/client_import.py

205 lignes ; SHA-256 `ad4414fad8b7e207a429de9b1ced94e457b2e00bf3b5592a4275981eaedbfd96`.

Import d'historique commercial — modèle, aperçu, versement, annulation.  Quatre gestes, dans cet ordre : on télécharge le modèle, on le remplit, on regarde ce que l'import ferait, on valide. L'aperçu n'est pas une politesse : c'est ce qui évite de découvrir après coup qu'un fichier a créé quatre-vingts sociétés parce qu'une colonne était décalée.  Motif d'upload repris de `api/amc.py`, qui lit et rend sans persister.

Fonctions : `_format_depuis:37`; `_lire:48`; `modele_excel:60`; `modele_json_:71`; `schema:80`; `apercu:96`; `verser:114`; `lots:155`; `annuler_lot:174`

### backend/app/api/client_intelligence.py

290 lignes ; SHA-256 `1cacb2296a2abd033bdf91c3f4da45a1f8d89645a2bd2abb4b8d52f624aa74a6`.

Read-only CRM analytics with entity isolation and explicit temporal scope.  ``asof`` bounds observed trade dates. Commercial reference records, opportunity statuses and operational follow-ups remain current and are identified as such. This is not a reconstruction of historical knowledge or missing status history.

Fonctions : `_asof:28`; `lecture_client:38`; `lecture_personne:64`; `lecture_affiliation:77`; `signaux:112`; `analytiques:142`; `apercu:265`

### backend/app/api/clients.py

1115 lignes ; SHA-256 `81f354fa5a899ab71eee63f0d2f056e34e7619e7c2170a48ac268d9552870283`.

Clients — l'organisation cliente, sa couverture et ses contraintes.  Portée : le client appartient à l'ENTITÉ, pas à l'utilisateur. Deux commerciaux qui couvrent ABC Asset Management doivent voir une seule fiche, sinon les statistiques de Client Intelligence compteraient deux sociétés là où il n'y en a qu'une. Qui couvre quoi se lit dans `client_coverage` et se filtre à la demande, jamais en dupliquant la ligne.  Toutes les vérifications d'appartenance sont ici, pas dans l'écran : un `GET /api/clients/123` lancé à la main doit se heurter au même refus que l'interface.

Fonctions : `_scoped_client:144`; `_validate_preference_scope:163`; `_preference_evidence:177`; `_record_preference_changes:219`; `_coverage_of:272`; `_mandate_row:287`; `_mandates_of:302`; `_rendu:311`; `list_clients:345`; `get_client:400`; `list_client_contacts:409`; `list_client_mandates:447`; `_mandate_name_available:457`; `create_client_mandate:472`; `update_client_mandate:511`; `check_client_duplicates:560`; `create_client:575`; `update_client:630`; `update_scalar_constraints:694`; `constraints_schema:746`; `scoped_preferences_schema:791`; `replace_scoped_preferences:834`; `get_preference_history:910`; `replace_constraints:926`; `upsert_coverage:986`; `remove_coverage:1021`; `archive_client:1044`; `reactivate_client:1064`; `delete_client:1085`

Classes : `ClientCreate:50`; `ClientUpdate:66`; `PreferenceEvidence:78`; `ScalarConstraintsUpdate:89`; `ConstraintsUpdate:100`; `ScopedPreferencesUpdate:112`; `CoverageUpsert:120`; `MandateCreate:125`; `MandateUpdate:133`

### backend/app/api/compute.py

184 lignes ; SHA-256 `3c98a4f56b49f438f0a963408e0abd980ccad3d552aaefac6515c3b3f333be6c`.

Thin API surface over the generic compute module (core/compute/) — enqueue a batch, poll its status/results. Deliberately does NOT execute anything itself: a batch sits in `queued` until the worker daemon (backend/scripts/run_compute_worker.py, started separately by Philippe, same convention as run.py) picks it up. See core/compute/queue_store.py for the lifecycle this wraps.  Only `kind="payscript_reprice"` is accepted from this endpoint for now — the only pricer safe to expose broadly to any authenticated user today (same sandboxed PayScript execution every other pricing endpoint already runs). An external-pricer kind (core/compute/pricers/

Fonctions : `_batch_row:43`; `_job_row:62`; `create_batch:73`; `list_batches:94`; `get_batch:106`; `admin_list_batches:130`; `admin_delete_batch:147`; `admin_stop_batch:157`; `admin_relaunch_batch:172`

Classes : `ComputeJobIn:30`; `ComputeBatchCreate:35`

### backend/app/api/constraint_definitions.py

269 lignes ; SHA-256 `9e28822ec0c431a9cb97faeb384cf3894e760097963576f64228c4212a0a58cd`.

Déclarer un champ de contrainte — pour la maison, ou pour un client.  Le référentiel décrit ce qu'est une contrainte ; ce routeur permet d'en ajouter. Deux portées, et la distinction n'est pas cosmétique :  - **Sans `client_id`** : un champ de la maison. Il apparaît sur toutes les   fiches de l'entité. C'est le geste d'un admin qui formalise une politique. - **Avec `client_id`** : un nom convenu entre l'utilisateur et ce client-là.   Il n'apparaît que sur sa fiche. C'est le geste d'un commercial qui note la   contrainte que son client formule dans son vocabulaire à lui.  Trois refus structurent l'écriture, tous pour la même raison — un champ 

Fonctions : `_client_de_l_entite:71`; `_ligne_de_l_entite:78`; `_rendu:86`; `meta:104`; `list_definitions:120`; `create_definition:143`; `update_definition:175`; `archive_definition:211`; `restore_definition:238`; `read_catalog:261`

Classes : `DefinitionCreate:44`; `DefinitionUpdate:56`

### backend/app/api/deals.py

7899 lignes ; SHA-256 `1b72b12bf73b2e4de27e22861c9dd1291a2129be562fbf7a5f7858c8953a5763`.

Deal booking and lifecycle management.

Fonctions : `_date_plus_years:192`; `_years_between:196`; `_validate_economics:201`; `_deal_product_terms:271`; `_validate_rfq_booking_identity:291`; `_resoudre_pour_booking:331`; `_fenetres_par_date:351`; `_fenetre_de_depart:365`; `_niveau_initial_constate:378`; `_evenements_pour_la_note:409`; `_figer_echeancier:435`; `_derive_observation_times:456`; `_rfq_provenance:500`; `_gen_ref:588`; `_deal_row:593`; `_event_row:698`; `_get_events:740`; `_fixing_version_row:747`; `_proposal_row:783`; `_get_lifecycle_proposals:812`; `_amendment_row:819`; `_audit_row:843`; `_contract_snapshot:862`; `_commercial_attribution_ids:919`; `_amendment_current_value:928`; `_validated_amendment_value:936`; `_workflow_failure:1028`; `_reject_workflow_action:1047`; `_ops_deal:1077`; `_decode_fixing_evidence:1119`; `_parse_official_observed_at:1187`; `_fixing_submission_failures:1236`; `_fixing_record_payload:1340`; `_fixing_record_hash:1374`; `_checker_request:1379`; `_booking_request_summary:1430`; `_safe_booking_numbers:1462`; `_non_finite_booking_paths:1473`; `_ai_script_provenance:1483`; `_apply_pricing_receipt:1512`; `_reject_booking:1594`; `next_ref:1617`; `_book_deal:1625`; `_execute_booking:1654`; `book_deal:2448`; `_deal_for_portfolio_change:2464`; `_validated_portfolios:2474`; `set_deal_portfolios:2491`; `assign_deal_portfolio:2531`; `list_deals:2559`; `eligible_counterparties:2586`; `watchlist:2600`; `_product_name:2632`; `build_watchlist_row:2649`; `_deal_terms:2842`; `_script_flags:2867`; `pending_amendment_requests:2889`; `get_deal:2917`; `get_deal_audit:2972`; `update_deal:3045`; `request_amendment:3093`; `_amendment_action_rejection:3177`; `approve_amendment:3198`; `reject_amendment:3266`; `apply_amendment:3304`; `update_event:3521`; `_required_underlying_names:3770`; `_spot_failures:3775`; `validate_fixing:3797`; `download_fixing_evidence:4050`; `reject_fixing:4107`; `_ensure_alert:4313`; `_evaluate_lifecycle:4337`; `refresh_events:4433`; `_create_lifecycle_proposal:4451`; `refresh_deal_core:4502`; `_refresh_deal_core:4541`; `_reference_history_arrays:4581`; `_auto_yahoo_event_values:4609`; `_auto_yahoo_evidence:4731`; `_auto_exception_manual_evidence:4772`; `_user_exception_lifecycle_evaluation:4807`; `_pending_auto_fixing_exceptions:4850`; `resolve_auto_fixing_exception:4865`; `_resolve_auto_fixing_exception:4879`; `_auto_yahoo_exception:5272`; `_auto_validate_yahoo_event:5319`; `_auto_review_proposal:5518`; `_auto_apply_lifecycle:5573`; `_refresh_auto_yahoo_deal_core:5771`; `_proposal_required_events:5908`; `_proposal_fixing_failures:5920`; `_payout_reconciliation_tolerance:6008`; `_terminal_deal_state:6023`; `_owned_proposal:6038`; `_reject_lifecycle:6073`; `validate_lifecycle_proposal:6107`; `apply_lifecycle_proposal:6282`; `reprice_inputs:6471`; `_regenerate_dividend_curve:6566`; `reinvest_roll_endpoint:6586`; `_price_reinvest_candidate:6681`; `_reinvest_valuation_context:6758`; `_reinvest_context:6777`; `reinvest_scan_endpoint:6826`; `_reinvest_proposal_data:6878`; `reinvest_proposal_endpoint:6976`; `freeze_reinvest_proposal:7003`; `reinvest_proposal_pdf_endpoint:7033`; `list_deal_archives:7047`; `_mtm_core:7061`; `deal_mtm:7079`; `deal_greeks:7127`; `_avertissement_greeks_pre_strike:7272`; `_run_explain_step:7305`; `_greeks_state:7340`; `_residual_greeks:7356`; `_explain_core:7397`; `deal_mtm_explain:7582`; `deal_mtm_explain_report:7621`; `_monitor_levels:7635`; `deal_mtm_report:7672`; `_valuation_run_row:7756`; `latest_mtm_runs:7781`; `list_valuation_runs:7851`; `get_valuation_run:7874`; `replay_saved_valuation_run:7887`

Classes : `DealUpdate:91`; `EventUpdate:117`; `FixingValidationRequest:136`; `AutoFixingExceptionResolutionRequest:140`; `LifecycleValidationRequest:170`; `AmendmentRequestCreate:175`; `AmendmentDecisionRequest:186`; `DealPortfolioAssign:2456`; `DealPortfoliosSet:2460`; `MtmExplainRequest:7246`

### backend/app/api/documents.py

210 lignes ; SHA-256 `97fe06e7e7e6469e322cf0f7cddbf88d000be8d4a9c280b63e0d2b7e3669f9f1`.

Document library — store, list, download generated documents (KID PDF, term sheets, etc.).

Fonctions : `_doc_row:44`; `_accessible:58`; `list_documents:73`; `upload_document:89`; `download_document:180`; `delete_document:195`

Classes : `DocumentCreate:35`

### backend/app/api/emt.py

429 lignes ; SHA-256 `f6cf3de8d0ad0c5458fbac73c033da11f2f264b7c44da25e9d2298e5e18e03f9`.

EMT / Target Market — MiFID II product governance summary.  Derives an indicative European MiFID Template (EMT) profile for the priced product: knowledge & experience required, capacity to bear losses, risk tolerance and recommended holding period.  SRI/MRM/CRM are NOT recomputed here — they are passed in from the already computed /api/kid result, so the KID and EMT keep one risk indicator instead of two Monte Carlo runs that could drift apart.  Capital protection is a separate contractual input: the KID stress scenario can measure a loss but never establish a guarantee.  The frontend (EmtPanel.vue) refuses to call this endpoint until a KID h

Fonctions : `_script_without_comments:61`; `_detect_features:73`; `_capital_tier:110`; `_knowledge_tier:138`; `_risk_tolerance:146`; `emt_compute:157`; `get_emt_synthesis_payload:260`; `synthesis_prompt:270`; `preview_synthesis:277`; `synthesize_emt:282`; `_emt_record_row:318`; `save_emt:339`; `list_emt_records:412`

Classes : `EmtRequest:47`; `EmtSynthesizeRequest:247`; `EmtSaveRequest:295`

### backend/app/api/fifo.py

169 lignes ; SHA-256 `627dd569b59dd2e2f24faeda8aad9fac0d74d500abfd3a5ebf956c20df3675af`.

FIFO order-book reconstruction — REST endpoints.  Thin HTTP layer over core/fifo/pipeline.py — the same pipeline the AMC study uses (amc_study.py), so both entry points share one implementation and can't drift out of sync again.

Fonctions : `_detect_qty_mode:45`; `_serial:54`; `_run_fifo:65`; `fifo_run:103`; `fifo_detect:135`

Classes : `FifoRunRequest:34`

### backend/app/api/folders.py

104 lignes ; SHA-256 `35ed5cf5cd31fbfc74d513b3da84c1fc52bfb73458ce06bf38a4a604c3763988`.

Fonctions : `_build_tree:21`; `list_folders:48`; `create_folder:57`; `rename_folder:74`; `delete_folder:90`

Classes : `FolderCreate:12`; `FolderRename:17`

### backend/app/api/indicatives.py

266 lignes ; SHA-256 `2493fc4742ab40e04244814e7e2ef917a5be080663e5a95c6b835ae2ff0cec59`.

Pre-trade pricing opportunities — the stage before a Deal exists.  An Indicative is what KID/EMT attach to while a product is still being discussed with a client (no trade yet, so no Deal row). If it converts, the resulting Deal keeps a permanent pointer back via Deal.indicative_id — the Indicative's own id never changes and its KID/EMT records are never re-keyed. See db/models.py:Indicative for the full rationale.

Fonctions : `_gen_ref:53`; `_row:59`; `_indicative_snapshot:80`; `_sync_product_indicative:84`; `create_indicative:108`; `list_indicatives:190`; `get_indicative:202`; `update_indicative:214`; `get_linked_deal:256`

Classes : `IndicativeCreate:30`; `IndicativeUpdate:44`

### backend/app/api/inlife.py

654 lignes ; SHA-256 `1b56513955859c73af3949a3c09f0999be027fd00475ab7b5d4297616d73f384`.

Valorisation en cours de vie depuis le Pricer.  Le Pricer ne savait valoriser qu'à l'émission : toute trajectoire démarrait à 100 % du strike. Impossible d'y répondre à « combien vaut cette note qui a deux ans de vie ». La seule voie était de booker le produit et de lire son MtM — un détournement quand il s'agit d'une opportunité de marché secondaire qu'on ne détient pas.  Ce module ouvre la même machinerie que le MtM des deals (core/inlife_valuation) à un produit décrit par un formulaire. Le mode ne se choisit pas : il se déduit de la date de valorisation. Égale à la date de strike, on price à l'émission ; postérieure, on rejoue le passé sur

Fonctions : `_snapshot_underlying:124`; `_closes_at:151`; `variant_terms_or_none:264`; `build_request_residual:284`; `price_in_life:406`; `implied_funding:592`

Classes : `InLifePricingRequest:57`; `ResidualContext:165`; `ImpliedFundingRequest:579`

### backend/app/api/interactions.py

505 lignes ; SHA-256 `8e43f44a4cd2abb0b11fd0d8ae057efc8b3247cadb17d0bc5e4bc49e9470b3d2`.

Interactions — les événements commerciaux datés.  Une interaction se rattache TOUJOURS à un client, JAMAIS obligatoirement à une opportunité : une prospection initiale n'a pas de dossier derrière elle, et l'exiger obligerait à ouvrir une opportunité vide pour enregistrer un premier appel.  Les participants sont désignés par leur affiliation du moment, comme partout ailleurs dans ce module : une réunion tenue chez Bank A en 2024 reste une réunion chez Bank A, même si son participant travaille ailleurs aujourd'hui.

Fonctions : `_scoped:74`; `_scoped_client:81`; `_scoped_follow_up:88`; `_participants_rendus:96`; `_rendu:114`; `_follow_up_row:141`; `_sync_follow_up:155`; `_set_participants:186`; `list_interactions:220`; `list_types:254`; `get_interaction:259`; `create_interaction:268`; `update_interaction:328`; `close_follow_up:386`; `reschedule_follow_up:420`; `reopen_follow_up:450`; `delete_interaction:478`

Classes : `ParticipantIn:36`; `InteractionCreate:41`; `InteractionUpdate:53`; `FollowUpClose:64`; `FollowUpReschedule:69`

### backend/app/api/kid.py

552 lignes ; SHA-256 `2510271c71c786ed2f60d2b8c9d665ee8469619d72d6fcc51efe45382053fb73`.

KID PRIIPs — Key Information Document analytical computation.  Runs 3 Monte Carlo simulations (T_full, T_half, T_1Y) and returns:   - SRI (Synthetic Risk Indicator 1-7) from VEV / MRM / CRM   - 4 PRIIPs scenarios (stress/défavorable/modéré/favorable) × 3 horizons   - Annualized net returns after costs for a 10 000€ investment

Fonctions : `_mrm_from_vev:50`; `_sri:57`; `_mc_percentiles:63`; `_percentile_rows:103`; `_horizon_percentiles:136`; `_scenario_row:215`; `kid_compute:306`; `_kid_record_row:451`; `save_kid:467`; `list_kid_records:535`

Classes : `KidRequest:293`; `KidSaveRequest:434`

### backend/app/api/market_data.py

77 lignes ; SHA-256 `4a5ba31bd4850798e32563d0b073ab61df72ba96ed2d65558e8d8c8931fe6e0e`.

Market data API endpoints — Yahoo Finance vol, dividends, correlations, historical prices.

Fonctions : `hist_vol_endpoint:17`; `hist_prices_endpoint:31`; `list_underlyings_endpoint:42`; `dividend_profile_endpoint:65`

### backend/app/api/opportunities.py

641 lignes ; SHA-256 `9ff323f10f3404cc023f8ab287006aee81a5091ab8ea6241aa279de8d038fdf2`.

Opportunités — l'intention d'investissement, entre le client et la RFQ.  Deux règles gouvernent ce fichier.  **Un contact appartient au client de son opportunité.** Vérifié à la création, à la modification, et surtout au changement de client — le cas §29, où l'on remplace Client A par Client B en laissant derrière des contacts qui n'y travaillent pas. Le contrôle est ici et pas seulement à l'écran : un appel direct doit se heurter au même refus.  **Une opportunité ne suit jamais une personne qui change d'employeur.** Elle reste attachée à l'affiliation sous laquelle elle a été ouverte, donc au client de l'époque. Si le contact part, on la clô

Fonctions : `_scoped:113`; `_scoped_client:120`; `_contact_rendu:127`; `_rendu:147`; `_set_participants:224`; `list_opportunities:256`; `list_lost_reasons:301`; `get_opportunity:308`; `create_opportunity:319`; `update_opportunity:381`; `change_status:539`; `delete_opportunity:596`

Classes : `ParticipantIn:48`; `OpportunityCreate:53`; `OpportunityUpdate:79`; `StatusChange:105`

### backend/app/api/persons.py

622 lignes ; SHA-256 `16e9f7e6527768418a6dbdaaff1a4469e97108f6030c39cb10b2a2481e460b4b`.

Personnes et affiliations — l'identité et l'historique professionnel.  Une personne n'appartient pas à une société : elle y travaille pendant une période. Ce module n'expose donc aucun moyen de « changer l'employeur » d'une personne. Il expose un moyen de **clore une affiliation et d'en ouvrir une autre**, ce qui n'est pas la même chose : la première formulation réécrit un passé, la seconde l'empile.  C'est la raison d'être de `POST /{id}/change-company`, et la raison pour laquelle aucun `PATCH` de ce fichier ne touche au couple (person, client) d'une affiliation existante.

Fonctions : `_scoped_person:101`; `_scoped_client:108`; `_affiliation_rendue:115`; `_rendu:130`; `list_persons:165`; `search_duplicates:201`; `get_person:217`; `create_person:228`; `update_person:285`; `deactivate_person:307`; `reactivate_person:325`; `delete_person:343`; `list_affiliations:368`; `create_affiliation:382`; `update_affiliation:419`; `close_person_affiliation:457`; `delete_affiliation:484`; `change_person_company:539`; `upsert_contact_coverage:587`

Classes : `PersonCreate:40`; `PersonUpdate:55`; `AffiliationCreate:63`; `AffiliationUpdate:71`; `ChangeCompany:81`; `CloseAffiliation:90`; `ContactCoverageUpsert:94`

### backend/app/api/portfolios.py

1047 lignes ; SHA-256 `8fb2ace688c028f055390d8e2a8d95079568576525623fa69d1972e31bd891bb`.

User-defined portfolios (risk-aggregation buckets) and Greeks aggregation across the deals they contain. See PLAN squishy-baking-sedgewick.  CRUD mirrors folders.py (user-scoped organizational bucket). The aggregation itself is pure arithmetic over immutable, date-matched GREEKS valuation runs (api/deals.py POST /{id}/greeks) — no Monte Carlo here, cheap enough to run on every screen load. What can be expensive is producing those per-deal Greeks, which stays an explicit action in the frontend.

Fonctions : `_fx_to_reporting:42`; `_fx_missing_row:55`; `_portfolio_row:70`; `_is_admin:87`; `_active_deals_statement:91`; `_all_deals_statement:96`; `_portfolio_accessible:101`; `_portfolio_deals:105`; `list_portfolios:138`; `create_portfolio:169`; `rename_portfolio:192`; `delete_portfolio:208`; `_canonical_pair:240`; `_greeks_valuation_date:254`; `_parsed_computed_at:263`; `_greeks_snapshots:273`; `_aggregate_risk:333`; `risk_global:603`; `_run_explain_on_book:631`; `pnl_explain_global:727`; `pnl_explain_portfolio:747`; `portfolio_risk:770`; `_aggregate_exposure_by_counterparty:793`; `_barrier_severity:905`; `_deal_severity:938`; `_aggregate_barriers:944`; `barriers_global:976`; `portfolio_barriers:993`; `exposure_by_counterparty_global:1013`; `exposure_by_counterparty_portfolio:1031`

Classes : `PortfolioCreate:59`; `PortfolioRename:66`

### backend/app/api/pricing.py

1011 lignes ; SHA-256 `bc2e9e79fa3799da2f1dabd1cdfc1910edda7422318af19bab2b50c95d6541d9`.

Fonctions : `_clean_flux:46`; `parse_endpoint:70`; `price_endpoint:108`; `profile_endpoint:219`; `analysis_user_params:264`; `residual_context_or_none:274`; `paths_endpoint:295`; `proba_endpoint:345`; `mtf_endpoint:396`; `script_providers_endpoint:470`; `script_prompt_endpoint:480`; `product_analyse_endpoint:506`; `product_analyse_prompt_endpoint:527`; `product_intentions_endpoint:545`; `script_generate_endpoint:552`; `script_transcribe_engines_endpoint:590`; `script_transcribe_prepare_endpoint:602`; `script_transcribe_endpoint:622`; `mtf_drilldown_endpoint:668`; `backtest_endpoint:742`; `_windowed_backtest:862`; `_realized_corr:924`; `backtest_compare_endpoint:935`

Classes : `ProductAnalysisRequest:494`

### backend/app/api/product_optimizer.py

213 lignes ; SHA-256 `e7332e6d594b24fc50da8610123a1039da4b2dd0681024ece62a5e43bcccf0f1`.

Owned persistent research jobs and the compatible ephemeral streaming API.

Fonctions : `validate_catalogue:51`; `market_reference:63`; `cancel_run:80`; `get_capabilities:90`; `create_research:95`; `list_researches:119`; `read_research:136`; `archive_research:142`; `cancel_research:150`; `estimate:157`; `run:163`

Classes : `_Lease:34`

### backend/app/api/products.py

593 lignes ; SHA-256 `d53deee92aa2c349bd843b88d1c298d2f36d2cbbc13f1f9fa4e426438474ce9c`.

Persisted Product dossiers shared by pricing and downstream modules.

Fonctions : `_fail:94`; `_validated_pricing_input:98`; `_default_name:110`; `_row_summary:118`; `create_product:145`; `_create_product:153`; `fork_product_for_booking:216`; `list_products:269`; `get_product:315`; `product_history:340`; `update_product:356`; `revise_product_terms:397`; `archive_product:441`; `compose_product_pricing_input:463`; `retain_product_calculation:488`; `get_product_calculation:555`

Classes : `ProductCreate:32`; `ProductUpdate:42`; `ProductTermsUpdate:58`; `ProductArchive:65`; `ProductPricingInput:71`; `ProductCalculationCreate:76`; `ProductBookingFork:82`; `RetainedDraftInput:89`

### backend/app/api/rfq.py

1938 lignes ; SHA-256 `30e8439ef4bc7708034024ce756232b1b8c97c5a856dd2c12be54c6104546ea0`.

RFQ (request-for-quote) tracker: collect and compare bank quotes for a structured product against Structura's own model price.

Fonctions : `_gen_ref:196`; `_parse_utc_datetime:202`; `_edge_bps:217`; `_rfq_audit_state:240`; `_validate_quote_price:286`; `_improves:300`; `_merge_pricing_params:318`; `_refuse_if_booked:343`; `list_providers:372`; `_is_expert_script:388`; `_refuser_reglement_avant_maturite:403`; `_resolve_commercial_context:430`; `_clean_optional:504`; `_validate_rfq_correlation:509`; `_product_terms_from_payload:530`; `_product_terms_from_rfq:548`; `_create_rfq:553`; `create_rfq:786`; `list_rfqs:795`; `rfq_history:812`; `get_rfq:877`; `rfq_terms:888`; `request_electronic_execution:906`; `declare_treatment:913`; `confirm_treatment:920`; `cancel_treatment:931`; `list_rfq_shares:938`; `change_rfq_assignment:955`; `share_rfq:965`; `revoke_rfq_share:1010`; `compose_rfq_pricing_input:1036`; `_network_recipient:1046`; `_transport_issues:1056`; `authorized_rfq_recipients:1070`; `_shared_rfq_request:1093`; `preview_rfq_exchange:1148`; `rfq_exchange_tracking:1217`; `send_rfq_exchange:1224`; `update_rfq:1247`; `_update_rfq:1266`; `delete_rfq:1579`; `add_quote:1629`; `update_quote:1708`; `delete_quote:1885`; `review_rfq_booking:1922`; `book_reviewed_rfq:1929`

Classes : `RfqCreate:68`; `RfqUpdate:101`; `RfqExchangePreview:135`; `RfqExchangeSend:149`; `RfqSharePut:154`; `RfqAssignmentPut:160`; `QuoteCreate:170`; `QuoteUpdate:178`; `TreatmentCancellation:926`

### backend/app/api/rfq_desks.py

182 lignes ; SHA-256 `e5a12d4242ff0492357ee0e31e015e33614ed918e00392b2345ded635320e48b`.

Explicit RFQ desk admission and membership management.

Fonctions : `_desk_row:33`; `_require_admin_scope:38`; `_utc_naive:45`; `my_desks:50`; `organization_desks:64`; `desk_members:76`; `admin_desks:96`; `create_desk:115`; `put_membership:141`

Classes : `DeskCreate:21`; `MembershipPut:26`

### backend/app/api/rfq_inbox.py

145 lignes ; SHA-256 `b957e6aea2ae9746c18243cf323656ac79db4bfb53851538586f555e9062e1b1`.

Read and explicitly acknowledge requests addressed to the user's bank desk.

Fonctions : `list_received:22`; `received_request:44`; `decide_electronic_execution:54`; `set_publication_policy:62`; `prepare_quote:69`; `validate_quote:76`; `publish_quote:83`; `withdraw_quote:95`; `claim_request:108`; `assign_request:115`; `pricing_members:122`; `acknowledge_read:131`

Classes : `Withdrawal:89`; `BankAssignment:101`

### backend/app/api/rfq_reconciliation.py

42 lignes ; SHA-256 `1edf154203c2d1c8a3c89c77abe486afd9a4f0c7f682c606749103e6b269faf9`.

Scoped read and explicit durable resume for electronic RFQ reconciliation.

Fonctions : `list_reconciliation:13`; `get_reconciliation:34`; `refresh_reconciliation:39`

### backend/app/api/rfq_relations.py

83 lignes ; SHA-256 `5e76f54d900a5900e51eca6d48e9dc5e44c196ec58a2c44820bfe01edb70a85f`.

Organization administration of explicit bilateral RFQ relationships.

Fonctions : `relation_catalog:20`; `list_relations:35`; `get_relation:44`; `create_relation:50`; `update_relation:55`; `recognize_relation:60`; `suspend_relation:65`; `relation_history:70`

### backend/app/api/rfq_transport.py

180 lignes ; SHA-256 `f264602e712ac9e6c4bb051faf2f4e37be4240eb5dfad6ec8930382a7c9f5bd4`.

Organization pairing administration and authenticated installation endpoint.

Fonctions : `retry:25`; `row:69`; `owned:77`; `channels:86`; `configure:95`; `state:135`; `probe:154`; `receive:165`

Classes : `ChannelCreate:50`; `ChannelState:63`

### backend/app/api/scenarios.py

121 lignes ; SHA-256 `940e02fd50e7c7540fe3bac0e970484f1cc7e72882b7df4d8d41a7c05bd2e3b6`.

Scenario API endpoint — stress grid: price under combined spot x vol shocks.

Fonctions : `scenarios_endpoint:22`

### backend/app/api/schedule.py

170 lignes ; SHA-256 `28577c38ce37d45b36f221d9603762e5aa25f82ce9d94d7566435da013b0b4cf`.

Schedule API endpoint — CONSTAT()/CONSTAT()() calendar generation (expert mode), independent of any PayScript. See core/schedule.py for the algorithm.

Fonctions : `_parse_date:19`; `calendar_catalog:27`; `_calendars:32`; `generate_schedule_endpoint:37`; `resolve_business_day:69`; `window_preview_endpoint:89`; `period_window_preview_endpoint:114`

### backend/app/api/scripts_db.py

512 lignes ; SHA-256 `62cb6485a3dae2983c125a1d6bfb28126a9f03776f1d00038b2bdf3637560ea0`.

Fonctions : `_row:63`; `list_scripts:97`; `create_script:147`; `get_script:181`; `update_script:200`; `delete_script:236`; `_contexte:316`; `_visible_par:326`; `_lisible:342`; `_origine:351`; `_vue_variante:366`; `list_variants:406`; `create_variant:429`; `update_variant:471`; `resolve_variant:503`

Classes : `ScriptCreate:18`; `ScriptUpdate:36`; `VariantCreate:303`; `VariantUpdate:310`

### backend/app/api/shocks.py

683 lignes ; SHA-256 `0eea7ed6b752f2f30abee2c979e249ff80451bbb1e78ef8c4d99a7b5784dc61a`.

Market-shock scenarios (spot/vol/rate/corr) — full reprice, not a linear Greeks approximation, because barrier payoffs (autocalls, phoenix...) are too non-linear for that (a -20% shock isn't 20x the delta). See PLAN squishy-baking-sedgewick.  Reuses run_mc's existing bump vocabulary (spot_mult, vol_add, dr) exactly as compute_greeks does, but with larger, named amplitudes and a full reprice instead of a tiny bump-and-reprice derivative. Correlation shocks bypass run_mc's corr_delta (single-pair only, built for Greeks' cross-gamma) and pass a directly-shifted corr_matrix instead — run_mc already accepts that as a first-class parameter, no new 

Fonctions : `_build_shock_arrays:94`; `_shock_corr:120`; `_describe_shock:131`; `_run_shock_on_deal:146`; `_run_shock_on_book:236`; `_smile_shift:306`; `_validate_smile_parameter:318`; `_smile_underlying_overrides:328`; `_run_smile_on_deal:380`; `_run_smile_on_book:438`; `_describe_smile:492`; `_persist_shock:510`; `_shock_run_row:526`; `shock_deal:537`; `shock_portfolio:558`; `shock_global:580`; `_persist_smile:596`; `smile_risk_portfolio:620`; `smile_risk_global:645`; `list_shocks:662`

Classes : `ShockOverride:39`; `ShockRequest:44`; `SmileUnderlyingOverride:59`; `SmileRiskRequest:78`

### backend/app/api/simulation.py

176 lignes ; SHA-256 `8503887ed383b3737425d5f59218c2b9607cb7f9895925f905aa2b504184f406`.

Simulation API endpoints — PARAM solver (target price) and 2D price grid/heatmap.  Both endpoints share the same validation shape: parse the script, check the requested PARAM name(s) actually exist in it, check the correlation matrix dimensions, then delegate to core/payscript/simulation.py for the math.

Fonctions : `_parse_and_validate:28`; `_check_param_exists:72`; `solve_endpoint:79`; `grid_endpoint:127`

### backend/app/api/trading.py

300 lignes ; SHA-256 `d1e75952d6b6bf99e73a5f1b19007c69b85341399c3f39c8d9a16bce11f8d08c`.

Reusable bilateral relationships, note bookings and settlement evidence.

Fonctions : `require_trading_permission:28`; `entity_id:67`; `relation:73`; `relationships:78`; `check_references:83`; `create_relationship:108`; `update_relationship:126`; `execution:155`; `contract_identity:163`; `executions:173`; `book_note:180`; `_book_note:187`; `settle:262`; `positions:286`

Classes : `RelationshipTerms:36`; `RelationshipUpdate:63`; `NoteBooking:145`; `SettlementProof:257`

### backend/app/api/valuation_notes.py

287 lignes ; SHA-256 `ab506cc554cd0b54c0da85b54a4c293e61c4ca269dc4a1eb2e693bbfe30dc5b0`.

Valuation note workspace: immutable evidence, revisioned editorial drafts.

Fonctions : `_deal:61`; `_note:68`; `_row:76`; `_check_revision:84`; `_create:89`; `create_note:131`; `list_notes:147`; `note_sources:157`; `get_note:176`; `save_note:181`; `freeze_note:197`; `versions:221`; `note_pdf:230`; `note_assist_prompt:247`; `preview_assist_note:274`; `assist_note:279`

Classes : `CreateNote:24`; `Editorial:31`; `Revision:39`; `UpdateNote:43`; `AssistNote:54`

### backend/app/api/valuation_progress.py

45 lignes ; SHA-256 `90612cb0bb6e2d39de1e5ac33f25770727a55e224b38103b47a52aa4e99d69fc`.

Stream actual valuation phases while a synchronous worker owns its session.

Fonctions : `valuation_progress_response:11`

### backend/app/api/var.py

541 lignes ; SHA-256 `0d1383757ece216c9aebfeb6da9853088e64fd9ef2dcae9c5d60ce94ef6e05b4`.

VaR/ES study endpoints — launches an async ComputeBatch (kind= 'var_scenario') covering every active deal in scope × every generated market scenario (historical and/or parametric — both run side by side in the same study, never blended, per the VaR chantier discussion), and lets the caller poll it. Nothing here executes synchronously: a batch sits `queued` until the worker daemon (backend/scripts/run_compute_worker.py, started separately by Philippe) drains it — see core/compute/'s own docstring for why this whole feature exists as an async module rather than a blocking endpoint like /shock.  Aggregation (VaR/ES/percentiles per method) happen

Fonctions : `_deal_descriptor:55`; `_aggregate_var_jobs:64`; `_launch_var_study:248`; `launch_var_global:438`; `launch_var_portfolio:452`; `list_var_history:472`; `get_var_result:502`

Classes : `VarRequest:40`

### backend/app/api/variants.py

333 lignes ; SHA-256 `6a69611587fd5dfb3d8feb4dde7ad132b3fea3458a88f92af04fe1e1116178d3`.

Compare variants using one market context and the original nominal basis.  A roll buys net exit proceeds / all-in entry price units of the new note. Quantity, future undiscounted recovery and a proven contractual cap are separate metrics. A simulated maximum never establishes a contractual bound. The sealed study retains the funding assumptions, inputs, prices and resulting distributions.

Fonctions : `_prix:53`; `_corps_avenant:58`; `_corps_roll:73`; `_ajoute_en_unites_moteur:128`; `_maturite:152`; `_proba_pair:163`; `compare_variants:174`; `freeze_variant_study:282`; `list_variant_studies:303`; `_refus:312`; `_params_moteur_http:328`

Classes : `CompareRequest:39`

### backend/app/api/volatility.py

39 lignes ; SHA-256 `607f610585c18559081a210eaaa17b402e07afce3b2111dfbc7e6f24d80e3eb1`.

Authenticated, stateless validation of editable smile assumptions.

Fonctions : `validate_surface:27`; `calibrate:33`

Classes : `SurfaceRequest:15`; `CalibrationRequest:19`

### backend/app/core/__init__.py

0 lignes ; SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

### backend/app/core/access.py

61 lignes ; SHA-256 `7239bbd2b99180f788e28be2900e504aabe8d29c1617b08575c307f9bfceab6d`.

Separate local business administration from central/technical administration.

Fonctions : `is_organization_superuser:5`; `is_local_admin:10`; `has_business_role:14`; `profile:18`; `capabilities:23`; `has_capability:33`; `require_capability:44`; `require_booking_permission:49`; `require_managed_capability:57`

### backend/app/core/admin_registry.py

358 lignes ; SHA-256 `83bcd645c211d9453578d5a1081ec6da787931df49f2df9195ac8b44a2f5d76b`.

Declarative registry of business tables browsable from the admin data viewer: read-only + delete by default, since several of these tables carry JSON blobs (script_snapshot, underlyings_json...) that a naive column editor would corrupt. To add a table, add an entry here; no other code changes required.  A table becomes editable (not just delete-able) by adding an `editable_fields` list. Booked deals deliberately have none: every economic correction now goes through the controlled amendment request envelope.  KidRecord/EmtRecord are deliberately absent — they're immutable regulatory records (see db/models.py docstrings) and must never be admin

Fonctions : `_cleanup_document_file:37`; `_prepare_deal_delete:44`; `_break_rfq_quote_cycle:67`; `registry_meta:150`; `_get_config:157`; `list_rows:164`; `get_row:207`; `delete_row:222`; `_config_for_model:277`; `delete_rows:284`; `update_row:305`

### backend/app/core/agregats_officiels.py

157 lignes ; SHA-256 `4d5887fcdc0378a98a3455ebd0e27021eea0d9e357b061ab4521b5000a5dd266`.

L'agrégat officiel d'une constatation moyennée — point 6 du §14.  Une constatation sur période n'est pas observable : elle se calcule depuis les cours de sa fenêtre. Ce module fait ce calcul, et surtout il dit quand il ne peut PAS le faire.  Deux principes, et le second compte autant que le premier :  **La réduction est par sous-jacent.** `AVG` moyenne chaque actif sur ses propres relevés ; `MIN` et `MAX` prennent son extrême à lui. L'agrégation panier — worst-of, best-of, moyenne — vient après, dans le payoff, jamais ici. Réduire l'agrégat au lieu de chaque actif donne un autre produit : `moyenne(min) <= min(moyennes)` toujours, et l'écart s

Fonctions : `_reduire:79`; `calculer:87`; `est_perime:142`

Classes : `Neutralisation:36`; `Agregat:51`

### backend/app/core/ai_contract.py

16 lignes ; SHA-256 `dc847ba7ddc98bf7957a9d4c5d12def6ccf59269321789aeec069fd7cbb5ebec`.

Shared request contract for all text assistants.

Classes : `PromptOverride:5`; `AiOptions:11`

### backend/app/core/amc_attribution.py

255 lignes ; SHA-256 `f92828112bf3763508c60b088e011fc758b983fc690bf3731d013828e67417ba`.

VAG Phase 2 — Attribution : timing des achats / sélection des sorties.  Principe -------- Pour chaque ordre EXÉCUTÉ du carnet d'ordres, on mesure la contribution de cette décision de trading par rapport au fait de ne rien avoir fait :      contribution_i = qty_signée_i × (P_terminal_j − P_exécution_i)  [en devise AMC]    • BUY  (qty > 0) : positif si P_terminal > P_exécution  (acheté avant une hausse)   • SELL (qty < 0) : positif si P_terminal < P_exécution  (vendu avant une baisse)  Normalisation : on divise par l'AUM du portefeuille (meta.total_aum).  Décomposition --------------   timing  → contributions des ordres BUY   exits   → contribu

Fonctions : `_terminal_price:35`; `_pct:65`; `compute_attribution:73`

### backend/app/core/amc_benchmarks.py

72 lignes ; SHA-256 `a09f712104da99c3a91acf5509730181dde43911e1fba4dfbded58000a73e82d`.

Composite benchmark definitions and ISIN → benchmark mapping.  To add a new composite benchmark: append an entry to COMPOSITE_BENCHMARKS. To map an ISIN to a default benchmark: add a line to ISIN_DEFAULT_BENCHMARK. No code changes required anywhere else.

Fonctions : `get_composite:67`; `is_composite:71`

### backend/app/core/amc_bh.py

163 lignes ; SHA-256 `8e32de1baae5ffecbc114fd9da2b45a7c07dd7ba70b447c151a0daad30abeeff`.

Référentiel Inertiel — Buy & Hold depuis la date d'émission.  compute_bh() compare la NAV réelle à un portefeuille de référence passif maintenu sans aucun trade depuis le lancement.  Source de la composition initiale (par ordre de priorité) :   1. termsheet_positions  — poids et quantités issus de la term sheet (source de vérité).      → Immune aux problèmes de splits (utilise le poids %, pas le prix × qty).   2. Identité comptable   — qty_initiale = position_actuelle + ventes − achats réels      → Fallback quand la TS n'est pas renseignée dans le manifeste.  VAG = performance réelle − performance Référentiel Inertiel   > 0 → le gérant a créé

Fonctions : `_order_date_key:31`; `compute_bh:43`; `_bh_from_termsheet:82`

### backend/app/core/amc_blocks.py

572 lignes ; SHA-256 `088963633432d92f9f0cfd8e9f452f74caa250858c3df97a8a5a8738a11f094c`.

AMC analysis blocks B / C / D — built on the order-book reconstruction.    • Bloc B — attribution by underlying & period (realised + latent P&L, price vs FX)   • Bloc C — trading quality / turnover (round-trips, hit ratio, trading vs hold)   • Bloc D — manager behaviour (conviction vs uncertainty, 2×2 matrix)  All amounts are in the product (NAV) currency. These blocks are fully offline: they need only the raw order book + composition snapshot.

Fonctions : `_safe_div:20`; `_performance_fee_drag:26`; `_transaction_cost_drag:58`; `_nav_reconciliation:66`; `block_b_attribution:209`; `block_c_trading:333`; `_avg_aum:407`; `_period_days:430`; `block_d_behaviour:439`

### backend/app/core/amc_brinson.py

632 lignes ; SHA-256 `d09fff2892a2cc713f60b184485035c13e86030e6ff2eea7154dd1ed99c41c15`.

Block G — Brinson-Fachler Attribution (single-period).  Decomposes the portfolio's active return vs benchmark into three effects (Brinson-Fachler, 1985):   - Allocation   : did we overweight the right sectors?   - Selection    : did we pick better stocks within each sector?   - Interaction  : did we overweight exactly where we over-selected?  Portfolio weights = inception-window BUY orders (first 60 days, same as VAG). Benchmark sector weights = ETF snapshot via yfinance, or static MSCI World fallback. Benchmark sector returns = SPDR Select Sector ETF proxies (US bias noted).  The module also handles brinson_prices.json — a lightweight cache 

Fonctions : `save_price_cache:124`; `load_price_cache:145`; `compute_brinson:158`; `_build_inception_weights:454`; `_fetch_sectors:489`; `_series_total_return:527`; `_get_benchmark_sector_weights:566`; `_get_sector_etf_returns:605`

### backend/app/core/amc_cash_events.py

35 lignes ; SHA-256 `266b127a38873de7cbc37986388f2a160b17c377d4c4ba4f8234fa0c25b0c28b`.

Explicit cash income supplied with an investor's study (never inferred from NAV).

Fonctions : `load_cash_income:7`

### backend/app/core/amc_confidence.py

60 lignes ; SHA-256 `016a60a662e9aa194fd28632aa1885d051f98b228a28fe5f2ab224ba7b3c2424`.

Observable data coverage, never a probability of manager skill.

Fonctions : `attach_brinson:5`; `build_confidence:20`

### backend/app/core/amc_controls.py

117 lignes ; SHA-256 `51f2400b82d4d30d54d74e49eb5887219873b5c8fbec73d0f39100e851c55354`.

Shared study controls: dates, causal prices, inputs and provenance.

Fonctions : `date_key:12`; `validate_nav:15`; `price_at:31`; `resolve_file:47`; `fingerprint:64`; `input_provenance:68`; `clustered_mean_test:75`; `source_orders:87`; `market_capture:102`; `record_market:111`

### backend/app/core/amc_dividends.py

294 lignes ; SHA-256 `b39d0b41527e6aa9ba33bf4ea2b9a0c937617a2f016a7fdc70df7d3d5e23037d`.

Dated dividend receivables and auditable reinvestment; no market side effects.

Fonctions : `_day:79`; `_execution_day:87`; `_rate:98`; `_summary:108`; `legacy_dividends:122`; `prepare_dividends:141`

Classes : `DividendPolicy:14`; `Execution:37`; `DividendEvent:47`

### backend/app/core/amc_engine.py

987 lignes ; SHA-256 `f13c44ad289846506962d37efc1195b0a4d8fd761399b3ea1aa5e04374e8a438`.

AMC Fama-French analysis engine.  Parses the diagnostic Excel, downloads FF factors from Ken French's library, fetches benchmark via yfinance, runs OLS + rolling OLS, and returns a self-contained result dict for the frontend.

Fonctions : `_safe_records:143`; `parse_amc_excel:160`; `_ff_parquet:254`; `ff_data_status:258`; `ff_refresh:283`; `_load_ff_data:319`; `_parse_ff_csv:336`; `get_ff_series_list:377`; `get_benchmark_list:383`; `_download_raw_ticker:406`; `_download_benchmark:418`; `run_analysis:444`; `_compute_activity:807`; `_compute_concentration:885`; `_dependency_score:944`

### backend/app/core/amc_fifo_adapter.py

192 lignes ; SHA-256 `735c76bb0c9a9eb06bf29745b8d42a85e6bee77613de27b0f4b8b32211da8362`.

Adapter: converts fifo.ReconResult → legacy dict format expected by amc_blocks.  The FIFO module is intentionally lean (no AMC-specific concepts). This adapter adds the fields that Block B/C/D need without polluting the FIFO module:    - FX decomposition (price_pnl / fx_pnl) from raw price_local + fx fields   - exit_quarter, holding_days, ret_pct  (derived from dates)   - ccy, value_prod, unreal_ret_pct      (trivially computable)   - first_entry_date, last_entry_date, n_buys  (from OpenPosition.lots)   - flips (direction changes per ISIN, computed from carnet orders)   - synthetic_report converted to list[dict]   - warnings synthesised from 

Fonctions : `_quarter:24`; `_compute_flips:30`; `fifo_to_legacy_recon:50`

### backend/app/core/amc_managerskill.py

306 lignes ; SHA-256 `3245a370ab63827cbb899479cc56778c52678cb2a9f1e77ccd33f21065e09f57`.

Manager Skill Score — global aggregator of all study blocks.  Combines Block A (alpha FF), Block I (stock picking), Block E (Référentiel Inertiel / VAG), Block J (risk management), Block H (timing), Block D (conviction) into a single 0-100 composite score.  Base weights (renormalized if a block is unavailable):   Alpha FF              30%   (Bloc A)   Stock Picking         25%   (Bloc I)   Référentiel / VAG     20%   (Bloc E)   Risk Mgmt             15%   (Bloc J)   Timing                 7%   (Bloc H)   Conviction             3%   (Bloc D)

Fonctions : `_clamp:48`; `_alpha_score:54`; `_stockpicking_score:75`; `_vag_score:83`; `_riskmanagement_score:134`; `_timing_score:140`; `_conviction_score:151`; `_label_color:169`; `_interpret:178`; `compute_manager_skill_score:226`

### backend/app/core/amc_manifest.py

442 lignes ; SHA-256 `4cd1b6593c034906fa75f6e8bfc6959ed91e462994702623cf7383592248344b`.

AMC study manifest — schema, folder auto-detection, template generation.  The manifest is the single input that launches a study. Raw data files (the LUKB exports: composition `Def.txt`, NAV `timeseries` CSV, order-book JSON) carry the *data*; the manifest carries everything that is NOT in the data and must be supplied by the structurer (fees from the term sheet, the benchmark ticker, factor model, behavioural thresholds) plus which analysis blocks to run.  `detect_study_folder()` scans an ISIN folder, maps each file to its role, and pre-fills a manifest — leaving the manual fields flagged so the user knows exactly what to complete for a bran

Fonctions : `_theme_from_name:325`; `_ff_series_for_ccy:336`; `detect_study_folder:341`; `blank_template:435`

Classes : `ProductInfo:32`; `FileRoles:39`; `TermsheetPosition:49`; `ReferencePortfolio:62`; `ManualParams:82`; `BlockToggles:131`; `OutputOptions:148`; `StudyManifest:153`

### backend/app/core/amc_market_bundle.py

125 lignes ; SHA-256 `bcb3536a31bc677ed440bf4a58e35c8e0969ab6dcabae30cd0bb7f0770634dd6`.

Request-scoped, explicit market inputs. Never populate shared market caches.

Fonctions : `active_bundle:13`; `_frame:17`; `market_bundle:118`

Classes : `MarketBundle:32`

### backend/app/core/amc_marketshocks.py

264 lignes ; SHA-256 `f9880e695f28048afe8e78dd3669d4e3e5818b41edd233f24eb74804e8fc1122`.

Block K — Réactivité aux Chocs de Marché.  Juxtapose l'activité de trading du gérant avec un calendrier d'événements de marché majeurs (subprimes, COVID, chocs chinois, etc.) pour évaluer si la gestion a sur-réagi, sous-réagi, ou réagi de façon disciplinée pendant ces épisodes de stress.  Principe -------- Pour chaque événement dont la fenêtre chevauche l'historique réel du fonds (entre la première NAV et l'as_of) :   1. Activité  : volume brut tradé pendant la fenêtre vs volume brut "normal"                  du fonds (moyenne journalière hors fenêtres d'événements) →                  activity_ratio. >1 = plus actif que d'habitude, <1 = moins

Fonctions : `_parse:73`; `_as_date:77`; `_label:90`; `compute_market_shocks:114`

### backend/app/core/amc_orderbook.py

702 lignes ; SHA-256 `d6ab3c481cf8fa79d3210d6a16f5fef1f43d75c20657d479febc47bc8a63b799`.

AMC order-book parser — the shared foundation for blocks B / C / D.  Loads the raw LUKB exports (composition `Def.txt`, NAV timeseries CSV, order-book JSON) and reconstructs, using only the order book:   • normalised order flow (signed quantities, local price, FX, product-ccy price)   • FIFO position reconstruction → completed round-trips + open lots   • current marks per name (from the composition snapshot) → latent P&L  Everything is in the *product* (NAV) currency. P&L on closed trades is split into a price effect and an FX effect; open positions are marked to the issuer's composition snapshot (single current mark — no continuous constitue

Fonctions : `_parse_dt:32`; `_f:46`; `load_composition:55`; `load_nav:94`; `load_orders:123`; `apply_split_corrections:161`; `_fetch_t0_price:205`; `reconstruct:315`; `_quarter:596`; `load_study_data:604`

Classes : `_Lot:300`; `ReconResult:308`

### backend/app/core/amc_pdf.py

4123 lignes ; SHA-256 `0c62aa943a541103c9b46c4146bd45dcaaac33d3a89c6b0da41ecbb19fdd8989`.

Professional PDF export for AMC Fama-French analysis reports.

Fonctions : `_sty:55`; `_fig_to_image:94`; `_dark_axes:103`; `_chart_performance:117`; `_chart_rolling:158`; `_chart_dependency_gauge:194`; `_chart_exposures:220`; `_tbl:253`; `_p:274`; `_pn:275`; `_sig:278`; `_pfmt:287`; `_pval_safe:294`; `_pct:299`; `_kpi_row:304`; `_on_page:351`; `_make_study_page:376`; `_draw_study_cover:422`; `generate_pdf:579`; `_fmt_usd:940`; `_fmt_prod:947`; `_chart_nav_bh:958`; `_chart_replicant_vs_amc:994`; `_chart_factor_contribs:1028`; `_chart_quarterly_pnl:1057`; `_chart_holding_dist:1078`; `_chart_conviction_matrix:1097`; `generate_study_pdf:1151`; `_append_block_a_sections:1435`; `_append_block_b:1629`; `_append_block_c:1770`; `_append_block_d:1823`; `_append_block_g_brinson:2006`; `_append_block_f_replicability:2237`; `_append_block_e_vag:2442`; `_append_confidence:2631`; `_chart_timing_distributions:2700`; `_chart_alpha_distributions:2727`; `_append_block_i_stockpicking:2766`; `_append_block_i_appendix:2927`; `_append_block_h_timing:2992`; `_append_block_h_appendix:3141`; `_chart_radar_scores:3200`; `_make_progress_bar:3236`; `_gauge_strip:3257`; `_append_executive_summary:3322`; `_append_block_j_rms:3516`; `_append_block_k_marketshocks:3747`; `_append_manager_skill:3799`; `_append_block_bh:3913`; `_append_disclaimer:4014`

Classes : `ColorRect:79`

### backend/app/core/amc_prices.py

711 lignes ; SHA-256 `687cee5dd5f78ab7efa3fc6001371203d331c2c4eff5782553a930cdffd12664`.

AMC underlying price store.  Persistent store for underlying price time series used in the VAG module. Logical instrument keys resolve through an atomic market manifest to immutable Parquet generations; exact legacy addresses remain readable without migration.  Two acquisition paths:   1. Yahoo Finance auto-fetch  (yfinance)   2. Manual upload             (Excel or JSON)

Fonctions : `is_gbx_ticker:42`; `_slug:53`; `_logical_price_path:64`; `_parquet_path:68`; `_load_ticker_map:80`; `_save_ticker_map:93`; `price_status:99`; `_validate_key:127`; `_save_series:133`; `fetch_prices:158`; `_unique_json_object:197`; `upload_prices:206`; `delete_prices:256`; `get_fx_series:269`; `_stored_fx_series:278`; `fx_quote_to:342`; `fx_rate_to:395`; `_bundle_key:401`; `get_currency:410`; `resolve_ticker:425`; `load_prices:451`; `spot_on_date:465`; `yf_symbol:482`; `get_split_calendar:528`; `split_factor_between:562`; `build_marks:576`; `auto_populate_store:664`; `execution_series:685`

### backend/app/core/amc_replicability.py

283 lignes ; SHA-256 `726b856ba2c30d9ebd3ddf1b232f3e1078f047f01f75fa25023016fff98552ba`.

Block F — Réplicabilité de la stratégie.  Construit un portefeuille réplicant passif à partir des bêtas Fama-French estimés en Bloc A, compare sa trajectoire à la NAV réelle, et calcule un score de réplicabilité 0-100.  Aucune donnée externe supplémentaire requise : tout vient du résultat Bloc A.

Fonctions : `compute_replicability:17`; `_factor_contributions:162`; `_score:184`; `_profile:224`; `_interpretation:236`

### backend/app/core/amc_riskmanagement.py

606 lignes ; SHA-256 `6ff1feb9bf1af318d2c5cf56bdf49f358f41143812f620fa3274e39457a84879`.

Block J — Risk Management Score.  Evaluates whether the manager properly managed the risk they took. Five sub-scores, each 0-100, weighted into a global score.  Weights:   risk_adjusted  30%  — Sharpe, Calmar, capture ratios, IR   drawdown       25%  — Max DD, Ulcer Index, episode count/duration   downside_risk  20%  — Semi-deviation, Sortino, VaR 95%, ES 95%   concentration  15%  — Max weight, HHI, effective N   factor_risk    10%  — R², market beta, alpha t-stat (from Block A)  Reliability cap: n_obs < 30 → cap 50; 30-60 → cap 70; 60-120 → cap 85; 120+ → 100.

Fonctions : `_clamp:34`; `_blend_composite:40`; `_get_benchmark_series:66`; `_nav_to_returns:73`; `_drawdown_series:101`; `_compute_drawdown_episodes:107`; `_drawdown_episode:122`; `_score_drawdown:131`; `_score_downside_risk:188`; `_score_risk_adjusted:233`; `_score_concentration:299`; `_score_factor_risk:360`; `_reliability_cap:437`; `_score_label:446`; `_interpret:456`; `compute_risk_management_score:513`

### backend/app/core/amc_stockpicking.py

514 lignes ; SHA-256 `b17c341869288ae0aa315000f8236e87ec69f33e901fdcfb30a6f7d45c378f99`.

Block I — Stock Picking Score.  Measures whether the manager selects genuinely better stocks than their investment universe by comparing the forward return of each purchased security against the benchmark return over 1M, 3M, 6M, and 12M horizons.  Alpha_i(h) = Return(title, h) - Return(benchmark, h)  Score 0-100 is a weighted composite of:   40% — alpha magnitude (mean alpha across horizons)   35% — success rate (% purchases with positive alpha)   25% — information ratio (mean_alpha / std_alpha)  Prices are sourced from the parquet store populated by the VAG module. Benchmark prices are fetched via yfinance with an in-memory cache. Open posit

Fonctions : `_load_series:39`; `_forward_return:53`; `_blend_composite:73`; `_get_benchmark_series:101`; `_tstat_pvalue:142`; `_distribution:163`; `_compute_score_100:187`; `_score_label:199`; `_interpret:207`; `compute_stockpicking_score:287`

### backend/app/core/amc_study.py

534 lignes ; SHA-256 `699ebfe363bcbc59f6603218a8f2988d2cdbd95c6fd1d74f1c0e605b3e725661`.

AMC study orchestrator.  Entry point that turns a manifest + study folder into a complete result: manifest → raw data → order-book reconstruction → blocks A/B/C/D → confidence.  Blocks are independent and degrade gracefully: a disabled block is skipped, and a block that errors is reported (so the confidence section can account for it) without sinking the whole study.

Fonctions : `_resolve_order_files:39`; `run_study:50`; `_run_study:59`; `_nav_records:397`; `_comp_records:422`; `_orders_to_tx_records:428`; `_run_block_a:446`; `_add_concentration_warnings:502`

### backend/app/core/amc_synthesize.py

1059 lignes ; SHA-256 `fe907a416d238197a803ba07f0ffb6ff2c7b118bf250a4a304465c179dde62ef`.

AI synthesis for AMC study results — payload builder and LLM callers.

Fonctions : `_get_system_prompt:351`; `_fmt:366`; `_pct:377`; `_money:381`; `build_synthesis_payload:394`; `call_ollama:968`; `list_ollama_models:974`; `call_claude:982`; `call_openai:988`; `validate_synthesis:994`; `build_synthesis_brief:1007`

### backend/app/core/amc_timing.py

317 lignes ; SHA-256 `a12f3f037fba665413e1140d6c663b7061c213731cd0f4ebc64fb3c5316c4c8e`.

Block H — Timing Score.  Measures the quality of the manager's entry and exit points by positioning each executed price within the local price range observed over the 30 days before and after each trade.  Entry Score = (max_window - price_buy)  / (max_window - min_window) Exit  Score = (price_sell - min_window) / (max_window - min_window)  Score = 1  → perfect timing (bought at absolute low / sold at absolute high) Score = 0  → worst timing  (bought at absolute high / sold at absolute low) Score = 0.5 → random baseline  Prices are sourced from the persistent parquet store populated by the VAG module (amc_prices.py).  Trades for ISINs without 

Fonctions : `_label:40`; `_load_series:47`; `_score_trade:61`; `_tstat_pvalue:87`; `_distribution:109`; `_interpret:121`; `compute_timing_score:132`

### backend/app/core/audit.py

72 lignes ; SHA-256 `8a4683b58556b929312c1622c66a1fe9b285743fbf93ef1812c5bc4fd407652c`.

Persistent business audit helpers.  Accepted critical actions call ``record_audit_event`` before their normal transaction commit.  Rejected actions call ``commit_rejection`` before raising the HTTP/domain error.  If the audit insert itself fails, the critical action must fail as well: there is deliberately no best-effort logging path here.

Fonctions : `_json_default:19`; `_dump:27`; `record_audit_event:34`; `commit_rejection:67`

### backend/app/core/booking_contract.py

64 lignes ; SHA-256 `1f901171bf01160b9f8b276459c762738632b5c29824bba2af9d2046d2d3f8b3`.

Booking input contract, independent of HTTP routing.

Classes : `LegalIdentityExceptionRequest:6`; `DealCreate:11`

### backend/app/core/calendar_budget.py

45 lignes ; SHA-256 `baecb13e1133eff16577f7acedc984552cab50e2136e1c1c86dcd02540fcb86c`.

Explicit API preview budgets, checked before calendar construction.

Fonctions : `check_dates:10`; `tenor_days:17`; `check_schedule:24`; `check_window:39`

### backend/app/core/calendars.py

202 lignes ; SHA-256 `ed5d3ec5a587918e9420ddc142e7f90aadc8c265fb694ac0737e07c4eaeb3d67`.

Named observation calendars, payment centres and business-day conventions.  Observation venues and payment centres are separate contractual choices. Multiple calendars require a product-specific all-open or any-open rule. Historical currency-only configurations retain their original bank mapping.  The euro has no country calendar — EUR settlement follows TARGET, the payment system, which is why it is mapped to the ECB financial calendar rather than to any member state. Elsewhere the country's bank calendar applies, with the subdivision that matters for settlement (Zurich for the CHF: 2 January and 1 August are not holidays everywhere in Switz

Fonctions : `validate_settlement_lag:62`; `calendar_selection:69`; `calendar_context:94`; `_calendar:121`; `is_business_day:135`; `adjust:145`; `add_business_days:168`; `business_days_between:182`; `_roll:198`

Classes : `CalendarSelection:54`; `BusinessDayConvention:100`; `UnsupportedCurrency:113`

### backend/app/core/calibration.py

102 lignes ; SHA-256 `6080506bec640bfc6a064b109b29738303cd2114fac3bc9f05f90fafa392c13a`.

Realized-market calibration from historical closes.  Feeds the residual-MtM "marché actuel" mode (api/deals.py:deal_mtm): instead of the σ/corr frozen in the booking snapshot, estimate them from the recent daily history, loaded over its own window (`calibration_history_start`).  That window used to be the lifecycle replay's — from the strike minus seven days — to spare one market-data call. The saving made the "1-year" realized vol a since-strike vol for every deal younger than a year, and left a forward-start deal with a single week of history: 4 returns, below MIN_RETURNS, so its MtM was refused. The replay and the calibration answer differ

Fonctions : `calibration_history_start:34`; `realized_market:46`

### backend/app/core/ccr/__init__.py

1 lignes ; SHA-256 `efb0ddc31d5c12f94bb6830052a6fcdcda0cc5138f53a800fb1c28d92ef26953`.

Counterparty credit risk: legal eligibility, economic exposure and credit controls.

### backend/app/core/ccr/cache.py

92 lignes ; SHA-256 `534698717260422e7ec41b7c0343b3e1510bacd992374397879841b1a6d39997`.

Reuse frozen CCR base valuations, never a client-supplied risk decision.

Fonctions : `implementation_identity:15`; `preparation_key:24`; `find_prepared_base:47`; `archived_histories:67`

### backend/app/core/ccr/common_market.py

99 lignes ; SHA-256 `384196fbb065912fcdefdd3c62d78768630f3849229d9671c554721ea004c7a0`.

One dated statistical market for all prepared CCR residual contracts.

Fonctions : `harmonize_market:14`

### backend/app/core/ccr/contracts.py

224 lignes ; SHA-256 `83516669ecbb1b776ea528241a01a45be0dd6282f57f21a671e48ed776b5ab02`.

Explicit CCR input contracts. Money is in the stated currency; rates are fractions.

Classes : `Contract:10`; `CreditProfile:14`; `MasterAgreement:51`; `CSAAgreement:63`; `NettingSet:87`; `CreditLimit:102`; `CollateralPosition:122`; `CreditOverride:134`; `RegulatoryFramework:146`; `ProposedTrade:154`; `MarketOverride:163`; `PriceHistory:168`; `CalculationRequest:181`

### backend/app/core/ccr/exposure.py

158 lignes ; SHA-256 `840ada371e0492c8d585283d4a59f95a1cd757850182b171e80b3369e3985c45`.

Legal aggregation and economic exposure. No database or external market I/O.

Fonctions : `eligible_set:14`; `collateral_profile:31`; `cva:86`; `summarize:118`; `limit_check:138`; `decision:153`

### backend/app/core/ccr/preparation.py

224 lignes ; SHA-256 `893174f1625d62f94842c64a3f18dddaad8336ef59a4b9871827e24f6b2ee042`.

Prepare clean CCR valuations without changing official Booking valuations.

Fonctions : `adjust_context:122`; `prepare_trade:148`

Classes : `MarketHistory:20`

### backend/app/core/ccr/service.py

906 lignes ; SHA-256 `e7c87c2f4417f4de4622295d5f6ebd8e6ebbe17fd2f10233256562294e7d6be1`.

CCR orchestration: existing valuations, legal data, shared paths and audit.

Fonctions : `organization:27`; `row_payload:33`; `records:39`; `save_record:47`; `legal_assignment:109`; `portfolio_deals:123`; `archived_trade:175`; `proposed_trade:206`; `scope_diagnostic:213`; `runtime:247`; `validate_future_context:298`; `joint_scenarios:309`; `legal_maps:355`; `aggregate:360`; `evaluate_inputs:415`; `calculate:677`; `enforce_amendment:813`; `enforce_booking:865`

### backend/app/core/client_analysis.py

34 lignes ; SHA-256 `16fca8a89169441d1c12bf6067a1672bf41f9d748a4d4d7715db036b6c401e8c`.

Explicit currency units and temporal basis for CRM observations.

Fonctions : `currency_code:8`; `amount_summary:13`; `temporal_basis:30`

### backend/app/core/client_constraints_ref.py

554 lignes ; SHA-256 `168e674d45cbebba745d4dd5482bae718edb9edc21860730f6bd841c92105b0c`.

Le référentiel des contraintes client — champs standards et champs ajoutés.  Une contrainte client se saisissait jusqu'ici en texte libre séparé par des virgules. Trois défauts, tous du même genre : ils ne se signalent pas.  1. **« SX5E » ne rencontre jamais « ^STOXX50E ».** L'univers de sous-jacents se    compare aux tickers réellement traités ; tapé à la main, il ne correspond à    rien et l'écran conclut que le client n'a jamais traité son propre univers. 2. **Le vocabulaire fermé des types de produits était rappelé en prose** sous le    champ, à recopier de mémoire. Une faute de frappe passe la validation du    navigateur et échoue au ser

Fonctions : `_standards:135`; `_devises_proposees:225`; `catalog_options:231`; `_depuis_table:274`; `definitions_for:289`; `_refus:328`; `_valider_liste_de_chaines:333`; `_valider_liste_de_refs:353`; `_valider_nombre:384`; `validate_value:399`; `validate_constraints_against:427`; `normalize_key:465`; `require_definable:486`; `key_in_use:532`

Classes : `ConstraintRefError:53`; `Definition:93`

### backend/app/core/client_controls.py

935 lignes ; SHA-256 `d1add3cd791b4ad7207a3c615a8f51d686e7669ec4948e50045ff24d992a72ee`.

Règles d'intégrité de la couche commerciale — Client / Person / Affiliation.  Ce module porte les invariants qui ne doivent JAMAIS dépendre d'un écran. Le principe est celui du reste de l'application : un contrôle d'interface se contourne par un appel direct à l'API, donc tout ce qui protège un historique se vérifie ici, côté serveur.  Trois invariants structurants :  1. **L'affiliation est le seul point d'ancrage temporel.** « Qui travaille où »    ne se lit jamais sur la personne mais sur l'affiliation ouverte. Aucun code    de ce module ne réaffecte le couple (person_id, client_id) d'une affiliation    existante — c'est ce qui rend impossi

Fonctions : `_check_vocabulary:102`; `validate_client_type:111`; `validate_client_status:115`; `validate_data_origin:119`; `validate_commercial_role:126`; `validate_interaction_type:130`; `validate_opportunity_status:135`; `validate_coverage_role:140`; `validate_mandate_type:145`; `validate_mandate_status:149`; `rating_rank:168`; `validate_rating:175`; `_convertir:202`; `validate_constraints:212`; `validate_scalar_constraints:235`; `require_constraints_version:265`; `apply_constraints:291`; `apply_constraints_atomic:306`; `read_constraints:346`; `parse_iso_date:361`; `current_affiliation:373`; `affiliations_of_client:391`; `require_affiliation_of_client:405`; `require_mandate_of_client:430`; `validate_opportunity_contacts:465`; `change_company:498`; `close_affiliation:561`; `_normalise_nom:587`; `find_person_duplicates:591`; `find_client_duplicates:626`; `client_history_counts:659`; `require_client_deletable:684`; `person_history_counts:708`; `require_person_deletable:727`; `validate_status_transition:744`; `require_opportunity_rfq_ready:767`; `client_provenance_snapshot:790`; `require_deal_attribution_coherent:855`

Classes : `ClientRuleError:47`

### backend/app/core/client_cycle.py

406 lignes ; SHA-256 `3c52d7f630b3bb09aedf652da6c33ba847c4fb38365acd2baa210bb18e3ea0ba`.

Cadence d'investissement — le moteur de cycles.  Module PUR : des dates entrent, des statistiques sortent. Ni base, ni FastAPI, ni Yahoo. Même idiome que `core/inlife_valuation.py`, et pour la même raison — ce qui se teste sans monter une application se teste vraiment.  Trois principes gouvernent tout ce fichier.  **La médiane plutôt que la moyenne.** Un client qui traite tous les 90 jours et saute une année à cause d'un changement d'organisation a une moyenne fausse et une médiane juste. La moyenne est calculée et rendue, mais elle ne décide rien.  **Une fenêtre, jamais une date.** « 15–30 octobre » est une information ; « 22 octobre » est u

Fonctions : `default_lead_days:41`; `_mediane:64`; `_quantile:73`; `_demi_ecart_interquartile:84`; `_typologie:106`; `compute_cycle:167`; `observed_lead_days:290`; `recommend_contact_window:306`; `compare_cycles:346`

Classes : `Cycle:128`; `ContactWindow:278`

Variables d'environnement lues : `STRUCTURA_CLIENT_DEFAULT_LEAD_DAYS`

### backend/app/core/client_import.py

1090 lignes ; SHA-256 `5a71a20f65435258d2820c8a7b99b27d30e726d5c86495aeabf18e31352b03f6`.

Import d'historique commercial — le format, sa validation, son versement.  Un client arrive avec un passé stocké ailleurs. Ce module le fait entrer sans que personne n'ait à ressaisir cinq ans de relation.  **Un seul classeur, six feuilles, dans l'ordre des dépendances.** Un client doit exister avant la personne qui y travaille, qui doit exister avant sa transaction. Des fichiers séparés obligeraient à respecter cet ordre à la main, et à découvrir l'erreur au troisième. Une feuille par objet dans un même classeur — ou un objet JSON à six tableaux — résout l'ordonnancement tout seul, et tout entre dans une transaction unique.  **Rien ne s'écri

Fonctions : `empreinte_fichier:215`; `_empreinte_transaction:220`; `_transaction_identity:233`; `_normaliser_entete:267`; `_cellule:276`; `lire_classeur:286`; `lire_json:321`; `_date_ou_none:354`; `_nombre_ou_none:373`; `_oui_non_ou_none:392`; `_vocabulaire:416`; `_cle_nom:429`; `_traiter:485`; `analyser:901`; `appliquer:932`; `annuler:984`; `modele_json:1009`; `modele_xlsx:1028`

Classes : `Anomalie:162`; `Rapport:173`; `ImportError_:208`; `Resolveur:433`

### backend/app/core/client_intelligence.py

1715 lignes ; SHA-256 `3612c2339b1a4c103f1466edf81accb714224c20cf60e8248a1e84c87fb8bbeb`.

Client Intelligence — ce que les transactions disent, et à quel niveau.  Ce module lit la base et agrège ; toute l'arithmétique de cadence vit dans `client_cycle.py`, qui n'a besoin que de dates.  **Trois niveaux, jamais confondus.** Une même transaction se lit de trois façons : elle appartient à une personne (toutes sociétés confondues), à un passage dans une société donnée, et à la société elle-même. Les mélanger donnerait exactement ce que §40 interdit — un client décrit comme « risque moyen » parce qu'il abrite un gérant prudent et un gérant agressif.  **Déclaré et observé cohabitent.** Ce qu'un contact dit préférer et ce qu'il achète rée

Fonctions : `_payoff_family_for_reporting:42`; `_date_iso:53`; `affiliation_ids_of_person:72`; `_niveaux_du_deal:158`; `_json_object:189`; `_depuis_deal:199`; `_depuis_historique:240`; `_origin_maps:267`; `_normalise_transactions:283`; `eligible_transactions:311`; `eligible_opportunities:319`; `deals_of_affiliations:325`; `deals_of_client:339`; `transactions_of_entity:348`; `transactions_by_client:367`; `_dates_de_trade:383`; `evidence_level:390`; `recency_level:407`; `observed_behaviour:422`; `lost_reasons:538`; `_habit_evidence:576`; `habit_dimensions:588`; `mandate_divergences:647`; `_final_rfq_responses:679`; `provider_selection_analysis:697`; `_statement_value:792`; `preference_statements:799`; `_apply_statements:821`; `_project_statements:832`; `preference_history:853`; `declared_preferences:905`; `_cle:975`; `famille_de_produit:1000`; `_libelles_declares:1021`; `_superposer:1036`; `_compter:1102`; `negative_space:1122`; `_quantile:1171`; `_borne:1181`; `observed_ranges:1195`; `next_thresholds:1242`; `lead_time_pairs:1282`; `person_intelligence:1327`; `technical_view:1407`; `_rfqs_du_client:1480`; `client_intelligence:1519`

Classes : `Transaction:77`

### backend/app/core/client_signals.py

367 lignes ; SHA-256 `9dbfc41a03a82db68c5441da8b39f3436a2f91846f3478e619baeb34d1468dc3`.

Signaux commerciaux — ce qu'il y a à faire aujourd'hui.  Six types, pas davantage. Multiplier les catégories fabrique du bruit, et un tableau de bord qui signale tout ne signale rien.  Chaque signal porte sa raison en clair. C'est la même règle que partout dans ce module : un chiffre qu'on ne peut pas justifier n'aurait pas dû être affiché, et un signal qu'on ne peut pas expliquer n'aurait pas dû être levé.  Sur les événements produits (§52) : ce module ne calcule AUCUNE probabilité de rappel. Il lit la prochaine constatation que le cycle de vie connaît déjà. Inventer « autocall probable » demanderait un modèle que rien ici ne porte, et une p

Fonctions : `stale_after_days:49`; `maturity_horizon_days:61`; `_nom_personne:91`; `build_signals:98`

Classes : `Signal:69`

Variables d'environnement lues : `STRUCTURA_MATURITY_HORIZON_DAYS`, `STRUCTURA_OPPORTUNITY_STALE_DAYS`

### backend/app/core/client_technical.py

354 lignes ; SHA-256 `bd3d6a8e32fd68905fceaabb1e871adaccf1443d344db167902da110a12faa53`.

Lecture technique d'un portefeuille client — niveaux, protections, familles.  Ce module répond à trois questions qu'un structureur pose avant d'appeler un client : à quels **niveaux** il traite (coupon), quelles **protections** il accepte (barrière), et si le trade s'est fait **avec nous ou ailleurs** — et dans ce cas à quel prix.  Deux difficultés, toutes deux affrontées plutôt que contournées.  **Un deal booké ne porte pas ses niveaux en clair.** Coupon et barrière vivent dans les PARAM du script PayScript, pas dans des colonnes. Une ligne d'historique importée, elle, les porte explicitement. Sans extraction, l'écran afficherait des niveaux

Fonctions : `_plausible_coupon:40`; `niveaux_du_script:50`; `decouper_sous_jacents:151`; `_nature_du_groupe:183`; `catalogue_natures:193`; `nature_du_sous_jacent:207`; `famille_de_panier:226`; `libelle_famille:263`; `_mediane:274`; `moyennes_par_famille:294`; `repartition_execution:335`

### backend/app/core/compute/__init__.py

25 lignes ; SHA-256 `edd1e049ccbd86bb0319666a439f28368afe94a749175da9f42611cd8275e78a`.

Generic parallel compute module — the one place in the codebase that decides HOW an independent batch of jobs gets executed (thread pool vs process pool) and tracked (queued/running/terminal, per-job error isolation), so callers never reimplement concurrency primitives.  Not specific to any one feature: a VaR/ES study (many market scenarios), a bulk KID regeneration, a portfolio-wide shock re-run, or a client's own pricing model plugged in via pricers/external.py all submit through the same job/executor/queue_store trio. See PLAN squishy-baking-sedgewick and the VaR chantier discussion for the design rationale (in particular: why ProcessPoolE

### backend/app/core/compute/executor.py

142 lignes ; SHA-256 `0e5a677b6e354126697f5a5dd624f3febb4d1277598a64a6a9ecf9097988fd1e`.

Generic parallel batch dispatch — thread pool vs process pool, and per-job error isolation, in exactly one place so no caller (a VaR study, a bulk KID regen, a portfolio-wide shock re-run...) reimplements concurrency itself.  Why ProcessPoolExecutor is the real default, not a tuning knob: the PayScript engine's _eval_paths evaluates a script's AT/PAY/IF body path-by-path in pure Python (see core/payscript/engine.py) — the GIL serializes that completely under threads, so a ThreadPoolExecutor would barely parallelize a batch of PayScript reprices at all. Threads stay available (use_processes=False) for a pricer that's genuinely I/O-bound (e.g. 

Fonctions : `_run_one:32`; `run_batch:45`

### backend/app/core/compute/job.py

13 lignes ; SHA-256 `295f90c45a9fa3b1e54c5c82b70383698b605764e0f5da7c1acc1acc39e83e5a`.

In-memory result shape for a single compute job — see executor.py for what produces it and queue_store.py for how it gets persisted.

Classes : `JobResult:9`

### backend/app/core/compute/pricers/__init__.py

21 lignes ; SHA-256 `9cefc5cd671b9ed5060e080ec0088ce2df0f30faa053744cb910cd248f5d3e13`.

Registry of pricer functions, keyed by the `kind` a ComputeBatch declares. A pricer is any callable `(payload: dict) -> dict` where both sides are pure, JSON-plain data — that's what makes it safe to ship across a process boundary (see core/compute/executor.py) and to persist in ComputeJob.payload_json / result_json without any custom serialization.  Adding a new job kind (e.g. a client's external product, see external.py) means adding one entry here — nothing in executor.py or queue_store.py ever needs to change, same "drop it in, don't touch the core" spirit as adding a new PayScript product template.

### backend/app/core/compute/pricers/external.py

57 lignes ; SHA-256 `3721fdbaef943c968fd169aa44c490a2b7f557a2557462b453a1c225fb5068cd`.

Extension point for pricing a product that ISN'T expressed as a PayScript — a client's proprietary model, a competitor's structure to benchmark for a pitch, a legacy Excel-based pricer, anything the DSL can't (yet, or ever) express. Nothing here is wired to anything today — no external client has been onboarded — this module documents the CONTRACT such a pricer must satisfy to run through the same compute module (job/executor/queue_store) as a PayScript reprice, without that client's code ever being imported into backend/app/'s own process.  Two isolation levels — pick per situation, both slot into PRICERS the same way (a plain `(payload: dic

Fonctions : `subprocess_pricer:38`

### backend/app/core/compute/pricers/payscript.py

89 lignes ; SHA-256 `afa53a7f49246349086557a14eb9ae1f2a7e8f5d0c3f4640ca26f1e5d971db81`.

Adapter that lets the generic compute module reprice a PayScript deal — the only PayScript-specific code in core/compute/, everything else in this package is product-agnostic.  The payload is deliberately NOT "a Deal" (a live DB row, a CompiledScript, an engine underlying object) — it's the plain data those things are built from, because a ProcessPoolExecutor worker (see executor.py) gets this payload via pickle in a fresh Python process that has never seen the caller's Session or compiled script object. Re-parsing the script text costs a few ms; it's cheaper than solving "how do I pickle an exec()-produced closure" (you don't — CompiledScrip

Fonctions : `price_payscript_job:37`

### backend/app/core/compute/pricers/product_optimizer.py

13 lignes ; SHA-256 `a8df2d09b6dfd27dbc2a64e4695b925bf7a0294443850d837360418cbfbf99fb`.

Direct optimizer pricing in a spawned worker; no database or live closure.

Fonctions : `price_optimizer_candidate_job:4`

### backend/app/core/compute/pricers/scenario_grid.py

99 lignes ; SHA-256 `0a77a6c6ee1f4711e0028dcad5b65b0213eae0f2c2de3e7918700b2cdbf60834`.

Reprices ONE cell of the Pricer's stress grid (spot shock x vol shock, see core/payscript/scenarios.py) — a fresh full-life price, not a residual leg (contrast with pricers/var_scenario.py, which reprices an already-live deal's remaining cash flows). Same "ship pure data, rebuild the compiled script fresh in the worker" discipline as pricers/payscript.py.  Payload mirrors compute_scenario_grid()'s own call into run_mc — every knob that function already threads through (yield_curve/sigma_r/a_r included, see AUDIT_PRICING_2026-07.md #1.6) is carried here unchanged, so a parallelized cell prices identically to the sequential loop it replaces.  P

Fonctions : `price_scenario_grid_job:36`

### backend/app/core/compute/pricers/var_scenario.py

143 lignes ; SHA-256 `8b201f09e25aae959fd41f9f170da704b077c4d04eca496fe40442fa9ce1f419`.

Reprices ONE active deal's residual leg under ONE shocked market scenario — the job kind a VaR/ES study (core/var_engine.py) submits, one job per (deal × scenario) pair, through the generic compute module.  Same "ship pure data, rebuild the compiled objects fresh in the worker" discipline as pricers/payscript.py, but for the RESIDUAL (mark-to-future) leg rather than a fresh full-life price — the residual script and the replayed state (memory coupons, running extrema, observation index...) are what api/deals.py:_mtm_core builds today for a single synchronous MtM/shock call; var_engine.build_deal_scenario_base() extracts the pure-data equivalen

Fonctions : `residual_script_from_payload:44`; `price_var_scenario_job:83`

### backend/app/core/compute/queue_store.py

354 lignes ; SHA-256 `1f18f3e38dca499cca015d65fab7f46b57874229660b8cd35003db71f242a06e`.

DB-backed job queue for the generic compute module. Same queued -> running -> terminal lifecycle as a typical background-job table, with an atomic claim so a single worker daemon (scripts/run_compute_worker.py) stays safe even if accidentally started twice, and a stale-claim requeue so a worker that crashed mid-batch doesn't strand it forever.  Not a distributed queue (no Celery/Redis) — deliberately: this module's actual target is one family office's/small broker's own machine running one worker process, not a trading floor's compute grid. SQLite is already this app's only datastore (see CLAUDE.md/database.py) and that's fine here too, with 

Fonctions : `enqueue_batch:26`; `claim_next_batch:57`; `renew_lease:123`; `lease_is_active:139`; `pending_jobs:150`; `record_job_result:181`; `finalize_batch:221`; `cancel_batch:268`; `relaunch_batch:299`; `delete_batch:343`

### backend/app/core/compute_budget.py

417 lignes ; SHA-256 `8ee2a4993c7912af727bf2266d548026bc048fe5e7435da19f3e41ce6d31bb8f`.

Central resource limits for PayScript parsing and quantitative calculations.  The limits are business-facing safeguards, not performance promises.  They keep one malformed or oversized request from exhausting the local workstation while leaving a wide margin above Structura's current product templates.

Fonctions : `validate_script_source:71`; `validate_problem_dimensions:85`; `count_compiled_dates:102`; `validate_compiled_dates:112`; `estimate_mc:121`; `ensure_budget:198`; `greek_repricing_equivalent:218`; `estimate_pricing_request:245`; `estimate_mc_batch:311`; `estimate_var_portfolio:358`

Classes : `CalculationEstimate:52`

### backend/app/core/consultation_sessions.py

58 lignes ; SHA-256 `b09a547e8bd6f56496db7817d1ae2f159f9ac14dc896cac43019af5b2897e562`.

Session state beside the viewer lock, never inside an archived business book.

Fonctions : `connect:11`; `version:26`; `revoked:32`; `audit:37`; `load_user:47`

Variables d'environnement lues : `STRUCTURA_CONSULTATION_LOCK_DIR`

### backend/app/core/deal_valuation.py

715 lignes ; SHA-256 `a10e45705486fb69eeceb047ea87af44ada69603aee62748c0f867ac91e189a6`.

Residual deal valuation orchestration shared by MtM, risk and VaR.  This module owns the translation from a booked deal and realized history to a serializable ``ValuationContext``. API routes only perform authorization and response delivery; compute workers can import this module without depending on an API router.

Fonctions : `valuation_funding:61`; `standard_mtm_request:72`; `_get_events:82`; `mtm_core:89`

Classes : `MtmOverrideUL:38`; `MtmRequest:44`; `DealGreeksRequest:68`

### backend/app/core/deal_valuation_pdf.py

846 lignes ; SHA-256 `7170789f29ff4255cc47ed5bcd18268f088e2ceb6f258165613a38acdfb3a86d`.

Client-facing valuation note (PDF) for a live structured product deal.  Built from the residual-MtM output (api/deals.py:_mtm_core) — the PDF shows EXACTLY the figure displayed in the Booking page (same seed, same body). Light print-friendly palette (unlike the dark AMC report), French wording, rule-based explanation sentences (no free text generation): every statement is derived from fields of the MtM payload. Design: NOTE_VALO_DESIGN.md.  The builder is a pure function of a plain-dict `data` payload so it can be unit-tested offline (see tests/test_valuation_pdf.py).

Fonctions : `_sty:57`; `_fmt_nominal:82`; `_logo_image:86`; `_header:97`; `_footer:117`; `_fig_to_image:127`; `_monitor_label:138`; `build_explanation:150`; `_chart_history:252`; `_tbl:313`; `_id_table:329`; `_stat_tiles:349`; `_headline:373`; `_calendar_event_label:398`; `_events_table:414`; `_greeks_table:443`; `_annex_market_table:460`; `_editorial_section:475`; `generate_frozen_comparison_pdf:484`; `generate_valuation_pdf:529`; `_chart_waterfall:679`; `_explain_market_table:729`; `generate_explain_pdf:754`

### backend/app/core/emt_synthesize.py

111 lignes ; SHA-256 `f05f13a47fffab523998b324c9250f5a5275afc5899df6e1033555f315adc903`.

AI-assisted payoff description for the EMT / Target Market tab.  Mirrors the AMC study synthesis pattern (amc_synthesize.py): a payload builder that turns computed results into structured human-readable text, a dedicated editorial system prompt, and the same LLM callers reused as-is (call_ollama / call_claude / call_openai) so there is one implementation of "talk to the configured provider", not one per feature.  Unlike the AMC payload tab (data only), get_synthesis_payload() below also returns a "copy block" — system prompt + data concatenated into one text — because a plain external AI chat (ChatGPT/Claude/Gemini web UI) has no separate sys

Fonctions : `_fmt_pct:44`; `build_emt_payload:51`; `build_copy_block:103`

### backend/app/core/fifo/__init__.py

11 lignes ; SHA-256 `583bec309cd8446d7fb5b991a851eec01a9a473414b76eb8caa24d633267a900`.

FIFO order-book reconstruction module.  Independent from the legacy amc_orderbook.  Supports two quantity modes:   - "shares"     : executedQuantity = real share count, mark from Yahoo Finance   - "cert_units" : executedQuantity = cert-unit count, mark from stock price × scaling factor

### backend/app/core/fifo/engine.py

295 lignes ; SHA-256 `18dc82ea41d6223453f32fa30ca6c3c23c62920cc6c2de4a761d01ef34e7f92f`.

FIFO reconstruction engine.  Pure logic — no I/O, no Yahoo Finance calls.  Marks and T0 prices are injected by the caller (see reconstruct() signature).  Modes ----- qty_mode="shares"     Quantities are real share counts.  Mark = current stock price × FX.  qty_mode="cert_units"     Quantities are cert-unit counts.  The cert-unit price at each trade is in     price_prod (already prod-ccy).  Mark = stock_price_current × scaling_factor,     where scaling_factor is derived from the earliest lot per ISIN.  recon_mode="strict"     Excess sells (sell before any matching buy) are left as negative open positions.     Signals a data quality issue — do 

Fonctions : `_weighted_avg:42`; `reconstruct:49`; `_inject_synthetic:253`

### backend/app/core/fifo/loader.py

136 lignes ; SHA-256 `de04831c4f07ee61c2958f53dfa99755babffa410897e4b7657bf1f1a4a4b099`.

Load UTI/AMC order carnet JSON files into normalized Order objects.  Supported format (from UTI platform):   { "data": { "orders": { "items": [ <order>, ... ] } } }  Each order item:   {     "id": "...",     "state": "Done",     "creationDateTime": "2025-10-14T14:01:54+00:00",     "orderedQuantity": "-4",     "executedQuantity": "-4",     "executionPrice": { "amount": "1004.69", "currency": "USD" },     "usedFxRate": "1",     "underlying": { "name": "KLA Corporation", "isin": "US4824801009", "currency": "USD" }   }  Sign convention: negative executedQuantity = SELL, positive = BUY.

Fonctions : `_f:31`; `_parse_date:39`; `_order_from_item:56`; `load_orders:106`

### backend/app/core/fifo/marks.py

281 lignes ; SHA-256 `7c6d3a906871ac1e9b340e7ea253bc4bad29548c3d16e47813edcdf4c8dd680b`.

Mark computation for open-position valuation.  Two modes:    "shares" mode     mark = current stock price in prod_ccy, sourced from amc_prices (parquet store     or live yfinance fallback).  Standard for funds where executedQuantity = shares.    "cert_units" mode     The carnet records cert-unit quantities at cert-unit prices (≈ NAV fraction per     underlying at execution time).  The true current value per cert-unit is:          mark = current_stock_price × scaling_factor      where scaling_factor k = cert_unit_price_at_T0 / stock_price_at_T0 (split-adjusted).      When a termsheet_positions.json is available, k is derived from:         t0_c

Fonctions : `get_marks_shares:36`; `get_marks_cert_units:46`; `compute_scaling_factors:78`; `fetch_t0_stock_prices:108`; `fetch_t0_prices_from_earliest_lots:124`; `fetch_t0_prices_from_lots:149`; `compute_scaling_factors:187`; `compute_scaling_factors_from_positions:205`; `build_scaling_factors_from_termsheet:221`

### backend/app/core/fifo/nav.py

340 lignes ; SHA-256 `d12ec92d03fdee1da6720d89f95ff37e231fc8c32c5d0d0c4bbcf8c2cbfe4259`.

NAV timeseries utilities for FIFO reconstruction.  Reads the fund NAV CSV (Date, Price, Outstanding quantity) to determine:   - fixing_date    : first NAV date = fund inception / fixing date   - n_certs        : number of certificates outstanding at inception   - nav_initial    : NAV per certificate at inception (usually 100.00)  These are used by build_initial_orders() to inject the fund's starting basket as real T0 BUY orders, eliminating the need for heuristic synthetic injections on termsheet ISINs.

Fonctions : `load_nav_csv:21`; `get_fixing_info:33`; `detect_nav_csv:51`; `build_initial_orders:57`; `_compute_split_factors:164`; `build_growth_topups:228`

### backend/app/core/fifo/pipeline.py

349 lignes ; SHA-256 `966ae6bd9277e8204b6d066d31c061b097d61a038aeac4b4ec8cbedf3b605ccb`.

FIFO pipeline — orchestration pure sans FastAPI.  Utilisé à la fois par l'endpoint REST (api/fifo.py) et l'étude AMC (amc_study.py).

Fonctions : `detect_order_files:27`; `load_termsheet:36`; `fix_carnet_splits:53`; `run_fifo_recon:122`

### backend/app/core/fifo/schema.py

95 lignes ; SHA-256 `61bb3ca3919af5b9b4907f2abd0c5d1ba5b3f89596ecad8d44d2f5c9bc332d79`.

FIFO data structures — pure dataclasses, no I/O.

Classes : `Order:10`; `Lot:23`; `RoundTrip:37`; `OpenPosition:56`; `SyntheticInjection:69`; `ReconResult:84`

### backend/app/core/fixing_finality.py

58 lignes ; SHA-256 `96083ec253ab23e656cbf01c0fa23a2a4a452fa05e93d90fcae8b897ea00a182`.

D03/C13: a published daily close is eligible at session end, with no delay.  Eligibility under this operational policy is not an exchange certification. Unknown venues, missing timestamps and closed sessions fail closed.

Fonctions : `utc_now:21`; `session_calendar:26`; `qualify_close:31`

### backend/app/core/inlife_valuation.py

581 lignes ; SHA-256 `f6d03c24b389d7c0a151ddc94f41e81a273d5bd39ff6a49a160acbf9d8c4d23f`.

Valorisation en cours de vie : rejouer le passé, pricer le reliquat.  Ce code vivait dans la couche « deal » et lisait des colonnes de deal. Il est ici pour que le Pricer puisse valoriser un produit à une date quelconque sans avoir à le booker — un produit du marché secondaire n'est pas un deal qu'on a traité, et le booker pour l'évaluer serait un détournement.  Le principe : sur un produit à mémoire ou à barrière, une valorisation repartie de zéro avec le bon spot serait fausse. Il faut reconstituer l'ÉTAT — coupons déjà versés, mémoire accumulée, extrema franchis, compteur d'observations — en rejouant le script sur les cours réellement cons

Fonctions : `_engine_underlyings:152`; `_shift_dividend_curve:193`; `_dates_passees:231`; `_refuser_si_le_passe_diverge:238`; `_sans_les_param_semes:260`; `_variables_ecrites:283`; `_etat_repris_par_la_variante:292`; `_compiler_variante:306`; `build_residual:334`; `_assembler_residuel:478`

Classes : `ValuationError:30`; `InLifeProduct:38`; `VariantTerms:60`; `Residual:89`

### backend/app/core/instance_signing.py

75 lignes ; SHA-256 `752c5de558a787871f017785f04aa38bec30ee09fe7d1f7fc21cde0d39a7e7f3`.

Instance key loading shared by authentication and retained evidence.

Fonctions : `_load_secret:14`; `process_secret:69`; `receipt_signing_secret:73`

Variables d'environnement lues : `STRUCTURA_JWT_SECRET`

### backend/app/core/lifecycle_controls.py

389 lignes ; SHA-256 `93f51db5cbd333cce3f5cb9b4c850709a2871f8e72a4c50fcebf6a68bdb76a16`.

Official lifecycle replay and reconciliation controls.  Indicative history may create a proposal.  Only validated official fixings may validate it.  Observation-date products can be replayed from those fixings; payoffs requiring an intra-period path are failed closed until an official daily/continuous path feed is available.

Fonctions : `official_input_hash:28`; `path_dependency_reasons:69`; `semantic_maturity_outcome:75`; `_fenetres:100`; `_dates_de_releve:111`; `_dates_de_depart:115`; `releves_sans_fixing:124`; `_reductions_declarees:153`; `_avertissement_report:162`; `horizon_contractuel:201`; `replay_official_fixings:218`

### backend/app/core/market_policy.py

20 lignes ; SHA-256 `91c32c0b9da133ad05315c0de852f352987e3658207ec99b645a9be8a1fe449e`.

Explicit dated-market freshness policy; contractual finality is separate.

Fonctions : `freshness:11`

### backend/app/core/market_snapshot.py

53 lignes ; SHA-256 `22d9cfbefe5fc6648c28448210066351d2cea48f8849624fca9fab7dfdfbcd00`.

Readers for the market snapshot frozen on a booked deal.  A deal carries its pricing assumptions as a JSON blob (``Deal.market_snapshot_json``), written once at booking and never re-keyed. Every consumer — residual MtM, Greeks, shocks, P&L explain, lifecycle replay, reinvestment — reads it back, and they must all read it the same way: two consumers disagreeing on what a missing or zero field means is how the same deal ends up with two different values.  The rate is the field that made this module necessary. It used to be read as ``(market.get("r", 3.0) or 3.0) / 100.0`` at five call sites, one of which is the *official* lifecycle replay. In P

Fonctions : `snapshot_rate_is_default:28`; `snapshot_rate:38`

Variables d'environnement lues : `STRUCTURA_DEFAULT_RATE_PCT`

### backend/app/core/market_storage.py

312 lignes ; SHA-256 `d03abef5e66500aaf7b1fba78c94d68dd17f62888c204a3dd1915e5a5f0f1251`.

Atomic market-file generations, published by one durable manifest pointer.

Fonctions : `_root:29`; `store_context:34`; `_identity:43`; `_logical_name:47`; `_entry_key:54`; `_manifest:58`; `revision:79`; `view_revision:83`; `_file_version:89`; `versions:98`; `current_path:104`; `logical_paths:126`; `read_view:141`; `consistent_read:155`; `_writer_lock:164`; `transaction:266`; `validate_frame:282`

Classes : `Transaction:201`

### backend/app/core/official_history.py

53 lignes ; SHA-256 `13317e474a2d0fd159b4ae9286f4434aa5ec9a15fbc96b344ef3c44c60c9ad42`.

Read governed fixing versions and overlay contractual dates for valuation.

Fonctions : `official_history:11`

### backend/app/core/opportunity_integrity.py

19 lignes ; SHA-256 `62674690bf7ca7a6e1de7f9e6cc1a67b5dd3075c8ce600373a3d2ad1e4c870f7`.

Serialize CRM attribution changes with their Product/RFQ/Deal consumers.

Fonctions : `lock_opportunity:7`; `has_attribution_evidence:13`

### backend/app/core/payoff_families.py

54 lignes ; SHA-256 `be76740d36788e0577ace7a2ce78a0461415dfe9b30d80691b4b772612d6ba5e`.

Shared payoff classification for Opportunity, RFQ and Deal.  Historical rows keep their original text. This module classifies them for reporting and canonicalizes newly written values without rewriting history.

Fonctions : `_key:21`; `canonical_payoff_family:38`; `normalize_new_payoff_family:43`

### backend/app/core/payoff_terms.py

19 lignes ; SHA-256 `9baf265ec8a985a42a71bc9ed5a7e3f17ebabde5ec54d8f1dc97ab82e7a936d7`.

Shared interpretation of economic terms embedded in PayScript parameters.

Fonctions : `classify_param_barrier:4`

### backend/app/core/payscript/__init__.py

0 lignes ; SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

### backend/app/core/payscript/bindings.py

205 lignes ; SHA-256 `7fdb33e9ddfaf8dc164bf5cee8ceb4b7d1c674565bf5fa6aae7b7bc66079067e`.

Explicit Economics basket binding and initial-fixing syntax.  Lower the object syntax into the existing event compiler. Initialization is a contractual fixing operation, never an ordinary coupon event on the MC grid. No user-controlled Python attribute access is emitted.

Fonctions : `code_part:20`; `lower_source:25`; `effective_parameters:115`; `asset_values:137`; `average:151`; `shift_calendars:157`; `monitoring_source:178`

Classes : `SourceBinding:15`

### backend/app/core/payscript/bridge.py

203 lignes ; SHA-256 `f6ee235f86cc594912077ce7b476381fb2c7dad95a2acff9f9f5e73421186804`.

Conditional barrier reconstruction and its explicit basket approximation.  Correlated Gaussian midpoint bridges carry the dependence between assets. At the last subinterval only, one-dimensional exact extrema are sampled with independent residuals between non-perfectly-correlated factors. Refinement reduces that residual joint-law approximation; it does not make it exact.

Fonctions : `basket_bridge_substeps:18`; `validate_bridge_domain:32`; `resolve_bridge_substeps:52`; `semidefinite_factor:62`; `_marginal_extrema:74`; `_correlation_factor:93`; `bridge_extrema:120`; `bridge_metadata:181`; `bridge_note:195`

### backend/app/core/payscript/catalogue.py

632 lignes ; SHA-256 `907fe1ac7284f65e28067f7c88354c065095b59634784261a86e2ec5d13d177a`.

Catalogue des produits génériques — module « Modèles de produits ».  GÉNÉRÉ : ne pas éditer à la main. Source : `frontend/src/data/productCatalogue.json` (liste du module « Modèles de produits » du Pricer).  Régénérer avec `backend/scripts/sync_product_catalogue.py`. `backend/tests/test_product_catalogue.py` vérifie que les deux restent identiques, que chaque fiche compile et qu'elle price sur un calendrier généré.  Une fiche porte un script générique — PARAM avec unité et valeur initiale, CONSTAT sans date — et le rôle de chaque CONSTAT : `observations` (échéancier du strike à la maturité), `maturity` (date unique à maturité), `strike_window

Fonctions : `by_family:627`

### backend/app/core/payscript/engine.py

5068 lignes ; SHA-256 `37e62be348a68ad494888ae7cdeb801376d21adeccd94bb585cce10660b2edf1`.

Monte Carlo engine — vectorized path simulation + per-path PayScript evaluation.  Models: constant (GBM), heston (QE), sabr (ATM vol), localvol (Dupire), lsv (Local-Stochastic Vol — Dupire local vol target + Heston-QE stochastic variance, recalibrated each step via a leverage function; see _simulate_lsv). Variance reduction: antithetic variates. Greeks: CRN bump-and-reprice. Analytics: payoff profile, MC paths visualization, probability analysis, historical backtest.

Fonctions : `_simulation_axis:60`; `_event_schedule:68`; `_event_times:103`; `validate_model:115`; `cholesky:148`; `sabr_vol:194`; `_heston_qe_scalar:216`; `_heston_qe_vectorized:238`; `_ncdf:285`; `_smile_vol:289`; `_bs_call_n:295`; `_dupire_vol:305`; `_validate_dividend_curve:355`; `_build_dividend_step_matrix:393`; `_build_lv_grid:420`; `_seed_spot:480`; `_simulate_gbm:490`; `_simulate_heston:534`; `_simulate_sabr:632`; `_simulate_lv:705`; `_lsv_conditional_variance:764`; `_simulate_lsv:793`; `_bridge_extrema:919`; `_build_df_arr:938`; `_df_at_time:987`; `_forward_rate_arr:1026`; `_validate_short_rate_parameters:1034`; `_ou_transition:1041`; `_hw_convexity:1048`; `_stochastic_rate_paths:1093`; `_build_rate_term:1166`; `_funding_df_arr:1192`; `_blend_rate_factor:1218`; `_rate_coupled_factor:1240`; `_strike_fix_steps:1274`; `_window_steps:1284`; `_reduce_window:1297`; `_combine_reduction:1326`; `cle_de_fenetre:1360`; `_fusionner_realise:1367`; `_niveau_initial:1390`; `_rebaser_sur_le_niveau_initial:1410`; `_constater:1436`; `_rangs_observation:1463`; `_niveaux_constates:1487`; `_state_by_asset:1556`; `_fixer_le_strike_sur_les_trajectoires:1587`; `_running_state:1622`; `_basket_references:1671`; `_path_references:1676`; `_eval_paths:1687`; `_eval_paths_detailed:2008`; `_average_antithetic_flux_maps:2227`; `run_mc:2251`; `_window_report:2760`; `_correlation_bump:2798`; `compute_greeks:2815`; `_age_compiled_script:2992`; `_theta_and_event:3036`; `run_payoff_profile:3119`; `_run_analysis:3210`; `run_mc_paths:3241`; `run_mc_proba:3257`; `build_mtf_dates:3293`; `_mtf_step:3314`; `_shift_events_for_mtf:3321`; `_mtf_past_step_map:3402`; `_mtf_residual_script:3410`; `_mtf_realized_fix:3428`; `_mtf_releves_realises:3449`; `_tranche_realise:3488`; `_scenario_realise:3504`; `_simulate_mtf_outer:3518`; `_mtf_reject_unsupported:3537`; `_mtf_date_stats:3579`; `run_mark_to_future:3633`; `_mtf_flux_rows:3995`; `_mtf_observations:4020`; `_mtf_barriers:4051`; `run_mtf_drilldown:4080`; `_historical_running_extrema:4378`; `_historical_per_asset_extrema:4408`; `_jours_de_semaine_entre:4431`; `_ajouter_jours_de_semaine:4440`; `derniere_fenetre:4522`; `seances_jusqu_a:4540`; `eval_script_on_history:4548`; `compute_irr:4966`

Classes : `_ContractEventSchedule:56`; `_RateTerm:1137`; `_RunningState:1562`; `_LectureParDate:4456`

### backend/app/core/payscript/models.py

3 lignes ; SHA-256 `3cb4f908750e30dce2d78cc460f054923a7968fc2e74d7a24bf3e4e8bed233c1`.

Canonical identifiers for quantitative pricing models.

### backend/app/core/payscript/parser.py

1465 lignes ; SHA-256 `9061ef23e7bc6943bfd37231f294fd4748b6fb5f753772463b22e9e9155c3f98`.

PayScript DSL parser. Transpiles PayScript code to compiled Python event functions.  Grammar:   PARAM NAME = value[%]   [# description]   PARAM() NAME = value[%] (per-observation values: the UI supplies a table of                            rows, one per observation, resolved by INDEX at                            runtime; the last row extends to any further                            observations, so one row behaves like a scalar.                            The value is mandatory, like PARAM's, and pre-fills                            row 1.)   CONSTAT NAME            (single date, filled in via the UI)   CONSTAT() NAME          (a CONSTAT()

Fonctions : `_parse_qualifiers:105`; `_reduction_of:115`; `check_reserved:156`; `language_vocabulary:165`; `_pobs:198`; `_transpile_expr:355`; `_sidx:432`; `_basket:446`; `_compile_body:463`; `_parse_dates:583`; `script_source_hash:634`; `parse_script:639`; `_blocs_et_references:939`; `_verifier_portee_du_rang:974`; `_analyze_monitors:1001`; `resolve_analysis_constats:1042`; `analysis_origin:1069`; `resolve_constats:1095`; `effective_T_max:1445`

Classes : `Param:182`; `Constat:219`; `CompiledScript:251`; `CompiledEvent:306`

### backend/app/core/payscript/qualification.py

164 lignes ; SHA-256 `cb48c5b7afade58947ee8140814d03083bc45b8e1e5a9537a6037b39ed9200b9`.

Versioned catalogue approvals backed by independent deterministic cashflows.  This panel checks payoff branches on a synthetic observation grid. It does not certify contractual terms, production calendars or a stochastic pricing model. Changing a source requires explicit review of its approval and reference panel.

Fonctions : `reference_cases:34`; `expected_cashflows:61`; `_run_panel:104`; `qualify_payoff:146`; `recognize_payoff:156`

### backend/app/core/payscript/scenarios.py

114 lignes ; SHA-256 `9f703737dcefb36d22bccad9f9c5235e9d0f11189a9c77716f05b0c788475909`.

Stress scenario grid — price the product under combined spot x vol shocks.  Unlike simulation.py (which shocks script PARAMs), this shocks MARKET data: spot (multiplicative, e.g. -10% -> spot_mult=0.90) and vol (additive, e.g. +5pp -> vol_add=0.05), applied uniformly to every underlying. Both are already native parameters of engine.run_mc (the same mechanism compute_greeks uses for bump-and-reprice), so this module is just the grid loop around it — no new pricing primitive needed, and every model (constant/heston/sabr/ localvol) is supported as-is since vol_add is wired into all four.  Same seed as the main pricing run (common random numbers)

Fonctions : `compute_scenario_grid:39`

### backend/app/core/payscript/schedule_model.py

226 lignes ; SHA-256 `9d5bd434f3985ba612165c940074004952cec71fd7cb3e3cb50b7144a7facbef`.

L'échéancier résolu d'un produit, comme objet de premier ordre.  Jusqu'ici cette information n'existait nulle part. Elle se dispersait, après `resolve_constats`, entre `CompiledEvent.dates`, `.window_dates`, `.payment_dates`, `.ranks`, `CompiledScript.strike_fix_dates`, puis se reconstituait différemment dans chaque consommateur — `step_map` côté Monte Carlo, une autre boucle côté rejeu historique, une troisième côté Mark-to-Future. C'est exactement ainsi que trois chemins finissent par décrire trois produits légèrement différents.  Ce module en fait une **structure unique**, construite une fois à la résolution et lisible par tous : le pricin

Fonctions : `construire:140`

Classes : `Releve:39`; `Constatation:53`; `FenetreDepart:92`; `Echeancier:103`

### backend/app/core/payscript/simulation.py

164 lignes ; SHA-256 `86ddc7d1898739ec7dfb3e269562cbc0ec2c58471e455f7eaa7c9b2fe353458e`.

Simulation tools — higher-level workflows built on top of the Monte Carlo pricing engine (engine.run_mc). Two features:    - solve_for_param: find the script PARAM value that hits a target price     (1D root-finding by bisection).   - compute_price_grid: 2D price heatmap over two script PARAM ranges.  Both vary ONE OR TWO of the script's PARAM values (the same `user_params` override mechanism used everywhere else) while holding the market data and all other PARAMs fixed, and reuse the SAME MC seed across every evaluation (common random numbers — the same trick engine.compute_greeks uses). This keeps the price curve/surface smooth enough to ro

Fonctions : `_price_with_params:26`; `_solver_result:56`; `solve_for_param:72`; `compute_price_grid:131`

### backend/app/core/payscript/templates.py

119 lignes ; SHA-256 `d0501c15311adcd5b970ee118fba609899ec4ed3809aa1d355f0395339c228d7`.

Bibliothèque de scripts PayScript de référence — corpus d'exemples.  GÉNÉRÉ : ne pas éditer à la main. Source : `frontend/src/data/payscriptTemplates.js` (sélecteur d'exemples de l'éditeur et typologie produit du module RFQ).  Régénérer avec `backend/scripts/sync_payscript_templates.py`. `backend/tests/test_payscript_templates.py` vérifie que les deux restent identiques et que chaque script compile.  Ce sont les exemples few-shot envoyés au modèle par l'assistant IA : des scripts qui pricent réellement ici, pas de la syntaxe plausible.

Fonctions : `by_group:114`

### backend/app/core/product/__init__.py

5 lignes ; SHA-256 `6022239055370819881302cfe99d6c7657d1aeec36c7d05087b6dce10b598b68`.

Canonical product data. No database, network or HTTP dependencies.

### backend/app/core/product/calendar.py

72 lignes ; SHA-256 `83fbda754994af5fc742c96b1df93cec0d0c2e182365c929565d593644702b8d`.

Freeze resolved calendar data, never compiled code or functions.

Fonctions : `freeze_calendar:13`; `_day:30`; `_sample:34`; `restore_calendar:38`

### backend/app/core/product/inputs.py

133 lignes ; SHA-256 `f4b05fee49e53c78ff3419bee17b0bbcef5695d85416391ce9b1bb6fafa00066`.

The single conversion between canonical terms and calculation requests.

Fonctions : `terms_from_input:21`; `split_pricing_input:86`; `calculation_context:91`; `pricing_input:101`; `describe_product:124`

### backend/app/core/product/models.py

195 lignes ; SHA-256 `90f27778eb5be82c88935599fb6d6c2ad3d1da7bdf2552857a599a82639ac882`.

Immutable product snapshots, distinct from external calculation inputs.

Classes : `FrozenModel:15`; `FrozenObject:19`; `UnderlyingIdentity:49`; `ContractParameter:55`; `ProductTerms:69`; `TradeIntent:136`; `CommercialContext:149`; `CalculationRef:156`; `Product:166`

### backend/app/core/product_optimizer/__init__.py

1 lignes ; SHA-256 `f91e92e9f5d8d6c912ac67040b286352655836164d0c069a1ea8d3d0b6757eb6`.

Capability-gated product exploration using the existing PayScript engine.

### backend/app/core/product_optimizer/capabilities.py

38 lignes ; SHA-256 `33b270503dd65d65e46807def28908f3074f49a2be53cff71f166e60d55fa730`.

An explicit allow-list, not a reflection of every model in the engine.

Fonctions : `capabilities:6`

### backend/app/core/product_optimizer/contracts.py

339 lignes ; SHA-256 `91003c9433bab900ca25c2e4ca7b608397a7398c1320196411b8d0277bb05229`.

Optimizer inputs use fractions, calendar months, and explicit assumptions.

Classes : `StrictModel:24`; `ParameterRange:28`; `MarketUnderlying:51`; `FieldProvenance:73`; `IssuanceEconomics:85`; `MarketAssumptions:90`; `StructuralRanges:155`; `HardConstraints:184`; `SearchConfiguration:211`; `OptimizationRequest:220`; `OptimizationCandidate:291`

### backend/app/core/product_optimizer/families.py

130 lignes ; SHA-256 `0812328b82ddc8a6d9816b95029d24f1b81ce8ab797222fb6eefd4f5808da225`.

Qualified adapters: script declarations own fields; policies own search roles.

Fonctions : `_mode_schema:40`; `family_schema:71`; `solution_scale:103`; `solution_scale_for_period:107`; `solution_definition:113`; `solved_value:117`; `coupon_labels:121`; `autocall_levels:125`

### backend/app/core/product_optimizer/market.py

60 lignes ; SHA-256 `37e5feb91d23ae1d66c6e93a12006037b21b4bb71a9b49646fb33d11b15ee03e`.

Frozen user/desk assumptions; origin is not a claim of provider quality.

Fonctions : `market_values:8`; `values_equal:17`; `freeze_market:25`; `market_engine_kwargs:58`

### backend/app/core/product_optimizer/parallel.py

80 lignes ; SHA-256 `840a2e022cc075d8364bcdbaaecc2f10f909e5176d220a5e2790dab5128c9793`.

Ephemeral streaming bridge to Structura's shared process-batch executor.

Fonctions : `iter_parallel_candidates:13`

### backend/app/core/product_optimizer/service.py

448 lignes ; SHA-256 `60d01410db6a440931255fdcd79ce7f2faf8b02d8403858e098ff5fdcf764682`.

Deterministic orchestration; all payoff evaluation stays in PayScript.

Fonctions : `solver_configuration:30`; `estimate_search:40`; `generate_candidates:96`; `build_candidate:124`; `price_candidate:165`; `filter_candidate:220`; `rank_candidates:261`; `evaluate_candidate:286`; `run_events:300`

### backend/app/core/product_optimizer/statistics.py

120 lignes ; SHA-256 `01451b06ea1edf3ca779e6776b5abf8f3efc2733e18e728914868cecdcbbf26e`.

Independent antithetic pairs, rather than 2N independent observations.

Fonctions : `normal_interval:9`; `bounded_interval:14`; `summarize_paths:27`; `apply_summary:98`

### backend/app/core/product_optimizer/validation.py

154 lignes ; SHA-256 `fbc16eae801fd23d854a662c1fd2c9cb6afc3a40e36e07c001f6eda18f0b5826`.

Hold out two reproducible samples after fixing the shortlist and its coupons.

Fonctions : `parameter_diagnostic:18`; `coupon_diagnostic:85`; `validate_candidate:89`; `evaluate_validation:144`

### backend/app/core/reference_data.py

38 lignes ; SHA-256 `18e2077541f7b09c4b2a4fbcf5c18e69136588c5849ac473756b4a4632e22a82`.

Explicit reference-data validation and governance, without external fetching.

Fonctions : `text_value:9`; `currency_value:15`; `audit_reference:35`

Classes : `ReferenceChange:23`

### backend/app/core/references.py

77 lignes ; SHA-256 `2613af89d58ab67e463543d0f38d1d57957ee53bbead9c5273d0fbc3d1bf13ee`.

Per-day sequential business references (RFQ-20260730-001, DEMO-20260730-002…).  Shared by the three tables that hand out such references — deals, indicatives and RFQs — because they had three copies of the same routine and all three carried the same defect: numbering by COUNTING the existing rows. Create 001 and 002, delete 001, create again → count is 1, so the new row is handed 002 a second time. On an RFQ that reference is the best-execution trail of a tender; on a deal it is what the client sees on a valuation note. Numbering off the highest suffix already handed out never reuses one, whatever gets deleted.  Allocation is persisted in a d

Fonctions : `next_reference:22`; `next_audited_id:49`

### backend/app/core/reinvest_proposal_pdf.py

341 lignes ; SHA-256 `f87860f1b5bee6cf4dfdd51c760879bd4168cdbf9f1efb5c5df61e5801a0ec54`.

Note de proposition de réinvestissement (PDF) — un candidat retenu par le scan Flow B (voir MEMORY investment-solution-module) devient un document présentant ses caractéristiques économiques, son profil de risque et son backtest historique. Document interne desk : pas encore pensé pour partir tel quel chez le client (voir disclaimer en pied de page).  Pure function of a plain-dict `data` payload (api/deals.py:_reinvest_proposal_data) — même logique que deal_valuation_pdf.py, module volontairement autonome (pas de helpers partagés entre modules PDF, même convention que amc_pdf.py/deal_valuation_pdf.py).

Fonctions : `_sty:48`; `_logo_image:65`; `_header:73`; `_footer:93`; `_fig_to_image:103`; `_tbl:111`; `_stat_tiles:127`; `_chart_backtest_history:148`; `_chart_window_irr:203`; `_fmt_param:231`; `generate_reinvest_proposal_pdf:235`

### backend/app/core/rfq_controls.py

371 lignes ; SHA-256 `0a19a7e38e30ee0814517b46dd27ef7789117db676e386ed622f181ee434489d`.

Central RFQ readiness, pricing-integrity and booking controls.

Fonctions : `failures_payload:32`; `_normalise:40`; `product_terms:54`; `_hash:80`; `product_terms_hash:85`; `booking_terms_differences:89`; `pricing_input_hash:128`; `_valid_iso_date:139`; `maturity_iso:147`; `rfq_readiness_failures:175`; `contract_calendar_failures:269`; `booking_gate_failures:294`

Classes : `ControlFailure:24`

Variables d'environnement lues : `STRUCTURA_RFQ_MODEL_PRICE_MAX_AGE_MINUTES`

### backend/app/core/risk_lifecycle.py

59 lignes ; SHA-256 `45b0518e8d68ccccccc0d15d2392bd2fc9de7b40a3e250117d7eb0ab165ec5e7`.

As-of lifecycle scope shared by risk calculations and deal listings.

Fonctions : `terminal_dates_by_deal:14`; `deal_risk_state:38`

### backend/app/core/risk_scope.py

32 lignes ; SHA-256 `3e332f263f963bb5462c6f2288d9249a0e43eb4e7c6c8a5f2bf00cf56659fe00`.

Explicit risk-book origin and immutable calculation-universe metadata.

Fonctions : `deal_data_scope:8`; `select_risk_deals:12`; `risk_scope_metadata:18`; `archived_data_scope:25`

### backend/app/core/roll_economics.py

116 lignes ; SHA-256 `435456c019d8d7bf0d35b1a6d175b67aa4f4bed756b88c0fe27399205dfd54ee`.

Explicit cash budget and recovery on the original holder's nominal basis.

Fonctions : `roll_budget:36`; `fixed_maturity_cap:73`; `recovery_summary:99`

Classes : `RollFinancing:13`

### backend/app/core/schedule.py

363 lignes ; SHA-256 `751197e53eee242e92692c1e73caf36ecda651da02c1e72c77aa1f0292b9ce2b`.

Schedule generation shared by preview, PayScript and contractual Products.  Three levels, mirroring the spec:   CONSTAT      — a single date.   CONSTAT()    — a schedule: start date, end date, roll date (anchor), roll                  frequency (a tenor, e.g. "3M"), and a stub convention.   CONSTAT()()  — CONSTAT() plus a sub-frequency that subdivides every interval                  of the main schedule (no stub logic of its own — it just fills                  each already-resolved interval evenly).  Stub convention (ISDA-style):   *_LAST  — the regular grid is generated FORWARD, anchored on roll_date, and             the irregular boundary 

Fonctions : `parse_tenor:60`; `_step:68`; `generate_main_schedule:80`; `_fill_interval:126`; `generate_schedule:140`; `generate_observation_schedule:217`; `period_windows:241`; `observation_window:288`; `_dedupe:352`

Classes : `StubConvention:37`; `Tenor:45`

### backend/app/core/schemas.py

711 lignes ; SHA-256 `6aa7ebf1afe42c558e0dbf2692bb32692494cd5ac63f50a9483cdf343ba8a404`.

Fonctions : `validate_term_curve:19`; `validate_correlation_matrix:42`

Classes : `VolatilitySurfaceParams:68`; `UnderlyingParams:86`; `PricingRequest:202`; `PricingResponse:282`; `ParseRequest:322`; `ParseResponse:326`; `VariantOverrides:346`; `AnalysisBase:360`; `ProfileRequest:429`; `PathsRequest:433`; `ProbaRequest:438`; `BacktestRequest:442`; `BacktestCompareRequest:450`; `MtfRequest:475`; `ScriptGenerateRequest:487`; `MtfDrilldownRequest:507`; `SolverRequest:525`; `ReinvestCandidate:537`; `ReinvestMetricFilter:542`; `ReinvestScanRequest:553`; `ReinvestProposalRequest:577`; `GridRequest:600`; `ScenarioRequest:613`; `CalendarPolicyRequest:626`; `BusinessDayRequest:633`; `ScheduleRequest:650`; `PeriodWindowPreviewRequest:673`; `WindowPreviewRequest:693`

### backend/app/core/session_security.py

22 lignes ; SHA-256 `298d02163a9c06a527d2266748bcb574ffa664dceabbfe54cba72171c1e8f73d`.

Shared session policy; independent of business database initialization.

Fonctions : `validate_password:7`; `session_claims:13`; `session_digest:17`

### backend/app/core/smile_calibration.py

211 lignes ; SHA-256 `153f71eb8a2eb1b4c7fe49ec52c417029dc904013b7db633507b2bbe95ae6283`.

Reproducible fits and bounded diagnostics of synthetic SSVI targets.

Fonctions : `heston_prices:19`; `heston_calls:93`; `qualification:97`; `calibrate_surface:111`

### backend/app/core/valuation_attribution.py

47 lignes ; SHA-256 `e9f7de2ec1a38cef51121b578ea0a05a9d85b436ce8958950fc388c88964c08f`.

Shared factor boundaries and contractual cash conventions for valuation explain.

Fonctions : `with_dividend_inputs:11`; `contractual_cash_in_period:25`

### backend/app/core/valuation_context.py

450 lignes ; SHA-256 `fc60df8e2976da42ef21f01fb0a5407142a99cbfb379c11dd552b25db8dafba1`.

Canonical inputs shared by pricing, MtM, Greeks, shocks and VaR.  The booked deal stores a market snapshot for two distinct reasons: reopen the original assumptions in the Pricer, and explain which inputs produced the initial fair value.  This module is the single unit boundary between the API schemas (engine units) and that persisted display snapshot.  ``ValuationContext`` itself is deliberately plain JSON data.  It contains no database row, closure or compiled PayScript and can therefore cross the worker process boundary used by VaR. ``run_valuation`` prices this context and ``run_analysis`` derives bounded analytics through the same ``run_

Fonctions : `canonical_json:28`; `canonical_fingerprint:35`; `_json_transport_value:39`; `json_transport_json:56`; `json_transport_fingerprint:61`; `valuation_context_from_dict:101`; `valuation_context_from_request:107`; `run_analysis:130`; `run_valuation:146`; `_display_underlying:230`; `_pillar_label:253`; `pricing_input_payload:260`; `market_snapshot_from_pricing_input:272`; `build_pricing_receipt:338`; `verify_pricing_receipt:352`; `funding_from_market_snapshot:379`; `deterministic_cashflow_pv:406`; `unsettled_cashflows_pv:439`

Classes : `ValuationContext:67`

### backend/app/core/valuation_note_support.py

123 lignes ; SHA-256 `1f7968132a1881f2adced3866212d12154a5740930e7dcd7736e4de5a68cde9f`.

Pure domain helpers shared by valuation-note assembly and API delivery.

Fonctions : `events_for_note:11`; `monitor_levels:45`; `_greeks_state:82`; `residual_greeks:95`

### backend/app/core/valuation_notes.py

235 lignes ; SHA-256 `cee2e604bf88af03ced16f86a4c522ab8a3ac4f0f59f824f6c960f52fff98110`.

Frozen valuation evidence, ordered attribution and editable note rendering.

Fonctions : `note_snapshot:16`; `saved_evidence:43`; `frozen_greeks:74`; `compare_runs:108`; `_compare_runs:122`; `build_note:198`; `render_note:225`

### backend/app/core/valuation_runs.py

206 lignes ; SHA-256 `909f77c87c9bcd09c00ebef711e4a0f6ecca47cc582000788a742a217dfa3a67`.

Append-only evidence and offline replay for explicit deal valuations.

Fonctions : `_repository_root:24`; `engine_identity:28`; `calculation_identity:49`; `replay_context:62`; `_market_evidence:86`; `_data_versions:102`; `current_fixings_match:115`; `stage_valuation_run:130`; `replay_valuation_run:173`

Variables d'environnement lues : `STRUCTURA_ENGINE_VERSION`

### backend/app/core/var_engine.py

454 lignes ; SHA-256 `a923544ccc49025df0dc0fc0ae3340f1d7c59d56804eb9ffd0498a90d41f06f3`.

VaR/ES engine — the business logic layer on top of core/compute/. Owns everything specific to "what is a market scenario" and "what does a VaR study's results mean"; core/compute/ itself stays product-agnostic (see its own docstring) and never imports anything from this module.  Three responsibilities:   1. build_deal_scenario_base() — extracts the pure-data equivalent of      core/deal_valuation.py:mtm_core's ctx for one active deal, ONCE, so every      scenario job for that deal can share it (the replay itself is cheap —      no Monte Carlo — recomputing it per scenario would be wasted work, and      more importantly the compiled objects in

Fonctions : `build_deal_scenario_base:46`; `_shock_corr_scalar:144`; `apply_scenario_to_deal_base:164`; `_usable_tickers:190`; `_horizon_returns:200`; `_rolling_vol:209`; `_rolling_avg_corr:223`; `generate_historical_scenarios:239`; `calibrate_comovement:293`; `generate_parametric_scenarios:333`; `aggregate_var:383`

Classes : `MarketScenario:154`

### backend/app/core/variants.py

539 lignes ; SHA-256 `50d37aa35406e554748d4050ac7c1ee38f6de9c3f2532a1994963cb4968304c0`.

Variantes d'un deal : un delta, jamais une copie.  Une variante ne stocke que ce qui DIFFÈRE de son parent. Ce n'est pas une économie d'octets, c'est ce qui rend possibles les deux exigences d'affichage sans lesquelles l'outil ne sert à rien :    - **colorer ce qui a changé** est gratuit, parce que la couleur est     l'appartenance au delta et non le résultat d'une comparaison qu'il faudrait     refaire à chaque affichage, sur les bons champs, sans en oublier ;   - **griser ce qui a été retiré** est simplement IMPOSSIBLE avec une copie.     Dans une copie, un sous-jacent retiré est absent, et rien ne distingue « on     l'a enlevé » de « il n'

Fonctions : `contexte_vide:54`; `_fendre:62`; `canonique:87`; `_underlying:101`; `resoudre:110`; `_poser:140`; `_retirer:190`; `_exiger_globale_amendable:224`; `_exiger_panier_modifiable:250`; `_ajouter_au_panier:264`; `_retirer_du_panier:310`; `decrire_ecarts:333`; `lire:352`; `_descendre:373`; `valider:381`; `_decaler:422`; `deriver_roll:430`; `params_moteur:499`; `termes_de_rejeu:523`

Classes : `VariantError:50`

### backend/app/core/volatility_surface.py

190 lignes ; SHA-256 `a93372141b048fb218fa7b377c94290688b98f221da710d4d5318991e58a55b2`.

Indicative SSVI targets for editable assumptions and offline comparisons.  This module is not a market-data loader or an automatic deal calibration. Targets use forward log-moneyness, with flat or piecewise-linear ATM variance and phi(theta)=eta/sqrt(shape_scale+theta). Sufficient Gatheral-Jacquier conditions are checked over the entire declared maturity horizon, for every strike.

Fonctions : `surface_from_underlying:174`

Classes : `SSVISurface:16`; `TermSSVISurface:111`

### backend/app/core/watchlist_observations.py

79 lignes ; SHA-256 `fcb4b104e8a79e466e4d3c2b3401eb15ef07214b196b85dcaaeff70e202ceb4f`.

Indicative unadjusted-close observations, indexed by booked constituent.

Fonctions : `_positive:7`; `watchlist_observations:17`

### backend/app/core/workflow.py

141 lignes ; SHA-256 `467c871fbe34b23f47461081525ecac492a0094c673d1dc36bc1d2fcf5a22ffd`.

Canonical workflow states introduced by the Phase-0 safety tranche.  Legacy RFQ status values remain stored for compatibility.  ``rfq_business_status`` is the single documented bridge to the target vocabulary; no controller may invent a second mapping.

Fonctions : `amendment_four_eyes_enabled:13`; `rfq_business_status:122`; `derive_rfq_status:130`

Classes : `WorkflowValue:34`; `DataCategory:39`; `QuoteFirmness:48`; `FixingStatus:54`; `FixingPolicy:68`; `LifecycleStatus:81`; `AmendmentStatus:93`; `RfqBusinessStatus:100`

Variables d'environnement lues : `STRUCTURA_AMENDMENT_FOUR_EYES`

### backend/app/db/__init__.py

0 lignes ; SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

### backend/app/db/archive_integrity.py

59 lignes ; SHA-256 `bc0b008b494b5721c31429074b68973e757a438c5da08e4a5e37ef901a6be4af`.

Identical archive protections for table creation and normal upgrades.

Fonctions : `statements:5`; `register:23`; `study_statements:32`; `document_statements:38`; `migrate:50`

### backend/app/db/ccr_models.py

64 lignes ; SHA-256 `6e9503fad867213455a3a869c156a5bc73ee0d91c83d558096d0c87cc833ee91`.

Organisation-owned CCR extensions of the existing Counterparty catalog.

Classes : `CCRRecord:7`; `CCRCreditProfile:17`; `CCRMasterAgreement:22`; `CCRCSAAgreement:26`; `CCRNettingSet:30`; `CCRCreditLimit:34`; `CCRCollateralPosition:38`; `CCRCreditOverride:42`; `CCRExposureCalculation:46`

### backend/app/db/database.py

1044 lignes ; SHA-256 `78c4572ff65efa43bfa07910fd5cdf8dd76c9bb3335f5ced997829ab1d53f854`.

Fonctions : `_sqlite_integrity_pragmas:29`; `_hash_pw:39`; `_verify_pw:43`; `get_session:47`; `_migrate_underlying_classes:52`; `_migrate:58`; `_ensure_unique_reference:653`; `_ensure_one_deal_per_rfq:682`; `_ensure_rfq_integrity_triggers:701`; `_make_kid_vev_nullable:728`; `_backfill_portfolio_memberships:765`; `_backfill_rfq_statuses:792`; `_retire_four_eyes_fixing_policy:834`; `init_db:895`; `_seed_underlyings:928`; `_seed:949`; `_seed_counterparties:986`; `_seed_rfq_providers:1021`

Variables d'environnement lues : `STRUCTURA_BOOTSTRAP_PROFILE`

### backend/app/db/models.py

2046 lignes ; SHA-256 `7b0a5e8999660f6ea8740c329319d0085e0702c28e0818084e78f62f2f285d4a`.

Fonctions : `position_sign:1187`

Classes : `ProductRecord:16`; `ProductTermsVersion:38`; `ProductRevision:51`; `ProductCalculationRun:65`; `ProductCommand:83`; `BookingCommand:95`; `ArchivedDocument:109`; `VariantStudyArchive:125`; `OptimizerResearch:136`; `Entity:161`; `User:168`; `RevokedSession:182`; `RfqDesk:189`; `RfqDeskMembership:199`; `RfqOwnership:212`; `RfqDeskShare:222`; `RfqRelationship:237`; `RfqRelationshipSide:253`; `RfqExchangeRound:267`; `RfqRoundLink:285`; `RfqSolicitation:291`; `RfqBankCase:309`; `RfqBankPublicationPolicy:323`; `RfqBankQuoteDraft:333`; `RfqQuotePublication:349`; `RfqExecutionAgreement:368`; `RfqExecutionBooking:405`; `RfqSendCommand:419`; `ReferenceCounter:429`; `AdminAuditLog:436`; `AuditEvent:449`; `UatGenerationBatch:468`; `Folder:496`; `Portfolio:505`; `DealPortfolioMembership:522`; `Script:535`; `Deal:579`; `TradeAmendmentRequest:760`; `DealContractVersion:784`; `Document:798`; `AmcStudy:813`; `Indicative:829`; `KidRecord:869`; `EmtRecord:897`; `RfqBookingEvidence:931`; `RfqRequest:942`; `RfqQuote:1032`; `Counterparty:1066`; `ReferenceCatalogState:1086`; `Underlying:1093`; `RfqProvider:1129`; `RfqProviderContact:1145`; `Alert:1160`; `AlertRead:1179`; `DealEvent:1210`; `OfficialFixingVersion:1268`; `LifecycleProposal:1317`; `ShockRun:1350`; `ComputeBatch:1368`; `ComputeJob:1404`; `ValuationRun:1427`; `ValuationNote:1451`; `ValuationNoteVersion:1468`; `SchedulerRun:1481`; `Client:1517`; `ClientMandate:1597`; `ClientPreferenceStatement:1625`; `Person:1663`; `Affiliation:1690`; `ClientCoverage:1726`; `ContactCoverage:1741`; `Interaction:1758`; `InteractionFollowUp:1784`; `InteractionParticipant:1805`; `Opportunity:1818`; `OpportunityParticipant:1877`; `ClientImportBatch:1907`; `ClientTradeHistory:1937`; `ConstraintDefinition:2004`

### backend/app/db/organization_scope_migrations.py

10 lignes ; SHA-256 `fdb629f76a70b790a98df0ad8960960c248fb1e3f843deae1f27f7d72c223e42`.

Freeze organization ownership when upgrading formerly personal collections.

Fonctions : `migrate_organization_scopes:5`

### backend/app/db/product_migrations.py

133 lignes ; SHA-256 `c2d467ba1f3e1dc5014aaef383bd0d7000f92b06a815c5ac463903112ea434b2`.

Additive product links; called only by the normal application migration.

Fonctions : `migrate_product_links:5`

### backend/app/db/rfq_electronic_models.py

38 lignes ; SHA-256 `d238d3c3bb0a2d6e5aabe8fe7ad6bcbcae73ab9158ac7071a83906a90f37ba63`.

Durable bilateral execution facts, separate from transport acknowledgements.

Classes : `RfqElectronicExecution:7`; `RfqElectronicBooking:25`; `RfqElectronicEvidence:34`

### backend/app/db/rfq_execution_integrity.py

56 lignes ; SHA-256 `506cab19d43a41073d374c3c657ecd9fad14ec077e38b65413675929bb08b1cf`.

Immutable treatment snapshots and local execution/booking evidence.

Fonctions : `install_execution_guards:5`

### backend/app/db/rfq_quote_migrations.py

12 lignes ; SHA-256 `57ea2295d11ecf4c9eb1fa584bd162f605d1c329360e250bf1748e2c3aef9141`.

Additive quote revisions; historical decisions are never silently requalified.

Fonctions : `migrate_quote_revisions:5`

### backend/app/db/rfq_reconciliation_models.py

19 lignes ; SHA-256 `0073c7bf84c67be3a2fe52ff6a4f8ece0467c3e9ee59cf844841638edc537d25`.

Immutable local and peer statements about a shared electronic execution.

Classes : `RfqReconciliationStatement:7`

### backend/app/db/rfq_transport_integrity.py

21 lignes ; SHA-256 `7eb2907fe85627131c7875f82dbc559c37fb969e2bb25a2de8d833dbdfe629d7`.

SQLite guards for immutable transport contents and durable receipt evidence.

Fonctions : `install_transport_guards:5`

### backend/app/db/rfq_transport_models.py

83 lignes ; SHA-256 `b3995aeb82fdcaaebb4064e94d176e0e3728b6f71dbc42dce0954b9a221e7d3c`.

Additive durable transport records; local business IDs never cross installations.

Classes : `RfqInstallation:8`; `RfqChannel:14`; `RfqRemoteLink:31`; `RfqTransportOutbox:40`; `RfqTransportInbox:64`; `RfqTransportAttempt:77`

### backend/app/db/trading_migrations.py

9 lignes ; SHA-256 `1e1204600414e5b088657c00f74a4726c5592d677c3e528d4a4fa04015406242`.

Keep the actual settlement declaration separate from contractual dates.

Fonctions : `migrate_settlement_evidence:5`

### backend/app/db/trading_models.py

36 lignes ; SHA-256 `40bd46b9d2bd92a466f188c035e6151d476048930fd4665f32c8219299b9a83e`.

Bilateral trading relationships and local execution reconciliation.

Classes : `TradingRelationship:7`; `TradingExecution:20`

### backend/app/db/underlyings_seed.py

89 lignes ; SHA-256 `3b486fdaf46dde10c527a3ab062461c6132a2dc39d318036354eda5f07ab82e4`.

Seed du référentiel de sous-jacents.  Repris tel quel du fichier frontend qui tenait cette liste avant qu'elle passe en base : mêmes tickers, mêmes libellés, mêmes groupes. Un ticker peut figurer dans deux groupes — BNP Paribas est à la fois une valeur du CAC et une banque — et c'est voulu : la table est unique sur le couple (ticker, groupe).  Les devises sont déduites du suffixe de cotation (.PA → EUR, .SW → CHF…) : c'est une inférence, corrigible depuis l'administration.

Fonctions : `seeded_asset_class:82`

### backend/app/hybrid/__init__.py

1 lignes ; SHA-256 `a59066775e11e5acfc3d22217798d7d2e59708b5404868b74e28f37a5eab0654`.

Explicit local hybrid deployment foundations; no central business processing.

### backend/app/hybrid/admin_adoption.py

143 lignes ; SHA-256 `a4af9f8015d0b4344aa99a5e342f0bef85b4edee0db1c849d1b07052a52d35f5`.

Explicit, offline adoption of the original single-admin development workspace.  Never called by startup: an occupied unmarked database still fails preflight. The private bootstrap credential is corroborating evidence, not a replacement for the operator's explicit manifest identity and database fingerprint.

Fonctions : `fingerprint:24`; `_offline:28`; `_inspect:46`; `_config:79`; `inspect_adoption:89`; `adopt:97`

### backend/app/hybrid/admin_workbench.py

113 lignes ; SHA-256 `f1f81d10287c1cafb4f04fdc54e228623db266292aae45dfec66a5a444fe727d`.

Complete local development application, independent of client installations.

Fonctions : `preflight:19`; `config:46`; `options:56`; `seed:64`; `login:91`

Classes : `AdminWorkbenchIdentity:12`

Variables d'environnement lues : `STRUCTURA_ADMIN_WORKBENCH_CONFIG`, `STRUCTURA_BOOTSTRAP_PROFILE`, `STRUCTURA_DATA_DIR`, `STRUCTURA_DEVELOPER_ACCESS`

### backend/app/hybrid/business.py

165 lignes ; SHA-256 `6c72eab6dbd21c064d668f77989c4b4dfef5b49dbe6588516cf2c4019dc0084b`.

Transactional managed bootstrap. Later starts observe drift without restoring grants.

Fonctions : `preflight:36`; `seed:69`; `inspect:139`

Classes : `HybridBootstrap:14`; `DevelopmentRedemption:24`

### backend/app/hybrid/config.py

99 lignes ; SHA-256 `ef415d20e4a1866662d2bcab1452345b402f3b92e8d36e0b5da3ad4bcda0ac75`.

Validated installation manifests, independent of business database imports.

Fonctions : `read_config:68`; `current_config:76`; `credentials:87`; `signing_secret:95`

Classes : `InstallationConfig:12`; `DirectoryEntry:51`

Variables d'environnement lues : `STRUCTURA_DATA_DIR`, `STRUCTURA_INSTALLATION_CONFIG`

### backend/app/hybrid/control_services.py

94 lignes ; SHA-256 `2da9ac1a8efd47c2f4275ae20660015ec844cf189a6f8bd964e61f4123470763`.

Owned auxiliary services outside the six manual business installations.

Fonctions : `prepare_controls:16`; `simulation_config:56`; `owned_stop:67`; `redirect_app:75`

Variables d'environnement lues : `STRUCTURA_INSTANCE_CONTROL_TOKEN`, `STRUCTURA_LAUNCH_ID`

### backend/app/hybrid/deployment.py

350 lignes ; SHA-256 `ca9b3bf769d3f958b5ac5f2c8ec6e8296aa605b175c0e04e1e350c6708353f5e`.

Prepare and operate only explicitly owned, fictitious local installations.

Fonctions : `atomic_json:30`; `load_layout:39`; `prepare:67`; `environment:150`; `initialize:174`; `probe:183`; `stop_candidate:194`; `stop:211`; `start:274`

Variables d'environnement lues : `OPENAI_API_KEY`, `STRUCTURA_LAUNCH_ID`

### backend/app/hybrid/development.py

84 lignes ; SHA-256 `2f84b80852e77a008d30588aebebed64ba3d9d8addf1faa207b21ab142b376e6`.

Explicit loopback-only development access; no organization password broker.

Fonctions : `enabled:26`; `origins:32`; `add_portal_cors:40`; `require_access:48`; `issue:62`; `verify:72`

Classes : `DevelopmentTarget:14`; `DevelopmentTicket:21`

Variables d'environnement lues : `STRUCTURA_DEVELOPER_ACCESS`

### backend/app/hybrid/launcher.py

488 lignes ; SHA-256 `df599522500cfda4d089f94f6c5178ca6bebffbdc150f93de8e586c600e84057`.

Shared launcher controller and a small French desktop menu.

Fonctions : `main:458`

Classes : `Launcher:27`; `LauncherWindow:140`

### backend/app/hybrid/launcher_widgets.py

126 lignes ; SHA-256 `b0c1b70d31529db6d9643e9eb95112cde4791497d23a5ee11bfb331d82c46fc0`.

Small vector widgets for the desktop launcher; no additional dependency.

Fonctions : `rounded:8`; `icon:98`

Classes : `RoundedPanel:17`; `RoundedButton:41`

### backend/app/hybrid/platform.py

350 lignes ; SHA-256 `c7cba9ac87e8f04040272b932d0f88c1611665106cdc17f84b1b0231e19c5260`.

Central directory only: separate schema, signing key and administrative scope.

Fonctions : `connect:34`; `initialize:46`; `create_app:89`

Classes : `PasswordChange:27`

Variables d'environnement lues : `STRUCTURA_INSTANCE_CONTROL_TOKEN`, `STRUCTURA_LAUNCH_ID`

### backend/app/hybrid/reset.py

169 lignes ; SHA-256 `ed308317586cddec7fc57c9cb1faaf1905704b680ce2da6a2f66fb980f7ff626`.

Inventory and retire identified fictitious data, without broad directory deletion.

Fonctions : `safe_path:16`; `fingerprint:30`; `identified_database:35`; `inventory:44`; `require_inactive:114`; `apply_inventory:149`

### backend/app/hybrid/simulation.py

114 lignes ; SHA-256 `bc72633f0f5b07bfb4dea5f151d5d7b3e3a8f8fde433782eff994af403a46ba6`.

Isolated simulation controller; only signed central administrative requests.

Fonctions : `request_signature:21`; `initialize_controller:29`; `create_app:43`

Variables d'environnement lues : `STRUCTURA_LAUNCH_ID`

### backend/app/hybrid/simulation_gateway.py

72 lignes ; SHA-256 `25ab5994e7a538db1dcc1d57f67cae9f84f4400ca585b8cd769a06f71a4a1566`.

Administrative gateway only; never forwards manual organization APIs.

Fonctions : `register_gateway:15`

### backend/app/main.py

306 lignes ; SHA-256 `c270b4c3091899e4deb237449792141a7f21ebc2ce174849670952092b04b4aa`.

Fonctions : `consultation_read_only:92`; `on_startup:102`; `stop_optimizer_researches:117`; `start_lifecycle_scheduler:137`; `start_rfq_transport:203`; `stop_rfq_transport:224`; `health:234`; `stop_owned_instance:254`; `consultation_session:268`

Variables d'environnement lues : `PYTEST_CURRENT_TEST`, `STRUCTURA_BOOTSTRAP_PROFILE`, `STRUCTURA_CONSULTATION_LOCK_DIR`, `STRUCTURA_CONSULTATION_USER_ID`, `STRUCTURA_DEVELOPER_ACCESS`, `STRUCTURA_DISABLE_RFQ_TRANSPORT`, `STRUCTURA_DISABLE_SCHEDULER`, `STRUCTURA_INSTANCE_CONTROL_TOKEN`, `STRUCTURA_INSTANCE_ID`, `STRUCTURA_LAUNCH_ID`

### backend/app/runtime.py

31 lignes ; SHA-256 `9d49b2993c90074925a5153a3cefb29895eddb2b579c1d56a65d4ca7a3561017`.

Instance configuration and optional isolated business clock.

Fonctions : `consultation_mode:10`; `data_path:14`; `business_now:21`; `business_today:28`

Variables d'environnement lues : `STRUCTURA_BUSINESS_CLOCK`, `STRUCTURA_CONSULTATION`, `STRUCTURA_DATA_DIR`

### backend/app/services/__init__.py

0 lignes ; SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

### backend/app/services/agent_workshop/__init__.py

1 lignes ; SHA-256 `1c506ff7d285a92868850596e7a3c263d11861cdfe89e692c06cbbfaf21c5f4a`.

AI user acceptance workshop for isolated Structura instances.

### backend/app/services/agent_workshop/brain.py

260 lignes ; SHA-256 `9090b948ede3179bb5194b8002358967bfc4f47284a26bb8e7b249dfd1194ecb`.

One actual model decision at a time, with private role-scoped context.

Fonctions : `_openai_decision:31`; `model_request:46`; `action_schema:106`; `prepare_model:174`; `decide:188`

Classes : `Decision:13`; `DecisionCancelled:20`; `DecisionError:24`

### backend/app/services/agent_workshop/configuration.py

253 lignes ; SHA-256 `9c7bc1d1e1a847d695da8c4b86ff4888746ea0485f32486a5f8c61071e5df06d`.

Versioned diagnostic scenarios and inexpensive, side-effect-free forecasts.

Fonctions : `default_participants:111`; `default_products:120`; `default_calendar:126`; `is_diagnostic:132`; `participants:136`; `schedule:140`; `validate_scenario:162`; `funding_at:190`; `preview:199`

Classes : `StrictModel:21`; `FundingPoint:25`; `Economy:30`; `Participant:61`; `ProductSettings:74`; `RfqSlot:92`; `CalendarMonth:98`; `Cadences:104`

### backend/app/services/agent_workshop/consultation.py

201 lignes ; SHA-256 `50e2e59102d2b0f0138cb50f7e19daec76d20c193d9f6a5b16fde462a2d0e60c`.

Native read-only viewers of saved actor books, independent of AI execution.

Classes : `Consultations:24`

### backend/app/services/agent_workshop/coverage.py

159 lignes ; SHA-256 `79d922b5a782d46e06004f18b2d88c7a47fd97ff6f71fd340e9f9ba57825effa`.

Bounded native checks, with honest evidence and no code repair during a run.

Fonctions : `exercise:13`

Classes : `IntegrityError:9`

### backend/app/services/agent_workshop/diagnostic.py

426 lignes ; SHA-256 `d76a65819005cc248785afcb3810114d1dde5c5359cd7fc2c52b13d4b0f7c410`.

Event-driven diagnostic controller using Structura's ordinary business tools.

Fonctions : `diagnostic_defaults:15`; `calendar_month:36`; `convert_legacy:42`; `observation:63`; `ready_action:133`; `review_due:152`; `checked_action:173`; `run:277`

### backend/app/services/agent_workshop/engine.py

779 lignes ; SHA-256 `57bf910fa19ab7faa07594ec7e9e956036196bcb698b177f3bd0a832c0f9ecf8`.

Persistent controller; commercial decisions belong to the model agents.

Fonctions : `public_state:21`; `safe_record:28`; `failure_message:36`; `routine_decision:47`; `needs_agent_decision:63`; `account_model_usage:67`; `model_limit_reason:78`; `workflow_facts:87`; `context_result:96`; `context_message:116`; `context_terms:124`; `observation:139`

Classes : `Manager:303`

### backend/app/services/agent_workshop/historical_market.py

141 lignes ; SHA-256 `6db67c559afd6a50fb8caa9a23bb74bc6399dde5f134500d567130ac38fb7665`.

Read existing local price series and freeze their observations for replay.

Fonctions : `cache_roots:15`; `market_path:20`; `cached_series:24`; `sources:58`; `freeze_market:74`; `historical_history:104`

### backend/app/services/agent_workshop/instances.py

452 lignes ; SHA-256 `474498eeb5f604bdd0bd83db9c4264a118a4e171c2192aae90a31fece6078bbc`.

Fonctions : `free_port:21`; `clock_file:27`

Classes : `Instances:33`

### backend/app/services/agent_workshop/lease.py

55 lignes ; SHA-256 `204e5c8fa5cd591193a453bf1424e100a3b6f40f8a80ae9a044340d327edc5b1`.

A process-wide OS lease, released automatically on controller death.

Classes : `CampaignLease:5`

### backend/app/services/agent_workshop/native_rfq.py

181 lignes ; SHA-256 `e76840bb4afd6b31bc76cfad5b9224e7cea01cc31abec42c814c4578d259ace4`.

Simulation adapter for the existing authenticated bilateral RFQ workflow.

Fonctions : `requester:10`; `command:14`

Classes : `NativeRfq:18`

### backend/app/services/agent_workshop/openai_model.py

183 lignes ; SHA-256 `d15fd3c10ebf9f83e51ec3f0cc6220d2e320ecb6f9b17913fc1132e4935392af`.

OpenAI decisions for fictitious workshop campaigns only.  The existing LLM key loader is shared with Structura's other AI features. This adapter deliberately does not reuse their free-form completions: workshop decisions need cancellation, JSON validation, and per-campaign usage accounting.

Fonctions : `price:51`; `_content:56`; `_request:67`; `_decision_schema:105`; `response:126`

Classes : `ModelUnavailable:33`; `BudgetReached:39`; `IncompleteOutput:43`

### backend/app/services/agent_workshop/persistence.py

20 lignes ; SHA-256 `4ec2d15bb1dcc296ce06b4a5b64d70e598a25ec79e16247667b11aa62d98eca5`.

Atomic evidence writes resilient to brief Windows reader locks.

Fonctions : `atomic_write:7`

### backend/app/services/agent_workshop/reconciliation.py

93 lignes ; SHA-256 `d3dcd6d4f14a3774db4c542d976de37b49ede5ae3f47c33d54159f061f6b28af`.

Reconcile recorded native executions without inferring missing evidence.

Fonctions : `check_books:8`

### backend/app/services/agent_workshop/store.py

311 lignes ; SHA-256 `b29bee87dbcf40e593277e4b7c17121cd34c7be20dfcd9283410426bf4fb6304`.

Fonctions : `contract_mandate:284`; `source_manifest:298`

Classes : `CampaignConfig:20`; `Store:85`

Variables d'environnement lues : `STRUCTURA_WORKSHOP_ROOT`

### backend/app/services/agent_workshop/tools.py

1094 lignes ; SHA-256 `0a5860d6e9260e9de40a9a4306bda0cea41970a65d9c58e78a88327448317b9a`.

Agent tools acting on public authenticated HTTP and real browser screens.

Classes : `_LoginRejected:23`; `Tools:27`

### backend/app/services/archived_documents.py

97 lignes ; SHA-256 `915e99fcc708662fd790ad26ada6585cd24b7b946330f79d0824255e169a9277`.

Dated immutable documents. Export reads retained bytes and never reprices.

Fonctions : `sign_preview:27`; `seal:37`; `verify_preview:44`; `unseal:55`; `stage:69`; `load:87`; `response:94`

Classes : `DocumentSelection:17`; `ProposalFreeze:22`

### backend/app/services/booking_commands.py

37 lignes ; SHA-256 `0a140490b7cac65d2df7ea0e23876c662211532b5258d4fa2d7899472fa26925`.

Durable per-actor booking intents; no successful command without its Deal.

Fonctions : `booking_intent:9`; `stage_booking_command:34`

### backend/app/services/business_access.py

83 lignes ; SHA-256 `54f7e7b5d883207b438c68314af3d23b80dd82a7faaee998304f3f6e854efc8e`.

Canonical read scope for booked contracts and their derived projections.

Fonctions : `deal_entity_id:8`; `can_read_deal:15`; `visible_deals:41`; `can_read_organization_record:45`; `can_read_product_contract:56`

### backend/app/services/calibration_evidence.py

70 lignes ; SHA-256 `c2131aa2027184920fe9951daf46dcef2d6fcf6d5db0b27849218f0b62807b6e`.

Server-authenticated calibration dossiers, archived with pricing inputs.

Fonctions : `sign_calibration:13`; `verify_calibration:19`; `validate_pricing_calibrations:32`

### backend/app/services/legal_identity.py

76 lignes ; SHA-256 `8c8cc0bc9efecf477850bfe534dcd77ac7e5e80f207008506f7db155286959da`.

Resolve local legal IDs; labels describe identities and never replace them.

Fonctions : `active_counterparty:8`; `booking_exception:15`; `provider_identity:38`; `network_counterparty:57`; `relation_counterparty:65`; `quote_counterparty:72`

### backend/app/services/lifecycle_alerts.py

271 lignes ; SHA-256 `3f21ce9c67af01cab332d6efb1d07ce7f9396ddc1451611a1ef00368f4bba5fc`.

Daily lifecycle refresh + alert creation.  One pass over ACTIVE deals officialises controlled, unadjusted provider closes and may apply a deterministic terminal result. Barrier alerts remain indicative until their contractual observation date.  Ran two ways: - by the in-process scheduler (main.py) every day at 23:00 local time,   after the US close — events are close-of-day observations and Yahoo   only serves reliable closes, so intraday runs would add noise, not info; - on demand for one user, or the full visible book for an administrator, via   POST /api/alerts/refresh-book.  Alerts are deduplicated by logical fact.  A terminal KI crossing

Fonctions : `configure_lifecycle_handlers:45`; `_alert_once:52`; `_pct:63`; `refresh_book:67`; `scheduled_slot:175`; `_claim_scheduler_run:184`; `run_scheduled_refresh:228`; `run_missed_refresh_if_needed:269`

### backend/app/services/llm/__init__.py

140 lignes ; SHA-256 `e73be84e045ee06e3e08c3d5da81de9e34e86de228c88fdc1eb77d52293d358c`.

Assistant de scripting PayScript adossé à un modèle de langage.  Le modèle écrit une STRUCTURE ; il ne price pas et ne fixe aucun niveau que l'utilisateur n'a pas donné. Le moteur Monte-Carlo reste seul juge du prix.  Enchaînement : `generate()` construit le prompt (prompt.py), appelle le fournisseur (providers.py), assainit et contrôle la réponse (validate.py), et réessaie une fois si le parser refuse — en lui renvoyant son propre message d'erreur.

Fonctions : `_examples_version:36`; `generate:43`; `preview_prompt:124`

### backend/app/services/llm/analysis.py

159 lignes ; SHA-256 `9e7c65bbb670d929c6b8ac04bf36e28bd77cd169ecca0f8955b9f14eb23170c6`.

Second avis d'un modèle de langage sur un produit déjà pricé.  Distinct de l'assistant de scripting (`__init__.generate`) : celui-là ÉCRIT une structure à partir d'une description, celui-ci COMMENTE une structure déjà décrite et déjà pricée.  La règle qui gouverne tous les prompts : **le modèle ne valide jamais un chiffre.** Un LLM ne peut pas vérifier un Monte-Carlo, et il produira une réponse plausible et fausse avec aplomb. On lui pose des questions de structure et d'économie ; le moteur reste seul juge du prix. Chaque prompt système le dit explicitement, parce qu'un modèle à qui on tend un prix cherchera spontanément à le commenter.  Le r

Fonctions : `construire_prompts:111`; `analyse_produit:140`

### backend/app/services/llm/examples_extra.py

15 lignes ; SHA-256 `5f7ca492a9b5450f54f9681ab0892eb3120dcf5b9cc07930750fe390aabd99f8`.

The assistant teaches the same generic models as the editor.

Fonctions : `all_examples:6`

### backend/app/services/llm/keys.py

64 lignes ; SHA-256 `d5fbb068b77bc920743af3e3639fa35282b096205ce47f2629eec8fd1e6826e7`.

Clés d'API des fournisseurs de modèles.  Même politique que la clé de signature JWT (`api/auth.py`) : l'environnement d'abord, puis un fichier dans `backend/data/` — le répertoire qui héberge la base. Attention : `backend/data/` n'est **pas** ignoré en bloc par git, seuls certains motifs le sont ; les deux fichiers ci-dessous ont donc leur ligne nommément dans `.gitignore`, comme `.jwt_secret`. Jamais dans le dépôt, jamais en base, et **jamais dans le bundle frontend** : c'est pour cela que l'appel au modèle part du serveur. Un appel navigateur → OpenAI expédierait la clé à chaque utilisateur de l'application.  Ollama ne demande aucune clé : 

Fonctions : `load_key:33`; `missing_key_message:57`

### backend/app/services/llm/prompt.py

190 lignes ; SHA-256 `dbfa5b8e659cec00d1c60a0079752385b4c58e14e1fa1374dcb9f19fb98bd0e4`.

Construction du prompt de l'assistant de scripting.  Le corps du prompt système est `docs/reference/PAYSCRIPT_REFERENCE.md`, lu à l'exécution. Recopier la grammaire ici en ferait une seconde source de vérité qui dériverait en silence : le prompt promettrait au modèle une syntaxe que le parser refuse, et l'assistant échouerait à chaque appel sans que rien n'explique pourquoi. `test_payscript_reference.py` verrouille l'accord entre la référence et le parser ; ce module se contente de la servir.

Fonctions : `_read_reference:48`; `select_examples:57`; `build_system_prompt:97`; `build_user_prompt:156`; `build_repair_prompt:171`; `build_refine_prompt:184`

### backend/app/services/llm/providers.py

280 lignes ; SHA-256 `ebd5af9a4c01b10071c86075471b694bec24fa3e69d0ab591d59743cbc4ba2ee`.

Trois fournisseurs de modèles, une seule interface.  Ollama, OpenAI et Anthropic exposent la même chose — un message système, un message utilisateur, du texte en retour — sous trois enveloppes JSON différentes. Trois adaptateurs `httpx` suffisent ; installer trois SDK reviendrait à porter trois arbres de dépendances et trois cycles de versions pour trois requêtes HTTP identiques.  Ollama est le défaut : local, sans clé, et surtout la description du produit ne quitte pas la machine.

Fonctions : `validate_ollama_url:77`; `ollama_models:84`; `available_providers:101`; `_post:143`; `_complete_ollama:177`; `_complete_openai:189`; `_complete_anthropic:205`; `_modele_effectif:228`; `complete_with_metadata:251`; `complete:275`

Classes : `ProviderInfo:30`; `Completion:41`; `LlmError:73`

### backend/app/services/llm/validate.py

381 lignes ; SHA-256 `05470710bdf54d66c35aabc0140726cd64a1bd1855553f4c6c3670544bdf1883`.

Assainissement et contrôle d'un script produit par un modèle.  Le parser attrape les scripts qui ne compilent pas. Il n'attrape pas le cas dangereux : un script qui compile, price, et décrit un AUTRE produit que celui demandé. Un `STOP` oublié fait un autocall qui ne rappelle jamais ; un `WOF` à la place d'un `WOF_MIN` transforme une barrière américaine en européenne, ce qui vaut plusieurs points de nominal. Aucun des deux ne lève quoi que ce soit.  Ce module produit donc une fiche de contrôle. Elle ne bloque rien : elle rend visible ce que le script fait vraiment, pour que la relecture humaine porte sur des points précis au lieu d'être une r

Fonctions : `split_response:79`; `_strip_fences:102`; `structural_checks:130`; `smoke_price:224`; `_contexte_marche:255`; `price_check:284`; `_looks_like_a_note:312`; `validate:330`

Classes : `Check:28`; `Validation:35`

### backend/app/services/llm/workbench.py

52 lignes ; SHA-256 `3521b822bb0582a3bf41d84f03b4698fb86637e0f43453c760b765ca8525a660`.

Prompt preview, context binding and provenance shared by the assistants.

Fonctions : `prompt_preview:12`; `resolve_prompt:18`; `connection_options:28`; `generate_text:37`

### backend/app/services/market_data.py

625 lignes ; SHA-256 `7f42c98fe2b70678360ecb968cd914d8ad43c8414897a7bc08f3fa4a1c18e273`.

Yahoo Finance market data — realized vol, dividends, correlations, historical prices.

Fonctions : `load_hist_vol:25`; `normalize_market_data_provider:89`; `market_data_provider_for_deal:105`; `_business_sessions_between:127`; `vider_cache_prix:145`; `load_hist_prices:153`; `_load_hist_prices_uncached:201`; `load_yahoo_reference_closes:269`; `search_symbols:397`; `probe_ticker:427`; `dividend_profile:466`; `_ts:623`

### backend/app/services/market_history.py

195 lignes ; SHA-256 `38f7be196f65afb0f85a8e0abc88470dbd2b833b9fd516e175ed28bf0558fcf0`.

Shared durable provider observations, separate from pricing assumptions.

Fonctions : `_path:16`; `clean_series:21`; `store_history:28`; `local_history:46`; `_profile_path:90`; `local_profile:95`; `store_profile:104`; `align_history:110`; `storage_status:168`

### backend/app/services/optimizer_market.py

97 lignes ; SHA-256 `486d6c2c756f0ccffb2b2fe854867b767e080f18a87c93236cd46c423f53e163`.

Dated optimizer references built from the existing historical services.

Fonctions : `_number:34`; `load_optimizer_references:38`

Classes : `MarketReferenceRequest:16`

### backend/app/services/optimizer_research.py

187 lignes ; SHA-256 `8d200ef3c1e630cd802552ffcf31d137171b0c0477bd260bd3578cc8a5178a52`.

Persist owned research requests and run calculations independently of HTTP clients.

Fonctions : `dump:35`; `fingerprint:38`; `owned:41`; `existing:47`; `create:54`; `projection:88`; `partial_result:99`; `start:114`; `cancel:169`; `recover:175`; `shutdown:184`

Classes : `ResearchCreate:23`; `ArchiveChange:31`

### backend/app/services/product_lifecycle.py

130 lignes ; SHA-256 `2c54e0c7b0acc2affba46094e5719f2ad10b88540fac12ff764895c161a532c3`.

Project governed Deal lifecycle state into the shared Product dossier.

Fonctions : `_json_object:13`; `_iso:17`; `lifecycle_snapshot:21`; `stage_product_lifecycle:88`

### backend/app/services/product_receipts.py

97 lignes ; SHA-256 `1f39212d11c0a71f7b4c4c419241d7e7ef1ec57f0dea4ca699a59848c3b539bb`.

Stateless server evidence for optionally retained exploratory prices.

Fonctions : `_signature:18`; `_claims:27`; `signed_receipt:38`; `verify_server_receipt:53`

### backend/app/services/product_repository.py

333 lignes ; SHA-256 `286b7056f698aa17aaaa3d00fdddaecdfd3ae79538bc9d5f4a26b9289ab48ad6`.

Explicit product persistence. Callers own the transaction and commit.

Fonctions : `owned_record:29`; `load_product:77`; `stage_revision:117`; `stage_new_product:167`; `stage_internal_product:191`; `stage_terms:224`; `stage_booked_terms_amendment:244`; `lock_command_actor:273`; `previous_command:280`; `stage_command:292`; `stage_calculation:299`

Classes : `ProductError:23`

### backend/app/services/rfq_access.py

171 lignes ; SHA-256 `765b3cfc14560f37ff013f31a20f2adbffee85772e88a800b3f3710c6a0037bf`.

Desk-scoped access to new RFQs. Historical rows retain creator-only access.

Fonctions : `_valid:19`; `membership_rights:23`; `profile_rights:37`; `ownership:50`; `effective_rights:54`; `require_rfq_access:78`; `require_create_desk:91`; `visible_rfqs:101`; `lock_rfq_organization:110`; `assign_rfq:127`

### backend/app/services/rfq_bank.py

178 lignes ; SHA-256 `e6860ffb6fad5c061649949975cb85453b688c45b7df97bc9c1eb50698bb1886`.

Native bank Product and desk responsibility; no commercial price publication.

Fonctions : `case_for_product:20`; `require_action:24`; `require_open:38`; `work_row:55`; `_calculation_row:80`; `claim:91`; `assign:133`; `private_product_access:162`; `require_pricing:169`

### backend/app/services/rfq_booking.py

148 lignes ; SHA-256 `35b6b61241a96f60b3786825de582670af3f2c6b0d54f83be82791d79d27509e`.

Operational booking from retained evidence; private inputs stay server-side.

Fonctions : `retain_evidence:26`; `_context:65`; `review:102`; `book:116`

Classes : `ReviewBooking:20`

### backend/app/services/rfq_electronic.py

350 lignes ; SHA-256 `5f7058171522d428bbc508507e67f4273f7365ddb337dc66924bafc52ead2035`.

Explicit bank decisions on exact published quotes, durably delivered both ways.

Fonctions : `available:62`; `for_item:66`; `public_row:73`; `workspace:89`; `requester_workspace:94`; `request:104`; `_bank_checks:146`; `receive_request:181`; `decide:206`; `_decide:229`; `receive_decision:246`; `protect_publication:291`; `_bank_entry:297`; `bank_booking_context:304`; `attach_booking:331`; `_audit:346`

Classes : `ElectronicRequest:25`; `BankDecision:33`; `WireRequest:40`; `WireDecision:50`

### backend/app/services/rfq_exchange.py

200 lignes ; SHA-256 `b364de12819c9b02d47eb969cfbfe3e6a57d470e60afc77bf4635f03461a7247`.

Atomic local delivery of immutable Product projections, with no pricing side effects.

Fonctions : `digest:17`; `iso:22`; `round_for:26`; `close_round:30`; `identity:39`; `freeze:49`; `delivery_row:80`; `tracking:100`; `delivery_with_responses:117`; `replay:132`; `deliver:142`; `can_receive:188`; `require_received:196`

### backend/app/services/rfq_execution.py

375 lignes ; SHA-256 `e499a2249bf41984353e07451154931db308fdf4e7d15a70fc79a0a48ac71e33`.

Explicit external treatment evidence and idempotent local booking (RFQ V1).

Fonctions : `active_agreement:45`; `row:51`; `workspace:72`; `protect_mutation:79`; `_counterparty:85`; `_check_relation:93`; `_snapshot:107`; `request_treatment:149`; `confirm_treatment:186`; `_require:250`; `cancel_request:257`; `_record:273`; `booking_request_hash:281`; `booking_context:285`; `attach_booking:335`; `flag_external_conflict:349`; `record_booking_block:360`

Classes : `TreatmentRequest:24`; `TreatmentConfirmation:34`

### backend/app/services/rfq_model_reference.py

24 lignes ; SHA-256 `f98be2214d1c8af8e125c49ca77f3ee0aa9553e63415aa6eae7f92ad5111bfe8`.

Freeze the desk benchmark when a quote is received, without backfilling history.

Fonctions : `snapshot:8`

### backend/app/services/rfq_publication.py

404 lignes ; SHA-256 `b961b1f3a6e8922053049d8697bcdc3e18290a27351213cdc8f0a01db87fae92`.

Human approval of an exact bank response, then atomic local delivery.

Fonctions : `policy_row:68`; `put_policy:74`; `publication_for_quote:106`; `publication_state:110`; `public_row:136`; `utc:160`; `commercial_checks:167`; `save_draft:211`; `expected_draft:258`; `validate:269`; `validation_current:287`; `publish:295`; `withdraw:355`; `workspace:389`

Classes : `PolicyPut:25`; `QuoteCondition:33`; `DraftPut:39`; `Decision:62`

### backend/app/services/rfq_quote_integrity.py

27 lignes ; SHA-256 `8ed42b3255e9d97146ed996c1ada177d45ac16ecb58a85198211a761ba11a615`.

Shared quote/decision identity and currency checks against frozen Product terms.

Fonctions : `request_currency:5`; `effective_currency:10`; `same_currency:14`; `clear_selection:19`; `selection_matches:26`

### backend/app/services/rfq_reconciliation.py

261 lignes ; SHA-256 `2661581bc37377834ad2a3d03135b33ac0c6956ae6c81e164ff7ab69c4f4dd14`.

Compare dated public execution/booking facts; never copy or repair private books.

Fonctions : `available:62`; `latest:66`; `fact:72`; `expected_booking:99`; `workspace:111`; `authorize:168`; `stage_current:186`; `refresh:205`; `receive:226`; `publication_time:252`; `confirmed_booking_pending:257`

Classes : `RefreshCommand:24`; `BookingFact:29`; `WireStatement:48`

### backend/app/services/rfq_relationships.py

362 lignes ; SHA-256 `1e848838d4422ed383926c7802bfa1d645ed4cd1d768e05eaa816139189ba6ed`.

Bilateral RFQ permissions, independent of private pricing and booking terms.

Fonctions : `organization_admin:108`; `sides:115`; `require_relation:120`; `status:127`; `public_row:142`; `row_for:165`; `_validate_mapping:174`; `_validate_config:196`; `_lock_version:206`; `_audit:216`; `create_relation:222`; `update_relation:252`; `recognize_relation:273`; `suspend_relation:294`; `eligibility:312`

Classes : `SharedContact:24`; `RelationshipTerms:37`; `RelationshipConfiguration:78`; `RelationshipCreate:88`; `RelationshipUpdate:94`; `RelationshipDecision:98`; `RelationshipSuspension:104`

### backend/app/services/rfq_state.py

459 lignes ; SHA-256 `9d91ef2d57c4ca06fcf9a26ceabbe3c9907321c1773986f5498fefdca49deb59`.

Canonical RFQ facts and projections shared by routes and workflows.

Fonctions : `_utc_iso:56`; `_booked_deals_by_rfq:70`; `_rfq_row:81`; `_sync_product_rfq:187`; `_counterparty_by_provider:237`; `_quote_row:264`; `_get_quotes:325`; `_derive_status:364`; `_sync_status:377`; `superseded_quote_ids:390`; `_get_owned:403`; `_rfq_product:408`; `compose_rfq_pricing_input:426`

Classes : `RfqPricingInput:50`

### backend/app/services/rfq_transport.py

662 lignes ; SHA-256 `9885d1ab628967885b4df0380a4208142df1e64d1ac657a29fc2c78b9ceabc6d`.

Authenticated bilateral RFQ transport with transactional outbox and receipts.  HMAC keys belong to one explicitly paired channel. HTTPS supplies confidentiality; no JWT, private calculation or local database key is part of the protocol.

Fonctions : `canonical:37`; `identity:41`; `endpoint:53`; `agreement:72`; `channel_current:80`; `signature:95`; `envelope:99`; `verify:106`; `confirm:126`; `channel_for_relation:146`; `link_for:150`; `queue:154`; `wire_message:172`; `shared_request:177`; `transport_row:185`; `remote_source:198`; `receive_request:210`; `receive_event:283`; `receive:402`; `call_peer:471`; `probe:483`; `retry_checks:492`; `reconcile_closures:554`; `deliver_one:582`; `process_pending:654`

Variables d'environnement lues : `STRUCTURA_RFQ_ALLOW_LOOPBACK_HTTP`

### backend/app/services/scenario_market.py

70 lignes ; SHA-256 `728a5afbe524e4739e76223d0f2745bbea28f6f6b4338e3a04c53b2d2b0725ce`.

Explicit synthetic market source for private acceptance installations only.

Fonctions : `configured_path:13`; `create_market:19`; `history:47`

Variables d'environnement lues : `STRUCTURA_SCENARIO_MARKET`, `STRUCTURA_WORKSHOP_CHILD`

### backend/app/services/transcription/__init__.py

15 lignes ; SHA-256 `2d1b798f8cefa07418efa8d62591e3d0f231c1e33c01d6eb77d5551a63f9a055`.

Dictée de la description produit — transcription locale.  L'utilisateur décrit son produit à voix haute plutôt qu'au clavier. Le texte transcrit atterrit dans le champ de saisie, éditable, et rien ne part au modèle de langage tant qu'il n'a pas cliqué : une transcription qui avale « à tout moment » décrit un autre produit, et l'aide de l'écran dit elle-même que c'est la différence entre deux produits qui ne valent pas le même prix.

### backend/app/services/transcription/engines.py

278 lignes ; SHA-256 `111e52b421da472e73ba6b91a8bd6a84ed2e490417dfc4fc106975d299f3155f`.

Dictée : un registre de moteurs, un seul livré — et il est local.  Même parti pris que `services/llm/providers.py`, pour la même raison, en plus fort. Ollama y est le défaut parce qu'« une description de produit structuré envoyée à un tiers, c'est une idée de structuration qui sort du desk » ; à la dictée on en dit davantage qu'au clavier — le nom du client, la contrepartie, le niveau visé sortent sans qu'on y pense. L'audio ne quitte donc pas la machine, et aucun moteur distant n'est branché ici.  Rien de tout cela ne s'exécute DANS le serveur : la transcription part dans un processus séparé (`worker.py`), qui explique pourquoi. En résumé, c

Fonctions : `_faster_whisper_disponible:90`; `modele_telecharge:102`; `available_engines:116`; `_run_worker:137`; `_diagnostic:200`; `warmup:218`; `_normalise:227`; `_echo_du_vocabulaire:231`; `transcribe:243`

Classes : `EngineInfo:65`; `TranscriptionError:86`

### backend/app/services/transcription/vocabulary.py

30 lignes ; SHA-256 `0d90bfa92477b5a5822616bd5da33c54bb9d590ce425531aafd2aa08dba7af15`.

Vocabulaire de desk soufflé au moteur de dictée.  Whisper accepte un `initial_prompt` : un texte qui n'est pas transcrit, mais qui conditionne le registre et l'orthographe attendus. C'est le seul vrai levier de qualité disponible — et la raison principale d'avoir écarté l'API vocale du navigateur, qui n'offre aucun équivalent.  Sans amorçage, la dictée rend « autocall » en « auto-call » ou « oto call », « worst-of » en « worse of », et surtout « soixante pour cent » en « 60 » sans le signe. Le pourcentage compte : un niveau de barrière mal transcrit produit une description plausible d'un autre produit.  Contrainte dure : Whisper ne retient qu

### backend/app/services/transcription/worker.py

110 lignes ; SHA-256 `7ed950d20b62c038c278f6556a872d833d309b083f3afbcd4a6a7d5c0b29d112`.

Transcription dans un processus séparé — et pourquoi elle ne peut pas être ailleurs.  ctranslate2, le moteur de faster-whisper, embarque son propre runtime OpenMP (`libiomp5md.dll`). numpy et scipy en ont déjà chargé un quand le serveur démarre. Deux runtimes OpenMP dans le même processus Windows ne cohabitent pas : le chargement du modèle part en violation d'accès, le processus meurt sur place, sans exception Python et donc sans trace. Mesuré : `import app.main` puis chargement du modèle = code de sortie 139, alors que le même chargement dans un processus neuf passe sans rien dire.  Il existe une variable d'environnement qui fait taire le co

Fonctions : `rendre:38`; `main:60`

### backend/app/services/uat_generation.py

1616 lignes ; SHA-256 `3dba3c9471423acfd4d978035e0f3a46099b9e9bd1897f2ca3e159be6e6e9aa0`.

Admin generator for Product -> RFQ -> booking -> valuation UAT data.  The generator deliberately calls the production Product, RFQ, booking, fixing, MtM and Greeks functions. It does not write a parallel approximation of the workflow. Synthetic rows are tagged with an explicit batch id, making preview reproducible and cleanup strictly scoped to data created by this service.

Fonctions : `configure_uat_workflows:49`; `_require_workflows:57`; `_utc_iso:170`; `_batch_row:174`; `list_batches:210`; `generator_config:217`; `_validate_request:258`; `_quarter_year:336`; `_profile_for_index:341`; `_family_for_profile:347`; `_profile_tenor_floor:362`; `_to_business_day:373`; `_profile_dates:389`; `_phoenix_period_coupon:433`; `_product_script:444`; `_build_specs:449`; `_price_specs:584`; `_pricing_scenarios:727`; `_retained_pricing_count:739`; `_workflow_label:743`; `preview_generation:754`; `_create_product:810`; `_retain_product_calculations:840`; `_create_rfq:880`; `_book:959`; `_assert_product_continuity:1001`; `_load_yahoo_fixings:1049`; `_materialize_lifecycle_profile:1071`; `_age_generated_records:1151`; `_valuation_dates:1211`; `_materialize_post_booking_runs:1228`; `generate_batch:1311`; `delete_batch:1527`

Classes : `UatGenerationRequest:134`

## Frontend

Tests inclus ; les APIs dynamiques ne sont pas toutes déductibles par extraction lexicale.

| Source | Lignes | Store | API littérales / tests |
|---|---|---|---|
| `frontend/src/App.vue` | 46 |  |  |
| `frontend/src/charts/theme.js` | 111 |  |  |
| `frontend/src/components/AiWorkbench.vue` | 79 |  |  |
| `frontend/src/components/AppHeader.vue` | 164 |  |  |
| `frontend/src/components/AutoFixingExceptionModal.vue` | 275 |  |  |
| `frontend/src/components/BacktestTab.vue` | 313 |  |  |
| `frontend/src/components/BookingPricingReview.vue` | 104 |  |  |
| `frontend/src/components/CalendarPolicyFields.vue` | 48 |  | /api/calendar/catalog |
| `frontend/src/components/CcrAmount.vue` | 16 |  |  |
| `frontend/src/components/CcrCreditCheck.vue` | 109 |  |  |
| `frontend/src/components/CcrProgress.vue` | 25 |  |  |
| `frontend/src/components/CcrResult.vue` | 154 |  |  |
| `frontend/src/components/ComparatorTab.vue` | 279 |  | /api/finance/hist_vol?tickers=${encodeURIComponent(row.tickers.join(, /api/price |
| `frontend/src/components/ConstatWindowFields.vue` | 86 |  |  |
| `frontend/src/components/ContextSelector.test.js` | 51 |  | 5 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/ContextSelector.vue` | 81 |  | /api/platform/development/access, /api/platform/development/admin-workbench |
| `frontend/src/components/DealReferenceLink.vue` | 19 |  |  |
| `frontend/src/components/DealTab.test.js` | 208 |  | 13 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/DealTab.vue` | 915 |  | /api/clients, /api/clients/${clientId}/contacts, /api/clients/${clientId}/mandates, /api/deals/counterparties, /api/opportunities?client_id=${clientId}&open_only=true, /api/products/${deal.product_id}, /api/rfq/${store.currentRfqId}/terms, /api/trading/book-note, /api/trading/relationships |
| `frontend/src/components/DemoModeToggle.vue` | 94 |  |  |
| `frontend/src/components/DividendCurveCard.vue` | 223 |  |  |
| `frontend/src/components/EconomicsCalendars.test.js` | 219 |  | 19 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/EconomicsTab.test.js` | 45 |  | 3 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/EconomicsTab.vue` | 510 |  | /api/calendar/resolve |
| `frontend/src/components/EmtPanel.vue` | 454 |  | /api/emt/compute, /api/emt/save, /api/emt/synthesize |
| `frontend/src/components/EventsTab.test.js` | 71 |  | 5 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/EventsTab.vue` | 1370 |  | /api/clients, /api/clients/${clientId}/contacts, /api/clients/${clientId}/mandates, /api/deals/${deal.value.id}/events/${ev.id}/fixing-versions/${version.id}/evidence, /api/deals/counterparties, /api/opportunities?client_id=${clientId} |
| `frontend/src/components/FluxDecomposition.vue` | 286 |  |  |
| `frontend/src/components/FundingCurveCard.vue` | 184 |  |  |
| `frontend/src/components/HelpTip.vue` | 69 |  |  |
| `frontend/src/components/InLifeNotAlignedBanner.vue` | 36 |  |  |
| `frontend/src/components/InputRetentionUi.test.js` | 146 |  | 7 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/KidPanel.vue` | 383 |  | /api/kid/compute, /api/kid/save |
| `frontend/src/components/LifecycleRefreshSummary.test.js` | 48 |  | 7 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/LifecycleRefreshSummary.vue` | 27 |  |  |
| `frontend/src/components/MarketDataProvenance.vue` | 23 |  |  |
| `frontend/src/components/MarketParams.vue` | 459 |  |  |
| `frontend/src/components/MicDictation.vue` | 426 |  |  |
| `frontend/src/components/MtfDrilldownModal.vue` | 370 |  |  |
| `frontend/src/components/MtfTab.vue` | 636 |  |  |
| `frontend/src/components/ObservationSchedule.vue` | 278 |  | /api/schedule/generate, /api/schedule/period-window |
| `frontend/src/components/OptimizerCurveInput.test.js` | 24 |  | 3 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/OptimizerCurveInput.vue` | 43 |  |  |
| `frontend/src/components/OptimizerNumberInput.test.js` | 43 |  | 3 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/OptimizerNumberInput.vue` | 26 |  |  |
| `frontend/src/components/OptimizerPanel.vue` | 16 |  |  |
| `frontend/src/components/OptimizerPayoffFields.test.js` | 42 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/OptimizerPayoffFields.vue` | 73 |  |  |
| `frontend/src/components/OptimizerPricingResults.test.js` | 52 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/OptimizerPricingResults.vue` | 78 |  |  |
| `frontend/src/components/OptimizerRadar.vue` | 32 |  |  |
| `frontend/src/components/OptimizerResearchResults.test.js` | 51 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/OptimizerResearchResults.vue` | 84 |  |  |
| `frontend/src/components/PathsTab.vue` | 180 |  |  |
| `frontend/src/components/PayScriptCalendars.vue` | 114 |  | /api/schedule/window |
| `frontend/src/components/PayScriptConfigurations.vue` | 102 |  | /api/db/scripts |
| `frontend/src/components/PayScriptEditor.vue` | 365 |  |  |
| `frontend/src/components/PayScriptPresetPicker.vue` | 66 |  |  |
| `frontend/src/components/PriceComparisonPanel.vue` | 321 |  |  |
| `frontend/src/components/PriceGridHeatmap.vue` | 198 |  |  |
| `frontend/src/components/PriceSeriesImport.test.js` | 36 |  | 1 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/PriceSeriesImport.vue` | 51 |  |  |
| `frontend/src/components/ProbaTab.vue` | 322 |  |  |
| `frontend/src/components/ProductContextBar.vue` | 225 |  |  |
| `frontend/src/components/ProfileTab.vue` | 197 |  |  |
| `frontend/src/components/ResultsPanel.test.js` | 29 |  | 1 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/ResultsPanel.vue` | 970 |  |  |
| `frontend/src/components/RfqBankQuotePanel.vue` | 132 |  | /api/rfq-inbox/${id}, /api/rfq-inbox/${id}/${path} |
| `frontend/src/components/RfqElectronicExecutionPanel.test.js` | 93 |  | 7 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/RfqElectronicExecutionPanel.vue` | 124 |  | /api/rfq-inbox/${id}, /api/rfq-inbox/${id}/electronic-execution/${entry.value.id}/decision, /api/rfq/${id}/terms |
| `frontend/src/components/RfqExchangePanel.vue` | 201 |  |  |
| `frontend/src/components/RfqExecutionPanel.vue` | 153 |  | /api/rfq/${id}/terms |
| `frontend/src/components/RfqNetworkSettings.vue` | 84 |  | /api/rfq-transport${path} |
| `frontend/src/components/RfqParamsEditor.vue` | 68 |  |  |
| `frontend/src/components/RfqPricingPanel.test.js` | 39 |  | 5 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/RfqPricingPanel.vue` | 181 |  |  |
| `frontend/src/components/RfqReconciliationPanel.test.js` | 62 |  | 5 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/RfqReconciliationPanel.vue` | 71 |  | /api/rfq-reconciliation/${id} |
| `frontend/src/components/RfqTransportStatus.vue` | 30 |  | /api/rfq-transport/messages/${props.transport.message_id}/retry |
| `frontend/src/components/ScenarioGrid.vue` | 139 |  |  |
| `frontend/src/components/ScriptAssistantModal.test.js` | 54 |  | 2 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/ScriptAssistantModal.vue` | 239 |  | /api/script/generate, /api/script/prompt |
| `frontend/src/components/SensitiveChart.vue` | 37 |  |  |
| `frontend/src/components/SensitiveValue.vue` | 62 |  |  |
| `frontend/src/components/SimulationTab.vue` | 11 |  |  |
| `frontend/src/components/SolverPanel.vue` | 211 |  |  |
| `frontend/src/components/SummaryTab.vue` | 163 |  | /api/product/analyse |
| `frontend/src/components/UnderlyingVolFields.vue` | 105 |  |  |
| `frontend/src/components/VariantBar.vue` | 260 |  | /api/db/scripts/${parentId.value}/variants, /api/db/scripts/${v.id} |
| `frontend/src/components/VariantCompareTab.test.js` | 112 |  | 8 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/components/VariantCompareTab.vue` | 329 |  | /api/db/scripts/${parentId.value}/variants, /api/variants/archives, /api/variants/archives/${id}, /api/variants/compare |
| `frontend/src/components/VolSmile.vue` | 209 |  |  |
| `frontend/src/components/VolSurfaceEditor.vue` | 212 |  | /api/volatility/validate |
| `frontend/src/components/WorkshopBooks.vue` | 41 |  |  |
| `frontend/src/components/WorkshopConfiguration.vue` | 79 |  |  |
| `frontend/src/components/WorkshopHelp.vue` | 7 |  |  |
| `frontend/src/components/WorkshopIssues.vue` | 52 |  |  |
| `frontend/src/components/WorkshopMonitor.vue` | 64 |  |  |
| `frontend/src/components/YieldCurveCard.vue` | 284 |  |  |
| `frontend/src/components/clients/ChangeCompanyModal.vue` | 146 |  |  |
| `frontend/src/components/clients/ClientCard.vue` | 578 |  |  |
| `frontend/src/components/clients/ClientFormModal.vue` | 179 |  |  |
| `frontend/src/components/clients/ConstraintFieldModal.vue` | 196 |  |  |
| `frontend/src/components/clients/ConstraintsPanel.vue` | 551 |  |  |
| `frontend/src/components/clients/CyclePanel.vue` | 151 |  |  |
| `frontend/src/components/clients/DimensionGrid.vue` | 178 |  |  |
| `frontend/src/components/clients/ImportPanel.vue` | 379 |  | /api/client-import/${route}, /api/client-import/batches, /api/client-import/batches/${lot.id}/revert, /api/client-import/schema, /api/client-import/template.${format} |
| `frontend/src/components/clients/InteractionFormModal.vue` | 133 |  |  |
| `frontend/src/components/clients/LostReasonModal.vue` | 63 |  |  |
| `frontend/src/components/clients/OpportunityFormModal.vue` | 331 |  | /api/clients/${clientId}/contacts, /api/clients/${clientId}/mandates |
| `frontend/src/components/clients/PersonFormModal.vue` | 181 |  |  |
| `frontend/src/components/clients/RangeRail.vue` | 130 |  |  |
| `frontend/src/components/clients/TechnicalPanel.vue` | 298 |  |  |
| `frontend/src/components/clients/ValuePicker.vue` | 217 |  |  |
| `frontend/src/components/ui/ActionMenu.vue` | 45 |  |  |
| `frontend/src/components/ui/AlertMessage.vue` | 45 |  |  |
| `frontend/src/components/ui/BackLink.vue` | 39 |  |  |
| `frontend/src/components/ui/BaseModal.vue` | 155 |  |  |
| `frontend/src/components/ui/ConfirmDialog.vue` | 55 |  |  |
| `frontend/src/components/ui/DataFilterBar.vue` | 63 |  |  |
| `frontend/src/components/ui/EmptyState.vue` | 30 |  |  |
| `frontend/src/components/ui/LoadingSpinner.vue` | 36 |  |  |
| `frontend/src/composables/useAiSettings.js` | 54 |  | /api/ai/providers?ollama_url=${encodeURIComponent(url)} |
| `frontend/src/composables/useAiWorkbench.js` | 78 |  |  |
| `frontend/src/composables/useAiWorkbench.test.js` | 137 |  | 12 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/composables/useBookingMtm.js` | 192 |  | /api/deals/${id}/mtm?stream=true, /api/deals/valuation-runs/latest-mtm?${query} |
| `frontend/src/composables/useBookingMtm.test.js` | 195 |  | 15 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/composables/useConfirm.js` | 66 |  |  |
| `frontend/src/composables/useContextChanges.js` | 18 |  |  |
| `frontend/src/composables/useDataFilter.js` | 120 |  |  |
| `frontend/src/composables/useDividendCurve.js` | 23 |  |  |
| `frontend/src/composables/useDocumentScrollLock.js` | 22 |  |  |
| `frontend/src/composables/useDocumentScrollLock.test.js` | 30 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/composables/useMarketAssumptions.js` | 184 |  |  |
| `frontend/src/composables/useMarketAssumptions.test.js` | 253 |  | 18 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/composables/useObservationPreview.js` | 239 |  | /api/calendar/resolve, /api/finance/hist_prices?${q}, /api/schedule/generate |
| `frontend/src/composables/useProductSummary.js` | 344 |  |  |
| `frontend/src/composables/useSensitiveChart.js` | 39 |  |  |
| `frontend/src/composables/useValuationNoteDraft.js` | 63 |  | /api/valuation-notes, /api/valuation-notes/${id}, /api/valuation-notes/sources/ |
| `frontend/src/composables/useValuationNoteDraft.test.js` | 68 |  | 5 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/composables/useValuationRunSelection.js` | 37 |  |  |
| `frontend/src/composables/useValuationRunSelection.test.js` | 38 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/composables/useVariantDelta.js` | 200 |  |  |
| `frontend/src/composables/useVariantDelta.test.js` | 161 |  | 11 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/composables/useVariantMark.js` | 112 |  |  |
| `frontend/src/composables/useYieldCurveAnchor.js` | 59 |  |  |
| `frontend/src/composables/useYieldCurveAnchor.test.js` | 112 |  | 11 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/data/commonUnderlyings.js` | 75 |  | /api/finance/underlyings |
| `frontend/src/data/commonUnderlyings.test.js` | 62 |  | 8 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/data/payscriptTemplates.js` | 9 |  |  |
| `frontend/src/main.js` | 19 |  |  |
| `frontend/src/router/index.js` | 302 |  |  |
| `frontend/src/stores/asyncContext.test.js` | 192 |  | 12 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/stores/auth.js` | 179 | auth | /api/auth/development-admin-session, /api/auth/development-session, /api/auth/identity, /api/auth/login, /api/auth/logout, /api/auth/me, /api/platform/development/session |
| `frontend/src/stores/auth.test.js` | 126 |  | 10 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/stores/authSecurity.test.js` | 103 |  | 11 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/stores/clients.js` | 673 | clients | /api/client-intelligence/analytics${suffixe}, /api/client-intelligence/clients/${clientId}${suffixe}, /api/client-intelligence/persons/${personId}${suffixe}, /api/client-intelligence/signals?${params}, /api/clients, /api/clients${suffixe}, /api/clients/${clientId}/constraints/schema, /api/clients/${clientId}/mandates, /api/clients/${clientId}/mandates/${mandatId}, /api/clients/${clientId}/preference-history${suffixe}, /api/clients/${clientId}/scoped-preferences, /api/clients/${clientId}/scoped-preferences/schema?${params}, /api/clients/${id}, /api/clients/${id}/archive, /api/clients/${id}/constraints, /api/clients/${id}/contacts?include_former=true, /api/clients/${id}/coverage, /api/clients/${id}/reactivate, /api/clients/${id}/scalar-constraints, /api/constraint-definitions, /api/constraint-definitions${suffixe}, /api/constraint-definitions/${id}, /api/constraint-definitions/${id}${forcer, /api/constraint-definitions/${id}/restore, /api/constraint-definitions/meta, /api/interactions, /api/interactions${suffixe}, /api/interactions/${id}, /api/interactions/follow-ups/${id}/close, /api/opportunities, /api/opportunities${suffixe}, /api/opportunities/${id}, /api/opportunities/${id}/status, /api/persons, /api/persons${suffixe}, /api/persons/${id}, /api/persons/${id}/deactivate, /api/persons/${id}/reactivate, /api/persons/${personId}/affiliations, /api/persons/${personId}/affiliations/${affiliationId}/close, /api/persons/${personId}/change-company, /api/persons/duplicates?${params} |
| `frontend/src/stores/clients.test.js` | 183 |  | 16 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/stores/deals.js` | 288 | deals | /api/deals, /api/deals/${dealId}, /api/deals/${dealId}/amendment-requests, /api/deals/${dealId}/amendment-requests/${requestId}/${action}, /api/deals/${dealId}/audit?${params}, /api/deals/${dealId}/events/${eventId}, /api/deals/${dealId}/events/${eventId}/reject, /api/deals/${dealId}/events/${eventId}/resolve-auto-exception, /api/deals/${dealId}/events/${eventId}/validate, /api/deals/${dealId}/events/refresh, /api/deals/${dealId}/lifecycle-proposals/${proposalId}/${action}, /api/deals/${dealId}/reprice, /api/deals/${id}, /api/deals/amendment-requests/pending, /api/deals/next-ref, /api/deals/watchlist${suffix} |
| `frontend/src/stores/deals.test.js` | 62 |  | 5 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/stores/demoMode.js` | 56 | demoMode |  |
| `frontend/src/stores/inputRetention.test.js` | 190 |  | 17 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/stores/portfolios.js` | 483 | portfolios | /api/deals/${dealId}/portfolios, /api/deals/${id}/shock, /api/portfolios, /api/portfolios/${id}/shock, /api/portfolios/${p.id}, /api/portfolios/${view.value}/barriers, /api/portfolios/${view.value}/exposure-by-counterparty, /api/portfolios/${view.value}/pnl-explain, /api/portfolios/${view.value}/risk?valuation_date=${encodeURIComponent(valuationDate.value)}, /api/portfolios/${view.value}/smile-risk, /api/portfolios/${view.value}/var, /api/portfolios/barriers-global, /api/portfolios/exposure-by-counterparty, /api/portfolios/pnl-explain-global, /api/portfolios/risk-global?valuation_date=${encodeURIComponent(valuationDate.value)}, /api/portfolios/shock-global, /api/portfolios/smile-risk-global, /api/portfolios/var-global, /api/portfolios/var-history?${params}, /api/portfolios/var/${batchId}, /api/shocks?${params} |
| `frontend/src/stores/portfolios.test.js` | 65 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/stores/portfoliosScope.test.js` | 149 |  | 11 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/stores/pricing.js` | 3437 | pricing | /api/backtest, /api/backtest/compare, /api/calendar/resolve, /api/db/scripts, /api/db/scripts/${currentScriptId.value}, /api/db/scripts/variants/${v.id}, /api/finance/dividends?${params}, /api/finance/hist_prices?${q}, /api/finance/hist_vol?${params}, /api/grid, /api/indicatives, /api/mtf, /api/mtf/drilldown, /api/parse, /api/paths, /api/price, /api/price/implied-funding, /api/price/in-life, /api/proba, /api/products/${ind.product_id}, /api/products/${product.product_id}/pricing-input, /api/profile, /api/rfq/${rfqId}/pricing-input, /api/scenarios, /api/script/transcribe, /api/script/transcribe/engines, /api/script/transcribe/prepare, /api/solve |
| `frontend/src/stores/pricing.test.js` | 1520 |  | 80 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/stores/products.js` | 231 | products | /api/products, /api/products/${id}${termsVersion, /api/products/${id}/history?limit=20&offset=${offset}, /api/products/${id}?calculations_limit=${limit}&calculations_offset=${offset}, /api/products/${product.id}/archive, /api/products/${product.product_id}, /api/products/${product.product_id}/booking-forks, /api/products/${product.product_id}/calculations, /api/products/${product.product_id}/terms, /api/products/${productId}/calculations/${calculationId}, /api/products?archived=${archived}&paged=true&limit=${pageSize}&offset=${pageOffset} |
| `frontend/src/stores/products.test.js` | 123 |  | 6 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/stores/rfq.js` | 382 | rfq | /api/price, /api/price/in-life, /api/rfq, /api/rfq/${id}, /api/rfq/${id}/exchange, /api/rfq/${id}/recipients, /api/rfq/${id}/send, /api/rfq/${rfq.id}/exchange-preview, /api/rfq/${rfq.id}/pricing-input, /api/rfq/${rfqId}, /api/rfq/${rfqId}/electronic-execution, /api/rfq/${rfqId}/quotes, /api/rfq/${rfqId}/quotes/${quoteId}, /api/rfq/${rfqId}/treatment${suffix}, /api/rfq/history, /api/rfq/providers |
| `frontend/src/stores/rfq.test.js` | 315 |  | 19 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/stores/valuationContext.test.js` | 17 |  | /api/paths, /api/proba |
| `frontend/src/test/setup.js` | 24 |  |  |
| `frontend/src/utils/__fixtures__/payscriptPresetServer.js` | 56 |  | /api/calendar/resolve, /api/parse, /api/schedule/generate |
| `frontend/src/utils/accessErrors.js` | 6 |  |  |
| `frontend/src/utils/api.js` | 53 |  | /api/db/scripts |
| `frontend/src/utils/api.test.js` | 76 |  | 7 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/barriers.js` | 143 |  |  |
| `frontend/src/utils/barriers.test.js` | 101 |  | 11 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/calculationBudget.js` | 125 |  |  |
| `frontend/src/utils/calculationBudget.test.js` | 31 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/ccr.js` | 70 |  | /api/ccr${path}, /api/ccr/calculate?stream=true |
| `frontend/src/utils/ccrHelp.js` | 119 |  |  |
| `frontend/src/utils/clientAmounts.js` | 19 |  |  |
| `frontend/src/utils/clientAmounts.test.js` | 30 |  | 8 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/commands.js` | 62 |  |  |
| `frontend/src/utils/commands.test.js` | 113 |  | 9 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/concurrentPool.js` | 26 |  |  |
| `frontend/src/utils/concurrentPool.test.js` | 28 |  | 2 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/contextSwitch.js` | 32 |  | /api/clients/${match[1]}, /api/db/scripts/${match[1]}, /api/deals/${match[1]}, /api/products/${match[1]}, /api/rfq/${match[1]}, /api/rfq/${match[1]}/booking-review |
| `frontend/src/utils/dealEvents.js` | 71 |  |  |
| `frontend/src/utils/dealEvents.test.js` | 69 |  | 8 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/format.js` | 148 |  |  |
| `frontend/src/utils/greekDisplay.js` | 26 |  |  |
| `frontend/src/utils/greekDisplay.test.js` | 51 |  | 6 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/marketProvenance.js` | 51 |  |  |
| `frontend/src/utils/optimizerAutomaticMarket.test.js` | 53 |  | 8 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/optimizerDiagnostics.js` | 88 |  |  |
| `frontend/src/utils/optimizerDiagnostics.test.js` | 78 |  | 10 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/optimizerMarket.js` | 107 |  |  |
| `frontend/src/utils/optimizerMarket.test.js` | 71 |  | 7 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/optimizerOutcome.js` | 49 |  |  |
| `frontend/src/utils/optimizerOutcome.test.js` | 63 |  | 8 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/optimizerPayoff.js` | 56 |  |  |
| `frontend/src/utils/optimizerPayoff.test.js` | 80 |  | 8 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/optimizerRadar.js` | 18 |  |  |
| `frontend/src/utils/optimizerRadar.test.js` | 36 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/optimizerResearch.js` | 72 |  | /api/product-optimizer/researches${path} |
| `frontend/src/utils/optimizerResume.js` | 32 |  |  |
| `frontend/src/utils/payoffFamilies.js` | 28 |  |  |
| `frontend/src/utils/payoffFamilies.test.js` | 34 |  | 3 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/payscriptEconomics.js` | 76 |  |  |
| `frontend/src/utils/payscriptPresets.js` | 63 |  | /api/calendar/resolve, /api/parse, /api/schedule/generate |
| `frontend/src/utils/payscriptPresets.test.js` | 58 |  | 6 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/pricingConfiguration.js` | 68 |  |  |
| `frontend/src/utils/pricingSession.js` | 18 |  |  |
| `frontend/src/utils/pricingSession.test.js` | 50 |  | 3 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/productCalculations.js` | 145 |  |  |
| `frontend/src/utils/productCalculations.test.js` | 61 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/productModels.js` | 104 |  |  |
| `frontend/src/utils/productModels.test.js` | 88 |  | 10 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/productOptimizer.js` | 65 |  | /api/product-optimizer/${path}, /api/product-optimizer/run |
| `frontend/src/utils/productOptimizer.test.js` | 34 |  | 5 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/rfqAnalysis.js` | 24 |  |  |
| `frontend/src/utils/rfqAnalysis.test.js` | 25 |  | 2 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/rfqBasket.js` | 81 |  |  |
| `frontend/src/utils/rfqBasket.test.js` | 51 |  | 5 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/rfqNetworkPrototype.js` | 254 |  |  |
| `frontend/src/utils/rfqNetworkPrototype.test.js` | 210 |  | 21 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/rfqQuoteStates.js` | 8 |  |  |
| `frontend/src/utils/rfqReconciliationLabels.js` | 9 |  |  |
| `frontend/src/utils/riskDates.js` | 20 |  |  |
| `frontend/src/utils/riskDates.test.js` | 21 |  | 3 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/riskScope.js` | 3 |  |  |
| `frontend/src/utils/rollEconomics.js` | 40 |  |  |
| `frontend/src/utils/rollEconomics.test.js` | 64 |  | 9 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/session.js` | 52 |  | /api/, /api/platform/ |
| `frontend/src/utils/session.test.js` | 71 |  | 9 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/smileCalibration.js` | 50 |  | /api/volatility/calibrate |
| `frontend/src/utils/smileCalibration.test.js` | 67 |  | 7 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/studySetup.js` | 19 |  |  |
| `frontend/src/utils/studySetup.test.js` | 27 |  | 5 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/studySnapshot.js` | 14 |  |  |
| `frontend/src/utils/studySnapshot.test.js` | 29 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/studySynthesis.js` | 13 |  |  |
| `frontend/src/utils/studySynthesis.test.js` | 26 |  | 5 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/underlyingDefaults.js` | 28 |  |  |
| `frontend/src/utils/valuationComparison.js` | 36 |  |  |
| `frontend/src/utils/valuationComparison.test.js` | 34 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/valuationSource.js` | 17 |  |  |
| `frontend/src/utils/valuationSource.test.js` | 17 |  | 2 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/volSurface.js` | 126 |  |  |
| `frontend/src/utils/volSurface.test.js` | 58 |  | 7 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/workshopDate.js` | 7 |  |  |
| `frontend/src/utils/workshopDate.test.js` | 11 |  | 3 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/workshopHelp.js` | 50 |  |  |
| `frontend/src/utils/workshopIssues.js` | 67 |  |  |
| `frontend/src/utils/workshopIssues.test.js` | 47 |  | 8 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/workshopPilot.js` | 54 |  |  |
| `frontend/src/utils/workshopPilot.test.js` | 48 |  | 8 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/utils/workshopProgress.js` | 130 |  |  |
| `frontend/src/utils/workshopProgress.test.js` | 87 |  | 11 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/views/AccountSecurityView.vue` | 43 |  | /api/auth/logout-all, /api/auth/password |
| `frontend/src/views/AdminBrowseView.vue` | 424 |  | /api/admin/browse, /api/admin/browse/${activeTable.value}, /api/admin/browse/${activeTable.value}/${editRow.value.id}, /api/admin/browse/${activeTable.value}/${row.id}, /api/admin/browse/${activeTable.value}/delete |
| `frontend/src/views/AdminComputeView.vue` | 178 |  | /api/compute/admin/batches, /api/compute/admin/batches/${b.id}, /api/compute/admin/batches/${b.id}/relaunch, /api/compute/admin/batches/${b.id}/stop |
| `frontend/src/views/AdminCounterpartiesView.vue` | 169 |  | /api/admin/counterparties, /api/admin/counterparties/${c.id} |
| `frontend/src/views/AdminEntitiesView.vue` | 121 |  | /api/admin/entities, /api/admin/entities/${e.id} |
| `frontend/src/views/AdminMarketDataView.vue` | 197 |  | /api/admin/market-data, /api/admin/market-data/fetch |
| `frontend/src/views/AdminRfqProvidersView.vue` | 259 |  | /api/admin/counterparties, /api/admin/rfq-providers, /api/admin/rfq-providers/${p.id}, /api/admin/rfq-providers/${provider.id}/contacts, /api/admin/rfq-providers/${selectedProvider.value.id}/contacts, /api/admin/rfq-providers/${selectedProvider.value.id}/contacts/${contact.id} |
| `frontend/src/views/AdminRfqRelationsView.vue` | 242 |  | /api/rfq-relations${path} |
| `frontend/src/views/AdminUatGeneratorView.vue` | 620 |  | /api/admin/uat-generator/batches, /api/admin/uat-generator/batches/${batch.id}, /api/admin/uat-generator/config, /api/admin/uat-generator/preview |
| `frontend/src/views/AdminUnderlyingsView.vue` | 323 |  | /api/admin/underlyings, /api/admin/underlyings/${u.id}, /api/admin/underlyings/${u.id}/revalidate, /api/admin/underlyings/search?q=${encodeURIComponent(q)} |
| `frontend/src/views/AdminUsersView.vue` | 320 |  | /api/admin/entities, /api/admin/users, /api/admin/users/${u.id}, /api/admin/users/${user.id}/${action}, /api/rfq-desks/admin, /api/rfq-desks/admin/${selectedDeskId.value}/members/${memberDraft.user_id} |
| `frontend/src/views/AdminView.vue` | 143 |  |  |
| `frontend/src/views/AgentWorkshopView.vue` | 289 |  | /api/agent-workshop, /api/platform/simulation/start |
| `frontend/src/views/AmcView.vue` | 5912 |  | /api/amc/analyze, /api/amc/benchmarks, /api/amc/export-pdf, /api/amc/ff-refresh?series_key=${encodeURIComponent(seriesKey)}, /api/amc/ff-series, /api/amc/ff-status, /api/amc/marketshocks, /api/amc/prices/attribution, /api/amc/prices/brinson, /api/amc/prices/fetch, /api/amc/prices/resolve-tickers, /api/amc/prices/status-for-study, /api/amc/prices/upload, /api/amc/studies, /api/amc/studies/${id}, /api/amc/study/detect, /api/amc/study/doc, /api/amc/study/export-pdf, /api/amc/study/run, /api/amc/synthesize, /api/amc/synthesize/payload, /api/amc/upload |
| `frontend/src/views/BookingView.vue` | 2957 |  | /api/alerts/${a.id}/read, /api/alerts/read-all, /api/alerts/refresh-book, /api/alerts?unread_only=true, /api/deals/${d.id}/mtm/explain, /api/deals/${d.id}/mtm/explain/report, /api/deals/${d.id}/reinvest/roll, /api/deals/${id}, /api/deals/${id}/greeks |
| `frontend/src/views/CcrView.vue` | 380 |  |  |
| `frontend/src/views/ClientDetailView.vue` | 796 |  |  |
| `frontend/src/views/ClientsView.vue` | 816 |  |  |
| `frontend/src/views/ConsultationView.vue` | 26 |  |  |
| `frontend/src/views/DealValuationsView.vue` | 600 |  | /api/deals/${dealId}, /api/deals/${dealId}/valuation-runs?run_type=MTM&include_payload=true, /api/deals/valuation-runs/${run.id} |
| `frontend/src/views/DocumentationView.vue` | 301 |  | /api/documents, /api/documents/${doc.id}/download, /api/documents/${id} |
| `frontend/src/views/FifoView.vue` | 328 |  | /api/fifo/detect, /api/fifo/run |
| `frontend/src/views/HomeView.vue` | 679 |  | /api/alerts?unread_only=true&limit=1, /api/amc/studies |
| `frontend/src/views/LoginView.test.js` | 115 |  | 9 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/views/LoginView.vue` | 171 |  | /api/auth/options, /api/auth/register, /api/platform/development/access, /api/platform/development/admin-workbench, /api/platform/login-options |
| `frontend/src/views/OpportunityDetailView.vue` | 381 |  | /api/clients/${fiche.client_id}/contacts |
| `frontend/src/views/OptimizerResearchListView.vue` | 57 |  |  |
| `frontend/src/views/OptimizerResultsView.test.js` | 46 |  | 5 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/views/OptimizerResultsView.vue` | 32 |  |  |
| `frontend/src/views/PersonDetailView.vue` | 319 |  |  |
| `frontend/src/views/PlatformView.vue` | 63 |  | /api/platform/installations, /api/platform/installations/${item.key}/start, /api/platform/simulation/start, /api/platform/status |
| `frontend/src/views/Pricer.vue` | 222 |  |  |
| `frontend/src/views/PricerView.vue` | 151 |  | /api/db/scripts/${id}, /api/db/scripts/variants/${id}/resolved, /api/rfq-inbox/${Number(route.query.receivedRfq)}, /api/rfq/${rfq.id}/terms |
| `frontend/src/views/ProductModelsView.vue` | 293 |  |  |
| `frontend/src/views/ProductOptimizerView.test.js` | 173 |  | 11 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/views/ProductOptimizerView.vue` | 320 |  |  |
| `frontend/src/views/ProductsView.vue` | 690 |  | /api/documents/${doc.record_id}/download |
| `frontend/src/views/ReinvestView.vue` | 793 |  | /api/deals/${deal.value.id}/reinvest/proposal, /api/deals/${deal.value.id}/reinvest/proposal/freeze, /api/deals/${deal.value.id}/reinvest/proposal/pdf, /api/deals/${deal.value.id}/reinvest/scan, /api/deals/${dealId}/archives |
| `frontend/src/views/RfqAnalysisView.vue` | 275 |  |  |
| `frontend/src/views/RfqBookingView.vue` | 98 |  | /api/rfq/${route.params.rfqId}/book, /api/rfq/${route.params.rfqId}/booking-review |
| `frontend/src/views/RfqInboxView.vue` | 170 |  | /api/rfq-inbox${before}, /api/rfq-inbox/${id}/assignment, /api/rfq-inbox/${id}/claim, /api/rfq-inbox/${id}/members, /api/rfq-inbox/${item.id}, /api/rfq-inbox/${item.id}/read |
| `frontend/src/views/RfqNetworkPrototypeView.test.js` | 41 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/views/RfqNetworkPrototypeView.vue` | 302 |  |  |
| `frontend/src/views/RfqProductTransition.test.js` | 92 |  | 5 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/views/RfqView.vue` | 2926 |  | /api/calendar/resolve, /api/clients, /api/clients/${clientId}/contacts, /api/clients/${clientId}/mandates, /api/db/scripts, /api/deals, /api/deals/counterparties, /api/finance/hist_vol?tickers=${encodeURIComponent(tk)}&period=1y&asof=${encodeURIComponent(asof)}, /api/opportunities/${id}, /api/opportunities?client_id=${clientId}&open_only=true, /api/parse, /api/rfq-desks, /api/rfq-desks/${assignmentDraft.pilot_desk_id}/members, /api/rfq-desks/organization, /api/rfq/${rfq.current.id}/shares, /api/rfq/${rfq.current.id}/shares/${share.desk_id}, /api/rfq/${rfq.current.id}/shares/${shareDraft.desk_id}, /api/rfq/${snapshot.id}/assignment, /api/rfq/${source.id}/shares |
| `frontend/src/views/RiskManagementView.test.js` | 82 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/views/RiskManagementView.vue` | 1874 |  | /api/deals/${id}/greeks |
| `frontend/src/views/ScriptsView.vue` | 449 |  | /api/db/scripts, /api/db/scripts/${id}${cascade, /api/db/scripts/${s.id}, /api/db/scripts/${s.id}/variants, /api/db/scripts/${v.id}, /api/folders, /api/folders/${id} |
| `frontend/src/views/StructuringView.vue` | 27 |  |  |
| `frontend/src/views/TradingView.vue` | 412 |  |  |
| `frontend/src/views/ValoExplainView.vue` | 332 |  | /api/deals, /api/deals/${dealId.value}/mtm?stream=true, /api/deals/valuation-runs/${r.id}, /api/valuation-notes, /api/valuation-notes/${id}, /api/valuation-notes/${note.id}/assist, /api/valuation-notes/${note.value.id}/pdf?${version, /api/valuation-notes/${note.value.id}/versions, /api/valuation-notes/${route.query.note}, /api/valuation-notes/${value.id}/versions, /api/valuation-notes/sources/${dealId.value}, /api/valuation-notes?stream=true |
| `frontend/src/views/archiveDocuments.test.js` | 85 |  | 5 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/views/asyncInterfaces.test.js` | 300 |  | 20 libellés it/test/describe (non assimilables à autant de cas) |
| `frontend/src/views/marketDataGovernance.test.js` | 111 |  | 4 libellés it/test/describe (non assimilables à autant de cas) |

## Scripts et outils de maintenance

- `backend/scripts/benchmark_product_optimizer.py` : Offline direct-pricing benchmark; no server, database, or market download.
- `backend/scripts/check_environment.py` : Fail-fast smoke check for a newly installed Structura environment.
- `backend/scripts/compare_common_surface.py` : Offline common-surface calibration, numerical gates and Athena repricing.  Synthetic market only. Production diffusion functions are called directly; this does not introduce an editable surface or calibration workflow in the UI. I
- `backend/scripts/eval_script_assistant.py` : Jeu d'évaluation de l'assistant de scripting.  Mesure ce que le prompt obtient réellement d'un modèle donné, sur des demandes en français dont on connaît les propriétés STRUCTURELLES attendues — pas le texte attendu : deux scripts
- `backend/scripts/generate_amc_excel.py` : Generate AMC Diagnostic Excel workbooks from LUKB raw exports.  Usage:     python generate_amc_excel.py  Reads:  C:/Users/phili/Downloads/UTI/Data/{ISIN}/ Writes: C:/Users/phili/Downloads/UTI/Data/{ISIN}/{ISIN}_AMC_Diagnostic_Mast
- `backend/scripts/generate_demo_deals.py` : Retired direct-Deal demo writer; use the canonical UAT workflow.
- `backend/scripts/rebuild_database_schema.py` : Offline, backed-up SQLite schema rebuild against current SQLModel metadata.  Without --apply the source is opened read-only and the rebuilt copy is only validated.  The live file is never opened through the application engine.
- `backend/scripts/report_common_surface.py` : Render the completed offline comparison as French Markdown and a plot.
- `backend/scripts/report_integrated_smile.py` : Render the completed integrated-smile study, keeping failures visible.
- `backend/scripts/run_compute_worker.py` : Daemon worker for the generic compute module (backend/app/core/compute/).  Polls compute_batches for queued (or stale-running, i.e. abandoned by a crashed worker) work, executes every job of a claimed batch in parallel (ProcessPoo
- `backend/scripts/run_ff_analysis.py` : Run FF analysis on CH1352587708 and print a diagnostic.
- `backend/scripts/seed_ccr_test_client.py` : Seed explicit, synthetic CCR scenarios for the existing `test` user's UAT deals.  Run from the repository root. The default is read-only; --apply writes audited configuration records only when the three counterparties have no CCR 
- `backend/scripts/seed_client_demo.py` : Jeu de données fictives pour éprouver le module Client.  Le volume n'est pas l'objectif : la COUVERTURE l'est. Chaque société existe pour mettre un comportement précis à l'épreuve, et `test_client_demo_seed.py` vérifie qu'elle le 
- `backend/scripts/seed_workflow_uat.py` : Create a local UAT batch through the production Product workflow.  This CLI is intentionally a thin adapter over Administration's generator. It must not maintain its own RFQ, fixing or lifecycle fixtures: doing so used to leave th
- `backend/scripts/studies_backup.py` : Consistent SQLite backup and verified restore into a new directory only.
- `backend/scripts/study_integrated_smile.py` : Repeat the 4Y Athena study using the editable surface's actual production path.  No database, network market data, or engine configuration is modified. Stage outputs are deliberately separate, so a failed numerical gate is not hid
- `backend/scripts/sync_payscript_templates.py` : Régénère `backend/app/core/payscript/templates.py` depuis le fichier JS.  La bibliothèque d'exemples PayScript vit côté frontend (`frontend/src/data/payscriptTemplates.js`) : c'est le sélecteur d'exemples de l'éditeur et la typolo
- `backend/scripts/sync_product_catalogue.py` : Régénère `backend/app/core/payscript/catalogue.py` depuis le catalogue JSON.  Le catalogue des produits génériques vit côté frontend (`frontend/src/data/productCatalogue.json`) : c'est la liste du module « Modèles de produits », q
- `backend/scripts/validate_excel.py` : Validates that the 3 generated Excel files are readable by the classic engine.
- `backend/scripts/validate_product_optimizer.py` : Offline Athena GBM reference, sample-size ladder and observation-grid study.
- `backend/scripts/validate_vol_models.py` : Reproducible offline validation of production volatility simulators.  Run from the repository root. Synthetic inputs only; no database or network. PDE reference convergence is reported separately from Monte Carlo uncertainty. LSV 
- `backend/scripts/vol_model_references.py` : Offline numerical oracles. No imports from the production pricing engine.  The SABR solver uses the spot convention dS=(r-q)S dt+alpha S**beta dW, dalpha=nu alpha dZ, and absorption at S=0. It is a diagnostic, not a calibration se
- `scripts/adopt_admin_workbench.py` : Inspect, then explicitly attest an offline legacy Admin workspace.
- `scripts/check_agent_workshop.py` : Qualify real HTTP/browser adapters, independently of AI commercial decisions.  Uses fresh disposable instances; never opens the user's Structura database. Run from repository root: .venv/Scripts/python.exe scripts/check_agent_work
- `scripts/check_hybrid_access.py` : Check the common development portal on already running manual installations.
- `scripts/check_hybrid_foundation.py` : Native seven-service acceptance on temporary databases with guaranteed teardown.
- `scripts/check_rfq_network_pilot.py` : Isolated, authenticated RFQ pilot on three native Structura installations.  Run from the repository root with .venv/Scripts/python.exe. No pytest fixtures, mock prices, external data download or user database are used. Every run c
- `scripts/check_structura_launcher.py` : Native launcher access acceptance, without creating or starting AI campaigns.
- `scripts/check_trading_ui.py` : Qualify note issuance through the normal UI in private installations.
- `scripts/check_workshop_campaign.py` : Verify a finished real-agent campaign against its isolated native databases.  Read-only: no agent decisions, business writes, resumptions or synthetic results. The optional report is a qualification artifact, not a campaign state 
- `scripts/check_workshop_consultation_ui.py` : Inspect saved BNP/Hector books via native read-only Structura and the built UI.  The campaign is never resumed. All API writes in the viewer must be rejected; source campaign and database hashes must remain identical. No main DB i
- `scripts/check_workshop_controls_ui.py` : Inspect an existing real campaign and qualify cross-controller UI controls.
- `scripts/check_workshop_diagnostic.py` : Bounded native acceptance check; isolated data, no model calls, owned cleanup.
- `scripts/check_workshop_live_activity.py` : Short genuine AI run checking published phases and native contract requests.  Fresh private accounts/data only. Stop after the first native relationship has been created; this checks live visibility, not a new annual qualification
- `scripts/check_workshop_management_ui.py` : Exercise the built UI against real management APIs with temporary campaigns.  No main DB, AI model or private backend is started. Only the models inventory is stubbed; campaign GET/reset/DELETE run the actual router, controller an
- `scripts/check_workshop_observability_ui.py` : UI-only observability checks with intercepted API fixtures, no campaign writes.  The existing server supplies static assets only. Recorded campaign data validates history presentation; live phases are explicit display fixtures, no
- `scripts/check_workshop_pilot_ui.py` : Pilot UI qualification with isolated campaign APIs and explicit display fixtures.  No model or business backend is started. These states qualify presentation, diagnosis, pagination and reconciliation, not autonomous commercial dec
- `scripts/inspect_agent_workshop_ui.py` : Check the real admin UI against an explicitly isolated test server.
- `scripts/launch_structura.py` : Open the desktop menu with the project's interpreter, without arguments.
- `scripts/manage_hybrid_dev.py` : Prepare/init/start/status/stop an owned seven-service development environment.
- `scripts/reset_hybrid_legacy.py` : Prepare an exact inventory, then apply it to authorized fictitious Structura data.
- `scripts/run_agent_workshop.py` : Run actual local AI users; evidence is available in Structura's admin page.  No real application database is opened by this controller. Every worker has its own fresh data directory. Commercial decisions come from Ollama.
- `scripts/run_workshop_campaign.py` : Launch and supervise an explicitly requested complete native RFQ campaign.
- `scripts/studies_reference/build_extended.py` : Independent reference data. No imports from Studies or application modules.  Bootstrap with --source, --import-source and --factors. Thereafter the output directory is a portable, frozen package; rerun its generator offline.
- `scripts/studies_reference/build_flows_2a.py` : Offline long-only flow fixture. Standard library only; no application imports.  Bootstrap with --base and --unified. Subsequent runs only require --output: all frozen sources and this generator are copied into that directory.
- `scripts/studies_reference/compare_studies.py` : Optional integration harness. Uses Studies ONLY as the system under test.  All market dependencies are supplied in memory; socket access is denied. Never used by the independent generator or verifier; no live cache is changed. Run
- `scripts/studies_reference/install_e_prices.py` : Install only the isolated E USD proxy series. Never replace an existing key.  Usage: python install_e_prices.py PACKAGE --store REPO/backend/data/underlying_prices Existing identical series are accepted; any collision aborts befor
- `scripts/studies_reference/methodology_reference.py` : Independent reference for the declared descriptive score policy (Studies 2.4).  Uses frozen independent metrics, never the application's computed score. The original V1 oracle remains unchanged.
- `scripts/studies_reference/package_reference.py` : Reproduce, verify, tamper-test, then package the frozen reference.
- `scripts/studies_reference/report_comparison.py` : Compare independent references with the isolated Studies run. Never fit references to outputs.
- `scripts/studies_reference/setup_unified.py` : Assemble an ordinary Studies folder from frozen independent inputs.  This is packaging only: no Studies calculation and no reference results are used to produce market inputs. Run from the repository root.
- `scripts/studies_reference/test_e_install.py` : Exercise the optional installer only in temporary directories.
- `scripts/studies_reference/test_flows_2a.py` : Fixture integrity tests; run from repository root with unittest discovery.
- `scripts/studies_reference/test_reference.py` : Small hand-verifiable cases; tests the independent oracle, not Studies.
- `scripts/studies_reference/verify_extended.py` : Independent checks of serialized outputs; does not import the generator.
- `scripts/studies_reference/verify_flows_2a.py` : Independent Decimal replay of the exported 2A ledger; no generator/app imports.
- `scripts/studies_reference/verify_unified.py` : Exercise the ordinary scanner and engine, without replacing market loaders.
