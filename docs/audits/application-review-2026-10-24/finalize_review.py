"""Verify and package this documentation review; never start/import Structura."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
REPORT = ROOT / 'docs/audits/APPLICATION_REVIEW_2026-10-24.md'
ARCHIVE = ROOT / 'output/structura-application-review-2026-10-24.zip'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main():
    manifest = json.loads((OUT/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    drift = []
    for record in manifest:
        path = ROOT/record['path']
        if not path.is_file() or digest(path) != record['sha256']:
            drift.append(record['path'])
    if drift:
        raise RuntimeError('Source drift since inventory: '+', '.join(drift))

    text = REPORT.read_text(encoding='utf-8')
    chapters = list(map(int,re.findall(r'^## (\d+)\.',text,re.M)))
    cases = re.findall(r'^\| (V\d+) \|',text,re.M)
    findings = re.findall(r'^\| (R\d+) \|',text,re.M)
    assert chapters == list(range(1,45))
    assert set(cases) == {f'V{i:02d}' for i in range(1,91)} and len(cases)==90
    assert set(findings) == {f'R{i:02d}' for i in range(1,26)} and len(findings)==25
    assert text.count('```') % 2 == 0 and 'CONTINUATION' not in text

    evidence = []
    reports = [
        'BACKEND_FULL_VALIDATION_2026-10-23.md',
        'GRAPHICAL_ACCEPTANCE_2026-10-23.md',
        'BILATERAL_RFQ_ACCEPTANCE_2026-10-24.md',
        'ELECTRONIC_RFQ_EXECUTION_2026-10-24.md',
        'RFQ_RECONCILIATION_2026-10-24.md',
        'LAUNCHER_ACCESS_ACCEPTANCE_2026-10-24.md',
        'ADMIN_ACCOUNT_SWITCH_2026-10-24.md',
        'REMEDIATION_C15_2026-10-21.md',
        'REMEDIATION_C16_2026-10-21.md',
        'REMEDIATION_C17_2026-10-21.md',
    ]
    for name in reports:
        path = ROOT/'docs/audits'/name
        assert path.is_file(), path
        evidence.append({'path':path.relative_to(ROOT).as_posix(),'sha256':digest(path),
                         'scope':'Historical documentation, not a new execution of this review'})
    proof_path = ROOT/'docs/audits/remediation-lot-0-2026-10-20/LAUNCHER_ACCESS_VALIDATION.json'
    proof = json.loads(proof_path.read_text(encoding='utf-8'))
    comparisons = []
    for name, expected in proof.get('source_sha256',{}).items():
        path = ROOT/name
        actual = digest(path) if path.is_file() else None
        comparisons.append({'path':name,'recorded_sha256':expected,'current_sha256':actual,'matches':actual==expected})
    documentary = {
        'inspection_date':'2026-10-24','new_tests_executed':False,
        'reports':evidence,
        'latest_launcher_evidence':{
            'path':proof_path.relative_to(ROOT).as_posix(),'sha256':digest(proof_path),
            'status':proof['status'],'backend_distinct_passed':proof['backend']['distinct_passed'],
            'backend_followup_passed':proof['backend']['current_change_followup_passed'],
            'frontend_passed':proof['frontend']['passed'],'frontend_files':proof['frontend']['files_passed'],
            'build_exit_code':proof['frontend']['build_exit_code'],
            'graphical_checkpoints':proof['graphical']['count'],
            'production_qualified':proof['production_qualified'],
            'activation_remaining':proof['activation']['remaining'],
            'source_comparisons':comparisons,
            'note':'Hash agreement is file identity only, not rerun validation or qualification of other modules.',
        },
    }
    save('DOCUMENTARY_EVIDENCE.json',documentary)

    ref=json.loads((OUT/'INSPECTION_REFERENCE.json').read_text(encoding='utf-8'))
    current_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert current_head==ref['head']
    checks={
        'status':'PASS_DOCUMENTARY_CHECKS','date':'2026-10-24',
        'source_manifest_entries_verified':len(manifest),'source_drift':drift,
        'head_unchanged':True,'head':current_head,
        'report_chapters':len(chapters),'priority_review_points':len(findings),
        'proposed_validation_scenarios':len(cases),'main_report_words_whitespace':len(text.split()),
        'main_report_lines':len(text.splitlines()),'main_report_bytes':REPORT.stat().st_size,
        'syntax_parse_errors':ref['python_syntax_errors'],
        'new_business_tests_executed':False,'pytest_collection_executed':False,
        'application_imports_performed':False,'application_services_started_by_review':False,
        'business_databases_opened_by_review':False,'secret_files_opened_by_review':False,
        'existing_application_and_test_sources_edited_by_review':False,
        'git_commit_push_merge_performed':False,
        'authorized_output':'Review documentation, static inventory scripts and package; docs/README.md index entry',
        'coverage_limit':'Structural inventory is systematic within exclusions. Semantic inspection is domain/critical-path based, not a complete line-by-line proof.',
        'test_results_limit':'Historical results are not summed and are not represented as new runs on this snapshot.',
        'documentary_source_hash_matches':sum(c['matches'] for c in comparisons),
        'documentary_source_hash_comparisons':len(comparisons),
    }
    save('PRESERVATION_CHECKS.json',checks)

    start='''# Dossier de revue de Structura — 24 octobre 2026

Pour lancer la revue dans un autre chat, copier le bloc de LAUNCH_REVIEW_PROMPT.md, qui indique le chemin local du ZIP et son utilisation en pièce jointe.
L'IA doit lire et appliquer intégralement annexes/REVIEW_PROMPT.md : prompt complet de contre-revue métier et quantitative, avec catégories de constats et livrable attendu.
Elle doit examiner APPLICATION_REVIEW_2026-10-24.md : rapport français de 44 chapitres, environ 24 500 mots, puis annexes/ANNEXES.md pour naviguer dans les inventaires et preuves.

Le rapport comprend 25 points de revue prioritaires et 90 scénarios proposés, jamais présentés comme exécutés.
Les annexes contiennent routes, modèles/champs, modules, tests et 48 extraits exacts de code.
Les fichiers reference-evidence/ sont des rapports historiques du dépôt, avec références datées ; certains liens relatifs de ces rapports nécessitent le dépôt original.

Cette archive ne contient aucune base métier, clé privée ni valeur de credentials, aucun bundle frontend et aucune dépendance à installer.
Elle ne contient pas tous les fichiers source de l'application : les inventaires et extraits servent à demander les fichiers complets utiles à chaque conclusion.
Une IA ayant seulement ce dossier peut évaluer cohérence et hypothèses ; elle ne peut pas certifier toute l'implémentation sans sources complètes et reproductions indépendantes.

Périmètre : code local non committé de Structura, pas INDEX_STUDIO. Aucun nouveau test métier ou service démarré pendant la préparation du rapport.
'''
    (OUT/'START_HERE.md').write_text(start,encoding='utf-8')
    package=[('APPLICATION_REVIEW_2026-10-24.md',REPORT),('START_HERE.md',OUT/'START_HERE.md'),
             ('LAUNCH_REVIEW_PROMPT.md',OUT/'LAUNCH_REVIEW_PROMPT.md')]
    package.extend((f'annexes/{path.name}',path) for path in sorted(OUT.iterdir())
        if path.is_file() and path.name not in {'ARTIFACT_MANIFEST.json','START_HERE.md','LAUNCH_REVIEW_PROMPT.md'}
        and path.suffix in {'.md','.json','.py'})
    package.extend((f'reference-evidence/{name}',ROOT/'docs/audits'/name) for name in reports)
    artifact_manifest={
        'date':'2026-10-24','package':'structura-application-review-2026-10-24.zip',
        'note':'Hashes of delivered entries, excluding this manifest and the ZIP itself.',
        'files':[{'archive_path':name,'bytes':path.stat().st_size,'sha256':digest(path)} for name,path in package],
    }
    save('ARTIFACT_MANIFEST.json',artifact_manifest)
    package.append(('ARTIFACT_MANIFEST.json',OUT/'ARTIFACT_MANIFEST.json'))
    ARCHIVE.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(ARCHIVE,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as bundle:
        for name,path in package:
            bundle.write(path,name)
    with zipfile.ZipFile(ARCHIVE) as bundle:
        assert bundle.testzip() is None
        for record in artifact_manifest['files']:
            assert hashlib.sha256(bundle.read(record['archive_path'])).hexdigest()==record['sha256']
    summary={'archive':str(ARCHIVE),'archive_sha256':digest(ARCHIVE),'archive_bytes':ARCHIVE.stat().st_size,
             'entries':len(package),'main_report_words':checks['main_report_words_whitespace'],
             'chapters':len(chapters),'proposed_scenarios':len(cases),'review_points':len(findings),
             'source_drift':drift,'source_hash_matches':checks['documentary_source_hash_matches'],
             'source_hash_comparisons':len(comparisons)}
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
