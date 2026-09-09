// Reperage. N'enregistre rien : ouvre l'application en 1920x1080, capture les
// ecrans a filmer et liste les libelles cliquables, pour que record.mjs soit
// ecrit sur des faits et non sur des suppositions.
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SHOTS = path.join(HERE, 'build', 'scout');
fs.mkdirSync(SHOTS, { recursive: true });

const APP = 'http://localhost:8000';

const browser = await chromium.launch({ args: ['--hide-scrollbars'] });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });

async function dump(tag) {
  await page.screenshot({ path: path.join(SHOTS, `${tag}.png`) });
  const items = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('button, a, [role=tab], select, textarea, input[type=text], input[type=number]').forEach(e => {
      const r = e.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) return;
      const t = (e.innerText || e.value || e.placeholder || '').trim().replace(/\s+/g, ' ').slice(0, 46);
      if (!t && e.tagName !== 'SELECT' && e.tagName !== 'INPUT') return;
      out.push(`${e.tagName.toLowerCase().padEnd(8)} ${String(Math.round(r.x)).padStart(5)},${String(Math.round(r.y)).padStart(4)}  ${t}`);
    });
    return out;
  });
  console.log(`\n===== ${tag} =====`);
  console.log(items.join('\n'));
}

await page.goto(APP, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
await dump('01-login');

// Connexion rapide : le bouton "Admin" du bas de l'ecran de connexion.
await page.getByText('Admin', { exact: true }).first().click();
await page.waitForTimeout(2500);
await dump('02-home');

await page.goto(APP + '/#/pricer', { waitUntil: 'networkidle' });
await page.waitForTimeout(2500);
await dump('03-pricer');

for (const tab of ['Deal', 'Marché & Paramètres']) {
  const b = page.getByRole('button', { name: new RegExp(tab.split(' ')[0], 'i') }).first();
  if (await b.count()) {
    await b.click().catch(() => {});
    await page.waitForTimeout(1600);
    await dump('04-' + tab.split(' ')[0].toLowerCase());
  }
}

// Retour au script puis ouverture de l'assistant.
await page.getByRole('button', { name: /Script PayScript/i }).first().click().catch(() => {});
await page.waitForTimeout(900);
await page.getByRole('button', { name: /Assistant IA/i }).first().click().catch(() => {});
await page.waitForTimeout(2200);
await dump('05-assistant');

await browser.close();
console.log('\nCaptures dans build/scout/');
