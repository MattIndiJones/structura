// Shared Economics boundary for the Pricer, RFQ and saved configurations.
export function usesAbsoluteSpots(script) {
  const name=/^\s*UNDERLYING\s+(\w+)/mi.exec(script||'')?.[1]
  if(!name) return false
  const member=`${name}\\.spot(?:0)?(?:\\s*\\[[^\\]]+\\])?`
  let text=String(script).replace(/#.*$/gm,'')
  text=text.replace(new RegExp(`^\\s*${name}\\.spot0\\s*=\\s*${name}\\.spot\\s*@\\w+\\s*$`,'gmi'),'')
  text=text.replace(new RegExp(`${name}\\.spot(\\s*\\[[^\\]]+\\])?\\s*/\\s*${name}\\.spot0(?:\\s*\\[[^\\]]+\\])?`,'gi'),'')
  return new RegExp(`\\b${member}\\b`,'i').test(text)
}
export const tenorString = value => typeof value === 'string' ? value : value?.value ? `${value.value}${value.unit}` : null
export function tenorPair(value) {
  if (value && typeof value === 'object') return { ...value }
  const match = /^(\d+)([DWMY])$/i.exec(value || '')
  return { value: match ? Number(match[1]) : null, unit: match ? match[2].toUpperCase() : 'M' }
}
export function calendarValue(c, saved) {
  if (c.kind === 'single' && !c.reduction && (!saved || typeof saved === 'string')) return saved || ''
  const value = { ...(saved && typeof saved === 'object' ? saved : {}) }
  if (c.kind === 'single') value.date ||= typeof saved === 'string' ? saved : ''
  else {
    for (const field of ['start_date', 'first_observation_date', 'period_start_date', 'end_date', 'roll_date']) value[field] ||= ''
    value.frequency = tenorPair(value.frequency)
    value.stub ||= 'short_last'
    if (c.kind === 'nested_schedule') value.sub_frequency = tenorPair(value.sub_frequency)
  }
  if (c.reduction) {
    if (c.window_scope !== 'period') value.window_length = tenorPair(value.window_length)
    value.window_frequency = tenorPair(value.window_frequency)
  }
  value.convention ||= 'none'
  value.settlement_lag ??= 0
  return value
}
export function serializeCalendars(declarations, values, initialDate = '') {
  const explicit = declarations.some(c => c.role === 'initial_fixing')
  return Object.fromEntries(declarations.map(c => {
    const source = values[c.name]
    if (typeof source === 'string' || !source) return [c.name, source || '']
    const value = { ...source }
    for (const key of ['frequency', 'sub_frequency', 'window_length', 'window_frequency']) {
      if (key in value) value[key] = tenorString(value[key])
    }
    if (c.kind !== 'single' && explicit) {
      delete value.start_date
      value.roll_date ||= value.first_observation_date
      value.period_start_date ||= initialDate
    }
    return [c.name, value]
  }))
}
export function fixingDate(declarations, values) {
  const name = declarations.find(c => c.role === 'initial_fixing')?.name
  const value = values[name]
  return typeof value === 'string' ? value : value?.date || ''
}
export function parameterValues(declarations, values, { allowMissing = false } = {}) {
  return Object.fromEntries(declarations.map(p => {
    const raw = Object.hasOwn(values, p.name) ? values[p.name] : p.display_default
    const convert = v => {
      if (v == null || v === '') {
        if (allowMissing) return null
        throw new Error(`Le paramètre ${p.name} est requis.`)
      }
      if (!Number.isFinite(Number(v))) throw new Error(`Le paramètre ${p.name} doit être numérique.`)
      return Number(v) / (p.is_pct ? 100 : 1)
    }
    if (Array.isArray(raw) && !raw.length) throw new Error(`Le paramètre ${p.name} est vide.`)
    return [p.name, Array.isArray(raw) ? raw.map(convert) : convert(raw)]
  }))
}
