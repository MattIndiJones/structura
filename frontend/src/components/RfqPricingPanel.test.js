import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia } from 'pinia'
import Panel from './RfqPricingPanel.vue'
import Flux from './FluxDecomposition.vue'

describe('restitution du calcul privé RFQ', () => {
  it('ancre les flux forward sur la valorisation et conserve les dates contractuelles au strike', async () => {
    const result={price:1,n_eff:1,pre_strike:true,valuation_date:'2026-10-24',
      flux_table:{pay:{t:367/365.25,t_pay:370/365.25,lbl:'Capital',n:1,sum:1,pv:1}},
      schedule:{constatations:[{date:'2027-10-26',date_paiement:'2027-10-29',calendrier:'OBS',rang:1}]}}
    const app=createSSRApp({render:()=>h(Panel,{rfq:{},pricing:{result,strikeDate:'2026-10-26',valueDate:'2026-10-26',hypotheses:{}}})})
    app.use(createPinia())
    const html=await renderToString(app)
    expect(html).toContain('26/10/2027');expect(html).toContain('29/10/2027')
    expect(html).not.toContain('28/10/2027');expect(html).not.toContain('27/10/2027')
  })

  it('convertit les années en jours calendaires UTC même à travers le changement d’heure',async()=>{
    const result={price:1,n_eff:1,flux_table:{pay:{t:365/365.25,t_pay:365/365.25,lbl:'Capital',n:1,sum:1,pv:1}}}
    const app=createSSRApp({render:()=>h(Flux,{result,originDate:'2026-10-26'})})
    app.use(createPinia())
    const html=await renderToString(app)
    expect(html).toContain('26/10/2027');expect(html).not.toContain('25/10/2027')
  })

  it('explique la restriction sans proposer une commande indisponible', async () => {
    const html = await renderToString(createSSRApp({ render: () => h(Panel, { rfq: {}, canPrice: false }) }))
    expect(html).toContain('Calcul privé réservé aux profils habilités au pricing.')
    expect(html).not.toContain('Aucun prix modèle')
    expect(html).not.toContain('Lancez')
  })
  it('conserve le guidage du profil habilité sans calcul', async () => {
    const html = await renderToString(createSSRApp({ render: () => h(Panel, { rfq: {}, canPrice: true }) }))
    expect(html).toContain('Aucun prix modèle')
    expect(html).toContain('Calculer prix modèle')
  })
})
