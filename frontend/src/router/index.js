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
  },
  {
    path: '/scripts',
    component: () => import('../views/ScriptsView.vue'),
  },
  {
    path: '/pricer',
    component: () => import('../views/PricerView.vue'),
  },
  {
    path: '/pricer/:id',
    component: () => import('../views/PricerView.vue'),
  },
  {
    path: '/documentation',
    component: () => import('../views/DocumentationView.vue'),
  },
  {
    path: '/booking',
    component: () => import('../views/BookingView.vue'),
  },
  {
    path: '/reinvest',
    component: () => import('../views/ReinvestView.vue'),
  },
  {
    path: '/amc',
    component: () => import('../views/AmcView.vue'),
  },
  {
    path: '/fifo',
    component: () => import('../views/FifoView.vue'),
  },
  {
    path: '/rfq',
    component: () => import('../views/RfqView.vue'),
  },
  {
    path: '/rfq/analyse',
    component: () => import('../views/RfqAnalysisView.vue'),
  },
  {
    path: '/admin',
    component: () => import('../views/AdminView.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/admin/rfq-providers',
    component: () => import('../views/AdminRfqProvidersView.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/admin/counterparties',
    component: () => import('../views/AdminCounterpartiesView.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/admin/browse/:table?',
    component: () => import('../views/AdminBrowseView.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/admin/users',
    component: () => import('../views/AdminUsersView.vue'),
    meta: { requiresAdmin: true },
  },
  {
    path: '/admin/entities',
    component: () => import('../views/AdminEntitiesView.vue'),
    meta: { requiresAdmin: true },
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
