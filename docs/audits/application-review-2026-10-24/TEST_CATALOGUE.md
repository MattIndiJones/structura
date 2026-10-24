# Définitions de tests backend

Présence dans la source uniquement ; aucune collecte ni exécution pendant cette revue.
Les paramétrisations, fixtures et marks exacts sont dans TEST_DEFINITIONS.json et les fichiers originaux.

## backend/tests/test_admin_browse_delete.py

- `test_deleting_a_bare_deal_works` — ligne 71
- `test_deleting_a_deal_carrying_its_whole_lifecycle` — ligne 88
- `test_deleting_a_deal_removes_its_valuation_history_and_latest_pointer` — ligne 120
- `test_deleting_an_rfq_with_a_selected_quote` — ligne 148
- `test_a_booked_tender_is_still_protected` — ligne 172
- `test_batch_delete_reports_each_row` — ligne 191
- `test_an_undeclared_relation_gives_an_actionable_message` — ligne 208

## backend/tests/test_admin_registry.py

- `test_get_row_exposes_summary_only_for_immutable_deals` — ligne 38
- `test_deals_inventory_exposes_owner_and_entity_names` — ligne 49
- `test_deals_table_refuses_former_admin_correction_path_and_audits_it` — ligne 82
- `test_deals_table_rejects_a_non_whitelisted_field` — ligne 100
- `test_admin_refuse_les_corrections_qui_cassent_le_deal` — ligne 121
- `test_a_table_without_editable_fields_is_rejected_entirely` — ligne 129
- `test_update_row_404s_on_missing_record` — ligne 141
- `test_registry_meta_exposes_no_direct_deal_editor` — ligne 148
- `test_bulk_delete_removes_every_selected_row` — ligne 157
- `test_a_protected_row_does_not_sink_the_batch` — ligne 174
- `test_bulk_delete_keeps_going_after_a_blocked_row` — ligne 213
- `test_bulk_delete_reports_a_missing_row_instead_of_crashing` — ligne 233

## backend/tests/test_admin_workbench_adoption.py

- `test_inspection_is_read_only_and_adoption_backs_up_every_original_row` — ligne 53
- `test_refused_adoption_never_changes_existing_database` — ligne 92
- `test_explicit_attestation_is_required` — ligne 128
- `test_active_workspace_and_foreign_port_are_refused` — ligne 135
- `test_audit_failure_rolls_back_identity_but_keeps_backup` — ligne 152
- `test_normal_migration_and_restarts_preserve_existing_account` — ligne 164

## backend/tests/test_agent_workshop.py

- `test_registration_uses_the_actor_tab_session_not_a_shared_old_identity` — ligne 9
- `test_real_pricing_booking_idempotence_and_contract_identity` — ligne 124
- `test_incomplete_contract_and_external_resale_are_refused` — ligne 138
- `test_scope_version_and_otc_without_master` — ligne 148
- `test_store_and_private_agent_observations` — ligne 157
- `test_synthetic_history_cannot_look_ahead` — ligne 167
- `test_note_rejects_otc_netting_and_changed_issuer_or_documentation` — ligne 177
- `test_client_book_is_required_and_price_mismatch_is_detected` — ligne 191
- `test_lease_and_published_snapshot_are_independent` — ligne 205
- `test_official_user_fixing_survives_missing_provider` — ligne 222
- `test_manual_maturity_uses_contract_date_not_rounded_time` — ligne 236
- `test_pending_booking_choices_do_not_repeat_the_completed_buy` — ligne 246
- `test_control_from_another_controller_is_acknowledged` — ligne 262
- `test_contract_draw_and_current_quote_choices` — ligne 276
- `test_normal_instance_keeps_its_local_calendar_day` — ligne 289
- `test_all_documentation_refusals_close_the_need_without_a_fake_trade` — ligne 299
- `test_atomic_save_retries_a_brief_windows_reader_lock` — ligne 319
- `test_risk_choices_exclude_a_counterparty_already_reviewed_today` — ligne 334
- `test_actor_installation_cannot_inspect_or_control_parent_campaigns` — ligne 349
- `test_regular_user_cannot_run_or_read_agent_recipes` — ligne 362
- `test_native_request_is_visible_before_response_and_refusals_are_retained` — ligne 379
- `test_controller_publishes_decision_execution_and_clears_activity_on_stop` — ligne 415
- `test_resolved_error_advice_does_not_block_current_work` — ligne 464
- `test_reports_and_confirmations_do_not_bypass_the_conversation_bound` — ligne 482
- `test_free_api_uses_routes_discovered_in_current_native_openapi` — ligne 493
- `test_business_progress_requires_changed_workflow_facts` — ligne 523
- `test_model_context_keeps_terms_without_duplicate_pricing_or_native_receipts` — ligne 535
- `test_context_percentages_do_not_change_frozen_pricing_units` — ligne 551
- `test_large_native_api_result_is_bounded_without_losing_saved_evidence` — ligne 565
- `test_bank_sees_own_decline_without_competitors_responses` — ligne 574
- `test_quiet_actor_waits_until_a_real_message_or_task_arrives` — ligne 584
- `test_context_focus_preserves_previous_terms_and_unfinished_bookings` — ligne 599
- `test_snapshot_distinguishes_a_stale_running_record_from_an_external_controller` — ligne 619
- `test_campaign_listing_uses_current_snapshot_without_exposing_other_owners` — ligne 634

## backend/tests/test_agregats_officiels.py

- `test_avg_moyenne_chaque_sous_jacent_separement` — ligne 30
- `test_min_et_max_prennent_l_extreme_de_chaque_sous_jacent` — ligne 36
- `test_la_reduction_ne_prend_jamais_l_agregat_panier` — ligne 41
- `test_une_fenetre_incomplete_est_refusee_et_dit_ce_qui_manque` — ligne 53
- `test_un_sous_jacent_sans_cours_sur_toute_la_fenetre_bloque` — ligne 63
- `test_une_reduction_inconnue_est_refusee` — ligne 77
- `test_un_releve_neutralise_sort_du_calcul_avec_sa_trace` — ligne 83
- `test_neutraliser_toute_la_fenetre_ne_donne_pas_un_agregat_vide` — ligne 98
- `test_un_agregat_est_perime_quand_un_fixing_est_corrige` — ligne 107
- `test_une_correction_rendant_la_meme_valeur_perime_quand_meme` — ligne 117
- `test_un_agregat_non_calculable_n_est_pas_perimable` — ligne 125

## backend/tests/test_ai_workbench.py

- `test_preview_edit_and_generation_share_exact_prompt` — ligne 21
- `test_script_refinement_preview_and_custom_prompt_reach_validation` — ligne 58
- `test_blank_or_stale_custom_prompts_never_call_provider` — ligne 77
- `test_modules_defer_defaults_to_the_shared_catalog` — ligne 84
- `test_explicit_missing_ollama_model_does_not_silently_switch` — ligne 94
- `test_shared_transport_uses_selected_model_messages_and_connection` — ligne 102
- `test_provider_errors_do_not_reflect_response_secrets` — ligne 118
- `test_provenance_uses_model_reported_by_provider` — ligne 126
- `test_invalid_ollama_connection_is_rejected_before_network` — ligne 135

## backend/tests/test_amc_studies.py

- `test_invalid_manifest_rejected` — ligne 39
- `test_execution_zero_never_uses_ordered_quantity` — ligne 43
- `test_fx_required_only_across_currencies` — ligne 49
- `test_duplicate_conflicting_execution_rejected` — ligne 55
- `test_price_cutoff_and_staleness` — ligne 65
- `test_input_paths_confined_and_ambiguous` — ligne 72
- `test_bh_cutoff_and_cash_not_renormalized` — ligne 80
- `test_full_redemption_zero_outstanding` — ligne 94
- `test_missing_initial_outstanding_not_backfilled` — ligne 103
- `test_drawdown_includes_first_loss` — ligne 108
- `test_downside_uses_zero_target_and_compounds_weeks` — ligne 113
- `test_monthly_nav_not_annualized_as_daily` — ligne 121
- `test_missing_benchmark_never_called_alpha` — ligne 125
- `test_overlapping_trades_not_independent_samples` — ligne 132
- `test_timing_only_cannot_publish_manager_skill` — ligne 139
- `test_empty_book_no_fixed_ninety_percent_confidence` — ligne 144
- `test_benchmark_regression_does_not_fill_missing_returns` — ligne 150
- `test_nav_only_study_has_no_fifo_dependency` — ligne 161
- `test_frozen_orders_do_not_rescan_directory` — ligne 177
- `test_price_mark_missing_fx_is_not_one` — ligne 183
- `test_fx_rate_to_respects_historical_asof` — ligne 194
- `test_t0_allocations_and_fx_decomposition` — ligne 214
- `test_execution_series_undoes_only_future_splits` — ligne 227
- `test_fifo_exact_lots_and_price_fx_identity` — ligne 236
- `test_brinson_reconciles_its_proxy_and_preserves_cash` — ligne 250
- `test_study_files_scope_and_concurrency` — ligne 275
- `test_complete_generic_study_uses_only_manifest_and_nav_cutoff` — ligne 293
- `test_saved_snapshot_archive_and_ownership` — ligne 329
- `test_public_registration_requires_explicit_enable` — ligne 350
- `test_timing_incomplete_future_window_excluded` — ligne 362
- `test_backup_restore_integrity_and_no_overwrite` — ligne 377
- `test_pdf_uses_saved_confidence_without_recomputing` — ligne 397
- `test_provided_returns_cannot_override_nav_levels` — ligne 414

## backend/tests/test_analytics_calendrier.py

- `test_chaque_requete_d_analyse_resout_son_calendrier` — ligne 100
- `test_le_calendrier_resolu_est_celui_du_prix` — ligne 117
- `test_sans_devise_le_refus_reste_explicite` — ligne 135
- `test_aucun_endpoint_ne_resout_son_calendrier_a_la_main` — ligne 143
- `test_tout_appel_a_resolve_constats_passe_une_devise` — ligne 158
- `test_la_grille_de_scenarios_survit_a_un_decalage_de_reglement` — ligne 184
- `test_le_profil_de_payoff_bascule_sur_la_jambe_residuelle` — ligne 199
- `test_une_analytique_sans_date_de_valorisation_reste_a_l_emission` — ligne 222
- `test_les_probabilites_basculent_sur_la_jambe_residuelle` — ligne 232
- `test_les_chemins_partent_du_niveau_du_jour` — ligne 255
- `test_chaque_analytique_bascule_sur_la_vie_restante` — ligne 289
- `test_le_backtest_reste_a_l_emission_et_le_dit` — ligne 311

## backend/tests/test_backtest_oracle.py

- `test_le_rang_d_observation_est_le_meme_des_deux_cotes` — ligne 93
- `test_le_rang_reste_le_meme_avec_deux_calendriers` — ligne 100
- `test_un_param_par_observation_lit_la_meme_ligne_des_deux_cotes` — ligne 114
- `test_evenement_sur_agregat` — ligne 125
- `test_evenement_direct_sur_une_sous_date` — ligne 133
- `test_le_meme_fixing_sert_aux_deux_roles` — ligne 145
- `test_un_stop_intermediaire_arrete_le_rejeu` — ligne 157
- `test_plusieurs_sous_jacents` — ligne 168
- `test_historique_insuffisant` — ligne 177
- `test_historique_absent_ne_leve_pas` — ligne 188
- `test_chaque_constatation_se_lit_a_sa_date` — ligne 199
- `test_un_cours_manquant_est_reporte_et_non_saute` — ligne 227
- `test_une_serie_complete_ne_signale_aucun_report` — ligne 247

## backend/tests/test_booking_legal_exception.py

- `test_http_permissions_default_refusal_and_admin_atomic_acceptance` — ligne 34
- `test_exception_invalid_inputs_are_audited_and_never_booked` — ligne 81
- `test_exception_cannot_reactivate_inactive_bank_or_skip_known_credit_limit` — ligne 92
- `test_exception_never_replaces_rfq_or_pricing_or_economics` — ligne 110
- `test_regularization_checks_credit_preserves_exception_and_original_contract` — ligne 120
- `test_exception_column_migration_is_additive_idempotent_and_does_not_qualify_legacy` — ligne 150
- `test_audit_failure_rolls_back_deal_product_and_exception` — ligne 168

## backend/tests/test_booking_mtm_daily.py

- `test_restoration_selects_latest_compatible_run_with_local_midnight_bounds` — ligne 69
- `test_restoration_keeps_access_controls` — ligne 92
- `test_stream_matches_regular_mtm_and_records_one_run` — ligne 106
- `test_stream_reports_market_failure_without_persisting` — ligne 135
- `test_progress_is_delivered_before_computation_completes` — ligne 144

## backend/tests/test_bridge_dependence.py

- `test_identical_bridges_share_extrema_and_conditional_crossings` — ligne 15
- `test_complete_payoff_is_unchanged_when_the_same_conditional_path_is_duplicated` — ligne 30
- `test_zero_volatility_never_creates_a_barrier_crossing` — ligne 53
- `test_basket_result_explicitly_labels_the_joint_approximation` — ligne 60
- `test_each_refined_marginal_keeps_the_exact_conditional_law` — ligne 70
- `test_independent_assets_match_the_union_of_two_analytic_crossings` — ligne 81
- `test_perfect_asset_factors_remain_identical_with_c15_rates` — ligne 89
- `test_refinement_policy_is_explicit` — ligne 107
- `test_unqualified_basket_domains_are_refused_without_changing_monitoring` — ligne 116
- `test_neighbor_analyses_apply_the_same_admission_rule` — ligne 125
- `test_neighbor_analyses_expose_the_same_approximation_policy` — ligne 133
- `test_resource_estimate_accounts_for_correlation_dependent_refinement` — ligne 142
- `test_correlation_greeks_keep_one_refinement_across_the_bump` — ligne 152
- `test_invalid_or_missing_joint_correlations_fail_closed` — ligne 166
- `test_price_api_preserves_the_numeric_policy_and_warning` — ligne 172
- `test_archived_run_identity_includes_the_bridge_source` — ligne 185

## backend/tests/test_business_permissions.py

- `test_agreement_permission_matrix_and_audited_denials` — ligne 84
- `test_settlement_is_operations_only_idempotent_and_dates_are_distinct` — ligne 106
- `test_secondary_profiles_cannot_compute_through_alternate_endpoints` — ligne 128
- `test_front_colleague_operations_controller_handoff_and_revocation` — ligne 162
- `test_manual_refresh_only_processes_the_shared_visible_book` — ligne 197
- `test_booking_review_refuses_stale_or_missing_evidence` — ligne 214
- `test_historical_rfq_without_desk_keeps_personal_access` — ligne 236
- `test_operational_valuation_keeps_contract_scope` — ligne 249
- `test_shared_collections_and_documents_keep_contract_authorization` — ligne 260
- `test_crm_details_aggregates_signals_and_alerts_follow_deal_scope` — ligne 298
- `test_scope_migration_freezes_owner_and_keeps_unknown_settlement_dates` — ligne 346

## backend/tests/test_c19_archives.py

- `test_optimizer_terminal_evidence_is_null_safe_and_undeletable` — ligne 28
- `test_receivable_replay_really_uses_its_inputs` — ligne 63
- `test_legacy_fixed_price_is_not_a_replay` — ligne 70
- `test_known_claim_var_scenario_carries_rate_shock_without_asset_correlation` — ligne 75
- `test_historical_claim_remains_priceable_after_current_settlement` — ligne 82
- `test_replay_uses_frozen_calendar_and_never_current_resolver` — ligne 97
- `test_old_identity_is_not_invented_and_probe_does_not_overwrite` — ligne 109
- `test_numerical_replay_failure_keeps_observed_difference` — ligne 118
- `test_invalid_contract_calendar_still_blocks_note` — ligne 131
- `test_unverified_scalar_model_benchmark_is_dated_and_detached` — ligne 140
- `test_archive_owner_immutability_and_identical_pdf` — ligne 150
- `test_rfq_history_uses_dated_benchmark_and_keeps_it_private` — ligne 166
- `test_fixing_correction_invalidates_current_projection_without_changing_archive` — ligne 186
- `test_calculation_receipt_binds_engine_identity_to_signature` — ligne 200
- `test_proposal_pdf_keeps_displayed_coupon_after_vol_changes_and_separate_successor` — ligne 224
- `test_freeze_refuses_modified_or_wrong_proof` — ligne 247
- `test_archive_upgrade_adds_reference_column_and_reinstalls_same_guards` — ligne 259

## backend/tests/test_cache_prix.py

- `test_le_meme_historique_n_est_telecharge_qu_une_fois` — ligne 47
- `test_l_ordre_des_tickers_ne_cree_pas_deux_entrees` — ligne 54
- `test_une_demande_differente_revalide_sa_couverture` — ligne 68
- `test_le_cache_expire_mais_le_stock_qualifie_est_reutilise` — ligne 85
- `test_l_appelant_ne_peut_pas_muter_le_cache` — ligne 95
- `test_une_erreur_n_est_pas_mise_en_cache` — ligne 105

## backend/tests/test_calendars.py

- `test_le_calendrier_suit_la_devise_de_reglement` — ligne 15
- `test_les_fetes_lunaires_sont_couvertes` — ligne 24
- `test_les_week_ends_ne_sont_jamais_ouvres` — ligne 31
- `test_modified_following_ne_franchit_pas_le_mois` — ligne 38
- `test_modified_following_avance_quand_le_mois_le_permet` — ligne 47
- `test_un_jour_ouvre_n_est_jamais_deplace` — ligne 52
- `test_convention_none_laisse_la_date_intacte` — ligne 58
- `test_decalage_de_reglement_saute_feries_et_week_end` — ligne 63
- `test_decalage_zero_ramene_sur_un_jour_ouvre` — ligne 69
- `test_decalage_negatif_remonte_le_calendrier` — ligne 75
- `test_comptage_et_decalage_sont_reciproques` — ligne 79
- `test_une_devise_sans_calendrier_echoue_bruyamment` — ligne 86
- `test_la_devise_est_insensible_a_la_casse` — ligne 94

## backend/tests/test_calibration_window.py

- `test_un_forward_start_se_recalibre_sur_un_an_de_marche` — ligne 102
- `test_un_deal_jeune_ne_prend_plus_une_vol_depuis_le_strike` — ligne 124
- `test_la_fenetre_suit_la_date_de_valorisation_et_sa_longueur` — ligne 142

## backend/tests/test_caracterisation_echeancier.py

- `test_un_evenement_principal_lit_l_agregat_de_sa_fenetre` — ligne 78
- `test_un_evenement_sur_releve_lit_le_cours_brut` — ligne 88
- `test_un_releve_isole_tombe_a_sa_propre_date` — ligne 100
- `test_une_fenetre_d_un_seul_point_vaut_la_constatation_ponctuelle` — ligne 113
- `test_un_stop_interrompt_les_blocs_suivants_du_meme_jour` — ligne 144
- `test_l_ordre_du_script_fait_foi_a_date_egale` — ligne 154
- `test_index_compte_les_constatations_du_calendrier` — ligne 170
- `test_index_est_independant_par_calendrier` — ligne 178
- `test_un_bloc_sur_une_sous_date_ne_decale_pas_les_constatations` — ligne 191
- `test_param_par_observation_suit_le_calendrier_de_son_bloc` — ligne 203
- `test_index_est_refuse_dans_un_bloc_sans_echeancier` — ligne 221
- `test_un_bloc_a_dates_litterales_garde_son_rang` — ligne 229
- `test_un_param_par_observation_lu_depuis_deux_calendriers_est_refuse` — ligne 237
- `test_deux_blocs_du_meme_calendrier_partagent_leur_param` — ligne 246
- `test_le_rang_survit_au_decalage_residuel` — ligne 255

## backend/tests/test_ccr.py

- `test_limit_boundaries` — ligne 24
- `test_no_limit_never_ok_and_currency_not_assumed` — ligne 28
- `test_isda_alone_never_nets_and_different_sets_never_net` — ligne 56
- `test_actual_mc_standalone_and_incremental_hedge_reproducible` — ligne 70
- `test_standalone_without_counterparty_and_new_trade_increases_pfe` — ligne 87
- `test_collateral_sign_im_haircut_and_unknown_mpor` — ligne 98
- `test_cva_analytic_and_historical_pd_not_labelled_cva` — ligne 112
- `test_unsupported_model_and_missing_valuation_never_zero_pfe` — ligne 122
- `test_schema_and_tenant_audit_optimistic_lock` — ligne 131
- `test_matured_cash_is_exposed_until_payment_then_zero` — ligne 152
- `test_autocall_does_not_erase_unpaid_receivable` — ligne 163
- `test_separate_sets_and_non_enforceable_agreements_do_not_offset` — ligne 175
- `test_market_and_credit_stress_reuses_pricer_without_overwriting_base` — ligne 189
- `test_hard_block_at_real_booking_boundary_keeps_pricing_available` — ligne 201
- `test_additive_migration_preserves_old_unknown_data` — ligne 228
- `test_settlement_only_horizon_covers_payment_and_credit_stress` — ligne 252
- `test_legacy_user_cannot_bypass_configured_credit_policy` — ligne 277
- `test_credit_adjusted_price_does_not_clear_current_exposure_limit` — ligne 295
- `test_posted_collateral_outside_eligible_sets_is_not_silently_omitted` — ligne 305

## backend/tests/test_ccr_api.py

- `test_http_configuration_calculation_replay_and_scope` — ligne 18
- `test_anonymous_ccr_is_not_accessible` — ligne 56
- `test_rfq_uses_explicit_provider_mapping_and_frozen_engine_units` — ligne 62

## backend/tests/test_ccr_cache.py

- `test_cached_base_keeps_fresh_limits_and_credit_stress` — ligne 23
- `test_cache_invalidates_contract_events_market_scope_and_engine` — ligne 54
- `test_incomplete_or_foreign_base_cannot_be_reused` — ligne 87
- `test_archived_histories_are_reused_offline_without_mixing_price_types` — ligne 108
- `test_active_deal_stress_reuses_base_but_reprices_shocked_value` — ligne 129

## backend/tests/test_ccr_common_market.py

- `test_harmonization_prices_every_trade_then_computes_pfes_offline` — ligne 36
- `test_manual_overrides_win_and_selection_is_order_independent` — ligne 66
- `test_failed_common_market_does_not_report_partial_pfe` — ligne 80
- `test_adjusted_local_history_never_uses_contractual_manual_series` — ligne 91
- `test_common_correlation_stress_also_changes_cross_product_pairs` — ligne 104

## backend/tests/test_ccr_preparation.py

- `test_stream_prepares_settlement_and_archives_without_changing_booking` — ligne 21
- `test_missing_mtm_is_built_with_actual_residual_engine_and_manual_history` — ligne 46
- `test_failed_deal_remains_in_scope_and_exposure_is_incomplete` — ligne 113
- `test_local_raw_history_has_priority_and_cannot_use_adjusted_close` — ligne 131
- `test_incomplete_manual_data_never_silently_fetches` — ligne 147
- `test_common_market_overrides_are_explicit_and_do_not_mutate_source` — ligne 157
- `test_common_rate_default_harmonizes_different_bookings_and_preserves_replay` — ligne 172

## backend/tests/test_ccr_scope.py

- `test_scopes_batch_portfolio_and_entity_are_intersected` — ligne 63
- `test_uat_uses_identical_engine_and_cannot_replace_production_monitor` — ligne 85
- `test_empty_scope_and_missing_mtm_are_explained` — ligne 110
- `test_suggested_dates_account_for_historical_deal_scope` — ligne 128
- `test_historical_scope_excludes_paid_early_call_despite_original_payment_date` — ligne 145

## backend/tests/test_central_simulation.py

- `test_controller_rejects_direct_sessions_wrong_request_and_replay` — ligne 34
- `test_campaign_is_private_to_delegated_admin_and_legacy_alias_works` — ligne 46
- `test_central_admin_controls_are_explicit_and_business_tokens_are_rejected` — ligne 65

## backend/tests/test_chaine_pricing_booking_mtm.py

- `test_pricing_booking_mtm_au_strike_conservent_le_meme_produit` — ligne 22

## backend/tests/test_client_affiliations.py

- `test_un_changement_de_societe_ne_deplace_aucun_historique` — ligne 70
- `test_les_deux_periodes_restent_lisibles_separement` — ligne 121
- `test_l_affiliation_courante_se_deduit_de_la_date_de_fin` — ligne 160
- `test_une_affiliation_close_ne_se_propose_plus_a_la_creation` — ligne 174
- `test_rejoindre_deux_fois_la_meme_societe_est_refuse` — ligne 189
- `test_une_fin_anterieure_au_debut_est_refusee` — ligne 201
- `test_le_changement_de_societe_ne_laisse_pas_d_etat_intermediaire` — ligne 211
- `test_un_contact_d_un_autre_client_est_refuse` — ligne 232
- `test_le_contact_principal_ne_se_repete_pas_dans_les_participants` — ligne 244
- `test_un_participant_ne_figure_pas_deux_fois` — ligne 255
- `test_une_selection_coherente_passe` — ligne 269
- `test_un_trade_ne_peut_pas_melanger_deux_clients` — ligne 281
- `test_un_contact_sans_client_est_refuse_sur_un_trade` — ligne 301
- `test_un_trade_non_rattache_reste_valide` — ligne 313
- `test_le_cliche_commercial_fige_ce_qui_etait_vrai_au_booking` — ligne 324
- `test_un_email_identique_est_un_signal_fort` — ligne 350
- `test_un_homonyme_est_un_signal_faible_mais_signale` — ligne 361
- `test_la_detection_de_doublon_n_empeche_pas_l_ecriture` — ligne 373
- `test_un_identifiant_externe_identique_signale_un_client_en_double` — ligne 382
- `test_un_client_vierge_se_supprime` — ligne 395
- `test_un_client_avec_historique_refuse_la_suppression` — ligne 401
- `test_une_personne_avec_historique_refuse_la_suppression` — ligne 418
- `test_perdre_une_opportunite_sans_motif_est_refuse` — ligne 431
- `test_un_motif_de_perte_hors_vocabulaire_est_refuse` — ligne 437
- `test_un_motif_connu_passe` — ligne 443
- `test_aucun_ordre_n_est_impose_entre_les_etapes` — ligne 447
- `test_un_participant_en_double_est_refuse_par_la_base` — ligne 456

## backend/tests/test_client_analytics.py

- `test_sans_dossier_tranche_le_taux_de_conversion_est_nul_pas_zero` — ligne 92
- `test_les_dossiers_ouverts_ne_pesent_pas_sur_le_taux` — ligne 102
- `test_le_pipeline_ne_compte_que_les_dossiers_ouverts` — ligne 111
- `test_les_motifs_de_perte_sortent_du_plus_frequent_au_moins` — ligne 117
- `test_sans_historique_les_delais_sont_nuls_pas_zero` — ligne 127
- `test_le_delai_dossier_vers_trade_se_calcule_quand_la_chaine_existe` — ligne 134
- `test_les_analytiques_s_arretent_a_l_entite` — ligne 153
- `test_une_lecture_client_d_une_autre_entite_est_refusee` — ligne 161
- `test_les_seuils_sont_rendus_avec_les_signaux` — ligne 170
- `test_asof_permet_de_rejouer_une_analyse_a_une_date_passee` — ligne 182
- `test_une_date_asof_illisible_est_refusee` — ligne 202
- `test_l_apercu_groupe_les_signaux_par_nature` — ligne 208

## backend/tests/test_client_api.py

- `test_une_autre_entite_ne_voit_pas_le_client` — ligne 84
- `test_une_autre_entite_ne_peut_pas_modifier_ni_supprimer` — ligne 94
- `test_un_collegue_de_la_meme_entite_voit_la_fiche` — ligne 104
- `test_le_createur_couvre_ce_qu_il_cree` — ligne 112
- `test_la_provenance_fictive_est_le_defaut_et_reste_explicitement_modifiable` — ligne 122
- `test_la_source_de_marche_est_configuree_sur_le_compte_client` — ligne 136
- `test_un_doublon_probable_suspend_la_creation_avec_de_quoi_decider` — ligne 148
- `test_la_confirmation_debloque_la_creation` — ligne 158
- `test_une_personne_deja_connue_est_signalee_avant_creation` — ligne 166
- `test_un_client_avec_historique_refuse_la_suppression_et_dit_pourquoi` — ligne 183
- `test_un_client_vierge_se_supprime` — ligne 196
- `test_le_refus_de_suppression_laisse_une_trace` — ligne 201
- `test_archiver_puis_reactiver` — ligne 216
- `test_deux_ecritures_concurrentes_la_seconde_recoit_un_409` — ligne 230
- `test_le_conflit_d_ecriture_est_audite` — ligne 253
- `test_une_cle_de_contrainte_inconnue_est_refusee` — ligne 268
- `test_les_scalaires_se_modifient_hors_verrou` — ligne 277
- `test_un_ticket_minimum_au_dessus_du_maximum_est_refuse` — ligne 291
- `test_une_preference_datee_reste_rejouable_et_garde_sa_source` — ligne 299
- `test_un_mandat_porte_son_propre_profil_sans_modifier_le_client` — ligne 350
- `test_le_changement_de_societe_conserve_l_historique` — ligne 403
- `test_les_contacts_actifs_seuls_sont_proposes` — ligne 430
- `test_une_affiliation_ne_se_deplace_pas_par_patch` — ligne 445
- `test_un_contact_d_un_autre_client_est_refuse_par_le_serveur` — ligne 463
- `test_changer_le_client_d_une_opportunite_invalide_les_contacts` — ligne 477
- `test_le_contact_principal_ne_se_repete_pas_dans_les_participants` — ligne 499
- `test_perdre_une_opportunite_sans_motif_est_refuse` — ligne 511
- `test_l_opportunite_recoit_une_reference_serie` — ligne 529
- `test_une_opportunite_reliee_refuse_la_suppression` — ligne 540
- `test_une_interaction_existe_sans_opportunite` — ligne 556
- `test_un_participant_d_un_autre_client_est_refuse` — ligne 566
- `test_une_interaction_rafraichit_l_activite_de_l_opportunite` — ligne 580
- `test_une_interaction_se_supprime_et_laisse_une_trace` — ligne 594
- `test_une_relance_cloturee_disparait_des_signaux_et_peut_etre_rouverte` — ligne 607
- `test_modifier_une_prochaine_action_met_a_jour_la_relance_ouverte` — ligne 640
- `test_une_opportunite_se_reattribue_a_un_collegue` — ligne 658
- `test_on_ne_reattribue_pas_a_une_autre_entite` — ligne 675

## backend/tests/test_client_c24.py

- `test_client_move_revalidates_persisted_participants_when_patch_omits_them` — ligne 64
- `test_historical_profile_excludes_future_transactions_from_every_observation` — ligne 73
- `test_cycle_rejects_future_dates_as_observed_history` — ligne 86
- `test_pipeline_and_ticket_never_sum_or_median_different_currency_units` — ligne 91
- `test_real_import_engine_excludes_demo_mandate_from_real_profile` — ligne 106
- `test_unlinked_client_move_requires_explicit_coherent_replacement` — ligne 121
- `test_linked_opportunity_cannot_move_client_or_mandate` — ligne 132
- `test_all_dated_entrypoints_exclude_future_observations` — ligne 169
- `test_pipeline_current_state_is_distinct_from_dated_transactions` — ligne 180
- `test_same_currency_medians_and_declared_bounds_keep_their_unit` — ligne 193
- `test_missing_currency_never_inherits_eur_in_analytics` — ligne 210
- `test_real_mode_does_not_implicitly_include_a_demo_only_dataset` — ligne 222
- `test_future_and_undated_rows_are_separately_explained` — ligne 233
- `test_other_entity_context_is_not_disclosed_or_accepted` — ligne 241
- `test_only_future_dates_give_no_cycle_and_no_negative_duration` — ligne 249
- `test_asof_boundary_and_unknown_dates_are_explicit` — ligne 254
- `test_person_profile_uses_affiliation_effective_on_requested_date` — ligne 262
- `test_persisted_primary_contact_also_requires_explicit_replacement` — ligne 272
- `test_declared_ticket_range_is_visible_without_observations` — ligne 280
- `test_imported_future_trade_cannot_create_a_lifecycle_signal` — ligne 288
- `test_move_and_product_creation_cannot_commit_conflicting_attributions` — ligne 296
- `test_t14_attribution_dates_currencies_and_imported_demo_interact_coherently` — ligne 344

## backend/tests/test_client_card.py

- `test_les_emetteurs_autorises_jamais_sollicites_sont_rendus` — ligne 76
- `test_un_emetteur_traite_hors_liste_est_signale_avec_ses_dates` — ligne 92
- `test_un_emetteur_traite_bien_qu_exclu_est_signale_a_part` — ligne 107
- `test_le_module_ne_pretend_pas_savoir_quand_une_exclusion_a_ete_posee` — ligne 120
- `test_sans_politique_declaree_rien_n_est_hors_politique` — ligne 132
- `test_le_rapprochement_ignore_la_casse_mais_affiche_la_saisie` — ligne 145
- `test_un_nom_commercial_se_range_sous_sa_famille` — ligne 157
- `test_une_famille_declaree_et_jamais_traitee_reste_une_ouverture` — ligne 190
- `test_un_produit_inclassable_n_est_pas_une_anomalie` — ligne 205
- `test_la_famille_se_deduit_du_libelle` — ligne 221
- `test_l_espace_negatif_couvre_devises_produits_et_sous_jacents` — ligne 236
- `test_au_dela_du_seuil_les_bornes_rendent_une_bande` — ligne 249
- `test_en_dessous_du_seuil_les_bornes_rendent_les_points` — ligne 263
- `test_sans_transaction_les_bornes_restent_vides_sans_planter` — ligne 277
- `test_les_seuils_disent_ce_qui_manque_et_a_partir_de_combien` — ligne 290
- `test_sur_un_client_etabli_les_seuils_sont_atteints` — ligne 313
- `test_la_fiche_complete_porte_tout_ce_que_l_ecran_affiche` — ligne 331
- `test_sans_dossier_tranche_le_taux_reste_vide_pas_zero` — ligne 364
- `test_un_client_sans_transaction_rend_une_fiche_complete_et_muette` — ligne 377

## backend/tests/test_client_chain.py

- `test_une_rfq_creee_depuis_une_opportunite_garde_le_lien` — ligne 157
- `test_une_opportunite_d_une_autre_entite_est_refusee` — ligne 180
- `test_un_deal_booke_depuis_une_opportunite_porte_son_rattachement` — ligne 195
- `test_un_trade_ne_peut_pas_melanger_deux_clients` — ligne 221
- `test_une_opportunite_d_un_autre_client_est_refusee_au_booking` — ligne 237
- `test_un_contact_sans_client_est_refuse` — ligne 250
- `test_la_chaine_se_remonte_du_trade_jusqu_a_la_personne` — ligne 260
- `test_le_trade_reste_chez_l_ancien_employeur_apres_un_depart` — ligne 300
- `test_l_opportunite_liee_a_un_trade_refuse_la_suppression` — ligne 328
- `test_une_rfq_sans_opportunite_fonctionne_comme_avant` — ligne 343
- `test_une_rfq_directe_peut_etre_rattachee_au_client_et_au_mandat` — ligne 352
- `test_une_rfq_client_sans_mandat_est_refusee` — ligne 368
- `test_un_deal_sans_client_se_booke_comme_avant` — ligne 382
- `test_un_deal_produit_peut_porter_une_structure_juridique_sans_client` — ligne 392
- `test_un_deal_direct_client_exige_un_motif` — ligne 403
- `test_le_refus_de_rattachement_n_alloue_pas_de_reference` — ligne 411
- `test_rfq_booking_refusal_preserves_crm_product_and_allows_clean_retry` — ligne 487

## backend/tests/test_client_coherence.py

- `test_les_analytiques_comptent_l_historique_importe` — ligne 127
- `test_reimporter_ne_double_pas_les_interactions` — ligne 147
- `test_on_ne_booke_pas_sur_le_client_d_une_autre_entite` — ligne 163
- `test_on_ne_booke_pas_sur_l_opportunite_d_une_autre_entite` — ligne 179
- `test_un_rattachement_legitime_passe_toujours` — ligne 193
- `test_plusieurs_lignes_le_meme_jour_ne_contredisent_pas_les_deux_ecrans` — ligne 214
- `test_tout_le_meme_jour_reste_un_historique_insuffisant` — ligne 244
- `test_les_analytiques_ne_font_pas_de_n_plus_un` — ligne 257
- `test_les_signaux_ne_font_pas_de_n_plus_un_non_plus` — ligne 282

## backend/tests/test_client_constraints.py

- `test_deux_editions_concurrentes_la_seconde_est_refusee_pas_perdue` — ligne 48
- `test_le_compare_and_swap_en_base_refuse_deux_sessions_sur_la_meme_version` — ligne 70
- `test_une_ecriture_sur_la_version_a_jour_passe` — ligne 94
- `test_la_version_avance_a_chaque_ecriture` — ligne 105
- `test_une_ecriture_sans_version_est_refusee` — ligne 115
- `test_les_scalaires_se_modifient_sans_toucher_au_verrou` — ligne 125
- `test_une_cle_inconnue_est_refusee` — ligne 140
- `test_un_vocabulaire_hors_liste_est_refuse` — ligne 149
- `test_une_liste_attendue_qui_n_en_est_pas_une_est_refusee` — ligne 156
- `test_un_issuer_se_stocke_avec_son_identifiant_et_son_libelle` — ligne 162
- `test_un_issuer_sans_libelle_est_refuse` — ligne 171
- `test_un_blob_complet_et_valide_passe` — ligne 177
- `test_le_rang_suit_la_qualite_de_credit_pas_l_alphabet` — ligne 193
- `test_un_client_exigeant_A_moins_refuse_BBB_accepte_AA` — ligne 206
- `test_la_casse_et_les_espaces_ne_font_pas_echouer_une_notation` — ligne 214
- `test_une_notation_inventee_est_refusee` — ligne 218
- `test_l_echelle_est_ordonnee_du_meilleur_au_pire` — ligne 224
- `test_un_ticket_minimum_superieur_au_maximum_est_refuse` — ligne 232
- `test_une_maturite_minimale_superieure_au_maximum_est_refusee` — ligne 242
- `test_une_concentration_au_dela_de_cent_pourcent_est_refusee` — ligne 249
- `test_une_maturite_de_dix_huit_mois_est_exprimable` — ligne 257
- `test_des_bornes_absentes_ne_bloquent_rien` — ligne 264
- `test_une_fiche_sans_contrainte_se_relit_en_objet_vide` — ligne 273
- `test_un_blob_illisible_ne_fait_pas_tomber_l_ecran` — ligne 279

## backend/tests/test_client_constraints_ref.py

- `test_un_libelle_francais_donne_une_cle_stable` — ligne 86
- `test_un_libelle_sans_lettre_ne_produit_pas_de_cle` — ligne 92
- `test_un_ticker_present_dans_deux_groupes_n_est_propose_qu_une_fois` — ligne 102
- `test_une_contrepartie_inactive_n_est_pas_proposee` — ligne 109
- `test_un_catalogue_inconnu_se_signale` — ligne 117
- `test_un_pourcentage_hors_bornes_est_refuse` — ligne 125
- `test_un_booleen_n_est_pas_un_nombre` — ligne 134
- `test_une_duree_s_exprime_en_mois_entiers` — ligne 142
- `test_un_vocabulaire_ferme_refuse_ce_qui_n_y_est_pas` — ligne 149
- `test_une_reference_saisie_librement_est_admise` — ligne 158
- `test_une_cle_qu_aucune_definition_ne_decrit_reste_refusee` — ligne 168
- `test_une_liste_vide_ne_se_stocke_pas` — ligne 176
- `test_un_champ_declare_pour_un_client_ne_fuit_pas_chez_un_autre` — ligne 186
- `test_un_champ_de_maison_vaut_pour_tous_les_clients` — ligne 204
- `test_une_cle_standard_ne_se_redeclare_pas` — ligne 215
- `test_une_liste_fermee_sans_valeurs_est_refusee` — ligne 223
- `test_deux_champs_de_meme_cle_dans_la_meme_portee_se_refusent` — ligne 230
- `test_archiver_un_champ_ne_bloque_pas_la_fiche_de_ceux_qui_l_ont_rempli` — ligne 240
- `test_un_champ_archive_reste_visible_tant_qu_il_porte_une_valeur` — ligne 266
- `test_un_champ_jamais_rempli_se_supprime_pour_de_bon` — ligne 290
- `test_restaurer_un_champ_le_remet_en_saisie` — ligne 300
- `test_le_schema_decrit_les_champs_et_resout_les_catalogues` — ligne 313
- `test_un_payoff_propre_au_client_reutilise_le_champ_existant` — ligne 333
- `test_le_champ_ajoute_apparait_dans_le_schema_sans_toucher_a_l_ecran` — ligne 351
- `test_une_definition_de_client_prime_sur_celle_de_la_maison` — ligne 365
- `test_le_cloisonnement_d_entite_vaut_aussi_pour_les_definitions` — ligne 390

## backend/tests/test_client_cycle.py

- `test_aucune_transaction_ne_produit_aucune_prediction` — ligne 40
- `test_une_seule_transaction_ne_produit_aucune_fenetre` — ligne 48
- `test_deux_transactions_donnent_un_intervalle_mais_peu_de_confiance` — ligne 60
- `test_une_cadence_trop_dispersee_n_est_pas_nommee` — ligne 70
- `test_aucune_fenetre_de_contact_sans_cadence_connue` — ligne 79
- `test_une_pause_exceptionnelle_ne_deforme_pas_la_cadence` — ligne 90
- `test_la_moyenne_reste_rendue_pour_qui_veut_la_lire` — ligne 101
- `test_une_cadence_reguliere_donne_une_fenetre_etroite` — ligne 110
- `test_une_cadence_irreguliere_donne_une_fenetre_large` — ligne 119
- `test_la_fenetre_n_est_jamais_reduite_a_un_jour` — ligne 129
- `test_beaucoup_d_observations_regulieres_donnent_une_confiance_haute` — ligne 140
- `test_beaucoup_d_observations_irregulieres_ne_suffisent_pas` — ligne 146
- `test_peu_d_observations_regulieres_donnent_une_confiance_moyenne` — ligne 153
- `test_chaque_resultat_porte_ses_observations_en_clair` — ligne 159
- `test_un_trimestriel_muet_depuis_cent_jours_n_est_pas_en_retard` — ligne 171
- `test_un_mensuel_muet_depuis_cent_jours_est_en_retard` — ligne 177
- `test_un_client_dans_les_temps_n_est_pas_signale` — ligne 186
- `test_la_fenetre_de_contact_recule_du_delai_observe` — ligne 195
- `test_sans_delai_observable_le_defaut_configure_s_applique` — ligne 208
- `test_le_delai_observe_est_une_mediane_pas_une_moyenne` — ligne 219
- `test_une_paire_incoherente_est_ecartee` — ligne 231
- `test_aucune_paire_exploitable_rend_none` — ligne 239
- `test_une_cadence_stable_entre_deux_societes_se_lit_comme_telle` — ligne 245
- `test_une_cadence_qui_epouse_celle_de_la_maison_se_lit_aussi` — ligne 261
- `test_la_comparaison_ne_conclut_jamais_a_une_cause` — ligne 273
- `test_sans_historique_dans_la_societe_actuelle_rien_n_est_comparable` — ligne 295

## backend/tests/test_client_demo_seed.py

- `test_les_neuf_societes_sont_semees` — ligne 83
- `test_toutes_les_transactions_sont_rattachees` — ligne 88
- `test_chaque_affiliation_pointe_sur_le_bon_client` — ligne 96
- `test_rhone_a_une_cadence_de_confiance_haute` — ligne 106
- `test_rhone_ouvre_sa_fenetre_de_contact_aujourdhui` — ligne 117
- `test_rhone_porte_les_deux_anomalies_d_emetteur` — ligne 129
- `test_rhone_distingue_le_booke_de_l_importe` — ligne 143
- `test_rhone_a_un_taux_de_conversion_et_des_motifs_de_perte` — ligne 150
- `test_rhone_expose_son_appel_d_offres` — ligne 160
- `test_jura_ne_nomme_aucune_cadence` — ligne 170
- `test_jura_rend_des_points_et_non_une_bande` — ligne 182
- `test_jura_a_des_seuils_encore_a_atteindre` — ligne 192
- `test_jura_leve_une_relance_echue_et_aucune_fenetre` — ligne 202
- `test_la_fondation_est_muette_mais_sa_fiche_est_entiere` — ligne 230
- `test_alpes_est_dormant_par_rapport_a_sa_propre_cadence` — ligne 250
- `test_geneve_reste_en_confiance_basse_malgre_dix_transactions` — ligne 269
- `test_valais_ne_produit_aucune_anomalie_faute_de_politique` — ligne 280
- `test_valais_n_a_pas_de_rail_faute_de_fourchette` — ligne 294
- `test_leman_montre_deux_profils_que_la_moyenne_effacerait` — ligne 303
- `test_l_historique_d_anne_reste_chez_son_ancien_employeur` — ligne 322
- `test_la_comparaison_d_anne_est_lisible_et_descriptive` — ligne 342
- `test_le_jeu_produit_des_signaux_de_plusieurs_natures` — ligne 353
- `test_demo_signals_require_explicit_http_opt_in` — ligne 364
- `test_le_fichier_d_import_demontre_bien_ses_anomalies` — ligne 394
- `test_le_fichier_d_import_accepte_les_dates_francaises` — ligne 432
- `test_le_semis_prend_l_entite_du_compte_et_non_none` — ligne 443
- `test_un_compte_inexistant_arrete_le_semis` — ligne 483
- `test_le_jeu_se_retire_entierement` — ligne 496
- `test_le_jeu_produit_plusieurs_familles_de_sous_jacent` — ligne 530
- `test_les_trois_etats_d_execution_existent_dans_le_jeu` — ligne 546
- `test_une_comparaison_de_prix_est_possible_quelque_part` — ligne 560
- `test_un_capital_garanti_n_invente_pas_un_coupon` — ligne 574
- `test_l_univers_declare_rencontre_vraiment_les_sous_jacents_traites` — ligne 584

## backend/tests/test_client_import.py

- `test_l_apercu_annonce_sans_rien_ecrire` — ligne 105
- `test_le_versement_ecrit_ce_que_l_apercu_avait_annonce` — ligne 121
- `test_l_import_conserve_le_mandat_le_cadre_juridique_et_le_payoff` — ligne 131
- `test_l_historique_verse_atteint_le_moteur_de_cycles` — ligne 161
- `test_l_ecran_sait_distinguer_l_importe_du_booke` — ligne 187
- `test_une_transaction_se_rattache_a_l_affiliation_de_sa_date` — ligne 200
- `test_une_transaction_hors_de_tout_passage_est_refusee` — ligne 215
- `test_verser_deux_fois_le_meme_fichier_ne_double_rien` — ligne 236
- `test_une_transaction_sans_reference_externe_est_idempotente` — ligne 254
- `test_deux_lignes_identiques_du_fichier_restent_deux_souscriptions` — ligne 273
- `test_deux_transactions_proches_mais_distinctes_ne_sont_pas_fusionnees` — ligne 301
- `test_un_import_complete_les_champs_vides_sans_ecraser_la_saisie` — ligne 318
- `test_une_ligne_fautive_bloque_tout_le_versement` — ligne 338
- `test_on_peut_demander_explicitement_d_ignorer_les_lignes_fautives` — ligne 348
- `test_un_vocabulaire_inconnu_est_refuse_avec_les_valeurs_acceptees` — ligne 355
- `test_une_date_illisible_est_signalee_avec_son_numero_de_ligne` — ligne 362
- `test_les_dates_francaises_sont_acceptees` — ligne 375
- `test_les_entetes_tolerent_la_casse_et_les_accents` — ligne 385
- `test_une_section_inconnue_est_signalee_sans_bloquer` — ligne 392
- `test_un_fichier_sans_section_exploitable_est_refuse` — ligne 399
- `test_un_json_illisible_est_refuse_clairement` — ligne 405
- `test_une_extension_inconnue_est_refusee` — ligne 413
- `test_le_modele_excel_porte_une_feuille_par_objet` — ligne 423
- `test_le_modele_excel_se_reimporte_tel_quel` — ligne 434
- `test_le_modele_json_porte_ses_vocabulaires` — ligne 451
- `test_un_versement_laisse_un_lot_consultable` — ligne 460
- `test_annuler_un_lot_retire_ses_transactions_mais_garde_le_referentiel` — ligne 469
- `test_un_lot_deja_annule_ne_se_rannule_pas` — ligne 484
- `test_apres_annulation_le_moteur_redevient_muet` — ligne 492

## backend/tests/test_client_intelligence.py

- `test_historical_payoff_labels_are_grouped_without_rewriting_the_deals` — ligne 70
- `test_les_trois_niveaux_se_lisent_separement` — ligne 88
- `test_la_comparaison_dit_ressemblance_pas_causalite` — ligne 120
- `test_le_comportement_observe_compte_sans_interpreter` — ligne 143
- `test_les_seuils_d_habitude_restent_explicites` — ligne 167
- `test_la_recence_ne_supprime_pas_une_habitude_ancienne` — ligne 171
- `test_declare_et_observe_cohabitent_sans_s_ecraser` — ligne 177
- `test_une_societe_n_est_pas_reduite_a_sa_moyenne` — ligne 196
- `test_une_personne_sans_transaction_ne_recoit_aucune_prediction` — ligne 220
- `test_une_relance_echue_leve_un_signal` — ligne 234
- `test_un_client_dormant_est_signale_relativement_a_sa_cadence` — ligne 252
- `test_une_opportunite_sans_activite_est_signalee` — ligne 274
- `test_une_opportunite_close_ne_dort_pas` — ligne 293
- `test_une_maturite_proche_est_signalee_sans_prediction_de_rappel` — ligne 307
- `test_la_prochaine_constatation_lifecycle_remplace_la_maturite_lointaine` — ligne 333
- `test_un_releve_de_fenetre_ne_se_signale_pas_comme_une_constatation` — ligne 358
- `test_une_maturite_importee_reste_commerciale_et_sans_lien_lifecycle` — ligne 388
- `test_evenement_annule_non_projete_et_mes_dossiers_respecte` — ligne 406
- `test_un_deal_sans_client_ne_produit_aucun_signal` — ligne 436
- `test_les_signaux_sortent_du_plus_urgent_au_plus_lointain` — ligne 450

## backend/tests/test_client_lot2.py

- `test_l_agregat_client_signale_les_mandats_aux_habitudes_opposees` — ligne 38
- `test_un_client_reel_exclut_les_deals_uat_par_defaut` — ligne 78
- `test_marex_peut_etre_souvent_meilleur_puis_finalement_retenu` — ligne 128
- `test_le_nombre_de_requetes_ne_depend_pas_du_nombre_de_mandats` — ligne 181

## backend/tests/test_client_migration.py

- `test_les_colonnes_de_rattachement_arrivent_sur_une_base_existante` — ligne 132
- `test_les_lignes_existantes_ne_bougent_pas` — ligne 164
- `test_rejouer_la_migration_ne_casse_rien` — ligne 194
- `test_les_index_de_recherche_sont_poses` — ligne 211
- `test_un_nouveau_clone_traverse_la_sequence_de_demarrage` — ligne 232

## backend/tests/test_client_technical.py

- `test_le_coupon_et_la_protection_se_lisent_dans_le_script` — ligne 96
- `test_un_script_herite_sans_moniteurs_passe_par_l_heuristique` — ligne 106
- `test_un_script_illisible_ne_fait_pas_tomber_la_fiche` — ligne 115
- `test_un_script_absent_rend_des_niveaux_vides_et_non_zero` — ligne 124
- `test_un_param_a_zero_n_est_pas_un_coupon` — ligne 131
- `test_les_parametres_bookes_remplacent_les_valeurs_par_defaut_du_script` — ligne 136
- `test_un_param_coupon_par_constatation_reste_un_echeancier` — ligne 148
- `test_un_deal_et_une_ligne_importee_rendent_les_memes_champs` — ligne 165
- `test_deux_deals_du_meme_script_gardent_leurs_economics_bookes_distincts` — ligne 208
- `test_la_nature_vient_du_catalogue` — ligne 237
- `test_le_prefixe_yahoo_sert_de_repli` — ligne 246
- `test_un_ticker_inconnu_ne_se_devine_pas` — ligne 252
- `test_mono_et_multi_se_distinguent_par_le_compte` — ligne 258
- `test_un_panier_melange_est_dit_mixte` — ligne 267
- `test_un_panier_partiellement_connu_est_signale` — ligne 274
- `test_les_libelles_sont_lisibles` — ligne 283
- `test_les_moyennes_se_font_par_famille` — ligne 299
- `test_une_seule_observation_ne_fait_pas_une_moyenne` — ligne 314
- `test_une_famille_sans_coupon_connu_rend_null` — ligne 325
- `test_les_trois_etats_d_execution_restent_distincts` — ligne 335
- `test_sans_prix_connu_la_mediane_reste_nulle` — ligne 353
- `test_l_import_lit_traite_avec_nous_et_le_prix` — ligne 362
- `test_une_valeur_ni_oui_ni_non_est_refusee_avec_le_bon_conseil` — ligne 393
- `test_un_panier_importe_tient_dans_une_cellule` — ligne 412
- `test_un_ticker_seul_reste_un_ticker` — ligne 426
- `test_le_decoupage_atteint_vraiment_la_lecture_d_historique` — ligne 435
- `test_la_mediane_ne_laisse_pas_fuir_le_binaire` — ligne 462
- `test_une_famille_nomme_les_payoffs_qu_elle_melange` — ligne 473

## backend/tests/test_coherence_analytiques.py

- `test_la_table_de_flux_somme_au_prix` — ligne 122
- `test_l_intervalle_de_confiance_encadre_le_prix` — ligne 132
- `test_les_scenarios_se_partagent_tous_les_chemins` — ligne 141
- `test_les_pourcentages_suivent_leurs_comptes` — ligne 149
- `test_la_ventilation_par_date_somme_au_compteur_de_rappels` — ligne 157
- `test_aucune_date_de_rappel_n_est_orpheline` — ligne 170
- `test_les_percentiles_sont_ordonnes` — ligne 178
- `test_l_histogramme_couvre_tout_l_echantillon` — ligne 185
- `test_le_prix_des_probabilites_rejoint_celui_des_resultats` — ligne 193
- `test_la_duree_esperee_reste_dans_la_vie_du_produit` — ligne 206
- `test_les_chemins_se_partagent_tous_les_tirages` — ligne 214
- `test_le_fugit_et_la_duree_esperee_decrivent_la_meme_chose` — ligne 227
- `test_le_profil_dessine_la_barriere_du_script` — ligne 253
- `test_deplacer_la_barriere_deplace_la_rupture` — ligne 262
- `test_le_solveur_atteint_vraiment_le_prix_qu_il_annonce` — ligne 271
- `test_la_grille_retombe_sur_le_prix_aux_valeurs_courantes` — ligne 294
- `test_le_scenario_sans_choc_redonne_le_prix` — ligne 315
- `test_un_capital_garanti_n_annonce_aucune_perte` — ligne 344
- `test_la_perte_en_capital_est_absente_de_l_analyse_de_prix` — ligne 359
- `test_la_perte_nette_se_mesure_contre_le_prix_paye` — ligne 366
- `test_les_deux_mesures_repondent_bien_a_deux_questions` — ligne 373
- `test_la_perte_en_capital_recoupe_le_compte_de_pertes` — ligne 387

## backend/tests/test_commands_c08.py

- `test_lost_direct_booking_response_reuses_one_product_and_deal` — ligne 32
- `test_other_trade_forks_a_clean_product_without_changing_source` — ligne 43
- `test_same_booking_key_with_changed_content_is_an_audited_conflict` — ligne 66
- `test_legacy_exact_retry_is_safe_but_two_explicit_intentions_are_distinct` — ligne 77
- `test_retry_does_not_consume_limits_or_repeat_initial_audit_and_events` — ligne 90
- `test_failed_command_rolls_back_every_business_row_and_can_be_retried` — ligne 113
- `test_fork_keeps_old_rfq_terms_pinned_and_cannot_declassify_its_source` — ligne 129
- `test_fork_refuses_stale_or_missing_terms_without_creating_a_dossier` — ligne 171
- `test_a_fork_can_book_a_second_trade_and_preserves_the_original_archive` — ligne 184
- `test_concurrent_retries_commit_exactly_one_result` — ligne 220
- `test_private_bank_calculation_cannot_be_forked_into_an_ordinary_product` — ligne 243
- `test_agreement_replay_with_another_key_is_still_bound_to_the_same_result` — ligne 256
- `test_uat_cleanup_keeps_filiation_in_batch_and_tombstones_successful_commands` — ligne 274
- `test_failed_product_command_is_atomic_and_retryable` — ligne 297

## backend/tests/test_common_surface.py

- `test_ssvi_static_arbitrage_certificate_covers_all_strikes_and_horizon` — ligne 10
- `test_ssvi_derivatives_and_digital_match_independent_finite_differences` — ligne 23
- `test_ssvi_flat_limit_and_equity_smile` — ligne 37
- `test_ssvi_rejects_invalid_surface_instead_of_falling_back` — ligne 49
- `test_athena_separates_capital_coupon_and_put_and_stops_at_recall` — ligne 55
- `test_athena_final_recall_and_exact_protection_boundary` — ligne 66

## backend/tests/test_compute.py

- `test_run_batch_process_pool_matches_direct_run_mc` — ligne 44
- `test_run_batch_parallelizes_multiple_scenarios` — ligne 58
- `test_run_batch_isolates_per_job_failure` — ligne 74
- `test_run_batch_unknown_kind_raises_per_job` — ligne 90
- `test_run_batch_empty_jobs_returns_empty` — ligne 97
- `test_enqueue_then_claim_then_complete` — ligne 115
- `test_finalize_marks_completed_with_failures_when_partial` — ligne 145
- `test_record_job_result_updates_batch_counters_incrementally` — ligne 161
- `test_finalize_marks_failed_when_all_jobs_fail` — ligne 189
- `test_claim_next_batch_ignores_fresh_running_batch` — ligne 204
- `test_claim_next_batch_requeues_stale_running` — ligne 217
- `test_claim_next_batch_none_when_nothing_queued` — ligne 234
- `test_cancel_batch_stops_a_queued_batch` — ligne 241
- `test_cancel_batch_refused_on_terminal_batch` — ligne 253
- `test_cancel_batch_none_for_unknown_id` — ligne 265
- `test_finalize_batch_does_not_overwrite_a_cancelled_batch` — ligne 270
- `test_relaunch_batch_requeues_only_failed_jobs` — ligne 289
- `test_relaunch_batch_refused_on_fully_completed_batch` — ligne 316
- `test_relaunch_batch_refuses_a_failed_batch_without_failed_job` — ligne 328
- `test_relaunch_batch_refused_while_still_running` — ligne 344
- `test_delete_batch_removes_batch_and_its_jobs` — ligne 352
- `test_delete_batch_false_for_unknown_id` — ligne 365

## backend/tests/test_constatations_periode.py

- `test_les_trois_reductions_donnent_trois_prix_distincts` — ligne 67
- `test_allonger_la_fenetre_deplace_le_prix` — ligne 81
- `test_fenetre_d_un_point_est_le_comportement_ponctuel` — ligne 94
- `test_le_decompte_de_points_signale_une_fenetre_degeneree` — ligne 104
- `test_reduire_par_actif_puis_agreger_n_est_pas_l_inverse_sur_un_worst_of` — ligne 121
- `test_la_commutativite_protege_le_panier_pas_le_worst_of` — ligne 139
- `test_aucune_observation_americaine_avant_que_s0_existe` — ligne 167
- `test_la_fenetre_de_depart_part_de_sa_date_les_autres_y_arrivent` — ligne 191
- `test_la_longueur_en_jours_compte_les_observations_pas_les_jours_calendaires` — ligne 204
- `test_les_unites_calendaires_restent_des_durees` — ligne 214
- `test_la_frequence_de_releve_atteint_le_moteur` — ligne 228
- `test_le_produit_du_chantier_price_et_coute_moins_qu_un_ponctuel` — ligne 240
- `test_la_periode_donne_une_constatation_par_date_du_calendrier` — ligne 288
- `test_les_periodes_ne_se_recouvrent_pas` — ligne 300
- `test_periode_sur_une_date_unique_est_refusee` — ligne 313
- `test_deux_blocs_au_meme_jour_lisent_deux_niveaux_differents` — ligne 324
- `test_le_bloc_de_releve_ne_porte_aucune_reduction` — ligne 340
- `test_second_niveau_sans_fenetre_est_refuse` — ligne 350
- `test_trois_niveaux_sont_refuses_a_la_compilation` — ligne 359
- `test_periode_et_sous_frequence_se_contredisent` — ligne 364
- `test_la_sous_frequence_se_recale_sur_chaque_date_principale` — ligne 378
- `test_l_apercu_refuse_un_calendrier_absurde` — ligne 399
- `test_l_apercu_d_une_fenetre_de_longueur_dit_les_vraies_dates` — ligne 437

## backend/tests/test_contractual_calendars.py

- `test_month_end_is_anchored_in_both_directions_and_leap_year` — ligne 47
- `test_nested_monthly_grid_keeps_original_roll_before_business_adjustment` — ligne 52
- `test_invalid_lag_rejected_without_coercion_at_every_boundary` — ligne 61
- `test_preview_product_pricing_and_booking_share_dates_and_defaults` — ligne 76
- `test_target_payment_proposal_crosses_easter_and_thirty_is_supported` — ligne 93
- `test_nyse_closure_does_not_close_target_settlement_and_policy_is_retained` — ligne 99
- `test_basket_rule_is_explicit_and_shared_with_windows` — ligne 115
- `test_invalid_policy_is_refused_even_without_business_adjustment` — ligne 132
- `test_long_stub_always_merges_irregular_boundary_without_half_period_threshold` — ligne 145
- `test_long_stub_does_not_merge_regular_boundary` — ligne 151
- `test_frozen_pre_c05_calendar_is_restored_verbatim_even_with_old_drift` — ligne 155
- `test_param_arrays_expose_their_own_named_calendar_to_economics` — ligne 166
- `test_reinvestment_refuses_extra_observation_created_by_month_end_roll` — ligne 174
- `test_calendar_http_routes_keep_c01_business_price_permissions` — ligne 187
- `test_http_previews_refuse_invalid_settlement_lag` — ligne 202
- `test_product_price_and_booking_retain_the_explicit_calendar_and_dates` — ligne 207
- `test_rfq_retains_explicit_policy_and_frozen_dates_with_real_desk` — ligne 261
- `test_reinvestment_refuses_partial_calendar_resizing_without_mutating_source` — ligne 286

## backend/tests/test_contractual_timeline.py

- `test_distinct_dates_execute_chronologically_in_one_diffusion_step` — ligne 29
- `test_same_date_retains_explicit_source_order` — ligne 49
- `test_frozen_calendar_january_31_then_february_1_matches_historical_replay` — ligne 55
- `test_dated_blocks_precede_maturity_even_if_declared_after_it` — ligne 74
- `test_occurrences_keep_their_rank_window_and_payment_without_mutating_terms` — ligne 79
- `test_flow_times_are_contractual_and_stop_prevents_later_cashflows` — ligne 96
- `test_calendar_rounding_is_admitted_without_executing_a_future_date` — ligne 103
- `test_price_probabilities_and_paths_share_exact_terminal_time` — ligne 112
- `test_realvol_annualization_matches_dated_and_maturity_blocks` — ligne 124
- `test_one_day_mtm_uses_contractual_horizon_and_converges` — ligne 154
- `test_short_axis_is_shared_by_every_supported_model` — ligne 173
- `test_one_day_horizon_reaches_var_worker_and_offline_run` — ligne 186
- `test_unbooked_inlife_pricing_keeps_the_same_one_day_horizon` — ligne 199

## backend/tests/test_curve_consistency.py

- `test_forward_prepaye_vaut_exp_moins_qt_sous_courbe_plate` — ligne 55
- `test_forward_prepaye_vaut_exp_moins_qt_sous_courbe_pentue` — ligne 68
- `test_forward_prepaye_sigma_nulle_sur_maturite_non_ronde_est_exact` — ligne 75
- `test_theta_zero_coupon_est_le_portage_quotidien_du_df` — ligne 86
- `test_forward_prepaye_sous_modeles_a_vol_locale` — ligne 99
- `test_courbe_plate_au_niveau_r_equivaut_au_taux_plat` — ligne 107
- `test_parite_call_put_sous_courbe` — ligne 116
- `test_rho_du_zero_coupon_vaut_moins_t_fois_le_df` — ligne 128
- `test_le_taux_stochastique_reprice_sa_propre_courbe` — ligne 146
- `test_rho_non_nul_sous_courbe_et_taux_stochastiques` — ligne 164
- `test_les_forwards_reconstituent_exactement_les_facteurs_d_actualisation` — ligne 177
- `test_dr_decale_la_courbe_entiere_en_parallele` — ligne 188
- `test_absence_de_courbe_se_reconnait_a_step_fwd_none` — ligne 200
- `test_la_grille_de_vol_locale_suit_la_courbe` — ligne 212
- `test_les_probabilites_utilisent_la_courbe_pour_la_derive` — ligne 228

## backend/tests/test_dividend_curve.py

- `test_buckets_annuels_et_derniere_annee_partielle` — ligne 46
- `test_forward_prepaye_reproduit_integrale_de_la_courbe` — ligne 58
- `test_courbe_plate_reproduit_exactement_le_q_legacy` — ligne 63
- `test_tous_les_modeles_consument_la_meme_courbe` — ligne 73
- `test_schema_refuse_une_courbe_croissante_ou_non_annuelle` — ligne 80
- `test_snapshot_booking_restitue_les_noeuds_exacts_en_unites_moteur` — ligne 89
- `test_mark_to_future_refuse_la_courbe_plutot_que_de_la_reappliquer` — ligne 110
- `test_mtm_residuel_decale_les_buckets_sans_repartir_de_l_an_un` — ligne 116
- `test_mtm_apres_dernier_noeud_prolonge_le_dernier_bucket_a_plat` — ligne 125

## backend/tests/test_dividend_profile.py

- `test_le_rendement_declare_rapporte_les_dividendes_au_cours` — ligne 76
- `test_dividend_feed_error_is_missing_data_not_a_zero_yield` — ligne 85
- `test_le_rendement_implicite_se_lit_dans_l_ecart_des_deux_series` — ligne 94
- `test_les_deux_methodes_concordent_a_cours_stable` — ligne 100
- `test_un_titre_qui_ne_verse_pas_est_dit_tel` — ligne 107
- `test_une_divergence_forte_est_signalee` — ligne 115
- `test_le_rendement_se_calcule_a_une_date_passee` — ligne 129
- `test_un_ticker_muet_est_signale_sans_zero_silencieux` — ligne 140

## backend/tests/test_dupire_calibration.py

- `test_nappe_plate_donne_la_vol_locale_plate` — ligne 61
- `test_nappe_plate_le_prix_localvol_egale_le_prix_vol_constante` — ligne 67
- `test_nappe_plate_le_delta_localvol_egale_le_delta_vol_constante` — ligne 80
- `test_le_skew_reste_un_skew` — ligne 91

## backend/tests/test_echeancier_fige.py

- `test_le_booking_fige_les_dates_calendaires` — ligne 48
- `test_il_fige_les_releves_de_chaque_constatation` — ligne 56
- `test_il_fige_le_rang_la_reduction_et_les_blocs` — ligne 66
- `test_il_marque_le_releve_qui_declenche_aussi_un_evenement` — ligne 76
- `test_un_ancrage_different_donne_un_echeancier_different` — ligne 86
- `test_un_script_non_resoluble_ne_bloque_pas_le_booking` — ligne 98
- `test_un_produit_en_mode_normal_est_fige_aussi` — ligne 106
- `test_la_fenetre_de_depart_est_figee_a_part` — ligne 115
- `test_le_json_fige_est_stable` — ligne 127

## backend/tests/test_economic_amendments.py

- `test_limit_blocks_two_million_atomically_but_accepts_replacement_at_1_4m` — ligne 44
- `test_current_policy_and_other_positions_are_reread_at_application` — ligne 79
- `test_concentration_and_limit_survive_rename_inactive_bank_and_historical_labels` — ligne 94
- `test_unknown_same_name_exception_and_missing_fx_remain_explicit` — ligne 114
- `test_measured_limit_missing_data_blocks_then_qualified_current_value_is_used` — ligne 133
- `test_qualified_native_measures_drive_replacement_decision` — ligne 159
- `test_changed_payment_horizon_cannot_reuse_old_measured_value` — ligne 185
- `test_d01_attestation_does_not_authorize_later_nominal_change` — ligne 203
- `test_full_measured_limits_are_never_cleared_by_nominal_only_data` — ligne 217
- `test_http_c01_permissions_and_shared_operations_amendment` — ligne 229
- `test_non_finite_numeric_amendments_are_rejected` — ligne 254
- `test_credit_evidence_migration_is_additive_and_idempotent` — ligne 262
- `test_read_scope_and_strict_checker_scope_remain_identical_to_c01` — ligne 277
- `test_replacement_uat_is_scoped_to_its_batch_without_production_consumption` — ligne 294
- `test_two_concurrent_amendments_cannot_both_consume_the_same_remaining_limit` — ligne 307

## backend/tests/test_editable_vol_surface.py

- `test_class_and_level_profiles_match_proposed_anchors_and_flat_limit` — ligne 24
- `test_nonflat_atm_term_structure_has_positive_density_and_calendar_derivative` — ligne 35
- `test_invalid_manual_edits_are_rejected_not_fallback` — ligne 47
- `test_surface_survives_display_booking_residual_roundtrip_without_percent_conversion` — ligne 56
- `test_surface_grid_uses_term_carry_and_responds_to_sigma_scenario` — ligne 68
- `test_surface_reaches_pricing_and_flat_target_equals_gbm_with_common_random_numbers` — ligne 79
- `test_authenticated_surface_api_rejects_invalid_and_returns_full_certificate` — ligne 91
- `test_heston_fit_changes_initial_variance_with_target_level` — ligne 104
- `test_legacy_shape_scenario_cannot_silently_ignore_the_new_surface` — ligne 114

## backend/tests/test_emt.py

- `test_un_panier_multi_actifs_n_est_pas_un_worst_of` — ligne 5
- `test_le_worst_of_est_lu_dans_le_payoff` — ligne 13
- `test_un_commentaire_ne_declenche_pas_un_worst_of` — ligne 20
- `test_un_libelle_de_flux_ne_declenche_pas_un_worst_of` — ligne 27
- `test_seule_une_protection_contractuelle_complete_et_inconditionnelle_est_garantie` — ligne 34
- `test_le_levier_emt_lit_la_valeur_economique_saisie` — ligne 46

## backend/tests/test_engine.py

- `test_call_atm_1y` — ligne 52
- `test_call_otm_2y` — ligne 59
- `test_put_call_parity` — ligne 70
- `test_param_default_used_when_user_params_omits_it` — ligne 82
- `test_runtime_error_in_script_raises_instead_of_silently_pricing_zero` — ligne 101
- `test_bare_basket_keyword_prices_without_nameerror` — ligne 114
- `test_bare_n_keyword_prices_without_nameerror` — ligne 132
- `test_antithetic_reduces_variance` — ligne 145
- `test_sabr_vol_atm` — ligne 156
- `test_sabr_mc_matches_hagan_formula` — ligne 162
- `test_local_vol_collapses_to_gbm_when_flat` — ligne 183
- `test_heston_spot_process_is_martingale` — ligne 196
- `test_heston_qe_vectorized_matches_scalar` — ligne 214
- `test_lsv_marginal_matches_local_vol_target` — ligne 233
- `test_lsv_differs_from_pure_local_vol_on_autocall` — ligne 259
- `test_payoff_profile_pins_level_no_drift_spike` — ligne 302
- `test_n_eff_antithetic` — ligne 339
- `test_n_eff_plain` — ligne 348
- `test_flux_table_populated` — ligne 356
- `test_flux_table_agrege_exactement_les_deux_jambes_antithetiques` — ligne 365
- `test_mtf_shape_and_stat_keys` — ligne 392
- `test_mtf_zcb_is_deterministic` — ligne 422
- `test_mtf_call_tracks_forward_martingale` — ligne 441
- `test_s_min_s_max_bound_current_spot` — ligne 466
- `test_s_prev_equals_inception_at_first_observation` — ligne 481
- `test_s_prev_telescoping_sum_matches_terminal_payoff` — ligne 494
- `test_realvol_converges_to_input_sigma` — ligne 512
- `test_sigma_r_zero_matches_deterministic_rate` — ligne 533
- `test_sigma_r_refits_the_curve_on_zcb` — ligne 543
- `test_sigma_r_runs_on_every_model` — ligne 569
- `test_rho_rS_inert_when_sigma_r_zero` — ligne 579
- `test_a_r_zero_is_default_and_matches_abm` — ligne 592
- `test_hull_white_zero_coupon_matches_curve_within_sampling_error` — ligne 602
- `test_hull_white_stationary_variance` — ligne 618
- `test_hull_white_runs_on_every_model` — ligne 637
- `test_eval_paths_inherits_wof_min_init` — ligne 653
- `test_greeks_delta_gamma_theta_match_bs` — ligne 691
- `test_greeks_accept_yield_curve` — ligne 714
- `test_corr_greek_positive_for_basket_call` — ligne 730
- `test_proba_ki_classification_is_discount_independent` — ligne 759
- `test_corr_matrix_validation_raises` — ligne 770
- `test_heston_collapses_to_bs_when_xi_tiny` — ligne 788
- `test_heston_skew_direction_follows_rho` — ligne 800
- `test_continuous_barrier_matches_first_passage_analytic` — ligne 822
- `test_continuous_barrier_monitoring_runs_on_every_model` — ligne 848
- `test_barrier_monitoring_invalid_value_raises` — ligne 861
- `test_heston_vectorized_matches_reference_loop` — ligne 902
- `test_sabr_vectorized_matches_reference_loop` — ligne 946
- `test_historical_running_extrema_finds_mid_window_dip` — ligne 981
- `test_historical_running_extrema_empty_window_is_neutral` — ligne 993
- `test_backtest_replay_captures_intra_period_barrier_breach` — ligne 1013
- `test_backtest_replay_no_breach_when_price_stays_above_barrier` — ligne 1039
- `test_backtest_bof_max_accumulates_across_observations` — ligne 1066
- `test_residual_autocall_certain_recall_and_index` — ligne 1163
- `test_residual_degressive_param_reads_right_row` — ligne 1182
- `test_residual_memory_coupons_inherited` — ligne 1202
- `test_residual_ki_already_touched` — ligne 1215
- `test_shift_events_drops_past_keeps_maturity` — ligne 1226
- `test_resolve_constats_anchor` — ligne 1235
- `test_residual_s_min_barrier_already_breached` — ligne 1288
- `test_residual_realvol_inherited` — ligne 1300
- `test_residual_wof0_seed_kills_phantom_return` — ligne 1314
- `test_residual_strike_fix_past_window` — ligne 1324
- `test_niveau_initial_combines_past_and_future` — ligne 1335
- `test_residual_s_prev_inherited` — ligne 1360
- `test_history_replay_extended_state` — ligne 1373
- `test_history_replay_fix_window_realized` — ligne 1398
- `test_history_replay_script_using_s_min_no_crash` — ligne 1428

## backend/tests/test_engine_golden.py

- `test_prix_inchanges_sans_courbe_tous_modeles` — ligne 118
- `test_prix_inchange_produit_a_barriere` — ligne 128
- `test_prix_inchange_produit_a_barriere_heston` — ligne 135
- `test_prix_inchange_autocall` — ligne 141
- `test_prix_inchanges_taux_stochastique` — ligne 170
- `test_prix_inchange_etat_residuel_complet` — ligne 180
- `test_prix_inchange_fenetre_strike_fix` — ligne 208
- `test_prix_inchange_barriere_continue` — ligne 226
- `test_prix_inchange_barriere_continue_heston` — ligne 232
- `test_greeks_pretrade_inchanges` — ligne 240

## backend/tests/test_fenetre_de_depart_vie.py

- `test_le_spot_du_jour_se_mesure_contre_le_s0_du_rejeu` — ligne 74
- `test_le_niveau_initial_rendu_est_celui_de_la_fenetre` — ligne 84
- `test_la_fenetre_de_depart_lit_chaque_releve_a_sa_date` — ligne 92

## backend/tests/test_fixing_finality_registry.py

- `test_no_delay_but_no_intraday_bar` — ligne 37
- `test_finality_fails_closed` — ligne 54
- `test_intraday_cannot_create_official_version_or_coupon` — ligne 58
- `test_three_calendar_day_carry_boundary` — ligne 80
- `test_official_automatic_fixing_survives_missing_provider_row` — ligne 89
- `test_total_outage_keeps_official_prefix_and_diagnoses_source` — ligne 101
- `test_exception_decision_rolls_back_and_same_request_can_retry` — ligne 113
- `test_mtm_uses_official_90_for_coupon_not_provider_40` — ligne 161
- `test_pending_version_is_not_a_provider_fallback` — ligne 175
- `test_unversioned_candidate_is_never_a_legacy_strike_reference` — ligne 184
- `test_correction_invalidates_current_but_preserves_frozen_run` — ligne 192
- `test_failure_during_application_rolls_back_fixing_and_product` — ligne 218
- `test_reference_feed_uses_atomic_local_copy_before_network` — ligne 240

## backend/tests/test_fixings_releves.py

- `test_une_constatation_moyennee_declare_ses_releves` — ligne 64
- `test_le_dernier_releve_est_la_constatation_elle_meme` — ligne 74
- `test_un_produit_ponctuel_ne_declare_aucun_releve` — ligne 83
- `test_les_fenetres_se_relisent_depuis_l_echeancier_fige` — ligne 91
- `test_un_echeancier_absent_ne_fait_pas_planter_la_relecture` — ligne 107
- `test_le_modele_porte_le_lien_releve_constatation` — ligne 117
- `test_l_api_expose_le_lien_releve_constatation` — ligne 140
- `test_un_releve_ne_porte_pas_de_regle_d_agregation` — ligne 155
- `test_la_fenetre_de_depart_a_ses_releves_bookes_sous_le_strike` — ligne 243
- `test_start_window_booking_checks_http_permissions_and_contract_scope` — ligne 277

## backend/tests/test_garde_fous.py

- `test_un_modele_inconnu_est_refuse` — ligne 46
- `test_parametres_heston_hors_domaine_refuses` — ligne 60
- `test_parametres_sabr_hors_domaine_refuses` — ligne 68
- `test_indice_zero_est_refuse_au_lieu_de_designer_le_dernier_actif` — ligne 75
- `test_poids_de_panier_en_exces_refuses` — ligne 89
- `test_pay_d_un_param_tableau_fonctionne` — ligne 98
- `test_matrice_psd_singuliere_ne_leve_plus_d_erreur_brute` — ligne 112
- `test_reparation_negligeable_est_reportee_et_non_silencieuse` — ligne 119
- `test_reparation_materielle_est_refusee` — ligne 128
- `test_mtf_ne_marque_plus_un_produit_deja_rappele` — ligne 139
- `test_le_vega_heston_declare_sa_couverture` — ligne 190
- `test_le_monitoring_continu_est_signale_comme_approche` — ligne 208

## backend/tests/test_greeks_stateful.py

- `test_barriere_deja_franchie_rend_le_produit_lineaire` — ligne 91
- `test_le_rang_d_observation_choisit_la_bonne_ligne_de_barriere` — ligne 107
- `test_le_niveau_de_reference_de_la_vol_realisee_suit_le_bump` — ligne 139
- `test_le_bump_est_relatif_au_spot_du_jour` — ligne 152
- `test_le_coupon_de_la_semaine_est_isole_du_theta` — ligne 164
- `test_pas_d_evenement_dans_la_semaine_pas_de_decomposition` — ligne 177
- `test_le_compteur_avance_quand_une_observation_est_enjambee` — ligne 186
- `test_theta_absent_plutot_que_faux_sur_un_etat_non_roulable` — ligne 213
- `test_vieillissement_preserve_tous_les_champs_du_script_compile` — ligne 231
- `test_theta_refuse_de_franchir_un_releve_de_fenetre` — ligne 267
- `test_les_unites_des_notes_pdf_sont_preservees` — ligne 296
- `test_le_vega_des_notes_existe_desormais_hors_gbm` — ligne 311
- `test_vega_heston_respecte_la_martingale_du_payoff_lineaire` — ligne 320

## backend/tests/test_hybrid_bootstrap.py

- `test_bootstrap_is_idempotent_and_only_seeds_configuration` — ligne 52
- `test_managed_login_never_offers_simulation_registration` — ligne 68
- `test_reinitialization_observes_revocation_without_restoring_it` — ligne 79
- `test_initialization_refuses_preexisting_data_and_wrong_identity` — ligne 97
- `test_profiles_and_local_admin_are_explicit` — ligne 111
- `test_tokens_reject_foreign_audience_issuer_and_organization` — ligne 125
- `test_local_admin_cannot_grant_technical_role_or_reassign_organization` — ligne 141
- `test_desk_grants_do_not_allow_self_elevation` — ligne 154
- `test_secondary_profiles_cannot_price_or_book_by_calling_functions` — ligne 164
- `test_distributor_seed_has_sales_desk_and_no_banking_policy` — ligne 182
- `test_interrupted_transaction_can_be_initialized_without_duplicate_accounts` — ligne 193
- `test_managed_studies_cannot_read_another_installation` — ligne 213
- `test_foreign_installation_is_refused_before_migration` — ligne 224
- `test_preflight_allows_empty_interrupted_schema_but_not_private_rows` — ligne 241
- `test_managed_preflight_rejects_admin_identity_with_valid_business_bootstrap` — ligne 255
- `test_managed_installation_reinitializes_in_a_fresh_process` — ligne 267

## backend/tests/test_hybrid_development.py

- `test_development_access_is_disabled_by_default` — ligne 18
- `test_central_catalog_and_grants_have_no_private_data` — ligne 28
- `test_redemption_is_local_audited_and_replay_safe` — ligne 51
- `test_grants_reject_wrong_scope_expiry_and_disabled_account` — ligne 70

## backend/tests/test_hybrid_installations.py

- `test_preparation_is_repeatable_and_private` — ligne 15
- `test_managed_environment_does_not_inherit_other_installation` — ligne 29
- `test_openai_key_is_only_forwarded_to_central_campaign_controller` — ligne 40
- `test_prepare_refuses_unidentified_or_protected_data` — ligne 54
- `test_partial_layout_resumes_and_lost_secret_is_not_replaced` — ligne 64
- `test_layout_cannot_redirect_to_other_private_directory` — ligne 76
- `test_central_service_has_no_business_schema_or_routes` — ligne 86
- `test_directory_rejects_private_business_contents` — ligne 113
- `test_central_bootstrap_refuses_an_unidentified_business_database` — ligne 125

## backend/tests/test_hybrid_reset.py

- `test_reset_only_identified_data_preserves_manual_and_unrelated_work` — ligne 45
- `test_changed_inventory_and_tracked_file_are_refused` — ligne 59
- `test_reset_requires_empty_initialized_manual_runtime` — ligne 71
- `test_another_checkout_inside_tmp_is_preserved` — ligne 80
- `test_reset_cannot_leave_repo_or_ignore_an_active_service` — ligne 91

## backend/tests/test_inlife_pricing.py

- `test_sans_date_de_valorisation_on_price_a_l_emission` — ligne 92
- `test_inlife_preserves_continuous_monitoring_policy_and_warning` — ligne 99
- `test_avec_une_date_passee_le_produit_a_une_histoire` — ligne 108
- `test_le_niveau_initial_est_lu_dans_l_historique` — ligne 120
- `test_un_niveau_initial_saisi_l_emporte_sur_l_historique` — ligne 126
- `test_la_memoire_accumulee_entre_dans_la_valeur` — ligne 135
- `test_avant_la_constatation_initiale_le_fixing_est_simule` — ligne 158
- `test_avant_le_strike_l_actualisation_part_de_la_date_de_valorisation` — ligne 182
- `test_avant_le_strike_le_pricer_et_booking_donnent_le_meme_prix` — ligne 198
- `test_la_date_mtm_est_bornee_par_le_trade_et_aujourdhui` — ligne 249
- `test_le_prix_avant_le_strike_bouge_avec_la_volatilite` — ligne 268
- `test_valoriser_apres_la_maturite_est_refuse` — ligne 283
- `test_missing_history_still_blocks_a_product_after_strike` — ligne 290
- `test_sans_historique_un_produit_dependant_du_chemin_est_refuse` — ligne 298
- `test_les_parametres_du_script_ne_sont_pas_de_la_memoire` — ligne 327
- `test_un_produit_a_memoire_garde_la_sienne` — ligne 345
- `test_la_reponse_porte_les_memes_statistiques_que_le_pricing_normal` — ligne 353
- `test_la_courbe_de_dividende_atteint_le_moteur` — ligne 372
- `test_la_courbe_de_taux_atteint_le_moteur` — ligne 388
- `test_les_greeks_se_calculent_sur_la_jambe_residuelle` — ligne 398
- `test_sans_demande_explicite_aucun_greek_n_est_calcule` — ligne 416
- `test_le_funding_fait_BAISSER_le_prix` — ligne 425
- `test_funding_et_taux_agissent_en_sens_OPPOSES` — ligne 437
- `test_le_funding_ne_touche_pas_le_drift` — ligne 454
- `test_le_greek_de_credit_vaut_a_peu_pres_moins_prix_fois_duree` — ligne 466
- `test_le_spread_implicite_retrouve_celui_qui_a_produit_le_prix` — ligne 480
- `test_un_prix_hors_d_atteinte_le_dit_au_lieu_de_converger_a_cote` — ligne 492
- `test_A7_l_horizon_simule_est_la_vie_restante_et_non_le_tenor` — ligne 539
- `test_A7_les_t_du_flux_se_recomptent_depuis_la_valorisation` — ligne 554
- `test_A7_le_passe_se_compte_depuis_le_strike` — ligne 586
- `test_A7_avancer_la_valorisation_deplace_la_frontiere` — ligne 602

## backend/tests/test_input_retention.py

- `test_partial_draft_can_be_retained_completed_and_reopened_without_losing_cells` — ligne 31
- `test_library_labels_old_price_and_paginates_calculations_and_history` — ligne 68
- `test_large_library_materializes_only_the_requested_page` — ligne 94
- `test_calculation_comparison_can_cross_a_page_boundary` — ligne 117
- `test_incomplete_retained_product_cannot_be_booked_using_a_different_complete_receipt` — ligne 130
- `test_non_finite_booking_is_refused_before_hashing_and_leaves_no_partial_product` — ligne 152
- `test_custom_funding_never_masks_the_older_standard_booking_run` — ligne 171

## backend/tests/test_installation_identity_security.py

- `test_password_portal_directory_and_central_session_revocation_without_developer_mode` — ligne 18
- `test_admin_preflight_rejects_foreign_or_unmarked_db_before_any_migration` — ligne 53
- `test_marked_admin_workspace_starts_idempotently_and_retains_revocations` — ligne 77
- `test_central_foreign_identity_is_refused_without_schema_changes` — ligne 99
- `test_additive_session_migration_preserves_accounts_and_is_repeatable` — ligne 110
- `test_legacy_read_only_book_uses_separate_revocation_and_audit_store` — ligne 131

## backend/tests/test_kid_mrm.py

- `test_perte_totale_ne_peut_pas_donner_la_note_la_plus_basse` — ligne 25
- `test_echelle_mrm_monotone` — ligne 46
- `test_un_kid_perte_totale_est_sauvegardable_sans_vev_finie` — ligne 51
- `test_migration_rend_vev_nullable_sur_une_base_existante` — ligne 58
- `test_call_achete_12_double_a_un_tri_de_100_pourcent_sur_un_an` — ligne 95
- `test_perte_integrale_de_la_prime_est_moins_cent_pourcent` — ligne 105
- `test_montant_et_tri_utilisent_exactement_les_memes_flux_nets` — ligne 115
- `test_coupon_annuel_huit_pourcent_garde_un_tri_de_huit_pourcent` — ligne 134
- `test_tri_ambigu_reste_non_calculable_et_ne_devient_pas_une_perte_totale` — ligne 147

## backend/tests/test_lecture_par_date.py

- `test_avancer_puis_compter_les_jours_de_semaine_se_compensent` — ligne 119
- `test_une_fenetre_quotidienne_lit_dix_seances_quel_que_soit_le_jour_de_depart` — ligne 132
- `test_la_derniere_fenetre_garde_tout_son_horizon_dans_l_historique` — ligne 149
- `test_un_releve_sans_cotation_est_reporte_et_signale` — ligne 172
- `test_le_rejeu_officiel_lit_chacun_des_dix_fixings_de_la_fenetre_de_depart` — ligne 190
- `test_deux_fixings_differents_a_la_meme_date_ne_se_departagent_pas_en_silence` — ligne 206
- `test_un_rappel_se_decide_sur_ses_deux_fixings_et_se_date_a_sa_constatation` — ligne 220
- `test_le_remboursement_d_une_maturite_calendaire_se_retrouve` — ligne 235
- `test_la_surveillance_decide_le_rappel_sur_les_cours_de_ses_dates` — ligne 253
- `test_une_constatation_posterieure_a_la_derniere_cloture_reste_a_simuler` — ligne 289

## backend/tests/test_legal_identity_workflows.py

- `test_provider_rename_and_reassignment_never_reassign_historical_quotes` — ligne 17
- `test_unfrozen_quote_requires_explicit_audited_qualification` — ligne 31
- `test_network_mapping_accepts_different_local_name_and_refuses_inactive_id` — ligne 47
- `test_direct_booking_rejects_missing_unknown_or_inconsistent_legal_identity` — ligne 62
- `test_legal_amendment_updates_deal_product_and_keeps_original_snapshot` — ligne 70
- `test_legal_amendment_credit_refusal_has_no_partial_mutation` — ligne 87
- `test_real_credit_limit_blocks_bank_transfer_without_rewriting_contract` — ligne 103
- `test_trailing_space_cannot_bypass_a_real_booking_credit_limit` — ligne 124

## backend/tests/test_lifecycle_alerts.py

- `test_deux_observations_de_rappel_creent_deux_alertes` — ligne 25
- `test_le_ki_garde_une_cle_terminale_independante_des_observations` — ligne 57
- `test_rappel_se_regle_a_sa_date_effective_sans_attendre_la_maturite` — ligne 84

## backend/tests/test_lifecycle_c26.py

- `test_missing_first_underlying_never_becomes_second` — ligne 55
- `test_indexed_extrema_read_the_history` — ligne 65
- `test_all_failed_run_is_failed_and_same_slot_can_retry` — ligne 72
- `test_partial_run_has_explicit_coverage_and_is_retryable` — ligne 83
- `test_missing_member_leaves_basket_and_its_own_extrema_unavailable` — ligne 97
- `test_second_index_stays_available_when_first_is_missing` — ligne 106
- `test_a_hole_or_invalid_price_does_not_publish_an_extremum` — ligne 113
- `test_current_price_respects_c11_source_age` — ligne 122
- `test_no_pre_strike_extremum_or_future_price_is_used` — ligne 129
- `test_pre_strike_spot_is_never_a_since_strike_extremum` — ligne 138
- `test_maximum_includes_the_initial_level_and_keeps_index` — ligne 146
- `test_missing_watchlist_is_failed_even_after_refresh_succeeded` — ligne 153
- `test_unavailable_barrier_is_visible_in_run_coverage` — ligne 164
- `test_rollback_discards_dirty_failed_deal_and_continues` — ligne 173
- `test_settlement_failure_is_per_deal_and_does_not_leave_audit_or_status` — ligne 188
- `test_legacy_false_success_with_errors_can_be_reclaimed` — ligne 205
- `test_successful_alerts_are_deduplicated_on_partial_retry` — ligne 214
- `test_old_worker_cannot_overwrite_a_new_claim` — ligne 234
- `test_future_strike_requires_no_market_call_and_is_expected_pending` — ligne 252
- `test_out_of_range_index_is_unavailable` — ligne 260
- `test_database_flush_failure_is_rolled_back_before_next_deal` — ligne 266
- `test_settlement_wait_and_invalid_date_have_distinct_outcomes` — ligne 281
- `test_current_claim_is_skipped_and_stale_running_claim_can_resume` — ligne 291
- `test_t08_official_correction_updates_watchlist_without_rewriting_previous_result` — ligne 301
- `test_pending_official_version_cannot_fall_back_to_provider_in_watchlist` — ligne 324
- `test_official_fixing_is_newer_than_a_carried_provider_row` — ligne 342
- `test_provider_outage_keeps_the_recent_official_watchlist_level` — ligne 357
- `test_full_watchlist_to_alert_retry_never_crosses_on_the_wrong_constituent` — ligne 369
- `test_missing_initial_level_does_not_shift_the_other_constituent` — ligne 385

## backend/tests/test_lifecycle_fenetres.py

- `test_une_constatation_moyennee_n_est_plus_reputee_dependante_du_chemin` — ligne 48
- `test_une_barriere_americaine_reste_bloquee` — ligne 56
- `test_une_fenetre_sans_fixings_est_signalee` — ligne 65
- `test_une_fenetre_partiellement_fixee_est_signalee_aussi` — ligne 72
- `test_une_fenetre_complete_ne_bloque_rien` — ligne 80
- `test_un_cours_nul_ne_compte_pas_comme_un_fixing` — ligne 86
- `test_un_produit_ponctuel_n_est_pas_concerne` — ligne 96
- `test_un_deal_sans_echeancier_fige_n_est_pas_bloque` — ligne 105
- `test_un_echeancier_illisible_ne_leve_pas` — ligne 112
- `test_l_avertissement_nomme_les_dates_reportees` — ligne 121
- `test_sur_une_moyenne_le_report_ne_renverse_pas_la_decision` — ligne 129
- `test_sur_un_extreme_le_report_peut_renverser_la_decision` — ligne 139
- `test_les_releves_de_la_fenetre_de_depart_sont_verifies_aussi` — ligne 162
- `test_le_report_sur_la_fenetre_de_depart_dit_qu_il_touche_s0` — ligne 173

## backend/tests/test_llm_scripting.py

- `test_missing_maturity_does_not_invent_a_pricing_horizon` — ligne 39
- `test_les_exemples_complementaires_compilent_et_pricent` — ligne 50
- `test_le_prompt_montre_tout_idiome_qu_il_impose` — ligne 61
- `test_la_selection_est_pertinente_et_bornee` — ligne 77
- `test_le_prompt_systeme_porte_la_reference_et_le_contrat_de_sortie` — ligne 88
- `test_le_prompt_utilisateur_transmet_le_contexte_connu` — ligne 100
- `test_le_prompt_de_reparation_porte_l_erreur_exacte` — ligne 107
- `test_les_reponses_decorees_sont_nettoyees` — ligne 122
- `test_l_explication_est_recuperee_quand_elle_existe` — ligne 132
- `test_une_reponse_vide_ne_leve_pas` — ligne 138
- `test_un_bon_script_ne_leve_aucune_alerte` — ligne 165
- `test_un_rappel_sans_stop_est_signale` — ligne 175
- `test_une_barriere_europeenne_la_ou_l_americaine_est_demandee_est_signalee` — ligne 187
- `test_un_coupon_memoire_sans_memoire_est_signale` — ligne 199
- `test_un_parametre_jamais_lu_est_signale` — ligne 215
- `test_un_indice_hors_du_panier_est_signale` — ligne 224
- `test_un_bloc_de_maturite_absent_est_signale` — ligne 230
- `test_un_script_qui_ne_compile_pas_remonte_l_erreur_du_parser` — ligne 236
- `test_un_script_a_constat_ne_declenche_pas_de_pricing` — ligne 244
- `test_une_option_n_est_pas_jugee_comme_une_note` — ligne 255
- `test_ollama_est_le_defaut_et_ne_demande_aucune_cle` — ligne 267
- `test_les_moteurs_sont_annonces_avec_leur_disponibilite` — ligne 275
- `test_un_moteur_inconnu_est_refuse` — ligne 291
- `test_le_selecteur_liste_les_modeles_reellement_installes` — ligne 307
- `test_le_modele_recommande_est_retenu_s_il_est_installe` — ligne 322
- `test_ollama_indisponible_est_annonce_avec_la_marche_a_suivre` — ligne 335
- `test_ollama_models_ne_leve_jamais` — ligne 349
- `test_le_prompt_est_consultable_sans_appeler_de_modele` — ligne 361
- `test_le_prompt_change_avec_la_description` — ligne 376
- `test_compile_pricing_et_avertissements_sont_trois_verdicts_distincts` — ligne 384
- `test_la_provenance_capture_chaque_prompt_reponse_et_modele_effectif` — ligne 396

## backend/tests/test_lot7_operational.py

- `test_bail_refuse_un_result_ancien_et_limite_la_fenetre` — ligne 36
- `test_deux_workers_ne_peuvent_pas_claim_le_meme_batch` — ligne 58
- `test_annulation_executor_termine_les_processus_actifs_rapidement` — ligne 82
- `test_estimation_var_agrege_les_deals_et_scenarios` — ligne 99
- `test_runs_de_valorisation_sont_append_only_et_rejouables` — ligne 114
- `test_scheduler_un_seul_passage_par_creneau` — ligne 165
- `test_reconstruction_schema_en_mode_validation_ne_touche_pas_la_source` — ligne 181
- `test_les_couches_metier_n_importent_aucune_route_api` — ligne 194

## backend/tests/test_market_data_governance.py

- `test_pending_policy_does_not_qualify_carried_prices_or_fx` — ligne 53
- `test_approved_policy_accepts_day_three_and_excludes_day_four` — ligne 63
- `test_sixty_day_suspension_is_excluded_instead_of_zero_returns` — ligne 73
- `test_long_interior_halt_cannot_be_compressed_into_daily_return` — ligne 83
- `test_closed_market_carry_is_bounded_and_source_dates_are_visible` — ligne 91
- `test_leading_missing_prices_are_trimmed_without_backfill` — ligne 103
- `test_missing_asset_requires_explicit_exploratory_reduction` — ligne 111
- `test_durable_local_replay_needs_no_network_and_caches_are_defensive` — ligne 121
- `test_amc_storage_supplies_the_correct_raw_and_adjusted_basis_offline` — ligne 134
- `test_adjusted_only_storage_is_not_reported_usable_for_contract_replay` — ligne 146
- `test_dated_and_current_vol_use_the_same_declared_common_sample` — ligne 154
- `test_fx_quote_retains_date_and_age_but_excludes_old_or_future_rate` — ligne 170
- `test_provenance_cannot_replace_the_actual_validated_engine_values` — ligne 184
- `test_invalid_provenance_is_rejected` — ligne 194
- `test_legacy_underlying_does_not_gain_a_null_provenance_key` — ligne 199
- `test_reference_override_and_exact_value_survive_receipt_product_and_reopen` — ligne 203
- `test_reinvest_unknown_dividend_does_not_call_solver` — ligne 229
- `test_admin_fetch_populates_the_stores_consumers_replay_offline` — ligne 238
- `test_old_fx_excludes_exposure_and_does_not_clear_a_counterparty_limit` — ligne 255
- `test_dividend_profile_reuses_saved_observations_before_requesting_cash_events` — ligne 274
- `test_full_backtest_refuses_missing_asset_but_comparison_records_reduction` — ligne 285
- `test_backtest_correlation_uses_common_estimator_without_rounding` — ligne 301
- `test_more_complete_amc_stock_precedes_refetch_when_shared_copy_is_partial` — ligne 310

## backend/tests/test_market_data_lot4.py

- `test_recalibration_uses_adjusted_history_but_contract_replay_stays_raw` — ligne 60
- `test_replay_uses_the_booked_s0_as_its_unit` — ligne 94
- `test_known_maturity_cashflow_is_valued_until_payment_and_kept_in_var` — ligne 109
- `test_settlement_window_closes_on_the_payment_date` — ligne 147

## backend/tests/test_market_snapshot_rate.py

- `test_snapshot_rate_honours_the_booked_value` — ligne 43
- `test_snapshot_rate_falls_back_only_when_the_key_is_absent` — ligne 47
- `test_snapshot_rate_is_default_distinguishes_a_substitution` — ligne 54
- `test_snapshot_rate_refuses_an_unreadable_value` — ligne 62
- `test_no_call_site_reintroduces_the_or_fallback` — ligne 69
- `test_zero_rate_deal_is_not_discounted` — ligne 153
- `test_mtm_preserves_the_booked_continuous_monitoring_policy` — ligne 165
- `test_three_percent_deal_still_discounts` — ligne 180
- `test_zero_and_three_percent_no_longer_price_identically` — ligne 196
- `test_legacy_snapshot_without_rate_is_flagged` — ligne 208
- `test_marche_actuel_rafraichit_le_niveau_de_dividende_et_garde_le_decay` — ligne 225

## backend/tests/test_market_storage_integrity.py

- `test_invalid_import_keeps_the_entire_series_mapping_and_manifest` — ligne 73
- `test_missing_convention_is_rejected_before_replacement` — ligne 84
- `test_optional_raw_prices_require_explicit_share_unit_date` — ligne 90
- `test_raw_only_import_is_not_mislabelled_as_a_total_return_series` — ligne 98
- `test_duplicate_json_object_keys_cannot_hide_duplicate_dates` — ligne 103
- `test_excel_import_rejects_bad_rows_without_trimming_them` — ligne 110
- `test_lossy_long_or_case_variant_keys_do_not_collide` — ligne 116
- `test_legacy_ambiguous_slug_is_not_adopted_for_another_name` — ligne 125
- `test_unambiguous_legacy_name_is_readable_without_rewriting_it` — ligne 134
- `test_failed_download_changes_neither_series_nor_instrument_association` — ligne 145
- `test_unknown_provider_currency_cannot_publish_a_partial_download` — ligne 154
- `test_write_failure_keeps_old_amc_shared_bases_and_mapping` — ligne 161
- `test_one_commit_exposes_both_bases_and_mapping_together` — ligne 181
- `test_process_crash_before_publish_leaves_previous_generation_readable` — ligne 195
- `test_concurrent_raw_history_merges_do_not_lose_observations` — ligne 211
- `test_concurrent_instrument_commits_do_not_lose_map_entries` — ligne 222
- `test_shared_history_rejects_duplicate_and_nonfinite_input_before_replacing` — ligne 228
- `test_nested_response_mutation_and_simultaneous_cache_hits_are_independent` — ligne 235
- `test_identical_concurrent_misses_share_one_provider_call` — ligne 248
- `test_storage_update_invalidates_memory_before_ttl_and_old_view_cannot_poison_new` — ligne 264
- `test_fx_cache_write_failure_returns_old_cache_and_does_not_truncate_it` — ligne 273
- `test_http_import_requires_admin_and_preserves_old_series_on_rejection` — ligne 285
- `test_late_download_cannot_overwrite_a_more_recent_instrument_replacement` — ligne 305
- `test_late_read_and_cache_clear_cannot_republish_old_observations` — ligne 320
- `test_cross_process_writers_share_the_same_commit_lock` — ligne 339
- `test_failed_publish_preserves_legacy_files_without_a_migration` — ligne 366
- `test_corrupted_mapping_is_not_silently_replaced_by_an_empty_map` — ligne 376
- `test_cached_response_is_isolated_between_runtime_data_roots` — ligne 382
- `test_T04_calendar_freshness_failed_import_and_offline_recovery` — ligne 392
- `test_historical_campaign_reader_resolves_committed_series_and_ticker_map` — ligne 415
- `test_reference_installer_uses_only_the_explicit_target_store` — ligne 430
- `test_reference_installer_aborts_whole_batch_on_collision` — ligne 444
- `test_copy_to_another_data_directory_preserves_committed_references` — ligne 455

## backend/tests/test_mtf_audit_2026_08_03.py

- `test_partition_des_dates_sans_recouvrement` — ligne 102
- `test_pas_de_double_comptage_dans_la_fenetre_d_arrondi` — ligne 120
- `test_tour_sur_autocall_a_toutes_les_dates` — ligne 134
- `test_strike_fix_realise_conserve_en_mtf` — ligne 174
- `test_fenetre_de_fixing_entierement_passee_ne_revient_pas_au_neutre` — ligne 188
- `test_quantiles_standards_et_strictement_ordonnes` — ligne 203
- `test_date_de_mark_sous_un_demi_pas_refusee` — ligne 223
- `test_grille_de_dates_strictement_croissante_sur_produit_ultra_court` — ligne 234
- `test_courbe_et_taux_stochastiques_refuses_au_lieu_d_etre_ignores` — ligne 243
- `test_endpoint_mtf_transmet_courbe_et_sigma_r` — ligne 259
- `test_toutes_les_statistiques_portent_sur_les_survivants` — ligne 270

## backend/tests/test_mtf_drilldown.py

- `test_le_mark_du_panneau_est_celui_de_l_eventail` — ligne 112
- `test_la_somme_des_va_reconstruit_le_mark` — ligne 133
- `test_la_trajectoire_expliquee_est_celle_de_l_eventail` — ligne 154
- `test_contrat_eteint_marque_a_zero_et_sans_flux` — ligne 179
- `test_le_payoff_final_est_celui_de_la_trajectoire_et_non_une_esperance` — ligne 199
- `test_observations_statut_et_coherence_du_rappel` — ligne 218
- `test_barrieres_detectees_sans_confondre_coupon_et_niveau` — ligne 239
- `test_panier_trois_actifs_series_par_sous_jacent_et_observable_distingue` — ligne 254
- `test_date_hors_grille_refusee` — ligne 310
- `test_scenario_hors_bornes_refuse` — ligne 319
- `test_trop_de_scenarios_refuse` — ligne 327
- `test_memes_refus_que_l_eventail` — ligne 335
- `test_doublons_de_scenarios_dedupliques` — ligne 350
- `test_esperances_conditionnelles_recalculables` — ligne 361
- `test_esperance_totale_est_la_moyenne_ponderee_des_deux_conditionnelles` — ligne 393

## backend/tests/test_mtf_fenetres.py

- `test_le_mark_d_une_fenetre_a_cheval_compte_les_releves_deja_constates` — ligne 56
- `test_le_mtm_d_une_fenetre_a_cheval_compte_les_releves_deja_constates` — ligne 137
- `test_le_mark_to_future_d_un_deal_vivant_repart_de_son_etat_rejoue` — ligne 151
- `test_la_vol_realisee_se_raccorde_a_la_date_de_marque` — ligne 178
- `test_le_drill_down_explique_le_meme_mark_que_l_eventail` — ligne 214
- `test_le_worker_de_var_reprice_la_meme_fenetre_que_le_mtm` — ligne 229
- `test_la_grille_de_stress_reprice_la_meme_fenetre_que_le_mtm` — ligne 252

## backend/tests/test_mtm_explain.py

- `test_explain_flat_market_only_time_effect` — ligne 90
- `test_explain_spot_ramp_spot_effect_dominates` — ligne 103
- `test_explain_chain_telescopes_exactly` — ligne 128
- `test_explain_guards` — ligne 137
- `test_explain_phrases_present` — ligne 155
- `test_payloads_are_json_serializable` — ligne 164
- `test_explain_report_returns_pdf` — ligne 208
- `test_residual_greeks_sane` — ligne 227

## backend/tests/test_optimizer_c20.py

- `test_every_offered_mode_is_saved_started_and_retained` — ligne 29
- `test_financeable_rc_four_years_is_resolved_and_independently_confirmed` — ligne 51
- `test_last_calculation_overrun_is_always_explicit_partial` — ligne 69
- `test_rounded_parameter_is_repriced_without_trusting_solver_success` — ligne 103
- `test_budget_overrun_is_retained_as_partial_by_background_research` — ligne 115
- `test_coupon_entitlement_uses_the_contractual_stop_date_between_grid_nodes` — ligne 136

## backend/tests/test_optimizer_researches.py

- `test_saved_request_summary_market_and_prices_survive_client_disconnection` — ligne 60
- `test_retry_is_idempotent_and_changed_request_is_rejected` — ligne 74
- `test_ownership_archive_filters_and_linked_new_version` — ligne 83
- `test_background_cancel_keeps_partial_prices_and_shared_admission` — ligne 102
- `test_error_keeps_received_prices_and_releases_capacity` — ligne 120
- `test_restart_marks_unfinished_job_and_frozen_evidence_cannot_be_rewritten` — ligne 133
- `test_real_parallel_pricings_are_saved_by_detached_background_job` — ligne 149

## backend/tests/test_parser.py

- `test_parse_vanilla` — ligne 53
- `test_parse_api_exposes_reserved_maturity_event` — ligne 62
- `test_parse_api_exposes_literal_observation_dates` — ligne 68
- `test_parse_autocall` — ligne 80
- `test_parse_range_accrual` — ligne 90
- `test_params_pct_detection` — ligne 98
- `test_constat_single` — ligne 105
- `test_constat_schedule` — ligne 112
- `test_constat_nested_schedule` — ligne 119
- `test_constat_mixed_with_params_and_multiple_kinds` — ligne 126
- `test_no_constat_gives_empty_list` — ligne 143
- `test_param_description_quoted_form` — ligne 148
- `test_param_description_comment_form` — ligne 153
- `test_param_description_falls_back_to_name` — ligne 161
- `test_events_callable` — ligne 166
- `test_at_maturity_payoff` — ligne 187
- `test_at_maturity_otm` — ligne 206
- `test_invalid_body_raises` — ligne 226
- `test_typo_in_param_reference_raises` — ligne 231
- `test_set_variable_reference_does_not_raise` — ligne 239
- `test_at_recognizes_declared_constat_name` — ligne 249
- `test_at_literal_dates_unaffected_by_constat_presence` — ligne 256
- `test_resolve_constats_noop_without_constat_ref` — ligne 264
- `test_resolve_constats_unknown_name_raises` — ligne 270
- `test_resolve_constats_single` — ligne 276
- `test_resolve_constats_schedule_excludes_start_date` — ligne 288
- `test_resolve_constats_nested_schedule_sub_frequency` — ligne 306
- `test_at_qualifier_parsing_first_last_index` — ligne 330
- `test_qualifier_first_resolves_to_first_date` — ligne 345
- `test_qualifier_last_resolves_to_last_date` — ligne 354
- `test_qualifier_index_is_one_indexed` — ligne 363
- `test_unqualified_block_is_additive_with_qualified_blocks` — ligne 372
- `test_qualifier_index_out_of_range_raises` — ligne 390
- `test_qualifier_on_single_constat_raises` — ligne 397
- `test_effective_t_max_noop_when_dates_fit` — ligne 405
- `test_effective_t_max_extends_for_literal_dates_beyond_requested_T` — ligne 413
- `test_effective_t_max_extends_for_resolved_constat_dates` — ligne 420
- `test_effective_t_max_ignores_at_maturity_event` — ligne 435
- `test_resolve_constats_missing_field_raises` — ligne 442
- `test_at_date_zero_or_negative_rejected` — ligne 453
- `test_param_array_declaration` — ligne 499
- `test_parameter_without_default_requires_economics_value` — ligne 508
- `test_param_array_per_observation_resolution` — ligne 519
- `test_param_array_last_row_extends` — ligne 531
- `test_param_array_scalar_passthrough` — ligne 542
- `test_param_array_maturity_uses_last_relevant_row` — ligne 549
- `test_monitors_direction_from_usage` — ligne 561
- `test_monitors_reversed_comparison_and_other_observables` — ligne 568
- `test_monitors_ambiguous_usage_is_neutral` — ligne 587
- `test_monitors_unused_m_param_has_no_direction` — ligne 600

## backend/tests/test_payoff_families.py

- `test_legacy_labels_group_into_one_primary_family` — ligne 10
- `test_new_values_are_canonical_and_other_has_a_description` — ligne 20
- `test_catalogue_names_and_aliases_are_unambiguous` — ligne 29

## backend/tests/test_payoff_qualification.py

- `test_unexpected_indent_never_discards_an_instruction` — ligne 19
- `test_empty_blocks_tabs_and_bad_dedents_are_explicit_errors` — ligne 38
- `test_valid_coupon_is_paid_and_stop_cancels_maturity_flows` — ligne 43
- `test_all_approved_sources_pass_independent_cashflow_panels` — ligne 54
- `test_memory_panel_has_known_missed_catchup_reset_unpaid_and_recall_cashflows` — ligne 67
- `test_economic_change_invalidates_source_approval_even_with_identical_declarations` — ligne 78
- `test_modified_athena_is_refused_by_request_and_existing_candidate` — ligne 93
- `test_diagnostic_requires_compiled_and_input_identity` — ligne 106
- `test_source_proof_normalization_is_narrow_and_cache_cannot_be_mutated` — ligne 121
- `test_reference_failure_cannot_keep_a_green_approval` — ligne 130
- `test_nonfinite_reference_price_is_never_qualified` — ligne 139
- `test_assistant_does_not_qualify_unused_or_missing_memory` — ligne 155
- `test_assistant_recognizes_only_the_tested_memory_source` — ligne 163

## backend/tests/test_payscript_acceptance.py

- `test_all_nineteen_payoffs_against_independent_redemption` — ligne 90
- `test_coupon_memory_catches_up_exactly_once` — ligne 98
- `test_final_date_recall_does_not_also_pay_terminal_capital` — ligne 105
- `test_inter_observation_breach_distinguishes_european_and_american` — ligne 115
- `test_mc_cash_legs_reconcile_to_price_and_independent_redemption` — ligne 123
- `test_explicit_basket_contract_reaches_actual_ccr_engine` — ligne 134
- `test_solver_and_grid_inject_their_candidates_into_required_parameters` — ligne 149
- `test_terminal_window_does_not_read_a_fixing_after_its_observation` — ligne 167
- `test_terminal_average_includes_its_contractual_last_fixing` — ligne 174
- `test_one_day_window_on_closed_day_keeps_one_fixing` — ligne 184

## backend/tests/test_payscript_binding.py

- `test_fixing_is_separate_from_coupon_rank_and_first_observation_is_included` — ligne 40
- `test_missing_parameter_fails_in_engine_instead_of_defaulting_to_zero` — ligne 51
- `test_mc_recall_or_maturity_has_distinct_cash_legs` — ligne 59
- `test_explicit_raw_default_and_required_array_are_distinct` — ligne 74
- `test_history_uses_individual_initial_levels` — ligne 81
- `test_unsupported_property_or_future_reference_fails` — ligne 92
- `test_generic_draft_does_not_invent_economics` — ligne 97
- `test_frozen_calendar_binds_the_payoff_version_and_preserves_initial_fixing` — ligne 106
- `test_basket_observables_use_contractual_order_and_units` — ligne 123
- `test_raw_levels_are_carried_from_initial_window_into_mc` — ligne 132
- `test_initial_date_conflicts_and_observation_at_strike_are_rejected` — ligne 145
- `test_pricing_api_returns_actionable_error_for_missing_economics` — ligne 154
- `test_conditional_alias_does_not_misclassify_the_observable` — ligne 168
- `test_explicit_fixing_and_put_survive_residual_pricing` — ligne 175
- `test_reinvestment_moves_initial_and_observation_dates_together` — ligne 193
- `test_reinvestment_risk_flags_use_booked_values_of_required_parameters` — ligne 221

## backend/tests/test_payscript_presets.py

- `test_forward_start_examples_price_without_historical_data` — ligne 25
- `test_examples_match_scripts_and_survive_calendar_roundtrip` — ligne 88
- `test_autocall_3y_separates_coupon_capital_and_put` — ligne 117
- `test_phoenix_memory_coupon_is_per_quarter_and_catches_up` — ligne 128
- `test_stepdown_example_uses_the_third_barrier_and_three_coupons` — ligne 134

## backend/tests/test_payscript_reference.py

- `test_la_reference_existe_et_est_lisible` — ligne 48
- `test_tout_mot_du_langage_est_documente` — ligne 53
- `test_la_reference_n_invente_rien` — ligne 61
- `test_le_vocabulaire_couvre_les_categories_attendues` — ligne 70
- `test_les_tables_du_module_alimentent_vraiment_le_transpileur` — ligne 84
- `test_un_param_ne_peut_pas_porter_un_nom_du_langage` — ligne 97
- `test_stop_commente_reste_un_rappel` — ligne 122
- `test_chaque_variable_de_marche_compile` — ligne 140
- `test_chaque_variable_indicee_compile` — ligne 147
- `test_chaque_fonction_compile` — ligne 153
- `test_chaque_mot_logique_compile` — ligne 160
- `test_les_trois_formes_de_basket_compilent` — ligne 166
- `test_l_exemple_commente_de_la_reference_parse` — ligne 171
- `test_tous_les_blocs_de_code_de_la_reference_sont_valides` — ligne 189

## backend/tests/test_payscript_templates.py

- `test_le_corpus_est_synchrone_avec_le_frontend` — ligne 28
- `test_le_corpus_n_est_pas_vide_et_couvre_les_familles` — ligne 43
- `test_chaque_exemple_compile` — ligne 52
- `test_chaque_exemple_price` — ligne 60
- `test_les_exemples_avec_rappel_declarent_leur_rappel` — ligne 79
- `test_le_corpus_illustre_les_idiomes_cles_du_prompt` — ligne 89

## backend/tests/test_pnl_c22.py

- `test_coupon_cash_uses_payment_day_and_reconciles` — ligne 63
- `test_portfolio_cash_and_mtm_have_one_position_sign` — ligne 78
- `test_only_q_change_has_dividend_effect_and_no_vega` — ligne 101
- `test_portfolio_keeps_dividend_contribution` — ligne 113
- `test_frozen_comparison_rolls_receivables_with_realized_state_without_false_jump` — ligne 136
- `test_realized_coupon_memory_moves_with_calendar` — ligne 156
- `test_equal_pay_legs_are_not_deduplicated` — ligne 167
- `test_negative_contractual_cash_is_preserved` — ligne 175
- `test_frozen_dividends_do_not_change_diffusion_bucket` — ligne 184
- `test_portfolio_uses_prices_before_rounding_points` — ligne 203
- `test_unknown_payment_or_amount_does_not_become_observation_cash` — ligne 217
- `test_official_correction_changes_new_cash_but_not_archived_explain` — ligne 223

## backend/tests/test_portal_account_start.py

- `test_explicit_open_starts_only_the_selected_installation_before_grant` — ligne 35
- `test_grant_without_explicit_start_keeps_existing_non_starting_contract` — ligne 51
- `test_no_service_start_before_access_and_profile_checks` — ligne 62
- `test_unavailable_service_returns_french_error_without_grant` — ligne 68
- `test_directory_divergence_cannot_start_a_different_local_manifest` — ligne 81
- `test_return_url_is_public_and_only_advertised_in_development` — ligne 91

## backend/tests/test_portfolio_barriers.py

- `test_portfolio_barriers_without_a_business_role_remains_denied` — ligne 27
- `test_portfolio_barriers_ranks_by_urgency_and_counts_severity` — ligne 98
- `test_barriers_global_spans_portfolios` — ligne 135
- `test_barriers_deal_with_no_monitored_params_is_excluded` — ligne 154
- `test_barriers_bucket_unexpected_failure_without_aborting_book` — ligne 171
- `test_barriers_are_listed_before_the_strike_has_happened` — ligne 200

## backend/tests/test_portfolio_corr_greek.py

- `test_corr_pairs_bucket_same_underlying_pair_regardless_of_order` — ligne 48
- `test_corr_pairs_distinct_pairs_stay_separate` — ligne 80
- `test_deal_with_no_basket_has_no_corr_contribution` — ligne 101
- `test_vegas_de_perimetres_differents_ne_sont_pas_additionnes` — ligne 120
- `test_un_run_greeks_d_une_ancienne_version_est_exclu` — ligne 148
- `test_un_cache_legacy_sans_version_est_exclu_apres_amendement` — ligne 172

## backend/tests/test_portfolio_pnl.py

- `test_portfolio_pnl_aggregates_spot_ramp` — ligne 78
- `test_portfolio_pnl_skips_unexplainable_deal` — ligne 124
- `test_global_pnl_spans_portfolios` — ligne 157

## backend/tests/test_portfolios_crud.py

- `test_portfolio_count_uses_the_live_risk_perimeter` — ligne 13
- `test_legacy_pointer_is_backfilled_once_and_default_lock_is_retired` — ligne 30
- `test_admin_lists_every_owners_portfolios_while_user_stays_scoped` — ligne 54
- `test_admin_assigns_a_deal_only_to_a_portfolio_of_its_owner` — ligne 70
- `test_same_deal_can_belong_to_multiple_portfolios` — ligne 107
- `test_admin_deletes_portfolio_without_deleting_deal_or_other_membership` — ligne 137
- `test_admin_creates_a_portfolio_for_the_selected_account` — ligne 162

## backend/tests/test_position_sign.py

- `test_convention_de_signe` — ligne 63
- `test_un_sens_inconnu_leve_plutot_que_de_choisir` — ligne 71
- `test_long_et_short_identiques_donnent_un_risque_nul` — ligne 80
- `test_une_position_vendue_inverse_ses_sensibilites` — ligne 107

## backend/tests/test_prestrike_mtm.py

- `test_avant_le_strike_les_constatations_reculent_de_l_ecart_au_strike` — ligne 109
- `test_avant_le_strike_rien_n_est_realise` — ligne 127
- `test_un_stock_absent_ne_bloque_plus_avant_le_strike` — ligne 142
- `test_apres_le_strike_le_regime_ordinaire_est_intact` — ligne 151
- `test_le_prix_pre_strike_bouge_avec_la_volatilite` — ligne 174
- `test_sous_vol_constante_le_fixing_diffuse_ne_change_pas_le_prix` — ligne 183
- `test_sous_vol_locale_la_dispersion_du_fixing_compte` — ligne 193
- `test_sans_dynamique_de_smile_le_delta_est_nul` — ligne 216
- `test_sous_dupire_le_delta_de_smile_existe_et_suit_le_skew` — ligne 229
- `test_un_choc_de_spot_avant_le_strike_ne_met_pas_le_produit_hors_de_la_monnaie` — ligne 240
- `test_le_delta_pre_strike_n_est_pas_le_delta_directionnel` — ligne 261

## backend/tests/test_pricing_anchor.py

- `test_anchor_moves_the_effective_horizon_and_the_price` — ligne 39
- `test_anchor_defaults_to_today` — ligne 51
- `test_scenario_grid_carries_the_anchor_to_its_workers` — ligne 58

## backend/tests/test_pricing_validation_lot5.py

- `test_pricing_route_refuses_anonymous_access` — ligne 27
- `test_noeud_de_courbe_malforme_retourne_422` — ligne 34
- `test_matrice_de_correlation_malformee_est_refusee` — ligne 44
- `test_reparation_correlation_et_approximation_barriere_traversent_api` — ligne 50

## backend/tests/test_product_analysis.py

- `test_l_apercu_est_exactement_ce_qui_part` — ligne 76
- `test_l_apercu_n_appelle_pas_le_modele` — ligne 96
- `test_le_resume_part_tel_quel_sans_reconstruction` — ligne 110
- `test_le_cadre_porte_ses_garde_fous` — ligne 130
- `test_toute_intention_herite_du_cadre` — ligne 134
- `test_la_restructuration_vise_la_reprise_de_valeur` — ligne 142
- `test_les_demandes_impossibles_sont_refusees` — ligne 162
- `test_l_api_refuse_en_422_pas_en_500` — ligne 173
- `test_une_precision_ne_remplace_pas_l_intention` — ligne 179
- `test_la_question_libre_remplace_bien_la_consigne` — ligne 187
- `test_l_avis_arrive_avec_sa_provenance` — ligne 199
- `test_les_intentions_exposees_sont_celles_qui_existent` — ligne 213
- `test_analysis_routes_require_authentication` — ligne 243
- `test_analysis_routes_refuse_secondary_profiles` — ligne 256
- `test_authorized_analysis_http_preserves_preview_and_provenance` — ligne 264
- `test_analysis_checks_current_user_state_after_token_issuance` — ligne 301

## backend/tests/test_product_catalogue.py

- `test_la_copie_serveur_est_synchrone_avec_le_catalogue` — ligne 65
- `test_le_catalogue_couvre_les_familles_et_les_tenors_m9` — ligne 76
- `test_chaque_fiche_est_generique_et_bornee` — ligne 83
- `test_chaque_fiche_compile_et_declare_ses_roles` — ligne 98
- `test_chaque_fiche_price_sur_un_calendrier_genere` — ligne 123
- `test_le_calendrier_genere_part_du_strike_et_finit_a_maturite` — ligne 149

## backend/tests/test_product_optimizer.py

- `test_unsupported_inputs_are_rejected` — ligne 48
- `test_ranges_are_bounded_finite_ordered` — ligne 54
- `test_decimal_grid_and_count_have_same_endpoints` — ligne 59
- `test_market_date_currency_duplicates_and_correlation_are_not_guessed` — ligne 66
- `test_registry_is_explicit_and_not_shared_mutable_state` — ligne 82
- `test_estimate_caps_work_before_generation_or_pricing` — ligne 90
- `test_generator_prunes_invalid_economics_and_stub` — ligne 102
- `test_calendar_and_coupon_unit_reuse_catalogue` — ligne 110
- `test_filter_uses_uncertainty_bounds_not_only_point_estimates` — ligne 138
- `test_missing_analytics_never_pass_and_target_coupon_is_enforced` — ligne 145
- `test_ranking_and_pareto_are_deterministic` — ligne 155
- `test_one_failure_does_not_stop_search_or_leak_exception` — ligne 166
- `test_time_budget_returns_explicit_partial_scope` — ligne 184
- `test_real_coupon_solver_and_reprice_are_deterministic` — ligne 192
- `test_athena_flat_path_early_call_and_final_call_are_distinct` — ligne 203
- `test_real_worst_of_basket_is_supported` — ligne 218
- `test_manual_dividend_assumption_reaches_pricing_and_changes_value` — ligne 229
- `test_catalogue_payoff_capital_loss_and_protection_branches` — ligne 243
- `test_api_authentication_validation_and_catalogue` — ligne 277
- `test_api_runs_are_ephemeral_user_isolated_and_capacity_is_released` — ligne 291
- `test_api_stream_error_releases_capacity` — ligne 311

## backend/tests/test_product_optimizer_market.py

- `test_market_contract_refuses_ambiguous_or_invalid_terms` — ligne 35
- `test_dividend_curve_requires_matching_first_year_and_declining_buckets` — ligne 41
- `test_snapshot_keeps_reference_override_date_and_hash` — ligne 46
- `test_reference_contract_rejects_future_unknown_and_incomplete_import` — ligne 65
- `test_currency_change_does_not_relabel_imported_rates_as_another_currency` — ligne 74
- `test_reference_shapes_match_the_financial_field` — ligne 81
- `test_funding_changes_pv_without_changing_diffusion_or_cash_flows` — ligne 93
- `test_curves_reach_solver_reprice_and_independent_holdout` — ligne 104
- `test_rate_curve_changes_the_engine_result_not_only_the_payload` — ligne 115
- `test_dividend_curve_changes_terminal_redemption` — ligne 123
- `test_costs_reduce_resolved_coupon_but_loss_is_measured_against_gross_issue` — ligne 136
- `test_zero_cost_defaults_reproduce_legacy_resolution` — ligne 153
- `test_snapshot_is_isolated_after_started_event` — ligne 159
- `test_api_exports_pricer_origin_net_budget_and_full_snapshot` — ligne 172
- `test_spawned_workers_preserve_curves_references_and_net_budget` — ligne 183

## backend/tests/test_product_optimizer_parallel.py

- `test_parallel_worker_count_is_bounded` — ligne 29
- `test_estimate_accounts_for_concurrent_memory_and_cpu` — ligne 34
- `test_parallelism_is_reduced_before_memory_budget_refusal` — ligne 48
- `test_holdout_peak_exceeding_memory_cap_is_refused_even_sequentially` — ligne 59
- `test_spawned_optimizer_matches_sequential_economics_and_ranking` — ligne 70
- `test_out_of_order_process_failure_is_sanitized_and_results_are_sorted` — ligne 80
- `test_closing_stream_signals_cancellation_and_joins_coordinator` — ligne 93
- `test_expired_parallel_search_has_no_false_failed_candidates` — ligne 111
- `test_cancelling_real_process_pool_leaves_no_owned_children` — ligne 127
- `test_cancelling_real_holdout_process_pool_leaves_no_owned_children` — ligne 137
- `test_api_parallel_stream_exposes_budget_and_releases_capacity` — ligne 151

## backend/tests/test_product_optimizer_participation.py

- `test_protected_capital_and_participation_above_strike` — ligne 36
- `test_booster_cap_is_redemption_level_and_downside_is_one_for_one` — ligne 41
- `test_geared_put_is_european_and_loss_cannot_exceed_capital` — ligne 46
- `test_gear_coupon_is_same_at_early_and_late_recall_without_athena_cumulation` — ligne 50
- `test_gearing_and_put_strike_affect_solved_coupon_and_loss_on_common_paths` — ligne 55
- `test_real_solver_holdout_freezes_quantity_and_roundtrips_contract` — ligne 68
- `test_protected_participation_price_matches_independent_black_scholes` — ligne 86
- `test_flat_booster_price_selects_upper_bound_and_diagnostic_does_not_claim_ranking` — ligne 102
- `test_unfinanceable_protected_nominal_is_skipped_without_fake_participation` — ligne 113
- `test_severity_excludes_coupon_and_respects_independent_pair_order` — ligne 119
- `test_capital_loss_label_change_requires_adapter_requalification` — ligne 131
- `test_inapplicable_fields_and_objectives_are_rejected` — ligne 139
- `test_new_quantity_and_fields_match_spawned_process_results` — ligne 149

## backend/tests/test_product_optimizer_payoffs.py

- `test_frontend_schema_fixture_tracks_current_server_scripts` — ligne 21
- `test_schema_matches_exact_script_and_pricing_parameters` — ligne 44
- `test_script_changes_require_qualification_instead_of_hidden_unbound_fields` — ligne 56
- `test_coupon_label_changes_do_not_silently_produce_zero_coupon_analytics` — ligne 64
- `test_inapplicable_or_missing_fields_are_rejected_by_api_contract` — ligne 76
- `test_coupon_before_simultaneous_recall_and_stop_prevent_later_flows` — ligne 108
- `test_memory_catchup_reset_and_remaining_unpaid_at_maturity` — ligne 114
- `test_coupon_barrier_boundary_and_no_automatic_call` — ligne 127
- `test_step_down_schedule_is_generated_and_changes_recall` — ligne 133
- `test_reverse_convertible_has_single_coupon_protection_and_loss` — ligne 143
- `test_real_solver_holdout_and_coupon_diagnostic_under_curves_and_costs` — ligne 153
- `test_coupon_barrier_and_memory_have_real_price_effects_on_common_paths` — ligne 166
- `test_two_asset_worst_of_resolves_with_all_fields_effectively_bound` — ligne 178
- `test_multi_date_coupons_and_contract_stop_drive_analytics` — ligne 188
- `test_optional_flow_labels_preserve_shared_engine_price_and_pair_order` — ligne 204
- `test_phoenix_grid_count_includes_coupon_barrier_and_api_exposes_script` — ligne 215
- `test_new_families_match_real_spawned_process_results` — ligne 224

## backend/tests/test_product_optimizer_validation.py

- `test_antithetic_metrics_use_both_legs_and_pair_variance` — ligne 14
- `test_bounded_intervals_do_not_claim_zero_risk_after_no_observed_loss` — ligne 27
- `test_holdout_keeps_coupon_uses_new_seeds_and_final_sample` — ligne 42
- `test_holdout_can_reject_an_exploration_winner_without_resolving_coupon` — ligne 60
- `test_incompatible_independent_samples_prevent_confirmation` — ligne 68
- `test_zero_observed_loss_still_fails_a_zero_risk_cap` — ligne 76
- `test_validation_failure_is_private_and_never_recommended` — ligne 83
- `test_coupon_diagnostic_is_independent_uncertainty_and_does_not_change_quote` — ligne 92
- `test_coupon_rank_diagnostic_reports_separation_or_overlap` — ligne 112
- `test_shortlist_is_frozen_no_refill_and_unvalidated_candidates_are_unranked` — ligne 132
- `test_deadline_between_phases_never_recommends_pending_candidates` — ligne 153
- `test_real_independent_holdout_is_finite_reproducible_and_uses_pairs` — ligne 166
- `test_exact_date_reference_reproduces_closed_form_single_observation` — ligne 182

## backend/tests/test_product_optimizer_workflow.py

- `test_automatic_reference_uses_requested_date_effective_close_and_basket_order` — ligne 40
- `test_missing_data_is_not_zero_or_generic_defaults` — ligne 54
- `test_future_references_are_never_used_and_suspect_dividends_remain_visible` — ligne 64
- `test_automatic_endpoint_uses_its_own_catalogue_selection` — ligne 73
- `test_historical_pricing_date_and_issuance_date_roles_are_explicit` — ligne 85
- `test_existing_catalogue_migration_is_additive_and_idempotent` — ligne 94
- `test_catalogue_type_overrides_the_form_and_invalid_classification_is_rejected` — ligne 105
- `test_screenshot_135_structures_are_admitted_without_changing_paths_or_grid` — ligne 126
- `test_contractually_excluded_candidates_are_counted_before_any_pricing` — ligne 139
- `test_manual_stop_keeps_already_confirmed_candidates` — ligne 145
- `test_cancellation_token_is_owned_and_cleaned_even_on_initialization_error` — ligne 163
- `test_risk_failure_distinguishes_central_excess_from_uncertainty` — ligne 194

## backend/tests/test_product_transition_integrity.py

- `test_product_to_rfq_inherits_sell_nominal_and_commercial_context` — ligne 60
- `test_old_rfq_sync_never_regresses_terms_or_overwrites_current_context` — ligne 71
- `test_promoting_terms_from_obsolete_rfq_is_a_conflict_without_writes` — ligne 90
- `test_pricing_patch_cannot_smuggle_contract_terms_and_is_atomic` — ligne 109
- `test_allowed_market_inputs_preserve_the_frozen_calendar_and_context` — ligne 124
- `test_generic_booked_context_mutation_is_refused_but_cosmetic_edit_is_allowed` — ligne 139
- `test_sql_insert_requires_an_existing_product_version_pair` — ligne 189
- `test_sql_update_requires_a_valid_version_and_keeps_historical_link` — ligne 199
- `test_repository_and_sql_refuse_retrograde_current_pointer` — ligne 209
- `test_same_version_cannot_hide_changed_terms_or_an_invalid_revision` — ligne 221
- `test_null_product_is_rejected_even_with_a_valid_version_number` — ligne 235
- `test_migration_preserves_unqualified_historical_rows_without_inventing_a_version` — ligne 242
- `test_another_products_version_does_not_qualify_a_link` — ligne 257
- `test_rfq_annotation_never_reverts_c04_governed_amendment` — ligne 268
- `test_sql_guards_allow_c04_payment_amendment_and_keep_rfq_on_old_version` — ligne 286

## backend/tests/test_products.py

- `test_product_link_migration_installs_all_insert_guards` — ligne 99
- `test_conservation_sans_prix_ne_stocke_que_les_termes` — ligne 119
- `test_indicatif_persistant_cree_un_product_interne_et_y_rattache_le_kid` — ligne 133
- `test_prix_signe_est_conserve_comme_calcul_separe` — ligne 164
- `test_recu_du_pricing_http_peut_etre_conserve_tel_quel` — ligne 187
- `test_recu_pricing_supporte_un_roundtrip_json_navigateur` — ligne 200
- `test_preuve_ancienne_reste_valide_apres_roundtrip_navigateur` — ligne 212
- `test_prix_entier_reste_signe_apres_roundtrip_navigateur` — ligne 228
- `test_recu_modifie_est_refuse_et_transaction_annulee` — ligne 241
- `test_creation_idempotente_et_cle_reutilisee_avec_autre_contenu_refusee` — ligne 255
- `test_produit_d_un_autre_utilisateur_repond_404` — ligne 269
- `test_composition_du_pricing_reinjecte_le_marche_sans_modifier_les_termes` — ligne 276
- `test_repricing_date_est_ajoute_sans_modifier_les_termes` — ligne 303
- `test_repricing_sur_d_autres_termes_est_refuse` — ligne 335
- `test_frozen_object_ne_partage_pas_ses_structures_internes` — ligne 353
- `test_rfq_consomme_les_termes_du_product_et_l_enrichit` — ligne 360
- `test_rfq_depuis_pricer_conserve_tout_le_panier_du_product` — ligne 389
- `test_booking_direct_rattache_l_execution_au_product` — ligne 426
- `test_booking_direct_cree_un_product_interne_sans_doublon` — ligne 463
- `test_booking_depuis_un_indicatif_reutilise_exactement_son_product` — ligne 491
- `test_booking_direct_refuse_un_recu_non_signe` — ligne 528
- `test_kid_et_emt_s_attachent_directement_au_product` — ligne 550
- `test_calcul_emt_prend_les_termes_du_product_comme_autorite` — ligne 579
- `test_document_product_est_telechargeable_et_historique` — ligne 596
- `test_migration_pose_une_protection_sql_sur_les_versions` — ligne 619

## backend/tests/test_public_registration.py

- `test_disabled_registration_rejects_valid_payload_without_writes` — ligne 50
- `test_enabled_registration_persists_regular_user_and_issues_usable_session` — ligne 66
- `test_registration_enforces_password_bounds_before_persistence` — ligne 113
- `test_managed_registration_ignores_public_opt_in` — ligne 129

## backend/tests/test_raw_vs_adjusted_prices.py

- `test_par_defaut_on_recoit_le_cours_nu` — ligne 49
- `test_le_cours_ajuste_reste_accessible_mais_doit_etre_demande` — ligne 55
- `test_l_estimation_de_volatilite_garde_le_rendement_total` — ligne 62
- `test_la_calibration_datee_utilise_la_meme_fenetre_que_le_mtm` — ligne 69
- `test_les_fixings_contractuels_etaient_deja_sur_le_cours_nu` — ligne 103
- `test_la_borne_de_fin_est_inclusive_et_la_provenance_est_exposee` — ligne 110

## backend/tests/test_realized_calibration.py

- `test_realized_sigma_exact` — ligne 20
- `test_realized_corr_psd_and_bounds` — ligne 30
- `test_realized_corr_degenerate_regularized` — ligne 47
- `test_realized_window_truncates_and_minimum` — ligne 56

## backend/tests/test_reference_governance.py

- `test_catalog_uses_local_metadata_offline_and_prevents_currency_divergence` — ligne 18
- `test_invalid_reference_metadata_is_rejected` — ligne 44
- `test_reference_reason_authorization_soft_delete_and_explicit_revalidation` — ligne 51
- `test_restart_preserves_catalog_moves_deactivations_and_even_an_empty_catalog` — ligne 70
- `test_explicit_invalid_provider_link_never_falls_back_to_homonymous_bank` — ligne 98
- `test_credit_control_never_silently_skips_unknown_or_inactive_identity` — ligne 110
- `test_legacy_quote_migration_never_invents_a_historical_identity` — ligne 120

## backend/tests/test_releves_consommateurs.py

- `test_la_watchlist_vise_la_prochaine_constatation` — ligne 106
- `test_l_alerte_de_rappel_compte_les_jours_jusqu_a_la_constatation` — ligne 126
- `test_la_note_de_valorisation_ne_liste_que_les_constatations` — ligne 147
- `test_la_note_d_un_produit_ponctuel_est_inchangee` — ligne 167
- `test_l_audit_d_une_modification_refusee_cite_les_vrais_temps_d_observation` — ligne 181
- `test_la_watchlist_mesure_contre_le_s0_de_la_fenetre_de_depart` — ligne 248
- `test_tant_qu_un_releve_de_depart_manque_s0_n_est_pas_defini` — ligne 267

## backend/tests/test_remediation_2026_08_02.py

- `test_signing_key_is_not_the_published_one` — ligne 40
- `test_unusable_env_secret_is_refused` — ligne 50
- `test_env_secret_wins_over_the_stored_file` — ligne 57
- `test_login_locks_out_after_five_consecutive_failures` — ligne 65
- `test_successful_login_clears_the_counter` — ligne 79
- `test_no_conversion_needed_answers_one` — ligne 93
- `test_unknown_currency_answers_none_not_parity` — ligne 99
- `test_no_module_still_falls_back_to_parity` — ligne 109
- `test_history_no_longer_backfills_before_the_first_quote` — ligne 118
- `test_load_hist_prices_carries_no_bfill` — ligne 138
- `test_total_loss_has_an_irr_of_minus_one` — ligne 147
- `test_near_total_loss_is_solved_not_dropped` — ligne 153
- `test_ordinary_windows_are_unchanged` — ligne 164
- `test_several_sign_changes_return_none_rather_than_one_arbitrary_root` — ligne 168
- `test_var_and_p5_are_one_definition` — ligne 178
- `test_var_and_es_are_exact_on_a_known_sample` — ligne 185
- `test_rho_rS_no_longer_moves_the_equity_correlation` — ligne 195
- `test_incompatible_rate_and_equity_correlations_are_refused` — ligne 207
- `test_rho_rS_stays_inert_without_a_stochastic_rate` — ligne 216
- `test_intermediate_horizon_does_not_redeem_the_product` — ligne 260
- `test_every_horizon_agrees_on_the_present_value` — ligne 270
- `test_amount_is_what_the_investor_receives` — ligne 310
- `test_return_is_the_irr_over_the_scenario_own_life` — ligne 316
- `test_annual_coupon_gives_the_same_irr_whenever_it_is_called` — ligne 329
- `test_each_cell_carries_the_life_it_was_annualised_over` — ligne 338
- `test_amount_and_return_come_from_the_same_scenario` — ligne 349
- `test_per_path_flows_stay_opt_in` — ligne 358
- `test_uncertainty_widens_with_the_horizon` — ligne 368
- `test_intermediate_horizons_refuse_what_they_cannot_price` — ligne 378
- `test_recalled_paths_leave_the_sample_instead_of_marking_zero` — ligne 415
- `test_surviving_marks_decline_as_the_bad_scenarios_accumulate` — ligne 428
- `test_a_survivor_can_still_be_worth_more_than_par` — ligne 436
- `test_no_cash_series_is_published_next_to_the_mark` — ligne 444
- `test_no_percentile_is_published_on_a_thin_sample` — ligne 455
- `test_model_price_can_be_recomputed_with_quotes_in_hand` — ligne 516
- `test_repricing_never_touches_the_contractual_identity` — ligne 539
- `test_repricing_keeps_every_underlying_of_the_basket` — ligne 567
- `test_a_genuine_term_change_is_still_refused` — ligne 583

## backend/tests/test_resource_limits.py

- `test_parser_rejects_non_positive_date_range_steps_without_looping` — ligne 22
- `test_parser_rejects_descending_and_non_progressing_date_ranges` — ligne 28
- `test_parser_caps_expanded_dates_and_source_size` — ligne 35
- `test_resolved_script_caps_dates_across_multiple_events` — ligne 44
- `test_pricing_estimate_includes_greek_reprices_without_stacking_memory` — ligne 53
- `test_pricing_estimate_includes_expanded_event_cost` — ligne 78
- `test_budget_rejects_memory_and_work_independently` — ligne 92
- `test_batch_estimate_accounts_for_parallel_worker_memory` — ligne 110
- `test_request_schema_caps_maturity_assets_and_script_size` — ligne 135
- `test_request_schema_rejects_non_finite_or_invalid_market_inputs` — ligne 147
- `test_engine_rejects_oversized_run_before_random_allocation` — ligne 156
- `test_analytic_engines_do_not_fall_back_to_gbm_for_unknown_model` — ligne 171

## backend/tests/test_rfq.py

- `test_rfq_provider_contacts_are_admin_managed_and_offered_on_rfq` — ligne 111
- `test_price_is_a_valid_selection_reason` — ligne 129
- `test_rfq_creates_an_internal_product_before_its_own_record` — ligne 133
- `test_rfq_contract_change_creates_a_product_terms_version` — ligne 146
- `test_deleted_rfq_and_quote_ids_are_never_reused_by_sqlite` — ligne 166
- `test_to_trade_calendar_is_rejected_before_the_rfq_is_created` — ligne 179
- `test_to_trade_schedule_shape_is_rejected_before_persistence` — ligne 211
- `test_multi_underlying_rfq_requires_a_complete_correlation_matrix` — ligne 226
- `test_multi_underlying_repricing_cannot_replace_the_matrix_with_an_incomplete_one` — ligne 257
- `test_quoted_at_round_trips_without_timezone_shift` — ligne 285
- `test_quotes_sorted_by_response_time_not_add_order` — ligne 308
- `test_last_look_creates_nested_child_quote` — ligne 329
- `test_last_look_cannot_be_reverted_once_answered` — ligne 353
- `test_selecting_an_unpriced_quote_is_rejected` — ligne 380
- `test_selecting_an_expired_quote_is_rejected` — ligne 392
- `test_selecting_a_quote_from_another_rfq_is_rejected` — ligne 408
- `test_deleting_the_selected_quote_clears_the_selection` — ligne 421
- `test_changing_the_selected_quote_does_not_reuse_the_previous_reason` — ligne 434
- `test_deleting_a_quote_cascades_to_its_last_look_child` — ligne 455
- `test_rfq_defaults_to_indicatif_kind` — ligne 469
- `test_to_trade_rfq_requires_an_expert_calendar_script` — ligne 475
- `test_booking_from_an_rfq_links_deal_and_closes_the_rfq` — ligne 508
- `test_multi_underlying_rfq_reaches_the_deal_without_losing_market_inputs` — ligne 534
- `test_booking_never_reuses_a_deal_id_retained_by_the_audit_trail` — ligne 600
- `test_booking_uses_the_rfq_commercial_and_legal_context_as_authority` — ligne 616
- `test_rfq_defaults_to_achat` — ligne 761
- `test_edge_is_positive_when_a_provider_quotes_below_model_on_a_buy` — ligne 768
- `test_edge_flips_sign_on_a_sell` — ligne 774
- `test_edge_is_none_without_a_model_price` — ligne 780
- `test_history_reports_edge_alongside_the_raw_spread` — ligne 785
- `test_booking_rejects_an_unknown_rfq_id` — ligne 801
- `test_booking_rejects_another_users_rfq` — ligne 811
- `test_status_follows_the_tender_from_draft_to_retenue` — ligne 828
- `test_deselecting_a_quote_takes_the_rfq_back_to_cotee` — ligne 847
- `test_deleting_the_selected_quote_takes_the_rfq_back_too` — ligne 861
- `test_clearing_a_price_takes_the_rfq_back_to_envoyee` — ligne 873
- `test_closed_round_requires_an_explicit_successor` — ligne 882
- `test_a_booked_rfq_never_falls_back` — ligne 907
- `test_status_cannot_be_posed_by_hand_beyond_sans_suite` — ligne 925
- `test_reference_numbering_survives_a_deletion` — ligne 935
- `test_reference_numbering_ignores_foreign_formats` — ligne 950
- `test_deleting_an_rfq_a_deal_was_booked_from_is_refused` — ligne 966
- `test_only_an_unsolicited_unbooked_rfq_stays_deletable` — ligne 980
- `test_provider_with_an_identical_name_needs_no_configuration` — ligne 1011
- `test_diverging_labels_resolve_through_the_explicit_link` — ligne 1017
- `test_unmatched_provider_resolves_to_nothing_rather_than_its_label` — ligne 1027
- `test_an_inactive_counterparty_is_never_proposed` — ligne 1033
- `test_quote_row_carries_the_resolved_counterparty` — ligne 1041
- `test_an_answered_last_look_supersedes_its_parent` — ligne 1063
- `test_an_unanswered_last_look_supersedes_nothing` — ligne 1080
- `test_history_flags_the_winner_only_once_the_deal_is_booked` — ligne 1093
- `test_booking_from_an_rfq_without_a_retained_quote_is_refused` — ligne 1115
- `test_booking_freezes_the_competitive_picture_on_the_deal` — ligne 1128
- `test_booking_freezes_selection_reason_and_every_final_response` — ligne 1159
- `test_provenance_keeps_only_final_quotes_as_competition` — ligne 1197
- `test_a_deal_booked_outside_any_tender_has_no_provenance` — ligne 1215
- `test_an_rfq_cannot_be_booked_twice` — ligne 1230
- `test_a_booked_rfq_points_at_its_deal` — ligne 1244
- `test_an_unbooked_rfq_has_no_deal_pointer` — ligne 1256
- `test_observations_are_derived_without_any_pricing` — ligne 1308
- `test_the_contractual_calendar_wins_over_the_simulation_grid` — ligne 1322
- `test_an_unresolvable_script_is_refused_even_with_client_times` — ligne 1336
- `test_maturity_lands_on_the_deals_own_maturity_date` — ligne 1362
- `test_a_coupon_calendar_shorter_than_the_note_keeps_the_notes_maturity` — ligne 1382
- `test_a_deal_with_no_observation_at_all_is_refused` — ligne 1398
- `test_a_broken_calendar_is_not_rescued_by_pricing_times` — ligne 1414
- `test_the_competitive_record_is_frozen_once_the_tender_traded` — ligne 1452
- `test_the_winner_survives_every_refused_mutation` — ligne 1470
- `test_annotating_a_booked_tender_stays_possible` — ligne 1481
- `test_booking_refuses_what_is_not_a_trade` — ligne 1501
- `test_booking_accepts_a_forward_start_paid_before_its_strike` — ligne 1512
- `test_unknown_counterparty_requires_explicit_audited_admin_exception` — ligne 1520
- `test_quote_prices_are_percentage_points` — ligne 1545
- `test_the_same_provider_cannot_be_solicited_twice_on_one_tender` — ligne 1557
- `test_a_last_look_that_degrades_the_price_is_refused` — ligne 1573
- `test_a_last_look_that_degrades_is_read_the_other_way_on_a_sell` — ligne 1596
- `test_sens_and_kind_are_constrained` — ligne 1612
- `test_a_negative_model_price_is_refused` — ligne 1621
- `test_booking_refuse_un_autre_produit_sous_le_meme_rfq_id` — ligne 1665
- `test_booking_conforme_fige_un_hash_des_termes_rfq` — ligne 1675
- `test_termes_contractuels_rfqs_sont_figes_apres_sollicitation` — ligne 1683
- `test_last_look_ne_peut_pas_devenir_une_chaine_cachee` — ligne 1698
- `test_datetime_avec_offset_est_normalise_en_utc` — ligne 1711
- `test_calendrier_post_maturite_est_refuse` — ligne 1722
- `test_deux_ans_de_coupons_sur_une_note_a_trois_ans_se_booke` — ligne 1749
- `test_le_pricer_reprend_le_contrat_canonique_du_product_de_la_rfq` — ligne 1853
- `test_un_autre_contrat_reste_refuse_au_booking_de_la_rfq` — ligne 1869
- `test_t_se_compare_en_jours_arrondis_comme_les_ecrans` — ligne 1892
- `test_allocation_de_references_est_atomique_sous_concurrence` — ligne 1900
- `test_unicite_structurelle_un_deal_par_rfq` — ligne 1924
- `test_backfill_statuts_rfq_est_une_migration_executee_une_seule_fois` — ligne 1949
- `test_renaming_a_counterparty_keeps_its_providers_attached` — ligne 1973
- `test_les_hypotheses_de_marche_atteignent_les_params_stockes` — ligne 2031
- `test_les_hypotheses_ne_deplacent_aucun_terme_contractuel` — ligne 2047
- `test_les_hypotheses_survivent_a_un_second_calcul` — ligne 2067
- `test_le_booking_qualifie_une_quote_a_qualifier` — ligne 2106
- `test_une_quote_deja_ferme_ne_doit_rien_au_booking` — ligne 2114
- `test_une_quote_indicative_se_booke_et_laisse_sa_trace` — ligne 2124
- `test_un_ao_reglant_avant_sa_maturite_est_refuse_a_la_creation` — ligne 2173
- `test_un_ao_coherent_se_cree_normalement` — ligne 2182
- `test_le_refus_vaut_aussi_a_la_modification` — ligne 2188
- `test_deleting_last_look_family_clears_selection_and_preserves_other_quotes` — ligne 2202
- `test_closed_round_refuses_quote_deletion_and_preserves_its_product` — ligne 2225
- `test_quote_deletion_respects_current_desk_rights_without_changing_product` — ligne 2241

## backend/tests/test_rfq_bank_pricing.py

- `test_claim_creates_bank_product_once_with_identical_terms` — ligne 38
- `test_native_engine_prices_and_retains_signed_bank_calculation_privately` — ligne 56
- `test_foreign_admin_and_read_only_bank_member_cannot_read_private_product` — ligne 81
- `test_terms_and_trade_intent_locked_even_through_product_apis` — ligne 98
- `test_assignment_is_explicit_stale_protected_and_ownership_not_transferred` — ligne 117
- `test_closed_round_or_revoked_membership_blocks_new_private_calculations` — ligne 141
- `test_unsupported_terms_remain_readable_without_silent_default_product` — ligne 158

## backend/tests/test_rfq_bank_publication.py

- `test_single_validator_publishes_commercial_price_once_without_private_inputs` — ligne 57
- `test_second_validator_required_and_configurable` — ligne 86
- `test_editing_price_invalidates_validation_and_stale_recap_is_rejected` — ligne 99
- `test_changed_policy_or_revoked_validator_blocks_publication` — ligne 113
- `test_price_received_is_readonly_and_manual_still_works` — ligne 131
- `test_revision_keeps_original_and_does_not_move_selection` — ligne 147
- `test_withdrawal_preserves_price_and_acceptance_prevents_withdrawal` — ligne 164
- `test_conditional_response_not_ranked_as_compliant_and_stale_calculation_refused` — ligne 182
- `test_sender_and_bank_without_explicit_grants_cannot_validate_or_publish` — ligne 197
- `test_suspended_relation_rechecked_at_publication` — ligne 212
- `test_payload_fingerprint_is_recomputed_before_publication` — ligne 225
- `test_firm_offer_requires_recognized_treatment_permissions` — ligne 239
- `test_newer_calculation_invalidates_approved_response` — ligne 249
- `test_revoked_approval_is_not_current_in_workspace_and_history_is_preserved` — ligne 266

## backend/tests/test_rfq_c23.py

- `test_price_revision_invalidates_decision_and_preserves_audit` — ligne 39
- `test_currency_is_explicit_and_mismatch_cannot_be_selected` — ligne 55
- `test_quoted_at_only_patch_validates_merged_times` — ligne 68
- `test_improved_parent_retires_last_look_and_its_decision` — ligne 79
- `test_closed_round_cannot_reopen_and_new_round_is_explicit` — ligne 94
- `test_material_revision_revokes_selection_with_reason_and_product_projection` — ligne 133
- `test_note_and_identical_retry_preserve_revision_and_decision` — ligne 152
- `test_stale_edit_and_stale_selection_are_rejected` — ligne 167
- `test_malformed_currency_refused_without_partial_price_change` — ligne 185
- `test_merged_times_normalize_offsets_and_preserve_entry_time` — ligne 195
- `test_invalidated_last_look_requires_new_improvement_before_reactivation` — ligne 205
- `test_historical_network_quote_survives_closure_without_becoming_selectable` — ligne 221
- `test_quote_revision_migration_is_additive_idempotent_and_does_not_certify_legacy_decisions` — ligne 239
- `test_two_concurrent_edits_of_same_revision_cannot_both_win` — ligne 255
- `test_no_selection_right_cannot_use_revision_metadata_to_select` — ligne 290
- `test_network_price_revision_preserves_old_response_and_clears_exact_decision` — ligne 303
- `test_booking_gate_refuses_unqualified_revision_or_currency_even_if_selection_is_forged` — ligne 332
- `test_closed_manual_round_keeps_history_but_refuses_economic_edits` — ligne 348
- `test_successor_of_legacy_abandoned_round_preserves_closed_state` — ligne 363

## backend/tests/test_rfq_desk_access.py

- `test_creation_requires_authorized_pilot_desk_and_preserves_organization` — ligne 51
- `test_same_desk_reprises_but_other_desks_and_admin_cannot_read` — ligne 65
- `test_model_input_identity_is_private_to_pricing_right` — ligne 77
- `test_share_is_capped_by_member_rights_and_revoke_cuts_open_links` — ligne 94
- `test_creator_has_no_residual_access_after_membership_revoked` — ligne 115
- `test_read_only_member_cannot_obtain_private_pricing_or_mutate` — ligne 129
- `test_admin_can_manage_desks_without_reading_rfqs_or_granting_self` — ligne 149
- `test_assignment_replaces_responsible_without_changing_creator_or_terms` — ligne 169
- `test_transfer_does_not_leave_an_implicit_share_to_source_desk` — ligne 183
- `test_assignment_refuses_wrong_org_unentitled_responsible_and_stale_scope` — ligne 197

## backend/tests/test_rfq_electronic_execution.py

- `test_exact_quote_confirmed_by_bank_not_by_delivery_ack` — ligne 109
- `test_request_retry_uses_same_intention_and_conflicts_are_rejected` — ligne 137
- `test_bank_decision_retry_is_idempotent_and_conflicting_decision_is_refused` — ligne 150
- `test_lost_ack_recovered_by_status_without_reapplying_decision` — ligne 162
- `test_first_arrival_after_expiry_is_explicitly_rejected_not_backdated` — ligne 193
- `test_valid_arrival_can_be_decided_after_expiry_without_rewriting_receipt` — ligne 208
- `test_pending_request_prevents_replacement_withdrawal_and_local_forged_confirmation` — ligne 221
- `test_execution_requires_desk_book_right_not_just_price_or_publish` — ligne 242
- `test_immutable_execution_and_decision_survive_raw_mutation_attempts` — ligne 255
- `test_concurrent_duplicate_transport_receipt_is_one_execution` — ligne 267
- `test_modified_quote_is_rejected_as_business_fact` — ligne 300
- `test_changed_bank_context_cannot_be_confirmed_silently` — ligne 315
- `test_two_native_bookings_and_exact_replays_make_one_deal_per_local_leg` — ligne 368
- `test_pending_electronic_request_blocks_each_linked_local_booking` — ligne 386
- `test_bank_booking_cannot_change_the_confirmed_economics` — ligne 401
- `test_unbound_or_future_confirmation_cannot_confirm_local_agreement` — ligne 416
- `test_other_message_id_cannot_create_a_second_intention` — ligne 430
- `test_revocation_before_delivery_blocks_without_inventing_a_bank_refusal` — ligne 443
- `test_bank_reception_time_cannot_be_backdated_while_decision_is_pending` — ligne 459

## backend/tests/test_rfq_execution.py

- `test_network_booking_requires_exact_confirmation_without_rewriting_publication` — ligne 164
- `test_relationship_suspension_blocks_new_confirmation` — ligne 186
- `test_requested_is_not_confirmation_and_cancel_preserves_history` — ligne 200
- `test_external_confirmation_freezes_terms_and_preserves_manual_route` — ligne 213
- `test_confirmed_trade_books_after_quote_expiry_and_replays_once` — ligne 229
- `test_expired_offer_cannot_be_backdated_into_a_new_treatment` — ligne 248
- `test_acceptance_after_expiry_or_future_confirmation_is_rejected` — ligne 256
- `test_booking_refusal_preserves_confirmation_and_block_reason` — ligne 269
- `test_no_book_right_and_foreign_organization_cannot_confirm` — ligne 281
- `test_immutable_evidence_and_duplicate_execution_reference` — ligne 292
- `test_manual_booking_without_new_confirmation_keeps_existing_workflow` — ligne 308
- `test_duplicate_execution_reference_across_rfqs_has_conflict` — ligne 315
- `test_external_conflict_keeps_confirmed_trade_and_blocks_booking` — ligne 333
- `test_concurrent_booking_of_same_execution_returns_one_deal` — ligne 346

## backend/tests/test_rfq_network_delivery.py

- `test_actual_delivery_read_receipt_and_same_command_replay` — ligne 27
- `test_admin_without_desk_and_foreign_org_cannot_read_inbox` — ligne 54
- `test_send_rechecks_relation_and_preview_after_preparation` — ligne 65
- `test_stale_request_cannot_be_sent_and_key_cannot_change_content` — ligne 79
- `test_network_freeze_blocks_material_edits_but_allows_private_pricing` — ligne 95
- `test_new_round_links_previous_without_moving_quotes_or_messages` — ligne 110
- `test_manual_solicitation_freezes_terms_even_after_quote_deletion` — ligne 128
- `test_duplicate_organization_not_resent_under_fresh_key` — ligne 139
- `test_extra_recipient_gets_same_frozen_request_without_competitor_identity` — ligne 151

## backend/tests/test_rfq_product_exchange.py

- `test_request_projection_uses_product_and_keeps_private_data_out` — ligne 36
- `test_rfqs_keep_their_own_terms_version_after_a_product_revision` — ligne 57
- `test_stale_version_never_prepares_a_different_request` — ligne 72
- `test_invalid_or_duplicate_recipient_is_refused` — ligne 79
- `test_inactive_recipient_and_past_or_unzoned_deadlines_are_refused` — ligne 85
- `test_another_user_cannot_read_either_projection` — ligne 97
- `test_native_pricing_uses_the_current_engine_and_persisted_private_inputs` — ligne 107
- `test_price_is_not_recorded_after_inputs_change` — ligne 127
- `test_inception_receipt_cannot_attest_a_later_rfq_valuation` — ligne 137
- `test_pricer_can_change_private_context_but_not_contractual_terms` — ligne 153

## backend/tests/test_rfq_reconciliation.py

- `test_confirmation_alone_never_implies_a_booking_or_a_matched_book` — ligne 60
- `test_incomplete_local_leg_resumes_after_remote_close_and_both_books_match` — ligne 72
- `test_refresh_reuses_command_and_never_creates_or_repairs_a_deal` — ligne 96
- `test_authenticated_peer_economic_discrepancies_are_visible_not_auto_repaired` — ligne 115
- `test_unbound_old_future_or_private_status_cannot_replace_the_peer_state` — ligne 136
- `test_lost_status_ack_and_restarts_recover_without_duplicate_statement_or_reply` — ligne 151
- `test_statements_and_proofs_are_immutable` — ligne 171
- `test_read_access_does_not_grant_resume_and_revocation_is_rechecked` — ligne 182
- `test_failed_booking_rolls_back_the_booking_statement_then_same_command_recovers` — ligne 196
- `test_closed_or_expired_unconfirmed_rfq_does_not_gain_pricing_recovery` — ligne 214
- `test_concurrent_same_resume_command_queues_one_snapshot` — ligne 222
- `test_peer_booking_disappearance_is_a_discrepancy_kept_in_history` — ligne 245
- `test_resume_also_reschedules_a_closure_that_blocks_later_status_messages` — ligne 258
- `test_existing_confirmed_bookings_gain_no_peer_certificate_until_refresh` — ligne 271
- `test_foreign_organization_cannot_read_or_resume` — ligne 294
- `test_bank_refusal_is_reconciled_without_inventing_bookings` — ligne 303
- `test_different_booked_trade_dates_are_reported_without_choosing_a_date` — ligne 312
- `test_confirmed_incomplete_bank_leg_can_be_explicitly_reassigned_after_close` — ligne 326
- `test_operational_inventory_and_bank_queue_are_scoped_and_surface_incomplete_legs` — ligne 339

## backend/tests/test_rfq_relationships.py

- `test_relation_requires_both_parties_and_explicit_local_mapping` — ligne 75
- `test_authorized_projection_preserves_product_without_private_booking_data` — ligne 88
- `test_suspension_rechecked_after_list_and_resume_needs_recognition` — ligne 103
- `test_changed_terms_invalidate_both_and_stale_references_are_refused` — ligne 116
- `test_perimeter_controls_do_not_depend_on_browser_filters` — ligne 137
- `test_other_organizations_and_nonadmins_cannot_manage_relationships` — ligne 153
- `test_existing_booking_agreements_are_linked_explicitly_in_local_scope` — ligne 168
- `test_invalid_material_terms_are_refused` — ligne 182

## backend/tests/test_rfq_transport.py

- `test_pairing_recognizes_exact_agreement_without_leaking_key` — ligne 114
- `test_remote_delivery_uses_local_ids_and_private_projection` — ligne 122
- `test_duplicate_request_and_conflicting_payload` — ligne 142
- `test_signature_address_and_stale_envelope_rejected` — ligne 160
- `test_lost_receipt_recovered_after_worker_restart_without_second_request` — ligne 173
- `test_revoked_sender_rights_prevent_first_delivery` — ligne 195
- `test_closed_unsent_request_is_cancelled_without_disclosing_terms` — ligne 205
- `test_out_of_order_messages_are_not_applied` — ligne 220
- `test_quote_publication_returns_automatically_and_withdrawal_is_ordered` — ligne 232
- `test_stale_calculation_during_interruption_returns_history_only` — ligne 252
- `test_closure_after_delivery_reaches_bank_and_blocks_pricing` — ligne 263
- `test_https_and_redirect_policy` — ligne 274
- `test_wire_request_excludes_local_ids_and_private_fields` — ligne 283
- `test_withdrawal_still_delivered_after_relationship_suspension` — ligne 300
- `test_withdrawn_unsent_quote_is_cancelled_then_stream_continues` — ligne 316
- `test_immutable_outbox_and_receipts_allow_worker_state_updates` — ligne 329
- `test_parallel_duplicate_receipts_create_one_bank_dossier` — ligne 342
- `test_active_lease_prevents_second_worker_and_expired_lease_resumes` — ligne 364

## backend/tests/test_risk_c21.py

- `test_missing_scenario_factor_is_rejected` — ligne 21
- `test_invalid_history_is_not_a_covered_factor` — ligne 29
- `test_partial_greeks_are_unknown_with_latest_run_source` — ligne 33
- `test_short_claim_keeps_exposure_and_blocks_cva_limit` — ligne 72
- `test_discounted_claim_cva_matches_constant_discounted_exposure` — ligne 86
- `test_monitor_and_preparation_invalidate_after_official_fixing` — ligne 92
- `test_var_launch_refuses_incomplete_factors_before_enqueue` — ligne 115
- `test_partial_portfolio_totals_are_separate_from_available_sums` — ligne 131
- `test_risk_scope_defaults_to_production_with_explicit_uat` — ligne 146
- `test_corrected_fixing_rejects_archived_mtm_and_cached_greeks` — ligne 160
- `test_short_optional_projection_is_unavailable_instead_of_extended` — ligne 176
- `test_fixed_claims_net_only_over_their_actual_common_life` — ligne 189
- `test_c04_amendment_rechecks_short_claim_cva_without_mutating_terms` — ligne 207
- `test_var_http_production_uat_and_c01_visibility_are_preserved` — ligne 239

## backend/tests/test_risk_dates.py

- `test_risk_uses_the_snapshot_for_the_selected_date_and_grays_outside_life` — ligne 28
- `test_risk_does_not_reuse_greeks_from_another_date` — ligne 66

## backend/tests/test_risk_scope_c27.py

- `test_default_exposure_excludes_uat_and_other_organization` — ligne 57
- `test_explicit_uat_exposure_is_not_a_mixed_total` — ligne 64
- `test_shock_persists_the_selected_scope_and_frozen_universe` — ligne 68
- `test_legacy_shock_is_not_relabelled_production` — ligne 79
- `test_all_portfolio_consumers_share_origin_and_c01_visibility` — ligne 91
- `test_global_calculations_use_the_visible_collective_book` — ligne 107
- `test_membership_badges_follow_selected_origin` — ligne 113
- `test_history_filters_before_limiting_and_never_reclassifies_from_live_deals` — ligne 120
- `test_unknown_origin_is_rejected_for_reads_and_new_studies` — ligne 133
- `test_explicit_deal_shock_uses_its_origin_and_refuses_a_conflicting_body` — ligne 140
- `test_var_history_is_frozen_per_origin_and_portfolio_and_keeps_legacy_separate` — ligne 149
- `test_other_users_var_and_shock_histories_remain_private` — ligne 168
- `test_var_creation_freezes_origin_and_view_without_reusing_a_current_book_later` — ligne 180
- `test_deleted_portfolio_archives_keep_their_frozen_view_and_are_still_browsable` — ligne 193
- `test_one_million_production_and_one_million_uat_never_make_a_two_million_default` — ligne 212

## backend/tests/test_roll_c25.py

- `test_fixed_120_percent_payoff_is_distinct_from_quantity_and_recovers_above_par` — ligne 66
- `test_observed_bid_and_entry_costs_really_change_quantity_and_recovery` — ligne 77
- `test_each_cost_changes_recovery_without_changing_model_prices_or_amendments` — ligne 95
- `test_incomplete_or_ambiguous_financing_is_rejected_before_pricing` — ligne 118
- `test_non_finite_financing_is_never_accepted` — ligne 126
- `test_a_bid_after_asof_and_a_negative_budget_leave_explicit_unpriced_rows` — ligne 132
- `test_zero_cash_means_zero_position_and_never_a_free_note` — ligne 141
- `test_only_proven_literal_contracts_publish_a_cap` — ligne 157
- `test_finite_sample_max_is_never_a_contractual_cap` — ligne 161
- `test_t16_costs_funding_calendar_and_frozen_study_survive_market_and_variant_changes` — ligne 176
- `test_recovery_threshold_changes_when_costs_make_par_unaffordable` — ligne 217
- `test_cost_evidence_cannot_be_changed_after_server_sealing` — ligne 226
- `test_cost_inputs_do_not_allow_another_user_to_read_or_archive_the_study` — ligne 237
- `test_model_timestamp_preserves_the_instant_of_an_aware_business_clock` — ligne 251

## backend/tests/test_scenario_cut_lot4.py

- `test_var_worker_keeps_event_after_exact_replay_cut` — ligne 9
- `test_scenario_grid_worker_keeps_event_after_exact_replay_cut` — ligne 28

## backend/tests/test_scenarios.py

- `test_grid_shape_and_base_price` — ligne 22
- `test_base_price_independent_of_shock_lists` — ligne 41
- `test_pre_strike_grid_uses_the_future_fixing_in_every_cell` — ligne 53
- `test_call_price_increases_with_spot_and_vol_shocks` — ligne 69
- `test_grid_runs_on_every_model` — ligne 86

## backend/tests/test_schedule.py

- `test_parse_tenor` — ligne 9
- `test_perfectly_aligned_schedule_has_no_stub` — ligne 19
- `test_start_and_end_always_included` — ligne 31
- `test_short_last_stub_is_short` — ligne 38
- `test_long_last_merges_short_stub` — ligne 50
- `test_short_first_stub_is_short` — ligne 62
- `test_long_first_merges_short_stub` — ligne 74
- `test_end_before_start_raises` — ligne 84
- `test_sub_frequency_subdivides_every_main_interval` — ligne 90
- `test_no_sub_frequency_dates_equals_main_dates` — ligne 102
- `test_year_fractions_start_at_zero_and_increase` — ligne 108

## backend/tests/test_schedule_model.py

- `test_l_echeancier_est_construit_a_la_resolution` — ligne 43
- `test_chaque_constatation_porte_sa_date_calendaire` — ligne 49
- `test_les_releves_sont_rattaches_a_leur_constatation` — ligne 59
- `test_un_releve_vise_par_un_bloc_porte_les_deux_roles` — ligne 68
- `test_les_blocs_sont_rattaches_dans_l_ordre_du_script` — ligne 79
- `test_deux_blocs_du_meme_calendrier_ne_font_qu_une_constatation` — ligne 88
- `test_la_fenetre_de_depart_n_est_pas_une_constatation` — ligne 97
- `test_les_dates_de_releve_listent_tous_les_fixings_a_collecter` — ligne 110
- `test_plusieurs_constatations_peuvent_tomber_le_meme_jour` — ligne 121
- `test_la_structure_se_serialise_pour_le_booking` — ligne 137
- `test_un_script_a_dates_litterales_a_aussi_son_echeancier` — ligne 148

## backend/tests/test_schedule_settlement.py

- `test_sans_devise_les_dates_restent_calendaires` — ligne 23
- `test_avec_devise_les_observations_tombent_un_jour_ouvre` — ligne 32
- `test_le_roll_se_fait_avant_ajustement` — ligne 44
- `test_le_decalage_de_reglement_produit_les_dates_de_paiement` — ligne 53
- `test_un_decalage_sans_calendrier_est_refuse` — ligne 60
- `test_deux_dates_ajustees_sur_le_meme_jour_fusionnent` — ligne 67
- `test_convention_none_laisse_le_calendrier_brut` — ligne 77
- `test_sans_devise_les_flux_sont_payes_a_la_constatation` — ligne 102
- `test_avec_devise_chaque_observation_porte_sa_date_de_paiement` — ligne 107
- `test_sans_convention_la_date_du_term_sheet_ne_bouge_pas` — ligne 121
- `test_chaque_calendrier_porte_sa_propre_convention` — ligne 144
- `test_convention_inconnue_est_refusee` — ligne 157
- `test_un_decalage_sans_devise_est_refuse_aussi_au_niveau_du_script` — ligne 164
- `test_le_qualificatif_selectionne_la_meme_ligne_des_deux_cotes` — ligne 170

## backend/tests/test_seed_ccr_test_client.py

- `test_ccr_test_fixture_covers_credit_and_legal_scenarios_without_note_assignment` — ligne 16

## backend/tests/test_session_security.py

- `test_logout_is_persistent_and_only_revokes_current_session` — ligne 17
- `test_habilitation_change_and_reactivation_never_resurrect_old_tokens` — ligne 33
- `test_temporary_password_activation_personal_change_and_admin_reset` — ligne 46
- `test_password_audit_correlates_success_failure_and_contains_no_secrets` — ligne 77
- `test_managed_organization_is_unique_and_name_locked` — ligne 96
- `test_pre_c02_token_requires_reauthentication` — ligne 117
- `test_canonical_name_drift_requires_provisioning_without_implicit_repair` — ligne 126
- `test_normal_portal_cors_is_allowed_without_developer_access` — ligne 138
- `test_calendars_require_price_capability_and_allow_valid_previews` — ligne 168
- `test_calendar_budget_rejects_before_generator` — ligne 185

## backend/tests/test_settlement_discounting.py

- `test_un_remboursement_sans_date_de_paiement_est_actualise_a_la_maturite` — ligne 34
- `test_la_date_de_paiement_finale_actualise_davantage` — ligne 41
- `test_le_flux_table_porte_la_date_de_paiement` — ligne 56
- `test_le_decalage_de_reglement_des_coupons_coute_de_l_actualisation` — ligne 86
- `test_chaque_coupon_est_actualise_a_sa_propre_date_de_paiement` — ligne 97
- `test_sans_calendrier_de_reglement_rien_ne_change` — ligne 108
- `test_les_greeks_reutilisent_les_dates_completes` — ligne 118
- `test_theta_fait_vieillir_la_date_de_paiement_explicite` — ligne 136
- `test_le_paiement_global_gouverne_un_constat_terminal_date` — ligne 145
- `test_le_worker_conserve_le_paiement_sans_constat` — ligne 154

## backend/tests/test_shocks.py

- `test_spot_shock_matches_closed_form` — ligne 91
- `test_vol_shock_has_no_first_order_effect` — ligne 107
- `test_rate_shock_reduces_zero_coupon_price` — ligne 122
- `test_corr_shock_no_op_on_single_underlying` — ligne 136
- `test_choc_nul_ne_bouge_pas_un_deal_dont_le_spot_a_monte` — ligne 171
- `test_le_choc_de_spot_est_relatif_au_niveau_courant` — ligne 194
- `test_corr_shock_runs_on_basket` — ligne 210
- `test_portfolio_shock_aggregates_and_persists_one_run` — ligne 225
- `test_smile_parameters_are_model_specific_and_explicit` — ligne 263

## backend/tests/test_simulation.py

- `test_solve_for_param_converges_on_strike` — ligne 23
- `test_solve_for_param_non_bracketing_reports_unconverged` — ligne 43
- `test_solve_for_param_exact_bound_short_circuits` — ligne 55
- `test_price_grid_shape_and_axes` — ligne 68
- `test_price_grid_matches_direct_pricing_at_corner` — ligne 79
- `test_price_grid_call_decreasing_in_strike` — ligne 91

## backend/tests/test_spot_baseline.py

- `test_seeding_d_un_deal_vivant_ne_declenche_pas_le_bump_differe` — ligne 53
- `test_le_bump_differe_applique_le_ratio_pas_le_niveau` — ligne 77
- `test_le_bump_reste_actif_sans_baseline_explicite` — ligne 87
- `test_seeding_sans_fenetre_de_fixing_est_inchange` — ligne 97

## backend/tests/test_stochastic_rate_integrity.py

- `test_vanishing_rate_volatility_has_one_funding_discount` — ligne 25
- `test_payment_rebase_and_parallel_shocks_do_not_double_count_funding` — ligne 31
- `test_funding_changes_present_value_without_changing_raw_asset_payoffs` — ligne 45
- `test_funding_leaves_stochastic_rates_and_risk_free_factors_identical` — ligne 54
- `test_mono_uses_the_joint_factor_in_every_simulator` — ligne 71
- `test_joint_basket_covariance_is_preserved` — ligne 88
- `test_incompatible_joint_correlations_are_refused` — ligne 106
- `test_prepaid_forward_martingale_on_independent_replications` — ligne 113
- `test_discrete_convexity_matches_independent_gaussian_covariance` — ligne 130
- `test_paths_and_factors_are_continuous_at_zero_reversion` — ligne 151
- `test_zero_coupon_price_is_finite_and_continuous_near_zero` — ligne 165
- `test_short_and_long_zero_coupon_prices_have_a_continuous_zero_limit` — ligne 173
- `test_invalid_rate_parameters_fail_closed` — ligne 184
- `test_nonfinite_or_underflowed_factors_are_refused` — ligne 193

## backend/tests/test_strike_value_split.py

- `test_sur_un_flux_certain_l_actualisation_ne_bouge_pas` — ligne 36
- `test_le_remboursement_est_actualise_a_l_horizon_reel` — ligne 46
- `test_l_horizon_exact_rend_visible_le_decalage_de_deux_jours` — ligne 56
- `test_un_ecart_superieur_au_pas_de_grille_se_voit` — ligne 66
- `test_value_date_nulle_reproduit_le_comportement_historique` — ligne 76
- `test_le_recalage_s_applique_aussi_a_la_date_de_paiement` — ligne 83

## backend/tests/test_structura_launcher.py

- `test_menu_choices_start_only_needed_services_and_reuse_them` — ligne 29
- `test_failed_partial_launch_only_stops_newly_created_services` — ligne 50
- `test_occupied_admin_port_does_not_replace_its_occupant_or_block_portal` — ligne 65
- `test_backend_without_explicit_environment_opens_launcher` — ligne 79
- `test_full_admin_has_its_own_manifest_and_separate_data_directory` — ligne 92
- `test_each_organization_shortcut_opens_its_own_superuser_route` — ligne 102
- `test_console_shortcut_remains_separate_from_full_admin` — ligne 111
- `test_simulation_shortcut_opens_admin_screen_without_campaign_or_controller` — ligne 118
- `test_acceptance_failure_cleans_admin_and_controller_but_preserves_existing_portal` — ligne 126

## backend/tests/test_studies_dividends.py

- `test_detachment_receivable_payment_is_not_second_income` — ligne 28
- `test_entitlement_before_ex_date_trades` — ligne 40
- `test_unknown_none_and_contradiction` — ligne 47
- `test_fx_receivable_and_payment` — ligne 55
- `test_reinvestment_new_lot_and_cash_remainder` — ligne 71
- `test_existing_purchase_is_linked_not_duplicated` — ligne 80
- `test_reconstruction_refuses_ambiguous_existing_buy` — ligne 88
- `test_basket_fee_and_reinvestment_entitlement` — ligne 95
- `test_second_dividend_includes_reconstructed_shares` — ligne 106
- `test_pending_reinvestment_and_missing_execution` — ligne 114
- `test_invalid_events_rejected` — ligne 123
- `test_duplicates_and_unknown_tax_rejected` — ligne 128
- `test_policy_allocations_and_discretionary_reconstruction_rejected` — ligne 139
- `test_split_units_and_net_only_event` — ligne 146
- `test_reinvestment_overspend_and_order_reuse` — ligne 160
- `test_weekday_delay_and_missing_price` — ligne 170
- `test_full_pipeline_receivable_then_reinvestment` — ligne 180
- `test_dated_six_year_oracle_per_asset` — ligne 215

## backend/tests/test_studies_flows_import.py

- `test_generated_flows_fixture_scans_with_initial_units` — ligne 15
- `test_scan_keeps_inception_units_separate_from_final_snapshot` — ligne 29
- `test_generated_dividend_ledgers_agree_without_double_counting` — ligne 41

## backend/tests/test_studies_market_bundle.py

- `test_gateways_use_only_declared_inputs` — ligne 32
- `test_causal_fx_and_staleness` — ligne 54
- `test_reference_is_not_an_initial_fifo_position` — ligne 64
- `test_invalid_bundle_rejected` — ligne 77
- `test_context_isolation_and_reset_on_failure` — ligne 86
- `test_market_file_is_hashed_and_cannot_escape_folder` — ligne 99
- `test_brinson_period_must_match_declared_reference` — ligne 109
- `test_secondary_endpoints_keep_bundle_reference_and_sync_coverage` — ligne 116

## backend/tests/test_studies_methodology.py

- `test_negative_vag_included_at_twenty_percent_on_its_own_period` — ligne 23
- `test_undocumented_or_invalid_vag_not_silently_scored` — ligne 34
- `test_brinson_calculated_is_indicative_not_missing` — ligne 43
- `test_fx_ratio_uses_signed_realized_only` — ligne 55
- `test_drawdown_all_episodes_calendar_duration_and_recovery` — ligne 65
- `test_risk_benchmark_includes_first_observed_return` — ligne 79
- `test_brinson_current_weights_keep_cash_and_reject_missing_holdings` — ligne 92
- `test_secondary_brinson_updates_saved_coverage_and_identity_without_losing_other_rows` — ligne 102
- `test_descriptive_score_does_not_claim_significant_skill` — ligne 116
- `test_factor_drawdown_is_relative_to_peak_and_keeps_first_loss` — ligne 122
- `test_replicant_uses_unrounded_coefficients_and_rounds_gap_once` — ligne 140
- `test_market_shocks_keep_multiple_orders_for_same_title_and_date` — ligne 151
- `test_factor_performance_matching_is_symmetric` — ligne 162

## backend/tests/test_studies_recipe_fixes.py

- `test_reject_unusable_synthesis` — ligne 14
- `test_prose_is_allowed_without_certifying_its_content` — ligne 19
- `test_prompt_keeps_financial_controls_without_raw_hash_catalogue` — ligne 26
- `test_editorial_brief_distinguishes_lifetime_and_yearly_returns` — ligne 37
- `test_ollama_context_and_truncation_metadata` — ligne 51
- `test_factorial_turnover_uses_calendar_time_not_nav_count` — ligne 63
- `test_api_rejects_technical_synthesis` — ligne 73
- `test_pdf_fee_text_and_dividend_bridge` — ligne 83

## backend/tests/test_studies_reconciliation.py

- `test_management_conventions` — ligne 24
- `test_annual_hwm_reversal_and_partial_cutoff` — ligne 29
- `test_periodic_fees_reject_flows` — ligne 40
- `test_cash_income_cutoff_no_double_deduction_and_duplicates` — ligne 47
- `test_snapshot_cannot_value_an_earlier_cutoff` — ligne 59
- `test_crystallization_periods` — ligne 69
- `test_missing_latent_is_not_zero` — ligne 75
- `test_cash_and_zero_results_not_classified_as_losses` — ligne 84
- `test_fifo_roundoff_does_not_create_trades_and_tiny_real_trades_survive` — ligne 90
- `test_saved_manifest_is_used_and_paths_confined` — ligne 102
- `test_six_year_reference_end_to_end` — ligne 111

## backend/tests/test_surface_calibration_integrity.py

- `test_qualification_is_distinct_from_optimizer_success` — ligne 51
- `test_material_seven_year_pillar_changes_objective_and_fit` — ligne 55
- `test_full_dossier_and_unqualified_exclusions` — ligne 67
- `test_deterministic_variance_heston_matches_independent_black_scholes` — ligne 84
- `test_low_variance_wings_converge_without_negative_or_spurious_calls` — ligne 96
- `test_heston_against_independent_riccati_ode_and_extended_fourier_domain` — ligne 110
- `test_invalid_legacy_smile_refuses_pricing_without_mutating_old_inputs` — ligne 137
- `test_legacy_flat_short_tenor_and_admissible_skew_are_not_replaced` — ligne 146
- `test_component_or_training_mc_fit_is_explicitly_exploratory` — ligne 155
- `test_legacy_valid_nonflat_smile_still_prices` — ligne 161
- `test_automatic_application_rejects_stale_or_unsupported_context` — ligne 170
- `test_signed_dossier_survives_disk_price_receipt_and_residual_snapshot` — ligne 188
- `test_even_authentic_server_proof_cannot_apply_unqualified_fit` — ligne 205
- `test_api_blocks_unsigned_automatic_fit_before_simulation_and_keeps_manual_mode` — ligne 218
- `test_calibration_api_issues_complete_signed_dossier_and_preserves_long_horizon` — ligne 238
- `test_retained_product_calculation_reloads_full_dossier_from_sqlite` — ligne 259

## backend/tests/test_transcription.py

- `test_le_moteur_par_defaut_est_local` — ligne 39
- `test_moteur_absent_annonce_comment_l_installer` — ligne 47
- `test_poids_absents_previennent_du_telechargement` — ligne 57
- `test_moteur_pret_n_affiche_aucun_avertissement` — ligne 68
- `test_un_moteur_inconnu_est_refuse` — ligne 75
- `test_un_fragment_du_vocabulaire_est_reconnu_comme_echo` — ligne 86
- `test_une_vraie_description_n_est_pas_prise_pour_un_echo` — ligne 92
- `test_un_echo_ressort_en_texte_vide` — ligne 100
- `test_une_dictee_normale_remonte_telle_quelle` — ligne 108
- `test_le_vocabulaire_est_bien_souffle_au_moteur` — ligne 118
- `test_un_worker_qui_meurt_ne_tue_pas_le_serveur` — ligne 132
- `test_le_worker_ne_depend_pas_du_paquet_app` — ligne 154
- `test_l_etat_du_moteur_est_exposé_a_l_ecran` — ligne 174
- `test_enregistrement_vide_est_une_erreur_de_requete` — ligne 182
- `test_enregistrement_trop_long_est_refuse_avant_transcription` — ligne 188
- `test_un_moteur_en_panne_est_un_502_lisible` — ligne 197

## backend/tests/test_uat_generation.py

- `test_preview_is_deterministic_and_read_only` — ligne 130
- `test_full_chain_uses_uat_references_and_batch_cleanup_is_isolated` — ligne 145
- `test_full_chain_retains_product_history_basket_and_provider_competition` — ligne 216
- `test_each_uat_entry_path_preserves_one_product_identity` — ligne 273
- `test_post_booking_options_create_mtm_history_and_risk_runs` — ligne 319
- `test_rfq_control_mix_builds_expected_non_bookable_cases` — ligne 382
- `test_invalid_ranges_are_rejected_before_batch_creation` — ligne 411
- `test_booked_uat_uses_the_same_pricing_snapshot_boundary_as_the_pricer` — ligne 421
- `test_every_offered_product_family_completes_the_full_chain` — ligne 460
- `test_every_reached_observation_carries_its_real_close` — ligne 494
- `test_forward_start_has_nothing_to_fix_yet` — ligne 556
- `test_uat_generator_refuses_retired_fixing_policies` — ligne 573
- `test_complete_mix_covers_all_eight_profiles_and_cleans_terminal_dependencies` — ligne 579
- `test_periodic_historical_profile_rejects_non_periodic_product_selection` — ligne 629
- `test_provider_outage_reports_unfilled_fixings_without_inventing_s0` — ligne 641
- `test_partial_history_keeps_the_official_prefix_and_reports_the_gap` — ligne 661
- `test_refresh_failure_does_not_commit_a_half_applied_fixing` — ligne 688
- `test_usd_observation_keeps_its_frozen_date_on_a_target_holiday` — ligne 712
- `test_le_lot_de_controle_reste_bookable_quel_que_soit_le_jour` — ligne 751

## backend/tests/test_uat_scripts.py

- `test_uat_uses_the_exact_current_catalogue_script` — ligne 41
- `test_generated_calendars_keep_fixing_separate_and_include_first_observation` — ligne 63
- `test_phoenix_memory_catches_up_missed_coupon_before_call` — ligne 103
- `test_first_observation_coupon_does_not_count_startdate` — ligne 112
- `test_maturity_keeps_capital_and_sold_put_as_separate_flows` — ligne 121
- `test_capital_guaranteed_participation_is_supplied_by_economics` — ligne 134

## backend/tests/test_underlyings_catalog.py

- `test_le_semis_reprend_la_liste_du_front` — ligne 52
- `test_seed_adopts_legacy_catalog_without_silent_symbol_rewrite` — ligne 69
- `test_seed_keeps_existing_correct_axa_and_custom_catalogue_entries` — ligne 84
- `test_ajouter_un_titre_verifie_qu_il_repond` — ligne 103
- `test_un_ticker_muet_est_refuse` — ligne 114
- `test_le_meme_ticker_peut_vivre_dans_deux_groupes` — ligne 125
- `test_le_meme_couple_ticker_groupe_est_refuse` — ligne 135
- `test_la_liste_sort_triee_par_groupe_puis_libelle` — ligne 144
- `test_desactiver_retire_des_menus_sans_perdre_la_ligne` — ligne 155

## backend/tests/test_valuation_context.py

- `test_preuve_pricing_fige_funding_seed_globale_monitoring_et_unites` — ligne 33
- `test_preuve_modifiee_est_refusee` — ligne 47
- `test_ancien_deal_sans_funding_devient_explicitement_zero` — ligne 56
- `test_courbe_funding_prolonge_son_dernier_niveau_apres_son_dernier_pilier` — ligne 60
- `test_run_valuation_transmet_tout_le_contexte` — ligne 65
- `test_un_scenario_ne_peut_pas_remplacer_le_calendrier_du_contexte` — ligne 93
- `test_scenario_smile_changes_only_the_named_underlying` — ligne 105
- `test_booking_utilise_le_snapshot_serveur_identifie` — ligne 147
- `test_booking_refuse_un_script_different_du_pricing` — ligne 159
- `test_booking_refuse_une_maturite_numerique_differente_du_pricing` — ligne 170

## backend/tests/test_valuation_notes.py

- `test_note_reuses_exact_price_archives_history_and_computes_frozen_greeks` — ligne 59
- `test_stream_has_progress_and_persists_one_note` — ligne 81
- `test_pdf_labels_the_archived_observation_source` — ligne 95
- `test_drafts_are_revision_checked_and_versions_keep_identical_pdf` — ligne 113
- `test_ownership_and_http_validation` — ligne 135
- `test_two_identical_frozen_contexts_have_zero_attribution` — ligne 159
- `test_frozen_spot_move_and_funding_are_separate_and_telescope` — ligne 168
- `test_noncomparable_runs_show_only_observed_difference` — ligne 187
- `test_replay_mismatch_blocks_attribution` — ligne 202
- `test_ai_is_explicit_grounded_and_does_not_change_draft` — ligne 210
- `test_legacy_note_warns_without_inventing_history` — ligne 238
- `test_saved_notes_block_normal_deal_deletion_but_uat_purge_cleans_children` — ligne 247
- `test_sources_are_compact_authorized_and_preserve_dates` — ligne 266
- `test_reversed_comparison_and_calendar_roll_reconcile` — ligne 275
- `test_two_underlying_correlation_change_uses_archived_matrix` — ligne 294

## backend/tests/test_valuation_pdf.py

- `test_pdf_generates_single_underlying` — ligne 61
- `test_schedule_uses_contractual_dates_instead_of_model_tenors` — ligne 72
- `test_pdf_multi_underlying_legacy_no_monitors` — ligne 76
- `test_pdf_no_history_still_generates` — ligne 83
- `test_explanation_ki_untouched_and_conclusion` — ligne 90
- `test_explanation_ki_touched` — ligne 99
- `test_explanation_best_case_capped` — ligne 105
- `test_explanation_best_case_uncapped_no_signal` — ligne 113
- `test_pdf_with_exit_signal_callout` — ligne 125
- `test_coupon_barrier_is_not_labelled_as_a_recall` — ligne 133
- `test_explain_pdf_generates` — ligne 169
- `test_explain_pdf_negative_effects_and_no_greeks` — ligne 175

## backend/tests/test_valuation_semantics.py

- `test_price_paths_and_probabilities_use_identical_financial_context` — ligne 31
- `test_deterministic_payments_include_funding_and_value_date_once` — ligne 45
- `test_positive_ten_percent_payment_is_not_zero_or_otm` — ligne 54
- `test_continuous_bridge_scope_is_preserved_in_all_consumers` — ligne 62
- `test_request_factory_keeps_dates_rates_and_antithetic_convention` — ligne 74
- `test_probability_sampling_cap_is_visible` — ligne 85
- `test_correlation_greek_uses_signed_admissible_denominator_and_base_antithetic` — ligne 93
- `test_nonperturbable_one_factor_correlation_is_unavailable` — ligne 108
- `test_lsv_vega_metadata_describes_actual_bump` — ligne 116
- `test_detached_coupon_rate_shock_uses_actual_payment_and_keeps_baseline` — ligne 125
- `test_reinvestment_solver_and_proba_share_inherited_funding_and_model` — ligne 135
- `test_api_price_proba_and_paths_share_context` — ligne 153
- `test_lsv_vega_is_kept_separate_in_portfolio_totals` — ligne 167
- `test_prestrike_and_inherited_barrier_state_match_price_for_both_analyses` — ligne 184
- `test_prestrike_api_analyses_share_the_residual_price_without_history_fetch` — ligne 192
- `test_pricer_solver_and_grid_use_the_full_context` — ligne 211
- `test_active_deal_shock_separates_optional_and_detached_coupon` — ligne 230
- `test_effective_valuation_source_is_archived_independently_of_request` — ligne 249

## backend/tests/test_var_engine.py

- `test_var_request_refuse_un_nombre_de_paths_inferieur_au_plancher_moteur` — ligne 29
- `test_historical_scenarios_carry_real_dates_and_moves` — ligne 66
- `test_historical_scenarios_worst_day_matches_biggest_realized_drop` — ligne 76
- `test_historical_scenarios_single_ticker_has_no_corr_shock` — ligne 85
- `test_historical_lookback_does_not_shrink_with_return_horizon` — ligne 92
- `test_calibrate_comovement_signs_match_crisis_dynamics` — ligne 107
- `test_parametric_scenarios_shape_and_reproducibility` — ligne 129
- `test_parametric_worst_draws_have_positive_vol_shock` — ligne 138
- `test_apply_scenario_refuses_an_untouched_missing_ticker` — ligne 152
- `test_aggregate_var_matches_hand_computed_percentile` — ligne 171
- `test_aggregate_var_queue_fractionnaire` — ligne 188
- `test_aggregate_var_empty_input` — ligne 201
- `test_un_job_echoue_interdit_la_var_globale_et_produit_la_var_hors_deal` — ligne 244
- `test_tous_les_jobs_en_echec_ne_publient_ni_zero_ni_var_reduite` — ligne 265
- `test_un_deal_ecarte_au_preflight_reste_visible_et_declenche_le_scope_reduit` — ligne 281
- `test_univers_complet_publie_la_var_globale_sans_scope_reduit` — ligne 307
- `test_api_var_marque_le_global_incomplet_en_echec_et_publie_le_scope_reduit` — ligne 330
- `test_build_deal_scenario_base_is_json_serializable_and_matches_mtm` — ligne 428
- `test_build_deal_scenario_base_skips_matured_deal` — ligne 460
- `test_var_scenario_pricer_reacts_to_spot_shock` — ligne 473

## backend/tests/test_variantes_avenant.py

- `test_le_passe_ne_rappelle_pas_sous_le_seuil_de_la_variante` — ligne 136
- `test_le_meme_seuil_au_rejeu_aurait_bien_rappele` — ligne 154
- `test_la_variante_price_bien_la_vie_restante_a_son_seuil` — ligne 166
- `test_sans_variante_le_comportement_est_celui_d_avant` — ligne 194
- `test_changer_la_frequence_passee_est_refuse` — ligne 209
- `test_prolonger_la_maturite_est_permis` — ligne 221
- `test_une_memoire_abandonnee_est_signalee_et_non_refusee` — ligne 239
- `test_une_variante_qui_garde_ses_variables_ne_signale_rien_de_perdu` — ligne 255
- `test_les_param_de_la_variante_pricent_le_reliquat_sans_toucher_au_passe` — ligne 263
- `test_un_param_saisi_atteint_le_moteur_en_cours_de_vie` — ligne 284
- `test_les_param_ne_survivent_pas_au_rejeu_mais_les_variables_si` — ligne 306
- `test_prolonger_deplace_l_horizon_de_simulation` — ligne 325
- `test_l_api_price_la_variante_et_pas_le_parent` — ligne 353
- `test_l_api_signale_ce_que_la_variante_fait_de_l_etat_repris` — ligne 369
- `test_hors_variante_le_rapport_est_vide` — ligne 375
- `test_une_note_neuve_ne_se_valorise_pas_en_cours_de_vie` — ligne 379
- `test_les_probabilites_decrivent_la_meme_variante_que_le_prix` — ligne 388

## backend/tests/test_variantes_comparaison.py

- `test_l_origine_est_repricee_dans_le_meme_appel` — ligne 155
- `test_un_avenant_garde_le_pair_atteignable` — ligne 169
- `test_les_param_de_la_variante_atteignent_bien_le_moteur` — ligne 182
- `test_les_pourcentages_stockes_sont_convertis_pour_le_moteur` — ligne 194
- `test_une_note_neuve_distingue_le_nominal_du_plafond_non_demontre` — ligne 208
- `test_la_proba_du_roll_est_ramenee_au_pair_D_ORIGINE` — ligne 220
- `test_un_roll_ne_reprend_pas_les_niveaux_du_term_sheet_d_origine` — ligne 241
- `test_une_variante_impriceable_garde_sa_ligne_avec_son_motif` — ligne 254
- `test_le_tableau_compte_les_ecarts_de_chaque_ligne` — ligne 267
- `test_toutes_les_lignes_portent_les_memes_colonnes` — ligne 274
- `test_un_avenant_expose_les_termes_de_rejeu_de_son_origine` — ligne 320
- `test_une_note_neuve_n_expose_pas_de_termes_de_rejeu` — ligne 332
- `test_le_corps_de_l_ecran_ne_rappelle_pas_dans_le_passe` — ligne 340
- `test_sans_la_separation_le_passe_rappelle_bien` — ligne 358
- `test_la_barriere_de_la_variante_agit_sur_la_vie_restante` — ligne 376
- `test_les_termes_de_rejeu_portent_le_calendrier_de_l_origine` — ligne 394
- `test_un_calendrier_mal_forme_est_refuse_lisiblement` — ligne 403
- `test_les_probabilites_ne_rappellent_pas_dans_le_passe` — ligne 443
- `test_la_barriere_de_la_variante_agit_sur_les_probabilites` — ligne 462
- `test_la_vue_de_variante_porte_le_contexte_de_son_origine` — ligne 477
- `test_enregistrer_un_delta_le_relit_a_l_identique` — ligne 489
- `test_les_comptes_de_rappel_sont_tous_lisibles_par_leur_date` — ligne 515
- `test_aucune_date_de_rappel_n_est_orpheline` — ligne 540
- `test_une_declinaison_d_un_autre_deal_est_refusee` — ligne 555
- `test_une_note_neuve_ne_contamine_pas_les_lignes_suivantes` — ligne 579
- `test_sans_parent_id_la_comparaison_reste_possible` — ligne 599
- `test_les_scenarios_suivent_la_variante` — ligne 625
- `test_la_grille_de_stress_et_la_grille_2d_concordent` — ligne 649
- `test_frozen_comparison_keeps_origin_variants_and_displayed_results` — ligne 678

## backend/tests/test_variantes_filiation.py

- `test_ce_qui_n_est_pas_dit_est_herite` — ligne 46
- `test_un_delta_vide_rend_le_parent_a_l_identique` — ligne 59
- `test_resoudre_ne_modifie_jamais_le_parent` — ligne 64
- `test_chaque_espace_de_noms_atteint_sa_cible` — ligne 79
- `test_l_espace_des_sous_jacents_sert_a_ajouter_un_titre` — ligne 84
- `test_un_chemin_inconnu_est_refuse` — ligne 98
- `test_retirer_un_sous_jacent_reduit_aussi_la_correlation` — ligne 109
- `test_le_parent_garde_ce_que_la_variante_retire` — ligne 120
- `test_on_ne_vide_pas_le_panier` — ligne 133
- `test_toucher_au_panier_est_refuse_sur_un_avenant` — ligne 147
- `test_le_meme_delta_passe_en_note_neuve` — ligne 157
- `test_les_ecarts_portent_l_avant_et_l_apres` — ligne 164
- `test_sans_ecart_il_n_y_a_rien_a_colorer` — ligne 178
- `test_un_delta_mal_forme_est_refuse` — ligne 192
- `test_une_variante_ne_copie_pas_le_contexte_de_son_origine` — ligne 253
- `test_la_variante_suit_son_origine` — ligne 277
- `test_les_variantes_ne_polluent_pas_la_liste_mais_s_y_comptent` — ligne 293
- `test_les_variantes_restent_a_plat` — ligne 307
- `test_un_titre_est_obligatoire` — ligne 320
- `test_un_delta_incoherent_est_refuse_a_la_creation` — ligne 328
- `test_l_api_rend_les_ecarts_prets_a_colorer` — ligne 338
- `test_modifier_une_variante_ne_touche_pas_l_origine` — ligne 349
- `test_une_variante_roll_ressort_deja_recalee` — ligne 368
- `test_avenant_et_roll_du_meme_delta_ne_donnent_pas_le_meme_produit` — ligne 388
- `test_la_liste_des_variantes_porte_ce_que_l_ecran_affiche` — ligne 412
- `test_le_contexte_rendu_a_la_forme_que_le_pricer_recharge` — ligne 427
- `test_la_liste_des_scripts_porte_le_compte_de_variantes` — ligne 435
- `test_une_declinaison_se_supprime_seule` — ligne 447
- `test_supprimer_une_origine_a_declinaisons_est_refuse` — ligne 464
- `test_la_cascade_explicite_emporte_les_declinaisons` — ligne 480
- `test_une_origine_sans_declinaison_se_supprime_comme_avant` — ligne 493
- `test_un_avenant_ne_deplace_pas_les_dates_du_passe` — ligne 503
- `test_un_avenant_peut_amender_le_reglement_final` — ligne 518
- `test_une_note_neuve_deplace_librement_ses_dates` — ligne 525
- `test_l_api_refuse_une_declinaison_qui_deplace_le_strike` — ligne 531
- `test_une_variante_n_expose_pas_une_origine_devenue_privee` — ligne 553
- `test_la_liste_ne_rend_pas_les_brouillons_des_autres` — ligne 584
- `test_la_cascade_n_emporte_pas_les_declinaisons_d_autrui` — ligne 605
- `test_le_put_generique_refuse_d_ecrire_un_contexte_de_variante` — ligne 638
- `test_la_fiche_d_une_variante_reste_modifiable` — ligne 658
- `test_une_origine_garde_le_droit_d_ecrire_son_contexte` — ligne 667
- `test_un_script_sauvegarde_conserve_la_provenance_ia_complete` — ligne 674

## backend/tests/test_variantes_roll.py

- `test_toutes_les_dates_glissent_du_meme_ecart` — ligne 58
- `test_le_tenor_est_preserve` — ligne 67
- `test_la_note_neuve_est_strikee_a_la_date_de_valorisation` — ligne 76
- `test_les_niveaux_du_term_sheet_d_origine_sont_purges` — ligne 84
- `test_une_date_fixee_par_le_delta_n_est_pas_decalee` — ligne 97
- `test_un_roll_peut_changer_le_panier` — ligne 109
- `test_rouler_une_note_pas_encore_emise_est_refuse` — ligne 119
- `test_une_valorisation_anterieure_au_strike_est_refusee` — ligne 128
- `test_un_avenant_ne_decale_rien` — ligne 135
- `test_la_note_neuve_price_au_voisinage_du_pair` — ligne 170
- `test_la_note_neuve_ne_reprend_aucun_etat_du_passe` — ligne 197
- `test_on_ajoute_un_titre_avec_sa_definition_entiere` — ligne 223
- `test_l_ajout_etend_la_matrice_de_correlation` — ligne 235
- `test_un_ajout_sans_correlation_est_refuse` — ligne 244
- `test_modifier_la_calibration_d_un_titre_herite_est_refuse` — ligne 254
- `test_remplacer_un_titre_en_bloc_est_refuse` — ligne 268
- `test_remplacer_un_titre_se_dit_en_un_retrait_et_un_ajout` — ligne 276
- `test_un_avenant_ne_touche_toujours_pas_au_panier` — ligne 289
- `test_un_titre_ajoute_garde_son_dividende_et_son_quanto` — ligne 297
- `test_un_script_ancien_dit_ce_qu_il_faut_faire` — ligne 326
- `test_une_date_de_valorisation_reellement_absente_le_dit_autrement` — ligne 341

## backend/tests/test_vol_model_validation.py

- `test_sabr_pde_reduces_to_black_scholes` — ligne 12
- `test_sabr_pde_reduces_to_absorbing_cev_including_zero_mass` — ligne 24
- `test_lsv_thin_tail_uses_neighbouring_conditional_variance` — ligne 37
- `test_lsv_conditional_variance_handles_tiny_sample_and_zero_variance` — ligne 49
- `test_sabr_downside_put_matches_spot_pde_reference_in_audited_regime` — ligne 55
- `test_lsv_flat_surface_does_not_create_spurious_deep_puts` — ligne 75
- `test_multi_asset_marginals_use_same_dynamics_as_correlated_mono` — ligne 101

## backend/tests/test_workflow_controls.py

- `test_booking_gate_rejects_independent_failures` — ligne 93
- `test_un_last_look_frais_passe_le_portillon` — ligne 109
- `test_aucune_etiquette_de_fermete_ne_bloque_le_booking` — ligne 119
- `test_booking_gate_rejects_no_selected_quote` — ligne 132
- `test_booking_gate_rejects_unmapped_provider` — ligne 137
- `test_booking_gate_rejects_counterparty_mismatch` — ligne 143
- `test_booking_gate_rejects_incomplete_terms` — ligne 156
- `test_booking_gate_accepts_complete_firm_fresh_request` — ligne 165
- `test_expired_selected_quote_is_visible_in_business_status` — ligne 170
- `test_manual_fixing_is_received_but_not_automatically_validated` — ligne 273
- `test_partial_manual_fixing_is_explicit` — ligne 283
- `test_incomplete_fixing_validation_is_rejected_and_audited` — ligne 290
- `test_complete_official_fixing_can_be_validated` — ligne 303
- `test_fixing_validation_requires_an_intact_archived_evidence_payload` — ligne 314
- `test_checker_can_download_the_verified_archived_evidence` — ligne 332
- `test_user_role_cannot_capture_an_official_fixing_candidate` — ligne 344
- `test_deal_owner_cannot_capture_even_when_role_is_ops_maker` — ligne 355
- `test_fixing_capture_requires_complete_actionable_provenance` — ligne 369
- `test_fixing_provider_must_match_the_client_account_source` — ligne 381
- `test_fixing_timestamp_offset_must_match_the_market_timezone` — ligne 393
- `test_fixing_maker_cannot_validate_own_submission` — ligne 406
- `test_fixing_checker_is_scoped_to_the_deal_entity` — ligne 422
- `test_fixing_correction_creates_a_new_immutable_version` — ligne 435
- `test_checker_can_reject_an_initial_fixing_candidate` — ligne 472
- `test_rejecting_a_correction_restores_the_previous_official_version` — ligne 488
- `test_a_second_correction_waits_for_the_checker_decision` — ligne 515
- `test_fixing_audit_contains_before_after_reason_and_source` — ligne 538
- `test_audit_failure_prevents_fixing_persistence` — ligne 553
- `test_validated_fixing_cannot_be_overwritten_and_creates_alert` — ligne 568
- `test_legacy_four_eyes_refresh_switches_to_automatic_fixings` — ligne 584
- `test_repeated_automatic_monitoring_applies_terminal_result_once` — ligne 606
- `test_refresh_error_is_visible_audited_and_alerted` — ligne 626
- `test_startup_migration_retires_four_eyes_and_stales_pending_proposal` — ligne 638
- `test_new_deal_schema_refuses_four_eyes_policy` — ligne 661
- `test_auto_yahoo_officializes_fixings_and_applies_terminal_lifecycle` — ligne 697
- `test_auto_yahoo_waits_for_same_day_close_without_manual_exception` — ligne 726
- `test_auto_yahoo_revision_never_overwrites_an_official_fixing` — ligne 748
- `test_auto_yahoo_never_bypasses_a_pending_human_exception` — ligne 781
- `test_auto_exception_owner_can_confirm_pending_human_value` — ligne 833
- `test_auto_exception_owner_can_explicitly_adopt_yahoo` — ligne 861
- `test_user_confirmed_exception_is_not_reopened_by_the_yahoo_feed` — ligne 885
- `test_auto_exception_resolution_is_refused_for_four_eyes_deal` — ligne 912
- `test_last_user_exception_replays_and_applies_terminal_lifecycle` — ligne 927
- `test_resolution_validation_requires_all_official_validated_fixings` — ligne 963
- `test_resolution_validation_requires_explicit_outcome_confirmation` — ligne 984
- `test_resolution_authorization_and_application_are_atomic` — ligne 995
- `test_resolution_application_is_exactly_once` — ligne 1012
- `test_resolution_rolls_back_authorization_and_application_if_audit_fails` — ligne 1029
- `test_resolution_rejection_rolls_back_the_intermediate_authorization` — ligne 1053
- `test_direct_post_booking_change_is_rejected_and_audited` — ligne 1095
- `test_amendment_request_is_persistent_but_does_not_change_deal` — ligne 1105
- `test_legacy_migration_marks_ambiguous_rows_for_manual_review` — ligne 1118
- `test_startup_creates_product_tables_before_upgrading_legacy_rows` — ligne 1163
- `test_la_maturite_se_lit_dans_le_calendrier_quand_il_existe` — ligne 1283
- `test_la_maturite_se_deduit_de_T_sans_calendrier` — ligne 1287
- `test_un_reglement_avant_la_maturite_est_signale` — ligne 1294
- `test_un_reglement_apres_la_maturite_ne_signale_rien` — ligne 1300
- `test_un_reglement_le_jour_meme_de_la_maturite_passe` — ligne 1308

## backend/tests/test_workflow_phase2.py

- `test_maturity_label_is_semantic_not_a_payout_threshold` — ligne 205
- `test_explicit_script_ki_state_drives_the_label` — ligne 212
- `test_path_dependent_official_replay_fails_closed` — ligne 222
- `test_partial_official_fixing_prefix_cannot_manufacture_maturity` — ligne 230
- `test_auto_yahoo_refresh_uses_official_replay_as_lifecycle_truth` — ligne 242
- `test_auto_yahoo_stops_before_observations_after_an_autocall` — ligne 289
- `test_admin_can_run_mtm_and_greeks_on_a_foreign_uat_deal` — ligne 354
- `test_admin_refresh_uses_current_scope_without_foreign_unbound_alerts` — ligne 368
- `test_admin_watchlist_includes_foreign_uat_deals` — ligne 389
- `test_watchlist_filters_on_commercial_ids_without_requiring_them` — ligne 406
- `test_watchlist_row_exposes_commercial_ids_without_changing_counterparty` — ligne 437
- `test_validation_freezes_official_replay_and_application_uses_it` — ligne 452
- `test_payout_difference_above_currency_tolerance_blocks_authorization` — ligne 472
- `test_deal_owner_cannot_authorize_own_lifecycle_resolution` — ligne 493
- `test_fixing_maker_cannot_authorize_resolution_that_consumes_own_fixing` — ligne 512
- `test_official_indicative_outcome_mismatch_blocks_validation` — ligne 532
- `test_amendment_requires_four_eyes_and_applies_exactly_once` — ligne 569
- `test_payment_amendment_versions_the_product_terms_and_execution` — ligne 611
- `test_commercial_attribution_always_requires_four_eyes` — ligne 648
- `test_amendment_is_carried_through_by_its_own_maker_by_default` — ligne 708
- `test_single_signature_mode_still_refuses_a_foreign_user` — ligne 754
- `test_amendment_checker_is_entity_scoped` — ligne 772
- `test_pricing_or_calendar_amendment_requires_rebooking` — ligne 789
- `test_deal_audit_timeline_is_owner_scoped_and_filterable` — ligne 809
- `test_deal_audit_timeline_excludes_rows_from_a_recycled_legacy_id` — ligne 826

## backend/tests/test_workshop_consultation.py

- `test_permissions_actor_boundary_and_missing_book` — ligne 49
- `test_viewer_never_opens_for_an_active_or_unprepared_campaign` — ligne 68
- `test_external_controller_lease_blocks_consultation` — ligne 76
- `test_live_viewer_blocks_ai_restart_and_retirement` — ligne 85
- `test_other_instance_identity_is_never_closed` — ligne 96
- `test_consultation_lease_blocks_restart_even_without_http_health` — ligne 113
- `test_native_viewer_preserves_books_campaign_and_reuses_its_process` — ligne 127

## backend/tests/test_workshop_diagnostic.py

- `test_calendar_zero_multiple_requests_and_distinct_requesters` — ligne 16
- `test_self_response_and_unavailable_requester_are_rejected` — ligne 27
- `test_funding_bound_variation_and_interpolation` — ligne 37
- `test_forecast_is_free_and_changes_with_workload_model_and_cadence` — ligne 45
- `test_pricing_paths_respect_native_pricer_minimum` — ligne 59
- `test_accepted_client_offer_uses_native_accept_quote_argument` — ligne 68
- `test_config_can_be_edited_only_before_first_run` — ligne 76
- `test_private_observation_and_dual_role_signatures` — ligne 85
- `test_three_native_payoffs_really_price_with_funding` — ligne 102
- `test_contract_event_does_not_open_the_next_month_early` — ligne 119
- `test_current_valuation_funding_preserves_booked_terms_and_units` — ligne 128
- `test_blocking_action_stops_and_preserves_evidence_without_repair` — ligne 143
- `test_roles_must_be_consistent_before_any_model_call` — ligne 161
- `test_recover_committed_quote_and_confirmation_without_repeating_writes` — ligne 168
- `test_reference_baseline_reuses_identities_without_copying_signing_keys` — ligne 184
- `test_cancelled_request_is_not_reported_as_a_structura_bug` — ligne 205
- `test_controller_advances_empty_months_and_schedules_each_request_once` — ligne 215

## backend/tests/test_workshop_historical.py

- `test_existing_cache_last_close_without_future_data_or_network` — ligne 17
- `test_defaults_historical_cutoff_and_no_repeated_decision_budget` — ligne 37
- `test_one_model_response_is_saved_before_execution_and_reused` — ligne 51
- `test_invalid_model_response_is_not_requested_again` — ligne 70
- `test_normal_athena_has_five_business_day_observations` — ligne 85
- `test_called_note_remains_a_receivable_until_its_payment` — ligne 104
- `test_closed_books_do_not_generate_repetitive_reviews` — ligne 114
- `test_manual_replay_stops_at_first_proven_call` — ligne 124
- `test_official_athena_replay_keeps_coupon_rank_and_payment` — ligne 141
- `test_controller_stops_at_cutoff_with_open_position` — ligne 168

## backend/tests/test_workshop_management.py

- `test_reset_creates_fresh_accounts_and_preserves_the_entire_previous_run` — ligne 46
- `test_delete_only_selected_campaign_and_keep_private_backup` — ligne 68
- `test_external_lease_blocks_management_even_when_saved_state_says_completed` — ligne 85
- `test_paused_local_controller_cannot_be_reset` — ligne 98
- `test_owner_and_child_boundaries_for_management` — ligne 107
- `test_failed_worker_shutdown_retains_campaign` — ligne 122
- `test_failed_reset_write_restores_old_campaign` — ligne 133
- `test_start_and_management_share_a_cross_process_guard` — ligne 144
- `test_retirement_cannot_return_cached_history_from_another_controller` — ligne 155
- `test_deleting_an_old_run_does_not_interrupt_another_live_campaign` — ligne 164
- `test_replay_keeps_previous_campaign_visible_and_creates_no_shared_data` — ligne 175
- `test_issue_review_survives_controller_save_and_is_exported` — ligne 191
- `test_issue_review_requires_evidence_note_and_respects_boundaries` — ligne 207

## backend/tests/test_workshop_openai.py

- `test_existing_key_is_used_for_json_decision_without_storing_response` — ligne 15
- `test_openai_duplicate_json_is_accepted_only_when_decisions_match` — ligne 44
- `test_budget_blocks_before_paid_call` — ligne 54
- `test_truncated_response_keeps_usage_and_is_retryable` — ligne 62
- `test_campaign_accounting_and_model_guards` — ligne 76
- `test_payoff_schedule_and_multiyear_maturity_use_existing_templates` — ligne 91
- `test_routine_setup_and_notification_only_do_not_consume_model_calls` — ligne 113
- `test_strict_openai_schema_keeps_native_tool_arguments` — ligne 128

## backend/tests/test_workshop_reconciliation.py

- `test_extra_booking_cannot_count_as_complete` — ligne 22
- `test_wrong_counterparty_and_wrong_actor_are_detected` — ligne 31
- `test_missing_evidence_is_not_filled_in_from_the_other_book` — ligne 40
- `test_matching_books_cannot_contradict_the_accepted_quote` — ligne 49
- `test_bank_does_not_receive_competitor_declines` — ligne 60
- `test_free_api_updates_native_relationships_and_bookings` — ligne 69
- `test_timeouts_distinguish_no_model_decision_from_an_uncertain_native_write` — ligne 84

