"""Package independent, offline HTML editions; exclude speaker content from sharing."""
import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    script = (ROOT / "presentation.js").read_text(encoding="utf-8")
    data = (ROOT / "assets/data.js").read_text(encoding="utf-8")
    for private, filename in [(False, "Presentation-a-partager.html"), (True, "Presentation-presentateur.html")]:
        page, js = html, script
        if not private:
            # Remove the content itself, rather than merely hiding its controls.
            page = re.sub(r'<dialog id="notes-dialog".*?</dialog>', '', page, flags=re.S)
            page = re.sub(r'<button id="notes".*?</button>', '', page)
            js = re.sub(r'  const notes = \[.*?\n  \];\n', '', js, flags=re.S)
            js = js.replace("  const notesDialog = document.querySelector('#notes-dialog');\n", '')
            js = re.sub(r'  function updateNotes\(\) \{.*?\n  \}\n', '', js, flags=re.S)
            js = js.replace('    updateNotes();\n', '')
            js = re.sub(r"  document.querySelector\('#notes'\).onclick=.*?;\};\n", '', js)
            js = js.replace('notesDialog.open||', '')
            js = re.sub(r"    else if\(e.key.toLowerCase\(\)==='n'\).*?\n", '', js)
            assert not any(s in js for s in ('notesDialog', 'updateNotes', 'const notes =', 'Question d’ouverture'))
            page = page.replace('Diagnostic de gestion · TP Advisory Services', 'TP Advisory Services · Diagnostic de gestion')
        else:
            page = page.replace('Diagnostic de gestion · TP Advisory Services', 'PRÉSENTATEUR · TP Advisory Services')
            page = page.replace('RENCONTRE PARTENAIRES', 'VERSION PRÉSENTATEUR')
        page = page.replace('<link rel="stylesheet" href="styles.css">', '<style>\n' + css + '\n</style>')
        page = page.replace('<script src="assets/data.js" defer></script><script src="presentation.js" defer></script>', '')
        # Both editions include the images, charts and code in one transferable file.
        for name in ('report-summary.png', 'report-risk.png'):
            encoded = base64.b64encode((ROOT / 'assets' / name).read_bytes()).decode('ascii')
            page = page.replace('assets/' + name, 'data:image/png;base64,' + encoded)
        page = page.replace('</body>', '<script>\n' + data + '\n' + js + '\n</script></body>')
        page = '\n'.join(line.rstrip() for line in page.splitlines()) + '\n'
        (ROOT / filename).write_text(page, encoding='utf-8')


if __name__ == '__main__':
    build()
