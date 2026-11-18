// Régime de valorisation (pré-strike, en cours de vie) et maturité.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.
import { apiFetch } from '../../utils/api.js'
import { calendarPolicy } from '../../utils/payscriptEconomics.js'
import { computed, reactive, ref, watch } from 'vue'
import { _datePlusYears, _frDate, _plausibleIsoDate } from './helpers.js'

export function installDates(s) {
  const {
    _activeBookedContract, constatOverrides, contractTermsLocked, currentProduct,
    currentRfqId, globalParams, scriptAtDates, scriptConstats, scriptHasMaturityEvent,
  } = s

  // ── Price ─────────────────────────────────────────────────────────
  /** Vrai quand la date de valorisation demande un rejeu du passé. */
  function isInLife() {
    const v = globalParams.valuation_date
    return !!(v && globalParams.strike_date && v > globalParams.strike_date)
  }

  function isPreStrike() {
    const v = globalParams.valuation_date
    return !!(v && globalParams.strike_date && v < globalParams.strike_date)
  }

  function usesDatedPricing() {
    return isInLife() || isPreStrike()
  }

  // A constatation falling on a closed day moves by its convention, and
  // booking compares the maturity with the ADJUSTED dates. The adjustment
  // comes from the currency calendar, server side; until it is known, the
  // typed date stands for the effective one.
  const _effectiveDates = reactive({})
  const _effectiveFailures = new Set()
  const _effectiveInFlight = new Set()

  function _effectiveKey(date, convention, policy = {}) {
    return JSON.stringify({ currency: globalParams.deal_ccy || 'EUR', convention, date, ...policy })
  }

  function _effectiveDate(date, convention, policy) {
    if (!date || !convention || convention === 'none') return date
    return _effectiveDates[_effectiveKey(date, convention, policy)] || date
  }

  async function _resolveEffectiveDate(key) {
    if (key in _effectiveDates || _effectiveFailures.has(key) || _effectiveInFlight.has(key)) return
    const request = JSON.parse(key)
    _effectiveInFlight.add(key)
    try {
      const res = await apiFetch('/api/calendar/resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      })
      const data = res?.ok ? await res.json() : null
      if (data && _plausibleIsoDate(data.date)) _effectiveDates[key] = data.date
      else _effectiveFailures.add(key)
    } catch {
      _effectiveFailures.add(key)
    } finally {
      _effectiveInFlight.delete(key)
    }
  }

  /**
   * The product's dated constatations, each with its last date.
   *
   * Every CONSTAT counts — schedules and single dates alike — except
   * `STRIKE_FIX`, which fixes the initial level: it is a departure window.
   * No recognition by the name `MATURITE` any more: the terminal
   * constatation is computed.
   */
  function _datedConstats() {
    const out = []
    for (const c of scriptConstats.value) {
      if (c.name === 'STRIKE_FIX' || c.role === 'initial_fixing') continue
      const value = constatOverrides[c.name]
      let raw = ''
      let convention = 'none'
      if (c.kind === 'single') {
        raw = typeof value === 'string' ? value : (value?.date || '')
        if (value && typeof value === 'object') convention = value.convention || 'none'
      } else if (value && typeof value === 'object') {
        raw = value.end_date || ''
        convention = value.convention || 'none'
      }
      if (raw) out.push({ name: c.name, kind: c.kind, raw, convention,
                          policy: calendarPolicy(value), date: _effectiveDate(raw, convention, calendarPolicy(value)) })
    }
    return out
  }

  /** The script's `AT` years, dated from the strike. */
  function _atEventDates() {
    const strike = globalParams.strike_date
    if (!_plausibleIsoDate(strike)) return []
    return scriptAtDates.value
      .filter(t => Number.isFinite(Number(t)) && Number(t) > 0)
      .map(t => ({ t: Number(t), date: _datePlusYears(strike, Number(t)) }))
  }

  function _maturityDate() {
    const retained = _activeBookedContract()?.maturity_date || (contractTermsLocked.value ? currentProduct.value?.terms?.maturity_date : null)
    if (retained) return retained
    const constatDates = _datedConstats().map(entry => entry.date)
    const dates = [...constatDates, ..._atEventDates().map(entry => entry.date)]
    // `AT MATURITY` has no date of its own: it carries the Maturity field's.
    // Without that block, the field only speaks for a product that has no
    // dated constatation yet.
    if (scriptHasMaturityEvent.value || !constatDates.length) {
      // Historical fallback on strike + T, for a script without any calendar
      // only: with a calendar, T is derived from the maturity and carries no
      // information of its own.
      const declared = globalParams.maturity_date
        || (!constatDates.length && _plausibleIsoDate(globalParams.strike_date) && globalParams.T
          ? _datePlusYears(globalParams.strike_date, globalParams.T) : '')
      if (declared) dates.push(declared)
    }
    if (!dates.length) return null
    return dates.reduce((a, b) => (b > a ? b : a))
  }

  // Une source unique pour l'affichage Economics et le payload de booking.
  // Dupliquer cette dérivation dans deux composants ferait tôt ou tard
  // diverger la date affichée de celle effectivement figée sur le deal.
  const maturityDate = computed(() => _maturityDate() || '')

  const maturityDateEditable = computed(() => !contractTermsLocked.value)
  // Why the last typed maturity was refused, worded for the screen. Empty
  // while nothing has been refused.
  const maturityError = ref('')

  watch(() => JSON.stringify(_datedConstats()
    .filter(entry => entry.convention !== 'none' && _plausibleIsoDate(entry.raw))
    .map(entry => _effectiveKey(entry.raw, entry.convention, entry.policy))),
  keys => { if (!contractTermsLocked.value) for (const key of JSON.parse(keys)) _resolveEffectiveDate(key) })

  function syncTenorFromMaturity() {
    // Une RFQ porte le tenor effectivement cote. Son echeancier peut finir un
    // week-end puis etre ajuste au jour ouvre suivant pour le pricing :
    // recalculer T depuis cette date effective transforme alors, a tort, le
    // meme contrat en un tenor different et le booking est refuse. Depuis une
    // RFQ, les termes restent ceux de l'AO ; tout autre produit doit passer par
    // une nouvelle RFQ.
    if (currentRfqId.value) return
    const maturity = _maturityDate()
    if (!maturity || !globalParams.strike_date) return
    const start = new Date(`${globalParams.strike_date}T00:00:00Z`)
    const end = new Date(`${maturity}T00:00:00Z`)
    const days = Math.round((end - start) / 86400000)
    if (Number.isFinite(days) && days > 0) {
      globalParams.T = Math.round((days / 365.25) * 1e6) / 1e6
    }
  }

  /**
   * Moves the maturity. Returns true when the date is accepted.
   *
   * Only the TERMINAL constatations move, those that fell on the old
   * maturity: a schedule's end (and its roll date when aligned on it), a
   * single CONSTAT's date with its window. A schedule ending earlier stays
   * put — two years of coupons on a three-year note remain expressible.
   *
   * Refused, with a message naming the obstacle:
   * - before the end of a non-terminal schedule (M12);
   * - before the last `AT` year written in the script (Normal mode).
   */
  function setMaturityDate(value) {
    if (contractTermsLocked.value) return false
    maturityError.value = ''
    if (!value) {
      // Field cleared: no calendar date is erased, only the declared
      // maturity is dropped.
      globalParams.maturity_date = ''
      syncTenorFromMaturity()
      return true
    }
    if (!_plausibleIsoDate(value)) {
      maturityError.value = `Date de maturité invalide : ${value}.`
      return false
    }
    const previous = _maturityDate()
    const entries = _datedConstats()
    const terminal = entries.filter(entry =>
      previous && (entry.date === previous || entry.raw === previous))
    const blocking = entries
      .filter(entry => !terminal.includes(entry) && entry.date > value)
      .sort((a, b) => (a.date < b.date ? 1 : -1))[0]
    if (blocking) {
      maturityError.value = blocking.kind === 'single'
        ? `Maturité refusée : la constatation ${blocking.name} tombe le ${_frDate(blocking.date)}, `
          + `après le ${_frDate(value)}. Avancez-la d'abord.`
        : `Maturité refusée : l'échéancier ${blocking.name} se termine le ${_frDate(blocking.date)}, `
          + `après le ${_frDate(value)}. Avancez d'abord sa date de fin.`
      return false
    }
    const lastAt = _atEventDates().reduce((a, b) => (!a || b.date > a.date ? b : a), null)
    if (lastAt && lastAt.date > value) {
      maturityError.value = `Maturité refusée : le script observe encore à ${lastAt.t} an(s) `
        + `(AT ${lastAt.t}), soit le ${_frDate(lastAt.date)}. Modifiez les dates AT du script.`
      return false
    }
    for (const entry of terminal) {
      const current = constatOverrides[entry.name]
      if (entry.kind === 'single') {
        if (typeof current === 'string') constatOverrides[entry.name] = value
        else if (current && typeof current === 'object') current.date = value
      } else if (current && typeof current === 'object') {
        if (current.roll_date === current.end_date) current.roll_date = value
        current.end_date = value
      }
    }
    globalParams.maturity_date = value
    syncTenorFromMaturity()
    return true
  }

  Object.assign(s, { isInLife, isPreStrike, usesDatedPricing, _effectiveDates, _effectiveFailures, _effectiveInFlight, _effectiveKey, _effectiveDate, _resolveEffectiveDate, _datedConstats, _atEventDates, _maturityDate, maturityDate, maturityDateEditable, maturityError, syncTenorFromMaturity, setMaturityDate })
}
