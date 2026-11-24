// Structura desk prototype: eight screens sharing one product state.
(function (g) {
  const { useState, useEffect, useMemo, useRef, useCallback, useDeferredValue } = React;
  const { html, fr, sg, clamp, Payoff, VBars, Waterfall, Tornado, TermGrid, Paths, Convergence, Spark, SeriesChart, Scatter, ShockMatrix, CrossSection, BrushChart } = g.UI;
  const E = g.Eng, NH = 3000;

  const NAV = [['accueil', 'Accueil'], ['structuring', 'Structuring'], ['clients', 'Clients'], ['pricer', 'Pricing'], ['booking', 'Life Cycle'], ['risk', 'Risk'], ['rfq', 'RFQ'], ['etudes', 'Études']];
  const short = (s) => s;
  const DEALS = [
    { id: 'D-2364', prod: 'Autocall', cp: 'Banque A', u: 'SX5E', nom: 8, next: '23/11', j: 3, wof: 101.8, bar: 100, bl: 'Rappel 100', kind: 'ac', mtm: 103.10, dv: 0.42, st: ['wa', 'Zone rappel'], d: ['21/11/25', '28/11/25', '21/11/28', '24/11/28'], client: 'beta' },
    { id: 'D-2382', prod: 'Reverse convertible', cp: 'Banque C', u: 'CAC', nom: 3.5, next: '14/12', j: 24, wof: 63.1, bar: 60, bl: 'KI 60', kind: 'ki', mtm: 88.40, dv: -0.91, st: ['ko', 'Barrière proche'], d: ['14/03/25', '21/03/25', '15/03/27', '18/03/27'], client: 'gamma' },
    { id: 'D-2329', prod: 'Phoenix mémoire', cp: 'Banque D', u: 'SX7E, SX5E', nom: 6, next: '18/12', j: 28, wof: 69.6, bar: 65, bl: 'KI 65', kind: 'ki', mtm: 90.12, dv: -0.68, st: ['ko', 'Barrière proche'], d: ['17/01/25', '24/01/25', '17/01/28', '20/01/28'], client: 'delta' },
    { id: 'D-2288', prod: 'Shark note', cp: 'Banque C', u: 'CAC', nom: 2.5, next: '15/06/27', j: 207, wof: 104.6, bar: 130, bl: 'KO 130', kind: 'ko', mtm: 102.05, dv: 0.11, st: ['ok', 'Actif'], d: ['16/06/25', '23/06/25', '15/06/27', '18/06/27'], client: 'gamma' },
    { id: 'D-2398', prod: 'Phoenix mémoire', cp: 'Banque A', u: 'SX7E, SX5E, CAC', nom: 10, next: '14/12', j: 24, wof: 86.4, bar: 60, bl: 'KI 60', kind: 'ki', mtm: 91.68, dv: -0.50, st: ['ok', 'Actif'], d: ['13/06/25', '20/06/25', '13/06/28', '16/06/28'], client: 'alpha' },
    { id: 'D-2254', prod: 'Reverse convertible', cp: 'Banque A', u: 'SX5E', nom: 6.5, next: '30/12', j: 40, wof: 97.4, bar: 65, bl: 'KI 65', kind: 'ki', mtm: 99.15, dv: 0.08, st: ['ok', 'Actif'], d: ['30/06/25', '07/07/25', '30/06/28', '05/07/28'], client: 'beta' },
    { id: 'D-2317', prod: 'Autocall Athena', cp: 'Banque E', u: 'DAX', nom: 7.5, next: '05/01/27', j: 46, wof: 94.2, bar: 60, bl: 'KI 60', kind: 'ki', mtm: 98.77, dv: -0.14, st: ['ok', 'Actif'], d: ['03/07/25', '10/07/25', '05/07/28', '10/07/28'], client: 'beta' },
    { id: 'D-2305', prod: 'Twin Win', cp: 'Banque B', u: 'SX5E', nom: 4, next: '20/03/27', j: 120, wof: 108.3, bar: 70, bl: 'KI 70', kind: 'ki', mtm: 110.25, dv: 0.33, st: ['ok', 'Actif'], d: ['20/03/25', '27/03/25', '20/03/29', '23/03/29'], client: 'alpha' },
    { id: 'D-2351', prod: 'Capital garanti 95 %', cp: 'Banque B', u: 'SX5E', nom: 5, next: '25/11', j: 5, wof: 103.2, bar: null, bl: '', kind: '', mtm: 99.40, dv: 0.05, st: ['ok', 'Actif'], d: ['25/02/25', '04/03/25', '25/01/30', '30/01/30'], client: 'alpha' },
    { id: 'D-2271', prod: 'Booster', cp: 'Banque D', u: 'DAX', nom: 3, next: '12/02/27', j: 84, wof: 112.1, bar: null, bl: '', kind: '', mtm: 114.60, dv: 0.27, st: ['ok', 'Actif'], d: ['12/02/25', '19/02/25', '12/02/29', '15/02/29'], client: 'delta' }
  ].map((x, i) => ({ ...x, dist: x.bar === null ? null : x.kind === 'ko' ? x.bar - x.wof : x.wof - x.bar, s: walk(x.wof, 300 + i * 7) }));

  function walk(end, seed, n = 70) {
    const z = E.gaussians(n, seed), out = [];
    let c = 0;
    const steps = Array.from({ length: n }, (_, i) => { if (i) c += z[i]; return c; });
    const last = steps[n - 1];
    for (let i = 0; i < n; i++) { const u = i / (n - 1); out.push(100 + (end - 100) * u + 1.45 * (steps[i] - last * u)); }
    return out;
  }

  const Status = ({ s }) => html`<span className=${'st ' + s[0]}>${s[1]}</span>`;
  const Tabs = ({ items, cur, set }) => html`<div className="ptabs" role="tablist">${items.map(([k, l]) => html`<button key=${k} type="button" role="tab" aria-selected=${k === cur} className=${'pt' + (k === cur ? ' on' : '')} onClick=${() => set(k)}>${l}</button>`)}</div>`;
  const Metric = ({ l, v, cl }) => html`<div><span>${l}</span><strong className=${cl || ''}>${v}</strong></div>`;
  const Card = ({ title, sub, children, cls, style }) => html`<section className=${'card ' + (cls || '')} style=${style}><div className="card-h"><b>${title}</b><span>${sub}</span></div><div className="card-b">${children}</div></section>`;
  const Ticket = ({ back, go, title, sub, metrics = [], children }) => html`<div className="ticket">
    ${back ? html`<a className="b" href=${'#' + back}>← Retour</a>` : null}
    <div className="tk-title"><b>${title}</b><span>${sub}</span></div>
    ${metrics.length ? html`<div className="tk-m">${metrics.map(([l, v]) => html`<div key=${l}><span>${l}</span><b>${v}</b></div>`)}</div>` : null}
    <div className="tk-end">${children}</div>
  </div>`;
  const Num = ({ id, label, code, value, step, min, max, unit, onChange, hi }) => html`<label className=${'pr' + (hi ? ' hi' : '')} htmlFor=${id}><span>${label}${code ? html`<code>${code}</code>` : null}</span><span className="num"><input id=${id} type="number" value=${value} step=${step} min=${min} max=${max} onChange=${(e) => { const v = parseFloat(e.target.value); if (Number.isFinite(v)) onChange(clamp(v, min, max)); }}/><em>${unit}</em></span></label>`;
  const Ro = ({ l, v }) => html`<div className="pr"><span>${l}</span><span className="ro">${v}</span></div>`;

  const SCRIPT = ['UNDERLYING Basket', '', '# Phoenix à coupon mémoire', 'PARAM COUPON', 'PARAM M_AC_BAR', 'PARAM M_CPN_BAR', 'PARAM M_KI_BAR', '', 'CONSTAT StartDate', 'CONSTAT() ObservationDates', '', 'AT StartDate:', '  Basket.spot0 = Basket.spot@StartDate', '', 'AT Date FROM ObservationDates:', '  IF WORSTOF(Basket.yield) >= M_CPN_BAR:', '    PAY COUPON * (INDEX - MEMO) "Coupon"', '    SET MEMO = INDEX', '  IF WORSTOF(Basket.yield) >= M_AC_BAR:', '    PAY 1 "Remboursement anticipé"', '    STOP', '', 'AT ObservationDates.last:', '  SET KI = INDIC(WORSTOF(Basket.yield) < M_KI_BAR)', '  PAY 1 "Capital à maturité"', '  PAY -KI * MAX(1 - WORSTOF(Basket.yield), 0) "Put"'];
  function codeLine(l, i) {
    if (l.startsWith('#')) return html`<span key=${i} className="l"><span className="c">${l}</span></span>`;
    const parts = l.split(/(\b(?:UNDERLYING|PARAM|CONSTAT|AT|FROM|IF|PAY|SET|STOP)\b|\bM_[A-Z_]+\b|\bCOUPON\b|"[^"]*")/g).filter((x) => x !== '');
    return html`<span key=${i} className="l">${parts.length ? parts.map((p, k) => /^(UNDERLYING|PARAM|CONSTAT|AT|FROM|IF|PAY|SET|STOP)$/.test(p) ? html`<span key=${k} className="k">${p}</span>` : /^(M_|COUPON)/.test(p) ? html`<span key=${k} className="p">${p}</span>` : p.startsWith('"') ? html`<span key=${k} className="s">${p}</span>` : p) : ' '}</span>`;
  }

  // ---------- Pricing ----------
  function Pricer({ ctx }) {
    const { terms: t, setTerms, market: m, setMarket, W, res: r, job, Z } = ctx;
    const [left, setLeft] = useState('eco');
    const [view, setView] = useState('prix');
    const dt = useDeferredValue(t), dm = useDeferredValue(m);
    const sens = useMemo(() => (view === 'sens' ? E.sensitivities(Z, NH, dt, dm, E.value(E.simulate(dm, Z, NH), dt, dm).px) : []), [view, dt, dm, Z]);
    const fresh = job.phase === 'done' && !job.stale;
    const px = ctx.px, ci = fresh ? job.res.ci : r.ci;
    const exits = [...r.exits.slice(3).map((v, i) => ({ l: 'T' + (i + 4), v, t: 'Rappel en T' + (i + 4) + ' · ' + E.fd(E.OBS[i + 3]) })), { l: 'Pair', v: r.par, c: 'mid', t: 'Remboursé au pair à maturité' }, { l: 'Perte', v: r.loss, c: 'loss', t: 'Perte en capital à maturité' }];
    const setU = (k, i, v) => setMarket({ ...m, [k]: m[k].map((x, j) => (j === i ? v / 100 : x)) });
    const ex = 100 - px;
    return html`<${React.Fragment}>
      <${Ticket} back="accueil" title="Phoenix mémoire worst-of 3 ans" sub=${'Modèle Phoenix à coupon mémoire · ' + (job.stale ? 'termes modifiés, à recalculer' : 'calcul à jour')} metrics=${[['Nominal', '5 000 000 €'], ['Strike', E.fd(E.STRIKE)], ['Maturité', E.fd(E.OBS[11])], ['Paiement', E.fd(E.PAY[11])]]}>
        <button className="b" type="button" onClick=${() => setTerms(E.TERMS)}>Réinitialiser</button>
        <a className="b" href="#rfq">Ouvrir une RFQ</a>
        <button className="b p" type="button" onClick=${job.run}>Pricer <kbd>F9</kbd></button>
      <//>
      <div className="work w-p">
        <section className="pane" aria-label="Définition du produit">
          <${Tabs} cur=${left} set=${setLeft} items=${[['eco', 'Economics'], ['script', 'PayScript'], ['mkt', 'Marché']]}/>
          <div className="pbody">
            ${left === 'eco' ? html`<${React.Fragment}>
              <div className="sh c">Quatre dates <span>TARGET</span></div>
              <${Ro} l="Strike / fixing S₀" v=${E.fd(E.STRIKE)}/><${Ro} l="Date de valeur" v=${E.fd(E.VALUE)}/><${Ro} l="Maturité" v=${E.fd(E.OBS[11])}/><${Ro} l="Paiement final, J+3" v=${E.fd(E.PAY[11])}/>
              <div className="sh c">Payoff <span>Economics fait foi</span></div>
              <${Num} id="f-c" label="Coupon" code="COUPON" value=${t.c} step="0.05" min="0" max="6" unit="%" hi onChange=${(v) => setTerms({ ...t, c: v })}/>
              <${Num} id="f-cpn" label="Barrière coupon" code="M_CPN_BAR" value=${t.cpn} step="1" min=${t.ki} max="100" unit="%" onChange=${(v) => setTerms({ ...t, cpn: v })}/>
              <${Num} id="f-ki" label="Protection" code="M_KI_BAR" value=${t.ki} step="1" min="35" max=${t.cpn} unit="%" onChange=${(v) => setTerms({ ...t, ki: v })}/>
              <${Num} id="f-ac" label="Rappel" code="M_AC_BAR" value=${t.ac} step="1" min="80" max="120" unit="%" onChange=${(v) => setTerms({ ...t, ac: v })}/>
              <${Num} id="f-from" label="Premier rappel" value=${t.acFrom + 1} step="1" min="1" max="12" unit="T" onChange=${(v) => setTerms({ ...t, acFrom: Math.round(v) - 1 })}/>
              <div className="pr"><span>Effet mémoire</span><button type="button" aria-pressed=${t.memo} className=${'tog' + (t.memo ? ' on' : '')} onClick=${() => setTerms({ ...t, memo: !t.memo })}>${t.memo ? 'Oui' : 'Non'}</button></div>
              <div className="sh m">Sous-jacents <span>worst-of de 3</span></div>
              ${E.UND.map((u) => html`<${Ro} key=${u.k} l=${u.n} v=${fr(u.spot)}/>`)}
              <div className="sh c">Observations <span>12 constatations</span></div>
              <${Ro} l="Première" v=${E.fd(E.OBS[0])}/><${Ro} l="Fréquence · convention" v="3 M · Suivant"/>
            <//>` : null}
            ${left === 'script' ? html`<${React.Fragment}><div className="sh h">Phoenix à coupon mémoire <span>v2.0 · validé</span></div><pre className="code">${SCRIPT.map(codeLine)}</pre><//>` : null}
            ${left === 'mkt' ? html`<${React.Fragment}>
              <div className="sh m">Volatilité <span>valeur utilisée</span></div>
              ${E.UND.map((u, i) => html`<${Num} key=${u.k} id=${'v' + i} label=${u.n} code=${u.src === 'Surcharge' ? 'surcharge' : ''} value=${+(m.vols[i] * 100).toFixed(2)} step="0.5" min="5" max="80" unit="%" onChange=${(v) => setU('vols', i, v)}/>`)}
              <div className="sh m">Dividendes</div>
              ${E.UND.map((u, i) => html`<${Num} key=${u.k} id=${'q' + i} label=${u.n} value=${+(m.qs[i] * 100).toFixed(2)} step="0.05" min="0" max="12" unit="%" onChange=${(v) => setU('qs', i, v)}/>`)}
              <div className="sh c">Courbes</div>
              <${Num} id="f-r" label="Taux, drift et actualisation" value=${+(m.r * 100).toFixed(2)} step="0.05" min="-1" max="8" unit="%" onChange=${(v) => setMarket({ ...m, r: v / 100 })}/>
              <${Num} id="f-s" label="Spread, actualisation seule" value=${Math.round(m.s * 1e4)} step="5" min="0" max="400" unit="bps" onChange=${(v) => setMarket({ ...m, s: v / 1e4 })}/>
              <div className="sh h">Aperçu navigateur</div>
              <${Ro} l="Modèle" v="GBM corrélé"/><${Ro} l="Chemins" v="6 000, antithétiques"/>
            <//>` : null}
          </div>
        </section>

        <section className="pane" aria-label="Résultats">
          <${Tabs} cur=${view} set=${setView} items=${[['prix', 'Prix & payoff'], ['grille', 'Grille de structuration'], ['traj', 'Trajectoires'], ['sens', 'Sensibilités']]}/>
          <div className="pbody"><div className="pad fillcol">
            <div className="hero">
              <div className="hero-p"><small>${fresh ? 'Prix équitable, date de valeur' : 'Aperçu instantané'}</small><b>${fr(px)} %</b><small>IC 95 % ±${fr(ci)} pt · ${fresh ? fr(job.res.n, 0) : '6 000'} chemins</small></div>
              <div className="hs">
                <${Metric} l="Écart au pair" v=${sg(-ex) + ' pts'}/><${Metric} l="Vie espérée" v=${fr(r.life) + ' ans'}/><${Metric} l="P(perte)" v=${fr(r.loss, 1) + ' %'}/><${Metric} l="Perte moyenne" v=${r.loss ? fr(r.lossLevel, 1) + ' %' : '—'}/>
                <${Metric} l="Coupons, PV" v=${fr(r.pv.cpn) + ' pts'}/><${Metric} l="Rappels, PV" v=${fr(r.pv.call) + ' pts'}/><${Metric} l="Maturité, PV" v=${fr(r.pv.par + r.pv.loss) + ' pts'}/><${Metric} l="P(rappel)" v=${fr(r.exits.reduce((a, b) => a + b, 0), 1) + ' %'}/>
              </div>
            </div>
            ${view === 'prix' ? html`<${React.Fragment}>
              <div className="two grow">
                <${Card} cls="grow" title="Remboursement à maturité" sub="glissez KI et Cpn sur le graphique"><${Payoff} t=${t} onChange=${setTerms}/><//>
                <${Card} cls="grow" title="Sorties par constatation" sub="se recalcule pendant le glissement"><${VBars} items=${exits} label="Probabilité de sortie à chaque constatation"/><//>
              </div>
              <${Card} title="Décomposition du prix" sub=${'aperçu 6 000 chemins : ' + fr(r.px) + ' %, points du nominal'}>
                <${Waterfall} h=${132} label="Décomposition du prix" items=${[{ l: 'Rappels', v: r.pv.call }, { l: 'Pair', v: r.pv.par }, { l: 'Capital après put', v: r.pv.loss }, { l: 'Coupons', v: r.pv.cpn }, { l: 'Aperçu', v: r.px, total: true }]}/>
              <//>
            <//>` : null}
            ${view === 'grille' ? html`<${Card} cls="grow" title="Prix selon le coupon et la protection" sub="cliquez une case pour adopter ces termes · repère 98 %"><${TermGrid} W=${W} t=${t} market=${m} onPick=${setTerms}/><//>` : null}
            ${view === 'traj' ? html`<${Card} cls="grow" title="Éventail du worst-of" sub="P5–P95, médiane et 28 trajectoires · survolez pour isoler une trajectoire"><${Paths} W=${W} t=${t} market=${m}/><//>` : null}
            ${view === 'sens' ? html`<${React.Fragment}>
              <${Card} title="Sensibilités du prix" sub="repricing complet sur les mêmes tirages, en points"><${Tornado} items=${sens.length ? sens : []} h=${210}/><//>
              <${Card} title="Contrôle du funding" sub="le spread n'apporte aucun drift">
                ${sens.length ? html`<table className="t"><tbody>
                  <tr><td>Taux +100 bps, drift et actualisation</td><td className="r neg">${sg(sens.find((x) => x.k === 'rate').d)} pt</td></tr>
                  <tr><td>Spread +100 bps, actualisation seule</td><td className="r neg">${sg(sens.find((x) => x.k === 'spread').d)} pt</td></tr>
                  <tr className="sum"><td>Contribution du drift</td><td className="r">${fr(sens.find((x) => x.k === 'rate').d - sens.find((x) => x.k === 'spread').d)} pt</td></tr>
                </tbody></table>` : null}
              <//>
            <//>` : null}
          </div></div>
        </section>

        <aside className="pane insp" aria-label="Calcul FastAPI">
          <div className="sh h" style=${{ minHeight: 33 }}>Calcul FastAPI <span>flux simulé</span></div>
          <div className="prog" role="progressbar" aria-valuenow=${Math.round(job.prog * 100)} aria-valuemin="0" aria-valuemax="100"><i style=${{ width: job.prog * 100 + '%' }}></i></div>
          <div className="pbody">
            <div className="chk"><span className=${'st ' + (job.phase === 'done' ? (job.stale ? 'wa' : 'ok') : 'nf')}>${job.phase === 'done' ? (job.stale ? 'Résultat périmé' : 'Calcul terminé') : job.phase === 'cancelled' ? 'Calcul annulé' : job.phase === 'idle' ? 'Prêt' : 'Calcul en cours, ' + Math.round(job.prog * 100) + ' %'}</span><small>Lots de 5 000 chemins, tirages indépendants</small></div>
            <div style=${{ padding: '6px 10px 2px' }}><${Convergence} points=${job.pts} total=${100000}/></div>
            ${job.phase === 'running' || job.phase === 'queued' ? html`<div style=${{ padding: '0 10px 6px' }}><button className="b" style=${{ width: '100%' }} type="button" onClick=${job.cancel}>Annuler le calcul</button></div>` : null}
            <div className="sh c">Échanges API</div>
            <pre className="log">${job.log.map((l, i) => html`<span key=${i}>${l[0]} <b>${l[1]}</b>${'\n'}</span>`)}</pre>
            <div className="sh m">Contrôle du prix</div>
            <div className="chk"><span className="st ok">Dates cohérentes</span><small>Actualisation à la date de paiement</small></div>
            <div className="chk"><span className="st ok">Funding hors drift</span><small>Spread en actualisation seule</small></div>
            <div className="chk"><span className="st wa">Volatilité saisie</span><small>Banks ${fr(m.vols[1] * 100)} %, pas d'implicite</small></div>
            <div className="chk"><span className="st wa">Modèle d'aperçu</span><small>GBM sans smile, données fictives</small></div>
          </div>
        </aside>
      </div>
    <//>`;
  }

  // ---------- Life Cycle ----------
  const Gauge = ({ d }) => { if (d.bar === null) return html`<span className="dim">Sans barrière</span>`; const x = (v) => clamp((v - 40) / 95 * 112, 0, 112); return html`<svg width="116" height="16" aria-hidden="true" style=${{ display: 'block' }}><rect x="0" y="6" width="114" height="4" style=${{ fill: 'var(--hair)' }}/><rect x=${x(d.bar) - 1} y="2" width="2" height="12" style=${{ fill: 'var(--neg)' }}/><circle cx=${x(d.wof)} cy="8" r="4" style=${{ fill: 'var(--s1)', stroke: 'var(--card)', strokeWidth: 1.5 }}/></svg>`; };
  function Booking({ ctx }) {
    const d = DEALS.find((x) => x.id === ctx.deal) || DEALS[4];
    const [flt, setFlt] = useState('all');
    const rows = DEALS.filter((x) => flt === 'all' || (flt === 'near' && x.dist !== null && x.dist < 5) || (flt === 'barrier' && x.bar !== null)).slice().sort((a, b) => (a.dist === null ? 999 : a.dist) - (b.dist === null ? 999 : b.dist));
    const f = d.dv / -0.5, parts = [['Spot', -0.74], ['Vol', 0.12], ['Temps', 0.08], ['Taux', -0.03], ['Spread', 0.05], ['Résidu', 0.02]].map(([l, v]) => ({ l, v: v * f }));
    const low = Math.min(d.mtm - d.dv, d.mtm, ...(() => { let c = d.mtm - d.dv; return parts.map((p) => (c += p.v)); })()), high = Math.max(d.mtm - d.dv, d.mtm, ...(() => { let c = d.mtm - d.dv; return parts.map((p) => (c += p.v)); })()), mg = Math.max(high - low, 0.1);
    return html`<${React.Fragment}>
      <${Ticket} back="accueil" title="Booking, produits bookés" sub="38 dossiers sur 38 sans erreur · rafraîchi le 20/11 à 17:35" metrics=${[['Deals vivants', '38'], ['Nominal', '186,4 M€'], ['MtM agrégé', '178,9 M€'], ['P&L du jour', '+42 300 €']]}>
        <a className="b" href="#risk">Portefeuilles & chocs</a><button className="b p" type="button">Rafraîchir le book</button>
      <//>
      <div className="work w-b">
        <section className="pane" aria-label="Blotter">
          <div className="filters">
            <input className="fs" type="search" aria-label="Filtrer les deals" placeholder="Référence, produit…"/>
            ${[['all', 'Tous', '10'], ['barrier', 'À barrière', '8'], ['near', 'À moins de 5 pts', '3']].map(([k, l, n]) => html`<button key=${k} type="button" aria-pressed=${flt === k} className=${'fc' + (flt === k ? ' on' : '')} onClick=${() => setFlt(k)}>${l} <span>${n}</span></button>`)}
            <span className="dim" style=${{ marginLeft: 'auto' }}>${rows.length} sur 38 · tri : seuil le plus proche</span>
          </div>
          <div className="pbody tbox"><table className="t" style=${{ minWidth: 820 }}>
            <thead><tr><th>Réf.</th><th>Produit</th><th>Contrepartie</th><th className="r">Nominal</th><th>Prochaine obs.</th><th>Trajectoire</th><th className="r">WOF %</th><th>Position / seuil</th><th className="r">Distance</th><th className="r">MtM %</th><th>Statut</th></tr></thead>
            <tbody>${rows.map((x) => html`<tr key=${x.id} className=${'row' + (x.id === d.id ? ' sel' : '')} onClick=${() => ctx.setDeal(x.id)}>
              <td><button type="button" className="rowb">${x.id}</button></td><td>${x.prod}</td><td>${x.cp}</td><td className="r">${fr(x.nom, 1)} M</td><td>${x.next} <span className="dim">J-${x.j}</span></td>
              <td><${Spark} v=${x.s} bar=${x.bar}/></td><td className="r">${fr(x.wof)}</td><td><${Gauge} d=${x}/></td><td className=${'r ' + (x.dist !== null && x.dist < 5 && x.kind !== 'ac' ? 'neg' : '')}>${x.dist === null ? '—' : sg(x.dist, 1)}</td><td className="r">${fr(x.mtm)}</td><td><${Status} s=${x.st}/></td>
            </tr>`)}</tbody>
          </table></div>
        </section>
        <aside className="pane" aria-label="Détail du deal">
          <div className="sh h" style=${{ minHeight: 33 }}>${d.id} · ${d.prod}<span>${d.cp}</span></div>
          <div className="pbody"><div className="pad">
            <div className="hero" style=${{ gridTemplateColumns: 'minmax(0,1fr)' }}>
              <div className="hero-p" style=${{ borderRight: 0, borderBottom: '1px solid var(--chrome3)' }}><small>MtM résiduel, 20/11/2026</small><b>${fr(d.mtm)} %</b><small>${fr(d.nom, 1)} M€ · ${fr(d.nom * d.mtm * 1e4, 0)} €</small></div>
              <div className="hs" style=${{ gridTemplateColumns: 'repeat(3,minmax(0,1fr))' }}>
                <div style=${{ borderBottom: 0 }}><span>Variation 5 j</span><strong>${sg(d.dv)} pt</strong></div><div style=${{ borderBottom: 0 }}><span>Seuil</span><strong>${d.dist === null ? '—' : sg(d.dist, 1) + ' pts'}</strong></div><div style=${{ borderBottom: 0, borderRight: 0 }}><span>Prochaine obs.</span><strong>${d.next}</strong></div>
              </div>
            </div>
            <div className="dates"><div><span>Strike</span><b>${d.d[0]}</b></div><div><span>Valeur</span><b>${d.d[1]}</b></div><div><span>Maturité</span><b>${d.d[2]}</b></div><div><span>Paiement</span><b>${d.d[3]}</b></div></div>
            <${Card} title="Worst-of et seuils" sub="% du strike · survolez"><${SeriesChart} key=${d.id} h=${176} series=${d.s} refs=${d.bar === null ? [] : [{ l: d.bl, v: d.bar, hot: true }]} labels=${[{ i: 0, t: d.d[0] }, { i: 69, t: '20/11/26' }]} fmtX=${(i) => 'Séance ' + (i + 1) + ' sur 70'} label=${'Trajectoire du worst-of de ' + d.id}/><//>
            <${Card} title="Pont de valorisation" sub="13/11 → 20/11, axe tronqué"><${Waterfall} h=${132} domain=${[low - mg * 0.25, high + mg * 0.25]} label="Pont de valorisation" items=${[{ l: '13/11', v: d.mtm - d.dv, total: true }, ...parts, { l: '20/11', v: d.mtm, total: true }]}/><//>
            <div className="acts"><button className="b p" type="button">Calculer le MtM</button><button className="b" type="button">Note de valo</button><button className="b" type="button">Greeks</button><button className="b" type="button">Choc</button></div>
          </div></div>
        </aside>
      </div>
    <//>`;
  }

  // ---------- Accueil ----------
  function Accueil({ ctx }) {
    const items = DEALS.filter((x) => x.bar !== null).map((x) => ({ id: x.id, x: Math.min(x.j, 210), y: x.dist, c: x.dist < 5 ? 'hot' : '', tag: x.dist < 6 ? x.id : '', side: x.id === 'D-2382' ? 'l' : x.id === 'D-2329' ? 'r' : '', nom: x.nom, title: x.id + ' · ' + x.prod, rows: [['Prochaine obs.', x.next], ['Distance', sg(x.dist, 1) + ' pts'], ['Nominal', fr(x.nom, 1) + ' M€']] }));
    const acts = [['Aujourd\'hui', 'Valider un fixing', 'D-2382', 'CAC 40, écart de source 0,4 %', ['ko', 'Bloquant'], 'booking'], ['16:40', 'Choisir un émetteur', 'RFQ-0187', '5 cotations reçues', ['wa', 'Urgent'], 'rfq'], ['23/11', 'Constatation autocall', 'D-2364', 'Worst à 101,80 %, rappel probable', ['nf', 'À suivre'], 'booking'], ['24/11', 'Note de valorisation', 'D-2398', 'Trimestrielle, Family Office Alpha', ['nf', 'À préparer'], 'booking'], ['25/11', 'Paiement de coupon', 'D-2351', '97 500 €, règlement J+3', ['ok', 'Prêt'], 'booking']];
    const open = (id, route) => { if (id.startsWith('D-')) ctx.setDeal(id); location.hash = route; };
    return html`<${React.Fragment}>
      <${Ticket} title="Desk du vendredi 20 novembre" sub="Trois décisions attendues aujourd'hui, marché à la clôture">
        <a className="b" href="#structuring">Explorer des structures</a><a className="b" href="#rfq">Nouvelle RFQ</a><a className="b p" href="#pricer">Nouveau pricing</a>
      <//>
      <div className="work w3">
        <aside className="pane" aria-label="Reprendre">
          <div className="sh c" style=${{ minHeight: 33 }}>Reprendre <span>récents</span></div>
          <div className="pbody">
            ${[['pricer', 'Phoenix mémoire WO 3 ans', fr(ctx.px), 'Pricing · brouillon v3', 'il y a 12 min'], ['rfq', 'RFQ-0187', '5/5', 'Émetteur à choisir', 'avant 16:40'], ['booking', 'D-2398 Phoenix', '91,68', 'Note à émettre', 'hier'], ['structuring', 'Recherche Phoenix WO', '18', 'Candidats', 'hier'], ['etudes', 'Étude AMC Exemple', '84 %', 'Confiance', '18/11'], ['clients', 'Family Office Alpha', '2', 'Relances dues', '18/11']].map(([h, a, b, c, e]) => html`<a key=${a} className="li" href=${'#' + h}><b>${a}</b><em>${b}</em><small>${c}</small><small>${e}</small></a>`)}
          </div>
        </aside>
        <section className="pane" aria-label="Activité du desk"><div className="pbody"><div className="pad fillcol">
          <div className="solo"><div className="hs c5"><${Metric} l="Encours vivant" v="186,4 M€"/><${Metric} l="MtM agrégé" v="178,9 M€"/><${Metric} l="P&L du jour" v="+42 300 €" cl="lm"/><${Metric} l="Événements, 5 séances" v="11"/><${Metric} l="Barrières < 5 pts" v="2"/></div></div>
          <${Card} cls="grow" title="Radar du book" sub="distance au seuil selon l'échéance de la prochaine observation · taille = nominal · cliquez un deal">
            <${Scatter} items=${items} xd=${[0, 215]} yd=${[0, 45]} xt=${[0, 50, 100, 150, 200]} yt=${[0, 10, 20, 30, 40]} xFmt=${(v) => 'J+' + v} yFmt=${(v) => v + ' pts'} size=${(d) => 4 + d.nom * 0.85} onSel=${(id) => open(id, 'booking')} label="Radar des barrières du book"/>
          <//>
          <div className="card"><div className="card-h"><b>À traiter</b><span>par échéance</span></div><div className="tbox"><table className="t">
            <tbody>${acts.map((a) => html`<tr key=${a[2]} className="row" onClick=${() => open(a[2], a[5])}><td className="mono">${a[0]}</td><td>${a[1]}</td><td><button type="button" className="rowb">${a[2]}</button></td><td className="dim">${a[3]}</td><td><${Status} s=${a[4]}/></td></tr>`)}</tbody>
          </table></div></div>
        </div></div></section>
        <aside className="pane insp" aria-label="Fiabilité et modules">
          <div className="sh h" style=${{ minHeight: 33 }}>Fiabilité du marché <span>avant diffusion</span></div>
          <div className="pbody">
            <div className="chk"><span className="st wa">Cours non licenciés</span><small>Source Yahoo, prix indicatifs</small></div>
            <div className="chk"><span className="st wa">Volatilités saisies</span><small>Aucune implicite de marché</small></div>
            <div className="chk"><span className="st ok">Courbes à jour</span><small>Taux et funding au 20/11</small></div>
            <div className="chk"><span className="st ko">1 fixing à valider</span><small>D-2382, CAC 40</small></div>
            <div className="sh c">Cinq prochaines séances</div>
            ${[['Lun. 23', '3', 'Constatation D-2364'], ['Mar. 24', '2', 'Note de valo D-2398'], ['Mer. 25', '3', 'Coupon D-2351'], ['Jeu. 26', '1', 'Règlement D-2208'], ['Ven. 27', '2', 'Strike D-2417']].map(([a, n, t]) => html`<div key=${a} className="li" style=${{ cursor: 'default' }}><b>${a}</b><em>${n}</em><small>${t}</small><small>évén.</small></div>`)}
          </div>
        </aside>
      </div>
    <//>`;
  }

  // ---------- Structuring ----------
  function Structuring({ ctx }) {
    const { W, terms: t, market: m } = ctx;
    const [target, setTarget] = useState(98);
    const [limit, setLimit] = useState(30);
    const [sel, setSel] = useState(null);
    const cands = useMemo(() => { const out = []; [50, 55, 60, 65, 70, 75].forEach((ki) => [95, 100, 105].forEach((ac) => { const cpn = Math.max(t.cpn, ki), r = E.value(W, { ...t, ki, ac, cpn, c: 0 }, m), c = (target - r.A) / r.B; out.push({ id: ki + '-' + ac, ki, ac, cpn, c, loss: r.loss, life: r.life }); })); return out.sort((a, b) => b.c - a.c); }, [W, t.cpn, t.acFrom, t.memo, m, target]);
    const ok = cands.filter((x) => x.loss <= limit), best = ok[0], cur = cands.find((x) => x.id === sel) || best || cands[0];
    const frontier = useMemo(() => { const f = []; let top = -1; cands.slice().sort((a, b) => a.loss - b.loss).forEach((x) => { if (x.c > top) { top = x.c; f.push([x.loss, x.c]); } }); return f; }, [cands]);
    const cmin = Math.floor(Math.min(...cands.map((x) => x.c)) * 2) / 2, cmax = Math.ceil(Math.max(...cands.map((x) => x.c)) * 2) / 2;
    const yt = []; for (let v = cmin; v <= cmax + 1e-6; v += 0.5) yt.push(v);
    const items = cands.map((x) => ({ id: x.id, x: x.loss, y: x.c, c: x.loss > limit ? 'off' : '', title: 'KI ' + x.ki + ' % · rappel ' + x.ac + ' %', rows: [['Coupon', fr(x.c) + ' %'], ['P(perte)', fr(x.loss, 1) + ' %'], ['Vie', fr(x.life) + ' ans']] }));
    const adopt = () => { ctx.setTerms({ ...t, ki: cur.ki, ac: cur.ac, cpn: cur.cpn, c: Math.round(cur.c * 100) / 100 }); location.hash = 'pricer'; };
    return html`<${React.Fragment}>
      <${Ticket} back="accueil" title="Product Optimizer" sub="Phoenix mémoire worst-of · coupon résolu à valeur cible" metrics=${[['Objectif', 'Max. coupon'], ['Valeur cible', fr(target) + ' %'], ['P(perte) max.', limit + ' %'], ['Candidats', String(cands.length)]]}>
        <button className="b" type="button">Conserver la recherche</button><button className="b p" type="button" onClick=${adopt}>Ouvrir dans le Pricer</button>
      <//>
      <div className="work w3">
        <section className="pane" aria-label="Demande">
          <div className="sh c" style=${{ minHeight: 33 }}>Demande <span>marché figé</span></div>
          <div className="pbody">
            <${Ro} l="Famille" v="Phoenix"/><${Ro} l="Panier" v="SX5E, SX7E, CAC"/><${Ro} l="Maturité" v="3 ans"/>
            <div className="sh m">Axes explorés</div><${Ro} l="Protection" v="50–75 %"/><${Ro} l="Rappel" v="95–105 %"/>
            <div className="sh h">Contraintes</div>
            <${Num} id="s-t" label="Valeur cible" value=${target} step="0.25" min="90" max="102" unit="%" hi onChange=${setTarget}/>
            <${Num} id="s-l" label="P(perte) maximale" value=${limit} step="1" min="5" max="45" unit="%" onChange=${setLimit}/>
            <div className="chk"><span className="st nf">Copilot à venir</span><small>Traduira une intention en contraintes</small></div>
          </div>
        </section>
        <section className="pane" aria-label="Résultats"><div className="pbody"><div className="pad fillcol">
          <div className="solo"><div className="hs c5"><${Metric} l="Candidats" v=${cands.length}/><${Metric} l="Admissibles" v=${ok.length}/><${Metric} l="Écartés" v=${cands.length - ok.length}/><${Metric} l="Meilleur coupon" v=${best ? fr(best.c) + ' %' : '—'} cl="lm"/><${Metric} l="Son P(perte)" v=${best ? fr(best.loss, 1) + ' %' : '—'}/></div></div>
          <${Card} cls="grow" title="Frontière coupon / risque" sub="glissez la limite de perte · cliquez un candidat">
            <${Scatter} items=${items} sel=${cur.id} onSel=${setSel} frontier=${frontier} limit=${limit} onLimit=${setLimit} xd=${[5, 45]} yd=${[cmin, cmax]} xt=${[5, 15, 25, 35, 45]} yt=${yt} xFmt=${(v) => v + ' %'} yFmt=${(v) => fr(v, 1)} label="Coupon résolu selon la probabilité de perte"/>
          <//>
          <div className="card tbox" style=${{ maxHeight: 214, overflowY: 'auto' }}><table className="t"><thead><tr><th>Protection</th><th className="r">Rappel</th><th className="r">Coupon</th><th className="r">P(perte)</th><th className="r">Vie</th><th>Statut</th></tr></thead>
            <tbody>${cands.map((x) => html`<tr key=${x.id} className=${'row' + (x.id === cur.id ? ' sel' : '')} onClick=${() => setSel(x.id)}><td><button type="button" className="rowb">${x.ki} %</button></td><td className="r">${x.ac} %</td><td className="r">${fr(x.c)} %</td><td className="r">${fr(x.loss, 1)} %</td><td className="r">${fr(x.life)}</td><td><${Status} s=${x.loss > limit ? ['ko', 'Écarté'] : best && x.id === best.id ? ['ok', 'Meilleur'] : ['ok', 'Admissible']}/></td></tr>`)}</tbody>
          </table></div>
        </div></div></section>
        <aside className="pane insp" aria-label="Candidat">
          <div className="sh h" style=${{ minHeight: 33 }}>Candidat <span>${cur.loss > limit ? 'Écarté' : 'Admissible'}</span></div>
          <div className="pbody"><div className="pad">
            <div className="hero" style=${{ gridTemplateColumns: 'minmax(0,1fr)' }}><div className="hero-p" style=${{ borderRight: 0 }}><small>Coupon résolu, par trimestre</small><b>${fr(cur.c)} %</b><small>Soit ${fr(cur.c * 4)} % par an</small></div></div>
            <div className="card"><table className="t"><tbody><tr><td>Protection</td><td className="r">${cur.ki} %</td></tr><tr><td>Barrière coupon</td><td className="r">${cur.cpn} %</td></tr><tr><td>Rappel</td><td className="r">${cur.ac} %</td></tr><tr><td>P(perte)</td><td className="r">${fr(cur.loss, 1)} %</td></tr><tr><td>Vie espérée</td><td className="r">${fr(cur.life)} ans</td></tr></tbody></table></div>
            <button className="b p" type="button" onClick=${adopt}>Ouvrir dans le Pricer</button>
            <div className="note">Résultat GBM sans smile, à confirmer avant toute diffusion.</div>
          </div></div>
        </aside>
      </div>
    <//>`;
  }

  // ---------- RFQ ----------
  const QUOTES = [{ id: 'C', n: 'Banque C', r: 'AA−', c: 2.82, line: 96, exp: '16:55' }, { id: 'B', n: 'Banque B', r: 'A+', c: 2.78, line: 71, exp: '16:40' }, { id: 'E', n: 'Banque E', r: 'A', c: 2.75, line: 64, exp: '17:00' }, { id: 'A', n: 'Banque A', r: 'AA', c: 2.70, line: 52, exp: '17:15' }, { id: 'D', n: 'Banque D', r: 'A−', c: 2.65, line: 48, exp: '16:45' }];
  function Rfq({ ctx }) {
    const r = ctx.res;
    const [limit, setLimit] = useState(90);
    const [sel, setSel] = useState(null);
    const q = QUOTES.map((x) => ({ ...x, px: r.A + x.c * r.B, ok: x.line <= limit }));
    const best = q.find((x) => x.ok), cur = q.find((x) => x.id === sel) || best || q[0], topC = q[0].c;
    const items = q.map((x) => ({ id: x.id, x: x.line, y: x.c, c: x.ok ? '' : 'off', tag: x.n, title: x.n + ' · ' + x.r, rows: [['Coupon', fr(x.c) + ' %'], ['Valeur', fr(x.px) + ' %'], ['Ligne après', x.line + ' %']] }));
    return html`<${React.Fragment}>
      <${Ticket} back="pricer" title="RFQ-0187 · Phoenix mémoire worst-of 3 ans" sub="Coupon à résoudre à prix 100 % · tour 1 · desk pilote Paris" metrics=${[['Nominal', '5 000 000 €'], ['Cotations', '5 / 5'], ['Expire', '16:40']]}>
        <button className="b" type="button">Relancer un tour</button><button className="b p" type="button">Nouvelle RFQ</button>
      <//>
      <div className="work w3">
        <aside className="pane" aria-label="Demandes">
          <${Tabs} cur="d" set=${() => {}} items=${[['d', 'Demandes'], ['r', 'Reçues'], ['a', 'Analyse']]}/>
          <div className="pbody">
            <div className="li on"><b>RFQ-0187 Phoenix WO</b><em>5,0 M€</em><small>5 / 5 cotations</small><small>À décider</small></div>
            <div className="li"><b>RFQ-0186 Athena 5 ans</b><em>12,0 M€</em><small>3 / 4 cotations</small><small>En attente</small></div>
            <div className="li"><b>RFQ-0184 Capital garanti</b><em>8,0 M€</em><small>4 / 4 cotations</small><small>Confirmée</small></div>
            <div className="sh h">Journal</div>
            <pre className="log">14:02 Termes figés, v3${'\n'}14:05 Envoi à 5 émetteurs${'\n'}14:31 Cotation Banque A${'\n'}15:12 Banque E révise à 2,75 %${'\n'}15:26 Cotation Banque C</pre>
          </div>
        </aside>
        <section className="pane" aria-label="Comparatif"><div className="pbody"><div className="pad fillcol">
          <div className="dates"><div><span>Strike</span><b>${E.fd(E.STRIKE)}</b></div><div><span>Valeur</span><b>${E.fd(E.VALUE)}</b></div><div><span>Maturité</span><b>${E.fd(E.OBS[11])}</b></div><div><span>Paiement J+3</span><b>${E.fd(E.PAY[11])}</b></div></div>
          <${Card} cls="grow" title="Coupon contre consommation de ligne" sub="glissez la limite interne · cliquez un émetteur">
            <${Scatter} items=${items} sel=${cur.id} onSel=${setSel} limit=${limit} onLimit=${setLimit} xd=${[40, 100]} yd=${[2.6, 2.9]} xt=${[40, 50, 60, 70, 80, 90, 100]} yt=${[2.6, 2.7, 2.8, 2.9]} xFmt=${(v) => v + ' %'} yFmt=${(v) => fr(v, 1)} label="Coupon proposé selon la ligne de crédit après opération"/>
          <//>
          <div className="card tbox"><table className="t"><thead><tr><th>Émetteur</th><th>Note</th><th className="r">Coupon / trim.</th><th className="r">p.a.</th><th className="r">Valeur</th><th className="r">Marge impl.</th><th className="r">Ligne après</th><th className="r">Validité</th><th>Contrôle</th></tr></thead>
            <tbody>${q.map((x) => html`<tr key=${x.id} className=${'row' + (x.id === cur.id ? ' sel' : '')} onClick=${() => setSel(x.id)}><td><button type="button" className="rowb" style=${{ fontFamily: 'var(--sans)' }}>${x.n}</button></td><td>${x.r}</td><td className="r">${fr(x.c)} %</td><td className="r">${fr(x.c * 4)} %</td><td className="r">${fr(x.px)}</td><td className="r">${fr(100 - x.px)}</td><td className=${'r ' + (x.ok ? '' : 'neg')}>${x.line} %</td><td className="r">${x.exp}</td><td><${Status} s=${x.ok ? ['ok', 'Admissible'] : ['ko', 'Hors limite']}/></td></tr>`)}</tbody>
          </table></div>
        </div></div></section>
        <aside className="pane insp" aria-label="Décision">
          <div className="sh h" style=${{ minHeight: 33 }}>Décision <span>${cur.n}</span></div>
          <div className="pbody"><div className="pad">
            <div className="hero" style=${{ gridTemplateColumns: 'minmax(0,1fr)' }}><div className="hero-p" style=${{ borderRight: 0 }}><small>Coupon retenu, par trimestre</small><b>${fr(cur.c)} %</b><small>Soit ${fr(cur.c * 4)} % par an · ${cur.r}</small></div></div>
            <div className="card"><table className="t"><tbody><tr><td>Écart au meilleur coupon</td><td className="r">${cur.c === topC ? '—' : sg(cur.c - topC) + ' pt'}</td></tr><tr><td>Valeur Structura</td><td className="r">${fr(cur.px)} %</td></tr><tr><td>Marge implicite</td><td className="r">${fr((100 - cur.px) * 5e4, 0)} €</td></tr><tr><td>Ligne après opération</td><td className="r">${cur.line} %</td></tr></tbody></table></div>
            <span className=${'st ' + (cur.ok ? 'ok' : 'ko')}>${cur.ok ? 'Ligne de crédit disponible' : 'Au-delà de la limite interne'}</span>
            <button className="b p" type="button">${cur.ok ? 'Demander la confirmation' : 'Demander une exception'}</button>
            <div className="note">Le booking n'est créé qu'après confirmation de l'émetteur.</div>
          </div></div>
        </aside>
      </div>
    <//>`;
  }

  // ---------- Risk ----------
  const SX = ['−20 %', '−10 %', '−5 %', '0 %', '+5 %', '+10 %'], SXV = [-20, -10, -5, 0, 5, 10], SY = ['−5 pts', '0 pt', '+5 pts', '+10 pts'];
  const SZ = [[-3980, -1360, -370, 420, 980, 1330], [-4500, -1830, -810, 0, 600, 990], [-5040, -2310, -1250, -410, 230, 660], [-5560, -2770, -1670, -790, -120, 340]];
  const ISS = [['Banque A', 'AA', 52.2, 110], ['Banque B', 'A+', 44.7, 70], ['Banque C', 'AA−', 39.1, 46], ['Banque D', 'A−', 28, 69], ['Banque E', 'A', 22.4, 43]];
  const VAR = [['−500', 1], ['−400', 3], ['−300', 11], ['−200', 33], ['−100', 68], ['0', 74], ['+100', 40], ['+200', 16], ['+300', 5], ['+400', 1]];
  function Risk({ ctx }) {
    const [view, setView] = useState('shock');
    const [cell, setCell] = useState({ r: 1, c: 2 });
    return html`<${React.Fragment}>
      <${Ticket} back="booking" title="Risk Management" sub="Calculs en Production · 38 deals sur 38 valorisés" metrics=${[['Date des Greeks', '20/11/2026'], ['Encours', '186,4 M€'], ['MtM', '178,9 M€']]}>
        <button className="b" type="button">Exporter</button><button className="b p" type="button">Recalculer</button>
      <//>
      <div className="work w3">
        <aside className="pane" aria-label="Portefeuilles">
          <div className="sh c" style=${{ minHeight: 33 }}>Portefeuille actif <span>5</span></div>
          <div className="pbody">${[['Tous portefeuilles', '186,4', '38 deals'], ['Autocalls & Phoenix', '98,2', '19 deals'], ['Reverse convertibles', '31,5', '7 deals'], ['Capital protégé', '34,3', '7 deals'], ['Participation', '22,4', '5 deals']].map(([a, b, c], i) => html`<div key=${a} className=${'li' + (i ? '' : ' on')}><b>${a}</b><em>${b}</em><small>${c}</small><small>M€</small></div>`)}</div>
        </aside>
        <section className="pane" aria-label="Analyse">
          <${Tabs} cur=${view} set=${setView} items=${[['pf', 'Portefeuille'], ['greeks', 'Greeks'], ['cp', 'Contreparties'], ['shock', 'Chocs'], ['smile', 'Smile'], ['var', 'VaR'], ['pnl', 'P&L'], ['bar', 'Barrières']]}/>
          <div className="pbody"><div className="pad fillcol">
            <div className="solo"><div className="hs c5"><${Metric} l="Delta, +1 %" v="+141 k€"/><${Metric} l="Gamma, (1 %)²" v="−8,4 k€"/><${Metric} l="Véga, +1 pt" v="−82 k€"/><${Metric} l="VaR 99 %, 1 jour" v="382 k€"/><${Metric} l="P&L du jour" v="+42,3 k€" cl="lm"/></div></div>
            ${view === 'shock' ? html`<${React.Fragment}>
              <${Card} cls="grow" title="P&L sous choc spot × volatilité" sub="k€, full reprice · cliquez une case"><${ShockMatrix} xs=${SX} ys=${SY} z=${SZ} sel=${cell} onSel=${setCell}/><//>
              <${Card} cls="grow" title=${'Coupe à volatilité ' + SY[cell.r]} sub=${'P&L selon le spot · sélection ' + SX[cell.c] + ' : ' + sg(SZ[cell.r][cell.c], 0) + ' k€'}><${CrossSection} xv=${SXV} y=${SZ[cell.r]} label=${SY[cell.r]} mark=${cell.c}/><//>
            <//>` : null}
            ${view === 'var' ? html`<${React.Fragment}><${Card} cls="grow" title="Distribution du P&L à 1 jour" sub="252 scénarios historiques, bornes basses en k€"><${VBars} items=${VAR.map(([l, v], i) => ({ l, v, c: i < 2 ? 'loss' : '', t: 'De ' + l + ' k€', n: 'Scénarios' }))} unit="" dp=${0} label="Histogramme du P&L à un jour"/><//><div className="card"><table className="t"><tbody><tr><td>VaR 99 %, 1 jour</td><td className="r">382 k€</td></tr><tr><td>VaR 95 %, 1 jour</td><td className="r">214 k€</td></tr><tr><td>Expected shortfall 97,5 %</td><td className="r">401 k€</td></tr></tbody></table></div><//>` : null}
            ${view === 'pnl' ? html`<${Card} cls="grow" title="Explication du P&L" sub="19/11 → 20/11, k€"><${Waterfall} h=${330} dp=${1} domain=${[0, 76]} label="Explication du P&L" items=${[{ l: 'Ouverture', v: 0, total: true }, { l: 'Spot', v: 61.4 }, { l: 'Vol', v: -12.8 }, { l: 'Temps', v: 8.6 }, { l: 'Taux', v: -3.2 }, { l: 'Funding', v: -4.9 }, { l: 'Résidu', v: -6.8 }, { l: 'Total', v: 42.3, total: true }]}/><//>` : null}
            ${view === 'cp' ? html`<div className="card tbox"><div className="card-h"><b>Exposition par contrepartie</b><span>encours et limite, M€</span></div><table className="t"><thead><tr><th>Émetteur</th><th>Note</th><th className="r">Encours</th><th className="r">Limite</th><th>Utilisation</th><th className="r">%</th></tr></thead><tbody>${ISS.map((x) => { const u = x[2] / x[3] * 100; return html`<tr key=${x[0]}><td>${x[0]}</td><td>${x[1]}</td><td className="r">${fr(x[2], 1)}</td><td className="r">${x[3]}</td><td><svg width="150" height="10" aria-hidden="true"><rect width="150" height="8" y="1" style=${{ fill: 'var(--hair)' }}/><rect width=${u * 1.5} height="8" y="1" style=${{ fill: u > 80 ? 'var(--s2)' : 'var(--bar)' }}/></svg></td><td className=${'r ' + (u > 80 ? 'neg' : '')}>${fr(u, 0)} %</td></tr>`; })}</tbody></table></div>` : null}
            ${view === 'greeks' ? html`<div className="card tbox"><div className="card-h"><b>Greeks par sous-jacent</b><span>k€, bump-and-reprice CRN</span></div><table className="t"><thead><tr><th>Sous-jacent</th><th className="r">Delta / +1 %</th><th className="r">Gamma / (1 %)²</th><th className="r">Véga / +1 pt</th><th className="r">Barrière proche</th></tr></thead><tbody><tr><td>Euro Stoxx 50</td><td className="r pos">+62</td><td className="r neg">−3,4</td><td className="r neg">−30</td><td className="r">+11,2 pts</td></tr><tr><td>Euro Stoxx Banks</td><td className="r pos">+48</td><td className="r neg">−3,2</td><td className="r neg">−35</td><td className="r">+4,6 pts</td></tr><tr><td>CAC 40</td><td className="r pos">+31</td><td className="r neg">−1,8</td><td className="r neg">−17</td><td className="r">+3,1 pts</td></tr><tr className="sum"><td>Book</td><td className="r pos">+141</td><td className="r neg">−8,4</td><td className="r neg">−82</td><td className="r">+3,1 pts</td></tr></tbody></table></div>` : null}
            ${view === 'smile' ? html`<div className="card tbox"><div className="card-h"><b>Chocs de smile</b><span>k€, surface indicative</span></div><table className="t"><thead><tr><th>Scénario</th><th className="r">SX5E</th><th className="r">SX7E</th><th className="r">CAC</th><th className="r">Book</th></tr></thead><tbody><tr><td>Skew +2 pts</td><td className="r neg">−44</td><td className="r neg">−58</td><td className="r neg">−26</td><td className="r neg">−128</td></tr><tr><td>Skew −2 pts</td><td className="r pos">+41</td><td className="r pos">+53</td><td className="r pos">+24</td><td className="r pos">+118</td></tr><tr><td>Convexité +1 pt</td><td className="r neg">−12</td><td className="r neg">−19</td><td className="r neg">−8</td><td className="r neg">−39</td></tr><tr><td>Niveau ATM +2 pts</td><td className="r neg">−60</td><td className="r neg">−70</td><td className="r neg">−34</td><td className="r neg">−164</td></tr></tbody></table></div>` : null}
            ${view === 'pf' || view === 'bar' ? html`<div className="card tbox"><div className="card-h"><b>${view === 'pf' ? 'Composition' : 'Barrières du portefeuille'}</b><span>principales lignes</span></div><table className="t"><thead><tr><th>Réf.</th><th>Produit</th><th>Contrepartie</th><th className="r">Nominal</th><th>Position / seuil</th><th className="r">Distance</th><th className="r">MtM %</th></tr></thead><tbody>${DEALS.filter((x) => view === 'pf' || x.bar !== null).slice().sort((a, b) => (a.dist === null ? 999 : a.dist) - (b.dist === null ? 999 : b.dist)).map((x) => html`<tr key=${x.id} className="row" onClick=${() => { ctx.setDeal(x.id); location.hash = 'booking'; }}><td><button type="button" className="rowb">${x.id}</button></td><td>${x.prod}</td><td>${x.cp}</td><td className="r">${fr(x.nom, 1)} M</td><td><${Gauge} d=${x}/></td><td className="r">${x.dist === null ? '—' : sg(x.dist, 1)}</td><td className="r">${fr(x.mtm)}</td></tr>`)}</tbody></table></div>` : null}
          </div></div>
        </section>
        <aside className="pane insp" aria-label="Limites">
          <div className="sh h" style=${{ minHeight: 33 }}>Limites du book <span>4 suivies</span></div>
          <div className="pbody">
            ${[['VaR 500 k€', 76], ['Véga 120 k€', 68], ['Delta 250 k€', 56], ['Émetteur 30 %', 93]].map(([l, v]) => html`<div key=${l} className="chk"><span style=${{ display: 'flex', justifyContent: 'space-between' }}><span>${l}</span><b className="mono" style=${{ fontWeight: 500 }}>${v} %</b></span><svg width="100%" height="8" aria-hidden="true"><rect width="100%" height="6" y="1" style=${{ fill: 'var(--hair)' }}/><rect width=${v + '%'} height="6" y="1" style=${{ fill: v > 85 ? 'var(--s2)' : 'var(--bar)' }}/></svg></div>`)}
            <div className="sh m">Couverture du calcul</div>
            <div className="chk"><span className="st ok">Greeks 38 / 38</span><small>Calculés à 17:40</small></div>
            <div className="chk"><span className="st ok">Chocs 38 / 38</span><small>Full reprice à 17:42</small></div>
            <div className="chk"><span className="st wa">Smile indicatif</span><small>Aucune cotation d'options</small></div>
            <div className="chk"><span className="st ko">Banque C à 85 %</span><small>Bloque une partie des RFQ</small></div>
          </div>
        </aside>
      </div>
    <//>`;
  }

  // ---------- Clients ----------
  const CL = {
    alpha: { n: 'Family Office Alpha', k: 'Family office', city: 'Paris', cy: 'active', aum: '24,6 M€', dn: 7, last: '18/11/26', ki: 60, dur: 5, und: 'Indices, actions UE', ccy: 'EUR, CHF', rat: 'A', tkt: '1 à 5 M€', ev: [[1, 'Réunion'], [3, 'Idée'], [4, 'Deal'], [6, 'Appel'], [7, 'Réunion'], [9, 'Appel'], [10, 'Idée'], [11, 'Réunion'], [11.6, 'Appel']], due: [['ko', 'Envoyer la note D-2398', 'Due le 24/11'], ['wa', 'Rappeler sur le Phoenix WO', 'Due aujourd\'hui']], sig: [['wa', 'Plus-value latente', 'D-2305 à 110,25 : arbitrage possible'], ['nf', 'Concentration SX7E', '41 % de l\'encours']], who: 'Directeur des investissements' },
    beta: { n: 'Banque Privée Beta', k: 'Banque privée', city: 'Genève', cy: 'active', aum: '41,2 M€', dn: 9, last: '19/11/26', ki: 50, dur: 7, und: 'Indices mondiaux', ccy: 'EUR, USD, CHF', rat: 'A+', tkt: '2 à 10 M€', ev: [[0.5, 'Appel'], [2, 'Deal'], [3, 'Réunion'], [4.2, 'Email'], [5.5, 'Deal'], [7, 'Appel'], [8.5, 'Réunion'], [10, 'Email'], [10.8, 'Appel'], [11.7, 'Email']], due: [['wa', 'Réinvestissement D-2364', 'Si rappel le 23/11']], sig: [['nf', 'Rappel probable', 'D-2364, 8,0 M€ à replacer']], who: 'Responsable produits structurés' },
    gamma: { n: 'CGP Gamma', k: 'Conseil en gestion', city: 'Lyon', cy: 'à relancer', aum: '12,8 M€', dn: 6, last: '02/11/26', ki: 65, dur: 4, und: 'Indices européens', ccy: 'EUR', rat: 'A', tkt: '0,5 à 3 M€', ev: [[1, 'Réunion'], [4, 'Deal'], [6, 'Email'], [9, 'Réunion'], [10.5, 'Email'], [11, 'Appel']], due: [['ko', 'Alerter sur D-2382', 'À 3,1 pts de la protection'], ['wa', 'Reprendre contact', 'En retard de 6 jours']], sig: [['ko', 'Barrière proche', 'D-2382, CAC 40'], ['wa', 'Rupture de cadence', '20 jours sans contact']], who: 'Associé gérant' },
    delta: { n: 'Assurance Delta', k: 'Assureur', city: 'Luxembourg', cy: 'active', aum: '33,5 M€', dn: 4, last: '13/11/26', ki: 70, dur: 8, und: 'Indices, paniers', ccy: 'EUR', rat: 'AA−', tkt: '3 à 15 M€', ev: [[2, 'Réunion'], [5, 'Deal'], [8, 'Email'], [10, 'Email'], [11.4, 'Réunion']], due: [], sig: [['wa', 'Barrière à surveiller', 'D-2329, 4,6 pts']], who: 'Directrice financière' }
  };
  function Clients({ ctx }) {
    const [sel, setSel] = useState('alpha');
    const c = CL[sel], pos = DEALS.filter((x) => x.client === sel);
    const types = ['Deal', 'Réunion', 'Appel', 'Email', 'Idée'];
    const stages = ['Détectée', 'Qualifiée', 'Proposée', 'Négociation', 'Gagnée'];
    const pipe = { alpha: [1, 2, 1, 1, 2], beta: [2, 1, 2, 0, 3], gamma: [1, 0, 1, 0, 1], delta: [0, 1, 0, 1, 2] }[sel];
    return html`<${React.Fragment}>
      <${Ticket} back="accueil" title=${c.n} sub=${c.k + ' · ' + c.city + ' · relation ' + c.cy} metrics=${[['Encours structuré', c.aum], ['Deals', String(c.dn)], ['Dernier contact', c.last]]}>
        <button className="b" type="button">Noter une interaction</button><a className="b p" href="#structuring">Proposer un produit</a>
      <//>
      <div className="work w3">
        <aside className="pane" aria-label="Clients">
          <div className="sh c" style=${{ minHeight: 33 }}>Sociétés <span>24</span></div>
          <div className="pbody">${Object.keys(CL).map((k) => html`<button key=${k} type="button" className=${'li' + (k === sel ? ' on' : '')} onClick=${() => setSel(k)}><b>${CL[k].n}</b><em>${CL[k].aum}</em><small>${CL[k].k}</small><small>${CL[k].cy}</small></button>`)}</div>
        </aside>
        <section className="pane" aria-label="Fiche client"><div className="pbody"><div className="pad fillcol">
          <${Card} title="Rythme de la relation" sub="12 derniers mois, par type d'échange">
            <${g.UI.Plot} h=${150} label="Chronologie des échanges avec le client" draw=${(w, H) => { const l = 62, x = (v) => l + v / 12 * (w - l - 8), rh = (H - 18) / types.length; return html`<g>${types.map((t, r) => html`<g key=${t}><line className="gl" x1=${l} x2=${w - 8} y1=${rh * (r + 0.5)} y2=${rh * (r + 0.5)}/><text className="tx" x="0" y=${rh * (r + 0.5) + 3.5}>${t}</text></g>`)}${c.ev.map(([m, t], i) => html`<circle key=${i} className=${'dot ' + (t === 'Deal' ? 'sel' : '')} cx=${x(m)} cy=${rh * (types.indexOf(t) + 0.5)} r=${t === 'Deal' ? 6 : 4.5}><title>${t}</title></circle>`)}${['déc.', 'févr.', 'avr.', 'juin', 'août', 'oct.'].map((m, i) => html`<text key=${m} className="tx tm" x=${x(i * 2 + 0.5)} y=${H - 3}>${m}</text>`)}</g>`; }}/>
          <//>
          <div className="two">
            <div className="card tbox"><div className="card-h"><b>Positions vivantes</b><span>${c.dn} deals, principales lignes</span></div><table className="t"><tbody>${pos.map((x) => html`<tr key=${x.id} className="row" onClick=${() => { ctx.setDeal(x.id); location.hash = 'booking'; }}><td><button type="button" className="rowb">${x.id}</button></td><td>${x.prod}</td><td><${Spark} v=${x.s} bar=${x.bar} w=${64}/></td><td className="r">${fr(x.mtm)}</td></tr>`)}</tbody></table></div>
            <div className="card" style=${{ background: 'var(--k-c)' }}><div className="card-h"><b>Contraintes du mandat</b><span>contre le produit en cours</span></div><div className="card-b"><table className="t" style=${{ background: 'var(--card)' }}><tbody>
              <tr><td>Protection minimale</td><td className="r">${c.ki} %</td><td><${Status} s=${ctx.terms.ki <= c.ki ? ['ok', 'Conforme'] : ['ko', 'KI ' + ctx.terms.ki + ' %']}/></td></tr>
              <tr><td>Durée maximale</td><td className="r">${c.dur} ans</td><td><${Status} s=${c.dur >= 3 ? ['ok', 'Conforme'] : ['ko', 'Trop long']}/></td></tr>
              <tr><td>Sous-jacents</td><td className="r">${c.und}</td><td></td></tr><tr><td>Devises</td><td className="r">${c.ccy}</td><td></td></tr><tr><td>Note minimale</td><td className="r">${c.rat}</td><td></td></tr><tr><td>Ticket</td><td className="r">${c.tkt}</td><td></td></tr>
            </tbody></table></div></div>
          </div>
          <${Card} cls="grow" title="Pipeline d'opportunités" sub="nombre d'opportunités par étape">
            <${VBars} key=${sel} items=${stages.map((l, i) => ({ l, v: pipe[i], c: l === 'Gagnée' ? 'up' : l === 'Proposée' ? 'mid' : '', n: 'Opportunités' }))} unit="" dp=${0} label="Pipeline d'opportunités du client"/>
          <//>
        </div></div></section>
        <aside className="pane insp" aria-label="Relances">
          <div className="sh h" style=${{ minHeight: 33 }}>Relances dues <span>${c.due.length}</span></div>
          <div className="pbody">
            ${c.due.length ? c.due.map((u) => html`<div key=${u[1]} className="chk"><span className=${'st ' + u[0]}>${u[1]}</span><small>${u[2]}</small></div>`) : html`<div className="chk"><span className="st ok">Aucune relance due</span></div>`}
            <div className="sh m">Signaux</div>
            ${c.sig.map((u) => html`<div key=${u[1]} className="chk"><span className=${'st ' + u[0]}>${u[1]}</span><small>${u[2]}</small></div>`)}
            <div className="sh c">Contact principal</div><div className="chk"><b>${c.who}</b></div>
          </div>
        </aside>
      </div>
    <//>`;
  }

  // ---------- Études ----------
  const FUND = (() => {
    const n = 737, zm = E.gaussians(n, 77), ze = E.gaussians(n, 78), ib = E.gaussians(n, 79), a = [100], b = [100], dates = [];
    let t = E.D(2024, 1, 2);
    for (let i = 0; i < n; i++) { dates.push(t); t = E.addBD(t, 1); if (i) { a.push(a[i - 1] * Math.exp(0.0086 * zm[i] + 0.0034 * ze[i])); b.push(b[i - 1] * Math.exp(0.0086 * zm[i] + 0.0012 * ib[i])); } }
    const fix = (s, end) => { const k = Math.log(end / s[n - 1]) / (n - 1); return s.map((v, i) => v * Math.exp(k * i)); };
    return { a: fix(a, 118.4), b: fix(b, 114.1), dates, n };
  })();
  function stats(s, i0, i1) { let peak = s[i0], dd = 0, sum = 0, sq = 0; for (let i = i0 + 1; i <= i1; i++) { const r = Math.log(s[i] / s[i - 1]); sum += r; sq += r * r; peak = Math.max(peak, s[i]); dd = Math.min(dd, s[i] / peak - 1); } const m = i1 - i0; return { perf: 100 * (s[i1] / s[i0] - 1), vol: 100 * Math.sqrt(252 * Math.max(sq / m - (sum / m) * (sum / m), 0)), dd: 100 * dd }; }
  function Etudes() {
    const [win, setWin] = useState([0, FUND.n - 1]);
    const [view, setView] = useState('perf');
    const f = stats(FUND.a, win[0], win[1]), b = stats(FUND.b, win[0], win[1]);
    const preset = (d) => setWin(d === 0 ? [0, FUND.n - 1] : [Math.max(0, FUND.n - 1 - d), FUND.n - 1]);
    return html`<${React.Fragment}>
      <${Ticket} back="accueil" title="AMC Exemple Actions Europe" sub="Étude complète · reconstruction FIFO, régression, blocs B, C et D" metrics=${[['Devise', 'EUR'], ['Période', E.fd(FUND.dates[win[0]]) + ' → ' + E.fd(FUND.dates[win[1]])], ['Confiance', '84 %']]}>
        <button className="b" type="button">Configuration</button><button className="b p" type="button">Rapport PDF</button>
      <//>
      <div className="work w3">
        <aside className="pane" aria-label="Études">
          <div className="sh c" style=${{ minHeight: 33 }}>Études AMC <span>4</span></div>
          <div className="pbody">
            ${[['AMC Exemple Actions Europe', '84 %', 'EUR · 24 positions', '18/11'], ['AMC Exemple Financières', '79 %', 'CHF · 20 positions', '04/11'], ['AMC Exemple Infrastructures', '88 %', 'USD · 31 positions', '21/10'], ['AMC Exemple Santé', '—', 'Données à compléter', 'brouillon']].map(([a, b2, c, e], i) => html`<div key=${a} className=${'li' + (i ? '' : ' on')}><b>${a}</b><em>${b2}</em><small>${c}</small><small>${e}</small></div>`)}
            <div className="sh h">Données de l'étude</div>
            <div className="chk"><span className="st ok">Historique des NAV</span><small>${FUND.n} observations</small></div><div className="chk"><span className="st ok">Carnets de transactions</span><small>612 ordres</small></div><div className="chk"><span className="st wa">Dividendes</span><small>3 événements à confirmer</small></div>
          </div>
        </aside>
        <section className="pane" aria-label="Résultats">
          <${Tabs} cur=${view} set=${setView} items=${[['perf', 'Performance'], ['ff', 'Fama-French'], ['attr', 'Attribution'], ['trade', 'Trading & comportement']]}/>
          <div className="pbody"><div className="pad fillcol">
            <div className="solo"><div className="hs c5"><${Metric} l="Performance" v=${sg(f.perf, 1) + ' %'} cl="lm"/><${Metric} l="Indice" v=${sg(b.perf, 1) + ' %'}/><${Metric} l="Écart" v=${sg(f.perf - b.perf, 1) + ' pts'}/><${Metric} l="Volatilité" v=${fr(f.vol, 1) + ' %'}/><${Metric} l="Drawdown max." v=${sg(f.dd, 1) + ' %'}/></div></div>
            ${view === 'perf' ? html`<section className="card grow"><div className="card-h"><b>Performance rebasée sur la période</b><span className="lg"><span><i style=${{ background: 'var(--s1)' }}></i>Fonds</span><span><i style=${{ background: 'var(--s2)' }}></i>Indice</span></span></div>
              <div className="filters" style=${{ borderBottom: 0, padding: '2px 10px 4px' }}>${[['Max', 0], ['2 ans', 504], ['1 an', 252], ['6 mois', 126], ['3 mois', 63]].map(([l, d]) => { const on = (d === 0 && win[0] === 0 && win[1] === FUND.n - 1) || (d > 0 && win[1] === FUND.n - 1 && win[0] === FUND.n - 1 - d); return html`<button key=${l} type="button" aria-pressed=${on} className=${'fc' + (on ? ' on' : '')} onClick=${() => preset(d)}>${l}</button>`; })}<span className="note" style=${{ marginLeft: 'auto' }}>Glissez la fenêtre sous le graphique : les statistiques suivent</span></div>
              <div className="card-b"><${BrushChart} a=${FUND.a} b=${FUND.b} dates=${FUND.dates} win=${win} onWin=${setWin}/></div></section>` : null}
            ${view === 'ff' ? html`<div className="card tbox"><div className="card-h"><b>Régression Fama-French, 5 facteurs</b><span>OLS quotidien</span></div><table className="t"><thead><tr><th>Facteur</th><th className="r">Bêta</th><th className="r">t-stat</th><th>IC 95 %</th><th>Signif.</th></tr></thead><tbody>${[['Marché (Mkt-RF)', 0.94, 41.2, 0.90, 0.98, '***'], ['Taille (SMB)', 0.12, 3.1, 0.04, 0.20, '**'], ['Valeur (HML)', -0.08, -2.2, -0.15, -0.01, '*'], ['Rentabilité (RMW)', 0.05, 1.1, -0.04, 0.14, 'n.s.'], ['Investissement (CMA)', 0.03, 0.6, -0.07, 0.13, 'n.s.']].map((x) => { const X = (v) => 80 + v * 74; return html`<tr key=${x[0]}><td>${x[0]}</td><td className="r">${fr(x[1])}</td><td className="r">${fr(x[2], 1)}</td><td><svg width="170" height="16" aria-hidden="true"><line x1="80" x2="80" y1="0" y2="16" className="rf"/><line x1=${X(x[3])} x2=${X(x[4])} y1="8" y2="8" style=${{ stroke: 'var(--s1)', strokeWidth: 2 }}/><circle cx=${X(x[1])} cy="8" r="3.5" style=${{ fill: 'var(--s1)' }}/></svg></td><td className="mono">${x[5]}</td></tr>`; })}<tr className="sum"><td>Alpha annualisé</td><td className="r">+3,10 %</td><td className="r">2,1</td><td></td><td className="mono">*</td></tr></tbody></table></div>` : null}
            ${view === 'attr' ? html`<${Card} cls="grow" title="Décomposition de la performance" sub="points"><${Waterfall} h=${300} dp=${1} label="Décomposition de la performance" items=${[{ l: 'Industrie', v: 6.8 }, { l: 'Financières', v: 5.2 }, { l: 'Technologie', v: 3.8 }, { l: 'Santé', v: 2.4 }, { l: 'Autres', v: 3.4 }, { l: 'Change', v: -1.4 }, { l: 'Frais', v: -1.8 }, { l: 'Net', v: 18.4, total: true }]}/><//>` : null}
            ${view === 'trade' ? html`<div className="two"><div className="card"><div className="card-h"><b>Trading</b><span>reconstruction FIFO</span></div><table className="t"><tbody><tr><td>Ordres exécutés</td><td className="r">612</td></tr><tr><td>Allers-retours clôturés</td><td className="r">388</td></tr><tr><td>Taux de réussite</td><td className="r">54,2 %</td></tr><tr><td>Profit factor</td><td className="r">1,24</td></tr><tr><td>Rotation annualisée</td><td className="r">410 %</td></tr></tbody></table></div><div className="card"><div className="card-h"><b>Comportement</b><span>discipline du gérant</span></div><table className="t"><tbody><tr><td>Détention moyenne</td><td className="r">62 jours</td></tr><tr><td>Détention des gagnants</td><td className="r">74 jours</td></tr><tr><td>Détention des perdants</td><td className="r">48 jours</td></tr><tr><td>Positions de conviction</td><td className="r">8</td></tr><tr><td>Effet de disposition</td><td className="r">Faible</td></tr></tbody></table></div></div>` : null}
          </div></div>
        </section>
        <aside className="pane insp" aria-label="Réconciliation">
          <div className="sh h" style=${{ minHeight: 33 }}>Réconciliation <span>à l'arrêté</span></div>
          <div className="pbody">
            <div className="chk"><span className="st ok">NAV contre FIFO</span><small>Écart 0,02 %</small></div><div className="chk"><span className="st ok">Composition</span><small>24 lignes sur 24 rapprochées</small></div><div className="chk"><span className="st ok">Cours d'exécution</span><small>Hors dividendes</small></div><div className="chk"><span className="st wa">Change</span><small>11 ordres au taux de clôture</small></div>
            <div className="sh c">Confiance</div>
            ${[['NAV', 98], ['Carnet d\'ordres', 92], ['Change', 86], ['Régression', 81], ['Attribution', 78], ['Comportement', 72]].map(([l, v]) => html`<div key=${l} className="chk"><span style=${{ display: 'flex', justifyContent: 'space-between' }}><span>${l}</span><b className="mono" style=${{ fontWeight: 500 }}>${v} %</b></span><svg width="100%" height="7" aria-hidden="true"><rect width="100%" height="5" y="1" style=${{ fill: 'var(--hair)' }}/><rect width=${v + '%'} height="5" y="1" style=${{ fill: 'var(--bar)' }}/></svg></div>`)}
          </div>
        </aside>
      </div>
    <//>`;
  }

  // ---------- Shell ----------
  function useJob(terms, market) {
    const [st, set] = useState({ phase: 'idle', pts: [], prog: 0, log: [], res: null, sig: '' });
    const stop = useRef(null), seq = useRef(4182);
    const sig = JSON.stringify([terms, market]);
    const run = useCallback(() => {
      if (stop.current) stop.current();
      const id = 'job-' + (++seq.current), s = JSON.stringify([terms, market]);
      set({ phase: 'queued', pts: [], prog: 0, res: null, sig: s, log: [['POST /api/price/jobs', '202'], ['GET /jobs/' + id + '/events', 'SSE']] });
      stop.current = E.batchJob(terms, market, 5000, 100000, (pts, prog) => {
        const l = pts[pts.length - 1];
        set((o) => ({ ...o, phase: 'running', pts, prog, log: [...o.log.slice(0, 2), ['progress n=' + (l.n / 1000) + 'k', fr(l.px, 3)]] }));
      }, (res) => set((o) => ({ ...o, phase: 'done', res, log: [...o.log.slice(0, 2), ['event: result', 'px=' + fr(res.px, 3)], ['event: close', '200']] })));
    }, [terms, market]);
    const cancel = useCallback(() => { if (stop.current) stop.current(); set((o) => ({ ...o, phase: 'cancelled', log: [...o.log.slice(0, 3), ['DELETE /api/price/jobs/{id}', '204']] })); }, []);
    useEffect(() => { run(); return () => { if (stop.current) stop.current(); }; }, []);
    return { ...st, run, cancel, stale: st.sig !== sig };
  }

  function App() {
    const read = () => { const h = location.hash.slice(1); return NAV.some((n) => n[0] === h) ? h : 'pricer'; };
    const [route, setRoute] = useState(read);
    const [terms, setTerms] = useState(E.TERMS), [market, setMarket] = useState(E.MARKET), [deal, setDeal] = useState('D-2398');
    const [theme, setTheme] = useState(() => document.documentElement.getAttribute('data-theme') || 'light');
    const Z = useMemo(() => E.gaussians(NH * E.NO * E.NU, 42), []);
    const W = useMemo(() => E.simulate(market, Z, NH), [market, Z]);
    const res = useMemo(() => E.value(W, terms, market), [W, terms, market]);
    const job = useJob(terms, market);
    useEffect(() => { const f = () => setRoute(read()); addEventListener('hashchange', f); return () => removeEventListener('hashchange', f); }, []);
    const [palette, setPalette] = useState(() => document.documentElement.getAttribute('data-palette') || 'nuit');
    useEffect(() => { document.documentElement.setAttribute('data-theme', theme); }, [theme]);
    useEffect(() => { document.documentElement.setAttribute('data-palette', palette); try { localStorage.setItem('structura-palette', palette); } catch (e) { /* preference only */ } }, [palette]);
    useEffect(() => { const f = (e) => { if (e.key === 'F9') { e.preventDefault(); job.run(); } }; addEventListener('keydown', f); return () => removeEventListener('keydown', f); }, [job.run]);
    const px = job.phase === 'done' && !job.stale ? job.res.px : res.px;
    const ctx = { terms, setTerms, market, setMarket, W, Z, res, px, job, deal, setDeal };
    const S = { accueil: Accueil, structuring: Structuring, clients: Clients, pricer: Pricer, booking: Booking, risk: Risk, rfq: Rfq, etudes: Etudes }[route];
    const docs = [['accueil', 'Desk du jour', ''], ['pricer', 'Phoenix WO 3A', fr(px)], ['booking', 'Book principal', '38'], ['rfq', 'RFQ-0187', '5/5'], ['risk', 'Risque du book', '']];
    return html`<div className="x">
      <svg width="0" height="0" aria-hidden="true" style=${{ position: 'absolute' }}><defs><linearGradient id="soft-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" className="gs0"/><stop offset="1" className="gs1"/></linearGradient></defs></svg>
      <header className="cmd">
        <a className="logo" href="#accueil" aria-label="Structura, accueil"><svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><rect x="3.5" y="3.5" width="13" height="13" transform="rotate(45 10 10)" fill="none" stroke="#fff" strokeWidth="1.6"/><circle cx="10" cy="10" r="2.3" fill="#f2bf4a"/></svg>Structura</a>
        <nav className="cnav" aria-label="Navigation principale">${NAV.map(([k, l]) => html`<a key=${k} className=${'cn' + (k === route ? ' on' : '')} aria-current=${k === route ? 'page' : null} href=${'#' + k}>${l}</a>`)}</nav>
        <input className="cfind" type="search" aria-label="Rechercher" placeholder="Deal, ISIN, script, client…"/>
        <div className="cctx"><span>Marché <b>20/11/26</b></span><span>Desk Paris</span>
          <div className="pals" role="group" aria-label="Couleur de l'interface">${[['nuit', 'Bleu nuit'], ['indigo', 'Indigo'], ['aubergine', 'Aubergine']].map(([k, l]) => html`<button key=${k} type="button" title=${l} aria-label=${l} aria-pressed=${palette === k} className=${'sw ' + k + (palette === k ? ' on' : '')} onClick=${() => setPalette(k)}><i></i></button>`)}</div>
          <button type="button" className="thm" aria-label=${theme === 'dark' ? 'Passer en thème clair' : 'Passer en thème sombre'} onClick=${() => setTheme(theme === 'dark' ? 'light' : 'dark')}>${theme === 'dark' ? 'Clair' : 'Sombre'}</button>
        </div>
      </header>
      <div className="docs" aria-label="Dossiers ouverts">${docs.map(([k, l, s]) => html`<a key=${k} className=${'dt' + (k === route ? ' on' : '')} href=${'#' + k}>${k !== 'accueil' ? html`<i></i>` : null}${l}${s ? html`<small>${s}</small>` : null}</a>`)}</div>
      <${S} ctx=${ctx}/>
      <footer className="dock">
        <span><i className=${job.phase === 'done' && !job.stale ? '' : 'w'}></i>FastAPI <b>${job.phase === 'done' ? (job.stale ? 'à recalculer' : 'à jour') : job.phase === 'cancelled' ? 'annulé' : job.phase === 'idle' ? 'prêt' : Math.round(job.prog * 100) + ' %'}</b></span>
        <span>React + SVG</span>
        <span>Prix <b>${fr(px)} %</b></span>
        <span><i className="w"></i>Cours <b>Yahoo</b></span>
        <span className="r">Prototype, données fictives, flux API simulé</span>
      </footer>
    </div>`;
  }

  ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App));
})(window);
