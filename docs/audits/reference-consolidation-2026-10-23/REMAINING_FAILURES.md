# Échecs documentés restant à instruire — 23 octobre 2026

**121 cas, 7 groupes. Aucun test exécuté pendant cette consolidation.** Chaque cas ci-dessous possède un échec conservé et aucun succès ultérieur de même identité dans les preuves disponibles. Il ne s’agit ni de 121 défauts indépendants, ni d’une reproduction sur la référence actuelle.

Les messages complets, les reproductions avant correction, les échecs initiaux suivis d’un succès et les identités remplacées sont conservés dans [FAILURE_INVENTORY.json](FAILURE_INVENTORY.json). La [synthèse de référence](../REFERENCE_CONSOLIDATION_2026-10-23.md) explique les limites de déduplication.

| Groupe | Cas | Fichier | Dépendances | Priorité proposée pour la prochaine étape |
|---|---:|---|---|---|
| [F01](#f01) | 1 | `backend/tests/test_amc_studies.py` | C02 | P2 |
| [F02](#f02) | 1 | `backend/tests/test_workflow_controls.py` | C06, C13, C19 | P1 |
| [F03](#f03) | 90 | `backend/tests/test_rfq.py` | C01, C03, C06, C08, C23 | P1 |
| [F04](#f04) | 9 | `backend/tests/test_uat_generation.py` | C05, C06, C13, C27 | P1 |
| [F05](#f05) | 5 | `backend/tests/test_product_analysis.py` | C01, C09 | P2 |
| [F06](#f06) | 14 | `backend/tests/test_client_chain.py` | C01, C03, C06, C24, C27 | P1 |
| [F07](#f07) | 1 | `backend/tests/test_fixings_releves.py` | C01, C13, C26 | P2 |

## F01

**Auth : fixture de mot de passe — 1 cas.**

Fixture de 11 caracteres rejetee avant de tester l ouverture publique. Aucun rejeu ulterieur conserve.

**Critère de sortie proposé :** Conserver le refus de registration publique ; utiliser des donnees conformes pour atteindre l assertion cible.

La priorité porte sur la prochaine instruction du groupe ; elle ne remplace pas les priorités des constats d’audit. Les critères ci-dessous sont des validations futures, sans exécution autorisée dans cette étape.

| Identité du cas, dans `backend/tests/test_amc_studies.py` | Dernier message observé | Preuve |
|---|---|---|
| `test_public_registration_requires_explicit_enable` | pydantic_core._pydantic_core.ValidationError: 1 validation error for RegisterRequest | [C11 / backend-followup.xml](../../../.runtime/diagnostic-acceptance/c11-2026-10-21/backend-followup.xml) |

## F02

**Migration minimale : table products absente — 1 cas.**

Reproduction isolee C13 ; distincte du test CCR corrige en C21.

**Critère de sortie proposé :** Decider si ce schema historique est supporte, puis verifier migration idempotente et gardes Product sans les supprimer.

La priorité porte sur la prochaine instruction du groupe ; elle ne remplace pas les priorités des constats d’audit. Les critères ci-dessous sont des validations futures, sans exécution autorisée dans cette étape.

| Identité du cas, dans `backend/tests/test_workflow_controls.py` | Dernier message observé | Preuve |
|---|---|---|
| `test_legacy_migration_marks_ambiguous_rows_for_manual_review` | sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such table: main.products | [C13 / backend-second.xml](../../../.runtime/diagnostic-acceptance/c13-2026-10-21/backend-second.xml) |

## F03

**RFQ historiques : autorisations, motifs et identite juridique — 90 cas.**

90 echecs reproduits avant C19. Fixtures anciennes ; certaines attentes doivent etre rapprochees des regles retenues.

**Critère de sortie proposé :** Qualifier acteurs/desks, motifs et contreparties, garder les refus, la confidentialite, les versions et l idempotence ; un booking hors referentiel requiert l exception D01.

La priorité porte sur la prochaine instruction du groupe ; elle ne remplace pas les priorités des constats d’audit. Les critères ci-dessous sont des validations futures, sans exécution autorisée dans cette étape.

| Identité du cas, dans `backend/tests/test_rfq.py` | Dernier message observé | Preuve |
|---|---|---|
| `test_a_booked_rfq_never_falls_back` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_a_booked_rfq_points_at_its_deal` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_a_broken_calendar_is_not_rescued_by_pricing_times` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_a_counterparty_outside_the_catalog_stays_accepted` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_a_coupon_calendar_shorter_than_the_note_keeps_the_notes_maturity` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_a_deal_booked_outside_any_tender_has_no_provenance` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_a_deal_with_no_observation_at_all_is_refused` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_a_last_look_that_degrades_is_read_the_other_way_on_a_sell` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_a_last_look_that_degrades_the_price_is_refused` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_a_negative_model_price_is_refused` | AssertionError: assert 403 == 422 | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_an_answered_last_look_supersedes_its_parent` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_an_rfq_cannot_be_booked_twice` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_an_rfq_without_a_booked_deal_stays_deletable` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_an_unanswered_last_look_supersedes_nothing` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_an_unresolvable_script_is_refused_even_with_client_times` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_annotating_a_booked_tender_stays_possible` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_accepts_a_forward_start_paid_before_its_strike` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_conforme_fige_un_hash_des_termes_rfq` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_freezes_selection_reason_and_every_final_response` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_freezes_the_competitive_picture_on_the_deal` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_from_an_rfq_links_deal_and_closes_the_rfq` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_from_an_rfq_without_a_retained_quote_is_refused` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_never_reuses_a_deal_id_retained_by_the_audit_trail` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_refuse_un_autre_produit_sous_le_meme_rfq_id` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_refuses_what_is_not_a_trade[contrepartie vide-over5-contrepartie]` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_refuses_what_is_not_a_trade[fair value n\xe9gative-over3-fair value]` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_refuses_what_is_not_a_trade[fair value nulle-over2-fair value]` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_refuses_what_is_not_a_trade[nominal n\xe9gatif-over1-nominal]` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_refuses_what_is_not_a_trade[nominal nul-over0-nominal]` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_refuses_what_is_not_a_trade[prix trait\xe9 nul-over4-prix trait\xe9]` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_refuses_what_is_not_a_trade[r\xe8glement avant maturit\xe9-over6-r\xe8glement]` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_rejects_an_unknown_rfq_id` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_rejects_another_users_rfq` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_uses_the_rfq_commercial_and_legal_context_as_authority[Autocall-Autocall]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_booking_uses_the_rfq_commercial_and_legal_context_as_authority[Phoenix-None]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_calendrier_post_maturite_est_refuse` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_changing_the_selected_quote_does_not_reuse_the_previous_reason` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_clearing_a_price_takes_the_rfq_back_to_envoyee` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_datetime_avec_offset_est_normalise_en_utc` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_deleted_rfq_and_quote_ids_are_never_reused_by_sqlite` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_deleting_a_quote_cascades_to_its_last_look_child` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_deleting_an_rfq_a_deal_was_booked_from_is_refused` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_deleting_the_selected_quote_clears_the_selection` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_deleting_the_selected_quote_takes_the_rfq_back_too` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_deselecting_a_quote_takes_the_rfq_back_to_cotee` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_deux_ans_de_coupons_sur_une_note_a_trois_ans_se_booke` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_history_flags_the_winner_only_once_the_deal_is_booked` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_history_reports_edge_alongside_the_raw_spread` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_last_look_cannot_be_reverted_once_answered` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_last_look_creates_nested_child_quote` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_last_look_ne_peut_pas_devenir_une_chaine_cachee` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_le_booking_qualifie_une_quote_a_qualifier` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_le_pricer_reprend_le_contrat_canonique_du_product_de_la_rfq` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_le_refus_vaut_aussi_a_la_modification` | AssertionError: assert 403 == 422 | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_maturity_lands_on_the_deals_own_maturity_date` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_multi_underlying_repricing_cannot_replace_the_matrix_with_an_incomplete_one` | AssertionError: assert 403 == 422 | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_multi_underlying_rfq_reaches_the_deal_without_losing_market_inputs` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_observations_are_derived_without_any_pricing` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_provenance_keeps_only_final_quotes_as_competition` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_quote_prices_are_percentage_points[-50.0-nul ou n\xe9gatif]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_quote_prices_are_percentage_points[0.0-nul ou n\xe9gatif]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_quote_prices_are_percentage_points[10000.0-invraisemblable]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_quote_row_carries_the_resolved_counterparty` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_quoted_at_round_trips_without_timezone_shift` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_quotes_sorted_by_response_time_not_add_order` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_reference_numbering_survives_a_deletion` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_rfq_contract_change_creates_a_product_terms_version` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_rfq_provider_contacts_are_admin_managed_and_offered_on_rfq` | pydantic_core._pydantic_core.ValidationError: 1 validation error for RfqProviderCreate | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_sans_suite_is_terminal_until_reopened` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_selecting_a_quote_from_another_rfq_is_rejected` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_selecting_an_expired_quote_is_rejected` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_selecting_an_unpriced_quote_is_rejected` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_status_cannot_be_posed_by_hand_beyond_sans_suite` | AssertionError: assert 403 == 422 | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_status_follows_the_tender_from_draft_to_retenue` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_termes_contractuels_rfqs_sont_figes_apres_sollicitation` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_the_competitive_record_is_frozen_once_the_tender_traded[ajouter un fournisseur apr\xe8s coup-<lambda>]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_the_competitive_record_is_frozen_once_the_tender_traded[d\xe9s\xe9lectionner la gagnante-<lambda>]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_the_competitive_record_is_frozen_once_the_tender_traded[inverser le sens de l'AO-<lambda>]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_the_competitive_record_is_frozen_once_the_tender_traded[r\xe9\xe9crire le prix de la gagnante-<lambda>]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_the_competitive_record_is_frozen_once_the_tender_traded[r\xe9\xe9crire le prix mod\xe8le-<lambda>]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_the_competitive_record_is_frozen_once_the_tender_traded[reclasser sans suite-<lambda>]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_the_competitive_record_is_frozen_once_the_tender_traded[supprimer la gagnante-<lambda>]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_the_contractual_calendar_wins_over_the_simulation_grid` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_the_same_provider_cannot_be_solicited_twice_on_one_tender` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_the_winner_survives_every_refused_mutation` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_un_autre_contrat_reste_refuse_au_booking_de_la_rfq[fenetre_de_constatation-constats]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_un_autre_contrat_reste_refuse_au_booking_de_la_rfq[frequence-constats]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_un_autre_contrat_reste_refuse_au_booking_de_la_rfq[maturite_un_jour_plus_tard-T]` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_une_quote_deja_ferme_ne_doit_rien_au_booking` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_une_quote_indicative_se_booke_et_laisse_sa_trace` | fastapi.exceptions.HTTPException: 403: Habilitation RFQ insuffisante pour cette action | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |

## F04

**Generateur UAT : liens Product, S0 et dependances — 9 cas.**

9 echecs reproduits avec le lanceur Windows corrige. Cause applicative ou fixture encore a isoler.

**Critère de sortie proposé :** Prouver les versions Product valides, les S0 et clotures, les huit profils et le nettoyage isole, sans toucher aux donnees Production.

La priorité porte sur la prochaine instruction du groupe ; elle ne remplace pas les priorités des constats d’audit. Les critères ci-dessous sont des validations futures, sans exécution autorisée dans cette étape.

| Identité du cas, dans `backend/tests/test_uat_generation.py` | Dernier message observé | Preuve |
|---|---|---|
| `test_complete_mix_covers_all_eight_profiles_and_cleans_terminal_dependencies` | assert None | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_every_reached_observation_carries_its_real_close[ACTIVE_1Y_PENDING-ATHENA]` | AssertionError: pas de S0 : la surveillance des barrières ne peut rien calculer | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_every_reached_observation_carries_its_real_close[ACTIVE_2Y_OFFICIAL-PHOENIX]` | AssertionError: pas de S0 : la surveillance des barrières ne peut rien calculer | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_every_reached_observation_carries_its_real_close[CALLED-ATHENA]` | AssertionError: pas de S0 : la surveillance des barrières ne peut rien calculer | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_every_reached_observation_carries_its_real_close[CURRENT_ACTIVE-ATHENA]` | AssertionError: pas de S0 : la surveillance des barrières ne peut rien calculer | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_every_reached_observation_carries_its_real_close[MATURED_FINAL-CAPITAL_GUARANTEED]` | AssertionError: pas de S0 : la surveillance des barrières ne peut rien calculer | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_every_reached_observation_carries_its_real_close[MATURED_KI-REVERSE_CONVERTIBLE]` | AssertionError: pas de S0 : la surveillance des barrières ne peut rien calculer | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_every_reached_observation_carries_its_real_close[MATURED_PENDING-REVERSE_CONVERTIBLE]` | AssertionError: pas de S0 : la surveillance des barrières ne peut rien calculer | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |
| `test_full_chain_uses_uat_references_and_batch_cleanup_is_isolated` | sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) Version Product canonique valide requise | [C19 / dependencies.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/dependencies.xml) |

## F05

**Analyse produit : habilitation avant assertions HTTP — 5 cas.**

5 echecs reproduits avant C19, HTTP 403 au lieu du comportement cible.

**Critère de sortie proposé :** Employer un acteur autorise pour les cas 200/422 et conserver des cas explicites 401/403 ; aucun elargissement des permissions.

La priorité porte sur la prochaine instruction du groupe ; elle ne remplace pas les priorités des constats d’audit. Les critères ci-dessous sont des validations futures, sans exécution autorisée dans cette étape.

| Identité du cas, dans `backend/tests/test_product_analysis.py` | Dernier message observé | Preuve |
|---|---|---|
| `test_l_apercu_n_appelle_pas_le_modele` | assert 403 == 200 | [C19 / consumers.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/consumers.xml) |
| `test_l_api_refuse_en_422_pas_en_500[charge0]` | AssertionError: assert 403 == 422 | [C19 / consumers.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/consumers.xml) |
| `test_l_api_refuse_en_422_pas_en_500[charge1]` | AssertionError: assert 403 == 422 | [C19 / consumers.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/consumers.xml) |
| `test_l_api_refuse_en_422_pas_en_500[charge2]` | AssertionError: assert 403 == 422 | [C19 / consumers.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/consumers.xml) |
| `test_les_intentions_exposees_sont_celles_qui_existent` | assert 403 == 200 | [C19 / consumers.xml](../../../.runtime/diagnostic-acceptance/c19-2026-10-21/consumers.xml) |

## F06

**Chaine CRM : desk pilote, contrepartie et rattachements — 14 cas.**

14 echecs identiques avant/apres C24 ; certains KeyError et refus sont en cascade.

**Critère de sortie proposé :** Atteindre les assertions avec contexte juridique et desk valides ; verifier isolation, rattachement, suppression et atomicite sans masquer les echecs de creation.

La priorité porte sur la prochaine instruction du groupe ; elle ne remplace pas les priorités des constats d’audit. Les critères ci-dessous sont des validations futures, sans exécution autorisée dans cette étape.

| Identité du cas, dans `backend/tests/test_client_chain.py` | Dernier message observé | Preuve |
|---|---|---|
| `test_l_opportunite_liee_a_un_trade_refuse_la_suppression` | assert 204 == 409 | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |
| `test_la_chaine_se_remonte_du_trade_jusqu_a_la_personne` | KeyError: 'opportunity_id' | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |
| `test_le_refus_de_rattachement_n_alloue_pas_de_reference` | KeyError: 'reference' | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |
| `test_le_trade_reste_chez_l_ancien_employeur_apres_un_depart` | KeyError: 'id' | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |
| `test_un_deal_booke_depuis_une_opportunite_porte_son_rattachement` | AssertionError: {"detail":"Identifiant de contrepartie juridique actif requis ; qualifiez le référentiel."} | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |
| `test_un_deal_direct_client_exige_un_motif` | TypeError: string indices must be integers, not 'str' | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |
| `test_un_deal_produit_peut_porter_une_structure_juridique_sans_client` | AssertionError: {"detail":"Identifiant de contrepartie juridique actif requis ; qualifiez le référentiel."} | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |
| `test_un_deal_sans_client_se_booke_comme_avant` | AssertionError: {"detail":"Identifiant de contrepartie juridique actif requis ; qualifiez le référentiel."} | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |
| `test_un_trade_ne_peut_pas_melanger_deux_clients` | assert 'Bank B' in '{"detail":"Identifiant de contrepartie juridique actif requis ; qualifiez le référentiel."}' | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |
| `test_une_opportunite_d_une_autre_entite_est_refusee` | assert 422 == 404 | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |
| `test_une_rfq_client_sans_mandat_est_refusee` | TypeError: string indices must be integers, not 'str' | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |
| `test_une_rfq_creee_depuis_une_opportunite_garde_le_lien` | AssertionError: {"detail":"Choisissez un desk pilote habilité pour votre organisation."} | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |
| `test_une_rfq_directe_peut_etre_rattachee_au_client_et_au_mandat` | AssertionError: {"detail":"Choisissez un desk pilote habilité pour votre organisation."} | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |
| `test_une_rfq_sans_opportunite_fonctionne_comme_avant` | AssertionError: {"detail":"Choisissez un desk pilote habilité pour votre organisation."} | [C24 / legacy-chain-final.xml](../../../.runtime/diagnostic-acceptance/c24-2026-10-22/legacy-chain-final.xml) |

## F07

**Releves : utilisateur sans role — 1 cas.**

Meme AttributeError avant/apres C26.

**Critère de sortie proposé :** Qualifier acteur et acces ; verifier les releves sous strike et la priorite du registre officiel sans court-circuiter C01.

La priorité porte sur la prochaine instruction du groupe ; elle ne remplace pas les priorités des constats d’audit. Les critères ci-dessous sont des validations futures, sans exécution autorisée dans cette étape.

| Identité du cas, dans `backend/tests/test_fixings_releves.py` | Dernier message observé | Preuve |
|---|---|---|
| `test_la_fenetre_de_depart_a_ses_releves_bookes_sous_le_strike` | AttributeError: 'types.SimpleNamespace' object has no attribute 'role' | [C26 / final-backend.xml](../../../.runtime/diagnostic-acceptance/c26-2026-10-22/final-backend.xml) |

## Échecs historiques séparés du solde

- 337 identités ont une preuve XML ultérieure de succès ; leurs échecs initiaux restent consultables. Ce total utilise aussi les anciens journaux, pas seulement les XML initialement en échec.
- 10 anciens échecs identifiés dans les seuls journaux C01-C03 ont une résolution documentée au niveau fichier ou union ; aucun résultat machine par cas n’est inventé.
- 3 anciennes identités en échec ont été retirées ou remplacées : attente de choc nul implicite C21, semis AXA réécrivant silencieusement le ticker C03, ancien parcours de rafraîchissement administrateur C03. Leur retrait ne vaut pas un succès de la même identité ; les tests remplaçants restent distincts.
- La migration minimale F02 n’est pas le test de migration CCR corrigé dans C21. Les deux restent identifiés séparément.
- Les reproductions RED et essais avec fixture/lanceur invalide ne sont pas ajoutés au solde comme de nouvelles régressions.
- Le frontend a une preuve globale ultérieure de 731 succès dans 82 fichiers, mais pas la liste de toutes les identités de succès ; ses 10 libellés historiques en échec/collection sont conservés séparément dans EVIDENCE_INVENTORY.json.
