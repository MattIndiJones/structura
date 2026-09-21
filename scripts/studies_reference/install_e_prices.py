"""Install only the isolated E USD proxy series. Never replace an existing key.

Usage: python install_e_prices.py PACKAGE --store REPO/backend/data/underlying_prices
Existing identical series are accepted; any collision aborts before writing.
"""
from pathlib import Path
import argparse
import json
import pandas as pd


def install(root, store):
    planned = []
    for source in sorted((root / 'manual_prices_E').glob('SYNTH_E_USD_*.json')):
        if not source.stem.removeprefix('SYNTH_E_USD_').isdigit(): raise ValueError('Identifiant inattendu')
        f = pd.DataFrame(json.loads(source.read_text(encoding='utf-8')))
        f['date'] = pd.to_datetime(f.date)
        f = f.set_index('date')[['close']]
        f.attrs.update(currency='USD', source='independent_E_USD_total_return_proxy')
        destination = store / (source.stem + '.parquet')
        if destination.exists():
            existing = pd.read_parquet(destination)
            if not existing.equals(f) or existing.attrs.get('currency') != 'USD':
                raise ValueError(f'Collision : {destination}. Aucun fichier remplacé.')
        else: planned.append((destination, f))
    if not list((root / 'manual_prices_E').glob('SYNTH_E_USD_*.json')): raise ValueError('Aucune série fournie')
    store.mkdir(parents=True, exist_ok=True)
    for path, frame in planned: frame.to_parquet(path)
    print(f'{len(planned)} séries E créées ; aucune série existante remplacée.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('package', type=Path)
    parser.add_argument('--store', required=True, type=Path)
    args = parser.parse_args()
    install(args.package.resolve(), args.store.resolve())
