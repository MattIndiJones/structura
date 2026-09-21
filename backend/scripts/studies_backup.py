"""Consistent SQLite backup and verified restore into a new directory only."""
from __future__ import annotations
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import zipfile


def backup(database: Path, archive: Path, sources: list[Path] | None = None):
    database, archive = database.resolve(), archive.resolve()
    if not database.is_file():
        raise ValueError("Base source introuvable")
    if archive.exists():
        raise ValueError("L’archive existe déjà : choisissez un nouveau nom")
    with tempfile.TemporaryDirectory() as temp:
        snapshot = Path(temp) / "structura.db"
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(snapshot)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Contrôle SQLite échoué")
        files = {"database/structura.db": snapshot}
        for index, source in enumerate(sources or []):
            source = source.resolve()
            if not source.exists():
                raise ValueError(f"Source introuvable : {source}")
            for path in ([source] if source.is_file() else source.rglob("*")):
                if path.is_file():
                    if path.is_symlink() or not path.resolve().is_relative_to(source if source.is_dir() else source.parent):
                        raise ValueError("Lien extérieur interdit dans la sauvegarde")
                    relative = path.name if source.is_file() else path.relative_to(source).as_posix()
                    files[f"sources/{index}/{relative}"] = path
        hashes = {}
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as out:
            for name, path in files.items():
                content = path.read_bytes()
                hashes[name] = hashlib.sha256(content).hexdigest()
                out.writestr(name, content)
            out.writestr("checksums.json", json.dumps(hashes, sort_keys=True))
    return hashes


def restore(archive: Path, destination: Path):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("La destination doit être un nouveau dossier ; aucun écrasement autorisé")
    with zipfile.ZipFile(archive) as src:
        hashes = json.loads(src.read("checksums.json"))
        if set(src.namelist()) != set(hashes) | {"checksums.json"} or len(src.namelist()) != len(hashes) + 1:
            raise ValueError("Contenu de l’archive incohérent")
        for name, expected in hashes.items():
            target = (destination / name).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("Chemin extérieur interdit dans l’archive")
            if hashlib.sha256(src.read(name)).hexdigest() != expected:
                raise ValueError(f"Empreinte invalide : {name}")
        destination.mkdir(parents=True, exist_ok=False)
        for name in hashes:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(src.read(name))
    with closing(sqlite3.connect((destination / "database/structura.db").as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Base restaurée invalide")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("backup")
    create.add_argument("--database", type=Path, required=True)
    create.add_argument("--archive", type=Path, required=True)
    create.add_argument("--source", type=Path, action="append", default=[])
    recover = commands.add_parser("restore")
    recover.add_argument("--archive", type=Path, required=True)
    recover.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "backup":
        backup(args.database, args.archive, args.source)
    else:
        restore(args.archive, args.destination)
    print("Opération terminée et contrôlée.")
