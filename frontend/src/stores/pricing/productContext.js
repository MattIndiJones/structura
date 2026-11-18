// Identité du script, variante, produit, RFQ et deal liés à la session.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.
import { apiFetch } from '../../utils/api.js'
import { computed, ref, watch } from 'vue'

export function installProductContext(s) {
  const {
    globalParams, leftTab, script, underlyings,
  } = s

  // ── Current script DB identity ────────────────────────────────────
  const currentScriptId   = ref(null)
  // ── Variante ──────────────────────────────────────────────────────
  // Renseigné quand l'écran affiche une DÉCLINAISON d'un deal plutôt que le
  // deal lui-même. `ecarts` vient du serveur : c'est le delta stocké, enrichi
  // de la valeur d'origine. Le recalculer ici ferait diverger ce qu'on colore
  // de ce qui a servi à pricer.
  const variantInfo = ref(null)   // {id, parent_id, title, mode, ecarts[], delta, parent}

  /**
   * Oublie la déclinaison affichée.
   *
   * `variantInfo` décrit LE PRODUIT ACTUELLEMENT DANS LE STORE. Tout ce qui
   * remplace ce produit doit donc le relâcher — sans quoi l'état « modifié »
   * continue de comparer l'écran au parent d'une variante qu'on ne regarde
   * plus, et l'avertissement de sortie se redéclenche page après page.
   *
   * Appelé aussi quand l'utilisateur confirme qu'il quitte sans enregistrer :
   * il vient de dire que ces modifications sont abandonnées, les lui
   * représenter à la navigation suivante serait lui redemander ce qu'il a déjà
   * tranché. Revenir sur la déclinaison la rechargera depuis le serveur, donc
   * sans les modifications abandonnées — ce qui est exactement ce qu'il a
   * demandé.
   */
  function relacherVariante() {
    variantInfo.value = null
  }
  const currentScriptName = ref('')

  // ── Pre-trade opportunity (Indicative) this pricing session is tied to —
  // created lazily on first KID/EMT save, reused for every save after that
  // until reset. See db/models.py:Indicative for the full rationale. ──────
  const currentIndicativeId = ref(null)
  // Dossier Product conservé actuellement ouvert. Null signifie que la
  // session reste un brouillon de pricing entièrement éphémère.
  const currentProduct = ref(null)
  const variantComparisonInputs = ref(null)
  const editingProductTerms = ref(false)
  const productLoadNotice = ref('')
  // Last explicitly opened pricing entry. Navigation does not replace it.
  const sessionRouteKey = ref(null)

  // RFQ this pricing session was pre-filled from (see loadFromRfq below) —
  // sent as Deal.rfq_id at booking time so the winning quote's RFQ can be
  // traced back from the deal, and so book_deal can close out that RFQ.
  const currentRfqId = ref(null)
  const currentRfqExecution = ref(null)
  // One-shot handoff to DealTab.vue's commercial form. Les economics sont
  // déjà autoritatifs dans globalParams/underlyings/overrides ; dates et
  // nominal restent aussi dans ce handoff pour fermer les courses de
  // chargement asynchrones. Consumed and cleared by DealTab.
  const pendingDealPrefill = ref(null)
  // Booked deal this session was reopened from (loadFromDeal). Its economics
  // are in the store, while its commercial terms live in DealTab's form and
  // pass through pendingDealPrefill like the RFQ path does. Also what tells
  // DealTab this deal already exists: booking again
  // from here would silently create a duplicate under a new reference.
  const openedDeal = ref(null)
  const bookedContractTerms = ref(null)
  // A deal loaded through loadFromDeal is a persisted contract. The Pricer may
  // change its valuation assumptions, but it must not turn that contract into
  // another payoff while continuing to display the booked reference.
  const contractTermsLocked = computed(() => !!openedDeal.value || !!currentProduct.value?.execution
    || (!!currentProduct.value && !editingProductTerms.value))
  watch(() => JSON.stringify([globalParams.deal_ccy, underlyings.value.map(u => [u.ticker, u.exchange])]),
    (...args) => s._applyCalendarDefaults(...args), { flush: 'sync' })

  function beginProductTermsEdit() {
    if (!currentProduct.value || currentProduct.value.execution || openedDeal.value || currentRfqId.value) {
      throw new Error('Ce dossier ne permet pas la modification directe des termes.')
    }
    editingProductTerms.value = true
    s._invalidatePricingOutputs()
    leftTab.value = 'economics'
  }

  function _activeBookedContract() {
    return contractTermsLocked.value ? bookedContractTerms.value : null
  }

  function _contractUnderlyings(frozen) {
    const current = s._buildUls()
    if (!frozen) return current
    if (current.length !== frozen.underlyings.length) {
      throw new Error(
        `Deal booké : panier contractuel de ${frozen.underlyings.length} sous-jacent(s), `
        + `${current.length} présent(s) dans le pricer. Rechargez le deal.`)
    }
    return current.map((u, index) => ({ ...u, ...frozen.underlyings[index] }))
  }

  // Product title from the script's leading "# comment" line — shared by
  // KidPanel/EmtPanel save actions and the EMT print view.
  const productTitle = computed(() => {
    const m = script.value.match(/^\s*#\s*(.+)$/m)
    return m ? m[1].trim() : 'Produit structuré'
  })

  async function ensureIndicative() {
    if (currentIndicativeId.value) return currentIndicativeId.value
    const pricingInput = await s._authoritativeProductRequest(s._pricingBody())
    const res = await apiFetch('/api/indicatives', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        product_id: currentProduct.value?.product_id || null,
        product_terms_version: currentProduct.value?.terms_version || null,
        product_name: productTitle.value,
        pricing_input: pricingInput,
        contrepartie: '',
        counterparty_id: null,
        devise: globalParams.deal_ccy || 'EUR',
        nominal: 0,
        underlyings: underlyings.value.map(u => ({
          name: u.name, ticker: u.ticker, ccy: u.ccy,
        })),
        script_snapshot: script.value,
        script_id: currentScriptId.value || null,
        market_snapshot: { r: globalParams.r, T: globalParams.T, model: globalParams.model },
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail?.message || err.detail || 'Erreur création fiche indicative')
    }
    const ind = await res.json()
    currentIndicativeId.value = ind.id
    if (!currentProduct.value && ind.product_id) {
      const productResponse = await apiFetch(`/api/products/${ind.product_id}`)
      if (!productResponse.ok) {
        throw new Error('Le Product créé pour la fiche indicative ne peut pas être relu.')
      }
      currentProduct.value = await productResponse.json()
    }
    return ind.id
  }

  Object.assign(s, { currentScriptId, variantInfo, relacherVariante, currentScriptName, currentIndicativeId, currentProduct, variantComparisonInputs, editingProductTerms, productLoadNotice, sessionRouteKey, currentRfqId, currentRfqExecution, pendingDealPrefill, openedDeal, bookedContractTerms, contractTermsLocked, beginProductTermsEdit, _activeBookedContract, _contractUnderlyings, productTitle, ensureIndicative })
}
