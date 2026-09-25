(() => {
  'use strict';

  const lang = document.documentElement.lang === 'en' ? 'en' : 'fr';
  const c = window.FINEGAN_SP_CONTENT[lang];
  const root = document.getElementById('presentation');
  const arrow = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h15m-6-6 6 6-6 6"/></svg>';
  const logo = '<span class="brand"><img class="brand-symbol" src="../assets/finegan-logo.png" alt=""><span>FINEGAN</span></span>';
  const header = `<header class="slide-header">${logo}<span class="offering">STRUCTURED PRODUCTS ADVISORY</span></header>`;
  const heading = (n, s) => `<div class="section-heading"><p class="eyebrow reveal">${s.eyebrow}</p><h${n === 1 ? '1' : '2'} id="title-${n}" class="reveal" style="--delay:80ms">${s.title}</h${n === 1 ? '1' : '2'}></div>`;
  const section = (n, theme, body) => `<section id="slide-${n}" class="slide ${theme}" aria-labelledby="title-${n}" aria-roledescription="slide" aria-label="${n} / 5" ${n > 1 ? 'inert aria-hidden="true"' : ''}>${header}${body}<span class="print-number">${n} / 5</span></section>`;

  const payoffPath = 'M48 288 H250 L330 288 L450 108 L560 288 H742';
  const s1 = `${heading(1, c.s1)}
    <div class="opportunity-copy">
      <p class="lead reveal" style="--delay:180ms">${c.s1.lead}</p>
      <p class="condition reveal" style="--delay:320ms">${c.s1.condition}</p>
    </div>
    <figure class="opportunity-visual" aria-label="${c.s1.flow.join(', ')}">
      <svg class="flow-map" viewBox="0 0 800 430" role="img" aria-hidden="true">
        <defs><linearGradient id="flow-glow" x1="0" x2="1"><stop stop-color="#e04f38" stop-opacity=".25"/><stop offset="1" stop-color="#ef7968" stop-opacity=".02"/></linearGradient></defs>
        <path class="flow-base" d="M70 250 C190 250 190 180 310 180 S430 250 550 250 S650 180 750 180" pathLength="1"/>
        <path class="flow-active" d="M70 250 C190 250 190 180 310 180 S430 250 550 250 S650 180 750 180" pathLength="1"/>
        <path class="payoff-ghost" d="${payoffPath}" pathLength="1"/>
        <path class="payoff-line" d="${payoffPath}" pathLength="1"/>
        <path class="barrier-line" d="M390 82V330" pathLength="1"/>
        <path class="coupon-line" d="M570 145H742" pathLength="1"/>
        <circle class="flow-pulse pulse-1" cx="70" cy="250" r="6"/><circle class="flow-pulse pulse-2" cx="310" cy="180" r="6"/><circle class="flow-pulse pulse-3" cx="550" cy="250" r="6"/><circle class="flow-pulse pulse-4" cx="750" cy="180" r="6"/>
      </svg>
      <div class="flow-nodes">${c.s1.flow.map((label, i) => `<div class="flow-node n${i + 1} reveal" style="--delay:${650 + i * 190}ms"><span>0${i + 1}</span><h3>${label}</h3><p>${c.s1.micro[i]}</p></div>`).join('')}</div>
      <figcaption class="reveal" style="--delay:1500ms">${c.s1.caption}</figcaption>
    </figure>`;

  const stagePositions = [[15,12],[37,2],[64,2],[84,12],[88,40],[84,73],[69,89],[36,89],[15,73],[7,40]];
  const s2 = `${heading(2, c.s2)}
    <p class="chain-lead reveal" style="--delay:180ms">${c.s2.lead}</p>
    <div class="value-chain">
      <svg class="chain-orbit" viewBox="0 0 1000 490" aria-hidden="true"><path class="orbit-track" d="M130 250 C130 95 280 45 500 45 S870 95 870 250 S720 445 500 445 S130 405 130 250" pathLength="1"/><path class="orbit-progress" d="M130 250 C130 95 280 45 500 45 S870 95 870 250 S720 445 500 445 S130 405 130 250" pathLength="1"/></svg>
      <div class="chain-center reveal" style="--delay:500ms"><span class="chain-symbol" aria-hidden="true">◇</span><h3>${c.s2.center}</h3><p>${c.s2.centerSub}</p></div>
      ${c.s2.stages.map((stage, i) => `<div class="chain-stage reveal" style="left:${stagePositions[i][0]}%;top:${stagePositions[i][1]}%;--delay:${650 + i * 75}ms"><span>${String(i + 1).padStart(2, '0')}</span><strong>${stage}</strong></div>`).join('')}
    </div>
    <p class="chain-conclusion reveal" style="--delay:1450ms">${c.s2.conclusion}</p>`;

  const phaseIcons = [
    '<svg viewBox="0 0 54 54" aria-hidden="true"><circle cx="27" cy="27" r="15"/><path d="M27 4v8m0 30v8M4 27h8m30 0h8M15 15l5 5m14 14 5 5m0-24-5 5M20 34l-5 5"/></svg>',
    '<svg viewBox="0 0 54 54" aria-hidden="true"><path d="M8 42V25l19-13 19 13v17M17 42V28h20v14M27 13v29"/></svg>',
    '<svg viewBox="0 0 54 54" aria-hidden="true"><path d="M7 42L45 9m0 0-2 16m2-16-16 2"/><path d="M8 28v14h14"/></svg>',
    '<svg viewBox="0 0 54 54" aria-hidden="true"><path d="M11 35a18 18 0 1 0 1-18M11 9v12h12"/><path d="M27 18v10l7 5"/></svg>'
  ];
  const s3 = `${heading(3, c.s3)}<p class="capability-intro reveal" style="--delay:170ms">${c.s3.intro}</p>
    <div class="capability-roadmap">
      <div class="roadmap-line"><span></span></div>
      ${c.s3.phases.map((phase, i) => `<article class="phase p${i + 1} reveal" style="--delay:${350 + i * 180}ms"><div class="phase-icon">${phaseIcons[i]}</div><span class="phase-number">0${i + 1}</span><h3>${phase[0]}</h3><p>${phase[1]}</p><div class="handoff"><i></i>${c.s3.handoffs[i]}</div></article>`).join('')}
    </div>
    <p class="capability-foot reveal" style="--delay:1200ms">${c.s3.foot}</p>`;

  const s4 = `${heading(4, c.s4)}
    <div class="expertise-model">
      <div class="model-party client-party reveal" style="--delay:220ms"><span class="party-kicker">01</span><div class="party-symbol team-symbol" aria-hidden="true"><i></i><i></i><i></i></div><h3>${c.s4.team}</h3><p>${c.s4.teamSub}</p></div>
      <div class="model-plus reveal" style="--delay:420ms" aria-hidden="true"><span></span><span></span></div>
      <div class="model-party expert-party reveal" style="--delay:560ms"><span class="party-kicker">02</span><div class="party-symbol expert-symbol" aria-hidden="true"><i></i><i></i><i></i></div><h3>${c.s4.expert}</h3><p>${c.s4.expertSub}</p></div>
      <div class="expertise-areas">${c.s4.areas.map((area, i) => `<div class="expertise-area reveal" style="--delay:${760 + i * 80}ms"><i></i>${area}</div>`).join('')}</div>
    </div>
    <p class="expertise-message reveal" style="--delay:1450ms">${c.s4.message}</p>`;

  const s5 = `${heading(5, c.s5)}<p class="scale-intro reveal" style="--delay:150ms">${c.s5.intro}</p>
    <div class="scale-path"><svg class="scale-line" viewBox="0 0 1440 320" preserveAspectRatio="none" aria-hidden="true"><path d="M0 280 H288 V226 H576 V172 H864 V118 H1152 V64 H1440" pathLength="1"/></svg>${c.s5.steps.map((step, i) => `<article class="scale-step s${i + 1} reveal" style="--delay:${340 + i * 150}ms"><span>0${i + 1}</span><h3>${step[0]}</h3><p>${step[1]}</p></article>`).join('')}</div>
    <div class="scale-cta"><div><h3 class="reveal" style="--delay:1150ms">${c.s5.cta}</h3><p class="reveal" style="--delay:1250ms">${c.s5.ctaSub}</p></div><div class="cta-right reveal" style="--delay:1350ms"><a class="contact-link" href="https://finegan.fr/#contact" target="_blank" rel="noopener noreferrer">${c.s5.contact}${arrow}</a><span class="cta-signature">FINEGAN<span>${c.s5.signature}</span></span></div></div>`;

  root.innerHTML = `<div class="deck-frame"><div class="deck">${section(1, 'dark opportunity', s1)}${section(2, 'light chain', s2)}${section(3, 'light capability', s3)}${section(4, 'dark expertise', s4)}${section(5, 'light scale', s5)}<nav class="deck-nav" aria-label="${c.ui.section}"><div class="nav-left"><a class="language-link" href="../${lang === 'fr' ? 'en' : 'fr'}/index.html" title="${c.ui.language}" aria-label="${c.ui.language}"><span ${lang === 'fr' ? 'class="selected"' : ''}>FR</span><span class="language-divider">/</span><span ${lang === 'en' ? 'class="selected"' : ''}>EN</span></a><span class="nav-hint">${c.ui.keys}</span><button class="fullscreen" title="${c.ui.fullscreen}" aria-label="${c.ui.fullscreen}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/></svg></button><button class="replay" title="${c.ui.replay}" aria-label="${c.ui.replay}">↻</button><button class="print" title="${c.ui.print}" aria-label="${c.ui.print}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9V3h12v6M6 17H3V9h18v8h-3M6 14h12v7H6z"/></svg></button></div><div class="progress-dots">${c.ui.labels.map((label, i) => `<button data-slide="${i}" title="${label}" aria-label="${c.ui.slide} ${i + 1} : ${label}"><span></span></button>`).join('')}</div><div class="nav-right"><span class="slide-count"><b>01</b><span>/</span>05</span><button class="previous" aria-label="${c.ui.previous}">${arrow}</button><button class="next" aria-label="${c.ui.next}">${arrow}</button></div><div class="progress-track"><span></span></div></nav></div></div><div class="sr-only" role="status" aria-live="polite" aria-atomic="true"></div><div class="toast" role="status"></div>`;

  const deck = root.querySelector('.deck');
  const frame = root.querySelector('.deck-frame');
  const slides = [...root.querySelectorAll('.slide')];
  const prev = root.querySelector('.previous');
  const next = root.querySelector('.next');
  const fullscreen = root.querySelector('.fullscreen');
  let current = -1;
  let toastTimer;
  const fromHash = () => { const match = /^#slide-([1-5])$/.exec(location.hash); return match ? Number(match[1]) - 1 : 0; };
  const mobile = () => matchMedia('(max-width: 700px) and (orientation: portrait)').matches;

  function fit() {
    const scale = Math.min(innerWidth / 1600, innerHeight / 900);
    deck.style.setProperty('--scale', scale);
    frame.style.width = mobile() ? '100%' : `${1600 * scale}px`;
    frame.style.height = mobile() ? 'auto' : `${900 * scale}px`;
  }

  function show(index, updateHash = true) {
    const n = Math.max(0, Math.min(slides.length - 1, index));
    if (n === current) return;
    const previousSlide = slides[current];
    if (previousSlide?.contains(document.activeElement)) next.focus({preventScroll: true});
    slides.forEach((slide, i) => {
      slide.classList.toggle('active', i === n);
      slide.setAttribute('aria-hidden', String(i !== n));
      slide.inert = i !== n;
    });
    current = n;
    deck.dataset.theme = slides[n].classList.contains('dark') ? 'dark' : 'light';
    prev.disabled = n === 0;
    next.disabled = n === slides.length - 1;
    root.querySelector('.slide-count b').textContent = String(n + 1).padStart(2, '0');
    root.querySelector('.progress-track span').style.transform = `scaleX(${(n + 1) / slides.length})`;
    root.querySelectorAll('[data-slide]').forEach((button, i) => button.setAttribute('aria-current', i === n ? 'step' : 'false'));
    root.querySelector('.language-link').hash = `slide-${n + 1}`;
    root.querySelector('.sr-only').textContent = `${c.ui.slide} ${n + 1} / 5. ${c.ui.labels[n]}`;
    if (updateHash) {
      try { history.replaceState(null, '', `#slide-${n + 1}`); }
      catch { location.hash = `slide-${n + 1}`; }
    }
    if (mobile()) window.scrollTo({top: 0, behavior: 'instant'});
  }

  function replay() {
    const slide = slides[current];
    slide.classList.remove('active');
    void slide.offsetWidth;
    slide.classList.add('active');
  }

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen();
      else throw new Error('unsupported');
    } catch {
      const toast = root.querySelector('.toast');
      toast.textContent = c.ui.unavailable;
      toast.classList.add('visible');
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toast.classList.remove('visible'), 3500);
    }
  }

  prev.addEventListener('click', () => show(current - 1));
  next.addEventListener('click', () => show(current + 1));
  fullscreen.addEventListener('click', toggleFullscreen);
  root.querySelector('.replay').addEventListener('click', replay);
  root.querySelector('.print').addEventListener('click', () => window.print());
  root.querySelectorAll('[data-slide]').forEach(button => button.addEventListener('click', () => show(Number(button.dataset.slide))));
  document.addEventListener('keydown', event => {
    if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
    if ((event.key === ' ' || event.key === 'Enter') && event.target.closest('a,button')) return;
    if (['ArrowRight', 'PageDown', ' '].includes(event.key)) { event.preventDefault(); show(current + (event.shiftKey ? -1 : 1)); }
    else if (['ArrowLeft', 'PageUp'].includes(event.key)) { event.preventDefault(); show(current - 1); }
    else if (event.key === 'Home') { event.preventDefault(); show(0); }
    else if (event.key === 'End') { event.preventDefault(); show(4); }
    else if (event.key.toLowerCase() === 'f') { event.preventDefault(); toggleFullscreen(); }
    else if (event.key.toLowerCase() === 'r') { event.preventDefault(); replay(); }
  });

  let touchStart;
  root.addEventListener('touchstart', event => {
    if (event.touches.length !== 1 || event.target.closest('a,button')) { touchStart = null; return; }
    touchStart = {x: event.touches[0].clientX, y: event.touches[0].clientY};
  }, {passive: true});
  root.addEventListener('touchend', event => {
    if (!touchStart) return;
    const dx = event.changedTouches[0].clientX - touchStart.x;
    const dy = event.changedTouches[0].clientY - touchStart.y;
    if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.5) show(current + (dx < 0 ? 1 : -1));
    touchStart = null;
  }, {passive: true});
  root.addEventListener('touchcancel', () => { touchStart = null; }, {passive: true});
  document.addEventListener('fullscreenchange', () => {
    const label = document.fullscreenElement ? c.ui.exitFullscreen : c.ui.fullscreen;
    fullscreen.setAttribute('aria-label', label);
    fullscreen.title = label;
    fit();
  });
  window.addEventListener('resize', fit);
  window.addEventListener('hashchange', () => show(fromHash(), false));
  root.querySelectorAll('.brand-symbol').forEach(image => image.addEventListener('error', () => { image.hidden = true; }));
  fit();
  show(fromHash());
})();
