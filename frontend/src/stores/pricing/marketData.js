// Chargement des données de marché.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.
import { apiErrorMessage, apiFetch } from '../../utils/api.js'
import { fractionToPercentExact } from '../../utils/underlyingDefaults.js'
import { recordMarketReference } from '../../utils/marketProvenance.js'
import { ref, watch } from 'vue'
import { _histVolUrl } from './helpers.js'

export function installMarketData(s) {
  const {
    _clearMtf, backtest, comparator, contractTermsLocked, corrMatrix, currentProduct,
    globalParams, grid, kid, openedDeal, paths, proba, profile, result, rightTab, scenarios,
    solver, underlyings,
  } = s

  // ── Yahoo Finance data loader ─────────────────────────────────────
  const yfStatus = ref('')
  const marketDataLoading = ref(false)
  const marketDataAsOf = ref('')
  const marketDataEffectiveDate = ref('')
  s._marketDataRevision = 0
  let _marketContextRevision = 0
  s.automaticMarketRequest = null
  s.lastAutomaticMarketKey = null
  watch(()=>JSON.stringify([underlyings.value,corrMatrix.value,globalParams,currentProduct.value,openedDeal.value?.id]),
    ()=>{ _marketContextRevision++ },{flush:'sync'})
  function _marketResponseCurrent(revision, contextRevision) {
    if(revision!==s._marketDataRevision) return false
    if(contextRevision!==_marketContextRevision) {
      yfStatus.value='Réponse ignorée : le panier ou les hypothèses ont changé. Relancez le chargement.'
      return false
    }
    return true
  }

  /** Profil de dividende d'un titre à une date donnée : rendement déclaré,
   *  rendement implicite lu dans l'écart des séries, et les détachements qui
   *  fondent le chiffre. `asof` vide = aujourd'hui. */
  async function loadDividendProfile(ticker, asof) {
    try {
      const params = new URLSearchParams({ ticker })
      if (asof) params.set('asof', asof)
      const res = await apiFetch(`/api/finance/dividends?${params}`)
      return res.ok ? await res.json() : null
    } catch { return null }
  }

  function _marketDateLabel(data, requestedAsOf) {
    const effective = data.asof_effective || ''
    marketDataAsOf.value = requestedAsOf || data.requested_asof || ''
    marketDataEffectiveDate.value = effective
    if (!requestedAsOf && !effective) return ''
    if (effective && requestedAsOf && effective !== requestedAsOf) {
      return ` · marché au ${effective} (demandé ${requestedAsOf})`
    }
    return ` · marché au ${effective || requestedAsOf}`
  }

  function _invalidatePricingOutputs() {
    s._pricingRevision += 1
    result.value = null; profile.value = null; paths.value = null
    proba.value = null; backtest.value = null; _clearMtf()
    solver.value = null; grid.value = null; scenarios.value = null
    kid.value = null; comparator.value = null
    rightTab.value = 'empty'
  }

  async function loadYfOne(idx, options = {}) {
    const u = underlyings.value[idx]
    if (!u || !u.ticker?.trim()) { yfStatus.value = '⚠ Entrez un ticker (ex: ^STOXX50E)'; return }
    const tk = u.ticker.trim().toUpperCase()
    const requestedAsOf = options.asof ?? globalParams.valuation_date ?? ''
    const revision = ++s._marketDataRevision
    // On a draft, normalising the identifier is useful. On a booked deal the
    // ticker is contractual identity: refreshing market data must not rewrite
    // it, even cosmetically.
    if (!contractTermsLocked.value) underlyings.value[idx].ticker = tk
    const contextRevision = _marketContextRevision
    marketDataLoading.value = true
    yfStatus.value = `Chargement ${tk}${requestedAsOf ? ` au ${requestedAsOf}` : ''}…`
    try {
      const res = await apiFetch(_histVolUrl([tk], requestedAsOf))
      const data = await res.json()
      if (!_marketResponseCurrent(revision,contextRevision)) return
      if (!res.ok) throw Error(apiErrorMessage(data,'Chargement du marché refusé.'))
      if (data.error) { yfStatus.value = `⚠ ${tk}: ${data.error}`; return }
      // backend renvoie la clé uppercase identique à tk
      const vol = data.vols?.[tk] ?? null
      // Le dividende ne vient plus du champ instantané de Yahoo : il est
      // reconstruit à la DATE DE VALORISATION, avec le détail des
      // détachements qui le fondent (voir services/market_data.dividend_profile).
      const div = data.dividend_profiles?.[tk] ?? await loadDividendProfile(tk, requestedAsOf || null)
      if (!_marketResponseCurrent(revision,contextRevision)) return
      const q = div?.ok ? div.yield_declared : null
      if (vol != null) {
        // Keep enough precision for the Pricer to reproduce the deal MtM with
        // the same seed. Formatting belongs to the input, not to the value sent
        // to the engine.
        underlyings.value[idx].vol_level_source = 'realized'
        underlyings.value[idx].sigma = fractionToPercentExact(vol)
        underlyings.value[idx].alpha = fractionToPercentExact(vol)
        if (q != null) underlyings.value[idx].q = fractionToPercentExact(q)
        if (!contractTermsLocked.value
            && /^Sous-jacent \d+$/.test(underlyings.value[idx].name || '')) {
          underlyings.value[idx].name = tk
        }
        underlyings.value[idx].dividendProfile = div?.ok ? div : null
        recordMarketReference(underlyings.value[idx],data,tk,div)
        const suffixe = div?.ok
          ? (div.pays_dividends
              ? ` · ${div.dividends.length} détachement(s)` + (div.suspect ? ' ⚠ écart de sources' : '')
              : ' · ne verse pas de dividende')
          : ''
        const qLabel = q != null ? `, q=${(q*100).toFixed(2)}%` : ', q conservé (indisponible)'
        yfStatus.value = `✓ ${tk} — σ=${(vol*100).toFixed(1)}%${qLabel} · ${data.n_obs} rendements${_marketDateLabel(data, requestedAsOf)}${suffixe}`
      } else {
        yfStatus.value = `⚠ ${tk}: introuvable sur Yahoo Finance`
        if (data.missing?.includes(tk)) yfStatus.value += ' — vérifiez le ticker'
      }
    } catch (e) { if (_marketResponseCurrent(revision,contextRevision)) yfStatus.value = '⚠ ' + e.message }
    finally { if (revision === s._marketDataRevision) marketDataLoading.value = false }
  }

  async function loadYfAll(options = {}) {
    // Normalise tickers uppercase avant envoi
    if (!contractTermsLocked.value) {
      underlyings.value.forEach(u => { if (u.ticker) u.ticker = u.ticker.trim().toUpperCase() })
    }
    const pairs = underlyings.value
      .map((u, i) => ({ u, idx: i, tick: (u.ticker || '').trim().toUpperCase() }))
      .filter(p => p.tick)
    if (!pairs.length) { yfStatus.value = '⚠ Aucun ticker renseigné'; return }
    const requestedAsOf = options.asof ?? globalParams.valuation_date ?? ''
    const revision = ++s._marketDataRevision
    const contextRevision = _marketContextRevision
    marketDataLoading.value = true
    yfStatus.value = `Téléchargement${requestedAsOf ? ` au ${requestedAsOf}` : ''} en cours…`
    const tickers = pairs.map(p => p.tick)
    try {
      const res = await apiFetch(_histVolUrl(tickers, requestedAsOf))
      const data = await res.json()
      if (!_marketResponseCurrent(revision,contextRevision)) return
      if (!res.ok) throw Error(apiErrorMessage(data,'Chargement du marché refusé.'))
      if (data.error) { yfStatus.value = '⚠ ' + data.error; return }

      const dividendProfiles = await Promise.all(
        pairs.map(({ tick }) => data.dividend_profiles?.[tick] ?? loadDividendProfile(tick, requestedAsOf || null)))
      if (!_marketResponseCurrent(revision,contextRevision)) return

      pairs.forEach(({ u, idx, tick }, pairIndex) => {
        const vol = data.vols?.[tick] ?? null
        if (vol == null) return
        const div = dividendProfiles[pairIndex]
        const q = div?.ok ? div.yield_declared : null
        const references = u.market_data?.references
        const overridden = field => options.automatic && references?.[field]?.ticker === tick
          && Number(u[field])/100 !== (references[field].applied_value ?? references[field].value)
        const keepSigma = overridden('sigma')
        const keepQ = overridden('q')
        if (!keepSigma) {
          u.vol_level_source = 'realized'
          u.sigma = fractionToPercentExact(vol)
          u.alpha = fractionToPercentExact(vol)
        }
        if (q != null && !keepQ) u.q = fractionToPercentExact(q)
        if (!contractTermsLocked.value
            && /^Sous-jacent \d+$/.test(underlyings.value[idx].name || '')) {
          underlyings.value[idx].name = tick
        }
        underlyings.value[idx].dividendProfile = div?.ok ? div : null
        recordMarketReference(underlyings.value[idx],data,tick,div)
        if (keepSigma) u.market_data.references.sigma.applied_value = vol
        if (keepQ && q != null) u.market_data.references.q.applied_value = q
      })

      // Apply correlation matrix
      for (const left of pairs) for (const right of pairs) {
        const i = left.idx, j = right.idx
        const ti = left.tick, tj = right.tick
        if (i !== j && data.corr[ti]?.[tj] !== undefined) {
          if (!corrMatrix.value[i]) corrMatrix.value[i] = []
          corrMatrix.value[i][j] = parseFloat(data.corr[ti][tj].toFixed(4))
        }
      }

      const fnd = data.tickers.join(', ')
      const miss = data.missing?.length ? ` ⚠ Introuvables: ${data.missing.join(', ')}` : ''
      const missingDividends = pairs.filter((_, i) => !dividendProfiles[i]?.ok).map(p => p.tick)
      const divWarning = missingDividends.length
        ? ` · q conservé pour ${missingDividends.join(', ')}` : ''
      yfStatus.value = `✓ ${fnd} — σ, q, corr mis à jour · ${data.n_obs} rendements${_marketDateLabel(data, requestedAsOf)}${divWarning}${miss}`
      return !data.missing?.length && pairs.every(({tick}) => data.vols?.[tick] != null)
    } catch (e) { if (_marketResponseCurrent(revision,contextRevision)) yfStatus.value = '⚠ ' + e.message }
    finally { if (revision === s._marketDataRevision) marketDataLoading.value = false }
  }

  function onUnderlyingSelection() {
    if (contractTermsLocked.value) return
    return _loadAutomaticMarket()
  }

  function _loadAutomaticMarket() {
    const asof = globalParams.valuation_date
    const tickers = underlyings.value.map(u => (u.ticker || '').trim().toUpperCase())
    if (!asof || !tickers.some(Boolean)) return
    const key = JSON.stringify([asof, tickers])
    if (s.automaticMarketRequest?.key === key) return s.automaticMarketRequest.promise
    if (s.lastAutomaticMarketKey === key && !s.automaticMarketRequest) return
    const pending = {key, promise: null}
    s.automaticMarketRequest = pending
    pending.promise = loadYfAll({ asof, automatic: true }).then(success => {
      if (s.automaticMarketRequest === pending && success) s.lastAutomaticMarketKey = key
    }).finally(() => {
      if (s.automaticMarketRequest === pending) s.automaticMarketRequest = null
    })
    return pending.promise
  }

  async function onValuationDateChange() {
    _invalidatePricingOutputs()
    const asof = globalParams.valuation_date || ''
    if (!asof) {
      yfStatus.value = '⚠ Renseignez une date de valorisation pour charger le marché.'
      return
    }
    await _loadAutomaticMarket()
  }

  /** Clôtures NUES à une date, par ticker : { TICKER: {close, date} }.
   *
   *  Le fixing d'un produit structuré est la clôture non ajustée — celle que
   *  le term sheet cite. Cet écran lisait le magasin de prix AMC, qui est
   *  volontairement auto-ajusté (voir core/amc_prices.py) parce qu'il sert au
   *  FIFO et à l'attribution de portefeuille, où la série total-return est la
   *  bonne. Résultat : des spots déflatés des dividendes versés depuis, donc
   *  en contradiction avec le niveau que le moteur a réellement utilisé — et
   *  vides tant qu'on n'avait pas semé le magasin à la main.
   *
   *  On lit désormais la même source que le pricer, à la demande. */
  async function loadStrikeCloses(tickers, jour) {
    const tk = [...new Set((tickers || []).filter(Boolean))]
    if (!tk.length || !jour) return {}
    // Marge arrière : une date de strike un week-end ou un férié n'a pas de
    // cours, c'est la dernière clôture connue qui fait foi — même convention
    // que le rejeu côté serveur.
    const debut = new Date(jour)
    debut.setDate(debut.getDate() - 10)
    const q = new URLSearchParams({ tickers: tk.join(','),
                                     start: debut.toISOString().split('T')[0], end: jour })
    try {
      const res = await apiFetch(`/api/finance/hist_prices?${q}`)
      if (!res.ok) return {}
      const data = await res.json()
      const dates = data.dates || []
      let idx = -1
      for (let i = 0; i < dates.length; i++) { if (dates[i] <= jour) idx = i; else break }
      if (idx < 0) return {}
      const out = {}
      for (const t of tk) {
        const serie = data.prices?.[t]
        if (serie && serie[idx]) out[t] = { close: serie[idx], date: dates[idx] }
      }
      return out
    } catch { return {} }
  }

  Object.assign(s, { yfStatus, marketDataLoading, marketDataAsOf, marketDataEffectiveDate, _marketContextRevision, _marketResponseCurrent, loadDividendProfile, _marketDateLabel, _invalidatePricingOutputs, loadYfOne, loadYfAll, onUnderlyingSelection, _loadAutomaticMarket, onValuationDateChange, loadStrikeCloses })
}
