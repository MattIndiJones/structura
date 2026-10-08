import { vi } from 'vitest'
import { addMonthsIso } from '../productModels.js'

// HTTP boundary double. Actual holiday calendars and script compilation are
// checked in backend/tests/test_payscript_presets.py.
export function presetServer({ refuse = null, extraParam = false } = {}) {
  const following = iso => {
    const d = new Date(`${iso}T00:00:00Z`)
    while ([0, 6].includes(d.getUTCDay())) d.setUTCDate(d.getUTCDate() + 1)
    return d.toISOString().slice(0, 10)
  }
  return vi.fn(async (url, options) => {
    const body = JSON.parse(options.body)
    if (url === refuse) return { ok: false, json: async () => ({ detail: 'Calendrier indisponible.' }) }
    let data
    if (url === '/api/calendar/resolve') {
      const date = new Date(`${following(body.date)}T00:00:00Z`)
      for (let i = 0; i < (body.business_days || 0); i++) {
        date.setUTCDate(date.getUTCDate() + 1)
        while ([0, 6].includes(date.getUTCDay())) date.setUTCDate(date.getUTCDate() + 1)
      }
      data = { date: date.toISOString().slice(0, 10) }
    } else if (url === '/api/schedule/generate') {
      const step = parseInt(body.frequency) * (body.frequency.endsWith('Y') ? 12 : 1)
      const dates = []
      for (let i = 1; ; i++) {
        const raw = addMonthsIso(body.roll_date, step * i)
        if (raw > body.end_date) break
        dates.push(following(raw))
      }
      data = { dates }
      // Payment assertions use the request's J+3; exact cash dates use the API.
      data.payment_dates = dates.map(d => {
        const day = new Date(`${d}T00:00:00Z`)
        for (let i = 0; i < body.settlement_lag; i++) {
          day.setUTCDate(day.getUTCDate() + 1)
          while ([0, 6].includes(day.getUTCDay())) day.setUTCDate(day.getUTCDate() + 1)
        }
        return day.toISOString().slice(0, 10)
      })
    } else if (url === '/api/parse') {
      data = {
        ok: true,
        params: [...body.script.matchAll(/^PARAM(\(\))?\s+(\w+)$/gm)].map(m => ({
          name: m[2], kind: m[1] ? 'array' : 'scalar', is_pct: true, required: true, display_default: null,
        })),
        constats: [...body.script.matchAll(/^CONSTAT(\(\))?\s+(\w+)$/gm)].map(m => ({
          name: m[2].toUpperCase(), kind: m[1] ? 'schedule' : 'single',
          role: m[2] === 'StartDate' ? 'initial_fixing' : 'observation',
        })),
      }
      if (extraParam) data.params.push({ name: 'NEW_PARAMETER', is_pct: true })
    }
    return { ok: true, json: async () => data }
  })
}
