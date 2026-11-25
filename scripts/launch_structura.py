"""Open Structura's desktop launcher with the project's interpreter.

Without arguments (Start menu shortcut, lancer_structura.bat, backend/run.py),
the version chooser of the sibling structura-react checkout opens when it is
present, offering the Vue and React versions. ``--vue`` opens the Vue menu
directly: lancer_structura.vbs passes it, and the chooser's "Ouvrir Vue" runs
that script, so choosing Vue never loops back to the chooser.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VUE_ONLY = "--vue"
STALE_ENVIRONMENT = ("Le menu Structura ne peut pas démarrer : {error}.\n\n"
                     "Le dossier .venv ne correspond plus aux dépendances du dépôt, "
                     "par exemple après un git pull. Depuis la racine de Structura :\n\n"
                     ".venv\\Scripts\\python.exe -m pip install --require-hashes -r requirements.lock.txt")


def show_error(message):
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Structura — lancement impossible", message, parent=root)
    root.destroy()


def version_chooser():
    # Resolved from ROOT at call time, so a throwaway checkout has no sibling.
    return ROOT.with_name("structura-react") / "scripts" / "launch_versions.py"


def main(argv=None):
    vue_only = VUE_ONLY in (sys.argv[1:] if argv is None else argv)
    project_python = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not project_python.exists():
        project_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not project_python.exists():
        raise RuntimeError("Python du projet introuvable ; vérifiez le dossier .venv.")
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    chooser = version_chooser()
    if not vue_only and chooser.is_file():
        # structura-react has no interpreter of its own: its shortcut runs this one.
        subprocess.Popen([str(project_python), "-B", str(chooser)], cwd=chooser.parents[1],
                         creationflags=no_window)
        return
    if Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        # Do not replace or close an IDE's Python kernel when launched there.
        subprocess.Popen([str(project_python), str(Path(__file__).resolve()), *([VUE_ONLY] if vue_only else [])],
                         creationflags=no_window)
        return
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from app.hybrid.launcher import main as open_menu
    except ImportError as exc:
        # Under pythonw a failed import shows nothing: say so, then fail as before.
        show_error(STALE_ENVIRONMENT.format(error=exc))
        raise
    open_menu()


if __name__ == "__main__":
    main()
