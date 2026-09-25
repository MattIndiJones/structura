"""Compare independent references with the isolated Studies run. Never fit references to outputs."""
from pathlib import Path
import json
import csv
import sys


def report(root, *, unified_result=None, output=None):
    def load(path): return json.loads((root / path).read_text(encoding='utf-8'))
    ref = load('reference/summary.json')
    if unified_result is not None and unified_result.get('provenance', {}).get('method_version') in ('studies-2.4', 'studies-2.5'):
        from methodology_reference import revised_reference
        ref = revised_reference(root, ref)
    result = unified_result if unified_result is not None else load('comparison/studies_full.json')
    e = result['block_e'] if unified_result is not None else load('comparison/studies_E.json')['block_e']
    g = result['block_g'] if unified_result is not None else load('comparison/studies_G.json')
    output = Path(output) if output else root / 'comparison'
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    def compare(block, metric, expected, actual, tolerance):
        gap = actual - expected if isinstance(actual, (int, float)) else None
        checks.append(dict(block=block, metric=metric, independent=expected, studies=actual,
                           delta=gap, tolerance=tolerance, status='OK' if gap is not None and abs(gap) <= tolerance + 1e-12 else 'À examiner'))
    for key in ['bh_nav', 'bh_perf_pct', 'actual_perf_pct', 'value_added_pct', 'cash_weight_pct', 'n_positions']:
        compare('E', key, ref['E'][key], e.get(key), .005 if key != 'cash_weight_pct' else .00005)
    for key, actual, tol in [('round_trips', 'count', 0), ('hit_ratio_pct', 'win_rate_pct', .05),
        ('profit_factor', 'profit_factor', .005), ('realized_pnl_usd', 'realized_pnl', .005),
        ('mean_holding_days', 'avg_holding_days', .05), ('median_holding_days', 'median_holding_days', 0)]:
        compare('C', key, ref['C'][key], result['block_c']['round_trips'].get(actual), tol)
    for key, val in ref['D']['categories'].items(): compare('D', key, val, result['block_d']['conviction_matrix']['counts'].get(key), 0)
    reg = result['block_a']['net']['regression']
    for key, actual, tol in [('n_obs','n_obs',0),('alpha_daily','alpha_daily',.0000005),
        ('alpha_ann_linear_pct','alpha_ann_pct',.005),('r2','r2',.00005)]: compare('A', key, ref['A'][key], reg.get(actual), tol)
    with open(root / 'reference/A_coefficients.csv', encoding='utf-8') as stream:
        coefficients = list(csv.DictReader(stream))
    for coefficient in coefficients[1:]:
        actual = next(f['beta'] for f in reg['factors'] if f['name'] == coefficient['term'])
        compare('A', coefficient['term'], float(coefficient['coefficient']), actual, .00005)
    for key, actual in [('replicant_total_pct','replicant_total_pct'),('amc_total_aligned_pct','amc_total_pct'),('alpha_gap_pct','alpha_gap_pct'),('score_full_precision','score')]:
        compare('F', key, ref['F'][key], result['block_f'].get(actual), .005 if key != 'score_full_precision' else 0)
    for key, actual, tol in [('n_analyzed','n_trades_analyzed',0),('entry_mean','entry_score_mean',.00005),
        ('exit_mean','exit_score_mean',.00005),('global_mean','global_score_mean',.00005)]: compare('H',key,ref['H'][key],result['block_h'].get(actual),tol)
    for horizon, values in ref['I'].items():
        for key, tol in [('n',0),('alpha_mean',.00005),('success_rate',.00005)]:
            compare('I',horizon+' '+key,values[key],result['block_i']['stats_by_horizon'][horizon].get(key),tol)
    compare('I','score',ref['I_score']['score_full_precision'],result['block_i'].get('score'),0)
    for key in ['allocation_pct','selection_pct','interaction_pct','active_return_pct']: compare('G',key,ref['G'][key],g.get(key),.005)
    mappings = [('max_drawdown_pct','drawdown','max_drawdown_pct',.005),('ulcer_index_pct','drawdown','ulcer_index_pct',.005),
        ('sharpe_rf_zero','risk_adjusted','sharpe_ratio',.0005),('sortino_target_zero','risk_adjusted','sortino_ratio',.0005),
        ('calmar_252','risk_adjusted','calmar_ratio',.0005),('information_ratio','risk_adjusted','information_ratio',.0005),
        ('tracking_error_pct','risk_adjusted','tracking_error_pct',.005),('up_capture_pct','risk_adjusted','upside_capture_pct',.05),
        ('down_capture_pct','risk_adjusted','downside_capture_pct',.05),('var95_daily_pct','downside_risk','var_95_pct',.005),
        ('es95_daily_pct','downside_risk','es_95_pct',.005),('hhi_with_cash','concentration','hhi',.00005),
        ('effective_positions','concentration','effective_n',.005)]
    for key, section, actual, tol in mappings: compare('J',key,ref['J'][key],result['block_j']['sub_scores'][section].get(actual),tol)
    compare('J','score',ref['J_score']['score'],result['block_j'].get('score'),0)
    compare('J','nombre total épisodes',ref['J_score']['all_drawdown_episodes'],result['block_j']['sub_scores']['drawdown'].get('n_drawdown_episodes'),0)
    with open(root / 'reference/K_events.csv', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            actual = next(r for r in result['block_k']['events'] if r['id'] == row['event_id'])
            for key, field, tol in [('n_trades','n_trades',0),('gross_notional_usd','gross_notional',.5),('net_flow_usd','net_flow',.5),('activity_ratio','activity_ratio',.005)]:
                compare('K',row['event_id']+' '+key,float(row[key]),actual.get(field),tol)
    compare('Manager Skill','score',ref['Manager_Skill']['score'],result['manager_skill_score'].get('score'),0)
    out = output / 'checks.csv'
    with open(out, 'w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=checks[0].keys()); writer.writeheader(); writer.writerows(checks)
    gaps = [r for r in checks if r['status'] != 'OK']
    data = {'comparisons':len(checks),'passed':len(checks)-len(gaps),'to_examine':gaps,
            'scope': 'Moteur standard, dossier autonome ; politique réseau à documenter pour chaque exécution' if unified_result is not None else 'Banc isolé, données injectées en mémoire'}
    (output / 'summary.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(data,ensure_ascii=False,indent=2))
    return data


if __name__ == '__main__': report(Path(sys.argv[1]))
