"""Optional integration harness. Uses Studies ONLY as the system under test.

All market dependencies are supplied in memory; socket access is denied.
Never used by the independent generator or verifier; no live cache is changed.
Run from the repository root with its backend Python environment.
"""
from pathlib import Path
import sys
import json
from contextlib import ExitStack
from unittest.mock import patch
import pandas as pd

REPO = Path.cwd()
sys.path.insert(0, str(REPO / 'backend'))
from app.core import amc_study, amc_prices, amc_bh, amc_engine, amc_stockpicking, amc_riskmanagement, amc_brinson, amc_controls


def main(root):
    market = pd.read_csv(root / 'inputs/market_daily.csv', parse_dates=['date'])
    assets = pd.read_csv(root / 'inputs/asset_classification.csv').set_index('asset_id')
    frames = {}
    for key, g in market.groupby('asset_id'):
        f = g.set_index('date')[['total_return_index_local', 'price_split_adjusted']].rename(columns={
            'total_return_index_local': 'close', 'price_split_adjusted': 'price_close'})
        f.attrs.update(currency=assets.loc[key, 'currency'], adjustment_date='2025-12-31', source='independent_fixture')
        frames[key] = f
        frames[assets.loc[key, 'name']] = f
    for path in (root / 'manual_prices_E').glob('*.json'):
        f = pd.DataFrame(json.loads(path.read_text(encoding='utf-8')))
        f['date'] = pd.to_datetime(f.date)
        f = f.set_index('date'); f.attrs.update(currency='USD', source='E_USD_proxy')
        frames[path.stem] = f
    fx = market.drop_duplicates(['date', 'currency']).pivot(index='date', columns='currency', values='usd_per_local')
    benchmark = pd.read_csv(root / 'inputs/benchmark_daily.csv', index_col='date', parse_dates=True).close
    factors = pd.read_csv(root / 'sources/factors.csv', index_col='date', parse_dates=True)
    def load(key):
        if key not in frames: raise ValueError('Série absente du jeu : ' + key)
        return frames[key].copy()
    def currency(key): return frames[key].attrs['currency']
    fx_cache = {(source, target): fx[source] / fx[target] for source in fx.columns for target in fx.columns}
    def fx_series(source, target='USD', *args, **kwargs): return fx_cache[source, target]
    # Memoize the original validated FX lookup, without replacing its calculation.
    # I currently repeats identical lookups for every purchase and every horizon.
    original_lookup = amc_controls.price_at
    lookup_cache = {}
    frozen_fx_ids = {id(s) for s in fx_cache.values()}
    def cached_lookup(series, date, max_age_days=7):
        if id(series) not in frozen_fx_ids: return original_lookup(series, date, max_age_days)
        key = (id(series), str(date), max_age_days)
        if key not in lookup_cache: lookup_cache[key] = original_lookup(series, date, max_age_days)
        return lookup_cache[key]
    def blocked(*args, **kwargs): raise RuntimeError('Accès réseau interdit pendant la recette indépendante')
    with ExitStack() as stack:
        stack.enter_context(patch('socket.socket.connect', blocked))
        stack.enter_context(patch('socket.create_connection', blocked))
        stack.enter_context(patch.object(amc_prices.yf, 'download', blocked))
        stack.enter_context(patch.object(amc_prices.yf, 'Ticker', blocked))
        stack.enter_context(patch.object(amc_controls, 'price_at', cached_lookup))
        for mod in [amc_prices, amc_bh, amc_stockpicking, amc_brinson]:
            if hasattr(mod, 'load_prices'): stack.enter_context(patch.object(mod, 'load_prices', load))
            if hasattr(mod, 'get_fx_series'): stack.enter_context(patch.object(mod, 'get_fx_series', fx_series))
        stack.enter_context(patch.object(amc_prices, 'get_currency', currency))
        stack.enter_context(patch.object(amc_prices, 'split_factor_between', return_value=1.))
        stack.enter_context(patch.object(amc_engine, '_load_ff_data', return_value=factors))
        stack.enter_context(patch.object(amc_engine, '_download_benchmark', return_value=benchmark.pct_change().dropna()))
        stack.enter_context(patch.object(amc_stockpicking, '_get_benchmark_series', return_value=benchmark))
        stack.enter_context(patch.object(amc_riskmanagement, '_get_benchmark_series', return_value=benchmark))
        folder = root / 'sources/validated_import'
        m = json.loads((folder / 'manifest.json').read_text(encoding='utf-8-sig'))
        m['blocks'] = {key: key != 'E_bh' for key in m['blocks']}
        m['params'].update(ff_series='Developed_5F_MOM', selected_factors=['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', 'MOM'],
                           benchmark_ticker='SYNTH_BENCH20_USD', rolling_window=60)
        result = amc_study.run_study(m, str(folder.resolve()))
        efolder = root / 'studies_import_E_ONLY'
        em = json.loads((efolder / 'manifest.json').read_text(encoding='utf-8'))
        eresult = amc_study.run_study(em, str(efolder.resolve()))
        # Single-period G starts at the TS instant, without changing the full-fund result.
        economic = json.loads((root / 'inputs/termsheet_economic.json').read_text(encoding='utf-8'))
        gref = pd.read_csv(root / 'inputs/brinson_benchmark.csv').set_index('sector')
        stack.enter_context(patch.object(amc_brinson, '_get_benchmark_sector_weights', return_value=(gref.benchmark_weight.to_dict(), 'fixture')))
        stack.enter_context(patch.object(amc_brinson, '_get_sector_etf_returns', return_value=gref.benchmark_return.to_dict()))
        stack.enter_context(patch.object(amc_brinson, '_series_total_return', return_value=float((gref.benchmark_weight * gref.benchmark_return).sum())))
        stack.enter_context(patch.object(amc_prices, '_load_ticker_map', return_value={}))
        gs = {'meta': {**result['meta'], 'nav_start_date': economic['date']},
              'block_b': result['block_b'], 'termsheet_basket': economic['positions']}
        sectors = {row['name']: row['sector'] for row in assets.to_dict('records')}
        sectors['Liquidités'] = 'Liquidités'
        gresult = amc_brinson.compute_brinson(gs, {a: frames[a] for a in assets.index}, 'SYNTH_BENCH20_USD', 'USD', cached_sectors=sectors)
    out = root / 'comparison'
    out.mkdir(exist_ok=True)
    for name, value in [('studies_full', result), ('studies_E', eresult), ('studies_G', gresult)]:
        (out / f'{name}.json').write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps({k: {'available': v.get('available'), 'error': v.get('error')} for k, v in result.items() if k.startswith('block_') and isinstance(v, dict)}, ensure_ascii=False))
    print(json.dumps({'E': eresult.get('block_e'), 'G': {k: v for k, v in gresult.items() if k in ['available', 'error', 'total_allocation', 'total_selection', 'total_interaction']}}, ensure_ascii=False))


if __name__ == '__main__': main(Path(sys.argv[1]).resolve())
