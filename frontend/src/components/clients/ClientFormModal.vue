<!--
  Création et modification d'un client.

  La détection de doublons ne bloque pas : elle interrompt, montre ce qui
  ressemble, et laisse confirmer. Bloquer interdirait d'enregistrer deux
  sociétés qui portent réellement le même nom commercial ; ne rien dire
  laisserait la base se dédoubler en silence — et deux fiches pour une même
  société, c'est deux historiques amputés.
-->
<template>
  <BaseModal :model-value="true" max-width="560px"
             :title="client ? 'Modifier le client' : 'Nouveau client'"
             @close="$emit('ferme')">
    <form class="flex flex-col gap-4" @submit.prevent="enregistrer">

      <AlertMessage v-if="doublons.length" kind="warning">
        <div class="flex flex-col gap-2">
          <div class="font-semibold">Une société très proche existe déjà</div>
          <ul class="text-xs flex flex-col gap-0.5">
            <li v-for="d in doublons" :key="d.client_id">
              <span class="font-semibold">{{ d.label }}</span>
              — rapprochement sur {{ libelleSignal(d.signal) }}
            </li>
          </ul>
          <div class="text-xs">
            S'il s'agit bien d'une société distincte, confirmez pour enregistrer.
          </div>
        </div>
      </AlertMessage>

      <AlertMessage v-if="erreur" kind="error">{{ erreur }}</AlertMessage>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div class="sm:col-span-2">
          <label class="label">Nom <span style="color: var(--negative)">*</span></label>
          <input v-model="formulaire.name" class="input" required
                 placeholder="Ex : ABC Asset Management" @focus="$event.target.select()" />
        </div>

        <div class="sm:col-span-2">
          <label class="label">Raison sociale</label>
          <input v-model="formulaire.legal_name" class="input"
                 placeholder="Si elle diffère du nom commercial" />
        </div>

        <div>
          <label class="label">Type</label>
          <select v-model="formulaire.client_type" class="select">
            <option v-for="t in TYPES_CLIENT" :key="t.value" :value="t.value">
              {{ t.label }}
            </option>
          </select>
        </div>

        <div>
          <label class="label">Statut</label>
          <select v-model="formulaire.status" class="select">
            <option v-for="s in STATUTS_CLIENT" :key="s.value" :value="s.value">
              {{ s.label }}
            </option>
          </select>
        </div>

        <div>
          <label class="label">Pays</label>
          <input v-model="formulaire.country" class="input" placeholder="Ex : Suisse" />
        </div>

        <div>
          <label class="label">Identifiant externe</label>
          <input v-model="formulaire.external_ref" class="input"
                 placeholder="LEI, code interne…" />
        </div>

        <div>
          <label class="label">Provenance des données</label>
          <select v-model="formulaire.data_origin" class="select">
            <option v-for="origine in PROVENANCES_DONNEES" :key="origine.value"
                    :value="origine.value">{{ origine.label }}</option>
          </select>
          <p class="text-xs mt-1" style="color: var(--subtle)">
            Les données actuelles sont fictives tant qu'elles ne sont pas
            explicitement requalifiées.
          </p>
        </div>

        <div class="sm:col-span-2">
          <label class="label">Notes</label>
          <textarea v-model="formulaire.notes" class="input" rows="3"
                    placeholder="Contexte commercial, particularités…"></textarea>
        </div>
      </div>

      <div class="flex items-center justify-end gap-2 pt-1">
        <button type="button" class="btn-ghost" @click="$emit('ferme')">Annuler</button>
        <button type="submit" class="btn-primary" :disabled="enCours">
          {{ enCours ? 'Enregistrement…'
             : doublons.length ? 'Confirmer et enregistrer'
             : client ? 'Enregistrer' : 'Créer le client' }}
        </button>
      </div>
    </form>
  </BaseModal>
</template>

<script setup>
import { ref, reactive } from 'vue'
import {
  useClientsStore, TYPES_CLIENT, STATUTS_CLIENT, PROVENANCES_DONNEES,
} from '../../stores/clients.js'
import BaseModal from '../ui/BaseModal.vue'
import AlertMessage from '../ui/AlertMessage.vue'

const props = defineProps({
  client: { type: Object, default: null },
})
const emit = defineEmits(['ferme', 'enregistre'])

const store = useClientsStore()
const enCours = ref(false)
const erreur = ref('')
const doublons = ref([])

const formulaire = reactive({
  name: props.client?.name || '',
  legal_name: props.client?.legal_name || '',
  client_type: props.client?.client_type || 'other',
  status: props.client?.status || 'prospect',
  country: props.client?.country || '',
  external_ref: props.client?.external_ref || '',
  data_origin: props.client?.data_origin || 'demo',
  notes: props.client?.notes || '',
})

function libelleSignal(signal) {
  return { external_ref: "l'identifiant externe", legal_name: 'la raison sociale',
           name: 'le nom' }[signal] || signal
}

async function enregistrer() {
  enCours.value = true
  erreur.value = ''
  try {
    if (props.client) {
      const modifie = await store.modifierClient(props.client.id, { ...formulaire })
      emit('enregistre', modifie)
    } else {
      const cree = await store.creerClient({
        ...formulaire,
        // Le serveur ne crée qu'après confirmation explicite : le drapeau ne
        // se pose que lorsqu'un avertissement a réellement été montré.
        confirm_duplicate: doublons.value.length > 0,
      })
      emit('enregistre', cree)
    }
  } catch (e) {
    if (e.code === 'CLIENT_DUPLICATE_SUSPECTED') {
      doublons.value = e.duplicates || []
    } else {
      erreur.value = e.message
    }
  } finally {
    enCours.value = false
  }
}
</script>
