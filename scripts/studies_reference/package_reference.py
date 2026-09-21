"""Reproduce, verify, tamper-test, then package the frozen reference."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
import hashlib
from verify_extended import verify


def package(root):
    root = root.resolve()
    scripts = Path(__file__).resolve().parent
    destination = root / 'generator'
    destination.mkdir(exist_ok=True)
    for path in scripts.glob('*.py'):
        if path.resolve() != (destination / path.name).resolve(): shutil.copy2(path, destination / path.name)
    for test in ['test_reference.py', 'test_e_install.py']:
        subprocess.run([sys.executable, str(destination / test)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(destination / 'build_extended.py'), '--output', str(root)], check=True, stdout=subprocess.DEVNULL)
    first = json.loads((root / 'checksums.json').read_text(encoding='utf-8'))
    subprocess.run([sys.executable, str(destination / 'build_extended.py'), '--output', str(root)], check=True, stdout=subprocess.DEVNULL)
    second = json.loads((root / 'checksums.json').read_text(encoding='utf-8'))
    assert first == second, 'Régénération non identique'
    validation = verify(root)
    with tempfile.TemporaryDirectory(prefix='studies-reference-tamper-') as tmp:
        altered = Path(tmp) / 'package'
        shutil.copytree(root, altered, ignore=shutil.ignore_patterns('comparison', '__pycache__'))
        target = altered / 'inputs/benchmark_daily.csv'
        target.write_bytes(target.read_bytes() + b'alteration')
        try: verify(altered)
        except AssertionError as exc:
            assert 'Fichier altéré' in str(exc)
        else: raise AssertionError('Altération non détectée')
    validation.update(reproduction_identical=True, altered_benchmark_rejected=True, analytic_tests=10, installer_tests=2)
    (root / 'reference/verification.json').write_text(json.dumps(validation, indent=2), encoding='utf-8')
    archive = root.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(root.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                z.write(path, str(Path(root.name) / path.relative_to(root)))
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{sha}  {archive.name}\n', encoding='utf-8')
    print(json.dumps({'verification': validation, 'zip': str(archive), 'sha256': sha}, indent=2))


if __name__ == '__main__': package(Path(sys.argv[1]))
