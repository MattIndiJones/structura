import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('../views/HomeView.vue'),
    meta: { title: 'Accueil' },
  },
  {
    path: '/scripts',
    component: () => import('../views/ScriptsView.vue'),
    meta: { title: 'Mes Scripts' },
  },
  {
    path: '/pricer',
    component: () => import('../views/PricerView.vue'),
    meta: { title: 'Pricer' },
  },
  {
    path: '/pricer/:id',
    component: () => import('../views/PricerView.vue'),
    meta: { title: 'Pricer' },
  },
  {
    path: '/documentation',
    component: () => import('../views/DocumentationView.vue'),
    meta: { title: 'Documentation' },
  },
  {
    path: '/booking',
    component: () => import('../views/BookingView.vue'),
    meta: { title: 'Booking — produits bookés' },
  },
  {
    path: '/risk',
    component: () => import('../views/RiskManagementView.vue'),
    meta: { title: 'Risk Management' },
  },
  {
    path: '/reinvest',
    component: () => import('../views/ReinvestView.vue'),
    meta: { title: 'Réinvestissement' },
  },
  {
    path: '/amc',
    component: () => import('../views/AmcView.vue'),
    meta: { title: 'Analyse AMC' },
  },
  {
    path: '/fifo',
    component: () => import('../views/FifoView.vue'),
    meta: { title: "Carnet d'ordres — FIFO" },
  },
  {
    path: '/rfq',
    component: () => import('../views/RfqView.vue'),
    meta: { title: 'RFQ Fournisseurs' },
  },
  {
    path: '/rfq/analyse',
    component: () => import('../views/RfqAnalysisView.vue'),
    meta: { title: 'Analyse Contreparties' },
  },
  {
    path: '/admin',
    component: () => import('../views/AdminView.vue'),
    meta: { requiresAdmin: true, title: 'Administration' },
  },
  {
    path: '/admin/rfq-providers',
    component: () => import('../views/AdminRfqProvidersView.vue'),
    meta: { requiresAdmin: true, title: 'Fournisseurs RFQ' },
  },
  {
    path: '/admin/counterparties',
    component: () => import('../views/AdminCounterpartiesView.vue'),
    meta: { requiresAdmin: true, title: 'Contreparties deals' },
  },
  {
    path: '/admin/browse/:table?',
    component: () => import('../views/AdminBrowseView.vue'),
    meta: { requiresAdmin: true, title: "Données de l'application" },
  },
  {
    path: '/admin/users',
    component: () => import('../views/AdminUsersView.vue'),
    meta: { requiresAdmin: true, title: 'Utilisateurs' },
  },
  {
    path: '/admin/entities',
    component: () => import('../views/AdminEntitiesView.vue'),
    meta: { requiresAdmin: true, title: 'Entités' },
  },
  {
    path: '/admin/market-data',
    component: () => import('../views/AdminMarketDataView.vue'),
    meta: { requiresAdmin: true, title: 'Données de marché' },
  },
  {
    path: '/admin/compute',
    component: () => import('../views/AdminComputeView.vue'),
    meta: { requiresAdmin: true, title: 'Files de calcul' },
  },
  {
    path: '/admin/uat-generator',
    component: () => import('../views/AdminUatGeneratorView.vue'),
    meta: { requiresAdmin: true, title: 'Générateur UAT' },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) return true
  if (!auth.isAuthenticated) return '/login'
  // Restore user profile if missing (e.g. page refresh)
  if (!auth.user) await auth.fetchMe()
  if (!auth.isAuthenticated) return '/login'
  if (to.meta.requiresAdmin && !auth.isAdmin) return '/'
  return true
})

export default router
