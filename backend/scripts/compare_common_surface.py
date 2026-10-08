"""Offline common-surface calibration, numerical gates and Athena repricing.

Synthetic market only. Production diffusion functions are called directly;
this does not introduce an editable surface or calibration workflow in the UI.
Independent payoff evaluation keeps every capital, coupon and short-put flow.
"""
import argparse
from dataclasses import asdict
import gc
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import least_squares
from scipy.special import ndtr

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.app.core.compute_budget import estimate_mc,ensure_budget
from backend.app.core.payscript import engine
from backend.app.core.volatility_surface import SSVISurface
from backend.scripts.vol_model_references import black_scholes,heston_vanillas
from backend.scripts.vol_model_references import sabr_spot_pde

RATE,DIVIDEND=.03,.02
EXPIRIES=[.5,1.,2.,3.,4.]
STRIKES=[.4,.6,.8,1.,1.2,1.5]
PARAMETERS=dict(sigma=.2,q=.02,v0=.04,theta=.04,kappa=2.,xi=.5,rho_h=-.8,
                alpha=.2,beta=.5,rho=-.6,nu=.5,skew=0.,curvature=0.)
OUT=ROOT/'output/common-surface-20261007'
DATES=dict(start='2026-10-06',maturity='2030-10-07',payment='2030-10-10',
           observations=['2027-10-06','2028-10-06','2029-10-08','2030-10-07'],
           payments=['2027-10-11','2028-10-11','2029-10-11','2030-10-10'])


def contractual_dates():
    from datetime import date
    result=dict(DATES)
    origin=date.fromisoformat(DATES['start'])
    result['observation_years']=[(date.fromisoformat(t)-origin).days/365.25 for t in DATES['observations']]
    result['payment_years']=[(date.fromisoformat(t)-origin).days/365.25 for t in DATES['payments']]
    return result


def snapshots(model,parameters,*,expiry=4.,sy=104,pairs=20000,assets=1,
              seed=42,target=None,observations=None,shocks=None):
    ts=round(expiry*sy);dt=expiry/ts
    ensure_budget(estimate_mc(operation='common_surface_comparison',
                              maturity_years=ts/52,underlyings=assets,paths=pairs,model=model))
    underlyings=[dict(parameters) for _ in range(assets)]
    chol=np.linalg.cholesky(np.eye(1) if assets==1 else [[1.,.5],[.5,1.]])
    if shocks is None:
        rng=np.random.default_rng(seed)
        z=rng.standard_normal((ts,assets,pairs))
        zv=rng.standard_normal(z.shape) if model in ('sabr','heston','lsv') else None
    else:
        z,zv=shocks
        if z.shape!=(ts,assets,pairs) or (model in ('sabr','heston','lsv') and zv.shape!=z.shape):
            raise ValueError('Provided Brownian shocks do not match the simulation grid')
    if target is None:
        grid=engine._build_lv_grid(underlyings,engine._build_rate_term([],ts,dt,RATE,0),ts,dt)
    else:
        # Mid-step local volatility, with first node at dt/2 rather than
        # pretending the initial state has already evolved one full step.
        grid=target.local_grid((np.arange(ts)+.5)*dt,RATE,DIVIDEND)
        grid=([grid[0]]*assets,*grid[1:])
    observations=observations or [t for t in EXPIRIES if t<=expiry]
    indices=[round(t/dt) for t in observations]
    result=[]
    for sign in (1.,-1.):
        args=(ts,assets,pairs,dt,math.sqrt(dt),underlyings,RATE,chol,sign*z)
        if model=='constant': paths=engine._simulate_gbm(*args)
        elif model=='heston': paths=engine._simulate_heston(*args,sign*zv)
        elif model=='sabr': paths=engine._simulate_sabr(*args,sign*zv)
        elif model=='localvol': paths=engine._simulate_lv(*args,*grid)
        else: paths=engine._simulate_lsv(*args,sign*zv,*grid)
        result.append(paths[indices].copy())
        del paths
        gc.collect()
    return result


def vanilla_statistics(legs,expiries=EXPIRIES,strikes=STRIKES):
    rows=[]
    for i,t in enumerate(expiries):
        for asset in range(legs[0].shape[1]):
            a,b=legs[0][i,asset],legs[1][i,asset]
            for k in strikes:
                df=math.exp(-RATE*t)
                payoffs=[df*(np.maximum(a-k,0)+np.maximum(b-k,0))/2,
                         df*(np.maximum(k-a,0)+np.maximum(k-b,0))/2,
                         df*((a<k).astype(float)+(b<k).astype(float))/2]
                rows.append(dict(expiry=t,strike=k,asset=asset+1,**{
                    name:dict(price=float(x.mean()),se=float(x.std(ddof=1)/math.sqrt(x.size)))
                    for name,x in zip(('call','put','digital'),payoffs)}))
    return rows


def precision_study():
    report={'tolerances':{'vanilla_bp':2.,'digital_bp':10.,'autocall_bp':5.},'runs':[]}
    cache_path=OUT/'native_sabr_pde.json'
    if cache_path.exists():
        pde=json.loads(cache_path.read_text())
        if pde['parameters']!={k:PARAMETERS[k] for k in ('alpha','beta','rho','nu')}:
            raise ValueError('Native SABR cache parameter mismatch')
    else:
        params={k:PARAMETERS[k] for k in ('alpha','beta','rho','nu')}
        pde=dict(parameters=params,rows=sabr_spot_pde(STRIKES,[.5,1.],**params,
                 ds=.0125,dy=.075,y_width=3.6,steps_per_year=200))
        cache_path.write_text(json.dumps(pde,indent=2))
    for model in ('sabr','lsv'):
        for sy in (52,104,208):
            batches=[]
            for seed in (42,17,93,731,2026,77,123,991):
                print('PRECISION',model,sy,seed,flush=True)
                legs=snapshots(model,PARAMETERS,expiry=1.,sy=sy,pairs=25000,
                               assets=2,seed=seed,observations=[.5,1.])
                batches.append(vanilla_statistics(legs,[.5,1.],[.4,.6,.8,1.,1.2,1.5]))
            rows=[]
            for i,row in enumerate(batches[0]):
                if model=='lsv':
                    refs=black_scholes(row['strike'],row['expiry'],.2)
                else:
                    # Reuse the independently verified native-parameter PDE.
                    ti=EXPIRIES.index(row['expiry']);ki=STRIKES.index(row['strike'])
                    refs=[pde['rows'][ti][kind][ki] for kind in ('call','put','digital')]
                item={k:row[k] for k in ('expiry','strike','asset')}
                for kind,ref in zip(('call','put','digital'),refs):
                    values=np.array([batch[i][kind]['price'] for batch in batches])
                    se=float(values.std(ddof=1)/math.sqrt(len(values)))
                    tolerance=(10. if kind=='digital' else 2.)/10000
                    item[kind]=dict(price=float(values.mean()),reference=float(ref),
                        batch_se=se,error_bp=10000*(float(values.mean())-ref),
                        flagged=bool(abs(float(values.mean())-ref)>3*se+tolerance))
                rows.append(item)
            report['runs'].append(dict(model=model,sy=sy,pairs_per_batch=25000,batches=8,
                                       rows=rows,flags={kind:sum(x[kind]['flagged'] for x in rows)
                                                       for kind in ('call','put','digital')}))
            (OUT/'precision.json').write_text(json.dumps(report,indent=2))
            print(report['runs'][-1]['flags'],flush=True)
    return report


def heston_call_grid(parameters,expiries=EXPIRIES,strikes=STRIKES):
    """Vectorized fixed-node Fourier quadrature for deterministic calibration.

    Final parameters are rechecked against adaptive independent quadrature.
    """
    nodes,weights=np.polynomial.legendre.leggauss(256)
    u=(nodes+1)*150;weights=weights*150
    k=np.asarray(strikes)
    v0,theta,kap,xi,rho=[parameters[key] for key in ('v0','theta','kappa','xi','rho_h')]
    rows=[]
    for t in expiries:
        def cf(z):
            iz=1j*z;b=kap-rho*xi*iz;d=np.sqrt(b*b+xi*xi*(z*z+iz))
            g=(b-d)/(b+d);e=np.exp(-d*t)
            c=iz*(RATE-DIVIDEND)*t+kap*theta/xi**2*((b-d)*t-2*np.log((1-g*e)/(1-g)))
            dv=(b-d)/xi**2*(1-e)/(1-g*e)
            return np.exp(c+dv*v0)
        phase=np.exp(-1j*np.log(k[:,None])*u[None,:])/(1j*u[None,:])
        p1=.5+np.real(phase*cf(u-1j)/math.exp((RATE-DIVIDEND)*t))@weights/math.pi
        p2=.5+np.real(phase*cf(u))@weights/math.pi
        rows.append(math.exp(-DIVIDEND*t)*p1-k*math.exp(-RATE*t)*p2)
    return np.asarray(rows)


def hagan_call_grid(parameters):
    a,b,rho,nu=[parameters[key] for key in ('alpha','beta','rho','nu')]
    rows=[]
    for t in EXPIRIES:
        f=math.exp((RATE-DIVIDEND)*t);k=np.array(STRIKES)
        ell=np.log(f/k);fb=(f*k)**((1-b)/2);z=nu*fb/a*ell
        xx=np.log((np.sqrt(1-2*rho*z+z*z)+z-rho)/(1-rho))
        ratio=np.divide(z,xx,out=np.ones_like(z),where=np.abs(z)>1e-8)
        vol=a/fb/(1+(1-b)**2*ell**2/24+(1-b)**4*ell**4/1920)*ratio*(1+t*(
            (1-b)**2*a*a/(24*fb*fb)+rho*b*nu*a/(4*fb)+(2-3*rho*rho)*nu*nu/24))
        root=vol*math.sqrt(t);d1=(-np.log(k)+(RATE-DIVIDEND+.5*vol**2)*t)/root
        rows.append(math.exp(-DIVIDEND*t)*ndtr(d1)-k*math.exp(-RATE*t)*ndtr(d1-root))
    return np.asarray(rows)


def calibrate():
    target=SSVISurface()
    calls=np.array([target.vanillas(STRIKES,t)[0] for t in EXPIRIES])
    # Price-space loss expressed in approximate implied-vol units. A vega
    # floor avoids fitting vanishing option prices in poorly identified wings.
    vegas=[]
    for t in EXPIRIES:
        k=np.array(STRIKES);w=target.derivatives(np.log(k)-.01*t,t)[0]
        d1=-(np.log(k)-.01*t)/np.sqrt(w)+np.sqrt(w)/2
        vegas.append(np.maximum(.03,math.exp(-.02*t)*np.exp(-d1*d1/2)/
                                math.sqrt(2*math.pi)*math.sqrt(t)))
    vegas=np.array(vegas)
    report=dict(surface=target.certificate(),calibration_expiries=EXPIRIES,
                calibration_strikes=STRIKES,calibrations={})
    keys=('v0','theta','kappa','xi','rho_h')
    def hparams(x): return dict(PARAMETERS,**dict(zip(keys,x)))
    def hres(x): return ((heston_call_grid(hparams(x))-calls)/vegas).ravel()
    fit=least_squares(hres,[.04,.04,1.,.3,-.75],
                       bounds=([.005,.005,.05,.02,-.98],[.16,.16,12.,1.5,-.01]),
                       max_nfev=350,ftol=1e-9,xtol=1e-9,gtol=1e-9)
    heston=hparams(fit.x)
    prices=heston_call_grid(heston)
    independent=np.array([[heston_vanillas(k,t,heston)[0] for k in STRIKES] for t in EXPIRIES])
    if np.max(np.abs(prices-independent))>1e-6:
        raise ValueError('Heston calibration quadrature did not match independent reference')
    report['calibrations']['heston']=dict(parameters=heston,success=bool(fit.success),
        evaluations=int(fit.nfev),max_price_error_bp=float(np.max(np.abs(prices-calls))*10000),
        independent_reference_error_bp=float(np.max(np.abs(prices-independent))*10000))
    print('HESTON',report['calibrations']['heston'],flush=True)
    skeys=('alpha','beta','rho','nu')
    def sparams(x): return dict(PARAMETERS,**dict(zip(skeys,x)))
    bounds=([.05,0.,-.98,.001],[.5,1.,.1,1.5])
    bootstrap=least_squares(lambda x:((hagan_call_grid(sparams(x))-calls)/vegas).ravel(),
        [.2,.5,-.6,.4],bounds=bounds,max_nfev=250)
    print('SABR bootstrap only',sparams(bootstrap.x),flush=True)
    # Fit the SDE actually simulated, with fixed random numbers; Hagan only
    # initializes the optimizer and is not the final calibration oracle.
    evaluations=0
    def sres(x):
        nonlocal evaluations
        evaluations+=1
        legs=snapshots('sabr',sparams(x),sy=104,pairs=6000,seed=353)
        data=vanilla_statistics(legs)
        # OTM options remove sampled-forward noise from deep-ITM calls.
        mc=np.array([row['put']['price']+math.exp(-DIVIDEND*row['expiry'])
                     -row['strike']*math.exp(-RATE*row['expiry'])
                     if row['strike']<math.exp((RATE-DIVIDEND)*row['expiry'])
                     else row['call']['price'] for row in data]).reshape(len(EXPIRIES),len(STRIKES))
        if evaluations%10==0: print('SABR MC fit',evaluations,flush=True)
        return ((mc-calls)/vegas).ravel()
    fit_s=least_squares(sres,bootstrap.x,bounds=bounds,max_nfev=90,diff_step=.003,
                        ftol=1e-7,xtol=1e-7,gtol=1e-7)
    sabr=sparams(fit_s.x)
    report['calibrations']['sabr']=dict(parameters=sabr,success=bool(fit_s.success),
        evaluations=int(fit_s.nfev),mc_evaluations=evaluations,seed=353,sy=104,pairs=6000,
        max_in_sample_price_error_bp=float(np.max(np.abs(sres(fit_s.x).reshape(calls.shape)*vegas))*10000),
        bootstrap_parameters=sparams(bootstrap.x),note='Out-of-sample validation required')
    report['calibrations']['localvol']=dict(parameters=PARAMETERS,target=asdict(target),
                                          method='Analytic SSVI Dupire derivatives, no polynomial fallback')
    report['calibrations']['lsv']=dict(parameters=heston,target=asdict(target),
        method='Particle leverage on SSVI local volatility; variance parameters from fitted Heston')
    report['calibrations']['constant']=dict(parameters=dict(PARAMETERS,sigma=target.atm_vol),
        method='Forward ATM constant-volatility reference; no full-smile fit')
    (OUT/'calibration.json').write_text(json.dumps(report,indent=2))
    print('SABR final',report['calibrations']['sabr'],flush=True)
    return report


def athena_flows(levels,payment_times,coupon=.1,recall_barrier=1.,ki_barrier=.6):
    """European KI, accumulated coupons only at recall, including final date.

    Input is (observation,asset,path), initial fixings normalized to one.
    Capital and sold-put losses remain separate even on the same payment date.
    """
    worst=levels.min(axis=1)
    active=np.ones(worst.shape[1],dtype=bool)
    flows=[]
    for i,tpay in enumerate(payment_times):
        recalled=active & (worst[i]>=recall_barrier)
        coupon_flow=recalled.astype(float)*coupon*(i+1)
        capital=recalled.astype(float)
        put=np.zeros_like(capital)
        active &= ~recalled
        if i==len(payment_times)-1:
            capital+=active.astype(float)
            put=-active.astype(float)*(worst[i]<ki_barrier)*np.maximum(1-worst[i],0)
        flows.append(dict(observation=i+1,payment_time=tpay,
                          coupons=coupon_flow,capital=capital,put=put,
                          recall=recalled.astype(float)))
    capital_total=sum(x['capital'] for x in flows)
    if not np.all(capital_total==1.):
        raise ValueError('Every Athena path must repay exactly one capital leg')
    pv=sum(math.exp(-RATE*x['payment_time'])*(x['coupons']+x['capital']+x['put']) for x in flows)
    return pv,flows


def price_autocalls():
    calibration=json.loads((OUT/'calibration.json').read_text())
    target=SSVISurface(**calibration['surface']['parameters'])
    dates=contractual_dates()
    times=dates['observation_years'];payments=dates['payment_years']
    report=dict(surface=calibration['surface'],dates=dates,rate=RATE,dividend=DIVIDEND,
                correlation=.5,source='Synthetic common target; no live equity quotes',
                calibration=calibration['calibrations'],runs=[])
    seeds=(42,17,93,731,2026,77,123,991)
    combined=sorted(set(times+EXPIRIES))
    auto_indices=[combined.index(t) for t in times]
    vanilla_indices=[combined.index(t) for t in EXPIRIES]
    dt=times[-1]/round(times[-1]*208)
    effective_expiries=[round(t/dt)*dt for t in EXPIRIES]
    report['effective_vanilla_expiries']=effective_expiries
    for assets in (1,2):
        pairs=20000 if assets==1 else 10000
        for model in ('constant','heston','sabr','localvol','lsv'):
            parameters=calibration['calibrations'][model]['parameters']
            prices=[];pair_variances=[];flow_batches=[];validation_batches=[]
            for seed in seeds:
                print('AUTOCALL',assets,model,seed,flush=True)
                legs=snapshots(model,parameters,expiry=times[-1],sy=208,pairs=pairs,
                    assets=assets,seed=seed,target=target if model in ('localvol','lsv') else None,
                    observations=combined)
                validation_batches.append(vanilla_statistics([leg[vanilla_indices] for leg in legs],
                                                              effective_expiries))
                pa,fa=athena_flows(legs[0][auto_indices],payments)
                pb,fb=athena_flows(legs[1][auto_indices],payments)
                paired=(pa+pb)/2
                prices.append(float(paired.mean()))
                pair_variances.append(float(paired.var(ddof=1)/pairs))
                flow_batches.append([dict(observation=i+1,payment_time=payments[i],**{
                    kind:float(((a[kind]+b[kind])/2).mean()) for kind in ('capital','coupons','put','recall')})
                    for i,(a,b) in enumerate(zip(fa,fb))])
            mean=float(np.mean(prices))
            cluster_se=float(np.std(prices,ddof=1)/math.sqrt(len(prices)))
            paired_se=math.sqrt(sum(pair_variances))/len(prices)
            # Between independent batches also captures particle dependence.
            from scipy.stats import t as student_t
            half=float(student_t.ppf(.975,len(prices)-1))*cluster_se
            flows=[]
            for i in range(len(times)):
                item=dict(observation=i+1,observation_time=times[i],payment_time=payments[i])
                for kind in ('capital','coupons','put','recall'):
                    item[kind]=float(np.mean([batch[i][kind] for batch in flow_batches]))
                flows.append(item)
            legs_pv={kind:sum(math.exp(-RATE*x['payment_time'])*x[kind] for x in flows)
                     for kind in ('capital','coupons','put')}
            if abs(sum(legs_pv.values())-mean)>1e-12:
                raise ValueError('Athena component PVs do not reconcile to its price')
            run=dict(assets=assets,model=model,sy=208,pairs_per_batch=pairs,batches=len(seeds),
                     total_pairs=pairs*len(seeds),price_pct=100*mean,
                     cluster_se_bp=10000*cluster_se,paired_se_bp=10000*paired_se,
                     ci95_pct=[100*(mean-half),100*(mean+half)],
                     pv_legs_pct={k:100*v for k,v in legs_pv.items()},flows=flows,
                     batch_prices=prices,parameters=parameters,validation=[])
            for index,row in enumerate(validation_batches[0]):
                t,k=row['expiry'],row['strike']
                common=target.vanillas(k,t)
                own=black_scholes(k,t,.2) if model=='constant' else (
                    heston_vanillas(k,t,parameters) if model=='heston' else common)
                item={key:row[key] for key in ('expiry','strike','asset')}
                for kind,ref,common_ref in zip(('call','put','digital'),own,common):
                    estimates=np.array([batch[index][kind]['price'] for batch in validation_batches])
                    se=float(estimates.std(ddof=1)/math.sqrt(len(seeds)))
                    value=float(estimates.mean());tolerance=(10 if kind=='digital' else 2)/10000
                    item[kind]=dict(price=value,batch_se=se,common_target=float(common_ref),
                        common_error_bp=10000*(value-common_ref),own_reference=float(ref),
                        own_reference_kind='SSVI' if model in ('localvol','lsv') else
                            'pending calibrated SABR PDE' if model=='sabr' else 'exact model',
                        flagged=bool(abs(value-ref)>3*se+tolerance))
                run['validation'].append(item)
            report['runs'].append(run)
            (OUT/'autocalls.json').write_text(json.dumps(report,indent=2))
            print('PRICE',assets,model,run['price_pct'],run['ci95_pct'],flush=True)
    return report


def calibrated_reference():
    calibration=json.loads((OUT/'calibration.json').read_text())
    parameters=calibration['calibrations']['sabr']['parameters']
    dates=contractual_dates();horizon=dates['observation_years'][-1]
    dt=horizon/round(horizon*208)
    expiries=[round(t/dt)*dt for t in EXPIRIES]
    kwargs={k:parameters[k] for k in ('alpha','beta','rho','nu')}
    for name,settings in [('fine',dict(ds=.0125,dy=.075,y_width=3.6,steps_per_year=200)),
                           ('coarse',{}),('domain',dict(s_max=12.,y_width=4.))]:
        print('CALIBRATED SABR PDE',name,flush=True)
        rows=sabr_spot_pde(STRIKES,expiries,**kwargs,**settings)
        path=OUT/('calibrated_sabr_pde.json' if name=='fine' else 'calibrated_sabr_pde_'+name+'.json')
        data=dict(parameters=parameters,expiries=expiries,rows=rows) if name=='fine' else rows
        path.write_text(json.dumps(data,indent=2))


def finalize_results():
    path=OUT/'autocalls.json'
    report=json.loads(path.read_text())
    pde=json.loads((OUT/'calibrated_sabr_pde.json').read_text())
    coarse=json.loads((OUT/'calibrated_sabr_pde_coarse.json').read_text())
    domain=json.loads((OUT/'calibrated_sabr_pde_domain.json').read_text())
    if pde['parameters']!=report['calibration']['sabr']['parameters']:
        raise ValueError('Calibrated SABR PDE parameter mismatch')
    report['pde_convergence']=[]
    for ti,t in enumerate(pde['expiries']):
        for ki,k in enumerate(STRIKES):
            report['pde_convergence'].append(dict(expiry=t,strike=k,**{
                kind+'_mesh_bp':10000*(pde['rows'][ti][kind][ki]-coarse[ti][kind][ki])
                for kind in ('call','put','digital')},**{
                kind+'_domain_bp':10000*(coarse[ti][kind][ki]-domain[ti][kind][ki])
                for kind in ('call','put','digital')}))
    for run in report['runs']:
        if run['model']=='sabr':
            for row in run['validation']:
                ti=min(range(len(pde['expiries'])),key=lambda i:abs(pde['expiries'][i]-row['expiry']))
                if abs(row['expiry']-pde['expiries'][ti])>1e-6:
                    raise ValueError('Calibrated SABR reference expiry mismatch')
                ki=STRIKES.index(row['strike'])
                for kind in ('call','put','digital'):
                    value=row[kind];ref=pde['rows'][ti][kind][ki]
                    envelope=abs(ref-coarse[ti][kind][ki])+abs(coarse[ti][kind][ki]-domain[ti][kind][ki])
                    value['own_reference']=ref
                    value['own_reference_kind']='Independent calibrated spot SABR PDE'
                    value['pde_envelope_bp']=envelope*10000
                    value['flagged']=abs(value['price']-ref)>3*value['batch_se']+envelope+(10 if kind=='digital' else 2)/10000
        run['numerical_flags']={kind:sum(row[kind]['flagged'] for row in run['validation'])
                                for kind in ('call','put','digital')}
        run['calibration_max_error_bp']={kind:max(abs(row[kind]['own_reference']-row[kind]['common_target'])*10000
                                                 for row in run['validation']) for kind in ('call','put','digital')}
        run['recall_probabilities_pct']=[100*x['recall'] for x in run['flows']]
        run['early_recall_probability_pct']=sum(run['recall_probabilities_pct'][:-1])
        run['calibration_status']=('constant_vol_reference' if run['model']=='constant' else
            'parametric_fit_residual' if run['model'] in ('heston','sabr') else 'common_surface_reproduction')
        run['numerical_status']='residuals_to_review' if any(run['numerical_flags'].values()) else 'compatible_on_tested_grid'
    report['source_hashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (Path(__file__),Path(engine.__file__),ROOT/'backend/app/core/volatility_surface.py',
                  ROOT/'backend/scripts/vol_model_references.py')}
    from scipy.stats import t as student_t
    report['matched_surface_comparisons']=[]
    for assets in (1,2):
        lv=next(x for x in report['runs'] if x['model']=='localvol' and x['assets']==assets)
        lsv=next(x for x in report['runs'] if x['model']=='lsv' and x['assets']==assets)
        differences=np.array(lsv['batch_prices'])-np.array(lv['batch_prices'])
        mean=float(differences.mean());se=float(differences.std(ddof=1)/math.sqrt(differences.size))
        half=float(student_t.ppf(.975,differences.size-1))*se
        report['matched_surface_comparisons'].append(dict(assets=assets,comparison='LSV minus Local Vol',
            change_bp=10000*mean,batch_se_bp=10000*se,ci95_bp=[10000*(mean-half),10000*(mean+half)]))
    path.write_text(json.dumps(report,indent=2))
    print([(x['assets'],x['model'],x['numerical_flags'],x['calibration_max_error_bp']) for x in report['runs']],flush=True)
    return report


def price_convergence():
    calibration=json.loads((OUT/'calibration.json').read_text())
    target=SSVISurface(**calibration['surface']['parameters'])
    dates=json.loads((OUT/'autocalls.json').read_text())['dates']
    observations,payments=dates['observation_years'],dates['payment_years']
    horizon=observations[-1]
    report={'surface':calibration['surface'],'tolerance_bp':5.,'runs':[]}
    pairs=5000
    for assets in (1,2):
        for model in ('constant','heston','sabr','localvol','lsv'):
            differences=[];fine_prices=[]
            for seed in (42,17,93,731,2026,77,123,991):
                print('CONVERGENCE',assets,model,seed,flush=True)
                grids=[np.linspace(0,horizon,round(horizon*sy)+1) for sy in (104,208)]
                union=np.unique(np.concatenate(grids))
                rng=np.random.default_rng(seed)
                def brownian():
                    increments=rng.standard_normal((len(union)-1,assets,pairs))
                    increments*=np.sqrt(np.diff(union))[:,None,None]
                    np.cumsum(increments,axis=0,out=increments)
                    return np.concatenate((np.zeros((1,assets,pairs)),increments))
                spot_brownian=brownian();vol_brownian=brownian()
                values=[]
                for sy,grid in zip((104,208),grids):
                    idx=np.searchsorted(union,grid)
                    scale=math.sqrt(horizon/(len(grid)-1))
                    shocks=(np.diff(spot_brownian[idx],axis=0)/scale,
                            np.diff(vol_brownian[idx],axis=0)/scale)
                    legs=snapshots(model,calibration['calibrations'][model]['parameters'],
                        expiry=horizon,sy=sy,pairs=pairs,assets=assets,seed=seed,
                        target=target if model in ('localvol','lsv') else None,
                        observations=observations,shocks=shocks)
                    pa,_=athena_flows(legs[0],payments);pb,_=athena_flows(legs[1],payments)
                    values.append((pa+pb)/2)
                differences.append(float((values[1]-values[0]).mean()))
                fine_prices.append(float(values[1].mean()))
                del spot_brownian,vol_brownian,shocks,legs
                gc.collect()
            difference=float(np.mean(differences))
            se=float(np.std(differences,ddof=1)/math.sqrt(len(differences)))
            run=dict(assets=assets,model=model,coarse_sy=104,fine_sy=208,pairs_per_batch=pairs,
                     batches=8,change_bp=difference*10000,change_se_bp=se*10000,
                     flagged=bool(abs(difference)>3*se+.0005),
                     small_batch_fine_price_pct=float(np.mean(fine_prices))*100)
            report['runs'].append(run)
            (OUT/'convergence.json').write_text(json.dumps(report,indent=2))
            print(run,flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['precision','calibration','reference','pricing','convergence','finalize'],default='precision')
    args=parser.parse_args()
    OUT.mkdir(exist_ok=True,parents=True)
    {'precision':precision_study,'calibration':calibrate,'pricing':price_autocalls,
     'reference':calibrated_reference,'convergence':price_convergence,
     'finalize':finalize_results}[args.stage]()
