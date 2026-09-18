import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { useValuationNoteDraft } from './useValuationNoteDraft'

const initial = () => ({ id: 1, title: 'Note', revision: 1, draft: { analyse: 'Initial' } })
const states = []
const make = fn => { const s = useValuationNoteDraft(fn); states.push(s); s.load(initial()); return s }
afterEach(() => { states.forEach(s => s.dispose()); states.length = 0; vi.useRealTimers() })

describe('Valo Explain editorial draft', () => {
  it('does not save on load and autosaves the edited narrative only', async () => {
    vi.useFakeTimers()
    const request = vi.fn(async (_, opts) => ({ ...initial(), ...JSON.parse(opts.body), revision: 2 }))
    const s = make(request)
    await nextTick(); await vi.advanceTimersByTimeAsync(1000)
    expect(request).not.toHaveBeenCalled()
    s.draft.value.analyse = 'Edited'
    await nextTick(); await vi.advanceTimersByTimeAsync(1000)
    expect(s.dirty.value).toBe(false)
    expect(s.note.value.revision).toBe(2)
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ title: 'Note', draft: { analyse: 'Edited' }, revision: 1 })
  })

  it('serializes edits made during a save without losing the newer text', async () => {
    let release
    const request = vi.fn().mockImplementationOnce(() => new Promise(resolve => { release = resolve }))
      .mockImplementationOnce(async (_, opts) => ({ ...initial(), ...JSON.parse(opts.body), revision: 3 }))
    const s = make(request)
    s.draft.value.analyse = 'First'
    const saving = s.flush()
    await Promise.resolve()
    s.draft.value.analyse = 'Second'
    release({ ...initial(), revision: 2, draft: { analyse: 'First' } })
    await saving
    expect(s.draft.value.analyse).toBe('Second')
    expect(s.note.value.revision).toBe(3)
    expect(s.dirty.value).toBe(false)
    expect(JSON.parse(request.mock.calls[1][1].body).revision).toBe(2)
  })

  it('shares the save queue between autosave and an export waiting on newer edits', async () => {
    let release
    const request = vi.fn().mockImplementationOnce(() => new Promise(resolve => { release = resolve }))
      .mockImplementation(async (_, opts) => ({ ...initial(), ...JSON.parse(opts.body), revision: 3 }))
    const s = make(request)
    s.draft.value.analyse = 'First'
    const autosave = s.flush()
    await Promise.resolve()
    s.draft.value.analyse = 'For the PDF'
    const exportSave = s.flush()
    release({ ...initial(), revision: 2, draft: { analyse: 'First' } })
    await Promise.all([autosave, exportSave])
    expect(request).toHaveBeenCalledTimes(2)
    expect(s.note.value.draft.analyse).toBe('For the PDF')
    expect(s.dirty.value).toBe(false)
  })

  it('keeps unsaved text after a conflict and never silently overwrites it', async () => {
    const request = vi.fn().mockRejectedValue(new Error('Conflit de révision'))
    const s = make(request)
    s.draft.value.analyse = 'Must survive'
    await expect(s.flush()).rejects.toThrow('Conflit')
    expect(s.draft.value.analyse).toBe('Must survive')
    expect(s.dirty.value).toBe(true)
    expect(s.note.value.revision).toBe(1)
    expect(s.saveError.value).toContain('Conflit')
  })
})
