"""Explicit fits of editable SSVI assumptions; never labelled market quotes."""
import math
from functools import lru_cache

import numpy as np
from scipy.optimize import least_squares
from scipy.special import ndtr

from .volatility_surface import TermSSVISurface


@lru_cache(maxsize=1)
def quadrature():
    nodes, weights = np.polynomial.legendre.leggauss(256)
    return (nodes+1)*150, weights*150


def heston_calls(parameters, expiries, strikes, rate, dividend):
    u, weights = quadrature()
    k = np.asarray(strikes)
    v0, theta, kap, xi, rho = (parameters[key] for key in ('v0','theta','kappa','xi','rho_h'))
    result = []
    for t in expiries:
        def cf(z):
            iz=1j*z; b=kap-rho*xi*iz; d=np.sqrt(b*b+xi*xi*(z*z+iz))
            g=(b-d)/(b+d); e=np.exp(-d*t)
            c=iz*(rate-dividend)*t+kap*theta/xi**2*((b-d)*t-2*np.log((1-g*e)/(1-g)))
            dv=(b-d)/xi**2*(1-e)/(1-g*e)
            return np.exp(c+dv*v0)
        phase=np.exp(-1j*np.log(k[:,None])*u[None,:])/(1j*u[None,:])
        p1=.5+np.real(phase*cf(u-1j)/math.exp((rate-dividend)*t))@weights/math.pi
        p2=.5+np.real(phase*cf(u))@weights/math.pi
        result.append(math.exp(-dividend*t)*p1-k*math.exp(-rate*t)*p2)
    return np.asarray(result)


def calibrate_surface(payload, model, horizon, rate=.03, dividend=.02):
    surface = TermSSVISurface(payload)
    horizon = min(horizon, surface.max_expiry)
    expiries = sorted(set([min(t,horizon) for t in (.5,1.,2.,4.,horizon)]))
    strikes = np.array([.6,.8,1.,1.2,1.5])
    calls = np.array([surface.vanillas(strikes,t,rate,dividend)[0] for t in expiries])
    atm = math.sqrt(surface._theta(1.)[0])
    vegas=[]
    for t in expiries:
        w=surface.derivatives(np.log(strikes)-(rate-dividend)*t,t)[0]
        d1=-(np.log(strikes)-(rate-dividend)*t)/np.sqrt(w)+np.sqrt(w)/2
        vegas.append(np.maximum(.03, math.exp(-dividend*t)*np.exp(-d1*d1/2)/
                                math.sqrt(2*math.pi)*math.sqrt(t)))
    vegas=np.asarray(vegas)
    if model in ('heston','lsv'):
        keys=('v0','theta','kappa','xi','rho_h')
        initial=[atm**2,atm**2,1.,max(.15,atm),surface.rho]
        bounds=([.0001,.0001,.05,.01,-.98],[2.,2.,12.,3.,.98])
        evaluate=lambda x: heston_calls(dict(zip(keys,x)),expiries,strikes,rate,dividend)
        method='Fourier Heston'
    else:
        # Initialize from the target ATM level. The objective uses the same
        # spot SABR diffusion as pricing with fixed random numbers.
        from .payscript.engine import _simulate_sabr
        keys=('alpha','beta','rho','nu')
        initial=[atm,1.,surface.rho,.5]
        bounds=([.01,.05,-.98,.01],[2.,1.,.98,2.])
        ts=max(1,round(horizon*104)); dt=horizon/ts; pairs=3000
        rng=np.random.default_rng(353)
        z=rng.standard_normal((ts,1,pairs)); zv=rng.standard_normal(z.shape)
        indices=[round(t/dt) for t in expiries]
        # Quantized expiries match the simulator's grid.
        expiries=[i*dt for i in indices]
        calls=np.array([surface.vanillas(strikes,t,rate,dividend)[0] for t in expiries])
        def evaluate(x):
            params=dict(zip(keys,x),q=dividend)
            levels=[_simulate_sabr(ts,1,pairs,dt,math.sqrt(dt),[params],rate,
                                  np.eye(1),sgn*z,sgn*zv)[indices,0] for sgn in (1.,-1.)]
            rows=[]
            for i,t in enumerate(expiries):
                a,b=(v[i,:,None] for v in levels)
                call=.5*(np.maximum(a-strikes,0)+np.maximum(b-strikes,0)).mean(axis=0)*math.exp(-rate*t)
                put=.5*(np.maximum(strikes-a,0)+np.maximum(strikes-b,0)).mean(axis=0)*math.exp(-rate*t)
                rows.append(np.where(strikes<math.exp((rate-dividend)*t),
                        put+math.exp(-dividend*t)-strikes*math.exp(-rate*t),call))
            return np.array(rows)
        method='SABR spot MC, 3 000 paires, 104 pas/an, graine 353'
    fit=least_squares(lambda x: ((evaluate(x)-calls)/vegas).ravel(),initial,
                      bounds=bounds,max_nfev=65,diff_step=.003,
                      ftol=1e-6,xtol=1e-6,gtol=1e-6)
    prices=evaluate(fit.x)
    if not np.all(np.isfinite(prices)):
        raise ValueError('La calibration a produit des prix non finis.')
    error=float(np.max(np.abs(prices-calls))*10000)
    return dict(parameters=dict(zip(keys,map(float,fit.x))),max_price_error_bp=error,
                method=method,approximate=True,success=bool(fit.success),
                note='Ajustement paramétrique indicatif ; l’erreur est distincte de l’incertitude de pricing.')
