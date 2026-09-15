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
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { usePricingStore } from './pricing.js'
import { findProductModel } from '../utils/productModels.js'

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

  it('garde le tenor cote quand la maturite effective de la RFQ est ajustee', async () => {
    const store = await storeRenseigne()
    const rfq = {
      ...AO,
      params: {
        ...AO.params,
        strike_date: '2026-09-29',
        maturity_date: '2029-09-29',
        payment_date: '2029-10-03',
        T: 3.0007,
        constats: {
          OBSERVATIONS: {
            start_date: '2026-09-29', end_date: '2029-09-29',
            roll_date: '2026-12-29', frequency: '3M',
            convention: 'following', settlement_lag: 0,
          },
        },
      },
    }

    await store.loadFromRfq(rfq)
    store.syncTenorFromMaturity()

    expect(store.currentRfqId).toBe(rfq.id)
    expect(store.globalParams.T).toBe(3.0007)
  })

  it('reprend tout le panier et sa corrélation jusque dans le prochain pricing', async () => {
    const store = await storeRenseigne()
    await store.loadFromRfq({
      ...AO,
      params: {
        ...AO.params,
        underlyings: [
          { name: 'LVMH', ticker: 'MC.PA', ccy: 'EUR', sigma: 0.21, q: 0.018 },
          { name: 'DAX', ticker: '^GDAXI', ccy: 'EUR', sigma: 0.27, q: 0.031 },
        ],
        corr_matrix: [[1, 0.45], [0.45, 1]],
      },
    })

    expect(store.underlyings.map(u => [u.ticker, u.sigma, u.q])).toEqual([
      ['MC.PA', 21, 1.7999999999999998],
      ['^GDAXI', 27, 3.1],
    ])
    const body = store.pricingBody()
    expect(body.underlyings.map(u => [u.ticker, u.sigma, u.q])).toEqual([
      ['MC.PA', 0.21, 0.018],
      ['^GDAXI', 0.27, 0.031],
    ])
    expect(body.corr_matrix).toEqual([[1, 0.45], [0.45, 1]])
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
    const maintenant = new Date()
    const aujourdHuiLocal = new Date(
      maintenant.getTime() - maintenant.getTimezoneOffset() * 60_000,
    ).toISOString().slice(0, 10)
    expect(store.globalParams.valuation_date).toBe(aujourdHuiLocal)
    expect(store.isInLife()).toBe(aujourdHuiLocal > '2026-09-03')
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

  it('un deal rouvert se valorise aujourd’hui, avant ou après son strike', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-14T09:00:00Z'))
    try {
      const store = await storeRenseigne()
      const forward = {
        id: 30, reference: 'FWD-START', script_snapshot: VALIDE,
        market_snapshot: { underlyings: [{ name: 'SPX', ticker: '^GSPC', ccy: 'EUR' }] },
        T: 1.5, devise: 'EUR', nominal: 1_680_000,
        trade_date: '2026-09-11', strike_date: '2026-12-11', value_date: '2026-12-15',
        maturity_date: '2028-06-09', payment_date: '2028-06-14',
      }

      await store.loadFromDeal(forward)
      expect(store.globalParams.valuation_date).toBe('2026-09-14')
      expect(store.isPreStrike()).toBe(true)

      await store.loadFromDeal({ ...forward, id: 31, trade_date: '2026-10-01' })
      expect(store.globalParams.valuation_date).toBe('2026-09-14')

      await store.loadFromDeal({ ...forward, id: 32, trade_date: '2026-09-01',
                                 strike_date: '2026-09-03' })
      expect(store.globalParams.valuation_date).toBe('2026-09-14')
      expect(store.isInLife()).toBe(true)
    } finally {
      vi.useRealTimers()
    }
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

/**
 * Un serveur de parse qui lit vraiment les déclarations du texte : PARAM,
 * PARAM(), CONSTAT et années `AT`. `retiens` peut suspendre une réponse pour
 * rejouer l'ordre d'arrivée de deux validations.
 */
function serveurQuiLit({ retiens = null, autres = null } = {}) {
  return vi.fn(async (url, opts) => {
    if (!String(url).includes('/api/parse')) {
      return autres ? autres(url, opts) : { ok: false, json: async () => ({}) }
    }
    const texte = JSON.parse(opts.body).script
    if (retiens) await retiens(texte)
    if (texte.includes('INDIC(WOF\n')) {
      return { ok: true, json: async () => ({ ok: false, errors: 'Ligne 6 : expression incomplète' }) }
    }
    const params = [...texte.matchAll(/^PARAM(\(\))?\s+(\w+)\s*=\s*([\d.]+)(%?)/gm)].map(m => ({
      name: m[2], kind: m[1] ? 'array' : 'scalar',
      raw_default: Number(m[3]), display_default: Number(m[3]), is_pct: m[4] === '%',
    }))
    const constats = [...texte.matchAll(
      /^CONSTAT(\(\)(?:\(\))?)?\s+(\w+)(?:[ \t]+(MIN|MAX|AVG))?(?:[ \t]+(PERIOD))?/gm)].map(m => ({
      name: m[2], kind: !m[1] ? 'single' : (m[1] === '()()' ? 'nested_schedule' : 'schedule'),
      reduction: m[3] || null, window_scope: m[4] ? 'period' : 'length',
    }))
    const at_dates = [...texte.matchAll(/^AT\s+([\d.,\s]+):/gm)]
      .flatMap(m => m[1].split(',').map(Number)).sort((a, b) => a - b)
    return { ok: true, json: async () => ({
      ok: true, params, constats, at_dates,
      has_stop: /\bSTOP\b/.test(texte), has_maturity_event: /^AT MATURITY/m.test(texte),
    }) }
  })
}

const ATHENA_NORMAL = `# Autocall Athena
PARAM COUPON = 8%
PARAM M_AC_BAR = 100%
PARAM M_KI_BAR = 60%

AT 1, 2, 3:
  SET CALL = INDIC(WOF >= M_AC_BAR)
  PAY CALL * COUPON * INDEX
  PAY CALL * 1
  IF CALL = 1:
    STOP

AT MATURITY:
  SET KI = INDIC(WOF < M_KI_BAR)
  PAY (1 - KI) * 1
  PAY KI * WOF
`

const appelsParse = () => globalThis.fetch.mock.calls
  .filter(([url]) => String(url).includes('/api/parse')).length

async function storeQuiLit(texte = VALIDE) {
  setActivePinia(createPinia())
  globalThis.fetch = serveurQuiLit()
  const store = usePricingStore()
  store.script = texte
  await store.parseScript()
  return store
}

describe('la validation est un geste, pas un effet de la frappe', () => {
  it('ne relit rien pendant la frappe et signale le script non validé', async () => {
    const store = await storeQuiLit()
    store.paramOverrides.COUPON = 1.334167
    const avant = appelsParse()

    store.script = VALIDE.replace('PARAM COUPON = 2%', 'PARAM COUPON = 6')

    expect(store.scriptDirty).toBe(true)
    expect(appelsParse()).toBe(avant)
    expect(store.scriptParams[0]).toMatchObject({ display_default: 2, is_pct: true })
    expect(store.paramOverrides.COUPON).toBe(1.334167)
  })

  it('une valeur initiale changée remplace la saisie, et le dit', async () => {
    const store = await storeQuiLit()
    store.paramOverrides.COUPON = 1.334167
    store.script = VALIDE.replace('PARAM COUPON = 2%', 'PARAM COUPON = 3%')

    expect(await store.validateScript()).toBe(true)

    expect(store.scriptDirty).toBe(false)
    expect(store.paramOverrides.COUPON).toBe(3)
    expect(store.validationReport.replaced).toEqual([{
      name: 'COUPON', before: 1.334167, beforePct: true, after: 3, afterPct: true,
    }])
  })

  it('une déclaration inchangée ne touche pas la saisie', async () => {
    const store = await storeQuiLit()
    store.paramOverrides.COUPON = 1.334167
    store.script = `${VALIDE}# une ligne de commentaire\n`

    await store.validateScript()

    expect(store.paramOverrides.COUPON).toBe(1.334167)
    expect(store.validationReport).toEqual({ replaced: [], keptRows: [] })
  })

  it('une valeur jamais saisie suit le script sans être signalée', async () => {
    const store = await storeQuiLit()
    store.script = VALIDE.replace('PARAM COUPON = 2%', 'PARAM COUPON = 2.5%')

    await store.validateScript()

    expect(store.paramOverrides.COUPON).toBe(2.5)
    expect(store.validationReport.replaced).toEqual([])
  })

  it('D6 : 8, Ctrl+S, ajout du %, Ctrl+S donne 8 %', async () => {
    const store = await storeQuiLit(VALIDE.replace('PARAM COUPON = 2%', 'PARAM COUPON = 8'))
    expect(store.buildUserParams().COUPON).toBe(8)

    store.script = VALIDE.replace('PARAM COUPON = 2%', 'PARAM COUPON = 8%')
    await store.validateScript()

    expect(store.paramOverrides.COUPON).toBe(8)
    expect(store.buildUserParams().COUPON).toBeCloseTo(0.08, 12)
  })

  it('PARAM() : seules les lignes restées à l’ancienne valeur suivent le script (M11)', async () => {
    const DEGRESSIF = 'PARAM() M_AC_BAR = 100%\nCONSTAT() OBS\n\nAT OBS:\n  PAY 1\n'
    const store = await storeQuiLit(DEGRESSIF)
    store.paramOverrides.M_AC_BAR = [100, 95, 100]

    store.script = DEGRESSIF.replace('= 100%', '= 105%')
    await store.validateScript()

    expect(store.paramOverrides.M_AC_BAR).toEqual([105, 95, 105])
    expect(store.validationReport.keptRows).toEqual([
      { name: 'M_AC_BAR', count: 1, unitChanged: false },
    ])
  })

  it('un chargement devient la référence et ne reporte rien', async () => {
    const store = await storeQuiLit()
    store.paramOverrides.COUPON = 1.334167
    const AO = {
      id: 5, script_snapshot: VALIDE.replace('PARAM COUPON = 2%', 'PARAM COUPON = 5%'),
      params: { user_params: { COUPON: 0.04 } }, quotes: [],
    }

    await store.loadFromRfq(AO)
    expect(store.paramOverrides.COUPON).toBeCloseTo(4, 10)
    expect(store.validationReport).toBeNull()

    // Revalider le texte chargé ne change rien : la référence est le chargement.
    store.script = `${AO.script_snapshot}# relu\n`
    await store.validateScript()
    expect(store.paramOverrides.COUPON).toBeCloseTo(4, 10)
  })

  it('ignore une réponse de validation arrivée après une plus récente', async () => {
    setActivePinia(createPinia())
    let libere
    const retenue = new Promise(resolve => { libere = resolve })
    globalThis.fetch = serveurQuiLit({
      retiens: texte => (texte.includes('COUPON = 7%') ? retenue : null),
    })
    const store = usePricingStore()
    store.script = VALIDE
    await store.parseScript()

    store.script = VALIDE.replace('PARAM COUPON = 2%', 'PARAM COUPON = 7%')
    const ancienne = store.validateScript()
    store.script = VALIDE.replace('PARAM COUPON = 2%', 'PARAM COUPON = 9%')
    expect(await store.validateScript()).toBe(true)
    libere()

    expect(await ancienne).toBe(false)
    expect(store.paramOverrides.COUPON).toBe(9)
    expect(store.scriptDirty).toBe(false)
  })

  it('un calcul valide d’abord et s’arrête sur une erreur de script', async () => {
    const store = await storeQuiLit()
    store.script = CASSE

    await store.runPricing()

    const urls = globalThis.fetch.mock.calls.map(([url]) => String(url))
    expect(urls.some(url => url.includes('/api/price'))).toBe(false)
    expect(store.parseError).toBeTruthy()
    expect(store.error).toContain('Script non valide')
  })

  it('un calcul price le script validé, avec ses nouvelles valeurs', async () => {
    setActivePinia(createPinia())
    let corps = null
    globalThis.fetch = serveurQuiLit({
      autres: async (url, opts) => {
        if (String(url).includes('/api/price')) corps = JSON.parse(opts.body)
        return { ok: true, json: async () => ({ price: 1 }) }
      },
    })
    const store = usePricingStore()
    store.script = VALIDE
    await store.parseScript()
    store.script = `${VALIDE.replace('PARAM COUPON = 2%', 'PARAM COUPON = 4%')}PARAM FLOOR_LVL = 90%\n`

    await store.runPricing()

    expect(corps.script).toContain('COUPON = 4%')
    expect(corps.user_params).toEqual({ COUPON: 0.04, FLOOR_LVL: 0.9 })
  })

  it('revenir au texte validé après un essai raté efface l’erreur', async () => {
    const store = await storeQuiLit()
    store.script = CASSE
    await store.validateScript()
    expect(store.parseError).toBeTruthy()

    store.script = VALIDE
    expect(await store.ensureScriptValidated()).toBe(true)
    expect(store.parseError).toBeNull()
  })
})

/**
 * M4 (14/09/2026) : la maturité est toujours éditable et vaut la dernière date
 * de constatation du produit, quels que soient les échéanciers.
 *
 * La règle du 13/09 retenait la fin des échéanciers et verrouillait le champ :
 * deux ans de coupons sur une note à trois ans affichaient une maturité à deux
 * ans, un T de deux ans, un paiement proposé à deux ans — et un booking refusé.
 */
describe('la maturité est la dernière constatation du produit', () => {
  const NOTE = `PARAM COUPON = 5%
CONSTAT() COUPONS
CONSTAT MATURITE

AT COUPONS:
  PAY COUPON

AT MATURITE:
  PAY 1
`
  const COUPONS_2A = {
    start_date: '2026-09-14', end_date: '2028-09-14', roll_date: '2026-09-14',
    frequency: { value: 1, unit: 'Y' },
  }

  async function note({ autres } = {}) {
    setActivePinia(createPinia())
    globalThis.fetch = serveurQuiLit({ autres })
    const store = usePricingStore()
    store.script = NOTE
    await store.parseScript()
    store.globalParams.strike_date = '2026-09-14'
    Object.assign(store.constatOverrides.COUPONS, COUPONS_2A)
    store.constatOverrides.MATURITE = '2029-09-14'
    return store
  }

  it('deux ans de coupons et une maturité à trois ans : trois ans', async () => {
    const store = await note()
    store.syncTenorFromMaturity()

    expect(store.maturityDateEditable).toBe(true)
    expect(store.maturityDate).toBe('2029-09-14')
    expect(store.globalParams.T).toBeCloseTo(1096 / 365.25, 5)
    expect(store.pricingBody().maturity_date).toBe('2029-09-14')
  })

  it('déplace les constatations terminales et laisse les coupons en place', async () => {
    const store = await note()

    expect(store.setMaturityDate('2030-03-14')).toBe(true)

    expect(store.constatOverrides.MATURITE).toBe('2030-03-14')
    expect(store.constatOverrides.COUPONS).toMatchObject(COUPONS_2A)
    expect(store.maturityDate).toBe('2030-03-14')
  })

  it('refuse une maturité avancée avant la fin d’un échéancier non terminal (M12)', async () => {
    const store = await note()

    expect(store.setMaturityDate('2028-06-14')).toBe(false)

    expect(store.maturityError).toContain('COUPONS')
    expect(store.maturityError).toContain('14/09/2028')
    expect(store.constatOverrides.MATURITE).toBe('2029-09-14')
    expect(store.maturityDate).toBe('2029-09-14')
  })

  it('échéancier et date unique le même jour bougent ensemble, roll aligné compris', async () => {
    const store = await note()
    Object.assign(store.constatOverrides.COUPONS, {
      end_date: '2029-09-14', roll_date: '2029-09-14',
    })

    expect(store.setMaturityDate('2030-09-16')).toBe(true)

    expect(store.constatOverrides.COUPONS.end_date).toBe('2030-09-16')
    expect(store.constatOverrides.COUPONS.roll_date).toBe('2030-09-16')
    expect(store.constatOverrides.MATURITE).toBe('2030-09-16')
  })

  it('un calendrier trimestriel garde son ancrage quand sa fin bouge', async () => {
    const TRIMESTRIEL = 'CONSTAT() OBS\n\nAT OBS:\n  PAY 0.01\n\nAT OBS.last:\n  PAY 1\n'
    const store = await storeQuiLit(TRIMESTRIEL)
    store.globalParams.strike_date = '2026-09-14'
    Object.assign(store.constatOverrides.OBS, {
      start_date: '2026-09-14', end_date: '2029-09-14', roll_date: '2026-12-14',
      frequency: { value: 3, unit: 'M' },
    })

    expect(store.setMaturityDate('2029-12-14')).toBe(true)

    expect(store.constatOverrides.OBS).toMatchObject({
      start_date: '2026-09-14', end_date: '2029-12-14', roll_date: '2026-12-14',
    })
    expect(store.maturityDate).toBe('2029-12-14')
  })

  it('reconnaît la constatation terminale par sa date, plus par son nom', async () => {
    const store = await storeQuiLit('CONSTAT ECHEANCE\n\nAT ECHEANCE:\n  PAY 1\n')
    store.constatOverrides.ECHEANCE = '2027-09-14'

    expect(store.maturityDate).toBe('2027-09-14')
    expect(store.setMaturityDate('2028-03-14')).toBe(true)
    expect(store.constatOverrides.ECHEANCE).toBe('2028-03-14')
  })

  it('affiche la date ajustée d’une constatation tombant un jour fermé', async () => {
    const appels = []
    const store = await note({
      autres: async (url, opts) => {
        if (String(url).includes('/api/calendar/resolve')) {
          const demande = JSON.parse(opts.body)
          appels.push(demande)
          const moved = demande.date === '2029-09-15' && demande.convention === 'following'
          return { ok: true, json: async () => ({
            date: moved ? '2029-09-17' : demande.date, source: demande.date, moved,
          }) }
        }
        return { ok: false, json: async () => ({}) }
      },
    })
    // La dernière constatation est la fin des coupons, un samedi, en jour
    // ouvré suivant.
    store.constatOverrides.MATURITE = ''
    Object.assign(store.constatOverrides.COUPONS, {
      end_date: '2029-09-15', convention: 'following',
    })

    expect(store.maturityDate).toBe('2029-09-15')
    await vi.waitFor(() => expect(store.maturityDate).toBe('2029-09-17'))
    expect(appels).toEqual([{ date: '2029-09-15', currency: 'EUR', convention: 'following' }])
    expect(store.pricingBody().maturity_date).toBe('2029-09-17')
  })

  it('mode Normal : refuse une maturité antérieure à la dernière année AT', async () => {
    const store = await storeQuiLit(ATHENA_NORMAL)
    store.globalParams.strike_date = '2026-09-14'
    store.globalParams.maturity_date = ''

    // 1 096 jours après le strike : la même arithmétique que le booking.
    expect(store.maturityDate).toBe('2029-09-14')
    expect(store.setMaturityDate('2028-09-14')).toBe(false)
    expect(store.maturityError).toContain('AT 3')
    expect(store.setMaturityDate('2030-09-14')).toBe(true)
    expect(store.maturityDate).toBe('2030-09-14')
  })
})

/**
 * « Modèles de produits » (M6–M9, M13) : une fiche, un nombre de sous-jacents
 * et un ténor ouvrent le Pricer complété, sans écran de saisie en plus.
 */
describe('un modèle de produit ouvre le Pricer complété', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-09-14T09:00:00Z'))
  })
  afterEach(() => { vi.useRealTimers() })

  async function ouvrir(key, options) {
    setActivePinia(createPinia())
    globalThis.fetch = serveurQuiLit()
    const store = usePricingStore()
    await store.loadFromProductModel(findProductModel(key), options)
    return store
  }

  it('génère panier, calendrier et maturité depuis la date de strike du Pricer', async () => {
    const store = await ouvrir('autocall_athena', { underlyingCount: 2, tenorCode: '3Y' })

    expect(store.script).toBe(findProductModel('autocall_athena').script)
    expect(store.scriptDirty).toBe(false)
    expect(store.underlyings.map(u => [u.name, u.ticker])).toEqual([
      ['Sous-jacent 1', ''], ['Sous-jacent 2', ''],
    ])
    expect(store.corrMatrix).toEqual([[1, 0], [0, 1]])
    expect(store.globalParams.strike_date).toBe('2026-09-14')
    expect(store.constatOverrides.OBSERVATIONS).toMatchObject({
      start_date: '2026-09-14', end_date: '2029-09-14', roll_date: '2026-09-14',
      frequency: { value: 1, unit: 'Y' }, convention: 'none', settlement_lag: 0,
    })
    expect(store.maturityDate).toBe('2029-09-14')
    expect(store.globalParams.T).toBeCloseTo(1096 / 365.25, 5)
    expect(store.paramOverrides).toMatchObject({ COUPON: 8, M_AC_BAR: 100, M_KI_BAR: 60 })
    expect(store.hasUnsavedSession()).toBe(false)
  })

  it('le calendrier ne suit pas un changement de strike (M13)', async () => {
    const store = await ouvrir('autocall_athena', { underlyingCount: 1, tenorCode: '2Y' })

    store.globalParams.strike_date = '2026-10-01'

    expect(store.constatOverrides.OBSERVATIONS).toMatchObject({
      start_date: '2026-09-14', end_date: '2028-09-14',
    })
    expect(store.maturityDate).toBe('2028-09-14')
  })

  it('pose les fenêtres de la fiche et borne le panier à son minimum', async () => {
    const store = await ouvrir('call_panier_moyenne', { underlyingCount: 1, tenorCode: '1Y' })

    expect(store.underlyings).toHaveLength(2)
    expect(store.constatOverrides.STRIKE_FIX).toMatchObject({
      date: '2026-09-14', window_length: { value: 10, unit: 'D' },
    })
    expect(store.constatOverrides.MATURITE).toMatchObject({
      date: '2027-09-14', window_length: { value: 30, unit: 'D' },
    })
    // La fenêtre de départ ne date pas la maturité : la constatation finale, si.
    expect(store.maturityDate).toBe('2027-09-14')
  })

  it('sans ténor : le script générique et aucune date inventée', async () => {
    const store = await ouvrir('phoenix', { underlyingCount: 3 })

    expect(store.underlyings).toHaveLength(3)
    expect(store.globalParams.strike_date).toBe('')
    expect(store.globalParams.value_date).toBe('')
    expect(store.constatOverrides.OBSERVATIONS).toMatchObject({ start_date: '', end_date: '' })
    expect(store.maturityDate).toBe('')
  })

  it('remplacer une session à échéancier ne laisse aucune déclaration sans valeur', async () => {
    // Le banc visuel l'a montré : la remise à zéro effaçait les valeurs des
    // CONSTAT mais gardait un instant leurs déclarations, et Economics
    // plantait au rendu sur `constatOverrides.OBS.frequency`.
    const store = await storeRenseigne()
    globalThis.fetch = serveurQuiLit()
    const declaresSansValeur = () => store.scriptConstats
      .filter(c => !(c.name in store.constatOverrides)).map(c => c.name)

    store.resetToDefaults()
    expect(declaresSansValeur()).toEqual([])

    const chargement = store.loadFromProductModel(findProductModel('phoenix'), { tenorCode: '2Y' })
    expect(declaresSansValeur()).toEqual([])
    await chargement
    expect(declaresSansValeur()).toEqual([])
    expect(store.constatOverrides.OBSERVATIONS.end_date).toBe('2028-09-14')
  })

  it('signale une session modifiée avant qu’un modèle la remplace', async () => {
    const store = await ouvrir('call', { tenorCode: '6M' })
    expect(store.hasUnsavedSession()).toBe(false)

    store.paramOverrides.STRIKE = 95
    expect(store.hasUnsavedSession()).toBe(true)
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
