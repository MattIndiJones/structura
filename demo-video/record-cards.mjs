// Enregistrement des cartons animes (scenes 1, 2 et 8).
//
// Chaque carton est une page HTML qui joue sa propre conduite et pose
// `window.__done` a la fin. On enregistre exactement cette duree : deviner la
// longueur donnerait des cartes tronquees de quelques images, ce qui se voit.
//
// Playwright ecrit du .webm ; la conversion et l'assemblage sont le travail de
// assemble.mjs, pour que cette etape reste re-executable seule.
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, 'build', 'raw');
const CARDS = ['intro', 'architecture', 'outro'];

const W = 1920, H = 1080;

fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({
  args: ['--force-device-scale-factor=1', '--hide-scrollbars'],
});

const leads = {};

for (const name of CARDS) {
  // Origine de la bande : l'enregistrement demarre a la creation de la page.
  const t0 = Date.now();
  const ctx = await browser.newContext({
    viewport: { width: W, height: H },
    deviceScaleFactor: 1,
    recordVideo: { dir: OUT, size: { width: W, height: H } },
  });
  const page = await ctx.newPage();

  const url = 'file://' + path.join(HERE, 'cards', `${name}.html`).replace(/\\/g, '/');
  await page.goto(url);
  // Les polices Google doivent etre chargees AVANT la premiere image, sinon le
  // carton demarre en police de repli et bascule en cours de plan.
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);

  // Tout ce qui precede est du blanc : page vide, navigation, polices. On note
  // sa duree pour que le montage la coupe, puis seulement on declenche.
  leads[name] = (Date.now() - t0) / 1000;
  await page.evaluate(() => window.__start());

  await page.waitForFunction(() => window.__done === true, null, { timeout: 60000 });
  await page.waitForTimeout(300);

  const video = page.video();
  await ctx.close();                       // ferme et finalise le fichier video
  const src = await video.path();
  const dest = path.join(OUT, `${name}.webm`);
  fs.renameSync(src, dest);
  console.log(`OK  ${name}.webm`);
}

await browser.close();
fs.writeFileSync(path.join(HERE, 'build', 'cards.json'), JSON.stringify(leads, null, 2));
console.log('Cartons enregistres dans build/raw/ (amorces blanches dans cards.json)');
for (const [k, v] of Object.entries(leads)) console.log(`  ${k.padEnd(14)} amorce ${v.toFixed(2)} s`);
