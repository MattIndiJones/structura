"""Explicit synthetic market source for private acceptance installations only."""
from datetime import date, datetime, timedelta
import json
import math
import os
from pathlib import Path
import random
from ..runtime import business_today

PROVIDER = 'SYNTHETIC_SCENARIO'


def configured_path():
    value = os.environ.get('STRUCTURA_SCENARIO_MARKET')
    # Environment-level configuration cannot be enabled by an HTTP request.
    return Path(value) if value and os.environ.get('STRUCTURA_WORKSHOP_CHILD') == '1' else None


def create_market(path, start, seed, months=24):
    """Reproducible daily scenario; no realized or implied market claim."""
    origin = date.fromisoformat(start) - timedelta(days=365)
    end = date.fromisoformat(start) + timedelta(days=months*32+365)
    rng = random.Random(seed)
    rows = {}; spot = 100.0
    cursor = origin
    while cursor <= end:
        if cursor.weekday() < 5:
            spot *= math.exp((.025-.02-.5*.23**2)/252 + .23*math.sqrt(1/252)*rng.gauss(0,1))
            rows[cursor.isoformat()] = round(spot,8)
        cursor += timedelta(days=1)
    path.write_text(json.dumps({'provider':PROVIDER,'seed':seed,'series':{'AIR.PA':rows},
        'method':'Synthetic GBM scenario, r=2.5%, q=2%, sigma=23%; not historical data',
        'currencies':{'AIR.PA':'EUR'}}, ensure_ascii=False),encoding='utf-8')


def history(tickers, start, end=None, adjusted=False, *, path=None, as_of=None):
    path = path or configured_path()
    if not path:
        raise ValueError('Aucun marché de scénario configuré.')
    today = as_of or business_today()
    requested = date.fromisoformat(end) if end else today
    if requested > today:
        return {'error':'Le scénario ne fournit aucune donnée future.', 'provider':PROVIDER}
    data = json.loads(path.read_text(encoding='utf-8'))
    series = data['series']
    if any(t not in series for t in tickers):
        return {'error':'Ticker absent du marché synthétique.', 'provider':PROVIDER}
    dates = sorted(set.intersection(*[{d for d in series[t] if start <= d <= requested.isoformat()} for t in tickers])) if tickers else []
    if not dates:
        return {'error':'Aucune observation synthétique dans la fenêtre demandée.', 'provider':PROVIDER}
    return {'dates':dates, 'prices':{t:[series[t][d] for d in dates] for t in tickers},
        'provider':PROVIDER, 'price_type':'SYNTHETIC_ADJUSTED_PROXY' if adjusted else 'SYNTHETIC_RAW_CLOSE',
        'adjusted':adjusted, 'requested_start':start,'requested_asof':requested.isoformat(),
        'asof_effective':dates[-1],'effective_dates':{t:dates[-1] for t in tickers},
        'age_sessions':{t:0 for t in tickers}, 'fetched_at':datetime.utcnow().isoformat(),
        'warnings':[{'code':'SYNTHETIC_DATA','message':data['method']}]}
