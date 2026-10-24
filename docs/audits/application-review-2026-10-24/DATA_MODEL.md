# Modèles, contrats et champs

Extraction statique des classes de persistance et contrats Pydantic retenus.
Les champs d'une classe héritée ne sont pas répétés ; lire sa classe de base.
Une classe déclarée ne prouve ni table migrée ni fonctionnalité active. Les contraintes de service, validators, migrations et triggers restent déterminants.
Les définitions sont du code source, jamais des valeurs lues dans une base privée.

## RfqContactCreate

Source : `backend/app/api/admin.py:57`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `str` | `name: str` |
| `email` | `str` | `email: str = ''` |

## RfqContactUpdate

Source : `backend/app/api/admin.py:62`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `Optional[str]` | `name: Optional[str] = None` |
| `email` | `Optional[str]` | `email: Optional[str] = None` |
| `active` | `Optional[bool]` | `active: Optional[bool] = None` |

## BrowseDelete

Source : `backend/app/api/admin.py:463`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `ids` | `list[int]` | `ids: list[int]` |

## UserCreate

Source : `backend/app/api/admin.py:503`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `username` | `str` | `username: str` |
| `email` | `str` | `email: str` |
| `password` | `str` | `password: str` |
| `role` | `Literal['user', 'ops_maker', 'checker', 'admin', 'organization_admin']` | `role: Literal['user', 'ops_maker', 'checker', 'admin', 'organization_admin'] = 'user'` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = None` |

## UserUpdate

Source : `backend/app/api/admin.py:512`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `email` | `Optional[str]` | `email: Optional[str] = None` |
| `role` | `Optional[Literal['user', 'ops_maker', 'checker', 'admin', 'organization_admin']]` | `role: Optional[Literal['user', 'ops_maker', 'checker', 'admin', 'organization_admin']] = None` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = None` |
| `is_active` | `Optional[bool]` | `is_active: Optional[bool] = None` |

## PasswordReset

Source : `backend/app/api/admin.py:604`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `password` | `str` | `password: str` |

## EntityCreate

Source : `backend/app/api/admin.py:642`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `str` | `name: str` |

## EntityUpdate

Source : `backend/app/api/admin.py:646`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `Optional[str]` | `name: Optional[str] = None` |

## MarketDataFetchRequest

Source : `backend/app/api/admin.py:810`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `key` | `str` | `key: str` |
| `ticker` | `str` | `ticker: str` |

## IssueReview

Source : `backend/app/api/agent_workshop.py:116`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `status` | `Literal['OPEN', 'IN_PROGRESS', 'CLOSED']` | `status: Literal['OPEN', 'IN_PROGRESS', 'CLOSED'] = 'OPEN'` |
| `qualification` | `Literal['UNCONFIRMED', 'CONFIRMED_BUG', 'USAGE', 'EXPECTED_REFUSAL', 'HARNESS', 'MISSING', 'DATA']` | `qualification: Literal['UNCONFIRMED', 'CONFIRMED_BUG', 'USAGE', 'EXPECTED_REFUSAL', 'HARNESS', 'MISSING', 'DATA'] = 'UNCONFIRMED'` |
| `note` | `str` | `note: str = Field(default='', max_length=3000)` |

Méthodes/validators : `require_diagnosis:123`

## AnalyzeRequest

Source : `backend/app/api/amc.py:86`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `nav` | `list` | `nav: list = Field(max_length=20000)` |
| `transactions` | `list` | `transactions: list = []` |
| `composition` | `list` | `composition: list = []` |
| `exposures` | `dict` | `exposures: dict = {}` |
| `ff_series` | `str` | `ff_series: str = 'Global_3F'` |
| `selected_factors` | `List[str]` | `selected_factors: List[str] = ['Mkt-RF', 'SMB', 'HML']` |
| `benchmark_ticker` | `str` | `benchmark_ticker: str = 'IGF'` |
| `rolling_window` | `int` | `rolling_window: int = Field(60, ge=20, le=2520)` |
| `nav_currency` | `str` | `nav_currency: str = 'USD'` |

## ExportPdfRequest

Source : `backend/app/api/amc.py:98`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `result` | `dict` | `result: dict` |
| `meta` | `dict` | `meta: dict = {}` |

## StudyRunRequest

Source : `backend/app/api/amc.py:226`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `manifest` | `dict` | `manifest: dict` |
| `folder` | `str` | `folder: str` |

## StudyExportRequest

Source : `backend/app/api/amc.py:231`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `study_result` | `dict` | `study_result: dict` |
| `synthese_text` | `str` | `synthese_text: str = ''` |
| `vag_result` | `Optional[dict]` | `vag_result: Optional[dict] = None` |
| `attribution_result` | `Optional[dict]` | `attribution_result: Optional[dict] = None` |
| `brinson_result` | `Optional[dict]` | `brinson_result: Optional[dict] = None` |
| `market_shocks_result` | `Optional[dict]` | `market_shocks_result: Optional[dict] = None` |
| `company_name` | `str` | `company_name: str = ''` |
| `client_name` | `str` | `client_name: str = ''` |
| `include_annexes` | `bool` | `include_annexes: bool = True` |
| `include_brinson` | `bool` | `include_brinson: bool = False` |
| `include_marketshocks` | `bool` | `include_marketshocks: bool = False` |

## ManagerSkillRequest

Source : `backend/app/api/amc.py:279`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `study_result` | `dict` | `study_result: dict` |
| `vag_result` | `Optional[dict]` | `vag_result: Optional[dict] = None` |

## MarketShocksRequest

Source : `backend/app/api/amc.py:300`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `study_result` | `dict` | `study_result: dict` |
| `folder` | `str` | `folder: str` |

## ResolveItem

Source : `backend/app/api/amc_prices.py:58`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `key` | `str` | `key: str` |
| `isin` | `str` | `isin: str = ''` |
| `name` | `str` | `name: str = ''` |

## FetchRequest

Source : `backend/app/api/amc_prices.py:86`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `key` | `str` | `key: str` |
| `ticker` | `str` | `ticker: str` |
| `start` | `Optional[str]` | `start: Optional[str] = None` |
| `end` | `Optional[str]` | `end: Optional[str] = None` |

## AttributionRequest

Source : `backend/app/api/amc_prices.py:149`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `folder` | `str` | `folder: str` |
| `study_result` | `dict` | `study_result: dict` |
| `amc_currency` | `str` | `amc_currency: str = 'CHF'` |

## BrinsonRequest

Source : `backend/app/api/amc_prices.py:190`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `study_result` | `dict` | `study_result: dict` |
| `price_keys` | `List[str]` | `price_keys: List[str]` |
| `amc_currency` | `str` | `amc_currency: str = 'CHF'` |
| `folder` | `str` | `folder: str = ''` |
| `benchmark_ticker` | `str` | `benchmark_ticker: str = 'ACWI'` |

## AmcStudyCreate

Source : `backend/app/api/amc_studies.py:22`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `isin` | `str` | `isin: str = ''` |
| `product_name` | `str` | `product_name: str = ''` |
| `label` | `str` | `label: str = ''` |
| `folder` | `str` | `folder: str = ''` |
| `manifest` | `dict` | `manifest: dict = {}` |
| `result` | `dict` | `result: dict = {}` |
| `synthese` | `str` | `synthese: str = ''` |

## PasswordChange

Source : `backend/app/api/auth.py:186`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `current_password` | `str` | `current_password: str` |
| `new_password` | `str` | `new_password: str` |

## RegisterRequest

Source : `backend/app/api/auth.py:371`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `username` | `str` | `username: str` |
| `email` | `str` | `email: str` |
| `password` | `str` | `password: str` |
| `entity_name` | `Optional[str]` | `entity_name: Optional[str] = None` |

## ConfigurationWrite

Source : `backend/app/api/ccr.py:28`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `data` | `dict` | `data: dict` |
| `expected_version` | `int \| None` | `expected_version: int \| None = None` |

## Assignment

Source : `backend/app/api/ccr.py:95`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `netting_set_id` | `int \| None` | `netting_set_id: int \| None = None` |
| `reason` | `str` | `reason: str` |

## ClientCreate

Source : `backend/app/api/clients.py:50`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `str` | `name: str` |
| `legal_name` | `Optional[str]` | `legal_name: Optional[str] = None` |
| `client_type` | `str` | `client_type: str = 'other'` |
| `country` | `Optional[str]` | `country: Optional[str] = None` |
| `status` | `str` | `status: str = 'prospect'` |
| `external_ref` | `Optional[str]` | `external_ref: Optional[str] = None` |
| `notes` | `Optional[str]` | `notes: Optional[str] = None` |
| `data_origin` | `str` | `data_origin: str = 'demo'` |
| `market_data_provider` | `str` | `market_data_provider: str = 'YAHOO_FINANCE'` |
| `confirm_duplicate` | `bool` | `confirm_duplicate: bool = False` |

## ClientUpdate

Source : `backend/app/api/clients.py:66`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `Optional[str]` | `name: Optional[str] = None` |
| `legal_name` | `Optional[str]` | `legal_name: Optional[str] = None` |
| `client_type` | `Optional[str]` | `client_type: Optional[str] = None` |
| `country` | `Optional[str]` | `country: Optional[str] = None` |
| `status` | `Optional[str]` | `status: Optional[str] = None` |
| `external_ref` | `Optional[str]` | `external_ref: Optional[str] = None` |
| `notes` | `Optional[str]` | `notes: Optional[str] = None` |
| `data_origin` | `Optional[str]` | `data_origin: Optional[str] = None` |
| `market_data_provider` | `Optional[str]` | `market_data_provider: Optional[str] = None` |

## PreferenceEvidence

Source : `backend/app/api/clients.py:78`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `statement_kind` | `str` | `statement_kind: str = 'sales_note'` |
| `statement_date` | `str` | `statement_date: str = ''` |
| `source_affiliation_id` | `Optional[int]` | `source_affiliation_id: Optional[int] = None` |
| `channel` | `Optional[str]` | `channel: Optional[str] = None` |
| `interaction_id` | `Optional[int]` | `interaction_id: Optional[int] = None` |
| `note` | `Optional[str]` | `note: Optional[str] = None` |

## ScalarConstraintsUpdate

Source : `backend/app/api/clients.py:89`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `ticket_min` | `Optional[float]` | `ticket_min: Optional[float] = None` |
| `ticket_max` | `Optional[float]` | `ticket_max: Optional[float] = None` |
| `ticket_currency` | `Optional[str]` | `ticket_currency: Optional[str] = None` |
| `maturity_min_months` | `Optional[int]` | `maturity_min_months: Optional[int] = None` |
| `maturity_max_months` | `Optional[int]` | `maturity_max_months: Optional[int] = None` |
| `min_rating` | `Optional[str]` | `min_rating: Optional[str] = None` |
| `max_concentration_pct` | `Optional[float]` | `max_concentration_pct: Optional[float] = None` |
| `evidence` | `Optional[PreferenceEvidence]` | `evidence: Optional[PreferenceEvidence] = None` |

## ConstraintsUpdate

Source : `backend/app/api/clients.py:100`. Bases : `BaseModel`.

Le blob de listes, sous verrou optimiste.  `constraints_version` est obligatoire : c'est la version que l'écran avait sous les yeux. Si elle a bougé entre-temps, l'écriture est refusée plutôt qu'appliquée par-dessus le travail de quelqu'un d'autre.

| Champ | Type | Définition |
|---|---|---|
| `constraints` | `dict` | `constraints: dict` |
| `constraints_version` | `int` | `constraints_version: int` |
| `evidence` | `Optional[PreferenceEvidence]` | `evidence: Optional[PreferenceEvidence] = None` |

## ScopedPreferencesUpdate

Source : `backend/app/api/clients.py:112`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `preferences` | `dict` | `preferences: dict` |
| `preferences_version` | `int` | `preferences_version: int` |
| `mandate_id` | `Optional[int]` | `mandate_id: Optional[int] = None` |
| `affiliation_id` | `Optional[int]` | `affiliation_id: Optional[int] = None` |
| `evidence` | `Optional[PreferenceEvidence]` | `evidence: Optional[PreferenceEvidence] = None` |

## CoverageUpsert

Source : `backend/app/api/clients.py:120`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `user_id` | `int` | `user_id: int` |
| `coverage_role` | `str` | `coverage_role: str = 'primary'` |

## MandateCreate

Source : `backend/app/api/clients.py:125`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `str` | `name: str` |
| `mandate_type` | `str` | `mandate_type: str = 'mandate'` |
| `reference_currency` | `Optional[str]` | `reference_currency: Optional[str] = None` |
| `comment` | `Optional[str]` | `comment: Optional[str] = None` |
| `data_origin` | `Optional[str]` | `data_origin: Optional[str] = None` |

## MandateUpdate

Source : `backend/app/api/clients.py:133`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `Optional[str]` | `name: Optional[str] = None` |
| `mandate_type` | `Optional[str]` | `mandate_type: Optional[str] = None` |
| `status` | `Optional[str]` | `status: Optional[str] = None` |
| `reference_currency` | `Optional[str]` | `reference_currency: Optional[str] = None` |
| `comment` | `Optional[str]` | `comment: Optional[str] = None` |
| `data_origin` | `Optional[str]` | `data_origin: Optional[str] = None` |

## ComputeJobIn

Source : `backend/app/api/compute.py:30`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `label` | `str` | `label: str = ''` |
| `payload` | `dict` | `payload: dict` |

## ComputeBatchCreate

Source : `backend/app/api/compute.py:35`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `kind` | `str` | `kind: str = 'payscript_reprice'` |
| `label` | `str` | `label: str = ''` |
| `jobs` | `List[ComputeJobIn]` | `jobs: List[ComputeJobIn]` |
| `max_workers` | `int` | `max_workers: int = 4` |
| `use_processes` | `bool` | `use_processes: bool = True` |

## DefinitionCreate

Source : `backend/app/api/constraint_definitions.py:44`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `label` | `str` | `label: str` |
| `kind` | `str` | `kind: str = 'text'` |
| `key` | `Optional[str]` | `key: Optional[str] = None` |
| `client_id` | `Optional[int]` | `client_id: Optional[int] = None` |
| `options` | `list[str]` | `options: list[str] = []` |
| `catalog` | `Optional[str]` | `catalog: Optional[str] = None` |
| `unit` | `Optional[str]` | `unit: Optional[str] = None` |
| `help_text` | `Optional[str]` | `help_text: Optional[str] = None` |
| `free_entry` | `bool` | `free_entry: bool = True` |

## DefinitionUpdate

Source : `backend/app/api/constraint_definitions.py:56`. Bases : `BaseModel`.

La CLÉ ne figure pas ici, et c'est le point.  Elle est écrite dans le blob de chaque client qui a rempli le champ ; la renommer orphelinerait toutes ces valeurs d'un coup, sans erreur ni trace. Le libellé, lui, se change librement — c'est ce que les gens lisent.

| Champ | Type | Définition |
|---|---|---|
| `label` | `Optional[str]` | `label: Optional[str] = None` |
| `options` | `Optional[list[str]]` | `options: Optional[list[str]] = None` |
| `catalog` | `Optional[str]` | `catalog: Optional[str] = None` |
| `unit` | `Optional[str]` | `unit: Optional[str] = None` |
| `help_text` | `Optional[str]` | `help_text: Optional[str] = None` |
| `free_entry` | `Optional[bool]` | `free_entry: Optional[bool] = None` |

## DealUpdate

Source : `backend/app/api/deals.py:91`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='allow')`

| Champ | Type | Définition |
|---|---|---|
| `status` | `Optional[str]` | `status: Optional[str] = None` |
| `contrepartie` | `Optional[str]` | `contrepartie: Optional[str] = None` |
| `price_traded` | `Optional[float]` | `price_traded: Optional[float] = None` |
| `nominal` | `Optional[float]` | `nominal: Optional[float] = None` |
| `devise` | `Optional[str]` | `devise: Optional[str] = None` |
| `fair_value` | `Optional[float]` | `fair_value: Optional[float] = None` |
| `sens` | `Optional[str]` | `sens: Optional[str] = None` |
| `trade_date` | `Optional[str]` | `trade_date: Optional[str] = None` |
| `strike_date` | `Optional[str]` | `strike_date: Optional[str] = None` |
| `value_date` | `Optional[str]` | `value_date: Optional[str] = None` |
| `maturity_date` | `Optional[str]` | `maturity_date: Optional[str] = None` |
| `payment_date` | `Optional[str]` | `payment_date: Optional[str] = None` |
| `T` | `Optional[float]` | `T: Optional[float] = None` |
| `underlyings` | `Optional[List[dict]]` | `underlyings: Optional[List[dict]] = None` |
| `observation_times` | `Optional[List[float]]` | `observation_times: Optional[List[float]] = None` |
| `script_snapshot` | `Optional[str]` | `script_snapshot: Optional[str] = None` |
| `market_snapshot` | `Optional[dict]` | `market_snapshot: Optional[dict] = None` |
| `rfq_id` | `Optional[int]` | `rfq_id: Optional[int] = None` |
| `selected_quote_id` | `Optional[int]` | `selected_quote_id: Optional[int] = None` |

## EventUpdate

Source : `backend/app/api/deals.py:117`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `spots` | `dict` | `spots: dict` |
| `source` | `Literal['manuel']` | `source: Literal['manuel'] = 'manuel'` |
| `status` | `Optional[str]` | `status: Optional[str] = None` |
| `provider` | `str` | `provider: str = ''` |
| `source_type` | `str` | `source_type: str = ''` |
| `external_reference` | `str` | `external_reference: str = ''` |
| `observed_at` | `str` | `observed_at: str = ''` |
| `venue` | `str` | `venue: str = ''` |
| `calendar` | `str` | `calendar: str = ''` |
| `timezone` | `str` | `timezone: str = ''` |
| `evidence_sha256` | `str` | `evidence_sha256: str = ''` |
| `evidence_filename` | `str` | `evidence_filename: str = ''` |
| `evidence_content_type` | `str` | `evidence_content_type: str = 'application/octet-stream'` |
| `evidence_payload_b64` | `str` | `evidence_payload_b64: str = ''` |
| `reason` | `str` | `reason: str = ''` |
| `supersedes_version` | `Optional[int]` | `supersedes_version: Optional[int] = None` |

## FixingValidationRequest

Source : `backend/app/api/deals.py:136`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=1000)` |

## AutoFixingExceptionResolutionRequest

Source : `backend/app/api/deals.py:140`. Bases : `BaseModel`.

One-person decision for an AUTO_YAHOO fixing exception.  The expected version is an optimistic lock: the UI must resolve exactly the version it displayed.  A concurrent capture or provider revision therefore fails closed instead of being silently overwritten.

| Champ | Type | Définition |
|---|---|---|
| `action` | `Literal['USE_YAHOO', 'CONFIRM_CURRENT', 'REPLACE_MANUAL']` | `action: Literal['USE_YAHOO', 'CONFIRM_CURRENT', 'REPLACE_MANUAL']` |
| `expected_version_id` | `Optional[int]` | `expected_version_id: Optional[int] = None` |
| `spots` | `Optional[dict]` | `spots: Optional[dict] = None` |
| `source_reference` | `str` | `source_reference: str = Field(default='', max_length=500)` |
| `reason` | `str` | `reason: str = Field(default='', max_length=2000)` |

Méthodes/validators : `_motive_required_when_overriding:162`

## LifecycleValidationRequest

Source : `backend/app/api/deals.py:170`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=2000)` |
| `confirmed_outcome` | `Optional[Literal['callé', 'ki', 'final']]` | `confirmed_outcome: Optional[Literal['callé', 'ki', 'final']] = None` |

## AmendmentRequestCreate

Source : `backend/app/api/deals.py:175`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `field_name` | `Literal['nominal', 'devise', 'contrepartie', 'price_traded', 'status', 'trade_date', 'strike_date', 'value_date', 'maturity_date', 'payment_date', 'script_snapshot', 'market_snapshot', 'commercial_attribution']` | `field_name: Literal['nominal', 'devise', 'contrepartie', 'price_traded', 'status', 'trade_date', 'strike_date', 'value_date', 'maturity_date', 'payment_date', 'script_snapshot', 'market_snapshot', 'commercial_attribution']` |
| `new_value` | `object` | `new_value: object` |
| `reason` | `str` | `reason: str = Field(min_length=10, max_length=2000)` |

## AmendmentDecisionRequest

Source : `backend/app/api/deals.py:186`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `reason` | `str` | `reason: str = Field(min_length=10, max_length=2000)` |

## DealPortfolioAssign

Source : `backend/app/api/deals.py:2456`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `portfolio_id` | `int` | `portfolio_id: int` |

## DealPortfoliosSet

Source : `backend/app/api/deals.py:2460`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `portfolio_ids` | `list[int]` | `portfolio_ids: list[int] = Field(default_factory=list)` |

## MtmExplainRequest

Source : `backend/app/api/deals.py:7246`. Bases : `BaseModel`.

Body of POST /{deal_id}/mtm/explain. date1 defaults to the deal's value date (booking), date2 to today. `recalibrate` sets the σ source at date 2 ; at date 1 the rule is fixed (booking σ when date1 = value date, realized σ otherwise — see EXPLICATION_VALO_DESIGN.md).

| Champ | Type | Définition |
|---|---|---|
| `date1` | `Optional[str]` | `date1: Optional[str] = None` |
| `date2` | `Optional[str]` | `date2: Optional[str] = None` |
| `recalibrate` | `Literal['none', 'realized']` | `recalibrate: Literal['none', 'realized'] = 'realized'` |
| `window_days` | `int` | `window_days: int = 252` |

## DocumentCreate

Source : `backend/app/api/documents.py:35`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `title` | `str` | `title: str` |
| `doc_type` | `str` | `doc_type: str = 'autre'` |
| `deal_id` | `Optional[int]` | `deal_id: Optional[int] = None` |
| `product_id` | `Optional[int]` | `product_id: Optional[int] = None` |
| `product_terms_version` | `Optional[int]` | `product_terms_version: Optional[int] = None` |
| `metadata` | `dict` | `metadata: dict = Field(default_factory=dict)` |

## EmtSaveRequest

Source : `backend/app/api/emt.py:295`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `product_id` | `Optional[int]` | `product_id: Optional[int] = None` |
| `product_terms_version` | `Optional[int]` | `product_terms_version: Optional[int] = None` |
| `indicative_id` | `Optional[int]` | `indicative_id: Optional[int] = None` |
| `deal_id` | `Optional[int]` | `deal_id: Optional[int] = None` |
| `product_title` | `str` | `product_title: str = 'Produit structuré'` |
| `sri` | `int` | `sri: int` |
| `mrm` | `int` | `mrm: int` |
| `crm` | `int` | `crm: int` |
| `T_rhp` | `float` | `T_rhp: float` |
| `capital_tier` | `str` | `capital_tier: str` |
| `capital_label` | `str` | `capital_label: str` |
| `knowledge_tier` | `str` | `knowledge_tier: str` |
| `knowledge_label` | `str` | `knowledge_label: str` |
| `risk_tolerance` | `str` | `risk_tolerance: str` |
| `objective` | `str` | `objective: str` |
| `features` | `dict` | `features: dict = Field(default_factory=dict)` |
| `client_type` | `str` | `client_type: str = 'retail'` |
| `distribution` | `str` | `distribution: str = 'advice'` |
| `negative_target_market` | `str` | `negative_target_market: str = ''` |
| `description` | `str` | `description: str = ''` |

## FifoRunRequest

Source : `backend/app/api/fifo.py:34`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `folder` | `str` | `folder: str` |
| `qty_mode` | `Literal['auto', 'shares', 'cert_units']` | `qty_mode: Literal['auto', 'shares', 'cert_units'] = 'auto'` |
| `recon_mode` | `Literal['strict', 't0_synthetic']` | `recon_mode: Literal['strict', 't0_synthetic'] = 't0_synthetic'` |
| `prod_ccy` | `str` | `prod_ccy: str = 'USD'` |
| `order_files` | `Optional[list[str]]` | `order_files: Optional[list[str]] = None` |
| `termsheet_path` | `Optional[str]` | `termsheet_path: Optional[str] = None` |

## FolderCreate

Source : `backend/app/api/folders.py:12`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `str` | `name: str` |
| `parent_id` | `int \| None` | `parent_id: int \| None = None` |

## FolderRename

Source : `backend/app/api/folders.py:17`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `str` | `name: str` |

## IndicativeCreate

Source : `backend/app/api/indicatives.py:30`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `product_id` | `Optional[int]` | `product_id: Optional[int] = None` |
| `product_terms_version` | `Optional[int]` | `product_terms_version: Optional[int] = None` |
| `product_name` | `str` | `product_name: str = ''` |
| `pricing_input` | `Optional[dict]` | `pricing_input: Optional[dict] = None` |
| `contrepartie` | `str` | `contrepartie: str = ''` |
| `devise` | `str` | `devise: str = 'EUR'` |
| `nominal` | `float` | `nominal: float = 0.0` |
| `underlyings` | `List[dict]` | `underlyings: List[dict] = []` |
| `script_snapshot` | `str` | `script_snapshot: str` |
| `script_id` | `Optional[int]` | `script_id: Optional[int] = None` |
| `market_snapshot` | `dict` | `market_snapshot: dict = {}` |

## IndicativeUpdate

Source : `backend/app/api/indicatives.py:44`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `status` | `Optional[str]` | `status: Optional[str] = None` |
| `contrepartie` | `Optional[str]` | `contrepartie: Optional[str] = None` |
| `nominal` | `Optional[float]` | `nominal: Optional[float] = None` |
| `script_snapshot` | `Optional[str]` | `script_snapshot: Optional[str] = None` |
| `underlyings` | `Optional[List[dict]]` | `underlyings: Optional[List[dict]] = None` |
| `market_snapshot` | `Optional[dict]` | `market_snapshot: Optional[dict] = None` |

## InLifePricingRequest

Source : `backend/app/api/inlife.py:57`. Bases : `BaseModel`.

Un produit et la date à laquelle on veut le valoriser.

- `model_config = ConfigDict(allow_inf_nan=False)`

| Champ | Type | Définition |
|---|---|---|
| `script` | `str` | `script: str = Field(max_length=MAX_SCRIPT_CHARS)` |
| `underlyings` | `list[UnderlyingParams]` | `underlyings: list[UnderlyingParams] = Field(min_length=1, max_length=MAX_UNDERLYINGS)` |
| `corr_matrix` | `list[list[float]]` | `corr_matrix: list[list[float]]` |
| `r` | `float` | `r: float = 0.03` |
| `N` | `int` | `N: int = Field(default=20000, ge=1000, le=200000)` |
| `model` | `str` | `model: str = 'constant'` |
| `user_params` | `dict` | `user_params: dict = Field(default_factory=dict)` |
| `constats` | `dict` | `constats: dict = Field(default_factory=dict)` |
| `frozen_schedule` | `Optional[dict]` | `frozen_schedule: Optional[dict] = None` |
| `seed` | `int` | `seed: int = 42` |
| `antithetic` | `bool` | `antithetic: bool = True` |
| `yield_curve` | `list[list[float]]` | `yield_curve: list[list[float]] = Field(default_factory=list)` |
| `funding_curve` | `list[list[float]]` | `funding_curve: list[list[float]] = Field(default_factory=list)` |
| `funding_spread` | `float` | `funding_spread: float = 0.0` |
| `sigma_r` | `float` | `sigma_r: float = 0.0` |
| `a_r` | `float` | `a_r: float = 0.0` |
| `barrier_monitoring` | `str` | `barrier_monitoring: str = 'weekly'` |
| `compute_greeks` | `bool` | `compute_greeks: bool = False` |
| `selected_greeks` | `list[str]` | `selected_greeks: list[str] = Field(default_factory=list)` |
| `strike_date` | `date` | `strike_date: date` |
| `value_date` | `date` | `value_date: date` |
| `maturity_date` | `date` | `maturity_date: date` |
| `payment_date` | `Optional[date]` | `payment_date: Optional[date] = None` |
| `valuation_date` | `Optional[date]` | `valuation_date: Optional[date] = None` |
| `settlement_ccy` | `str` | `settlement_ccy: str = 'EUR'` |
| `strike_levels` | `dict[str, float]` | `strike_levels: dict[str, float] = Field(default_factory=dict)` |
| `variant` | `Optional[VariantOverrides]` | `variant: Optional[VariantOverrides] = None` |

Méthodes/validators : `validate_yield_curve:110`; `validate_funding_curve:115`; `fixed_monte_carlo_seed:120`

## ParticipantIn

Source : `backend/app/api/interactions.py:36`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `affiliation_id` | `int` | `affiliation_id: int` |
| `role` | `str` | `role: str = 'other'` |

## InteractionCreate

Source : `backend/app/api/interactions.py:41`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `client_id` | `int` | `client_id: int` |
| `opportunity_id` | `Optional[int]` | `opportunity_id: Optional[int] = None` |
| `interaction_date` | `str` | `interaction_date: str` |
| `interaction_type` | `str` | `interaction_type: str = 'other'` |
| `summary` | `str` | `summary: str = ''` |
| `notes` | `Optional[str]` | `notes: Optional[str] = None` |
| `next_action` | `Optional[str]` | `next_action: Optional[str] = None` |
| `next_action_date` | `Optional[str]` | `next_action_date: Optional[str] = None` |
| `participants` | `list[ParticipantIn]` | `participants: list[ParticipantIn] = []` |

## InteractionUpdate

Source : `backend/app/api/interactions.py:53`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `interaction_date` | `Optional[str]` | `interaction_date: Optional[str] = None` |
| `interaction_type` | `Optional[str]` | `interaction_type: Optional[str] = None` |
| `summary` | `Optional[str]` | `summary: Optional[str] = None` |
| `notes` | `Optional[str]` | `notes: Optional[str] = None` |
| `next_action` | `Optional[str]` | `next_action: Optional[str] = None` |
| `next_action_date` | `Optional[str]` | `next_action_date: Optional[str] = None` |
| `opportunity_id` | `Optional[int]` | `opportunity_id: Optional[int] = None` |
| `participants` | `Optional[list[ParticipantIn]]` | `participants: Optional[list[ParticipantIn]] = None` |

## FollowUpClose

Source : `backend/app/api/interactions.py:64`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `status` | `str` | `status: str = 'done'` |
| `note` | `Optional[str]` | `note: Optional[str] = None` |

## FollowUpReschedule

Source : `backend/app/api/interactions.py:69`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `title` | `Optional[str]` | `title: Optional[str] = None` |
| `due_date` | `Optional[str]` | `due_date: Optional[str] = None` |

## KidSaveRequest

Source : `backend/app/api/kid.py:434`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `product_id` | `Optional[int]` | `product_id: Optional[int] = None` |
| `product_terms_version` | `Optional[int]` | `product_terms_version: Optional[int] = None` |
| `indicative_id` | `Optional[int]` | `indicative_id: Optional[int] = None` |
| `deal_id` | `Optional[int]` | `deal_id: Optional[int] = None` |
| `product_title` | `str` | `product_title: str = 'Produit structuré'` |
| `sri` | `int` | `sri: int` |
| `mrm` | `int` | `mrm: int` |
| `crm` | `int` | `crm: int` |
| `vev` | `Optional[float]` | `vev: Optional[float] = None` |
| `T_rhp` | `float` | `T_rhp: float` |
| `horizons` | `list` | `horizons: list = Field(default_factory=list)` |
| `costs` | `dict` | `costs: dict = Field(default_factory=dict)` |

## ParticipantIn

Source : `backend/app/api/opportunities.py:48`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `affiliation_id` | `int` | `affiliation_id: int` |
| `role` | `str` | `role: str = 'other'` |

## OpportunityCreate

Source : `backend/app/api/opportunities.py:53`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `client_id` | `int` | `client_id: int` |
| `mandate_id` | `Optional[int]` | `mandate_id: Optional[int] = None` |
| `primary_affiliation_id` | `Optional[int]` | `primary_affiliation_id: Optional[int] = None` |
| `participants` | `list[ParticipantIn]` | `participants: list[ParticipantIn] = []` |
| `title` | `str` | `title: str = ''` |
| `description` | `Optional[str]` | `description: Optional[str] = None` |
| `amount` | `Optional[float]` | `amount: Optional[float] = None` |
| `currency` | `str` | `currency: str = 'EUR'` |
| `horizon` | `Optional[str]` | `horizon: Optional[str] = None` |
| `expected_trade_date` | `Optional[str]` | `expected_trade_date: Optional[str] = None` |
| `expected_window_start` | `Optional[str]` | `expected_window_start: Optional[str] = None` |
| `expected_window_end` | `Optional[str]` | `expected_window_end: Optional[str] = None` |
| `priority` | `str` | `priority: str = 'medium'` |
| `source` | `Optional[str]` | `source: Optional[str] = None` |
| `transaction_format` | `Optional[str]` | `transaction_format: Optional[str] = None` |
| `instrument_family` | `Optional[str]` | `instrument_family: Optional[str] = None` |
| `payoff_family` | `Optional[str]` | `payoff_family: Optional[str] = None` |
| `payoff_description` | `Optional[str]` | `payoff_description: Optional[str] = None` |
| `data_origin` | `Optional[str]` | `data_origin: Optional[str] = None` |
| `status` | `str` | `status: str = 'lead'` |
| `notes` | `Optional[str]` | `notes: Optional[str] = None` |
| `next_action` | `Optional[str]` | `next_action: Optional[str] = None` |
| `next_action_date` | `Optional[str]` | `next_action_date: Optional[str] = None` |

## OpportunityUpdate

Source : `backend/app/api/opportunities.py:79`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `client_id` | `Optional[int]` | `client_id: Optional[int] = None` |
| `mandate_id` | `Optional[int]` | `mandate_id: Optional[int] = None` |
| `primary_affiliation_id` | `Optional[int]` | `primary_affiliation_id: Optional[int] = None` |
| `participants` | `Optional[list[ParticipantIn]]` | `participants: Optional[list[ParticipantIn]] = None` |
| `title` | `Optional[str]` | `title: Optional[str] = None` |
| `description` | `Optional[str]` | `description: Optional[str] = None` |
| `amount` | `Optional[float]` | `amount: Optional[float] = None` |
| `currency` | `Optional[str]` | `currency: Optional[str] = None` |
| `horizon` | `Optional[str]` | `horizon: Optional[str] = None` |
| `expected_trade_date` | `Optional[str]` | `expected_trade_date: Optional[str] = None` |
| `expected_window_start` | `Optional[str]` | `expected_window_start: Optional[str] = None` |
| `expected_window_end` | `Optional[str]` | `expected_window_end: Optional[str] = None` |
| `priority` | `Optional[str]` | `priority: Optional[str] = None` |
| `source` | `Optional[str]` | `source: Optional[str] = None` |
| `transaction_format` | `Optional[str]` | `transaction_format: Optional[str] = None` |
| `instrument_family` | `Optional[str]` | `instrument_family: Optional[str] = None` |
| `payoff_family` | `Optional[str]` | `payoff_family: Optional[str] = None` |
| `payoff_description` | `Optional[str]` | `payoff_description: Optional[str] = None` |
| `data_origin` | `Optional[str]` | `data_origin: Optional[str] = None` |
| `notes` | `Optional[str]` | `notes: Optional[str] = None` |
| `next_action` | `Optional[str]` | `next_action: Optional[str] = None` |
| `next_action_date` | `Optional[str]` | `next_action_date: Optional[str] = None` |
| `owner_user_id` | `Optional[int]` | `owner_user_id: Optional[int] = None` |

## StatusChange

Source : `backend/app/api/opportunities.py:105`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `status` | `str` | `status: str` |
| `lost_reason` | `Optional[str]` | `lost_reason: Optional[str] = None` |
| `lost_comment` | `Optional[str]` | `lost_comment: Optional[str] = None` |

## PersonCreate

Source : `backend/app/api/persons.py:40`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `first_name` | `str` | `first_name: str` |
| `last_name` | `str` | `last_name: str` |
| `email` | `Optional[str]` | `email: Optional[str] = None` |
| `phone` | `Optional[str]` | `phone: Optional[str] = None` |
| `notes` | `Optional[str]` | `notes: Optional[str] = None` |
| `confirm_duplicate` | `bool` | `confirm_duplicate: bool = False` |
| `client_id` | `Optional[int]` | `client_id: Optional[int] = None` |
| `job_title` | `str` | `job_title: str = ''` |
| `commercial_role` | `str` | `commercial_role: str = 'other'` |
| `start_date` | `Optional[str]` | `start_date: Optional[str] = None` |

## PersonUpdate

Source : `backend/app/api/persons.py:55`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `first_name` | `Optional[str]` | `first_name: Optional[str] = None` |
| `last_name` | `Optional[str]` | `last_name: Optional[str] = None` |
| `email` | `Optional[str]` | `email: Optional[str] = None` |
| `phone` | `Optional[str]` | `phone: Optional[str] = None` |
| `notes` | `Optional[str]` | `notes: Optional[str] = None` |

## AffiliationCreate

Source : `backend/app/api/persons.py:63`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `client_id` | `int` | `client_id: int` |
| `job_title` | `str` | `job_title: str = ''` |
| `commercial_role` | `str` | `commercial_role: str = 'other'` |
| `start_date` | `str` | `start_date: str` |
| `notes` | `Optional[str]` | `notes: Optional[str] = None` |

## AffiliationUpdate

Source : `backend/app/api/persons.py:71`. Bases : `BaseModel`.

Ce qu'on peut corriger sur une affiliation : sa description, jamais son rattachement. `client_id` et `person_id` sont volontairement absents — les changer réécrirait l'appartenance de tout ce qui pend à cette période.

| Champ | Type | Définition |
|---|---|---|
| `job_title` | `Optional[str]` | `job_title: Optional[str] = None` |
| `commercial_role` | `Optional[str]` | `commercial_role: Optional[str] = None` |
| `start_date` | `Optional[str]` | `start_date: Optional[str] = None` |
| `notes` | `Optional[str]` | `notes: Optional[str] = None` |

## ChangeCompany

Source : `backend/app/api/persons.py:81`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `new_client_id` | `int` | `new_client_id: int` |
| `start_date` | `str` | `start_date: str` |
| `job_title` | `str` | `job_title: str = ''` |
| `commercial_role` | `str` | `commercial_role: str = 'other'` |
| `end_date_previous` | `Optional[str]` | `end_date_previous: Optional[str] = None` |
| `notes` | `Optional[str]` | `notes: Optional[str] = None` |

## CloseAffiliation

Source : `backend/app/api/persons.py:90`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `end_date` | `str` | `end_date: str` |

## ContactCoverageUpsert

Source : `backend/app/api/persons.py:94`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `user_id` | `int` | `user_id: int` |
| `coverage_role` | `str` | `coverage_role: str = 'primary'` |

## PortfolioCreate

Source : `backend/app/api/portfolios.py:59`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `str` | `name: str` |
| `user_id` | `Optional[int]` | `user_id: Optional[int] = None` |

## PortfolioRename

Source : `backend/app/api/portfolios.py:66`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `str` | `name: str` |

## ProductCreate

Source : `backend/app/api/products.py:32`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `command_key` | `str` | `command_key: str = Field(min_length=8, max_length=100)` |
| `name` | `str` | `name: str = Field(default='', max_length=200)` |
| `pricing_input` | `dict` | `pricing_input: dict` |
| `pricing_receipt` | `dict \| None` | `pricing_receipt: dict \| None = None` |
| `listed` | `bool` | `listed: bool = True` |
| `intent` | `TradeIntent` | `intent: TradeIntent = Field(default_factory=TradeIntent)` |
| `commercial` | `CommercialContext` | `commercial: CommercialContext = Field(default_factory=CommercialContext)` |

## ProductUpdate

Source : `backend/app/api/products.py:42`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `expected_revision` | `int` | `expected_revision: int = Field(ge=1)` |
| `name` | `str \| None` | `name: str \| None = Field(default=None, max_length=200)` |
| `intent` | `TradeIntent \| None` | `intent: TradeIntent \| None = None` |
| `commercial` | `CommercialContext \| None` | `commercial: CommercialContext \| None = None` |
| `listed` | `bool \| None` | `listed: bool \| None = None` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=1000)` |

Méthodes/validators : `has_change:51`

## ProductTermsUpdate

Source : `backend/app/api/products.py:58`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `command_key` | `str` | `command_key: str = Field(min_length=8, max_length=100)` |
| `expected_revision` | `int` | `expected_revision: int = Field(ge=1)` |
| `pricing_input` | `dict` | `pricing_input: dict` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=1000)` |

## ProductArchive

Source : `backend/app/api/products.py:65`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `expected_revision` | `int` | `expected_revision: int = Field(ge=1)` |
| `archived` | `bool` | `archived: bool` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=1000)` |

## ProductPricingInput

Source : `backend/app/api/products.py:71`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `expected_terms_version` | `int` | `expected_terms_version: int = Field(ge=1)` |
| `context` | `dict` | `context: dict` |

## ProductCalculationCreate

Source : `backend/app/api/products.py:76`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `command_key` | `str` | `command_key: str = Field(min_length=8, max_length=100)` |
| `expected_revision` | `int` | `expected_revision: int = Field(ge=1)` |
| `pricing_receipt` | `dict` | `pricing_receipt: dict` |

## ProductBookingFork

Source : `backend/app/api/products.py:82`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `command_key` | `str` | `command_key: str = Field(min_length=8, max_length=100)` |
| `expected_revision` | `int` | `expected_revision: int = Field(ge=1)` |
| `expected_terms_version` | `int` | `expected_terms_version: int = Field(ge=1)` |
| `reason` | `str` | `reason: str = Field(min_length=10, max_length=1000)` |

## RfqCreate

Source : `backend/app/api/rfq.py:68`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `pilot_desk_id` | `Optional[int]` | `pilot_desk_id: Optional[int] = None` |
| `previous_round_id` | `Optional[int]` | `previous_round_id: Optional[int] = None` |
| `product_id` | `Optional[int]` | `product_id: Optional[int] = None` |
| `product_terms_version` | `Optional[int]` | `product_terms_version: Optional[int] = None` |
| `name` | `str` | `name: str` |
| `ao_date` | `Optional[str]` | `ao_date: Optional[str] = None` |
| `kind` | `str` | `kind: str = Field(default='indicatif', pattern='^(indicatif\|to_trade)$')` |
| `sens` | `str` | `sens: str = Field(default='achat', pattern='^(achat\|vente)$')` |
| `template_type` | `str` | `template_type: str = ''` |
| `script_id` | `Optional[int]` | `script_id: Optional[int] = None` |
| `script_snapshot` | `str` | `script_snapshot: str` |
| `params` | `dict` | `params: dict = {}` |
| `opportunity_id` | `Optional[int]` | `opportunity_id: Optional[int] = None` |
| `client_id` | `Optional[int]` | `client_id: Optional[int] = None` |
| `mandate_id` | `Optional[int]` | `mandate_id: Optional[int] = None` |
| `primary_affiliation_id` | `Optional[int]` | `primary_affiliation_id: Optional[int] = None` |
| `transaction_format` | `Optional[str]` | `transaction_format: Optional[str] = None` |
| `instrument_family` | `Optional[str]` | `instrument_family: Optional[str] = None` |
| `payoff_family` | `Optional[str]` | `payoff_family: Optional[str] = None` |
| `payoff_description` | `Optional[str]` | `payoff_description: Optional[str] = None` |
| `documentation_reference` | `Optional[str]` | `documentation_reference: Optional[str] = None` |

## RfqUpdate

Source : `backend/app/api/rfq.py:101`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `Optional[str]` | `name: Optional[str] = None` |
| `ao_date` | `Optional[str]` | `ao_date: Optional[str] = None` |
| `sens` | `Optional[str]` | `sens: Optional[str] = Field(default=None, pattern='^(achat\|vente)$')` |
| `params` | `Optional[dict]` | `params: Optional[dict] = None` |
| `pricing_params` | `Optional[dict]` | `pricing_params: Optional[dict] = None` |
| `status` | `Optional[str]` | `status: Optional[str] = None` |
| `model_price` | `Optional[float]` | `model_price: Optional[float] = None` |
| `pricing_receipt` | `Optional[dict]` | `pricing_receipt: Optional[dict] = None` |
| `expected_model_input_hash` | `Optional[str]` | `expected_model_input_hash: Optional[str] = Field(default=None, min_length=64, max_length=64)` |
| `selected_quote_id` | `Optional[int]` | `selected_quote_id: Optional[int] = None` |
| `expected_quote_revision` | `Optional[int]` | `expected_quote_revision: Optional[int] = Field(default=None, ge=1)` |
| `selection_reason_code` | `Optional[str]` | `selection_reason_code: Optional[str] = Field(default=None, pattern='^(price\|client_request\|documentation\|credit\|concentration\|relationship\|execution_quality\|other)$')` |
| `selection_reason_note` | `Optional[str]` | `selection_reason_note: Optional[str] = None` |
| `opportunity_id` | `Optional[int]` | `opportunity_id: Optional[int] = None` |
| `client_id` | `Optional[int]` | `client_id: Optional[int] = None` |
| `mandate_id` | `Optional[int]` | `mandate_id: Optional[int] = None` |
| `primary_affiliation_id` | `Optional[int]` | `primary_affiliation_id: Optional[int] = None` |
| `transaction_format` | `Optional[str]` | `transaction_format: Optional[str] = None` |
| `instrument_family` | `Optional[str]` | `instrument_family: Optional[str] = None` |
| `payoff_family` | `Optional[str]` | `payoff_family: Optional[str] = None` |
| `payoff_description` | `Optional[str]` | `payoff_description: Optional[str] = None` |
| `documentation_reference` | `Optional[str]` | `documentation_reference: Optional[str] = None` |

## RfqExchangePreview

Source : `backend/app/api/rfq.py:135`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `expected_terms_version` | `int` | `expected_terms_version: int = Field(gt=0)` |
| `shared_title` | `str` | `shared_title: str = Field(min_length=1, max_length=200)` |
| `response_deadline` | `datetime` | `response_deadline: datetime` |
| `provider_ids` | `list[int]` | `provider_ids: list[int] = Field(default_factory=list, max_length=50)` |
| `relationship_ids` | `list[int]` | `relationship_ids: list[int] = Field(default_factory=list, max_length=50)` |

Méthodes/validators : `recipients:143`

## RfqSharePut

Source : `backend/app/api/rfq.py:154`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `rights` | `list[str]` | `rights: list[str] = Field(min_length=1)` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=500)` |
| `expires_at` | `Optional[datetime]` | `expires_at: Optional[datetime] = None` |

## RfqAssignmentPut

Source : `backend/app/api/rfq.py:160`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `pilot_desk_id` | `int` | `pilot_desk_id: int` |
| `responsible_user_id` | `int` | `responsible_user_id: int` |
| `expected_pilot_desk_id` | `int` | `expected_pilot_desk_id: int` |
| `expected_responsible_user_id` | `Optional[int]` | `expected_responsible_user_id: Optional[int] = None` |
| `expected_share_desk_ids` | `list[int]` | `expected_share_desk_ids: list[int]` |
| `retained_share_desk_ids` | `list[int]` | `retained_share_desk_ids: list[int]` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=500)` |

## QuoteCreate

Source : `backend/app/api/rfq.py:170`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `provider` | `str` | `provider: str = Field(default='manuel', min_length=1)` |
| `contact` | `Optional[str]` | `contact: Optional[str] = None` |
| `note` | `Optional[str]` | `note: Optional[str] = None` |
| `provider_id` | `Optional[int]` | `provider_id: Optional[int] = None` |
| `counterparty_id` | `Optional[int]` | `counterparty_id: Optional[int] = None` |

## QuoteUpdate

Source : `backend/app/api/rfq.py:178`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `expected_revision` | `Optional[int]` | `expected_revision: Optional[int] = Field(default=None, ge=1)` |
| `counterparty_id` | `Optional[int]` | `counterparty_id: Optional[int] = None` |
| `identity_reason` | `Optional[str]` | `identity_reason: Optional[str] = Field(default=None, min_length=3, max_length=500)` |
| `price` | `Optional[float]` | `price: Optional[float] = Field(default=None, allow_inf_nan=False)` |
| `currency` | `Optional[str]` | `currency: Optional[str] = None` |
| `status` | `Optional[str]` | `status: Optional[str] = Field(default=None, pattern='^(en_attente\|recu\|decline\|expire)$')` |
| `note` | `Optional[str]` | `note: Optional[str] = None` |
| `quoted_at` | `Optional[str]` | `quoted_at: Optional[str] = None` |
| `firmness` | `Optional[str]` | `firmness: Optional[str] = Field(default=None, pattern='^(UNKNOWN\|INDICATIVE\|FIRM)$')` |
| `valid_until` | `Optional[str]` | `valid_until: Optional[str] = None` |
| `last_look` | `Optional[bool]` | `last_look: Optional[bool] = None` |

## TreatmentCancellation

Source : `backend/app/api/rfq.py:926`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=500)` |

## DeskCreate

Source : `backend/app/api/rfq_desks.py:21`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `entity_id` | `int` | `entity_id: int` |
| `name` | `str` | `name: str = Field(min_length=1, max_length=100)` |

## MembershipPut

Source : `backend/app/api/rfq_desks.py:26`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `user_id` | `int` | `user_id: int` |
| `rights` | `list[str]` | `rights: list[str] = Field(min_length=1)` |
| `expires_at` | `datetime \| None` | `expires_at: datetime \| None = None` |
| `active` | `bool` | `active: bool = True` |

## Withdrawal

Source : `backend/app/api/rfq_inbox.py:89`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `publication_id` | `int` | `publication_id: int` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=500)` |

## BankAssignment

Source : `backend/app/api/rfq_inbox.py:101`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `responsible_user_id` | `int` | `responsible_user_id: int` |
| `expected_revision` | `int` | `expected_revision: int = Field(ge=1)` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=500)` |

## ChannelCreate

Source : `backend/app/api/rfq_transport.py:50`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `relationship_id` | `int` | `relationship_id: int` |
| `expected_version` | `int` | `expected_version: int = Field(ge=1)` |
| `role` | `Literal['REQUESTER', 'BANK']` | `role: Literal['REQUESTER', 'BANK']` |
| `peer_installation_id` | `UUID` | `peer_installation_id: UUID` |
| `peer_url` | `str` | `peer_url: str = Field(max_length=500)` |
| `channel_id` | `UUID \| None` | `channel_id: UUID \| None = None` |
| `secret` | `str \| None` | `secret: str \| None = Field(default=None, pattern='^[0-9a-f]{64}$')` |
| `peer_counterparty_id` | `int` | `peer_counterparty_id: int` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=500)` |

## ChannelState

Source : `backend/app/api/rfq_transport.py:63`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `active` | `bool` | `active: bool` |
| `expected_version` | `int` | `expected_version: int = Field(ge=1)` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=500)` |

## ScriptCreate

Source : `backend/app/api/scripts_db.py:18`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `str` | `name: str` |
| `description` | `str` | `description: str = ''` |
| `folder_id` | `int \| None` | `folder_id: int \| None = None` |
| `script_text` | `str` | `script_text: str = ''` |
| `params_json` | `str` | `params_json: str = '{}'` |
| `constats_json` | `str` | `constats_json: str = '{}'` |
| `global_params_json` | `str` | `global_params_json: str = '{}'` |
| `category` | `str` | `category: str = ''` |
| `tags` | `str` | `tags: str = ''` |
| `is_shared` | `bool` | `is_shared: bool = False` |
| `ai_provider` | `str` | `ai_provider: str = ''` |
| `ai_model` | `str` | `ai_model: str = ''` |
| `ai_prompt` | `str` | `ai_prompt: str = ''` |
| `ai_generated_at` | `datetime \| None` | `ai_generated_at: datetime \| None = None` |
| `ai_provenance_json` | `str` | `ai_provenance_json: str = '{}'` |

## ScriptUpdate

Source : `backend/app/api/scripts_db.py:36`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `str \| None` | `name: str \| None = None` |
| `description` | `str \| None` | `description: str \| None = None` |
| `folder_id` | `int \| None` | `folder_id: int \| None = None` |
| `script_text` | `str \| None` | `script_text: str \| None = None` |
| `params_json` | `str \| None` | `params_json: str \| None = None` |
| `constats_json` | `str \| None` | `constats_json: str \| None = None` |
| `global_params_json` | `str \| None` | `global_params_json: str \| None = None` |
| `category` | `str \| None` | `category: str \| None = None` |
| `tags` | `str \| None` | `tags: str \| None = None` |
| `is_shared` | `bool \| None` | `is_shared: bool \| None = None` |
| `ai_provider` | `str \| None` | `ai_provider: str \| None = None` |
| `ai_model` | `str \| None` | `ai_model: str \| None = None` |
| `ai_prompt` | `str \| None` | `ai_prompt: str \| None = None` |
| `ai_generated_at` | `datetime \| None` | `ai_generated_at: datetime \| None = None` |
| `ai_provenance_json` | `str \| None` | `ai_provenance_json: str \| None = None` |

## VariantCreate

Source : `backend/app/api/scripts_db.py:303`. Bases : `BaseModel`.

Ce qu'il faut pour décliner un deal : un titre, un mode, des écarts.

| Champ | Type | Définition |
|---|---|---|
| `variant_title` | `str` | `variant_title: str` |
| `variant_mode` | `str` | `variant_mode: str = MODE_AVENANT` |
| `delta` | `dict` | `delta: dict = {}` |

## VariantUpdate

Source : `backend/app/api/scripts_db.py:310`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `variant_title` | `str \| None` | `variant_title: str \| None = None` |
| `variant_mode` | `str \| None` | `variant_mode: str \| None = None` |
| `delta` | `dict \| None` | `delta: dict \| None = None` |

## ShockOverride

Source : `backend/app/api/shocks.py:39`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `spot_shock_pct` | `Optional[float]` | `spot_shock_pct: Optional[float] = None` |
| `vol_shock_pts` | `Optional[float]` | `vol_shock_pts: Optional[float] = None` |

## SmileUnderlyingOverride

Source : `backend/app/api/shocks.py:59`. Bases : `BaseModel`.

Optional model parameters for one named/ticker underlying.  Values are shifts in displayed percentage points. They map to parameters with the same name; there is deliberately no hidden conversion from a generic "skew" into a SABR or Heston calibration parameter.

| Champ | Type | Définition |
|---|---|---|
| `atm_vol_pts` | `Optional[float]` | `atm_vol_pts: Optional[float] = None` |
| `skew_pts` | `Optional[float]` | `skew_pts: Optional[float] = None` |
| `curvature_pts` | `Optional[float]` | `curvature_pts: Optional[float] = None` |
| `sabr_alpha_pts` | `Optional[float]` | `sabr_alpha_pts: Optional[float] = None` |
| `sabr_rho_pts` | `Optional[float]` | `sabr_rho_pts: Optional[float] = None` |
| `sabr_nu_pts` | `Optional[float]` | `sabr_nu_pts: Optional[float] = None` |
| `heston_v0_pts` | `Optional[float]` | `heston_v0_pts: Optional[float] = None` |
| `heston_theta_pts` | `Optional[float]` | `heston_theta_pts: Optional[float] = None` |
| `heston_rho_pts` | `Optional[float]` | `heston_rho_pts: Optional[float] = None` |
| `heston_xi_pts` | `Optional[float]` | `heston_xi_pts: Optional[float] = None` |

## RelationshipTerms

Source : `backend/app/api/trading.py:36`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid', allow_inf_nan=False)`

| Champ | Type | Définition |
|---|---|---|
| `counterparty_id` | `int` | `counterparty_id: int` |
| `reference` | `str` | `reference: str = Field(min_length=3, max_length=100)` |
| `status` | `Literal['PENDING', 'ACTIVE', 'SUSPENDED', 'EXPIRED']` | `status: Literal['PENDING', 'ACTIVE', 'SUSPENDED', 'EXPIRED'] = 'PENDING'` |
| `effective_date` | `date` | `effective_date: date` |
| `expiry_date` | `date \| None` | `expiry_date: date \| None = None` |
| `currency` | `str` | `currency: str = 'EUR'` |
| `note_distribution_allowed` | `bool` | `note_distribution_allowed: bool = False` |
| `otc_allowed` | `bool` | `otc_allowed: bool = False` |
| `documentation_reference` | `str` | `documentation_reference: str = Field(default='', max_length=1000)` |
| `gross_notional_limit` | `float` | `gross_notional_limit: float = Field(default=100000000, gt=0)` |
| `master_agreement_id` | `int \| None` | `master_agreement_id: int \| None = None` |
| `csa_id` | `int \| None` | `csa_id: int \| None = None` |
| `csa_required` | `bool` | `csa_required: bool = False` |
| `settlement` | `Literal['DVP', 'FREE_OF_PAYMENT']` | `settlement: Literal['DVP', 'FREE_OF_PAYMENT'] = 'DVP'` |
| `notes` | `str` | `notes: str = Field(default='', max_length=3000)` |

Méthodes/validators : `dates:55`

## NoteBooking

Source : `backend/app/api/trading.py:145`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `trade_reference` | `str` | `trade_reference: str = Field(min_length=6, max_length=100)` |
| `relationship_id` | `int` | `relationship_id: int` |
| `issuer` | `str` | `issuer: str = Field(min_length=1, max_length=200)` |
| `our_side` | `Literal['BUY', 'SELL']` | `our_side: Literal['BUY', 'SELL']` |
| `instrument_reference` | `str` | `instrument_reference: str = Field(min_length=5, max_length=100)` |
| `deal` | `DealCreate` | `deal: DealCreate` |

## SettlementProof

Source : `backend/app/api/trading.py:257`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `reference` | `str` | `reference: str = Field(min_length=5, max_length=200)` |

## CreateNote

Source : `backend/app/api/valuation_notes.py:24`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `deal_id` | `int` | `deal_id: int` |
| `run_ids` | `list[int]` | `run_ids: list[int] = Field(min_length=1, max_length=2)` |
| `request_key` | `UUID` | `request_key: UUID` |

## Editorial

Source : `backend/app/api/valuation_notes.py:31`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `synthese` | `str` | `synthese: str = Field(default='', max_length=12000)` |
| `analyse` | `str` | `analyse: str = Field(default='', max_length=12000)` |
| `contexte` | `str` | `contexte: str = Field(default='', max_length=12000)` |
| `conclusion` | `str` | `conclusion: str = Field(default='', max_length=12000)` |

## Revision

Source : `backend/app/api/valuation_notes.py:39`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `revision` | `int` | `revision: int = Field(ge=1)` |

## VarRequest

Source : `backend/app/api/var.py:40`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `data_scope` | `Literal['PRODUCTION', 'UAT']` | `data_scope: Literal['PRODUCTION', 'UAT'] = 'PRODUCTION'` |
| `method` | `Literal['historical', 'parametric', 'both']` | `method: Literal['historical', 'parametric', 'both'] = 'both'` |
| `confidence` | `float` | `confidence: float = 0.95` |
| `horizon_days` | `int` | `horizon_days: int = Field(default=1, ge=1, le=20)` |
| `lookback_years` | `float` | `lookback_years: float = Field(default=5.0, ge=0.5, le=10.0)` |
| `n_parametric` | `int` | `n_parametric: int = Field(default=2000, ge=100, le=5000)` |
| `n_paths_per_scenario` | `int` | `n_paths_per_scenario: int = Field(default=3000, ge=1000, le=20000)` |
| `max_workers` | `int` | `max_workers: int = Field(default=4, ge=1, le=4)` |
| `confirmation_token` | `str \| None` | `confirmation_token: str \| None = None` |

## CompareRequest

Source : `backend/app/api/variants.py:39`. Bases : `BaseModel`.

Le corps du parent, tel que l'écran l'envoie, plus les variantes à situer.

| Champ | Type | Définition |
|---|---|---|
| `base` | `dict` | `base: dict` |
| `parent_id` | `Optional[int]` | `parent_id: Optional[int] = None` |
| `variant_ids` | `list[int]` | `variant_ids: list[int] = Field(default_factory=list)` |
| `N` | `int` | `N: int = Field(default=8000, ge=1000, le=50000)` |
| `roll_financing` | `RollFinancing` | `roll_financing: RollFinancing = Field(default_factory=RollFinancing)` |

## SurfaceRequest

Source : `backend/app/api/volatility.py:15`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `surface` | `VolatilitySurfaceParams` | `surface: VolatilitySurfaceParams` |

## PromptOverride

Source : `backend/app/core/ai_contract.py:5`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `base_hash` | `str` | `base_hash: str = Field(min_length=64, max_length=64)` |
| `system` | `str` | `system: str = Field(min_length=1, max_length=200000)` |
| `user` | `str` | `user: str = Field(min_length=1, max_length=400000)` |

## AiOptions

Source : `backend/app/core/ai_contract.py:11`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `provider` | `str` | `provider: str = 'ollama'` |
| `model` | `str \| None` | `model: str \| None = Field(default=None, max_length=160)` |
| `ollama_url` | `str` | `ollama_url: str = Field(default='http://localhost:11434', max_length=500)` |
| `api_key` | `str` | `api_key: str = Field(default='', max_length=1000, repr=False)` |
| `prompt_override` | `PromptOverride \| None` | `prompt_override: PromptOverride \| None = None` |

## DividendPolicy

Source : `backend/app/core/amc_dividends.py:14`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid', allow_inf_nan=False)`

| Champ | Type | Définition |
|---|---|---|
| `status` | `Literal['unknown', 'none', 'provided']` | `status: Literal['unknown', 'none', 'provided'] = 'unknown'` |
| `treatment` | `Literal['cash', 'automatic', 'discretionary']` | `treatment: Literal['cash', 'automatic', 'discretionary'] = 'cash'` |
| `destination` | `Literal['same_asset', 'basket']` | `destination: Literal['same_asset', 'basket'] = 'same_asset'` |
| `allocations` | `dict[str, float]` | `allocations: dict[str, float] = Field(default_factory=dict)` |
| `execution_source` | `Literal['orders', 'reconstruct']` | `execution_source: Literal['orders', 'reconstruct'] = 'orders'` |
| `delay_weekdays` | `int` | `delay_weekdays: int = Field(default=0, ge=0, le=365)` |
| `fractional_shares` | `bool` | `fractional_shares: bool = True` |
| `reinvestment_fee_pct` | `float \| None` | `reinvestment_fee_pct: float \| None = Field(default=None, ge=0, lt=100)` |
| `documentation` | `str` | `documentation: str = ''` |

Méthodes/validators : `validate_policy:27`

## Execution

Source : `backend/app/core/amc_dividends.py:37`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid', allow_inf_nan=False)`

| Champ | Type | Définition |
|---|---|---|
| `asset_id` | `str` | `asset_id: str = Field(min_length=1)` |
| `date` | `dt.date` | `date: dt.date` |
| `order_id` | `str \| None` | `order_id: str \| None = None` |
| `price_local` | `float \| None` | `price_local: float \| None = Field(default=None, gt=0)` |
| `currency` | `str \| None` | `currency: str \| None = Field(default=None, pattern='^[A-Z]{3}$')` |
| `fx_to_fund` | `float \| None` | `fx_to_fund: float \| None = Field(default=None, gt=0)` |

## DividendEvent

Source : `backend/app/core/amc_dividends.py:47`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid', allow_inf_nan=False)`

| Champ | Type | Définition |
|---|---|---|
| `id` | `str` | `id: str = Field(min_length=1)` |
| `asset_id` | `str` | `asset_id: str = Field(min_length=1)` |
| `currency` | `str` | `currency: str = Field(pattern='^[A-Z]{3}$')` |
| `ex_date` | `dt.date` | `ex_date: dt.date` |
| `payment_date` | `dt.date` | `payment_date: dt.date` |
| `eligible_quantity` | `float \| None` | `eligible_quantity: float \| None = Field(default=None, ge=0)` |
| `entitlement_unit_factor` | `float` | `entitlement_unit_factor: float = Field(default=1, gt=0)` |
| `gross_per_share` | `float \| None` | `gross_per_share: float \| None = Field(default=None, ge=0)` |
| `gross_local` | `float \| None` | `gross_local: float \| None = Field(default=None, ge=0)` |
| `net_local` | `float \| None` | `net_local: float \| None = Field(default=None, ge=0)` |
| `withholding_local` | `float \| None` | `withholding_local: float \| None = Field(default=None, ge=0)` |
| `withholding_rate` | `float \| None` | `withholding_rate: float \| None = Field(default=None, ge=0, le=1)` |
| `fx_at_ex` | `float \| None` | `fx_at_ex: float \| None = Field(default=None, gt=0)` |
| `fx_at_payment` | `float \| None` | `fx_at_payment: float \| None = Field(default=None, gt=0)` |
| `fx_at_valuation` | `float \| None` | `fx_at_valuation: float \| None = Field(default=None, gt=0)` |
| `fx_valuation_date` | `dt.date \| None` | `fx_valuation_date: dt.date \| None = None` |
| `executions` | `list[Execution]` | `executions: list[Execution] = Field(default_factory=list)` |

Méthodes/validators : `validate_event:69`

## ProductInfo

Source : `backend/app/core/amc_manifest.py:32`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `isin` | `str` | `isin: str` |
| `name` | `str` | `name: str = ''` |
| `currency` | `str` | `currency: str = Field(default='CHF', pattern='^[A-Z]{3}$')` |
| `theme` | `str` | `theme: str = ''` |

## FileRoles

Source : `backend/app/core/amc_manifest.py:39`. Bases : `BaseModel`.

Paths are relative to the study folder (manifest lives there).

| Champ | Type | Définition |
|---|---|---|
| `market_data` | `str` | `market_data: str = ''` |
| `dividends` | `str` | `dividends: str = ''` |
| `cash_events` | `str` | `cash_events: str = ''` |
| `composition` | `str` | `composition: str = ''` |
| `nav_timeseries` | `str` | `nav_timeseries: str = ''` |
| `orders` | `List[str]` | `orders: List[str] = Field(default_factory=list, max_length=100)` |

## TermsheetPosition

Source : `backend/app/core/amc_manifest.py:49`. Bases : `BaseModel`.

One equity line from the AMC term sheet. Used for the Référentiel Inertiel (Bloc E).

| Champ | Type | Définition |
|---|---|---|
| `isin` | `str` | `isin: str` |
| `name` | `str` | `name: str = ''` |
| `weight_pct` | `float` | `weight_pct: float` |
| `qty_per_cert` | `float` | `qty_per_cert: float` |
| `fixing_price` | `float` | `fixing_price: float = 0.0` |
| `ccy` | `str` | `ccy: str = 'USD'` |

## ReferencePortfolio

Source : `backend/app/core/amc_manifest.py:62`. Bases : `BaseModel`.

Passive comparison basket, never seeded into the actual FIFO portfolio.

| Champ | Type | Définition |
|---|---|---|
| `start_date` | `str` | `start_date: str` |
| `positions` | `List[TermsheetPosition]` | `positions: List[TermsheetPosition] = Field(min_length=1, max_length=500)` |

Méthodes/validators : `validate_reference:68`

## ManualParams

Source : `backend/app/core/amc_manifest.py:82`. Bases : `BaseModel`.

Inputs that are NOT present in the raw exports — must be supplied.

- `model_config = ConfigDict(allow_inf_nan=False)`

| Champ | Type | Définition |
|---|---|---|
| `reference_portfolio` | `Optional[ReferencePortfolio]` | `reference_portfolio: Optional[ReferencePortfolio] = None` |
| `dividends` | `DividendPolicy` | `dividends: DividendPolicy = Field(default_factory=DividendPolicy)` |
| `as_of` | `Optional[str]` | `as_of: Optional[str] = None` |
| `management_fee_basis` | `Literal['nav_252', 'previous_nav_act365', 'current_nav_act365', 'previous_nav_act360', 'current_nav_act360']` | `management_fee_basis: Literal['nav_252', 'previous_nav_act365', 'current_nav_act365', 'previous_nav_act360', 'current_nav_act360'] = 'nav_252'` |
| `performance_crystallization` | `Literal['daily', 'monthly', 'quarterly', 'annual']` | `performance_crystallization: Literal['daily', 'monthly', 'quarterly', 'annual'] = 'daily'` |
| `valuation_source` | `Literal['market', 'composition']` | `valuation_source: Literal['market', 'composition'] = 'market'` |
| `orders_split_adjusted` | `bool` | `orders_split_adjusted: bool = False` |
| `management_fee_pct` | `Optional[float]` | `management_fee_pct: Optional[float] = Field(default=None, ge=0, lt=100)` |
| `perf_fee_pct` | `Optional[float]` | `perf_fee_pct: Optional[float] = Field(default=None, ge=0, lt=100)` |
| `txn_cost_pct` | `Optional[float]` | `txn_cost_pct: Optional[float] = Field(default=None, ge=0, lt=100)` |
| `benchmark_ticker` | `str` | `benchmark_ticker: str = 'ACWI'` |
| `factor_model` | `Literal['FF3', 'FF5', 'FF5+MOM']` | `factor_model: Literal['FF3', 'FF5', 'FF5+MOM'] = 'FF5+MOM'` |
| `ff_series` | `str` | `ff_series: str = 'Developed_5F'` |
| `selected_factors` | `Optional[List[str]]` | `selected_factors: Optional[List[str]] = None` |
| `rolling_window` | `int` | `rolling_window: int = Field(default=60, ge=20, le=2520)` |
| `risk_free` | `str` | `risk_free: str = 'auto'` |
| `long_term_holding_days` | `int` | `long_term_holding_days: int = Field(default=180, ge=1, le=36500)` |
| `conviction_weight_pct` | `float` | `conviction_weight_pct: float = Field(default=4.0, ge=0, le=100)` |
| `recon_mode` | `Literal['strict', 't0_synthetic']` | `recon_mode: Literal['strict', 't0_synthetic'] = 'strict'` |
| `n_certs` | `int` | `n_certs: int = Field(default=75000, gt=0)` |
| `termsheet_positions` | `List[TermsheetPosition]` | `termsheet_positions: List[TermsheetPosition] = Field(default_factory=list, max_length=500)` |

Méthodes/validators : `validate_economics:116`

## BlockToggles

Source : `backend/app/core/amc_manifest.py:131`. Bases : `BaseModel`.

Run the complete study or any subset. B/C/D share the order-book parser.

| Champ | Type | Définition |
|---|---|---|
| `E_bh` | `bool` | `E_bh: bool = True` |
| `G_brinson` | `bool` | `G_brinson: bool = False` |
| `A_factor` | `bool` | `A_factor: bool = True` |
| `B_attribution` | `bool` | `B_attribution: bool = True` |
| `C_trading` | `bool` | `C_trading: bool = True` |
| `D_behaviour` | `bool` | `D_behaviour: bool = True` |
| `F_replicability` | `bool` | `F_replicability: bool = True` |
| `H_timing` | `bool` | `H_timing: bool = True` |
| `I_stockpicking` | `bool` | `I_stockpicking: bool = True` |
| `J_riskmanagement` | `bool` | `J_riskmanagement: bool = True` |
| `K_marketshocks` | `bool` | `K_marketshocks: bool = False` |

## OutputOptions

Source : `backend/app/core/amc_manifest.py:148`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `language` | `str` | `language: str = 'fr'` |
| `audience` | `str` | `audience: str = 'committee'` |

## StudyManifest

Source : `backend/app/core/amc_manifest.py:153`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `schema_version` | `str` | `schema_version: str = '1.0'` |
| `product` | `ProductInfo` | `product: ProductInfo` |
| `files` | `FileRoles` | `files: FileRoles` |
| `params` | `ManualParams` | `params: ManualParams = Field(default_factory=ManualParams)` |
| `blocks` | `BlockToggles` | `blocks: BlockToggles = Field(default_factory=BlockToggles)` |
| `output` | `OutputOptions` | `output: OutputOptions = Field(default_factory=OutputOptions)` |

## LegalIdentityExceptionRequest

Source : `backend/app/core/booking_contract.py:6`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `reason` | `str` | `reason: str` |

## DealCreate

Source : `backend/app/core/booking_contract.py:11`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `command_key` | `Optional[str]` | `command_key: Optional[str] = Field(default=None, min_length=8, max_length=100)` |
| `counterparty_id` | `Optional[int]` | `counterparty_id: Optional[int] = None` |
| `legal_identity_exception` | `Optional[LegalIdentityExceptionRequest]` | `legal_identity_exception: Optional[LegalIdentityExceptionRequest] = None` |
| `ccr_netting_set_id` | `Optional[int]` | `ccr_netting_set_id: Optional[int] = None` |
| `product_id` | `Optional[int]` | `product_id: Optional[int] = None` |
| `product_terms_version` | `Optional[int]` | `product_terms_version: Optional[int] = None` |
| `sens` | `Literal['achat', 'vente']` | `sens: Literal['achat', 'vente'] = 'vente'` |
| `contrepartie` | `str` | `contrepartie: str` |
| `devise` | `str` | `devise: str = 'EUR'` |
| `product_type` | `str` | `product_type: str = ''` |
| `fixing_policy` | `Literal['AUTO_YAHOO']` | `fixing_policy: Literal['AUTO_YAHOO'] = 'AUTO_YAHOO'` |
| `nominal` | `float` | `nominal: float` |
| `fair_value` | `float` | `fair_value: float` |
| `price_traded` | `float` | `price_traded: float` |
| `trade_date` | `str` | `trade_date: str` |
| `strike_date` | `str` | `strike_date: str` |
| `value_date` | `str` | `value_date: str` |
| `maturity_date` | `str` | `maturity_date: str` |
| `payment_date` | `str` | `payment_date: str = ''` |
| `T` | `float` | `T: float` |
| `underlyings` | `List[dict]` | `underlyings: List[dict]` |
| `observation_times` | `List[float]` | `observation_times: List[float]` |
| `script_snapshot` | `str` | `script_snapshot: str` |
| `script_id` | `Optional[int]` | `script_id: Optional[int] = None` |
| `market_snapshot` | `dict` | `market_snapshot: dict = {}` |
| `pricing_receipt` | `Optional[dict]` | `pricing_receipt: Optional[dict] = None` |
| `indicative_id` | `Optional[int]` | `indicative_id: Optional[int] = None` |
| `rfq_id` | `Optional[int]` | `rfq_id: Optional[int] = None` |
| `execution_agreement_id` | `Optional[int]` | `execution_agreement_id: Optional[int] = None` |
| `client_id` | `Optional[int]` | `client_id: Optional[int] = None` |
| `opportunity_id` | `Optional[int]` | `opportunity_id: Optional[int] = None` |
| `primary_affiliation_id` | `Optional[int]` | `primary_affiliation_id: Optional[int] = None` |
| `mandate_id` | `Optional[int]` | `mandate_id: Optional[int] = None` |
| `transaction_format` | `Optional[str]` | `transaction_format: Optional[str] = None` |
| `instrument_family` | `Optional[str]` | `instrument_family: Optional[str] = None` |
| `payoff_family` | `Optional[str]` | `payoff_family: Optional[str] = None` |
| `payoff_description` | `Optional[str]` | `payoff_description: Optional[str] = None` |
| `documentation_reference` | `Optional[str]` | `documentation_reference: Optional[str] = None` |
| `commercial_reason` | `Optional[str]` | `commercial_reason: Optional[str] = None` |

## Contract

Source : `backend/app/core/ccr/contracts.py:10`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid', allow_inf_nan=False)`

## MtmOverrideUL

Source : `backend/app/core/deal_valuation.py:38`. Bases : `BaseModel`.

Manual per-underlying override in display units.

| Champ | Type | Définition |
|---|---|---|
| `sigma` | `Optional[float]` | `sigma: Optional[float] = None` |
| `q` | `Optional[float]` | `q: Optional[float] = None` |

## MtmRequest

Source : `backend/app/core/deal_valuation.py:44`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `recalibrate` | `Literal['none', 'realized']` | `recalibrate: Literal['none', 'realized'] = 'none'` |
| `overrides` | `Optional[dict[str, MtmOverrideUL]]` | `overrides: Optional[dict[str, MtmOverrideUL]] = None` |
| `r` | `Optional[float]` | `r: Optional[float] = None` |
| `window_days` | `int` | `window_days: int = 252` |
| `valuation_date` | `Optional[date]` | `valuation_date: Optional[date] = None` |
| `funding_curve` | `Optional[List[List[float]]]` | `funding_curve: Optional[List[List[float]]] = None` |
| `funding_spread` | `Optional[float]` | `funding_spread: Optional[float] = Field(default=None, ge=-0.05, le=0.5)` |
| `funding_source_reference` | `Optional[str]` | `funding_source_reference: Optional[str] = Field(default=None, max_length=300)` |

Méthodes/validators : `validate_funding:56`

## FrozenModel

Source : `backend/app/core/product/models.py:15`. Bases : `BaseModel`.

- `model_config = ConfigDict(frozen=True, extra='forbid', allow_inf_nan=False)`

## UnderlyingIdentity

Source : `backend/app/core/product/models.py:49`. Bases : `FrozenModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `str` | `name: str = Field(min_length=1)` |
| `ticker` | `str` | `ticker: str = ''` |
| `ccy` | `str` | `ccy: str = Field(min_length=3, max_length=3)` |

## ContractParameter

Source : `backend/app/core/product/models.py:55`. Bases : `FrozenModel`.

| Champ | Type | Définition |
|---|---|---|
| `name` | `str` | `name: str = Field(min_length=1)` |
| `value` | `float \| tuple[float \| None, ...] \| None` | `value: float \| tuple[float \| None, ...] \| None` |
| `is_pct` | `bool` | `is_pct: bool` |
| `kind` | `Literal['scalar', 'array']` | `kind: Literal['scalar', 'array']` |
| `description` | `str` | `description: str = ''` |

Méthodes/validators : `shape:63`

## ProductTerms

Source : `backend/app/core/product/models.py:69`. Bases : `FrozenModel`.

| Champ | Type | Définition |
|---|---|---|
| `schema_version` | `Literal[1]` | `schema_version: Literal[1] = 1` |
| `script` | `str` | `script: str = Field(min_length=1, max_length=32000)` |
| `parameters` | `tuple[ContractParameter, ...]` | `parameters: tuple[ContractParameter, ...] = ()` |
| `underlyings` | `tuple[UnderlyingIdentity, ...]` | `underlyings: tuple[UnderlyingIdentity, ...] = Field(default=(), max_length=12)` |
| `constats` | `FrozenObject` | `constats: FrozenObject = Field(default_factory=FrozenObject)` |
| `T` | `float \| None` | `T: float \| None = Field(default=None, gt=0, le=30)` |
| `strike_date` | `date \| None` | `strike_date: date \| None = None` |
| `value_date` | `date \| None` | `value_date: date \| None = None` |
| `maturity_date` | `date \| None` | `maturity_date: date \| None = None` |
| `payment_date` | `date \| None` | `payment_date: date \| None = None` |
| `anchor` | `date \| None` | `anchor: date \| None = None` |
| `settlement_ccy` | `str \| None` | `settlement_ccy: str \| None = None` |
| `schedule` | `FrozenObject \| None` | `schedule: FrozenObject \| None = None` |
| `resolved_events` | `FrozenObject \| None` | `resolved_events: FrozenObject \| None = None` |
| `schedule_error` | `str \| None` | `schedule_error: str \| None = None` |

Méthodes/validators : `identities:87`; `fingerprint:101`; `user_params:104`; `require_complete:108`; `pricing_fields:122`

## TradeIntent

Source : `backend/app/core/product/models.py:136`. Bases : `FrozenModel`.

| Champ | Type | Définition |
|---|---|---|
| `nominal` | `float \| None` | `nominal: float \| None = Field(default=None, gt=0)` |
| `side` | `Literal['BUY', 'SELL']` | `side: Literal['BUY', 'SELL'] = 'BUY'` |
| `counterparty_id` | `int \| None` | `counterparty_id: int \| None = None` |
| `counterparty_name` | `str` | `counterparty_name: str = ''` |
| `product_type` | `str` | `product_type: str = ''` |
| `transaction_format` | `str` | `transaction_format: str = ''` |
| `instrument_family` | `str` | `instrument_family: str = ''` |
| `payoff_family` | `str` | `payoff_family: str = ''` |
| `payoff_description` | `str` | `payoff_description: str = ''` |
| `documentation_reference` | `str` | `documentation_reference: str = ''` |

## CommercialContext

Source : `backend/app/core/product/models.py:149`. Bases : `FrozenModel`.

| Champ | Type | Définition |
|---|---|---|
| `client_id` | `int \| None` | `client_id: int \| None = None` |
| `mandate_id` | `int \| None` | `mandate_id: int \| None = None` |
| `opportunity_id` | `int \| None` | `opportunity_id: int \| None = None` |
| `primary_affiliation_id` | `int \| None` | `primary_affiliation_id: int \| None = None` |

## CalculationRef

Source : `backend/app/core/product/models.py:156`. Bases : `FrozenModel`.

| Champ | Type | Définition |
|---|---|---|
| `id` | `int` | `id: int` |
| `terms_version` | `int` | `terms_version: int` |
| `kind` | `str` | `kind: str` |
| `calculated_at` | `str` | `calculated_at: str` |
| `valuation_date` | `str \| None` | `valuation_date: str \| None = None` |
| `price` | `float \| None` | `price: float \| None = None` |
| `source` | `str` | `source: str` |

## Product

Source : `backend/app/core/product/models.py:166`. Bases : `FrozenModel`.

| Champ | Type | Définition |
|---|---|---|
| `schema_version` | `Literal[1]` | `schema_version: Literal[1] = 1` |
| `product_id` | `int \| None` | `product_id: int \| None = None` |
| `reference` | `str \| None` | `reference: str \| None = None` |
| `name` | `str` | `name: str = ''` |
| `revision` | `int` | `revision: int = 0` |
| `terms_version` | `int` | `terms_version: int = 0` |
| `origin_product_id` | `int \| None` | `origin_product_id: int \| None = None` |
| `data_origin` | `Literal['native', 'demo', 'uat', 'imported']` | `data_origin: Literal['native', 'demo', 'uat', 'imported'] = 'native'` |
| `listed` | `bool` | `listed: bool = True` |
| `archived` | `bool` | `archived: bool = False` |
| `terms` | `ProductTerms` | `terms: ProductTerms` |
| `intent` | `TradeIntent` | `intent: TradeIntent = Field(default_factory=TradeIntent)` |
| `commercial` | `CommercialContext` | `commercial: CommercialContext = Field(default_factory=CommercialContext)` |
| `indicatives` | `tuple[FrozenObject, ...]` | `indicatives: tuple[FrozenObject, ...] = ()` |
| `rfqs` | `tuple[FrozenObject, ...]` | `rfqs: tuple[FrozenObject, ...] = ()` |
| `execution` | `FrozenObject \| None` | `execution: FrozenObject \| None = None` |
| `lifecycle` | `FrozenObject \| None` | `lifecycle: FrozenObject \| None = None` |
| `documents` | `tuple[FrozenObject, ...]` | `documents: tuple[FrozenObject, ...] = ()` |
| `calculations` | `tuple[CalculationRef, ...]` | `calculations: tuple[CalculationRef, ...] = ()` |

Méthodes/validators : `terms_fingerprint:191`; `to_dict:194`

## StrictModel

Source : `backend/app/core/product_optimizer/contracts.py:24`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid', allow_inf_nan=False)`

## ReferenceChange

Source : `backend/app/core/reference_data.py:23`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=500)` |

Méthodes/validators : `meaningful_reason:28`

## RollFinancing

Source : `backend/app/core/roll_economics.py:13`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid', allow_inf_nan=False)`

| Champ | Type | Définition |
|---|---|---|
| `exit_basis` | `Literal['model', 'model_haircut', 'observed_bid']` | `exit_basis: Literal['model', 'model_haircut', 'observed_bid'] = 'model'` |
| `bid_pct` | `float \| None` | `bid_pct: float \| None = Field(default=None, ge=0)` |
| `bid_source` | `str` | `bid_source: str = Field(default='', max_length=300)` |
| `bid_observed_at` | `AwareDatetime \| None` | `bid_observed_at: AwareDatetime \| None = None` |
| `haircut_points` | `float` | `haircut_points: float = Field(default=0, ge=0)` |
| `exit_cost_points` | `float` | `exit_cost_points: float = Field(default=0, ge=0)` |
| `entry_cost_points` | `float` | `entry_cost_points: float = Field(default=0, ge=0)` |

Méthodes/validators : `explicit_basis:24`

## VolatilitySurfaceParams

Source : `backend/app/core/schemas.py:68`. Bases : `BaseModel`.

- `model_config = ConfigDict(allow_inf_nan=False, extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `version` | `int` | `version: int = Field(default=1, ge=1, le=1)` |
| `profile` | `str` | `profile: str = Field(default='equity', pattern='^(equity\|index\|custom)$')` |
| `mode` | `str` | `mode: str = Field(default='automatic', pattern='^(automatic\|manual)$')` |
| `rho` | `float` | `rho: float = Field(ge=-0.99, le=0.99)` |
| `eta` | `float` | `eta: float = Field(ge=0, le=3)` |
| `shape_scale` | `float` | `shape_scale: float = Field(default=0.04, gt=0, le=10)` |
| `max_expiry` | `float` | `max_expiry: float = Field(default=10, gt=0, le=MAX_MATURITY_YEARS)` |
| `atm_nodes` | `List[List[float]]` | `atm_nodes: List[List[float]] = Field(min_length=1, max_length=20)` |

Méthodes/validators : `validate_surface:80`

## UnderlyingParams

Source : `backend/app/core/schemas.py:86`. Bases : `BaseModel`.

- `model_config = ConfigDict(allow_inf_nan=False)`

| Champ | Type | Définition |
|---|---|---|
| `name` | `str` | `name: str = 'Underlying'` |
| `ticker` | `str` | `ticker: str = ''` |
| `ccy` | `str` | `ccy: str = 'EUR'` |
| `spot0` | `float \| None` | `spot0: float \| None = Field(default=None, gt=0, allow_inf_nan=False)` |
| `sigma` | `float` | `sigma: float = Field(default=0.2, ge=0.0, le=10.0)` |
| `q` | `float` | `q: float = Field(default=0.02, ge=0.0, le=2.0)` |
| `dividend_curve` | `List[List[float]]` | `dividend_curve: List[List[float]] = Field(default_factory=list)` |
| `dividend_decay` | `float` | `dividend_decay: float = Field(default=0.0, ge=0.0, le=1.0)` |
| `sigma_fx` | `float` | `sigma_fx: float = Field(default=0.0, ge=0.0, le=10.0)` |
| `rho_sfx` | `float` | `rho_sfx: float = Field(default=0.0, ge=-1.0, le=1.0)` |
| `ccyh` | `float` | `ccyh: float = 0.0` |
| `v0` | `float` | `v0: float = 0.04` |
| `kappa` | `float` | `kappa: float = 2.0` |
| `theta` | `float` | `theta: float = 0.04` |
| `xi` | `float` | `xi: float = 0.35` |
| `rho_h` | `float` | `rho_h: float = Field(default=-0.7, ge=-1.0, le=1.0)` |
| `rho_rS` | `float` | `rho_rS: float = Field(default=0.0, ge=-1.0, le=1.0)` |
| `alpha` | `float` | `alpha: float = 0.2` |
| `beta` | `float` | `beta: float = Field(default=0.5, ge=0.0, le=1.0)` |
| `rho` | `float` | `rho: float = Field(default=-0.3, ge=-1.0, le=1.0)` |
| `nu` | `float` | `nu: float = 0.4` |
| `skew` | `float` | `skew: float = 0.0` |
| `curvature` | `float` | `curvature: float = 0.0` |
| `vol_surface` | `VolatilitySurfaceParams \| None` | `vol_surface: VolatilitySurfaceParams \| None = None` |
| `asset_class` | `str` | `asset_class: str = Field(default='unknown', pattern='^(equity\|index\|unknown)$')` |
| `smile_parameter_mode` | `str` | `smile_parameter_mode: str = Field(default='automatic', pattern='^(automatic\|manual)$')` |
| `calibration_evidence` | `dict \| None` | `calibration_evidence: dict \| None = Field(default=None, exclude_if=lambda value: value is None)` |
| `market_data` | `dict \| None` | `market_data: dict \| None = Field(default=None, exclude_if=lambda value: value is None)` |

Méthodes/validators : `finite_calibration_evidence:129`; `validate_market_provenance:139`; `validate_dividend_curve:177`

## PricingRequest

Source : `backend/app/core/schemas.py:202`. Bases : `BaseModel`.

- `model_config = ConfigDict(allow_inf_nan=False)`

| Champ | Type | Définition |
|---|---|---|
| `script` | `str` | `script: str = Field(max_length=MAX_SCRIPT_CHARS)` |
| `underlyings` | `List[UnderlyingParams]` | `underlyings: List[UnderlyingParams] = Field(min_length=1, max_length=MAX_UNDERLYINGS)` |
| `corr_matrix` | `List[List[float]]` | `corr_matrix: List[List[float]]` |
| `r` | `float` | `r: float = Field(default=0.03, ge=MIN_RATE, le=MAX_RATE)` |
| `T` | `float` | `T: float = Field(default=3.0, gt=0.0, le=MAX_MATURITY_YEARS)` |
| `N` | `int` | `N: int = Field(default=20000, ge=1000, le=200000)` |
| `seed` | `int` | `seed: int = 42` |
| `model` | `str` | `model: str = Field(default='constant', pattern=f"^({'\|'.join(MODELS)})$")` |
| `antithetic` | `bool` | `antithetic: bool = True` |
| `user_params` | `Dict[str, Any]` | `user_params: Dict[str, Any] = {}` |
| `compute_greeks` | `bool` | `compute_greeks: bool = False` |
| `selected_greeks` | `List[str]` | `selected_greeks: List[str] = ['delta', 'gamma', 'vega', 'theta', 'rho']` |
| `yield_curve` | `List[List[float]]` | `yield_curve: List[List[float]] = []` |
| `funding_curve` | `List[List[float]]` | `funding_curve: List[List[float]] = []` |
| `funding_spread` | `float` | `funding_spread: float = Field(default=0.0, ge=-0.05, le=0.5)` |
| `sigma_r` | `float` | `sigma_r: float = Field(default=0.0, ge=0.0, le=0.1)` |
| `a_r` | `float` | `a_r: float = Field(default=0.0, ge=0.0, le=2.0)` |
| `barrier_monitoring` | `str` | `barrier_monitoring: str = Field(default='weekly', pattern='^(weekly\|continuous)$')` |
| `constats` | `Dict[str, Any]` | `constats: Dict[str, Any] = {}` |
| `frozen_schedule` | `Optional[Dict[str, Any]]` | `frozen_schedule: Optional[Dict[str, Any]] = None` |
| `anchor` | `Optional[date]` | `anchor: Optional[date] = None` |
| `settlement_ccy` | `Optional[str]` | `settlement_ccy: Optional[str] = None` |
| `payment_date` | `Optional[date]` | `payment_date: Optional[date] = None` |
| `maturity_date` | `Optional[date]` | `maturity_date: Optional[date] = None` |
| `strike_date` | `Optional[date]` | `strike_date: Optional[date] = None` |
| `value_date` | `Optional[date]` | `value_date: Optional[date] = None` |

Méthodes/validators : `fixed_monte_carlo_seed:238`; `validate_yield_curve:268`; `validate_funding_curve:273`; `validate_correlation:277`

## PricingResponse

Source : `backend/app/core/schemas.py:282`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `price` | `float` | `price: float` |
| `ic95` | `List[float]` | `ic95: List[float]` |
| `median` | `float` | `median: float` |
| `var5` | `float` | `var5: float` |
| `prob_gt100` | `float` | `prob_gt100: float` |
| `payoffs` | `List[float]` | `payoffs: List[float]` |
| `flux_table` | `Dict[str, Any]` | `flux_table: Dict[str, Any]` |
| `greeks` | `Dict[str, Any]` | `greeks: Dict[str, Any]` |
| `elapsed_ms` | `float` | `elapsed_ms: float` |
| `n_paths` | `int` | `n_paths: int` |
| `n_eff` | `int` | `n_eff: int` |
| `status` | `str` | `status: str = 'ok'` |
| `errors` | `Optional[str]` | `errors: Optional[str] = None` |
| `t_max_effective` | `float` | `t_max_effective: float = 0.0` |
| `fugit` | `Optional[float]` | `fugit: Optional[float] = None` |
| `constatation_windows` | `Optional[List[Dict[str, Any]]]` | `constatation_windows: Optional[List[Dict[str, Any]]] = None` |
| `schedule` | `Optional[Dict[str, Any]]` | `schedule: Optional[Dict[str, Any]] = None` |
| `calculation_budget` | `Optional[Dict[str, Any]]` | `calculation_budget: Optional[Dict[str, Any]] = None` |
| `pricing_receipt` | `Optional[Dict[str, Any]]` | `pricing_receipt: Optional[Dict[str, Any]] = None` |
| `corr_repair` | `Optional[Dict[str, Any]]` | `corr_repair: Optional[Dict[str, Any]] = None` |
| `barrier_monitoring` | `str` | `barrier_monitoring: str = 'weekly'` |
| `barrier_monitoring_note` | `Optional[str]` | `barrier_monitoring_note: Optional[str] = None` |
| `barrier_monitoring_details` | `Optional[Dict[str, Any]]` | `barrier_monitoring_details: Optional[Dict[str, Any]] = None` |

## ParseRequest

Source : `backend/app/core/schemas.py:322`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `script` | `str` | `script: str` |

## ParseResponse

Source : `backend/app/core/schemas.py:326`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `ok` | `bool` | `ok: bool` |
| `underlying` | `str \| None` | `underlying: str \| None = None` |
| `initial_fixing` | `str \| None` | `initial_fixing: str \| None = None` |
| `params` | `List[Dict[str, Any]]` | `params: List[Dict[str, Any]]` |
| `constats` | `List[Dict[str, Any]]` | `constats: List[Dict[str, Any]] = []` |
| `events_count` | `int` | `events_count: int` |
| `has_stop` | `bool` | `has_stop: bool = False` |
| `has_maturity_event` | `bool` | `has_maturity_event: bool = False` |
| `at_dates` | `List[float]` | `at_dates: List[float] = []` |
| `monitors` | `List[Dict[str, Any]]` | `monitors: List[Dict[str, Any]] = []` |
| `errors` | `Optional[str]` | `errors: Optional[str] = None` |

## VariantOverrides

Source : `backend/app/core/schemas.py:346`. Bases : `BaseModel`.

Les termes d'un avenant — ce qui remplace le parent à partir d'aujourd'hui.  Déclaré ici plutôt que dans l'API pour que le prix ET les analytiques puissent le porter : une variante que seul le prix connaîtrait ferait décrire au profil de payoff et aux probabilités le produit d'ORIGINE, sous un prix d'avenant. C'est précisément l'écart qu'on a passé la session à fermer partout ailleurs.

| Champ | Type | Définition |
|---|---|---|
| `script` | `Optional[str]` | `script: Optional[str] = None` |
| `user_params` | `Optional[Dict[str, Any]]` | `user_params: Optional[Dict[str, Any]] = None` |
| `constats` | `Optional[Dict[str, Any]]` | `constats: Optional[Dict[str, Any]] = None` |
| `mode` | `str` | `mode: str = 'avenant'` |

## AnalysisBase

Source : `backend/app/core/schemas.py:360`. Bases : `BaseModel`.

Shared fields for profile / paths / proba / backtest / mtf requests.

- `model_config = ConfigDict(allow_inf_nan=False)`

| Champ | Type | Définition |
|---|---|---|
| `script` | `str` | `script: str = Field(max_length=MAX_SCRIPT_CHARS)` |
| `underlyings` | `List[UnderlyingParams]` | `underlyings: List[UnderlyingParams] = Field(min_length=1, max_length=MAX_UNDERLYINGS)` |
| `corr_matrix` | `List[List[float]]` | `corr_matrix: List[List[float]]` |
| `r` | `float` | `r: float = Field(default=0.03, ge=MIN_RATE, le=MAX_RATE)` |
| `T` | `float` | `T: float = Field(default=3.0, gt=0.0, le=MAX_MATURITY_YEARS)` |
| `seed` | `int` | `seed: int = 42` |
| `antithetic` | `bool` | `antithetic: bool = True` |
| `model` | `str` | `model: str = Field(default='constant', pattern=f"^({'\|'.join(MODELS)})$")` |
| `user_params` | `Dict[str, Any]` | `user_params: Dict[str, Any] = {}` |
| `yield_curve` | `List[List[float]]` | `yield_curve: List[List[float]] = []` |
| `sigma_r` | `float` | `sigma_r: float = Field(default=0.0, ge=0.0, le=0.1)` |
| `a_r` | `float` | `a_r: float = Field(default=0.0, ge=0.0, le=2.0)` |
| `barrier_monitoring` | `str` | `barrier_monitoring: str = Field(default='weekly', pattern='^(weekly\|continuous)$')` |
| `constats` | `Dict[str, Any]` | `constats: Dict[str, Any] = {}` |
| `frozen_schedule` | `Optional[Dict[str, Any]]` | `frozen_schedule: Optional[Dict[str, Any]] = None` |
| `anchor` | `Optional[date]` | `anchor: Optional[date] = None` |
| `settlement_ccy` | `Optional[str]` | `settlement_ccy: Optional[str] = None` |
| `variant` | `Optional[VariantOverrides]` | `variant: Optional[VariantOverrides] = None` |
| `strike_date` | `Optional[date]` | `strike_date: Optional[date] = None` |
| `value_date` | `Optional[date]` | `value_date: Optional[date] = None` |
| `payment_date` | `Optional[date]` | `payment_date: Optional[date] = None` |
| `valuation_date` | `Optional[date]` | `valuation_date: Optional[date] = None` |
| `maturity_date` | `Optional[date]` | `maturity_date: Optional[date] = None` |
| `funding_curve` | `List[List[float]]` | `funding_curve: List[List[float]] = []` |
| `funding_spread` | `float` | `funding_spread: float = Field(default=0.0, ge=-0.05, le=0.5)` |

Méthodes/validators : `fixed_monte_carlo_seed:374`; `validate_yield_curve:415`; `validate_funding_curve:420`; `validate_correlation:424`

## BacktestCompareRequest

Source : `backend/app/core/schemas.py:450`. Bases : `BaseModel`.

Underlying comparator — backtest the same script against a pool of candidate underlyings, one at a time, then (if basket_size > 1) against combinations drawn from the best `shortlist_n` single performers only — testing every C(N, basket_size) combination is combinatorially infeasible for any non-trivial candidate pool.

- `model_config = ConfigDict(allow_inf_nan=False)`

| Champ | Type | Définition |
|---|---|---|
| `script` | `str` | `script: str = Field(max_length=MAX_SCRIPT_CHARS)` |
| `candidates` | `List[UnderlyingParams]` | `candidates: List[UnderlyingParams] = Field(min_length=1, max_length=MAX_UNDERLYINGS)` |
| `r` | `float` | `r: float = Field(default=0.03, ge=MIN_RATE, le=MAX_RATE)` |
| `T` | `float` | `T: float = Field(default=3.0, gt=0.0, le=MAX_MATURITY_YEARS)` |
| `model` | `str` | `model: str = Field(default='constant', pattern=f"^({'\|'.join(MODELS)})$")` |
| `user_params` | `Dict[str, Any]` | `user_params: Dict[str, Any] = {}` |
| `constats` | `Dict[str, Any]` | `constats: Dict[str, Any] = {}` |
| `anchor` | `Optional[date]` | `anchor: Optional[date] = None` |
| `basket_size` | `int` | `basket_size: int = Field(default=1, ge=1, le=5)` |
| `shortlist_n` | `int` | `shortlist_n: int = Field(default=8, ge=2, le=20)` |
| `start_date` | `str` | `start_date: str = '2010-01-01'` |
| `end_date` | `Optional[str]` | `end_date: Optional[str] = None` |
| `freq` | `int` | `freq: int = Field(default=21, ge=1, le=252)` |
| `invest_pct` | `float` | `invest_pct: float = Field(default=100.0, gt=0, le=200)` |
| `rf_rate` | `float` | `rf_rate: float = 2.0` |

## ReinvestCandidate

Source : `backend/app/core/schemas.py:537`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `ticker` | `str` | `ticker: str` |
| `name` | `str` | `name: str = ''` |

## ReinvestMetricFilter

Source : `backend/app/core/schemas.py:542`. Bases : `BaseModel`.

One risk guardrail on the candidate scan — a hard cutoff, not a weight: candidates violating it are dropped before the coupon ranking, never just penalized. metric is one of ki/autocall/capital_loss/full_coupon (the *_pct fields returned by /pricing/proba). direction "max" means the metric must not exceed threshold; "min" means it must not fall below it.

| Champ | Type | Définition |
|---|---|---|
| `metric` | `str` | `metric: str = Field(pattern='^(ki\|autocall\|capital_loss\|full_coupon)$')` |
| `threshold` | `float` | `threshold: float = Field(ge=0, le=100)` |
| `direction` | `str` | `direction: str = Field(pattern='^(max\|min)$')` |

## ReinvestScanRequest

Source : `backend/app/core/schemas.py:553`. Bases : `BaseModel`.

Flow B — scan a pool of candidate underlyings for the deal's own script: solve each candidate's coupon (or whichever PARAM) to par, price its risk profile, keep only those passing every filter, rank the rest by coupon. target_price/lo/hi are in the PARAM's stored units, same convention as SolverRequest (the frontend converts display % to stored units before calling, exactly like the existing Solver panel does).

| Champ | Type | Définition |
|---|---|---|
| `candidates` | `List[ReinvestCandidate]` | `candidates: List[ReinvestCandidate]` |
| `param_name` | `str` | `param_name: str` |
| `target_price` | `float` | `target_price: float` |
| `lo` | `float` | `lo: float` |
| `hi` | `float` | `hi: float` |
| `filters` | `List[ReinvestMetricFilter]` | `filters: List[ReinvestMetricFilter] = []` |
| `N` | `int` | `N: int = Field(default=6000, ge=1000, le=20000)` |
| `model` | `Optional[str]` | `model: Optional[str] = Field(default=None, pattern=f"^({'\|'.join(MODELS)})$")` |
| `vol_period` | `str` | `vol_period: str = '1y'` |
| `T` | `Optional[float]` | `T: Optional[float] = Field(default=None, gt=0.0, le=MAX_MATURITY_YEARS)` |
| `param_overrides` | `Dict[str, Any]` | `param_overrides: Dict[str, Any] = {}` |

## ReinvestProposalRequest

Source : `backend/app/core/schemas.py:577`. Bases : `BaseModel`.

A single scanned candidate turned into a proposal: same conventions as ReinvestScanRequest (one candidate instead of a pool), plus a backtest window. Re-derives price/proba server-side rather than trusting client-echoed scan-result figures for a document.

| Champ | Type | Définition |
|---|---|---|
| `ticker` | `str` | `ticker: str` |
| `name` | `str` | `name: str = ''` |
| `param_name` | `str` | `param_name: str` |
| `target_price` | `float` | `target_price: float` |
| `lo` | `float` | `lo: float` |
| `hi` | `float` | `hi: float` |
| `T` | `Optional[float]` | `T: Optional[float] = Field(default=None, gt=0.0, le=MAX_MATURITY_YEARS)` |
| `param_overrides` | `Dict[str, Any]` | `param_overrides: Dict[str, Any] = {}` |
| `N` | `int` | `N: int = Field(default=8000, ge=1000, le=20000)` |
| `model` | `Optional[str]` | `model: Optional[str] = Field(default=None, pattern=f"^({'\|'.join(MODELS)})$")` |
| `vol_period` | `str` | `vol_period: str = '1y'` |
| `backtest_start` | `str` | `backtest_start: str = '2015-01-01'` |
| `backtest_freq` | `int` | `backtest_freq: int = Field(default=21, ge=1, le=252)` |
| `backtest_invest_pct` | `float` | `backtest_invest_pct: float = Field(default=100.0, gt=0, le=200)` |
| `study_preview` | `Optional[dict]` | `study_preview: Optional[dict] = None` |
| `parent_archive_id` | `Optional[str]` | `parent_archive_id: Optional[str] = Field(default=None, max_length=40)` |

## CalendarPolicyRequest

Source : `backend/app/core/schemas.py:626`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `observation_calendars` | `Optional[List[str]]` | `observation_calendars: Optional[List[str]] = None` |
| `observation_join` | `Optional[str]` | `observation_join: Optional[str] = None` |
| `settlement_calendars` | `Optional[List[str]]` | `settlement_calendars: Optional[List[str]] = None` |
| `settlement_join` | `Optional[str]` | `settlement_join: Optional[str] = None` |

## CCRRecord

Source : `backend/app/db/ccr_models.py:7`. Bases : `SQLModel`.

| Champ | Type | Définition |
|---|---|---|
| `id` | `int \| None` | `id: int \| None = Field(default=None, primary_key=True)` |
| `entity_id` | `int` | `entity_id: int = Field(foreign_key='entities.id', index=True)` |
| `counterparty_id` | `int` | `counterparty_id: int = Field(foreign_key='counterparties.id', index=True)` |
| `version` | `int` | `version: int = 1` |
| `payload_json` | `str` | `payload_json: str = Field(default='{}', sa_type=Text)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_by` | `int` | `updated_by: int = Field(foreign_key='users.id')` |

## CCRCreditProfile

Source : `backend/app/db/ccr_models.py:17`. Bases : `CCRRecord`.

- `__tablename__ = 'ccr_credit_profiles'`
- `__table_args__ = (UniqueConstraint('entity_id', 'counterparty_id'),)`

Options de classe : `table=True`

## CCRMasterAgreement

Source : `backend/app/db/ccr_models.py:22`. Bases : `CCRRecord`.

- `__tablename__ = 'ccr_master_agreements'`

Options de classe : `table=True`

## CCRCSAAgreement

Source : `backend/app/db/ccr_models.py:26`. Bases : `CCRRecord`.

- `__tablename__ = 'ccr_csa_agreements'`

Options de classe : `table=True`

## CCRNettingSet

Source : `backend/app/db/ccr_models.py:30`. Bases : `CCRRecord`.

- `__tablename__ = 'ccr_netting_sets'`

Options de classe : `table=True`

## CCRCreditLimit

Source : `backend/app/db/ccr_models.py:34`. Bases : `CCRRecord`.

- `__tablename__ = 'ccr_credit_limits'`

Options de classe : `table=True`

## CCRCollateralPosition

Source : `backend/app/db/ccr_models.py:38`. Bases : `CCRRecord`.

- `__tablename__ = 'ccr_collateral_positions'`

Options de classe : `table=True`

## CCRCreditOverride

Source : `backend/app/db/ccr_models.py:42`. Bases : `CCRRecord`.

- `__tablename__ = 'ccr_credit_overrides'`

Options de classe : `table=True`

## CCRExposureCalculation

Source : `backend/app/db/ccr_models.py:46`. Bases : `SQLModel`.

- `__tablename__ = 'ccr_exposure_calculations'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `int \| None` | `id: int \| None = Field(default=None, primary_key=True)` |
| `entity_id` | `int` | `entity_id: int = Field(foreign_key='entities.id', index=True)` |
| `counterparty_id` | `int \| None` | `counterparty_id: int \| None = Field(default=None, foreign_key='counterparties.id', index=True)` |
| `created_by` | `int` | `created_by: int = Field(foreign_key='users.id')` |
| `calculation_timestamp` | `datetime` | `calculation_timestamp: datetime = Field(default_factory=datetime.utcnow)` |
| `as_of_date` | `str` | `as_of_date: str` |
| `methodology` | `str` | `methodology: str` |
| `input_hash` | `str` | `input_hash: str` |
| `inputs_json` | `str` | `inputs_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `results_json` | `str` | `results_json: str = Field(sa_column=Column(Text, nullable=False))` |

## ProductRecord

Source : `backend/app/db/models.py:16`. Bases : `SQLModel`.

Identity and optimistic revision pointer; never holds market data.

- `__tablename__ = 'products'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `reference` | `str` | `reference: str = Field(unique=True, index=True)` |
| `name` | `str` | `name: str` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id')` |
| `uat_batch_id` | `Optional[int]` | `uat_batch_id: Optional[int] = Field(default=None, foreign_key='uat_generation_batches.id', index=True)` |
| `origin_product_id` | `Optional[int]` | `origin_product_id: Optional[int] = Field(default=None, foreign_key='products.id')` |
| `data_origin` | `str` | `data_origin: str = Field(default='native')` |
| `revision` | `int` | `revision: int = Field(default=0)` |
| `terms_version` | `int` | `terms_version: int = Field(default=0)` |
| `listed` | `bool` | `listed: bool = Field(default=True, index=True)` |
| `archived` | `bool` | `archived: bool = Field(default=False)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## ProductTermsVersion

Source : `backend/app/db/models.py:38`. Bases : `SQLModel`.

- `__tablename__ = 'product_terms_versions'`
- `__table_args__ = (UniqueConstraint('product_id', 'version'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `product_id` | `int` | `product_id: int = Field(foreign_key='products.id', index=True)` |
| `version` | `int` | `version: int` |
| `parent_version` | `Optional[int]` | `parent_version: Optional[int] = None` |
| `fingerprint` | `str` | `fingerprint: str = Field(index=True)` |
| `terms_json` | `str` | `terms_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `reason` | `str` | `reason: str` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## ProductRevision

Source : `backend/app/db/models.py:51`. Bases : `SQLModel`.

- `__tablename__ = 'product_revisions'`
- `__table_args__ = (UniqueConstraint('product_id', 'revision'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `product_id` | `int` | `product_id: int = Field(foreign_key='products.id', index=True)` |
| `revision` | `int` | `revision: int` |
| `terms_version` | `int` | `terms_version: int` |
| `snapshot_json` | `str` | `snapshot_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `actor_user_id` | `Optional[int]` | `actor_user_id: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `action` | `str` | `action: str` |
| `reason` | `str` | `reason: str = ''` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## ProductCalculationRun

Source : `backend/app/db/models.py:65`. Bases : `SQLModel`.

- `__tablename__ = 'product_calculation_runs'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `product_id` | `int` | `product_id: int = Field(foreign_key='products.id', index=True)` |
| `terms_version` | `int` | `terms_version: int` |
| `input_revision` | `int` | `input_revision: int` |
| `kind` | `str` | `kind: str = 'PRICING'` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `calculated_at` | `datetime` | `calculated_at: datetime` |
| `valuation_date` | `Optional[str]` | `valuation_date: Optional[str] = None` |
| `source` | `str` | `source: str = 'SERVER'` |
| `input_hash` | `str` | `input_hash: str` |
| `input_json` | `str` | `input_json: str = Field(default='{}', sa_column=Column(Text))` |
| `result_json` | `str` | `result_json: str = Field(default='{}', sa_column=Column(Text))` |
| `valuation_run_id` | `Optional[int]` | `valuation_run_id: Optional[int] = Field(default=None, foreign_key='valuation_runs.id')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## ProductCommand

Source : `backend/app/db/models.py:83`. Bases : `SQLModel`.

- `__tablename__ = 'product_commands'`
- `__table_args__ = (UniqueConstraint('user_id', 'command_key'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `command_key` | `str` | `command_key: str` |
| `input_hash` | `str` | `input_hash: str` |
| `product_id` | `int` | `product_id: int = Field(foreign_key='products.id', index=True)` |
| `result_revision` | `int` | `result_revision: int` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## BookingCommand

Source : `backend/app/db/models.py:95`. Bases : `SQLModel`.

Successful booking intent, committed atomically with its local position.

- `__tablename__ = 'booking_commands'`
- `__table_args__ = (UniqueConstraint('user_id', 'command_key'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id')` |
| `command_key` | `str` | `command_key: str` |
| `input_hash` | `str` | `input_hash: str` |
| `deal_id` | `Optional[int]` | `deal_id: Optional[int] = Field(default=None, foreign_key='deals.id', index=True)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## ArchivedDocument

Source : `backend/app/db/models.py:109`. Bases : `SQLModel`.

Server-owned immutable proposal or explain, including the rendered PDF.

- `__tablename__ = 'archived_documents'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `str` | `id: str = Field(primary_key=True)` |
| `kind` | `str` | `kind: str = Field(index=True)` |
| `deal_id` | `int` | `deal_id: int = Field(foreign_key='deals.id', index=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `parent_id` | `Optional[str]` | `parent_id: Optional[str] = Field(default=None, foreign_key='archived_documents.id')` |
| `contract_version` | `int` | `contract_version: int` |
| `request_json` | `str` | `request_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `data_json` | `str` | `data_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `content_hash` | `str` | `content_hash: str` |
| `pdf_base64` | `str` | `pdf_base64: str = Field(sa_column=Column(Text, nullable=False))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## VariantStudyArchive

Source : `backend/app/db/models.py:125`. Bases : `SQLModel`.

A frozen exploratory comparison; it is never an execution or a Product.

- `__tablename__ = 'variant_study_archives'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `str` | `id: str = Field(primary_key=True)` |
| `script_id` | `int` | `script_id: int = Field(foreign_key='scripts.id', index=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `parent_id` | `Optional[str]` | `parent_id: Optional[str] = Field(default=None, foreign_key='variant_study_archives.id')` |
| `evidence_json` | `str` | `evidence_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## OptimizerResearch

Source : `backend/app/db/models.py:136`. Bases : `SQLModel`.

A dated exploration and its server-owned calculation; never a booked product.

- `__tablename__ = 'optimizer_researches'`
- `__table_args__ = (UniqueConstraint('user_id', 'command_key'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `str` | `id: str = Field(primary_key=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `parent_id` | `Optional[str]` | `parent_id: Optional[str] = Field(default=None, foreign_key='optimizer_researches.id', index=True)` |
| `command_key` | `str` | `command_key: str` |
| `title` | `str` | `title: str` |
| `intention` | `str` | `intention: str = ''` |
| `summary` | `str` | `summary: str` |
| `product_family` | `str` | `product_family: str = Field(index=True)` |
| `pricing_date` | `str` | `pricing_date: str = Field(index=True)` |
| `status` | `str` | `status: str = Field(default='RUNNING', index=True)` |
| `archived` | `bool` | `archived: bool = Field(default=False, index=True)` |
| `request_hash` | `str` | `request_hash: str` |
| `request_json` | `str` | `request_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `context_json` | `str` | `context_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `result_json` | `str` | `result_json: str = Field(default='{}', sa_column=Column(Text))` |
| `progress_json` | `str` | `progress_json: str = Field(default='{}', sa_column=Column(Text))` |
| `error` | `str` | `error: str = ''` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `finished_at` | `Optional[datetime]` | `finished_at: Optional[datetime] = None` |

## Entity

Source : `backend/app/db/models.py:161`. Bases : `SQLModel`.

- `__tablename__ = 'entities'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `name` | `str` | `name: str = Field(index=True)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## User

Source : `backend/app/db/models.py:168`. Bases : `SQLModel`.

- `__tablename__ = 'users'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `username` | `str` | `username: str = Field(unique=True, index=True)` |
| `email` | `str` | `email: str = Field(unique=True, index=True)` |
| `password_hash` | `str` | `password_hash: str` |
| `role` | `str` | `role: str = Field(default='user')` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id')` |
| `is_active` | `bool` | `is_active: bool = Field(default=True)` |
| `auth_version` | `int` | `auth_version: int = Field(default=0)` |
| `password_change_required` | `bool` | `password_change_required: bool = Field(default=False)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## RevokedSession

Source : `backend/app/db/models.py:182`. Bases : `SQLModel`.

- `__tablename__ = 'revoked_sessions'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `token_digest` | `str` | `token_digest: str = Field(primary_key=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `expires_at` | `datetime` | `expires_at: datetime` |

## RfqDesk

Source : `backend/app/db/models.py:189`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_desks'`
- `__table_args__ = (UniqueConstraint('entity_id', 'name'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `entity_id` | `int` | `entity_id: int = Field(foreign_key='entities.id', index=True)` |
| `name` | `str` | `name: str` |
| `active` | `bool` | `active: bool = Field(default=True)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqDeskMembership

Source : `backend/app/db/models.py:199`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_desk_memberships'`
- `__table_args__ = (UniqueConstraint('desk_id', 'user_id'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `desk_id` | `int` | `desk_id: int = Field(foreign_key='rfq_desks.id', index=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `rights_json` | `str` | `rights_json: str = Field(default='[]', sa_column=Column(Text))` |
| `active` | `bool` | `active: bool = Field(default=True)` |
| `expires_at` | `Optional[datetime]` | `expires_at: Optional[datetime] = None` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqOwnership

Source : `backend/app/db/models.py:212`. Bases : `SQLModel`.

New RFQ access scope; rows absent for historical test dossiers.

- `__tablename__ = 'rfq_ownerships'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `rfq_id` | `int` | `rfq_id: int = Field(primary_key=True, foreign_key='rfq_requests.id')` |
| `entity_id` | `int` | `entity_id: int = Field(foreign_key='entities.id', index=True)` |
| `pilot_desk_id` | `int` | `pilot_desk_id: int = Field(foreign_key='rfq_desks.id', index=True)` |
| `responsible_user_id` | `Optional[int]` | `responsible_user_id: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqDeskShare

Source : `backend/app/db/models.py:222`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_desk_shares'`
- `__table_args__ = (UniqueConstraint('rfq_id', 'desk_id'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `rfq_id` | `int` | `rfq_id: int = Field(foreign_key='rfq_requests.id', index=True)` |
| `desk_id` | `int` | `desk_id: int = Field(foreign_key='rfq_desks.id', index=True)` |
| `rights_json` | `str` | `rights_json: str = Field(default='[]', sa_column=Column(Text))` |
| `active` | `bool` | `active: bool = Field(default=True)` |
| `expires_at` | `Optional[datetime]` | `expires_at: Optional[datetime] = None` |
| `reason` | `str` | `reason: str = Field(default='')` |
| `actor_user_id` | `int` | `actor_user_id: int = Field(foreign_key='users.id')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqRelationship

Source : `backend/app/db/models.py:237`. Bases : `SQLModel`.

Directional bilateral permission to request prices from a partner desk.

- `__tablename__ = 'rfq_relationships'`
- `__table_args__ = (UniqueConstraint('requester_entity_id', 'reference'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `requester_entity_id` | `int` | `requester_entity_id: int = Field(foreign_key='entities.id', index=True)` |
| `partner_entity_id` | `int` | `partner_entity_id: int = Field(foreign_key='entities.id', index=True)` |
| `receiver_desk_id` | `int` | `receiver_desk_id: int = Field(foreign_key='rfq_desks.id')` |
| `reference` | `str` | `reference: str` |
| `version` | `int` | `version: int = Field(default=1)` |
| `terms_json` | `str` | `terms_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `created_by` | `int` | `created_by: int = Field(foreign_key='users.id')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqRelationshipSide

Source : `backend/app/db/models.py:253`. Bases : `SQLModel`.

Local legal/booking mapping and explicit recognition by one organization.

- `__tablename__ = 'rfq_relationship_sides'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `relationship_id` | `int` | `relationship_id: int = Field(primary_key=True, foreign_key='rfq_relationships.id')` |
| `entity_id` | `int` | `entity_id: int = Field(primary_key=True, foreign_key='entities.id')` |
| `counterparty_id` | `Optional[int]` | `counterparty_id: Optional[int] = Field(default=None, foreign_key='counterparties.id')` |
| `trading_relationship_id` | `Optional[int]` | `trading_relationship_id: Optional[int] = Field(default=None, foreign_key='trading_relationships.id')` |
| `contacts_json` | `str` | `contacts_json: str = Field(default='[]', sa_column=Column(Text))` |
| `recognized_version` | `Optional[int]` | `recognized_version: Optional[int] = None` |
| `suspended` | `bool` | `suspended: bool = Field(default=False)` |
| `updated_by` | `int` | `updated_by: int = Field(foreign_key='users.id')` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqExchangeRound

Source : `backend/app/db/models.py:267`. Bases : `SQLModel`.

Immutable common request; a revised consultation uses a linked RFQ.

- `__tablename__ = 'rfq_exchange_rounds'`
- `__table_args__ = (UniqueConstraint('exchange_reference', 'number'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `rfq_id` | `int` | `rfq_id: int = Field(foreign_key='rfq_requests.id', unique=True)` |
| `exchange_reference` | `str` | `exchange_reference: str = Field(index=True)` |
| `number` | `int` | `number: int` |
| `previous_round_id` | `Optional[int]` | `previous_round_id: Optional[int] = Field(default=None, foreign_key='rfq_exchange_rounds.id')` |
| `product_id` | `int` | `product_id: int = Field(foreign_key='products.id')` |
| `terms_version` | `int` | `terms_version: int` |
| `terms_fingerprint` | `str` | `terms_fingerprint: str` |
| `request_json` | `str` | `request_json: str = Field(sa_column=Column(Text))` |
| `state` | `str` | `state: str = Field(default='OPEN')` |
| `frozen_by` | `int` | `frozen_by: int = Field(foreign_key='users.id')` |
| `frozen_at` | `datetime` | `frozen_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqRoundLink

Source : `backend/app/db/models.py:285`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_round_links'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `rfq_id` | `int` | `rfq_id: int = Field(primary_key=True, foreign_key='rfq_requests.id')` |
| `previous_round_id` | `int` | `previous_round_id: int = Field(foreign_key='rfq_exchange_rounds.id', unique=True)` |

## RfqSolicitation

Source : `backend/app/db/models.py:291`. Bases : `SQLModel`.

A persisted individually addressed request is the bank's inbox item.

- `__tablename__ = 'rfq_solicitations'`
- `__table_args__ = (UniqueConstraint('round_id', 'relationship_id'), UniqueConstraint('round_id', 'recipient_entity_id'))`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `round_id` | `int` | `round_id: int = Field(foreign_key='rfq_exchange_rounds.id', index=True)` |
| `relationship_id` | `int` | `relationship_id: int = Field(foreign_key='rfq_relationships.id')` |
| `recipient_entity_id` | `int` | `recipient_entity_id: int = Field(foreign_key='entities.id', index=True)` |
| `recipient_desk_id` | `int` | `recipient_desk_id: int = Field(foreign_key='rfq_desks.id', index=True)` |
| `message_id` | `str` | `message_id: str = Field(unique=True)` |
| `request_json` | `str` | `request_json: str = Field(sa_column=Column(Text))` |
| `sent_by` | `int` | `sent_by: int = Field(foreign_key='users.id')` |
| `sent_at` | `datetime` | `sent_at: datetime = Field(default_factory=datetime.utcnow)` |
| `delivered_at` | `datetime` | `delivered_at: datetime = Field(default_factory=datetime.utcnow)` |
| `read_at` | `Optional[datetime]` | `read_at: Optional[datetime] = None` |
| `read_by` | `Optional[int]` | `read_by: Optional[int] = Field(default=None, foreign_key='users.id')` |

## RfqBankCase

Source : `backend/app/db/models.py:309`. Bases : `SQLModel`.

Desk-owned private work on one received immutable request.

- `__tablename__ = 'rfq_bank_cases'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `solicitation_id` | `int` | `solicitation_id: int = Field(primary_key=True, foreign_key='rfq_solicitations.id')` |
| `product_id` | `int` | `product_id: int = Field(foreign_key='products.id', unique=True)` |
| `responsible_user_id` | `int` | `responsible_user_id: int = Field(foreign_key='users.id')` |
| `revision` | `int` | `revision: int = Field(default=1)` |
| `state` | `str` | `state: str = Field(default='IN_PROGRESS')` |
| `private_note` | `str` | `private_note: str = Field(default='', sa_column=Column(Text))` |
| `shared_decline_note` | `str` | `shared_decline_note: str = Field(default='', sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqBankPublicationPolicy

Source : `backend/app/db/models.py:323`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_bank_publication_policies'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `desk_id` | `int` | `desk_id: int = Field(primary_key=True, foreign_key='rfq_desks.id')` |
| `version` | `int` | `version: int = Field(default=1)` |
| `second_validation_required` | `bool` | `second_validation_required: bool` |
| `max_calculation_age_minutes` | `int` | `max_calculation_age_minutes: int` |
| `updated_by` | `int` | `updated_by: int = Field(foreign_key='users.id')` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqBankQuoteDraft

Source : `backend/app/db/models.py:333`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_bank_quote_drafts'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `solicitation_id` | `int` | `solicitation_id: int = Field(primary_key=True, foreign_key='rfq_solicitations.id')` |
| `revision` | `int` | `revision: int = Field(default=1)` |
| `case_revision` | `int` | `case_revision: int` |
| `calculation_id` | `int` | `calculation_id: int = Field(foreign_key='product_calculation_runs.id')` |
| `prepared_by` | `int` | `prepared_by: int = Field(foreign_key='users.id')` |
| `prepared_at` | `datetime` | `prepared_at: datetime = Field(default_factory=datetime.utcnow)` |
| `payload_json` | `str` | `payload_json: str = Field(sa_column=Column(Text))` |
| `payload_hash` | `str` | `payload_hash: str` |
| `validated_by` | `Optional[int]` | `validated_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `validated_at` | `Optional[datetime]` | `validated_at: Optional[datetime] = None` |
| `validated_hash` | `Optional[str]` | `validated_hash: Optional[str] = None` |
| `validated_policy_version` | `Optional[int]` | `validated_policy_version: Optional[int] = None` |

## RfqQuotePublication

Source : `backend/app/db/models.py:349`. Bases : `SQLModel`.

Immutable published commercial response and its local delivery evidence.

- `__tablename__ = 'rfq_quote_publications'`
- `__table_args__ = (UniqueConstraint('solicitation_id', 'revision'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `solicitation_id` | `int` | `solicitation_id: int = Field(foreign_key='rfq_solicitations.id', index=True)` |
| `revision` | `int` | `revision: int` |
| `quote_id` | `int` | `quote_id: int = Field(foreign_key='rfq_quotes.id', unique=True)` |
| `message_id` | `str` | `message_id: str = Field(unique=True)` |
| `payload_json` | `str` | `payload_json: str = Field(sa_column=Column(Text))` |
| `published_by` | `int` | `published_by: int = Field(foreign_key='users.id')` |
| `published_at` | `datetime` | `published_at: datetime = Field(default_factory=datetime.utcnow)` |
| `delivered_at` | `datetime` | `delivered_at: datetime = Field(default_factory=datetime.utcnow)` |
| `withdrawn_at` | `Optional[datetime]` | `withdrawn_at: Optional[datetime] = None` |
| `withdrawn_by` | `Optional[int]` | `withdrawn_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `withdrawal_reason` | `Optional[str]` | `withdrawal_reason: Optional[str] = None` |
| `acceptance_received_at` | `Optional[datetime]` | `acceptance_received_at: Optional[datetime] = None` |

## RfqExecutionAgreement

Source : `backend/app/db/models.py:368`. Bases : `SQLModel`.

Local external treatment evidence; never a bank's electronic acceptance.

- `__tablename__ = 'rfq_execution_agreements'`
- `__table_args__ = (UniqueConstraint('rfq_id', 'command_key'), UniqueConstraint('entity_id', 'execution_reference'), Index('uq_rfq_active_execution_agreement', 'rfq_id', unique=True, sqlite_where=text("state != 'CANCELLED'"), postgresql_where=text("state != 'CANCELLED'")))`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `rfq_id` | `int` | `rfq_id: int = Field(foreign_key='rfq_requests.id', index=True)` |
| `entity_id` | `int` | `entity_id: int = Field(foreign_key='entities.id')` |
| `quote_id` | `int` | `quote_id: int = Field(foreign_key='rfq_quotes.id')` |
| `command_key` | `str` | `command_key: str` |
| `request_hash` | `str` | `request_hash: str` |
| `state` | `str` | `state: str = Field(default='REQUESTED')` |
| `snapshot_json` | `str` | `snapshot_json: str = Field(sa_column=Column(Text))` |
| `snapshot_hash` | `str` | `snapshot_hash: str` |
| `requested_by` | `int` | `requested_by: int = Field(foreign_key='users.id')` |
| `requested_at` | `datetime` | `requested_at: datetime = Field(default_factory=datetime.utcnow)` |
| `request_source` | `str` | `request_source: str` |
| `request_reference` | `str` | `request_reference: str` |
| `bank_contact` | `str` | `bank_contact: str` |
| `execution_reference` | `Optional[str]` | `execution_reference: Optional[str] = None` |
| `acceptance_received_at` | `Optional[datetime]` | `acceptance_received_at: Optional[datetime] = None` |
| `acceptance_evidence` | `Optional[str]` | `acceptance_evidence: Optional[str] = None` |
| `confirmed_at` | `Optional[datetime]` | `confirmed_at: Optional[datetime] = None` |
| `confirmed_by` | `Optional[int]` | `confirmed_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `confirmation_source` | `Optional[str]` | `confirmation_source: Optional[str] = None` |
| `confirmation_evidence` | `Optional[str]` | `confirmation_evidence: Optional[str] = None` |
| `confirmation_hash` | `Optional[str]` | `confirmation_hash: Optional[str] = None` |
| `written_confirmation_pending` | `bool` | `written_confirmation_pending: bool = Field(default=False)` |
| `cancellation_reason` | `Optional[str]` | `cancellation_reason: Optional[str] = None` |
| `booking_block_reason` | `Optional[str]` | `booking_block_reason: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `booking_blocked_at` | `Optional[datetime]` | `booking_blocked_at: Optional[datetime] = None` |
| `review_required_reason` | `Optional[str]` | `review_required_reason: Optional[str] = Field(default=None, sa_column=Column(Text))` |

## RfqExecutionBooking

Source : `backend/app/db/models.py:405`. Bases : `SQLModel`.

One immutable local booking per confirmed execution and organization.

- `__tablename__ = 'rfq_execution_bookings'`
- `__table_args__ = (UniqueConstraint('entity_id', 'execution_reference'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `agreement_id` | `int` | `agreement_id: int = Field(primary_key=True, foreign_key='rfq_execution_agreements.id')` |
| `entity_id` | `int` | `entity_id: int = Field(foreign_key='entities.id')` |
| `execution_reference` | `str` | `execution_reference: str` |
| `rfq_id` | `int` | `rfq_id: int = Field(foreign_key='rfq_requests.id', unique=True)` |
| `deal_id` | `int` | `deal_id: int = Field(foreign_key='deals.id', unique=True)` |
| `request_hash` | `str` | `request_hash: str` |
| `booked_by` | `int` | `booked_by: int = Field(foreign_key='users.id')` |
| `booked_at` | `datetime` | `booked_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqSendCommand

Source : `backend/app/db/models.py:419`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_send_commands'`
- `__table_args__ = (UniqueConstraint('rfq_id', 'command_key'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `rfq_id` | `int` | `rfq_id: int = Field(foreign_key='rfq_requests.id')` |
| `command_key` | `str` | `command_key: str` |
| `payload_hash` | `str` | `payload_hash: str` |
| `result_json` | `str` | `result_json: str = Field(sa_column=Column(Text))` |

## ReferenceCounter

Source : `backend/app/db/models.py:429`. Bases : `SQLModel`.

Atomic allocator state for externally visible business references.

- `__tablename__ = 'reference_counters'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `prefix` | `str` | `prefix: str = Field(primary_key=True)` |
| `last_value` | `int` | `last_value: int = Field(default=0)` |

## AdminAuditLog

Source : `backend/app/db/models.py:436`. Bases : `SQLModel`.

Append-only trace of privileged corrections made through Admin.

- `__tablename__ = 'admin_audit_logs'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `admin_user_id` | `Optional[int]` | `admin_user_id: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `table_key` | `str` | `table_key: str = Field(index=True)` |
| `row_id` | `int` | `row_id: int = Field(index=True)` |
| `action` | `str` | `action: str = Field(default='update')` |
| `before_json` | `str` | `before_json: str = Field(default='{}', sa_column=Column(Text))` |
| `after_json` | `str` | `after_json: str = Field(default='{}', sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow, index=True)` |

## AuditEvent

Source : `backend/app/db/models.py:449`. Bases : `SQLModel`.

Append-only business audit trail for critical workflow decisions.

- `__tablename__ = 'audit_events'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `action` | `str` | `action: str = Field(index=True)` |
| `object_type` | `str` | `object_type: str = Field(index=True)` |
| `object_id` | `Optional[int]` | `object_id: Optional[int] = Field(default=None, index=True)` |
| `actor_user_id` | `Optional[int]` | `actor_user_id: Optional[int] = Field(default=None, foreign_key='users.id', index=True)` |
| `actor_type` | `str` | `actor_type: str = Field(default='USER')` |
| `result` | `str` | `result: str = Field(default='SUCCESS', index=True)` |
| `before_json` | `str` | `before_json: str = Field(default='{}', sa_column=Column(Text))` |
| `after_json` | `str` | `after_json: str = Field(default='{}', sa_column=Column(Text))` |
| `reason` | `Optional[str]` | `reason: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `data_source` | `Optional[str]` | `data_source: Optional[str] = Field(default=None)` |
| `correlation_id` | `Optional[str]` | `correlation_id: Optional[str] = Field(default=None, index=True)` |
| `metadata_json` | `str` | `metadata_json: str = Field(default='{}', sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow, index=True)` |

## UatGenerationBatch

Source : `backend/app/db/models.py:468`. Bases : `SQLModel`.

Admin-created, reproducible RFQ/deal test-data lot.  Generated rows carry this batch id, which is the only deletion boundary: ordinary business data can never be swept by a reference-prefix purge. The row itself is retained after cleanup so the operator history remains auditable.

- `__tablename__ = 'uat_generation_batches'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `batch_key` | `str` | `batch_key: str = Field(unique=True, index=True)` |
| `label` | `str` | `label: str = Field(default='')` |
| `created_by` | `int` | `created_by: int = Field(foreign_key='users.id', index=True)` |
| `target_user_id` | `int` | `target_user_id: int = Field(foreign_key='users.id', index=True)` |
| `mode` | `str` | `mode: str = Field(index=True)` |
| `seed` | `int` | `seed: int` |
| `requested_count` | `int` | `requested_count: int` |
| `rfq_count` | `int` | `rfq_count: int = Field(default=0)` |
| `deal_count` | `int` | `deal_count: int = Field(default=0)` |
| `status` | `str` | `status: str = Field(default='RUNNING', index=True)` |
| `config_json` | `str` | `config_json: str = Field(default='{}', sa_column=Column(Text))` |
| `result_json` | `str` | `result_json: str = Field(default='{}', sa_column=Column(Text))` |
| `error_message` | `Optional[str]` | `error_message: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow, index=True)` |
| `completed_at` | `Optional[datetime]` | `completed_at: Optional[datetime] = Field(default=None)` |
| `deleted_at` | `Optional[datetime]` | `deleted_at: Optional[datetime] = Field(default=None)` |

## Folder

Source : `backend/app/db/models.py:496`. Bases : `SQLModel`.

- `__tablename__ = 'folders'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `name` | `str` | `name: str` |
| `parent_id` | `Optional[int]` | `parent_id: Optional[int] = Field(default=None, foreign_key='folders.id')` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## Portfolio

Source : `backend/app/db/models.py:505`. Bases : `SQLModel`.

A user-defined risk view over deals.  Membership is many-to-many through DealPortfolioMembership: the same economic position may legitimately appear in several monitoring views. Removing a portfolio therefore removes only its memberships, never the deals or their valuation history.

- `__tablename__ = 'portfolios'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `name` | `str` | `name: str` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id', index=True)` |
| `is_default` | `bool` | `is_default: bool = Field(default=False)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## DealPortfolioMembership

Source : `backend/app/db/models.py:522`. Bases : `SQLModel`.

Explicit, auditable membership of one deal in one portfolio.

- `__tablename__ = 'deal_portfolio_memberships'`
- `__table_args__ = (UniqueConstraint('deal_id', 'portfolio_id', name='uq_deal_portfolio_membership'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `deal_id` | `int` | `deal_id: int = Field(foreign_key='deals.id', index=True)` |
| `portfolio_id` | `int` | `portfolio_id: int = Field(foreign_key='portfolios.id', index=True)` |
| `added_by_user_id` | `Optional[int]` | `added_by_user_id: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## Script

Source : `backend/app/db/models.py:535`. Bases : `SQLModel`.

- `__tablename__ = 'scripts'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `name` | `str` | `name: str` |
| `description` | `str` | `description: str = Field(default='')` |
| `folder_id` | `Optional[int]` | `folder_id: Optional[int] = Field(default=None, foreign_key='folders.id')` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `script_text` | `str` | `script_text: str = Field(default='')` |
| `params_json` | `str` | `params_json: str = Field(default='{}')` |
| `constats_json` | `str` | `constats_json: str = Field(default='{}')` |
| `global_params_json` | `str` | `global_params_json: str = Field(default='{}')` |
| `category` | `str` | `category: str = Field(default='')` |
| `tags` | `str` | `tags: str = Field(default='')` |
| `is_shared` | `bool` | `is_shared: bool = Field(default=False)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |
| `ai_provider` | `str` | `ai_provider: str = Field(default='')` |
| `ai_model` | `str` | `ai_model: str = Field(default='')` |
| `ai_prompt` | `str` | `ai_prompt: str = Field(default='')` |
| `ai_generated_at` | `Optional[datetime]` | `ai_generated_at: Optional[datetime] = Field(default=None)` |
| `ai_provenance_json` | `str` | `ai_provenance_json: str = Field(default='{}', sa_column=Column(Text))` |
| `parent_id` | `Optional[int]` | `parent_id: Optional[int] = Field(default=None, foreign_key='scripts.id', index=True)` |
| `variant_title` | `str` | `variant_title: str = Field(default='')` |
| `variant_mode` | `str` | `variant_mode: str = Field(default='')` |
| `variant_delta_json` | `str` | `variant_delta_json: str = Field(default='{}')` |

## Deal

Source : `backend/app/db/models.py:579`. Bases : `SQLModel`.

- `__tablename__ = 'deals'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `product_id` | `Optional[int]` | `product_id: Optional[int] = Field(default=None, foreign_key='products.id', unique=True)` |
| `product_terms_version` | `Optional[int]` | `product_terms_version: Optional[int] = Field(default=None)` |
| `counterparty_id` | `Optional[int]` | `counterparty_id: Optional[int] = Field(default=None, foreign_key='counterparties.id')` |
| `legal_identity_exception_json` | `Optional[str]` | `legal_identity_exception_json: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `ccr_netting_set_id` | `Optional[int]` | `ccr_netting_set_id: Optional[int] = Field(default=None, foreign_key='ccr_netting_sets.id')` |
| `reference` | `str` | `reference: str = Field(index=True, unique=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id')` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `uat_batch_id` | `Optional[int]` | `uat_batch_id: Optional[int] = Field(default=None, foreign_key='uat_generation_batches.id', index=True)` |
| `indicative_id` | `Optional[int]` | `indicative_id: Optional[int] = Field(default=None, foreign_key='indicatives.id')` |
| `rfq_id` | `Optional[int]` | `rfq_id: Optional[int] = Field(default=None, foreign_key='rfq_requests.id', unique=True)` |
| `rfq_provenance_json` | `Optional[str]` | `rfq_provenance_json: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `client_id` | `Optional[int]` | `client_id: Optional[int] = Field(default=None, foreign_key='clients.id', index=True)` |
| `opportunity_id` | `Optional[int]` | `opportunity_id: Optional[int] = Field(default=None, foreign_key='opportunities.id', index=True)` |
| `primary_affiliation_id` | `Optional[int]` | `primary_affiliation_id: Optional[int] = Field(default=None, foreign_key='affiliations.id', index=True)` |
| `mandate_id` | `Optional[int]` | `mandate_id: Optional[int] = Field(default=None, foreign_key='client_mandates.id', index=True)` |
| `client_provenance_json` | `Optional[str]` | `client_provenance_json: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `client_attribution_json` | `Optional[str]` | `client_attribution_json: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `transaction_format` | `Optional[str]` | `transaction_format: Optional[str] = Field(default=None, index=True)` |
| `instrument_family` | `Optional[str]` | `instrument_family: Optional[str] = Field(default=None, index=True)` |
| `payoff_family` | `Optional[str]` | `payoff_family: Optional[str] = Field(default=None, index=True)` |
| `payoff_description` | `Optional[str]` | `payoff_description: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `documentation_reference` | `Optional[str]` | `documentation_reference: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `commercial_reason` | `Optional[str]` | `commercial_reason: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `portfolio_id` | `Optional[int]` | `portfolio_id: Optional[int] = Field(default=None, foreign_key='portfolios.id')` |
| `script_snapshot` | `str` | `script_snapshot: str = Field(default='', sa_column=Column(Text))` |
| `script_id` | `Optional[int]` | `script_id: Optional[int] = Field(default=None, foreign_key='scripts.id')` |
| `sens` | `str` | `sens: str = Field(default='vente')` |
| `contrepartie` | `str` | `contrepartie: str = Field(default='')` |
| `devise` | `str` | `devise: str = Field(default='EUR')` |
| `nominal` | `float` | `nominal: float = Field(default=0.0)` |
| `fair_value` | `float` | `fair_value: float = Field(default=0.0)` |
| `price_traded` | `float` | `price_traded: float = Field(default=0.0)` |
| `product_type` | `str` | `product_type: str = Field(default='')` |
| `fixing_policy` | `str` | `fixing_policy: str = Field(default='AUTO_YAHOO', index=True)` |
| `trade_date` | `str` | `trade_date: str = Field(default='')` |
| `strike_date` | `str` | `strike_date: str = Field(default='')` |
| `value_date` | `str` | `value_date: str = Field(default='')` |
| `maturity_date` | `str` | `maturity_date: str = Field(default='')` |
| `payment_date` | `str` | `payment_date: str = Field(default='')` |
| `T` | `float` | `T: float = Field(default=0.0)` |
| `realized_payout` | `Optional[float]` | `realized_payout: Optional[float] = Field(default=None)` |
| `settlement_amount` | `Optional[float]` | `settlement_amount: Optional[float] = Field(default=None)` |
| `resolution_outcome` | `Optional[str]` | `resolution_outcome: Optional[str] = Field(default=None)` |
| `settlement_date` | `Optional[str]` | `settlement_date: Optional[str] = Field(default=None)` |
| `underlyings_json` | `str` | `underlyings_json: str = Field(default='[]', sa_column=Column(Text))` |
| `market_snapshot_json` | `str` | `market_snapshot_json: str = Field(default='{}', sa_column=Column(Text))` |
| `schedule_json` | `str` | `schedule_json: str = Field(default='{}', sa_column=Column(Text))` |
| `greeks_json` | `str` | `greeks_json: str = Field(default='{}', sa_column=Column(Text))` |
| `greeks_computed_at` | `Optional[datetime]` | `greeks_computed_at: Optional[datetime] = Field(default=None)` |
| `latest_valuation_run_id` | `Optional[int]` | `latest_valuation_run_id: Optional[int] = Field(default=None, foreign_key='valuation_runs.id', index=True)` |
| `status` | `str` | `status: str = Field(default='actif')` |
| `contract_version` | `int` | `contract_version: int = Field(default=1)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## TradeAmendmentRequest

Source : `backend/app/db/models.py:760`. Bases : `SQLModel`.

Governed maker-checker request against one contract version.

- `__tablename__ = 'trade_amendment_requests'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `deal_id` | `int` | `deal_id: int = Field(foreign_key='deals.id', index=True)` |
| `field_name` | `str` | `field_name: str = Field(index=True)` |
| `old_value_json` | `str` | `old_value_json: str = Field(default='null', sa_column=Column(Text))` |
| `new_value_json` | `str` | `new_value_json: str = Field(default='null', sa_column=Column(Text))` |
| `reason` | `str` | `reason: str = Field(default='', sa_column=Column(Text))` |
| `requested_by` | `Optional[int]` | `requested_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `status` | `str` | `status: str = Field(default='PENDING', index=True)` |
| `base_contract_version` | `int` | `base_contract_version: int = Field(default=1)` |
| `validated_by` | `Optional[int]` | `validated_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `validated_at` | `Optional[datetime]` | `validated_at: Optional[datetime] = Field(default=None)` |
| `decision_reason` | `Optional[str]` | `decision_reason: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `rejected_by` | `Optional[int]` | `rejected_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `rejected_at` | `Optional[datetime]` | `rejected_at: Optional[datetime] = Field(default=None)` |
| `applied_by` | `Optional[int]` | `applied_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `applied_at` | `Optional[datetime]` | `applied_at: Optional[datetime] = Field(default=None)` |
| `applied_contract_version` | `Optional[int]` | `applied_contract_version: Optional[int] = Field(default=None)` |
| `credit_check_json` | `Optional[str]` | `credit_check_json: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow, index=True)` |

## DealContractVersion

Source : `backend/app/db/models.py:784`. Bases : `SQLModel`.

Immutable snapshot of a booked contract version.

- `__tablename__ = 'deal_contract_versions'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `deal_id` | `int` | `deal_id: int = Field(foreign_key='deals.id', index=True)` |
| `version` | `int` | `version: int = Field(index=True)` |
| `dedup_key` | `str` | `dedup_key: str = Field(unique=True, index=True)` |
| `snapshot_json` | `str` | `snapshot_json: str = Field(default='{}', sa_column=Column(Text))` |
| `amendment_request_id` | `Optional[int]` | `amendment_request_id: Optional[int] = Field(default=None, foreign_key='trade_amendment_requests.id', index=True)` |
| `created_by` | `Optional[int]` | `created_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow, index=True)` |

## Document

Source : `backend/app/db/models.py:798`. Bases : `SQLModel`.

- `__tablename__ = 'documents'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `product_id` | `Optional[int]` | `product_id: Optional[int] = Field(default=None, foreign_key='products.id', index=True)` |
| `product_terms_version` | `Optional[int]` | `product_terms_version: Optional[int] = Field(default=None)` |
| `deal_id` | `Optional[int]` | `deal_id: Optional[int] = Field(default=None, foreign_key='deals.id')` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `doc_type` | `str` | `doc_type: str = Field(default='')` |
| `title` | `str` | `title: str = Field(default='')` |
| `filename` | `str` | `filename: str = Field(default='')` |
| `file_path` | `str` | `file_path: str = Field(default='')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `metadata_json` | `str` | `metadata_json: str = Field(default='{}', sa_column=Column(Text))` |

## AmcStudy

Source : `backend/app/db/models.py:813`. Bases : `SQLModel`.

- `__tablename__ = 'amc_studies'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id', index=True)` |
| `isin` | `str` | `isin: str = Field(default='', index=True)` |
| `product_name` | `str` | `product_name: str = Field(default='')` |
| `label` | `str` | `label: str = Field(default='')` |
| `folder` | `str` | `folder: str = Field(default='')` |
| `manifest_json` | `str` | `manifest_json: str = Field(default='{}', sa_column=Column(Text))` |
| `result_json` | `str` | `result_json: str = Field(default='{}', sa_column=Column(Text))` |
| `synthese_text` | `str` | `synthese_text: str = Field(default='', sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## Indicative

Source : `backend/app/db/models.py:829`. Bases : `SQLModel`.

A pre-trade pricing opportunity — exists before any Deal does.  Holds its own frozen script/market snapshot exactly like Deal does, so KID/EMT generated during client discussion have something stable to attach to. If it converts to a trade, the resulting Deal points back via Deal.indicative_id — this row's id never changes and nothing here is ever re-keyed.

- `__tablename__ = 'indicatives'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `product_id` | `Optional[int]` | `product_id: Optional[int] = Field(default=None, foreign_key='products.id', index=True)` |
| `product_terms_version` | `Optional[int]` | `product_terms_version: Optional[int] = Field(default=None)` |
| `reference` | `str` | `reference: str = Field(index=True, unique=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id')` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `script_snapshot` | `str` | `script_snapshot: str = Field(default='', sa_column=Column(Text))` |
| `script_id` | `Optional[int]` | `script_id: Optional[int] = Field(default=None, foreign_key='scripts.id')` |
| `contrepartie` | `str` | `contrepartie: str = Field(default='')` |
| `devise` | `str` | `devise: str = Field(default='EUR')` |
| `nominal` | `float` | `nominal: float = Field(default=0.0)` |
| `underlyings_json` | `str` | `underlyings_json: str = Field(default='[]', sa_column=Column(Text))` |
| `market_snapshot_json` | `str` | `market_snapshot_json: str = Field(default='{}', sa_column=Column(Text))` |
| `status` | `str` | `status: str = Field(default='ouvert')` |
| `opportunity_id` | `Optional[int]` | `opportunity_id: Optional[int] = Field(default=None, foreign_key='opportunities.id', index=True)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## KidRecord

Source : `backend/app/db/models.py:869`. Bases : `SQLModel`.

One immutable KID PRIIPs computation. Never updated in place — each regeneration (required at least annually under PRIIPs) is a new row, so what was shown to a client at a given date stays reconstructable. Attached to exactly one of indicative_id / deal_id, whichever exists at generation time.

- `__tablename__ = 'kid_records'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `product_id` | `Optional[int]` | `product_id: Optional[int] = Field(default=None, foreign_key='products.id', index=True)` |
| `product_terms_version` | `Optional[int]` | `product_terms_version: Optional[int] = Field(default=None)` |
| `indicative_id` | `Optional[int]` | `indicative_id: Optional[int] = Field(default=None, foreign_key='indicatives.id')` |
| `deal_id` | `Optional[int]` | `deal_id: Optional[int] = Field(default=None, foreign_key='deals.id')` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `product_title` | `str` | `product_title: str = Field(default='')` |
| `sri` | `int` | `sri: int = Field(default=0)` |
| `mrm` | `int` | `mrm: int = Field(default=0)` |
| `crm` | `int` | `crm: int = Field(default=0)` |
| `vev` | `Optional[float]` | `vev: Optional[float] = Field(default=None)` |
| `t_rhp` | `float` | `t_rhp: float = Field(default=0.0)` |
| `horizons_json` | `str` | `horizons_json: str = Field(default='[]', sa_column=Column(Text))` |
| `costs_json` | `str` | `costs_json: str = Field(default='{}', sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## EmtRecord

Source : `backend/app/db/models.py:897`. Bases : `SQLModel`.

One immutable EMT / target-market computation — same append-only logic as KidRecord. sri/mrm/crm are copied from the KidRecord it was generated from (see emt.py), never recomputed independently.

- `__tablename__ = 'emt_records'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `product_id` | `Optional[int]` | `product_id: Optional[int] = Field(default=None, foreign_key='products.id', index=True)` |
| `product_terms_version` | `Optional[int]` | `product_terms_version: Optional[int] = Field(default=None)` |
| `indicative_id` | `Optional[int]` | `indicative_id: Optional[int] = Field(default=None, foreign_key='indicatives.id')` |
| `deal_id` | `Optional[int]` | `deal_id: Optional[int] = Field(default=None, foreign_key='deals.id')` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `product_title` | `str` | `product_title: str = Field(default='')` |
| `sri` | `int` | `sri: int = Field(default=0)` |
| `mrm` | `int` | `mrm: int = Field(default=0)` |
| `crm` | `int` | `crm: int = Field(default=0)` |
| `t_rhp` | `float` | `t_rhp: float = Field(default=0.0)` |
| `capital_tier` | `str` | `capital_tier: str = Field(default='')` |
| `capital_label` | `str` | `capital_label: str = Field(default='')` |
| `knowledge_tier` | `str` | `knowledge_tier: str = Field(default='')` |
| `knowledge_label` | `str` | `knowledge_label: str = Field(default='')` |
| `risk_tolerance` | `str` | `risk_tolerance: str = Field(default='')` |
| `objective` | `str` | `objective: str = Field(default='')` |
| `features_json` | `str` | `features_json: str = Field(default='{}', sa_column=Column(Text))` |
| `client_type` | `str` | `client_type: str = Field(default='retail')` |
| `distribution` | `str` | `distribution: str = Field(default='advice')` |
| `negative_target_market` | `str` | `negative_target_market: str = Field(default='', sa_column=Column(Text))` |
| `description` | `str` | `description: str = Field(default='', sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqBookingEvidence

Source : `backend/app/db/models.py:931`. Bases : `SQLModel`.

Server-verified RFQ calculation retained for an operational handoff.

- `__tablename__ = 'rfq_booking_evidence'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `rfq_id` | `int` | `rfq_id: int = Field(primary_key=True, foreign_key='rfq_requests.id')` |
| `terms_version` | `int` | `terms_version: int` |
| `input_hash` | `str` | `input_hash: str` |
| `receipt_json` | `str` | `receipt_json: str = Field(sa_column=Column(Text))` |
| `retained_by` | `int` | `retained_by: int = Field(foreign_key='users.id')` |
| `retained_at` | `datetime` | `retained_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqRequest

Source : `backend/app/db/models.py:942`. Bases : `SQLModel`.

A request for quote sent to one or more counterparty banks for a structured product. Mirrors Deal/Indicative: script frozen at creation time (template snapshot or copied from an existing Script), never re-keyed. Individual bank responses live in RfqQuote.

- `__tablename__ = 'rfq_requests'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `product_id` | `Optional[int]` | `product_id: Optional[int] = Field(default=None, foreign_key='products.id', index=True)` |
| `product_terms_version` | `Optional[int]` | `product_terms_version: Optional[int] = Field(default=None)` |
| `reference` | `str` | `reference: str = Field(index=True, unique=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id')` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `uat_batch_id` | `Optional[int]` | `uat_batch_id: Optional[int] = Field(default=None, foreign_key='uat_generation_batches.id', index=True)` |
| `name` | `str` | `name: str = Field(default='')` |
| `ao_date` | `str` | `ao_date: str = Field(default='')` |
| `kind` | `str` | `kind: str = Field(default='indicatif')` |
| `opportunity_id` | `Optional[int]` | `opportunity_id: Optional[int] = Field(default=None, foreign_key='opportunities.id', index=True)` |
| `client_id` | `Optional[int]` | `client_id: Optional[int] = Field(default=None, foreign_key='clients.id', index=True)` |
| `mandate_id` | `Optional[int]` | `mandate_id: Optional[int] = Field(default=None, foreign_key='client_mandates.id', index=True)` |
| `primary_affiliation_id` | `Optional[int]` | `primary_affiliation_id: Optional[int] = Field(default=None, foreign_key='affiliations.id', index=True)` |
| `commercial_context_json` | `Optional[str]` | `commercial_context_json: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `transaction_format` | `Optional[str]` | `transaction_format: Optional[str] = Field(default=None, index=True)` |
| `instrument_family` | `Optional[str]` | `instrument_family: Optional[str] = Field(default=None, index=True)` |
| `payoff_family` | `Optional[str]` | `payoff_family: Optional[str] = Field(default=None, index=True)` |
| `payoff_description` | `Optional[str]` | `payoff_description: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `documentation_reference` | `Optional[str]` | `documentation_reference: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `sens` | `str` | `sens: str = Field(default='achat')` |
| `template_type` | `str` | `template_type: str = Field(default='')` |
| `script_id` | `Optional[int]` | `script_id: Optional[int] = Field(default=None, foreign_key='scripts.id')` |
| `script_snapshot` | `str` | `script_snapshot: str = Field(default='', sa_column=Column(Text))` |
| `params_json` | `str` | `params_json: str = Field(default='{}', sa_column=Column(Text))` |
| `model_price` | `Optional[float]` | `model_price: Optional[float] = Field(default=None)` |
| `model_price_at` | `Optional[datetime]` | `model_price_at: Optional[datetime] = Field(default=None)` |
| `model_input_hash` | `Optional[str]` | `model_input_hash: Optional[str] = Field(default=None, index=True)` |
| `status` | `str` | `status: str = Field(default='draft')` |
| `selected_quote_id` | `Optional[int]` | `selected_quote_id: Optional[int] = Field(default=None, foreign_key='rfq_quotes.id')` |
| `selected_quote_revision` | `Optional[int]` | `selected_quote_revision: Optional[int] = Field(default=None)` |
| `selection_reason_code` | `Optional[str]` | `selection_reason_code: Optional[str] = Field(default=None, index=True)` |
| `selection_reason_note` | `Optional[str]` | `selection_reason_note: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqQuote

Source : `backend/app/db/models.py:1032`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_quotes'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `rfq_id` | `int` | `rfq_id: int = Field(foreign_key='rfq_requests.id', index=True)` |
| `revision` | `int` | `revision: int = Field(default=1)` |
| `provider` | `str` | `provider: str = Field(default='manuel')` |
| `provider_id` | `Optional[int]` | `provider_id: Optional[int] = Field(default=None, foreign_key='rfq_providers.id')` |
| `counterparty_id` | `Optional[int]` | `counterparty_id: Optional[int] = Field(default=None, foreign_key='counterparties.id')` |
| `counterparty_name` | `Optional[str]` | `counterparty_name: Optional[str] = None` |
| `identity_frozen` | `bool` | `identity_frozen: bool = Field(default=False)` |
| `contact` | `Optional[str]` | `contact: Optional[str] = Field(default=None)` |
| `price` | `Optional[float]` | `price: Optional[float] = Field(default=None)` |
| `model_reference_json` | `Optional[str]` | `model_reference_json: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `currency` | `Optional[str]` | `currency: Optional[str] = Field(default=None)` |
| `status` | `str` | `status: str = Field(default='en_attente')` |
| `note` | `Optional[str]` | `note: Optional[str] = Field(default=None)` |
| `quoted_at` | `Optional[datetime]` | `quoted_at: Optional[datetime] = Field(default=None)` |
| `firmness` | `str` | `firmness: str = Field(default='UNKNOWN')` |
| `valid_until` | `Optional[datetime]` | `valid_until: Optional[datetime] = Field(default=None)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `last_look` | `bool` | `last_look: bool = Field(default=False)` |
| `parent_quote_id` | `Optional[int]` | `parent_quote_id: Optional[int] = Field(default=None, foreign_key='rfq_quotes.id')` |

## Counterparty

Source : `backend/app/db/models.py:1066`. Bases : `SQLModel`.

Legal identity catalog. New bookings require an active stable ID; Deal.contrepartie retains the contractual label snapshot. Deactivation preserves historical links and never substitutes another legal entity.  limit_eur is an optional soft concentration limit (nominal EUR-converted across every active deal facing this counterparty) — set by an admin, read by the Risk Management "Contreparties" exposure view (api/portfolios.py:exposure-by-counterparty) to flag a breach. None means no limit configured (no breach ever flagged), not a zero limit.

- `__tablename__ = 'counterparties'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `name` | `str` | `name: str` |
| `country` | `str` | `country: str = Field(default='')` |
| `active` | `bool` | `active: bool = Field(default=True)` |
| `limit_eur` | `Optional[float]` | `limit_eur: Optional[float] = Field(default=None)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## ReferenceCatalogState

Source : `backend/app/db/models.py:1086`. Bases : `SQLModel`.

- `__tablename__ = 'reference_catalog_states'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `key` | `str` | `key: str = Field(primary_key=True)` |
| `initialized_at` | `datetime` | `initialized_at: datetime = Field(default_factory=datetime.utcnow)` |
| `adopted_existing` | `bool` | `adopted_existing: bool = Field(default=False)` |

## Underlying

Source : `backend/app/db/models.py:1093`. Bases : `SQLModel`.

Catalogue de sous-jacents administrable.  Cette liste vivait dans un fichier JavaScript du front : seul un développeur pouvait y ajouter un titre, et il fallait un rebuild. Elle est ici pour que l'ajout d'un sous-jacent redevienne un geste d'administration.  Un ticker peut figurer dans PLUSIEURS groupes — BNP Paribas est à la fois une valeur du CAC et une banque — donc l'unicité porte sur le couple (ticker, groupe) et non sur le ticker seul. C'est le comportement qu'avait le fichier, et il rend le choix d'un sous-jacent plus rapide selon qu'on raisonne par indice ou par secteur.  Le ticker est la clé Yahoo, place de cotation comprise : STMicroelectronics existe à Paris (STMPA.PA) et à Milan (STMMI.MI), et une note italienne fixe sur l'une des deux, pas sur l'autre.

- `__tablename__ = 'underlyings'`
- `__table_args__ = (UniqueConstraint('ticker', 'group_name', name='uq_underlying_ticker_group'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `ticker` | `str` | `ticker: str = Field(index=True)` |
| `label` | `str` | `label: str` |
| `group_name` | `str` | `group_name: str = Field(default='Autres')` |
| `ccy` | `str` | `ccy: str = Field(default='EUR')` |
| `asset_class` | `str` | `asset_class: str = Field(default='unknown')` |
| `exchange` | `str` | `exchange: str = Field(default='')` |
| `active` | `bool` | `active: bool = Field(default=True)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqProvider

Source : `backend/app/db/models.py:1129`. Bases : `SQLModel`.

RFQ channel catalog. Quotes freeze channel and local legal identity; legacy quotes remain readable and require explicit identity qualification.

- `__tablename__ = 'rfq_providers'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `label` | `str` | `label: str` |
| `mode` | `str` | `mode: str = Field(default='manual')` |
| `active` | `bool` | `active: bool = Field(default=True)` |
| `counterparty_id` | `Optional[int]` | `counterparty_id: Optional[int] = Field(default=None, foreign_key='counterparties.id')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqProviderContact

Source : `backend/app/db/models.py:1145`. Bases : `SQLModel`.

Client-admin directory of contacts for a quoting provider.  Quotes retain a contact name snapshot, so a later directory edit does not rewrite the historical record.

- `__tablename__ = 'rfq_provider_contacts'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `provider_id` | `int` | `provider_id: int = Field(foreign_key='rfq_providers.id', index=True)` |
| `name` | `str` | `name: str` |
| `email` | `str` | `email: str = Field(default='')` |
| `active` | `bool` | `active: bool = Field(default=True)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## Alert

Source : `backend/app/db/models.py:1160`. Bases : `SQLModel`.

Lifecycle/barrier alert raised by the daily refresh (or the manual 'Rafraîchir le book' action) — see services/lifecycle_alerts.py. dedup_key guarantees at most one alert per logical fact: one per deal resolution, one permanent knock-in crossing, and one autocall warning per contractual observation date. deal_reference is denormalized so the alert stays readable even if the deal is later deleted.

- `__tablename__ = 'alerts'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `deal_id` | `Optional[int]` | `deal_id: Optional[int] = Field(default=None, foreign_key='deals.id')` |
| `deal_reference` | `str` | `deal_reference: str = Field(default='')` |
| `kind` | `str` | `kind: str = Field(default='')` |
| `message` | `str` | `message: str = Field(default='', sa_column=Column(Text))` |
| `dedup_key` | `str` | `dedup_key: str = Field(default='', index=True)` |
| `read` | `bool` | `read: bool = Field(default=False)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## AlertRead

Source : `backend/app/db/models.py:1179`. Bases : `SQLModel`.

Reading a shared alert must not acknowledge it for another actor.

- `__tablename__ = 'alert_reads'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `alert_id` | `int` | `alert_id: int = Field(sa_column=Column(Integer, ForeignKey('alerts.id', ondelete='CASCADE'), primary_key=True))` |
| `user_id` | `int` | `user_id: int = Field(primary_key=True, foreign_key='users.id')` |
| `read_at` | `datetime` | `read_at: datetime = Field(default_factory=datetime.utcnow)` |

## DealEvent

Source : `backend/app/db/models.py:1210`. Bases : `SQLModel`.

- `__tablename__ = 'deal_events'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `deal_id` | `int` | `deal_id: int = Field(foreign_key='deals.id', index=True)` |
| `event_index` | `int` | `event_index: int = Field(default=0)` |
| `event_date` | `str` | `event_date: str = Field(default='')` |
| `t_years` | `float` | `t_years: float = Field(default=0.0)` |
| `spots_json` | `str` | `spots_json: str = Field(default='{}')` |
| `indicative_spots_json` | `str` | `indicative_spots_json: str = Field(default='{}', sa_column=Column(Text))` |
| `source` | `str` | `source: str = Field(default='pending')` |
| `status` | `str` | `status: str = Field(default='futur')` |
| `fixing_status` | `str` | `fixing_status: str = Field(default='EXPECTED', index=True)` |
| `data_category` | `str` | `data_category: str = Field(default='UNKNOWN')` |
| `current_fixing_version_id` | `Optional[int]` | `current_fixing_version_id: Optional[int] = Field(default=None, foreign_key='official_fixing_versions.id', index=True)` |
| `fixing_version` | `int` | `fixing_version: int = Field(default=0)` |
| `fixing_entered_by` | `Optional[int]` | `fixing_entered_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `fixing_entered_at` | `Optional[datetime]` | `fixing_entered_at: Optional[datetime] = Field(default=None)` |
| `fixing_provider` | `Optional[str]` | `fixing_provider: Optional[str] = Field(default=None)` |
| `fixing_source_type` | `Optional[str]` | `fixing_source_type: Optional[str] = Field(default=None)` |
| `fixing_external_reference` | `Optional[str]` | `fixing_external_reference: Optional[str] = Field(default=None)` |
| `fixing_observed_at` | `Optional[datetime]` | `fixing_observed_at: Optional[datetime] = Field(default=None)` |
| `fixing_venue` | `Optional[str]` | `fixing_venue: Optional[str] = Field(default=None)` |
| `fixing_calendar` | `Optional[str]` | `fixing_calendar: Optional[str] = Field(default=None)` |
| `fixing_timezone` | `Optional[str]` | `fixing_timezone: Optional[str] = Field(default=None)` |
| `fixing_evidence_sha256` | `Optional[str]` | `fixing_evidence_sha256: Optional[str] = Field(default=None)` |
| `fixing_record_sha256` | `Optional[str]` | `fixing_record_sha256: Optional[str] = Field(default=None, index=True)` |
| `fixing_reason` | `Optional[str]` | `fixing_reason: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `validated_by` | `Optional[int]` | `validated_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `validated_at` | `Optional[datetime]` | `validated_at: Optional[datetime] = Field(default=None)` |
| `applied_at` | `Optional[datetime]` | `applied_at: Optional[datetime] = Field(default=None)` |
| `label` | `str` | `label: str = Field(default='')` |
| `parent_event_id` | `Optional[int]` | `parent_event_id: Optional[int] = Field(default=None, foreign_key='deal_events.id', index=True)` |
| `reduction` | `str` | `reduction: str = Field(default='')` |

## OfficialFixingVersion

Source : `backend/app/db/models.py:1268`. Bases : `SQLModel`.

Immutable evidence record for one submitted official-fixing candidate.  A correction always creates a new row.  The event above only points to the current operational version; prior values, evidence and actors are never overwritten or deleted.

- `__tablename__ = 'official_fixing_versions'`
- `__table_args__ = (UniqueConstraint('deal_event_id', 'version', name='uq_official_fixing_event_version'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `deal_id` | `int` | `deal_id: int = Field(foreign_key='deals.id', index=True)` |
| `deal_event_id` | `int` | `deal_event_id: int = Field(foreign_key='deal_events.id', index=True)` |
| `version` | `int` | `version: int = Field(index=True)` |
| `supersedes_id` | `Optional[int]` | `supersedes_id: Optional[int] = Field(default=None, foreign_key='official_fixing_versions.id', index=True)` |
| `status` | `str` | `status: str = Field(default='RECEIVED', index=True)` |
| `spots_json` | `str` | `spots_json: str = Field(default='{}', sa_column=Column(Text))` |
| `provider` | `str` | `provider: str` |
| `source_type` | `str` | `source_type: str` |
| `external_reference` | `str` | `external_reference: str` |
| `observed_at` | `datetime` | `observed_at: datetime` |
| `received_at` | `datetime` | `received_at: datetime = Field(default_factory=datetime.utcnow)` |
| `venue` | `str` | `venue: str` |
| `calendar` | `str` | `calendar: str` |
| `timezone` | `str` | `timezone: str` |
| `evidence_sha256` | `str` | `evidence_sha256: str` |
| `evidence_filename` | `str` | `evidence_filename: str = Field(default='')` |
| `evidence_content_type` | `str` | `evidence_content_type: str = Field(default='application/octet-stream')` |
| `evidence_size_bytes` | `int` | `evidence_size_bytes: int = Field(default=0)` |
| `evidence_payload_b64` | `str` | `evidence_payload_b64: str = Field(default='', sa_column=Column(Text))` |
| `record_sha256` | `str` | `record_sha256: str = Field(index=True)` |
| `capture_reason` | `str` | `capture_reason: str = Field(sa_column=Column(Text))` |
| `entered_by` | `int` | `entered_by: int = Field(foreign_key='users.id', index=True)` |
| `capture_actor_type` | `str` | `capture_actor_type: str = Field(default='USER', index=True)` |
| `validated_by` | `Optional[int]` | `validated_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `validation_reason` | `Optional[str]` | `validation_reason: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `validated_at` | `Optional[datetime]` | `validated_at: Optional[datetime] = Field(default=None)` |
| `rejected_by` | `Optional[int]` | `rejected_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `rejection_reason` | `Optional[str]` | `rejection_reason: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `rejected_at` | `Optional[datetime]` | `rejected_at: Optional[datetime] = Field(default=None)` |
| `applied_at` | `Optional[datetime]` | `applied_at: Optional[datetime] = Field(default=None)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow, index=True)` |

## LifecycleProposal

Source : `backend/app/db/models.py:1317`. Bases : `SQLModel`.

Non-binding result proposed from monitoring data.  Validation and application are explicit separate transitions.  The economic result is immutable once proposed.

- `__tablename__ = 'lifecycle_proposals'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `deal_id` | `int` | `deal_id: int = Field(foreign_key='deals.id', index=True)` |
| `event_id` | `Optional[int]` | `event_id: Optional[int] = Field(default=None, foreign_key='deal_events.id', index=True)` |
| `dedup_key` | `str` | `dedup_key: str = Field(unique=True, index=True)` |
| `status` | `str` | `status: str = Field(default='PROPOSED', index=True)` |
| `proposed_outcome` | `str` | `proposed_outcome: str = Field(index=True)` |
| `result_json` | `str` | `result_json: str = Field(default='{}', sa_column=Column(Text))` |
| `data_source` | `str` | `data_source: str = Field(default='INDICATIVE')` |
| `official_result_json` | `Optional[str]` | `official_result_json: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `official_input_hash` | `Optional[str]` | `official_input_hash: Optional[str] = Field(default=None, index=True)` |
| `official_replayed_at` | `Optional[datetime]` | `official_replayed_at: Optional[datetime] = Field(default=None)` |
| `comparison_status` | `Optional[str]` | `comparison_status: Optional[str] = Field(default=None, index=True)` |
| `proposed_by` | `Optional[int]` | `proposed_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `validated_by` | `Optional[int]` | `validated_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `validation_reason` | `Optional[str]` | `validation_reason: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `validated_at` | `Optional[datetime]` | `validated_at: Optional[datetime] = Field(default=None)` |
| `applied_by` | `Optional[int]` | `applied_by: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `applied_at` | `Optional[datetime]` | `applied_at: Optional[datetime] = Field(default=None)` |
| `error_message` | `Optional[str]` | `error_message: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `correlation_id` | `Optional[str]` | `correlation_id: Optional[str] = Field(default=None, index=True)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow, index=True)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## ShockRun

Source : `backend/app/db/models.py:1350`. Bases : `SQLModel`.

One market-shock scenario (spot/vol/rate/corr, full reprice — see api/shocks.py) played against a deal or a portfolio. Append-only, same immutable-history pattern as KidRecord/EmtRecord — a shock's parameters can change on the next run, so past runs stay reconstructable rather than overwritten.

- `__tablename__ = 'shock_runs'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `scope` | `str` | `scope: str = Field(default='deal')` |
| `deal_id` | `Optional[int]` | `deal_id: Optional[int] = Field(default=None, foreign_key='deals.id')` |
| `portfolio_id` | `Optional[int]` | `portfolio_id: Optional[int] = Field(default=None, foreign_key='portfolios.id')` |
| `label` | `str` | `label: str = Field(default='')` |
| `params_json` | `str` | `params_json: str = Field(default='{}', sa_column=Column(Text))` |
| `result_json` | `str` | `result_json: str = Field(default='{}', sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## ComputeBatch

Source : `backend/app/db/models.py:1368`. Bases : `SQLModel`.

One submission to the generic parallel compute module (core/compute/) — a set of independent jobs, all processed by the same pricer (`kind`), executed by a worker daemon (scripts/run_compute_worker.py) that polls this table. Mirrors ShockRun's persistence intent (a run's inputs/outputs stay reconstructable) but adds a full queued → running → terminal lifecycle instead of append-only, since a batch (unlike a single shock) can take long enough to need polling from the caller.  First consumer in mind: a VaR/ES study (chantier #2) submits one batch per method (historical/parametric), one job per market scenario — but nothing here is VaR-specific; `kind` + each job's own payload_json is where the actual meaning lives (see core/compute/pricers/).

- `__tablename__ = 'compute_batches'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `kind` | `str` | `kind: str = Field(default='')` |
| `label` | `str` | `label: str = Field(default='')` |
| `status` | `str` | `status: str = Field(default='queued')` |
| `total_jobs` | `int` | `total_jobs: int = Field(default=0)` |
| `completed_jobs` | `int` | `completed_jobs: int = Field(default=0)` |
| `failed_jobs` | `int` | `failed_jobs: int = Field(default=0)` |
| `params_json` | `str` | `params_json: str = Field(default='{}', sa_column=Column(Text))` |
| `result_summary_json` | `str` | `result_summary_json: str = Field(default='{}', sa_column=Column(Text))` |
| `worker_name` | `Optional[str]` | `worker_name: Optional[str] = Field(default=None)` |
| `claimed_at` | `Optional[datetime]` | `claimed_at: Optional[datetime] = Field(default=None)` |
| `lease_token` | `Optional[str]` | `lease_token: Optional[str] = Field(default=None, index=True)` |
| `lease_expires_at` | `Optional[datetime]` | `lease_expires_at: Optional[datetime] = Field(default=None, index=True)` |
| `heartbeat_at` | `Optional[datetime]` | `heartbeat_at: Optional[datetime] = Field(default=None)` |
| `cancel_requested_at` | `Optional[datetime]` | `cancel_requested_at: Optional[datetime] = Field(default=None)` |
| `cost_estimate_json` | `str` | `cost_estimate_json: str = Field(default='{}', sa_column=Column(Text))` |
| `started_at` | `Optional[datetime]` | `started_at: Optional[datetime] = Field(default=None)` |
| `finished_at` | `Optional[datetime]` | `finished_at: Optional[datetime] = Field(default=None)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## ComputeJob

Source : `backend/app/db/models.py:1404`. Bases : `SQLModel`.

One independent unit of work inside a ComputeBatch — payload_json is pure data (never a live Python object): on ProcessPoolExecutor (the default — see core/compute/executor.py for why threads don't help the PayScript engine), a job payload crosses a real process boundary via pickle, so anything not JSON-plain (a CompiledScript's exec()-produced closures, in particular) can never be part of it — only script TEXT and market data, recompiled fresh in the worker.

- `__tablename__ = 'compute_jobs'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `batch_id` | `int` | `batch_id: int = Field(foreign_key='compute_batches.id', index=True)` |
| `job_index` | `int` | `job_index: int = Field(default=0)` |
| `label` | `str` | `label: str = Field(default='')` |
| `payload_json` | `str` | `payload_json: str = Field(default='{}', sa_column=Column(Text))` |
| `status` | `str` | `status: str = Field(default='queued')` |
| `lease_token` | `Optional[str]` | `lease_token: Optional[str] = Field(default=None, index=True)` |
| `attempt` | `int` | `attempt: int = Field(default=0)` |
| `result_json` | `str` | `result_json: str = Field(default='{}', sa_column=Column(Text))` |
| `error` | `Optional[str]` | `error: Optional[str] = Field(default=None)` |
| `started_at` | `Optional[datetime]` | `started_at: Optional[datetime] = Field(default=None)` |
| `finished_at` | `Optional[datetime]` | `finished_at: Optional[datetime] = Field(default=None)` |

## ValuationRun

Source : `backend/app/db/models.py:1427`. Bases : `SQLModel`.

Immutable evidence for one explicit deal valuation action.  Internal bump legs belong to the result of the same run.  Replaying a run consumes only context_json and never refreshes external market data.

- `__tablename__ = 'valuation_runs'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `deal_id` | `int` | `deal_id: int = Field(foreign_key='deals.id', index=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `run_type` | `str` | `run_type: str = Field(default='MTM', index=True)` |
| `contract_version` | `int` | `contract_version: int = Field(default=1)` |
| `context_json` | `str` | `context_json: str = Field(default='{}', sa_column=Column(Text))` |
| `context_hash` | `str` | `context_hash: str = Field(index=True)` |
| `market_data_json` | `str` | `market_data_json: str = Field(default='{}', sa_column=Column(Text))` |
| `data_versions_json` | `str` | `data_versions_json: str = Field(default='{}', sa_column=Column(Text))` |
| `engine_version` | `str` | `engine_version: str = Field(default='unknown')` |
| `engine_fingerprint` | `str` | `engine_fingerprint: str = Field(default='')` |
| `n_paths` | `int` | `n_paths: int = Field(default=0)` |
| `result_json` | `str` | `result_json: str = Field(default='{}', sa_column=Column(Text))` |
| `diagnostics_json` | `str` | `diagnostics_json: str = Field(default='{}', sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow, index=True)` |

## ValuationNote

Source : `backend/app/db/models.py:1451`. Bases : `SQLModel`.

Editable narrative over immutable valuation evidence.

- `__tablename__ = 'valuation_notes'`
- `__table_args__ = (UniqueConstraint('user_id', 'request_key'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `deal_id` | `int` | `deal_id: int = Field(foreign_key='deals.id', index=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `request_key` | `str` | `request_key: str` |
| `title` | `str` | `title: str` |
| `kind` | `str` | `kind: str` |
| `evidence_json` | `str` | `evidence_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `draft_json` | `str` | `draft_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `revision` | `int` | `revision: int = Field(default=1)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## ValuationNoteVersion

Source : `backend/app/db/models.py:1468`. Bases : `SQLModel`.

- `__tablename__ = 'valuation_note_versions'`
- `__table_args__ = (UniqueConstraint('note_id', 'revision'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `note_id` | `int` | `note_id: int = Field(foreign_key='valuation_notes.id', index=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `revision` | `int` | `revision: int` |
| `title` | `str` | `title: str` |
| `draft_json` | `str` | `draft_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `pdf_base64` | `str` | `pdf_base64: str = Field(sa_column=Column(Text, nullable=False))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## SchedulerRun

Source : `backend/app/db/models.py:1481`. Bases : `SQLModel`.

Durable, idempotent journal for one scheduled lifecycle slot.

- `__tablename__ = 'scheduler_runs'`
- `__table_args__ = (UniqueConstraint('job_key', 'scheduled_for', name='uq_scheduler_job_slot'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `job_key` | `str` | `job_key: str = Field(index=True)` |
| `scheduled_for` | `datetime` | `scheduled_for: datetime = Field(index=True)` |
| `timezone` | `str` | `timezone: str = Field(default='Europe/Paris')` |
| `status` | `str` | `status: str = Field(default='RUNNING', index=True)` |
| `trigger` | `str` | `trigger: str = Field(default='SCHEDULED')` |
| `result_json` | `str` | `result_json: str = Field(default='{}', sa_column=Column(Text))` |
| `error` | `Optional[str]` | `error: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `started_at` | `datetime` | `started_at: datetime = Field(default_factory=datetime.utcnow)` |
| `finished_at` | `Optional[datetime]` | `finished_at: Optional[datetime] = Field(default=None)` |

## Client

Source : `backend/app/db/models.py:1517`. Bases : `SQLModel`.

Une organisation cliente — jamais une personne.  Portée par l'entité, pas par l'utilisateur : deux commerciaux qui couvrent tous deux « ABC Asset Management » doivent voir UNE ligne, pas deux. Qui couvre quoi se lit dans ClientCoverage.  constraints_json est le nom technique historique du profil courant : devises, formats, instruments, payoffs, univers et habitudes d'émetteurs. Ces informations guident le commercial mais ne bloquent aucun RFQ ni Deal. Une restriction opérationnelle réelle reste explicitement distinguée dans le référentiel. JSON plutôt que colonnes parce que le vocabulaire bouge avec le métier, comme market_snapshot_json ailleurs.

- `__tablename__ = 'clients'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id', index=True)` |
| `name` | `str` | `name: str = Field(index=True)` |
| `legal_name` | `Optional[str]` | `legal_name: Optional[str] = Field(default=None)` |
| `client_type` | `str` | `client_type: str = Field(default='other', index=True)` |
| `country` | `Optional[str]` | `country: Optional[str] = Field(default=None)` |
| `status` | `str` | `status: str = Field(default='prospect', index=True)` |
| `external_ref` | `Optional[str]` | `external_ref: Optional[str] = Field(default=None, index=True)` |
| `notes` | `Optional[str]` | `notes: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `data_origin` | `str` | `data_origin: str = Field(default='demo', index=True)` |
| `market_data_provider` | `str` | `market_data_provider: str = Field(default='YAHOO_FINANCE', index=True)` |
| `ticket_min` | `Optional[float]` | `ticket_min: Optional[float] = Field(default=None)` |
| `ticket_max` | `Optional[float]` | `ticket_max: Optional[float] = Field(default=None)` |
| `ticket_currency` | `str` | `ticket_currency: str = Field(default='EUR')` |
| `maturity_min_months` | `Optional[int]` | `maturity_min_months: Optional[int] = Field(default=None)` |
| `maturity_max_months` | `Optional[int]` | `maturity_max_months: Optional[int] = Field(default=None)` |
| `min_rating` | `Optional[str]` | `min_rating: Optional[str] = Field(default=None)` |
| `max_concentration_pct` | `Optional[float]` | `max_concentration_pct: Optional[float] = Field(default=None)` |
| `constraints_json` | `str` | `constraints_json: str = Field(default='{}', sa_column=Column(Text))` |
| `constraints_version` | `int` | `constraints_version: int = Field(default=1)` |
| `created_by_user_id` | `Optional[int]` | `created_by_user_id: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## ClientMandate

Source : `backend/app/db/models.py:1597`. Bases : `SQLModel`.

Mandat, fonds, compte ou desk couvert pour un Client.  L'objet précise le périmètre d'une attribution commerciale mais ne devient jamais une dépendance du moteur Produit. Il s'archive lorsqu'il n'est plus utilisable ; les objets historiques gardent leur lien et leurs snapshots.

- `__tablename__ = 'client_mandates'`
- `__table_args__ = (UniqueConstraint('client_id', 'name', name='uq_client_mandate_name'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id', index=True)` |
| `client_id` | `int` | `client_id: int = Field(foreign_key='clients.id', index=True)` |
| `mandate_type` | `str` | `mandate_type: str = Field(default='mandate', index=True)` |
| `name` | `str` | `name: str = Field(index=True)` |
| `status` | `str` | `status: str = Field(default='active', index=True)` |
| `reference_currency` | `Optional[str]` | `reference_currency: Optional[str] = Field(default=None)` |
| `comment` | `Optional[str]` | `comment: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `data_origin` | `str` | `data_origin: str = Field(default='demo', index=True)` |
| `created_by_user_id` | `Optional[int]` | `created_by_user_id: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## ClientPreferenceStatement

Source : `backend/app/db/models.py:1625`. Bases : `SQLModel`.

Append-only evidence for a declared or commercially recorded preference.  `Client.constraints_json` remains the compatibility projection used by the existing form.  This table answers the questions that a current JSON blob cannot: who said what, for which mandate/contact, on which date, and what statement superseded the previous understanding.  Rows are never updated to mark them obsolete.  The current view is derived deterministically from the latest effective statement for a scope/key; older rows therefore remain auditable without a mutable status flag.

- `__tablename__ = 'client_preference_statements'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id', index=True)` |
| `client_id` | `int` | `client_id: int = Field(foreign_key='clients.id', index=True)` |
| `mandate_id` | `Optional[int]` | `mandate_id: Optional[int] = Field(default=None, foreign_key='client_mandates.id', index=True)` |
| `affiliation_id` | `Optional[int]` | `affiliation_id: Optional[int] = Field(default=None, foreign_key='affiliations.id', index=True)` |
| `preference_key` | `str` | `preference_key: str = Field(index=True)` |
| `value_json` | `str` | `value_json: str = Field(default='null', sa_column=Column(Text))` |
| `statement_kind` | `str` | `statement_kind: str = Field(default='client_declared', index=True)` |
| `statement_date` | `str` | `statement_date: str = Field(default='', index=True)` |
| `source_affiliation_id` | `Optional[int]` | `source_affiliation_id: Optional[int] = Field(default=None, foreign_key='affiliations.id', index=True)` |
| `channel` | `Optional[str]` | `channel: Optional[str] = Field(default=None, index=True)` |
| `interaction_id` | `Optional[int]` | `interaction_id: Optional[int] = Field(default=None, foreign_key='interactions.id', index=True)` |
| `note` | `Optional[str]` | `note: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `recorded_by_user_id` | `int` | `recorded_by_user_id: int = Field(foreign_key='users.id', index=True)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow, index=True)` |

## Person

Source : `backend/app/db/models.py:1663`. Bases : `SQLModel`.

Une personne physique, dont l'identité ne dépend d'aucun employeur.  Pas de client_id ici, délibérément : l'employeur du jour se lit dans l'affiliation ouverte (end_date IS NULL). Poser un client_id permanent serait exactement le raccourci qui fait basculer un historique entier d'une société à l'autre le jour d'un changement de poste.  email est indexé mais PAS unique : la détection de doublons avertit, elle ne bloque pas. Deux homonymes existent, et une adresse peut être ressaisie légitimement — une contrainte dure interdirait à l'utilisateur de confirmer qu'il s'agit bien d'une nouvelle personne.

- `__tablename__ = 'persons'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id', index=True)` |
| `first_name` | `str` | `first_name: str = Field(default='', index=True)` |
| `last_name` | `str` | `last_name: str = Field(default='', index=True)` |
| `email` | `Optional[str]` | `email: Optional[str] = Field(default=None, index=True)` |
| `phone` | `Optional[str]` | `phone: Optional[str] = Field(default=None)` |
| `notes` | `Optional[str]` | `notes: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `is_active` | `bool` | `is_active: bool = Field(default=True, index=True)` |
| `created_by_user_id` | `Optional[int]` | `created_by_user_id: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## Affiliation

Source : `backend/app/db/models.py:1690`. Bases : `SQLModel`.

Le pivot historique : une personne, chez un client, sur une période.  C'est l'objet sur lequel pointent Interaction, Opportunity et Deal. Son couple (person_id, client_id) est immuable après création — le corriger reviendrait à réécrire un passé. Une erreur de saisie se répare en supprimant l'affiliation tant qu'elle ne porte rien, jamais en la réaffectant à un autre client.  « Actuelle » n'est pas stockée : elle se DÉDUIT de end_date IS NULL, comme RfqRequest.status se déduit des faits du dossier. Un booléen redondant peut diverger de la date qui fait foi, et la question « qui travaille ici aujourd'hui » n'aurait alors plus une seule réponse.  preferences_json porte ce qui est propre à cette personne DANS cette société — Jean aime les autocalls, mais chez Bank B il est tenu à une maturité ≤ 3 ans. Les préférences durables de la personne restent sur Person, les contraintes de la société sur Client.constraints_json : les trois niveaux existent et ne doivent pas être confondus.

- `__tablename__ = 'affiliations'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `person_id` | `int` | `person_id: int = Field(foreign_key='persons.id', index=True)` |
| `client_id` | `int` | `client_id: int = Field(foreign_key='clients.id', index=True)` |
| `job_title` | `str` | `job_title: str = Field(default='')` |
| `commercial_role` | `str` | `commercial_role: str = Field(default='other', index=True)` |
| `start_date` | `str` | `start_date: str = Field(default='')` |
| `end_date` | `Optional[str]` | `end_date: Optional[str] = Field(default=None, index=True)` |
| `notes` | `Optional[str]` | `notes: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `preferences_json` | `str` | `preferences_json: str = Field(default='{}', sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## ClientCoverage

Source : `backend/app/db/models.py:1726`. Bases : `SQLModel`.

Qui, chez nous, couvre ce client. Le client reste une identité unique ; seule la couverture est propre à un utilisateur.

- `__tablename__ = 'client_coverage'`
- `__table_args__ = (UniqueConstraint('user_id', 'client_id', name='uq_client_coverage_user_client'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `client_id` | `int` | `client_id: int = Field(foreign_key='clients.id', index=True)` |
| `coverage_role` | `str` | `coverage_role: str = Field(default='primary', index=True)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## ContactCoverage

Source : `backend/app/db/models.py:1741`. Bases : `SQLModel`.

Qui couvre quel contact. Porte sur l'AFFILIATION et non la Person : deux commerciaux peuvent couvrir le même client sur des contacts différents — l'un le CIO, l'autre les conseillers.

- `__tablename__ = 'contact_coverage'`
- `__table_args__ = (UniqueConstraint('user_id', 'affiliation_id', name='uq_contact_coverage_user_affiliation'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `affiliation_id` | `int` | `affiliation_id: int = Field(foreign_key='affiliations.id', index=True)` |
| `coverage_role` | `str` | `coverage_role: str = Field(default='primary', index=True)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## Interaction

Source : `backend/app/db/models.py:1758`. Bases : `SQLModel`.

Un événement commercial daté.  opportunity_id est nullable et le restera : une prospection initiale n'a aucune opportunité derrière elle, et l'exiger obligerait à ouvrir un dossier vide pour enregistrer un premier appel.

- `__tablename__ = 'interactions'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id', index=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `client_id` | `int` | `client_id: int = Field(foreign_key='clients.id', index=True)` |
| `opportunity_id` | `Optional[int]` | `opportunity_id: Optional[int] = Field(default=None, foreign_key='opportunities.id', index=True)` |
| `interaction_date` | `str` | `interaction_date: str = Field(default='', index=True)` |
| `interaction_type` | `str` | `interaction_type: str = Field(default='other', index=True)` |
| `summary` | `str` | `summary: str = Field(default='')` |
| `notes` | `Optional[str]` | `notes: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `next_action` | `Optional[str]` | `next_action: Optional[str] = Field(default=None)` |
| `next_action_date` | `Optional[str]` | `next_action_date: Optional[str] = Field(default=None, index=True)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## InteractionFollowUp

Source : `backend/app/db/models.py:1784`. Bases : `SQLModel`.

Action commerciale issue d'une interaction, avec une vraie clôture.

- `__tablename__ = 'interaction_follow_ups'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id', index=True)` |
| `interaction_id` | `int` | `interaction_id: int = Field(foreign_key='interactions.id', index=True)` |
| `client_id` | `int` | `client_id: int = Field(foreign_key='clients.id', index=True)` |
| `opportunity_id` | `Optional[int]` | `opportunity_id: Optional[int] = Field(default=None, foreign_key='opportunities.id', index=True)` |
| `owner_user_id` | `int` | `owner_user_id: int = Field(foreign_key='users.id', index=True)` |
| `title` | `str` | `title: str = Field(default='')` |
| `due_date` | `Optional[str]` | `due_date: Optional[str] = Field(default=None, index=True)` |
| `status` | `str` | `status: str = Field(default='open', index=True)` |
| `created_by_user_id` | `int` | `created_by_user_id: int = Field(foreign_key='users.id')` |
| `closed_by_user_id` | `Optional[int]` | `closed_by_user_id: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `closure_note` | `Optional[str]` | `closure_note: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |
| `closed_at` | `Optional[datetime]` | `closed_at: Optional[datetime] = Field(default=None)` |

## InteractionParticipant

Source : `backend/app/db/models.py:1805`. Bases : `SQLModel`.

Les personnes présentes, désignées par leur affiliation du moment.

- `__tablename__ = 'interaction_participants'`
- `__table_args__ = (UniqueConstraint('interaction_id', 'affiliation_id', name='uq_interaction_participant'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `interaction_id` | `int` | `interaction_id: int = Field(foreign_key='interactions.id', index=True)` |
| `affiliation_id` | `int` | `affiliation_id: int = Field(foreign_key='affiliations.id', index=True)` |
| `role` | `str` | `role: str = Field(default='other')` |

## Opportunity

Source : `backend/app/db/models.py:1818`. Bases : `SQLModel`.

Une intention d'investissement — distincte d'une RFQ et d'un Indicative.  Un Indicative est un PRIX figé avec son script, son snapshot de marché et son KID ; une Opportunity est le BESOIN commercial qui a motivé ce prix. Un même besoin fait souvent pricer trois idées dont une seule se traite : les fondre écraserait cette cardinalité. Indicative.opportunity_id et RfqRequest.opportunity_id portent le rattachement, tous deux nullables pour que ces deux modules continuent de fonctionner sans client identifié.  primary_affiliation_id est nullable : un besoin institutionnel peut arriver par la société sans qu'une personne en particulier le porte. Quand il est posé, il doit désigner une affiliation DE CE CLIENT — contrôle serveur, parce qu'un contrôle d'écran se contourne par un appel direct.

- `__tablename__ = 'opportunities'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `reference` | `str` | `reference: str = Field(index=True, unique=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id', index=True)` |
| `owner_user_id` | `int` | `owner_user_id: int = Field(foreign_key='users.id', index=True)` |
| `client_id` | `int` | `client_id: int = Field(foreign_key='clients.id', index=True)` |
| `primary_affiliation_id` | `Optional[int]` | `primary_affiliation_id: Optional[int] = Field(default=None, foreign_key='affiliations.id', index=True)` |
| `mandate_id` | `Optional[int]` | `mandate_id: Optional[int] = Field(default=None, foreign_key='client_mandates.id', index=True)` |
| `title` | `str` | `title: str = Field(default='')` |
| `description` | `Optional[str]` | `description: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `amount` | `Optional[float]` | `amount: Optional[float] = Field(default=None)` |
| `currency` | `str` | `currency: str = Field(default='EUR')` |
| `horizon` | `Optional[str]` | `horizon: Optional[str] = Field(default=None)` |
| `expected_trade_date` | `Optional[str]` | `expected_trade_date: Optional[str] = Field(default=None, index=True)` |
| `expected_window_start` | `Optional[str]` | `expected_window_start: Optional[str] = Field(default=None)` |
| `expected_window_end` | `Optional[str]` | `expected_window_end: Optional[str] = Field(default=None)` |
| `priority` | `str` | `priority: str = Field(default='medium', index=True)` |
| `source` | `Optional[str]` | `source: Optional[str] = Field(default=None)` |
| `transaction_format` | `Optional[str]` | `transaction_format: Optional[str] = Field(default=None, index=True)` |
| `instrument_family` | `Optional[str]` | `instrument_family: Optional[str] = Field(default=None, index=True)` |
| `payoff_family` | `Optional[str]` | `payoff_family: Optional[str] = Field(default=None, index=True)` |
| `payoff_description` | `Optional[str]` | `payoff_description: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `data_origin` | `str` | `data_origin: str = Field(default='demo', index=True)` |
| `status` | `str` | `status: str = Field(default='lead', index=True)` |
| `lost_reason` | `Optional[str]` | `lost_reason: Optional[str] = Field(default=None, index=True)` |
| `lost_comment` | `Optional[str]` | `lost_comment: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `next_action` | `Optional[str]` | `next_action: Optional[str] = Field(default=None)` |
| `next_action_date` | `Optional[str]` | `next_action_date: Optional[str] = Field(default=None, index=True)` |
| `notes` | `Optional[str]` | `notes: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `last_activity_at` | `Optional[datetime]` | `last_activity_at: Optional[datetime] = Field(default=None, index=True)` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## OpportunityParticipant

Source : `backend/app/db/models.py:1877`. Bases : `SQLModel`.

Les autres personnes impliquées, hors contact principal.  Une opportunité n'est presque jamais l'affaire d'une seule personne : le gérant décide, le CIO valide, le middle exécute. L'unicité empêche qu'une même affiliation figure deux fois ; que le contact principal n'y figure pas est un contrôle applicatif, la base ne voit pas cette colonne.

- `__tablename__ = 'opportunity_participants'`
- `__table_args__ = (UniqueConstraint('opportunity_id', 'affiliation_id', name='uq_opportunity_participant'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `opportunity_id` | `int` | `opportunity_id: int = Field(foreign_key='opportunities.id', index=True)` |
| `affiliation_id` | `int` | `affiliation_id: int = Field(foreign_key='affiliations.id', index=True)` |
| `role` | `str` | `role: str = Field(default='other')` |

## ClientImportBatch

Source : `backend/app/db/models.py:1907`. Bases : `SQLModel`.

Un versement, avec de quoi le défaire.  Chaque ligne écrite par un import porte l'identifiant de son lot. C'est ce qui rend un import RÉVERSIBLE : sans cela, un fichier mal formaté versé sur une base déjà peuplée laisserait des lignes qu'on ne saurait plus distinguer des vraies, et le seul remède serait de repartir d'une sauvegarde.  `report_json` conserve le compte rendu tel qu'il a été montré avant la validation — combien de lignes lues, créées, mises à jour, ignorées, et pourquoi. Une reprise six mois plus tard doit pouvoir répondre à « d'où sort cette ligne » sans reconstituer le fichier d'origine.

- `__tablename__ = 'client_import_batches'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id', index=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id', index=True)` |
| `filename` | `str` | `filename: str = Field(default='')` |
| `file_fingerprint` | `str` | `file_fingerprint: str = Field(default='', index=True)` |
| `source_format` | `str` | `source_format: str = Field(default='xlsx')` |
| `status` | `str` | `status: str = Field(default='applied', index=True)` |
| `rows_created` | `int` | `rows_created: int = Field(default=0)` |
| `rows_updated` | `int` | `rows_updated: int = Field(default=0)` |
| `rows_skipped` | `int` | `rows_skipped: int = Field(default=0)` |
| `report_json` | `str` | `report_json: str = Field(default='{}', sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `reverted_at` | `Optional[datetime]` | `reverted_at: Optional[datetime] = Field(default=None)` |

## ClientTradeHistory

Source : `backend/app/db/models.py:1937`. Bases : `SQLModel`.

Une transaction passée d'un client, versée depuis un fichier.  **Délibérément PAS un `Deal`.** Un Deal est une position que nous portons : il alimente le booking, l'agrégation de risque, le MtM et le cycle de vie, et il suppose un script, un instantané de marché et un calendrier de constatations. Une ligne d'historique client n'a rien de tout cela — c'est le fait qu'un investisseur a acheté quelque chose, souvent par un autre canal que nous.  Les fondre créerait de fausses positions dans le book : exactement le défaut relevé sur les deals UAT, qui entrent aujourd'hui dans l'exposition contrepartie et le HHI sans être des trades réels. Cette table est lue par Client Intelligence et par personne d'autre.  Comme un Deal rattaché, elle pointe sur l'AFFILIATION : une transaction faite chez Bank A en 2024 y reste, même si son auteur travaille ailleurs aujourd'hui.

- `__tablename__ = 'client_trade_history'`
- `__table_args__ = (UniqueConstraint('entity_id', 'natural_key', name='uq_client_trade_history_natural_key'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id', index=True)` |
| `import_batch_id` | `Optional[int]` | `import_batch_id: Optional[int] = Field(default=None, foreign_key='client_import_batches.id', index=True)` |
| `natural_key` | `Optional[str]` | `natural_key: Optional[str] = Field(default=None, index=True)` |
| `client_id` | `int` | `client_id: int = Field(foreign_key='clients.id', index=True)` |
| `affiliation_id` | `Optional[int]` | `affiliation_id: Optional[int] = Field(default=None, foreign_key='affiliations.id', index=True)` |
| `mandate_id` | `Optional[int]` | `mandate_id: Optional[int] = Field(default=None, foreign_key='client_mandates.id', index=True)` |
| `trade_date` | `str` | `trade_date: str = Field(default='', index=True)` |
| `maturity_date` | `Optional[str]` | `maturity_date: Optional[str] = Field(default=None)` |
| `product_type` | `str` | `product_type: str = Field(default='')` |
| `transaction_format` | `Optional[str]` | `transaction_format: Optional[str] = Field(default=None, index=True)` |
| `instrument_family` | `Optional[str]` | `instrument_family: Optional[str] = Field(default=None, index=True)` |
| `payoff_family` | `Optional[str]` | `payoff_family: Optional[str] = Field(default=None, index=True)` |
| `payoff_description` | `Optional[str]` | `payoff_description: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `documentation_reference` | `Optional[str]` | `documentation_reference: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `underlying` | `Optional[str]` | `underlying: Optional[str] = Field(default=None)` |
| `issuer` | `Optional[str]` | `issuer: Optional[str] = Field(default=None)` |
| `currency` | `str` | `currency: str = Field(default='EUR')` |
| `notional` | `Optional[float]` | `notional: Optional[float] = Field(default=None)` |
| `coupon_pct` | `Optional[float]` | `coupon_pct: Optional[float] = Field(default=None)` |
| `barrier_pct` | `Optional[float]` | `barrier_pct: Optional[float] = Field(default=None)` |
| `traded_with_us` | `Optional[bool]` | `traded_with_us: Optional[bool] = Field(default=None, index=True)` |
| `price_pct` | `Optional[float]` | `price_pct: Optional[float] = Field(default=None)` |
| `external_ref` | `Optional[str]` | `external_ref: Optional[str] = Field(default=None, index=True)` |
| `notes` | `Optional[str]` | `notes: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## ConstraintDefinition

Source : `backend/app/db/models.py:2004`. Bases : `SQLModel`.

Un champ du profil déclaré — par l'admin, ou pour un client précis.  Le profil se stocke dans le blob historique `constraints_json` sur `Client`, et `validate_constraints` refuse toute clé qu'aucune définition ne décrit. Cette table est ce qui rend le refus extensible sans le rendre laxiste : une clé devient connue parce qu'elle a été DÉCLARÉE, jamais parce qu'elle a été envoyée.  `client_id` porte toute la nuance du besoin. Nul, le champ vaut pour toute la maison — un vocabulaire interne, une catégorie suivie partout. Renseigné, c'est un nom convenu entre l'utilisateur et ce client-là : sa « poche défensive », sa « limite Rouge ». Ce vocabulaire n'a de sens que dans cette relation ; le proposer aux autres clients serait du bruit, et le ranger dans un champ de notes le rendrait illisible par le module.  Rien n'est jamais supprimé, seulement `archived` : la valeur déjà saisie chez un client survivrait à la définition, et la validation suivante la refuserait comme clé inconnue.

- `__tablename__ = 'constraint_definitions'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `entity_id` | `Optional[int]` | `entity_id: Optional[int] = Field(default=None, foreign_key='entities.id', index=True)` |
| `client_id` | `Optional[int]` | `client_id: Optional[int] = Field(default=None, foreign_key='clients.id', index=True)` |
| `key` | `str` | `key: str = Field(index=True)` |
| `label` | `str` | `label: str` |
| `kind` | `str` | `kind: str = Field(default='text')` |
| `options_json` | `str` | `options_json: str = Field(default='[]')` |
| `catalog` | `Optional[str]` | `catalog: Optional[str] = Field(default=None)` |
| `unit` | `Optional[str]` | `unit: Optional[str] = Field(default=None)` |
| `help_text` | `Optional[str]` | `help_text: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `free_entry` | `bool` | `free_entry: bool = Field(default=True)` |
| `archived` | `bool` | `archived: bool = Field(default=False, index=True)` |
| `created_by_user_id` | `Optional[int]` | `created_by_user_id: Optional[int] = Field(default=None, foreign_key='users.id')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqElectronicExecution

Source : `backend/app/db/rfq_electronic_models.py:7`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_electronic_executions'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `str` | `id: str = Field(primary_key=True)` |
| `solicitation_id` | `int` | `solicitation_id: int = Field(foreign_key='rfq_solicitations.id', unique=True)` |
| `product_id` | `int` | `product_id: int = Field(foreign_key='products.id')` |
| `agreement_id` | `int \| None` | `agreement_id: int \| None = Field(default=None, foreign_key='rfq_execution_agreements.id', unique=True)` |
| `request_message_id` | `str` | `request_message_id: str = Field(unique=True)` |
| `request_json` | `str` | `request_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `request_hash` | `str` | `request_hash: str` |
| `role` | `str` | `role: str` |
| `state` | `str` | `state: str` |
| `requested_by` | `int` | `requested_by: int = Field(foreign_key='users.id')` |
| `received_at` | `datetime \| None` | `received_at: datetime \| None = None` |
| `decision_json` | `str \| None` | `decision_json: str \| None = Field(default=None, sa_column=Column(Text))` |
| `decision_message_id` | `str \| None` | `decision_message_id: str \| None = Field(default=None, unique=True)` |
| `decided_by` | `int \| None` | `decided_by: int \| None = Field(default=None, foreign_key='users.id')` |

## RfqElectronicBooking

Source : `backend/app/db/rfq_electronic_models.py:25`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_electronic_bookings'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `execution_id` | `str` | `execution_id: str = Field(primary_key=True, foreign_key='rfq_electronic_executions.id')` |
| `deal_id` | `int` | `deal_id: int = Field(foreign_key='deals.id', unique=True)` |
| `request_hash` | `str` | `request_hash: str` |
| `booked_by` | `int` | `booked_by: int = Field(foreign_key='users.id')` |
| `booked_at` | `datetime` | `booked_at: datetime` |

## RfqElectronicEvidence

Source : `backend/app/db/rfq_electronic_models.py:34`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_electronic_evidence'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `message_id` | `str` | `message_id: str = Field(primary_key=True, foreign_key='rfq_transport_inbox.id')` |
| `envelope_json` | `str` | `envelope_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `received_at` | `datetime` | `received_at: datetime` |

## RfqReconciliationStatement

Source : `backend/app/db/rfq_reconciliation_models.py:7`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_reconciliation_statements'`
- `__table_args__ = (UniqueConstraint('execution_id', 'role', 'version'), UniqueConstraint('execution_id', 'command_key'))`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `message_id` | `str` | `message_id: str = Field(primary_key=True)` |
| `execution_id` | `str` | `execution_id: str = Field(foreign_key='rfq_electronic_executions.id', index=True)` |
| `role` | `str` | `role: str` |
| `version` | `int` | `version: int` |
| `payload_json` | `str` | `payload_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `payload_hash` | `str` | `payload_hash: str` |
| `is_local` | `bool` | `is_local: bool` |
| `command_key` | `str \| None` | `command_key: str \| None = None` |
| `recorded_at` | `datetime` | `recorded_at: datetime` |

## RfqInstallation

Source : `backend/app/db/rfq_transport_models.py:8`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_installation'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `int` | `id: int = Field(default=1, primary_key=True)` |
| `installation_id` | `str` | `installation_id: str = Field(unique=True)` |

## RfqChannel

Source : `backend/app/db/rfq_transport_models.py:14`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_channels'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `str` | `id: str = Field(primary_key=True)` |
| `relationship_id` | `int` | `relationship_id: int = Field(foreign_key='rfq_relationships.id', unique=True)` |
| `relationship_version` | `int` | `relationship_version: int` |
| `entity_id` | `int` | `entity_id: int = Field(foreign_key='entities.id', index=True)` |
| `role` | `str` | `role: str` |
| `peer_installation_id` | `str` | `peer_installation_id: str` |
| `peer_url` | `str` | `peer_url: str` |
| `secret` | `str` | `secret: str` |
| `agreement_hash` | `str` | `agreement_hash: str` |
| `active` | `bool` | `active: bool = True` |
| `confirmed_at` | `Optional[datetime]` | `confirmed_at: Optional[datetime] = None` |
| `configured_by` | `int` | `configured_by: int = Field(foreign_key='users.id')` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqRemoteLink

Source : `backend/app/db/rfq_transport_models.py:31`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_remote_links'`
- `__table_args__ = (UniqueConstraint('channel_id', 'request_message_id'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `solicitation_id` | `int` | `solicitation_id: int = Field(primary_key=True, foreign_key='rfq_solicitations.id')` |
| `channel_id` | `str` | `channel_id: str = Field(foreign_key='rfq_channels.id')` |
| `request_message_id` | `str` | `request_message_id: str` |
| `inbound` | `bool` | `inbound: bool` |

## RfqTransportOutbox

Source : `backend/app/db/rfq_transport_models.py:40`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_transport_outbox'`
- `__table_args__ = (UniqueConstraint('channel_id', 'request_message_id', 'sequence'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `str` | `id: str = Field(primary_key=True)` |
| `channel_id` | `str` | `channel_id: str = Field(foreign_key='rfq_channels.id', index=True)` |
| `solicitation_id` | `int` | `solicitation_id: int = Field(foreign_key='rfq_solicitations.id', index=True)` |
| `request_message_id` | `str` | `request_message_id: str` |
| `sequence` | `int` | `sequence: int` |
| `kind` | `str` | `kind: str` |
| `payload_json` | `str` | `payload_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `payload_hash` | `str` | `payload_hash: str` |
| `actor_user_id` | `int` | `actor_user_id: int = Field(foreign_key='users.id')` |
| `state` | `str` | `state: str = Field(default='PENDING', index=True)` |
| `attempts` | `int` | `attempts: int = 0` |
| `next_attempt_at` | `datetime` | `next_attempt_at: datetime = Field(default_factory=datetime.utcnow)` |
| `lease_until` | `Optional[datetime]` | `lease_until: Optional[datetime] = None` |
| `lease_token` | `Optional[str]` | `lease_token: Optional[str] = None` |
| `received_at` | `Optional[datetime]` | `received_at: Optional[datetime] = None` |
| `receipt_json` | `Optional[str]` | `receipt_json: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `signed_receipt_json` | `Optional[str]` | `signed_receipt_json: Optional[str] = Field(default=None, sa_column=Column(Text))` |
| `last_error` | `Optional[str]` | `last_error: Optional[str] = None` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqTransportInbox

Source : `backend/app/db/rfq_transport_models.py:64`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_transport_inbox'`
- `__table_args__ = (UniqueConstraint('channel_id', 'request_message_id', 'sequence'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `str` | `id: str = Field(primary_key=True)` |
| `channel_id` | `str` | `channel_id: str = Field(foreign_key='rfq_channels.id')` |
| `request_message_id` | `str` | `request_message_id: str` |
| `sequence` | `int` | `sequence: int` |
| `payload_hash` | `str` | `payload_hash: str` |
| `payload_json` | `str` | `payload_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `receipt_json` | `str` | `receipt_json: str = Field(sa_column=Column(Text, nullable=False))` |
| `received_at` | `datetime` | `received_at: datetime = Field(default_factory=datetime.utcnow)` |

## RfqTransportAttempt

Source : `backend/app/db/rfq_transport_models.py:77`. Bases : `SQLModel`.

- `__tablename__ = 'rfq_transport_attempts'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `Optional[int]` | `id: Optional[int] = Field(default=None, primary_key=True)` |
| `message_id` | `str` | `message_id: str = Field(foreign_key='rfq_transport_outbox.id', index=True)` |
| `attempted_at` | `datetime` | `attempted_at: datetime = Field(default_factory=datetime.utcnow)` |
| `outcome` | `str` | `outcome: str` |
| `detail` | `Optional[str]` | `detail: Optional[str] = None` |

## TradingRelationship

Source : `backend/app/db/trading_models.py:7`. Bases : `SQLModel`.

- `__tablename__ = 'trading_relationships'`
- `__table_args__ = (UniqueConstraint('entity_id', 'counterparty_id', 'reference'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `int \| None` | `id: int \| None = Field(default=None, primary_key=True)` |
| `entity_id` | `int` | `entity_id: int = Field(foreign_key='entities.id', index=True)` |
| `counterparty_id` | `int` | `counterparty_id: int = Field(foreign_key='counterparties.id')` |
| `reference` | `str` | `reference: str` |
| `version` | `int` | `version: int = 1` |
| `terms_json` | `str` | `terms_json: str` |
| `updated_by` | `int` | `updated_by: int = Field(foreign_key='users.id')` |
| `updated_at` | `datetime` | `updated_at: datetime = Field(default_factory=datetime.utcnow)` |

## TradingExecution

Source : `backend/app/db/trading_models.py:20`. Bases : `SQLModel`.

- `__tablename__ = 'trading_executions'`
- `__table_args__ = (UniqueConstraint('entity_id', 'trade_reference'),)`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `int \| None` | `id: int \| None = Field(default=None, primary_key=True)` |
| `entity_id` | `int` | `entity_id: int = Field(foreign_key='entities.id', index=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `deal_id` | `int` | `deal_id: int = Field(foreign_key='deals.id')` |
| `relationship_id` | `int` | `relationship_id: int = Field(foreign_key='trading_relationships.id')` |
| `trade_reference` | `str` | `trade_reference: str` |
| `request_hash` | `str` | `request_hash: str` |
| `issuer` | `str` | `issuer: str` |
| `our_side` | `str` | `our_side: str` |
| `instrument_reference` | `str` | `instrument_reference: str` |
| `settlement_status` | `str` | `settlement_status: str = 'PENDING'` |
| `settlement_reference` | `str` | `settlement_reference: str = ''` |
| `settled_at` | `datetime \| None` | `settled_at: datetime \| None = None` |
| `created_at` | `datetime` | `created_at: datetime = Field(default_factory=datetime.utcnow)` |

## AdminWorkbenchIdentity

Source : `backend/app/hybrid/admin_workbench.py:12`. Bases : `SQLModel`.

- `__tablename__ = 'admin_workbench_identity'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `int` | `id: int = Field(default=1, primary_key=True)` |
| `installation_id` | `str` | `installation_id: str = Field(unique=True)` |
| `entity_id` | `int` | `entity_id: int = Field(foreign_key='entities.id')` |

## HybridBootstrap

Source : `backend/app/hybrid/business.py:14`. Bases : `SQLModel`.

- `__tablename__ = 'hybrid_bootstrap'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `id` | `int` | `id: int = Field(default=1, primary_key=True)` |
| `installation_id` | `str` | `installation_id: str = Field(unique=True)` |
| `organization_id` | `str` | `organization_id: str = Field(unique=True)` |
| `entity_id` | `int` | `entity_id: int = Field(foreign_key='entities.id')` |
| `seed_version` | `int` | `seed_version: int = 1` |
| `baseline_json` | `str` | `baseline_json: str` |

## DevelopmentRedemption

Source : `backend/app/hybrid/business.py:24`. Bases : `SQLModel`.

- `__tablename__ = 'hybrid_development_redemptions'`

Options de classe : `table=True`

| Champ | Type | Définition |
|---|---|---|
| `ticket_id` | `str` | `ticket_id: str = Field(primary_key=True)` |
| `user_id` | `int` | `user_id: int = Field(foreign_key='users.id')` |
| `origin_json` | `str` | `origin_json: str` |
| `received_at` | `datetime` | `received_at: datetime = Field(default_factory=datetime.utcnow)` |

## InstallationConfig

Source : `backend/app/hybrid/config.py:12`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid', frozen=True)`

| Champ | Type | Définition |
|---|---|---|
| `version` | `Literal[1]` | `version: Literal[1] = 1` |
| `installation_id` | `UUID` | `installation_id: UUID` |
| `organization_id` | `UUID \| None` | `organization_id: UUID \| None = None` |
| `key` | `str` | `key: str = Field(pattern='^[a-z][a-z0-9-]*$')` |
| `name` | `str` | `name: str` |
| `kind` | `Literal['organization', 'platform']` | `kind: Literal['organization', 'platform']` |
| `service` | `Literal['application', 'simulation_controller', 'portal_redirect', 'admin_workbench']` | `service: Literal['application', 'simulation_controller', 'portal_redirect', 'admin_workbench'] = 'application'` |
| `environment` | `Literal['DEVELOPMENT']` | `environment: Literal['DEVELOPMENT'] = 'DEVELOPMENT'` |
| `data_dir` | `Path` | `data_dir: Path` |
| `port` | `int` | `port: int = Field(ge=1024, le=65535)` |
| `capabilities` | `tuple[Literal['request_rfq', 'respond_rfq'], ...]` | `capabilities: tuple[Literal['request_rfq', 'respond_rfq'], ...] = ()` |
| `retention` | `Literal['UNTIL_EXPLICIT_RESET']` | `retention: Literal['UNTIL_EXPLICIT_RESET'] = 'UNTIL_EXPLICIT_RESET'` |
| `registry_state` | `Literal['NOT_CONFIGURED']` | `registry_state: Literal['NOT_CONFIGURED'] = 'NOT_CONFIGURED'` |
| `billing_enabled` | `Literal[False]` | `billing_enabled: Literal[False] = False` |

Méthodes/validators : `check_scope:30`; `public_descriptor:41`

## DirectoryEntry

Source : `backend/app/hybrid/config.py:51`. Bases : `BaseModel`.

Allowlist central metadata; rejects business contents and private paths.

- `model_config = ConfigDict(extra='forbid', frozen=True)`

| Champ | Type | Définition |
|---|---|---|
| `installation_id` | `UUID` | `installation_id: UUID` |
| `organization_id` | `UUID` | `organization_id: UUID` |
| `key` | `str` | `key: str = Field(pattern='^[a-z][a-z0-9-]*$')` |
| `name` | `str` | `name: str` |
| `kind` | `Literal['organization']` | `kind: Literal['organization']` |
| `environment` | `Literal['DEVELOPMENT']` | `environment: Literal['DEVELOPMENT']` |
| `capabilities` | `tuple[Literal['request_rfq', 'respond_rfq'], ...]` | `capabilities: tuple[Literal['request_rfq', 'respond_rfq'], ...]` |
| `url` | `str` | `url: str = Field(pattern='^http://127\\.0\\.0\\.1:[0-9]{4,5}$')` |
| `registry_state` | `Literal['NOT_CONFIGURED']` | `registry_state: Literal['NOT_CONFIGURED']` |
| `billing_enabled` | `Literal[False]` | `billing_enabled: Literal[False]` |
| `retention` | `Literal['UNTIL_EXPLICIT_RESET']` | `retention: Literal['UNTIL_EXPLICIT_RESET']` |

## DevelopmentTarget

Source : `backend/app/hybrid/development.py:14`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `installation_id` | `str` | `installation_id: str` |
| `username` | `str` | `username: str = 'superuser'` |
| `start_if_needed` | `bool` | `start_if_needed: bool = False` |

## DevelopmentTicket

Source : `backend/app/hybrid/development.py:21`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `ticket` | `str` | `ticket: str` |

## PasswordChange

Source : `backend/app/hybrid/platform.py:27`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `current_password` | `str` | `current_password: str` |
| `new_password` | `str` | `new_password: str` |

## Decision

Source : `backend/app/services/agent_workshop/brain.py:13`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `tool` | `str` | `tool: str` |
| `args` | `dict` | `args: dict = Field(default_factory=dict)` |
| `reason` | `str` | `reason: str = Field(min_length=1, max_length=1200)` |

## StrictModel

Source : `backend/app/services/agent_workshop/configuration.py:21`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid', allow_inf_nan=False)`

## CampaignConfig

Source : `backend/app/services/agent_workshop/store.py:20`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `schema_version` | `Literal[1, 2]` | `schema_version: Literal[1, 2] = 1` |
| `horizon_months` | `int` | `horizon_months: int = Field(default=60, ge=1, le=120)` |
| `market_mode` | `Literal['synthetic', 'historical']` | `market_mode: Literal['synthetic', 'historical'] = 'synthetic'` |
| `end_date` | `str \| None` | `end_date: str \| None = None` |
| `participants` | `list[Participant]` | `participants: list[Participant] = Field(default_factory=default_participants, min_length=1, max_length=6)` |
| `products` | `list[ProductSettings]` | `products: list[ProductSettings] = Field(default_factory=default_products, max_length=3)` |
| `calendar` | `list[CalendarMonth]` | `calendar: list[CalendarMonth] = Field(default_factory=default_calendar, max_length=120)` |
| `economy_common` | `Economy` | `economy_common: Economy = Field(default_factory=Economy)` |
| `cadences` | `Cadences` | `cadences: Cadences = Field(default_factory=Cadences)` |
| `max_wall_minutes` | `int` | `max_wall_minutes: int = Field(default=60, ge=1, le=1440)` |
| `coverage_modules` | `list[str]` | `coverage_modules: list[str] = Field(default_factory=lambda: list(COVERAGE))` |
| `name` | `str` | `name: str = Field(default='Une année avec Hector', min_length=1, max_length=100)` |
| `provider` | `Literal['ollama', 'openai']` | `provider: Literal['ollama', 'openai'] = 'ollama'` |
| `model` | `str` | `model: str = Field(default='qwen2.5-coder:7b', min_length=1, max_length=100)` |
| `start_date` | `str` | `start_date: str = Field(default_factory=lambda: (date.today() - relativedelta(years=1)).isoformat())` |
| `months` | `int` | `months: int = Field(default=12, ge=1, le=60)` |
| `maturity_months` | `int` | `maturity_months: int = Field(default=6, ge=6, le=60)` |
| `payoff_templates` | `list[Literal['reverse_convertible', 'phoenix', 'autocall_athena']]` | `payoff_templates: list[Literal['reverse_convertible', 'phoenix', 'autocall_athena']] = Field(default_factory=list, max_length=3)` |
| `target_volume` | `float` | `target_volume: float = Field(default=100000000, gt=0, le=10000000000.0)` |
| `ticket` | `float` | `ticket: float = Field(default=10000000, gt=0, le=1000000000.0)` |
| `max_turns` | `int` | `max_turns: int = Field(default=800, ge=10, le=5000)` |
| `timeout_seconds` | `int` | `timeout_seconds: int = Field(default=90, ge=10, le=180)` |
| `max_ai_cost_usd` | `float` | `max_ai_cost_usd: float = Field(default=5, ge=0.01, le=500)` |
| `max_model_calls` | `int` | `max_model_calls: int = Field(default=1500, ge=1, le=20000)` |
| `seed` | `int` | `seed: int = Field(default=42, ge=0, le=2147483647)` |
| `coaching` | `bool` | `coaching: bool = True` |
| `exploratory_actions` | `bool` | `exploratory_actions: bool = False` |
| `include_sg` | `bool` | `include_sg: bool = True` |
| `contract_scenario` | `Literal['baseline', 'all_complete', 'random']` | `contract_scenario: Literal['baseline', 'all_complete', 'random'] = 'baseline'` |
| `environment` | `Literal['legacy', 'hybrid']` | `environment: Literal['legacy', 'hybrid'] = 'hybrid'` |
| `leonteq_role` | `Literal['bank']` | `leonteq_role: Literal['bank'] = 'bank'` |
| `native_rfq` | `bool` | `native_rfq: bool = True` |

Méthodes/validators : `validate_model_selection:54`; `validate_start:70`

## DocumentSelection

Source : `backend/app/services/archived_documents.py:17`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `archive_id` | `str` | `archive_id: str = Field(min_length=1, max_length=40)` |

## ProposalFreeze

Source : `backend/app/services/archived_documents.py:22`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `preview` | `dict` | `preview: dict` |

## ResearchCreate

Source : `backend/app/services/optimizer_research.py:23`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `optimization` | `OptimizationRequest` | `optimization: OptimizationRequest` |
| `title` | `str` | `title: str = Field(default='', max_length=160)` |
| `intention` | `str` | `intention: str = Field(default='', max_length=4000)` |
| `parent_id` | `str \| None` | `parent_id: str \| None = Field(default=None, max_length=40)` |
| `command_key` | `str` | `command_key: str = Field(min_length=1, max_length=128)` |

## ArchiveChange

Source : `backend/app/services/optimizer_research.py:31`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `archived` | `bool` | `archived: bool` |

## ReviewBooking

Source : `backend/app/services/rfq_booking.py:20`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `review_token` | `str` | `review_token: str = Field(min_length=64, max_length=64)` |
| `ccr_netting_set_id` | `int \| None` | `ccr_netting_set_id: int \| None = None` |

## ElectronicRequest

Source : `backend/app/services/rfq_electronic.py:25`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `quote_id` | `int` | `quote_id: int` |
| `expected_terms_version` | `int` | `expected_terms_version: int = Field(gt=0)` |
| `expected_terms_fingerprint` | `str` | `expected_terms_fingerprint: str = Field(min_length=64, max_length=64)` |
| `command_key` | `str` | `command_key: str = Field(min_length=16, max_length=100)` |

## BankDecision

Source : `backend/app/services/rfq_electronic.py:33`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `expected_request_hash` | `str` | `expected_request_hash: str = Field(min_length=64, max_length=64)` |
| `decision` | `Literal['CONFIRMED', 'REJECTED']` | `decision: Literal['CONFIRMED', 'REJECTED']` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=500)` |

## WireRequest

Source : `backend/app/services/rfq_electronic.py:40`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `format_version` | `Literal[1]` | `format_version: Literal[1]` |
| `execution_id` | `UUID` | `execution_id: UUID` |
| `execution_reference` | `str` | `execution_reference: str = Field(min_length=3, max_length=100)` |
| `quote` | `dict` | `quote: dict` |
| `requested_at` | `datetime` | `requested_at: datetime` |
| `requester` | `dict[str, str]` | `requester: dict[str, str]` |

## WireDecision

Source : `backend/app/services/rfq_electronic.py:50`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `format_version` | `Literal[1]` | `format_version: Literal[1]` |
| `execution_id` | `UUID` | `execution_id: UUID` |
| `request_hash` | `str` | `request_hash: str = Field(min_length=64, max_length=64)` |
| `decision` | `Literal['CONFIRMED', 'REJECTED']` | `decision: Literal['CONFIRMED', 'REJECTED']` |
| `received_at` | `datetime` | `received_at: datetime` |
| `decided_at` | `datetime` | `decided_at: datetime` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=500)` |
| `bank` | `dict[str, str]` | `bank: dict[str, str]` |

## TreatmentRequest

Source : `backend/app/services/rfq_execution.py:24`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `quote_id` | `int` | `quote_id: int` |
| `expected_terms_version` | `int` | `expected_terms_version: int` |
| `expected_terms_fingerprint` | `str` | `expected_terms_fingerprint: str = Field(min_length=64, max_length=64)` |
| `command_key` | `str` | `command_key: str = Field(min_length=16, max_length=100)` |
| `source` | `Literal['EMAIL', 'PHONE', 'DOCUMENT']` | `source: Literal['EMAIL', 'PHONE', 'DOCUMENT']` |
| `reference` | `str` | `reference: str = Field(min_length=3, max_length=500)` |
| `bank_contact` | `str` | `bank_contact: str = Field(min_length=3, max_length=200)` |

## TreatmentConfirmation

Source : `backend/app/services/rfq_execution.py:34`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `expected_snapshot_hash` | `str` | `expected_snapshot_hash: str = Field(min_length=64, max_length=64)` |
| `execution_reference` | `str` | `execution_reference: str = Field(min_length=3, max_length=100)` |
| `acceptance_received_at` | `datetime` | `acceptance_received_at: datetime` |
| `acceptance_evidence` | `str` | `acceptance_evidence: str = Field(min_length=3, max_length=1000)` |
| `confirmed_at` | `datetime` | `confirmed_at: datetime` |
| `source` | `Literal['BANK_CONFIRMATION', 'PHONE_DECLARATION']` | `source: Literal['BANK_CONFIRMATION', 'PHONE_DECLARATION']` |
| `evidence` | `str` | `evidence: str = Field(min_length=3, max_length=1000)` |
| `bank_contact` | `str` | `bank_contact: str = Field(min_length=3, max_length=200)` |

## PolicyPut

Source : `backend/app/services/rfq_publication.py:25`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `expected_version` | `int` | `expected_version: int = Field(ge=0)` |
| `second_validation_required` | `bool` | `second_validation_required: bool` |
| `max_calculation_age_minutes` | `int` | `max_calculation_age_minutes: int = Field(ge=1, le=10080)` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=500)` |

## QuoteCondition

Source : `backend/app/services/rfq_publication.py:33`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `code` | `Literal['DOCUMENTATION', 'CREDIT_APPROVAL', 'OTHER']` | `code: Literal['DOCUMENTATION', 'CREDIT_APPROVAL', 'OTHER']` |
| `description` | `str` | `description: str = Field(min_length=3, max_length=500)` |

## DraftPut

Source : `backend/app/services/rfq_publication.py:39`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid', allow_inf_nan=False)`

| Champ | Type | Définition |
|---|---|---|
| `expected_revision` | `int` | `expected_revision: int = Field(ge=0)` |
| `calculation_id` | `int` | `calculation_id: int` |
| `price` | `float` | `price: float = Field(gt=0, le=1000)` |
| `firmness` | `Literal['INDICATIVE', 'FIRM']` | `firmness: Literal['INDICATIVE', 'FIRM']` |
| `valid_until` | `datetime` | `valid_until: datetime` |
| `conditions_type` | `Literal['NONE', 'CONDITIONAL']` | `conditions_type: Literal['NONE', 'CONDITIONAL']` |
| `conditions` | `list[QuoteCondition]` | `conditions: list[QuoteCondition] = Field(default_factory=list, max_length=10)` |
| `issuer_name` | `str` | `issuer_name: str = Field(default='', max_length=200)` |
| `guarantor_name` | `str` | `guarantor_name: str = Field(default='', max_length=200)` |
| `documentation_reference` | `str` | `documentation_reference: str = Field(default='', max_length=1000)` |
| `comment` | `str` | `comment: str = Field(default='', max_length=1000)` |

Méthodes/validators : `explicit_conditions:54`

## Decision

Source : `backend/app/services/rfq_publication.py:62`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `expected_revision` | `int` | `expected_revision: int = Field(ge=1)` |
| `expected_payload_hash` | `str` | `expected_payload_hash: str = Field(min_length=64, max_length=64)` |

## RefreshCommand

Source : `backend/app/services/rfq_reconciliation.py:24`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `command_key` | `str` | `command_key: str = Field(min_length=16, max_length=100)` |

## BookingFact

Source : `backend/app/services/rfq_reconciliation.py:29`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `side` | `Literal['BUY', 'SELL']` | `side: Literal['BUY', 'SELL']` |
| `nominal` | `float` | `nominal: float = Field(gt=0, allow_inf_nan=False)` |
| `currency` | `str` | `currency: str = Field(min_length=3, max_length=3)` |
| `price` | `float` | `price: float = Field(allow_inf_nan=False)` |
| `terms_fingerprint` | `str` | `terms_fingerprint: str = Field(min_length=64, max_length=64)` |
| `trade_date` | `str` | `trade_date: str` |
| `strike_date` | `str` | `strike_date: str` |
| `value_date` | `str` | `value_date: str` |
| `maturity_date` | `str` | `maturity_date: str` |
| `payment_date` | `str` | `payment_date: str` |
| `documentation_reference` | `str` | `documentation_reference: str` |
| `transaction_format` | `str` | `transaction_format: str` |
| `instrument_family` | `str` | `instrument_family: str` |
| `payoff_family` | `str` | `payoff_family: str` |
| `legal_mapping_matches` | `bool` | `legal_mapping_matches: bool = Field(strict=True)` |

## WireStatement

Source : `backend/app/services/rfq_reconciliation.py:48`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `format_version` | `Literal[1]` | `format_version: Literal[1]` |
| `execution_id` | `UUID` | `execution_id: UUID` |
| `request_hash` | `str` | `request_hash: str = Field(min_length=64, max_length=64)` |
| `role` | `Literal['REQUESTER', 'BANK']` | `role: Literal['REQUESTER', 'BANK']` |
| `version` | `int` | `version: int = Field(gt=0, strict=True)` |
| `execution_state` | `Literal['CONFIRMED', 'REJECTED']` | `execution_state: Literal['CONFIRMED', 'REJECTED']` |
| `decision_hash` | `str` | `decision_hash: str = Field(min_length=64, max_length=64)` |
| `observed_at` | `datetime` | `observed_at: datetime` |
| `booking` | `BookingFact \| None` | `booking: BookingFact \| None` |
| `request_reply` | `bool` | `request_reply: bool = Field(strict=True)` |

## SharedContact

Source : `backend/app/services/rfq_relationships.py:24`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `name` | `str` | `name: str = Field(min_length=1, max_length=150)` |
| `email` | `str` | `email: str = Field(default='', max_length=254)` |

Méthodes/validators : `clean:30`

## RelationshipTerms

Source : `backend/app/services/rfq_relationships.py:37`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid', allow_inf_nan=False)`

| Champ | Type | Définition |
|---|---|---|
| `formats` | `list[str]` | `formats: list[str] = Field(min_length=1, max_length=30)` |
| `instruments` | `list[str]` | `instruments: list[str] = Field(min_length=1, max_length=30)` |
| `payoff_families` | `list[str]` | `payoff_families: list[str] = Field(min_length=1, max_length=40)` |
| `currencies` | `list[str]` | `currencies: list[str] = Field(min_length=1, max_length=30)` |
| `min_notional` | `float \| None` | `min_notional: float \| None = Field(default=None, gt=0)` |
| `max_notional` | `float \| None` | `max_notional: float \| None = Field(default=None, gt=0)` |
| `effective_date` | `date` | `effective_date: date` |
| `expiry_date` | `date \| None` | `expiry_date: date \| None = None` |
| `solicitation_allowed` | `bool` | `solicitation_allowed: bool = False` |
| `indicative_allowed` | `bool` | `indicative_allowed: bool = True` |
| `to_trade_allowed` | `bool` | `to_trade_allowed: bool = False` |
| `treatment_allowed` | `bool` | `treatment_allowed: bool = False` |
| `documentation_reference` | `str` | `documentation_reference: str = Field(default='', max_length=1000)` |
| `policy` | `Literal['RFQ_V1']` | `policy: Literal['RFQ_V1'] = 'RFQ_V1'` |

Méthodes/validators : `perimeter:55`

## RelationshipConfiguration

Source : `backend/app/services/rfq_relationships.py:78`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `receiver_desk_id` | `int` | `receiver_desk_id: int` |
| `terms` | `RelationshipTerms` | `terms: RelationshipTerms` |
| `counterparty_id` | `int` | `counterparty_id: int` |
| `trading_relationship_id` | `int \| None` | `trading_relationship_id: int \| None = None` |
| `contacts` | `list[SharedContact]` | `contacts: list[SharedContact] = Field(default_factory=list, max_length=20)` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=500)` |

## RelationshipDecision

Source : `backend/app/services/rfq_relationships.py:98`. Bases : `BaseModel`.

- `model_config = ConfigDict(extra='forbid')`

| Champ | Type | Définition |
|---|---|---|
| `expected_version` | `int` | `expected_version: int = Field(gt=0)` |
| `reason` | `str` | `reason: str = Field(min_length=3, max_length=500)` |

## RfqPricingInput

Source : `backend/app/services/rfq_state.py:50`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `expected_terms_version` | `int` | `expected_terms_version: int = Field(gt=0)` |
| `valuation_date` | `Optional[date]` | `valuation_date: Optional[date] = None` |
| `context` | `Optional[dict]` | `context: Optional[dict] = None` |

## UatGenerationRequest

Source : `backend/app/services/uat_generation.py:134`. Bases : `BaseModel`.

| Champ | Type | Définition |
|---|---|---|
| `target_user_id` | `int` | `target_user_id: int` |
| `mode` | `Literal['RFQ_ONLY', 'FULL_CHAIN', 'PRICER_RFQ_CHAIN', 'SAVED_PRODUCT_RFQ_CHAIN', 'BOOKED_ONLY']` | `mode: Literal['RFQ_ONLY', 'FULL_CHAIN', 'PRICER_RFQ_CHAIN', 'SAVED_PRODUCT_RFQ_CHAIN', 'BOOKED_ONLY'] = 'FULL_CHAIN'` |
| `count` | `int` | `count: int = Field(default=5, ge=1, le=100)` |
| `seed` | `int` | `seed: int = Field(default=42, ge=0, le=2147483647)` |
| `label` | `str` | `label: str = Field(default='', max_length=120)` |
| `product_types` | `list[str]` | `product_types: list[str] = Field(default_factory=lambda: list(PRODUCTS))` |
| `underlying_tickers` | `list[str]` | `underlying_tickers: list[str] = Field(default_factory=lambda: [item['ticker'] for item in UNDERLYINGS])` |
| `min_underlyings` | `int` | `min_underlyings: int = Field(default=1, ge=1, le=len(UNDERLYINGS))` |
| `max_underlyings` | `int` | `max_underlyings: int = Field(default=2, ge=1, le=len(UNDERLYINGS))` |
| `maturity_min_years` | `float` | `maturity_min_years: float = Field(default=1.0, ge=0.25, le=10.0)` |
| `maturity_max_years` | `float` | `maturity_max_years: float = Field(default=5.0, ge=0.25, le=10.0)` |
| `nominal_min` | `float` | `nominal_min: float = Field(default=100000.0, gt=0, le=100000000.0)` |
| `nominal_max` | `float` | `nominal_max: float = Field(default=2000000.0, gt=0, le=100000000.0)` |
| `currencies` | `list[str]` | `currencies: list[str] = Field(default_factory=lambda: ['EUR'])` |
| `fixing_policy` | `Literal['AUTO_YAHOO']` | `fixing_policy: Literal['AUTO_YAHOO'] = 'AUTO_YAHOO'` |
| `quotes_per_rfq` | `int` | `quotes_per_rfq: int = Field(default=2, ge=1, le=5)` |
| `provider_ids` | `list[int] \| None` | `provider_ids: list[int] \| None = None` |
| `rfq_profile` | `Literal['EXECUTABLE', 'CONTROL_MIX']` | `rfq_profile: Literal['EXECUTABLE', 'CONTROL_MIX'] = 'EXECUTABLE'` |
| `product_calculations` | `int` | `product_calculations: int = Field(default=1, ge=1, le=5)` |
| `mtm_history_count` | `int` | `mtm_history_count: int = Field(default=0, ge=0, le=5)` |
| `compute_greeks` | `bool` | `compute_greeks: bool = False` |
| `lifecycle_profile` | `Literal['CURRENT_ACTIVE', 'FORWARD_START', 'ACTIVE_1Y_PENDING', 'ACTIVE_2Y_OFFICIAL', 'MATURED_PENDING', 'CALLED', 'MATURED_FINAL', 'MATURED_KI', 'COMPLETE_MIX']` | `lifecycle_profile: Literal['CURRENT_ACTIVE', 'FORWARD_START', 'ACTIVE_1Y_PENDING', 'ACTIVE_2Y_OFFICIAL', 'MATURED_PENDING', 'CALLED', 'MATURED_FINAL', 'MATURED_KI', 'COMPLETE_MIX'] = 'CURRENT_ACTIVE'` |

