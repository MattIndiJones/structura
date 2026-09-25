(() => {
  'use strict';
  const lang = document.documentElement.lang === 'en' ? 'en' : 'fr';
  const c = window.FINEGAN_CONTENT[lang];
  const root = document.getElementById('presentation');
  const arrow = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h15m-6-6 6 6-6 6"/></svg>';
  const logo = '<span class="brand"><img class="brand-symbol" src="../assets/finegan-logo.png" alt=""><span>FINEGAN</span></span>';
  const header = `<header class="slide-header">${logo}<span class="offering">FUND & AMC ANALYSIS</span></header>`;
  const section = (n,theme,body) => `<section id="slide-${n}" class="slide ${theme}" aria-labelledby="title-${n}" aria-roledescription="slide" aria-label="${n} / 5" ${n>1?'inert aria-hidden="true"':''}>${header}${body}<span class="print-number">${n} / 5</span></section>`;
  const heading = (n,s) => `<div class="section-heading"><p class="eyebrow reveal">${s.eyebrow}</p><h${n===1?'1':'2'} id="title-${n}" class="reveal" style="--delay:80ms">${s.title}</h${n===1?'1':'2'}></div>`;
  // Abstract paths illustrate decomposition only: no returns, dates or numerical scale.
  const curve = 'M35 270 C75 268 83 243 113 249 S150 210 180 218 S212 193 242 205 S271 171 300 183 S339 143 367 157 S398 116 427 133 S463 101 496 112 S533 74 559 90 S596 54 629 68';
  const paths = [
    'M35 270 C90 270 102 263 148 264 S199 257 242 250 S289 248 333 240 S375 241 420 230 S475 220 514 217 S581 213 629 197',
    'M35 270 C88 270 104 288 151 283 S196 277 242 287 S295 271 335 284 S379 270 420 278 S473 263 520 275 S577 256 629 263',
    'M35 270 C89 274 104 310 150 307 S199 329 242 318 S291 342 333 338 S380 330 420 352 S473 339 516 350 S584 364 629 355',
    'M35 270 C84 279 105 330 150 343 S197 356 242 361 S288 387 333 379 S381 410 420 401 S475 427 516 414 S578 443 629 432'
  ];
  const s1 = `${heading(1,c.s1)}<div class="hero-copy"><p class="lead reveal" style="--delay:180ms">${c.s1.lead}</p><p class="hero-bottom reveal" style="--delay:350ms">${c.s1.bottom}</p></div>
    <figure class="performance-figure"><div class="figure-kicker">${c.s1.chartTop}</div><svg class="performance-chart" viewBox="0 0 700 500" role="img" aria-label="${c.s1.observed}: ${c.s1.sources.join(', ')}"><defs><linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#ef7968" stop-opacity=".13"/><stop offset="1" stop-color="#ef7968" stop-opacity="0"/></linearGradient></defs><g class="chart-grid"><path d="M35 75H660 M35 175H660 M35 275H660 M35 375H660 M35 475H660"/><path d="M35 40V475 M190 40V475 M345 40V475 M500 40V475 M660 40V475"/></g><path class="chart-area" d="${curve} L629 475 H35 Z"/><path class="observed-curve" d="${curve}" pathLength="1"/>${paths.map((p,i)=>`<path class="source-curve source-${i}" d="${p}" pathLength="1"/>`).join('')}<circle class="end-dot" cx="629" cy="68" r="5"/></svg><div class="observed-label">${c.s1.observed}</div><div class="figure-divider"></div><div class="figure-kicker bottom-kicker">${c.s1.chartBottom}</div><div class="source-legend">${c.s1.sources.map((s,i)=>`<span class="legend-${i}" style="--delay:${1500+i*160}ms"><i></i>${s}</span>`).join('')}</div><figcaption>${c.s1.note}</figcaption></figure>`;
  const s2 = `${heading(2,c.s2)}<div class="evidence-body"><aside class="metrics reveal" style="--delay:160ms"><p class="small-label">${c.s2.metricsLabel}</p>${c.s2.metrics.map((m,i)=>`<div class="metric"><span class="metric-glyph glyph-${i}" aria-hidden="true"><i></i><i></i><i></i><i></i></span><span>${m}</span></div>`).join('')}<p class="metric-note">${c.s2.metricNote}</p></aside><div class="evidence-flow"><p class="small-label reveal">${c.s2.label}</p><div class="observed-node reveal" style="--delay:200ms">${c.s2.observed}</div><div class="vertical-line line-reveal" style="--delay:350ms"></div><div class="question-node reveal" style="--delay:450ms">${c.s2.question}</div><div class="branch-line line-reveal" style="--delay:650ms"></div><div class="evidence-sources">${c.s2.sources.map((s,i)=>`<span class="reveal" style="--delay:${750+i*90}ms">${s}</span>`).join('')}</div></div></div><div class="evidence-conclusion reveal" style="--delay:1100ms">${c.s2.conclusion}</div>`;
  const s3 = `${heading(3,c.s3)}<div class="review-orbit"><svg class="orbit-lines" viewBox="0 0 1440 450" aria-hidden="true"><circle cx="720" cy="210" r="139"/><circle class="inner-orbit" cx="720" cy="210" r="109"/><path d="M625 108L488 40H385 M582 190H385 M810 103L940 40H1058 M858 205H1058"/></svg><div class="portfolio-center reveal" style="--delay:200ms"><span class="center-mark" aria-hidden="true">◇</span><h3>${c.s3.center}</h3><p>${c.s3.centerSub}</p></div>${c.s3.questions.map((q,i)=>`<div class="management-question q${i+1} reveal" style="--delay:${350+i*130}ms"><div><h3>${q[0]}</h3><p>${q[1]}</p></div></div>`).join('')}</div>`;
  const s4 = `${heading(4,c.s4)}<div class="decision-body"><div class="diagnostic reveal" style="--delay:150ms"><div class="diagnostic-mark" aria-hidden="true"><span></span><span></span><span></span><span></span></div><h3>${c.s4.diagnostic}</h3><p>${c.s4.sub}</p></div><svg class="decision-lines" viewBox="0 0 230 450" preserveAspectRatio="none" aria-hidden="true"><path pathLength="1" d="M0 225H90V65H230 M90 225H230 M90 225V385H230"/><circle cx="90" cy="225" r="5"/></svg><div class="decision-rows">${c.s4.rows.map((r,i)=>`<article class="decision-row reveal" style="--delay:${500+i*220}ms"><span class="decision-index">0${i+1}</span><div><h3>${r[0]}</h3><p class="decision-context">${r[1]}</p><p class="decision-outcome">${r[2]}</p></div><span class="decision-arrow" aria-hidden="true">↗</span></article>`).join('')}</div></div><p class="decision-foot reveal" style="--delay:1250ms">${c.s4.foot}</p>`;
  const s5 = `${heading(5,c.s5)}<p class="engagement-intro reveal" style="--delay:150ms">${c.s5.intro}</p><div class="engagement-steps">${c.s5.steps.map((s,i)=>`<article class="engagement-step reveal ${i===3?'optional':''}" style="--delay:${250+i*160}ms"><div class="step-top"><span>0${i+1}</span>${i===3?`<span class="optional-label">${c.s5.optional}</span>`:arrow}</div><h3>${s[0]}</h3><p>${s[1]}</p></article>`).join('')}</div><div class="engagement-cta"><div><h3 class="reveal" style="--delay:950ms">${c.s5.cta}</h3><p class="reveal" style="--delay:1050ms">${c.s5.ctaSub}</p></div><div class="cta-right reveal" style="--delay:1150ms"><a class="contact-link" href="https://finegan.fr/#contact" target="_blank" rel="noopener noreferrer">${c.s5.contact}${arrow}</a><span class="cta-signature">FINEGAN<span>${c.s5.signature}</span></span></div></div>`;
  root.innerHTML = `<div class="deck-frame"><div class="deck">${section(1,'dark hero',s1)}${section(2,'light evidence',s2)}${section(3,'light review',s3)}${section(4,'dark decisions',s4)}${section(5,'light engagement',s5)}<nav class="deck-nav" aria-label="${c.ui.section}"><div class="nav-left"><a class="language-link" href="../${lang==='fr'?'en':'fr'}/index.html" title="${c.ui.language}" aria-label="${c.ui.language}"><span ${lang==='fr'?'class="selected"':''}>FR</span><span class="language-divider">/</span><span ${lang==='en'?'class="selected"':''}>EN</span></a><span class="nav-hint">${c.ui.keys}</span><button class="fullscreen" title="${c.ui.fullscreen}" aria-label="${c.ui.fullscreen}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/></svg></button><button class="replay" title="${c.ui.replay}" aria-label="${c.ui.replay}">↻</button><button class="print" title="${c.ui.print}" aria-label="${c.ui.print}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9V3h12v6M6 17H3V9h18v8h-3M6 14h12v7H6z"/></svg></button></div><div class="progress-dots">${c.ui.labels.map((l,i)=>`<button data-slide="${i}" title="${l}" aria-label="${c.ui.slide} ${i+1} : ${l}"><span></span></button>`).join('')}</div><div class="nav-right"><span class="slide-count"><b>01</b><span>/</span>05</span><button class="previous" aria-label="${c.ui.previous}">${arrow}</button><button class="next" aria-label="${c.ui.next}">${arrow}</button></div><div class="progress-track"><span></span></div></nav></div></div><div class="sr-only" role="status" aria-live="polite" aria-atomic="true"></div><div class="toast" role="status"></div>`;
  const deck = root.querySelector('.deck');
  const frame = root.querySelector('.deck-frame');
  const slides = [...root.querySelectorAll('.slide')];
  const prev = root.querySelector('.previous');
  const next = root.querySelector('.next');
  const fullscreen = root.querySelector('.fullscreen');
  let current = -1;
  let toastTimer;
  const fromHash = () => { const match = /^#slide-([1-5])$/.exec(location.hash); return match ? Number(match[1])-1 : 0; };
  const mobile = () => matchMedia('(max-width: 700px) and (orientation: portrait)').matches;
  function fit() {
    const scale = Math.min(innerWidth / 1600, innerHeight / 900);
    deck.style.setProperty('--scale', scale);
    frame.style.width = mobile() ? '100%' : `${1600*scale}px`;
    frame.style.height = mobile() ? 'auto' : `${900*scale}px`;
  }
  function show(index, updateHash=true) {
    const n = Math.max(0, Math.min(slides.length-1, index));
    if (n === current) return;
    const previousSlide = slides[current];
    if (previousSlide?.contains(document.activeElement)) next.focus({preventScroll:true});
    slides.forEach((s,i)=> {s.classList.toggle('active',i===n); s.setAttribute('aria-hidden',String(i!==n));s.inert=i!==n;});
    current=n;
    deck.dataset.theme=slides[n].classList.contains('dark')?'dark':'light';
    deck.dataset.currentSlide=String(n+1);
    prev.disabled=n===0; next.disabled=n===slides.length-1;
    root.querySelector('.slide-count b').textContent=String(n+1).padStart(2,'0');
    root.querySelector('.progress-track span').style.transform=`scaleX(${(n+1)/slides.length})`;
    root.querySelectorAll('.progress-dots button[data-slide]').forEach((b,i)=> {b.setAttribute('aria-current',i===n?'step':'false');});
    root.querySelector('.language-link').hash=`slide-${n+1}`;
    root.querySelector('.sr-only').textContent=`${c.ui.slide} ${n+1} / 5. ${c.ui.labels[n]}`;
    if(updateHash) { try {history.replaceState(null,'',`#slide-${n+1}`);} catch {location.hash=`slide-${n+1}`;} }
    if(mobile()) window.scrollTo({top:0,behavior:'instant'});
  }
  function replay() { const s=slides[current];s.classList.remove('active');void s.offsetWidth;s.classList.add('active'); }
  async function toggleFullscreen() {
    try {if(document.fullscreenElement) await document.exitFullscreen();else if(document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen();else throw new Error('unsupported');}
    catch {const toast=root.querySelector('.toast');toast.textContent=c.ui.unavailable;toast.classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove('visible'),3500);}
  }
  prev.addEventListener('click',()=>show(current-1));
  next.addEventListener('click',()=>show(current+1));
  fullscreen.addEventListener('click',toggleFullscreen);
  root.querySelector('.replay').addEventListener('click',replay);
  root.querySelector('.print').addEventListener('click',()=>window.print());
  root.querySelectorAll('.progress-dots button[data-slide]').forEach(b=>b.addEventListener('click',()=>show(Number(b.dataset.slide))));
  document.addEventListener('keydown',e=> {
    if(e.altKey||e.ctrlKey||e.metaKey||e.target.closest('input,textarea,select,[contenteditable="true"]'))return;
    if((e.key===' '||e.key==='Enter')&&e.target.closest('a,button'))return;
    if(['ArrowRight','PageDown',' '].includes(e.key)){e.preventDefault();show(current+(e.shiftKey?-1:1));}
    else if(['ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();show(current-1);}
    else if(e.key==='Home'){e.preventDefault();show(0);}
    else if(e.key==='End'){e.preventDefault();show(4);}
    else if(e.key.toLowerCase()==='f'){e.preventDefault();toggleFullscreen();}
    else if(e.key.toLowerCase()==='r'){e.preventDefault();replay();}
  });
  let touchStart;
  root.addEventListener('touchstart',e=>{if(e.touches.length!==1||e.target.closest('a,button')){touchStart=null;return;}touchStart={x:e.touches[0].clientX,y:e.touches[0].clientY};},{passive:true});
  root.addEventListener('touchend',e=>{if(!touchStart)return;const dx=e.changedTouches[0].clientX-touchStart.x;const dy=e.changedTouches[0].clientY-touchStart.y;if(Math.abs(dx)>55&&Math.abs(dx)>Math.abs(dy)*1.5)show(current+(dx<0?1:-1));touchStart=null;},{passive:true});
  root.addEventListener('touchcancel',()=>{touchStart=null;},{passive:true});
  document.addEventListener('fullscreenchange',()=>{const label=document.fullscreenElement?c.ui.exitFullscreen:c.ui.fullscreen;fullscreen.setAttribute('aria-label',label);fullscreen.title=label;fit();});
  window.addEventListener('resize',fit);
  window.addEventListener('hashchange',()=>show(fromHash(),false));
  root.querySelectorAll('.brand-symbol').forEach(img=>{img.addEventListener('error',()=>{img.hidden=true;});});
  fit();show(fromHash());
})();
