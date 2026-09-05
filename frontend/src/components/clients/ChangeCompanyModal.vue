<!--
  Changement de société.

  L'écran dit explicitement ce qui va se passer, parce que le geste ressemble à
  une modification alors que c'en est deux : la période actuelle se ferme, une
  nouvelle s'ouvre. La formulation compte — « changer l'employeur » ferait
  croire qu'on corrige un champ, et cacherait que tout l'historique laissé
  derrière reste chez la société précédente.
-->
<template>
  <BaseModal :model-value="true" max-width="520px"
             title="Changer de société" @close="$emit('ferme')">
    <form class="flex flex-col gap-4" @submit.prevent="enregistrer">

      <AlertMessage v-if="erreur" kind="error">{{ erreur }}</AlertMessage>

      <div v-if="affiliationActuelle" class="rounded-[10px] p-3 text-sm"
           style="background: var(--surface2); border: 1px solid var(--border)">
        <div class="text-xs font-semibold uppercase tracking-wider mb-1"
             style="color: var(--muted)">Situation actuelle</div>
        <div>
          <span class="font-semibold">{{ affiliationActuelle.client_name }}</span>
          — {{ affiliationActuelle.job_title || 'poste non précisé' }},
          depuis le {{ formaterDate(affiliationActuelle.start_date) }}
        </div>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div class="sm:col-span-2">
          <label class="label">
            Nouvelle société <span style="color: var(--negative)">*</span>
          </label>
          <select v-model="formulaire.new_client_id" class="select" required>
            <option :value="null">— Choisir —</option>
            <option v-for="c in clientsPossibles" :key="c.id" :value="c.id">
              {{ c.name }}
            </option>
          </select>
        </div>

        <div>
          <label class="label">Date de prise de poste</label>
          <input v-model="formulaire.start_date" type="date" class="input" required />
        </div>

        <div>
          <label class="label">Fin du poste précédent</label>
          <input v-model="formulaire.end_date_previous" type="date" class="input"
                 :disabled="!affiliationActuelle" />
          <p class="text-xs mt-1" style="color: var(--subtle)">
            Par défaut, la date de prise de poste.
          </p>
        </div>

        <div>
          <label class="label">Nouvelle fonction</label>
          <input v-model="formulaire.job_title" class="input" placeholder="Ex : CIO" />
        </div>

        <div>
          <label class="label">Rôle commercial</label>
          <select v-model="formulaire.commercial_role" class="select">
            <option v-for="r in ROLES_COMMERCIAUX" :key="r.value" :value="r.value">
              {{ r.label }}
            </option>
          </select>
        </div>
      </div>

      <AlertMessage kind="info">
        <div class="text-xs">
          Le passage chez
          <span class="font-semibold">{{ affiliationActuelle?.client_name || 'la société actuelle' }}</span>
          sera clôturé, et un nouveau s'ouvrira. Les interactions, opportunités
          et trades enregistrés jusqu'ici <span class="font-semibold">restent
          rattachés à la société précédente</span> et ne suivront pas.
        </div>
      </AlertMessage>

      <div class="flex items-center justify-end gap-2 pt-1">
        <button type="button" class="btn-ghost" @click="$emit('ferme')">Annuler</button>
        <button type="submit" class="btn-primary"
                :disabled="enCours || !formulaire.new_client_id">
          {{ enCours ? 'Enregistrement…' : 'Enregistrer le changement' }}
        </button>
      </div>
    </form>
  </BaseModal>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useClientsStore, ROLES_COMMERCIAUX } from '../../stores/clients.js'
import BaseModal from '../ui/BaseModal.vue'
import AlertMessage from '../ui/AlertMessage.vue'
import { formatDate } from '../../utils/format.js'

const props = defineProps({
  personne: { type: Object, required: true },
  clients: { type: Array, default: () => [] },
})
const emit = defineEmits(['ferme', 'enregistre'])

const store = useClientsStore()
const enCours = ref(false)
const erreur = ref('')

const affiliationActuelle = computed(() => props.personne.current_affiliation)

// La société actuelle ne se propose pas : y « changer » n'a pas de sens, et le
// serveur le refuse de toute façon (AFFILIATION_SAME_CLIENT).
const clientsPossibles = computed(
  () => props.clients.filter(c => c.id !== affiliationActuelle.value?.client_id))

const formulaire = reactive({
  new_client_id: null,
  start_date: new Date().toISOString().slice(0, 10),
  end_date_previous: '',
  job_title: '',
  commercial_role: 'other',
})

// Delegue a utils/format.js : separateur de milliers normalise, date lue
// en calendrier local. Un formateur local re-introduirait l'espace fine
// insecable d'Intl, invisible a l'ecran.
const formaterDate = formatDate

async function enregistrer() {
  enCours.value = true
  erreur.value = ''
  try {
    const modifiee = await store.changerSociete(props.personne.id, {
      new_client_id: formulaire.new_client_id,
      start_date: formulaire.start_date,
      end_date_previous: formulaire.end_date_previous || null,
      job_title: formulaire.job_title,
      commercial_role: formulaire.commercial_role,
    })
    emit('enregistre', modifiee)
  } catch (e) {
    erreur.value = e.message
  } finally {
    enCours.value = false
  }
}
</script>
