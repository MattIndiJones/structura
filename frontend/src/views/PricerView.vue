<template>
  <!-- The Pricer is mounted fresh every navigation (no keep-alive).
       If a script ID is in the route, we load it before showing the pricer. -->
  <Pricer v-if="ready" />
  <div v-else class="flex-1 flex items-center justify-center text-slate-500 text-sm">
    Chargement…
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import Pricer from './Pricer.vue'
import { usePricingStore } from '../stores/pricing.js'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'

const route  = useRoute()
const store  = usePricingStore()
const auth   = useAuthStore()
const ready  = ref(false)

onMounted(async () => {
  const id = route.params.id
  if (id) {
    await loadScriptFromDb(parseInt(id))
  } else {
    store.resetToDefaults()
  }
  ready.value = true
})

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
