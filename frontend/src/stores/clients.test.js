/**
 * Ce que le store commercial doit garantir côté écran.
 *
 * Deux choses seulement, mais ce sont celles qui cassent en silence.
 *
 * **Un refus doit rester lisible.** L'API renvoie tantôt `{detail: "phrase"}`,
 * tantôt `{detail: {code, message, duplicates}}` quand le refus porte de quoi
 * agir. Un écran qui ne sait pas distinguer les deux affiche « [object Object] »
 * et transforme un refus utile en mur.
 *
 * **Le verrou optimiste doit remonter jusqu'à l'écran.** Si le code
 * `CONSTRAINTS_VERSION_STALE` se perd en route, la vue ne peut pas proposer de
 * recharger, et l'utilisateur croit avoir enregistré ce qui a été refusé —
 * exactement la perte silencieuse que le verrou existe pour empêcher.
 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useClientsStore, lireErreur, libelleStatutClient, libelleRaisonPerte,
         STATUTS_CLOS } from './clients.js'

function reponse(status, corps) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => corps,
  }
}

describe('lireErreur rend toujours quelque chose d’affichable', () => {
  it('déplie un refus métier structuré', async () => {
    const details = await lireErreur(reponse(409, {
      detail: { code: 'CLIENT_HAS_HISTORY',
                message: 'Ce client porte 3 contact(s).' },
    }))
    expect(details.code).toBe('CLIENT_HAS_HISTORY')
    expect(details.message).toBe('Ce client porte 3 contact(s).')
  })

  it('accepte aussi un detail en simple chaîne', async () => {
    const details = await lireErreur(reponse(422, { detail: 'Le nom est requis.' }))
    expect(details.code).toBeNull()
    expect(details.message).toBe('Le nom est requis.')
  })

  it('remonte la liste des doublons pour que l’écran puisse la montrer', async () => {
    const details = await lireErreur(reponse(409, {
      detail: { code: 'PERSON_DUPLICATE_SUSPECTED', message: 'Déjà connue ?',
                duplicates: [{ person_id: 4, signal: 'email' }] },
    }))
    expect(details.duplicates).toHaveLength(1)
    expect(details.duplicates[0].signal).toBe('email')
  })

  it('ne rend jamais un objet brut, même sans corps exploitable', async () => {
    const details = await lireErreur({
      ok: false, status: 500, json: async () => { throw new Error('pas de JSON') },
    })
    expect(typeof details.message).toBe('string')
    expect(details.message).toContain('500')
  })
})

describe('le verrou optimiste remonte jusqu’à l’appelant', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('propage le code CONSTRAINTS_VERSION_STALE et son message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => reponse(409, {
      detail: {
        code: 'CONSTRAINTS_VERSION_STALE',
        message: 'Ces contraintes ont été modifiées entre-temps par quelqu’un d’autre.',
      },
    })))

    const store = useClientsStore()
    // La vue distingue ce cas de tous les autres pour proposer un rechargement
    // plutôt qu’un simple bandeau rouge : sans le code, elle ne le peut pas.
    await expect(store.enregistrerContraintes(1, { currencies: ['EUR'] }, 1))
      .rejects.toMatchObject({ code: 'CONSTRAINTS_VERSION_STALE' })
  })

  it('envoie bien la version que l’écran avait sous les yeux', async () => {
    const appels = []
    vi.stubGlobal('fetch', vi.fn(async (url, options) => {
      appels.push({ url, corps: JSON.parse(options.body) })
      return reponse(200, { id: 1, constraints_version: 8 })
    }))

    const store = useClientsStore()
    await store.enregistrerContraintes(1, { currencies: ['EUR'] }, 7)

    // Omettre la version, ou en envoyer une autre que celle affichée,
    // rouvrirait la fenêtre de perte que le verrou ferme.
    expect(appels[0].corps.constraints_version).toBe(7)
    expect(appels[0].url).toBe('/api/clients/1/constraints')
  })

  it('transmet la date et la source sans les confondre avec la préférence', async () => {
    const appels = []
    vi.stubGlobal('fetch', vi.fn(async (url, options) => {
      appels.push({ url, corps: JSON.parse(options.body) })
      return reponse(200, { id: 1, constraints_version: 9 })
    }))
    const store = useClientsStore()
    await store.enregistrerContraintes(1, { currencies: ['EUR'] }, 8, {
      statement_kind: 'client_declared', statement_date: '2026-09-01',
      source_affiliation_id: 12, channel: 'meeting',
    })

    expect(appels[0].corps.constraints).toEqual({ currencies: ['EUR'] })
    expect(appels[0].corps.evidence.source_affiliation_id).toBe(12)
    expect(appels[0].corps.evidence.statement_date).toBe('2026-09-01')
  })

  it('un refus ne laisse pas la fiche dans un état à moitié modifié', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => reponse(409, {
      detail: { code: 'CONSTRAINTS_VERSION_STALE', message: 'Périmé' },
    })))
    const store = useClientsStore()
    store.clientCourant = { id: 1, constraints_version: 3,
                            constraints: { currencies: ['EUR'] } }

    await expect(store.enregistrerContraintes(1, { currencies: ['USD'] }, 3))
      .rejects.toThrow()
    expect(store.clientCourant.constraints.currencies).toEqual(['EUR'])
    expect(store.clientCourant.constraints_version).toBe(3)
  })
})

describe('les profils multi-périmètres gardent leur adresse explicite', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })
  afterEach(() => { vi.unstubAllGlobals() })

  it('porte le mandat sur les lectures et l’écriture, jamais dans un état implicite', async () => {
    const appels = []
    vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
      appels.push({ url, corps: options.body ? JSON.parse(options.body) : null })
      return reponse(200, { values: {} })
    }))
    const store = useClientsStore()

    await store.lireIntelligenceClient(4, null, { mandate_id: 21 })
    await store.lireSchemaPreferencesScope(4, { mandate_id: 21 })
    await store.enregistrerPreferencesScope(
      4, { transaction_formats: ['OTC'] }, { mandate_id: 21 }, 7,
      { statement_kind: 'client_confirmed', statement_date: '2026-09-01' })

    expect(appels[0].url).toBe(
      '/api/client-intelligence/clients/4?mandate_id=21')
    expect(appels[1].url).toBe(
      '/api/clients/4/scoped-preferences/schema?mandate_id=21')
    expect(appels[2].corps).toMatchObject({
      mandate_id: 21, affiliation_id: null, preferences_version: 7,
      preferences: { transaction_formats: ['OTC'] },
    })
  })
})

describe('les vocabulaires s’affichent en français sans perdre leur code', () => {
  it('traduit un statut connu', () => {
    expect(libelleStatutClient('active')).toBe('Actif')
    expect(libelleRaisonPerte('coupon_too_low')).toBe('Coupon trop faible')
  })

  it('rend la valeur brute plutôt que de masquer un code inconnu', () => {
    // Un code que le serveur ajouterait sans que le front suive doit rester
    // visible : afficher « — » ferait croire à une absence de donnée.
    expect(libelleStatutClient('nouveau_statut')).toBe('nouveau_statut')
  })

  it('la liste des statuts clos est celle du serveur', () => {
    // Doit rester alignée sur OPPORTUNITY_TERMINAL — une divergence ferait
    // apparaître des dossiers clos dans le pipeline ouvert.
    expect(STATUTS_CLOS).toEqual(['won', 'lost', 'cancelled', 'archived'])
  })
})
