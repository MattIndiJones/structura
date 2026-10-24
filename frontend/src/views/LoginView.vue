<template>
  <main class="access-page"><div class="access-scroll"><div class="access-content">
    <header class="access-title"><img src="/tp_logo.png" alt="TP Advisory" /><div><h1>Structura</h1><p>Produits structurés · RFQ · Cycle de vie</p></div></header>
    <nav class="access-actions" aria-label="Retour et choix de compte">
      <button class="btn-secondary" @click="goBack">← Retour</button>
      <button v-if="installationPortal && installations.length" class="btn-secondary" :disabled="loading && !adminUrl" @click="returnToAdmin">Retour à Structura Admin</button>
    </nav>
    <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
    <p v-if="loading" role="status">Ouverture du compte… Le retour reste disponible.</p>
    <section v-if="adminEnabled" class="card credentials">
      <h2>Structura complet — Admin</h2>
      <p class="my-3">Tous les modules, l’administration et la simulation dans votre environnement de développement.</p>
      <button class="btn-primary" :disabled="loading" @click="openAdmin">{{ loading ? 'Ouverture…' : 'Ouvrir Structura Admin' }}</button>
      <a v-if="platformUrl" :href="platformUrl + '/#/login'" class="block mt-4 text-sm">Accès aux six organisations</a>
    </section>
    <section v-if="installations.length" aria-label="Installations de développement">
      <div class="access-caption"><h2>Choisir une organisation</h2><span>Environnements fictifs de développement</span></div>
      <label class="label access-profile" data-context-selector>Profil à ouvrir<select v-model="developmentProfile" class="input" :disabled="loading"><option v-for="profile in profiles" :key="profile[0]" :value="profile[0]">{{ profile[1] }}</option></select></label>
      <div class="access-grid">
        <button v-for="item in installations" :key="item.installation_id" class="card access-card" :disabled="loading" @click="open(item)">
          <span class="access-mark">{{ item.kind === 'platform' ? 'S' : initials(item.name) }}</span><strong>{{ item.kind === 'platform' ? 'Admin Structura' : item.name }}</strong>
          <span>{{ item.kind === 'platform' ? 'Application complète' : profileLabel }}</span>
          <small>{{ item.kind === 'platform' ? 'Tous les modules · Administration · Simulation' : item.capabilities.includes('respond_rfq') ? 'Banque · Répondant RFQ' : 'Institution · Demandeur RFQ' }}</small>
        </button>
      </div>
    </section>
    <div v-if="registrationEnabled" class="registration-tabs">
      <button class="btn-secondary" @click="mode='login'; error=''">Connexion</button>
      <button class="btn-secondary" @click="mode='register'; error=''">Créer un compte</button>
    </div>
    <details v-if="mode==='login'" class="card credentials" :open="!installations.length">
      <summary>Connexion avec identifiant et mot de passe</summary>
      <form @submit.prevent="submit" class="credentials-form">
        <label v-if="loginInstallations.length" class="label">Installation<select v-model="selectedId" class="input" required><option disabled value="">Choisir une installation</option><option v-for="item in loginInstallations" :key="item.installation_id" :value="item.installation_id">{{ item.name }}</option></select></label>
        <label class="label">Identifiant<input v-model="username" type="text" class="input" autocomplete="username" required /></label>
        <label class="label">Mot de passe<input v-model="password" class="input" type="password" autocomplete="current-password" required /></label>
        <button class="btn-primary" :disabled="loading || !loginReady">{{ loading ? 'Connexion…' : 'Se connecter' }}</button>
      </form>
    </details>
    <form v-if="mode==='register' && registrationEnabled" class="card credentials credentials-form" @submit.prevent="register">
      <h2>Créer un compte de simulation</h2>
      <label class="label">Identifiant<input v-model="registration.username" type="text" class="input" placeholder="ex: jdupont" required /></label>
      <label class="label">E-mail<input v-model="registration.email" type="email" class="input" placeholder="ex: j.dupont@banque.fr" required /></label>
      <label class="label">Mot de passe · 12 caractères minimum<input v-model="registration.password" type="password" class="input" autocomplete="new-password" required minlength="12" /></label>
      <label class="label">Confirmer le mot de passe<input v-model="registration.confirmation" type="password" class="input" autocomplete="new-password" required minlength="12" /></label>
      <label class="label">Organisation de simulation<input v-model="registration.entity" type="text" class="input" placeholder="ex: Desk Structuration" required /></label>
      <button class="btn-primary" :disabled="loading">Créer mon compte</button>
    </form>
  </div></div></main>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { useRoute } from 'vue-router'
import AlertMessage from '../components/ui/AlertMessage.vue'
import { installationUrl } from '../utils/session.js'
import { accessErrorMessage } from '../utils/accessErrors.js'
const auth = useAuthStore()
const route = useRoute()
const installations = ref([]), selectedId = ref(''), username = ref(''), password = ref(''), loading = ref(false), error = ref('')
const loginInstallations = ref([]), loginReady = ref(false), installationPortal = ref(false)
const registrationEnabled = ref(false), mode = ref('login')
const adminEnabled = ref(false), platformUrl = ref('')
const adminUrl = ref(''), developmentProfile = ref('superuser')
const profiles = [['superuser','Super utilisateur'],['front','Front'],['operations','Opérations'],['controller','Contrôleur']]
const profileLabel = computed(() => profiles.find(profile => profile[0] === developmentProfile.value)?.[1] || '')
const registration = ref({username:'',email:'',password:'',confirmation:'',entity:''})
function initials(name) { return name.split(' ').slice(0, 2).map(part => part[0]).join('') }
onMounted(async () => {
  error.value = sessionStorage.getItem('auth_notice') || ''
  sessionStorage.removeItem('auth_notice')
  try {
    const options = await fetch('/api/auth/options')
    if (!options.ok) throw new Error('Options de connexion indisponibles.')
    if (options.ok) {
      const settings = await options.json()
      registrationEnabled.value = settings.registration_enabled === true
      adminEnabled.value = settings.development_admin_enabled === true
      platformUrl.value = settings.platform_url || ''
      installationPortal.value = settings.installation_portal === true
      if (settings.admin_workbench_url) adminUrl.value = installationUrl({url: settings.admin_workbench_url})
      if (installationPortal.value) {
        const directory = await fetch('/api/platform/login-options')
        if (!directory.ok) throw new Error('Annuaire de connexion indisponible ; réessayez.')
        loginInstallations.value = (await directory.json()).installations || []
        if (!loginInstallations.value.length) throw new Error('Aucune installation disponible.')
        selectedId.value = loginInstallations.value.find(item => item.key === route.query.organization)?.installation_id || ''
      }
      loginReady.value = true
      if (adminEnabled.value && route.query.development_admin === '1') { await openAdmin(); return }
    }
    const response = await fetch('/api/platform/development/access')
    if (!response.ok) return
    const data = await response.json()
    if (data.enabled) installations.value = data.installations
    if (route.query.console === '1') {
      const central = installations.value.find(item => item.kind === 'platform')
      if (central) { const session = await auth.developmentLogin(central, 'admin'); auth.activate(session.accessToken, session.descriptor, session.identity); enter(); return }
    }
    const requested = installations.value.find(item => item.key === route.query.organization)
    if (requested) await open(requested)
  } catch (e) { error.value = accessErrorMessage(e) }
})
function enter() {
  const requested = ['/platform', '/agent-workshop', '/admin/agent-workshop'].includes(route.query.next) ? route.query.next : '/platform'
  const adminNext = ['/', '/admin', '/agent-workshop', '/admin/agent-workshop'].includes(route.query.next) ? route.query.next : '/'
  window.location.hash = auth.user?.password_change_required ? '#/account/security' : auth.isPlatformAdmin ? '#' + requested : auth.isAdmin ? '#' + adminNext : '#/'
  window.location.reload()
}
async function open(item) {
  loading.value = true; error.value = ''
  try {
    if (item.kind === 'platform') {
      const response = await fetch('/api/platform/development/admin-workbench', { method:'POST', headers:{'X-Structura-Development':'1'} })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Ouverture Admin indisponible.')
      window.location.assign(data.url); return
    }
    const session = await auth.developmentLogin(item, developmentProfile.value); auth.activate(session.accessToken, session.descriptor, session.identity); enter()
  }
  catch (e) { error.value = accessErrorMessage(e) } finally { loading.value = false }
}
async function returnToAdmin() {
  if (adminUrl.value) { window.location.assign(adminUrl.value + '/#/'); return }
  const admin = installations.value.find(item => item.kind === 'platform')
  if (admin) await open(admin)
}
function goBack() {
  if (window.history?.length > 1) { window.history.back(); return }
  if (installationPortal.value) { returnToAdmin(); return }
  window.location.hash = '#/'
  window.location.reload()
}
async function openAdmin() {
  loading.value=true; error.value=''
  try { await auth.developmentAdminLogin(); enter() }
  catch(e) { error.value=accessErrorMessage(e) } finally { loading.value=false }
}
async function submit() {
  loading.value = true; error.value = ''
  try {
    if (!loginReady.value) throw new Error('Options de connexion indisponibles.')
    const descriptor = loginInstallations.value.find(item => item.installation_id === selectedId.value)
    if (installationPortal.value && !descriptor) throw new Error('Choisissez une installation.')
    await auth.login(username.value, password.value, descriptor || null); enter()
  }
  catch (e) { error.value = accessErrorMessage(e) } finally { loading.value = false }
}
async function register() {
  if (registration.value.password !== registration.value.confirmation) { error.value='Les mots de passe diffèrent.'; return }
  loading.value=true; error.value=''
  try {
    const response=await fetch('/api/auth/register', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:registration.value.username,email:registration.value.email,password:registration.value.password,entity_name:registration.value.entity})})
    const data=await response.json()
    if (!response.ok) throw new Error(data.detail || 'Inscription indisponible.')
    await auth.login(registration.value.username,registration.value.password)
    enter()
  } catch(e) {error.value=e.message} finally {loading.value=false}
}
</script>
<style scoped>
.access-page{height:100dvh;display:flex;min-height:0;background:var(--bg)}.access-scroll{flex:1;overflow:auto;padding:clamp(20px,4vh,48px) 24px}.access-content{max-width:1050px;margin:auto;display:flex;flex-direction:column;gap:24px}
.access-title{display:flex;align-items:center;gap:16px}.access-title img{width:64px;height:64px;object-fit:contain}h1{font-size:26px;font-weight:800;letter-spacing:-.04em}p,.access-caption span{font-size:13px;color:var(--muted)}
.access-caption{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:14px}h2{font-size:16px;font-weight:700}.access-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.access-actions{display:flex;gap:12px;flex-wrap:wrap}.access-profile{display:flex;flex-direction:column;gap:6px;max-width:280px;margin-bottom:16px}
.access-card{display:flex;flex-direction:column;align-items:flex-start;gap:8px;min-height:175px;text-align:left;transition:border-color .15s}.access-card:hover,.access-card:focus-visible{border-color:var(--accent)}.access-card strong{font-size:14px}.access-card span:not(.access-mark){font-size:12px;color:var(--accent)}.access-card small{font-size:11px;color:var(--muted)}
.access-mark{display:grid;place-items:center;width:34px;height:34px;background:var(--accent-light);color:var(--accent);border-radius:8px;font-size:12px;font-weight:800}.credentials{max-width:520px;width:100%;align-self:center}.credentials summary{cursor:pointer;font-size:13px;font-weight:600}.credentials-form{display:flex;flex-direction:column;gap:12px;margin-top:18px}.credentials-form label{display:flex;flex-direction:column;gap:5px}
.registration-tabs{display:flex;justify-content:center;gap:10px}
@media(max-width:850px){.access-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:440px){.access-grid{grid-template-columns:1fr}.access-scroll{padding:20px 14px}.access-card{min-height:145px}}
</style>
