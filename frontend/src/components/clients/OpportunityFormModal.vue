<!--
  Création et modification d'une opportunité.

  Le point sensible est le couple client/contacts. Le sélecteur ne propose que
  les personnes EN POSTE chez le client choisi, et changer de client vide la
  sélection : garder des contacts d'une autre maison produirait un refus serveur
  incompréhensible au moment d'enregistrer. Vider tôt vaut mieux qu'expliquer
  tard.

  Le serveur applique la même règle de son côté — ce filtre est un confort,
  pas la garantie.
-->
<template>
  <BaseModal :model-value="true" max-width="620px"
             :title="opportunite ? 'Modifier l’opportunité' : 'Nouvelle opportunité'"
             @close="$emit('ferme')">
    <form class="flex flex-col gap-4" @submit.prevent="enregistrer">

      <AlertMessage v-if="erreur" kind="error">{{ erreur }}</AlertMessage>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div class="sm:col-span-2">
          <label class="label">Client <span style="color: var(--negative)">*</span></label>
          <select v-model="formulaire.client_id" class="select" required
                  :disabled="!!opportunite" @change="clientChange">
            <option :value="null">— Choisir —</option>
            <option v-for="c in clients" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
          <p v-if="opportunite" class="text-xs mt-1" style="color: var(--subtle)">
            Le client d'une opportunité ouverte se change depuis sa fiche, avec
            une nouvelle sélection de contacts.
          </p>
        </div>

        <div class="sm:col-span-2">
          <label class="label">Intitulé</label>
          <input v-model="formulaire.title" class="input"
                 placeholder="Ex : Phoenix worst-of 3Y, coupon mémoire" />
        </div>

        <div class="sm:col-span-2">
          <label class="label">Mandat / périmètre</label>
          <select v-model="formulaire.mandate_id" class="select"
                  :disabled="!formulaire.client_id">
            <option :value="null">— À qualifier —</option>
            <option v-for="m in mandatsDisponibles" :key="m.id" :value="m.id">
              {{ m.name }} · {{ libelleTypeMandat(m.mandate_type) }}
            </option>
          </select>
          <p class="text-xs mt-1" style="color: var(--subtle)">
            Facultatif au stade brouillon, obligatoire avant de lancer une RFQ Client.
          </p>
        </div>

        <div class="sm:col-span-2">
          <label class="label">Contact principal</label>
          <select v-model="formulaire.primary_affiliation_id" class="select"
                  :disabled="!formulaire.client_id">
            <option :value="null">— Aucun —</option>
            <option v-for="c in contactsDisponibles" :key="c.affiliation_id"
                    :value="c.affiliation_id">
              {{ c.first_name }} {{ c.last_name }}
              <template v-if="c.job_title"> — {{ c.job_title }}</template>
            </option>
          </select>
          <p v-if="formulaire.client_id && !contactsDisponibles.length"
             class="text-xs mt-1" style="color: var(--gold)">
            Aucun contact en poste chez ce client. Ajoutez-en un depuis sa fiche.
          </p>
        </div>

        <div v-if="autresContacts.length" class="sm:col-span-2">
          <label class="label">Autres participants</label>
          <div class="flex flex-col gap-1.5 max-h-32 overflow-y-auto rounded-[10px] p-2"
               style="background: var(--surface2); border: 1px solid var(--border)">
            <label v-for="c in autresContacts" :key="c.affiliation_id"
                   class="flex items-center gap-2 text-sm cursor-pointer">
              <input v-model="participants" type="checkbox" :value="c.affiliation_id" />
              <span>{{ c.first_name }} {{ c.last_name }}</span>
              <span class="text-xs" style="color: var(--subtle)">{{ c.job_title }}</span>
            </label>
          </div>
          <p class="text-xs mt-1" style="color: var(--subtle)">
            Une opportunité est rarement l'affaire d'une seule personne.
          </p>
        </div>

        <div>
          <label class="label">Montant envisagé</label>
          <input v-model.number="formulaire.amount" type="number" class="input"
                 placeholder="—" @focus="$event.target.select()" />
        </div>
        <div>
          <label class="label">Devise</label>
          <select v-model="formulaire.currency" class="select">
            <option v-for="d in DEVISES" :key="d" :value="d">{{ d }}</option>
          </select>
        </div>

        <div>
          <label class="label">Statut</label>
          <select v-model="formulaire.status" class="select" :disabled="!!opportunite">
            <option v-for="s in STATUTS_OUVERTS" :key="s.value" :value="s.value">
              {{ s.label }}
            </option>
          </select>
        </div>
        <div>
          <label class="label">Priorité</label>
          <select v-model="formulaire.priority" class="select">
            <option v-for="p in PRIORITES" :key="p.value" :value="p.value">
              {{ p.label }}
            </option>
          </select>
        </div>

        <div>
          <label class="label">Date de trade attendue</label>
          <input v-model="formulaire.expected_trade_date" type="date" class="input" />
        </div>
        <div>
          <label class="label">Origine</label>
          <input v-model="formulaire.source" class="input"
                 placeholder="Ex : demande entrante, roadshow" />
        </div>

        <div>
          <label class="label">Format juridique</label>
          <input v-model="formulaire.transaction_format" class="input" list="formats-transaction"
                 placeholder="EMTN, BMTN, OTC…" />
          <datalist id="formats-transaction">
            <option v-for="v in FORMATS_TRANSACTION" :key="v" :value="v" />
          </datalist>
        </div>
        <div>
          <label class="label">Instrument</label>
          <input v-model="formulaire.instrument_family" class="input" list="familles-instrument"
                 placeholder="Note, Swap…" />
          <datalist id="familles-instrument">
            <option v-for="v in FAMILLES_INSTRUMENT" :key="v" :value="v" />
          </datalist>
        </div>
        <div>
          <label class="label">Famille de payoff</label>
          <input v-model="formulaire.payoff_family" class="input" list="familles-payoff"
                 placeholder="Phoenix, Autocall…" />
          <datalist id="familles-payoff">
            <option v-for="v in FAMILLES_PAYOFF" :key="v" :value="v" />
          </datalist>
        </div>
        <div>
          <label class="label">Nature des données</label>
          <select v-model="formulaire.data_origin" class="select">
            <option v-for="v in PROVENANCES_DONNEES" :key="v.value" :value="v.value">
              {{ v.label }}
            </option>
          </select>
        </div>

        <div class="sm:col-span-2">
          <label class="label">Description du payoff</label>
          <textarea v-model="formulaire.payoff_description" class="input" rows="2"
                    placeholder="Précisions propres à ce besoin client."></textarea>
        </div>

        <div class="sm:col-span-2">
          <label class="label">Besoin exprimé</label>
          <textarea v-model="formulaire.description" class="input" rows="3"
                    placeholder="Ce que le client cherche, dans ses termes."></textarea>
        </div>
      </div>

      <div class="flex items-center justify-end gap-2 pt-1">
        <button type="button" class="btn-ghost" @click="$emit('ferme')">Annuler</button>
        <button type="submit" class="btn-primary"
                :disabled="enCours || !formulaire.client_id">
          {{ enCours ? 'Enregistrement…'
             : opportunite ? 'Enregistrer' : "Créer l'opportunité" }}
        </button>
      </div>
    </form>
  </BaseModal>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import {
  useClientsStore, STATUTS_OPPORTUNITE, PRIORITES, STATUTS_CLOS,
  FORMATS_TRANSACTION, FAMILLES_INSTRUMENT,
  FAMILLES_PAYOFF, PROVENANCES_DONNEES, libelleTypeMandat,
} from '../../stores/clients.js'
import { apiFetch } from '../../utils/api.js'
import BaseModal from '../ui/BaseModal.vue'
import AlertMessage from '../ui/AlertMessage.vue'

const DEVISES = ['EUR', 'USD', 'CHF', 'GBP', 'JPY', 'SGD']

// Un dossier ne s'ouvre pas déjà clos : les statuts terminaux se posent depuis
// la fiche, avec le motif que le serveur exige pour « perdue ».
const STATUTS_OUVERTS = STATUTS_OPPORTUNITE.filter(
  s => !STATUTS_CLOS.includes(s.value))

const props = defineProps({
  opportunite: { type: Object, default: null },
  clients: { type: Array, default: () => [] },
  clientPrefill: { type: [Number, null], default: null },
})
const emit = defineEmits(['ferme', 'enregistre'])

const store = useClientsStore()
const enCours = ref(false)
const erreur = ref('')
const participants = ref([])
const contactsDisponibles = ref([])
const mandatsDisponibles = ref([])

const formulaire = reactive({
  client_id: props.opportunite?.client_id ?? props.clientPrefill ?? null,
  primary_affiliation_id: props.opportunite?.primary_contact?.affiliation_id ?? null,
  mandate_id: props.opportunite?.mandate_id ?? null,
  title: props.opportunite?.title || '',
  description: props.opportunite?.description || '',
  amount: props.opportunite?.amount ?? null,
  currency: props.opportunite?.currency || 'EUR',
  status: props.opportunite?.status || 'lead',
  priority: props.opportunite?.priority || 'medium',
  expected_trade_date: props.opportunite?.expected_trade_date || '',
  source: props.opportunite?.source || '',
  transaction_format: props.opportunite?.transaction_format || '',
  instrument_family: props.opportunite?.instrument_family || '',
  payoff_family: props.opportunite?.payoff_family || '',
  payoff_description: props.opportunite?.payoff_description || '',
  data_origin: props.opportunite?.data_origin || 'demo',
})

const autresContacts = computed(
  () => contactsDisponibles.value.filter(
    c => c.affiliation_id !== formulaire.primary_affiliation_id))

async function chargerContacts(clientId) {
  contactsDisponibles.value = []
  if (!clientId) return
  const reponse = await apiFetch(`/api/clients/${clientId}/contacts`)
  if (reponse.ok) contactsDisponibles.value = await reponse.json()
}

async function chargerMandats(clientId) {
  mandatsDisponibles.value = []
  if (!clientId) return
  const reponse = await apiFetch(`/api/clients/${clientId}/mandates`)
  if (reponse.ok) mandatsDisponibles.value = await reponse.json()
}

function clientChange() {
  // Changer de client invalide toute sélection antérieure : conserver un
  // contact d'une autre maison produirait un refus serveur au moment
  // d'enregistrer, alors que la cause serait déjà hors de l'écran.
  formulaire.primary_affiliation_id = null
  formulaire.mandate_id = null
  participants.value = []
  chargerContacts(formulaire.client_id)
  chargerMandats(formulaire.client_id)
}

// Le contact principal ne doit jamais figurer aussi dans les participants —
// le serveur le refuse (PARTICIPANT_IS_PRIMARY), autant ne pas le proposer.
watch(() => formulaire.primary_affiliation_id, (nouveau) => {
  participants.value = participants.value.filter(id => id !== nouveau)
})

watch(() => formulaire.client_id, chargerContacts, { immediate: true })
watch(() => formulaire.client_id, chargerMandats, { immediate: true })

if (props.opportunite) {
  participants.value = (props.opportunite.participants || [])
    .map(p => p.affiliation_id).filter(Boolean)
}

async function enregistrer() {
  enCours.value = true
  erreur.value = ''
  try {
    const corps = {
      client_id: formulaire.client_id,
      primary_affiliation_id: formulaire.primary_affiliation_id,
      mandate_id: formulaire.mandate_id,
      participants: participants.value.map(id => ({ affiliation_id: id })),
      title: formulaire.title,
      description: formulaire.description || null,
      amount: formulaire.amount,
      currency: formulaire.currency,
      priority: formulaire.priority,
      expected_trade_date: formulaire.expected_trade_date || null,
      source: formulaire.source || null,
      transaction_format: formulaire.transaction_format || null,
      instrument_family: formulaire.instrument_family || null,
      payoff_family: formulaire.payoff_family || null,
      payoff_description: formulaire.payoff_description || null,
      data_origin: formulaire.data_origin,
    }
    if (props.opportunite) {
      emit('enregistre', await store.modifierOpportunite(props.opportunite.id, corps))
    } else {
      emit('enregistre',
           await store.creerOpportunite({ ...corps, status: formulaire.status }))
    }
  } catch (e) {
    erreur.value = e.message
  } finally {
    enCours.value = false
  }
}
</script>
