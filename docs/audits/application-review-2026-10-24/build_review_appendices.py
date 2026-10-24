"""Render the static inventory as portable review appendices, without app imports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def write(name, rows):
    (OUT / name).write_text("\n".join(rows) + "\n", encoding="utf-8")


def clean(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def main():
    modules = read("PYTHON_SYMBOLS.json")
    files = read("SOURCE_MANIFEST.json")
    by_file = {f["path"]: f for f in files}
    reference = read("INSPECTION_REFERENCE.json")
    routes = read("API_ROUTES.json")
    rows = ["# Catalogue statique des routes API", "",
        "Extraction de décorateurs, sans démarrer FastAPI ni générer son OpenAPI.", "",
        "Une ligne est une déclaration de route. Les méthodes `API_ROUTE` portent une liste de méthodes.",
        "Les préfixes APIRouter simples sont précomposés. Les alias, fabriques imbriquées, montages et conditions restent à lire dans les déclarations ci-dessous.",
        "Le routeur de l'atelier est monté sous `/api/agent-workshop` et `/api/admin/agent-workshop` ; ses chemins locaux ne sont pas des URL racine.",
        "L'authentification peut être héritée d'un routeur ou de ses dépendances ; son absence dans une signature n'est pas une preuve de route publique.", ""]
    for module in modules:
        if not module["routes"]:
            continue
        rows.extend(["## " + module["path"], ""])
        for declaration in module.get("router_declarations", []):
            rows.extend(["```python", declaration, "```", ""])
        if module.get("mounts"):
            rows.extend(["Montages déclarés :", ""])
            rows.extend(f"- Ligne {m['line']} : `{m['call']}`" for m in module["mounts"])
            rows.append("")
        rows.extend(["| Méthode | Chemin local/préfixé | Fonction | Ligne |", "|---|---|---|---|"])
        for route in sorted(module["routes"], key=lambda x: x["line"]):
            methods = ",".join(route.get("declared_methods") or []) or route["method"]
            rows.append(f"| {methods} | `{clean(route['local_full_path'])}` | `{route['function']}` | {route['line']} |")
        rows.append("")
    write("API_CATALOGUE.md", rows)

    rows = ["# Modèles, contrats et champs", "",
        "Extraction statique des classes de persistance et contrats Pydantic retenus.",
        "Les champs d'une classe héritée ne sont pas répétés ; lire sa classe de base.",
        "Une classe déclarée ne prouve ni table migrée ni fonctionnalité active. Les contraintes de service, validators, migrations et triggers restent déterminants.",
        "Les définitions sont du code source, jamais des valeurs lues dans une base privée.", ""]
    for model in read("MODELS_AND_FIELDS.json"):
        rows.extend([f"## {model['name']}", "",
            f"Source : `{model['path']}:{model['line']}`. Bases : `{', '.join(model['bases'])}`.", ""])
        if model["docstring"]:
            rows.extend([clean(model["docstring"]), ""])
        if model.get('attributes'):
            rows.extend([f"- `{key} = {clean(value)}`" for key, value in model['attributes'].items()])
            rows.append('')
        if model.get('keywords'):
            rows.extend(['Options de classe : ' + ', '.join(f'`{clean(value)}`' for value in model['keywords']), ''])
        if model["fields"]:
            rows.extend(["| Champ | Type | Définition |", "|---|---|---|"])
            for field in model["fields"]:
                rows.append(f"| `{field['name']}` | `{clean(field['type'])}` | `{clean(field['definition'])}` |")
            rows.append("")
        if model["methods"]:
            rows.extend(["Méthodes/validators : " + "; ".join(f"`{f['name']}:{f['line']}`" for f in model["methods"]), ""])
    write("DATA_MODEL.md", rows)

    rows = ["# Catalogue des modules", "",
        "Inventaire de structure, pas attestation d'exécution ni lecture sémantique exhaustive.",
        "Les descriptions ci-dessous proviennent des docstrings de la source et peuvent être historiques. Le rapport principal arbitre les points revérifiés.", "",
        "## Backend applicatif", ""]
    for module in modules:
        if not module["path"].startswith("backend/app/"):
            continue
        meta = by_file[module["path"]]
        rows.extend(["### " + module["path"], "",
            f"{meta['lines']} lignes ; SHA-256 `{meta['sha256']}`.", ""])
        if module["docstring"]:
            rows.extend([clean(module["docstring"][:650]), ""])
        if module["functions"]:
            rows.extend(["Fonctions : " + "; ".join(f"`{f['name']}:{f['line']}`" for f in module["functions"]), ""])
        if module["classes"]:
            rows.extend(["Classes : " + "; ".join(f"`{c['name']}:{c['line']}`" for c in module["classes"]), ""])
        if module["environment"]:
            rows.extend(["Variables d'environnement lues : " + ", ".join(f"`{v}`" for v in sorted(set(e["name"] for e in module["environment"]))), ""])
    rows.extend(["## Frontend", "", "Tests inclus ; les APIs dynamiques ne sont pas toutes déductibles par extraction lexicale.", "",
        "| Source | Lignes | Store | API littérales / tests |", "|---|---|---|---|"])
    for item in read("FRONTEND_INVENTORY.json"):
        meta = by_file[item["path"]]
        detail = ", ".join(item["api_literals"])
        if item["test_labels"]:
            detail = f"{len(item['test_labels'])} libellés it/test/describe (non assimilables à autant de cas)"
        rows.append(f"| `{item['path']}` | {meta['lines']} | {clean(', '.join(item['store_ids']))} | {clean(detail)} |")
    rows.extend(["", "## Scripts et outils de maintenance", ""])
    for module in modules:
        if module["path"].startswith(("scripts/", "backend/scripts/")):
            rows.extend([f"- `{module['path']}` : {clean(module['docstring'][:230])}"])
    write("MODULE_CATALOGUE.md", rows)

    rows = ["# Définitions de tests backend", "",
        "Présence dans la source uniquement ; aucune collecte ni exécution pendant cette revue.",
        "Les paramétrisations, fixtures et marks exacts sont dans TEST_DEFINITIONS.json et les fichiers originaux.", ""]
    for item in read("TEST_DEFINITIONS.json"):
        if not item["definitions"]:
            continue
        rows.extend(["## " + item["path"], ""])
        rows.extend(f"- `{definition['name']}` — ligne {definition['line']}" for definition in item["definitions"])
        rows.append("")
    write("TEST_CATALOGUE.md", rows)

    snippets = [
        ("Product canonique", "backend/app/core/product/models.py", 185, 229),
        ("Contrat du pricing", "backend/app/core/schemas.py", 202, 280),
        ("Axe de temps", "backend/app/core/payscript/engine.py", 60, 102),
        ("GBM et quanto", "backend/app/core/payscript/engine.py", 490, 531),
        ("Heston, variance et spot", "backend/app/core/payscript/engine.py", 576, 629),
        ("SABR et écrêtage", "backend/app/core/payscript/engine.py", 673, 702),
        ("LSV et particules", "backend/app/core/payscript/engine.py", 879, 914),
        ("OU et convexité", "backend/app/core/payscript/engine.py", 1041, 1088),
        ("Funding", "backend/app/core/payscript/engine.py", 1192, 1216),
        ("Statistiques MC", "backend/app/core/payscript/engine.py", 2671, 2692),
        ("Portée du vega", "backend/app/core/payscript/engine.py", 2924, 2966),
        ("Domaine de barrière", "backend/app/core/payscript/bridge.py", 16, 54),
        ("Métadonnées du pont", "backend/app/core/payscript/bridge.py", 174, 202),
        ("Qualification de calibration", "backend/app/core/smile_calibration.py", 97, 142),
        ("Fraîcheur", "backend/app/core/market_policy.py", 1, 24),
        ("Finalité de close", "backend/app/core/fixing_finality.py", 31, 64),
        ("Réutilisation locale", "backend/app/services/market_data.py", 201, 267),
        ("Autorité des fixings", "backend/app/core/official_history.py", 12, 66),
        ("Contrôles de publication", "backend/app/services/rfq_publication.py", 167, 209),
        ("Contrôles de réception bancaire", "backend/app/services/rfq_electronic.py", 146, 179),
        ("Contexte bancaire de booking", "backend/app/services/rfq_electronic.py", 304, 345),
        ("Transport authentifié", "backend/app/services/rfq_transport.py", 53, 124),
        ("Booking natif", "backend/app/api/deals.py", 1654, 1720),
        ("Rejeu résiduel", "backend/app/core/inlife_valuation.py", 334, 378),
        ("MtM d'une créance", "backend/app/core/deal_valuation.py", 171, 227),
        ("Identité du moteur", "backend/app/core/valuation_runs.py", 17, 61),
        ("Cash contractuel", "backend/app/core/valuation_attribution.py", 1, 50),
        ("CVA et EPE", "backend/app/core/ccr/exposure.py", 86, 137),
        ("CCR non réglementaire", "backend/app/core/ccr/service.py", 626, 653),
        ("VaR et ES", "backend/app/core/var_engine.py", 383, 437),
        ("Solveur général", "backend/app/core/payscript/simulation.py", 74, 135),
        ("Allowlist Optimizer", "backend/app/core/product_optimizer/capabilities.py", 1, 45),
        ("KID : arguments MC", "backend/app/api/kid.py", 76, 109),
        ("KID : héritage et paramètres", "backend/app/api/kid.py", 293, 304),
        ("KID : orchestration et VEV", "backend/app/api/kid.py", 339, 407),
        ("KID : avertissement UI", "frontend/src/components/KidPanel.vue", 65, 79),
        ("EMT : détection", "backend/app/api/emt.py", 77, 111),
        ("Upload documentaire", "backend/app/api/documents.py", 133, 159),
        ("Sessions frontend", "frontend/src/utils/session.js", 1, 65),
        ("Cadence CRM", "backend/app/core/client_cycle.py", 167, 224),
        ("Inférence des études", "backend/app/core/amc_controls.py", 75, 85),
        ("Régression factorielle", "backend/app/core/amc_engine.py", 567, 586),
        ("Conditions du score composite", "backend/app/core/amc_managerskill.py", 238, 275),
        ("Poids du score composite", "backend/app/core/amc_managerskill.py", 1, 33),
        ("Prix d'exécution AMC", "backend/app/core/amc_prices.py", 685, 711),
        ("Financement du roll", "backend/app/core/roll_economics.py", 36, 70),
        ("Four eyes configurable", "backend/app/core/workflow.py", 13, 31),
        ("Manifeste développement", "backend/app/hybrid/config.py", 12, 49),
    ]
    rows = ["# Extraits critiques de source", "",
        "Copies exactes de plages de source locale, avec numéros de ligne d'origine et SHA-256 du fichier complet.",
        "Ces extraits sont incomplets par construction ; les imports, validateurs et appelants peuvent changer l'interprétation. Demander le fichier complet lorsqu'une conclusion en dépend.",
        "Aucune donnée de base privée, clé ou fichier de credentials n'est inclus.", ""]
    for title, name, begin, end in snippets:
        content = (ROOT / name).read_text(encoding="utf-8-sig").splitlines()
        meta = by_file[name]
        rows.extend(["## " + title, "", f"`{name}:{begin}` à {min(end, len(content))} ; SHA-256 `{meta['sha256']}`.", "", "```text"])
        rows.extend(f"{line}: {content[line-1]}" for line in range(begin, min(end, len(content))+1))
        rows.extend(["```", ""])
    write("CRITICAL_SOURCE_EXCERPTS.md", rows)

    primary = ROOT / "docs/audits/APPLICATION_REVIEW_2026-10-24.md"
    words = len(re.findall(r"\S+", primary.read_text(encoding="utf-8")))
    rows = ["# Annexes du rapport Structura", "", "## Référence", "",
        f"Date : {reference['date']}, {reference['timezone']}. Branche `{reference['branch']}`, HEAD `{reference['head']}` plus modifications locales.",
        "Les empreintes SOURCE_MANIFEST et le contrôle PRESERVATION_CHECKS identifient les fichiers, sans attester leur fonctionnement.", "",
        "## Livrables lisibles", "",
        "| Fichier | Usage |", "|---|---|",
        "| APPLICATION_REVIEW_2026-10-24.md (racine du ZIP) | Rapport principal en français, 44 chapitres |",
        "| REVIEW_PROMPT.md | Consigne autonome pour l'IA de contre-revue |",
        "| API_CATALOGUE.md | Routes déclarées, préfixes et montages |",
        "| DATA_MODEL.md | Champs des modèles et contrats |",
        "| MODULE_CATALOGUE.md | Modules, fonctions, classes, frontend et scripts |",
        "| TEST_CATALOGUE.md | Définitions de tests backend, sans résultats inventés |",
        "| CRITICAL_SOURCE_EXCERPTS.md | Extraits exacts des mécanismes financiers et contrôles |",
        "| INSPECTION_REFERENCE.json | Méthode, limites, état Git et comptages |",
        "| SOURCE_MANIFEST.json | SHA-256 et taille des fichiers inventoriés |",
        "| PRESERVATION_CHECKS.json | Contrôle final de stabilité des sources |",
        "| ARTIFACT_MANIFEST.json | SHA-256 des livrables livrés |", "",
        "## Données recherchables", "",
        "PYTHON_SYMBOLS.json, API_ROUTES.json, MODELS_AND_FIELDS.json, FRONTEND_INVENTORY.json, FRONTEND_ROUTES.json et TEST_DEFINITIONS.json contiennent les extractions détaillées.",
        "FRONTEND_ROUTES est lexical : il peut inclure des chemins de redirection et ne constitue pas un export du routeur à l'exécution.", "",
        "## Méthode de couverture", "",
        "- Inventaire systématique des fichiers suivis et non ignorés dans les extensions retenues ; artefacts binaires, données ignorées et bundles compilés exclus.",
        "- Parsing AST des sources Python backend/scripts, classes/champs/fonctions/décorateurs ; aucune résolution dynamique d'import.",
        "- Extraction lexicale des imports/stores/API/tests frontend ; aucun montage de composant ni test navigateur nouveau.",
        "- Lecture sémantique par domaines et chemins critiques détaillés dans le rapport principal. Les catalogues générés ne prouvent pas une lecture humaine ligne par ligne de chaque fichier.",
        "- Lecture et attribution de preuves antérieures datées ; aucune nouvelle campagne métier, base privée ou collecte pytest.",
        "- Les docstrings peuvent être anciennes ; les contrats et appels actifs priment lorsque le rapport les a confrontés.", "",
        "## Reproduction de l'inventaire", "",
        "Depuis la racine du dépôt, avec un interpréteur Python disponible :", "", "```powershell",
        ".\\.venv\\Scripts\\python.exe docs/audits/application-review-2026-10-24/inspect_sources.py",
        ".\\.venv\\Scripts\\python.exe docs/audits/application-review-2026-10-24/build_review_appendices.py", "```", "",
        "Ces scripts lisent le dépôt et réécrivent les inventaires de ce dossier. Ils ne démarrent pas l'application, n'ouvrent aucune base métier et n'exécutent aucun test.",
        "Ne pas les relancer en pensant reproduire la photographie originale après modification de source : conserver d'abord les inventaires livrés.", "",
        f"Volume indicatif du rapport principal lors de cette génération : {words:,} groupes séparés par espace (code/tableaux compris).", ""]
    write("ANNEXES.md", rows)
    print(json.dumps({"main_report_words_whitespace": words, "route_declarations": len(routes),
                      "critical_excerpt_ranges": len(snippets), "appendices_generated": 6}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
