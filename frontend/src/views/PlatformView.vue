<template>
  <main class="platform-page"><div class="platform-content">
    <div class="platform-heading"><div><h1>Administration centrale</h1><p class="platform-intro">Supervision des installations et simulation de développement</p></div><button class="btn-secondary" :disabled="!!busy" @click="refresh">Actualiser l’état</button></div>
    <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
    <div class="platform-status card"><span>Registre RFQ : non configuré</span><span>Facturation : désactivée</span></div>
    <section v-if="auth.canManageSimulation" class="card simulation-access"><div><h2>Simulation avec agents</h2><p>Campagnes, comptes et bases séparés des essais manuels. Vous choisissez quand démarrer les IA.</p><p>{{ serviceState('simulation') }}</p></div><button class="btn-primary" :disabled="!!busy" @click="openSimulation">Ouvrir la simulation</button></section>
    <div class="platform-grid"><article v-for="item in installations" :key="item.installation_id" class="card">
      <h2>{{ item.name }}</h2><p>{{ item.capabilities.includes('respond_rfq') ? 'Banque · Répondant RFQ' : 'Institution · Demandeur RFQ' }}</p>
      <dl><dt>Installation</dt><dd>{{ item.key }}</dd><dt>Conservation</dt><dd>Jusqu’à remise à zéro explicite</dd><dt>Environnement</dt><dd>Développement fictif</dd></dl>
      <div class="installation-actions"><span role="status">{{ serviceState(item.key) }}</span><button v-if="auth.user?.developer_access" class="btn-secondary btn-sm" :disabled="!!busy" @click="openOrganization(item)">{{ busy === item.key ? 'Ouverture…' : 'Ouvrir en super utilisateur' }}</button></div>
    </article></div>
    <p class="platform-intro">Les utilisateurs, desks et droits métier se gèrent dans l’administration de leur organisation. Le sélecteur de l’en-tête permet de revenir ici.</p>
  </div></main>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { apiFetch } from '../utils/api.js'
import { prepareContextReload } from '../composables/useContextChanges.js'
import AlertMessage from '../components/ui/AlertMessage.vue'
const auth = useAuthStore(), router = useRouter()
const installations = ref([]), services = ref([]), busy = ref(''), error = ref('')
async function request(path, options) {
  const response = await apiFetch(path, options)
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail || 'Service indisponible.')
  return data
}
async function refresh() {
  error.value = ''
  try {
    installations.value = (await request('/api/platform/installations')).installations
    if (auth.user?.developer_access) services.value = (await request('/api/platform/status')).services
  }
  catch(e) { error.value = e.message }
}
function serviceState(key) {
  const state = services.value.find(service => service.key === key)
  return state?.state === 'RUNNING' ? 'Service actif' : state ? 'Service arrêté ou indisponible' : 'État non vérifié'
}
async function openSimulation() {
  busy.value = 'simulation'; error.value = ''
  try { await request('/api/platform/simulation/start', {method:'POST'}); await router.push('/agent-workshop') }
  catch(e) { error.value = e.message } finally { busy.value = '' }
}
async function openOrganization(item) {
  busy.value = item.key; error.value = ''
  try {
    await request(`/api/platform/installations/${item.key}/start`, {method:'POST'})
    const session = await auth.developmentLogin(item, 'superuser')
    prepareContextReload()
    auth.activate(session.accessToken, session.descriptor, session.identity)
    window.location.hash = '#/'
    window.location.reload()
  } catch(e) { error.value = e.message; busy.value = '' }
}
onMounted(refresh)
</script>
<style scoped>
.platform-page{flex:1;min-height:0;overflow:auto;padding:28px}.platform-content{max-width:1100px;margin:auto;display:flex;flex-direction:column;gap:20px}h1{font-size:24px;font-weight:800}h2{font-size:15px;font-weight:700}.platform-intro,p,dt{color:var(--muted);font-size:13px}.platform-status{display:flex;gap:24px;flex-wrap:wrap;font-size:13px}.platform-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(290px,100%),1fr));gap:14px}dl{margin-top:16px;display:grid;grid-template-columns:100px minmax(0,1fr);gap:8px;font-size:12px}dd{overflow-wrap:anywhere}
.platform-heading,.simulation-access{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}.simulation-access p{margin-top:5px}.installation-actions{margin-top:16px;display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;font-size:12px}.installation-actions span{color:var(--muted)}
</style>
