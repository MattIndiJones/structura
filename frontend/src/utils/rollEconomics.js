export function defaultRollFinancing() {
  return { exit_basis: 'model', bid_pct: '', bid_source: '', bid_observed_at: '',
    haircut_points: 0, exit_cost_points: 0, entry_cost_points: 0 }
}

function number(value) { return value === '' || value == null ? null : Number(value) }

export function rollFinancingPayload(form) {
  const payload = { exit_basis: form.exit_basis,
    haircut_points: form.exit_basis === 'model_haircut' ? number(form.haircut_points) : 0,
    exit_cost_points: number(form.exit_cost_points), entry_cost_points: number(form.entry_cost_points) }
  if (form.exit_basis === 'observed_bid') {
    const observed = form.bid_observed_at ? new Date(form.bid_observed_at) : null
    if (observed && !Number.isFinite(observed.getTime())) throw new Error('Horodatage du bid invalide.')
    Object.assign(payload, { bid_pct: number(form.bid_pct), bid_source: form.bid_source.trim(),
      bid_observed_at: observed?.toISOString() || null })
  }
  return payload
}

export function rollFinancingForm(saved) {
  const form = { ...defaultRollFinancing(), ...saved }
  form.bid_pct ??= ''
  form.bid_source ??= ''
  form.bid_observed_at ??= ''
  if (form.bid_observed_at) {
    const date = new Date(form.bid_observed_at)
    if (Number.isFinite(date.getTime())) form.bid_observed_at = new Date(
      date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, -1)
  }
  return form
}

/** Preserve archive bytes; legacy quantities never become qualified caps. */
export function comparisonRows(result) {
  if (result?.comparison_schema_version === 2) return result.lignes || []
  return (result?.lignes || []).map(row => ({ ...row, plafond: null,
    reinvested_notional: null, recovery_mean: null, recovery_median: null,
    recovery_sample_max: null, recovery_cap_method: 'LEGACY_UNQUALIFIED' }))
}
