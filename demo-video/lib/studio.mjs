// Outillage de tournage : curseur visible, deplacements lisibles, reperes de
// montage.
//
// Playwright pilote une vraie souris mais ne la DESSINE pas dans la video
// enregistree. Sans curseur synthetique on verrait des champs se remplir tout
// seuls, ce qui ne se lit pas comme une demonstration. On injecte donc un
// curseur dans la page et on le deplace en meme temps que la vraie souris.
//
// Les reperes (`mark`) sont l'equivalent d'un clap : l'enregistrement est une
// prise continue, et c'est ce fichier de temps qui permet a ffmpeg de decouper
// les scenes sans compter les images a la main.

export const CURSOR_CSS = `
#__cur {
  position: fixed; left: 0; top: 0; width: 26px; height: 26px;
  margin: -3px 0 0 -3px; z-index: 2147483647; pointer-events: none;
  transition: transform .06s linear;
}
#__cur svg { filter: drop-shadow(0 2px 4px rgba(0,0,0,.45)); }
#__cur.click::after {
  content: ''; position: absolute; left: -9px; top: -9px;
  width: 44px; height: 44px; border-radius: 50%;
  border: 2.5px solid rgba(37,99,235,.9); animation: __ping .45s ease-out forwards;
}
@keyframes __ping { from { transform: scale(.25); opacity: 1; } to { transform: scale(1); opacity: 0; } }
/* Cadre discret pour designer une zone sans la masquer. */
#__hl {
  position: fixed; z-index: 2147483646; pointer-events: none;
  border: 2.5px solid rgba(37,99,235,.95); border-radius: 10px;
  box-shadow: 0 0 0 9999px rgba(8,16,30,.32);
  opacity: 0; transition: opacity .35s ease, all .45s cubic-bezier(.22,.8,.28,1);
}
#__hl.on { opacity: 1; }
`;

export async function installCursor(page) {
  await page.addStyleTag({ content: CURSOR_CSS });
  await page.evaluate(() => {
    if (document.getElementById('__cur')) return;
    const c = document.createElement('div');
    c.id = '__cur';
    c.innerHTML = `<svg viewBox="0 0 24 24" width="26" height="26">
      <path d="M5 2.5 L5 20 L9.6 15.6 L12.4 21.6 L15.4 20.2 L12.6 14.4 L19 14.2 Z"
            fill="#ffffff" stroke="#0b1a31" stroke-width="1.4" stroke-linejoin="round"/></svg>`;
    document.body.appendChild(c);
    const h = document.createElement('div');
    h.id = '__hl';
    document.body.appendChild(h);
    window.__cur = { x: 960, y: 980 };
    c.style.transform = 'translate(960px, 980px)';
  });
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

// Deplacement en cosinus : un mouvement lineaire se lit comme un robot, une
// acceleration puis un freinage se lisent comme une main.
export async function moveTo(page, x, y, ms = 700) {
  const from = await page.evaluate(() => window.__cur || { x: 960, y: 980 });
  const steps = Math.max(12, Math.round(ms / 16));
  for (let i = 1; i <= steps; i++) {
    const t = i / steps;
    const e = (1 - Math.cos(Math.PI * t)) / 2;
    const cx = from.x + (x - from.x) * e;
    const cy = from.y + (y - from.y) * e;
    await page.evaluate(([px, py]) => {
      window.__cur = { x: px, y: py };
      const c = document.getElementById('__cur');
      if (c) c.style.transform = `translate(${px}px, ${py}px)`;
    }, [cx, cy]);
    await page.mouse.move(cx, cy);
    await sleep(16);
  }
}

async function centerOf(locator) {
  const b = await locator.boundingBox();
  if (!b) throw new Error('element sans boite englobante (invisible ?)');
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
}

export async function moveToEl(page, locator, ms = 750) {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  const { x, y } = await centerOf(locator);
  await moveTo(page, x, y, ms);
  return { x, y };
}

export async function clickEl(page, locator, { ms = 750, settle = 550 } = {}) {
  await moveToEl(page, locator, ms);
  await page.evaluate(() => {
    const c = document.getElementById('__cur');
    if (!c) return;
    c.classList.remove('click');
    void c.offsetWidth;
    c.classList.add('click');
  });
  await sleep(160);
  await locator.click({ force: true });
  await sleep(settle);
}

// Frappe lente et reguliere : le spectateur doit pouvoir LIRE ce qui est saisi,
// c'est le message de la scene, pas un remplissage de formulaire.
export async function typeInto(page, locator, text, { cps = 34 } = {}) {
  await clickEl(page, locator, { settle: 260 });
  await locator.type(text, { delay: 1000 / cps });
}

export async function highlight(page, locator, pad = 8) {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  const b = await locator.boundingBox();
  if (!b) return;
  await page.evaluate(([x, y, w, h]) => {
    const el = document.getElementById('__hl');
    if (!el) return;
    el.style.left = x + 'px'; el.style.top = y + 'px';
    el.style.width = w + 'px'; el.style.height = h + 'px';
    el.classList.add('on');
  }, [b.x - pad, b.y - pad, b.width + pad * 2, b.height + pad * 2]);
}

export async function unhighlight(page) {
  await page.evaluate(() => document.getElementById('__hl')?.classList.remove('on'));
}

// --- Reperes de montage ----------------------------------------------------
export function makeMarks(t0) {
  const marks = [];
  return {
    marks,
    mark(label) {
      const t = (Date.now() - t0) / 1000;
      marks.push({ label, t });
      console.log(`  [${t.toFixed(2).padStart(7)} s]  ${label}`);
    },
  };
}

export { sleep };
