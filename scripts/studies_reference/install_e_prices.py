"""Install only the isolated E USD proxy series. Never replace an existing key.

Usage: python install_e_prices.py PACKAGE --store REPO/backend/data/underlying_prices
Existing identical series are accepted; any collision aborts before writing.
"""
from pathlib import Path
import argparse
import json
import pandas as pd


def install(root, store):
    from backend.app.core import market_storage
    planned = []
    for source in sorted((root / 'manual_prices_E').glob('SYNTH_E_USD_*.json')):
        if not source.stem.removeprefix('SYNTH_E_USD_').isdigit(): raise ValueError('Identifiant inattendu')
        f = pd.DataFrame(json.loads(source.read_text(encoding='utf-8')))
        f = f.set_index('date')[['close']]
        f = market_storage.validate_frame(f)
        f.attrs.update(currency='USD', source='independent_E_USD_total_return_proxy',
                       price_type='TOTAL_RETURN_NAV',unit='CURRENCY')
        destination = store / (source.stem + '.parquet')
        planned.append((destination, f))
    if not list((root / 'manual_prices_E').glob('SYNTH_E_USD_*.json')): raise ValueError('Aucune série fournie')
    created = 0
    with market_storage.store_context(store.resolve().parent):
        with market_storage.transaction() as pending:
            for destination,frame in planned:
                existing = pending.path(destination)
                if existing.exists():
                    value = pd.read_parquet(existing)
                    if not value.equals(frame) or value.attrs.get('currency') != 'USD':
                        raise ValueError(f'Collision : {destination}. Aucun fichier remplacé.')
                else:
                    pending.parquet(destination,frame)
                    created += 1
    print(f'{created} séries E créées ; aucune série existante remplacée.')


if __name__ == '__main__':
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    parser = argparse.ArgumentParser()
    parser.add_argument('package', type=Path)
    parser.add_argument('--store', required=True, type=Path)
    args = parser.parse_args()
    install(args.package.resolve(), args.store.resolve())
