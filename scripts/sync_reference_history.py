"""Explicit Yahoo max-history audit for every ticker in an existing installation.

The business database is opened read-only. Only market observations and the audit
report are written; no application bootstrap, account or deal migration runs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def reference_tickers(database):
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        rows = connection.execute('SELECT ticker, label, group_name, active FROM underlyings ORDER BY ticker, id').fetchall()
    reference = {}
    for ticker, label, group, active in rows:
        ticker = ticker.strip().upper()
        if not ticker:
            continue
        item = reference.setdefault(ticker, dict(ticker=ticker, label=label, groups=[], active=bool(active)))
        item['groups'].append(group)
        item['active'] = item['active'] or bool(active)
    return list(reference.values()), len(rows)


def save_report(path, report):
    """Windows virus scanners can briefly hold an otherwise replaceable report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.pending.json')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for attempt in range(20):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(.1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation-config', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--tickers', nargs='+', help='Optional explicit subset of reference tickers')
    args = parser.parse_args()
    from backend.app.hybrid.config import read_config
    config = read_config(str(args.installation_config.resolve()))
    os.environ['STRUCTURA_INSTALLATION_CONFIG'] = str(args.installation_config.resolve())
    os.environ['STRUCTURA_DATA_DIR'] = str(config.data_dir)
    if os.environ.get('STRUCTURA_SCENARIO_MARKET'):
        raise RuntimeError('Un scénario ne peut pas qualifier les données Yahoo réelles.')
    from backend.app.services.market_data import load_hist_prices, vider_cache_prix
    from backend.app.services.market_history import local_history
    from backend.app.runtime import business_today
    reference, reference_rows = reference_tickers(config.data_dir / 'structura.db')
    if args.tickers:
        selected = {ticker.upper() for ticker in args.tickers}
        if selected - {item['ticker'] for item in reference}:
            raise ValueError('Ticker absent du référentiel.')
        reference = [item for item in reference if item['ticker'] in selected]
    report_path = (args.report or config.data_dir / 'market-history-audit.json').resolve()
    report = dict(started_at=datetime.now(timezone.utc).isoformat(), installation_id=str(config.installation_id),
                  reference_rows=reference_rows, distinct_tickers=len(reference), end=business_today().isoformat(),
                  provider='YAHOO_FINANCE', history_scope='MAX_AVAILABLE_REQUESTED', results=[])
    for number, item in enumerate(reference, 1):
        outcome = dict(item, ok=False, bases={})
        for adjusted, name in ((False, 'unadjusted'), (True, 'adjusted')):
            basis = dict(ok=False, attempts=0)
            for attempt in range(2):
                basis['attempts'] += 1
                try:
                    result = load_hist_prices([item['ticker']], None, report['end'], adjusted=adjusted,
                                              raw_history=True, full_history=True)
                    if result.get('error'):
                        raise ValueError(str(result.get('missing_reasons') or result['error']))
                    values, source = local_history(item['ticker'], '1900-01-01', report['end'], adjusted, prefer_full=True)
                    if values is None or values.empty or source.get('history_scope') != 'MAX_AVAILABLE_REQUESTED':
                        raise ValueError('Historique maximal absent après écriture et relecture.')
                    basis.update(ok=True, rows=len(values), first_date=values.index[0].date().isoformat(),
                        last_date=values.index[-1].date().isoformat(), source=source)
                    basis['usable_for_backtest'] = len(values) >= 2
                    basis.pop('error', None)
                    break
                except Exception as exc:
                    basis['error'] = f'{type(exc).__name__}: {exc}'
                    if attempt == 0:
                        time.sleep(3)
            outcome['bases'][name] = basis
        outcome['ok'] = all(basis['ok'] and basis.get('usable_for_backtest') for basis in outcome['bases'].values())
        report['results'].append(outcome)
        report.update(completed=len(report['results']), succeeded=sum(row['ok'] for row in report['results']),
                      failed=sum(not row['ok'] for row in report['results']), updated_at=datetime.now(timezone.utc).isoformat())
        report['basis_summary'] = {name: dict(
            persisted=sum(row['bases'][name]['ok'] for row in report['results']),
            usable_for_backtest=sum(bool(row['bases'][name].get('usable_for_backtest')) for row in report['results']),
            failed=sum(not row['bases'][name]['ok'] for row in report['results']))
            for name in ('unadjusted', 'adjusted')}
        save_report(report_path, report)
        detail = str({name: (basis.get('rows'), basis.get('first_date'), basis.get('last_date'), basis.get('error'))
                      for name, basis in outcome['bases'].items()})
        print(f"[{number}/{len(reference)}] {item['ticker']} {'OK' if outcome['ok'] else 'ECHEC'} {detail}", flush=True)
        time.sleep(.4)
        vider_cache_prix()
    print(f"Rapport: {report_path} ; {report['succeeded']} OK, {report['failed']} échec(s)", flush=True)
    return 1 if report['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
