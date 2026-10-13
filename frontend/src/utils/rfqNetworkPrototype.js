// In-memory lot 0 prototype. No API, storage, pricing engine or real execution.
import { findProductModel } from './productModels.js'

export const PROTOTYPE_BANKS = [
  { id: 'bank-a', name: 'Banque A', desk: 'Structuration', modelPrice: 98.2 },
  { id: 'bank-b', name: 'Banque B', desk: 'Structuration', modelPrice: 98.65 },
]

export function createRfqPrototype() {
  const model = findProductModel('autocall_athena')
  return {
    now: '2026-10-12T12:45:00.000Z',
    deadline: '2026-10-12T13:00:00.000Z',
    request: null,
    terms: {
      template: { id: model.key, version: model.version, script: model.script },
      parameters: { COUPON: { value: 0.08, unit: 'fraction' }, M_AC_BAR: { value: 1, unit: 'fraction' }, M_KI_BAR: { value: 0.6, unit: 'fraction' } },
      underlyings: [{ id: 'FR0000121014', name: 'LVMH', ticker: 'MC.PA', venue: 'XPAR', currency: 'EUR' }],
      dates: { strike: '2026-10-12', value: '2026-10-14', maturity: '2029-10-12', payment: '2029-10-17' },
      calendar: { business_calendar: 'TARGET', convention: 'FOLLOWING', settlement_lag_business_days: 3,
        observations: ['2027-10-12', '2028-10-12', '2029-10-12'], payments: ['2027-10-15', '2028-10-17', '2029-10-17'] },
      fixing: { convention: 'Clôture officielle XPAR', initial_levels: null },
    },
    banks: PROTOTYPE_BANKS.map(bank => ({ ...bank, status: 'NOT_SENT', secondValidation: false,
      calculated: false, calculatedAt: null, freshnessMinutes: 10,
      draft: { price: Number((bank.modelPrice + 0.15).toFixed(2)), firmness: 'FIRM', validityMinutes: 5, conditions: '' },
      review: null, awaitingReview: false })),
    quotes: [], selectedId: null, agreement: null, booking: null, events: [], sequence: 0,
  }
}

function requireThat(condition, message) {
  if (!condition) throw new Error(message)
}

function record(state, type, party, label) {
  state.events.push({ id: ++state.sequence, time: state.now, type, party, label })
}

function validateDraft(draft) {
  requireThat(Number.isFinite(draft.price) && draft.price > 0, 'Le prix doit être un nombre positif en % du nominal.')
  requireThat(['FIRM', 'INDICATIVE'].includes(draft.firmness), 'Indiquer la fermeté de la réponse.')
  requireThat(Number.isInteger(draft.validityMinutes) && draft.validityMinutes > 0 && draft.validityMinutes <= 60,
    'La validité de cet exercice doit être comprise entre 1 et 60 minutes.')
  requireThat(typeof draft.conditions === 'string', 'Indiquer les conditions ou leur absence.')
}

export function prototypeQuoteStatus(quote, now) {
  if (quote.status === 'ACTIVE' && Date.parse(now) >= Date.parse(quote.validUntil)) return 'EXPIRED'
  return quote.status
}

export function prototypeCanSelect(quote, now) {
  return prototypeQuoteStatus(quote, now) === 'ACTIVE'
}

export function prototypeBestQuoteIds(state) {
  const eligible = state.quotes.filter(quote => prototypeCanSelect(quote, state.now) && quote.firmness === 'FIRM' && !quote.conditions)
  if (!eligible.length) return []
  const best = (state.request.side === 'BUY' ? Math.min : Math.max)(...eligible.map(quote => quote.price))
  return eligible.filter(quote => quote.price === best).map(quote => quote.id)
}

export function prototypeRequestForBank(state, bankId) {
  if (!state.request || !state.request.recipients.includes(bankId)) return null
  const { recipients, ...request } = state.request
  const bank = state.banks.find(item => item.id === bankId)
  return { ...structuredClone(request), message_id: `${request.id}:${bankId}`, recipient: { organization: bank.name, desk: bank.desk } }
}

export function prototypeEvents(state, bankId = null) {
  const privateTypes = ['PRIVATE_CALCULATION', 'DRAFT_CHANGED', 'POLICY_CHANGED', 'REVIEW_REQUESTED', 'VALIDATED']
  return state.events.filter(event => bankId ? event.party === bankId : !privateTypes.includes(event.type))
}

function addQuote(state, { bankId = null, provider, draft, contact }) {
  const previous = state.quotes.filter(quote => bankId ? quote.bankId === bankId : quote.origin === 'MANUAL')
  requireThat(!previous.some(quote => ['RESERVED', 'CONFIRMED'].includes(quote.status)),
    'Le prix est déjà réservé au traitement : aucune révision RFQ ordinaire.')
  for (const quote of previous) if (prototypeQuoteStatus(quote, state.now) === 'ACTIVE') quote.status = 'REPLACED'
  const quote = {
    id: `DEMO-Q-${++state.sequence}`, revision: previous.length + 1, replaces: previous.at(-1)?.id || null,
    bankId, provider, contact, origin: bankId ? 'NETWORK' : 'MANUAL',
    requester: structuredClone(state.request.sender),
    respondent: { organization: provider, legal_entity: `${provider} démo`, desk: bankId ? 'Structuration' : null },
    issuer: `${provider} démo`, guarantor: null,
    dates: structuredClone(state.terms.dates), publishedBy: bankId ? 'Publieur bancaire démo' : 'Utilisateur demandeur démo',
    requestId: state.request.id, round: state.request.round, termsVersion: state.request.terms_version,
    termsFingerprint: state.request.terms_fingerprint, price: draft.price, unit: 'PERCENT_OF_NOTIONAL',
    notional: state.request.notional, currency: state.request.currency, side: state.request.side,
    firmness: draft.firmness, conditions: draft.conditions.trim(), status: 'ACTIVE',
    publishedAt: state.now, receivedAt: state.now,
    validUntil: new Date(Date.parse(state.now) + draft.validityMinutes * 60_000).toISOString(),
  }
  state.quotes.push(quote)
  const displayedPrice = quote.price.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (bankId) {
    record(state, 'QUOTE_PUBLISHED', bankId, `${provider} : réponse v${quote.revision} publiée à ${displayedPrice} %.`)
    record(state, 'QUOTE_RECEIVED', bankId, `${provider} : réponse enregistrée chez le demandeur.`)
  } else {
    record(state, 'MANUAL_QUOTE_RECORDED', null, `${provider} : réponse saisie manuellement à ${displayedPrice} %, interlocuteur ${contact}.`)
  }
  return quote
}

// Every action returns a fresh state; a rejected action leaves its input intact.
// These transitions illustrate the specification, not production authorization.
export async function applyRfqPrototypeAction(input, action) {
  const state = structuredClone(input)
  const bank = action.bankId ? state.banks.find(item => item.id === action.bankId) : null
  if (action.bankId) requireThat(bank, 'Banque inconnue dans cet exercice.')
  if (['CALCULATE', 'SAVE_DRAFT', 'VALIDATE', 'PUBLISH', 'DECLINE', 'SECOND_VALIDATION'].includes(action.type)) {
    requireThat(state.request && state.request.recipients.includes(bank.id), 'Cette banque n’a pas reçu la demande.')
    requireThat(bank.status !== 'DECLINED', 'Cette banque a décliné ; recommencer l’exercice pour une nouvelle consultation.')
  }
  switch (action.type) {
    case 'SEND': {
      requireThat(!state.request, 'La demande est déjà envoyée ; sa retransmission ne crée pas un nouveau tour.')
      requireThat(Array.isArray(action.bankIds) && action.bankIds.length > 0, 'Choisir au moins une banque destinataire.')
      requireThat(new Set(action.bankIds).size === action.bankIds.length && action.bankIds.every(id => state.banks.some(item => item.id === id)),
        'La liste contient un destinataire non autorisé ou un doublon.')
      requireThat(Number.isFinite(action.notional) && action.notional > 0, 'Le nominal doit être positif.')
      requireThat(['BUY', 'SELL'].includes(action.side), 'Indiquer le sens du demandeur.')
      requireThat(Date.parse(state.now) < Date.parse(state.deadline), 'Le délai de réponse est dépassé.')
      const bytes = new TextEncoder().encode(JSON.stringify(state.terms))
      const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes)
      const fingerprint = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
      state.request = { id: 'DEMO-RFQ-001', message_type: 'RFQ_REQUEST', format_version: 1, round: 1,
        terms_version: 1, terms_fingerprint: fingerprint, sender: { organization: 'ClientTech démo', desk: 'Sales', legal_entity: 'ClientTech démo' },
        title: 'Athena LVMH 3 ans — coupon 8 %', kind: 'TO_TRADE', side: action.side,
        notional: action.notional, currency: 'EUR', price_unit: 'PERCENT_OF_NOTIONAL', price_convention: 'ALL_IN',
        instrument_family: 'NOTE', transaction_format: 'EMTN', documentation: 'Documentation fictive du pilote',
        published_at: state.now, response_deadline: state.deadline, terms: structuredClone(state.terms), recipients: [...action.bankIds] }
      for (const id of action.bankIds) {
        const recipient = state.banks.find(item => item.id === id)
        recipient.status = 'RECEIVED'
        record(state, 'REQUEST_SENT', id, `Demande envoyée à ${recipient.name} ; termes v1 figés.`)
        record(state, 'REQUEST_RECEIVED', id, `${recipient.name} : demande enregistrée ; aucune cotation reçue.`)
      }
      break
    }
    case 'CALCULATE':
      bank.calculated = true
      bank.calculatedAt = state.now
      bank.review = null
      bank.awaitingReview = false
      record(state, 'PRIVATE_CALCULATION', bank.id, 'Calcul fictif préparé ; résultat conservé dans l’espace bancaire privé.')
      break
    case 'SAVE_DRAFT':
      validateDraft(action.draft)
      bank.draft = { ...action.draft }
      bank.review = null
      bank.awaitingReview = false
      record(state, 'DRAFT_CHANGED', bank.id, 'Préparation modifiée ; contrôle à refaire. Aucun prix transmis.')
      break
    case 'SECOND_VALIDATION':
      bank.secondValidation = !!action.enabled
      bank.review = null
      bank.awaitingReview = false
      record(state, 'POLICY_CHANGED', bank.id, `Seconde validation ${bank.secondValidation ? 'activée' : 'désactivée'} dans cet exercice.`)
      break
    case 'VALIDATE':
      requireThat(bank.calculated, 'Préparer le calcul fictif avant le contrôle.')
      validateDraft(bank.draft)
      requireThat(['PREPARER', 'CHECKER'].includes(action.actor), 'Choisir un intervenant pour le contrôle.')
      if (bank.secondValidation && action.actor === 'PREPARER') {
        bank.awaitingReview = true
        record(state, 'REVIEW_REQUESTED', bank.id, 'Préparation soumise à un second validateur ; aucun prix transmis.')
      } else {
        requireThat(!bank.secondValidation || bank.awaitingReview, 'Soumettre la préparation avant sa seconde validation.')
        bank.review = { actor: action.actor, content: JSON.stringify(bank.draft) }
        bank.awaitingReview = false
        record(state, 'VALIDATED', bank.id, `Prix contrôlé par ${action.actor === 'CHECKER' ? 'le second validateur' : 'le préparateur habilité'}.`)
      }
      break
    case 'PUBLISH':
      requireThat(Date.parse(state.now) < Date.parse(state.deadline), 'Le délai de publication des réponses est dépassé.')
      requireThat(bank.calculated && bank.review?.content === JSON.stringify(bank.draft), 'Le contenu exact doit être contrôlé avant publication.')
      requireThat(Date.parse(state.now) - Date.parse(bank.calculatedAt) <= bank.freshnessMinutes * 60_000, 'Le calcul fictif est trop ancien : préparer puis contrôler un nouveau calcul.')
      requireThat(!bank.secondValidation || bank.review.actor === 'CHECKER', 'La seconde validation est nécessaire.')
      if (bank.review.publishedQuoteId) return state
      validateDraft(bank.draft)
      bank.review.publishedQuoteId = addQuote(state, { bankId: bank.id, provider: bank.name, draft: bank.draft, contact: 'Contact bancaire démo' }).id
      bank.status = 'QUOTED'
      break
    case 'DECLINE':
      requireThat(!state.quotes.some(quote => quote.bankId === bank.id), 'Une réponse publiée doit faire l’objet d’un retrait explicite.')
      bank.status = 'DECLINED'
      record(state, 'DECLINED', bank.id, `${bank.name} : déclin, sans prix et sans motif commercial communiqué.`)
      break
    case 'MANUAL':
      requireThat(state.request, 'Envoyer la consultation fictive avant de saisir sa réponse manuelle.')
      validateDraft(action.draft)
      requireThat(action.contact?.trim(), 'Renseigner l’interlocuteur de la réponse manuelle.')
      addQuote(state, { provider: 'Partenaire manuel', draft: action.draft, contact: action.contact.trim() })
      break
    case 'SELECT': {
      requireThat(!state.agreement, 'Un traitement est déjà demandé ; ne pas déplacer la sélection.')
      const quote = state.quotes.find(item => item.id === action.quoteId)
      requireThat(quote && prototypeCanSelect(quote, state.now), 'Cette réponse n’est plus active.')
      state.selectedId = quote.id
      record(state, 'SELECTED', null, `Réponse de ${quote.provider} retenue localement ; aucun traitement demandé.`)
      break
    }
    case 'WITHDRAW': {
      const quote = state.quotes.find(item => item.id === action.quoteId)
      requireThat(quote && quote.bankId === bank?.id, 'Cette réponse ne relève pas de la banque sélectionnée.')
      requireThat(!['RESERVED', 'CONFIRMED'].includes(quote.status), 'Acceptation reçue : prix réservé, retrait RFQ ordinaire refusé.')
      requireThat(prototypeQuoteStatus(quote, state.now) === 'ACTIVE', 'Cette réponse n’est plus active.')
      requireThat(action.reason?.trim(), 'Le motif de retrait est obligatoire.')
      quote.status = 'WITHDRAWN'
      record(state, 'WITHDRAWN', bank.id, `${bank.name} : retrait notifié — ${action.reason.trim()}`)
      break
    }
    case 'ACCEPT': {
      requireThat(!state.agreement, 'Un traitement est déjà demandé ; attendre son résultat.')
      const quote = state.quotes.find(item => item.id === state.selectedId)
      requireThat(quote && prototypeCanSelect(quote, state.now), 'La réponse sélectionnée est expirée, retirée ou remplacée.')
      requireThat(quote.firmness === 'FIRM', 'Une cotation indicative exige un nouvel accord de prix ; elle ne réserve pas le prix publié.')
      requireThat(!quote.conditions, 'Les conditions doivent être résolues avant une acceptation conforme.')
      requireThat(quote.termsFingerprint === state.request.terms_fingerprint && quote.termsVersion === state.request.terms_version,
        'La cotation porte sur une autre version des termes.')
      quote.status = 'RESERVED'
      state.agreement = { status: 'REQUESTED', quote: structuredClone(quote), acceptedAt: state.now,
        confirmedAt: null, source: null, contact: null, executionReference: null, writtenFollowUp: false }
      record(state, 'ACCEPTED', quote.bankId, 'Acceptation reçue simulée : prix réservé ; confirmation de traitement attendue.')
      break
    }
    case 'CONFIRM':
      requireThat(state.agreement?.status === 'REQUESTED', 'Un traitement demandé doit précéder sa confirmation.')
      requireThat(['BANK_MESSAGE', 'PHONE_DECLARED'].includes(action.source), 'Indiquer la source de confirmation.')
      requireThat(action.contact?.trim() && action.executionReference?.trim(), 'Interlocuteur bancaire et référence d’exécution obligatoires.')
      Object.assign(state.agreement, { status: 'CONFIRMED', confirmedAt: state.now, source: action.source,
        contact: action.contact.trim(), executionReference: action.executionReference.trim(), writtenFollowUp: action.source === 'PHONE_DECLARED' })
      state.quotes.find(quote => quote.id === state.selectedId).status = 'CONFIRMED'
      record(state, 'CONFIRMED', state.agreement.quote.bankId,
        action.source === 'PHONE_DECLARED' ? 'Accord téléphonique déclaré ; confirmation écrite à suivre.' : 'Confirmation reçue de la banque, simulée dans cet exercice.')
      break
    case 'BOOK':
      requireThat(state.agreement?.status === 'CONFIRMED', 'La confirmation économique doit précéder le booking.')
      if (state.booking) return state
      state.booking = { reference: 'DEMO-DEAL-001', executionReference: state.agreement.executionReference, bookedAt: state.now }
      record(state, 'BOOKED', null, 'Booking local simulé sur l’accord figé ; aucune inscription dans les books réels.')
      break
    case 'ADVANCE':
      requireThat(Number.isInteger(action.minutes) && action.minutes > 0 && action.minutes <= 60, 'Avancer l’horloge de 1 à 60 minutes.')
      state.now = new Date(Date.parse(state.now) + action.minutes * 60_000).toISOString()
      record(state, 'CLOCK_ADVANCED', null, `Horloge de l’exercice avancée de ${action.minutes} minute(s).`)
      break
    default:
      throw new Error('Action inconnue dans ce prototype.')
  }
  return state
}
