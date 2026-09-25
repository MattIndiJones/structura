"""Offline long-only flow fixture. Standard library only; no application imports.

Bootstrap with --base and --unified. Subsequent runs only require --output:
all frozen sources and this generator are copied into that directory.
"""
import argparse
import csv
import hashlib
import json
import math
import shutil
import statistics
from collections import defaultdict, deque
from datetime import date
from pathlib import Path


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def table(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def generate(root):
    source = root / 'sources'
    assets = read_csv(source/'assets.csv')
    ids = [a['asset_id'] for a in assets]
    meta = {a['asset_id']: a for a in assets}
    market = defaultdict(dict)
    for row in read_csv(source/'prices_daily.csv'):
        market[row['date']][row['asset_id']] = {
            k: float(row[k]) for k in ('price_local', 'usd_per_local', 'split_ratio', 'dividend_per_share_local')}
    days = sorted(market)
    qty = dict.fromkeys(ids, 0.)
    cash, units, liability, previous_aum, peak = 10_000_000., 100_000., 0., 10_000_000., 100.
    navs, trades, positions, events, dividends, investor = [], [], [], [], [], []
    flags = set()
    events.append(dict(date=days[0], type='INITIAL_CAPITAL', asset_id='', amount_local=cash,
                       currency='USD', usd_per_local=1., amount_usd=cash, reference='100000 parts à 100 USD'))
    lots = {a: deque() for a in ids}
    attribution = {a: dict(asset_id=a, name=meta[a]['name'], realized_usd=0., realized_fx_usd=0., dividends_usd=0., transaction_cost_usd=0.) for a in ids}
    roundtrips = []
    for n, ds in enumerate(days):
        prices = market[ds]
        gap = (date.fromisoformat(ds)-date.fromisoformat(days[n-1])).days if n else 0
        fee = previous_aum * .01 * gap / 365
        liability += fee
        cost = income = price_pnl = fx_pnl = 0.
        previous_units = units
        for a in ids:
            m = prices[a]
            old_quantity = qty[a]
            split = m['split_ratio']
            qty[a] *= split
            for lot in lots[a]:
                lot['quantity'] *= split
                lot['price'] /= split
            if n:
                old = market[days[n-1]][a]
                price_pnl += qty[a]*(m['price_local']-old['price_local']/split)*m['usd_per_local']
                fx_pnl += old_quantity*old['price_local']*(m['usd_per_local']-old['usd_per_local'])
            if m['dividend_per_share_local']:
                amount = qty[a]*m['dividend_per_share_local']
                converted = amount*m['usd_per_local']
                income += converted
                cash += converted
                attribution[a]['dividends_usd'] += converted
                # Both supplied ledgers must describe the same payments. Studies
                # cross-checks this ledger against dated events, without adding twice.
                events.append(dict(date=ds, type='DIVIDEND', asset_id=a, amount_local=amount,
                    currency=meta[a]['currency'], usd_per_local=m['usd_per_local'], amount_usd=converted,
                    reference='Paiement du dividende daté ; contrôle croisé, pas un revenu supplémentaire'))
                # Eligible quantities use actual ex-date units; orders use final split-adjusted units.
                factor = math.prod(market[d][a]['split_ratio'] for d in days if d > ds)
                dividends.append(dict(id=f'DIV-{ds}-{a}', asset_id=a, currency=meta[a]['currency'],
                    ex_date=ds, payment_date=ds, eligible_quantity=qty[a], entitlement_unit_factor=1/factor,
                    gross_per_share=m['dividend_per_share_local'], gross_local=amount, net_local=amount,
                    withholding_local=0., fx_at_ex=m['usd_per_local'], fx_at_payment=m['usd_per_local']))

        def execute(a, delta, reason):
            nonlocal cash, cost
            if abs(delta) < 1e-9:
                return
            m = prices[a]
            local, fx = m['price_local'], m['usd_per_local']
            notional = delta*local*fx
            commission = abs(notional)*.0005
            cash -= notional+commission
            cost += commission
            attribution[a]['transaction_cost_usd'] += commission
            qty[a] += delta
            if abs(qty[a]) < 1e-8:
                qty[a] = 0.
            if delta > 0:
                lots[a].append(dict(quantity=delta, price=local, fx=fx, date=ds))
            else:
                remaining = -delta
                while remaining > 1e-8:
                    lot = lots[a][0]
                    matched = min(remaining, lot['quantity'])
                    pnl = matched*(local*fx-lot['price']*lot['fx'])
                    attribution[a]['realized_usd'] += pnl
                    attribution[a]['realized_fx_usd'] += matched*lot['price']*(fx-lot['fx'])
                    roundtrips.append(dict(asset_id=a, buy_date=lot['date'], sell_date=ds, quantity=matched,
                        pnl_usd=pnl, holding_days=(date.fromisoformat(ds)-date.fromisoformat(lot['date'])).days))
                    remaining -= matched
                    lot['quantity'] -= matched
                    if lot['quantity'] < 1e-8:
                        lots[a].popleft()
            trades.append(dict(trade_id=f'FLOW2A-{len(trades)+1:06}', date=ds, asset_id=a,
                side='BUY' if delta > 0 else 'SELL', quantity_signed=delta, price_local=local,
                currency=meta[a]['currency'], usd_per_local=fx, notional_usd_signed=notional,
                transaction_fee_usd=commission, cash_change_usd=-notional-commission, reason=reason))
            assert cash >= -1e-6 and qty[a] >= 0, (ds, a, cash)

        rebalance = n == 1 or (n > 1 and ds[5:7] != days[n-1][5:7])
        tactical = n > 1 and ds[8:10] == '20'
        securities = lambda: sum(qty[a]*prices[a]['price_local']*prices[a]['usd_per_local'] for a in ids)
        if rebalance or tactical:
            month = (int(ds[:4])-2020)*12+int(ds[5:7])-1
            excluded = {month % 20, (month+9) % 20}
            weights = [0 if i in excluded else 1+.35*math.sin(.7*month+i) for i in range(20)]
            budget = .84*(cash+securities()-liability)
            delta = [budget*weights[i]/sum(weights)/(prices[a]['price_local']*prices[a]['usd_per_local'])-qty[a]
                     if rebalance else 0. for i, a in enumerate(ids)]
            if tactical:
                seller, buyer = (month+3) % 20, (month+12) % 20
                delta[seller] = -.08*qty[ids[seller]]
                m = prices[ids[seller]]
                value = -delta[seller]*m['price_local']*m['usd_per_local']
                m = prices[ids[buyer]]
                delta[buyer] = .98*value/(m['price_local']*m['usd_per_local'])
            for i in sorted(range(20), key=lambda i: (delta[i] >= 0, i)):
                execute(ids[i], delta[i], 'INITIAL_BUY' if n == 1 else 'MONTHLY_REBALANCE' if rebalance else 'TACTICAL')
        preliminary_nav = (cash+securities()-liability)/units
        scheduled = []
        # Causal scenario triggers: only this day's NAV and previous high are used.
        if ds >= '2021-01-01' and 'high' not in flags and preliminary_nav > peak:
            scheduled = [('SUBSCRIPTION', 2_000_000., 'Souscription sur nouveau plus-haut')]
            flags.add('high')
        if ds >= '2022-01-01' and 'drawdown' not in flags and preliminary_nav/peak-1 <= -.20:
            scheduled = [('SUBSCRIPTION', 1_500_000., 'Souscription en drawdown supérieur à 20 %')]
            flags.add('drawdown')
        if ds == '2023-01-20':
            scheduled = [('REDEMPTION', -3_000_000., 'Rachat partiel avant récupération du plus-haut')]
        if ds >= '2023-02-01' and 'drawdown' in flags and 'recovery' not in flags and preliminary_nav >= peak:
            scheduled = [('SUBSCRIPTION', 1_000_000., 'Souscription après récupération du plus-haut')]
            flags.add('recovery')
        if ds == '2025-11-20':
            scheduled = [('SUBSCRIPTION', 750_000., 'Deux mouvements opposés à NAV identique'),
                         ('REDEMPTION', -750_000., 'Deux mouvements opposés à NAV identique')]
        net_flow = sum(amount for _, amount, _ in scheduled)
        # Fund the net redemption and accrued fees before striking the dealing NAV.
        shortage = max(0., -net_flow+liability-cash)
        if shortage:
            sell_fraction = (shortage+1.)/(1-.0005)/securities()
            assert sell_fraction < 1
            for a in ids:
                execute(a, -qty[a]*sell_fraction, 'REDEMPTION_FUNDING')
        pre_flow_aum = cash+securities()-liability
        dealing_nav = pre_flow_aum/units
        for kind, amount, reason in scheduled:
            issued = amount/dealing_nav
            investor.append(dict(date=ds, type=kind, amount_usd=amount, dealing_nav_usd=dealing_nav,
                units_delta=issued, units_before=units, units_after=units+issued,
                prior_peak_nav_usd=peak, drawdown_before_flow=dealing_nav/peak-1, reason=reason))
            units += issued
            cash += amount
        paid = 0.
        if n == len(days)-1 or days[n+1][5:7] != ds[5:7]:
            paid, liability = liability, 0.
            cash -= paid
            events.append(dict(date=ds, type='MANAGEMENT_FEE_PAYMENT', asset_id='', amount_local=-paid,
                currency='USD', usd_per_local=1., amount_usd=-paid, reference='Règlement de la provision mensuelle'))
        aum = cash+securities()-liability
        nav = aum/units
        residual = aum-previous_aum-net_flow-price_pnl-fx_pnl-income+cost+fee
        assert abs(residual) < 1e-6 and abs(nav-dealing_nav) < 1e-10 and cash >= 0 and units > 0, (ds, residual)
        navs.append(dict(date=ds, nav_usd=nav, units=units, opening_units=previous_units,
            net_assets_usd=aum, pre_flow_net_assets_usd=pre_flow_aum, net_investor_flow_usd=net_flow,
            subscriptions_usd=sum(max(amount, 0) for _, amount, _ in scheduled),
            redemptions_usd=-sum(min(amount, 0) for _, amount, _ in scheduled),
            cash_usd=cash, securities_usd=securities(), management_liability_usd=liability,
            management_expense_usd=fee, management_paid_usd=paid, performance_expense_usd=0.,
            transaction_cost_usd=cost, dividends_usd=income, price_pnl_usd=price_pnl, fx_pnl_usd=fx_pnl,
            prior_peak_nav_usd=peak, nav_bridge_residual_usd=residual))
        for a in ids:
            m = prices[a]
            value = qty[a]*m['price_local']*m['usd_per_local']
            positions.append(dict(date=ds, asset_id=a, quantity=qty[a], value_usd=value, weight=value/aum))
        previous_aum, peak = aum, max(peak, nav)
    assert flags == {'high', 'drawdown', 'recovery'}, flags
    for a in ids:
        m = market[days[-1]][a]
        latent = sum(l['quantity']*(m['price_local']*m['usd_per_local']-l['price']*l['fx']) for l in lots[a])
        row = attribution[a]
        row.update(unrealized_usd=latent, total_price_pnl_usd=row['realized_usd']+latent,
                   total_with_dividends_usd=row['realized_usd']+latent+row['dividends_usd'])
    sums = {field: sum(r[field] for r in navs) for field in ('net_investor_flow_usd', 'subscriptions_usd',
        'redemptions_usd', 'management_expense_usd', 'management_paid_usd', 'transaction_cost_usd',
        'dividends_usd', 'price_pnl_usd', 'fx_pnl_usd')}
    returns = [b['nav_usd']/a['nav_usd']-1 for a, b in zip(navs, navs[1:])]
    vol = statistics.stdev(returns)*math.sqrt(252)
    peak, dd = 100., 0.
    for r in navs:
        peak = max(peak, r['nav_usd'])
        dd = min(dd, r['nav_usd']/peak-1)
    realized = sum(r['realized_usd'] for r in attribution.values())
    unrealized = sum(r['unrealized_usd'] for r in attribution.values())
    profit = navs[-1]['net_assets_usd']-10_000_000-sums['net_investor_flow_usd']
    assert abs(profit-(realized+unrealized+sums['dividends_usd']-sums['management_expense_usd']-sums['transaction_cost_usd'])) < 1e-5
    summary = dict(scenario='LO_FLOWS_2A_2020_2025', ending_nav_usd=navs[-1]['nav_usd'],
        ending_units=units, ending_aum_usd=navs[-1]['net_assets_usd'], net_profit_excluding_flows_usd=profit,
        total_return_decimal=navs[-1]['nav_usd']/100-1, observations=len(navs), orders=len(trades),
        investor_events=len(investor), realized_usd=realized, unrealized_usd=unrealized,
        realized_fx_usd=sum(r['realized_fx_usd'] for r in attribution.values()),
        performance_fee_usd=0., max_drawdown_decimal=dd, volatility_sample_252=vol,
        sharpe_rf_zero_252=statistics.mean(returns)*252/vol,
        roundtrip_fifo_matches=len(roundtrips), hit_rate=sum(r['pnl_usd'] > 0 for r in roundtrips)/len(roundtrips),
        profit_factor=sum(max(r['pnl_usd'], 0) for r in roundtrips)/-sum(min(r['pnl_usd'], 0) for r in roundtrips),
        median_holding_calendar_days=statistics.median(r['holding_days'] for r in roundtrips), **sums)
    annual = []
    previous_nav = 100.
    for year in range(2020, 2026):
        rows = [r for r in navs if r['date'].startswith(str(year))]
        annual.append(dict(year=year, ending_nav_usd=rows[-1]['nav_usd'], ending_units=rows[-1]['units'],
            ending_aum_usd=rows[-1]['net_assets_usd'], return_decimal=rows[-1]['nav_usd']/previous_nav-1,
            **{k: sum(r[k] for r in rows) for k in sums}))
        previous_nav = rows[-1]['nav_usd']
    for filename, rows in [('nav_daily', navs), ('positions_daily', positions), ('investor_flows', investor),
                            ('trades', trades), ('pnl_by_asset', list(attribution.values())), ('annual_results', annual),
                            ('fifo_matches', roundtrips)]:
        table(root/'RESULTATS_ATTENDUS'/f'{filename}.csv', rows)
    dump(root/'RESULTATS_ATTENDUS/summary.json', summary)
    export(root, days, market, assets, navs, positions, trades, events, dividends)
    return summary


def export(root, days, market, assets, navs, positions, trades, events, dividends):
    meta = {a['asset_id']: a for a in assets}
    orders = []
    for t in trades:
        a = t['asset_id']
        factor = math.prod(market[d][a]['split_ratio'] for d in days if d > t['date'])
        orders.append(dict(id=t['trade_id'], state='Done', tradeDate=t['date'], creationDateTime=t['date']+'T17:00:00+00:00',
            orderedQuantity=t['quantity_signed']*factor, executedQuantity=t['quantity_signed']*factor,
            executionPrice=dict(amount=t['price_local']/factor, currency=t['currency']), usedFxRate=t['usd_per_local'],
            underlying=dict(isin=a, name=meta[a]['name'], currency=t['currency'])))
    dump(root/'LO_2A Data.json', {'data': {'orders': {'items': orders}}})
    final = navs[-1]
    components = [dict(underlying=dict(isin=r['asset_id'], name=meta[r['asset_id']]['name'], currency=meta[r['asset_id']]['currency']),
                       position=r['quantity'], weight=r['weight']) for r in positions if r['date'] == days[-1] and r['quantity'] > 0]
    components.append(dict(underlying=dict(isin='', name='USD', currency='USD'), position=final['cash_usd'], weight=final['cash_usd']/final['net_assets_usd']))
    product = dict(isin='SYNTH_LO_FLOWS_2A', name='Fonds 2A — long only avec souscriptions et rachats', currency='USD')
    dump(root/'LO_2A Def.txt', {'data': {'products': {'items': [dict(**product, outstandingQuantity=final['units'],
        netAssetValue=dict(value=final['nav_usd'], date=days[-1]), components=components)]}}})
    table(root/'LO_2A timeseries.csv', [{'Date': date.fromisoformat(r['date']).strftime('%d.%m.%Y'),
        'Price': r['nav_usd'], 'Outstanding quantity': r['units']} for r in navs])
    table(root/'cash_events.csv', events)
    dump(root/'dividends.json', {'events': dividends})
    shutil.copyfile(root/'sources/market_data.json', root/'market_data.json')
    manifest = json.loads((root/'sources/manifest_template.json').read_text(encoding='utf-8'))
    manifest['product'] = product
    manifest['files'].update(composition='LO_2A Def.txt', nav_timeseries='LO_2A timeseries.csv', orders=['LO_2A Data.json'])
    params = manifest['params']
    # n_certs is inception capital, not the final outstanding quantity.
    # Preserve fractional closing quantities in the composition and NAV history.
    initial_units = navs[0]['units']
    assert initial_units == int(initial_units), 'This fixture starts with whole units'
    params.update(management_fee_pct=1., perf_fee_pct=0., txn_cost_pct=.05, n_certs=int(initial_units), performance_crystallization='daily')
    params['dividends']['documentation'] = 'Dividendes fournis, conservés en cash ; paiement à la date ex, sans retenue.'
    ts_date = days[1]
    basket = []
    for r in positions:
        if r['date'] != ts_date or not r['quantity']:
            continue
        a = r['asset_id']
        m = market[ts_date][a]
        basket.append(dict(isin=a, name=meta[a]['name'], weight_pct=r['weight']*100,
            qty_per_cert=r['quantity']/navs[1]['units'], fixing_price=m['price_local'], ccy=meta[a]['currency'],
            fx_usd_per_local=m['usd_per_local'], initial_quantity=r['quantity']))
    params['reference_portfolio'] = dict(start_date=ts_date, positions=basket)
    # The frozen benchmark sector weights/returns remain unchanged; fund weights are its own TS.
    dump(root/'manifest.json', manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base', type=Path)
    parser.add_argument('--unified', type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    source = root/'sources'
    source.mkdir(parents=True, exist_ok=True)
    if args.base:
        for name in ('assets.csv', 'prices_daily.csv', 'fx_daily.csv'):
            shutil.copyfile(args.base/'inputs'/name, source/name)
        shutil.copyfile(args.base/'sources/provenance.json', source/'fx_provenance.json')
    if args.unified:
        shutil.copyfile(args.unified/'market_data.json', source/'market_data.json')
        shutil.copyfile(args.unified/'manifest.json', source/'manifest_template.json')
    dump(root/'hypotheses.json', dict(
        initial_capital_usd=10000000, initial_units=100000, initial_nav_usd=100,
        management_fee_rate=.01, transaction_fee_rate=.0005, performance_fee_rate=0,
        performance_hwm='Not applicable: no performance fee; prior_peak_nav is a drawdown diagnostic only',
        fee_basis='Previous closing net AUM, ACT/365 fixed, paid last weekday of month',
        dealing='Fixed USD amounts at same-day closing NAV after trades, expenses and dividends; fractional units',
        flow_order='Value portfolio; fund net redemption including costs; strike NAV; issue/cancel units; pay accrued fees',
        settlement_lag_days=0, subscription_redemption_fee_rate=0, swing_pricing=False,
        redemption_funding='Sell securities pro rata if cash cannot cover net redemption and accrued management fees; costs borne by fund',
        subscription_investment='Cash held until next scheduled monthly or tactical trade',
        dividends='Cash; opening post-split holdings; ex-date payment; no withholding; no automatic reinvestment',
        cash_currency='USD', cash_interest_rate=0, units_precision='Binary64, no cent or share rounding',
        calendar='Weekdays, including local holidays: synthetic exchanges; frozen ECB FX forward-filled',
        scenario_selection='Causal NAV/high-water-price triggers plus fixed dates; designed test scenario, not a backtest of investor behaviour',
        missing_capabilities='Gross investor ledger is a separate audit file; the application receives daily closing outstanding units',
        no_flow_performance_fee_equalization='Not covered; reserved for fund 2B',
        independent_oracle_scope='NAV, AUM, cash, holdings, fees, dividends, FIFO attribution, core trading/risk and investor movements; not all A-K scores'))
    summary = generate(root)
    generator = root/'generator/build_flows_2a.py'
    generator.parent.mkdir(exist_ok=True)
    if generator.resolve() != Path(__file__).resolve():
        shutil.copyfile(__file__, generator)
    verifier = Path(__file__).with_name('verify_flows_2a.py')
    if verifier.exists() and verifier.resolve() != (generator.parent/verifier.name).resolve():
        shutil.copyfile(verifier, generator.parent/verifier.name)
    dump(root/'source_hashes.json', {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.iterdir()) if p.is_file()})
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
