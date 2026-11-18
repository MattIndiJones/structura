"""Monte Carlo engine — vectorized path simulation + per-path PayScript evaluation.

Models: constant (GBM), heston (QE), sabr (ATM vol), localvol (Dupire),
lsv (Local-Stochastic Vol — Dupire local vol target + Heston-QE stochastic
variance, recalibrated each step via a leverage function; see _simulate_lsv).
Variance reduction: antithetic variates.
Greeks: CRN bump-and-reprice.
Analytics: payoff profile, MC paths visualization, probability analysis, historical backtest.

Facade since 18/11/2026: the code lives in the modules below, one per
concern. Every name the engine ever defined or imported is re-exported, so
`engine.run_mc`, `engine._simulate_lv` and the like keep working. To replace
a function in a test, patch it in the module that calls it.
"""
from __future__ import annotations

# Names the original module imported, still reachable as engine.<name>.
from .bindings import effective_parameters
from .time_grid import (contract_axis, durations as _durations, times as _times,
                        time_at as _time_at, step_at as _step_at, metadata as _axis_metadata)
from .bridge import (
    bridge_extrema, bridge_metadata, bridge_note, semidefinite_factor,
    validate_bridge_domain, resolve_bridge_substeps,
)
import bisect
import math
import time
from dataclasses import replace
from datetime import date, timedelta
from typing import NamedTuple
from ..simulation_grid import grid_frequency, with_simulation_grid

import numpy as np
from numpy.random import default_rng
from scipy.special import erfc
from .parser import CompiledScript, CompiledEvent, validate_observation_dates
from .models import MODELS
from ..compute_budget import (
    ABSOLUTE_WORK_LIMIT,
    WORKER_MEMORY_LIMIT_BYTES,
    ensure_budget,
    count_compiled_dates,
    estimate_mc,
    estimate_mc_batch,
    validate_compiled_dates,
    validate_problem_dimensions,
)

from .mc_axis import (  # noqa: F401
    SY,
    TIME_AXIS_POLICY,
    _ContractEventSchedule,
    _event_schedule,
    _event_times,
    _simulation_axis,
)
from .diffusion import (  # noqa: F401
    CORR_REPAIR_TOL,
    PSI_C,
    _LSV_CONDITIONAL_BUCKETS,
    _LSV_MIN_BUCKET_PATHS,
    _atm_step_vols,
    _bridge_extrema,
    _heston_qe_scalar,
    _heston_qe_vectorized,
    _local_vol_at_spot,
    _lsv_conditional_variance,
    _seed_spot,
    _simulate_gbm,
    _simulate_heston,
    _simulate_lsv,
    _simulate_lv,
    _simulate_sabr,
    cholesky,
    sabr_vol,
    validate_model,
)
from .local_vol import (  # noqa: F401
    _SSVI_LOCAL_VOL_LIMIT,
    _SSVI_PROTECTED_LOG_FORWARD,
    _bs_call_n,
    _build_dividend_step_matrix,
    _build_lv_grid,
    _dupire_vol,
    _extend_ssvi_local_vol_wings,
    _ncdf,
    _smile_vol,
    _validate_dividend_curve,
)
from .rates import (  # noqa: F401
    _RateTerm,
    _blend_rate_factor,
    _build_df_arr,
    _build_rate_term,
    _df_at_time,
    _forward_rate_arr,
    _funding_df_arr,
    _hw_convexity,
    _ou_transition,
    _rate_coupled_factor,
    _stochastic_rate_paths,
    _validate_short_rate_parameters,
)
from .evaluation import (  # noqa: F401
    _RunningState,
    _basket_references,
    _combine_reduction,
    _constater,
    _eval_paths,
    _eval_paths_detailed,
    _fixer_le_strike_sur_les_trajectoires,
    _fusionner_realise,
    _niveau_initial,
    _niveaux_constates,
    _path_references,
    _rangs_observation,
    _rebaser_sur_le_niveau_initial,
    _reduce_window,
    _running_state,
    _state_by_asset,
    _strike_fix_steps,
    _window_steps,
    cle_de_fenetre,
)
from .monte_carlo import (  # noqa: F401
    _average_antithetic_flux_maps,
    _window_report,
    run_mc,
)
from .greeks import (  # noqa: F401
    _age_compiled_script,
    _correlation_bump,
    _theta_and_event,
    compute_greeks,
)
from .analytics import (  # noqa: F401
    _run_analysis,
    run_mc_paths,
    run_mc_proba,
    run_payoff_profile,
)
from .mark_to_future import (  # noqa: F401
    MTF_MAX_BATCH,
    MTF_MIN_ALIVE,
    MTF_PRICER_MODELS,
    _exact_mtf_residual,
    _mtf_claim_rows,
    _mtf_date_stats,
    _mtf_inner_paths,
    _mtf_known_only_row,
    _mtf_model_paths,
    _mtf_outer_state,
    _mtf_past_step_map,
    _mtf_payment_args,
    _mtf_realized_fix,
    _mtf_reject_unsupported,
    _mtf_releves_realises,
    _mtf_replay,
    _mtf_residual_script,
    _mtf_step,
    _scenario_realise,
    _shift_events_for_mtf,
    _simulate_mtf_outer,
    _tranche_realise,
    build_mtf_dates,
    mtf_date_grid,
    mtf_simulation_axis,
    run_mark_to_future,
)
from .mtf_drilldown import (  # noqa: F401
    _mtf_barriers,
    _mtf_flux_rows,
    _mtf_observations,
    run_mtf_drilldown,
)
from .backtest import (  # noqa: F401
    IRR_CAP,
    IRR_FLOOR,
    _LectureParDate,
    _ajouter_jours_de_semaine,
    _historical_per_asset_extrema,
    _historical_running_extrema,
    _jours_de_semaine_entre,
    compute_irr,
    derniere_fenetre,
    eval_script_on_history,
    seances_jusqu_a,
)

from . import (analytics, backtest, diffusion, evaluation, greeks, local_vol, mark_to_future,
               mc_axis, monte_carlo, mtf_drilldown, rates)

# Every module the engine was split into. A test that replaces an engine
# dependency goes through backend/tests/engine_patch.py, which patches the name
# in each of these modules that binds it.
SUBMODULES = (mc_axis, diffusion, local_vol, rates, evaluation, monte_carlo, greeks,
              analytics, mark_to_future, mtf_drilldown, backtest)
