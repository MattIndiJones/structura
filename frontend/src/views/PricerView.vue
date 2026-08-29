<template>
  <!-- The Pricer is mounted fresh every navigation (no keep-alive).
       If a script ID is in the route, we load it before showing the pricer. -->
  <Pricer v-if="ready" />
  <div v-else class="flex-1 flex items-center justify-center text-slate-500 text-sm">
    Chargement…
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import Pricer from './Pricer.vue'
import { usePricingStore } from '../stores/pricing.js'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'

const route  = useRoute()
const store  = usePricingStore()
const auth   = useAuthStore()
const ready  = ref(false)

async function charger() {
  const { id, variantId } = route.params
  if (variantId) {
    await loadVariantFromDb(parseInt(variantId))
  } else if (id) {
    await loadScriptFromDb(parseInt(id))
  } else {
    store.resetToDefaults()
  }
  ready.value = true
}

onMounted(charger)

// Vue Router RÉUTILISE le composant quand deux routes le partagent : passer de
// /pricer/5 à /pricer/v/3 ne remonte rien, donc onMounted ne rejoue pas. Sans
// ce watch, cliquer « Origine » ou une autre déclinaison changeait l'URL et
// laissait l'écran sur le produit précédent — et créer une variante n'ouvrait
// jamais la variante créée.
watch(() => [route.params.id, route.params.variantId], async () => {
  ready.value = false
  await charger()
})

async function loadVariantFromDb(id) {
  // Le contexte arrive déjà résolu — parent + delta, et pour une note neuve,
  // dates déjà recalées. Le refaire ici ferait diverger l'écran du prix.
  try {
    const res = await apiFetch(`/api/db/scripts/variants/${id}/resolved`,
                               { headers: auth.authHeaders() })
    if (!res.ok) { store.resetToDefaults(); return }
    await store.loadVariant(await res.json())
  } catch {
    store.resetToDefaults()
  }
}

async function loadScriptFromDb(id) {
  try {
    const res = await apiFetch(`/api/db/scripts/${id}`, { headers: auth.authHeaders() })
    if (!res.ok) { store.resetToDefaults(); return }
    const data = await res.json()
    await store.loadFromDb(data)
  } catch {
    store.resetToDefaults()
  }
}
</script>
