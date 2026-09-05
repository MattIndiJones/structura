<!--
  Enregistrement d'une interaction.

  Le sélecteur de participants ne propose que les personnes EN POSTE chez ce
  client : une réunion tenue chez cette maison ne peut pas avoir pour
  participant quelqu'un qui n'y travaille pas. Le serveur applique la même
  règle — ce filtre est un confort, pas la garantie.
-->
<template>
  <BaseModal :model-value="true" max-width="540px"
             :title="`Interaction — ${client.name}`" @close="$emit('ferme')">
    <form class="flex flex-col gap-4" @submit.prevent="enregistrer">

      <AlertMessage v-if="erreur" kind="error">{{ erreur }}</AlertMessage>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label class="label">Date</label>
          <input v-model="formulaire.interaction_date" type="date" class="input" required />
        </div>
        <div>
          <label class="label">Type</label>
          <select v-model="formulaire.interaction_type" class="select">
            <option v-for="t in TYPES_INTERACTION" :key="t.value" :value="t.value">
              {{ t.label }}
            </option>
          </select>
        </div>
        <div class="sm:col-span-2">
          <label class="label">Résumé</label>
          <input v-model="formulaire.summary" class="input"
                 placeholder="Ex : revue de book, appétit pour un Phoenix 3Y" />
        </div>
        <div class="sm:col-span-2">
          <label class="label">Notes</label>
          <textarea v-model="formulaire.notes" class="input" rows="3"></textarea>
        </div>
      </div>

      <div v-if="contacts.length">
        <label class="label">Participants</label>
        <div class="flex flex-col gap-1.5 max-h-40 overflow-y-auto rounded-[10px] p-2"
             style="background: var(--surface2); border: 1px solid var(--border)">
          <label v-for="contact in contacts" :key="contact.affiliation_id"
                 class="flex items-center gap-2 text-sm cursor-pointer">
            <input v-model="participants" type="checkbox"
                   :value="contact.affiliation_id" />
            <span>{{ contact.first_name }} {{ contact.last_name }}</span>
            <span class="text-xs" style="color: var(--subtle)">
              {{ contact.job_title }}
            </span>
          </label>
        </div>
      </div>

      <div class="rounded-[10px] p-3 flex flex-col gap-3"
           style="background: var(--surface2); border: 1px solid var(--border)">
        <div class="text-xs font-semibold uppercase tracking-wider"
             style="color: var(--muted)">Prochaine action</div>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div class="sm:col-span-2">
            <input v-model="formulaire.next_action" class="input"
                   placeholder="Ex : renvoyer un indicatif à 3 ans" />
          </div>
          <div>
            <input v-model="formulaire.next_action_date" type="date" class="input" />
          </div>
        </div>
        <p class="text-xs" style="color: var(--subtle)">
          Renseignée, elle remontera dans « Relances dues » le jour venu.
        </p>
      </div>

      <div class="flex items-center justify-end gap-2 pt-1">
        <button type="button" class="btn-ghost" @click="$emit('ferme')">Annuler</button>
        <button type="submit" class="btn-primary" :disabled="enCours">
          {{ enCours ? 'Enregistrement…' : 'Enregistrer' }}
        </button>
      </div>
    </form>
  </BaseModal>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useClientsStore, TYPES_INTERACTION } from '../../stores/clients.js'
import BaseModal from '../ui/BaseModal.vue'
import AlertMessage from '../ui/AlertMessage.vue'

const props = defineProps({
  client: { type: Object, required: true },
  contacts: { type: Array, default: () => [] },
  opportunityId: { type: [Number, null], default: null },
})
const emit = defineEmits(['ferme', 'enregistre'])

const store = useClientsStore()
const enCours = ref(false)
const erreur = ref('')
const participants = ref([])

const formulaire = reactive({
  interaction_date: new Date().toISOString().slice(0, 10),
  interaction_type: 'call',
  summary: '',
  notes: '',
  next_action: '',
  next_action_date: '',
})

async function enregistrer() {
  enCours.value = true
  erreur.value = ''
  try {
    const creee = await store.creerInteraction({
      client_id: props.client.id,
      opportunity_id: props.opportunityId,
      interaction_date: formulaire.interaction_date,
      interaction_type: formulaire.interaction_type,
      summary: formulaire.summary,
      notes: formulaire.notes || null,
      next_action: formulaire.next_action || null,
      next_action_date: formulaire.next_action_date || null,
      participants: participants.value.map(id => ({ affiliation_id: id })),
    })
    emit('enregistre', creee)
  } catch (e) {
    erreur.value = e.message
  } finally {
    enCours.value = false
  }
}
</script>
