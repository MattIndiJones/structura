"""Fixture integrity tests; run from repository root with unittest discovery."""
import contextlib
import hashlib
import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from verify_flows_2a import verify


REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO/'artifacts/studies/LO_FLOWS_2A_2020_2025'


@unittest.skipUnless((FIXTURE/'manifest.json').exists(), 'Generate local 2A fixture first')
class FlowFixtureTests(unittest.TestCase):
    def test_decimal_replay(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertGreater(verify(FIXTURE), 90000)

    def test_offline_reproduction(self):
        with tempfile.TemporaryDirectory(prefix='studies-2a-reproduce-') as tmp:
            root = Path(tmp)
            shutil.copytree(FIXTURE/'sources', root/'sources')
            subprocess.run([sys.executable, str(REPO/'scripts/studies_reference/build_flows_2a.py'),
                            '--output', str(root)], check=True, capture_output=True)
            # Every generated input and numeric result must reproduce byte for byte.
            generated = list((root/'RESULTATS_ATTENDUS').glob('*')) + [p for p in root.iterdir() if p.is_file()]
            for p in generated:
                self.assertEqual(hashlib.sha256(p.read_bytes()).digest(),
                                 hashlib.sha256((FIXTURE/p.relative_to(root)).read_bytes()).digest(), str(p))

    def test_corrupt_nav_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='studies-2a-tamper-') as tmp:
            root = Path(tmp)/'fixture'
            shutil.copytree(FIXTURE, root)
            nav = root/'RESULTATS_ATTENDUS/nav_daily.csv'
            content = nav.read_text(encoding='utf-8')
            self.assertIn('2020-01-01,100.0,', content)
            nav.write_text(content.replace('2020-01-01,100.0,', '2020-01-01,101.0,', 1), encoding='utf-8')
            with self.assertRaisesRegex(AssertionError, 'NAV reconstruite'):
                verify(root)

    def test_missing_gross_flow_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='studies-2a-flow-') as tmp:
            root = Path(tmp)/'fixture'
            shutil.copytree(FIXTURE, root)
            ledger = root/'RESULTATS_ATTENDUS/investor_flows.csv'
            lines = ledger.read_text(encoding='utf-8').splitlines()
            ledger.write_text('\n'.join(line for line in lines if not line.startswith('2025-11-20,SUBSCRIPTION'))+'\n', encoding='utf-8')
            with self.assertRaises(AssertionError):
                verify(root)


if __name__ == '__main__':
    unittest.main()
