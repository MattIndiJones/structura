import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router/index.js'
import App from './App.vue'
import './style.css'

// Note: le thème Chart.js (src/charts/theme.js) n'est PAS importé ici —
// il n'a aucune dépendance sur le paquet chart.js (208 Ko) et ce serait
// sinon le tirer dans le chunk d'entrée principal, chargé même sur les
// pages sans aucun graphique (Login, Admin...). Chaque vue/composant qui
// utilise déjà Chart.js appelle applyChartTheme(Chart) une fois, dans son
// propre chunk lazy-loadé existant — voir charts/theme.js.

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
