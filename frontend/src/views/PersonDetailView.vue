<!--
  Fiche personne — l'identité et le parcours professionnel.

  Le parcours est l'écran central de ce module. Il se lit du présent vers le
  passé : l'affiliation en cours d'abord, puis les précédentes. Chacune garde
  sa société et ses dates ; aucune ne se réécrit quand la personne bouge.

  « Changer de société » n'écrase rien : le bouton clôt l'affiliation en cours
  et en ouvre une nouvelle. Les interactions, opportunités et trades laissés
  chez l'employeur précédent y restent — c'est ce qui permettra plus tard de
  comparer ce que cette personne faisait là-bas et ce qu'elle fait ici.
-->
<template>
  <div class="min-h-screen" style="background: var(--bg)">
    <div class="max-w-5xl mx-auto px-6 py-8 flex flex-col gap-6">

      <LoadingSpinner v-if="store.chargement && !personne" />
      <AlertMessage v-else-if="!personne" kind="error">
        Cette personne est introuvable.
      </AlertMessage>

      <template v-else>
        <div class="flex flex-col gap-2">
          <BackLink class="self-start" fallback="/clients/liste" />
          <div class="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 class="font-display text-2xl font-black tracking-tight">
                {{ personne.first_name }} {{ personne.last_name }}
              </h1>
              <div class="flex items-center gap-2 mt-1.5 flex-wrap text-xs"
                   style="color: var(--muted)">
                <span v-if="personne.current_affiliation" class="badge badge-positive">
                  {{ personne.current_affiliation.client_name }}
                </span>
                <span v-else class="badge badge-muted">Sans affiliation</span>
                <span v-if="personne.current_affiliation">
                  {{ posteEtRole(personne.current_affiliation) }}
                </span>
                <span v-if="personne.email">· {{ personne.email }}</span>
                <span v-if="personne.phone">· {{ personne.phone }}</span>
                <span v-if="!personne.is_active" class="badge badge-muted">Inactif</span>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button class="btn-primary" @click="modaleChangement = true">
                Changer de société
              </button>
              <button v-if="personne.is_active" class="btn-ghost" @click="desactiver">
                Désactiver
              </button>
              <button v-else class="btn-secondary" @click="reactiver">Réactiver</button>
            </div>
          </div>
        </div>

        <AlertMessage v-if="messageErreur" kind="error" dismissible
                      @dismiss="messageErreur = ''">{{ messageErreur }}</AlertMessage>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">

          <!-- Parcours -->
          <div class="lg:col-span-2 card flex flex-col gap-4">
            <div class="card-title mb-0">Parcours professionnel</div>

            <EmptyState v-if="!personne.affiliations?.length" icon="🏛"
                        title="Aucune affiliation"
                        hint="Rattachez cette personne à une société pour commencer à suivre son activité." />

            <ol v-else class="flex flex-col">
              <li v-for="(affiliation, index) in parcours" :key="affiliation.id"
                  class="relative pl-6 pb-5 last:pb-0">
                <!-- Filet vertical de la frise, coupé sur le dernier élément -->
                <span v-if="index < parcours.length - 1"
                      class="absolute left-[5px] top-4 bottom-0 w-px"
                      style="background: var(--border)"></span>
                <span class="absolute left-0 top-1.5 w-[11px] h-[11px] rounded-full"
                      :style="affiliation.is_current
                        ? 'background: var(--positive)'
                        : 'background: var(--border)'"></span>

                <div class="flex items-start justify-between gap-3">
                  <div>
                    <div class="text-sm font-semibold">
                      {{ affiliation.client_name }}
                      <span v-if="affiliation.is_current"
                            class="badge badge-positive ml-1.5">En poste</span>
                    </div>
                    <div class="text-xs" style="color: var(--muted)">
                      {{ posteEtRole(affiliation) }}
                    </div>
                    <div class="text-xs mt-0.5" style="color: var(--subtle)">
                      {{ formaterDate(affiliation.start_date) }}
                      →
                      {{ affiliation.end_date
                         ? formaterDate(affiliation.end_date) : "aujourd'hui" }}
                    </div>
                  </div>
                  <div class="flex items-center gap-1.5 shrink-0">
                    <button class="btn-ghost btn-sm"
                            @click="$router.push(`/clients/fiche/${affiliation.client_id}`)">
                      Société →
                    </button>
                    <button v-if="affiliation.is_current" class="btn-ghost btn-sm"
                            @click="cloturer(affiliation)">
                      Clôturer
                    </button>
                  </div>
                </div>
              </li>
            </ol>
          </div>

          <!-- Ce que porte la fiche -->
          <div class="flex flex-col gap-5">
            <div class="card flex flex-col gap-3">
              <div class="card-title mb-0">Historique</div>
              <div class="flex flex-col gap-2 text-sm">
                <div class="flex items-center justify-between">
                  <span style="color: var(--muted)">Affiliations</span>
                  <span class="font-semibold tabular-nums">
                    {{ personne.history?.affiliations ?? 0 }}
                  </span>
                </div>
                <div class="flex items-center justify-between">
                  <span style="color: var(--muted)">Opportunités</span>
                  <span class="font-semibold tabular-nums">
                    {{ personne.history?.opportunities ?? 0 }}
                  </span>
                </div>
                <div class="flex items-center justify-between">
                  <span style="color: var(--muted)">Trades</span>
                  <span class="font-semibold tabular-nums">
                    {{ personne.history?.deals ?? 0 }}
                  </span>
                </div>
              </div>
              <p class="text-xs" style="color: var(--subtle)">
                Le comportement observé et la cadence d'investissement arrivent
                avec le moteur de cycles.
              </p>
            </div>

            <div class="card flex flex-col gap-3">
              <div class="card-title mb-0">Interactions</div>
              <EmptyState v-if="!interactions.length" icon="🗒"
                          title="Aucune interaction" />
              <ul v-else class="flex flex-col divide-y" style="border-color: var(--border)">
                <li v-for="item in interactions" :key="item.id" class="py-2">
                  <div class="text-sm truncate">{{ item.summary || '(sans résumé)' }}</div>
                  <div class="text-xs" style="color: var(--muted)">
                    {{ item.client_name }} · {{ formaterDate(item.interaction_date) }}
                  </div>
                </li>
              </ul>
            </div>

            <div v-if="personne.notes" class="card flex flex-col gap-2">
              <div class="card-title mb-0">Notes</div>
              <p class="text-sm whitespace-pre-line" style="color: var(--muted)">
                {{ personne.notes }}
              </p>
            </div>
          </div>
        </div>

        <!-- Cadence — pleine largeur.
             Elle vivait dans la colonne d'un tiers, où ses quatre tuiles se
             réduisaient à « Intervalle médian » sur trois lignes et
             « Dispersio » tronqué. Un chiffre illisible ne vaut pas mieux
             qu'un chiffre absent : ce panneau a besoin de la largeur. -->
        <div v-if="intelligence" class="card flex flex-col gap-4">
          <div class="flex items-center justify-between gap-3 flex-wrap">
            <div class="card-title mb-0">Cadence</div>
            <nav class="tabs">
              <button v-for="n in NIVEAUX" :key="n.cle" class="tab-btn"
                      :class="{ active: niveau === n.cle }" @click="niveau = n.cle">
                {{ n.libelle }}
              </button>
            </nav>
          </div>
          <p class="text-xs" style="color: var(--muted)">{{ aideNiveau }}</p>
          <CyclePanel :cycle="intelligence.cycles[niveau]"
                      :contact-window="niveau === 'current_affiliation'
                                       ? intelligence.contact_window : null" />

          <div v-if="intelligence.comparison?.comparable"
               class="rounded-[10px] p-3" style="background: var(--surface2);
                      border: 1px solid var(--border)">
            <div class="text-xs font-semibold uppercase tracking-wider mb-1"
                 style="color: var(--muted)">Lecture comparée</div>
            <ul class="flex flex-col gap-0.5">
              <li v-for="(ligne, i) in intelligence.comparison.explanation" :key="i"
                  class="text-xs" style="color: var(--muted)">{{ ligne }}</li>
            </ul>
          </div>
        </div>
      </template>
    </div>

    <ChangeCompanyModal v-if="modaleChangement" :personne="personne"
                        :clients="store.clientsActifs"
                        @ferme="modaleChangement = false"
                        @enregistre="apresChangement" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useClientsStore, libelleRole } from '../stores/clients.js'
import { confirmer } from '../composables/useConfirm.js'
import AlertMessage from '../components/ui/AlertMessage.vue'
import BackLink from '../components/ui/BackLink.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import ChangeCompanyModal from '../components/clients/ChangeCompanyModal.vue'
import CyclePanel from '../components/clients/CyclePanel.vue'
import { formatDate } from '../utils/format.js'

// Les trois lectures d'une même personne. L'onglet n'est pas cosmétique : les
// fondre donnerait une cadence qui ne décrit aucune des deux périodes.
const NIVEAUX = [
  { cle: 'personal', libelle: 'Tout son parcours' },
  { cle: 'current_affiliation', libelle: 'Poste actuel' },
  { cle: 'organization', libelle: 'La maison' },
]
const AIDE_NIVEAU = {
  personal: "Toutes ses transactions, toutes sociétés confondues — ce qu'elle fait, où qu'elle soit.",
  current_affiliation: "Ce qu'elle fait depuis qu'elle est dans cette maison.",
  organization: 'Les autres contacts de cette société, elle exclue — sinon on se comparerait en partie à soi-même.',
}

const route = useRoute()
const store = useClientsStore()

const modaleChangement = ref(false)
const messageErreur = ref('')
const interactions = ref([])
const intelligence = ref(null)
const niveau = ref('current_affiliation')
const aideNiveau = computed(() => AIDE_NIVEAU[niveau.value])

const personne = computed(() => store.personneCourante)

// Du présent vers le passé : l'affiliation en cours d'abord, puis les autres
// de la plus récente à la plus ancienne. C'est l'ordre dans lequel on lit une
// fiche — « où est-il aujourd'hui, et d'où vient-il ».
const parcours = computed(() => {
  const liste = [...(personne.value?.affiliations || [])]
  return liste.sort((a, b) => {
    if (a.is_current !== b.is_current) return a.is_current ? -1 : 1
    return String(b.start_date || '').localeCompare(String(a.start_date || ''))
  })
})

/**
 * Poste et rôle, sans redite : `job_title` est libre (« Gérant ») et le libellé
 * français de `commercial_role` est parfois le même mot. Les afficher tous deux
 * donnait « Gérant · Gérant ».
 */
function posteEtRole(affiliation) {
  const poste = (affiliation.job_title || '').trim()
  const role = libelleRole(affiliation.commercial_role)
  if (!poste) return role
  if (poste.toLowerCase() === role.toLowerCase()) return poste
  return `${poste} · ${role}`
}

// Delegue a utils/format.js : separateur de milliers normalise, date lue
// en calendrier local. Un formateur local re-introduirait l'espace fine
// insecable d'Intl, invisible a l'ecran.
const formaterDate = formatDate

async function charger() {
  await store.chargerPersonne(Number(route.params.id))
  await store.chargerClients()
  interactions.value = await store.chargerInteractions({
    person_id: route.params.id, limit: 10 })
  try {
    intelligence.value = await store.lireIntelligencePersonne(
      Number(route.params.id))
  } catch {
    // L'analyse enrichit la fiche, elle ne la conditionne pas : son échec ne
    // doit pas masquer le parcours professionnel, qui est l'essentiel ici.
    intelligence.value = null
  }
}

async function cloturer(affiliation) {
  const aujourdhui = new Date().toISOString().slice(0, 10)
  if (!await confirmer({
    titre: `Clôturer le passage chez ${affiliation.client_name} ?`,
    message: "La date de fin sera posée à aujourd'hui. Tout ce qui a été fait "
           + 'dans cette société y reste rattaché — rien ne sera déplacé.',
    confirmer: 'Clôturer' })) return
  try {
    await store.cloturerAffiliation(personne.value.id, affiliation.id, aujourdhui)
    await charger()
  } catch (e) { messageErreur.value = e.message }
}

async function desactiver() {
  try { await store.desactiverPersonne(personne.value.id) }
  catch (e) { messageErreur.value = e.message }
}

async function reactiver() {
  try { await store.reactiverPersonne(personne.value.id) }
  catch (e) { messageErreur.value = e.message }
}

async function apresChangement() {
  modaleChangement.value = false
  await charger()
}

onMounted(charger)
watch(() => route.params.id, charger)
</script>
