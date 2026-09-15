"""Régénère `backend/app/core/payscript/catalogue.py` depuis le catalogue JSON.

Le catalogue des produits génériques vit côté frontend
(`frontend/src/data/productCatalogue.json`) : c'est la liste du module
« Modèles de produits », qui ouvre le Pricer complété à partir d'une fiche, d'un
nombre de sous-jacents et d'un ténor. Le serveur en garde une copie, pour que
les fiches se testent — compilation, pricing sur un calendrier généré — et
puissent servir plus tard au corpus de l'assistant, aux RFQ ou aux jeux UAT.

Le JSON est la source unique : un script écrit ligne à ligne s'y relit sans
extraction fragile, et Python comme JavaScript le lisent tels quels.
`backend/tests/test_product_catalogue.py` rejoue la génération et échoue si la
copie n'est plus à jour : la duplication est mécanique et vérifiée.

Usage :  .venv\\Scripts\\python.exe backend\\scripts\\sync_product_catalogue.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from pprint import pformat

ROOT = Path(__file__).resolve().parents[2]
JSON_SOURCE = ROOT / "frontend" / "src" / "data" / "productCatalogue.json"
PY_TARGET = ROOT / "backend" / "app" / "core" / "payscript" / "catalogue.py"

HEADER = '''"""Catalogue des produits génériques — module « Modèles de produits ».

GÉNÉRÉ : ne pas éditer à la main. Source :
`frontend/src/data/productCatalogue.json` (liste du module « Modèles de
produits » du Pricer).

Régénérer avec `backend/scripts/sync_product_catalogue.py`.
`backend/tests/test_product_catalogue.py` vérifie que les deux restent
identiques, que chaque fiche compile et qu'elle price sur un calendrier généré.

Une fiche porte un script générique — PARAM avec unité et valeur initiale,
CONSTAT sans date — et le rôle de chaque CONSTAT : `observations` (échéancier
du strike à la maturité), `maturity` (date unique à maturité), `strike_window`
(fenêtre de départ STRIKE_FIX). Les dates viennent du Pricer, jamais du script.
"""
'''


def build() -> str:
    data = json.loads(JSON_SOURCE.read_text(encoding="utf-8"))
    products: dict[str, dict] = {}
    for product in data["products"]:
        key = product["key"]
        if key in products:
            raise SystemExit(f"fiche en double dans le catalogue : {key}")
        entry = {k: v for k, v in product.items() if k not in ("key", "script")}
        entry["script"] = "\n".join(product["script"])
        products[key] = entry
    tenors = {t["code"]: {"months": t["months"], "label": t["label"]} for t in data["tenors"]}
    families = {f["key"]: f["label"] for f in data["families"]}
    out = [
        HEADER,
        f"CATALOGUE_VERSION = {data['version']!r}",
        "",
        "TENORS: dict[str, dict] = " + pformat(tenors, sort_dicts=False, width=100),
        "",
        "FAMILIES: dict[str, str] = " + pformat(families, sort_dicts=False, width=100),
        "",
        "PRODUCTS: dict[str, dict] = " + pformat(products, sort_dicts=False, width=100),
        "",
        "",
        "def by_family() -> dict[str, list[str]]:",
        '    """Clés de fiche par famille, dans l\'ordre du catalogue."""',
        "    groups: dict[str, list[str]] = {}",
        "    for key, product in PRODUCTS.items():",
        '        groups.setdefault(product["family"], []).append(key)',
        "    return groups",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    content = build()
    if PY_TARGET.exists() and PY_TARGET.read_text(encoding="utf-8") == content:
        print(f"déjà à jour : {PY_TARGET.relative_to(ROOT)}")
        return 0
    PY_TARGET.write_text(content, encoding="utf-8")
    print(f"écrit {PY_TARGET.relative_to(ROOT)} — {content.count(chr(10))} lignes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
