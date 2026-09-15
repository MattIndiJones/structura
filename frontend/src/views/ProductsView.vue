<template>
  <div class="flex-1 flex flex-col min-h-0">
    <div class="page-header px-6 pt-6 pb-4 mb-0">
      <div class="flex items-center gap-3">
        <BackLink :fallback="{ path: '/', query: { category: 'pricing' } }" />
        <div>
          <h1 class="page-title">Mes Produits</h1>
          <p class="text-xs mt-1" style="color: var(--muted);">
            Dossiers volontairement conservés, avec leurs termes versionnés.
          </p>
        </div>
      </div>
      <div class="page-actions flex gap-2">
        <button class="btn-secondary text-xs" @click="toggleArchive">
          {{ archived ? 'Produits actifs' : 'Archives' }}
        </button>
        <RouterLink to="/pricer" class="btn-primary text-xs">+ Nouveau pricing</RouterLink>
      </div>
    </div>

    <AlertMessage v-if="products.error" kind="error" dismissible class="mx-6 mb-3"
                  @dismiss="products.error = ''">{{ products.error }}</AlertMessage>
    <LoadingSpinner v-if="products.loading" class="py-16" />
    <EmptyState v-else-if="!products.items.length" icon="◫"
                :title="archived ? 'Aucun produit archivé' : 'Aucun produit conservé'">
      <RouterLink v-if="!archived" to="/pricer" class="btn-primary text-xs">
        Ouvrir un nouveau pricing
      </RouterLink>
    </EmptyState>

    <div v-else class="mx-6 mb-6 overflow-auto rounded-lg border" style="border-color: var(--border);">
      <table class="w-full text-xs">
        <thead>
          <tr style="background: var(--surface2); color: var(--muted);">
            <th class="text-left px-3 py-2.5">Référence</th>
            <th class="text-left px-3 py-2.5">Produit</th>
            <th class="text-left px-3 py-2.5">Sous-jacent(s)</th>
            <th class="text-left px-3 py-2.5">Étape</th>
            <th class="text-right px-3 py-2.5">Dernier prix</th>
            <th class="text-left px-3 py-2.5">Maturité</th>
            <th class="text-right px-3 py-2.5">Actions</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="product in products.items" :key="product.id">
            <tr class="product-row border-t cursor-pointer"
                :class="{ 'product-row--open': expandedProductId === product.id }"
                style="border-color: var(--border);"
                @click="toggleCalculations(product)">
              <td class="px-3 py-3 font-mono font-semibold" style="color: var(--accent);">
                <div class="flex items-start gap-2">
                  <button class="chevron mt-0.5" :class="{ 'chevron--open': expandedProductId === product.id }"
                          :aria-expanded="expandedProductId === product.id"
                          :aria-label="expandedProductId === product.id ? 'Masquer les calculs' : 'Afficher les calculs'"
                          @click.stop="toggleCalculations(product)">›</button>
                  <div>
                    {{ product.reference }}
                    <div class="text-[9px] font-sans font-normal mt-0.5" style="color: var(--subtle);">
                      termes v{{ product.terms_version }} · rév. {{ product.revision }}
                    </div>
                  </div>
                </div>
              </td>
              <td class="px-3 py-3 font-semibold">{{ product.name }}</td>
              <td class="px-3 py-3" style="color: var(--muted);">
                {{ product.underlyings.map(u => u.name).join(', ') }}
              </td>
              <td class="px-3 py-3">
                <span class="badge" :class="stageClass(product.stage)">{{ stageLabel(product.stage) }}</span>
              </td>
              <td class="px-3 py-3 text-right font-mono">
                <SensitiveValue>{{ formatPrice(product.latest_price) }}</SensitiveValue>
              </td>
              <td class="px-3 py-3" style="color: var(--muted);">{{ product.maturity_date || 'À préciser' }}</td>
              <td class="px-3 py-3">
                <div class="flex justify-end gap-2">
                  <button class="btn-secondary text-[11px]"
                          :disabled="selectedCount(product.id) < 2"
                          @click.stop="showComparison(product)">
                    Comparer<span v-if="selectedCount(product.id)"> ({{ selectedCount(product.id) }})</span>
                  </button>
                  <RouterLink v-if="!archived" :to="`/products/${product.id}/pricer`"
                              class="btn-secondary text-[11px]" @click.stop>Reprendre</RouterLink>
                  <button class="btn-ghost text-[11px]" @click.stop="setArchive(product)">
                    {{ archived ? 'Restaurer' : 'Archiver' }}
                  </button>
                </div>
              </td>
            </tr>

            <tr v-if="expandedProductId === product.id" class="border-t"
                style="border-color: var(--border);">
              <td colspan="7" class="p-0">
                <section class="calculation-panel px-5 py-4" :aria-label="`Calculs de ${product.reference}`">
                  <LoadingSpinner v-if="loadingDetails[product.id]" class="py-5" />
                  <AlertMessage v-else-if="detailErrors[product.id]" kind="error">
                    {{ detailErrors[product.id] }}
                  </AlertMessage>
                  <template v-else>
                    <div class="flex items-center justify-between gap-3 mb-3">
                      <div>
                        <h2 class="text-xs font-bold uppercase tracking-wider" style="color: var(--text);">
                          Calculs conservés
                        </h2>
                        <p class="text-[10px] mt-0.5" style="color: var(--muted);">
                          Chaque ligne restitue une valorisation enregistrée sans relancer le moteur.
                        </p>
                      </div>
                      <span class="badge badge-muted">{{ calculationRows(product.id).length }}</span>
                    </div>

                    <div v-if="!calculationRows(product.id).length"
                         class="rounded-lg border px-3 py-4 text-xs text-center"
                         style="border-color: var(--border); color: var(--muted); background: var(--surface);">
                      Aucun calcul conservé pour ce produit.
                    </div>
                    <div v-else class="overflow-x-auto rounded-lg border" style="border-color: var(--border);">
                      <table class="w-full text-[11px]">
                        <thead>
                          <tr style="background: var(--surface); color: var(--muted);">
                            <th class="w-9 px-3 py-2">
                              <span class="sr-only">Sélection</span>
                            </th>
                            <th class="text-left px-3 py-2">Calculé le</th>
                            <th class="text-left px-3 py-2">Valorisation au</th>
                            <th class="text-right px-3 py-2">Prix</th>
                            <th class="text-left px-3 py-2">Termes</th>
                            <th class="text-left px-3 py-2">Source</th>
                            <th class="text-right px-3 py-2">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="calculation in calculationRows(product.id)" :key="calculation.id"
                              class="border-t" style="border-color: var(--border); background: var(--surface2);">
                            <td class="px-3 py-2.5 text-center">
                              <input type="checkbox" class="calculation-checkbox"
                                     :checked="isCalculationSelected(product.id, calculation.id)"
                                     :aria-label="`Sélectionner le calcul du ${formatDateTime(calculation.calculated_at)}`"
                                     @click.stop
                                     @change="toggleCalculationSelection(product.id, calculation.id)">
                            </td>
                            <td class="px-3 py-2.5 font-mono">{{ formatDateTime(calculation.calculated_at) }}</td>
                            <td class="px-3 py-2.5 font-mono">{{ formatDate(calculation.valuation_date) }}</td>
                            <td class="px-3 py-2.5 text-right font-mono font-semibold">
                              <SensitiveValue>{{ formatPrice(calculation.price) }}</SensitiveValue>
                            </td>
                            <td class="px-3 py-2.5">
                              v{{ calculation.terms_version }}
                              <span v-if="calculation.terms_version !== product.terms_version"
                                    class="ml-1 text-[9px]" style="color: var(--muted);">
                                ancienne version
                              </span>
                            </td>
                            <td class="px-3 py-2.5">{{ sourceLabel(calculation.source) }}</td>
                            <td class="px-3 py-2.5">
                              <div class="flex justify-end gap-2">
                                <button class="btn-ghost text-[10px]" @click.stop="showCalculation(product, calculation)">
                                  Voir le résultat
                                </button>
                                <RouterLink v-if="!archived && calculation.terms_version === product.terms_version"
                                  :to="{ path: `/products/${product.id}/pricer`, query: { calculation: calculation.id } }"
                                  class="btn-secondary text-[10px]" @click.stop>
                                  Recharger
                                </RouterLink>
                              </div>
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </template>
                </section>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <BaseModal v-model="calculationDialog.open" title="Résultat conservé" max-width="720px">
      <LoadingSpinner v-if="calculationDialog.loading" class="py-8" />
      <AlertMessage v-else-if="calculationDialog.error" kind="error">
        {{ calculationDialog.error }}
      </AlertMessage>
      <div v-else-if="calculationDialog.detail" class="space-y-4">
        <div class="rounded-lg border px-3 py-2.5 text-xs"
             style="border-color: var(--border); background: var(--surface2);">
          <div class="font-semibold">{{ calculationDialog.productReference }}</div>
          <div class="mt-1 flex flex-wrap gap-x-4 gap-y-1" style="color: var(--muted);">
            <span>Calculé le {{ formatDateTime(calculationDialog.detail.calculated_at) }}</span>
            <span>Valorisation au {{ formatDate(calculationDialog.detail.valuation_date) }}</span>
            <span>Termes v{{ calculationDialog.detail.terms_version }}</span>
            <span>{{ sourceLabel(calculationDialog.detail.source) }}</span>
          </div>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="result-stat">
            <span>Prix équitable</span>
            <strong><SensitiveValue>{{ formatPrice(calculationDialog.summary?.price) }}</SensitiveValue></strong>
          </div>
          <div class="result-stat">
            <span>Médiane</span>
            <strong><SensitiveValue>{{ formatPrice(calculationDialog.detail.result?.median) }}</SensitiveValue></strong>
          </div>
          <div class="result-stat">
            <span>VaR 5 %</span>
            <strong><SensitiveValue>{{ formatPrice(calculationDialog.detail.result?.var5) }}</SensitiveValue></strong>
          </div>
          <div class="result-stat">
            <span>Scénarios gagnants</span>
            <strong><SensitiveValue>{{ formatPrice(calculationDialog.detail.result?.prob_gt100) }}</SensitiveValue></strong>
          </div>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <div class="rounded-lg border px-3 py-2.5" style="border-color: var(--border);">
            <div class="text-[10px] uppercase tracking-wider" style="color: var(--muted);">Modèle</div>
            <div class="mt-1 font-semibold">{{ modelLabel(calculationDialog.detail.input?.model) }}</div>
          </div>
          <div class="rounded-lg border px-3 py-2.5" style="border-color: var(--border);">
            <div class="text-[10px] uppercase tracking-wider" style="color: var(--muted);">Simulation</div>
            <div class="mt-1 font-semibold">
              {{ formatInt(calculationDialog.detail.result?.n_paths || calculationDialog.detail.input?.N) }} chemins
              <span v-if="calculationDialog.detail.result?.elapsed_ms != null" style="color: var(--muted);">
                · {{ formatInt(calculationDialog.detail.result.elapsed_ms) }} ms
              </span>
            </div>
          </div>
        </div>

        <section class="market-snapshot rounded-lg border overflow-hidden"
                 style="border-color: var(--border);">
          <div class="market-snapshot__header px-3 py-2.5">
            <div>
              <div class="text-[10px] font-bold uppercase tracking-wider">Marché conservé</div>
              <div class="text-[10px] mt-0.5" style="color: var(--muted);">
                Valeurs exactes utilisées par le moteur à la date de valorisation.
              </div>
            </div>
            <span v-if="calculationDialog.previousDetail" class="badge badge-muted">
              {{ marketMovementCount() }} mouvement{{ marketMovementCount() > 1 ? 's' : '' }}
            </span>
          </div>
          <div v-if="calculationDialog.previousDetail"
               class="px-3 py-2 text-[10px] border-t"
               style="border-color: var(--border); color: var(--muted);">
            Comparaison avec le calcul précédent des mêmes termes, conservé le
            {{ formatDateTime(calculationDialog.previousDetail.calculated_at) }}.
          </div>
          <div v-else class="px-3 py-2 text-[10px] border-t"
               style="border-color: var(--border); color: var(--muted);">
            Premier calcul conservé pour cette version des termes : aucune base de comparaison antérieure.
          </div>
          <div v-if="marketRows().length" class="overflow-x-auto border-t" style="border-color: var(--border);">
            <table class="w-full text-[11px]">
              <thead>
                <tr style="background: var(--surface2); color: var(--muted);">
                  <th class="text-left px-3 py-2">Bloc</th>
                  <th class="text-left px-3 py-2">Paramètre</th>
                  <th class="text-right px-3 py-2">Marché conservé</th>
                  <th v-if="calculationDialog.previousDetail" class="text-right px-3 py-2">Précédent</th>
                  <th v-if="calculationDialog.previousDetail" class="text-right px-3 py-2">Mouvement</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in marketRows()" :key="row.key" class="border-t"
                    :class="{ 'market-row--changed': row.changed }"
                    style="border-color: var(--border);">
                  <td class="px-3 py-2" style="color: var(--muted);">{{ row.group }}</td>
                  <td class="px-3 py-2 font-medium">{{ row.label }}</td>
                  <td class="px-3 py-2 text-right font-mono">{{ formatMarketValue(row, row.value) }}</td>
                  <td v-if="calculationDialog.previousDetail"
                      class="px-3 py-2 text-right font-mono" style="color: var(--muted);">
                    {{ formatMarketValue(row, row.previousValue) }}
                  </td>
                  <td v-if="calculationDialog.previousDetail"
                      class="px-3 py-2 text-right font-mono"
                      :class="{ 'market-delta': row.changed }">
                    {{ formatMarketDelta(row) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <div v-if="calculationDialog.detail.result?.ic95?.length === 2"
             class="rounded-lg border px-3 py-2.5 text-xs"
             style="border-color: var(--border); color: var(--muted);">
          Intervalle de confiance à 95 % :
          <strong style="color: var(--text);">
            [{{ formatPrice(calculationDialog.detail.result.ic95[0]) }} ;
            {{ formatPrice(calculationDialog.detail.result.ic95[1]) }}]
          </strong>
        </div>
      </div>
      <template #footer>
        <button class="btn-secondary text-xs" @click="calculationDialog.open = false">Fermer</button>
        <RouterLink v-if="calculationDialog.detail && !archived
                     && calculationDialog.detail.terms_version === calculationDialog.productTermsVersion"
          :to="{ path: `/products/${calculationDialog.productId}/pricer`, query: { calculation: calculationDialog.detail.id } }"
          class="btn-primary text-xs">
          Recharger dans le Pricer
        </RouterLink>
      </template>
    </BaseModal>

    <BaseModal v-model="comparisonDialog.open" title="Comparateur de prix" max-width="1280px">
      <LoadingSpinner v-if="comparisonDialog.loading" class="py-8" />
      <AlertMessage v-else-if="comparisonDialog.error" kind="error">
        {{ comparisonDialog.error }}
      </AlertMessage>
      <PriceComparisonPanel v-else-if="comparisonDialog.items.length"
        :items="productComparisonItems" :groups="productComparisonGroups"
        :collapsible="false"
        version-warning="Les calculs portent sur plusieurs versions de termes : l’écart de prix ne représente pas un mouvement de marché pur."
        :title="`Évolution du prix de ${comparisonDialog.productReference}`"
        price-label="prix conservés" />
    </BaseModal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import BackLink from '../components/ui/BackLink.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import BaseModal from '../components/ui/BaseModal.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import SensitiveValue from '../components/SensitiveValue.vue'
import PriceComparisonPanel from '../components/PriceComparisonPanel.vue'
import { useProductsStore } from '../stores/products.js'
import { formatBps, formatDate, formatDateTime, formatInt, formatNumber, formatPercent } from '../utils/format.js'
import { compareMarketSnapshots, compareMarketSnapshotSeries } from '../utils/productCalculations.js'

const products = useProductsStore()
const archived = ref(false)
const expandedProductId = ref(null)
const detailsByProduct = reactive({})
const loadingDetails = reactive({})
const detailErrors = reactive({})
const selectedCalculations = reactive({})
const calculationDetailCache = reactive({})
const calculationDialog = reactive({
  open: false,
  loading: false,
  error: '',
  productId: null,
  productReference: '',
  productTermsVersion: null,
  summary: null,
  detail: null,
  previousDetail: null,
})
const comparisonDialog = reactive({
  open: false,
  loading: false,
  error: '',
  productId: null,
  productReference: '',
  items: [],
})
const productComparisonItems = computed(() => comparisonDialog.items.map(item => ({
  id: item.detail.id,
  calculatedAt: item.detail.calculated_at,
  valuationDate: item.detail.valuation_date,
  price: item.summary?.price ?? null,
  basis: `Termes v${item.detail.terms_version}`,
  version: item.detail.terms_version,
})))

const productComparisonGroups = computed(() => {
  if (!comparisonDialog.items.length) return []
  const priceRow = {
    key: 'result:price', label: 'Prix équitable', unit: 'percent', decimals: 2,
    values: comparisonDialog.items.map(item => item.summary?.price ?? null),
  }
  const marketRows = compareMarketSnapshotSeries(
    comparisonDialog.items.map(item => item.detail.market_snapshot))
  const groups = new Map([['Résultat', [priceRow]]])
  for (const row of marketRows) {
    if (!groups.has(row.group)) groups.set(row.group, [])
    groups.get(row.group).push({
      key: row.key,
      label: row.label,
      unit: row.unit,
      decimals: row.unit === 'bps' ? 1 : 2,
      values: row.values,
    })
  }
  return [...groups].map(([label, rows]) => ({ label, rows }))
})

onMounted(() => products.fetchAll())

async function toggleArchive() {
  archived.value = !archived.value
  expandedProductId.value = null
  await products.fetchAll({ archived: archived.value })
}

async function toggleCalculations(product) {
  if (expandedProductId.value === product.id) {
    expandedProductId.value = null
    return
  }
  expandedProductId.value = product.id
  if (detailsByProduct[product.id] || loadingDetails[product.id]) return
  loadingDetails[product.id] = true
  detailErrors[product.id] = ''
  try {
    detailsByProduct[product.id] = await products.fetchDetails(product.id)
  } catch (error) {
    detailErrors[product.id] = error.message
  } finally {
    loadingDetails[product.id] = false
  }
}

function calculationRows(productId) {
  return [...(detailsByProduct[productId]?.calculations || [])].reverse()
}

function selectedCount(productId) {
  return selectedCalculations[productId]?.length || 0
}

function isCalculationSelected(productId, calculationId) {
  return selectedCalculations[productId]?.includes(calculationId) || false
}

function toggleCalculationSelection(productId, calculationId) {
  const selected = selectedCalculations[productId] || []
  selectedCalculations[productId] = selected.includes(calculationId)
    ? selected.filter(id => id !== calculationId)
    : [...selected, calculationId]
}

async function loadCalculationDetail(productId, calculationId) {
  const key = `${productId}:${calculationId}`
  if (!calculationDetailCache[key]) {
    calculationDetailCache[key] = await products.fetchCalculation(productId, calculationId)
  }
  return calculationDetailCache[key]
}

async function showCalculation(product, calculation) {
  const previous = previousCalculation(product.id, calculation)
  Object.assign(calculationDialog, {
    open: true,
    loading: true,
    error: '',
    productId: product.id,
    productReference: product.reference,
    productTermsVersion: product.terms_version,
    summary: calculation,
    detail: null,
    previousDetail: null,
  })
  try {
    const [detail, previousDetail] = await Promise.all([
      loadCalculationDetail(product.id, calculation.id),
      previous ? loadCalculationDetail(product.id, previous.id) : Promise.resolve(null),
    ])
    calculationDialog.detail = detail
    calculationDialog.previousDetail = previousDetail
  } catch (error) {
    calculationDialog.error = error.message
  } finally {
    calculationDialog.loading = false
  }
}

async function showComparison(product) {
  const selected = new Set(selectedCalculations[product.id] || [])
  const summaries = (detailsByProduct[product.id]?.calculations || [])
    .filter(calculation => selected.has(calculation.id))
  if (summaries.length < 2) return
  Object.assign(comparisonDialog, {
    open: true,
    loading: true,
    error: '',
    productId: product.id,
    productReference: product.reference,
    items: [],
  })
  try {
    const details = await Promise.all(summaries.map(calculation =>
      loadCalculationDetail(product.id, calculation.id)))
    const summaryById = new Map(summaries.map(summary => [summary.id, summary]))
    comparisonDialog.items = details
      .map(detail => ({ detail, summary: summaryById.get(detail.id) }))
      .sort((left, right) => {
        const dateOrder = String(left.detail.calculated_at).localeCompare(String(right.detail.calculated_at))
        return dateOrder || Number(left.detail.id) - Number(right.detail.id)
      })
  } catch (error) {
    comparisonDialog.error = error.message
  } finally {
    comparisonDialog.loading = false
  }
}

function previousCalculation(productId, calculation) {
  const sameTerms = (detailsByProduct[productId]?.calculations || [])
    .filter(item => item.terms_version === calculation.terms_version)
    .sort((left, right) => {
      const dateOrder = String(left.calculated_at).localeCompare(String(right.calculated_at))
      return dateOrder || Number(left.id) - Number(right.id)
    })
  const selectedIndex = sameTerms.findIndex(item => item.id === calculation.id)
  return selectedIndex > 0 ? sameTerms[selectedIndex - 1] : null
}

function marketRows() {
  const current = calculationDialog.detail?.market_snapshot
  if (!current) return []
  return compareMarketSnapshots(
    current, calculationDialog.previousDetail?.market_snapshot || null)
}

function marketMovementCount() {
  return marketRows().filter(row => row.changed).length
}

function formatMarketValue(row, value) {
  if (value == null) return '—'
  if (row.unit === 'bps') return formatBps(value, 1)
  if (row.unit === 'correlation') return formatNumber(value, 2)
  if (row.unit === 'number') return formatNumber(value, 2)
  return formatPercent(value, 2)
}

function formatMarketDelta(row) {
  if (row.delta == null) return row.changed ? 'changement de structure' : '—'
  if (!row.changed) return '—'
  const sign = row.delta > 0 ? '+' : ''
  if (row.unit === 'bps') return `${sign}${formatNumber(row.delta, 1)} bps`
  if (row.unit === 'correlation') return `${sign}${formatNumber(row.delta, 2)}`
  if (row.unit === 'number') return `${sign}${formatNumber(row.delta, 2)}`
  return `${sign}${formatNumber(row.delta, 2)} pt`
}

async function setArchive(product) {
  try {
    await products.setArchived(product, !archived.value)
    if (expandedProductId.value === product.id) expandedProductId.value = null
    await products.fetchAll({ archived: archived.value })
  } catch (e) {
    products.error = e.message
  }
}

function stageLabel(stage) {
  return ({ SAVED: 'Conservé', RFQ: 'RFQ', BOOKED: 'Booké' })[stage] || stage
}

function stageClass(stage) {
  return stage === 'BOOKED' ? 'badge-positive' : stage === 'RFQ' ? 'badge-warning' : 'badge-muted'
}

function formatPrice(value) {
  return value == null ? '—' : formatPercent(value, 2)
}

function sourceLabel(source) {
  return ({ PRICER: 'Pricer', SERVER: 'Serveur' })[source] || source || 'Source inconnue'
}

function modelLabel(model) {
  return ({
    constant: 'Black-Scholes / GBM',
    heston: 'Heston',
    sabr: 'SABR',
    local_vol: 'Volatilité locale',
    lsv: 'LSV',
  })[model] || model || 'Non renseigné'
}
</script>

<style scoped>
.product-row { transition: background-color .15s ease; }
.product-row:hover,
.product-row--open { background: color-mix(in srgb, var(--accent) 5%, var(--surface)); }
.chevron {
  display: inline-block;
  color: var(--muted);
  font-family: sans-serif;
  font-size: 1.25rem;
  line-height: 1;
  transition: transform .15s ease;
}
.chevron--open { transform: rotate(90deg); color: var(--accent); }
.calculation-panel { background: color-mix(in srgb, var(--surface2) 70%, var(--surface)); }
.market-snapshot__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .75rem;
  background: color-mix(in srgb, var(--accent) 4%, var(--surface));
}
.market-row--changed { background: color-mix(in srgb, var(--accent) 6%, var(--surface)); }
.market-delta { color: var(--accent); font-weight: 700; }
.calculation-checkbox { width: 14px; height: 14px; accent-color: var(--accent); }
.result-stat {
  display: flex;
  min-height: 76px;
  flex-direction: column;
  justify-content: space-between;
  gap: .5rem;
  border: 1px solid var(--border);
  border-radius: .5rem;
  padding: .7rem;
  background: var(--surface2);
}
.result-stat span { color: var(--muted); font-size: .65rem; text-transform: uppercase; letter-spacing: .04em; }
.result-stat strong { color: var(--text); font-size: 1rem; font-family: ui-monospace, monospace; }
@media (prefers-reduced-motion: reduce) {
  .product-row, .chevron { transition: none; }
}
</style>
