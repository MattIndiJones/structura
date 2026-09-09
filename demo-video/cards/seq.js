// Sequenceur des cartons.
//
// L'enregistrement se fait EN TEMPS REEL par Playwright : il n'y a pas de piste
// de montage ou l'on ferait glisser des images-cles. Le rythme de la video est
// donc ce fichier, et il doit rester lisible comme une conduite — chaque ligne
// est un instant en millisecondes et ce qui s'y passe.
//
// La conduite NE DEMARRE PAS au chargement. L'enregistrement video commence a
// la creation de la page, donc avant que le document ne soit peint : les
// premieres images etaient blanches, et la conduite tournait deja pendant le
// chargement des polices. Le tourneur declenche explicitement, une fois la page
// prete, et coupe ce qui precede.
//
// `window.__done` dit a l'enregistreur quand couper. Sans ce signal il faudrait
// deviner la duree, et une carte tronquee de 200 ms se voit.
window.__done = false;

function show(sel) {
  document.querySelectorAll(sel).forEach(e => {
    e.classList.remove('out');
    e.classList.add('in');
  });
}

function hide(sel) {
  document.querySelectorAll(sel).forEach(e => {
    e.classList.remove('in');
    e.classList.add('out');
  });
}

function run(steps, totalMs) {
  window.__start = () => {
    steps.forEach(([ms, fn]) => setTimeout(fn, ms));
    setTimeout(() => { window.__done = true; }, totalMs);
  };
}
