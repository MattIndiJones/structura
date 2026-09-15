function numeric(value) {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function addRow(rows, key, group, label, value, unit = 'percent') {
  rows.set(key, { key, group, label, value: numeric(value), unit })
}

function snapshotRows(snapshot = {}) {
  const rows = new Map()
  const yieldCurve = snapshot.yieldCurve || []
  if (yieldCurve.length) {
    for (const pillar of yieldCurve) {
      addRow(rows, `rate:${pillar.T}`, 'Taux', `Taux ${pillar.label || `${pillar.T}Y`}`, pillar.rate)
    }
  } else {
    addRow(rows, 'rate:flat', 'Taux', 'Taux sans risque', snapshot.r)
  }

  const funding = snapshot.funding || {}
  if (funding.mode === 'pillars' && funding.pillars?.length) {
    for (const pillar of funding.pillars) {
      addRow(rows, `funding:${pillar.T}`, 'Funding', `Funding ${pillar.label || `${pillar.T}Y`}`, pillar.spread)
    }
  } else {
    addRow(rows, 'funding:flat', 'Funding', 'Funding', funding.level ?? 0)
  }

  const model = snapshot.model || 'constant'
  const modelFields = {
    constant: [['sigma', 'Volatilité']],
    heston: [
      ['v0', 'Variance initiale'], ['kappa', 'Retour à la moyenne', 'number'],
      ['theta', 'Variance long terme'], ['xi', 'Vol de variance'], ['rho_h', 'Corrélation spot/vol'],
    ],
    sabr: [
      ['alpha', 'Alpha'], ['beta', 'Bêta'], ['rho', 'Rho'], ['nu', 'Nu'],
    ],
    local_vol: [
      ['sigma', 'Volatilité ATM'], ['skew', 'Skew'], ['curvature', 'Courbure'],
    ],
    lsv: [
      ['v0', 'Variance initiale'], ['kappa', 'Retour à la moyenne', 'number'],
      ['theta', 'Variance long terme'], ['xi', 'Vol de variance'], ['rho_h', 'Corrélation spot/vol'],
      ['skew', 'Skew local'], ['curvature', 'Courbure locale'],
    ],
  }

  for (const [index, underlying] of (snapshot.underlyings || []).entries()) {
    const ticker = underlying.ticker || underlying.name || `Sous-jacent ${index + 1}`
    const group = ticker
    const dividendCurve = underlying.dividendCurve || []
    if (dividendCurve.length) {
      for (const pillar of dividendCurve) {
        addRow(rows, `ul:${index}:dividend:${pillar.T}`, group,
          `Dividende ${pillar.T}A`, pillar.rate)
      }
    } else {
      addRow(rows, `ul:${index}:q`, group, 'Dividende', underlying.q)
    }
    for (const [field, label, unit = 'percent'] of (modelFields[model] || modelFields.constant)) {
      addRow(rows, `ul:${index}:${field}`, group, label, underlying[field], unit)
    }
    if (numeric(underlying.sigma_fx) || numeric(underlying.rho_sfx) || numeric(underlying.ccyh)) {
      addRow(rows, `ul:${index}:sigma_fx`, group, 'Volatilité FX', underlying.sigma_fx)
      addRow(rows, `ul:${index}:rho_sfx`, group, 'Corrélation sous-jacent/FX', underlying.rho_sfx)
      addRow(rows, `ul:${index}:ccyh`, group, 'Coût de couverture FX', underlying.ccyh, 'bps')
    }
  }

  const names = (snapshot.underlyings || []).map((underlying, index) =>
    underlying.ticker || underlying.name || `Sous-jacent ${index + 1}`)
  const correlations = snapshot.corrMatrix || []
  for (let left = 0; left < correlations.length; left += 1) {
    for (let right = left + 1; right < correlations.length; right += 1) {
      addRow(rows, `corr:${left}:${right}`, 'Corrélations',
        `${names[left]} / ${names[right]}`, correlations[left]?.[right], 'correlation')
    }
  }
  return rows
}

export function compareMarketSnapshots(currentSnapshot, previousSnapshot = null) {
  const current = snapshotRows(currentSnapshot)
  const previous = previousSnapshot ? snapshotRows(previousSnapshot) : new Map()
  const keys = [...new Set([...current.keys(), ...previous.keys()])]
  return keys.map(key => {
    const currentRow = current.get(key)
    const previousRow = previous.get(key)
    const value = currentRow?.value ?? null
    const previousValue = previousRow?.value ?? null
    const delta = value === null || previousValue === null ? null : value - previousValue
    return {
      ...(currentRow || previousRow),
      value,
      previousValue,
      delta,
      changed: previousSnapshot != null && (
        value === null || previousValue === null || Math.abs(delta) > 1e-10),
    }
  })
}

export function compareMarketSnapshotSeries(snapshots = []) {
  const series = snapshots.map(snapshot => snapshotRows(snapshot || {}))
  const keys = [...new Set(series.flatMap(rows => [...rows.keys()]))]
  return keys.map(key => {
    const reference = series.map(rows => rows.get(key)).find(Boolean)
    const values = series.map(rows => rows.get(key)?.value ?? null)
    const deltas = values.map((value, index) => {
      if (index === 0 || value === null || values[index - 1] === null) return null
      return value - values[index - 1]
    })
    const changed = values.some((value, index) => index > 0 && (
      value === null || values[index - 1] === null
      || Math.abs(value - values[index - 1]) > 1e-10))
    return { ...reference, values, deltas, changed }
  })
}
