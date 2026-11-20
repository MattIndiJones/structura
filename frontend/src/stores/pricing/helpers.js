// Fonctions pures du store, sans état.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.
import { defaultUnderlying } from '../../utils/underlyingDefaults.js'
import { examples } from '../../data/payscriptTemplates.js'
import { reactive } from 'vue'

export const DEFAULT_SCRIPT = examples.autocall_athena

export function _sameNumber(a, b) {
  if (a === '' || a == null || b === '' || b == null) return false
  return Number(a) === Number(b)
}

// frequency/sub_frequency are {value, unit} pairs in the UI (a number input +
// a D/M/Y select) rather than a single "3M"-style text field — _tenorStr()
// combines them into the tenor string the backend expects.
// Une constatation sur période (le script a écrit MIN/MAX/AVG après le nom)
// porte en plus la fenêtre sur laquelle elle réduit : longueur et fréquence
// d'échantillonnage. Ce sont des données de term sheet, pas de payoff — d'où
// leur place ici et non dans le script. `10D` = 10 observations, la date de
// constatation comprise.
export function _defaultWindow(scope = 'length') {
  // Une fenêtre de PÉRIODE n'a pas de longueur — elle court d'une
  // constatation à la suivante — donc seule la fréquence de relevé se saisit.
  return {
    window_length: scope === 'period' ? null : { value: null, unit: 'D' },
    window_frequency: { value: null,
                        unit: scope === 'period' ? 'M' : 'D' },
  }
}

export function _tenorStr(t) {
  return (t && t.value) ? `${t.value}${t.unit}` : null
}

/** Une longueur/fréquence de fenêtre, de la forme serveur "10D" vers {value, unit}. */
export function _restoreTenor(ov, saved, key, fallback) {
  const raw = saved[key]
  if (raw == null) return
  if (!ov[key]) ov[key] = reactive({ ...fallback })
  if (typeof raw === 'object') {
    ov[key].value = raw.value ?? fallback.value
    ov[key].unit  = raw.unit  ?? fallback.unit
  } else {
    const m = String(raw).match(/^(\d+)([DWMY])$/i)
    if (m) { ov[key].value = parseInt(m[1]); ov[key].unit = m[2].toUpperCase() }
  }
}

export function _canonical(value) {
  if (Array.isArray(value)) return value.map(_canonical)
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort()
      .filter(k => value[k] !== undefined)
      .map(k => [k, _canonical(value[k])]))
  }
  return value
}

// ── Maturity ──────────────────────────────────────────────────────
// Decision of 14/09/2026 (M4): the maturity is ALWAYS editable and equals the
// product's last constatation date, whatever the schedules. It replaces the
// 13/09 rule, which locked the field as soon as a schedule existed and kept
// its end — so two years of coupons on a three-year note showed a two-year
// maturity, which booking then refused.

export function _plausibleIsoDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ''))) return false
  const year = Number(String(value).slice(0, 4))
  return year >= 1990 && year <= 2200
}

/** Same arithmetic as booking's `_date_plus_years`: t × 365.25 days. */
export function _datePlusYears(iso, years) {
  const date = new Date(`${iso}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + Math.round(years * 365.25))
  return date.toISOString().slice(0, 10)
}

export function _frDate(iso) {
  const [year, month, day] = String(iso || '').split('-')
  return day ? `${day}/${month}/${year}` : String(iso || '')
}

export function _histVolUrl(tickers, asof = '') {
  const params = new URLSearchParams({
    tickers: tickers.join(','), period: '1y', window_days: '252',
    session_aware: 'true',
  })
  if (asof) params.set('asof', asof)
  return `/api/finance/hist_vol?${params}`
}

// ── Underlyings management ────────────────────────────────────────
// ── Reset / Load from DB ──────────────────────────────────────────
export function _defaultUnderlying(n) {
  return defaultUnderlying(n)
}

export function _localTodayIso() {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
    .toISOString().slice(0, 10)
}

/**
 * Le contexte courant, avec les sous-jacents dans la forme d'INSTANTANÉ.
 *
 * La fiche brute de l'écran ne porte pas sa courbe de dividende : celle-ci se
 * DÉRIVE de `q` et du taux de décroissance, et seulement si la courbe est
 * activée. Un titre ajouté à une note neuve arriverait donc au moteur sans
 * dividende, avec un prix parfaitement plausible.
 *
 * On la dérive donc ici, dans la forme que `_engine_underlyings` sait relire
 * côté serveur — celle que produit déjà `_snapshot_underlying` pour la
 * valorisation en cours de vie. C'est ce qui permet au serveur de n'avoir
 * QU'UN convertisseur : une seconde voie, même soignée, finit toujours par
 * perdre un champ que la première gère.
 */
/** Les entrées d'une table de surcharges dont le nom est encore déclaré. */
export function _declares(surcharges, declarations) {
  const noms = new Set(declarations.map(d => d.name))
  return Object.fromEntries(
    Object.entries(surcharges).filter(([nom]) => noms.has(nom)))
}

// Les clés d'un objet JSON n'ont pas d'ordre garanti, et `removed` est une
// liste dont l'ordre ne porte rien : sans tri, deux deltas identiques
// paraîtraient différents et l'écran annoncerait des modifications fantômes.
export function _trie(d) {
  return {
    set: Object.fromEntries(Object.entries(d.set || {}).sort()),
    removed: [...(d.removed || [])].sort(),
  }
}
