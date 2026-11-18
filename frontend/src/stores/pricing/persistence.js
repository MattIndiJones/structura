// Variantes, sauvegarde du script et gestion des sous-jacents.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.
import { CALCULATION_LIMITS } from '../../utils/calculationBudget.js'
import { apiFetch } from '../../utils/api.js'
import { calculerDelta, contexteDepuisCorps } from '../../composables/useVariantDelta.js'
import { computed } from 'vue'
import { examples } from '../../data/payscriptTemplates.js'
import { _defaultUnderlying, _trie } from './helpers.js'

export function installPersistence(s) {
  const {
    _buildDividendCurve, _markSessionBaseline, _maturityDate, activeUnderlyingIdx,
    adoptedGeneratedScriptText, constatOverrides, contractTermsLocked, corrMatrix,
    currentScriptId, currentScriptName, fundingCurve, globalParams, paramOverrides, script,
    scriptConstats, scriptGenerationProvenance, scriptParams, underlyings, validateScript,
    variantInfo, yieldCurve,
  } = s

  function _scriptBody() {
    const provenance = scriptGenerationProvenance.value
      ? { ...scriptGenerationProvenance.value,
          modified_after_adoption: script.value !== adoptedGeneratedScriptText.value }
      : null
    return {
      script_text: script.value,
      params_json: JSON.stringify({ ...paramOverrides }),
      constats_json: JSON.stringify(JSON.parse(JSON.stringify(constatOverrides))),
      // Tout ce qu'il faut pour retrouver le pricing tel quel, pas seulement
      // le script. Il manquait les trois dates qui définissent la vie du
      // produit, le panier et sa calibration, et la corrélation : rouvrir un
      // script sauvegardé rendait un écran qu'il fallait resaisir sous-jacent
      // par sous-jacent, avec des dates repartant d'aujourd'hui — donc un
      // autre prix, sans que rien ne le signale.
      global_params_json: JSON.stringify({
        r: globalParams.r, T: globalParams.T, N: globalParams.N,
        seed: globalParams.seed, model: globalParams.model,
        antithetic: globalParams.antithetic, deal_ccy: globalParams.deal_ccy,
        rateModel: globalParams.rateModel, sigma_r: globalParams.sigma_r, a_r: globalParams.a_r,
        barrierMonitoring: globalParams.barrierMonitoring, stepsPerYear: globalParams.stepsPerYear,
        trade_date: globalParams.trade_date,
        strike_date: globalParams.strike_date,
        value_date: globalParams.value_date,
        maturity_date: _maturityDate(),
        payment_date: globalParams.payment_date,
        valuation_date: globalParams.valuation_date,
        underlyings: underlyings.value.map(u => ({ ...u })),
        corr_matrix: corrMatrix.value.map(row => [...row]),
        // Le spread émetteur fait partie des hypothèses de valorisation au
        // même titre que la vol : sans lui, rouvrir le script rendrait un
        // autre prix sans que rien ne le signale.
        funding: { enabled: fundingCurve.enabled, mode: fundingCurve.mode,
                    level: fundingCurve.level,
                    pillars: fundingCurve.pillars.map(x => ({ ...x })) },
        yield_curve_enabled: yieldCurve.enabled,
        yield_curve_pillars: yieldCurve.pillars.map(x => ({ ...x })),
      }),
      ai_provider: provenance?.provider || '',
      ai_model: provenance?.effective_model || '',
      ai_prompt: provenance?.attempts?.[0]?.prompt?.user || '',
      ai_generated_at: provenance?.generated_at || null,
      ai_provenance_json: JSON.stringify(provenance || {}),
    }
  }

  /**
   * Enregistre la déclinaison affichée — en écrivant ses ÉCARTS, pas une copie.
   *
   * Sans ça, travailler sur une variante puis revenir dessus perdait tout :
   * l'écran chargeait le contexte du serveur, qui ne portait aucune des
   * modifications restées locales.
   *
   * Les écarts sont déduits en comparant l'état courant au contexte de
   * l'origine — voir useVariantDelta pour ce qui compte comme un écart, et
   * surtout pour ce qui n'en est pas un.
   */
  /**
   * Les écarts que l'écran porte À CET INSTANT, contre l'origine.
   *
   * Dérivé plutôt que suivi à la main : un drapeau « modifié » qu'il faut
   * penser à lever se désynchronise au premier champ ajouté, et c'est
   * précisément le genre d'oubli qui fait perdre du travail sans un mot.
   * Ici l'état ne peut pas mentir — il EST la comparaison.
   */
  const deltaCourant = computed(() => {
    const v = variantInfo.value
    if (!v?.parent) return null
    return calculerDelta(v.parent, _contexteAPlat(), {
      params: scriptParams.value.map(x => x.name),
      constats: scriptConstats.value.map(x => x.name),
    })
  })

  function _contexteAPlat() {
    const ctx = contexteDepuisCorps(_scriptBody())
    const uls = ctx.global?.underlyings
    if (Array.isArray(uls)) {
      ctx.global.underlyings = uls.map(u => ({
        ...u,
        dividendCurve: _buildDividendCurve(u),
        dividendDecay: u.dividendCurveEnabled
          ? Math.max(0, Math.min(100, Number(u.dividendDecay) || 0)) : 0,
      }))
    }
    return ctx
  }

  /** Vrai quand l'écran diffère de ce qui est enregistré pour cette variante. */
  const variantDirty = computed(() => {
    const v = variantInfo.value
    if (!v?.parent) return false
    const enregistre = { set: v.delta?.set || {}, removed: v.delta?.removed || [] }
    const courant = deltaCourant.value || { set: {}, removed: [] }
    return JSON.stringify(_trie(courant)) !== JSON.stringify(_trie(enregistre))
  })

  async function saveVariant() {
    const v = variantInfo.value
    if (!v?.parent) throw new Error("Aucune déclinaison affichée.")
    const delta = deltaCourant.value
    if (!delta) throw new Error("Aucune déclinaison affichée.")

    const res = await apiFetch(`/api/db/scripts/variants/${v.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delta }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || "Enregistrement refusé")
    // On rafraîchit les écarts sans recharger l'écran : recharger écraserait
    // ce que l'utilisateur vient de saisir par ce que le serveur en a compris,
    // et un aller-retour invisible est le meilleur moyen de perdre une saisie.
    variantInfo.value = { ...v, ecarts: data.ecarts || [],
                          delta: data.delta || delta,
                          base: data.base_pricing || v.base }
    return data
  }

  async function saveScript({ name, description = '', folderId = null, isShared = false, tags = '' }) {
    if (contractTermsLocked.value) {
      throw new Error('Le PayScript est figé sur un deal booké.')
    }
    const res = await apiFetch('/api/db/scripts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description, folder_id: folderId, is_shared: isShared, tags, ..._scriptBody(), params_json: '{}', constats_json: '{}', global_params_json: '{}' }),
    })
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Erreur sauvegarde') }
    const saved = await res.json()
    currentScriptId.value   = saved.id
    currentScriptName.value = saved.name
    _markSessionBaseline()
    return saved
  }

  async function updateScript(patch = {}) {
    if (contractTermsLocked.value) {
      throw new Error('Le PayScript est figé sur un deal booké.')
    }
    if (!currentScriptId.value) throw new Error('Aucun script courant')
    const res = await apiFetch(`/api/db/scripts/${currentScriptId.value}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...patch, ..._scriptBody(), params_json: '{}', constats_json: '{}', global_params_json: '{}' }),
    })
    if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Erreur mise à jour') }
    const updated = await res.json()
    currentScriptName.value = updated.name ?? currentScriptName.value
    _markSessionBaseline()
    return updated
  }

  async function saveConfiguration(name, includeBasket = false) {
    if (!await validateScript()) throw new Error('Validez le script avant de conserver une configuration.')
    const body = _scriptBody()
    const global = JSON.parse(body.global_params_json)
    if (!includeBasket) { delete global.underlyings; delete global.corr_matrix }
    const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(script.value))
    global.configuration = {
      version: 1, script_version: Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join(''),
      model_key: Object.entries(examples).find(([, text]) => text === script.value)?.[0] || null,
      include_basket: includeBasket,
      model_version: Object.entries(examples).some(([, text]) => text === script.value) ? '2.0' : null,
      parameter_units: Object.fromEntries(scriptParams.value.map(p => [p.name, p.is_pct ? ' %' : ''])),
    }
    body.global_params_json = JSON.stringify(global)
    const response = await apiFetch('/api/db/scripts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, name, tags: 'configuration:payscript-v2', is_shared: false }),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || 'Enregistrement refusé.')
    return data
  }

  function addUnderlying() {
    if (contractTermsLocked.value) return
    const n = underlyings.value.length
    if (n >= CALCULATION_LIMITS.maxUnderlyings) return
    underlyings.value.push(_defaultUnderlying(n+1))
    const m = corrMatrix.value
    m.forEach(row => row.push(0))
    m.push(new Array(n+1).fill(0))
    m[n][n] = 1
    activeUnderlyingIdx.value = n
  }

  function removeUnderlying(i) {
    if (contractTermsLocked.value) return
    if (underlyings.value.length <= 1) return
    underlyings.value.splice(i, 1)
    corrMatrix.value.splice(i, 1)
    corrMatrix.value.forEach(row => row.splice(i, 1))
    activeUnderlyingIdx.value = Math.min(activeUnderlyingIdx.value, underlyings.value.length - 1)
  }

  Object.assign(s, { _scriptBody, deltaCourant, _contexteAPlat, variantDirty, saveVariant, saveScript, updateScript, saveConfiguration, addUnderlying, removeUnderlying })
}
