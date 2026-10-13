import { afterEach, describe, expect, it, vi } from 'vitest'
import { lockDocumentScroll } from './useDocumentScrollLock.js'

afterEach(() => vi.unstubAllGlobals())
describe('défilement du document sous les modales', () => {
  it('garde le document verrouillé jusqu’à fermeture du dernier masque', () => {
    const document = { body: { style: { overflow: 'auto' } }, documentElement: { style: { overflow: '' } } }
    vi.stubGlobal('document', document)
    const first = lockDocumentScroll()
    const second = lockDocumentScroll()
    first()
    first()
    expect(document.body.style.overflow).toBe('hidden')
    second()
    expect(document.body.style.overflow).toBe('auto')
    expect(document.documentElement.style.overflow).toBe('')
  })
  it('restaure aussi un document déjà borné par l’application', () => {
    const document = { body: { style: { overflow: 'hidden' } }, documentElement: { style: { overflow: 'clip' } } }
    vi.stubGlobal('document', document)
    const release = lockDocumentScroll()
    release()
    expect(document.documentElement.style.overflow).toBe('clip')
    expect(document.body.style.overflow).toBe('hidden')
  })
  it('n’exige pas de document lors du rendu serveur', () => {
    vi.stubGlobal('document', undefined)
    expect(() => lockDocumentScroll()()).not.toThrow()
  })
})
