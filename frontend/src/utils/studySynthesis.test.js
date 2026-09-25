import { describe, it, expect } from 'vitest'
import { acceptStudySynthesis } from './studySynthesis'

describe('Study synthesis acceptance', () => {
  it('keeps a generated synthesis as a draft for review', () => {
    expect(acceptStudySynthesis({ study_hash: 'a', synthesis: ' Analyse ' }, 'a', ' '))
      .toEqual({ generated: 'Analyse', synthesis: ' ', inserted: false })
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


it('rejects technical output or an explicit token cutoff without replacing prose', () => {
  for (const data of [{ synthesis: '```json\n{"data":{}}' }, { synthesis: '{"sha256":"abc"}' },
    { synthesis: 'Une conclusion interrompue', finish_reason: 'length' }]) {
    expect(() => acceptStudySynthesis({ study_hash: 'a', ...data }, 'a', 'Texte relu')).toThrow('inexploitable')
  }
})
