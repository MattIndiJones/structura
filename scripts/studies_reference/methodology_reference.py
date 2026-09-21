"""Independent reference for the declared descriptive score policy (Studies 2.4).

Uses frozen independent metrics, never the application's computed score.
The original V1 oracle remains unchanged.
"""
import copy
import datetime as dt
import json
import math
import csv


def revised_reference(root, original):
    ref = copy.deepcopy(original)
    start = json.loads((root / 'inputs/termsheet_economic.json').read_text(encoding='utf-8'))['date']
    end = '2025-12-31'
    years = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days / 365.25
    annual_gap = ref['E']['value_added_pct'] / years
    # Recompute the declared drawdown policy from the frozen independent series.
    with open(root / 'reference/J_drawdown_episodes.csv', encoding='utf-8') as stream:
        episodes = list(csv.DictReader(stream))
    with open(root / 'inputs/benchmark_daily.csv', encoding='utf-8') as stream:
        benchmark = list(csv.DictReader(stream))
    values = [float(r['close']) for r in benchmark]
    peak, bench_dd = values[0], 0
    for value in values:
        peak = max(peak, value)
        bench_dd = min(bench_dd, (value / peak - 1) * 100)
    avg_obs = sum(float(r['duration_observations']) for r in episodes) / len(episodes)
    clip = lambda value: max(0, min(100, value))
    jr = ref['J']
    dd_score = round(.35 * clip(100 - abs(jr['max_drawdown_pct']) * 1.6) +
        .30 * clip(100 - jr['ulcer_index_pct'] * 3) +
        .20 * (.6 * clip(100 - avg_obs * .8) + .4 * clip(100 - len(episodes) * 8)) +
        .15 * clip(50 + (jr['max_drawdown_pct'] - bench_dd) * 2.5))
    js = ref['J_score']
    js.update(drawdown=dd_score, episodes_used_for_score=len(episodes),
              duration_unit='Score : observations ; restitution : jours calendaires')
    js['score'] = round(.30*js['risk_adjusted'] + .25*dd_score + .20*js['downside'] +
                        .15*js['concentration'] + .10*js['factors'])
    ref['Manager_Skill']['dimensions']['risk_mgmt'] = js['score']
    dims = ref['Manager_Skill']['dimensions']
    dims['vag'] = 50 + 50 * math.tanh(annual_gap / 20)
    weights = {'alpha': .30, 'stock_picking': .25, 'vag': .20, 'risk_mgmt': .15, 'timing': .07, 'conviction': .03}
    ref['Manager_Skill'].update(score=round(sum(dims[k] * w for k, w in weights.items())),
        available_base_weight_pct=100, E_must_be_excluded=False, methodology_version='2.4',
        vag_annual_gap_linear=annual_gap,
        reason='VAG inclus à 20 % dans le score descriptif ; comparaison net/brut explicitée, hors mesure isolée du talent.')
    return ref
