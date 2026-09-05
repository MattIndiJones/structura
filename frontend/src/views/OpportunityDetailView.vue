<!--
  Fiche opportunité — le maillon entre le client et l'appel d'offres.

  Deux points valent d'être expliqués.

  **« Perdue » exige un motif.** Le formulaire de clôture ne laisse pas passer
  sans raison : c'est la matière première de tout ce qui suivra. Savoir qu'un
  client refuse a peu de valeur ; savoir qu'il refuse pour un coupon trop faible
  en a beaucoup.

  **Le bouton « Créer un appel d'offres » ne duplique pas le module RFQ** — il
  ouvre le Pricer avec le contexte, et le lien se pose à la création. Refaire un
  écran de RFQ ici aurait été le meilleur moyen d'en avoir deux qui divergent.
-->
<template>
  <div class="min-h-screen" style="background: var(--bg)">
    <div class="max-w-5xl mx-auto px-6 py-8 flex flex-col gap-6">

      <LoadingSpinner v-if="!opportunite && chargement" />
      <AlertMessage v-else-if="!opportunite" kind="error">
        Cette opportunité est introuvable.
      </AlertMessage>

      <template v-else>
        <div class="flex flex-col gap-2">
          <BackLink class="self-start" fallback="/clients/liste" />
          <div class="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div class="text-xs font-mono" style="color: var(--subtle)">
                {{ opportunite.reference }}
              </div>
              <h1 class="font-display text-2xl font-black tracking-tight">
                {{ opportunite.title || '(sans intitulé)' }}
              </h1>
              <div class="flex items-center gap-2 mt-1.5 flex-wrap text-xs">
                <span class="badge" :class="classeStatut(opportunite.status)">
                  {{ libelleStatutOpportunite(opportunite.status) }}
                </span>
                <RouterLink :to="`/clients/fiche/${opportunite.client_id}`"
                            class="font-semibold hover:underline">
                  {{ opportunite.client_name }}
                </RouterLink>
                <span style="color: var(--muted)">
                  · Priorité {{ libellePriorite(opportunite.priority).toLowerCase() }}
                </span>
                <span v-if="opportunite.amount" style="color: var(--muted)">
                  · {{ montant(opportunite.amount) }} {{ opportunite.currency }}
                </span>
              </div>
            </div>
            <div class="flex items-center gap-2 flex-wrap">
              <button v-if="!estClos" class="btn-secondary"
                      @click="modaleEdition = true">Modifier</button>
              <button v-if="!estClos" class="btn-primary" @click="creerAppelOffres">
                Créer un appel d'offres
              </button>
              <button v-if="!estClos" class="btn-secondary"
                      @click="changerStatut('won')">Marquer gagnée</button>
              <button v-if="!estClos" class="btn-ghost"
                      @click="modalePerte = true">Marquer perdue</button>
            </div>
          </div>
        </div>

        <AlertMessage v-if="messageErreur" kind="error" dismissible
                      @dismiss="messageErreur = ''">{{ messageErreur }}</AlertMessage>

        <AlertMessage v-if="opportunite.status === 'lost'" kind="warning">
          <span class="font-semibold">Perdue —
            {{ libelleRaisonPerte(opportunite.lost_reason) }}</span>
          <span v-if="opportunite.lost_comment"> · {{ opportunite.lost_comment }}</span>
        </AlertMessage>

        <AlertMessage v-if="contactPartiDepuis" kind="info">
          {{ contactPartiDepuis }} a quitté {{ opportunite.client_name }} depuis
          l'ouverture de ce dossier. L'opportunité reste rattachée à cette
          société — continuez avec un autre contact de la maison, ou clôturez-la
          et ouvrez-en une nouvelle chez son nouvel employeur.
        </AlertMessage>

        <AlertMessage v-if="!estClos && !opportunite.mandate_id" kind="warning">
          Mandat ou périmètre à qualifier avant de lancer une RFQ Client.
          L'Opportunity peut rester en brouillon dans cet état.
        </AlertMessage>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div class="lg:col-span-2 flex flex-col gap-5">

            <div v-if="opportunite.description" class="card flex flex-col gap-2">
              <div class="card-title mb-0">Besoin exprimé</div>
              <p class="text-sm whitespace-pre-line" style="color: var(--muted)">
                {{ opportunite.description }}
              </p>
            </div>

            <!-- Appels d'offres -->
            <div class="card flex flex-col gap-3">
              <div class="card-title mb-0">Appels d'offres</div>
              <EmptyState v-if="!opportunite.rfqs?.length" icon="📨"
                          title="Aucun appel d'offres"
                          hint="Quand le besoin est assez précis, lancez une consultation des banques depuis cette fiche." />
              <ul v-else class="flex flex-col divide-y" style="border-color: var(--border)">
                <li v-for="rfq in opportunite.rfqs" :key="rfq.id"
                    class="py-2.5 flex items-center justify-between gap-3">
                  <div class="min-w-0">
                    <div class="text-sm font-semibold truncate">{{ rfq.name }}</div>
                    <div class="text-xs font-mono" style="color: var(--subtle)">
                      {{ rfq.reference }}
                    </div>
                  </div>
                  <div class="flex items-center gap-2 shrink-0">
                    <span class="badge badge-muted">{{ rfq.status }}</span>
                    <RouterLink to="/rfq" class="btn-ghost btn-sm">Ouvrir →</RouterLink>
                  </div>
                </li>
              </ul>
            </div>

            <!-- Trades -->
            <div v-if="opportunite.deals?.length" class="card flex flex-col gap-3">
              <div class="card-title mb-0">Trades</div>
              <ul class="flex flex-col divide-y" style="border-color: var(--border)">
                <li v-for="deal in opportunite.deals" :key="deal.id"
                    class="py-2.5 flex items-center justify-between gap-3">
                  <span class="text-sm font-mono">{{ deal.reference }}</span>
                  <span class="text-sm tabular-nums">
                    {{ montant(deal.nominal) }} {{ deal.devise }}
                  </span>
                </li>
              </ul>
            </div>

            <!-- Interactions -->
            <div class="card flex flex-col gap-3">
              <div class="flex items-center justify-between gap-3">
                <div class="card-title mb-0">Suivi</div>
                <button class="btn-secondary btn-sm" @click="modaleInteraction = true">
                  + Enregistrer
                </button>
              </div>
              <EmptyState v-if="!opportunite.interactions?.length" icon="🗒"
                          title="Aucun échange enregistré" />
              <ul v-else class="flex flex-col divide-y" style="border-color: var(--border)">
                <li v-for="item in opportunite.interactions" :key="item.id"
                    class="py-2.5 flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="text-sm">{{ item.summary || '(sans résumé)' }}</div>
                    <div class="text-xs" style="color: var(--muted)">
                      {{ libelleTypeInteraction(item.interaction_type) }}
                    </div>
                  </div>
                  <span class="text-xs tabular-nums shrink-0" style="color: var(--subtle)">
                    {{ formaterDate(item.interaction_date) }}
                  </span>
                </li>
              </ul>
            </div>
          </div>

          <!-- Colonne de droite -->
          <div class="flex flex-col gap-5">
            <div class="card flex flex-col gap-2">
              <div class="card-title mb-0">Cadre Client et produit</div>
              <div class="flex items-center justify-between text-sm gap-3">
                <span style="color: var(--muted)">Mandat</span>
                <span class="text-right">{{ opportunite.mandate?.name || 'À qualifier' }}</span>
              </div>
              <div class="flex items-center justify-between text-sm gap-3">
                <span style="color: var(--muted)">Format</span>
                <span>{{ opportunite.transaction_format || '—' }}</span>
              </div>
              <div class="flex items-center justify-between text-sm gap-3">
                <span style="color: var(--muted)">Instrument</span>
                <span>{{ opportunite.instrument_family || '—' }}</span>
              </div>
              <div class="flex items-center justify-between text-sm gap-3">
                <span style="color: var(--muted)">Payoff</span>
                <span>{{ opportunite.payoff_family || '—' }}</span>
              </div>
              <p v-if="opportunite.payoff_description" class="text-xs whitespace-pre-line"
                 style="color: var(--muted)">{{ opportunite.payoff_description }}</p>
              <span class="badge badge-muted self-start">
                {{ libelleProvenance(opportunite.data_origin) }}
              </span>
            </div>

            <div class="card flex flex-col gap-3">
              <div class="card-title mb-0">Interlocuteurs</div>
              <div v-if="opportunite.primary_contact">
                <div class="text-xs font-semibold uppercase tracking-wider"
                     style="color: var(--muted)">Contact principal</div>
                <RouterLink :to="`/clients/contacts/${opportunite.primary_contact.person_id}`"
                            class="text-sm font-semibold hover:underline">
                  {{ opportunite.primary_contact.name }}
                </RouterLink>
                <div class="text-xs" style="color: var(--subtle)">
                  {{ opportunite.primary_contact.job_title || '—' }}
                  <span v-if="!opportunite.primary_contact.still_current"
                        class="badge badge-gold ml-1">A quitté la société</span>
                </div>
              </div>
              <EmptyState v-else icon="👤" title="Aucun contact principal" />

              <div v-if="opportunite.participants?.length" class="pt-2"
                   style="border-top: 1px solid var(--border)">
                <div class="text-xs font-semibold uppercase tracking-wider mb-1.5"
                     style="color: var(--muted)">Participants</div>
                <ul class="flex flex-col gap-1">
                  <li v-for="p in opportunite.participants" :key="p.affiliation_id"
                      class="text-sm">
                    {{ p.name }}
                    <span class="text-xs" style="color: var(--subtle)">
                      {{ p.job_title }}
                    </span>
                  </li>
                </ul>
              </div>
            </div>

            <div class="card flex flex-col gap-2">
              <div class="card-title mb-0">Calendrier</div>
              <div class="flex items-center justify-between text-sm">
                <span style="color: var(--muted)">Trade attendu</span>
                <span class="tabular-nums">
                  {{ formaterDate(opportunite.expected_trade_date) }}
                </span>
              </div>
              <div class="flex items-center justify-between text-sm">
                <span style="color: var(--muted)">Dernière activité</span>
                <span class="tabular-nums">
                  {{ formaterDateHeure(opportunite.last_activity_at) }}
                </span>
              </div>
              <div v-if="opportunite.source" class="flex items-center justify-between text-sm">
                <span style="color: var(--muted)">Origine</span>
                <span>{{ opportunite.source }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <OpportunityFormModal v-if="modaleEdition" :opportunite="opportunite"
                          :clients="store.clientsActifs"
                          @ferme="modaleEdition = false"
                          @enregistre="apresEdition" />
    <InteractionFormModal v-if="modaleInteraction && opportunite"
                          :client="{ id: opportunite.client_id, name: opportunite.client_name }"
                          :contacts="contactsDuClient"
                          :opportunity-id="opportunite.id"
                          @ferme="modaleInteraction = false"
                          @enregistre="apresInteraction" />
    <LostReasonModal v-if="modalePerte" @ferme="modalePerte = false"
                     @confirme="marquerPerdue" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import {
  useClientsStore, STATUTS_CLOS, libelleStatutOpportunite, libellePriorite,
  libelleRaisonPerte, libelleTypeInteraction, libelleProvenance,
} from '../stores/clients.js'
import { apiFetch } from '../utils/api.js'
import AlertMessage from '../components/ui/AlertMessage.vue'
import BackLink from '../components/ui/BackLink.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import OpportunityFormModal from '../components/clients/OpportunityFormModal.vue'
import InteractionFormModal from '../components/clients/InteractionFormModal.vue'
import LostReasonModal from '../components/clients/LostReasonModal.vue'
import { formatDate, formatInt } from '../utils/format.js'

const route = useRoute()
const router = useRouter()
const store = useClientsStore()

const chargement = ref(true)
const messageErreur = ref('')
const modaleEdition = ref(false)
const modaleInteraction = ref(false)
const modalePerte = ref(false)
const contactsDuClient = ref([])

const opportunite = computed(() => store.opportuniteCourante)
const estClos = computed(
  () => STATUTS_CLOS.includes(opportunite.value?.status))

// Le cas §30 : le contact a changé d'employeur pendant que le dossier était
// ouvert. L'opportunité ne bouge pas — mais il faut le dire, sinon on
// continue d'appeler quelqu'un qui n'y travaille plus.
const contactPartiDepuis = computed(() => {
  const contact = opportunite.value?.primary_contact
  if (!contact || contact.still_current || estClos.value) return null
  return contact.name
})

function classeStatut(statut) {
  if (statut === 'won' || statut === 'partially_won') return 'badge-positive'
  if (statut === 'lost') return 'badge-negative'
  if (STATUTS_CLOS.includes(statut)) return 'badge-muted'
  return 'badge-accent'
}

const montant = formatInt

// Delegue a utils/format.js : separateur de milliers normalise, date lue
// en calendrier local. Un formateur local re-introduirait l'espace fine
// insecable d'Intl, invisible a l'ecran.
const formaterDate = formatDate

function formaterDateHeure(iso) {
  return iso ? formaterDate(iso) : '—'
}

async function charger() {
  chargement.value = true
  try {
    const fiche = await store.chargerOpportunite(Number(route.params.id))
    await store.chargerClients()
    const reponse = await apiFetch(`/api/clients/${fiche.client_id}/contacts`)
    if (reponse.ok) contactsDuClient.value = await reponse.json()
  } catch (e) {
    messageErreur.value = e.message
  } finally {
    chargement.value = false
  }
}

async function changerStatut(statut) {
  try { await store.changerStatut(opportunite.value.id, statut) }
  catch (e) { messageErreur.value = e.message }
}

async function marquerPerdue({ raison, commentaire }) {
  modalePerte.value = false
  try {
    await store.changerStatut(opportunite.value.id, 'lost', raison, commentaire)
  } catch (e) { messageErreur.value = e.message }
}

/**
 * Ouvre l'écran d'appel d'offres avec le contexte de cette opportunité.
 *
 * On ne refait pas un écran de RFQ ici : le module existe, il est éprouvé, et
 * en avoir deux garantit qu'ils divergeront. Le contexte passe par l'URL, et
 * `RfqView` le joint à la création — c'est là que le lien se pose réellement.
 */
function creerAppelOffres() {
  if (!opportunite.value.mandate_id) {
    messageErreur.value = 'Renseignez un mandat ou périmètre actif avant de lancer la RFQ.'
    modaleEdition.value = true
    return
  }
  if (!(opportunite.value.title || '').trim()
      && !(opportunite.value.description || '').trim()) {
    messageErreur.value = 'Décrivez le besoin Client avant de lancer la RFQ.'
    modaleEdition.value = true
    return
  }
  router.push({ path: '/rfq', query: { opportunity: opportunite.value.id } })
}

async function apresEdition() {
  modaleEdition.value = false
  await charger()
}

async function apresInteraction() {
  modaleInteraction.value = false
  await charger()
}

onMounted(charger)
watch(() => route.params.id, charger)
</script>
