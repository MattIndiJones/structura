// Généré par scripts/generate_api_client.py depuis le schéma OpenAPI du serveur
// (P1-11). Ne pas modifier à la main : changer le contrat de réponse de la
// route (backend/app/api/responses.py), puis relancer le script. Un test
// backend échoue tant que ce fichier ne correspond plus au schéma.
import { apiFetch, apiErrorMessage } from '../utils/api.js'

/** Refus du serveur : le message lisible, le statut HTTP et le corps reçu. */
export class ApiError extends Error {
  constructor(message, status, body) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function call(method, path, { query, body } = {}) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query || {})) {
    if (value !== undefined && value !== null) params.append(key, String(value))
  }
  const url = params.toString() ? `${path}?${params}` : path
  const init = { method }
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body)
  }
  const res = await apiFetch(url, init)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(apiErrorMessage(data, `Erreur ${res.status}`), res.status, data)
  return data
}

/**
 * @typedef {Object} AlertList
 * @property {number} unread
 * @property {Array<AlertRow>} alerts
 */

/**
 * @typedef {Object} AlertRow
 * @property {number} id
 * @property {(number|null)} [deal_id]
 * @property {string} deal_reference
 * @property {string} kind
 * @property {string} message
 * @property {boolean} read
 * @property {string} created_at
 */

/**
 * @typedef {Object} AmcStudySummary
 * @property {number} id
 * @property {string} isin
 * @property {string} product_name
 * @property {string} label
 * @property {string} folder
 * @property {string} created_at
 * @property {string} updated_at
 */

/**
 * @typedef {Object} AthenaBarrierCheck
 * @property {'call'|'coupon'|'capital'} kind
 * @property {string} observation_date
 * @property {number} fixing
 * @property {number} initial_fixing
 * @property {number} ratio
 * @property {number} threshold
 * @property {boolean} condition_met
 */

/**
 * @typedef {Object} AthenaBatchTicket
 * @property {number} id
 * @property {'queued'|'running'|'completed'|'completed_with_failures'|'failed'|'cancelled'} status
 * @property {number} total_jobs
 * @property {string} request_key
 * @property {string} results_path
 */

/**
 * @typedef {Object} AthenaCouponClaim
 * @property {string} event_id
 * @property {string} observed_date
 * @property {string} payment_date
 * @property {number} amount
 * @property {'coupon'} kind
 * @property {(number|null)} [memory_periods]
 */

/**
 * @typedef {Object} AthenaFixedCoupon
 * @property {'fixed'} mode
 * @property {number} fixed_coupon
 */

/**
 * @typedef {Object} AthenaFixedQuote
 * @property {'fixed'} mode
 */

/**
 * @typedef {Object} AthenaFixing
 * @property {string} day
 * @property {number} spot
 * @property {string} reference
 */

/**
 * @typedef {Object} AthenaIssueBatch
 * @property {string} request_key
 * @property {string} [label]
 * @property {number} [max_workers]
 * @property {Array<AthenaIssueRequest>} jobs
 */

/**
 * @typedef {Object} AthenaIssueRequest
 * @property {string} note_id
 * @property {AthenaTerms} terms
 * @property {AthenaMarket} market
 * @property {AthenaPricing} pricing
 * @property {((AthenaFixedCoupon|AthenaSolvedCoupon)|null)} [coupon]
 * @property {((AthenaFixedQuote|AthenaSolvedQuote)|null)} [quote]
 * @property {number} initial_fixing
 * @property {string} initial_fixing_reference
 */

/**
 * @typedef {Object} AthenaLifecycleRequest
 * @property {AthenaVintage} vintage
 * @property {string} as_of
 * @property {Array<AthenaFixing>} fixings
 */

/**
 * @typedef {Object} AthenaLifecycleResult
 * @property {string} day
 * @property {string} note_id
 * @property {string} terms_reference
 * @property {string} receipt_id
 * @property {boolean} terminated
 * @property {'active'|'called'|'matured'} status
 * @property {(AthenaRedemption|null)} redemption
 * @property {(Array<AthenaCouponClaim>|null)} [coupon_claims]
 * @property {(Array<AthenaParticipationClaim>|null)} [participation_claims]
 * @property {(AthenaOptionSettlement|null)} [option_settlement]
 * @property {Array<AthenaBarrierCheck>} barriers
 * @property {Object<string, string>} fixing_references
 */

/**
 * @typedef {Object} AthenaMarkBatch
 * @property {string} request_key
 * @property {string} [label]
 * @property {number} [max_workers]
 * @property {Array<AthenaMarkRequest>} jobs
 */

/**
 * @typedef {Object} AthenaMarkRequest
 * @property {AthenaVintage} vintage
 * @property {AthenaMarket} market
 * @property {AthenaPricing} pricing
 * @property {Array<AthenaFixing>} fixings
 */

/**
 * @typedef {Object} AthenaMarket
 * @property {string} as_of
 * @property {string} reference
 * @property {number} spot
 * @property {number} rate
 * @property {number} volatility
 * @property {number} dividend_yield
 * @property {number} funding_spread
 * @property {(Array<Array<*>>|null)} [dividend_curve]
 * @property {(Array<Array<*>>|null)} [yield_curve]
 * @property {(Array<Array<*>>|null)} [funding_curve]
 * @property {(VolatilitySurfaceParams|null)} [vol_surface]
 */

/**
 * @typedef {Object} AthenaObservation
 * @property {string} observation_date
 * @property {string} payment_date
 */

/**
 * @typedef {Object} AthenaOptionSettlement
 * @property {string} event_id
 * @property {string} observed_date
 * @property {string} payment_date
 * @property {number} amount
 * @property {'option_payoff'} kind
 */

/**
 * @typedef {Object} AthenaParticipationClaim
 * @property {string} event_id
 * @property {string} observed_date
 * @property {string} payment_date
 * @property {number} amount
 * @property {'participation'} kind
 */

/**
 * @typedef {Object} AthenaPayoffCapability
 * @property {string} id
 * @property {string} version
 * @property {Array<string>} issue_models
 * @property {Array<string>} mtm_models
 */

/**
 * @typedef {Object} AthenaPricing
 * @property {'constant'|'heston'|'sabr'|'localvol'} [model]
 * @property {number} [n_paths]
 * @property {number} [seed]
 * @property {52|104|208} [steps_per_year]
 * @property {boolean} [antithetic]
 * @property {(number|null)} [v0]
 * @property {(number|null)} [kappa]
 * @property {(number|null)} [theta]
 * @property {(number|null)} [xi]
 * @property {(number|null)} [rho_h]
 * @property {(number|null)} [alpha]
 * @property {(number|null)} [beta]
 * @property {(number|null)} [rho]
 * @property {(number|null)} [nu]
 * @property {(number|null)} [skew]
 * @property {(number|null)} [curvature]
 */

/**
 * @typedef {Object} AthenaPricingCatalogue
 * @property {'athena-pricing-v1'} [version]
 * @property {string} default_model
 * @property {Array<AthenaPricingModel>} models
 * @property {Array<AthenaPayoffCapability>} payoffs
 */

/**
 * @typedef {Object} AthenaPricingField
 * @property {string} name
 * @property {string} label
 * @property {string} help
 * @property {'integer'|'boolean'|'number'} kind
 * @property {(number|boolean)} default
 * @property {(Array<number>|null)} [choices]
 * @property {(number|null)} [minimum]
 * @property {(number|null)} [maximum]
 * @property {(number|null)} [scale]
 */

/**
 * @typedef {Object} AthenaPricingModel
 * @property {string} id
 * @property {string} label
 * @property {Array<AthenaPricingField>} fields
 * @property {Array<AthenaPricingField>} market_fields
 * @property {Array<'dividend_curve'|'yield_curve'|'funding_curve'>} market_curves
 * @property {boolean} [supports_vol_surface]
 * @property {(number|null)} [reference_volatility]
 */

/**
 * @typedef {Object} AthenaRealizedVolatility
 * @property {'RMS_LOG_RETURNS'} [method]
 * @property {252} [window_sessions]
 * @property {252} [annualization]
 * @property {Array<AthenaVolatilityObservation>} observations
 */

/**
 * @typedef {Object} AthenaRealizedVolatilityRequest
 * @property {Array<AthenaVolatilityClose>} closes
 * @property {Array<string>} sessions
 */

/**
 * @typedef {Object} AthenaRedemption
 * @property {string} event_id
 * @property {string} observed_date
 * @property {string} payment_date
 * @property {number} amount
 * @property {('redemption'|null)} [kind]
 */

/**
 * @typedef {Object} AthenaSolvedCoupon
 * @property {'solve_to_target'} mode
 * @property {number} target_price
 * @property {number} min_coupon
 * @property {number} max_coupon
 * @property {number} [price_tolerance]
 */

/**
 * @typedef {Object} AthenaSolvedQuote
 * @property {'solve_to_target'} mode
 * @property {'participation'|'redemption_cap'|'single_coupon'} quantity
 * @property {number} target_price
 * @property {number} minimum
 * @property {number} maximum
 * @property {number} [price_tolerance]
 */

/**
 * @typedef {Object} AthenaTerms
 * @property {string} strike_date
 * @property {Array<AthenaObservation>} observations
 * @property {string} calendar_reference
 * @property {1|3|6|12} [observation_months]
 * @property {number} [call_barrier]
 * @property {(Array<number>|null)} [call_barriers]
 * @property {number} [protection_barrier]
 * @property {(number|null)} [coupon_barrier]
 * @property {(boolean|null)} [coupon_memory]
 * @property {(boolean|null)} [reverse_convertible]
 * @property {(number|null)} [maturity_years]
 * @property {(number|null)} [maturity_months]
 * @property {((CapitalGuaranteedPayoff|BoosterPayoff|AutocallGearPutPayoff|EuropeanPutPayoff|EuropeanCallPayoff)|null)} [payoff]
 * @property {number} [settlement_lag]
 * @property {'SX5E'} [underlying]
 * @property {'EUR'} [currency]
 */

/**
 * @typedef {Object} AthenaVintage
 * @property {string} note_id
 * @property {AthenaTerms} terms
 * @property {number} initial_fixing
 * @property {string} initial_fixing_reference
 * @property {(number|null)} [annual_coupon]
 */

/**
 * @typedef {Object} AthenaVolatilityClose
 * @property {string} day
 * @property {number} close
 */

/**
 * @typedef {Object} AthenaVolatilityObservation
 * @property {string} day
 * @property {number} volatility
 */

/**
 * @typedef {Object} AutocallGearPutPayoff
 * @property {'autocall-gear-put-sx5e'} id
 * @property {number} put_strike
 * @property {number} gearing
 * @property {(number|null)} [single_coupon]
 */

/**
 * Underlying comparator — backtest the same script against a pool of
 * candidate underlyings, one at a time, then (if basket_size > 1) against
 * combinations drawn from the best `shortlist_n` single performers only —
 * testing every C(N, basket_size) combination is combinatorially
 * infeasible for any non-trivial candidate pool.
 * @typedef {Object} BacktestCompareRequest
 * @property {string} script
 * @property {Array<UnderlyingParams>} candidates
 * @property {number} [r]
 * @property {number} [T]
 * @property {string} [model]
 * @property {Object} [user_params]
 * @property {Object} [constats]
 * @property {(string|null)} [anchor]
 * @property {number} [basket_size]
 * @property {number} [shortlist_n]
 * @property {(string|null)} [start_date]
 * @property {(string|null)} [end_date]
 * @property {string} [history_mode]
 * @property {number} [max_delay_days]
 * @property {(string|null)} [strike_date]
 * @property {(string|null)} [value_date]
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [settlement_ccy]
 * @property {number} [freq]
 * @property {number} [invest_pct]
 * @property {number} [rf_rate]
 */

/**
 * @typedef {Object} BacktestRequest
 * @property {52|104|208} [steps_per_year]
 * @property {string} script
 * @property {Array<UnderlyingParams>} underlyings
 * @property {Array<Array<number>>} corr_matrix
 * @property {number} [r]
 * @property {number} [T]
 * @property {number} [seed]
 * @property {boolean} [antithetic]
 * @property {string} [model]
 * @property {Object} [user_params]
 * @property {Array<Array<number>>} [yield_curve]
 * @property {number} [sigma_r]
 * @property {number} [a_r]
 * @property {string} [barrier_monitoring]
 * @property {Object} [constats]
 * @property {(Object|null)} [frozen_schedule]
 * @property {(string|null)} [anchor]
 * @property {(string|null)} [settlement_ccy]
 * @property {(VariantOverrides|null)} [variant]
 * @property {(string|null)} [strike_date]
 * @property {(string|null)} [value_date]
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [valuation_date]
 * @property {(string|null)} [maturity_date]
 * @property {Array<Array<number>>} [funding_curve]
 * @property {number} [funding_spread]
 * @property {(string|null)} [start_date]
 * @property {(string|null)} [end_date]
 * @property {string} [history_mode]
 * @property {number} [max_delay_days]
 * @property {number} [freq]
 * @property {number} [invest_pct]
 * @property {number} [rf_rate]
 */

/**
 * @typedef {Object} BoosterPayoff
 * @property {'booster-sx5e'} id
 * @property {(number|null)} [participation]
 * @property {(number|null)} [redemption_cap]
 */

/**
 * Resolve one date against a settlement calendar.
 *
 * Serves the two things a UI needs and cannot compute itself: moving a typed
 * date onto a business day according to a chosen convention, and proposing a
 * date N business days after another one (a settlement lag).
 * @typedef {Object} BusinessDayRequest
 * @property {(Array<string>|null)} [observation_calendars]
 * @property {(string|null)} [observation_join]
 * @property {(Array<string>|null)} [settlement_calendars]
 * @property {(string|null)} [settlement_join]
 * @property {string} date
 * @property {string} [currency]
 * @property {string} [convention]
 * @property {number} [business_days]
 * @property {number} [settlement_lag]
 */

/**
 * @typedef {Object} CalendarCatalog
 * @property {Array<string>} codes
 * @property {Array<string>} observation_codes
 * @property {Array<string>} settlement_codes
 * @property {Array<string>} joins
 */

/**
 * @typedef {Object} CalibrationRequest
 * @property {VolatilitySurfaceParams} surface
 * @property {string} model
 * @property {number} horizon
 * @property {number} [rate]
 * @property {number} [dividend]
 * @property {(HestonFit|null)} [heston_fit]
 */

/**
 * @typedef {Object} CapitalGuaranteedPayoff
 * @property {'capital-guaranteed-sx5e'} id
 * @property {number} participation_strike
 * @property {(number|null)} [participation]
 */

/**
 * @typedef {Object} CurrentUser
 * @property {boolean} admin_workbench
 * @property {boolean} development_admin_enabled
 * @property {(string|null)} [platform_url]
 * @property {number} id
 * @property {string} username
 * @property {string} email
 * @property {boolean} password_change_required
 * @property {string} role
 * @property {(number|null)} [entity_id]
 * @property {string} profile
 * @property {Array<string>} capabilities
 * @property {(Object|null)} [installation]
 * @property {boolean} developer_access
 * @property {(Object|null)} [developer_origin]
 * @property {boolean} amendment_four_eyes
 * @property {boolean} read_only
 * @property {(Object|null)} [consultation]
 */

/**
 * @typedef {Object} DealDetail
 * @property {number} id
 * @property {(number|null)} [product_id]
 * @property {(number|null)} [product_terms_version]
 * @property {string} reference
 * @property {(number|null)} [entity_id]
 * @property {number} user_id
 * @property {(number|null)} [counterparty_id]
 * @property {(Object|null)} [legal_identity_exception]
 * @property {(number|null)} [ccr_netting_set_id]
 * @property {(number|null)} [uat_batch_id]
 * @property {(number|null)} [indicative_id]
 * @property {(number|null)} [rfq_id]
 * @property {(Object|null)} [rfq_provenance]
 * @property {(number|null)} [client_id]
 * @property {string} market_data_provider
 * @property {(number|null)} [opportunity_id]
 * @property {(number|null)} [primary_affiliation_id]
 * @property {(number|null)} [mandate_id]
 * @property {(Object|null)} [client_provenance]
 * @property {(Object|null)} [client_attribution_current]
 * @property {(string|null)} [transaction_format]
 * @property {(string|null)} [instrument_family]
 * @property {(string|null)} [payoff_family]
 * @property {(string|null)} [payoff_description]
 * @property {(string|null)} [documentation_reference]
 * @property {(string|null)} [commercial_reason]
 * @property {Array<number>} portfolio_ids
 * @property {(number|null)} [portfolio_id]
 * @property {string} sens
 * @property {string} contrepartie
 * @property {string} devise
 * @property {(string|null)} [product_type]
 * @property {(string|null)} [fixing_policy]
 * @property {number} nominal
 * @property {number} fair_value
 * @property {number} price_traded
 * @property {number} margin
 * @property {(string|null)} [trade_date]
 * @property {(string|null)} [strike_date]
 * @property {(string|null)} [value_date]
 * @property {(string|null)} [maturity_date]
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [risk_terminal_date]
 * @property {number} T
 * @property {(number|null)} [realized_payout]
 * @property {(number|null)} [settlement_amount]
 * @property {(string|null)} [settlement_date]
 * @property {(string|null)} [resolution_outcome]
 * @property {Array<Object>} underlyings
 * @property {Object} market_snapshot
 * @property {Object} greeks
 * @property {(string|null)} [greeks_computed_at]
 * @property {(number|null)} [latest_valuation_run_id]
 * @property {string} status
 * @property {(number|null)} [contract_version]
 * @property {(number|null)} [script_id]
 * @property {string} script_snapshot
 * @property {string} created_at
 * @property {string} updated_at
 * @property {Array<DealEventRow>} events
 * @property {(Object|null)} [schedule]
 * @property {(Object|null)} [frozen_schedule]
 * @property {'FROZEN'|'UNAVAILABLE'} calendar_status
 * @property {*} [terms]
 * @property {*} [flags]
 * @property {Array<Object>} lifecycle_proposals
 * @property {Array<Object>} amendment_requests
 */

/**
 * api/deals/serializers._event_row, with the event's fixing versions.
 * @typedef {Object} DealEventRow
 * @property {number} id
 * @property {number} deal_id
 * @property {number} event_index
 * @property {string} event_date
 * @property {number} t_years
 * @property {(number|null)} [parent_event_id]
 * @property {(string|null)} [reduction]
 * @property {Object} spots
 * @property {Object} indicative_spots
 * @property {string} source
 * @property {string} status
 * @property {string} fixing_status
 * @property {string} data_category
 * @property {(number|null)} [current_fixing_version_id]
 * @property {(number|null)} [fixing_version]
 * @property {(number|null)} [fixing_entered_by]
 * @property {(string|null)} [fixing_entered_at]
 * @property {(string|null)} [fixing_provider]
 * @property {(string|null)} [fixing_source_type]
 * @property {(string|null)} [fixing_external_reference]
 * @property {(string|null)} [fixing_observed_at]
 * @property {(string|null)} [fixing_venue]
 * @property {(string|null)} [fixing_calendar]
 * @property {(string|null)} [fixing_timezone]
 * @property {(string|null)} [fixing_evidence_sha256]
 * @property {(string|null)} [fixing_record_sha256]
 * @property {(string|null)} [fixing_reason]
 * @property {(number|null)} [validated_by]
 * @property {(string|null)} [validated_at]
 * @property {(string|null)} [applied_at]
 * @property {string} label
 * @property {Array<Object>} [fixing_versions]
 */

/**
 * Residual MtM of a booked deal (core/deal_valuation.mtm_core), staged as
 * a valuation run. Its market and provenance blocks follow the engine.
 * @typedef {Object} DealMtm
 * @property {(number|null)} [mtm]
 * @property {(Array<number>|null)} [ic95]
 * @property {(string|null)} [valuation_date]
 * @property {(Object|null)} [market_used]
 * @property {(boolean|null)} [resolved_pending]
 * @property {(string|null)} [message]
 */

/**
 * api/deals/serializers._deal_row.
 * @typedef {Object} DealRow
 * @property {number} id
 * @property {(number|null)} [product_id]
 * @property {(number|null)} [product_terms_version]
 * @property {string} reference
 * @property {(number|null)} [entity_id]
 * @property {number} user_id
 * @property {(number|null)} [counterparty_id]
 * @property {(Object|null)} [legal_identity_exception]
 * @property {(number|null)} [ccr_netting_set_id]
 * @property {(number|null)} [uat_batch_id]
 * @property {(number|null)} [indicative_id]
 * @property {(number|null)} [rfq_id]
 * @property {(Object|null)} [rfq_provenance]
 * @property {(number|null)} [client_id]
 * @property {string} market_data_provider
 * @property {(number|null)} [opportunity_id]
 * @property {(number|null)} [primary_affiliation_id]
 * @property {(number|null)} [mandate_id]
 * @property {(Object|null)} [client_provenance]
 * @property {(Object|null)} [client_attribution_current]
 * @property {(string|null)} [transaction_format]
 * @property {(string|null)} [instrument_family]
 * @property {(string|null)} [payoff_family]
 * @property {(string|null)} [payoff_description]
 * @property {(string|null)} [documentation_reference]
 * @property {(string|null)} [commercial_reason]
 * @property {Array<number>} portfolio_ids
 * @property {(number|null)} [portfolio_id]
 * @property {string} sens
 * @property {string} contrepartie
 * @property {string} devise
 * @property {(string|null)} [product_type]
 * @property {(string|null)} [fixing_policy]
 * @property {number} nominal
 * @property {number} fair_value
 * @property {number} price_traded
 * @property {number} margin
 * @property {(string|null)} [trade_date]
 * @property {(string|null)} [strike_date]
 * @property {(string|null)} [value_date]
 * @property {(string|null)} [maturity_date]
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [risk_terminal_date]
 * @property {number} T
 * @property {(number|null)} [realized_payout]
 * @property {(number|null)} [settlement_amount]
 * @property {(string|null)} [settlement_date]
 * @property {(string|null)} [resolution_outcome]
 * @property {Array<Object>} underlyings
 * @property {Object} market_snapshot
 * @property {Object} greeks
 * @property {(string|null)} [greeks_computed_at]
 * @property {(number|null)} [latest_valuation_run_id]
 * @property {string} status
 * @property {(number|null)} [contract_version]
 * @property {(number|null)} [script_id]
 * @property {string} script_snapshot
 * @property {string} created_at
 * @property {string} updated_at
 */

/**
 * @typedef {Object} EligibleCounterparty
 * @property {number} id
 * @property {string} name
 * @property {(string|null)} [country]
 */

/**
 * @typedef {Object} EuropeanCallPayoff
 * @property {number} strike_ratio
 * @property {'european-call-sx5e'} id
 */

/**
 * @typedef {Object} EuropeanPutPayoff
 * @property {number} strike_ratio
 * @property {'european-put-sx5e'} id
 */

/**
 * @typedef {Object} GeneratedSchedule
 * @property {boolean} first_is_observation
 * @property {Array<string>} main_dates
 * @property {Array<string>} dates
 * @property {Array<string>} raw_dates
 * @property {Array<string>} payment_dates
 * @property {Array<number>} year_fractions
 */

/**
 * 2D price heatmap over two script PARAM ranges (stored units).
 * @typedef {Object} GridRequest
 * @property {52|104|208} [steps_per_year]
 * @property {string} script
 * @property {Array<UnderlyingParams>} underlyings
 * @property {Array<Array<number>>} corr_matrix
 * @property {number} [r]
 * @property {number} [T]
 * @property {number} [seed]
 * @property {boolean} [antithetic]
 * @property {string} [model]
 * @property {Object} [user_params]
 * @property {Array<Array<number>>} [yield_curve]
 * @property {number} [sigma_r]
 * @property {number} [a_r]
 * @property {string} [barrier_monitoring]
 * @property {Object} [constats]
 * @property {(Object|null)} [frozen_schedule]
 * @property {(string|null)} [anchor]
 * @property {(string|null)} [settlement_ccy]
 * @property {(VariantOverrides|null)} [variant]
 * @property {(string|null)} [strike_date]
 * @property {(string|null)} [value_date]
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [valuation_date]
 * @property {(string|null)} [maturity_date]
 * @property {Array<Array<number>>} [funding_curve]
 * @property {number} [funding_spread]
 * @property {string} param_x
 * @property {number} x_min
 * @property {number} x_max
 * @property {number} [x_steps]
 * @property {string} param_y
 * @property {number} y_min
 * @property {number} y_max
 * @property {number} [y_steps]
 * @property {number} [N]
 */

/**
 * @typedef {Object} HestonFit
 * @property {(number|null)} [vanilla_limit_bp]
 * @property {('atm'|'atm_digital'|'atm_smile'|null)} [mode]
 */

/**
 * Closes per ticker on common dates, or an error. The provenance of the
 * history (provider, price type, storage, gaps) follows the source.
 * @typedef {Object} HistoricalPrices
 * @property {(Array<string>|null)} [dates]
 * @property {(Object<string, Array<(number|null)>>|null)} [prices]
 * @property {(string|null)} [error]
 */

/**
 * La même valorisation, mais à l'envers : on donne le prix, on cherche le
 * spread émetteur qui le reproduit.
 * @typedef {Object} ImpliedFundingRequest
 * @property {52|104|208} [steps_per_year]
 * @property {string} script
 * @property {Array<UnderlyingParams>} underlyings
 * @property {Array<Array<number>>} corr_matrix
 * @property {number} [r]
 * @property {number} [N]
 * @property {string} [model]
 * @property {Object} [user_params]
 * @property {Object} [constats]
 * @property {(Object|null)} [frozen_schedule]
 * @property {number} [seed]
 * @property {boolean} [antithetic]
 * @property {Array<Array<number>>} [yield_curve]
 * @property {Array<Array<number>>} [funding_curve]
 * @property {number} [funding_spread]
 * @property {number} [sigma_r]
 * @property {number} [a_r]
 * @property {string} [barrier_monitoring]
 * @property {boolean} [compute_greeks]
 * @property {Array<string>} [selected_greeks]
 * @property {string} strike_date
 * @property {string} value_date
 * @property {string} maturity_date
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [valuation_date]
 * @property {string} [settlement_ccy]
 * @property {Object<string, number>} [strike_levels]
 * @property {(VariantOverrides|null)} [variant]
 * @property {number} target_price
 * @property {number} [lo]
 * @property {number} [hi]
 * @property {number} [tol]
 * @property {number} [max_iter]
 */

/**
 * The replay of past closes finds the product already recalled.
 * @typedef {Object} InLifeEarlyRecall
 * @property {true} early_recall
 * @property {string} message
 * @property {(number|null)} [T_actual]
 * @property {string} valuation_date
 */

/**
 * api/inlife.price_in_life: the residual price and what produced it.
 * @typedef {Object} InLifePrice
 * @property {number} price
 * @property {Object} valuation_context
 * @property {(Object|null)} [frozen_calendar]
 * @property {number} T_elapsed
 * @property {number} steps_per_year
 * @property {(Object|null)} [surface_context]
 * @property {(Object|null)} [lsv_calibration]
 * @property {*} [lsv_frozen_leverage]
 * @property {(Object|null)} [lsv_limits]
 * @property {(Object|null)} [time_axis]
 * @property {(string|null)} [barrier_monitoring]
 * @property {(string|null)} [barrier_monitoring_note]
 * @property {*} [barrier_monitoring_details]
 * @property {(string|null)} [grid_notice]
 * @property {*} [local_vol_wings]
 * @property {Array<number>} ic95
 * @property {number} median
 * @property {number} var5
 * @property {number} prob_gt100
 * @property {Array<number>} payoffs
 * @property {Object} calculation_budget
 * @property {number} elapsed_ms
 * @property {(Object|null)} [greeks]
 * @property {number} n_paths
 * @property {number} t_max_effective
 * @property {Object} flux_table
 * @property {(Object|null)} [schedule]
 * @property {(number|null)} [n_eff]
 * @property {(number|null)} [fugit]
 * @property {string} valuation_date
 * @property {boolean} in_life
 * @property {boolean} pre_strike
 * @property {*} [variant_state_check]
 * @property {Object} pricing_receipt
 * @property {Object} past
 */

/**
 * @typedef {Object} InLifePricingRequest
 * @property {52|104|208} [steps_per_year]
 * @property {string} script
 * @property {Array<UnderlyingParams>} underlyings
 * @property {Array<Array<number>>} corr_matrix
 * @property {number} [r]
 * @property {number} [N]
 * @property {string} [model]
 * @property {Object} [user_params]
 * @property {Object} [constats]
 * @property {(Object|null)} [frozen_schedule]
 * @property {number} [seed]
 * @property {boolean} [antithetic]
 * @property {Array<Array<number>>} [yield_curve]
 * @property {Array<Array<number>>} [funding_curve]
 * @property {number} [funding_spread]
 * @property {number} [sigma_r]
 * @property {number} [a_r]
 * @property {string} [barrier_monitoring]
 * @property {boolean} [compute_greeks]
 * @property {Array<string>} [selected_greeks]
 * @property {string} strike_date
 * @property {string} value_date
 * @property {string} maturity_date
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [valuation_date]
 * @property {string} [settlement_ccy]
 * @property {Object<string, number>} [strike_levels]
 * @property {(VariantOverrides|null)} [variant]
 */

/**
 * @typedef {Object} LeftWingAdjustment
 * @property {Object} surface
 * @property {(number|null)} [achieved]
 * @property {(string|null)} [reason]
 * @property {boolean} changed
 */

/**
 * @typedef {Object} LeftWingRequest
 * @property {VolatilitySurfaceParams} surface
 * @property {number} expiry
 * @property {number} strike
 * @property {number} target
 * @property {number} horizon
 * @property {number} rate
 * @property {number} dividend
 */

/**
 * @typedef {Object} LoginOptions
 * @property {boolean} admin_workbench
 * @property {boolean} development_admin_enabled
 * @property {(string|null)} [platform_url]
 * @property {boolean} registration_enabled
 */

/**
 * @typedef {Object} MtfComparisonRequest
 * @property {MtfRequest} a
 * @property {MtfRequest} b
 */

/**
 * Explication détaillée de quelques scénarios à UNE date de l'éventail MTF.
 *
 * n_outer / n_inner / n_dates / seed doivent reprendre ceux du run à expliquer :
 * ils fixent les tirages (le rang de la date indexe le RNG interne), donc c'est
 * ce qui garantit que le mark du panneau est exactement celui du graphique.
 * scenario_ids sont des indices dans les tableaux `pvs` / `alive` de la réponse
 * /api/mtf — le client sélectionne lui-même ses quantiles, ce qui évite de
 * recalculer tout l'éventail pour en expliquer cinq trajectoires.
 * @typedef {Object} MtfDrilldownRequest
 * @property {52|104|208} [steps_per_year]
 * @property {string} script
 * @property {Array<UnderlyingParams>} underlyings
 * @property {Array<Array<number>>} corr_matrix
 * @property {number} [r]
 * @property {number} [T]
 * @property {number} [seed]
 * @property {boolean} [antithetic]
 * @property {string} [model]
 * @property {Object} [user_params]
 * @property {Array<Array<number>>} [yield_curve]
 * @property {number} [sigma_r]
 * @property {number} [a_r]
 * @property {string} [barrier_monitoring]
 * @property {Object} [constats]
 * @property {(Object|null)} [frozen_schedule]
 * @property {(string|null)} [anchor]
 * @property {(string|null)} [settlement_ccy]
 * @property {(VariantOverrides|null)} [variant]
 * @property {(string|null)} [strike_date]
 * @property {(string|null)} [value_date]
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [valuation_date]
 * @property {(string|null)} [maturity_date]
 * @property {Array<Array<number>>} [funding_curve]
 * @property {number} [funding_spread]
 * @property {(Array<number>|null)} [mtm_dates]
 * @property {(string|null)} [context_fingerprint]
 * @property {(string|null)} [lsv_qualification]
 * @property {number} main_price
 * @property {(number|null)} [reference_paths]
 * @property {boolean} [gbm_atm_curve]
 * @property {boolean} [indicative_heston]
 * @property {number} t
 * @property {Array<number>} scenario_ids
 * @property {Array<string>} [labels]
 * @property {number} [n_outer]
 * @property {number} [n_inner]
 * @property {number} [n_dates]
 */

/**
 * Mark-to-Future — nested Monte Carlo. main_price is the t=0 fair price
 * (% of notional, from a prior /price call), used as the P(MTM >= P0) threshold.
 * @typedef {Object} MtfRequest
 * @property {52|104|208} [steps_per_year]
 * @property {string} script
 * @property {Array<UnderlyingParams>} underlyings
 * @property {Array<Array<number>>} corr_matrix
 * @property {number} [r]
 * @property {number} [T]
 * @property {number} [seed]
 * @property {boolean} [antithetic]
 * @property {string} [model]
 * @property {Object} [user_params]
 * @property {Array<Array<number>>} [yield_curve]
 * @property {number} [sigma_r]
 * @property {number} [a_r]
 * @property {string} [barrier_monitoring]
 * @property {Object} [constats]
 * @property {(Object|null)} [frozen_schedule]
 * @property {(string|null)} [anchor]
 * @property {(string|null)} [settlement_ccy]
 * @property {(VariantOverrides|null)} [variant]
 * @property {(string|null)} [strike_date]
 * @property {(string|null)} [value_date]
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [valuation_date]
 * @property {(string|null)} [maturity_date]
 * @property {Array<Array<number>>} [funding_curve]
 * @property {number} [funding_spread]
 * @property {(Array<number>|null)} [mtm_dates]
 * @property {number} main_price
 * @property {(number|null)} [reference_paths]
 * @property {boolean} [gbm_atm_curve]
 * @property {boolean} [indicative_heston]
 * @property {number} [n_outer]
 * @property {number} [n_inner]
 * @property {number} [n_dates]
 */

/**
 * Manual per-underlying override in display units.
 * @typedef {Object} MtmOverrideUL
 * @property {(number|null)} [sigma]
 * @property {(number|null)} [q]
 */

/**
 * @typedef {Object} MtmRequest
 * @property {(52|104|208|null)} [steps_per_year]
 * @property {'none'|'realized'} [recalibrate]
 * @property {(Object<string, MtmOverrideUL>|null)} [overrides]
 * @property {(number|null)} [r]
 * @property {number} [window_days]
 * @property {(string|null)} [valuation_date]
 * @property {(Array<Array<number>>|null)} [funding_curve]
 * @property {(number|null)} [funding_spread]
 * @property {(string|null)} [funding_source_reference]
 */

/**
 * @typedef {Object} ParseRequest
 * @property {string} script
 */

/**
 * @typedef {Object} ParseResponse
 * @property {boolean} ok
 * @property {(string|null)} [underlying]
 * @property {(string|null)} [initial_fixing]
 * @property {Array<Object>} params
 * @property {Array<Object>} [constats]
 * @property {number} events_count
 * @property {boolean} [has_stop]
 * @property {boolean} [has_maturity_event]
 * @property {Array<number>} [at_dates]
 * @property {Array<Object>} [monitors]
 * @property {(string|null)} [errors]
 */

/**
 * @typedef {Object} PathsRequest
 * @property {52|104|208} [steps_per_year]
 * @property {string} script
 * @property {Array<UnderlyingParams>} underlyings
 * @property {Array<Array<number>>} corr_matrix
 * @property {number} [r]
 * @property {number} [T]
 * @property {number} [seed]
 * @property {boolean} [antithetic]
 * @property {string} [model]
 * @property {Object} [user_params]
 * @property {Array<Array<number>>} [yield_curve]
 * @property {number} [sigma_r]
 * @property {number} [a_r]
 * @property {string} [barrier_monitoring]
 * @property {Object} [constats]
 * @property {(Object|null)} [frozen_schedule]
 * @property {(string|null)} [anchor]
 * @property {(string|null)} [settlement_ccy]
 * @property {(VariantOverrides|null)} [variant]
 * @property {(string|null)} [strike_date]
 * @property {(string|null)} [value_date]
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [valuation_date]
 * @property {(string|null)} [maturity_date]
 * @property {Array<Array<number>>} [funding_curve]
 * @property {number} [funding_spread]
 * @property {number} [N_stat]
 * @property {number} [N_display]
 */

/**
 * State of an interactive pricing job (core/compute/interactive.Job.snapshot).
 * @typedef {Object} PricingJob
 * @property {string} job_id
 * @property {string} kind
 * @property {'queued'|'running'|'done'|'failed'|'cancelled'|'timeout'|'abandoned'} status
 * @property {(number|null)} [queue_position]
 * @property {number} elapsed_ms
 * @property {*} [result]
 * @property {(number|null)} [status_code]
 * @property {*} [detail]
 */

/**
 * @typedef {Object} PricingRequest
 * @property {52|104|208} [steps_per_year]
 * @property {string} script
 * @property {Array<UnderlyingParams>} underlyings
 * @property {Array<Array<number>>} corr_matrix
 * @property {number} [r]
 * @property {number} [T]
 * @property {number} [N]
 * @property {number} [seed]
 * @property {string} [model]
 * @property {boolean} [antithetic]
 * @property {Object} [user_params]
 * @property {boolean} [compute_greeks]
 * @property {Array<string>} [selected_greeks]
 * @property {Array<Array<number>>} [yield_curve]
 * @property {Array<Array<number>>} [funding_curve]
 * @property {number} [funding_spread]
 * @property {number} [sigma_r]
 * @property {number} [a_r]
 * @property {string} [barrier_monitoring]
 * @property {Object} [constats]
 * @property {(Object|null)} [frozen_schedule]
 * @property {(string|null)} [anchor]
 * @property {(string|null)} [settlement_ccy]
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [maturity_date]
 * @property {(string|null)} [strike_date]
 * @property {(string|null)} [value_date]
 */

/**
 * @typedef {Object} PricingResponse
 * @property {52|104|208} [steps_per_year]
 * @property {(Object|null)} [time_axis]
 * @property {number} price
 * @property {Array<number>} ic95
 * @property {number} median
 * @property {number} var5
 * @property {number} prob_gt100
 * @property {Array<number>} payoffs
 * @property {Object} flux_table
 * @property {Object} greeks
 * @property {number} elapsed_ms
 * @property {number} n_paths
 * @property {number} n_eff
 * @property {string} [status]
 * @property {(string|null)} [errors]
 * @property {number} [t_max_effective]
 * @property {(number|null)} [fugit]
 * @property {(Array<Object>|null)} [constatation_windows]
 * @property {(Object|null)} [schedule]
 * @property {(Object|null)} [calculation_budget]
 * @property {(Object|null)} [pricing_receipt]
 * @property {(Object|null)} [corr_repair]
 * @property {string} [barrier_monitoring]
 * @property {(string|null)} [barrier_monitoring_note]
 * @property {(Object|null)} [barrier_monitoring_details]
 * @property {(string|null)} [grid_notice]
 * @property {(Array<Object>|null)} [local_vol_wings]
 * @property {(Object|null)} [surface_context]
 * @property {(Object|null)} [lsv_calibration]
 * @property {(boolean|null)} [lsv_frozen_leverage]
 * @property {(Array<Object>|null)} [lsv_limits]
 */

/**
 * @typedef {Object} ProbaRequest
 * @property {52|104|208} [steps_per_year]
 * @property {string} script
 * @property {Array<UnderlyingParams>} underlyings
 * @property {Array<Array<number>>} corr_matrix
 * @property {number} [r]
 * @property {number} [T]
 * @property {number} [seed]
 * @property {boolean} [antithetic]
 * @property {string} [model]
 * @property {Object} [user_params]
 * @property {Array<Array<number>>} [yield_curve]
 * @property {number} [sigma_r]
 * @property {number} [a_r]
 * @property {string} [barrier_monitoring]
 * @property {Object} [constats]
 * @property {(Object|null)} [frozen_schedule]
 * @property {(string|null)} [anchor]
 * @property {(string|null)} [settlement_ccy]
 * @property {(VariantOverrides|null)} [variant]
 * @property {(string|null)} [strike_date]
 * @property {(string|null)} [value_date]
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [valuation_date]
 * @property {(string|null)} [maturity_date]
 * @property {Array<Array<number>>} [funding_curve]
 * @property {number} [funding_spread]
 * @property {number} [N]
 */

/**
 * @typedef {Object} ProfileRequest
 * @property {52|104|208} [steps_per_year]
 * @property {string} script
 * @property {Array<UnderlyingParams>} underlyings
 * @property {Array<Array<number>>} corr_matrix
 * @property {number} [r]
 * @property {number} [T]
 * @property {number} [seed]
 * @property {boolean} [antithetic]
 * @property {string} [model]
 * @property {Object} [user_params]
 * @property {Array<Array<number>>} [yield_curve]
 * @property {number} [sigma_r]
 * @property {number} [a_r]
 * @property {string} [barrier_monitoring]
 * @property {Object} [constats]
 * @property {(Object|null)} [frozen_schedule]
 * @property {(string|null)} [anchor]
 * @property {(string|null)} [settlement_ccy]
 * @property {(VariantOverrides|null)} [variant]
 * @property {(string|null)} [strike_date]
 * @property {(string|null)} [value_date]
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [valuation_date]
 * @property {(string|null)} [maturity_date]
 * @property {Array<Array<number>>} [funding_curve]
 * @property {number} [funding_spread]
 */

/**
 * Realized volatility, dividends and correlation at a date, or an error.
 * The history's provenance fields are carried over as they come.
 * @typedef {Object} RealizedMarket
 * @property {(Array<string>|null)} [tickers]
 * @property {(Object<string, number>|null)} [vols]
 * @property {(Object<string, number>|null)} [div_yields]
 * @property {(Object|null)} [dividend_profiles]
 * @property {(Array<string>|null)} [missing_dividends]
 * @property {(Object<string, Object<string, number>>|null)} [corr]
 * @property {(string|null)} [period]
 * @property {(number|null)} [window_days]
 * @property {(number|null)} [n_obs]
 * @property {(string|null)} [requested_asof]
 * @property {(Object|null)} [estimator]
 * @property {(string|null)} [error]
 */

/**
 * @typedef {Object} ResolvedBusinessDay
 * @property {string} date
 * @property {string} source
 * @property {boolean} moved
 * @property {string} payment_date
 */

/**
 * Stress grid — price under combined spot x vol shocks (market data, not
 * script PARAMs). spot_shocks are multiplicative fractions (e.g. -0.10 = -10%
 * spot), vol_shocks are additive fractions (e.g. 0.05 = +5pp vol).
 * @typedef {Object} ScenarioRequest
 * @property {52|104|208} [steps_per_year]
 * @property {string} script
 * @property {Array<UnderlyingParams>} underlyings
 * @property {Array<Array<number>>} corr_matrix
 * @property {number} [r]
 * @property {number} [T]
 * @property {number} [seed]
 * @property {boolean} [antithetic]
 * @property {string} [model]
 * @property {Object} [user_params]
 * @property {Array<Array<number>>} [yield_curve]
 * @property {number} [sigma_r]
 * @property {number} [a_r]
 * @property {string} [barrier_monitoring]
 * @property {Object} [constats]
 * @property {(Object|null)} [frozen_schedule]
 * @property {(string|null)} [anchor]
 * @property {(string|null)} [settlement_ccy]
 * @property {(VariantOverrides|null)} [variant]
 * @property {(string|null)} [strike_date]
 * @property {(string|null)} [value_date]
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [valuation_date]
 * @property {(string|null)} [maturity_date]
 * @property {Array<Array<number>>} [funding_curve]
 * @property {number} [funding_spread]
 * @property {Array<number>} [spot_shocks]
 * @property {Array<number>} [vol_shocks]
 * @property {number} [N]
 */

/**
 * CONSTAT()/CONSTAT()() calendar generation — "expert mode", independent
 * of any script. Dates are ISO strings (YYYY-MM-DD); frequency/sub_frequency
 * are tenor strings (e.g. "3M", "1W", "1Y", "1D").
 * @typedef {Object} ScheduleRequest
 * @property {(Array<string>|null)} [observation_calendars]
 * @property {(string|null)} [observation_join]
 * @property {(Array<string>|null)} [settlement_calendars]
 * @property {(string|null)} [settlement_join]
 * @property {(string|null)} [start_date]
 * @property {(string|null)} [first_observation_date]
 * @property {string} end_date
 * @property {(string|null)} [roll_date]
 * @property {string} frequency
 * @property {string} [stub]
 * @property {(string|null)} [sub_frequency]
 * @property {(string|null)} [currency]
 * @property {number} [settlement_lag]
 * @property {string} [convention]
 */

/**
 * calibrate_surface's result, plus its signed evidence.
 * @typedef {Object} SmileCalibration
 * @property {Object} dossier
 * @property {Object} calibration_evidence
 */

/**
 * Solve for the script PARAM value that hits a target price (bisection).
 * target_price/lo/hi are in the PARAM's stored units (fraction for % params).
 * @typedef {Object} SolverRequest
 * @property {52|104|208} [steps_per_year]
 * @property {string} script
 * @property {Array<UnderlyingParams>} underlyings
 * @property {Array<Array<number>>} corr_matrix
 * @property {number} [r]
 * @property {number} [T]
 * @property {number} [seed]
 * @property {boolean} [antithetic]
 * @property {string} [model]
 * @property {Object} [user_params]
 * @property {Array<Array<number>>} [yield_curve]
 * @property {number} [sigma_r]
 * @property {number} [a_r]
 * @property {string} [barrier_monitoring]
 * @property {Object} [constats]
 * @property {(Object|null)} [frozen_schedule]
 * @property {(string|null)} [anchor]
 * @property {(string|null)} [settlement_ccy]
 * @property {(VariantOverrides|null)} [variant]
 * @property {(string|null)} [strike_date]
 * @property {(string|null)} [value_date]
 * @property {(string|null)} [payment_date]
 * @property {(string|null)} [valuation_date]
 * @property {(string|null)} [maturity_date]
 * @property {Array<Array<number>>} [funding_curve]
 * @property {number} [funding_spread]
 * @property {string} param_name
 * @property {number} target_price
 * @property {number} lo
 * @property {number} hi
 * @property {number} [N]
 * @property {number} [tol]
 * @property {number} [param_tol]
 * @property {number} [max_iter]
 */

/**
 * @typedef {Object} SurfaceRequest
 * @property {VolatilitySurfaceParams} surface
 */

/**
 * A relationship's version and its terms (api/trading.RelationshipTerms).
 * @typedef {Object} TradingRelationshipRow
 * @property {number} id
 * @property {number} version
 * @property {number} counterparty_id
 * @property {string} reference
 * @property {'PENDING'|'ACTIVE'|'SUSPENDED'|'EXPIRED'} status
 * @property {string} effective_date
 * @property {(string|null)} [expiry_date]
 * @property {string} currency
 * @property {boolean} note_distribution_allowed
 * @property {boolean} otc_allowed
 * @property {string} documentation_reference
 * @property {number} gross_notional_limit
 * @property {(number|null)} [master_agreement_id]
 * @property {(number|null)} [csa_id]
 * @property {boolean} csa_required
 * @property {'DVP'|'FREE_OF_PAYMENT'} settlement
 * @property {string} notes
 */

/**
 * @typedef {Object} UnderlyingGroup
 * @property {string} group
 * @property {Array<UnderlyingItem>} items
 */

/**
 * @typedef {Object} UnderlyingItem
 * @property {string} ticker
 * @property {string} label
 * @property {string} ccy
 * @property {string} asset_class
 */

/**
 * @typedef {Object} UnderlyingParams
 * @property {string} [name]
 * @property {string} [ticker]
 * @property {string} [ccy]
 * @property {(number|null)} [spot0]
 * @property {number} [sigma]
 * @property {number} [q]
 * @property {Array<Array<number>>} [dividend_curve]
 * @property {number} [dividend_decay]
 * @property {number} [sigma_fx]
 * @property {number} [rho_sfx]
 * @property {number} [ccyh]
 * @property {number} [v0]
 * @property {number} [kappa]
 * @property {number} [theta]
 * @property {number} [xi]
 * @property {number} [rho_h]
 * @property {number} [rho_rS]
 * @property {number} [alpha]
 * @property {number} [beta]
 * @property {number} [rho]
 * @property {number} [nu]
 * @property {number} [skew]
 * @property {number} [curvature]
 * @property {(VolatilitySurfaceParams|null)} [vol_surface]
 * @property {string} [asset_class]
 * @property {string} [smile_parameter_mode]
 * @property {(Object|null)} [calibration_evidence]
 * @property {(Object|null)} [market_data]
 */

/**
 * @typedef {Object} ValidatedSurface
 * @property {Object} surface
 * @property {Object} certificate
 */

/**
 * Les termes d'un avenant — ce qui remplace le parent à partir d'aujourd'hui.
 *
 * Déclaré ici plutôt que dans l'API pour que le prix ET les analytiques
 * puissent le porter : une variante que seul le prix connaîtrait ferait
 * décrire au profil de payoff et aux probabilités le produit d'ORIGINE, sous
 * un prix d'avenant. C'est précisément l'écart qu'on a passé la session à
 * fermer partout ailleurs.
 * @typedef {Object} VariantOverrides
 * @property {(string|null)} [script]
 * @property {(Object|null)} [user_params]
 * @property {(Object|null)} [constats]
 * @property {string} [mode]
 */

/**
 * @typedef {Object} VolatilitySurfaceParams
 * @property {number} [version]
 * @property {string} [profile]
 * @property {string} [mode]
 * @property {number} rho
 * @property {number} eta
 * @property {number} [shape_scale]
 * @property {number} [max_expiry]
 * @property {Array<Array<number>>} atm_nodes
 * @property {(Array<Array<*>>|null)} [wing_nodes]
 * @property {('flat'|'contango'|'backwardation'|'hump'|'custom'|null)} [atm_scenario]
 */

/**
 * GET /api/alerts
 * List Alerts
 * @param {Object} [query]
 * @param {boolean} [query.unread_only]
 * @param {number} [query.limit]
 * @returns {Promise<AlertList>}
 */
export function listAlerts(query = {}) {
  return call('GET', '/api/alerts', { query })
}

/**
 * GET /api/amc/studies
 * Lightweight list of the current user's saved studies, most recent first.
 * @returns {Promise<Array<AmcStudySummary>>}
 */
export function listStudies() {
  return call('GET', '/api/amc/studies')
}

/**
 * GET /api/auth/me
 * Me
 * @returns {Promise<CurrentUser>}
 */
export function me() {
  return call('GET', '/api/auth/me')
}

/**
 * GET /api/auth/options
 * Login Options
 * @returns {Promise<LoginOptions>}
 */
export function loginOptions() {
  return call('GET', '/api/auth/options')
}

/**
 * GET /api/calendar/catalog
 * Calendar Catalog
 * @returns {Promise<CalendarCatalog>}
 */
export function calendarCatalog() {
  return call('GET', '/api/calendar/catalog')
}

/**
 * POST /api/calendar/resolve
 * Une date contractuelle, resolue sur le calendrier de sa devise.
 * @param {BusinessDayRequest} body
 * @returns {Promise<ResolvedBusinessDay>}
 */
export function resolveBusinessDay(body) {
  return call('POST', '/api/calendar/resolve', { body })
}

/**
 * GET /api/deals
 * List Deals
 * @returns {Promise<Array<DealRow>>}
 */
export function listDeals() {
  return call('GET', '/api/deals')
}

/**
 * GET /api/deals/counterparties
 * Eligible Counterparties
 * @returns {Promise<Array<EligibleCounterparty>>}
 */
export function eligibleCounterparties() {
  return call('GET', '/api/deals/counterparties')
}

/**
 * GET /api/deals/{deal_id}
 * Get Deal
 * @param {number|string} deal_id
 * @returns {Promise<DealDetail>}
 */
export function getDeal(deal_id) {
  return call('GET', `/api/deals/${encodeURIComponent(deal_id)}`)
}

/**
 * POST /api/deals/{deal_id}/mtm
 * Residual MtM endpoint — see _mtm_core.
 * @param {number|string} deal_id
 * @param {(MtmRequest|null)} body
 * @param {Object} [query]
 * @param {number} [query.n_paths]
 * @param {boolean} [query.stream]
 * @returns {Promise<DealMtm>}
 */
export function dealMtm(deal_id, body, query = {}) {
  return call('POST', `/api/deals/${encodeURIComponent(deal_id)}/mtm`, { query, body })
}

/**
 * GET /api/finance/hist_prices
 * Load daily close prices for backtest replay.
 * @param {Object} [query]
 * @param {string} query.tickers
 * @param {string} [query.start]
 * @param {(string|null)} [query.end]
 * @returns {Promise<HistoricalPrices>}
 */
export function histPrices(query = {}) {
  return call('GET', '/api/finance/hist_prices', { query })
}

/**
 * GET /api/finance/hist_vol
 * Load realized vol/correlation for a current or historical as-of date.
 * @param {Object} [query]
 * @param {string} query.tickers
 * @param {string} [query.period]
 * @param {(string|null)} [query.asof]
 * @param {(number|null)} [query.window_days]
 * @param {boolean} [query.session_aware]
 * @returns {Promise<RealizedMarket>}
 */
export function histVol(query = {}) {
  return call('GET', '/api/finance/hist_vol', { query })
}

/**
 * GET /api/finance/underlyings
 * Le catalogue de sous-jacents, groupé et trié alphabétiquement.
 * @returns {Promise<Array<UnderlyingGroup>>}
 */
export function listUnderlyings() {
  return call('GET', '/api/finance/underlyings')
}

/**
 * POST /api/parse
 * Parse Endpoint
 * @param {ParseRequest} body
 * @returns {Promise<ParseResponse>}
 */
export function parse(body) {
  return call('POST', '/api/parse', { body })
}

/**
 * POST /api/price
 * Price Endpoint
 * @param {PricingRequest} body
 * @returns {Promise<PricingResponse>}
 */
export function price(body) {
  return call('POST', '/api/price', { body })
}

/**
 * POST /api/price/in-life
 * Price In Life
 * @param {InLifePricingRequest} body
 * @returns {Promise<(InLifeEarlyRecall|InLifePrice)>}
 */
export function priceInLife(body) {
  return call('POST', '/api/price/in-life', { body })
}

/**
 * POST /api/price/jobs/backtest
 * Submit Backtest
 * @param {BacktestRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitBacktest(body) {
  return call('POST', '/api/price/jobs/backtest', { body })
}

/**
 * POST /api/price/jobs/backtest-compare
 * Submit Backtest Compare
 * @param {BacktestCompareRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitBacktestCompare(body) {
  return call('POST', '/api/price/jobs/backtest-compare', { body })
}

/**
 * POST /api/price/jobs/grid
 * Submit Grid
 * @param {GridRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitGrid(body) {
  return call('POST', '/api/price/jobs/grid', { body })
}

/**
 * POST /api/price/jobs/implied-funding
 * Submit Implied Funding
 * @param {ImpliedFundingRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitImpliedFunding(body) {
  return call('POST', '/api/price/jobs/implied-funding', { body })
}

/**
 * POST /api/price/jobs/in-life
 * Submit In Life
 * @param {InLifePricingRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitInLife(body) {
  return call('POST', '/api/price/jobs/in-life', { body })
}

/**
 * POST /api/price/jobs/mtf
 * Submit Mtf
 * @param {MtfRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitMtf(body) {
  return call('POST', '/api/price/jobs/mtf', { body })
}

/**
 * POST /api/price/jobs/mtf-compare
 * Submit Mtf Compare
 * @param {MtfComparisonRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitMtfCompare(body) {
  return call('POST', '/api/price/jobs/mtf-compare', { body })
}

/**
 * POST /api/price/jobs/mtf-drilldown
 * Submit Mtf Drilldown
 * @param {MtfDrilldownRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitMtfDrilldown(body) {
  return call('POST', '/api/price/jobs/mtf-drilldown', { body })
}

/**
 * POST /api/price/jobs/paths
 * Submit Paths
 * @param {PathsRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitPaths(body) {
  return call('POST', '/api/price/jobs/paths', { body })
}

/**
 * POST /api/price/jobs/price
 * Submit Price
 * @param {PricingRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitPrice(body) {
  return call('POST', '/api/price/jobs/price', { body })
}

/**
 * POST /api/price/jobs/proba
 * Submit Proba
 * @param {ProbaRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitProba(body) {
  return call('POST', '/api/price/jobs/proba', { body })
}

/**
 * POST /api/price/jobs/profile
 * Submit Profile
 * @param {ProfileRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitProfile(body) {
  return call('POST', '/api/price/jobs/profile', { body })
}

/**
 * POST /api/price/jobs/scenarios
 * Submit Scenarios
 * @param {ScenarioRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitScenarios(body) {
  return call('POST', '/api/price/jobs/scenarios', { body })
}

/**
 * POST /api/price/jobs/solve
 * Submit Solve
 * @param {SolverRequest} body
 * @returns {Promise<PricingJob>}
 */
export function submitSolve(body) {
  return call('POST', '/api/price/jobs/solve', { body })
}

/**
 * DELETE /api/price/jobs/{job_id}
 * Cancel Job
 * @param {number|string} job_id
 * @returns {Promise<PricingJob>}
 */
export function cancelJob(job_id) {
  return call('DELETE', `/api/price/jobs/${encodeURIComponent(job_id)}`)
}

/**
 * GET /api/price/jobs/{job_id}
 * Job Status
 * @param {number|string} job_id
 * @returns {Promise<PricingJob>}
 */
export function jobStatus(job_id) {
  return call('GET', `/api/price/jobs/${encodeURIComponent(job_id)}`)
}

/**
 * POST /api/schedule/generate
 * Build a CONSTAT()/CONSTAT()() date schedule and its year-fraction preview.
 * @param {ScheduleRequest} body
 * @returns {Promise<GeneratedSchedule>}
 */
export function generateSchedule(body) {
  return call('POST', '/api/schedule/generate', { body })
}

/**
 * GET /api/trading/relationships
 * Relationships
 * @returns {Promise<Array<TradingRelationshipRow>>}
 */
export function relationships() {
  return call('GET', '/api/trading/relationships')
}

/**
 * POST /api/v1/structured-indices/athena/issue-batches
 * Submit Issue Batch
 * @param {AthenaIssueBatch} body
 * @returns {Promise<AthenaBatchTicket>}
 */
export function submitIssueBatch(body) {
  return call('POST', '/api/v1/structured-indices/athena/issue-batches', { body })
}

/**
 * POST /api/v1/structured-indices/athena/lifecycle
 * Check Lifecycle
 * @param {AthenaLifecycleRequest} body
 * @returns {Promise<AthenaLifecycleResult>}
 */
export function checkLifecycle(body) {
  return call('POST', '/api/v1/structured-indices/athena/lifecycle', { body })
}

/**
 * POST /api/v1/structured-indices/athena/mtm-batches
 * Submit Mark Batch
 * @param {AthenaMarkBatch} body
 * @returns {Promise<AthenaBatchTicket>}
 */
export function submitMarkBatch(body) {
  return call('POST', '/api/v1/structured-indices/athena/mtm-batches', { body })
}

/**
 * GET /api/v1/structured-indices/athena/pricing-models
 * Pricing Models
 * @returns {Promise<AthenaPricingCatalogue>}
 */
export function pricingModels() {
  return call('GET', '/api/v1/structured-indices/athena/pricing-models')
}

/**
 * POST /api/v1/structured-indices/athena/realized-volatility
 * Apply Structura's estimator to the caller's qualified closing series.
 * @param {AthenaRealizedVolatilityRequest} body
 * @returns {Promise<AthenaRealizedVolatility>}
 */
export function realizeVolatility(body) {
  return call('POST', '/api/v1/structured-indices/athena/realized-volatility', { body })
}

/**
 * POST /api/volatility/calibrate
 * Calibrate
 * @param {CalibrationRequest} body
 * @returns {Promise<SmileCalibration>}
 */
export function calibrate(body) {
  return call('POST', '/api/volatility/calibrate', { body })
}

/**
 * POST /api/volatility/left-wing
 * Adjust Left Wing
 * @param {LeftWingRequest} body
 * @returns {Promise<LeftWingAdjustment>}
 */
export function adjustLeftWing(body) {
  return call('POST', '/api/volatility/left-wing', { body })
}

/**
 * POST /api/volatility/validate
 * Validate Surface
 * @param {SurfaceRequest} body
 * @returns {Promise<ValidatedSurface>}
 */
export function validateSurface(body) {
  return call('POST', '/api/volatility/validate', { body })
}
