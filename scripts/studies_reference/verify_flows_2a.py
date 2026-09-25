"""Independent Decimal replay of the exported 2A ledger; no generator/app imports."""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal as D
from pathlib import Path


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def verify(root):
    checks = 0

    def check(condition, message):
        nonlocal checks
        if not condition:
            raise AssertionError(message)
        checks += 1

    def near(actual, expected, message, tolerance='0.000001'):
        check(abs(D(str(actual))-D(str(expected))) <= D(tolerance), message)

    for name, expected in json.loads((root/'source_hashes.json').read_text()).items():
        check(hashlib.sha256((root/'sources'/name).read_bytes()).hexdigest() == expected, f'Source altérée : {name}')
    market = defaultdict(dict)
    for r in rows(root/'sources/prices_daily.csv'):
        market[r['date']][r['asset_id']] = r
    by_day = defaultdict(list)
    trades = rows(root/'RESULTATS_ATTENDUS/trades.csv')
    for r in trades:
        by_day[r['date']].append(r)
    flows = defaultdict(list)
    flow_rows = rows(root/'RESULTATS_ATTENDUS/investor_flows.csv')
    for r in flow_rows:
        flows[r['date']].append(r)
    closing = defaultdict(dict)
    for r in rows(root/'RESULTATS_ATTENDUS/positions_daily.csv'):
        closing[r['date']][r['asset_id']] = r
    navs = rows(root/'RESULTATS_ATTENDUS/nav_daily.csv')
    dividend_import = json.loads((root/'dividends.json').read_text(encoding='utf-8'))['events']
    dividend_lookup = {(r['ex_date'], r['asset_id']): r for r in dividend_import}
    check(len(dividend_lookup) == len(dividend_import), 'Pas de dividendes dupliqués')
    cash_dividends = {(r['date'], r['asset_id']): r for r in rows(root/'cash_events.csv') if r['type'] == 'DIVIDEND'}
    check(set(cash_dividends) == set(dividend_lookup), 'Mêmes paiements de dividendes dans les deux registres')
    for key, event in dividend_lookup.items():
        near(cash_dividends[key]['amount_local'], event['net_local'], f'Paiement local rapproché {key}')
        near(cash_dividends[key]['amount_usd'], D(str(event['net_local']))*D(str(event['fx_at_payment'])), f'Paiement USD rapproché {key}')
    asset_trade_cash = defaultdict(lambda: D(0))
    asset_income = defaultdict(lambda: D(0))
    asset_costs = defaultdict(lambda: D(0))
    cash, units, provision, previous_aum = D(10000000), D(100000), D(0), D(10000000)
    quantity = defaultdict(lambda: D(0))
    previous_day = None
    for n, nav in enumerate(navs):
        ds = nav['date']
        gap = (date.fromisoformat(ds)-date.fromisoformat(previous_day)).days if previous_day else 0
        charge = previous_aum*D('.01')*gap/365
        provision += charge
        near(nav['management_expense_usd'], charge, f'Provision gestion {ds}')
        income = D(0)
        for a, m in market[ds].items():
            quantity[a] *= D(m['split_ratio'])
            amount = quantity[a]*D(m['dividend_per_share_local'])*D(m['usd_per_local'])
            cash += amount
            income += amount
            asset_income[a] += amount
            if D(m['dividend_per_share_local']):
                imported = dividend_lookup[ds, a]
                near(imported['eligible_quantity'], quantity[a], f'Dividende quantité éligible {ds} {a}')
                near(imported['gross_per_share'], m['dividend_per_share_local'], f'Dividende par part {ds} {a}')
                near(D(str(imported['net_local']))*D(str(imported['fx_at_payment'])), amount, f'Dividende exporté {ds} {a}')
        near(nav['dividends_usd'], income, f'Dividendes {ds}')
        costs = D(0)
        for t in by_day[ds]:
            a = t['asset_id']
            m = market[ds][a]
            near(t['price_local'], m['price_local'], f'Prix trade {t["trade_id"]}')
            near(t['usd_per_local'], m['usd_per_local'], f'FX trade {t["trade_id"]}', '0.000000000001')
            delta = D(t['quantity_signed'])
            notional = delta*D(m['price_local'])*D(m['usd_per_local'])
            commission = abs(notional)*D('.0005')
            costs += commission
            asset_costs[a] += commission
            asset_trade_cash[a] -= notional
            cash -= notional+commission
            quantity[a] += delta
            check(quantity[a] >= D('-0.00000001') and cash >= D('-0.000001'), f'Long only / liquidité {ds}')
            near(t['transaction_fee_usd'], commission, f'Frais trade {t["trade_id"]}')
        near(nav['transaction_cost_usd'], costs, f'Total frais transactions {ds}')
        securities = sum(quantity[a]*D(m['price_local'])*D(m['usd_per_local']) for a, m in market[ds].items())
        dealing_nav = (cash+securities-provision)/units
        near(nav['pre_flow_net_assets_usd'], cash+securities-provision, f'AUM avant flux {ds}')
        for flow in flows[ds]:
            amount = D(flow['amount_usd'])
            near(flow['units_before'], units, f'Parts avant flux {ds}')
            near(flow['dealing_nav_usd'], dealing_nav, f'NAV de souscription/rachat {ds}', '0.00000001')
            near(flow['units_delta'], amount/dealing_nav, f'Parts émises/détruites {ds}')
            units += amount/dealing_nav
            cash += amount
            near(flow['units_after'], units, f'Parts après flux {ds}')
        near(nav['net_investor_flow_usd'], sum(D(f['amount_usd']) for f in flows[ds]), f'Flux net {ds}')
        if n == len(navs)-1 or navs[n+1]['date'][5:7] != ds[5:7]:
            near(nav['management_paid_usd'], provision, f'Paiement gestion {ds}')
            cash -= provision
            provision = D(0)
        else:
            near(nav['management_paid_usd'], 0, f'Absence paiement {ds}')
        aum = cash+securities-provision
        near(nav['nav_usd'], aum/units, f'NAV reconstruite {ds}', '0.00000001')
        near(nav['nav_usd'], dealing_nav, f'Absence dilution {ds}', '0.00000001')
        near(nav['units'], units, f'Parts clôture {ds}')
        near(nav['cash_usd'], cash, f'Cash clôture {ds}')
        near(nav['net_assets_usd'], aum, f'AUM clôture {ds}')
        near(nav['management_liability_usd'], provision, f'Dette gestion {ds}')
        for a, m in market[ds].items():
            near(closing[ds][a]['quantity'], quantity[a], f'Position {ds} {a}')
            near(closing[ds][a]['value_usd'], quantity[a]*D(m['price_local'])*D(m['usd_per_local']), f'Valeur {ds} {a}')
        previous_day, previous_aum = ds, aum
    check(len(navs) == 1566 and len(flow_rows) == 6, 'Calendrier / scénarios')
    check(D(flow_rows[0]['drawdown_before_flow']) > 0, 'Souscription au plus-haut')
    check(D(flow_rows[1]['drawdown_before_flow']) <= D('-.20'), 'Souscription pendant drawdown')
    check(D(flow_rows[2]['drawdown_before_flow']) < 0, 'Rachat avant récupération')
    check(D(flow_rows[3]['drawdown_before_flow']) >= 0, 'Souscription après récupération')
    check(len(flows['2025-11-20']) == 2 and sum(D(f['amount_usd']) for f in flows['2025-11-20']) == 0, 'Flux opposés conservés')
    check(any(t['reason'] == 'REDEMPTION_FUNDING' for t in trades), 'Ventes pour financer le rachat')
    summary = json.loads((root/'RESULTATS_ATTENDUS/summary.json').read_text())
    pnl = rows(root/'RESULTATS_ATTENDUS/pnl_by_asset.csv')
    for row in pnl:
        a = row['asset_id']
        m = market[navs[-1]['date']][a]
        final_value = quantity[a]*D(m['price_local'])*D(m['usd_per_local'])
        near(row['total_price_pnl_usd'], asset_trade_cash[a]+final_value, f'P&L par titre {a}')
        near(row['dividends_usd'], asset_income[a], f'Dividendes cumulés par titre {a}')
        near(row['transaction_cost_usd'], asset_costs[a], f'Frais cumulés par titre {a}')
    gross = sum(D(r['total_with_dividends_usd']) for r in pnl)
    net = gross-D(str(summary['management_expense_usd']))-D(str(summary['transaction_cost_usd']))
    near(net, previous_aum-D(10000000)-sum(D(f['amount_usd']) for f in flow_rows), 'Pont P&L indépendant')
    near(summary['net_profit_excluding_flows_usd'], net, 'Résumé P&L net')
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    check(manifest['params']['perf_fee_pct'] == 0, 'Pas de commission performance')
    near(manifest['params']['n_certs'], navs[0]['units'], 'Parts à émission dans le manifeste', '0')
    check(isinstance(manifest['params']['n_certs'], int), 'Type entier des parts initiales du scénario 2A')
    composition = json.loads((root/manifest['files']['composition']).read_text(encoding='utf-8'))['data']['products']['items'][0]
    near(composition['outstandingQuantity'], navs[-1]['units'], 'Parts finales fractionnaires préservées', '0')
    for value in manifest['files'].values():
        for name in value if isinstance(value, list) else [value]:
            check((root/name).is_file(), f'Input manquant {name}')
    imported_navs = rows(root/manifest['files']['nav_timeseries'])
    check(len(imported_navs) == len(navs), 'Nombre de NAV importées')
    for exported, ref in zip(imported_navs, navs):
        near(exported['Price'], ref['nav_usd'], 'NAV exportée', '0')
        near(exported['Outstanding quantity'], ref['units'], 'Parts exportées', '0')
        check(exported['Date'] == date.fromisoformat(ref['date']).strftime('%d.%m.%Y'), 'Date exportée')
    orders = json.loads((root/'LO_2A Data.json').read_text(encoding='utf-8'))['data']['orders']['items']
    check(len(orders) == len(trades), 'Nombre ordres exportés')
    for order, trade in zip(orders, trades):
        ds, a = trade['date'], trade['asset_id']
        factor = D(1)
        for day in market:
            if day > ds:
                factor *= D(market[day][a]['split_ratio'])
        near(order['executedQuantity'], D(trade['quantity_signed'])*factor, 'Quantité ajustée splits')
        near(order['executionPrice']['amount'], D(trade['price_local'])/factor, 'Prix ajusté splits')
    check((root/'market_data.json').read_bytes() == (root/'sources/market_data.json').read_bytes(), 'Marchés inchangés')
    print(f'{checks} contrôles indépendants conformes (rejeu Decimal, inputs et scénarios).')
    return checks


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    verify(parser.parse_args().root)
