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
  // 'neutral' — M_ param whose usage in the script is ambiguous: the gap is
  // shown but not color-read, we don't know which way the barrier bites.
  return 'bg-slate-800 text-slate-400 border border-slate-600'
}

export function barrierGapLabel(b) {
  const g = b.gap_pts
  if (barrierPending(b)) return 'en attente du strike'
  if (b.kind === 'ki' && g <= 0) return `franchie (${g.toFixed(1)} pts)`
  if (b.kind === 'autocall' && g >= 0) return `≥ barrière (+${g.toFixed(1)} pts)`
  return `${g >= 0 ? '+' : ''}${g.toFixed(1)} pts`
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
  return 'ok'
}

const _SEVERITY_RANK = { critique: 0, attention: 1, ok: 2 }

export function dealSeverity(barriers) {
  if (!barriers || !barriers.length) return 'ok'
  return barriers
    .map(barrierSeverity)
    .sort((a, b) => _SEVERITY_RANK[a] - _SEVERITY_RANK[b])[0]
}
