// Pure labels, formats and term helpers of the RFQ screen, moved out of
// RfqView.vue (P1-10, U3). No state here: a helper that mutates only acts on
// what it is handed.
import { canonicalPayoffFamily } from '../../utils/payoffFamilies.js'
import { calendarValue, serializeCalendars, fixingDate, tenorString, tenorPair } from '../../utils/payscriptEconomics.js'

// ── CONSTAT calendar helpers — mirror of pricing.js's constatOverrides
// shape/serialization (see RfqParamsEditor.vue's docstring), duplicated
// here rather than imported since pricing.js's version is tangled up with
// that store's own script/parseScript state.
export function syncConstatOverrides(constats, values) {
  const names = new Set(constats.map(c => c.name))
  for (const name of Object.keys(values)) if (!names.has(name)) delete values[name]
  for (const c of constats) values[c.name] = calendarValue(c, values[c.name])
}

export const tenorStr = tenorString

export const parseTenor = tenorPair

export function buildConstatsPayload(constats, values) {
  return serializeCalendars(constats, values, fixingDate(constats, values))
}

export function restoreConstatOverrides(constats, values, saved) {
  for (const c of constats) values[c.name] = calendarValue(c, saved?.[c.name])
}

export const can = (row, right) => !row?.pilot_desk_id || row.access_rights?.includes(right)

export const shareRights = [
  { key: 'read', label: 'Lire' }, { key: 'prepare', label: 'Contribuer / manuel' },
  { key: 'price', label: 'Pricing interne' }, { key: 'select', label: 'Sélectionner' },
  { key: 'solicit', label: 'Solliciter' },
]

export function todayIso() {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}

// addBizDays a disparu avec les dates devinees : il ne comptait que les jours
// de semaine, sans aucun ferie, et servait a proposer une value date a
// strike + 2. Les jours ouvres vivent desormais cote serveur, sur un vrai
// calendrier par devise (core/calendars.py).
export function addYears(isoDate, years) {
  const d = new Date(isoDate)
  d.setDate(d.getDate() + Math.round(years * 365.25))
  return d.toISOString().split('T')[0]
}

// Inverse of addYears (same 365.25-day year) — turns an absolute calendar end
// back into the tenor /api/price expects.
export function yearsBetween(fromIso, toIso) {
  const days = (new Date(toIso) - new Date(fromIso)) / 86400000
  return Math.round((days / 365.25) * 1e4) / 1e4
}

// A tenor derived from a calendar rarely lands round (2.9986 years for a
// 3Y schedule) — display it rounded, price the exact value.
export function fmtTenor(t) {
  return Number.isFinite(t) ? String(Math.round(t * 100) / 100) : t
}

export const normalizedFamily = value => canonicalPayoffFamily(value) || value || ''

export function replaceBasket(target, rows) {
  target.splice(0, target.length, ...rows)
}

export function setCorrelation(target, i, j, raw) {
  const value = Math.max(-1, Math.min(1, Number(raw) || 0))
  const matrix = Array.isArray(target) ? target : target.value
  matrix[i][j] = value
  matrix[j][i] = value
}

// Tri récursif des clés : les termes stockés viennent du serveur, ceux de
// l'éditeur sont reconstruits — sans canonisation, deux objets identiques
// mais différemment ordonnés passeraient pour une modification. Même règle
// que le _normalise() de rfq_controls.py côté serveur.
export function canonical(v) {
  if (Array.isArray(v)) return v.map(canonical)
  if (v && typeof v === 'object') {
    return Object.keys(v).sort().reduce((o, k) => { o[k] = canonical(v[k]); return o }, {})
  }
  return v
}

// Sous-ensemble contractuel — ce que le serveur compare pour décider si les
// termes ont bougé (product_terms). Les hypothèses de modèle en sont exclues.
export function contractualSubset(p) {
  return JSON.stringify(canonical({
    user_params: p.user_params ?? {},
    constats: p.constats ?? {},
    strike_date: p.strike_date ?? null,
    value_date: p.value_date ?? null,
    payment_date: p.payment_date ?? null,
    T: p.T ?? null,
  }))
}

// Une cotation vit quelques heures, pas quelques jours : dès qu'on connaît
// l'heure de réponse, on tient le prix pour valable deux heures. C'est une
// valeur proposée — une validité déjà saisie n'est jamais écrasée, et le
// serveur exige de toute façon une validité postérieure à la réponse
// (api/rfq.py update_quote).
export const DEFAULT_VALIDITY_HOURS = 2

export function withDefaultValidity(q, quotedAtIso, payload) {
  if (quotedAtIso && !q.valid_until) {
    payload.valid_until = new Date(
      new Date(quotedAtIso).getTime() + DEFAULT_VALIDITY_HOURS * 3600_000
    ).toISOString()
  }
  return payload
}

// <input type="datetime-local"> expects "YYYY-MM-DDTHH:mm" in local time.
export function toDatetimeLocal(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// Statuts déduits côté serveur du déroulé de l'AO (api/rfq.py
// _derive_status) — sauf « Bookée » (posé au booking) et « Sans suite »
// (posé à la main : AO abandonné ou perdu).
export const STATUS_LABELS = { draft: 'Brouillon', envoye: 'Envoyée', quote: 'Cotée', retenue: 'Retenue', clos: 'Bookée', sans_suite: 'Sans suite' }

export const STATUS_BADGES = {
  draft:      'bg-slate-800 text-slate-400 border-slate-700',
  sans_suite: 'bg-red-900/40 text-red-300 border-red-900',
  envoye:  'bg-blue-900/50 text-blue-300 border-blue-800',
  quote:   'bg-green-900/50 text-green-400 border-green-800',
  retenue: 'bg-amber-900/50 text-amber-300 border-amber-800',
  clos:    'bg-slate-800 text-slate-500 border-slate-700',
}

export function statusLabel(s) { return STATUS_LABELS[s] || s }

export function statusBadge(s) { return STATUS_BADGES[s] || STATUS_BADGES.draft }

export const KIND_LABELS = { indicatif: 'Indicatif', to_trade: 'To trade' }

export const KIND_BADGES = {
  indicatif: 'bg-slate-800 text-slate-400 border-slate-700',
  to_trade:  'bg-amber-900/40 text-amber-300 border-amber-800',
}

export function kindLabel(k) { return KIND_LABELS[k] || KIND_LABELS.indicatif }

export function kindBadge(k) { return KIND_BADGES[k] || KIND_BADGES.indicatif }

// Notre côté du trade, pas celui de la contrepartie — attention, Deal.sens
// suit la convention INVERSE ("Vente (banque vend)" = nous achetons), d'où
// l'inversion au moment de préremplir le booking (pricing.js:loadFromRfq).
export const SENS_LABELS = { achat: '↓ Achat', vente: '↑ Vente' }

export const SENS_BADGES = {
  achat: 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
  vente: 'bg-blue-900/40 text-blue-300 border-blue-800',
}

export function sensLabel(s) { return SENS_LABELS[s] || SENS_LABELS.achat }

export function sensBadge(s) { return SENS_BADGES[s] || SENS_BADGES.achat }

export function sensHint(s) {
  return s === 'vente'
    ? 'Nous vendons le produit : la meilleure réponse est le prix le PLUS HAUT (on encaisse davantage).'
    : 'Nous achetons le produit aux fournisseurs : la meilleure réponse est le prix le PLUS BAS (on paie moins).'
}

export const SELECTION_REASONS = [
  { value: 'price', label: 'Prix' },
  { value: 'client_request', label: 'Demande du Client' },
  { value: 'documentation', label: 'Documentation / programme' },
  { value: 'credit', label: 'Crédit / contrepartie' },
  { value: 'concentration', label: 'Concentration' },
  { value: 'relationship', label: 'Relation fournisseur' },
  { value: 'execution_quality', label: "Qualité d'exécution" },
  { value: 'other', label: 'Autre' },
]

export function selectionReasonLabel(code) {
  return SELECTION_REASONS.find(reason => reason.value === code)?.label || 'Non renseigné'
}
