// Montage. Decoupe la prise selon les reperes, incruste les sous-titres,
// concatene avec les cartons, encode en MP4.
//
// Le plan de coupe est declaratif : chaque segment dit d'ou a ou il va (par
// REPERE, pas par horodatage en dur), quel sous-titre l'accompagne, et
// eventuellement quelle zone cadrer. Si le tournage est refait et que les
// durees bougent, ce fichier n'a pas a changer.
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const B = path.join(HERE, 'build');
const RAW = path.join(B, 'raw');
const CAP = path.join(B, 'captions');
const SEG = path.join(B, 'retake', 'seg');
fs.mkdirSync(SEG, { recursive: true });

const LEADS = (() => {
  try { return JSON.parse(fs.readFileSync(path.join(B, 'cards.json'), 'utf8')); }
  catch { return {}; }
})();

const marks = JSON.parse(fs.readFileSync(path.join(B, 'retake', 'marks.json'), 'utf8'));
const T = Object.fromEntries(marks.map(m => [m.label, m.t]));
const has = l => T[l] !== undefined;

// --- Plan de coupe ---------------------------------------------------------
// `max` borne la duree : le rythme de la video prime sur l'exhaustivite d'une
// prise. `pad` decale le debut pour eviter d'entrer sur un mouvement de souris
// deja commence.
const PLAN = [
  { card: 'intro' },
  { card: 'architecture' },

  // SCENE 3 — le produit, en termes financiers.
  //
  // TOUTE la mise en place est hors montage : choix des sous-jacents, dates du
  // deal, matrice de correlation. On la fait dans la prise — sans elle il n'y a
  // pas de produit a pricer — mais elle n'a pas a etre vue. Le plan qui la
  // montrait affichait d'ailleurs le bas de l'onglet Deal (marge, trade date,
  // value date), pas les trois indices comme je le croyais.
  //
  // Les indices restent nommes deux fois a l'ecran, en clair : dans la
  // description saisie, et dans l'explication que le modele redonne.
  //
  // La video entre donc directement sur l'editeur vide, puis l'ouverture de
  // l'assistant. Aucun plan ne peut laisser apparaitre l'exemple par defaut.
  { from: 'setup_corr_done', to: 's3_assistant_open', max: 3.5, cap: null },
  // Toute la saisie d'un seul tenant, acceleree. Le plan etait auparavant coupe
  // en deux extraits du meme intervalle : on voyait la frappe commencer, une
  // coupe, puis le meme ecran avec le texte plus avance — un aller-retour sans
  // objet. La description reste lisible en entier dans le plan suivant, en
  // haut de la fenetre.
  { from: 's3_typing_start', to: 's4_generate_click', speed: 2.6,
    caps: [['c_describe', 0.30, 4.00], ['c_local', 4.40, 7.10]] },

  // SCENE 4 — traduction en script executable.
  // Un seul plan continu : le script cadre, puis la fiche de controle. Pas
  // d'acceleration ici, le script doit rester lisible.
  { from: 's4_script_ready', to: 's4_checks_shown', max: 9.0,
    caps: [['c_gen1', 0.30, 4.40], ['c_control', 4.80, 8.50]] },
  { from: 's4_adopted', to: 's4_edited', max: 5.0, cap: 'c_gen3' },

  // SCENE 5 — le pricing d'un seul tenant : clic, calcul, prix. Accelere pour
  // absorber l'attente du moteur sans quitter l'ecran.
  { from: 's5_price_click', to: 's5_price_done', speed: 2.0, cap: 'c_engine' },

  // SCENE 6 — les masques de resultat. Un plan par ecran, jamais deux extraits
  // du meme : ce sont des ONGLETS differents, donc une coupe normale et non un
  // retour sur une page qu'on vient de quitter.
  //
  // Fusionner le pricing et les probabilites en un seul plan accelere ne
  // marchait pas : a 2,4x, l'ecran des probabilites n'occupait plus que la
  // derniere seconde et son sous-titre tombait sur le panneau de resultats.
  //
  // ATTENTION au sens de la coupe : chaque repere est pose APRES le rendu de
  // son onglet, jamais au clic. Prendre le DEBUT d'un intervalle montre donc
  // l'onglet precedent. D'ou `tail` sur les trois plans qui suivent.
  // `pad` mord sur la seconde qui suit le repere : l'analyse probabiliste
  // n'existe que 2,6 s avant lui (le temps de pose du tournage), et sans ce
  // prolongement le plan entrait sur l'onglet encore vide.
  { from: 's5_price_done', to: 's6_proba', pad: 0.5, tail: true, max: 3.4,
    cap: 'c_proba' },

  { from: 's6_proba', to: 's6_flux', tail: true, max: 4.0, cap: 'c_flows' },
  { from: 's6_flux', to: 'end', pad: 1.5, tail: true, max: 5.0, cap: 'c_resume' },

  { card: 'outro' },
];

const ff = (args) => execFileSync('ffmpeg', ['-y', '-v', 'error', ...args], { stdio: 'inherit' });

const FADE = 0.35;      // fondus d'entree et de sortie de chaque segment
const ENC = ['-c:v', 'libx264', '-preset', 'slow', '-crf', '19',
             '-pix_fmt', 'yuv420p', '-r', '30', '-an'];

const parts = [];
let idx = 0;

for (const s of PLAN) {
  const out = path.join(SEG, `${String(idx).padStart(2, '0')}.mp4`);
  idx++;

  if (s.card) {
    const src = path.join(RAW, `${s.card}.webm`);
    // `lead` : la page blanche du debut — creation de la page, navigation,
    // chargement des polices — avant que la conduite ne soit declenchee. Elle
    // se voyait comme un eclair blanc en ouverture de video.
    const lead = LEADS[s.card] || 0;
    ff([...(lead ? ['-ss', lead.toFixed(3)] : []), '-i', src,
        '-vf', `fps=30,scale=1920:1080,setsar=1,format=yuv420p`, ...ENC, out]);
    parts.push(out);
    console.log(`carton   ${s.card}${lead ? `  (amorce ${lead.toFixed(2)} s coupee)` : ''}`);
    continue;
  }

  if (!has(s.from) || !has(s.to)) {
    console.log(`IGNORE   ${s.from} -> ${s.to}  (repere absent, scene non tournee)`);
    idx--;
    continue;
  }

  // `pad` prolonge au-dela du repere de fin : le dernier plan s'arretait 1,5 s
  // apres son repere, trop court pour qu'un sous-titre soit lu.
  // `offset` recule le point de depart, `pad` prolonge la fin. Les deux servent
  // la meme contrainte : un sous-titre doit rester lisible ~4 s, et le dernier
  // onglet n'etait suivi que de 2,6 s de matiere.
  const a0 = T[s.from] + (s.offset || 0), b0 = T[s.to] + (s.pad || 0);
  let start = a0, dur = Math.max(0.8, b0 - a0);
  if (s.max && dur > s.max) {
    // `tail` : garder la FIN de l'intervalle (le resultat), pas le debut
    // (l'attente). C'est la seule liberte prise sur la matiere filmee.
    if (s.tail) start = b0 - s.max;
    dur = s.max;
  }

  // `speed` comprime le plan. C'est ce qui permet de rester sur UN plan continu
  // par ecran au lieu d'en prendre deux morceaux : deux extraits du meme
  // intervalle donnaient l'impression de revenir sur une page qu'on venait de
  // quitter — on voyait la saisie commencer, une coupe, puis la meme page avec
  // le texte plus avance. Accelerer une attente se lit ; y revenir, non.
  const speed = s.speed || 1;
  const outDur = dur / speed;

  const vBase = `fps=30,scale=1920:1080,setsar=1` +
                (speed !== 1 ? `,setpts=PTS/${speed}` : '');
  const fades = `fade=t=in:st=0:d=${FADE},fade=t=out:st=${(outDur - FADE).toFixed(2)}:d=${FADE}`;

  // Un plan peut porter plusieurs sous-titres successifs : [id, debut, fin] en
  // secondes DANS le plan. `cap` reste accepte pour le cas simple.
  const caps = s.caps
    ? s.caps
    : (s.cap ? [[s.cap, 0.30, Math.max(1.2, outDur - 0.55)]] : []);

  // Chaine unique : source -> floutage eventuel -> sous-titre eventuel ->
  // fondus. Deux branches separees finissaient toujours par diverger.
  let chain = `[0:v]${vBase}[v];`;
  let last = 'v';

  // Le mecanisme de floutage reste disponible ; plus aucun plan ne s'en sert
  // depuis que les statistiques ont ete expliquees (correlation nulle).
  if (s.blur) {
    const [bx, by, bw, bh] = s.blur;
    // Flou gaussien modere, pas un boxblur agressif : a fort rayon, une zone de
    // cartes gris clair sur fond blanc se moyenne en aplat uniforme et se lit
    // comme un rectangle plein. A sigma 8 les cartes restent des cartes, leurs
    // bords arrondis et l'emplacement des libelles restent perceptibles, et
    // seuls les chiffres deviennent illisibles — ce qu'on cherche.
    chain += `[${last}]split[vb][vc];` +
             `[vc]crop=${bw}:${bh}:${bx}:${by},gblur=sigma=8:steps=3[bl];` +
             `[vb][bl]overlay=${bx}:${by}[vz];`;
    last = 'vz';
  }

  const inputs = ['-ss', start.toFixed(3), '-t', dur.toFixed(3), '-i', path.join(B, 'retake', 'app.webm')];

  caps.forEach(([id, cIn, cOut], k) => {
    const png = path.join(CAP, `${id}.png`);
    if (!fs.existsSync(png)) return;
    const idx = inputs.filter(a => a === '-i').length;   // numero de l'entree
    inputs.push('-loop', '1', '-t', outDur.toFixed(3), '-i', png);
    chain += `[${idx}:v]format=rgba,fade=t=in:st=${cIn.toFixed(2)}:d=0.35:alpha=1,` +
             `fade=t=out:st=${cOut.toFixed(2)}:d=0.35:alpha=1[c${k}];` +
             `[${last}][c${k}]overlay=0:0:format=auto[ov${k}];`;
    last = `ov${k}`;
  });

  chain += `[${last}]${fades},format=yuv420p[o]`;
  ff([...inputs, '-filter_complex', chain, '-map', '[o]', ...ENC, out]);
  parts.push(out);
  console.log(`segment  ${s.from} -> ${s.to}  ${outDur.toFixed(1)} s`
    + (speed !== 1 ? `  x${speed}` : '')
    + (caps.length ? '  [' + caps.map(c => c[0]).join(' + ') + ']' : ''));
}

// --- Concatenation ---------------------------------------------------------
const listFile = path.join(B, 'concat.txt');
fs.writeFileSync(listFile, parts.map(p => `file '${p.replace(/\\/g, '/')}'`).join('\n'));

const FINAL = path.join(B, 'retake', 'full-retake.mp4');
ff(['-f', 'concat', '-safe', '0', '-i', listFile, '-c', 'copy', FINAL]);

const dur = execFileSync('ffprobe',
  ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', FINAL]).toString().trim();
console.log(`\nstructura-ai-demo.mp4  —  ${Number(dur).toFixed(1)} s`);
