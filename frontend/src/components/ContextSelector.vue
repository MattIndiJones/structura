<template>
  <div class="context" data-context-selector>
    <button class="context-current" :disabled="!auth.user?.developer_access && !adminPortal" :aria-expanded="opened" @click="opened = !opened">
      <strong>{{ auth.user?.installation?.name || 'Structura' }}</strong><span>{{ profileLabel }} · {{ auth.user?.username }} <span v-if="auth.user?.developer_access || adminPortal">▾</span></span>
    </button>
    <BaseModal v-model="opened" title="Changer de contexte" max-width="460px">
        <div class="context-body" data-context-selector>
          <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
          <p v-if="adminPortal">Choisissez une organisation et un profil dans le portail des comptes. Un retour vers Structura Admin reste disponible, y compris si l’ouverture échoue.</p>
          <template v-else>
            <label class="label">Organisation<select v-model="selectedId" class="input" :disabled="loading"><option v-for="item in installations" :key="item.installation_id" :value="item.installation_id">{{ item.name }}</option></select></label>
            <label v-if="selected?.kind !== 'platform'" class="label">Profil<select v-model="username" class="input" :disabled="loading"><option v-for="item in profiles" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label>
            <p>La session de cet onglet sera remplacée. Les autres onglets conservent leur contexte.</p>
          </template>
        </div>
        <template #footer><button class="btn-secondary" :disabled="loading" @click="opened = false">Annuler</button><button class="btn-primary" :disabled="loading || (!selected && !adminPortal)" @click="switchContext">{{ loading ? 'Ouverture…' : adminPortal ? 'Choisir un autre compte' : 'Ouvrir ce contexte' }}</button></template>
    </BaseModal>
  </div>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { usePricingStore } from '../stores/pricing.js'
import { confirmer } from '../composables/useConfirm.js'
import { hasContextChanges, prepareContextReload } from '../composables/useContextChanges.js'
import { destinationForContext } from '../utils/contextSwitch.js'
import AlertMessage from './ui/AlertMessage.vue'
import BaseModal from './ui/BaseModal.vue'
import { portalFetch } from '../utils/session.js'
import { installationUrl } from '../utils/session.js'
import { accessErrorMessage } from '../utils/accessErrors.js'
const auth = useAuthStore(), pricing = usePricingStore(), route = useRoute()
const opened = ref(false), loading = ref(false), error = ref(''), installations = ref([]), selectedId = ref(''), username = ref('superuser')
const profiles = [['superuser','Super utilisateur'],['front','Front'],['operations','Opérations'],['controller','Contrôleur']]
const selected = computed(() => installations.value.find(item => item.installation_id === selectedId.value))
const adminPortal = computed(() => auth.user?.admin_workbench && auth.user?.development_admin_enabled && auth.user?.platform_url)
const profileLabel = computed(() => ({ organization_admin:'Super utilisateur', user:'Front', ops_maker:'Opérations', checker:'Contrôleur', platform_admin:'Admin central', admin:'Admin' }[auth.user?.role] || auth.user?.role))
watch(selectedId, () => { username.value = 'superuser' }, { flush: 'sync' })
watch(opened, async value => {
  if (!value) return
  error.value = ''
  if (adminPortal.value) return
  try { const response = await portalFetch('/api/platform/development/access'); const data = await response.json(); if (!response.ok || !data.enabled) throw new Error('Accès développeur indisponible.'); installations.value = data.installations; selectedId.value = auth.installation?.installation_id || ''; username.value = auth.user.username }
  catch(e) { error.value = accessErrorMessage(e) }
})
async function switchContext() {
  if (loading.value) return
  if (adminPortal.value) {
    if ((pricing.variantDirty || pricing.hasUnsavedSession() || hasContextChanges()) && !await confirmer({ titre:'Changer de compte sans enregistrer ?', message:'Enregistrez vos saisies avant de quitter cet écran, ou abandonnez-les.', confirmer:'Abandonner et changer', danger:true })) return
    try {
      const target = installationUrl({url: auth.user.platform_url})
      prepareContextReload()
      window.location.assign(target + '/#/login')
    } catch (e) { error.value = accessErrorMessage(e) }
    return
  }
  if (!selected.value) return
  const targetUsername = selected.value.kind === 'platform' ? 'admin' : username.value
  if (selectedId.value === auth.installation?.installation_id && targetUsername === auth.user.username) { opened.value = false; return }
  if (pricing.variantDirty || pricing.hasUnsavedSession() || hasContextChanges()) {
    opened.value = false
    if (!await confirmer({ titre:'Changer de contexte sans enregistrer ?', message:'Des saisies ont été modifiées. Enregistrez-les avant de changer de contexte, ou abandonnez-les.', confirmer:'Abandonner et changer', danger:true })) return
  }
  loading.value = true; error.value = ''
  try {
    if (selected.value.kind === 'platform') {
      const response = await portalFetch('/api/platform/development/admin-workbench', {method:'POST',headers:{'X-Structura-Development':'1'}})
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Ouverture Admin indisponible.')
      prepareContextReload(); window.location.assign(data.url); return
    }
    const session = await auth.developmentLogin(selected.value, targetUsername); const path = await destinationForContext(route, auth.installation, session.descriptor, session.accessToken, session.identity); prepareContextReload(); auth.activate(session.accessToken, session.descriptor, session.identity); pricing.relacherVariante(); window.location.replace(window.location.pathname + window.location.search + '#' + path); window.location.reload()
  }
  catch(e) { error.value = accessErrorMessage(e); loading.value = false; opened.value = true }
}
</script>
<style scoped>
.context-current{display:flex;flex-direction:column;text-align:left;max-width:250px;padding:4px 9px;border:1px solid var(--border);border-radius:7px}.context-current strong{font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.context-current span{font-size:11px;color:var(--muted)}
.context-backdrop{position:fixed;inset:0;z-index:60;background:#10243d55;display:flex;align-items:center;justify-content:center;padding:20px}.context-dialog{width:460px;max-width:100%;max-height:calc(100dvh - 40px);padding:0;display:flex;flex-direction:column;overflow:hidden}.context-heading{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid var(--border)}h2{font-size:16px;font-weight:700}.context-body{padding:20px;overflow:auto;display:flex;flex-direction:column;gap:16px;min-height:0}.context-body label{display:flex;flex-direction:column;gap:6px}.context-body p{color:var(--muted);font-size:12px}footer{display:flex;justify-content:flex-end;gap:8px;padding:14px 20px;border-top:1px solid var(--border)}
</style>
