// Pure labels, classes and formats of the Booking screen, moved out of
// BookingView.vue (P1-10, U3). No state here: the view and its panels import
// them directly.
import { canonicalPayoffFamily } from '../../utils/payoffFamilies.js'
import { productTypeLabel } from '../../data/payscriptTemplates.js'

export function dealHasPortfolio(deal, portfolioId) {
  return (deal.portfolio_ids || []).includes(portfolioId)
}

export const autoExceptionStatuses = new Set([
  'RECEIVED', 'PARTIAL', 'MISSING', 'REJECTED', 'CONTESTED', 'MANUAL_REVIEW_REQUIRED',
])

// Position (%) of a date within the deal's life [value_date → maturity_date]
export function datePct(d, iso) {
  const t0 = new Date(d.value_date).getTime()
  const t1 = new Date(d.maturity_date).getTime()
  if (!iso || t1 <= t0) return null
  const p = ((new Date(iso).getTime() - t0) / (t1 - t0)) * 100
  return Math.max(0, Math.min(100, p))
}

export function eventPct(d, ev) {
  return datePct(d, ev.event_date) ?? 0
}

export function eventDotClass(ev) {
  const map = {
    'observé': 'bg-blue-500 border-blue-400',
    'callé': 'bg-amber-500 border-amber-400',
    'final': 'bg-emerald-500 border-emerald-400',
    'ki': 'bg-red-500 border-red-400',
    'annulé': 'bg-slate-700 border-slate-600 opacity-50',
    'futur': 'bg-slate-900 border-slate-600',
  }
  return map[ev.status] || 'bg-slate-800 border-slate-600'
}

export function eventStatusClass(s) {
  const map = {
    'observé': 'bg-blue-900/40 text-blue-400',
    'callé': 'bg-amber-900/40 text-amber-400',
    'final': 'bg-emerald-900/40 text-emerald-400',
    'ki': 'bg-red-900/40 text-red-400',
    'annulé': 'bg-slate-800 text-slate-500 line-through',
    'futur': 'bg-slate-800 text-slate-500',
  }
  return map[s] || 'bg-slate-800 text-slate-500'
}

export function fixingStatusLabel(status) {
  const labels = {
    EXPECTED: 'Attendu',
    RECEIVED: 'Reçu — exception source',
    VALIDATED: 'Officiel',
    APPLIED: 'Appliqué',
    PARTIAL: 'Incomplet',
    MISSING: 'Manquant',
    REJECTED: 'Rejeté',
    CONTESTED: 'Contesté',
    MANUAL_REVIEW_REQUIRED: 'Exception source',
  }
  return labels[status] || status || 'Inconnu'
}

export function fixingStatusClass(status) {
  if (['VALIDATED', 'APPLIED'].includes(status)) return 'bg-emerald-900/40 text-emerald-400'
  if (status === 'RECEIVED') return 'bg-amber-900/40 text-amber-400'
  if (['PARTIAL', 'MISSING', 'REJECTED', 'CONTESTED', 'MANUAL_REVIEW_REQUIRED'].includes(status)) {
    return 'bg-red-900/40 text-red-400'
  }
  return 'bg-slate-800 text-slate-500'
}

export function operationalEventClass(ev) {
  if (['PARTIAL', 'MISSING', 'REJECTED', 'CONTESTED', 'MANUAL_REVIEW_REQUIRED'].includes(ev.fixing_status)) {
    return 'bg-red-900/40 text-red-400'
  }
  if (ev.fixing_status === 'RECEIVED') return 'bg-amber-900/40 text-amber-400'
  return eventStatusClass(ev.status)
}

export function formatSpot(s) {
  if (!s) return '–'
  return s.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
}

// Terms come in stored units (fractions) — display ×100 with % when is_pct.
// Array params show every per-observation row in AT-date order.
export function formatTerm(t) {
  const one = (x) => t.is_pct ? `${+(x * 100).toFixed(4)}%` : `${+(+x).toFixed(4)}`
  return Array.isArray(t.value) ? t.value.map(one).join(' / ') : one(t.value)
}

export function termBusinessLabel(name = '') {
  const normalized = String(name).toUpperCase()
  // Before the coupon itself: M_CPN_BAR 70 % and COUPON 2 % both read
  // "Coupon" otherwise, side by side on a Phoenix.
  if (/(COUP|CPN).*BAR/.test(normalized)) return 'Barrière de coupon'
  if (/COUP|CPN/.test(normalized)) return 'Coupon'
  if (/AC.*BAR|AUTOCALL/.test(normalized)) return 'Barrière de rappel'
  if (/KI.*BAR|PROTECT/.test(normalized)) return 'Barrière de protection'
  if (/PARTIC/.test(normalized)) return 'Participation'
  if (/CAP/.test(normalized)) return 'Plafond'
  if (/FLOOR/.test(normalized)) return 'Plancher'
  if (/STRIKE/.test(normalized)) return 'Strike'
  return String(name).replace(/^M_/, '').replaceAll('_', ' ').toLowerCase()
    .replace(/^./, char => char.toUpperCase())
}

export function primaryTerms(terms = []) {
  const important = /COUP|CPN|AC.*BAR|AUTOCALL|KI.*BAR|PROTECT|PARTIC|CAP|FLOOR|STRIKE/i
  const ranked = [...terms].sort((a, b) => Number(important.test(b.name)) - Number(important.test(a.name)))
  return ranked.slice(0, 4)
}

export function barrierBusinessLabel(barrier) {
  // The name first for a coupon barrier: WOF >= M_CPN_BAR is an upward
  // monitor, the same kind as the recall — read by kind alone, a Phoenix
  // showed two "Barrière de rappel".
  if (/COUP|CPN/i.test(barrier?.name || '')) return 'Barrière de coupon'
  if (barrier?.kind === 'autocall') return 'Barrière de rappel'
  if (barrier?.kind === 'ki') return 'Barrière de protection'
  return termBusinessLabel(barrier?.name || 'Barrière')
}

// Colour of a signed figure. A class the panel stylesheet owns: a Tailwind
// text-red-400 lost to the scoped `color` of its own element, and a negative
// margin was printed in black.
export function signToneClass(value) {
  return Number(value) >= 0 ? 'tone-pos' : 'tone-neg'
}

export function formatGaugeLevel(value) {
  return `${+Number(value).toFixed(1)}%`
}

export function mtmButtonTitle(deal) {
  return deal.status === 'en_reglement'
    ? 'Valeur actualisée du remboursement connu jusqu’à sa date de paiement'
    : 'Valorise les flux restants du produit vivant à la date du calcul'
}

export function displayEventLabel(label = '') {
  return String(label)
    .replace(/Strike\s*\/\s*Fixing\s*S[₀0]/gi, 'Fixing du strike')
    .replace(/\bS[₀0]\b/g, 'Strike')
}

export function signedNumber(value, decimals = 2) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '–'
  return `${number >= 0 ? '+' : ''}${number.toFixed(decimals)}`
}

export function signedPercent(value, decimals = 1) {
  const formatted = signedNumber(value, decimals)
  return formatted === '–' ? formatted : `${formatted}%`
}

export function alertKindLabel(kind) {
  return {
    'callé': 'rappel', ki: 'KI', final: 'échéance',
    barrier_ki: 'barrière KI', barrier_ac: 'zone rappel',
  }[kind] || kind
}

export function alertChipClass(kind) {
  if (kind === 'ki' || kind === 'barrier_ki') return 'bg-red-900/40 text-red-400'
  if (kind === 'final') return 'bg-emerald-900/40 text-emerald-400'
  return 'bg-amber-900/40 text-amber-400'
}

export function mtmMinDate(deal) {
  if (deal.status === 'en_reglement') return deal.maturity_date || deal.trade_date || undefined
  return deal.trade_date || undefined
}

export function modelBusinessLabel(model) {
  const labels = {
    constant: 'GBM',
    gbm: 'GBM',
    heston: 'Heston',
    sabr: 'SABR',
    local_vol: 'Vol locale',
    localvol: 'Vol locale',
    lsv: 'LSV',
  }
  return labels[String(model || '').toLowerCase()] || model || 'Non renseigné'
}

// Effective market parameters of the MtM run — one compact line so a quoted
// number is never separated from what priced it.
export function marketUsedLabel(mu) {
  if (mu.source === 'known_settlement') {
    const provider = mu.data?.provider === 'YAHOO_FINANCE'
      ? 'Yahoo Finance' : (mu.data?.provider || '')
    return `flux connu · r ${mu.r}% · funding ${mu.funding_spread || 0}% · ${provider}`
  }
  const uls = Object.entries(mu.sigma || {})
    .map(([n, s]) => `${n} σ ${s}%` + (mu.q && mu.q[n] != null ? ` q ${mu.q[n]}%` : ''))
    .join(' · ')
  let corr = ''
  const c = mu.corr || []
  if (c.length === 2) corr = ` · ρ ${(c[0][1] * 100).toFixed(0)}%`
  else if (c.length > 2) {
    let sum = 0, k = 0
    for (let i = 0; i < c.length; i++) for (let j = i + 1; j < c.length; j++) { sum += c[i][j]; k++ }
    corr = ` · ρ̄ ${(sum / k * 100).toFixed(0)}%`
  }
  const model = mu.model === 'constant' ? 'GBM' : mu.model
  let src = mu.source && mu.source.indexOf('realized') === 0
    ? `marché actuel${mu.window_returns ? ` (${mu.window_returns} rendements)` : ''}`
    : 'params booking'
  if (mu.source && mu.source.indexOf('+overrides') >= 0) src += ' + overrides'
  const provider = mu.data?.provider === 'YAHOO_FINANCE'
    ? 'Yahoo Finance' : mu.data?.provider
  const effective = mu.data?.contractual_history?.asof_effective
  const data = provider ? ` · ${provider}${effective ? ` au ${effective}` : ''}` : ''
  return `${uls}${corr} · r ${mu.r}% · ${model} · ${src}${data}`
}

export function queryId(value) {
  const parsed = Number(Array.isArray(value) ? value[0] : value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export const UAT_BATCH_SUFFIX = /\s*\[\d{8}-\d{6}-[A-Z0-9]+\]\s*$/i

export function watchlistProductName(row) {
  const rawName = String(row?.product_name || '')
    .replace(UAT_BATCH_SUFFIX, '')
    .trim()
  if (!rawName) return ''

  const productType = String(row?.product_type || '').trim().toLocaleLowerCase('fr-FR')
  return rawName
    .split(/\s+—\s+/)
    .map(part => part.trim())
    .filter(part => part && (!productType || part.toLocaleLowerCase('fr-FR') !== productType))
    .join(' — ')
}

// Mêmes filtres que l'onglet Deals, sur les axes que porte la watchlist —
// voir composables/useDataFilter.
export const wlFilterFields = [
  { key: 'q', label: 'Recherche', kind: 'text', width: 'min-w-[180px]',
    placeholder: 'Référence, produit, contrepartie…',
    get: w => [w.reference, w.product_name, w.contrepartie] },
  { key: 'contrepartie', label: 'Contrepartie', kind: 'select' },
  { key: 'ticker', label: 'Sous-jacent', kind: 'select',
    get: w => (w.underlyings || []).map(u => u.ticker).filter(Boolean) },
  { key: 'product_type', label: 'Type', kind: 'select' },
]

export const wlColumns = [
  { key: 'reference', label: 'Référence', heading: 'Réf',
    help: "Référence du deal. Cliquez sur la référence d’une ligne pour ouvrir sa fiche ; l’icône ⇥ ouvre le Pricer." },
  { key: 'contrepartie', label: 'Contrepartie',
    help: 'Entité juridique faisant face au deal. Le client commercial éventuel est porté séparément par le filtre de contexte.' },
  { key: 'underlyings', label: 'Sous-jacent',
    get: row => (row.underlyings || []).map(u => u.ticker || u.name).join(' / '),
    help: 'Tri alphabétique sur les sous-jacents tels qu’affichés. Pour un panier, la comparaison commence par le premier sous-jacent.' },
  { key: 'product_name', label: 'Produit', get: watchlistProductName,
    help: 'Tri alphabétique sur le libellé métier affiché. La famille du payoff figure dans Type et l’identifiant technique dans Réf.' },
  { key: 'product_type', label: 'Type', get: row => row.product_type ? productTypeLabel(row.product_type) : '',
    help: 'Tri alphabétique sur le type affiché : Autocall Athena, Phoenix Mémoire, Reverse Convertible…' },
  { key: 'days_to_next', label: 'Prochaine obs.', heading: 'Prochaine obs',
    help: 'Date de la prochaine observation et jours restants. Tri par défaut : de la plus proche à la plus lointaine ; sans observation en dernier.' },
  { key: 'wof', label: 'WOF',
    help: 'Tri numérique sur la performance actuelle du pire sous-jacent par rapport au strike. Le minimum historique entre parenthèses ne sert pas au tri.' },
  { key: 'min_gap', label: 'Barrière la plus proche', heading: 'Barrières',
    help: 'Tri sur la plus petite distance absolue à une barrière, en points du strike : croissant = plus proche d’abord. Les écarts non calculables restent en dernier. La couleur indique séparément le sens favorable ou défavorable.' },
]

// barrierChipClass/barrierGapLabel now live in utils/barriers.js — shared
// with Risk Management's Barrières tab so the color/label convention can't
// diverge between the two.

export const statusOptions = ['actif', 'en_reglement', 'callé', 'échu', 'résilié']

export const _STATUS_ORDER = { actif: 0, en_reglement: 1, 'callé': 2, 'échu': 3 }

export function dealPayoffFamily(deal) {
  return canonicalPayoffFamily(deal.payoff_family || deal.product_type)
    || deal.payoff_family || ''
}

export function pct(n, total) {
  return total ? `${Math.round((n / total) * 100)}%` : '0%'
}

export function statusClass(s) {
  const map = {
    actif: 'badge-positive',
    en_reglement: 'badge-gold',
    'callé': 'badge-gold',
    'échu': 'badge-muted',
    'résilié': 'badge-negative',
  }
  return map[s] || 'badge-muted'
}

export function statusLabel(status) {
  return {
    actif: 'En cours',
    en_reglement: 'En règlement',
    'callé': 'Rappelé',
    'échu': 'Échu',
    'résilié': 'Résilié',
  }[status] || status || 'Statut inconnu'
}

export function describeOutcome(ev) {
  if (!ev) return null
  if (ev.outcome === 'callé') return `Rappel anticipé détecté — ${ev.event_date}`
  if (ev.outcome === 'final') return `Remboursé à maturité (${ev.event_date}) — 100% du nominal`
  if (ev.outcome === 'ki') return `Knock-in à maturité (${ev.event_date}) — ${(ev.maturity_payout * 100).toFixed(1)}% du nominal remboursé`
  if (ev.outcome === 'en_cours') return 'Toujours en vie — aucun rappel ni maturité détecté sur l\'historique disponible'
  return null
}
