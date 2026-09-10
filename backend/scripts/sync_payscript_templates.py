"""Régénère `backend/app/core/payscript/templates.py` depuis le fichier JS.

La bibliothèque d'exemples PayScript vit côté frontend
(`frontend/src/data/payscriptTemplates.js`) : c'est le sélecteur d'exemples de
l'éditeur et la typologie produit du module RFQ. L'assistant IA en a besoin
côté serveur, comme corpus few-shot — l'appel au modèle part du backend.

Plutôt que de recopier 16 scripts à la main (et de les laisser diverger),
ce script les extrait et génère le module Python.
`backend/tests/test_payscript_templates.py` rejoue l'extraction et échoue si le
fichier généré n'est plus à jour : la duplication est donc mécanique et
vérifiée, jamais silencieuse.

Usage :  .venv\\Scripts\\python.exe backend\\scripts\\sync_payscript_templates.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS_SOURCE = ROOT / "frontend" / "src" / "data" / "payscriptTemplates.js"
PY_TARGET = ROOT / "backend" / "app" / "core" / "payscript" / "templates.py"

HEADER = '''"""Bibliothèque de scripts PayScript de référence — corpus d'exemples.

GÉNÉRÉ : ne pas éditer à la main. Source :
`frontend/src/data/payscriptTemplates.js` (sélecteur d'exemples de l'éditeur et
typologie produit du module RFQ).

Régénérer avec `backend/scripts/sync_payscript_templates.py`.
`backend/tests/test_payscript_templates.py` vérifie que les deux restent
identiques et que chaque script compile.

Ce sont les exemples few-shot envoyés au modèle par l'assistant IA : des
scripts qui pricent réellement ici, pas de la syntaxe plausible.
"""
'''


def extract(js_text: str) -> tuple[dict[str, tuple[str, str]], list[tuple[str, str]]]:
    """(métadonnées par clé, [(clé, script)] en mode normal).

    Le mode normal seulement : ses dates `AT` sont écrites en dur, donc ses
    scripts se compilent et se pricent tels quels. Les variantes expert
    référencent des CONSTAT dont les valeurs vivent dans l'interface — un
    exemple que le modèle ne pourrait pas reproduire de façon autonome."""
    meta_block = re.search(r"export const templateMeta = \[(.*?)\n\]", js_text, re.S)
    if not meta_block:
        raise SystemExit("templateMeta introuvable dans le fichier JS.")
    # `expertOnly` sort du corpus : ces modèles constatent sur une période, et
    # leur fenêtre vit dans un CONSTAT dont les valeurs sont à l'écran. Le
    # modèle ne pourrait pas les reproduire seul, et ils ne se pricent pas tels
    # quels. Le filtre est explicite pour ne pas dépendre du fait qu'une regex
    # plus étroite les rate — elle finirait par les rattraper.
    meta = {
        k: (label, group)
        for k, label, group, expert_only in re.findall(
            r"\{\s*key:\s*'([^']+)',\s*label:\s*'([^']+)',\s*group:\s*'([^']+)'"
            r"(\s*,\s*expertOnly:\s*true)?\s*\}",
            meta_block.group(1))
        if not expert_only
    }
    ex_block = re.search(r"export const examples = \{(.*?)\n\}", js_text, re.S)
    if not ex_block:
        raise SystemExit("bloc `examples` introuvable dans le fichier JS.")
    examples = re.findall(r"(\w+):\s*`([^`]*)`", ex_block.group(1))
    return meta, examples


def render(meta: dict, examples: list) -> str:
    out = [HEADER, "TEMPLATES: dict[str, dict] = {"]
    for key, script in examples:
        label, group = meta.get(key, (key, ""))
        out += [
            f"    {key!r}: {{",
            f"        \"label\": {label!r},",
            f"        \"group\": {group!r},",
            f"        \"script\": {script!r},",
            "    },",
        ]
    out += [
        "}",
        "",
        "",
        "def by_group() -> dict[str, list[str]]:",
        '    """Clés de template par famille de produit."""',
        "    g: dict[str, list[str]] = {}",
        "    for key, tpl in TEMPLATES.items():",
        '        g.setdefault(tpl["group"], []).append(key)',
        "    return g",
        "",
    ]
    return "\n".join(out)


def build() -> str:
    meta, examples = extract(JS_SOURCE.read_text(encoding="utf-8"))
    manquants = [k for k, _ in examples if k not in meta]
    if manquants:
        raise SystemExit(f"exemples sans entrée templateMeta : {manquants}")
    return render(meta, examples)


def main() -> int:
    content = build()
    if PY_TARGET.exists() and PY_TARGET.read_text(encoding="utf-8") == content:
        print(f"déjà à jour : {PY_TARGET.relative_to(ROOT)}")
        return 0
    PY_TARGET.write_text(content, encoding="utf-8")
    n = content.count('"script":')
    print(f"écrit {PY_TARGET.relative_to(ROOT)} — {n} scripts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
