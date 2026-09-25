"""Import compatibility only: the independent fund oracle never imports Studies."""
import csv
import json
from pathlib import Path

import pytest

from backend.app.core.amc_manifest import detect_study_folder


FIXTURE = Path(__file__).resolve().parents[2] / 'artifacts/studies/LO_FLOWS_2A_2020_2025'


@pytest.mark.skipif(not (FIXTURE / 'manifest.json').exists(), reason='Generate local fund 2A first')
def test_generated_flows_fixture_scans_with_initial_units():
    scanned = detect_study_folder(str(FIXTURE))
    manifest = scanned['manifest']
    assert manifest['params']['n_certs'] == 100000
    assert not scanned['missing_manual_fields']
    with (FIXTURE / manifest['files']['nav_timeseries']).open(encoding='utf-8', newline='') as f:
        navs = list(csv.DictReader(f))
    assert manifest['params']['n_certs'] == float(navs[0]['Outstanding quantity'])
    final_units = float(navs[-1]['Outstanding quantity'])
    assert final_units == pytest.approx(110533.57791513814, abs=1e-8, rel=0)
    composition = json.loads((FIXTURE / manifest['files']['composition']).read_text(encoding='utf-8'))
    assert composition['data']['products']['items'][0]['outstandingQuantity'] == final_units


def test_scan_keeps_inception_units_separate_from_final_snapshot(tmp_path):
    manifest = {
        'product': {'isin': 'TEST_FLOWS', 'currency': 'USD'},
        'params': {'n_certs': 100000},
        'files': {'composition': 'snapshot.json'},
    }
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    (tmp_path / 'snapshot.json').write_text(json.dumps({'outstandingQuantity': 110533.57791513814}), encoding='utf-8')
    assert detect_study_folder(str(tmp_path))['manifest']['params']['n_certs'] == 100000


@pytest.mark.skipif(not (FIXTURE / 'manifest.json').exists(), reason='Generate local fund 2A first')
def test_generated_dividend_ledgers_agree_without_double_counting(tmp_path):
    from backend.app.core.amc_dividends import prepare_dividends
    from backend.app.core.amc_orderbook import load_study_data

    manifest = detect_study_folder(str(FIXTURE))['manifest']
    data = load_study_data(str(FIXTURE), manifest['files'], as_of='2025-12-31',
        require_orders=True, require_composition=True, product_currency='USD',
        valuation_source='composition', orders_split_adjusted=True)
    kwargs = dict(path=str(FIXTURE / 'dividends.json'), policy=manifest['params']['dividends'],
        orders=data['orders'], start=data['nav'][0]['date'], end=data['nav'][-1]['date'], fund_currency='USD',
        initial_positions=[], units=100000, transaction_fee_pct=.05)
    combined = prepare_dividends(legacy_path=str(FIXTURE / 'cash_events.csv'), **kwargs)
    dated_only = prepare_dividends(legacy_path='', **kwargs)
    expected = json.loads((FIXTURE / 'RESULTATS_ATTENDUS/summary.json').read_text())['dividends_usd']
    assert combined['totals']['net_income_prod'] == pytest.approx(expected, abs=.00001, rel=0)
    assert combined['totals'] == dated_only['totals']
    assert not combined['issues']
    # Reproduce the actual reported failure by stripping payments from the cash ledger.
    with (FIXTURE / 'cash_events.csv').open(encoding='utf-8', newline='') as f:
        payments = list(csv.DictReader(f))
    incomplete = tmp_path / 'incomplete_cash_events.csv'
    with incomplete.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(payments[0]))
        writer.writeheader()
        writer.writerows(r for r in payments if r['type'] != 'DIVIDEND')
    with pytest.raises(ValueError, match='Paiements de dividendes contradictoires'):
        prepare_dividends(legacy_path=str(incomplete), **kwargs)
