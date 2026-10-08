"""Offline numerical oracles. No imports from the production pricing engine.

The SABR solver uses the spot convention dS=(r-q)S dt+alpha S**beta dW,
dalpha=nu alpha dZ, and absorption at S=0. It is a diagnostic, not a
calibration service: both mesh and domain convergence must be checked.
"""
import cmath
import math

import numpy as np
from scipy import sparse
from scipy.integrate import quad
from scipy.sparse.linalg import splu
from scipy.special import ndtr
from scipy.stats import ncx2


def black_scholes(strike, expiry, volatility, rate=0.03, dividend=0.02):
    root = volatility * math.sqrt(expiry)
    d1 = (-math.log(strike) + (rate-dividend+volatility**2/2)*expiry)/root
    d2 = d1-root
    call = math.exp(-dividend*expiry)*ndtr(d1)-strike*math.exp(-rate*expiry)*ndtr(d2)
    put = strike*math.exp(-rate*expiry)*ndtr(-d2)-math.exp(-dividend*expiry)*ndtr(-d1)
    digital = math.exp(-rate*expiry)*ndtr(-d2)
    return float(call), float(put), float(digital)


def cev_zero_carry(strike, expiry, alpha, beta, rate=0.03):
    """Absorbing CEV exact law, beta in [0,1), unit initial spot, r=q.

    Noncentral chi-square representation also used by QuantLib's CEVCalculator.
    """
    if not 0 <= beta < 1 or alpha <= 0 or expiry <= 0 or strike <= 0:
        raise ValueError("Invalid absorbing CEV domain")
    delta = (1-2*beta)/(1-beta)
    x = 1/(alpha*(1-beta))**2/expiry
    k = strike**(2*(1-beta))*x
    df = math.exp(-rate*expiry)
    call = df*(ncx2.sf(k, 4-delta, x)-strike*ncx2.cdf(x, 2-delta, k))
    put = df*(-ncx2.cdf(k, 4-delta, x)+strike*ncx2.sf(x, 2-delta, k))
    return float(call), float(put)


def heston_vanillas(strike, expiry, parameters, rate=0.03, dividend=0.02,
                    integration_bound=200.):
    """Unit-spot Heston Fourier inversion; digital is discounted (1-P2)."""
    v0, theta, kappa, xi, rho = [parameters[x]
                                for x in ('v0','theta','kappa','xi','rho_h')]
    forward = math.exp((rate-dividend)*expiry)
    def cf(u):
        iu = 1j*u
        b = kappa-rho*xi*iu
        d = cmath.sqrt(b*b+xi*xi*(u*u+iu))
        g = (b-d)/(b+d)
        e = cmath.exp(-d*expiry)
        c = iu*(rate-dividend)*expiry+kappa*theta/xi**2*(
            (b-d)*expiry-2*cmath.log((1-g*e)/(1-g)))
        dv = (b-d)/xi**2*(1-e)/(1-g*e)
        return cmath.exp(c+dv*v0)
    def probability(shifted):
        def integrand(u):
            phi = cf(u-1j)/forward if shifted else cf(u)
            return (cmath.exp(-1j*u*math.log(strike))*phi/(1j*u)).real
        return .5+quad(integrand,0.,integration_bound,epsabs=1e-10,
                       epsrel=1e-10,limit=500)[0]/math.pi
    p1, p2 = probability(True), probability(False)
    df = math.exp(-rate*expiry)
    call = math.exp(-dividend*expiry)*p1-strike*df*p2
    return call, call-math.exp(-dividend*expiry)+strike*df, df*(1-p2)


def sabr_spot_pde(strikes, expiries, *, alpha=0.2, beta=0.5, rho=-0.6,
                  nu=0.5, rate=0.03, dividend=0.02, ds=0.025,
                  s_max=6., dy=0.1, y_width=3.5, steps_per_year=100):
    """Backward 2D finite differences in (S, log(alpha/alpha0)).

    Crank-Nicolson with four implicit half-steps at the payoff discontinuity.
    Dirichlet S boundaries, reflecting log-vol boundaries. Interior mixed
    derivatives use a central nine-point stencil. Digital payoffs are averaged
    in the cell containing the strike. No production clipping is reproduced.
    Returns discounted calls, puts and below-strike cash digitals.
    """
    strikes = np.asarray(strikes, dtype=float)
    expiries = np.asarray(expiries, dtype=float)
    if (alpha <= 0 or not 0 <= beta <= 1 or nu < 0 or abs(rho) > 1
            or np.any(strikes <= 0) or np.any(expiries <= 0)
            or ds <= 0 or dy <= 0 or steps_per_year <= 0
            or s_max <= max(1., float(strikes.max())) or y_width <= 0):
        raise ValueError("Invalid SABR reference domain")
    ns = round(s_max/ds)+1
    ny = 2*round(y_width/dy)+1
    ds = s_max/(ns-1)
    dy = 2*y_width/(ny-1)
    ni = ns-2
    size = ni*ny
    nt = math.ceil(float(expiries.max())*steps_per_year)
    if size > 80000 or nt > 1600 or len(strikes) > 20:
        raise ValueError("Offline PDE reference exceeds its bounded resource grid")
    s = np.linspace(0., s_max, ns)[1:-1]
    y = np.linspace(-y_width, y_width, ny)
    # Flatten with S as the fast axis; boundary forcing is kept separate.
    rr, cc, vv = [], [], []
    lower = np.zeros(size)
    upper = np.zeros(size)
    def add(row, j, i, value):
        if i < 0:
            lower[row] += value
        elif i >= ni:
            upper[row] += value
        else:
            rr.append(row); cc.append(j*ni+i); vv.append(value)
    for j in range(ny):
        a = alpha*math.exp(y[j])
        for i, spot in enumerate(s):
            row = j*ni+i
            diffusion = .5*a*a*spot**(2*beta)/ds**2
            drift = (rate-dividend)*spot/(2*ds)
            add(row,j,i-1,diffusion-drift)
            add(row,j,i+1,diffusion+drift)
            add(row,j,i,-2*diffusion-nu*nu/dy**2)
            ay = .5*nu*nu/dy**2
            by = -.5*nu*nu/(2*dy)
            if j == 0:
                add(row,j+1,i,2*ay)
            elif j == ny-1:
                add(row,j-1,i,2*ay)
            else:
                add(row,j-1,i,ay-by)
                add(row,j+1,i,ay+by)
                mixed = rho*nu*a*spot**beta/(4*ds*dy)
                for dj, di in [(-1,-1),(1,1),(-1,1),(1,-1)]:
                    add(row,j+dj,i+di,mixed*dj*di)
    operator = sparse.csc_matrix((vv,(rr,cc)),shape=(size,size))
    identity = sparse.eye(size,format='csc')
    k = strikes[None,:]
    payoff = np.concatenate((np.maximum(s[:,None]-k,0),
                             np.maximum(k-s[:,None],0),
                             np.clip((k-s[:,None])/ds+.5,0,1)),axis=1)
    values = np.tile(payoff,(ny,1))
    count = len(strikes)
    def forcing(t):
        lo = np.concatenate((np.zeros(count),strikes,np.ones(count)))
        hi = np.concatenate((s_max*math.exp((rate-dividend)*t)-strikes,
                             np.zeros(2*count)))
        return lower[:,None]*lo+upper[:,None]*hi
    time = 0.
    results = []
    cache = {}
    for expiry in expiries:
        if expiry < time:
            raise ValueError("Reference expiries must be increasing")
        while time < expiry-1e-12:
            dt = min(1/steps_per_year, expiry-time)
            half = time < 2/steps_per_year-1e-12
            if half:
                dt = min(dt,.5/steps_per_year)
            theta = 1. if half else .5
            key = (round(dt,12),theta)
            if key not in cache:
                cache[key] = splu(identity-theta*dt*operator)
            rhs = values+(1-theta)*dt*(operator@values+forcing(time))
            rhs += theta*dt*forcing(time+dt)
            values = cache[key].solve(rhs)
            time += dt
        center = values[(ny//2)*ni:(ny//2+1)*ni]
        price = np.array([np.interp(1.,s,center[:,i])
                          for i in range(3*count)])*math.exp(-rate*expiry)
        results.append({'expiry':float(expiry), 'call':price[:count].tolist(),
                        'put':price[count:2*count].tolist(),
                        'digital':price[2*count:].tolist()})
    return results
