import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import RfqNetworkPrototypeView from './RfqNetworkPrototypeView.vue'
import { applyRfqPrototypeAction as act, createRfqPrototype } from '../utils/rfqNetworkPrototype.js'

async function render(props = {}) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/rfq', component: { template: '<div />' } }] })
  await router.push('/rfq')
  await router.isReady()
  return renderToString(createSSRApp(RfqNetworkPrototypeView, props).use(router))
}

describe('écrans du prototype RFQ', () => {
  it('affiche un brouillon fictif et le maintien du parcours manuel', async () => {
    const html = await render()
    expect(html).toContain('Maquette fonctionnelle sur données fictives')
    expect(html).toContain('aucun message externe')
    expect(html).toContain('Saisir une réponse manuelle')
    expect(html).toContain('Vérifier et envoyer la RFQ')
    expect(html).not.toContain('Calcul privé et réponse commerciale')
  })
  it('ne présente pas les termes ni le pricing à une banque non sollicitée', async () => {
    const html = await render({ initialPerspective: 'bank' })
    expect(html).toContain('Aucune demande adressée à cette banque')
    expect(html).not.toContain('Produit commun · termes v1')
    expect(html).not.toContain('Calcul privé et réponse commerciale')
  })
  it('affiche la préparation bancaire sans exposer le calcul à la perspective demandeur', async () => {
    let state = await act(createRfqPrototype(), { type: 'SEND', bankIds: ['bank-a'], notional: 1_000_000, side: 'BUY' })
    state = await act(state, { type: 'CALCULATE', bankId: 'bank-a' })
    const bank = await render({ initialState: state, initialPerspective: 'bank' })
    const requester = await render({ initialState: state })
    expect(bank).toContain('Résultat fictif privé')
    expect(bank).toContain('98,20 %')
    expect(requester).not.toContain('Résultat fictif privé')
    expect(requester).not.toContain('98,20 %')
    expect(requester).toContain('Aucun prix reçu')
  })
})
