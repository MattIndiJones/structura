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
          <tr v-for="product in products.items" :key="product.id"
              class="border-t" style="border-color: var(--border);">
            <td class="px-3 py-3 font-mono font-semibold" style="color: var(--accent);">
              {{ product.reference }}
              <div class="text-[9px] font-sans font-normal mt-0.5" style="color: var(--subtle);">
                termes v{{ product.terms_version }} · rév. {{ product.revision }}
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
              <SensitiveValue>{{ product.latest_price == null ? '—' : `${product.latest_price.toFixed(2)}%` }}</SensitiveValue>
            </td>
            <td class="px-3 py-3" style="color: var(--muted);">{{ product.maturity_date || 'À préciser' }}</td>
            <td class="px-3 py-3">
              <div class="flex justify-end gap-2">
                <RouterLink v-if="!archived" :to="`/products/${product.id}/pricer`"
                            class="btn-secondary text-[11px]">Reprendre</RouterLink>
                <button class="btn-ghost text-[11px]" @click="setArchive(product)">
                  {{ archived ? 'Restaurer' : 'Archiver' }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import BackLink from '../components/ui/BackLink.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import SensitiveValue from '../components/SensitiveValue.vue'
import { useProductsStore } from '../stores/products.js'

const products = useProductsStore()
const archived = ref(false)

onMounted(() => products.fetchAll())

async function toggleArchive() {
  archived.value = !archived.value
  await products.fetchAll({ archived: archived.value })
}

async function setArchive(product) {
  try {
    await products.setArchived(product, !archived.value)
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
</script>
