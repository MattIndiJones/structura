<template>
  <header class="sticky top-0 z-40 border-b bg-surface2/95 backdrop-blur"
          style="border-color: var(--border); background-color: rgba(255,255,255,.95);">
    <div class="px-5 py-2.5 flex items-center gap-1">
      <RouterLink to="/" class="flex items-center gap-2.5 pr-4 mr-1 border-r shrink-0 hover:opacity-80 transition-opacity"
                  style="border-color: var(--border);">
        <img src="/tp_logo.png" alt="TP Advisory" class="h-7 w-7 rounded-sm bg-white object-contain p-0.5">
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
import DemoModeToggle from './DemoModeToggle.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// Regroupement par domaine métier — un lien par grande zone fonctionnelle,
// actif dès qu'on est sur une de ses sous-pages (préfixe de route).
const navItems = [
  { label: 'Accueil',    to: '/',              prefixes: [] },
  { label: 'Pricing',    to: '/scripts',       prefixes: ['/scripts', '/pricer', '/documentation'] },
  { label: 'Life Cycle', to: '/booking',       prefixes: ['/booking', '/reinvest'] },
  { label: 'Études',     to: '/amc',           prefixes: ['/amc', '/fifo'] },
  { label: 'RFQ',        to: '/rfq',           prefixes: ['/rfq'] },
]

function isActive(item) {
  if (item.to === '/') return route.path === '/'
  return item.prefixes.some(p => route.path.startsWith(p))
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
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
