"""Exercise the optional installer only in temporary directories."""
import unittest
import tempfile
import json
from pathlib import Path
from install_e_prices import install


class InstallerTests(unittest.TestCase):
    def test_idempotence_and_collision_preserve_existing_prices(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prices = root / 'manual_prices_E'
            prices.mkdir()
            source = prices / 'SYNTH_E_USD_02.json'
            source.write_text(json.dumps([{'date': '2020-01-02', 'close': 100}]), encoding='utf-8')
            store = root / 'store'
            install(root, store)
            target = store / 'SYNTH_E_USD_02.parquet'
            original = target.read_bytes()
            install(root, store)
            self.assertEqual(original, target.read_bytes())
            source.write_text(json.dumps([{'date': '2020-01-02', 'close': 999}]), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Collision'): install(root, store)
            self.assertEqual(original, target.read_bytes())

    def test_no_price_input_creates_no_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, 'Aucune série'): install(root, root / 'store')
            self.assertFalse((root / 'store').exists())


if __name__ == '__main__': unittest.main()
