// React + SVG chart components. Each one draws to the real pixel size of its container.
(function (g) {
  const { useState, useRef, useLayoutEffect, useMemo } = React;
  const html = htm.bind(React.createElement);
  const E = g.Eng;
  const fr = (v, d = 2) => Number(v).toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d });
  const sg = (v, d = 2) => (v >= 0 ? '+' : '−') + fr(Math.abs(v), d);
  const lin = (a, b, c, d) => { const f = (v) => c + (v - a) / (b - a) * (d - c); f.inv = (y) => a + (y - c) / (d - c) * (b - a); return f; };
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const pt = (e) => { const r = e.currentTarget.ownerSVGElement.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  const path = (pts) => pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('');

  function useSize() {
    const ref = useRef(null);
    const [s, set] = useState({ w: 0, h: 0 });
    useLayoutEffect(() => {
      const el = ref.current;
      if (!el) return undefined;
      const f = () => set({ w: el.clientWidth, h: el.clientHeight });
      f();
      const ro = new ResizeObserver(f);
      ro.observe(el);
      return () => ro.disconnect();
    }, []);
    return [ref, s];
  }

  function Plot({ h = 220, label, draw, tip }) {
    const [ref, s] = useSize();
    const fill = h === 'fill', H = fill ? s.h : h;
    const left = tip ? (tip.x > s.w - 178 ? Math.max(0, tip.x - 166) : tip.x + 12) : 0;
    const top = tip ? clamp(tip.y - 16, 0, Math.max(0, H - 92)) : 0;
    return html`<div ref=${ref} className=${'plot' + (fill ? ' fill' : '')} style=${fill ? null : { height: h }}>
      ${s.w > 0 && H > 0 ? html`<svg width=${s.w} height=${H} role="img" aria-label=${label}>${draw(s.w, H)}</svg>` : null}
      ${tip ? html`<div className="tip" style=${{ left, top }}><b>${tip.title}</b>${(tip.rows || []).map((r) => html`<span key=${r[0]}><small>${r[0]}</small>${r[1]}</span>`)}</div>` : null}
    </div>`;
  }

  const hTicks = (ticks, y, x0, x1, f = (v) => v) => ticks.map((t) => html`<g key=${t}><line className="gl" x1=${x0} x2=${x1} y1=${y(t)} y2=${y(t)}/><text className="tx te" x=${x0 - 6} y=${y(t) + 3.5}>${f(t)}</text></g>`);

  // Maturity redemption, with barriers dragged directly on the chart.
  function Payoff({ t, onChange, h = 'fill' }) {
    const [drag, setDrag] = useState(null);
    const [hov, setHov] = useState(null);
    const redemption = (w) => (w < t.ki ? w : w < t.cpn ? 100 : 100 + t.c);
    const m = { l: 36, r: 12, t: 22, b: 26 };
    const tip = hov !== null && !drag ? { x: hov.px, y: hov.py, title: 'Worst final ' + fr(hov.w, 1) + ' %', rows: [['Remboursement', fr(redemption(hov.w)) + ' %']] } : drag ? { x: drag.px, y: 26, title: drag.k === 'ki' ? 'Protection' : 'Barrière de coupon', rows: [['Niveau', fr(t[drag.k], 0) + ' %']] } : null;
    const setLevel = (k, v) => {
      const r = Math.round(v);
      if (k === 'ki') onChange({ ...t, ki: clamp(r, 35, t.cpn) });
      else onChange({ ...t, cpn: clamp(r, t.ki, 100) });
    };
    return html`<${Plot} h=${h} tip=${tip} label=${'Remboursement à maturité. Protection ' + t.ki + ' %, barrière de coupon ' + t.cpn + ' %.'} draw=${(w, H) => {
      const x = lin(30, 130, m.l, w - m.r), y = lin(20, 115, H - m.b, m.t);
      const move = (e) => { const p = pt(e), v = clamp(x.inv(p.x), 30, 130); if (drag) { setLevel(drag.k, v); setDrag({ ...drag, px: p.x }); } else setHov({ w: v, px: p.x, py: p.y }); };
      const down = (e) => { const p = pt(e), dk = Math.abs(p.x - x(t.ki)), dc = Math.abs(p.x - x(t.cpn)); if (Math.min(dk, dc) > 16) return; e.currentTarget.setPointerCapture(e.pointerId); setDrag({ k: dk <= dc ? 'ki' : 'cpn', px: p.x }); };
      const key = (k) => (e) => { const dlt = { ArrowLeft: -1, ArrowRight: 1, ArrowDown: -1, ArrowUp: 1 }[e.key]; if (dlt) { e.preventDefault(); setLevel(k, t[k] + dlt); } };
      const nearHandle = hov && !drag && Math.min(Math.abs(hov.px - x(t.ki)), Math.abs(hov.px - x(t.cpn))) <= 16;
      return html`<g>
        <rect className="zl" x=${m.l} y=${m.t} width=${Math.max(0, x(t.ki) - m.l)} height=${H - m.t - m.b}/>
        ${hTicks([40, 60, 80, 100], y, m.l, w - m.r)}
        <line className="ax" x1=${m.l} x2=${w - m.r} y1=${H - m.b} y2=${H - m.b}/>
        ${[40, 60, 80, 100, 120].map((v) => html`<text key=${v} className="tx tm" x=${x(v)} y=${H - 9}>${v}</text>`)}
        <line className="rf" x1=${x(100)} x2=${x(100)} y1=${m.t} y2=${H - m.b}/>
        <path className="ln" d=${path([[x(30), y(30)], [x(t.ki), y(t.ki)]])}/>
        <path className="ln" d=${path([[x(t.ki), y(100)], [x(t.cpn), y(100)]])}/>
        <path className="ln" d=${path([[x(t.cpn), y(100 + t.c)], [x(130), y(100 + t.c)]])}/>
        <text className="tb te" x=${w - m.r - 2} y=${y(100 + t.c) - 6}>${fr(100 + t.c)} %</text>
        <line className="rk" x1=${x(t.ki)} x2=${x(t.ki)} y1=${m.t} y2=${H - m.b}/>
        <line className="rf" x1=${x(t.cpn)} x2=${x(t.cpn)} y1=${m.t} y2=${H - m.b}/>
        ${hov && !drag ? html`<g><line className="xh" x1=${x(hov.w)} x2=${x(hov.w)} y1=${m.t} y2=${H - m.b}/><circle className="dot" cx=${x(hov.w)} cy=${y(redemption(hov.w))} r="4"/></g>` : null}
        <rect className=${'hit' + (drag || nearHandle ? ' drag' : '')} x=${m.l} y="0" width=${w - m.l - m.r} height=${H - m.b} onPointerMove=${move} onPointerDown=${down} onPointerUp=${() => setDrag(null)} onPointerLeave=${() => { if (!drag) setHov(null); }}/>
        ${[['ki', 'k', 'KI'], ['cpn', '', 'Cpn']].map(([k, c, l]) => html`<g key=${k} className=${'hd ' + c + (drag && drag.k === k ? ' act' : '')} tabIndex="0" role="slider" aria-label=${k === 'ki' ? 'Barrière de protection' : 'Barrière de coupon'} aria-valuemin="35" aria-valuemax="100" aria-valuenow=${t[k]} onKeyDown=${key(k)} style=${{ pointerEvents: 'none' }}>
          <circle cx=${x(t[k])} cy=${m.t} r="7"/>
          <text className=${'tb' + (k === 'ki' ? ' te' : '')} x=${x(t[k]) + (k === 'ki' ? 7 : -7)} y=${m.t - 11}>${l} ${t[k]}</text>
        </g>`)}
      </g>`;
    }}/>`;
  }

  function VBars({ items, h = 'fill', label, unit = '%', dp = 1 }) {
    const [hov, setHov] = useState(null);
    const tip = hov !== null ? { x: hov.x, y: hov.y, title: items[hov.i].t || items[hov.i].l, rows: [[items[hov.i].n || 'Probabilité', fr(items[hov.i].v, dp) + (unit ? ' ' + unit : '')]] } : null;
    return html`<${Plot} h=${h} label=${label} tip=${tip} draw=${(w, H) => {
      const m = { l: 2, r: 2, t: 16, b: 20 }, max = Math.max(...items.map((d) => d.v), 1e-9), y = lin(0, max, H - m.b, m.t), band = (w - m.l - m.r) / items.length, gap = Math.min(5, band * 0.16);
      return html`<g>
        <line className="ax" x1=${m.l} x2=${w - m.r} y1=${H - m.b} y2=${H - m.b}/>
        ${items.map((d, i) => { const X = m.l + i * band + gap / 2, bw = band - gap, Y = y(d.v), rd = Math.max(0, Math.min(5, bw / 2, H - m.b - Y)); return html`<g key=${d.l}>
          <path className=${'bar ' + (d.c || '') + (hov && hov.i !== i ? ' dim' : '')} d=${`M${X} ${H - m.b}V${Y + rd}Q${X} ${Y} ${X + rd} ${Y}H${X + bw - rd}Q${X + bw} ${Y} ${X + bw} ${Y + rd}V${H - m.b}Z`}/>
          ${band > 26 || d.v === max ? html`<text className="tn tm" x=${X + bw / 2} y=${Y - 4}>${fr(d.v, dp)}</text>` : null}
          <text className="tx tm" x=${X + bw / 2} y=${H - 6}>${d.l}</text>
          <rect className="hit" x=${m.l + i * band} y=${m.t - 14} width=${band} height=${H - m.t - m.b + 34} onPointerMove=${(e) => { const p = pt(e); setHov({ i, x: p.x, y: p.y }); }} onPointerLeave=${() => setHov(null)}/>
        </g>`; })}
      </g>`;
    }}/>`;
  }

  function Waterfall({ items, h = 190, domain, label, dp = 2 }) {
    const [hov, setHov] = useState(null);
    let run = 0;
    const steps = items.map((d) => { if (d.total) { run = d.v; return { ...d, a: domain ? domain[0] : 0, b: d.v }; } const a = run; run += d.v; return { ...d, a, b: run }; });
    const lo = domain ? domain[0] : 0, hi = domain ? domain[1] : Math.max(...steps.map((s) => Math.max(s.a, s.b))) * 1.08;
    const tip = hov ? { x: hov.x, y: hov.y, title: hov.d.l, rows: [[hov.d.total ? 'Niveau' : 'Contribution', (hov.d.total ? fr(hov.d.v, dp) : sg(hov.d.v, dp)) + ' pt']] } : null;
    return html`<${Plot} h=${h} label=${label} tip=${tip} draw=${(w, H) => {
      const m = { l: 2, r: 2, t: 16, b: 20 }, y = lin(lo, hi, H - m.b, m.t), band = (w - m.l - m.r) / steps.length, bw = band * 0.72;
      return html`<g><line className="ax" x1=${m.l} x2=${w - m.r} y1=${H - m.b} y2=${H - m.b}/>
        ${steps.map((s, i) => { const X = m.l + i * band + (band - bw) / 2, top = y(Math.max(s.a, s.b)), bh = Math.max(2, Math.abs(y(s.a) - y(s.b))); return html`<g key=${s.l}>
          ${i < steps.length - 1 ? html`<line className="gl" x1=${X + bw} x2=${X + band} y1=${y(s.b)} y2=${y(s.b)}/>` : null}
          <rect className=${'bar ' + (s.total ? '' : s.v >= 0 ? 'up' : 'down')} x=${X} y=${top} width=${bw} height=${bh} rx=${Math.min(4, bh / 2)}/>
          <text className="tn tm" x=${X + bw / 2} y=${top - 4}>${s.total ? fr(s.v, dp) : sg(s.v, dp)}</text>
          <text className="tx tm" x=${X + bw / 2} y=${H - 6}>${s.l}</text>
          <rect className="hit" x=${m.l + i * band} y=${m.t - 14} width=${band} height=${H - m.t - m.b + 34} onPointerMove=${(e) => { const p = pt(e); setHov({ d: s, x: p.x, y: p.y }); }} onPointerLeave=${() => setHov(null)}/>
        </g>`; })}
      </g>`;
    }}/>`;
  }

  function Tornado({ items, h = 190 }) {
    const [hov, setHov] = useState(null);
    return html`<${Plot} h=${h} label="Sensibilités du prix aux chocs de marché" tip=${hov ? { x: hov.x, y: hov.y, title: hov.d.l, rows: [['Prix', sg(hov.d.d) + ' pt']] } : null} draw=${(w, H) => {
      const lab = Math.min(170, w * 0.42), max = Math.max(...items.map((d) => Math.abs(d.d)), 0.1) * 1.28, x = lin(-max, max, lab, w - 4), rh = (H - 6) / items.length;
      return html`<g><line className="ax" x1=${x(0)} x2=${x(0)} y1="2" y2=${H - 4}/>
        ${items.map((d, i) => { const Y = 3 + i * rh, bh = Math.min(17, rh - 7), X = Math.min(x(0), x(d.d)), bw = Math.abs(x(d.d) - x(0)); return html`<g key=${d.k}>
          <text className="tx" x="0" y=${Y + rh / 2 + 3}>${d.l}</text>
          <rect className=${'bar ' + (d.k === 'spread' ? 'loss' : d.d >= 0 ? 'up' : '')} x=${X} y=${Y + (rh - bh) / 2} width=${Math.max(1, bw)} height=${bh} rx=${Math.min(4, bw / 2)}/>
          <text className=${'tn ' + (d.d < 0 ? 'te' : '')} x=${d.d < 0 ? X - 4 : X + bw + 4} y=${Y + rh / 2 + 3.5}>${sg(d.d)}</text>
          <rect className="hit" x="0" y=${Y} width=${w} height=${rh} onPointerMove=${(e) => { const p = pt(e); setHov({ d, x: p.x, y: p.y }); }} onPointerLeave=${() => setHov(null)}/>
        </g>`; })}
      </g>`;
    }}/>`;
  }

  // Coupon by protection grid: every cell is a real repricing, a click adopts its terms.
  function TermGrid({ W, t, market, onPick, target = 98 }) {
    const [hov, setHov] = useState(null);
    const coupons = useMemo(() => [-0.6, -0.4, -0.2, 0, 0.2, 0.4, 0.6].map((d) => Math.round((t.c + d) * 100) / 100), [t.c]);
    const kis = [50, 55, 60, 65, 70];
    const cells = useMemo(() => kis.map((ki) => { const base = E.value(W, { ...t, ki, cpn: Math.max(t.cpn, ki) }, market); return coupons.map((c) => ({ ki, c, px: base.A + c * base.B, loss: base.loss })); }), [W, t.cpn, t.ac, t.acFrom, t.memo, market, coupons]);
    const cls = (d) => { const v = d - target; return v <= -1.5 ? 'f-o4' : v <= -0.9 ? 'f-o3' : v <= -0.4 ? 'f-o2' : v < -0.12 ? 'f-o1' : v <= 0.12 ? 'f-z' : v < 0.6 ? 'f-u1' : v < 1.2 ? 'f-u2' : 'f-u3'; };
    return html`<${Plot} h="fill" label="Grille de prix selon le coupon et la protection" tip=${hov ? { x: hov.x, y: hov.y, title: 'Coupon ' + fr(hov.d.c) + ' % · KI ' + hov.d.ki + ' %', rows: [['Prix', fr(hov.d.px) + ' %'], ['Écart à ' + target, sg(hov.d.px - target) + ' pt'], ['P(perte)', fr(hov.d.loss, 1) + ' %']] } : null} draw=${(w, H) => {
      const l = 46, top = 22, cw = (w - l) / coupons.length, ch = (H - top) / kis.length;
      return html`<g>
        <text className="tx" x="0" y="13">KI \\ Cpn</text>
        ${coupons.map((c, i) => html`<text key=${c} className=${c === t.c ? 'tb tm' : 'tx tm'} x=${l + cw * (i + 0.5)} y="13">${fr(c)} %</text>`)}
        ${kis.map((ki, r) => html`<g key=${ki}><text className=${ki === t.ki ? 'tb' : 'tx'} x="0" y=${top + ch * (r + 0.5) + 3.5}>${ki} %</text>
          ${cells[r].map((d, i) => { const on = d.c === t.c && d.ki === t.ki; return html`<g key=${d.c}>
            <rect className=${'cell ' + cls(d.px)} rx="6" x=${l + i * cw} y=${top + r * ch} width=${cw} height=${ch} onClick=${() => onPick({ ...t, ki: d.ki, cpn: Math.max(t.cpn, d.ki), c: d.c })} onPointerMove=${(e) => { const p = pt(e); setHov({ d, x: p.x, y: p.y }); }} onPointerLeave=${() => setHov(null)}/>
            <text className="tn tm" style=${{ pointerEvents: 'none' }} x=${l + cw * (i + 0.5)} y=${top + ch * (r + 0.5) + 4}>${fr(d.px)}</text>
            ${on ? html`<rect className="cellsel" rx="5" x=${l + i * cw + 1} y=${top + r * ch + 1} width=${cw - 2} height=${ch - 2}/>` : null}
          </g>`; })}
        </g>`)}
      </g>`;
    }}/>`;
  }

  function Paths({ W, t, market }) {
    const [hov, setHov] = useState(null);
    const q = useMemo(() => E.quantiles(W, [0.05, 0.25, 0.5, 0.75, 0.95]), [W]);
    const sample = useMemo(() => { const n = W.length / E.NO, out = []; for (let k = 0; k < 28; k++) { const p = Math.floor((k + 0.37) * n / 28), s = [100]; let stop = E.NO; for (let o = 0; o < E.NO; o++) { const v = 100 * W[p * E.NO + o]; s.push(v); if (o >= t.acFrom && v >= t.ac) { stop = o + 1; break; } } out.push({ s, stop }); } return out; }, [W, t.ac, t.acFrom]);
    const outcome = (d) => (d.stop < E.NO ? 'Rappel en T' + d.stop : d.s[E.NO] >= t.ac ? 'Rappel en T12' : d.s[E.NO] < t.ki ? 'Perte en capital' : 'Remboursé au pair');
    return html`<${Plot} h="fill" label="Éventail du worst-of avec seuils du contrat et trajectoires individuelles" tip=${hov ? { x: hov.x, y: hov.y, title: 'T' + hov.o + (hov.o ? ' · ' + E.fd(E.OBS[hov.o - 1]) : ' · strike'), rows: hov.o ? [['P95', fr(q[hov.o - 1][4], 1)], ['Médiane', fr(q[hov.o - 1][2], 1)], ['P5', fr(q[hov.o - 1][0], 1)], ['Trajectoire', outcome(hov.d)]] : [] } : null} draw=${(w, H) => {
      const m = { l: 36, r: 44, t: 10, b: 22 }, x = lin(0, 12, m.l, w - m.r), y = lin(30, 190, H - m.b, m.t);
      const band = (a, b) => path([[x(0), y(100)], ...q.map((r, i) => [x(i + 1), y(r[a])]), ...q.map((r, i) => [x(12 - i), y(q[11 - i][b])]), [x(0), y(100)]]) + 'Z';
      const move = (e) => { const p = pt(e), o = clamp(Math.round(x.inv(p.x)), 0, 12); let best = sample[0], dist = 1e9; sample.forEach((d) => { const v = d.s[Math.min(o, d.s.length - 1)], dd = Math.abs(y(v) - p.y); if (dd < dist) { dist = dd; best = d; } }); setHov({ o, d: best, x: p.x, y: p.y }); };
      return html`<g>
        ${hTicks([40, 70, 100, 130, 160], y, m.l, w - m.r)}
        <path className="bo" d=${band(0, 4)}/><path className="bi" d=${band(1, 3)}/>
        ${sample.map((d, i) => html`<path key=${i} className="lnf" d=${path(d.s.map((v, k) => [x(k), y(v)]))}/>`)}
        <path className="ln" d=${path([[x(0), y(100)], ...q.map((r, i) => [x(i + 1), y(r[2])])])}/>
        ${hov ? html`<g><line className="xh" x1=${x(hov.o)} x2=${x(hov.o)} y1=${m.t} y2=${H - m.b}/><path className="lnh" d=${path(hov.d.s.map((v, k) => [x(k), y(v)]))}/></g>` : null}
        <line className="rf" x1=${x(t.acFrom + 1)} x2=${x(12)} y1=${y(t.ac)} y2=${y(t.ac)}/><text className="tb" x=${x(12) + 4} y=${y(t.ac) + 3}>AC ${t.ac}</text>
        <line className="rf" x1=${x(0)} x2=${x(12)} y1=${y(t.cpn)} y2=${y(t.cpn)}/><text className="tb" x=${x(12) + 4} y=${y(t.cpn) + 3}>Cpn ${t.cpn}</text>
        <line className="rk" x1=${x(0)} x2=${x(12)} y1=${y(t.ki)} y2=${y(t.ki)}/><text className="tb" x=${x(12) + 4} y=${y(t.ki) + 3}>KI ${t.ki}</text>
        <line className="ax" x1=${m.l} x2=${w - m.r} y1=${H - m.b} y2=${H - m.b}/>
        ${[0, 2, 4, 6, 8, 10, 12].map((k) => html`<text key=${k} className="tx tm" x=${x(k)} y=${H - 6}>${k ? 'T' + k : 'Strike'}</text>`)}
        <rect className="hit" x=${m.l} y="0" width=${w - m.l - m.r} height=${H - m.b} onPointerMove=${move} onPointerLeave=${() => setHov(null)}/>
      </g>`;
    }}/>`;
  }

  function Convergence({ points, total, h = 112 }) {
    return html`<${Plot} h=${h} label="Convergence du prix et de son intervalle à 95 %" draw=${(w, H) => {
      if (!points.length) return html`<text className="tx" x="0" y="20">En attente du premier lot</text>`;
      const last = points[points.length - 1], spread = Math.max(...points.map((p) => p.ci), 0.08) * 1.15, m = { l: 40, r: 4, t: 6, b: 16 };
      const x = lin(0, total, m.l, w - m.r), y = lin(last.px - spread, last.px + spread, H - m.b, m.t), cl = (v) => clamp(v, m.t, H - m.b);
      const upper = points.map((p) => [x(p.n), cl(y(p.px + p.ci))]), lower = points.map((p) => [x(p.n), cl(y(p.px - p.ci))]).reverse();
      return html`<g>
        ${[last.px - spread * 0.6, last.px, last.px + spread * 0.6].map((v) => html`<g key=${v}><line className="gl" x1=${m.l} x2=${w - m.r} y1=${y(v)} y2=${y(v)}/><text className="tx te" x=${m.l - 4} y=${y(v) + 3}>${fr(v)}</text></g>`)}
        <path className="band" d=${path([...upper, ...lower]) + 'Z'}/>
        <path className="ln1" d=${path(points.map((p) => [x(p.n), cl(y(p.px))]))}/>
        <circle className="dot sel" cx=${x(last.n)} cy=${cl(y(last.px))} r="4"/>
        <text className="tx" x=${m.l} y=${H - 3}>0</text><text className="tx te" x=${w - m.r} y=${H - 3}>${fr(total / 1000, 0)} k chemins</text>
      </g>`;
    }}/>`;
  }

  function Spark({ v, w = 86, h = 22, bar }) {
    const min = Math.min(...v, bar === null || bar === undefined ? Infinity : bar), max = Math.max(...v, bar === null || bar === undefined ? -Infinity : bar), x = lin(0, v.length - 1, 1, w - 3), y = lin(min, max, h - 2, 2);
    return html`<svg width=${w} height=${h} aria-hidden="true" style=${{ display: 'block' }}>
      ${bar !== null && bar !== undefined ? html`<line className="rk" style=${{ strokeWidth: 1 }} x1="0" x2=${w} y1=${y(bar)} y2=${y(bar)}/>` : null}
      <path className="spk" d=${path(v.map((p, i) => [x(i), y(p)]))}/>
      <circle cx=${x(v.length - 1)} cy=${y(v[v.length - 1])} r="2" style=${{ fill: 'var(--s2)' }}/>
    </svg>`;
  }

  function SeriesChart({ series, refs = [], labels, fmtX, h = 'fill', yFmt = (v) => fr(v, 0), name = 'Worst-of', label }) {
    const [hov, setHov] = useState(null);
    const n = series.length, vals = [...series, ...refs.map((r) => r.v)], min = Math.min(...vals), max = Math.max(...vals), pad = (max - min) * 0.1 || 1;
    return html`<${Plot} h=${h} label=${label} tip=${hov !== null ? { x: hov.x, y: hov.y, title: fmtX(hov.i), rows: [[name, fr(series[hov.i]) + ' %'], ...refs.map((r) => [r.l, sg(series[hov.i] - r.v, 1) + ' pts'])] } : null} draw=${(w, H) => {
      const m = { l: 34, r: 60, t: 8, b: 20 }, x = lin(0, n - 1, m.l, w - m.r), y = lin(min - pad, max + pad, H - m.b, m.t), step = (max - min + 2 * pad) / 4, ticks = [0, 1, 2, 3].map((k) => Math.round(min - pad + step * (k + 0.5)));
      const move = (e) => { const p = pt(e); setHov({ i: clamp(Math.round(x.inv(p.x)), 0, n - 1), x: p.x, y: p.y }); };
      return html`<g>${hTicks(ticks, y, m.l, w - m.r, yFmt)}
        ${refs.map((r) => html`<g key=${r.l}><line className=${r.hot ? 'rk' : 'rf'} x1=${m.l} x2=${w - m.r} y1=${y(r.v)} y2=${y(r.v)}/><text className="tb" x=${w - m.r + 4} y=${y(r.v) + 3}>${r.l}</text></g>`)}
        <path fill="url(#soft-area)" d=${path([[x(0), H - m.b], ...series.map((v, i) => [x(i), y(v)]), [x(n - 1), H - m.b]]) + 'Z'}/>
        <path className="ln1" d=${path(series.map((v, i) => [x(i), y(v)]))}/>
        <circle className="dot sel" cx=${x(n - 1)} cy=${y(series[n - 1])} r="4"/>
        ${(labels || []).map((l) => html`<text key=${l.i} className="tx tm" x=${x(l.i)} y=${H - 6}>${l.t}</text>`)}
        <line className="ax" x1=${m.l} x2=${w - m.r} y1=${H - m.b} y2=${H - m.b}/>
        ${hov ? html`<g><line className="xh" x1=${x(hov.i)} x2=${x(hov.i)} y1=${m.t} y2=${H - m.b}/><circle className="dot" cx=${x(hov.i)} cy=${y(series[hov.i])} r="4"/></g>` : null}
        <rect className="hit" x=${m.l} y="0" width=${w - m.l - m.r} height=${H - m.b} onPointerMove=${move} onPointerLeave=${() => setHov(null)}/>
      </g>`;
    }}/>`;
  }

  function Scatter({ items, xd, yd, xt, yt, xFmt, yFmt, sel, onSel, limit, onLimit, frontier, h = 'fill', label, size }) {
    const [hov, setHov] = useState(null);
    const [drag, setDrag] = useState(false);
    return html`<${Plot} h=${h} label=${label} tip=${hov ? { x: hov.x, y: hov.y, title: hov.d.title, rows: hov.d.rows } : null} draw=${(w, H) => {
      const m = { l: 40, r: 14, t: 20, b: 24 }, x = lin(xd[0], xd[1], m.l, w - m.r), y = lin(yd[0], yd[1], H - m.b, m.t);
      const mv = (e) => { if (drag) onLimit(clamp(Math.round(x.inv(pt(e).x)), xd[0], xd[1])); };
      return html`<g>
        ${hTicks(yt, y, m.l, w - m.r, yFmt)}
        <line className="ax" x1=${m.l} x2=${w - m.r} y1=${H - m.b} y2=${H - m.b}/>
        ${xt.map((v) => html`<text key=${v} className="tx tm" x=${x(v)} y=${H - 7}>${xFmt(v)}</text>`)}
        ${frontier ? html`<path className="rf" style=${{ fill: 'none' }} d=${path(frontier.map((p) => [x(p[0]), y(p[1])]))}/>` : null}
        ${limit !== undefined ? html`<g>
          <rect className="zl" x=${x(limit)} y=${m.t} width=${Math.max(0, w - m.r - x(limit))} height=${H - m.t - m.b}/>
          <line className="rk" x1=${x(limit)} x2=${x(limit)} y1=${m.t} y2=${H - m.b}/>
          <text className="tb tm" x=${clamp(x(limit), m.l + 40, w - 50)} y="10">Limite ${limit} %</text>
        </g>` : null}
        ${items.map((d) => html`<g key=${d.id}>
          <circle className=${'dot ' + (d.id === sel ? 'sel' : d.c || '')} style=${{ cursor: 'pointer' }} cx=${x(d.x)} cy=${y(d.y)} r=${size ? size(d) : d.id === sel ? 7.5 : 6} onClick=${() => onSel && onSel(d.id)} onPointerMove=${(e) => { const p = pt(e); setHov({ d, x: p.x, y: p.y }); }} onPointerLeave=${() => setHov(null)}/>
          ${d.tag ? (d.side ? html`<text className=${'tb' + (d.side === 'l' ? ' te' : '')} style=${{ pointerEvents: 'none' }} x=${x(d.x) + (d.side === 'l' ? -1 : 1) * ((size ? size(d) : 7) + 4)} y=${y(d.y) + 3.5}>${d.tag}</text>` : html`<text className="tb tm" style=${{ pointerEvents: 'none' }} x=${x(d.x)} y=${y(d.y) - (size ? size(d) : 7) - 4}>${d.tag}</text>`) : null}
        </g>`)}
        ${limit !== undefined ? html`<rect x=${x(limit) - 9} y=${m.t} width="18" height=${H - m.t - m.b} className="hit drag" role="slider" tabIndex="0" aria-label="Limite de probabilité de perte" aria-valuenow=${limit} aria-valuemin=${xd[0]} aria-valuemax=${xd[1]} onKeyDown=${(e) => { const dl = { ArrowLeft: -1, ArrowRight: 1 }[e.key]; if (dl) { e.preventDefault(); onLimit(clamp(limit + dl, xd[0], xd[1])); } }} onPointerDown=${(e) => { e.currentTarget.setPointerCapture(e.pointerId); setDrag(true); }} onPointerMove=${mv} onPointerUp=${() => setDrag(false)}/>` : null}
      </g>`;
    }}/>`;
  }

  // Shock matrix linked to a cross-section through the selected volatility row.
  function ShockMatrix({ xs, ys, z, sel, onSel }) {
    const [hov, setHov] = useState(null);
    const cls = (v) => (v <= -4000 ? 'f-o4' : v <= -2500 ? 'f-o3' : v <= -1000 ? 'f-o2' : v < 0 ? 'f-o1' : v === 0 ? 'f-z' : v < 500 ? 'f-u1' : v < 1000 ? 'f-u2' : 'f-u3');
    return html`<${Plot} h="fill" label="P&L du book selon les chocs de spot et de volatilité" tip=${hov ? { x: hov.x, y: hov.y, title: 'Spot ' + hov.sx + ' · Vol ' + hov.sy, rows: [['P&L', sg(hov.v, 0) + ' k€'], ['% du MtM', sg(hov.v / 1789, 2) + ' %']] } : null} draw=${(w, H) => {
      const l = 58, t = 20, cw = (w - l) / xs.length, ch = (H - t) / ys.length;
      return html`<g>
        ${xs.map((s, i) => html`<text key=${s} className=${i === sel.c ? 'tb tm' : 'tx tm'} x=${l + cw * (i + 0.5)} y="13">${s}</text>`)}
        ${ys.map((s, r) => html`<g key=${s}><text className=${r === sel.r ? 'tb' : 'tx'} x="0" y=${t + ch * (r + 0.5) + 3.5}>${s}</text>
          ${z[r].map((v, c) => html`<g key=${c}>
            <rect className=${'cell ' + cls(v)} rx="6" x=${l + c * cw} y=${t + r * ch} width=${cw} height=${ch} onClick=${() => onSel({ r, c })} onPointerMove=${(e) => { const p = pt(e); setHov({ v, sx: xs[c], sy: s, x: p.x, y: p.y }); }} onPointerLeave=${() => setHov(null)}/>
            <text className="tn tm" style=${{ pointerEvents: 'none', fontSize: 12 }} x=${l + cw * (c + 0.5)} y=${t + ch * (r + 0.5) + 4}>${v > 0 ? '+' : v < 0 ? '−' : ''}${fr(Math.abs(v), 0)}</text>
          </g>`)}
        </g>`)}
        <rect className="cellsel" rx="5" x=${l + sel.c * cw + 1} y=${t + sel.r * ch + 1} width=${cw - 2} height=${ch - 2}/>
      </g>`;
    }}/>`;
  }

  function CrossSection({ xv, y, label: lab, mark }) {
    return html`<${Plot} h="fill" label=${'Coupe du P&L : ' + lab} draw=${(w, H) => {
      const m = { l: 44, r: 10, t: 12, b: 20 }, x = lin(xv[0], xv[xv.length - 1], m.l, w - m.r), yy = lin(-6000, 2000, H - m.b, m.t), pts = xv.map((v, i) => [x(v), yy(y[i])]);
      return html`<g>${hTicks([-6000, -4000, -2000, 0, 2000], yy, m.l, w - m.r, (v) => (v / 1000).toLocaleString('fr-FR') + ' M')}
        <line className="ax" x1=${m.l} x2=${w - m.r} y1=${yy(0)} y2=${yy(0)}/>
        <path className="ln1" d=${path(pts)}/>
        ${pts.map((p, i) => html`<circle key=${i} className=${'dot ' + (i === mark ? 'sel' : '')} cx=${p[0]} cy=${p[1]} r=${i === mark ? 6 : 3.5}/>`)}
        ${xv.map((v) => html`<text key=${v} className="tx tm" x=${x(v)} y=${H - 6}>${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v)} %</text>`)}
      </g>`;
    }}/>`;
  }

  // Two rebased series with a brush: the window drives the chart and the statistics.
  function BrushChart({ a, b, dates, win, onWin }) {
    const [hov, setHov] = useState(null);
    const [drag, setDrag] = useState(null);
    const [i0, i1] = win, fa = a.slice(i0, i1 + 1).map((v) => 100 * v / a[i0]), fb = b.slice(i0, i1 + 1).map((v) => 100 * v / b[i0]);
    const all = [...fa, ...fb], lo = Math.min(...all), hi = Math.max(...all), pad = (hi - lo) * 0.08 || 1;
    return html`<${Plot} h="fill" label="Performance rebasée du fonds et de l'indice, avec sélection de période" tip=${hov !== null ? { x: hov.x, y: 30, title: E.fd(dates[i0 + hov.i]), rows: [['Fonds', fr(fa[hov.i])], ['Indice', fr(fb[hov.i])], ['Écart', sg(fa[hov.i] - fb[hov.i]) + ' pts']] } : null} draw=${(w, H) => {
      const m = { l: 40, r: 10, t: 8, b: 72 }, x = lin(0, fa.length - 1, m.l, w - m.r), y = lin(lo - pad, hi + pad, H - m.b, m.t);
      const bx = lin(0, a.length - 1, m.l, w - m.r), mn = Math.min(...a, ...b), mx = Math.max(...a, ...b), by = lin(mn, mx, H - 8, H - 44);
      const ticks = [0, 1, 2, 3].map((k) => Math.round(lo + (hi - lo) * (k + 0.5) / 4));
      const stepA = Math.max(1, Math.floor(a.length / 240));
      const mini = (s) => path(s.filter((_, i) => i % stepA === 0).map((v, i) => [bx(i * stepA), by(v)]));
      const onMove = (e) => {
        const p = pt(e);
        if (!drag) return;
        const idx = clamp(Math.round(bx.inv(p.x)), 0, a.length - 1);
        if (drag.m === 'l') onWin([Math.min(idx, i1 - 20), i1]);
        else if (drag.m === 'r') onWin([i0, Math.max(idx, i0 + 20)]);
        else { const span = drag.b - drag.a, d = idx - drag.s, s = clamp(drag.a + d, 0, a.length - 1 - span); onWin([s, s + span]); }
      };
      const onDown = (e) => {
        const p = pt(e), idx = clamp(Math.round(bx.inv(p.x)), 0, a.length - 1);
        e.currentTarget.setPointerCapture(e.pointerId);
        if (Math.abs(p.x - bx(i0)) < 9) setDrag({ m: 'l' });
        else if (Math.abs(p.x - bx(i1)) < 9) setDrag({ m: 'r' });
        else if (idx > i0 && idx < i1) setDrag({ m: 'mv', s: idx, a: i0, b: i1 });
        else { const span = i1 - i0, s = clamp(idx - Math.round(span / 2), 0, a.length - 1 - span); onWin([s, s + span]); setDrag({ m: 'mv', s: idx, a: s, b: s + span }); }
      };
      const idxTicks = [0, 0.25, 0.5, 0.75, 1].map((k) => Math.round(k * (fa.length - 1)));
      const short = (t) => { const s = E.fd(t); return s.slice(3, 5) + '/' + s.slice(8); };
      return html`<g>
        ${hTicks(ticks, y, m.l, w - m.r)}
        <path fill="url(#soft-area)" d=${path([[x(0), H - m.b], ...fa.map((v, i) => [x(i), y(v)]), [x(fa.length - 1), H - m.b]]) + 'Z'}/>
        <path className="ln2" d=${path(fb.map((v, i) => [x(i), y(v)]))}/>
        <path className="ln1" d=${path(fa.map((v, i) => [x(i), y(v)]))}/>
        ${idxTicks.map((i) => html`<text key=${i} className="tx tm" x=${clamp(x(i), m.l + 12, w - m.r - 18)} y=${H - m.b + 14}>${short(dates[i0 + i])}</text>`)}
        <line className="ax" x1=${m.l} x2=${w - m.r} y1=${H - m.b} y2=${H - m.b}/>
        ${hov !== null ? html`<g><line className="xh" x1=${x(hov.i)} x2=${x(hov.i)} y1=${m.t} y2=${H - m.b}/><circle className="dot" cx=${x(hov.i)} cy=${y(fa[hov.i])} r="4"/><circle className="dot hot" cx=${x(hov.i)} cy=${y(fb[hov.i])} r="4"/></g>` : null}
        <rect className="hit" x=${m.l} y="0" width=${w - m.l - m.r} height=${H - m.b} onPointerMove=${(e) => { const p = pt(e); setHov({ i: clamp(Math.round(x.inv(p.x)), 0, fa.length - 1), x: p.x }); }} onPointerLeave=${() => setHov(null)}/>
        <path className="lnf" style=${{ opacity: 0.9, strokeWidth: 1 }} d=${mini(a)}/>
        <rect className="brush" x=${bx(i0)} y=${H - 48} width=${Math.max(2, bx(i1) - bx(i0))} height="44"/>
        <line className="brushl" x1=${bx(i0)} x2=${bx(i0)} y1=${H - 48} y2=${H - 4}/><line className="brushl" x1=${bx(i1)} x2=${bx(i1)} y1=${H - 48} y2=${H - 4}/>
        <rect className="hit drag" x=${m.l - 8} y=${H - 50} width=${w - m.l - m.r + 16} height="48" role="slider" tabIndex="0" aria-label="Période analysée" aria-valuemin="0" aria-valuemax=${a.length - 1} aria-valuenow=${i0} onKeyDown=${(e) => { const dl = { ArrowLeft: -5, ArrowRight: 5 }[e.key]; if (dl) { e.preventDefault(); const span = i1 - i0, s = clamp(i0 + dl, 0, a.length - 1 - span); onWin([s, s + span]); } }} onPointerDown=${onDown} onPointerMove=${onMove} onPointerUp=${() => setDrag(null)}/>
      </g>`;
    }}/>`;
  }

  g.UI = { html, fr, sg, lin, clamp, pt, path, Plot, Payoff, VBars, Waterfall, Tornado, TermGrid, Paths, Convergence, Spark, SeriesChart, Scatter, ShockMatrix, CrossSection, BrushChart };
})(window);
