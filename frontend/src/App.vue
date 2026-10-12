<template>
  <div class="flex flex-col" :class="route.meta.fixedViewport ? 'h-dvh overflow-hidden' : 'min-h-screen'">
    <AppHeader v-if="!route.meta.public" class="shrink-0" />
    <div v-if="auth.readOnly && !route.meta.public" role="status" class="consultation-banner">
      Consultation — {{ auth.user.consultation?.entity }} · Données au {{ auth.user.consultation?.date }}
      <span>IA arrêtées · Écriture et recalcul désactivés</span>
    </div>
    <RouterView />
    <!-- Montée UNE fois, ici : le service de confirmation rend une promesse
         qu'il faut pouvoir résoudre depuis n'importe où, y compris depuis un
         garde de route, qui n'a aucun composant sous la main. -->
    <ConfirmDialog />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import AppHeader from './components/AppHeader.vue'
import ConfirmDialog from './components/ui/ConfirmDialog.vue'
import { usePricingStore } from './stores/pricing.js'
import { useAuthStore } from './stores/auth.js'

const route = useRoute()
const pricing = usePricingStore()
const auth = useAuthStore()

// Le dernier filet, celui que le routeur ne voit pas : fermeture d'onglet et
// rechargement de la page. Le navigateur impose ici SA formulation — on ne peut
// que déclencher son invite, pas la rédiger. C'est la seule confirmation de
// l'application qui reste native, et c'est parce qu'aucune autre n'est possible.
function avantFermeture(e) {
  if (!pricing.variantDirty) return
  e.preventDefault()
  e.returnValue = ''
}

onMounted(() => window.addEventListener('beforeunload', avantFermeture))
onUnmounted(() => window.removeEventListener('beforeunload', avantFermeture))
</script>

<style scoped>
.consultation-banner{background:#eaf1f7;color:#15375a;border-bottom:1px solid #c8d5e3;padding:10px 24px;font-size:13px;display:flex;gap:12px;justify-content:space-between;flex-wrap:wrap}
</style>
