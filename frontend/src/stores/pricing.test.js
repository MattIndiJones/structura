/**
 * Le script déclare des noms, le deal porte les valeurs.
 *
 * C'est la règle qui gouverne ce fichier, et elle vient d'un bug précis : en
 * ajoutant une ligne à un script, l'échéancier d'observation repartait vierge.
 *
 * L'éditeur reparse 500 ms après la dernière frappe, et une pause d'une
 * demi-seconde au milieu d'un `SET` est banale. Le script est alors incomplet,
 * `/api/parse` répond `ok: false`, et le store en concluait que le script ne
 * déclarait PLUS RIEN — donc supprimait toutes les saisies. Une erreur de parse
 * veut pourtant dire « je ne sais pas ce que ce script déclare », pas « il ne
 * déclare rien ».
 *
 * Le calendrier vidé se voyait. Trois conséquences ne se voyaient pas :
 *
 *   — les PARAM étaient réinitialisés à la valeur écrite dans le script, donc
 *     un champ qui a l'air rempli avec un chiffre plausible ;
 *   — le calendrier recréé n'était pas vide partout : fréquence 3M, aucune
 *     convention, règlement J+0, sur un produit mensuel/suivant à J+7 ;
 *   — sur une variante, enregistrer écrivait le vidage dans le delta et
 *     annulait la restructuration en silence.
 *
 * D'où ces tests, qui vérifient l'état APRÈS le cycle complet — et pas
 * seulement que rien n'a planté.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { usePricingStore } from './pricing.js'

const VALIDE = `PARAM COUPON = 2%
CONSTAT() OBS

AT OBS.last:
  PAY 1
`
// Marqueur d'un script que le serveur refuse — il tient lieu de tout état
// intermédiaire non parsable : un `SET ` inachevé, une parenthèse ouverte.
const CASSE = `${VALIDE}  SET CPN = INDIC(WOF\n`

const DECLARATIONS = {
  params: [{ name: 'COUPON', kind: 'scalar', display_default: 2, raw_default: 2, is_pct: true }],
  constats: [{ name: 'OBS', kind: 'schedule' }],
}

/** Le calendrier réel d'un Phoenix mensuel, tel qu'un term sheet le donne. */
const TERM_SHEET = {
  start_date: '2024-06-14', end_date: '2027-06-14', roll_date: '2024-07-14',
  frequency: { value: 1, unit: 'M' }, convention: 'following', settlement_lag: 7,
}

function serveurDeParse({ declare = DECLARATIONS } = {}) {
  return vi.fn(async (url, opts) => {
    if (!String(url).includes('/api/parse')) {
      return { ok: false, json: async () => ({}) }
    }
    const script = JSON.parse(opts.body).script
    const lisible = !script.includes('INDIC(WOF\n')
    return {
      ok: true,
      json: async () => (lisible
        ? { ok: true, params: declare.params, constats: declare.constats, has_stop: false }
        : { ok: false, errors: ['Ligne 6 : expression incomplète'] }),
    }
  })
}

async function storeRenseigne(declare) {
  setActivePinia(createPinia())
  globalThis.fetch = serveurDeParse(declare ? { declare } : {})
  const store = usePricingStore()
  store.script = VALIDE
  await store.parseScript()
  Object.assign(store.constatOverrides.OBS, TERM_SHEET)
  store.paramOverrides.COUPON = 1.334167
  return store
}

describe('une erreur de parse ne détruit aucune saisie', () => {
  let store
  beforeEach(async () => { store = await storeRenseigne() })

  it('garde le calendrier pendant que le script est incomplet', async () => {
    store.script = CASSE
    await store.parseScript()

    expect(store.parseError).toBeTruthy()
    expect(store.constatOverrides.OBS).toMatchObject(TERM_SHEET)
  })

  it('le rend intact une fois la ligne terminée', async () => {
    store.script = CASSE
    await store.parseScript()
    store.script = `${VALIDE}  SET CPN = 1\n`
    await store.parseScript()

    expect(store.parseError).toBeNull()
    expect(store.constatOverrides.OBS).toMatchObject(TERM_SHEET)
  })

  it('garde aussi les PARAM, que le vidage réinitialisait en silence', async () => {
    // Le cas dangereux : un PARAM recréé reprend la valeur ÉCRITE DANS LE
    // SCRIPT (2 %). Le champ a l'air rempli, avec un chiffre plausible, et on
    // price un autre produit sans rien remarquer.
    store.script = CASSE
    await store.parseScript()
    store.script = VALIDE
    await store.parseScript()

    expect(store.paramOverrides.COUPON).toBe(1.334167)
  })

  it("ne recrée pas un calendrier qui a l'air rempli mais ne l'est pas", async () => {
    // Le second piège : le calendrier recréé portait fréquence 3M, convention
    // « aucun ajustement » et règlement J+0. Les dates manquantes se voient ;
    // ces trois-là non, et elles décrivent un autre produit — douze
    // constatations au lieu de trente-six, sans décalage de règlement.
    store.script = CASSE
    await store.parseScript()
    store.script = VALIDE
    await store.parseScript()

    const obs = store.constatOverrides.OBS
    expect(obs.frequency).toEqual({ value: 1, unit: 'M' })
    expect(obs.convention).toBe('following')
    expect(obs.settlement_lag).toBe(7)
  })
})

describe('un nom qui disparaît du script dort, il ne meurt pas', () => {
  it('conserve la valeur quand le CONSTAT cesse d’être déclaré', async () => {
    const store = await storeRenseigne()
    globalThis.fetch = serveurDeParse({ declare: { params: DECLARATIONS.params, constats: [] } })
    store.script = 'PARAM COUPON = 2%\nAT 3:\n  PAY 1\n'
    await store.parseScript()

    expect(store.scriptConstats).toHaveLength(0)
    expect(store.constatOverrides.OBS).toMatchObject(TERM_SHEET)
  })

  it('la restitue quand le nom revient', async () => {
    const store = await storeRenseigne()
    globalThis.fetch = serveurDeParse({ declare: { params: DECLARATIONS.params, constats: [] } })
    store.script = 'PARAM COUPON = 2%\nAT 3:\n  PAY 1\n'
    await store.parseScript()

    globalThis.fetch = serveurDeParse()
    store.script = VALIDE
    await store.parseScript()

    // Un renommage par erreur suivi d'un retour en arrière ne coûte donc plus
    // une ressaisie de term sheet.
    expect(store.constatOverrides.OBS).toMatchObject(TERM_SHEET)
  })

  it('crée bien une entrée vierge pour un nom vraiment nouveau', async () => {
    const store = await storeRenseigne()
    globalThis.fetch = serveurDeParse({ declare: {
      params: DECLARATIONS.params,
      constats: [...DECLARATIONS.constats, { name: 'COUPON_OBS', kind: 'schedule' }],
    } })
    store.script = `${VALIDE}CONSTAT() COUPON_OBS\n`
    await store.parseScript()

    expect(store.constatOverrides.COUPON_OBS.start_date).toBe('')
    expect(store.constatOverrides.OBS).toMatchObject(TERM_SHEET)
  })
})

describe('ce qui part au moteur ne contient que le déclaré', () => {
  it('ignore les entrées dormantes', async () => {
    const store = await storeRenseigne()
    globalThis.fetch = serveurDeParse({ declare: { params: DECLARATIONS.params, constats: [] } })
    store.script = 'PARAM COUPON = 2%\nAT 3:\n  PAY 1\n'
    await store.parseScript()

    // Une entrée dormante décrirait au serveur un échéancier que le produit ne
    // porte plus. `_buildConstats` parcourt les déclarations, pas les entrées.
    expect(store.pricingBody().constats).toEqual({})
  })
})


/**
 * `variantInfo` décrit LE PRODUIT ACTUELLEMENT DANS LE STORE.
 *
 * Le store est global et survit à la navigation : quitter le Pricer ne le vide
 * pas. Tant que la déclinaison y reste accrochée, l'état « modifié » continue
 * de comparer l'écran au parent d'une variante qu'on ne regarde plus — et le
 * garde de route redemande « quitter sans enregistrer ? » à chaque page, alors
 * qu'on a déjà quitté et déjà répondu.
 *
 * Le second cas est plus grave et ne s'était pas encore vu : ouvrir un deal
 * booké ou une RFQ chargeait un AUTRE produit sans relâcher la déclinaison.
 * L'écart se calculait alors entre ce deal-là et le parent d'une variante sans
 * rapport, donc « modifié » presque à coup sûr — un avertissement qui parle
 * d'un travail que l'utilisateur n'a jamais fait.
 */
describe('la déclinaison ne survit pas au produit qu’elle décrit', () => {
  async function storeSurVarianteModifiee() {
    const store = await storeRenseigne()
    store.variantInfo = {
      id: 7, parent_id: 1, title: 'AC 50 %', mode: 'avenant', ecarts: [],
      delta: { set: {}, removed: [] },
      parent: {
        script_text: VALIDE, params: { COUPON: 2 },
        constats: { OBS: { ...TERM_SHEET } },
        global: { underlyings: [], corr_matrix: [] },
      },
    }
    store.paramOverrides.COUPON = 5   // une modification non enregistrée
    return store
  }

  it('est modifiée tant qu’on la regarde', async () => {
    const store = await storeSurVarianteModifiee()
    expect(store.variantDirty).toBe(true)
  })

  it('cesse de l’être dès qu’on la relâche', async () => {
    // Ce que fait le garde de route quand l'utilisateur confirme qu'il part :
    // il vient d'abandonner ces modifications, les lui représenter à la
    // navigation suivante serait lui redemander ce qu'il a déjà tranché.
    const store = await storeSurVarianteModifiee()
    store.relacherVariante()

    expect(store.variantInfo).toBeNull()
    expect(store.variantDirty).toBe(false)
  })

  it.each([
    ['resetToDefaults', (s) => s.resetToDefaults()],
    ['loadFromDeal', (s) => s.loadFromDeal({ id: 1, script_snapshot: VALIDE })],
    ['loadFromRfq', (s) => s.loadFromRfq({ id: 1, script_snapshot: VALIDE })],
  ])('%s relâche la déclinaison en chargeant un autre produit', async (_nom, charger) => {
    const store = await storeSurVarianteModifiee()
    await charger(store)

    expect(store.variantInfo).toBeNull()
    expect(store.variantDirty).toBe(false)
  })
})


/**
 * Les trois dates du term sheet passent l'AO ensemble.
 *
 * `loadFromRfq` recopiait `strike_date` et `value_date` — pas `payment_date`.
 * Le champ arrivait vide dans le masque de booking, où une proposition en J+3
 * depuis la MATURITÉ venait le remplir : une date qui n'est pas celle de l'AO.
 *
 * Or `payment_date` fait partie des termes contractuels gelés. Le booking
 * était donc refusé pour un écart que personne n'avait saisi, sur un message
 * nommant `payment_date` sans dire lequel des deux côtés avait tort.
 *
 * Un test qui n'aurait vérifié que « le préremplissage ne plante pas » serait
 * resté vert pendant tout ce temps.
 */
describe('le préremplissage depuis un AO garde ses dates', () => {
  const AO = {
    id: 42,
    script_snapshot: VALIDE,
    params: {
      strike_date: '2026-08-31',
      value_date: '2026-08-31',
      payment_date: '2029-09-05',
      T: 3.0, currency: 'EUR', notional: 1_000_000,
      underlyings: [{ name: 'SX5E', ticker: '^STOXX50E', ccy: 'EUR', sigma: 0.18, q: 0.03 }],
      corr_matrix: [[1]],
    },
    quotes: [],
  }

  it('reprend les trois dates, pas seulement deux', async () => {
    const store = await storeRenseigne()
    await store.loadFromRfq(AO)

    expect(store.globalParams.strike_date).toBe('2026-08-31')
    expect(store.globalParams.value_date).toBe('2026-08-31')
    expect(store.globalParams.payment_date).toBe('2029-09-05')
    expect(store.pendingDealPrefill.strike_date).toBe('2026-08-31')
    expect(store.pendingDealPrefill.value_date).toBe('2026-08-31')
    expect(store.pendingDealPrefill.payment_date).toBe('2029-09-05')
  })

  it('ne laisse pas traîner la date de l’affaire précédente', async () => {
    // Le contrôle négatif : garder l'ancienne valeur serait pire qu'un champ
    // vide — une date plausible, issue d'un autre produit.
    const store = await storeRenseigne()
    store.globalParams.payment_date = '2027-01-15'
    await store.loadFromRfq(AO)

    expect(store.globalParams.payment_date).toBe('2029-09-05')
  })

  it('envoie bien cette date au serveur', async () => {
    // Le fil jusqu'au bout : reprise à l'écran ne vaut rien si le corps de
    // requête ne la porte pas.
    const store = await storeRenseigne()
    await store.loadFromRfq(AO)

    expect(store.pricingBody().payment_date).toBe('2029-09-05')
  })
})
