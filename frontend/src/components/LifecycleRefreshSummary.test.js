import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import Summary from './LifecycleRefreshSummary.vue'

const render = summary => renderToString(createSSRApp({ render: () => h(Summary, { summary }) }))

describe('bilan du traitement lifecycle', () => {
  it('distingue couverture complète, rafraîchissement et règlement', async () => {
    const html = await render({ status: 'SUCCESS', deals: 3, refreshed: 1, settled: 1,
      coverage: { total: 3, succeeded: 3, failed: 0 }, errors: [], proposed: [{}], resolved: [{}] })
    expect(html).toContain('✓ Terminé')
    expect(html).toContain('couverture 3/3')
    expect(html).toContain('1 rafraîchi(s), 1 échéance(s) atteinte(s)')
    expect(html).toContain('1 proposition(s), 1 résolution(s)')
    expect(html).not.toContain('<details')
  })
  it('rend les erreurs partielles consultables et ne donne pas de coche de succès', async () => {
    const html = await render({ status: 'PARTIAL', deals: 2, refreshed: 2,
      coverage: { total: 2, succeeded: 1, failed: 1 }, errors: ['BAD: watchlist — source indisponible'] })
    expect(html).toContain('⚠ Partiel')
    expect(html).toContain('couverture 1/2')
    expect(html).toContain('consulter le détail avant de relancer')
    expect(html).toContain('BAD: watchlist — source indisponible')
    expect(html).not.toContain('✓')
  })
  it('annonce un échec même si tous les refresh ont précédé une surveillance en erreur', async () => {
    const html = await render({ status: 'FAILED', deals: 2, refreshed: 2,
      coverage: { total: 2, succeeded: 0, failed: 2 }, errors: ['A: erreur', 'B: erreur'] })
    expect(html).toContain('⚠ Échec')
    expect(html).toContain('couverture 0/2')
    expect(html).not.toContain('✓')
  })
  it('ne masque pas les erreurs d’un ancien résumé déclaré SUCCESS', async () => {
    const html = await render({ status: 'SUCCESS', deals: 1, refreshed: 0, errors: ['BANK: indisponible'] })
    expect(html).toContain('⚠ Échec')
    expect(html).toContain('BANK: indisponible')
  })
  it('échappe le message technique dans le détail', async () => {
    const html = await render({ deals: 1, errors: ['<script>alert(1)</script>'] })
    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;')
  })
  it('présente un book vide comme un traitement terminé de couverture nulle', async () => {
    expect(await render({ status: 'SUCCESS', coverage: { total: 0, succeeded: 0, failed: 0 } }))
      .toContain('couverture 0/0')
  })
})
