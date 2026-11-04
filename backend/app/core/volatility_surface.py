"""Indicative SSVI targets for editable assumptions and offline comparisons.

This module is not a market-data loader or an automatic deal calibration.
Targets use forward log-moneyness, with flat or piecewise-linear ATM variance and
phi(theta)=eta/sqrt(shape_scale+theta). Sufficient Gatheral-Jacquier conditions are
checked over the entire declared maturity horizon, for every strike.
"""
from dataclasses import asdict, dataclass
import math

import numpy as np
from scipy.optimize import brentq
from scipy.special import ndtr


@dataclass(frozen=True)
class SSVISurface:
    atm_vol: float = .20
    rho: float = -.75
    eta: float = .85
    shape_scale: float = .04
    max_expiry: float = 5.

    def __post_init__(self):
        if (not all(math.isfinite(x) for x in asdict(self).values())
                or self.atm_vol <= 0 or abs(self.rho) >= 1
                or self.eta < 0 or self.shape_scale <= 0 or self.max_expiry <= 0):
            raise ValueError("Invalid SSVI parameter domain")
        theta = self.atm_vol**2*self.max_expiry
        phi = self.eta/math.sqrt(self.shape_scale+theta)
        # Both left-hand sides increase with theta for this phi family.
        if theta*phi*(1+abs(self.rho)) >= 4:
            raise ValueError("SSVI wing slope violates sufficient no-arbitrage condition")
        if theta*phi**2*(1+abs(self.rho)) > 4:
            raise ValueError("SSVI curvature violates sufficient no-arbitrage condition")
        # d(theta*phi)/dtheta / phi lies in [1/2,1], below the
        # calendar bound (1+sqrt(1-rho**2))/rho**2, at least 1.

    def derivatives(self, log_forward_moneyness, expiry):
        if not math.isfinite(expiry) or not 0 < expiry <= self.max_expiry:
            raise ValueError("Expiry outside the certified SSVI horizon")
        k = np.asarray(log_forward_moneyness,dtype=float)
        if not np.all(np.isfinite(k)):
            raise ValueError("Non-finite SSVI log-moneyness")
        theta = self.atm_vol**2*expiry
        phi = self.eta/math.sqrt(self.shape_scale+theta)
        dphi = -.5*phi/(self.shape_scale+theta)
        z = phi*k+self.rho
        root = np.sqrt(z*z+1-self.rho**2)
        base = 1+self.rho*phi*k+root
        w = .5*theta*base
        wk = .5*theta*phi*(self.rho+z/root)
        wkk = .5*theta*phi**2*(1-self.rho**2)/root**3
        wt = self.atm_vol**2*(.5*base+.5*theta*k*dphi*(self.rho+z/root))
        return w,wk,wkk,wt

    def density_factor(self, log_forward_moneyness, expiry):
        k = np.asarray(log_forward_moneyness,dtype=float)
        w,wk,wkk,_ = self.derivatives(k,expiry)
        return (1-k*wk/(2*w))**2-wk**2/4*(1/w+.25)+.5*wkk

    def local_vol(self, log_forward_moneyness, expiry):
        *_,wt = self.derivatives(log_forward_moneyness,expiry)
        g = self.density_factor(log_forward_moneyness,expiry)
        if np.any(g <= 0) or np.any(wt <= 0):
            raise ValueError("Invalid SSVI density or calendar derivative; no fallback")
        return np.sqrt(wt/g)

    def vanillas(self, strikes, expiry, rate=.03, dividend=.02):
        strikes = np.asarray(strikes,dtype=float)
        if np.any(strikes <= 0) or not np.all(np.isfinite(strikes)):
            raise ValueError("Invalid SSVI strikes")
        k = np.log(strikes)-(rate-dividend)*expiry
        w,wk,_,_ = self.derivatives(k,expiry)
        root = np.sqrt(w)
        d1 = -k/root+root/2
        d2 = d1-root
        df = math.exp(-rate*expiry)
        prepaid = math.exp(-dividend*expiry)
        call = prepaid*ndtr(d1)-strikes*df*ndtr(d2)
        put = strikes*df*ndtr(-d2)-prepaid*ndtr(-d1)
        vega = prepaid*np.exp(-d1*d1/2)/math.sqrt(2*math.pi)*math.sqrt(expiry)
        # Cash put digital is dP/dK, including the smile slope.
        sigma_derivative = wk/(2*np.sqrt(w*expiry)*strikes)
        digital = df*ndtr(-d2)+vega*sigma_derivative
        return call,put,digital

    def local_grid(self, expiries, rate=.03, dividend=.02, nodes=400):
        expiries = np.asarray(expiries,dtype=float)
        lo,hi = math.log(.01),math.log(10.)
        log_spots = np.linspace(lo,hi,nodes)
        grid = np.array([self.local_vol(log_spots-(rate-dividend)*t,t)
                         for t in expiries],dtype=np.float64)
        if not np.all(np.isfinite(grid)) or np.any(grid <= 0):
            raise ValueError("Invalid SSVI local-vol grid")
        # Production simulators cap effective LV at 3; reject an unsupported
        # target rather than silently feeding a clipped calibration.
        if np.any(grid > 3.):
            raise ValueError("SSVI target exceeds simulator local-vol domain")
        return grid,nodes,lo,hi

    def certificate(self):
        theta=self.atm_vol**2*self.max_expiry
        phi=self.eta/math.sqrt(self.shape_scale+theta)
        return dict(parameters=asdict(self),source='Synthetic assumption, not market data',
                    butterfly_slope_bound=theta*phi*(1+abs(self.rho)),
                    butterfly_curvature_bound=theta*phi**2*(1+abs(self.rho)),
                    sufficient_limit=4.,calendar_monotone=True,
                    citation='https://arxiv.org/abs/1204.0646')


class TermSSVISurface(SSVISurface):
    """SSVI with increasing piecewise-linear forward ATM total variance.

    A common rho and either the original eta profile or certified psi knots
    preserve the sufficient all-strike calendar conditions.
    """

    def __init__(self, payload):
        self.nodes = np.asarray(payload['atm_nodes'], dtype=float)
        if (self.nodes.ndim != 2 or self.nodes.shape[1] != 2 or len(self.nodes) < 1
                or not np.all(np.isfinite(self.nodes)) or np.any(self.nodes <= 0)
                or np.any(np.diff(self.nodes[:, 0]) <= 0)):
            raise ValueError('Les piliers ATM doivent être positifs, finis et croissants en maturité.')
        self.thetas = self.nodes[:, 0] * self.nodes[:, 1]**2
        if np.any(np.diff(self.thetas) <= 0):
            raise ValueError('La variance totale ATM doit être strictement croissante entre maturités.')
        horizon = float(payload.get('max_expiry', max(10., self.nodes[-1, 0])))
        # Parent certificate uses the terminal total variance; derivative
        # evaluation below uses the full term structure.
        terminal = self._theta(horizon)[0]
        super().__init__(atm_vol=math.sqrt(terminal/horizon),
                         rho=float(payload['rho']), eta=float(payload['eta']),
                         shape_scale=float(payload.get('shape_scale', .04)), max_expiry=horizon)
        self.wings = None
        if payload.get('wing_nodes') is not None:
            self.wings = np.asarray(payload['wing_nodes'], dtype=float)
            if (self.wings.ndim != 2 or self.wings.shape[1] != 2 or not len(self.wings)
                    or not np.all(np.isfinite(self.wings)) or np.any(self.wings[:, 0] <= 0)
                    or np.any(np.diff(self.wings[:, 0]) <= 0) or self.wings[-1, 0] > horizon):
                raise ValueError('Maturités des piliers d’aile invalides.')
            self.wing_theta = np.array([self._theta(t)[0] for t in self.wings[:, 0]])
            psi = self.wings[:, 1]
            factor = 1 + abs(self.rho)
            if (np.any(psi < 0) or np.any(np.diff(psi) < -1e-12)
                    or np.any(np.diff(psi / self.wing_theta) > 1e-12)
                    or np.any(psi * factor >= 4)
                    or np.any(psi**2 / self.wing_theta * factor > 4)):
                raise ValueError('Piliers d’aile incompatibles avec les bornes SSVI sans arbitrage.')

    def _phi(self, theta):
        if self.wings is None:
            phi = self.eta/math.sqrt(self.shape_scale+theta)
            return phi, -.5*phi/(self.shape_scale+theta)
        # Linear psi=theta*phi in theta preserves nondecreasing psi and
        # nonincreasing phi. Butterfly bounds hold at the knots and between them
        # by convexity of psi²/theta; beyond the last knot psi stays constant.
        ts = self.wing_theta
        ps = self.wings[:, 1]
        i = np.searchsorted(ts, theta, side='right')
        if i == 0:
            return ps[0]/ts[0], 0.
        if i == len(ts):
            psi, slope = ps[-1], 0.
        else:
            slope = (ps[i]-ps[i-1])/(ts[i]-ts[i-1])
            psi = ps[i-1]+slope*(theta-ts[i-1])
        return psi/theta, (slope-psi/theta)/theta

    def _theta(self, t):
        times = np.r_[0., self.nodes[:, 0]]
        values = np.r_[0., self.thetas]
        index = min(np.searchsorted(times, t, side='right'), len(times)-1)
        if t >= times[-1]:
            slope = values[-1]/times[-1]
            return values[-1]+slope*(t-times[-1]), slope
        slope = (values[index]-values[index-1])/(times[index]-times[index-1])
        return values[index-1]+slope*(t-times[index-1]), slope

    def derivatives(self, log_forward_moneyness, expiry):
        if not math.isfinite(expiry) or not 0 < expiry <= self.max_expiry:
            raise ValueError('Maturité hors de l’horizon de la surface.')
        k = np.asarray(log_forward_moneyness, dtype=float)
        if not np.all(np.isfinite(k)):
            raise ValueError('Strike non fini dans la surface.')
        theta, slope = self._theta(expiry)
        phi, dphi = self._phi(theta)
        z = phi*k+self.rho
        root = np.sqrt(z*z+1-self.rho**2)
        base = 1+self.rho*phi*k+root
        w = .5*theta*base
        wk = .5*theta*phi*(self.rho+z/root)
        wkk = .5*theta*phi**2*(1-self.rho**2)/root**3
        wt = slope*(.5*base+.5*theta*k*dphi*(self.rho+z/root))
        return w, wk, wkk, wt

    def implied_vol(self, moneyness, expiry):
        return np.sqrt(self.derivatives(np.log(moneyness), expiry)[0]/expiry)

    def certificate(self):
        result=super().certificate()
        result['parameters']['atm_nodes']=self.nodes.tolist()
        result['interpolation']='Increasing piecewise-linear ATM total variance'
        if self.wings is not None:
            psi = self.wings[:, 1]
            factor = 1 + abs(self.rho)
            result['parameters']['wing_nodes'] = self.wings.tolist()
            result['wing_interpolation'] = 'Piecewise-linear theta*phi in ATM total variance'
            result['butterfly_slope_bound'] = float(max(psi)*factor)
            result['butterfly_curvature_bound'] = float(max(psi**2/self.wing_theta)*factor)
        return result


def surface_from_underlying(underlying, horizon=None):
    payload = underlying.get('vol_surface')
    if not payload:
        return None
    payload = dict(payload)
    # Sigma scenarios and realized refreshes change the reference level. The
    # entire target follows that explicit level change, retaining its shape.
    current=TermSSVISurface(payload)
    reference=math.sqrt(current._theta(1.)[0])
    requested=underlying.get('sigma',reference)
    if abs(requested-reference)>1e-10:
        if requested<=0 or not math.isfinite(requested):
            raise ValueError('Le niveau de vol de la surface doit être strictement positif.')
        payload['atm_nodes']=[[t,v*requested/reference] for t,v in payload['atm_nodes']]
    if horizon is not None:
        payload['max_expiry'] = max(payload.get('max_expiry', 10.), horizon)
    return TermSSVISurface(payload)


def fit_left_wing(payload, expiry, strike, target, horizon, rate, dividend):
    """Raise one left-wing target while changing other wing knots only as needed."""
    base = TermSSVISurface(payload)
    horizon = max(horizon, expiry)
    if expiry > base.max_expiry:
        raise ValueError('La cible est hors de l’horizon de la surface.')
    current = float(base.implied_vol(strike, expiry))
    if target <= current + 1e-7:
        return payload, current, 'already_at_or_above'

    times = sorted(set(base.nodes[:, 0]) | {expiry, base.max_expiry}
                   | (set(base.wings[:, 0]) if base.wings is not None else set()))
    if len(times) > 64:
        raise ValueError('La surface contient trop de piliers d’aile.')
    theta = np.array([base._theta(t)[0] for t in times])
    psi = np.array([w*base._phi(w)[0] for w in theta])
    i = times.index(expiry)
    factor = 1+abs(base.rho)
    caps = np.minimum((4-1e-8)/factor, np.sqrt((4-1e-8)*theta/factor))
    ceiling = min(np.min(caps[i:]), np.min(caps[:i+1]*theta[i]/theta[:i+1]))

    # A raised knot requires at least the same psi afterwards and the same phi
    # beforehand. The pointwise maximum preserves both calendar inequalities.
    weights = np.minimum(1., theta/theta[i])
    def candidate(level):
        return {**payload, 'mode': 'manual',
                'wing_nodes': list(zip(times, np.maximum(psi, level*weights).tolist()))}

    if ceiling <= psi[i]:
        return payload, current, 'ssvi'
    log_strike = math.log(strike)
    def point_vol(level):
        x = level/theta[i]*log_strike
        w = .5*theta[i]*(1+base.rho*x+math.sqrt((x+base.rho)**2+1-base.rho**2))
        return math.sqrt(w/expiry)

    upper = ceiling
    reason = 'ssvi'
    if point_vol(upper) >= target:
        upper = brentq(lambda level: point_vol(level)-target, psi[i], upper)
        reason = 'target'

    # Check the pricing grid at both resolutions, plus both sides of knots.
    # Leave a small margin for changes in the valuation time grid. The engine
    # also checks the grid of the actual valuation at runtime.
    knots = [t for t in times if t < horizon]
    checks = np.array(sorted({1e-5, horizon, *knots, *(t-1e-7 for t in knots if t > 1e-7),
                              *(t+1e-7 for t in knots if t+1e-7 < horizon)}))
    for resolution in (52, 104):
        n = max(1, round(resolution*horizon))
        checks = np.r_[checks, (np.arange(n)+.5)*horizon/n]
    spots = np.linspace(math.log(.01), math.log(10.), 300)
    def accepted(level):
        proposal = candidate(level)
        surface = TermSSVISurface({**proposal, 'max_expiry': max(base.max_expiry, horizon)})
        try:
            for t in checks:
                local = surface.local_vol(spots-(rate-dividend)*t, t)
                if np.any(~np.isfinite(local)) or np.any(local > 2.995):
                    return None
        except ValueError:
            return None
        return proposal

    proposal = accepted(upper)
    if proposal is None:
        lo, hi = psi[i], upper
        proposal = accepted(lo)
        if proposal is None:
            return payload, current, 'dupire'
        for _ in range(17):
            mid = (lo+hi)/2
            trial = accepted(mid)
            if trial is None:
                hi = mid
            else:
                lo, proposal = mid, trial
        upper, reason = lo, 'dupire'
    achieved = point_vol(upper)
    if achieved <= current + 1e-6:
        return payload, current, reason
    return proposal, achieved, reason
