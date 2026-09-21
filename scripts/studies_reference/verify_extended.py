"""Independent checks of serialized outputs; does not import the generator."""
from pathlib import Path
from decimal import Decimal as D
import argparse
import csv
import json
import hashlib
from datetime import date


def rows(path):
    with open(path, encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def verify(root):
    n = 0
    def check(condition, message):
        nonlocal n
        if not condition: raise AssertionError(message)
        n += 1
    checksums = json.loads((root / 'checksums.json').read_text(encoding='utf-8'))
    for relative, expected in checksums.items():
        check(hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected, f'Fichier altéré : {relative}')
    source = root / 'sources/original'
    nav = rows(source / 'reference/nav_daily.csv')
    trades = rows(source / 'inputs/trades.csv')
    check(len(nav) == 1566 and len(trades) == 1540, 'Calendrier / carnet original modifié')
    ts = json.loads((root / 'inputs/termsheet_economic.json').read_text(encoding='utf-8'))
    prices = {(r['date'], r['asset_id']): r for r in rows(source / 'inputs/prices_daily.csv')}
    opening = [r for r in rows(source / 'reference/positions_daily.csv') if r['date'] == ts['date'] and D(r['quantity']) > D('1e-8')]
    capital = D(nav[1]['net_assets_usd'])
    cash = D(nav[1]['cash_usd']) - D(nav[1]['management_liability_usd']) - D(nav[1]['performance_liability_usd'])
    check(abs(sum(D(r['value_usd']) for r in opening) + cash - capital) < D('0.00001'), 'Actif initial non rapproché')
    for ref in rows(root / 'reference/E_daily.csv'):
        value = cash
        for r in opening:
            first = prices[ts['date'], r['asset_id']]
            last = prices[ref['date'], r['asset_id']]
            growth = D(last['total_return_index_local']) / D(first['total_return_index_local']) * D(last['usd_per_local']) / D(first['usd_per_local'])
            value += D(r['value_usd']) * growth
        check(abs(value / D(100000) - D(ref['passive_reinvest_nav'])) < D('0.00000001'), f"Référence E : {ref['date']}")
    imports = json.loads((root / 'studies_import_E_ONLY/manifest.json').read_text(encoding='utf-8'))
    check(imports['files']['orders'] == [] and imports['blocks']['E_bh'] and sum(imports['blocks'].values()) == 1, 'Risque de double injection dans FIFO')
    check(all(p['ccy'] == 'USD' and p['isin'].startswith('SYNTH_E_USD_') for p in imports['params']['termsheet_positions']), 'Proxies E non isolés')
    check(abs(sum(D(str(p['weight_pct'])) for p in imports['params']['termsheet_positions']) / 100 + cash / capital - 1) < D('1e-12'), 'Poids TS + cash != 100 %')
    g = rows(root / 'reference/G_sector_attribution.csv')
    rp = sum(D(r['portfolio_weight']) * D(r['portfolio_return']) for r in g)
    rb = sum(D(r['benchmark_weight']) * D(r['benchmark_return']) for r in g)
    effects = sum(D(r['allocation']) + D(r['selection']) + D(r['interaction']) for r in g)
    check(abs(effects - rp + rb) < D('1e-12'), 'Brinson non rapproché')
    dates = [r['date'] for r in nav]
    spans = {'1M': 21, '3M': 63, '6M': 126, '12M': 252}
    for r in rows(root / 'reference/I_by_purchase_horizon.csv'):
        at = dates.index(r['date']) + spans[r['horizon']]
        check((r['available'] == 'True') == (at < len(dates)), 'Horizon I tronqué')
        if at < len(dates): check(r['end_date'] == dates[at], 'Dates I non alignées')
    for r in rows(root / 'reference/H_by_trade.csv'):
        check((date.fromisoformat(dates[-1]) - date.fromisoformat(r['date'])).days >= 30 or r['available'] == 'False', 'Timing utilisant le futur')
        if r['available'] == 'True': check(0 <= D(r['score']) <= 1, 'Timing hors bornes')
    for r in rows(root / 'reference/K_events.csv'):
        chosen = [t for t in trades if r['start'] <= t['date'] <= r['end']]
        check(len(chosen) == int(r['n_trades']), 'Nombre de trades choc erroné')
        check(abs(sum(abs(D(t['notional_usd_signed'])) for t in chosen) - D(r['gross_notional_usd'])) < D('0.00001'), 'Volume choc erroné')
    return {'status': 'passed', 'assertions': n, 'tolerance_E_nav_usd': '0.00000001', 'application_imports': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', nargs='?', type=Path, default=Path(__file__).resolve().parents[1])
    root = parser.parse_args().folder
    result = verify(root)
    (root / 'reference/verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
