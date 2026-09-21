import { describe, it, expect } from 'vitest'
import { acceptStudySynthesis } from './studySynthesis'

describe('Study synthesis acceptance', () => {
  it('inserts a generated synthesis into an empty report', () => {
    expect(acceptStudySynthesis({ study_hash: 'a', synthesis: ' Analyse ' }, 'a', ' '))
      .toEqual({ generated: 'Analyse', synthesis: 'Analyse', inserted: true })
  })
  it('preserves an existing edited synthesis', () => {
    expect(acceptStudySynthesis({ study_hash: 'a', text: 'Nouvelle analyse' }, 'a', 'Texte relu'))
      .toEqual({ generated: 'Nouvelle analyse', synthesis: 'Texte relu', inserted: false })
  })
  it('reports mismatched versions and empty responses rather than silently discarding them', () => {
    expect(() => acceptStudySynthesis({ study_hash: 'old', synthesis: 'Texte' }, 'new')).toThrow('version')
    expect(() => acceptStudySynthesis({ synthesis: 'Texte' }, undefined)).toThrow('version')
    expect(() => acceptStudySynthesis({ study_hash: 'a', text: ' ' }, 'a')).toThrow('vide')
  })
})
