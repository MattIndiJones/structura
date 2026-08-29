<template>
  <div class="min-h-screen flex flex-col">
    <AppHeader v-if="!route.meta.public" />
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

const route = useRoute()
const pricing = usePricingStore()

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
