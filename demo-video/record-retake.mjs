// Tournage de la demonstration dans l'application REELLE.
//
// Une seule prise continue, avec des reperes horodates ecrits dans
// build/marks.json. Le decoupage en scenes est fait ensuite par assemble.mjs :
// filmer d'un trait garantit que l'etat de l'application est continu — le
// script price ce que l'assistant vient d'ecrire, et rien n'est recolle.
//
// Ce que ce fichier ne fait PAS : fabriquer un resultat. Les prix, les Greeks
// et les echeanciers affiches sont ceux que le moteur calcule pendant la prise.
// La seule liberte prise au montage est de raccourcir les attentes.
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
import { installCursor, moveTo, moveToEl, clickEl, typeInto, highlight, unhighlight, makeMarks, sleep }
  from './lib/studio.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, 'build', 'raw');
const APP = 'http://localhost:8000';
const W = 1920, H = 1080;

// La description telle qu'elle sera lue a l'ecran. Deux ecarts assumes par
// rapport au brief, tous deux pour que le script AFFICHE dise exactement ce que
// la description ANNONCE — un professionnel verrait la contradiction :
//
//  - « observed at any time » et non « European » : interroge sur une barriere
//    europeenne, le modele ecrit WOF_MIN, c'est-a-dire la barriere continue.
//  - « 3-year » et non « 5-year » : la maturite transmise au modele est celle
//    configuree dans le Pricer, et elle devient lecture seule des qu'un script
//    definit ses constatations.
//
// Constatations ANNUELLES et non trimestrielles : le mode Expert du Pricer, qui
// produirait un calendrier CONSTAT(), ne pilote que les modeles d'exemples
// charges — il ne change pas ce que l'assistant ecrit. En trimestriel le script
// genere porte donc une liste de douze dates en dur qui s'etale sur toute la
// ligne ; en annuel il donne `AT 1, 2, 3:`, la forme classique d'un Athena, qui
// se lit d'un coup d'oeil a l'ecran.
const DESCRIPTION =
  'Create a 3-year worst-of autocall on EURO STOXX 50, S&P 500 and Nikkei 225, ' +
  'with annual observations, an 8% coupon paid only upon autocall (a single 8% payment, no accrual, no memory and no multiplication by elapsed years), autocall at 100% ' +
  'of the initial level, and a 60% protection barrier observed continuously throughout the product life. ' +
  'The knock-in depends on the minimum over the full path, not only the final level. ' +
  'If not autocalled, repay par when no knock-in occurred; otherwise repay the final worst-of performance. ' +
  'Explicitly explain this continuous observation in the French product summary.';

const INDICES = ['Euro Stoxx 50', 'S&P 500', 'Nikkei 225'];

fs.mkdirSync(OUT, { recursive: true });

// Prechargement AVANT d'ouvrir la page. L'enregistrement video demarre a la
// creation du contexte : tout ce qui se passe ensuite mais avant `t0` decale la
// bande par rapport aux reperes, et le montage coupe alors a cote — un plan
// annonce « script genere » montrait encore « Generation… ». L'origine de la
// video et celle des reperes doivent etre le meme instant.
console.log('Prechargement de qwen2.5-coder:14b…');
try {
  await fetch('http://localhost:11434/api/generate', {
    method: 'POST',
    body: JSON.stringify({ model: 'qwen2.5-coder:14b', prompt: 'ok', stream: false, keep_alive: '30m' }),
  });
  console.log('  modele charge.');
} catch { console.log('  (prechargement impossible — on continue)'); }

const browser = await chromium.launch({ args: ['--hide-scrollbars', '--force-device-scale-factor=1'] });
const ctx = await browser.newContext({
  viewport: { width: W, height: H },
  deviceScaleFactor: 1,
  recordVideo: { dir: OUT, size: { width: W, height: H } },
});
const page = await ctx.newPage();

// Origine commune a la bande et aux reperes : la page vient d'etre creee, donc
// l'enregistrement vient de commencer.
const t0 = Date.now();
const { marks, mark } = makeMarks(t0);

const btn = (re) => page.getByRole('button', { name: re }).first();

try {
  // ── Mise en place : connexion et produit ─────────────────────────
  await page.goto(APP, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await installCursor(page);
  await page.getByText('Admin', { exact: true }).first().click();
  await page.waitForTimeout(2600);

  await page.goto(APP + '/#/pricer', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2200);
  await installCursor(page);

  // ── Vider l'editeur, AVANT tout le reste ────────────────────────
  // L'ordre compte : si on vide apres avoir configure les sous-jacents, le
  // passage par l'onglet Script laisse apparaitre l'exemple « Autocall Athena »
  // une seconde a l'image, et une seconde suffit a faire croire qu'un script
  // existait deja.
  //
  // On garde les deux lignes de commentaire de l'etat vierge — elles disent ce
  // qu'est cet ecran et renvoient vers l'assistant — mais pas le `AT MATURITY /
  // PAY 1` qui les suit : ces deux lignes-la se lisent comme un script. Un
  // script reduit a des commentaires passe le parser (verifie : ok=true, aucune
  // erreur), donc aucun bandeau rouge a l'ecran.
  const EDITEUR_VIDE =
    '# Script libre — décrivez votre payoff.\n' +
    '# Aide : bouton ✨ Assistant IA, ou le mémo de vocabulaire ci-dessous.\n';
  const editeur = page.locator('textarea').first();
  await moveToEl(page, editeur, 620);
  await editeur.fill(EDITEUR_VIDE);
  await page.waitForTimeout(1500);
  mark('s3_blank');

  // ── Le produit : trois indices reels du catalogue ────────────────
  mark('setup_underlyings_start');
  await clickEl(page, btn(/Deal/i));
  await page.waitForTimeout(700);

  const addBtn = page.getByRole('button', { name: /\+ Ajouter/i }).first();
  for (let i = 0; i < 2; i++) {
    await addBtn.scrollIntoViewIfNeeded();
    await clickEl(page, addBtn, { settle: 500 });
  }

  // Un onglet par sous-jacent ; pour chacun on choisit l'indice au catalogue.
  for (let i = 0; i < INDICES.length; i++) {
    const tab = page.getByRole('button', { name: new RegExp(`^Sous-jacent ${i + 1}$`) }).first();
    if (await tab.count()) { await tab.scrollIntoViewIfNeeded(); await clickEl(page, tab, { ms: 420, settle: 350 }); }
    const sel = page.locator('select').filter({ hasText: 'Choisir un sous-jacent' }).first();
    await sel.scrollIntoViewIfNeeded();
    await moveToEl(page, sel, 420);
    await sel.selectOption({ label: INDICES[i] });
    await page.waitForTimeout(900);
  }
  await page.waitForTimeout(1000);
  await page.waitForTimeout(1600);      // un temps sur les trois indices : c'est le plan monte
  mark('setup_underlyings_done');

  // Chaque etape ci-dessous est isolee : une prise coute cinq minutes dont
  // deux et demie de generation, et un seul selecteur fautif ne doit pas
  // emporter tout ce qui a deja ete filme. La scene manquante sera simplement
  // absente du plan de coupe.
  const etape = async (label, fn) => {
    try { await fn(); mark(label); }
    catch (e) { console.log(`  (etape ${label} sautee : ${e.message.split('\n')[0]})`); }
  };

  // ── Hypotheses de marche — hors camera ──────────────────────────
  // Reglees AVANT la generation, et absentes du montage.
  //
  // L'ordre du metier veut qu'on ajuste le marche une fois le produit defini,
  // et c'est pour cela que cette etape n'est pas montree. Mais le pricing de
  // controle de l'assistant tourne PENDANT la generation : le laisser passer
  // apres signifiait le faire travailler a correlation nulle, et sa fiche
  // affichait alors « rho = 0.00 » a l'ecran. Arbitrage tranche par Philippe :
  // regler avant, hors camera, et revoir la question plus tard.
  //
  // Sans ce reglage, la matrice reste a zero — sur un worst-of, une correlation
  // nulle maximise la dispersion et donne un prix qu'aucun quant ne prendrait
  // au serieux.
  await etape('setup_corr_done', async () => {
    await clickEl(page, btn(/Marché & Paramètres/i), { settle: 700 });
    const bump = page.getByRole('button', { name: '+0.20', exact: true }).first();
    await bump.scrollIntoViewIfNeeded();
    for (let i = 0; i < 3; i++) await clickEl(page, bump, { ms: 300, settle: 400 });
    await page.waitForTimeout(700);
    // Revenir en haut ET sur l'onglet Script. Sans cela la page reste defilee
    // sur la matrice : « Deconnexion » (y=16) et « ▶ Pricer » (y=69) sont au
    // meme endroit a droite de l'en-tete, a 53 pixels l'un de l'autre, et un
    // clic pris pendant que le defilement se rejoue atterrit sur le mauvais.
    // Une prise entiere y est passee.
    await clickEl(page, btn(/Script PayScript/i), { settle: 500 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(900);
  });

  // ── SCENE 3 — la demande, en termes financiers ───────────────────
  // Retour sur l'onglet Script : l'editeur y est deja vide, rien ne clignote.
  await clickEl(page, btn(/Script PayScript/i), { settle: 900 });
  await clickEl(page, btn(/Assistant IA/i), { settle: 1100 });
  mark('s3_assistant_open');

  // ATTENTION au ciblage. `page.locator('textarea').first()` designe l'EDITEUR
  // DE SCRIPT : la fenetre modale est teleportee en fin de <body>, donc son
  // champ est le DERNIER textarea du document, pas le premier. La premiere
  // prise a ainsi tape la description anglaise dans le script PayScript, laisse
  // le champ du modal vide, et le bouton « Generer » — desactive sous 3
  // caracteres — n'a jamais rien lance. On ancre donc sur le modal lui-meme.
  const modal = page.locator('.modal-panel').last();
  const ta = modal.locator('textarea').first();
  mark('s3_typing_start');
  await typeInto(page, ta, DESCRIPTION, { cps: 38 });
  await page.waitForTimeout(1200);

  // Verification explicite avant de lancer : une prise de six minutes ne doit
  // pas se perdre sur un champ reste vide.
  const saisi = (await ta.inputValue()).trim();
  if (saisi.length < 40) throw new Error(`description non saisie (${saisi.length} car.)`);
  mark('s3_typing_done');

  // Le moteur et le modele restent visibles : c'est un modele LOCAL, la
  // description ne quitte pas la machine — un argument, pas un detail.
  const moteur = modal.locator('select').filter({ hasText: /Ollama/i }).first();
  if (await moteur.count()) { await highlight(page, moteur, 6); await page.waitForTimeout(1500); await unhighlight(page); }

  // ── SCENE 4 — traduction en script executable ────────────────────
  mark('s4_generate_click');
  await clickEl(page, btn(/Générer le script/i), { settle: 400 });

  // L'attente reelle du modele. Elle sera raccourcie au montage, jamais
  // remplacee : ce qui s'affiche ensuite est bien ce que le modele a produit.
  await page.getByText(/SCRIPT PROPOSÉ/i).first().waitFor({ timeout: 480000 });
  await page.waitForTimeout(1800);
  mark('s4_script_ready');
  fs.writeFileSync(path.join(HERE, 'build', 'retake', 'generated-review.txt'), await modal.innerText());
  await page.screenshot({path:path.join(HERE, 'build', 'retake', 'generated-review.png')});
  const generatedScript = await modal.locator('pre, .code-editor').first().innerText();
  if (!generatedScript.includes('WOF_MIN')) throw new Error('Continuous barrier missing from generated script');
  if (/\bINDEX\b/.test(generatedScript)) throw new Error('Unexpected coupon accumulation');


  const codeBloc = modal.locator('pre, .code-editor').first();
  if (await codeBloc.count()) { await highlight(page, codeBloc, 10); await page.waitForTimeout(2600); await unhighlight(page); }

  // La fiche de controle : ce qui empeche un script credible et faux de passer.
  const fiche = modal.getByText(/FICHE DE CONTRÔLE/i).first();
  if (await fiche.count()) {
    await moveToEl(page, fiche, 800);
    await highlight(page, fiche, 10);
    await page.waitForTimeout(2600);
    await unhighlight(page);
  }
  mark('s4_checks_shown');

  await clickEl(page, btn(/Adopter dans l'éditeur/i), { settle: 500 });
  // Attendre la FERMETURE du modal avant de chercher quoi que ce soit dans la
  // page : tant qu'il est monte, ses propres champs polluent tout selecteur.
  await page.locator('.modal-panel').waitFor({ state: 'detached', timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(1400);
  mark('s4_adopted');

  // ── SCENE 4b — le script reste editable ──────────────────────────
  // Deux ancrages ont echoue avant celui-ci, et les deux pour la meme raison :
  // avoir vise « la page » au lieu de la carte.
  //   - `input` en premier  -> la case du Mode Demo, dans l'en-tete, masquee
  //     par son propre curseur, donc jamais cliquable.
  //   - div contenant /PARAMÈTRES DU SCRIPT/ -> le libelle est ecrit
  //     « Paramètres du script » ; la capitale vient du CSS, pas du DOM.
  try {
    const paramCard = page.locator('.card').filter({ hasText: 'Paramètres du script' }).first();
    const coupon = paramCard.locator('input').first();
    await coupon.waitFor({ state: 'visible', timeout: 15000 });
    await coupon.scrollIntoViewIfNeeded();
    await highlight(page, coupon, 8);
    await moveToEl(page, coupon, 700);
    await coupon.click({ clickCount: 3 });
    await page.waitForTimeout(500);
    await coupon.type('9', { delay: 260 });
    await coupon.press('Tab');
    await page.waitForTimeout(1500);
    await unhighlight(page);
    mark('s4_edited');
  } catch (e) {
    console.log(`  (edition du PARAM sautee : ${e.message.split('\n')[0]})`);
    await unhighlight(page).catch(() => {});
  }

  // Garde-fou : si la session a saute, mieux vaut le savoir tout de suite que
  // d'attendre 180 s un prix qui n'arrivera jamais.
  if (!(await page.getByRole('button', { name: /Déconnexion/i }).count())) {
    throw new Error('session perdue avant le pricing');
  }

  // ── SCENE 5 — le moteur quantitatif ──────────────────────────────
  mark('s5_price_click');
  await etape('s5_price_done', async () => {
    await clickEl(page, btn(/▶ Pricer/i), { settle: 300 });
    await page.getByText(/PRIX ÉQUITABLE/i).first().waitFor({ timeout: 180000 });
    await page.waitForTimeout(2600);
  });

  // ── SCENE 6 — les masques de resultat, dans cet ordre ────────────
  // Le prix et ses probabilites, puis les flux, puis la description ecrite du
  // payoff. C'est la progression que suit un structureur qui recoit un prix :
  // combien, avec quelle probabilite, quels flux, et qu'est-ce que je vends.
  //
  // Les Greeks sont volontairement HORS du parcours filme : le bump-and-reprice
  // tourne plusieurs minutes et laisse une barre de progression dans l'en-tete
  // pendant tous les plans suivants. Mieux vaut ne pas les montrer que les
  // montrer en train de calculer.
  // L'onglet Probabilites ne calcule rien tout seul : il lance SA propre
  // simulation a 5 000 chemins, sur un clic. Sans ce clic on filmait son etat
  // vide — ce qui donnait un onglet ouvert et aucun resultat.
  await etape('s6_proba', async () => {
    await clickEl(page, btn(/Probabilités/i), { ms: 520, settle: 900 });
    await clickEl(page, page.getByRole('button', { name: /▶ Analyser/i }).first(), { ms: 420, settle: 300 });
    await page.getByText(/chemins analysés/i).first().waitFor({ timeout: 120000 });
    await page.waitForTimeout(2600);
  });

  for (const [re, label, settle] of [
    [/💰 Flux|Flux/i, 's6_flux', 2600],
    [/📝 Résumé|Résumé/i, 's6_resume', 2800],
  ]) {
    await etape(label, async () => { await clickEl(page, btn(re), { ms: 520, settle }); });
  }

  await page.waitForTimeout(2200);
  mark('end');
} catch (e) {
  mark('ERREUR');
  console.error('\nEchec du tournage :', e.message);
} finally {
  const video = page.video();
  await ctx.close();
  const src = await video.path();
  fs.renameSync(src, path.join(OUT, 'app.webm'));
  fs.writeFileSync(path.join(HERE, 'build', 'marks.json'), JSON.stringify(marks, null, 2));
  await browser.close();
  console.log('\napp.webm + marks.json ecrits dans build/');
}
