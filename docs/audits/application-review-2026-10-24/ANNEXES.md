# Annexes du rapport Structura

## Référence

Date : 2026-10-24, Europe/Berlin. Branche `codex/hybrid-saas-foundation`, HEAD `7dce3021a88feb4f0021ca3de8f3596277bc72a5` plus modifications locales.
Les empreintes SOURCE_MANIFEST et le contrôle PRESERVATION_CHECKS identifient les fichiers, sans attester leur fonctionnement.

## Livrables lisibles

| Fichier | Usage |
|---|---|
| APPLICATION_REVIEW_2026-10-24.md (racine du ZIP) | Rapport principal en français, 44 chapitres |
| REVIEW_PROMPT.md | Prompt intégral de contre-revue métier et quantitative fourni dans le chat |
| LAUNCH_REVIEW_PROMPT.md (racine du ZIP) | Prompt de lancement avec chemin local du ZIP et utilisation possible en pièce jointe |
| API_CATALOGUE.md | Routes déclarées, préfixes et montages |
| DATA_MODEL.md | Champs des modèles et contrats |
| MODULE_CATALOGUE.md | Modules, fonctions, classes, frontend et scripts |
| TEST_CATALOGUE.md | Définitions de tests backend, sans résultats inventés |
| CRITICAL_SOURCE_EXCERPTS.md | Extraits exacts des mécanismes financiers et contrôles |
| INSPECTION_REFERENCE.json | Méthode, limites, état Git et comptages |
| SOURCE_MANIFEST.json | SHA-256 et taille des fichiers inventoriés |
| PRESERVATION_CHECKS.json | Contrôle final de stabilité des sources |
| ARTIFACT_MANIFEST.json | SHA-256 des livrables livrés |

## Données recherchables

PYTHON_SYMBOLS.json, API_ROUTES.json, MODELS_AND_FIELDS.json, FRONTEND_INVENTORY.json, FRONTEND_ROUTES.json et TEST_DEFINITIONS.json contiennent les extractions détaillées.
FRONTEND_ROUTES est lexical : il peut inclure des chemins de redirection et ne constitue pas un export du routeur à l'exécution.

## Méthode de couverture

- Inventaire systématique des fichiers suivis et non ignorés dans les extensions retenues ; artefacts binaires, données ignorées et bundles compilés exclus.
- Parsing AST des sources Python backend/scripts, classes/champs/fonctions/décorateurs ; aucune résolution dynamique d'import.
- Extraction lexicale des imports/stores/API/tests frontend ; aucun montage de composant ni test navigateur nouveau.
- Lecture sémantique par domaines et chemins critiques détaillés dans le rapport principal. Les catalogues générés ne prouvent pas une lecture humaine ligne par ligne de chaque fichier.
- Lecture et attribution de preuves antérieures datées ; aucune nouvelle campagne métier, base privée ou collecte pytest.
- Les docstrings peuvent être anciennes ; les contrats et appels actifs priment lorsque le rapport les a confrontés.

## Reproduction de l'inventaire

Depuis la racine du dépôt, avec un interpréteur Python disponible :

```powershell
.\.venv\Scripts\python.exe docs/audits/application-review-2026-10-24/inspect_sources.py
.\.venv\Scripts\python.exe docs/audits/application-review-2026-10-24/build_review_appendices.py
```

Ces scripts lisent le dépôt et réécrivent les inventaires de ce dossier. Ils ne démarrent pas l'application, n'ouvrent aucune base métier et n'exécutent aucun test.
Ne pas les relancer en pensant reproduire la photographie originale après modification de source : conserver d'abord les inventaires livrés.

Volume indicatif du rapport principal lors de cette génération : 24,558 groupes séparés par espace (code/tableaux compris).

