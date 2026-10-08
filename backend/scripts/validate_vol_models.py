"""Reproducible offline validation of production volatility simulators.

Run from the repository root. Synthetic inputs only; no database or network.
PDE reference convergence is reported separately from Monte Carlo uncertainty.
LSV paired standard errors are diagnostic: particles are not independent.
"""
import argparse
import gc
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.core.compute_budget import ensure_budget, estimate_mc
from backend.app.core.payscript import engine
from backend.scripts.vol_model_references import black_scholes, heston_vanillas, sabr_spot_pde

EXPIRIES = [.5, 1., 2., 3., 4.]
STRIKES = [.4, .6, .8, 1., 1.2, 1.5]
PARAMETERS = dict(sigma=.2, q=.02, v0=.04, theta=.04, kappa=2., xi=.5,
                  rho_h=-.8, alpha=.2, beta=.5, rho=-.6, nu=.5,
                  skew=-.2, curvature=.1)
REFERENCE_MESHES = {
    'coarse':dict(ds=.025,dy=.1,y_width=3.5,s_max=6.,steps_per_year=100),
    'fine':dict(ds=.0125,dy=.075,y_width=3.6,s_max=6.,steps_per_year=200),
    'domain':dict(ds=.025,dy=.1,y_width=4.,s_max=12.,steps_per_year=100),
}


def sabr_reference(cache_path):
    identity = dict(parameters={k:PARAMETERS[k] for k in ('alpha','beta','rho','nu')},
                    rate=.03,dividend=.02,strikes=STRIKES,expiries=EXPIRIES,
                    meshes=REFERENCE_MESHES,
                    source_hash=hashlib.sha256(Path(__file__).with_name(
                        'vol_model_references.py').read_bytes()).hexdigest())
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding='utf-8'))
        if cache.get('identity') != identity:
            raise ValueError('Reference cache does not match parameters or reference source')
        return cache
    cache = {'identity':identity,'runs':{}}
    for name,mesh in REFERENCE_MESHES.items():
        print('PDE reference:',name,flush=True)
        cache['runs'][name] = sabr_spot_pde(STRIKES,EXPIRIES,**mesh)
    cache_path.write_text(json.dumps(cache,indent=2),encoding='utf-8')
    return cache


def simulate_snapshots(model, parameters, dimensions, pairs, seed):
    budget = estimate_mc(operation='volatility_validation', maturity_years=4.,
                         underlyings=dimensions,paths=pairs,model=model)
    ensure_budget(budget)
    ts, dt = 208, 1/52
    underlyings = [dict(parameters) for _ in range(dimensions)]
    correlation = np.full((dimensions,dimensions),.5)
    np.fill_diagonal(correlation,1.)
    cholesky = np.linalg.cholesky(correlation)
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((ts,dimensions,pairs))
    zv = (rng.standard_normal(z.shape) if model in ('heston','sabr','lsv') else None)
    grid = (engine._build_lv_grid(underlyings,engine._build_rate_term([],ts,dt,.03,0),
                                  ts,dt) if model in ('localvol','lsv') else None)
    snapshots = []
    for sign in (1.,-1.):
        args=(ts,dimensions,pairs,dt,math.sqrt(dt),underlyings,.03,cholesky,sign*z)
        if model == 'constant':
            paths=engine._simulate_gbm(*args)
        elif model == 'heston':
            paths=engine._simulate_heston(*args,sign*zv)
        elif model == 'sabr':
            paths=engine._simulate_sabr(*args,sign*zv)
        elif model == 'localvol':
            paths=engine._simulate_lv(*args,*grid)
        else:
            paths=engine._simulate_lsv(*args,sign*zv,*grid)
        snapshots.append(paths[[round(t/dt) for t in EXPIRIES]].copy())
        del paths
        gc.collect()
    return snapshots,budget.to_dict()


def statistics(paired, reference, tolerance):
    mean=float(paired.mean())
    se=float(paired.std(ddof=1)/math.sqrt(paired.size))
    return dict(price=mean,reference=float(reference),standard_error=se,
                error_bp=10000*(mean-reference),reference_tolerance_bp=10000*tolerance,
                flagged=bool(abs(mean-reference)>3*se+tolerance))


def finalize_report(report):
    report['source_hashes']={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in (Path(engine.__file__),Path(__file__),
                                          Path(__file__).with_name('vol_model_references.py'))}
    for run in report['runs']:
        summary=run['summary']
        summary['validation_status']=('invalid_target' if summary['reference_status']=='invalid_target'
            else 'residuals_to_review' if any(summary[x+'_flags'] for x in ('call','put','digital'))
            else 'compatible_on_tested_grid')
    report['scope']='Synthetic parameter regime only; no market calibration or autocall certification'
    return report


def reference_value(model, flat, t, k, parameter, pde, ti, ki):
    if flat or model=='constant':
        return black_scholes(k,t,.2),[.0001]*3,'Black-Scholes exact'
    if model=='heston':
        value=heston_vanillas(k,t,parameter)
        other=heston_vanillas(k,t,parameter,integration_bound=400.)
        if max(abs(a-b) for a,b in zip(value,other)) > 1e-7:
            raise ValueError('Heston Fourier integration did not converge')
        return value,[.0001]*3,'Heston Fourier'
    if model=='sabr':
        fine=pde['runs']['fine'][ti]
        coarse=pde['runs']['coarse'][ti]
        domain=pde['runs']['domain'][ti]
        values=[fine[x][ki] for x in ('call','put','digital')]
        tolerances=[.0001+abs(fine[x][ki]-coarse[x][ki])
                    +abs(coarse[x][ki]-domain[x][ki]) for x in ('call','put','digital')]
        return values,tolerances,'SABR spot PDE, mesh/domain diagnostic envelope'
    # Diagnostic only: the polynomial's lower wing has negative density at 4Y.
    ell=math.log(k)
    vol=parameter['sigma']+parameter['skew']*ell+parameter['curvature']*ell*ell
    c,p,d=black_scholes(k,t,vol)
    root=vol*math.sqrt(t)
    d1=(-ell+(.01+.5*vol*vol)*t)/root
    vega=math.exp(-.02*t)*math.exp(-d1*d1/2)/math.sqrt(2*math.pi)*math.sqrt(t)
    d += vega*(parameter['skew']+2*parameter['curvature']*ell)/k
    return [c,p,d],[.0001]*3,'Invalid polynomial implied target; diagnostic only'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'output/vol-model-validation-20261007')
    parser.add_argument('--pairs',type=int,default=50000)
    parser.add_argument('--seed',type=int,default=42)
    args=parser.parse_args()
    if args.pairs < 2:
        parser.error('--pairs must be at least 2 to estimate uncertainty')
    # Reject excessive MC requests before spending time on numerical references.
    for model in ('constant','heston','sabr','localvol','lsv'):
        ensure_budget(estimate_mc(operation='volatility_validation',maturity_years=4.,
                                 underlyings=2,paths=args.pairs,model=model))
    args.output.mkdir(parents=True,exist_ok=True)
    pde=sabr_reference(args.output/'sabr_reference.json')
    report=dict(parameters=PARAMETERS,expiries=EXPIRIES,strikes=STRIKES,
                seed=args.seed,pairs=args.pairs,rate=.03,dividend=.02,correlation=.5,
                lsv_error_note='Paired SE omits particle dependence; also inspect independent seeds',
                runs=[],pde_convergence=[])
    for ti,t in enumerate(EXPIRIES):
        for ki,k in enumerate(STRIKES):
            report['pde_convergence'].append(dict(expiry=t,strike=k,**{
                x+'_mesh_bp':10000*(pde['runs']['fine'][ti][x][ki]-pde['runs']['coarse'][ti][x][ki])
                for x in ('call','put','digital')},**{
                x+'_domain_bp':10000*(pde['runs']['domain'][ti][x][ki]-pde['runs']['coarse'][ti][x][ki])
                for x in ('call','put','digital')}))
    scenarios=[(m,False,n,args.seed) for n in (1,2)
               for m in ('constant','heston','sabr','localvol','lsv')]
    scenarios += [(m,True,n,args.seed) for n in (1,2) for m in ('localvol','lsv')]
    scenarios += [('lsv',True,1,seed) for seed in (17,93)]
    for model,flat,n,seed in scenarios:
        name=f'{model}_{"flat" if flat else "native"}_{n}asset_seed{seed}'
        print('MC:',name,flush=True)
        parameters=dict(PARAMETERS)
        if flat:
            parameters.update(skew=0.,curvature=0.)
        snapshots,budget=simulate_snapshots(model,parameters,n,args.pairs,seed)
        rows=[]
        forwards=[]
        for ti,t in enumerate(EXPIRIES):
            df=math.exp(-.03*t)
            for asset in range(n):
                s1,s2=snapshots[0][ti,asset],snapshots[1][ti,asset]
                forwards.append(dict(expiry=t,asset=asset+1,**statistics(
                    (s1+s2)/2,math.exp(.01*t),.0001)))
                for ki,k in enumerate(STRIKES):
                    ref,tol,label=reference_value(model,flat,t,k,parameters,pde,ti,ki)
                    call=df*(np.maximum(s1-k,0)+np.maximum(s2-k,0))/2
                    put=df*(np.maximum(k-s1,0)+np.maximum(k-s2,0))/2
                    digital=df*((s1<k).astype(float)+(s2<k).astype(float))/2
                    rows.append(dict(expiry=t,strike=k,asset=asset+1,reference_label=label,
                        call=statistics(call,ref[0],tol[0]),put=statistics(put,ref[1],tol[1]),
                        digital=statistics(digital,ref[2],tol[2]),
                        parity_identity_max_error=float(np.max(np.abs(call-put-df*((s1+s2)/2-k))))))
        summary={x+'_flags':sum(row[x]['flagged'] for row in rows) for x in ('call','put','digital')}
        summary['barrier_digital_flags']=sum(row['digital']['flagged'] for row in rows
                                            if row['strike'] in (.6,1.))
        summary['reference_status']=('invalid_target' if model in ('localvol','lsv') and not flat
                                      else 'numerical_reference' if model=='sabr' else 'exact_reference')
        report['runs'].append(dict(name=name,model=model,flat=flat,dimensions=n,seed=seed,
                                   summary=summary,rows=rows,forwards=forwards,budget=budget))
        finalize_report(report)
        (args.output/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(summary),flush=True)
        del snapshots
        gc.collect()


if __name__=='__main__':
    main()
