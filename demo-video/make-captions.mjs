// Fabrication des sous-titres, en PNG transparents 1920x1080.
//
// Pourquoi pas `drawtext` de ffmpeg : il ne sait pas composer une typographie
// de marque. Les cartons et les sous-titres doivent etre la MEME marque que
// l'application, donc ils sont rendus par le meme moteur — Chromium, avec les
// polices du projet — puis simplement superposes.
//
// Chaque PNG fait la taille de l'image entiere : la superposition ffmpeg se
// reduit alors a un overlay en 0:0, sans arithmetique de position a maintenir.
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, 'build', 'captions');
fs.mkdirSync(OUT, { recursive: true });

// id, texte, et style : 'band' pour un message principal, 'note' pour une
// precision secondaire, 'steps' pour une enumeration rythmee.
// Pas de point final, et le tiret comme separateur : une incrustation n'est pas
// une phrase, et un point y ferme une idee qu'on veut voir enchainer.
//
// Formulations POSITIVES. « Priced by STRUCTURA's engine — not by the AI »
// portait la meme negation que le carton d'architecture : dire qui fait, plutot
// que qui ne fait pas.
export const CAPTIONS = [
  ['c_describe',  'Describe the product in financial terms', 'band'],
  ['c_local',     'The model runs locally — the description stays on the desk', 'note'],
  ['c_gen1',      'Generated from the product specification', 'band'],
  ['c_control',   'A control sheet states what the script actually does', 'note'],
  ['c_gen3',      'Fully editable by the structurer', 'band'],
  ['c_engine',    "Priced by STRUCTURA's quantitative engine", 'band'],
  // « barrier breach » a ete retire : la mesure affichee sous ce nom compte en
  // realite les chemins qui ne recuperent pas le pair, pas les franchissements
  // de barriere. Autant ne pas reprendre l'erreur dans une video.
  ['c_proba',     'Autocall, capital loss, expected life — with their probabilities', 'note'],
  ['c_flows',     'Every cash flow — its date, its probability, its present value', 'note'],
  ['c_resume',    'A written product summary — the start of a term sheet', 'band'],
];

const HTML = (text, kind) => `<!doctype html><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  html,body{margin:0;width:1920px;height:1080px;background:transparent;overflow:hidden;
            font-family:'Plus Jakarta Sans',-apple-system,'Segoe UI',sans-serif;-webkit-font-smoothing:antialiased}
  .wrap{position:absolute;left:0;right:0;bottom:64px;display:flex;justify-content:center}
  .band,.note,.steps{
    display:inline-block;padding:20px 42px;border-radius:14px;
    background:rgba(9,20,38,.93);
    box-shadow:0 10px 40px rgba(0,0,0,.34);
    border:1px solid rgba(127,176,232,.28);
    color:#f5f3ee;text-align:center;max-width:1480px;
  }
  .band{font-size:38px;font-weight:600;letter-spacing:-.012em}
  .note{font-size:30px;font-weight:300;color:#cbd8ea;padding:16px 36px}
  .steps{font-size:36px;font-weight:600;color:#a8cbf2;letter-spacing:.01em}
</style>
<div class="wrap"><div class="${kind}">${text}</div></div>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });

for (const [id, text, kind] of CAPTIONS) {
  await page.setContent(HTML(text, kind));
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(220);
  await page.screenshot({ path: path.join(OUT, `${id}.png`), omitBackground: true });
  console.log('OK', id);
}

await browser.close();
console.log(`${CAPTIONS.length} sous-titres dans build/captions/`);
