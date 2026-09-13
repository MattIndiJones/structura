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
    ['loadFromDeal', (s) => s.loadFromDeal({
      id: 1, script_snapshot: VALIDE, T: 3, devise: 'EUR',
      underlyings: [{ name: 'A', ticker: 'A', ccy: 'EUR' }],
    })],
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
    expect(store.globalParams.nominal).toBe(1_000_000)
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

describe('les economics d’un deal rouvert restent autoritatifs', () => {
  it('restaure nominal, devise et dates dans le store partagé', async () => {
    const store = await storeRenseigne()
    await store.loadFromDeal({
      id: 7,
      reference: 'DEAL-7',
      script_snapshot: VALIDE,
      market_snapshot: {
        deal_ccy: 'USD', user_params: { COUPON: 0.0175 }, constats: {},
        underlyings: [{ name: 'A', ticker: 'A', ccy: 'USD', sigma: 20, q: 2 }],
      },
      T: 3,
      devise: 'USD',
      nominal: 2_500_000,
      sens: 'vente',
      contrepartie: 'Banque Test',
      product_type: 'Autocall',
      fixing_policy: 'AUTO_YAHOO',
      fair_value: 99.25,
      price_traded: 98.9,
      trade_date: '2026-09-01',
      strike_date: '2026-09-03',
      value_date: '2026-09-07',
      payment_date: '2029-09-06',
    })

    expect(store.globalParams.nominal).toBe(2_500_000)
    expect(store.globalParams.deal_ccy).toBe('USD')
    expect(store.globalParams.strike_date).toBe('2026-09-03')
    expect(store.globalParams.value_date).toBe('2026-09-07')
    expect(store.globalParams.payment_date).toBe('2029-09-06')
    // Ouvrir le deal restitue le pricing initial. Le MTM ne démarre que
    // lorsque l'utilisateur avance explicitement la Pricing date.
    expect(store.globalParams.valuation_date).toBe('2026-09-03')
    expect(store.isInLife()).toBe(false)
    store.globalParams.valuation_date = '2026-09-12'
    expect(store.isInLife()).toBe(true)
    expect(store.pricingBody().valuation_date).toBe('2026-09-12')
    expect(store.paramOverrides.COUPON).toBeCloseTo(1.75, 10)
  })

  it('remet à zéro courbes, funding et réglages absents du deal suivant', async () => {
    const store = await storeRenseigne()
    const base = {
      script_snapshot: VALIDE, T: 3, devise: 'EUR', nominal: 1_000_000,
      underlyings: [{ name: 'A', ticker: 'A', ccy: 'EUR' }],
    }
    await store.loadFromDeal({
      ...base, id: 1, reference: 'A',
      market_snapshot: {
        underlyings: [{ name: 'A', ticker: 'A', ccy: 'EUR' }],
        yieldCurve: [{ label: '1Y', T: 1, rate: 4 }], N: 50000,
        barrierMonitoring: 'continuous',
        funding: { enabled: true, mode: 'flat', level: 1.5, pillars: [] },
      },
    })
    await store.loadFromDeal({ ...base, id: 2, reference: 'B', market_snapshot: {} })

    expect(store.yieldCurve.enabled).toBe(false)
    expect(store.fundingCurve.enabled).toBe(true)
    expect(store.fundingCurve.level).toBe(0)
    expect(store.globalParams.N).toBe(20000)
    expect(store.globalParams.seed).toBe(42)
    expect(store.globalParams.barrierMonitoring).toBe('weekly')
  })

  it('fige le panier et la maturité tant que le deal booké reste ouvert', async () => {
    const store = await storeRenseigne()
    await store.loadFromDeal({
      id: 9, reference: 'DEAL-LOCKED', script_snapshot: VALIDE,
      market_snapshot: {
        underlyings: [{ name: 'SX5E', ticker: '^STOXX50E', ccy: 'EUR' }],
      },
      T: 3, devise: 'EUR', nominal: 1_000_000,
      strike_date: '2026-09-13', maturity_date: '2029-09-13',
    })

    expect(store.contractTermsLocked).toBe(true)
    store.addUnderlying()
    store.removeUnderlying(0)
    store.setMaturityDate('2030-09-13')

    expect(store.underlyings).toHaveLength(1)
    expect(store.underlyings[0]).toMatchObject({ name: 'SX5E', ticker: '^STOXX50E' })
    expect(store.maturityDate).toBe('2029-09-13')
    await expect(store.adoptBasket(
      ['^GDAXI'], ['DAX'], [[1]])).rejects.toThrow('panier est figé')

    store.resetToDefaults()
    expect(store.contractTermsLocked).toBe(false)
  })

  it('actualise le marché sans réécrire l’identité contractuelle', async () => {
    const store = await storeRenseigne()
    await store.loadFromDeal({
      id: 10, reference: 'DEAL-MARKET', script_snapshot: VALIDE,
      market_snapshot: {
        underlyings: [{ name: 'Sous-jacent 1', ticker: 'mc.pa', ccy: 'EUR', sigma: 20, q: 2 }],
      },
      T: 3, devise: 'EUR', nominal: 1_000_000,
      strike_date: '2026-09-13', maturity_date: '2029-09-13',
    })
    globalThis.fetch = vi.fn(async url => {
      if (String(url).includes('/api/finance/hist_vol')) {
        return { ok: true, json: async () => ({
          tickers: ['MC.PA'], vols: { 'MC.PA': 0.25 },
          corr: { 'MC.PA': { 'MC.PA': 1 } }, missing: [], n_obs: 252,
          requested_asof: '2026-09-13', asof_effective: '2026-09-11',
        }) }
      }
      if (String(url).includes('/api/finance/dividends')) {
        return { ok: true, json: async () => ({
          ok: true, yield_declared: 0.03, dividends: [],
          pays_dividends: true, suspect: false,
        }) }
      }
      return { ok: false, json: async () => ({}) }
    })

    await store.loadYfAll({ asof: '2026-09-13' })

    expect(store.underlyings[0].name).toBe('Sous-jacent 1')
    expect(store.underlyings[0].ticker).toBe('mc.pa')
    expect(store.underlyings[0].sigma).toBe(25)
    expect(store.underlyings[0].q).toBe(3)
  })

  it('construit toujours le pricing avec le contrat figé', async () => {
    const store = await storeRenseigne()
    await store.loadFromDeal({
      id: 11, reference: 'DEAL-FROZEN-PAYLOAD', script_snapshot: VALIDE,
      market_snapshot: {
        underlyings: [{ name: 'SX5E', ticker: '^STOXX50E', ccy: 'EUR', sigma: 20, q: 2 }],
        user_params: { COUPON: 0.0175 },
      },
      T: 3, devise: 'EUR', nominal: 1_000_000,
      strike_date: '2026-09-13', value_date: '2026-09-15',
      maturity_date: '2029-09-13', payment_date: '2029-09-18',
    })

    // Simule un futur composant mal protégé : les hypothèses de marché sont
    // autorisées, l'identité et le payoff ne doivent jamais partir au moteur.
    store.script = 'AT MATURITY:\n  PAY 0\n'
    store.paramOverrides.COUPON = 99
    store.underlyings[0].name = 'AUTRE'
    store.underlyings[0].ticker = 'OTHER'
    store.underlyings[0].sigma = 31
    store.globalParams.maturity_date = '2035-01-01'

    const body = store.pricingBody()
    expect(body.script).toBe(VALIDE)
    expect(body.user_params.COUPON).toBeCloseTo(0.0175, 10)
    expect(body.underlyings[0]).toMatchObject({
      name: 'SX5E', ticker: '^STOXX50E', ccy: 'EUR', sigma: 0.31,
    })
    expect(body.maturity_date).toBe('2029-09-13')
    expect(body.payment_date).toBe('2029-09-18')
  })

  it('refuse un panier dont la taille diverge malgré le verrou', async () => {
    const store = await storeRenseigne()
    await store.loadFromDeal({
      id: 12, reference: 'DEAL-BASKET-GUARD', script_snapshot: VALIDE,
      market_snapshot: {
        underlyings: [{ name: 'SX5E', ticker: '^STOXX50E', ccy: 'EUR' }],
      },
      T: 3, devise: 'EUR', strike_date: '2026-09-13', maturity_date: '2029-09-13',
    })

    store.underlyings.push({ ...store.underlyings[0], name: 'DAX', ticker: '^GDAXI' })

    expect(() => store.pricingBody()).toThrow('panier contractuel de 1 sous-jacent')
  })
})

describe('un résultat de pricing reste lié à ses entrées', () => {
  it('devient périmé dès qu’un PARAM change', async () => {
    const store = await storeRenseigne()
    const parseFetch = globalThis.fetch
    globalThis.fetch = vi.fn(async (url, opts) => {
      if (String(url).includes('/api/parse')) return parseFetch(url, opts)
      return {
        ok: true,
        json: async () => ({ price: 1, pricing_receipt: { pricing_input: { seed: 42 } } }),
      }
    })

    await store.runPricing()
    expect(store.resultIsStale).toBe(false)
    store.paramOverrides.COUPON = 3
    expect(store.resultIsStale).toBe(true)
  })

  it('ignore une réponse arrivée après une modification', async () => {
    const store = await storeRenseigne()
    let release
    const pending = new Promise(resolve => { release = resolve })
    globalThis.fetch = vi.fn(async url => {
      if (String(url).includes('/api/price')) await pending
      return { ok: true, json: async () => ({ price: 1 }) }
    })

    const run = store.runPricing()
    store.paramOverrides.COUPON = 4
    release()
    await run

    expect(store.result).toBeNull()
    expect(store.error).toContain('paramètres ont changé')
  })
})

describe('la maturité est une date contractuelle éditable', () => {
  it('fait de AT MATURITY une date et en déduit T', async () => {
    setActivePinia(createPinia())
    globalThis.fetch = serveurDeParse({ declare: {
      params: DECLARATIONS.params, constats: [],
    } })
    const store = usePricingStore()
    store.script = 'PARAM COUPON = 2%\nAT MATURITY:\n  PAY 1\n'
    await store.parseScript()
    store.globalParams.strike_date = '2026-09-13'

    store.setMaturityDate('2028-09-13')

    expect(store.maturityDate).toBe('2028-09-13')
    expect(store.globalParams.T).toBeCloseTo(2.00137, 4)
    expect(store.pricingBody().maturity_date).toBe('2028-09-13')
  })

  it('restaure la date objet d’un CONSTAT MATURITE unique', async () => {
    setActivePinia(createPinia())
    globalThis.fetch = serveurDeParse({ declare: {
      params: [], constats: [{ name: 'MATURITE', kind: 'single' }],
    } })
    const store = usePricingStore()
    await store.loadFromDeal({
      id: 17, reference: 'SINGLE-DATE',
      script_snapshot: 'CONSTAT MATURITE\nAT MATURITE:\n  PAY 1\n',
      market_snapshot: {
        underlyings: [{ name: 'SX5E', ticker: '^STOXX50E', ccy: 'EUR' }],
        constats: {
          MATURITE: { date: '2027-12-10', convention: 'following', settlement_lag: 3 },
        },
      },
      T: 1.25, devise: 'EUR', strike_date: '2026-09-13',
      maturity_date: '2027-12-10',
    })

    expect(store.maturityDate).toBe('2027-12-10')
    expect(store.constatOverrides.MATURITE).toBe('2027-12-10')
    expect(store.buildConstats()).toEqual({ MATURITE: '2027-12-10' })
  })
})

describe('la date de valorisation pilote le marché et le moteur', () => {
  it('route une date avant strike vers le pricer forward-start', async () => {
    const store = await storeRenseigne()
    store.globalParams.strike_date = '2026-12-11'
    store.globalParams.value_date = '2026-12-15'
    store.globalParams.valuation_date = '2026-09-13'
    store.globalParams.maturity_date = '2028-06-09'
    let pricedUrl = ''
    globalThis.fetch = vi.fn(async url => {
      if (String(url).includes('/api/price')) pricedUrl = String(url)
      return { ok: true, json: async () => ({ price: 0.99 }) }
    })

    await store.runPricing()

    expect(store.isPreStrike()).toBe(true)
    expect(pricedUrl).toContain('/api/price/in-life')
    expect(store.result.price).toBe(0.99)
  })

  it('recharge σ, q et corrélation à la date choisie sans renommer le deal', async () => {
    const store = await storeRenseigne()
    store.underlyings = [{
      ...store.underlyings[0], name: 'LVMH', ticker: 'MC.PA', sigma: 26, q: 2,
    }]
    store.globalParams.valuation_date = '2026-09-13'
    store.result = { price: 0.88 }
    const urls = []
    globalThis.fetch = vi.fn(async url => {
      urls.push(String(url))
      if (String(url).includes('/api/finance/hist_vol')) {
        return { ok: true, json: async () => ({
          tickers: ['MC.PA'], vols: { 'MC.PA': 0.30334158 },
          corr: { 'MC.PA': { 'MC.PA': 1 } }, missing: [], n_obs: 252,
          requested_asof: '2026-09-13', asof_effective: '2026-09-11',
        }) }
      }
      if (String(url).includes('/api/finance/dividends')) {
        return { ok: true, json: async () => ({
          ok: true, yield_declared: 0.031303, dividends: [1, 2],
          pays_dividends: true, suspect: false,
        }) }
      }
      return { ok: false, json: async () => ({}) }
    })

    await store.onValuationDateChange()

    expect(urls.find(url => url.includes('/hist_vol'))).toContain('asof=2026-09-13')
    expect(urls.find(url => url.includes('/dividends'))).toContain('asof=2026-09-13')
    expect(store.underlyings[0].name).toBe('LVMH')
    expect(store.underlyings[0].sigma).toBe(30.334158)
    expect(store.underlyings[0].q).toBe(3.1303)
    expect(store.marketDataEffectiveDate).toBe('2026-09-11')
    expect(store.result).toBeNull()
  })
})
