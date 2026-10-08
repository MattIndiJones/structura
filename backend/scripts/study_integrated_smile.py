"""Repeat the 4Y Athena study using the editable surface's actual production path.

No database, network market data, or engine configuration is modified. Stage
outputs are deliberately separate, so a failed numerical gate is not hidden by
an integration assertion or by a successful calibration optimizer.
"""
import argparse
import gc
import hashlib
import json
import math
from datetime import date
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.api.pricing import price_endpoint
from backend.app.core.calendars import adjust, add_business_days, BusinessDayConvention
from backend.app.core.payscript import engine
from backend.app.core.payscript.catalogue import PRODUCTS
from backend.app.core.payscript.parser import parse_script, resolve_analysis_constats
from backend.app.core.schemas import PricingRequest
from backend.app.core.smile_calibration import calibrate_surface
from backend.app.core.volatility_surface import TermSSVISurface
from backend.scripts.compare_common_surface import snapshots, athena_flows, vanilla_statistics
from backend.scripts.vol_model_references import black_scholes, heston_vanillas, sabr_spot_pde

OUT = ROOT / 'output/integrated-smile-20261007'
SEEDS = (42, 17, 93, 731, 2026, 77, 123, 991)
MODELS = ('constant', 'heston', 'sabr', 'localvol', 'lsv')
STRIKES = (.6, .8, 1., 1.2, 1.5)
START = date(2026, 10, 6)
END = date(2030, 10, 6)
MATURITY = adjust(END, 'EUR', BusinessDayConvention.FOLLOWING)
PAYMENT = add_business_days(MATURITY, 3, 'EUR')
COMMON = dict(script=PRODUCTS['autocall_athena']['script'], r=.03,
    T=(MATURITY-START).days/365.25, seed=42, antithetic=True, compute_greeks=False,
    user_params={'COUPON': .10, 'M_AC_BAR': 1., 'M_KI_BAR': .60},
    constats={'STARTDATE': str(START), 'OBSERVATIONDATES': {
        'first_observation_date': '2027-10-06', 'end_date': str(END),
        'frequency': '1Y', 'roll_date': '2027-10-06', 'period_start_date': str(START),
        'convention': 'following', 'settlement_lag': 3}},
    strike_date=START, anchor=START, value_date=START, maturity_date=MATURITY,
    payment_date=PAYMENT, settlement_ccy='EUR', funding_spread=0.,
    funding_curve=[], yield_curve=[], sigma_r=0., a_r=0., barrier_monitoring='weekly')


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / (name+'.json')).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def load(name):
    return json.loads((OUT / (name+'.json')).read_text(encoding='utf-8'))


def frontend_profiles():
    # Read the very same factory used by the UI, rather than copying its defaults.
    source = "import {makeSurface} from './frontend/src/utils/volSurface.js'; console.log(JSON.stringify([20,30].map(v=>({level:v,surface:makeSurface('equity',v)}))));"
    result = subprocess.run(['node', '--input-type=module', '-e', source], cwd=ROOT,
        check=True, capture_output=True, text=True, encoding='utf-8')
    return json.loads(result.stdout)


def request(scenario, model, assets=1, pairs=3000):
    params = scenario['parameters'][model]
    names = [('Société Générale', 'GLE.PA'), ('STMicroelectronics', 'STMPA.PA')]
    return PricingRequest(**COMMON, N=pairs, model=model,
        underlyings=[dict(params, name=name, ticker=ticker) for name, ticker in names[:assets]],
        corr_matrix=[[1.]] if assets == 1 else [[1., .5], [.5, 1.]])


def dates_for(req):
    compiled = resolve_analysis_constats(parse_script(req.script), req)
    event = compiled.events[0]
    assert event.ranks == [1, 2, 3, 4] and len(event.dates) == 4
    return dict(start=str(START), maturity=str(MATURITY), payment=str(PAYMENT),
                observations=event.dates, payments=event.payment_dates, ranks=event.ranks)


def calibrate():
    report = dict(source='Synthetic assumptions, frontend profile factory; no option market quotes',
                  scenarios=[], default_steps_per_year=engine.SY)
    for profile in frontend_profiles():
        level, surface = profile['level'], profile['surface']
        print('CALIBRATION', level, flush=True)
        base = dict(sigma=level/100, q=.02, vol_surface=surface,
                    asset_class='equity', smile_parameter_mode='automatic')
        fits = {model: calibrate_surface(surface, model, COMMON['T'], .03, .02)
                for model in ('heston', 'sabr')}
        params = {model: dict(base, **(fits['heston']['parameters'] if model in ('heston', 'lsv')
                   else fits['sabr']['parameters'] if model == 'sabr' else {})) for model in MODELS}
        scenario = dict(level=level, surface=surface, fits=fits, parameters=params,
                        certificate=TermSSVISurface(surface).certificate())
        scenario['dates'] = dates_for(request(scenario, 'constant'))
        report['scenarios'].append(scenario)
        save('calibration', report)
        print('FIT', level, fits, flush=True)
    return report


def api_check():
    report = dict(scope='Direct production API function, Pydantic + calendar + PayScript + engine; no HTTP/browser', runs=[])
    for scenario in load('calibration')['scenarios']:
        times, payments = scenario['dates']['observations'], scenario['dates']['payments']
        for assets in (1, 2):
            for model in MODELS:
                req = request(scenario, model, assets)
                print('API', scenario['level'], assets, model, flush=True)
                response = price_endpoint(req).model_dump(mode='json')
                rows = list(response['flux_table'].values())
                assert abs(sum(f['sum'] for f in rows if f['lbl'].startswith('Capital'))/req.N-1) < 1e-9
                pv = sum(f['pv'] for f in rows)/req.N
                assert abs(pv-response['price']) < 1e-6
                params = req.underlyings[0].model_dump()
                assert params['vol_surface'] == scenario['surface']
                legs = snapshots(model, params, expiry=times[-1], sy=engine.SY,
                                 pairs=req.N, assets=assets, seed=req.seed, observations=times)
                a, _ = athena_flows(legs[0], payments)
                b, _ = athena_flows(legs[1], payments)
                independent = float(((a+b)/2).mean())
                assert abs(independent-response['price']) < 1e-6, (model, independent, response['price'])
                report['runs'].append(dict(level=scenario['level'], assets=assets, model=model,
                    request=req.model_dump(mode='json'), sy=engine.SY, price_pct=response['price']*100,
                    independent_price_pct=independent*100, reconciliation_error=pv-response['price'],
                    flux_table=response['flux_table'], pricing_receipt=response['pricing_receipt']))
                save('api', report)
                del response, legs
                gc.collect()
    return report


def pricing(mono_pairs=10000, dimensions=(1, 2), output_name='pricing',
            levels=(20, 30), models=MODELS, multi_pairs=10000, seeds=SEEDS):
    report = dict(sy=208, seeds=seeds, runs=[])
    for scenario in load('calibration')['scenarios']:
        if scenario['level'] not in levels: continue
        times, payments = scenario['dates']['observations'], scenario['dates']['payments']
        horizon = times[-1]
        dt = horizon/round(horizon*208)
        effective = [round(t/dt)*dt for t in times]
        for assets in dimensions:
            pairs = mono_pairs if assets == 1 else multi_pairs
            for model in models:
                prices, flow_batches, vanilla_batches, forward_batches = [], [], [], []
                params = request(scenario, model).underlyings[0].model_dump()
                for seed in seeds:
                    print('PRICE', scenario['level'], assets, model, seed, flush=True)
                    legs = snapshots(model, params, expiry=horizon, sy=208, pairs=pairs,
                                     assets=assets, seed=seed, observations=times)
                    a, fa = athena_flows(legs[0], payments)
                    b, fb = athena_flows(legs[1], payments)
                    prices.append(float(((a+b)/2).mean()))
                    flow_batches.append([{kind: float(((x[kind]+y[kind])/2).mean())
                        for kind in ('capital', 'coupons', 'put', 'recall')}
                        for x, y in zip(fa, fb)])
                    vanilla_batches.append(vanilla_statistics(legs, effective, STRIKES))
                    forward_batches.append(((legs[0]+legs[1])/2).mean(axis=2))
                    del legs
                    gc.collect()
                mean, se = float(np.mean(prices)), float(np.std(prices, ddof=1)/math.sqrt(len(seeds)))
                half = float(student_t.ppf(.975, len(seeds)-1))*se
                flows = [dict(observation=i+1, observation_time=times[i], payment_time=payments[i],
                    **{kind: float(np.mean([batch[i][kind] for batch in flow_batches]))
                       for kind in ('capital', 'coupons', 'put', 'recall')}) for i in range(4)]
                pv = {kind: sum(math.exp(-.03*f['payment_time'])*f[kind] for f in flows)
                      for kind in ('capital', 'coupons', 'put')}
                assert abs(sum(pv.values())-mean) < 1e-12
                rows = []
                for i, row in enumerate(vanilla_batches[0]):
                    item = {key: row[key] for key in ('expiry', 'strike', 'asset')}
                    for kind in ('call', 'put', 'digital'):
                        estimates = [batch[i][kind]['price'] for batch in vanilla_batches]
                        item[kind] = dict(price=float(np.mean(estimates)),
                            batch_se=float(np.std(estimates, ddof=1)/math.sqrt(len(seeds))))
                    rows.append(item)
                forward = []
                for i, t in enumerate(effective):
                    for asset in range(assets):
                        values = [batch[i, asset] for batch in forward_batches]
                        value, error = float(np.mean(values)), float(np.std(values, ddof=1)/math.sqrt(len(seeds)))
                        target = math.exp(.01*t)
                        forward.append(dict(expiry=t, asset=asset+1, mean=value,
                            error_bp=(value-target)*10000, se_bp=error*10000,
                            flagged=bool(abs(value-target) > .0002+3*error)))
                run = dict(level=scenario['level'], assets=assets, model=model, parameters=params,
                    pairs_per_batch=pairs,
                    price_pct=mean*100, ci95_pct=[(mean-half)*100, (mean+half)*100], se_bp=se*10000,
                    batch_prices=prices, pv_legs_pct={k: v*100 for k, v in pv.items()},
                    flows=flows, validation=rows, forward=forward)
                report['runs'].append(run)
                save(output_name, report)
                print('RESULT', scenario['level'], assets, model, run['price_pct'], run['ci95_pct'], flush=True)
    return report


def refine_mono():
    return pricing(mono_pairs=20000, dimensions=(1,), output_name='refined-mono')


def independent_verification():
    return pricing(dimensions=(2,), output_name='verification', levels=(30,),
        models=('constant', 'localvol'), multi_pairs=20000,
        seeds=(4242, 1717, 9393, 731731, 20262026, 7777, 123123, 991991))


def merge_refinement():
    # Preserve all initial estimates and alerts before increasing every mono
    # model's particle count, including the models without initial alerts.
    save('initial-pricing', load('pricing'))
    if (OUT/'results.json').exists(): save('initial-results', load('results'))
    report, refinement = load('pricing'), load('refined-mono')
    assert len(report['runs']) == 20 and len(refinement['runs']) == 10
    report['runs'] = [next(x for x in refinement['runs'] if
        (x['level'], x['model']) == (r['level'], r['model'])) if r['assets']==1 else r
        for r in report['runs']]
    save('pricing', report)
    return report


def references():
    for scenario in load('calibration')['scenarios']:
        level = scenario['level']
        times = scenario['dates']['observations']
        dt = times[-1]/round(times[-1]*208)
        expiries = [round(t/dt)*dt for t in times]
        params = scenario['fits']['sabr']['parameters']
        for name, settings in [('fine', dict(ds=.0125, dy=.075, y_width=3.6, steps_per_year=200)),
                               ('coarse', {}), ('domain', dict(s_max=12., y_width=4.))]:
            print('PDE', level, name, flush=True)
            rows = sabr_spot_pde(STRIKES, expiries, **params, **settings)
            save(f'pde-{level}-{name}', dict(parameters=params, settings=settings, rows=rows))


def edited_surface_check():
    source = "import {makeSurface,shiftSurface,moveSurfaceNode,surfaceVol} from './frontend/src/utils/volSurface.js'; const s=makeSurface('equity',30); console.log(JSON.stringify([{name:'base',surface:s},{name:'all_atm_plus_1',surface:shiftSurface(s,1,1,true)},{name:'wing_80_plus_1',surface:moveSurfaceNode(s,1,.8,surfaceVol(s,1,.8)+1)}]));"
    result = subprocess.run(['node', '--input-type=module', '-e', source], cwd=ROOT,
        check=True, capture_output=True, text=True, encoding='utf-8')
    variants = json.loads(result.stdout)
    report = dict(source='Same curve-edit functions as UI; API repricing with fixed seed', runs=[])
    for variant in variants:
        surface = variant['surface']
        sigma = math.sqrt(TermSSVISurface(surface)._theta(1.)[0])
        scenario = dict(parameters={model: dict(sigma=sigma, q=.02, vol_surface=surface,
            asset_class='equity') for model in ('constant', 'localvol')})
        for assets in (1, 2):
            for model in ('constant', 'localvol'):
                print('EDIT', variant['name'], assets, model, flush=True)
                response = price_endpoint(request(scenario, model, assets, 10000)).model_dump(mode='json')
                baseline = next((r for r in report['runs'] if r['variant']=='base' and r['assets']==assets and r['model']==model), None)
                change = response['price']-baseline['price'] if baseline else 0.
                if variant['name']=='wing_80_plus_1' and model=='constant': assert change==0
                elif variant['name']!='base': assert abs(change)>.0001
                report['runs'].append(dict(variant=variant['name'], assets=assets, model=model,
                    surface=surface, sigma=sigma, price=response['price'], change_bp=change*10000))
                save('edits', report)
    return report


def convergence(levels=(20, 30), dimensions=(1, 2), models=MODELS, pairs=3000, output_name='convergence'):
    report = dict(pairs_per_batch=pairs, seeds=SEEDS, tolerance_bp=5., runs=[])
    for scenario in load('calibration')['scenarios']:
        if scenario['level'] not in levels: continue
        times, payments = scenario['dates']['observations'], scenario['dates']['payments']
        horizon = times[-1]
        for assets in dimensions:
            for model in models:
                params = request(scenario, model).underlyings[0].model_dump()
                differences = {52: [], 104: []}
                for seed in SEEDS:
                    print('CONVERGENCE', scenario['level'], assets, model, seed, flush=True)
                    grids = [np.linspace(0, horizon, round(horizon*sy)+1) for sy in (52, 104, 208)]
                    union = np.unique(np.concatenate(grids))
                    rng = np.random.default_rng(seed)
                    def brownian():
                        values = rng.standard_normal((len(union)-1, assets, pairs))
                        values *= np.sqrt(np.diff(union))[:, None, None]
                        np.cumsum(values, axis=0, out=values)
                        return np.concatenate((np.zeros((1, assets, pairs)), values))
                    spot, vol = brownian(), brownian()
                    values = []
                    for sy, grid in zip((52, 104, 208), grids):
                        idx = np.searchsorted(union, grid)
                        scale = math.sqrt(horizon/(len(grid)-1))
                        shocks = (np.diff(spot[idx], axis=0)/scale, np.diff(vol[idx], axis=0)/scale)
                        legs = snapshots(model, params, expiry=horizon, sy=sy, pairs=pairs,
                            assets=assets, observations=times, shocks=shocks)
                        a, _ = athena_flows(legs[0], payments)
                        b, _ = athena_flows(legs[1], payments)
                        values.append(float(((a+b)/2).mean()))
                        del shocks, legs
                    for i, sy in enumerate((52, 104)):
                        differences[sy].append(values[2]-values[i])
                    del spot, vol
                    gc.collect()
                for sy in (52, 104):
                    mean = float(np.mean(differences[sy]))
                    se = float(np.std(differences[sy], ddof=1)/math.sqrt(len(SEEDS)))
                    report['runs'].append(dict(level=scenario['level'], assets=assets, model=model,
                        coarse_sy=sy, fine_sy=208, change_bp=mean*10000, se_bp=se*10000,
                        flagged=bool(abs(mean) > .0005+3*se)))
                save(output_name, report)


def temporal_lv_verification():
    return convergence(levels=(30,), models=('localvol',), pairs=10000, output_name='temporal-lv')


def finalize(input_name='pricing', output_name='results'):
    report = load(input_name)
    for run in report['runs']:
        run.setdefault('pairs_per_batch', 10000)
        scenario = next(s for s in load('calibration')['scenarios'] if s['level'] == run['level'])
        target = TermSSVISurface(scenario['surface'])
        pdes = {name: load(f"pde-{run['level']}-{name}") for name in ('fine', 'coarse', 'domain')} if run['model'] == 'sabr' else {}
        for row in run['validation']:
            t, k = row['expiry'], row['strike']
            common = target.vanillas(k, t, .03, .02)
            envelope = [0., 0., 0.]
            if run['model'] == 'constant': own = black_scholes(k, t, run['level']/100)
            elif run['model'] == 'heston': own = heston_vanillas(k, t, run['parameters'])
            elif run['model'] == 'sabr':
                ti = next(i for i, x in enumerate(pdes['fine']['rows']) if abs(x['expiry']-t) < 1e-10)
                ki = STRIKES.index(k)
                own = [pdes['fine']['rows'][ti][kind][ki] for kind in ('call', 'put', 'digital')]
                envelope = [abs(own[j]-pdes['coarse']['rows'][ti][kind][ki])+
                            abs(pdes['coarse']['rows'][ti][kind][ki]-pdes['domain']['rows'][ti][kind][ki])
                            for j, kind in enumerate(('call', 'put', 'digital'))]
            else: own = common
            for j, kind in enumerate(('call', 'put', 'digital')):
                item = row[kind]
                item.update(reference=float(own[j]), surface_target=float(common[j]),
                    error_bp=(item['price']-float(own[j]))*10000,
                    calibration_error_bp=(float(own[j])-float(common[j]))*10000,
                    pde_envelope_bp=envelope[j]*10000,
                    flagged=bool(abs(item['price']-float(own[j])) > 3*item['batch_se']+
                                 envelope[j]+(10 if kind == 'digital' else 2)/10000))
        run['numerical_flags'] = {kind: sum(row[kind]['flagged'] for row in run['validation'])
                                  for kind in ('call', 'put', 'digital')}
        run['calibration_max_error_bp'] = {kind: max(abs(row[kind]['calibration_error_bp']) for row in run['validation'])
                                          for kind in ('call', 'put', 'digital')}
        baseline = next(x for x in report['runs'] if x['level'] == run['level'] and x['assets'] == run['assets'] and x['model'] == 'constant')
        values = np.array(run['batch_prices'])-baseline['batch_prices']
        change, se = float(values.mean()), float(values.std(ddof=1)/math.sqrt(len(SEEDS)))
        half = float(student_t.ppf(.975, len(SEEDS)-1))*se
        run['change_vs_constant_pct'] = 100*change
        run['change_ci95_pct'] = [100*(change-half), 100*(change+half)]
    report['source_hashes'] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [Path(__file__), Path(engine.__file__), ROOT/'backend/app/core/smile_calibration.py',
                     ROOT/'backend/app/core/volatility_surface.py', ROOT/'frontend/src/utils/volSurface.js',
                     ROOT/'backend/scripts/vol_model_references.py', ROOT/'backend/scripts/compare_common_surface.py',
                     ROOT/'backend/app/core/payscript/catalogue.py', ROOT/'backend/app/core/payscript/parser.py',
                     ROOT/'backend/app/core/calendars.py', ROOT/'backend/app/api/pricing.py',
                     ROOT/'backend/app/core/schemas.py']}
    save(output_name, report)
    for run in report['runs']:
        print(run['level'], run['assets'], run['model'], round(run['price_pct'], 4),
              run['numerical_flags'], 'forward flags', sum(x['flagged'] for x in run['forward']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=['calibration', 'api', 'pricing', 'refine-mono', 'verification', 'merge-refinement', 'references', 'edits', 'convergence', 'temporal-lv', 'finalize'])
    args = parser.parse_args()
    {'calibration': calibrate, 'api': api_check, 'pricing': pricing, 'refine-mono': refine_mono, 'verification': independent_verification, 'merge-refinement': merge_refinement,
     'references': references, 'edits': edited_surface_check, 'convergence': convergence, 'temporal-lv': temporal_lv_verification, 'finalize': finalize}[args.stage]()
