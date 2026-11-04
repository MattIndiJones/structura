// One population for the fan, statistics, quantile selections, histogram and export.
export function mtfRowsForView(rows, view) {
  return rows.map(row => {
    const legacy = row.stats_all === undefined
    const mask = legacy ? row.alive : view === 'all' ? row.pvs.map(() => true) : row.outstanding
    return { ...row, selected_mask: mask || [], n_selected: (mask || []).filter(Boolean).length,
      stats: legacy ? row.stats : view === 'all' ? row.stats_all : row.stats_outstanding,
      thin: legacy ? row.thin : view === 'all' ? row.thin_all : row.thin_outstanding,
      settled_pct: row.n_outer ? (row.n_settled || 0) / row.n_outer * 100 : 0 }
  })
}
export const MTF_MODEL_LABELS = {
  lsv: 'LSV · sous réserve de qualification',
  constant: 'Constant (GBM)', heston: 'Heston QE', sabr: 'SABR', localvol: 'Local Vol',
  gbm_atm_curve: 'GBM sur courbe ATM', heston_indicative: 'Heston · étude indicative',
}
