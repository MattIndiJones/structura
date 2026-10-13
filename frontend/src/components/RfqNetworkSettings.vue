<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { apiFetch } from '../utils/api.js'
import BaseModal from './ui/BaseModal.vue'
import AlertMessage from './ui/AlertMessage.vue'
const props = defineProps({ relations: Array, counterparties: Array, entityId: Number })
const emit = defineEmits(['changed'])
const identity = ref('')
const channels = ref([])
const show = ref(false)
const pairing = ref(null)
const busy = ref(false)
const error = ref('')
const imported = ref('')
const form = reactive({ relationship_id: null, peer_url: '', peer_installation_id: '', peer_counterparty_id: null, reason: '' })
const relation = computed(() => props.relations?.find(r => r.id === form.relationship_id))
const role = computed(() => relation.value?.requester_entity_id === props.entityId ? 'REQUESTER' : 'BANK')
const available = computed(() => props.relations?.filter(r => !channels.value.some(c => c.relationship_id === r.id)) || [])
async function api(path, options) {
  const res = await apiFetch(`/api/rfq-transport${path}`, options ? { ...options, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(options.body) } : undefined)
  const value = await res.json()
  if (!res.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Configuration du canal refusée')
  return value
}
async function load() {
  try { const value = await api('/channels'); identity.value = value.installation_id; channels.value = value.channels }
  catch (failure) { error.value = failure.message }
}
onMounted(load)
function open() {
  Object.assign(form, { relationship_id: null, peer_url: '', peer_installation_id: '', peer_counterparty_id: null, reason: '' })
  pairing.value = null; imported.value = ''; error.value = ''; show.value = true
}
async function configure() {
  busy.value = true; error.value = ''
  try {
    const peer = role.value === 'BANK' ? JSON.parse(imported.value) : {}
    const value = await api('/channels', { method: 'POST', body: { ...form, role: role.value, expected_version: relation.value.version,
      ...(role.value === 'BANK' ? { channel_id: peer.channel_id, secret: peer.secret, peer_installation_id: peer.installation_id } : {}) } })
    pairing.value = value.pairing
    imported.value = ''
    await load()
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}
async function change(channel, probe = false) {
  busy.value = true; error.value = ''
  try {
    if (probe) await api(`/channels/${channel.id}/probe`, { method: 'POST' })
    else await api(`/channels/${channel.id}`, { method: 'PUT', body: { active: !channel.active,
      expected_version: props.relations.find(r => r.id === channel.relationship_id).version,
      reason: channel.active ? 'Suspension administrative du canal' : 'Reprise administrative du canal' } })
    await load(); emit('changed')
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}
</script>
<template>
  <section v-if="entityId" class="card space-y-2">
    <div class="flex flex-wrap justify-between items-center gap-2"><h2 class="text-sm font-semibold">Échanges entre installations Structura</h2><button class="btn-secondary btn-sm" :disabled="busy" @click="open">Appairer un partenaire</button></div>
    <p class="text-xs text-slate-500">Installation : <span class="select-all break-all">{{ identity }}</span> · partagez cet identifiant avec l’administrateur du partenaire.</p>
    <AlertMessage v-if="error && !show" kind="error">{{ error }}</AlertMessage>
    <div class="max-h-48 overflow-y-auto overscroll-contain text-xs space-y-2">
      <div v-for="channel in channels" :key="channel.id" class="border-t pt-2 flex flex-wrap items-center justify-between gap-2"><div>{{ relations.find(r => r.id === channel.relationship_id)?.reference }} · {{ channel.peer_url }}<p>{{ !channel.active ? 'Suspendu' : channel.confirmed_at ? 'Accord distant reconnu' : 'Appairage à confirmer' }}</p></div><div class="flex gap-1"><button class="btn-ghost btn-sm" :disabled="busy || !channel.active" @click="change(channel, true)">Vérifier les deux installations</button><button class="btn-ghost btn-sm" :disabled="busy" @click="change(channel)">{{ channel.active ? 'Suspendre' : 'Reprendre' }}</button></div></div>
    </div>
    <BaseModal v-model="show" title="Appairer les installations RFQ" max-width="720px" @update:model-value="pairing = null">
      <div class="space-y-3">
        <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
        <template v-if="pairing"><AlertMessage kind="success">Canal enregistré. La clé ci-dessous est affichée une seule fois ; transmettez-la à l’administrateur du partenaire par votre canal sécurisé, puis vérifiez les deux installations.</AlertMessage><label class="block"><span class="label">Informations d’appairage confidentielles</span><textarea class="input w-full font-mono text-xs" rows="7" readonly :value="JSON.stringify(pairing, null, 2)" /></label></template>
        <form v-else id="rfq-channel-form" class="space-y-3" @submit.prevent="configure">
          <p class="text-xs">Chaque installation configure le même périmètre commercial et reconnaît sa propre partie de la relation. HTTPS est obligatoire. Les identifiants locaux et les calculs privés restent sur leur installation.</p>
          <label class="block"><span class="label">Relation directionnelle</span><select v-model.number="form.relationship_id" class="select w-full" required><option :value="null">Choisir une relation</option><option v-for="r in available" :key="r.id" :value="r.id">{{ r.requester_name }} → {{ r.partner_name }} · {{ r.reference }}</option></select></label>
          <p v-if="relation" class="text-xs">{{ role === 'BANK' ? 'Réception et publication côté banque' : 'Demandes et réception des prix côté demandeur' }} · reconnaissez d’abord votre version dans la relation.</p>
          <label class="block"><span class="label">Adresse HTTPS de l’installation distante</span><input v-model="form.peer_url" class="input w-full" required placeholder="https://structura.partenaire.fr" /></label>
          <label v-if="role === 'REQUESTER'" class="block"><span class="label">Identifiant de l’installation distante</span><input v-model="form.peer_installation_id" class="input w-full" required /></label>
          <label v-else class="block"><span class="label">Informations d’appairage du demandeur</span><textarea v-model="imported" class="input w-full font-mono text-xs" rows="6" required /></label>
          <label class="block"><span class="label">Votre entité juridique, vue comme contrepartie par le partenaire · rapprochement local</span><select v-model.number="form.peer_counterparty_id" class="select w-full" required><option :value="null">Rapprocher explicitement</option><option v-for="cp in counterparties" :key="cp.id" :value="cp.id">{{ cp.name }}</option></select></label>
          <label class="block"><span class="label">Motif</span><input v-model="form.reason" class="input w-full" minlength="3" required /></label>
        </form>
      </div>
      <template #footer><button class="btn-secondary" @click="show = false; pairing = null">Fermer</button><button v-if="!pairing" form="rfq-channel-form" type="submit" class="btn-primary" :disabled="busy || !relation">Enregistrer le canal</button></template>
    </BaseModal>
  </section>
</template>
