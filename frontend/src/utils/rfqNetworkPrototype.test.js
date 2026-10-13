import { createHash } from 'node:crypto'
import { describe, expect, it } from 'vitest'
import { applyRfqPrototypeAction as act, createRfqPrototype, prototypeBestQuoteIds,
  prototypeCanSelect, prototypeEvents, prototypeQuoteStatus, prototypeRequestForBank } from './rfqNetworkPrototype.js'

const send = (state = createRfqPrototype(), side = 'BUY') => act(state, { type: 'SEND', bankIds: ['bank-a', 'bank-b'], notional: 1_000_000, side })
async function publish(state, bankId = 'bank-a', draft = null) {
  let next = await act(state, { type: 'CALCULATE', bankId })
  if (draft) next = await act(next, { type: 'SAVE_DRAFT', bankId, draft })
  next = await act(next, { type: 'VALIDATE', bankId, actor: 'PREPARER' })
  return act(next, { type: 'PUBLISH', bankId })
}
async function accept(state) {
  const next = await act(state, { type: 'SELECT', quoteId: state.quotes[0].id })
  return act(next, { type: 'ACCEPT' })
}
const confirmation = { type: 'CONFIRM', source: 'BANK_MESSAGE', contact: 'Contact démo', executionReference: 'DEMO-EXEC-001' }

describe('demandes et publications du prototype RFQ', () => {
  it('ne sollicite aucune banque avant l’envoi explicite', () => {
    const state = createRfqPrototype()
    expect(prototypeRequestForBank(state, 'bank-a')).toBeNull()
    expect(state.quotes).toEqual([])
    expect(state.events).toEqual([])
  })
  it('communique les mêmes termes, une empreinte SHA-256 et aucune concurrence ou hypothèse privée', async () => {
    const state = await send()
    const first = prototypeRequestForBank(state, 'bank-a')
    const second = prototypeRequestForBank(state, 'bank-b')
    expect(first.terms).toEqual(second.terms)
    expect(first.terms_fingerprint).toBe(createHash('sha256').update(JSON.stringify(state.terms)).digest('hex'))
    expect(first.message_id).not.toBe(second.message_id)
    expect(first).not.toHaveProperty('recipients')
    expect(first).not.toHaveProperty('modelPrice')
    expect(first.terms.parameters.COUPON).toEqual({ value: 0.08, unit: 'fraction' })
    first.terms.parameters.COUPON.value = 0.2
    expect(state.request.terms.parameters.COUPON.value).toBe(0.08)
    expect(state.quotes).toHaveLength(0)
  })
  it('ne remet pas une demande à une banque non sollicitée', async () => {
    const state = await act(createRfqPrototype(), { type: 'SEND', bankIds: ['bank-a'], notional: 1_000_000, side: 'BUY' })
    expect(prototypeRequestForBank(state, 'bank-b')).toBeNull()
    await expect(act(state, { type: 'CALCULATE', bankId: 'bank-b' })).rejects.toThrow('pas reçu')
  })
  it.each([
    { bankIds: [], notional: 1, side: 'BUY' },
    { bankIds: ['unknown'], notional: 1, side: 'BUY' },
    { bankIds: ['bank-a', 'bank-a'], notional: 1, side: 'BUY' },
    { bankIds: ['bank-a'], notional: 0, side: 'BUY' },
    { bankIds: ['bank-a'], notional: 1, side: 'unknown' },
  ])('refuse une demande invalide sans modifier le brouillon (%j)', async fields => {
    const state = createRfqPrototype()
    await expect(act(state, { type: 'SEND', ...fields })).rejects.toThrow()
    expect(state.request).toBeNull()
    expect(state.events).toEqual([])
  })
  it('sépare calcul privé, contrôle, publication et réception', async () => {
    let state = await send()
    state = await act(state, { type: 'CALCULATE', bankId: 'bank-a' })
    expect(state.quotes).toHaveLength(0)
    expect(prototypeEvents(state).some(event => event.type === 'PRIVATE_CALCULATION')).toBe(false)
    await expect(act(state, { type: 'PUBLISH', bankId: 'bank-a' })).rejects.toThrow('contrôlé')
    state = await act(state, { type: 'VALIDATE', bankId: 'bank-a', actor: 'PREPARER' })
    expect(state.quotes).toHaveLength(0)
    state = await act(state, { type: 'PUBLISH', bankId: 'bank-a' })
    expect(state.quotes[0]).toMatchObject({ origin: 'NETWORK', price: 98.35, unit: 'PERCENT_OF_NOTIONAL' })
    expect(state.quotes[0]).not.toHaveProperty('modelPrice')
    expect(state.events.slice(-2).map(event => event.type)).toEqual(['QUOTE_PUBLISHED', 'QUOTE_RECEIVED'])
  })
  it('ne duplique pas une publication répétée de la même préparation', async () => {
    const state = await publish(await send())
    const replay = await act(state, { type: 'PUBLISH', bankId: 'bank-a' })
    expect(replay).toEqual(state)
  })
  it('invalide le contrôle quand le prix préparé change', async () => {
    const state = await publish(await send())
    const next = await act(state, { type: 'SAVE_DRAFT', bankId: 'bank-a', draft: { ...state.banks[0].draft, price: 99 } })
    expect(next.banks[0].review).toBeNull()
    expect(next.quotes[0].price).toBe(98.35)
    await expect(act(next, { type: 'PUBLISH', bankId: 'bank-a' })).rejects.toThrow('contrôlé')
  })
  it.each([0, -1, NaN, Infinity])('refuse un prix commercial invalide %s sans modifier la réponse précédente', async invalidPrice => {
    const state = await publish(await send())
    await expect(act(state, { type: 'SAVE_DRAFT', bankId: 'bank-a', draft: { ...state.banks[0].draft, price: invalidPrice } })).rejects.toThrow('positif')
    expect(state.quotes[0].price).toBe(98.35)
  })
  it('applique la seconde validation sans auto-validation', async () => {
    let state = await send()
    state = await act(state, { type: 'SECOND_VALIDATION', bankId: 'bank-a', enabled: true })
    state = await act(state, { type: 'CALCULATE', bankId: 'bank-a' })
    state = await act(state, { type: 'VALIDATE', bankId: 'bank-a', actor: 'PREPARER' })
    expect(state.banks[0].review).toBeNull()
    await expect(act(state, { type: 'PUBLISH', bankId: 'bank-a' })).rejects.toThrow()
    state = await act(state, { type: 'VALIDATE', bankId: 'bank-a', actor: 'CHECKER' })
    state = await act(state, { type: 'PUBLISH', bankId: 'bank-a' })
    expect(state.quotes).toHaveLength(1)
  })
  it('conserve l’ancien choix lorsqu’une révision remplace la réponse', async () => {
    let state = await publish(await send())
    const oldId = state.quotes[0].id
    state = await act(state, { type: 'SELECT', quoteId: oldId })
    state = await publish(state, 'bank-a', { ...state.banks[0].draft, price: 98.1 })
    expect(state.selectedId).toBe(oldId)
    expect(state.quotes[0].status).toBe('REPLACED')
    expect(state.quotes[1].replaces).toBe(oldId)
    await expect(act(state, { type: 'ACCEPT' })).rejects.toThrow('remplacée')
  })
  it('refuse un contrôle périmé et une publication hors délai', async () => {
    let state = await send()
    state = await act(state, { type: 'CALCULATE', bankId: 'bank-a' })
    state = await act(state, { type: 'VALIDATE', bankId: 'bank-a', actor: 'PREPARER' })
    state = await act(state, { type: 'ADVANCE', minutes: 11 })
    await expect(act(state, { type: 'PUBLISH', bankId: 'bank-a' })).rejects.toThrow('trop ancien')
    state = await act(state, { type: 'ADVANCE', minutes: 4 })
    await expect(act(state, { type: 'PUBLISH', bankId: 'bank-a' })).rejects.toThrow('dépassé')
  })
  it('garde le déclin sans inventer de prix', async () => {
    const state = await act(await send(), { type: 'DECLINE', bankId: 'bank-a' })
    expect(state.quotes).toEqual([])
    await expect(act(state, { type: 'CALCULATE', bankId: 'bank-a' })).rejects.toThrow('décliné')
  })
})

describe('fermeté, retrait, confirmation et manuel', () => {
  it('permet le retrait avant acceptation même si la réponse était sélectionnée', async () => {
    let state = await publish(await send())
    const quoteId = state.quotes[0].id
    state = await act(state, { type: 'SELECT', quoteId })
    state = await act(state, { type: 'WITHDRAW', bankId: 'bank-a', quoteId, reason: 'Erreur avant acceptation' })
    expect(state.agreement).toBeNull()
    await expect(act(state, { type: 'ACCEPT' })).rejects.toThrow('retirée')
  })
  it('exige le motif et refuse le retrait d’une réponse d’une autre banque', async () => {
    const state = await publish(await send())
    const quoteId = state.quotes[0].id
    await expect(act(state, { type: 'WITHDRAW', bankId: 'bank-a', quoteId, reason: '' })).rejects.toThrow('motif')
    await expect(act(state, { type: 'WITHDRAW', bankId: 'bank-b', quoteId, reason: 'Motif' })).rejects.toThrow('ne relève pas')
    expect(state.quotes[0].status).toBe('ACTIVE')
  })
  it('refuse retrait et révision après une acceptation valide', async () => {
    const state = await accept(await publish(await send()))
    expect(state.quotes[0].status).toBe('RESERVED')
    await expect(act(state, { type: 'WITHDRAW', bankId: 'bank-a', quoteId: state.quotes[0].id, reason: 'Erreur' })).rejects.toThrow('prix réservé')
    await expect(publish(state)).rejects.toThrow('réservé')
    await expect(act(state, { type: 'ACCEPT' })).rejects.toThrow('déjà demandé')
  })
  it('refuse l’acceptation à l’expiration, sans réserver un prix', async () => {
    let state = await publish(await send())
    state = await act(state, { type: 'SELECT', quoteId: state.quotes[0].id })
    state = await act(state, { type: 'ADVANCE', minutes: 5 })
    expect(prototypeQuoteStatus(state.quotes[0], state.now)).toBe('EXPIRED')
    expect(prototypeCanSelect(state.quotes[0], state.now)).toBe(false)
    await expect(act(state, { type: 'ACCEPT' })).rejects.toThrow('expirée')
    expect(state.agreement).toBeNull()
  })
  it('préserve une acceptation à temps puis permet le booking confirmé après expiration', async () => {
    let state = await accept(await publish(await send()))
    const validity = state.quotes[0].validUntil
    state = await act(state, { type: 'ADVANCE', minutes: 6 })
    expect(prototypeQuoteStatus(state.quotes[0], state.now)).toBe('RESERVED')
    await expect(act(state, { type: 'BOOK' })).rejects.toThrow('confirmation')
    state = await act(state, confirmation)
    state = await act(state, { type: 'BOOK' })
    expect(state.quotes[0].validUntil).toBe(validity)
    expect(state.booking.bookedAt > validity).toBe(true)
    expect(await act(state, { type: 'BOOK' })).toEqual(state)
  })
  it('conserve le téléphone déclaré et exige interlocuteur et référence', async () => {
    const state = await accept(await publish(await send()))
    await expect(act(state, { ...confirmation, contact: '' })).rejects.toThrow('obligatoires')
    const next = await act(state, { ...confirmation, source: 'PHONE_DECLARED' })
    expect(next.agreement).toMatchObject({ source: 'PHONE_DECLARED', writtenFollowUp: true })
    expect(next.agreement.quote).toMatchObject({ price: 98.35, notional: 1_000_000, currency: 'EUR', firmness: 'FIRM' })
  })
  it.each([
    { firmness: 'INDICATIVE', conditions: '' },
    { firmness: 'FIRM', conditions: 'Sous réserve de documentation' },
  ])('refuse de réserver une réponse non exécutable (%j)', async fields => {
    let state = await send()
    state = await publish(state, 'bank-a', { ...state.banks[0].draft, ...fields })
    state = await act(state, { type: 'SELECT', quoteId: state.quotes[0].id })
    await expect(act(state, { type: 'ACCEPT' })).rejects.toThrow()
    expect(state.quotes[0].firmness).toBe(fields.firmness)
  })
  it('refuse l’acceptation d’une autre version de termes', async () => {
    let state = await publish(await send())
    state = await act(state, { type: 'SELECT', quoteId: state.quotes[0].id })
    state.quotes[0].termsVersion = 2
    await expect(act(state, { type: 'ACCEPT' })).rejects.toThrow('autre version')
  })
  it.each(['BUY', 'SELL'])('compare les réponses fermes mixtes selon le sens %s', async side => {
    let state = await publish(await send(createRfqPrototype(), side))
    state = await act(state, { type: 'MANUAL', contact: 'Interlocuteur', draft: { price: 99, firmness: 'FIRM', validityMinutes: 10, conditions: '' } })
    const best = prototypeBestQuoteIds(state)
    expect(best).toEqual([state.quotes[side === 'BUY' ? 0 : 1].id])
    expect(state.quotes[1]).toMatchObject({ origin: 'MANUAL', contact: 'Interlocuteur' })
    expect(state.selectedId).toBeNull()
  })
  it('distingue une réponse saisie manuellement d’une publication bancaire', async () => {
    const state = await act(await send(), { type: 'MANUAL', contact: 'Interlocuteur', draft: { price: 99, firmness: 'FIRM', validityMinutes: 10, conditions: '' } })
    expect(state.events.at(-1)).toMatchObject({ type: 'MANUAL_QUOTE_RECORDED', party: null })
    expect(state.events.some(event => event.type === 'QUOTE_PUBLISHED')).toBe(false)
  })
  it('ne révèle pas les événements privés ou ceux d’une autre banque', async () => {
    const state = await publish(await publish(await send()), 'bank-b')
    const bankEvents = prototypeEvents(state, 'bank-a')
    expect(bankEvents.every(event => event.party === 'bank-a')).toBe(true)
    expect(prototypeEvents(state).some(event => ['PRIVATE_CALCULATION', 'VALIDATED', 'DRAFT_CHANGED'].includes(event.type))).toBe(false)
  })
})
