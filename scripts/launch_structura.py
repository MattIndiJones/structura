"""Open the desktop menu with the project's interpreter, without arguments."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
def main():
    project_python = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not project_python.exists():
        project_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not project_python.exists():
        raise RuntimeError("Python du projet introuvable ; vérifiez le dossier .venv.")
    if Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        # Do not replace or close an IDE's Python kernel when launched there.
        subprocess.Popen([str(project_python), str(Path(__file__).resolve())],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return
    sys.path.insert(0, str(ROOT / "backend"))
    from app.hybrid.launcher import main as open_menu
    open_menu()


if __name__ == "__main__":
    main()
