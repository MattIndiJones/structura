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
    // Une déclinaison s'ouvre par SON identifiant, pas par celui de son
    // parent : la barre de variantes retrouve l'origine toute seule, et un
    // lien partagé désigne sans ambiguïté ce qu'on voulait montrer.
    path: '/pricer/v/:variantId',
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
  // ── Module Clients ────────────────────────────────────────────────
  // Chaque section est une ROUTE, pas un onglet local. Trois conséquences,
  // toutes voulues : le retour du navigateur ramène à la section précédente
  // et non hors du module, une section se partage par son lien, et revenir
  // d'une fiche retrouve l'onglet d'où l'on venait.
  //
  // La fiche client vit sous `/clients/fiche/:id` et non `/clients/:id` :
  // sinon `/clients/contacts` serait capturé comme une fiche d'identifiant
  // « contacts ». Un segment explicite vaut mieux qu'un ordre de déclaration
  // qu'on finit toujours par casser.
  // `/clients` n'est PAS une page : le menu du module est la grille de
  // l'accueil, catégorie Clients. Deux écrans qui font le même choix divergent
  // au premier sous-module ajouté — celui qu'on n'ajoute qu'à un seul des deux.
  {
    path: '/clients',
    redirect: { path: '/', query: { category: 'clients' } },
  },
  {
    path: '/clients/fiche/:id/:section?',
    component: () => import('../views/ClientDetailView.vue'),
    meta: { title: 'Client' },
  },
  {
    path: '/clients/contacts/:id(\\d+)',
    component: () => import('../views/PersonDetailView.vue'),
    meta: { title: 'Contact' },
  },
  {
    path: '/clients/opportunites/:id(\\d+)',
    component: () => import('../views/OpportunityDetailView.vue'),
    meta: { title: 'Opportunité' },
  },
  {
    path: '/clients/:section(apercu|liste|contacts|opportunites|signaux|analytics|import)',
    component: () => import('../views/ClientsView.vue'),
    meta: { title: 'Clients' },
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
    path: '/admin/underlyings',
    component: () => import('../views/AdminUnderlyingsView.vue'),
    meta: { requiresAdmin: true, title: 'Sous-jacents' },
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

  // Une déclinaison modifiée et non enregistrée se perd dès qu'on quitte
  // l'écran. La barre de déclinaisons prévenait pour SES propres boutons, donc
  // pour un seul chemin sur cinq : le retour navigateur, le lien « ← Retour »,
  // le menu du haut et les liens du tableau comparatif emportaient tout en
  // silence. Le garde de route les couvre tous d'un coup, parce qu'il est le
  // seul endroit que toute navigation traverse.
  //
  // Aller d'une déclinaison à une autre est exclu : la barre pose déjà la
  // question, et la poser deux fois apprend à cliquer sans lire.
  if (!String(to.path).startsWith('/pricer')) {
    const { usePricingStore } = await import('../stores/pricing.js')
    const store = usePricingStore()
    if (store.variantDirty) {
      const { confirmer } = await import('../composables/useConfirm.js')
      const partir = await confirmer({
        titre: 'Quitter sans enregistrer ?',
        message: 'La déclinaison ouverte porte des modifications qui ne sont pas '
               + 'encore écrites. Elles seront perdues.',
        confirmer: 'Quitter sans enregistrer', danger: true,
      })
      if (!partir) return false
      // Il vient d'abandonner ces modifications. Garder la déclinaison en
      // mémoire les lui ferait redemander à CHAQUE navigation suivante, alors
      // qu'il n'est déjà plus sur l'écran — c'est exactement ce qui rend un
      // avertissement insupportable, puis ignoré.
      store.relacherVariante()
    }
  }
  return true
})

export default router
