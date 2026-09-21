"""Independent reference data. No imports from Studies or application modules.

Bootstrap with --source, --import-source and --factors. Thereafter the output
directory is a portable, frozen package; rerun its generator offline.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import math
import csv
import numpy as np
import pandas as pd
from scipy import stats

FACTORS = ['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA', 'MOM']
HORIZONS = {'1M': 21, '3M': 63, '6M': 126, '12M': 252}
EVENTS = [
    ('covid_2020', '2020-02-19', '2020-03-23'),
    ('china_2021', '2021-07-01', '2021-10-31'),
    ('bear_2022', '2022-01-03', '2022-10-13'),
    ('svb_2023', '2023-03-08', '2023-03-20'),
    ('china_property_2023', '2023-08-01', '2023-10-31'),
]


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False,
                               default=lambda x: x.item() if hasattr(x, 'item') else str(x)), encoding='utf-8')


def write_csv(path, frame, index=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=index, float_format='%.15g', date_format='%Y-%m-%d')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ols(y, factors):
    """QR/SVD least squares and independent Newey-West covariance, lag five."""
    x = np.column_stack([np.ones(len(y)), np.asarray(factors)])
    y = np.asarray(y)
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    error = y - x @ beta
    bread = np.linalg.inv(x.T @ x)
    z = x * error[:, None]
    meat = z.T @ z
    for lag in range(1, 6):
        cross = z[lag:].T @ z[:-lag]
        meat += (1 - lag / 6) * (cross + cross.T)
    se = np.sqrt(np.maximum(np.diag(bread @ meat @ bread), 0))
    return beta, se, float(1 - error @ error / ((y - y.mean()) @ (y - y.mean())))


def timing_score(prices, trade_price, side):
    if len(prices) < 5 or max(prices) <= min(prices):
        return None
    return float(np.clip(((max(prices) - trade_price) if side == 'BUY' else
                          (trade_price - min(prices))) / (max(prices) - min(prices)), 0, 1))


def brinson(wp, wb, rp, rb):
    rb_total = float(np.dot(wb, rb))
    return ((wp - wb) * (rb - rb_total), wb * (rp - rb), (wp - wb) * (rp - rb))


def risk_metrics(levels, benchmark):
    r = levels.pct_change().dropna()
    br = benchmark.pct_change().reindex(r.index)
    dd = levels / levels.cummax() - 1
    downside = np.sqrt(np.mean(np.minimum(r, 0) ** 2))
    vol = r.std(ddof=1) * np.sqrt(252)
    q = np.quantile(r, .05)
    active = r - br
    cagr252 = (levels.iloc[-1] / levels.iloc[0]) ** (252 / len(r)) - 1
    return {
        'n_returns': len(r), 'total_return_pct': (levels.iloc[-1] / levels.iloc[0] - 1) * 100,
        'volatility_pct': vol * 100, 'sharpe_rf_zero': r.mean() * 252 / vol,
        'sortino_target_zero': r.mean() * np.sqrt(252) / downside,
        'max_drawdown_pct': dd.min() * 100, 'ulcer_index_pct': np.sqrt(np.mean(dd ** 2)) * 100,
        'cagr_252_pct': cagr252 * 100, 'calmar_252': cagr252 / abs(dd.min()),
        'var95_daily_pct': q * 100, 'es95_daily_pct': r[r <= q].mean() * 100,
        'semi_deviation_ann_pct': downside * np.sqrt(252) * 100,
        'worst_day_pct': r.min() * 100,
        'worst_5_observations_pct': ((1 + r).rolling(5).apply(np.prod, raw=True) - 1).min() * 100,
        'worst_21_observations_pct': ((1 + r).rolling(21).apply(np.prod, raw=True) - 1).min() * 100,
        'tracking_error_pct': active.std(ddof=1) * np.sqrt(252) * 100,
        'information_ratio': active.mean() / active.std(ddof=1) * np.sqrt(252),
        'up_capture_pct': r[br > 0].mean() / br[br > 0].mean() * 100,
        'down_capture_pct': r[br < 0].mean() / br[br < 0].mean() * 100,
    }


def build(root):
    frozen = root / 'sources'
    assets = pd.read_csv(frozen / 'original/inputs/assets.csv').set_index('asset_id')
    prices = pd.read_csv(frozen / 'original/inputs/prices_daily.csv', parse_dates=['date'])
    positions = pd.read_csv(frozen / 'original/reference/positions_daily.csv', parse_dates=['date'])
    nav = pd.read_csv(frozen / 'original/reference/nav_daily.csv', parse_dates=['date']).set_index('date')
    trades = pd.read_csv(frozen / 'original/inputs/trades.csv', parse_dates=['date'])
    matches = pd.read_csv(frozen / 'original/reference/fifo_matches.csv', parse_dates=['buy_date', 'sell_date'])
    fifo = pd.read_csv(frozen / 'original/reference/fifo_by_asset.csv').set_index('asset_id')
    local = prices.pivot(index='date', columns='asset_id', values='price_local')
    fx = prices.pivot(index='date', columns='asset_id', values='usd_per_local')
    tr_local = prices.pivot(index='date', columns='asset_id', values='total_return_index_local')
    tr_usd = tr_local * fx
    splits = prices.pivot(index='date', columns='asset_id', values='split_ratio')
    future_splits = splits.iloc[::-1].cumprod().iloc[::-1] / splits
    execution = local / future_splits
    dates, end = nav.index, nav.index[-1]
    start = dates[1]  # after the initial purchases, not a second set of holdings at inception
    opening = positions[positions.date == start].set_index('asset_id')
    opening = opening[opening.quantity > 1e-8]
    capital = nav.loc[start, 'net_assets_usd']
    weights = opening.value_usd / capital
    cash_weight = 1 - weights.sum()
    summary = {'scenario': root.name, 'full_start': str(dates[0].date()), 'ts_start': str(start.date()),
               'as_of': str(end.date()), 'baseline_nav_unchanged': float(nav.nav_usd.iloc[-1]),
               'benchmark': 'SYNTH_BENCH20_USD — 20 titres équipondérés au départ, conservés, dividendes réinvestis localement',
               'independence': 'Aucun import du code Studies ; seules les conventions et interfaces ont été consultées.'}

    # Benchmark: equal initial capital per title, no daily rebalancing or future data.
    benchmark = (tr_usd / tr_usd.iloc[0]).mean(axis=1) * 100
    write_csv(root / 'inputs/benchmark_daily.csv', benchmark.rename('close').rename_axis('date').to_frame(), True)
    sector_names = sorted(assets.sector.unique())
    sector_levels = pd.DataFrame({s: (tr_usd[assets.index[assets.sector == s]] /
                                    tr_usd[assets.index[assets.sector == s]].iloc[0]).mean(axis=1) * 100 for s in sector_names})
    write_csv(root / 'inputs/sector_indices_daily.csv', sector_levels.rename_axis('date'), True)
    write_csv(root / 'inputs/asset_classification.csv', assets.reset_index())
    daily_benchmark_weights = (tr_usd / tr_usd.iloc[0]).div((tr_usd / tr_usd.iloc[0]).sum(axis=1), axis=0)
    write_csv(root / 'inputs/benchmark_weights_daily.csv', daily_benchmark_weights.rename_axis('date'), True)
    market = prices.copy()
    market['price_split_adjusted'] = [execution.loc[r.date, r.asset_id] for r in prices.itertuples()]
    market['total_return_index_usd'] = [tr_usd.loc[r.date, r.asset_id] for r in prices.itertuples()]
    write_csv(root / 'inputs/market_daily.csv', market)
    write_csv(root / 'inputs/market_events.csv', pd.DataFrame(EVENTS, columns=['event_id', 'start', 'end']))

    # E: both economically distinct dividend policies, gross after the opening instant.
    growth = tr_usd.loc[start:, opening.index].div(tr_usd.loc[start, opening.index])
    reinvest = (growth * weights).sum(axis=1) + cash_weight
    qty = opening.quantity.copy()
    cash = capital * cash_weight
    cash_rows = []
    for date in dates[dates >= start]:
        if date > start:
            qty *= splits.loc[date, qty.index]
            dividends = prices[prices.date == date].set_index('asset_id').dividend_per_share_local
            cash += float((qty * dividends[qty.index] * fx.loc[date, qty.index]).sum())
        total = float((qty * local.loc[date, qty.index] * fx.loc[date, qty.index]).sum()) + cash
        cash_rows.append(total / capital)
    e_daily = pd.DataFrame({'actual_nav': nav.loc[start:, 'nav_usd'],
                            'passive_reinvest_nav': reinvest * nav.loc[start, 'nav_usd'],
                            'passive_cash_dividends_nav': np.array(cash_rows) * nav.loc[start, 'nav_usd']})
    write_csv(root / 'reference/E_daily.csv', e_daily.rename_axis('date'), True)
    summary['E'] = {'opening_nav': nav.loc[start, 'nav_usd'], 'opening_aum_usd': capital,
                    'n_positions': len(opening), 'cash_net_of_opening_liabilities_usd': capital * cash_weight,
                    'cash_weight_pct': cash_weight * 100,
                    'bh_nav': float(e_daily.passive_reinvest_nav.iloc[-1]),
                    'bh_perf_pct': float((reinvest.iloc[-1] - 1) * 100),
                    'actual_perf_pct': float((nav.nav_usd.iloc[-1] / nav.loc[start, 'nav_usd'] - 1) * 100),
                    'passive_cash_dividends_nav': float(e_daily.passive_cash_dividends_nav.iloc[-1]),
                    'comparable_costs': False}
    summary['E']['value_added_pct'] = summary['E']['actual_perf_pct'] - summary['E']['bh_perf_pct']
    ts = []
    for a in opening.index:
        ts.append({'isin': a, 'name': assets.loc[a, 'name'], 'weight_pct': weights[a] * 100,
                   'qty_per_cert': opening.loc[a, 'quantity'] / 100000,
                   'fixing_price': local.loc[start, a], 'ccy': assets.loc[a, 'currency'],
                   'fx_usd_per_local': fx.loc[start, a], 'initial_quantity': opening.loc[a, 'quantity']})
    dump(root / 'inputs/termsheet_economic.json', {'date': str(start.date()), 'units': 100000,
         'net_assets_usd': capital, 'cash_usd': float(nav.loc[start, 'cash_usd']),
         'opening_fee_liability_usd': float(nav.loc[start, 'management_liability_usd']), 'positions': ts})

    # E-only UI adapter uses distinct USD proxy IDs: local TR and actual FX already combined.
    # It cannot affect B/C/D or inject duplicate initial purchases into the original fund.
    imp = root / 'studies_import_E_ONLY'
    imp.mkdir(exist_ok=True)
    nav_export = pd.DataFrame({'Date': nav.loc[start:].index.strftime('%d.%m.%Y'),
                               'Price': nav.loc[start:, 'nav_usd'].values, 'Outstanding quantity': 100000})
    write_csv(imp / 'E timeseries.csv', nav_export)
    ts_import = []
    for a in opening.index:
        key = a.replace('SYNTH_LO_', 'SYNTH_E_USD_')
        series = tr_usd[a] / tr_usd.loc[start, a] * local.loc[start, a] * fx.loc[start, a]
        dump(root / f'manual_prices_E/{key}.json', [{'date': str(d.date()), 'close': float(v)} for d, v in series.items()])
        ts_import.append({'isin': key, 'name': f"{assets.loc[a, 'name']} — proxy USD E", 'weight_pct': weights[a] * 100,
                          'qty_per_cert': opening.loc[a, 'quantity'] / 100000,
                          'fixing_price': float(series.loc[start]), 'ccy': 'USD'})
    dump(imp / 'termsheet_positions.json', ts_import)
    base_manifest = json.loads((frozen / 'validated_import/manifest.json').read_text(encoding='utf-8-sig'))
    m = json.loads(json.dumps(base_manifest))
    m['product'] = {'isin': 'SYNTH_E_ONLY', 'name': 'Référence E — départ après achats initiaux', 'currency': 'USD'}
    m['files'] = {'nav_timeseries': 'E timeseries.csv', 'composition': 'E Def.txt', 'orders': [], 'dividends': '', 'cash_events': ''}
    dump(imp / 'E Def.txt', {'data': {'products': {'items': [{'isin': 'SYNTH_E_ONLY',
        'name': 'Référence E — métadonnées uniquement, positions initiales dans la TS', 'currency': 'USD',
        'outstandingQuantity': 100000, 'netAssetValue': {'value': float(nav.nav_usd.iloc[-1]), 'date': str(end.date())},
        'components': []}]}}})
    m['params'].update({'termsheet_positions': ts_import, 'dividends': {'status': 'unknown', 'treatment': 'cash'},
                        'benchmark_ticker': 'SYNTH_BENCH20_USD'})
    m['blocks'] = {k: k == 'E_bh' for k in m['blocks']}
    dump(imp / 'manifest.json', m)

    # C and D: freeze already independently verified FIFO reference, recompute aggregates.
    pnl = matches.pnl_before_fees_usd
    holding = (matches.sell_date - matches.buy_date).dt.days
    turnover = trades.notional_usd_signed.abs().sum() / nav.net_assets_usd.mean()
    summary['C'] = {'round_trips': len(matches), 'hit_ratio_pct': (pnl > 0).mean() * 100,
                    'profit_factor': pnl[pnl > 0].sum() / -pnl[pnl < 0].sum(),
                    'realized_pnl_usd': pnl.sum(), 'mean_holding_days': holding.mean(),
                    'median_holding_days': float(holding.median()), 'gross_traded_usd': trades.notional_usd_signed.abs().sum(),
                    'average_aum_usd': nav.net_assets_usd.mean(), 'turnover_pct': turnover * 100,
                    'turnover_ann_pct': turnover * 365 / (trades.date.max() - trades.date.min()).days * 100}
    # Rebuild surviving lot dates in final split units, independently of the FIFO implementation.
    lots = {a: [] for a in assets.index}
    for t in trades.itertuples():
        q = t.quantity_signed * future_splits.loc[t.date, t.asset_id]
        if q > 0:
            lots[t.asset_id].append([t.date, q])
        else:
            remaining = -q
            while remaining > 1e-7 and lots[t.asset_id]:
                lot = lots[t.asset_id][0]
                used = min(remaining, lot[1]); remaining -= used; lot[1] -= used
                if lot[1] < 1e-7: lots[t.asset_id].pop(0)
            assert remaining < 1e-6
    final_positions = positions[positions.date == end].set_index('asset_id')
    d_rows = []
    for a in assets.index:
        closed = holding[matches.asset_id == a]
        max_hold = max([int(closed.max()) if len(closed) else 0] + [(end - lot[0]).days for lot in lots[a]])
        weight = final_positions.loc[a, 'weight_net_assets']
        profit = fifo.loc[a, 'realized_pnl_before_fees_usd'] + fifo.loc[a, 'unrealized_pnl_before_fees_usd']
        conviction = weight * 100 >= 4 or max_hold >= 180
        category = ('conviction_winners' if conviction else 'tactical_winners') if profit > 0 else ('stubborn_losers' if conviction else 'uncertainty')
        d_rows.append({'asset_id': a, 'final_weight_pct': weight * 100, 'max_holding_days': max_hold,
                       'price_pnl_usd': profit, 'category': category})
    write_csv(root / 'reference/D_classification.csv', pd.DataFrame(d_rows))
    summary['D'] = {'long_term_matches': int((holding >= 180).sum()), 'tactical_matches': int((holding < 180).sum()),
                    'categories': pd.Series([r['category'] for r in d_rows]).value_counts().to_dict(), 'excluded_cash': True}

    # A/F use a frozen local snapshot of the public factor data; no downloads, no future rows.
    factors = pd.read_csv(frozen / 'factors.csv', index_col='date', parse_dates=True)
    returns = nav.nav_usd.pct_change().rename('fund_return')
    aligned = pd.concat([returns, factors, benchmark.pct_change().rename('benchmark_return')], axis=1).dropna()
    beta, se, r2 = ols(aligned.fund_return - aligned.RF, aligned[FACTORS])
    a_rows = [{'term': term, 'coefficient': float(b), 'hac5_standard_error': float(e),
               'hac5_t': float(b / e), 'student_p_value': float(2 * stats.t.sf(abs(b / e), len(aligned) - 7))}
              for term, b, e in zip(['alpha'] + FACTORS, beta, se)]
    write_csv(root / 'reference/A_coefficients.csv', pd.DataFrame(a_rows))
    write_csv(root / 'reference/A_aligned_data.csv', aligned.rename_axis('date'), True)
    rolling = []
    for i in range(59, len(aligned)):
        window = aligned.iloc[i-59:i+1]
        b, _, rr = ols(window.fund_return - window.RF, window[FACTORS])
        rolling.append({'date': str(window.index[-1].date()), 'alpha_daily': b[0], 'r2': rr, **dict(zip(FACTORS, b[1:]))})
    write_csv(root / 'reference/A_rolling60.csv', pd.DataFrame(rolling))
    rep_returns = aligned.RF + aligned[FACTORS] @ beta[1:]
    rep = pd.DataFrame({'replicant_nav': 100 * (1 + rep_returns).cumprod(),
                        'actual_aligned_nav': 100 * (1 + aligned.fund_return).cumprod()})
    write_csv(root / 'reference/F_daily.csv', rep.rename_axis('date'), True)
    summary['A'] = {'n_obs': len(aligned), 'first_return': str(aligned.index[0].date()), 'last_return': str(aligned.index[-1].date()),
                    'alpha_daily': beta[0], 'alpha_ann_linear_pct': beta[0] * 25200,
                    'alpha_ann_compound_pct': ((1 + beta[0]) ** 252 - 1) * 100, 'r2': r2,
                    'hac_lags': 5, 'small_sample_correction': False}
    summary['F'] = {'replicant_total_pct': rep.replicant_nav.iloc[-1] - 100,
                    'amc_total_aligned_pct': rep.actual_aligned_nav.iloc[-1] - 100,
                    'alpha_gap_pct': rep.actual_aligned_nav.iloc[-1] - rep.replicant_nav.iloc[-1]}
    same_sign = summary['F']['replicant_total_pct'] * summary['F']['amc_total_aligned_pct'] > 0
    coverage = min(summary['F']['replicant_total_pct'] / summary['F']['amc_total_aligned_pct'],
                   summary['F']['amc_total_aligned_pct'] / summary['F']['replicant_total_pct']) * 100 if same_sign else (
                       100 if summary['F']['replicant_total_pct'] > 0 >= summary['F']['amc_total_aligned_pct'] else 0)
    summary['F']['score_full_precision'] = round(.4 * r2 * 100 + .35 * coverage + .25 * (1 - min(abs(beta[0] / se[0]) / 3, 1)) * 100)

    # H uses naked split-adjusted prices, +/-30 calendar days, no unseen future window.
    h_rows = []
    for t in trades.itertuples():
        window = execution[t.asset_id].loc[t.date - pd.Timedelta(days=30):t.date + pd.Timedelta(days=30)]
        mature = t.date + pd.Timedelta(days=30) <= end
        score = timing_score(window.values, t.price_local / future_splits.loc[t.date, t.asset_id], t.side) if mature else None
        h_rows.append({'trade_id': t.trade_id, 'asset_id': t.asset_id, 'date': str(t.date.date()), 'side': t.side,
                       'available': score is not None, 'score': score, 'window_min': window.min(), 'window_max': window.max(),
                       'observations': len(window), 'reason': '' if score is not None else 'Fenêtre future incomplète ou cours constants'})
    h = pd.DataFrame(h_rows)
    write_csv(root / 'reference/H_by_trade.csv', h)
    group_means = h[h.available].groupby('asset_id').score.mean()
    summary['H'] = {'n_analyzed': int(h.available.sum()), 'n_total': len(h), 'coverage_pct': h.available.mean() * 100,
                    'entry_mean': h.loc[h.side == 'BUY', 'score'].mean(), 'exit_mean': h.loc[h.side == 'SELL', 'score'].mean(),
                    'global_mean': h.score.mean(), 'independent_asset_clusters': len(group_means),
                    'cluster_tstat_vs_half': float(stats.ttest_1samp(group_means, .5).statistic)}

    # I: USD total returns, exactly matching dates; incomplete horizons are absent, never shortened.
    i_rows = []
    for t in trades[trades.side == 'BUY'].itertuples():
        n0 = dates.get_loc(t.date)
        for name, length in HORIZONS.items():
            valid = n0 + length < len(dates)
            n1 = dates[n0 + length] if valid else None
            stock = tr_usd.loc[n1, t.asset_id] / tr_usd.loc[t.date, t.asset_id] - 1 if valid else None
            bench = benchmark.loc[n1] / benchmark.loc[t.date] - 1 if valid else None
            i_rows.append({'trade_id': t.trade_id, 'asset_id': t.asset_id, 'date': str(t.date.date()), 'horizon': name,
                           'end_date': str(n1.date()) if valid else '', 'available': valid,
                           'return_title': stock, 'return_benchmark': bench, 'alpha': stock - bench if valid else None})
    ii = pd.DataFrame(i_rows)
    write_csv(root / 'reference/I_by_purchase_horizon.csv', ii)
    summary['I'] = {horizon: {'n': len(g), 'alpha_mean': g.alpha.mean(), 'success_rate': (g.alpha > 0).mean(),
                              'alpha_std': g.alpha.std(ddof=1)} for horizon, g in ii[ii.available].groupby('horizon')}
    horizon_weights = {'1M': .15, '3M': .25, '6M': .30, '12M': .30}
    weighted_alpha = sum(horizon_weights[h] * row['alpha_mean'] for h, row in summary['I'].items())
    weighted_success = sum(horizon_weights[h] * row['success_rate'] for h, row in summary['I'].items())
    ir_i = ii.alpha.mean() / ii.alpha.std(ddof=1)
    summary['I_score'] = {'global_alpha': weighted_alpha, 'global_success_rate': weighted_success,
        'information_ratio': ir_i,
        'score_full_precision': round(.4 * (50 + 50 * math.tanh(weighted_alpha / .175)) +
          .35 * np.clip((weighted_success - .3) / .4, 0, 1) * 100 + .25 * np.clip((ir_i + .5) / 2, 0, 1) * 100)}

    # G: transparent single-period, initial holdings, cash included. Not dynamic fund attribution.
    sector_rows = []
    for sector in sector_names + ['Liquidités']:
        members = assets.index[assets.sector == sector]
        held = opening.index.intersection(members)
        wp = float(weights.reindex(held).sum()) if sector != 'Liquidités' else cash_weight
        wb = len(members) / len(assets)
        rb = float((tr_usd.loc[end, members] / tr_usd.loc[start, members] - 1).mean()) if len(members) else 0.
        rp = float(((growth.loc[end, held] - 1) * weights[held]).sum() / wp) if wp > 0 and len(held) else 0.
        sector_rows.append({'sector': sector, 'portfolio_weight': wp, 'benchmark_weight': wb,
                            'portfolio_return': rp, 'benchmark_return': rb})
    g = pd.DataFrame(sector_rows)
    write_csv(root / 'inputs/brinson_benchmark.csv', g[['sector', 'benchmark_weight', 'benchmark_return']])
    allocation, selection, interaction = brinson(g.portfolio_weight.values, g.benchmark_weight.values,
                                                 g.portfolio_return.values, g.benchmark_return.values)
    g['allocation'] = allocation; g['selection'] = selection; g['interaction'] = interaction
    g['total'] = allocation + selection + interaction
    write_csv(root / 'reference/G_sector_attribution.csv', g)
    active = float((g.portfolio_weight * g.portfolio_return).sum() - (g.benchmark_weight * g.benchmark_return).sum())
    summary['G'] = {'allocation_pct': allocation.sum() * 100, 'selection_pct': selection.sum() * 100,
                    'interaction_pct': interaction.sum() * 100, 'active_return_pct': active * 100,
                    'identity_residual': float(g.total.sum() - active),
                    'basis': 'Panier initial conservé du 02/01/2020 ; benchmark équipondéré réinitialisé à cette date, cash inclus ; brut de frais'}

    # J: measurements, not an invented proprietary score.
    summary['J'] = risk_metrics(nav.nav_usd, benchmark)
    final_weights = final_positions.weight_net_assets.clip(lower=0)
    all_weights = np.append(final_weights[final_weights > 1e-8].values, nav.cash_usd.iloc[-1] / nav.net_assets_usd.iloc[-1])
    summary['J'].update({'hhi_with_cash': float(all_weights @ all_weights), 'effective_positions': float(1 / (all_weights @ all_weights)),
                          'n_lines_with_cash': len(all_weights), 'max_weight_pct': float(max(all_weights) * 100)})
    # Published score policy, independently evaluated from the measurements above.
    # The drawdown score uses the five deepest episodes; expose the complete count too.
    clip = lambda value: float(np.clip(value, 0, 100))
    jr = summary['J']
    dd = (nav.nav_usd / nav.nav_usd.cummax() - 1).iloc[1:]
    below = dd.values < 0
    boundaries = np.diff(np.r_[False, below, False].astype(int))
    starts, ends = np.where(boundaries == 1)[0], np.where(boundaries == -1)[0]
    episodes = sorted([{'depth_pct': float(dd.iloc[a:b].min() * 100), 'duration_observations': int(b-a)}
                       for a, b in zip(starts, ends)], key=lambda r: r['depth_pct'])
    write_csv(root / 'reference/J_drawdown_episodes.csv', pd.DataFrame(episodes))
    deepest = episodes[:5]
    avg_duration = np.mean([e['duration_observations'] for e in deepest])
    bench_dd = float((benchmark / benchmark.cummax() - 1).min() * 100)
    dd_score = round(.35 * clip(100 - abs(jr['max_drawdown_pct']) * 1.6) +
        .30 * clip(100 - jr['ulcer_index_pct'] * 3) +
        .20 * (.6 * clip(100 - avg_duration * .8) + .4 * clip(100 - len(deepest) * 8)) +
        .15 * clip(50 + (jr['max_drawdown_pct'] - bench_dd) * 2.5))
    downside_score = round(.35 * clip(100 - jr['semi_deviation_ann_pct'] * 2.5) +
        .40 * clip(40 + 50 * math.tanh(jr['sortino_target_zero'] / 1.5)) +
        .25 * clip(100 - abs(jr['es95_daily_pct']) * 11))
    adjusted_score = round(.35 * clip(40 + 50 * math.tanh(jr['sharpe_rf_zero'] / 1.5)) +
        .25 * clip(40 + 50 * math.tanh(jr['calmar_252'] / 2)) +
        .25 * clip(40 + 50 * math.tanh((jr['up_capture_pct'] / jr['down_capture_pct'] - 1) * 2)) +
        .15 * clip(40 + 50 * math.tanh(jr['information_ratio'] / .8)))
    concentration_score = round(.40 * clip(100 - jr['max_weight_pct'] * 1.1) +
        .35 * clip(100 * (1 - math.exp(-jr['effective_positions'] / 8))) +
        .25 * clip(100 - sum(sorted(all_weights, reverse=True)[:5]) * 90))
    market_beta, alpha_t = beta[1], beta[0] / se[0]
    r2_score = 45 if r2 < .2 else 70 if r2 <= .7 else clip(70 - (r2*100 - 70)*2)
    beta_score = 80 if .5 <= market_beta <= 1.2 else clip(80 - (market_beta - 1.2) * 60) if market_beta > 1.2 else 30 if market_beta < 0 else clip(40 + market_beta * 80)
    alpha_score = clip(70 + abs(alpha_t)*5) if alpha_t > 2 else clip(55 + abs(alpha_t)*7) if alpha_t > 0 else clip(40 + alpha_t*5) if alpha_t > -2 else clip(30 + alpha_t*3)
    factor_score = round(.30*r2_score + .40*beta_score + .30*alpha_score)
    total_j = round(.30*adjusted_score + .25*dd_score + .20*downside_score + .15*concentration_score + .10*factor_score)
    summary['J_score'] = {'score': total_j, 'risk_adjusted': adjusted_score, 'drawdown': dd_score,
        'downside': downside_score, 'concentration': concentration_score, 'factors': factor_score,
        'all_drawdown_episodes': len(episodes), 'episodes_used_for_score': len(deepest),
        'duration_unit': 'observations, pas jours calendaires', 'rounding': 'Précision entière conservée avant les scores de composantes.'}
    write_csv(root / 'reference/J_daily_drawdown.csv', pd.DataFrame({'nav': nav.nav_usd,
              'drawdown': nav.nav_usd / nav.nav_usd.cummax() - 1}).rename_axis('date'), True)

    # K: calendar-day baseline, union of shock intervals (no double counting).
    calendar = pd.date_range(dates[0], end, freq='D')
    event_mask = np.zeros(len(calendar), dtype=bool)
    for _, lo, hi in EVENTS: event_mask |= (calendar >= lo) & (calendar <= hi)
    in_event = np.zeros(len(trades), dtype=bool)
    for _, lo, hi in EVENTS: in_event |= trades.date.between(lo, hi).values
    base_daily = trades.loc[~in_event, 'notional_usd_signed'].abs().sum() / (~event_mask).sum()
    k_rows = []
    for event, lo, hi in EVENTS:
        selected = trades[trades.date.between(lo, hi)]
        days = (pd.Timestamp(hi) - pd.Timestamp(lo)).days + 1
        hs = h[h.trade_id.isin(selected.trade_id)]
        k_rows.append({'event_id': event, 'start': lo, 'end': hi, 'calendar_days': days, 'n_trades': len(selected),
                       'gross_notional_usd': selected.notional_usd_signed.abs().sum(), 'net_flow_usd': selected.notional_usd_signed.sum(),
                       'expected_notional_usd': base_daily * days, 'activity_ratio': selected.notional_usd_signed.abs().sum() / (base_daily * days),
                       'timing_mean': hs.score.mean(), 'n_with_timing': int(hs.available.sum())})
    write_csv(root / 'reference/K_events.csv', pd.DataFrame(k_rows))
    summary['K'] = {'applicable_events': len(k_rows), 'baseline_daily_notional_usd': base_daily}
    significance = 1 if abs(alpha_t) >= 2 else .9 if abs(alpha_t) >= 1.5 else .8 if abs(alpha_t) >= 1 else .7
    manager_dimensions = {
        'alpha': 50 + 50 * math.tanh(summary['A']['alpha_ann_linear_pct'] / 8) * significance,
        'stock_picking': summary['I_score']['score_full_precision'], 'risk_mgmt': total_j,
        'timing': clip(50 + 200 * (summary['H']['global_mean'] - .5)),
        'conviction': sum(r['price_pnl_usd'] > 0 for r in d_rows) / len(d_rows) * 100}
    manager_weights = {'alpha': .30, 'stock_picking': .25, 'risk_mgmt': .15, 'timing': .07, 'conviction': .03}
    summary['Manager_Skill'] = {'score': round(sum(manager_dimensions[k] * w for k, w in manager_weights.items()) / .8),
        'dimensions': manager_dimensions, 'available_base_weight_pct': 80, 'E_must_be_excluded': True,
        'reason': 'Comparaison E net/brut : comparable_costs=false ; renormalisation des cinq dimensions restantes.',
        'conditions': '20 titres indépendants, couverture H/I 100 %, plus de 120 rendements, qualité du fonds validée.'}
    dump(root / 'reference/summary.json', summary)
    summary_rows = []
    for block, values in summary.items():
        if isinstance(values, dict):
            for key, value in values.items():
                if isinstance(value, (int, float, np.number)) and not isinstance(value, bool):
                    summary_rows.append({'block': block, 'metric': key, 'expected': value})
    write_csv(root / 'reference/expected_by_screen.csv', pd.DataFrame(summary_rows))
    mini = [
        {'case': 'prix_constants', 'initial_qty': 10, 'initial_price': 100, 'final_price': 100, 'initial_fx': 1, 'final_fx': 1, 'dividend_per_share': 0, 'split': 1, 'initial_cash': 0, 'expected_final_value': 1000},
        {'case': 'change_seul', 'initial_qty': 10, 'initial_price': 100, 'final_price': 100, 'initial_fx': 1.1, 'final_fx': 1.2, 'dividend_per_share': 0, 'split': 1, 'initial_cash': 0, 'expected_final_value': 1200},
        {'case': 'dividende_detache', 'initial_qty': 10, 'initial_price': 100, 'final_price': 98, 'initial_fx': 1, 'final_fx': 1, 'dividend_per_share': 2, 'split': 1, 'initial_cash': 0, 'expected_final_value': 1000},
        {'case': 'split_neutre', 'initial_qty': 10, 'initial_price': 100, 'final_price': 50, 'initial_fx': 1, 'final_fx': 1, 'dividend_per_share': 0, 'split': 2, 'initial_cash': 0, 'expected_final_value': 1000},
        {'case': 'portefeuille_sans_trade', 'initial_qty': 8, 'initial_price': 100, 'final_price': 125, 'initial_fx': 1, 'final_fx': 1, 'dividend_per_share': 0, 'split': 1, 'initial_cash': 200, 'expected_final_value': 1200},
    ]
    write_csv(root / 'small_cases/accounting.csv', pd.DataFrame(mini))
    dump(root / 'small_cases/timing.json', {'window_prices': [90, 95, 100, 105, 110],
          'cases': [{'side': 'BUY', 'price': 90, 'score': 1}, {'side': 'BUY', 'price': 110, 'score': 0},
                    {'side': 'SELL', 'price': 110, 'score': 1}, {'side': 'SELL', 'price': 90, 'score': 0}],
          'flat_prices_expected': None})
    # Record source and output provenance; no timestamps in reproducible payloads.
    checks = {str(p.relative_to(root)).replace('\\', '/'): digest(p) for p in sorted(root.rglob('*'))
              if p.is_file() and p.name not in ['checksums.json', 'verification.json'] and '__pycache__' not in p.parts and 'comparison' not in p.parts}
    dump(root / 'checksums.json', checks)
    print(json.dumps({'E': summary['E'], 'C': summary['C'], 'H': summary['H'], 'A': summary['A']}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--import-source', type=Path)
    parser.add_argument('--factors', type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.source:
        if (root / 'sources').exists(): raise ValueError('Sources déjà figées : utiliser un nouveau dossier.')
        for name in ['inputs', 'reference']:
            shutil.copytree(args.source / name, root / 'sources/original' / name)
        shutil.copytree(args.import_source, root / 'sources/validated_import')
        frame = pd.read_parquet(args.factors).loc['2020-01-01':'2025-12-31']
        write_csv(root / 'sources/factors.csv', frame.rename_axis('date'), True)
        dump(root / 'sources/factor_provenance.json', {'source': str(args.factors), 'sha256_parquet': digest(args.factors),
             'series': 'Developed_5F_MOM', 'units': 'decimal daily returns',
             'origin': 'Snapshot local des séries Kenneth French ; aucun téléchargement ni validation externe nouvelle.'})
    build(root)


if __name__ == '__main__':
    main()
