// Shared read of a watchlist barrier entry ({name, kind, observable, level,
// gap_pts}, see backend build_watchlist_row / parser._analyze_monitors) —
// used by both Booking's Surveillance tab and Risk Management's Barrières
// tab so the color/label convention never diverges between the two.
//
// Chip color = how close the worst-of currently is to that barrier, read in
// the direction the barrier bites: a KI hurts when WOF falls TO it (small
// positive gap = danger), an autocall triggers when WOF rises ABOVE it.
// gap_pts null = écart pas encore calculable (strike non fixé, prix
// indisponibles). Surtout pas traité comme 0 : `null <= 0` est vrai en JS, ce
// qui afficherait une barrière « franchie » sur un produit qui n'a même pas
// encore démarré.
export function barrierPending(b) {
  return b.gap_pts === null || b.gap_pts === undefined
}

export function barrierChipClass(b) {
  const g = b.gap_pts
  if (barrierPending(b)) return 'bg-slate-800 text-slate-500 border border-slate-700 border-dashed'
  if (b.kind === 'ki') {
    if (g <= 0) return 'bg-red-900/60 text-red-300 border border-red-700'
    if (g <= 5) return 'bg-red-900/40 text-red-400'
    if (g <= 15) return 'bg-amber-900/40 text-amber-400'
    return 'bg-slate-800 text-slate-500'
  }
  if (b.kind === 'autocall') {
    if (g >= 0) return 'bg-emerald-900/40 text-emerald-400'
    if (g >= -5) return 'bg-amber-900/40 text-amber-400'
    return 'bg-slate-800 text-slate-500'
  }
  if (b.kind === 'coupon') {
    if (g >= 0) return 'bg-emerald-900/40 text-emerald-400'
    if (g >= -5) return 'bg-amber-900/40 text-amber-400'
    return 'bg-slate-800 text-slate-500'
  }
  // 'neutral' — M_ param whose usage in the script is ambiguous: the gap is
  // shown but not color-read, we don't know which way the barrier bites.
  return 'bg-slate-800 text-slate-400 border border-slate-600'
}

export function barrierGapLabel(b) {
  const g = b.gap_pts
  if (barrierPending(b)) return 'en attente du strike'
  if (b.kind === 'ki' && g <= 0) return `franchie (${g.toFixed(1)} pts)`
  if ((b.kind === 'autocall' || b.kind === 'coupon') && g >= 0) return `≥ barrière (+${g.toFixed(1)} pts)`
  return `${g >= 0 ? '+' : ''}${g.toFixed(1)} pts`
}

// Closest two tick labels may sit on the ruler, in % of its width: below
// that, "100%" and "95%" overlap on a ~300px panel. The hidden level stays
// in the tick's tooltip and in the barrier row under the ruler.
const MIN_LABEL_GAP_PCT = 10

// Ruler of the Booking card: where the observable sits between the barriers
// that bite on it. A pure re-read of the watchlist gaps, never a second
// market computation — current = level + gap, so the cursor and the chips
// cannot disagree.
//
// Only directional barriers are placed. A 'neutral' M_ param may just as well
// be a participation (M_PARTICIPATION 90 % is one): on a ruler it would read
// as a barrier. A pending gap has no position yet (barrierPending).
//
// The shading follows the direction, not the name: below the highest 'ki'
// level something is lost, above the lowest 'autocall' level something is
// earned. A coupon barrier (WOF >= M_CPN_BAR) is an 'autocall' kind too, so
// that zone means "favourable", never "rappel".
export function barrierGauges(barriers) {
  const groups = new Map()
  for (const b of barriers || []) {
    if (!['ki', 'autocall', 'coupon'].includes(b.kind) || barrierPending(b)) continue
    const level = Number(b.level) * 100
    const current = level + Number(b.gap_pts)
    if (!Number.isFinite(level) || !Number.isFinite(current)) continue
    const observable = b.observable || 'WOF'
    if (!groups.has(observable)) groups.set(observable, { observable, current, marks: [] })
    groups.get(observable).marks.push({ name: b.name, kind: b.kind, level })
  }

  return [...groups.values()].map(({ observable, current, marks }) => {
    const levels = marks.map(m => m.level)
    const low = Math.min(current, ...levels)
    const high = Math.max(current, ...levels)
    const pad = Math.max(5, (high - low) * 0.15)
    const lo = Math.max(0, Math.floor((low - pad) / 5) * 5)
    const hi = Math.max(lo + 10, Math.ceil((high + pad) / 5) * 5)
    const at = v => ((v - lo) / (hi - lo)) * 100

    let lastLabelled = -Infinity
    const placed = marks
      .map(m => ({ ...m, pct: at(m.level) }))
      .sort((a, b) => a.pct - b.pct)
      .map(m => {
        const labelled = m.pct - lastLabelled >= MIN_LABEL_GAP_PCT
        if (labelled) lastLabelled = m.pct
        return { ...m, labelled }
      })
    const loss = marks.filter(m => m.kind === 'ki').map(m => m.level)
    const gain = marks.filter(m => m.kind === 'autocall' || m.kind === 'coupon').map(m => m.level)
    return {
      observable,
      current,
      lo,
      hi,
      currentPct: at(current),
      marks: placed,
      lossZonePct: loss.length ? at(Math.max(...loss)) : null,
      gainZonePct: gain.length ? 100 - at(Math.min(...gain)) : null,
    }
  })
}

// Deal-level severity = worst (most urgent) barrier on that deal — same
// thresholds as barrierChipClass, collapsed to 3 tiers for KPI counts and
// row-level sorting/coloring where a single per-deal read is needed instead
// of one badge per barrier.
export function barrierSeverity(b) {
  const g = b.gap_pts
  if (barrierPending(b)) return 'ok'
  if (b.kind === 'ki') {
    if (g <= 5) return 'critique'
    if (g <= 15) return 'attention'
    return 'ok'
  }
  if (b.kind === 'autocall') {
    if (g >= -5 && g < 0) return 'attention'
    return 'ok'
  }
  if (b.kind === 'coupon') {
    if (g >= -5 && g < 0) return 'attention'
    return 'ok'
  }
  return 'ok'
}

const _SEVERITY_RANK = { critique: 0, attention: 1, ok: 2 }

export function dealSeverity(barriers) {
  if (!barriers || !barriers.length) return 'ok'
  return barriers
    .map(barrierSeverity)
    .sort((a, b) => _SEVERITY_RANK[a] - _SEVERITY_RANK[b])[0]
}
