<!--
  Création d'une personne, avec rattachement immédiat à une société.

  Deux choses valent d'être notées.

  La recherche de doublons se déclenche À LA SAISIE, pas seulement au moment
  d'enregistrer : le cas qu'on veut attraper est celui d'une personne déjà
  connue qui rejoint une nouvelle maison. Lui proposer son propre dossier
  pendant qu'on tape son nom évite le second Jean Dupont, alors qu'un
  avertissement à la validation arrive quand la décision est déjà prise.

  Le rattachement se fait dans le même écran : ajouter un contact depuis une
  fiche client ne doit pas imposer deux formulaires successifs.
-->
<template>
  <BaseModal :model-value="true" max-width="560px" title="Nouveau contact"
             @close="$emit('ferme')">
    <form class="flex flex-col gap-4" @submit.prevent="enregistrer">

      <AlertMessage v-if="doublons.length" kind="warning">
        <div class="flex flex-col gap-2">
          <div class="font-semibold">Cette personne est peut-être déjà connue</div>
          <ul class="flex flex-col gap-1">
            <li v-for="d in doublons" :key="d.person_id"
                class="flex items-center justify-between gap-3 text-xs">
              <span>
                <span class="font-semibold">{{ d.label }}</span>
                — rapprochement sur {{ d.signal === 'email' ? "l'e-mail" : 'le nom' }}
              </span>
              <button type="button" class="btn-secondary btn-sm"
                      @click="$emit('rattacher', d.person_id)">
                Ouvrir sa fiche
              </button>
            </li>
          </ul>
          <div class="text-xs">
            Si c'est la même personne, ouvrez sa fiche et ajoutez-lui une
            affiliation : son historique la suivra. Sinon, confirmez pour créer
            un dossier distinct.
          </div>
        </div>
      </AlertMessage>

      <AlertMessage v-if="erreur" kind="error">{{ erreur }}</AlertMessage>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label class="label">Prénom</label>
          <input v-model="formulaire.first_name" class="input"
                 @blur="chercherDoublons" />
        </div>
        <div>
          <label class="label">Nom <span style="color: var(--negative)">*</span></label>
          <input v-model="formulaire.last_name" class="input" required
                 @blur="chercherDoublons" />
        </div>
        <div>
          <label class="label">E-mail</label>
          <input v-model="formulaire.email" type="email" class="input"
                 @blur="chercherDoublons" />
        </div>
        <div>
          <label class="label">Téléphone</label>
          <input v-model="formulaire.phone" class="input" />
        </div>
      </div>

      <div class="rounded-[10px] p-4 flex flex-col gap-3"
           style="background: var(--surface2); border: 1px solid var(--border)">
        <div class="text-xs font-semibold uppercase tracking-wider"
             style="color: var(--muted)">Affiliation</div>
        <p class="text-xs" style="color: var(--subtle)">
          La société où cette personne travaille aujourd'hui. Elle pourra en
          changer plus tard sans perdre son historique.
        </p>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div class="sm:col-span-2">
            <label class="label">Société</label>
            <select v-model="formulaire.client_id" class="select">
              <option :value="null">— Aucune pour l'instant —</option>
              <option v-for="c in clients" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </div>
          <div>
            <label class="label">Fonction</label>
            <input v-model="formulaire.job_title" class="input"
                   :disabled="!formulaire.client_id" placeholder="Ex : Gérant" />
          </div>
          <div>
            <label class="label">Rôle commercial</label>
            <select v-model="formulaire.commercial_role" class="select"
                    :disabled="!formulaire.client_id">
              <option v-for="r in ROLES_COMMERCIAUX" :key="r.value" :value="r.value">
                {{ r.label }}
              </option>
            </select>
          </div>
          <div class="sm:col-span-2">
            <label class="label">Depuis le</label>
            <input v-model="formulaire.start_date" type="date" class="input"
                   :disabled="!formulaire.client_id" />
          </div>
        </div>
      </div>

      <div class="flex items-center justify-end gap-2 pt-1">
        <button type="button" class="btn-ghost" @click="$emit('ferme')">Annuler</button>
        <button type="submit" class="btn-primary" :disabled="enCours">
          {{ enCours ? 'Enregistrement…'
             : doublons.length ? 'Confirmer et créer' : 'Créer le contact' }}
        </button>
      </div>
    </form>
  </BaseModal>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useClientsStore, ROLES_COMMERCIAUX } from '../../stores/clients.js'
import BaseModal from '../ui/BaseModal.vue'
import AlertMessage from '../ui/AlertMessage.vue'

const props = defineProps({
  clients: { type: Array, default: () => [] },
  clientPrefill: { type: [Number, null], default: null },
})
const emit = defineEmits(['ferme', 'enregistre', 'rattacher'])

const store = useClientsStore()
const enCours = ref(false)
const erreur = ref('')
const doublons = ref([])

const formulaire = reactive({
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  client_id: props.clientPrefill,
  job_title: '',
  commercial_role: 'other',
  start_date: new Date().toISOString().slice(0, 10),
})

async function chercherDoublons() {
  if (!formulaire.last_name.trim()) { doublons.value = []; return }
  try {
    doublons.value = await store.chercherDoublonsPersonne({
      first_name: formulaire.first_name, last_name: formulaire.last_name,
      email: formulaire.email })
  } catch { /* la recherche est une aide, son échec ne bloque pas la saisie */ }
}

async function enregistrer() {
  enCours.value = true
  erreur.value = ''
  try {
    const corps = {
      first_name: formulaire.first_name, last_name: formulaire.last_name,
      email: formulaire.email || null, phone: formulaire.phone || null,
      confirm_duplicate: doublons.value.length > 0,
    }
    if (formulaire.client_id) {
      Object.assign(corps, {
        client_id: formulaire.client_id, job_title: formulaire.job_title,
        commercial_role: formulaire.commercial_role,
        start_date: formulaire.start_date,
      })
    }
    emit('enregistre', await store.creerPersonne(corps))
  } catch (e) {
    if (e.code === 'PERSON_DUPLICATE_SUSPECTED') {
      doublons.value = e.duplicates || []
    } else {
      erreur.value = e.message
    }
  } finally {
    enCours.value = false
  }
}
</script>
