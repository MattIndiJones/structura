// Demo pricing engine for the mockup: worst-of Phoenix under correlated GBM.
// It follows Structura's conventions: time axis anchored on the strike, cash flows
// discounted to their payment date, price rebased to the value date, and the issuer
// spread entering the discount curve only, never the drift.
(function (g) {
  const DAY = 864e5;
  const D = (y, m, d) => Date.UTC(y, m - 1, d);
  const isWE = (t) => [0, 6].includes(new Date(t).getUTCDay());
  const nextBD = (t) => { let x = t; while (isWE(x)) x += DAY; return x; };
  const addBD = (t, n) => { let x = t, k = n; while (k > 0) { x += DAY; if (!isWE(x)) k--; } return x; };
  const fd = (t) => { const x = new Date(t); return String(x.getUTCDate()).padStart(2, '0') + '/' + String(x.getUTCMonth() + 1).padStart(2, '0') + '/' + x.getUTCFullYear(); };

  const STRIKE = D(2026, 11, 27), VALUE = D(2026, 12, 4), NO = 12, NU = 3;
  const OBS = Array.from({ length: NO }, (_, i) => {
    const k = 10 + 3 * (i + 1);
    return nextBD(D(2026 + Math.floor(k / 12), (k % 12) + 1, 27));
  });
  const PAY = OBS.map((t) => addBD(t, 3));
  const yf = (t) => (t - STRIKE) / (365 * DAY);
  const TO = OBS.map(yf), TP = PAY.map(yf), TV = yf(VALUE);

  const UND = [
    { k: 'SX5E', n: 'Euro Stoxx 50', spot: 5720, src: 'Référence' },
    { k: 'SX7E', n: 'Euro Stoxx Banks', spot: 212.4, src: 'Surcharge' },
    { k: 'CAC', n: 'CAC 40', spot: 8140, src: 'Référence' }
  ];
  const MARKET = { r: 0.0235, s: 0.0085, vols: [0.178, 0.274, 0.186], qs: [0.031, 0.056, 0.0325], rho: [0.76, 0.90, 0.68] };
  const TERMS = { c: 2.70, cpn: 70, ac: 100, ki: 60, acFrom: 3, memo: true };

  function rng(seed) {
    let a = seed >>> 0;
    return () => {
      a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function gaussians(n, seed) {
    const r = rng(seed), out = new Float32Array(n);
    for (let i = 0; i < n; i += 2) {
      const u = Math.max(r(), 1e-12), v = r(), R = Math.sqrt(-2 * Math.log(u));
      out[i] = R * Math.cos(2 * Math.PI * v);
      if (i + 1 < n) out[i + 1] = R * Math.sin(2 * Math.PI * v);
    }
    return out;
  }
  function chol(m) {
    const [a, b, c] = m.rho;
    const l11 = 1, l21 = a, l22 = Math.sqrt(Math.max(1 - a * a, 1e-6)), l31 = b;
    const l32 = (c - b * a) / l22, l33 = Math.sqrt(Math.max(1 - b * b - l32 * l32, 1e-6));
    return [l11, l21, l22, l31, l32, l33];
  }

  // Worst-of level at each observation, antithetic pairs stored side by side.
  function simulate(m, Z, nh) {
    const W = new Float32Array(nh * 2 * NO), L = chol(m);
    const dt = TO.map((t, i) => t - (i ? TO[i - 1] : 0));
    const mu = dt.map((h) => m.vols.map((v, u) => (m.r - m.qs[u] - 0.5 * v * v) * h));
    const sd = dt.map((h) => m.vols.map((v) => v * Math.sqrt(h)));
    for (let p = 0; p < nh; p++) {
      for (let a = 0; a < 2; a++) {
        const s = a ? -1 : 1;
        let x0 = 0, x1 = 0, x2 = 0;
        for (let o = 0; o < NO; o++) {
          const i = (p * NO + o) * NU, z0 = s * Z[i], z1 = s * Z[i + 1], z2 = s * Z[i + 2];
          x0 += mu[o][0] + sd[o][0] * (L[0] * z0);
          x1 += mu[o][1] + sd[o][1] * (L[1] * z0 + L[2] * z1);
          x2 += mu[o][2] + sd[o][2] * (L[3] * z0 + L[4] * z1 + L[5] * z2);
          W[(p * 2 + a) * NO + o] = Math.exp(Math.min(x0, x1, x2));
        }
      }
    }
    return W;
  }

  function discount(m) {
    const y = m.r + m.s, base = Math.exp(-y * TV);
    return TP.map((t) => Math.exp(-y * t) / base);
  }

  // PV is linear in the coupon: PV = A + c * B, which makes solving instantaneous.
  function value(W, t, m) {
    const n = W.length / NO, df = discount(m), cu = t.c / 100, cb = t.cpn / 100, ac = t.ac / 100, ki = t.ki / 100;
    const exits = new Array(NO).fill(0);
    let par = 0, loss = 0, life = 0, sum = 0, sq = 0, B = 0, pvCall = 0, pvPar = 0, pvLoss = 0, prev = 0, lossSum = 0;
    for (let p = 0; p < n; p++) {
      const at = p * NO;
      let memo = 0, units = 0, cap = 0, last = NO - 1, called = false;
      for (let o = 0; o < NO; o++) {
        const w = W[at + o];
        if (w >= cb) {
          if (t.memo) { units += (o + 1 - memo) * df[o]; memo = o + 1; } else units += df[o];
        }
        if (o >= t.acFrom && w >= ac) { cap = df[o]; exits[o]++; pvCall += cap; last = o; called = true; break; }
      }
      if (!called) {
        const w = W[at + NO - 1];
        if (w < ki) { cap = w * df[NO - 1]; loss++; pvLoss += cap; lossSum += w; } else { cap = df[NO - 1]; par++; pvPar += cap; }
      }
      life += TO[last];
      B += units;
      const pv = cap + cu * units;
      if (p % 2) { const pair = 0.5 * (pv + prev); sum += pair; sq += pair * pair; } else prev = pv;
    }
    const h = n / 2, mean = sum / h, se = Math.sqrt(Math.max(sq / h - mean * mean, 0) / h);
    return {
      px: 100 * mean, ci: 196 * se, exits: exits.map((x) => 100 * x / n), par: 100 * par / n, loss: 100 * loss / n,
      life: life / n, lossLevel: loss ? 100 * lossSum / loss : 0, A: 100 * (pvCall + pvPar + pvLoss) / n, B: B / n,
      pv: { cpn: 100 * cu * B / n, call: 100 * pvCall / n, par: 100 * pvPar / n, loss: 100 * pvLoss / n }
    };
  }

  function quantiles(W, qs) {
    const n = W.length / NO, buf = new Float32Array(n);
    return Array.from({ length: NO }, (_, o) => {
      for (let p = 0; p < n; p++) buf[p] = W[p * NO + o];
      buf.sort();
      return qs.map((q) => 100 * buf[Math.min(n - 1, Math.floor(q * n))]);
    });
  }

  const bump = (m, f) => { const x = { ...m, vols: [...m.vols], qs: [...m.qs], rho: [...m.rho] }; f(x); return x; };
  const BUMPS = [
    { k: 'vol', l: 'Volatilité +1 pt', f: (x) => { x.vols = x.vols.map((v) => v + 0.01); } },
    { k: 'corr', l: 'Corrélation −5 pts', f: (x) => { x.rho = x.rho.map((v) => v - 0.05); } },
    { k: 'div', l: 'Dividendes +50 bps', f: (x) => { x.qs = x.qs.map((v) => v + 0.005); } },
    { k: 'rate', l: 'Taux +100 bps', f: (x) => { x.r += 0.01; } },
    { k: 'spread', l: 'Spread émetteur +100 bps', f: (x) => { x.s += 0.01; } }
  ];
  function sensitivities(Z, nh, t, m, base) {
    return BUMPS.map((b) => ({ k: b.k, l: b.l, d: value(simulate(bump(m, b.f), Z, nh), t, bump(m, b.f)).px - base }));
  }

  // Incremental job: each batch uses fresh draws, so the interval really narrows.
  function batchJob(t, m, batch, total, onStep, onDone) {
    let done = 0, sum = 0, sq = 0, seed = 1000, cancelled = false, timer = null;
    const points = [];
    const step = () => {
      if (cancelled) return;
      const nh = batch / 2, r = value(simulate(m, gaussians(nh * NO * NU, seed++), nh), t, m);
      const w = batch / (done + batch), v = r.ci / 1.96;
      sum = done ? sum * (1 - w) + r.px * w : r.px;
      sq = done ? sq * (1 - w) * (1 - w) + v * v * w * w : v * v;
      done += batch;
      points.push({ n: done, px: sum, ci: 1.96 * Math.sqrt(sq) });
      if (done >= total) { onStep(points.slice(), done / total); onDone({ px: sum, ci: 1.96 * Math.sqrt(sq), n: done }); return; }
      onStep(points.slice(), done / total);
      timer = setTimeout(step, 130);
    };
    timer = setTimeout(step, 260);
    return () => { cancelled = true; clearTimeout(timer); };
  }

  g.Eng = { D, DAY, fd, nextBD, addBD, STRIKE, VALUE, OBS, PAY, TO, TP, TV, NO, NU, UND, MARKET, TERMS, gaussians, simulate, value, quantiles, sensitivities, batchJob, discount };
})(typeof window !== 'undefined' ? window : globalThis);
