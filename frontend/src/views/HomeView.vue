<template>
  <div class="min-h-screen bg-slate-950 flex flex-col">

    <!-- Header -->
    <header class="border-b border-slate-800 px-6 py-3 flex items-center gap-4">
      <div class="flex items-center gap-2.5 mr-auto">
        <img src="/tp_logo.png" alt="TP Advisory" class="h-7 w-7 rounded-sm bg-white object-contain p-0.5">
        <span class="font-bold text-slate-100 tracking-tight">Structura</span>
      </div>
      <span class="text-xs text-slate-500">{{ auth.user?.username }}</span>
      <RouterLink v-if="auth.isAdmin" to="/admin" title="Administration"
        class="text-slate-400 hover:text-amber-300 transition-colors text-lg leading-none">⚙️</RouterLink>
      <button class="btn-secondary text-xs" @click="logout">Déconnexion</button>
    </header>

    <!-- Landing -->
    <main class="flex-1 flex flex-col items-center justify-center gap-10 px-6 py-16">

      <Transition name="category-switch" mode="out-in" @after-enter="onAfterEnter">
        <div :key="selectedCategory || 'level1'" tabindex="0"
          class="outline-none flex flex-col items-center gap-10 w-full" @keyup.esc="backToCategories">

          <!-- Titre : accueil ou catégorie sélectionnée -->
          <div v-if="!selectedCategory" class="text-center">
            <h1 class="text-2xl font-black tracking-tight bg-gradient-to-r from-slate-100 to-slate-400 bg-clip-text text-transparent">Bonjour, {{ auth.user?.username }}</h1>
            <p class="text-sm text-slate-500 mt-1">Que voulez-vous faire ?</p>
          </div>
          <div v-else class="flex items-center gap-3 w-full max-w-xl">
            <button class="btn-secondary" @click="backToCategories">← Retour</button>
            <h1 class="text-xl font-black tracking-tight bg-gradient-to-r from-slate-100 to-slate-400 bg-clip-text text-transparent">{{ categoryTitle }}</h1>
          </div>

          <!-- Niveau 1 : les 4 grandes catégories -->
          <div v-if="!selectedCategory" class="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">

            <div class="card flex flex-col gap-3
                       border-t-2 border-t-blue-600 hover:border-blue-700 hover:bg-blue-950/20
                       hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200
                       cursor-pointer group"
              @click="openCategory('pricing')">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-blue-900/50 flex items-center justify-center text-xl">📁</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-blue-300 transition-colors">Pricing</div>
                  <div class="text-xs text-slate-500">Scripts · Pricer · Documentation</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Structurez, pricez et documentez vos produits.</p>
            </div>

            <div class="card flex flex-col gap-3
                       border-t-2 border-t-yellow-600 hover:border-yellow-700 hover:bg-yellow-950/20
                       hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200
                       cursor-pointer group"
              @click="openCategory('life_cycle')">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-yellow-900/50 flex items-center justify-center text-xl">📒</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-yellow-300 transition-colors">Life Cycle</div>
                  <div class="text-xs text-slate-500">Produits bookés en vie</div>
                </div>
                <span v-if="unreadAlerts > 0"
                  class="ml-auto px-2 py-0.5 rounded-full bg-red-900/60 text-red-300 text-xs font-bold pulse-ring"
                  :title="`${unreadAlerts} alerte(s) non lue(s)`">
                  🔔 {{ unreadAlerts }}
                </span>
              </div>
              <p class="text-xs text-slate-600">Suivi des produits structurés : nominaux, strikes, dates d'observation, statut de rappel/KI.</p>
            </div>

            <div class="card flex flex-col gap-3
                       border-t-2 border-t-amber-600 hover:border-amber-600 hover:bg-amber-950/20
                       hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200
                       cursor-pointer group"
              @click="openCategory('studies')">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-amber-900/50 flex items-center justify-center text-xl">📐</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-amber-300 transition-colors">Studies</div>
                  <div class="text-xs text-slate-500">Fama-French · Carnet d'ordres</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Analyse de performance et reconstruction FIFO des carnets d'ordres.</p>
            </div>

            <div class="card flex flex-col gap-3
                       border-t-2 border-t-pink-600 hover:border-pink-700 hover:bg-pink-950/20
                       hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200
                       cursor-pointer group"
              @click="openCategory('competitive_bidding')">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-pink-900/50 flex items-center justify-center text-xl">📨</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-pink-300 transition-colors">Competitive Bidding</div>
                  <div class="text-xs text-slate-500">RFQ · Analyse contreparties</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Comparez les prix reçus des banques au prix modèle Structura.</p>
            </div>

          </div>

          <!-- Niveau 2 : sous-cards de la catégorie sélectionnée -->
          <div v-else-if="selectedCategory === 'pricing'" class="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">

            <!-- Mes Scripts -->
            <RouterLink to="/scripts"
              class="card flex flex-col gap-3
                     hover:border-blue-700 hover:bg-blue-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-blue-900/50 flex items-center justify-center text-xl">📁</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-blue-300 transition-colors">Mes Scripts</div>
                  <div class="text-xs text-slate-500">Bibliothèque de PayScripts</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Gérez, organisez et partagez vos scripts de pricing dans des dossiers.</p>
            </RouterLink>

            <!-- Nouveau script -->
            <RouterLink to="/pricer"
              class="card flex flex-col gap-3
                     hover:border-green-700 hover:bg-green-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-green-900/50 flex items-center justify-center text-xl">✏️</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-green-300 transition-colors">Nouveau Script</div>
                  <div class="text-xs text-slate-500">Pricer — éditeur vide</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Ouvrez le pricer avec un éditeur vide et commencez à structurer.</p>
            </RouterLink>

            <!-- Documentation -->
            <RouterLink to="/documentation"
              class="card flex flex-col gap-3
                     hover:border-purple-700 hover:bg-purple-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-purple-900/50 flex items-center justify-center text-xl">📚</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-purple-300 transition-colors">Documentation</div>
                  <div class="text-xs text-slate-500">KID PRIIPs · Term Sheets · Bibliothèque</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Générez et archivez vos documents réglementaires et commerciaux.</p>
            </RouterLink>

          </div>

          <div v-else-if="selectedCategory === 'life_cycle'" class="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">

            <!-- Booking -->
            <RouterLink to="/booking"
              class="card flex flex-col gap-3
                     hover:border-yellow-700 hover:bg-yellow-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-yellow-900/50 flex items-center justify-center text-xl">📒</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-yellow-300 transition-colors">Booking</div>
                  <div class="text-xs text-slate-500">Produits bookés</div>
                </div>
                <span v-if="unreadAlerts > 0"
                  class="ml-auto px-2 py-0.5 rounded-full bg-red-900/60 text-red-300 text-xs font-bold pulse-ring"
                  :title="`${unreadAlerts} alerte(s) non lue(s)`">
                  🔔 {{ unreadAlerts }}
                </span>
              </div>
              <p class="text-xs text-slate-600">Suivi des produits structurés en vie : nominaux, strikes, dates d'observation, statut de rappel/KI.</p>
            </RouterLink>

            <!-- Réinvestissement -->
            <RouterLink to="/reinvest"
              class="card flex flex-col gap-3
                     hover:border-orange-700 hover:bg-orange-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-orange-900/50 flex items-center justify-center text-xl">🔄</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-orange-300 transition-colors">Réinvestissement</div>
                  <div class="text-xs text-slate-500">Alternatives à un produit en vie</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Espace de travail interne : partez d'un deal client en vie et cherchez le meilleur sous-jacent de remplacement.</p>
            </RouterLink>

          </div>

          <div v-else-if="selectedCategory === 'studies'" class="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">

            <!-- Étude Fama-French -->
            <RouterLink to="/amc"
              class="card flex flex-col gap-3
                     hover:border-amber-600 hover:bg-amber-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-amber-900/50 flex items-center justify-center text-xl">📐</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-amber-300 transition-colors">Étude Fama-French</div>
                  <div class="text-xs text-slate-500">Analyse AMC · Dépendance gérant</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Décomposez la performance d'un AMC en facteurs de risque et mesurez la valeur ajoutée du gérant.</p>
            </RouterLink>

            <!-- Charger une étude -->
            <div class="card flex flex-col gap-3">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-indigo-900/50 flex items-center justify-center text-xl">📂</div>
                <div>
                  <div class="font-bold text-slate-100">Charger une étude</div>
                  <div class="text-xs text-slate-500">Études AMC sauvegardées</div>
                </div>
              </div>
              <div v-if="recentStudiesLoading" class="text-xs text-slate-600">Chargement…</div>
              <div v-else-if="!recentStudies.length" class="text-xs text-slate-600">Aucune étude sauvegardée pour l'instant. Lancez une étude dans le module AMC puis sauvegardez-la.</div>
              <ul v-else class="flex flex-col gap-1.5">
                <li v-for="s in recentStudies" :key="s.id" @click="openStudy(s.id)"
                  class="flex items-center justify-between gap-2 text-xs px-2.5 py-2 rounded-lg border border-slate-800 hover:border-indigo-600 hover:bg-indigo-950/20 cursor-pointer transition-colors">
                  <div class="min-w-0">
                    <div class="text-slate-200 truncate">{{ s.label }}</div>
                    <div class="text-[10px] text-slate-600 font-mono">{{ s.isin }} · {{ new Date(s.updated_at).toLocaleDateString('fr-FR') }}</div>
                  </div>
                  <span class="text-indigo-400 shrink-0">→</span>
                </li>
              </ul>
            </div>

            <!-- Carnet d'ordres FIFO -->
            <RouterLink to="/fifo"
              class="card flex flex-col gap-3
                     hover:border-cyan-700 hover:bg-cyan-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-cyan-900/50 flex items-center justify-center text-xl">📋</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-cyan-300 transition-colors">Carnet d'ordres</div>
                  <div class="text-xs text-slate-500">FIFO · P&amp;L réalisé &amp; latent</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Compilez les carnets d'ordres de fonds et AMC. Reconstruction FIFO avec modes actions ou cert-units.</p>
            </RouterLink>

          </div>

          <div v-else-if="selectedCategory === 'competitive_bidding'" class="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">

            <!-- RFQ Fournisseurs -->
            <RouterLink to="/rfq"
              class="card flex flex-col gap-3
                     hover:border-pink-700 hover:bg-pink-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-pink-900/50 flex items-center justify-center text-xl">📨</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-pink-300 transition-colors">RFQ Fournisseurs</div>
                  <div class="text-xs text-slate-500">Comparer les prix des contreparties</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Collectez les prix reçus des banques pour un produit et comparez-les au prix modèle Structura.</p>
            </RouterLink>

            <!-- Analyse Contreparties -->
            <RouterLink to="/rfq/analyse"
              class="card flex flex-col gap-3
                     hover:border-rose-700 hover:bg-rose-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-rose-900/50 flex items-center justify-center text-xl">📈</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-rose-300 transition-colors">Analyse Contreparties</div>
                  <div class="text-xs text-slate-500">Écarts de prix par banque &amp; produit</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Suivez dans le temps comment chaque contrepartie se positionne, par type de produit, vs le prix modèle Structura.</p>
            </RouterLink>

          </div>

        </div>
      </Transition>

    </main>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'

const auth   = useAuthStore()
const router = useRouter()

const recentStudies        = ref([])
const recentStudiesLoading = ref(true)

async function fetchRecentStudies() {
  recentStudiesLoading.value = true
  try {
    const res = await apiFetch('/api/amc/studies')
    if (res.ok) recentStudies.value = (await res.json()).slice(0, 5)
  } catch { /* ignore */ } finally {
    recentStudiesLoading.value = false
  }
}
fetchRecentStudies()

const unreadAlerts = ref(0)

async function fetchUnreadAlerts() {
  try {
    const res = await apiFetch('/api/alerts?unread_only=true&limit=1')
    if (res.ok) unreadAlerts.value = (await res.json()).unread
  } catch { /* ignore */ }
}
fetchUnreadAlerts()

function openStudy(id) {
  router.push({ path: '/amc', query: { study_id: id } })
}

function logout() {
  auth.logout()
  router.push('/login')
}

// ── Accueil en 4 catégories + drill-down (HOME_REDESIGN_DESIGN.md) ────────
const CATEGORY_TITLES = {
  pricing: 'Pricing',
  life_cycle: 'Life Cycle',
  studies: 'Studies',
  competitive_bidding: 'Competitive Bidding',
}
const selectedCategory = ref(null)
const categoryTitle = computed(() => CATEGORY_TITLES[selectedCategory.value] || '')

function openCategory(key) {
  selectedCategory.value = key
}
function backToCategories() {
  selectedCategory.value = null
}
function onAfterEnter(el) {
  // el.focus() called synchronously from the transitionend-driven after-enter
  // hook doesn't reliably stick (observed: activeElement stays <body>) —
  // deferring one frame lets the browser settle after the transition before
  // taking focus, which is what makes Échap work right after a drill-down.
  requestAnimationFrame(() => el.focus())
}
</script>
