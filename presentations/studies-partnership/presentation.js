'use strict';
(() => {
  const data = window.STUDIES_DATA;
  const slides = [...document.querySelectorAll('.slide')];
  const names = ['INTRODUCTION', 'LA DÉMARCHE', 'LES ANALYSES', 'LE CAS CONCRET', 'LA RESTITUTION', 'LE PARTENARIAT'];
  const notes = [
    ["Votre relation client, notre profondeur quantitative", "1 min 30", "TP Advisory Services se positionne comme un partenaire d’analyse quantitative du cabinet. Nous transformons les données d’un fonds ou AMC en un diagnostic documenté ; le cabinet conserve sa relation client et son jugement. Il ne s’agit pas de vendre un logiciel.", "La performance se constate. La gestion s’analyse. Un rendement positif ne dit pas à lui seul d’où vient le résultat ni quels risques ont été pris.", "Question d’ouverture : quelle question sur la gestion est la plus difficile à documenter dans vos missions ?"],
    ["Des données au diagnostic", "2 min", "Documenter : NAV, positions, transactions et documentation du produit. Rapprocher : contrôler les conventions, les frais, les dividendes et le change. Analyser : performance, décisions de gestion, facteurs et risque. Restituer : constats documentés et questions à discuter avec le gérant.", "Le périmètre des conclusions suit la qualité des données. Les contrôles servent à identifier les écarts et les limites ; ils ne garantissent pas que chaque dossier sera automatiquement réconcilié.", "Animation : cliquer successivement sur les quatre phrases colorées sous les étapes. Chaque explication reste affichée, même après un aller-retour sur un autre écran. Un rechargement remet les explications à zéro. Le PDF les affiche toutes. Transition : cette démarche permet de traiter quatre grandes questions métier."],
    ["Quatre questions pour comprendre la gestion", "2 min 30", "Cliquer sur chacune des quatre questions pour révéler son visuel. Les schémas restent ouverts pendant la navigation et se réinitialisent au rechargement ; le PDF les montre tous. Ce sont des illustrations pédagogiques sans échelle chiffrée, pas des résultats du fonds fictif. Les barres ne sont pas une décomposition additive commune à Fama-French et Brinson. Les repères achat, renforcement et vente ne certifient pas la qualité des décisions. Les deux trajectoires n’affirment aucune surperformance réelle ; la récupération dessinée ne constitue pas une prévision. D’où vient la performance ? Fama-French + Momentum estime les expositions factorielles et l’alpha avec t-stats, p-values et R². L’attribution P&L distingue réalisé, latent et change. Brinson distingue allocation, sélection et interaction. Le Brinson actuel est mono-période sur proxies : indicatif et exclu du scoring.", "Que valent les décisions du gérant ? Croiser taux de réussite, profit factor, durée et rotation avec le timing des achats et ventes, la performance post-achat et les caractéristiques de poids et de durée des positions. Une classification de conviction n’est pas une preuve d’alpha ; un lot FIFO n’est pas nécessairement une décision indépendante.", "La gestion active apporte-t-elle de la valeur ? Le Buy & Hold pose le scénario du panier initial sans arbitrage. Dans le cas fictif, ses frais et dividendes diffèrent de ceux du fonds : l’écart n’isole pas la valeur des décisions. La réplication factorielle est théorique et estimée sur la période ; elle n’est pas un portefeuille directement investissable.", "Quel risque a été pris ? Drawdowns, récupération, ratios de risque, pertes extrêmes et concentration, complétés par l’activité observée pendant les chocs historiques. Ce ne sont pas des prévisions.", "Notre valeur est le croisement de ces lectures et la possibilité de remonter au détail. Les scores sont descriptifs et complètent le jugement du consultant ; les tests statistiques et leurs limites se lisent séparément. Aucun score global ne certifie le talent. Ne pas dévoiler les formules, seuils ou pondérations internes."],
    ["Le cas fictif : distinguer les lectures", "2 min 30", "Le fonds fictif affiche +38,07 % net cumulé sur six ans, mais une baisse maximale de −31,70 %, avec 1 540 ordres. Conserver la mention fictive : aucune performance client n’est présentée.", "La zone sous le graphique indique ce que l’analyse cherche à distinguer : marché, facteurs, sélection, timing et allocation, prise de risque. Ces axes se recoupent ; ils ne constituent pas une décomposition chiffrée additive ou une conclusion déjà démontrée sur ce cas.", "Utiliser les onglets NAV, drawdown et contributions. Les contributions sont du P&L réalisé et latent, change inclus, hors dividendes et frais. Si demandé : 59,1 % des 1 341 rapprochements FIFO sont gagnants, profit factor 1,72.", "Transition : ces constats servent à préparer une discussion mieux documentée avec le gérant."],
    ["Des constats aux questions au gérant", "1 min 30", "Le rapport fournit une synthèse de mission, des analyses détaillées et un cadre documenté. Il aide le consultant à relier un constat quantifié à une question à approfondir avec le gérant.", "Exemples de questions à préparer : quels titres expliquent les gains ? Quelle exposition a contribué à une baisse ? Quelles opérations l’ont accompagnée ? Le consultant interprète, formule les questions et valide les conclusions. Ne pas promettre une génération automatique de recommandations.", "Les images sont des pages réelles du rapport du fonds fictif. Les scores visibles sont des indicateurs descriptifs, pas une certification. L’assistance IA à la rédaction est facultative et soumise à relecture. Le cabinet conserve la relation et le jugement client."],
    ["Un premier pilote commun", "2 min", "Enrichir les missions du cabinet sans lui demander d’internaliser une infrastructure quantitative dédiée. Son apport : connaissance du client, question métier et relation client. Notre apport : qualification des données, profondeur quantitative et diagnostic. Ensemble : valider les constats, préparer la restitution et restituer au client.", "Proposer un dossier réel, une question métier, un diagnostic et une restitution commune. Le dossier réel reste à qualifier : accès, confidentialité, traitement des données, calendrier, prix et responsabilités sont à convenir avant le pilote.", "À obtenir : le premier dossier, un référent et un échange de cadrage. Après restitution, évaluer l’utilité du diagnostic et l’effort réel de production.", "Clôture : quel premier dossier examiner ensemble ?"]
  ];
  const notesDialog = document.querySelector('#notes-dialog');
  const reportDialog = document.querySelector('#report-dialog');
  let current = Math.max(0, Math.min(5, (Number(location.hash.slice(1)) || 1) - 1));
  let chartMode = 'nav';
  const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = (v, decimals = 0) => v.toLocaleString('fr-FR', {maximumFractionDigits:decimals, minimumFractionDigits:decimals});
  const svg = (body, title, viewBox = '0 0 800 340') => `<svg viewBox="${viewBox}" role="img" aria-label="${escape(title)}" xmlns="http://www.w3.org/2000/svg">${body}</svg>`;
  const points = data.nav;
  let peak = points[0].value;
  const drawdowns = points.map(p => { peak = Math.max(peak, p.value); return {...p, value:100*(p.value/peak-1)}; });
  function seriesChart(mode, hero = false) {
    const isRisk = mode === 'risk', series = isRisk ? drawdowns : points;
    const w = hero ? 600 : 800, h = hero ? 260 : 340;
    const left = 47, right = w-30, top = 22, bottom = h-40;
    const min = isRisk ? -35 : 65, max = isRisk ? 0 : 155;
    const x = i => left + i/(series.length-1)*(right-left);
    const y = v => top + (max-v)/(max-min)*(bottom-top);
    const path = series.map((p,i) => `${i?'L':'M'}${x(i).toFixed(2)},${y(p.value).toFixed(2)}`).join(' ');
    let body = '';
    for (const tick of (isRisk ? [0,-10,-20,-30] : [75,100,125,150])) {
      body += `<line class="svg-grid" x1="${left}" y1="${y(tick)}" x2="${right}" y2="${y(tick)}"/><text class="svg-tick" x="${left-10}" y="${y(tick)+4}" text-anchor="end">${tick}${isRisk?' %':''}</text>`;
    }
    for (let year=2020;year<=2025;year++) {
      const i = series.findIndex(p=>p.date.startsWith(String(year)));
      body += `<text class="svg-tick" x="${x(i)}" y="${h-12}" text-anchor="middle">${year}</text>`;
    }
    const color = isRisk ? 'var(--gold)' : 'var(--mint)';
    body += `<path d="${path} L${right},${y(isRisk?0:min)} L${left},${y(isRisk?0:min)} Z" fill="${color}" opacity=".08"/><path class="trace" pathLength="1" d="${path}" stroke="${color}" stroke-width="${hero?2.4:2.2}" stroke-linejoin="round"/>`;
    if (isRisk) {
      const low = series.reduce((best,p,i)=>p.value<series[best].value?i:best,0);
      body += `<circle cx="${x(low)}" cy="${y(series[low].value)}" r="4" fill="${color}"/><text class="svg-title" x="${x(low)+12}" y="${y(series[low].value)-10}">−31,70 %</text>`;
    } else {
      body += `<circle cx="${right}" cy="${y(series.at(-1).value)}" r="4" fill="${color}"/><text class="svg-title" x="${right-6}" y="${y(series.at(-1).value)-14}" text-anchor="end">138,07</text>`;
    }
    return svg(body, isRisk?'Drawdowns quotidiens du fonds fictif de 2020 à 2025, minimum moins 31,70 pour cent':'NAV quotidienne du fonds fictif de 2020 à 2025, de 100 à 138,07', `0 0 ${w} ${h}`);
  }
  function contributionChart() {
    const ranked = [...data.contributions].sort((a,b)=>b.value-a.value);
    const rows = [...ranked.slice(0,3), ...ranked.slice(-2)];
    const left=260,zero=420,right=738,max=700000;
    let body = '<text class="svg-label" x="8" y="25">PRINCIPALES HAUSSES ET BAISSES · P&amp;L EN USD</text>';
    body += `<line class="svg-grid" x1="${zero}" y1="40" x2="${zero}" y2="310"/>`;
    rows.forEach((r,i)=>{
      const cy = 66+i*51, width = Math.abs(r.value)/max*(right-zero);
      const bx = r.value<0 ? zero-width : zero;
      body += `<text class="svg-title" x="8" y="${cy+6}">${escape(r.name)}</text><rect x="${bx}" y="${cy-13}" width="${width}" height="29" fill="${r.value<0?'var(--coral)':'var(--mint)'}" opacity=".85"/><text class="svg-title" x="${r.value<0?bx-9:bx+width+9}" y="${cy+6}" text-anchor="${r.value<0?'end':'start'}">${r.value>0?'+':''}${fmt(r.value/1000,1)} k</text>`;
    });
    return svg(body, 'Trois meilleures et deux moins bonnes contributions de prix du fonds fictif, hors dividendes et frais');
  }
  function renderChart(mode) {
    chartMode = mode;
    document.querySelector('#detail-chart').innerHTML = mode==='pnl'?contributionChart():seriesChart(mode);
    document.querySelector('#chart-caption').textContent = mode==='nav' ? 'NAV nette quotidienne, base 100 au 01/01/2020. Performance cumulée, non annualisée.' : mode==='risk' ? 'Baisse depuis le précédent plus-haut de NAV. 36 épisodes observés ; aucune prévision de risque futur.' : 'Sélection de 5 titres sur 20. P&L réalisé + latent, change inclus, hors dividendes et frais du fonds.';
    document.querySelectorAll('[data-chart]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.chart===mode)));
  }
  function updateNotes() {
    const note=notes[current];
    document.querySelector('#notes-title').textContent=note[0];
    document.querySelector('#notes-content').innerHTML=`<p class="mint">Durée indicative : ${note[1]}</p>`+note.slice(2).map(t=>`<p>${escape(t)}</p>`).join('');
  }
  function go(index, focus = true) {
    current = Math.max(0, Math.min(slides.length-1,index));
    slides.forEach((slide,i)=>{slide.hidden=i!==current;slide.classList.toggle('active',i===current);});
    document.querySelectorAll('.dots button').forEach((b,i)=>{if(i===current)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');});
    document.querySelector('#section-label').textContent=names[current];
    document.querySelector('#progress').style.width=`${(current+1)/slides.length*100}%`;
    document.querySelector('#previous').disabled=current===0;
    document.querySelector('#next').disabled=current===slides.length-1;
    if(location.hash!==`#${current+1}`) location.hash=String(current+1);
    document.querySelector('#announcement').textContent=`Écran ${current+1} sur 6 : ${names[current]}`;
    updateNotes();
    if(focus){slides[current].querySelector('h1,h2').focus({preventScroll:true});window.scrollTo(0,0);}
  }
  document.querySelector('#hero-chart').innerHTML=seriesChart('nav',true);
  renderChart('nav');
  document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>go(Number(b.dataset.go))));
  document.querySelectorAll('[data-chart]').forEach(b=>b.addEventListener('click',()=>renderChart(b.dataset.chart)));
  // Reveal each explanation once; keep it open when revisiting the slide.
  document.querySelectorAll('.process-reveal, .analysis-reveal').forEach(button => {
    button.addEventListener('click', () => {
      if (button.getAttribute('aria-expanded') === 'true') return;
      document.getElementById(button.getAttribute('aria-controls')).hidden = false;
      button.setAttribute('aria-expanded', 'true');
    });
  });
  document.querySelector('#previous').onclick=()=>go(current-1);
  document.querySelector('#next').onclick=()=>go(current+1);
  document.querySelector('#notes').onclick=()=>{updateNotes();notesDialog.showModal();};
  document.querySelectorAll('.dialog-close').forEach(b=>b.onclick=()=>b.closest('dialog').close());
  document.querySelectorAll('[data-report]').forEach(b=>b.onclick=()=>{document.querySelector('#report-image').src=b.dataset.report;reportDialog.showModal();});
  document.querySelector('#print').onclick=()=>window.print();
  async function fullscreen() {
    try {if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}
    catch {document.querySelector('#announcement').textContent='Le plein écran est indisponible. Utilisez F11 dans votre navigateur.';}
  }
  document.querySelector('#fullscreen').onclick=fullscreen;
  document.addEventListener('keydown',e=>{
    if(notesDialog.open||reportDialog.open||e.ctrlKey||e.altKey||e.metaKey)return;
    if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName))return;
    if(e.key==='ArrowRight'||e.key==='PageDown'||(e.key===' '&&e.target.tagName!=='BUTTON')){e.preventDefault();go(current+1);}
    else if(e.key==='ArrowLeft'||e.key==='PageUp'){e.preventDefault();go(current-1);}
    else if(e.key==='Home'){e.preventDefault();go(0);}
    else if(e.key==='End'){e.preventDefault();go(5);}
    else if(/^[1-6]$/.test(e.key))go(Number(e.key)-1);
    else if(e.key.toLowerCase()==='n'){e.preventDefault();updateNotes();notesDialog.showModal();}
    else if(e.key.toLowerCase()==='f'){e.preventDefault();fullscreen();}
  });
  window.addEventListener('hashchange',()=>{const index=Number(location.hash.slice(1))-1;if(Number.isInteger(index)&&index>=0&&index<6&&index!==current)go(index);});
  // Printing always uses the NAV chart, regardless of the current demonstration tab.
  let printMode;
  window.addEventListener('beforeprint',()=>{printMode=chartMode;renderChart('nav');});
  window.addEventListener('afterprint',()=>{if(printMode)renderChart(printMode);});
  go(current,false);
})();
