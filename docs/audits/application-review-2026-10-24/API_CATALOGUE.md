# Catalogue statique des routes API

Extraction de décorateurs, sans démarrer FastAPI ni générer son OpenAPI.

Une ligne est une déclaration de route. Les méthodes `API_ROUTE` portent une liste de méthodes.
Les préfixes APIRouter simples sont précomposés. Les alias, fabriques imbriquées, montages et conditions restent à lire dans les déclarations ci-dessous.
Le routeur de l'atelier est monté sous `/api/agent-workshop` et `/api/admin/agent-workshop` ; ses chemins locaux ne sont pas des URL racine.
L'authentification peut être héritée d'un routeur ou de ses dépendances ; son absence dans une signature n'est pas une preuve de route publique.

## backend/app/api/admin.py

```python
router = APIRouter(prefix='/api/admin', tags=['admin'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/admin/uat-generator/config` | `uat_generator_config` | 98 |
| GET | `/api/admin/uat-generator/batches` | `uat_generator_batches` | 106 |
| POST | `/api/admin/uat-generator/preview` | `uat_generator_preview` | 114 |
| POST | `/api/admin/uat-generator/batches` | `uat_generator_create` | 123 |
| DELETE | `/api/admin/uat-generator/batches/{batch_id}` | `uat_generator_delete` | 132 |
| GET | `/api/admin/rfq-providers` | `list_rfq_providers` | 143 |
| POST | `/api/admin/rfq-providers` | `create_rfq_provider` | 153 |
| PATCH | `/api/admin/rfq-providers/{provider_id}` | `update_rfq_provider` | 175 |
| DELETE | `/api/admin/rfq-providers/{provider_id}` | `delete_rfq_provider` | 206 |
| GET | `/api/admin/rfq-providers/{provider_id}/contacts` | `list_rfq_provider_contacts` | 224 |
| POST | `/api/admin/rfq-providers/{provider_id}/contacts` | `create_rfq_provider_contact` | 237 |
| PATCH | `/api/admin/rfq-providers/{provider_id}/contacts/{contact_id}` | `update_rfq_provider_contact` | 260 |
| GET | `/api/admin/counterparties` | `list_counterparties` | 323 |
| POST | `/api/admin/counterparties` | `create_counterparty` | 332 |
| PATCH | `/api/admin/counterparties/{cpty_id}` | `update_counterparty` | 353 |
| DELETE | `/api/admin/counterparties/{cpty_id}` | `delete_counterparty` | 400 |
| GET | `/api/admin/browse` | `browse_tables` | 420 |
| GET | `/api/admin/browse/{table_key}` | `browse_table_rows` | 425 |
| GET | `/api/admin/browse/{table_key}/{row_id}` | `browse_get_row` | 442 |
| DELETE | `/api/admin/browse/{table_key}/{row_id}` | `browse_delete_row` | 453 |
| POST | `/api/admin/browse/{table_key}/delete` | `browse_delete_rows` | 468 |
| PATCH | `/api/admin/browse/{table_key}/{row_id}` | `browse_update_row` | 490 |
| GET | `/api/admin/users` | `list_users` | 529 |
| POST | `/api/admin/users` | `create_user` | 541 |
| PATCH | `/api/admin/users/{user_id}` | `update_user` | 569 |
| POST | `/api/admin/users/{user_id}/revoke-sessions` | `revoke_sessions` | 617 |
| POST | `/api/admin/users/{user_id}/reset-password` | `reset_password` | 627 |
| GET | `/api/admin/entities` | `list_entities` | 655 |
| POST | `/api/admin/entities` | `create_entity` | 667 |
| PATCH | `/api/admin/entities/{entity_id}` | `update_entity` | 688 |
| GET | `/api/admin/market-data` | `market_data_catalog` | 792 |
| POST | `/api/admin/market-data/fetch` | `market_data_fetch` | 816 |
| GET | `/api/admin/underlyings` | `list_underlyings` | 863 |
| GET | `/api/admin/underlyings/search` | `search_underlyings` | 875 |
| POST | `/api/admin/underlyings` | `create_underlying` | 887 |
| PATCH | `/api/admin/underlyings/{underlying_id}` | `update_underlying` | 946 |
| DELETE | `/api/admin/underlyings/{underlying_id}` | `delete_underlying` | 988 |
| POST | `/api/admin/underlyings/{underlying_id}/revalidate` | `revalidate_underlying` | 1006 |

## backend/app/api/agent_workshop.py

```python
routes = APIRouter(tags=['AI user acceptance'], dependencies=[Depends(controller_only)])
```

```python
router = APIRouter()
```

```python
admin_router = APIRouter(dependencies=[Depends(get_current_admin)])
```

Montages déclarés :

- Ligne 196 : `router.include_router(routes, prefix='/api/agent-workshop')`
- Ligne 198 : `admin_router.include_router(routes, prefix='/api/admin/agent-workshop')`

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `` | `listing` | 34 |
| GET | `/models` | `models` | 44 |
| POST | `` | `create` | 69 |
| GET | `/defaults` | `defaults` | 75 |
| POST | `/preview` | `preview_scenario` | 81 |
| PATCH | `/{key}/configuration` | `configure` | 88 |
| GET | `/{key}` | `detail` | 97 |
| POST | `/{key}/{action}` | `command` | 102 |
| POST | `/{key}/consultations/{actor}` | `open_consultation` | 134 |
| DELETE | `/{key}/consultations/{actor}` | `close_consultation` | 145 |
| PATCH | `/{key}/issues/{issue_id}` | `review_issue` | 156 |
| DELETE | `/{key}` | `delete` | 169 |
| GET | `/{key}/export` | `export` | 179 |
| GET | `/{key}/screenshots/{filename}` | `screenshot` | 186 |

## backend/app/api/alerts.py

```python
router = APIRouter(prefix='/api/alerts', tags=['alerts'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/alerts/scheduler-runs` | `list_scheduler_runs` | 55 |
| GET | `/api/alerts` | `list_alerts` | 76 |
| POST | `/api/alerts/{alert_id}/read` | `mark_read` | 93 |
| POST | `/api/alerts/read-all` | `mark_all_read` | 108 |
| POST | `/api/alerts/refresh-book` | `refresh_whole_book` | 122 |

## backend/app/api/amc.py

```python
router = APIRouter(prefix='/api/amc', tags=['amc'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/amc/ff-series` | `list_ff_series` | 39 |
| GET | `/api/amc/ff-status` | `get_ff_status` | 44 |
| POST | `/api/amc/ff-refresh` | `refresh_ff` | 50 |
| GET | `/api/amc/benchmarks` | `list_benchmarks` | 66 |
| POST | `/api/amc/upload` | `upload_amc` | 71 |
| POST | `/api/amc/analyze` | `analyze` | 104 |
| POST | `/api/amc/export-pdf` | `export_pdf` | 130 |
| POST | `/api/amc/synthesize/payload` | `get_synthesis_payload` | 170 |
| POST | `/api/amc/synthesize/prompt` | `preview_synthesis` | 194 |
| POST | `/api/amc/synthesize` | `synthesize_study` | 199 |
| GET | `/api/amc/synthesize/ollama-models` | `get_ollama_models` | 211 |
| GET | `/api/amc/study/doc` | `study_doc` | 246 |
| GET | `/api/amc/study/template` | `study_template` | 252 |
| POST | `/api/amc/study/detect` | `study_detect` | 258 |
| POST | `/api/amc/manager-skill` | `compute_manager_skill` | 285 |
| POST | `/api/amc/marketshocks` | `compute_market_shocks_endpoint` | 306 |
| POST | `/api/amc/study/run` | `study_run` | 334 |
| POST | `/api/amc/study/export-pdf` | `study_export_pdf` | 356 |

## backend/app/api/amc_prices.py

```python
router = APIRouter(prefix='/api/amc/prices', tags=['amc-prices'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/amc/prices/status` | `get_price_status` | 26 |
| GET | `/api/amc/prices/spot` | `get_spot_on_date` | 34 |
| POST | `/api/amc/prices/status-for-study` | `get_price_status_for_study` | 47 |
| POST | `/api/amc/prices/resolve-tickers` | `resolve_tickers_endpoint` | 65 |
| POST | `/api/amc/prices/fetch` | `fetch_underlying` | 94 |
| POST | `/api/amc/prices/upload` | `upload_underlying` | 110 |
| DELETE | `/api/amc/prices/{key}` | `delete_underlying` | 137 |
| POST | `/api/amc/prices/attribution` | `compute_attribution_endpoint` | 170 |
| POST | `/api/amc/prices/brinson` | `compute_brinson_endpoint` | 199 |

## backend/app/api/amc_studies.py

```python
router = APIRouter(prefix='/api/amc/studies', tags=['amc-studies'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/amc/studies` | `list_studies` | 54 |
| GET | `/api/amc/studies/{study_id}` | `get_study` | 67 |
| POST | `/api/amc/studies` | `create_study` | 79 |
| DELETE | `/api/amc/studies/{study_id}` | `delete_study` | 112 |
| GET | `/api/amc/studies/{study_id}/archive` | `export_study_archive` | 126 |
| GET | `/api/amc/studies/{study_id}/compare/{other_id}` | `compare_studies` | 137 |

## backend/app/api/auth.py

```python
router = APIRouter(prefix='/api/auth', tags=['auth'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/auth/password` | `change_password` | 193 |
| POST | `/api/auth/logout` | `logout` | 210 |
| POST | `/api/auth/logout-all` | `logout_all` | 224 |
| GET | `/api/auth/options` | `login_options` | 254 |
| GET | `/api/auth/identity` | `login_identity` | 262 |
| POST | `/api/auth/development-admin-session` | `development_admin_session` | 268 |
| POST | `/api/auth/login` | `login` | 274 |
| POST | `/api/auth/development-session` | `development_session` | 314 |
| GET | `/api/auth/me` | `me` | 342 |
| POST | `/api/auth/register` | `register` | 380 |

## backend/app/api/ccr.py

```python
router = APIRouter(prefix='/api/ccr', tags=['CCR'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/ccr/schemas` | `schemas` | 23 |
| GET | `/api/ccr/counterparties` | `counterparties` | 34 |
| GET | `/api/ccr/counterparties/{cpty_id}/configuration` | `configuration` | 41 |
| POST | `/api/ccr/counterparties/{cpty_id}/{kind}` | `create_configuration` | 46 |
| PUT | `/api/ccr/counterparties/{cpty_id}/{kind}/{row_id}` | `update_configuration` | 54 |
| GET | `/api/ccr/deals` | `deals` | 62 |
| GET | `/api/ccr/uat-batches` | `uat_batches` | 77 |
| POST | `/api/ccr/diagnostic` | `diagnostic` | 84 |
| GET | `/api/ccr/portfolios` | `portfolios` | 89 |
| PUT | `/api/ccr/deals/{deal_id}/assignment` | `assign_deal` | 101 |
| POST | `/api/ccr/calculate` | `run_calculation` | 121 |
| GET | `/api/ccr/runs/{run_id}` | `get_run` | 142 |
| POST | `/api/ccr/runs/{run_id}/replay` | `replay` | 151 |
| GET | `/api/ccr/monitor` | `monitor` | 158 |
| GET | `/api/ccr/rfq/{rfq_id}/quotes/{quote_id}/context` | `rfq_credit_context` | 202 |
| POST | `/api/ccr/rfq/{rfq_id}/quotes/{quote_id}/check` | `rfq_check` | 208 |

## backend/app/api/client_import.py

```python
router = APIRouter(prefix='/api/client-import', tags=['client-import'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/client-import/template.xlsx` | `modele_excel` | 60 |
| GET | `/api/client-import/template.json` | `modele_json_` | 71 |
| GET | `/api/client-import/schema` | `schema` | 80 |
| POST | `/api/client-import/preview` | `apercu` | 96 |
| POST | `/api/client-import/apply` | `verser` | 114 |
| GET | `/api/client-import/batches` | `lots` | 155 |
| POST | `/api/client-import/batches/{batch_id}/revert` | `annuler_lot` | 174 |

## backend/app/api/client_intelligence.py

```python
router = APIRouter(prefix='/api/client-intelligence', tags=['client-intelligence'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/client-intelligence/clients/{client_id}` | `lecture_client` | 38 |
| GET | `/api/client-intelligence/persons/{person_id}` | `lecture_personne` | 64 |
| GET | `/api/client-intelligence/affiliations/{affiliation_id}` | `lecture_affiliation` | 77 |
| GET | `/api/client-intelligence/signals` | `signaux` | 112 |
| GET | `/api/client-intelligence/analytics` | `analytiques` | 142 |
| GET | `/api/client-intelligence/overview` | `apercu` | 265 |

## backend/app/api/clients.py

```python
router = APIRouter(prefix='/api/clients', tags=['clients'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/clients` | `list_clients` | 345 |
| GET | `/api/clients/{client_id}` | `get_client` | 400 |
| GET | `/api/clients/{client_id}/contacts` | `list_client_contacts` | 409 |
| GET | `/api/clients/{client_id}/mandates` | `list_client_mandates` | 447 |
| POST | `/api/clients/{client_id}/mandates` | `create_client_mandate` | 472 |
| PATCH | `/api/clients/{client_id}/mandates/{mandate_id}` | `update_client_mandate` | 511 |
| GET | `/api/clients/{client_id}/duplicates` | `check_client_duplicates` | 560 |
| POST | `/api/clients` | `create_client` | 575 |
| PATCH | `/api/clients/{client_id}` | `update_client` | 630 |
| PATCH | `/api/clients/{client_id}/scalar-constraints` | `update_scalar_constraints` | 694 |
| GET | `/api/clients/{client_id}/constraints/schema` | `constraints_schema` | 746 |
| GET | `/api/clients/{client_id}/scoped-preferences/schema` | `scoped_preferences_schema` | 791 |
| PUT | `/api/clients/{client_id}/scoped-preferences` | `replace_scoped_preferences` | 834 |
| GET | `/api/clients/{client_id}/preference-history` | `get_preference_history` | 910 |
| PUT | `/api/clients/{client_id}/constraints` | `replace_constraints` | 926 |
| PUT | `/api/clients/{client_id}/coverage` | `upsert_coverage` | 986 |
| DELETE | `/api/clients/{client_id}/coverage/{user_id}` | `remove_coverage` | 1021 |
| POST | `/api/clients/{client_id}/archive` | `archive_client` | 1044 |
| POST | `/api/clients/{client_id}/reactivate` | `reactivate_client` | 1064 |
| DELETE | `/api/clients/{client_id}` | `delete_client` | 1085 |

## backend/app/api/compute.py

```python
router = APIRouter(prefix='/api/compute', tags=['compute'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/compute/batches` | `create_batch` | 73 |
| GET | `/api/compute/batches` | `list_batches` | 94 |
| GET | `/api/compute/batches/{batch_id}` | `get_batch` | 106 |
| GET | `/api/compute/admin/batches` | `admin_list_batches` | 130 |
| DELETE | `/api/compute/admin/batches/{batch_id}` | `admin_delete_batch` | 147 |
| POST | `/api/compute/admin/batches/{batch_id}/stop` | `admin_stop_batch` | 157 |
| POST | `/api/compute/admin/batches/{batch_id}/relaunch` | `admin_relaunch_batch` | 172 |

## backend/app/api/constraint_definitions.py

```python
router = APIRouter(prefix='/api/constraint-definitions', tags=['constraint-definitions'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/constraint-definitions/meta` | `meta` | 104 |
| GET | `/api/constraint-definitions` | `list_definitions` | 120 |
| POST | `/api/constraint-definitions` | `create_definition` | 143 |
| PATCH | `/api/constraint-definitions/{definition_id}` | `update_definition` | 175 |
| DELETE | `/api/constraint-definitions/{definition_id}` | `archive_definition` | 211 |
| POST | `/api/constraint-definitions/{definition_id}/restore` | `restore_definition` | 238 |
| GET | `/api/constraint-definitions/catalog/{catalog}` | `read_catalog` | 261 |

## backend/app/api/deals.py

```python
router = APIRouter(prefix='/api/deals', tags=['deals'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/deals/next-ref` | `next_ref` | 1617 |
| POST | `/api/deals` | `book_deal` | 2448 |
| PUT | `/api/deals/{deal_id}/portfolios` | `set_deal_portfolios` | 2491 |
| PATCH | `/api/deals/{deal_id}/portfolio` | `assign_deal_portfolio` | 2531 |
| GET | `/api/deals` | `list_deals` | 2559 |
| GET | `/api/deals/counterparties` | `eligible_counterparties` | 2586 |
| GET | `/api/deals/watchlist` | `watchlist` | 2600 |
| GET | `/api/deals/amendment-requests/pending` | `pending_amendment_requests` | 2889 |
| GET | `/api/deals/{deal_id}` | `get_deal` | 2917 |
| GET | `/api/deals/{deal_id}/audit` | `get_deal_audit` | 2972 |
| PATCH | `/api/deals/{deal_id}` | `update_deal` | 3045 |
| POST | `/api/deals/{deal_id}/amendment-requests` | `request_amendment` | 3093 |
| POST | `/api/deals/{deal_id}/amendment-requests/{request_id}/approve` | `approve_amendment` | 3198 |
| POST | `/api/deals/{deal_id}/amendment-requests/{request_id}/reject` | `reject_amendment` | 3266 |
| POST | `/api/deals/{deal_id}/amendment-requests/{request_id}/apply` | `apply_amendment` | 3304 |
| PATCH | `/api/deals/{deal_id}/events/{event_id}` | `update_event` | 3521 |
| POST | `/api/deals/{deal_id}/events/{event_id}/validate` | `validate_fixing` | 3797 |
| GET | `/api/deals/{deal_id}/events/{event_id}/fixing-versions/{version_id}/evidence` | `download_fixing_evidence` | 4050 |
| POST | `/api/deals/{deal_id}/events/{event_id}/reject` | `reject_fixing` | 4107 |
| POST | `/api/deals/{deal_id}/events/refresh` | `refresh_events` | 4433 |
| POST | `/api/deals/{deal_id}/events/{event_id}/resolve-auto-exception` | `resolve_auto_fixing_exception` | 4865 |
| POST | `/api/deals/{deal_id}/lifecycle-proposals/{proposal_id}/validate` | `validate_lifecycle_proposal` | 6107 |
| POST | `/api/deals/{deal_id}/lifecycle-proposals/{proposal_id}/apply` | `apply_lifecycle_proposal` | 6282 |
| GET | `/api/deals/{deal_id}/reprice` | `reprice_inputs` | 6471 |
| POST | `/api/deals/{deal_id}/reinvest/roll` | `reinvest_roll_endpoint` | 6586 |
| POST | `/api/deals/{deal_id}/reinvest/scan` | `reinvest_scan_endpoint` | 6826 |
| POST | `/api/deals/{deal_id}/reinvest/proposal` | `reinvest_proposal_endpoint` | 6976 |
| POST | `/api/deals/{deal_id}/reinvest/proposal/freeze` | `freeze_reinvest_proposal` | 7003 |
| POST | `/api/deals/{deal_id}/reinvest/proposal/pdf` | `reinvest_proposal_pdf_endpoint` | 7033 |
| GET | `/api/deals/{deal_id}/archives` | `list_deal_archives` | 7047 |
| POST | `/api/deals/{deal_id}/mtm` | `deal_mtm` | 7079 |
| POST | `/api/deals/{deal_id}/greeks` | `deal_greeks` | 7127 |
| POST | `/api/deals/{deal_id}/mtm/explain` | `deal_mtm_explain` | 7582 |
| POST | `/api/deals/{deal_id}/mtm/explain/report` | `deal_mtm_explain_report` | 7621 |
| POST | `/api/deals/{deal_id}/mtm/report` | `deal_mtm_report` | 7672 |
| GET | `/api/deals/valuation-runs/latest-mtm` | `latest_mtm_runs` | 7781 |
| GET | `/api/deals/{deal_id}/valuation-runs` | `list_valuation_runs` | 7851 |
| GET | `/api/deals/valuation-runs/{run_id}` | `get_valuation_run` | 7874 |
| POST | `/api/deals/valuation-runs/{run_id}/replay` | `replay_saved_valuation_run` | 7887 |

## backend/app/api/documents.py

```python
router = APIRouter(prefix='/api/documents', tags=['documents'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/documents` | `list_documents` | 73 |
| POST | `/api/documents` | `upload_document` | 89 |
| GET | `/api/documents/{doc_id}/download` | `download_document` | 180 |
| DELETE | `/api/documents/{doc_id}` | `delete_document` | 195 |

## backend/app/api/emt.py

```python
router = APIRouter(prefix='/api/emt', tags=['emt'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/emt/compute` | `emt_compute` | 157 |
| POST | `/api/emt/synthesize/payload` | `get_emt_synthesis_payload` | 260 |
| POST | `/api/emt/synthesize/prompt` | `preview_synthesis` | 277 |
| POST | `/api/emt/synthesize` | `synthesize_emt` | 282 |
| POST | `/api/emt/save` | `save_emt` | 339 |
| GET | `/api/emt/records` | `list_emt_records` | 412 |

## backend/app/api/fifo.py

```python
router = APIRouter(prefix='/api/fifo', tags=['fifo'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/fifo/run` | `fifo_run` | 103 |
| POST | `/api/fifo/detect` | `fifo_detect` | 135 |

## backend/app/api/folders.py

```python
router = APIRouter(prefix='/api/folders', tags=['folders'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/folders` | `list_folders` | 48 |
| POST | `/api/folders` | `create_folder` | 57 |
| PUT | `/api/folders/{folder_id}` | `rename_folder` | 74 |
| DELETE | `/api/folders/{folder_id}` | `delete_folder` | 90 |

## backend/app/api/indicatives.py

```python
router = APIRouter(prefix='/api/indicatives', tags=['indicatives'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/indicatives` | `create_indicative` | 108 |
| GET | `/api/indicatives` | `list_indicatives` | 190 |
| GET | `/api/indicatives/{indicative_id}` | `get_indicative` | 202 |
| PATCH | `/api/indicatives/{indicative_id}` | `update_indicative` | 214 |
| GET | `/api/indicatives/{indicative_id}/deal` | `get_linked_deal` | 256 |

## backend/app/api/inlife.py

```python
router = APIRouter(prefix='/api', tags=['pricing'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/price/in-life` | `price_in_life` | 406 |
| POST | `/api/price/implied-funding` | `implied_funding` | 592 |

## backend/app/api/interactions.py

```python
router = APIRouter(prefix='/api/interactions', tags=['interactions'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/interactions` | `list_interactions` | 220 |
| GET | `/api/interactions/types` | `list_types` | 254 |
| GET | `/api/interactions/{interaction_id}` | `get_interaction` | 259 |
| POST | `/api/interactions` | `create_interaction` | 268 |
| PATCH | `/api/interactions/{interaction_id}` | `update_interaction` | 328 |
| POST | `/api/interactions/follow-ups/{follow_up_id}/close` | `close_follow_up` | 386 |
| PATCH | `/api/interactions/follow-ups/{follow_up_id}` | `reschedule_follow_up` | 420 |
| POST | `/api/interactions/follow-ups/{follow_up_id}/reopen` | `reopen_follow_up` | 450 |
| DELETE | `/api/interactions/{interaction_id}` | `delete_interaction` | 478 |

## backend/app/api/kid.py

```python
router = APIRouter(prefix='/api/kid', tags=['kid'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/kid/compute` | `kid_compute` | 306 |
| POST | `/api/kid/save` | `save_kid` | 467 |
| GET | `/api/kid/records` | `list_kid_records` | 535 |

## backend/app/api/market_data.py

```python
router = APIRouter(prefix='/api/finance', tags=['market-data'], dependencies=[Depends(get_current_user)])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/finance/hist_vol` | `hist_vol_endpoint` | 17 |
| GET | `/api/finance/hist_prices` | `hist_prices_endpoint` | 31 |
| GET | `/api/finance/underlyings` | `list_underlyings_endpoint` | 42 |
| GET | `/api/finance/dividends` | `dividend_profile_endpoint` | 65 |

## backend/app/api/opportunities.py

```python
router = APIRouter(prefix='/api/opportunities', tags=['opportunities'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/opportunities` | `list_opportunities` | 256 |
| GET | `/api/opportunities/lost-reasons` | `list_lost_reasons` | 301 |
| GET | `/api/opportunities/{opportunity_id}` | `get_opportunity` | 308 |
| POST | `/api/opportunities` | `create_opportunity` | 319 |
| PATCH | `/api/opportunities/{opportunity_id}` | `update_opportunity` | 381 |
| POST | `/api/opportunities/{opportunity_id}/status` | `change_status` | 539 |
| DELETE | `/api/opportunities/{opportunity_id}` | `delete_opportunity` | 596 |

## backend/app/api/persons.py

```python
router = APIRouter(prefix='/api/persons', tags=['persons'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/persons` | `list_persons` | 165 |
| GET | `/api/persons/duplicates` | `search_duplicates` | 201 |
| GET | `/api/persons/{person_id}` | `get_person` | 217 |
| POST | `/api/persons` | `create_person` | 228 |
| PATCH | `/api/persons/{person_id}` | `update_person` | 285 |
| POST | `/api/persons/{person_id}/deactivate` | `deactivate_person` | 307 |
| POST | `/api/persons/{person_id}/reactivate` | `reactivate_person` | 325 |
| DELETE | `/api/persons/{person_id}` | `delete_person` | 343 |
| GET | `/api/persons/{person_id}/affiliations` | `list_affiliations` | 368 |
| POST | `/api/persons/{person_id}/affiliations` | `create_affiliation` | 382 |
| PATCH | `/api/persons/{person_id}/affiliations/{affiliation_id}` | `update_affiliation` | 419 |
| POST | `/api/persons/{person_id}/affiliations/{affiliation_id}/close` | `close_person_affiliation` | 457 |
| DELETE | `/api/persons/{person_id}/affiliations/{affiliation_id}` | `delete_affiliation` | 484 |
| POST | `/api/persons/{person_id}/change-company` | `change_person_company` | 539 |
| PUT | `/api/persons/{person_id}/affiliations/{affiliation_id}/coverage` | `upsert_contact_coverage` | 587 |

## backend/app/api/portfolios.py

```python
router = APIRouter(prefix='/api/portfolios', tags=['portfolios'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/portfolios` | `list_portfolios` | 138 |
| POST | `/api/portfolios` | `create_portfolio` | 169 |
| PUT | `/api/portfolios/{portfolio_id}` | `rename_portfolio` | 192 |
| DELETE | `/api/portfolios/{portfolio_id}` | `delete_portfolio` | 208 |
| GET | `/api/portfolios/risk-global` | `risk_global` | 603 |
| POST | `/api/portfolios/pnl-explain-global` | `pnl_explain_global` | 727 |
| POST | `/api/portfolios/{portfolio_id}/pnl-explain` | `pnl_explain_portfolio` | 747 |
| GET | `/api/portfolios/{portfolio_id}/risk` | `portfolio_risk` | 770 |
| GET | `/api/portfolios/barriers-global` | `barriers_global` | 976 |
| GET | `/api/portfolios/{portfolio_id}/barriers` | `portfolio_barriers` | 993 |
| GET | `/api/portfolios/exposure-by-counterparty` | `exposure_by_counterparty_global` | 1013 |
| GET | `/api/portfolios/{portfolio_id}/exposure-by-counterparty` | `exposure_by_counterparty_portfolio` | 1031 |

## backend/app/api/pricing.py

```python
router = APIRouter(prefix='/api', tags=['pricing'], dependencies=[Depends(get_current_pricer)])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/parse` | `parse_endpoint` | 70 |
| POST | `/api/price` | `price_endpoint` | 108 |
| POST | `/api/profile` | `profile_endpoint` | 219 |
| POST | `/api/paths` | `paths_endpoint` | 295 |
| POST | `/api/proba` | `proba_endpoint` | 345 |
| POST | `/api/mtf` | `mtf_endpoint` | 396 |
| GET | `/api/ai/providers` | `script_providers_endpoint` | 470 |
| GET | `/api/script/providers` | `script_providers_endpoint` | 470 |
| POST | `/api/script/prompt` | `script_prompt_endpoint` | 480 |
| POST | `/api/product/analyse` | `product_analyse_endpoint` | 506 |
| POST | `/api/product/analyse/prompt` | `product_analyse_prompt_endpoint` | 527 |
| GET | `/api/product/analyse/intentions` | `product_intentions_endpoint` | 545 |
| POST | `/api/script/generate` | `script_generate_endpoint` | 552 |
| GET | `/api/script/transcribe/engines` | `script_transcribe_engines_endpoint` | 590 |
| POST | `/api/script/transcribe/prepare` | `script_transcribe_prepare_endpoint` | 602 |
| POST | `/api/script/transcribe` | `script_transcribe_endpoint` | 622 |
| POST | `/api/mtf/drilldown` | `mtf_drilldown_endpoint` | 668 |
| POST | `/api/backtest` | `backtest_endpoint` | 742 |
| POST | `/api/backtest/compare` | `backtest_compare_endpoint` | 935 |

## backend/app/api/product_optimizer.py

```python
router = APIRouter(prefix='/api/product-optimizer', tags=['product-optimizer'], dependencies=[Depends(get_current_pricer)])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/product-optimizer/market-reference` | `market_reference` | 63 |
| POST | `/api/product-optimizer/cancel/{run_id}` | `cancel_run` | 80 |
| GET | `/api/product-optimizer/capabilities` | `get_capabilities` | 90 |
| POST | `/api/product-optimizer/researches` | `create_research` | 95 |
| GET | `/api/product-optimizer/researches` | `list_researches` | 119 |
| GET | `/api/product-optimizer/researches/{research_id}` | `read_research` | 136 |
| PATCH | `/api/product-optimizer/researches/{research_id}` | `archive_research` | 142 |
| POST | `/api/product-optimizer/researches/{research_id}/cancel` | `cancel_research` | 150 |
| POST | `/api/product-optimizer/estimate-search` | `estimate` | 157 |
| POST | `/api/product-optimizer/run` | `run` | 163 |

## backend/app/api/products.py

```python
router = APIRouter(prefix='/api/products', tags=['products'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/products` | `create_product` | 145 |
| POST | `/api/products/{product_id}/booking-forks` | `fork_product_for_booking` | 216 |
| GET | `/api/products` | `list_products` | 269 |
| GET | `/api/products/{product_id}` | `get_product` | 315 |
| GET | `/api/products/{product_id}/history` | `product_history` | 340 |
| PATCH | `/api/products/{product_id}` | `update_product` | 356 |
| POST | `/api/products/{product_id}/terms` | `revise_product_terms` | 397 |
| POST | `/api/products/{product_id}/archive` | `archive_product` | 441 |
| POST | `/api/products/{product_id}/pricing-input` | `compose_product_pricing_input` | 463 |
| POST | `/api/products/{product_id}/calculations` | `retain_product_calculation` | 488 |
| GET | `/api/products/{product_id}/calculations/{calculation_id}` | `get_product_calculation` | 555 |

## backend/app/api/rfq.py

```python
router = APIRouter(prefix='/api/rfq', tags=['rfq'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/rfq/providers` | `list_providers` | 372 |
| POST | `/api/rfq` | `create_rfq` | 786 |
| GET | `/api/rfq` | `list_rfqs` | 795 |
| GET | `/api/rfq/history` | `rfq_history` | 812 |
| GET | `/api/rfq/{rfq_id}` | `get_rfq` | 877 |
| GET | `/api/rfq/{rfq_id}/terms` | `rfq_terms` | 888 |
| POST | `/api/rfq/{rfq_id}/electronic-execution` | `request_electronic_execution` | 906 |
| POST | `/api/rfq/{rfq_id}/treatment` | `declare_treatment` | 913 |
| POST | `/api/rfq/{rfq_id}/treatment/{agreement_id}/confirm` | `confirm_treatment` | 920 |
| POST | `/api/rfq/{rfq_id}/treatment/{agreement_id}/cancel` | `cancel_treatment` | 931 |
| GET | `/api/rfq/{rfq_id}/shares` | `list_rfq_shares` | 938 |
| PUT | `/api/rfq/{rfq_id}/assignment` | `change_rfq_assignment` | 955 |
| PUT | `/api/rfq/{rfq_id}/shares/{desk_id}` | `share_rfq` | 965 |
| DELETE | `/api/rfq/{rfq_id}/shares/{desk_id}` | `revoke_rfq_share` | 1010 |
| POST | `/api/rfq/{rfq_id}/pricing-input` | `compose_rfq_pricing_input` | 1036 |
| GET | `/api/rfq/{rfq_id}/recipients` | `authorized_rfq_recipients` | 1070 |
| POST | `/api/rfq/{rfq_id}/exchange-preview` | `preview_rfq_exchange` | 1148 |
| GET | `/api/rfq/{rfq_id}/exchange` | `rfq_exchange_tracking` | 1217 |
| POST | `/api/rfq/{rfq_id}/send` | `send_rfq_exchange` | 1224 |
| PATCH | `/api/rfq/{rfq_id}` | `update_rfq` | 1247 |
| DELETE | `/api/rfq/{rfq_id}` | `delete_rfq` | 1579 |
| POST | `/api/rfq/{rfq_id}/quotes` | `add_quote` | 1629 |
| PATCH | `/api/rfq/{rfq_id}/quotes/{quote_id}` | `update_quote` | 1708 |
| DELETE | `/api/rfq/{rfq_id}/quotes/{quote_id}` | `delete_quote` | 1885 |
| GET | `/api/rfq/{rfq_id}/booking-review` | `review_rfq_booking` | 1922 |
| POST | `/api/rfq/{rfq_id}/book` | `book_reviewed_rfq` | 1929 |

## backend/app/api/rfq_desks.py

```python
router = APIRouter(prefix='/api/rfq-desks', tags=['rfq'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/rfq-desks` | `my_desks` | 50 |
| GET | `/api/rfq-desks/organization` | `organization_desks` | 64 |
| GET | `/api/rfq-desks/{desk_id}/members` | `desk_members` | 76 |
| GET | `/api/rfq-desks/admin` | `admin_desks` | 96 |
| POST | `/api/rfq-desks/admin` | `create_desk` | 115 |
| PUT | `/api/rfq-desks/admin/{desk_id}/members/{user_id}` | `put_membership` | 141 |

## backend/app/api/rfq_inbox.py

```python
router = APIRouter(prefix='/api/rfq-inbox', tags=['rfq'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/rfq-inbox` | `list_received` | 22 |
| GET | `/api/rfq-inbox/{item_id}` | `received_request` | 44 |
| POST | `/api/rfq-inbox/{item_id}/electronic-execution/{execution_id}/decision` | `decide_electronic_execution` | 54 |
| PUT | `/api/rfq-inbox/{item_id}/publication-policy` | `set_publication_policy` | 62 |
| PUT | `/api/rfq-inbox/{item_id}/quote-draft` | `prepare_quote` | 69 |
| POST | `/api/rfq-inbox/{item_id}/validate` | `validate_quote` | 76 |
| POST | `/api/rfq-inbox/{item_id}/publish` | `publish_quote` | 83 |
| POST | `/api/rfq-inbox/{item_id}/withdraw` | `withdraw_quote` | 95 |
| POST | `/api/rfq-inbox/{item_id}/claim` | `claim_request` | 108 |
| PUT | `/api/rfq-inbox/{item_id}/assignment` | `assign_request` | 115 |
| GET | `/api/rfq-inbox/{item_id}/members` | `pricing_members` | 122 |
| POST | `/api/rfq-inbox/{item_id}/read` | `acknowledge_read` | 131 |

## backend/app/api/rfq_reconciliation.py

```python
router = APIRouter(prefix='/api/rfq-reconciliation', tags=['rfq'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/rfq-reconciliation` | `list_reconciliation` | 13 |
| GET | `/api/rfq-reconciliation/{execution_id}` | `get_reconciliation` | 34 |
| POST | `/api/rfq-reconciliation/{execution_id}/refresh` | `refresh_reconciliation` | 39 |

## backend/app/api/rfq_relations.py

```python
router = APIRouter(prefix='/api/rfq-relations', tags=['rfq'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/rfq-relations/catalog` | `relation_catalog` | 20 |
| GET | `/api/rfq-relations` | `list_relations` | 35 |
| GET | `/api/rfq-relations/{relation_id}` | `get_relation` | 44 |
| POST | `/api/rfq-relations` | `create_relation` | 50 |
| PUT | `/api/rfq-relations/{relation_id}` | `update_relation` | 55 |
| POST | `/api/rfq-relations/{relation_id}/recognize` | `recognize_relation` | 60 |
| POST | `/api/rfq-relations/{relation_id}/suspension` | `suspend_relation` | 65 |
| GET | `/api/rfq-relations/{relation_id}/history` | `relation_history` | 70 |

## backend/app/api/rfq_transport.py

```python
router = APIRouter(prefix='/api/rfq-transport', tags=['rfq'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/rfq-transport/messages/{message_id}/retry` | `retry` | 25 |
| GET | `/api/rfq-transport/channels` | `channels` | 86 |
| POST | `/api/rfq-transport/channels` | `configure` | 95 |
| PUT | `/api/rfq-transport/channels/{channel_id}` | `state` | 135 |
| POST | `/api/rfq-transport/channels/{channel_id}/probe` | `probe` | 154 |
| POST | `/api/rfq-transport/receive` | `receive` | 165 |

## backend/app/api/scenarios.py

```python
router = APIRouter(prefix='/api', tags=['scenarios'], dependencies=[Depends(get_current_pricer)])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/scenarios` | `scenarios_endpoint` | 22 |

## backend/app/api/schedule.py

```python
router = APIRouter(prefix='/api', tags=['schedule'], dependencies=[Depends(get_current_pricer)])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/calendar/catalog` | `calendar_catalog` | 27 |
| POST | `/api/schedule/generate` | `generate_schedule_endpoint` | 37 |
| POST | `/api/calendar/resolve` | `resolve_business_day` | 69 |
| POST | `/api/schedule/window` | `window_preview_endpoint` | 89 |
| POST | `/api/schedule/period-window` | `period_window_preview_endpoint` | 114 |

## backend/app/api/scripts_db.py

```python
router = APIRouter(prefix='/api/db/scripts', tags=['scripts-db'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/db/scripts` | `list_scripts` | 97 |
| POST | `/api/db/scripts` | `create_script` | 147 |
| GET | `/api/db/scripts/{script_id}` | `get_script` | 181 |
| PUT | `/api/db/scripts/{script_id}` | `update_script` | 200 |
| DELETE | `/api/db/scripts/{script_id}` | `delete_script` | 236 |
| GET | `/api/db/scripts/{script_id}/variants` | `list_variants` | 406 |
| POST | `/api/db/scripts/{script_id}/variants` | `create_variant` | 429 |
| PUT | `/api/db/scripts/variants/{variant_id}` | `update_variant` | 471 |
| GET | `/api/db/scripts/variants/{variant_id}/resolved` | `resolve_variant` | 503 |

## backend/app/api/shocks.py

```python
router = APIRouter(tags=['shocks'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/deals/{deal_id}/shock` | `shock_deal` | 537 |
| POST | `/api/portfolios/{portfolio_id}/shock` | `shock_portfolio` | 558 |
| POST | `/api/portfolios/shock-global` | `shock_global` | 580 |
| POST | `/api/portfolios/{portfolio_id}/smile-risk` | `smile_risk_portfolio` | 620 |
| POST | `/api/portfolios/smile-risk-global` | `smile_risk_global` | 645 |
| GET | `/api/shocks` | `list_shocks` | 662 |

## backend/app/api/simulation.py

```python
router = APIRouter(prefix='/api', tags=['simulation'], dependencies=[Depends(get_current_pricer)])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/solve` | `solve_endpoint` | 79 |
| POST | `/api/grid` | `grid_endpoint` | 127 |

## backend/app/api/trading.py

```python
router = APIRouter(prefix='/api/trading', tags=['Trading relationships'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/api/trading/relationships` | `relationships` | 78 |
| POST | `/api/trading/relationships` | `create_relationship` | 108 |
| PUT | `/api/trading/relationships/{row_id}` | `update_relationship` | 126 |
| GET | `/api/trading/executions` | `executions` | 173 |
| POST | `/api/trading/book-note` | `book_note` | 180 |
| POST | `/api/trading/executions/{row_id}/settle` | `settle` | 262 |
| GET | `/api/trading/positions` | `positions` | 286 |

## backend/app/api/valuation_notes.py

```python
router = APIRouter(prefix='/api/valuation-notes', tags=['Valo Explain'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/valuation-notes` | `create_note` | 131 |
| GET | `/api/valuation-notes` | `list_notes` | 147 |
| GET | `/api/valuation-notes/sources/{deal_id}` | `note_sources` | 157 |
| GET | `/api/valuation-notes/{note_id}` | `get_note` | 176 |
| PATCH | `/api/valuation-notes/{note_id}` | `save_note` | 181 |
| POST | `/api/valuation-notes/{note_id}/versions` | `freeze_note` | 197 |
| GET | `/api/valuation-notes/{note_id}/versions` | `versions` | 221 |
| GET | `/api/valuation-notes/{note_id}/pdf` | `note_pdf` | 230 |
| POST | `/api/valuation-notes/{note_id}/assist/prompt` | `preview_assist_note` | 274 |
| POST | `/api/valuation-notes/{note_id}/assist` | `assist_note` | 279 |

## backend/app/api/var.py

```python
router = APIRouter(prefix='/api/portfolios', tags=['var'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/portfolios/var-global` | `launch_var_global` | 438 |
| POST | `/api/portfolios/{portfolio_id}/var` | `launch_var_portfolio` | 452 |
| GET | `/api/portfolios/var-history` | `list_var_history` | 472 |
| GET | `/api/portfolios/var/{batch_id}` | `get_var_result` | 502 |

## backend/app/api/variants.py

```python
router = APIRouter(prefix='/api/variants', tags=['variants'])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/variants/compare` | `compare_variants` | 174 |
| POST | `/api/variants/archives` | `freeze_variant_study` | 282 |
| GET | `/api/variants/archives/{script_id}` | `list_variant_studies` | 303 |

## backend/app/api/volatility.py

```python
router = APIRouter(prefix='/api/volatility', tags=['volatility'], dependencies=[Depends(get_current_user)])
```

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/volatility/validate` | `validate_surface` | 27 |
| POST | `/api/volatility/calibrate` | `calibrate` | 33 |

## backend/app/hybrid/control_services.py

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/health` | `health` | 80 |
| POST | `/_instance/stop` | `stop` | 86 |
| GET | `/{path:path}` | `redirect` | 90 |

## backend/app/hybrid/platform.py

Montages déclarés :

- Ligne 341 : `app.mount('/assets', StaticFiles(directory=str(dist / 'assets')), name='assets')`

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/auth/logout` | `logout` | 128 |
| POST | `/api/auth/logout-all` | `logout_all` | 135 |
| POST | `/api/auth/password` | `change_password` | 141 |
| GET | `/health` | `health` | 156 |
| POST | `/_instance/stop` | `stop` | 162 |
| POST | `/api/auth/login` | `login` | 170 |
| GET | `/api/auth/options` | `login_options` | 197 |
| GET | `/api/auth/identity` | `login_identity` | 211 |
| GET | `/api/platform/login-options` | `password_login_options` | 215 |
| GET | `/api/auth/me` | `me` | 223 |
| GET | `/api/platform/development/access` | `development_access` | 230 |
| POST | `/api/platform/development/admin-workbench` | `open_admin_workbench` | 239 |
| POST | `/api/platform/development/session` | `development_session` | 251 |
| GET | `/api/platform/installations` | `directory` | 295 |
| GET | `/api/platform/status` | `status` | 303 |
| POST | `/api/platform/installations/{key}/start` | `start_organization` | 321 |
| GET | `/tp_logo.png` | `logo` | 344 |
| GET | `/` | `portal` | 348 |

## backend/app/hybrid/simulation.py

Montages déclarés :

- Ligne 102 : `app.include_router(agent_workshop.router)`
- Ligne 103 : `app.include_router(agent_workshop.admin_router)`

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/health` | `health` | 106 |
| POST | `/_instance/stop` | `stop` | 111 |

## backend/app/hybrid/simulation_gateway.py

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| POST | `/api/platform/simulation/start` | `start_simulation` | 27 |
| GET,POST | `/api/agent-workshop` | `root` | 66 |
| GET,POST | `/api/admin/agent-workshop` | `root` | 66 |
| GET,POST,PATCH,DELETE | `/api/agent-workshop/{tail:path}` | `resource` | 71 |
| GET,POST,PATCH,DELETE | `/api/admin/agent-workshop/{tail:path}` | `resource` | 71 |

## backend/app/main.py

Montages déclarés :

- Ligne 154 : `app.include_router(inlife_router)`
- Ligne 155 : `app.include_router(volatility_router)`
- Ligne 156 : `app.include_router(ccr_router)`
- Ligne 157 : `app.include_router(auth_router)`
- Ligne 158 : `app.include_router(folders_router)`
- Ligne 159 : `app.include_router(clients_router)`
- Ligne 160 : `app.include_router(persons_router)`
- Ligne 161 : `app.include_router(opportunities_router)`
- Ligne 162 : `app.include_router(interactions_router)`
- Ligne 163 : `app.include_router(client_intelligence_router)`
- Ligne 164 : `app.include_router(client_import_router)`
- Ligne 165 : `app.include_router(constraint_definitions_router)`
- Ligne 166 : `app.include_router(scripts_db_router)`
- Ligne 167 : `app.include_router(variants_router)`
- Ligne 168 : `app.include_router(deals_router)`
- Ligne 169 : `app.include_router(valuation_notes_router)`
- Ligne 170 : `app.include_router(portfolios_router)`
- Ligne 171 : `app.include_router(shocks_router)`
- Ligne 172 : `app.include_router(indicatives_router)`
- Ligne 173 : `app.include_router(kid_router)`
- Ligne 174 : `app.include_router(emt_router)`
- Ligne 175 : `app.include_router(documents_router)`
- Ligne 176 : `app.include_router(amc_router)`
- Ligne 177 : `app.include_router(amc_prices_router)`
- Ligne 178 : `app.include_router(amc_studies_router)`
- Ligne 179 : `app.include_router(fifo_router)`
- Ligne 180 : `app.include_router(rfq_router)`
- Ligne 181 : `app.include_router(rfq_desks_router)`
- Ligne 182 : `app.include_router(rfq_relations_router)`
- Ligne 183 : `app.include_router(rfq_inbox_router)`
- Ligne 184 : `app.include_router(rfq_transport_router)`
- Ligne 185 : `app.include_router(rfq_reconciliation_router)`
- Ligne 186 : `app.include_router(admin_router)`
- Ligne 187 : `app.include_router(alerts_router)`
- Ligne 188 : `app.include_router(compute_router)`
- Ligne 189 : `app.include_router(var_router)`
- Ligne 190 : `app.include_router(products_router)`
- Ligne 191 : `app.include_router(product_optimizer_router)`
- Ligne 192 : `app.include_router(trading_router)`
- Ligne 193 : `app.include_router(agent_workshop_router)`
- Ligne 194 : `app.include_router(admin_agent_workshop_router)`
- Ligne 195 : `app.include_router(pricing_router)`
- Ligne 196 : `app.include_router(market_data_router)`
- Ligne 197 : `app.include_router(simulation_router)`
- Ligne 198 : `app.include_router(scenarios_router)`
- Ligne 199 : `app.include_router(schedule_router)`
- Ligne 287 : `app.mount('/assets', StaticFiles(directory=str(DIST / 'assets')), name='assets')`

| Méthode | Chemin local/préfixé | Fonction | Ligne |
|---|---|---|---|
| GET | `/health` | `health` | 234 |
| POST | `/_instance/stop` | `stop_owned_instance` | 254 |
| POST | `/_instance/consultation-session` | `consultation_session` | 268 |
| GET | `/tp_logo.png` | `tp_logo_png` | 290 |
| GET | `/` | `root` | 294 |

