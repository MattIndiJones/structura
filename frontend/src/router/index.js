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
    path: '/amc',
    component: () => import('../views/AmcView.vue'),
  },
  {
    path: '/fifo',
    component: () => import('../views/FifoView.vue'),
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
  return true
})

export default router
