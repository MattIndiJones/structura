<template>
  <header class="app-header sticky top-0 z-40 border-b bg-surface2/95 backdrop-blur"
          style="border-color: var(--border); background-color: rgba(255,255,255,.95);">
    <div class="px-5 py-2.5 flex items-center gap-1">
      <RouterLink to="/" class="flex items-center gap-2.5 pr-4 mr-1 border-r shrink-0 hover:opacity-80 transition-opacity"
                  style="border-color: var(--border);">
        <span class="brand-mark">
          <img src="/tp_logo.png" alt="TP Advisory">
        </span>
        <span class="font-display font-black tracking-tight text-[15px]" style="color: var(--text);">Structura</span>
      </RouterLink>

      <nav class="flex items-center gap-0.5 overflow-x-auto" aria-label="Navigation principale">
        <RouterLink v-for="item in navItems" :key="item.label" :to="item.to"
          class="nav-link" :class="{ 'nav-link-active': isActive(item) }"
          :aria-current="isActive(item) ? 'page' : null">
          {{ item.label }}
        </RouterLink>
      </nav>

      <div class="ml-auto flex items-center gap-2.5 shrink-0 pl-2">
        <DemoModeToggle />
        <span class="text-xs hidden sm:inline" style="color: var(--muted);">{{ auth.user?.username }}</span>
        <RouterLink v-if="auth.isAdmin" to="/admin" title="Administration" aria-label="Administration" class="admin-gear">⚙️</RouterLink>
        <button class="btn-ghost btn-sm" @click="logout">Déconnexion</button>
      </div>
    </div>
  </header>
</template>

<script setup>
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { usePricingStore } from '../stores/pricing.js'
import DemoModeToggle from './DemoModeToggle.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const pricing = usePricingStore()

// Regroupement par domaine métier — un lien par grande zone fonctionnelle,
// actif dès qu'on est sur une de ses sous-pages (préfixe de route).
const navItems = [
  { label: 'Accueil',    to: '/', prefixes: [] },
  { label: 'Pricing',    to: { path: '/', query: { category: 'pricing' } },             prefixes: ['/scripts', '/pricer', '/documentation'], category: 'pricing' },
  { label: 'Life Cycle', to: { path: '/', query: { category: 'life_cycle' } },           prefixes: ['/booking', '/reinvest'],                 category: 'life_cycle' },
  { label: 'Risk Mgmt',  to: { path: '/', query: { category: 'risk_management' } },      prefixes: ['/risk'],                                 category: 'risk_management' },
  { label: 'Études',     to: { path: '/', query: { category: 'studies' } },              prefixes: ['/amc', '/fifo'],                         category: 'studies' },
  { label: 'RFQ',        to: { path: '/', query: { category: 'competitive_bidding' } },  prefixes: ['/rfq'],                                  category: 'competitive_bidding' },
]

function isActive(item) {
  if (item.to === '/') return route.path === '/' && !route.query.category
  if (route.path === '/') return !!item.category && route.query.category === item.category
  return item.prefixes.some(p => route.path.startsWith(p))
}

/**
 * Déconnexion : on RECHARGE, on ne navigue pas.
 *
 * Naviguer vers /login ne vidait que le store d'authentification. Les quatre
 * autres — pricing, deals, RFQ, portefeuilles, une cinquantaine d'états —
 * gardaient les données du compte précédent, et le compte suivant les voyait
 * jusqu'à ce qu'on rafraîchisse la page à la main.
 *
 * Écrire une remise à zéro par store serait une promesse à tenir pour chaque
 * `ref` ajouté un jour : le premier oubli ferait fuiter les deals d'un
 * utilisateur chez un autre. Sur une application qui porte des positions et
 * des prix par entité, la garantie doit être structurelle, pas disciplinaire.
 * Un rechargement la rend inconditionnelle — et la déconnexion n'est pas un
 * chemin où la milliseconde compte.
 */
function logout() {
  auth.logout()
  // Le jeton est parti ; la déclinaison éventuellement ouverte aussi, sinon
  // l'avertissement de fermeture du navigateur s'interposerait sur une sortie
  // délibérée.
  pricing.relacherVariante()
  window.location.hash = '#/login'
  window.location.reload()
}
</script>

<style scoped>
.app-header {
  box-shadow:
    0 1px 0 rgba(11, 26, 49, .04),
    0 7px 20px rgba(11, 26, 49, .045);
}
.app-header::after {
  content: '';
  position: absolute;
  top: 100%;
  right: 0;
  left: 0;
  height: 16px;
  background: linear-gradient(to bottom, rgba(255, 255, 255, .72), rgba(250, 249, 246, 0));
  pointer-events: none;
}
.brand-mark {
  display: inline-flex;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  align-items: flex-start;
  justify-content: center;
  overflow: hidden;
  border-radius: 4px;
  background: #fff;
}
.brand-mark img {
  width: 56px;
  height: 56px;
  max-width: none;
  flex: none;
  transform: translateY(-1px);
}
.nav-link {
  padding: .5rem .85rem;
  border-radius: 8px;
  font-size: .8rem;
  font-weight: 600;
  color: var(--muted);
  white-space: nowrap;
  transition: background-color .15s, color .15s;
}
.nav-link:hover { background: var(--surface2); color: var(--text); }
.nav-link-active { background: var(--accent-light); color: var(--accent); }
.admin-gear {
  font-size: 1.05rem;
  line-height: 1;
  color: var(--muted);
  transition: color .15s;
}
.admin-gear:hover { color: var(--gold); }
</style>
