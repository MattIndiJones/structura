import { describe, it, expect } from 'vitest'
import { createStudyEpoch, snapshotStudy, restoreStudyArtifacts } from './studySnapshot'

describe('Studies snapshots', () => {
  it('rejects responses from a previous study after run or load', () => {
    const epoch = createStudyEpoch()
    const old = epoch.next()
    const current = epoch.next()
    expect(epoch.accepts(old)).toBe(false)
    expect(epoch.accepts(current)).toBe(true)
  })
  it('preserves complete outputs without later mutation of the saved snapshot', () => {
    const result = { meta: { isin: 'GENERIC' }, provenance: { result_hash: 'abc' } }
    const artifacts = { attribution: { value: 12 }, brinson: { available: true },
      synthesis: 'Conclusion', ai: { effective_model: 'model', generation_id: 'generation' },
      company: 'Cabinet', client: 'Client' }
    const saved = snapshotStudy(result, artifacts)
    artifacts.attribution.value = 999
    result.meta.isin = 'OTHER'
    expect(saved.meta.isin).toBe('GENERIC')
    expect(restoreStudyArtifacts(saved).attribution.value).toBe(12)
    expect(restoreStudyArtifacts(saved).ai.generation_id).toBe('generation')
    expect(restoreStudyArtifacts(saved).client).toBe('Client')
  })
  it('opens legacy snapshots with empty derived outputs', () => {
    expect(restoreStudyArtifacts({}).brinson).toBeNull()
    expect(restoreStudyArtifacts({}).synthesis).toBe('')
  })
})
