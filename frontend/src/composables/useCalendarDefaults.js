import { computed, reactive, watch } from 'vue'

const states = new WeakMap()
const BANK_CODES = new Set(['EUR', 'USD', 'GBP', 'CHF', 'JPY', 'SGD'])
const SUFFIX_VENUES = { MI: 'XMIL', PA: 'XPAR', DE: 'XETR', SW: 'SIX', T: 'JPX', HK: 'HKEX', SI: 'SGX' }
const EXCHANGE_VENUES = { MIL: 'XMIL', PAR: 'XPAR', GER: 'XETR', EBS: 'SIX', JPX: 'JPX', TYO: 'JPX',
  HKG: 'HKEX', SES: 'SGX', NYQ: 'NYSE', NMS: 'NASDAQ', NGM: 'NASDAQ', NCM: 'NASDAQ' }

export const CALENDAR_LABELS = { XMIL: 'Milan', XPAR: 'Paris', TARGET: 'EUR / TARGET', EUR: 'EUR / TARGET',
  NYSE: 'New York — NYSE', NASDAQ: 'New York — Nasdaq', XETR: 'Francfort — Xetra', SIX: 'Suisse — SIX',
  JPX: 'Tokyo', HKEX: 'Hong Kong', SGX: 'Singapour' }

export function suggestedCalendars(underlyings, currency) {
  const bank = BANK_CODES.has(currency) ? (currency === 'EUR' ? 'TARGET' : currency) : null
  const tickers = underlyings.filter(u => u.ticker?.trim())
  const unresolved = [], observation = []
  for (const underlying of tickers) {
    const ticker = underlying.ticker.trim().toUpperCase()
    const venue = EXCHANGE_VENUES[underlying.exchange] || SUFFIX_VENUES[ticker.split('.').at(-1)]
    if (venue) observation.push(venue)
    else unresolved.push(ticker)
  }
  if ((!tickers.length || unresolved.length) && bank) observation.push(bank)
  return { observation: [...new Set(observation)], settlement: bank ? [bank] : [],
    approximation: !tickers.length || unresolved.length > 0, unresolved }
}

export function calendarDefaultState(values) {
    if (!states.has(values)) states.set(values, reactive(Object.fromEntries(
      ['observation', 'settlement'].map(purpose => [purpose, {
        automatic: !Object.hasOwn(values, `${purpose}_calendars`), last: null,
      }]))))
    return states.get(values)
}

export const hasCalendarDefaultState = values => states.has(values)
export function registerCalendarDefaults(values, automatic = true) {
  const state = calendarDefaultState(values)
  for (const purpose of ['observation', 'settlement']) {
    state[purpose].automatic = automatic && !Object.hasOwn(values, `${purpose}_calendars`)
    state[purpose].last = null
  }
}

export function syncCalendarDefault(values, suggested, purpose, frozen = false) {
    if (frozen) return
    const signature = () => JSON.stringify([values[`${purpose}_calendars`], values[`${purpose}_join`]])
    const control = calendarDefaultState(values)[purpose]
    if (!control.automatic) {
      if (values[`${purpose}_calendars`]?.length === 1 && !values[`${purpose}_join`])
        values[`${purpose}_join`] = 'all_open'
      return
    }
    if (control.last !== null && control.last !== signature()) { control.automatic = false; return }
    const target = JSON.stringify([suggested[purpose], 'all_open'])
    if (signature() !== target) {
      values[`${purpose}_calendars`] = [...suggested[purpose]]
      values[`${purpose}_join`] = 'all_open'
    }
    control.last = signature()
}

export function useCalendarDefaults(props) {
  const suggested = computed(() => suggestedCalendars(props.underlyings || [], props.currency))
  const state = computed(() => calendarDefaultState(props.values))
  function apply(purpose) {
    syncCalendarDefault(props.values, suggested.value, purpose, props.frozen)
  }
  watch(() => [props.values, props.currency, suggested.value, props.frozen], () => {
    for (const purpose of ['observation', 'settlement']) apply(purpose)
  }, { immediate: true })
  function reset(purpose) {
    if (props.frozen) return
    state.value[purpose].automatic = true; state.value[purpose].last = null; apply(purpose)
  }
  function customize(purpose, codes) {
    if (props.frozen) return
    state.value[purpose].automatic = false
    props.values[`${purpose}_calendars`] = codes
    props.values[`${purpose}_join`] ||= 'all_open'
  }
  return { suggested, state, reset, customize }
}
