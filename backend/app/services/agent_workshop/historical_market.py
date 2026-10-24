"""Read existing local price series and freeze their observations for replay."""
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

from ...runtime import data_path
from ...core import market_storage
from ...core.amc_prices import _slug


def cache_roots():
    return list(dict.fromkeys([data_path('underlying_prices'),
                              Path(__file__).resolve().parents[3] / 'data' / 'underlying_prices']))


def market_path(directory, config):
    return Path(directory) / ('historical_market.json' if config.get('market_mode')=='historical' else 'synthetic_market.json')


def cached_series(ticker, roots=None):
    """Reuse the price store's ticker map; never download or alter its files."""
    for root in roots or cache_roots():
        root = Path(root)
        with market_storage.store_context(root.resolve().parent), market_storage.read_view():
            mapping_path = market_storage.current_path(root/'_ticker_map.json')
            mapping = json.loads(mapping_path.read_text(encoding='utf-8')) if mapping_path.exists() else {}
            keys = [k for k, v in mapping.items() if str(v).upper() == ticker.upper()]
            keys += [ticker, ticker.split('.')[0]]
            for key in dict.fromkeys(keys):
                path = market_storage.current_path(root/(_slug(key)+'.parquet'))
                if not path.exists() and re.fullmatch(r'[A-Za-z0-9_\-]{1,80}',key.strip()):
                    path = market_storage.current_path(root/(key.strip()+'.parquet'))
                if not path.exists():
                    continue
                frame = pd.read_parquet(path)
                column = 'price_close' if 'price_close' in frame else 'close'
                if column not in frame:
                    continue
                series = frame[column].dropna().sort_index()
                series = series[series > 0]
                series.index = pd.to_datetime(series.index).tz_localize(None)
                if series.empty:
                    continue
                return series, {'ticker': ticker, 'cache_file': str(path.resolve()),
                                'source': frame.attrs.get('source', 'existing_local_cache'),
                                'price_basis': 'RAW_CLOSE' if column == 'price_close' else 'STORED_CLOSE',
                                'column': column, 'currency': frame.attrs.get('currency', 'EUR'),
                                'first_date': series.index[0].date().isoformat(),
                                'last_date': series.index[-1].date().isoformat(),
                                'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    raise ValueError(f'Aucun cours conservé pour {ticker}. Renseignez un cours explicite ou choisissez un sous-jacent du cache.')


def sources(config, roots=None):
    rows, warnings = [], []
    for ticker in sorted({t for p in config['products'] for t in p['tickers']}):
        try:
            _, info = cached_series(ticker, roots)
            rows.append(info)
            if info['price_basis'] == 'STORED_CLOSE':
                warnings.append(f'{ticker} : close du cache existant ; aucun cours brut distinct disponible.')
            if info['last_date'] < config['end_date']:
                warnings.append(f'{ticker} : dernier cours du cache au {info["last_date"]}, repris aux dates suivantes.')
        except ValueError as exc:
            rows.append({'ticker': ticker, 'price_basis': 'EXPLICIT_SPOT', 'available': False})
            warnings.append(str(exc))
    return rows, warnings


def freeze_market(path, config, roots=None):
    """Copy only existing observations, keeping hashes, basis and dates."""
    series, provenance, overrides = {}, {}, {}
    start = date.fromisoformat(config['start_date']) - timedelta(days=366)
    end = date.fromisoformat(config['end_date'])
    for product in config['products']:
        overrides.update(product.get('spot_overrides', {}))
    for ticker in sorted({t for p in config['products'] for t in p['tickers']}):
        try:
            prices, info = cached_series(ticker, roots)
        except ValueError:
            if ticker not in overrides:
                raise
            series[ticker] = {}
            provenance[ticker] = {'ticker': ticker, 'price_basis': 'EXPLICIT_SPOT'}
            continue
        prices = prices[prices.index.date <= end]
        # Retain the last observation preceding the lookback, even for a sparse cache.
        before = prices[prices.index.date < start].tail(1)
        window = prices[prices.index.date >= start]
        selected = pd.concat([before, window])
        series[ticker] = {d.date().isoformat(): float(v) for d, v in selected.items()}
        provenance[ticker] = info
    data = {'provider': 'HISTORICAL_CACHE', 'method': 'Existing local observations; last known close on or before the replay date',
            'series': series, 'provenance': provenance, 'spot_overrides': overrides,
            'cutoff': config['end_date'], 'currencies': {t: p.get('currency', 'EUR') for t, p in provenance.items()}}
    Path(path).write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    return provenance


def historical_history(data, tickers, start, requested, adjusted=False):
    """As-of joins preserve actual observation dates; no backward filling."""
    cutoff = min(requested, data['cutoff'])
    selected, overrides = {}, data.get('spot_overrides', {})
    for ticker in tickers:
        values = {d: v for d, v in data['series'].get(ticker, {}).items() if d <= cutoff}
        if not values and ticker not in overrides:
            return {'error': f'Aucun cours connu pour {ticker} au {cutoff}.', 'provider': data['provider']}
        selected[ticker] = values
    dates = sorted({d for v in selected.values() for d in v if start <= d <= cutoff})
    if not dates:
        dates = [max((d for v in selected.values() for d in v), default=cutoff)]
    if cutoff not in dates:
        dates.append(cutoff)
    # Each asset must have a known spot; do not borrow later observations for a leading gap.
    dates = [d for d in dates if all(t in overrides or any(k <= d for k in selected[t]) for t in tickers)]
    if not dates:
        return {'error': 'Aucune date commune avec des cours déjà connus.', 'provider': data['provider']}
    prices, effective, warnings = {}, {}, []
    for ticker in tickers:
        if not selected[ticker] and ticker in overrides:
            prices[ticker] = [overrides[ticker]] * len(dates)
            effective[ticker] = cutoff
            warnings.append({'code': 'EXPLICIT_SPOT', 'message': f'{ticker} : cours explicitement renseigné.'})
        else:
            items = sorted(selected[ticker].items())
            prices[ticker] = [next(v for k, v in reversed(items) if k <= d) for d in dates]
            effective[ticker] = items[-1][0]
            if effective[ticker] < cutoff:
                warnings.append({'code': 'LAST_KNOWN_CLOSE', 'message': f'{ticker} : cours du {effective[ticker]} repris au {cutoff}.'})
        if data['provenance'].get(ticker, {}).get('price_basis') == 'STORED_CLOSE':
            warnings.append({'code': 'STORED_CLOSE_BASIS', 'message': f'{ticker} : close conservé en cache, sans cours brut distinct.'})
    return {'dates': dates, 'prices': prices, 'provider': data['provider'], 'price_type': 'CACHED_HISTORICAL_CLOSE',
            'adjusted': adjusted, 'requested_start': start, 'requested_asof': requested,
            'asof_effective': max(effective.values()), 'effective_dates': effective,
            'provenance': {t: data['provenance'].get(t, {}) for t in tickers},
            'age_sessions': {t: (date.fromisoformat(cutoff)-date.fromisoformat(d)).days for t, d in effective.items()},
            'warnings': warnings}
