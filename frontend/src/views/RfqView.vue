<template>
  <div class="flex-1 flex flex-col min-h-0 overflow-hidden">

    <div class="page-header px-4 sm:px-6 pt-4 pb-3 mb-0 shrink-0 flex-wrap gap-2">
      <div class="flex items-center gap-3">
        <BackLink :fallback="{ path: '/', query: { category: 'competitive_bidding' } }" />
        <h1 class="page-title">RFQ Fournisseurs</h1>
      </div>
      <div class="page-actions flex-wrap">
        <button class="btn-ghost btn-sm md:hidden" @click="mobilePanel = mobilePanel === 'list' ? 'detail' : 'list'">{{ mobilePanel === 'list' ? 'Dossier' : 'Liste des RFQ' }}</button>
        <RouterLink to="/rfq/prototype-reseau" class="btn-ghost btn-sm">Parcours réseau · prototype</RouterLink>
        <RouterLink to="/rfq/recues" class="btn-secondary btn-sm">RFQ reçues</RouterLink>
        <RouterLink to="/rfq/analyse" class="btn-ghost btn-sm">📈 Analyse</RouterLink>
        <button class="btn-primary text-xs px-3 py-1.5" @click="openCreateForm">+ Nouvelle RFQ</button>
      </div>
    </div>
    <!-- Contexte commercial, quand on arrive depuis une fiche d'opportunité.
         L'appel d'offres créé ici portera le lien, ce qui permettra plus tard
         de remonter du trade jusqu'au client et à la personne qui l'a porté. -->
    <AlertMessage v-if="opportuniteContexte" kind="info" class="mx-6 mt-3">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <span>
          Appel d'offres pour
          <span class="font-semibold">{{ opportuniteContexte.title || opportuniteContexte.reference }}</span>
          — {{ opportuniteContexte.client_name }}
          <template v-if="opportuniteContexte.mandate?.name">
            · {{ opportuniteContexte.mandate.name }}
          </template>.
          La RFQ créée restera rattachée à cette opportunité.
        </span>
        <RouterLink :to="`/clients/opportunites/${opportuniteContexte.id}`"
                    class="btn-ghost btn-sm shrink-0">Revenir au dossier</RouterLink>
      </div>
    </AlertMessage>
    <AlertMessage v-if="listError" kind="error" dismissible class="mx-6 mt-3" @dismiss="listError = ''">{{ listError }}</AlertMessage>
    <AlertMessage v-if="notice" kind="success" dismissible class="mx-6 mt-3" @dismiss="notice = ''">{{ notice }}</AlertMessage>

    <div class="flex flex-1 min-h-0">

      <!-- ── Liste RFQ ──────────────────────────────────────────── -->
      <aside :class="['w-full md:w-64 lg:w-80 min-h-0 shrink-0 border-r border-slate-800 overflow-y-auto overscroll-contain p-3 flex-col gap-2', mobilePanel === 'list' ? 'flex' : 'hidden md:flex']">
        <LoadingSpinner v-if="loadingList" class="py-4" />
        <EmptyState v-else-if="!rfq.list.length" icon="📨" title="Aucune RFQ pour l'instant" />
        <template v-else>
          <DataFilterBar :fields="rfqFilterFields" :state="rfqFilter.state"
                         :field-options="rfqFilter.fieldOptions.value"
                         :has-active-filters="rfqFilter.hasActiveFilters.value"
                         :sorts="rfqSorts" :sort-by="rfqFilter.sortBy.value"
                         :sort-dir="rfqFilter.sortDir.value"
                         :count="filteredRfqs.length" :total="rfq.list.length" noun="AO"
                         class="p-2 gap-2"
                         @update:sort-by="rfqFilter.sortBy.value = $event"
                         @toggle-dir="rfqFilter.toggleSortDir()" @reset="rfqFilter.reset()" />
          <div v-if="!filteredRfqs.length" class="text-xs text-slate-600 px-1 py-3">
            Aucun AO ne correspond à ces filtres.
          </div>
        </template>
        <div v-for="r in filteredRfqs" :key="r.id"
             :class="['card p-3 flex flex-col gap-1.5 cursor-pointer transition-all duration-200 hover:shadow-lg hover:shadow-black/20',
                      selectedId === r.id ? 'border-blue-600 shadow-lg shadow-blue-950/30' : 'hover:border-slate-700']"
             @click="selectRfq(r.id)">
          <div class="flex items-start justify-between gap-2">
            <span class="font-semibold text-slate-200 text-sm truncate">{{ r.name || r.reference }}</span>
            <div class="flex items-center gap-1.5 shrink-0">
              <span :class="['text-[9px] rounded px-1.5 py-0.5 border', sensBadge(r.sens)]" :title="sensHint(r.sens)">{{ sensLabel(r.sens) }}</span>
              <span :class="['text-[9px] rounded px-1.5 py-0.5 border', kindBadge(r.kind)]">{{ kindLabel(r.kind) }}</span>
              <span :class="['text-[9px] rounded px-1.5 py-0.5 border', statusBadge(r.status)]">{{ statusLabel(r.status) }}</span>
              <button v-if="can(r, 'organize')" class="icon-btn-danger" title="Supprimer" aria-label="Supprimer la RFQ" @click.stop="deleteRfq(r.id)">🗑</button>
            </div>
          </div>
          <div class="text-[10px] text-slate-600 font-mono">{{ r.reference }} · AO {{ fmtDateOnly(r.ao_date) }}</div>
          <div class="flex items-center gap-3 text-[10px] text-slate-500 mt-1">
            <span v-if="r.model_price !== null">Modèle: <SensitiveValue>{{ fmtPrice(r.model_price) }}</SensitiveValue></span>
            <span v-else class="text-slate-700">Modèle: —</span>
          </div>
        </div>
      </aside>

      <!-- ── Panneau principal ──────────────────────────────────── -->
      <main :class="['flex-1 min-h-0 min-w-0 overflow-y-auto overscroll-contain p-4 sm:p-6', mobilePanel === 'list' ? 'hidden md:block' : '']">

        <!-- Formulaire de création -->
        <div v-if="showCreateForm" class="flex flex-col gap-4 max-w-2xl xl:max-w-[1500px]">
          <!-- Le titre ET les actions dans un bandeau collé en haut.
               Choisir un template ajoute les termes du produit et le calendrier
               CONSTAT — près de 400 px — et le bouton « Créer » descendait
               d'autant, sous le curseur de qui venait de choisir. Placé en bas,
               même collant, il bougeait encore entre un formulaire court et un
               formulaire long. En haut, il ne dépend plus du contenu du tout —
               c'est déjà où le Pricer met son action principale. -->
          <div class="sticky top-0 z-20 -mx-6 -mt-6 px-6 py-3 mb-1 flex items-center gap-3 flex-wrap border-b"
               style="background: rgba(250,249,246,.94); backdrop-filter: blur(10px);
                      border-color: var(--border); box-shadow: 0 4px 14px rgba(11,26,49,.04);">
            <h2 class="text-sm font-bold text-slate-300 uppercase tracking-wider">Nouvelle RFQ</h2>
            <span v-if="champsManquants.length" class="text-[11px] text-amber-600">
              À compléter : {{ champsManquants.join(', ') }}
            </span>
            <div class="ml-auto flex gap-2">
              <button class="btn-secondary text-sm" @click="showCreateForm = false">Annuler</button>
              <button class="btn-primary text-sm" :disabled="creating || !pilotDeskOptions.length" @click="submitCreate">
                {{ creating ? 'Création…' : 'Créer la RFQ' }}
              </button>
            </div>
          </div>

          <AlertMessage v-if="createError" kind="error">{{ createError }}</AlertMessage>
          <AlertMessage v-if="!pilotDeskOptions.length" kind="info">
            Aucun desk ne vous autorise à créer une RFQ. Demandez une habilitation dans Administration → Utilisateurs → Desks RFQ.
          </AlertMessage>
          <div v-else class="card flex flex-col gap-1 max-w-md">
            <label class="label">Desk pilote *</label>
            <select v-model.number="form.pilot_desk_id" class="select">
              <option v-for="desk in pilotDeskOptions" :key="desk.id" :value="desk.id">{{ desk.name }}</option>
            </select>
            <p class="text-[10px] text-slate-500">Ce desk possède le dossier. Les autres desks n'y accèdent que par partage explicite.</p>
          </div>
          <AlertMessage v-if="sourceProduct" kind="info">
            Cette RFQ utilise le Product <span class="font-mono font-semibold">{{ sourceProduct.reference }}</span>
            en termes v{{ sourceProduct.terms_version }}. Le serveur reprend ses termes et son calendrier comme source faisant autorité.
          </AlertMessage>

          <!-- Deux colonnes dès qu'il y a la place : à gauche ce qu'on
               demande et à qui, à droite le produit qu'on fait pricer. -->
          <div class="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
            <RfqCreateRequest />

            <RfqCreateProduct />
          </div>

        </div>

        <!-- Détail RFQ -->
        <div v-else-if="rfq.current" class="flex flex-col gap-4 max-w-[1900px]">
          <RfqDetailHeader />

          <!-- Deux colonnes figées : à gauche tout l'AO (produit, prix,
               script, cotations), à droite le contrôle du prix. La grille ne
               dépend QUE de la largeur de fenêtre, jamais de l'état des
               données — la colonne de gauche a la même largeur avant et après
               un pricing, rien ne se réagence quand le prix arrive.

               1650 px : en-dessous, la colonne de gauche descendrait sous
               700 px utiles une fois les 560 px du panneau retirés (plus la
               liste des AO et les marges) — on empile alors plutôt que de
               rendre les deux colonnes illisibles. 560 px, c'est la largeur
               qu'exige la table des flux pour ne pas défiler. -->
          <div class="flex flex-col gap-4 min-[1650px]:grid min-[1650px]:grid-cols-[minmax(0,1fr)_560px] min-[1650px]:items-start">
            <div class="flex flex-col gap-4 min-w-0">
              <RfqDetailTerms />

              <!-- Prix modèle — params modifiables avant recalcul -->
              <RfqDetailPricing />
              <AlertMessage v-if="computeError" kind="error">{{ computeError }}</AlertMessage>

              <!-- Script (collapsible) -->
              <details class="card text-xs text-slate-400">
                <summary class="font-bold cursor-pointer text-slate-300 select-none">▸ PayScript</summary>
                <SensitiveValue mode="input"><pre class="mt-3 font-mono text-slate-400 whitespace-pre-wrap">{{ rfq.current.script_snapshot }}</pre></SensitiveValue>
              </details>

              <!-- Quotes -->
              <RfqQuotesCard />
            </div>

            <SensitiveValue><RfqPricingPanel :rfq="rfq.current" :pricing="rfq.lastPricing" :can-price="can(rfq.current, 'price')" /></SensitiveValue>
            <div v-if="selectedQuote">
              <SensitiveValue v-if="demoMode.enabled" />
              <div v-show="!demoMode.enabled">
                <CcrCreditCheck :rfq-id="rfq.current.id" :quote-id="selectedQuote.id"
                  :counterparty-name="selectedQuote.counterparty" />
              </div>
            </div>
          </div>
        </div>

        <!-- État vide -->
        <div v-else class="flex flex-col items-center justify-center py-24 gap-3 text-slate-600">
          <div class="text-4xl">📨</div>
          <div class="text-sm">Sélectionnez une RFQ ou créez-en une nouvelle</div>
        </div>
      </main>
    </div>

    <BaseModal v-model="showExchange" title="Demande partagée et contrôle du prix" fullscreen>
      <RfqExchangePanel v-if="showExchange && rfq.current" :rfq="rfq.current" :providers="rfq.providers" :pricing="rfq.lastPricing"
        :calculating="computing" :can-price="can(rfq.current, 'price')" :can-prepare="can(rfq.current, 'prepare')" :pricing-error="computeError" @calculate="computeModelPrice" @pricer="openRfqPricer" @new-round="openNewRound" />
      <template #footer><button class="btn-secondary" @click="showExchange = false">Revenir à la RFQ</button></template>
    </BaseModal>
    <BaseModal v-model="showShares" title="Partage de la RFQ" max-width="620px">
      <div class="flex flex-col gap-3 text-sm">
        <p class="text-xs text-slate-500">Le desk destinataire doit déjà avoir ses propres habilitations. Le partage en limite les droits sur ce dossier.</p>
        <AlertMessage v-if="shareError" kind="error">{{ shareError }}</AlertMessage>
        <label class="flex flex-col gap-1">Desk destinataire
          <select v-model.number="shareDraft.desk_id" class="select">
            <option :value="null">— Choisir —</option>
            <option v-for="desk in organizationDesks.filter(d => d.id !== rfq.current?.pilot_desk_id)"
                    :key="desk.id" :value="desk.id">{{ desk.name }}</option>
          </select>
        </label>
        <div class="flex flex-wrap gap-3 text-xs">
          <label v-for="right in shareRights" :key="right.key" class="flex items-center gap-1">
            <input v-model="shareDraft.rights" type="checkbox" :value="right.key" /> {{ right.label }}
          </label>
        </div>
        <label class="flex flex-col gap-1">Motif du partage
          <input v-model="shareDraft.reason" class="input" placeholder="Intervention Structuration sur le pricing…" />
        </label>
        <label class="flex flex-col gap-1">Échéance éventuelle
          <input v-model="shareDraft.expires_at" type="datetime-local" class="input" />
        </label>
        <div v-if="rfqShares.length" class="border-t border-slate-700 pt-2 text-xs">
          <div class="font-semibold mb-1">Partages enregistrés</div>
          <div v-for="share in rfqShares.filter(s => s.active)" :key="share.desk_id" class="flex items-center justify-between gap-2 py-1">
            <span>{{ share.desk_name }} · {{ share.rights.join(', ') }}</span>
            <button class="btn-danger btn-sm" @click="revokeShare(share)">Retirer</button>
          </div>
        </div>
      </div>
      <template #footer>
        <button class="btn-secondary" @click="showShares = false">Fermer</button>
        <button class="btn-primary" :disabled="!shareDraft.desk_id || !shareDraft.reason.trim()" @click="saveShare">Partager</button>
      </template>
    </BaseModal>
    <BaseModal v-model="showAssignment" title="Responsable et desk pilote" max-width="620px">
      <div class="space-y-3">
        <AlertMessage v-if="assignmentError" kind="error">{{ assignmentError }}</AlertMessage>
        <p class="text-xs text-slate-500">L'organisation et les termes restent ceux du dossier. Un transfert ne partage pas automatiquement la RFQ avec le desk source.</p>
        <label class="block"><span class="label">Desk pilote</span><select v-model.number="assignmentDraft.pilot_desk_id" class="select w-full" @change="loadAssignmentMembers"><option v-for="desk in organizationDesks" :key="desk.id" :value="desk.id">{{ desk.name }}</option></select></label>
        <label class="block"><span class="label">Responsable habilité dans ce desk</span><select v-model.number="assignmentDraft.responsible_user_id" class="select w-full" :disabled="assignmentLoading"><option :value="null">— Choisir —</option><option v-for="member in assignmentMembers" :key="member.id" :value="member.id">{{ member.username }}</option></select></label>
        <fieldset class="space-y-2"><legend class="label">Partages existants à conserver explicitement</legend>
          <label v-for="share in rfqShares.filter(s => s.active && s.desk_id !== assignmentDraft.pilot_desk_id)" :key="share.desk_id" class="flex items-center gap-2 text-xs"><input v-model="assignmentDraft.retained_share_desk_ids" type="checkbox" :value="share.desk_id" />{{ share.desk_name }} · {{ share.rights.join(', ') }}</label>
          <p v-if="!rfqShares.some(s => s.active && s.desk_id !== assignmentDraft.pilot_desk_id)" class="text-xs text-slate-500">Aucun partage supplémentaire.</p>
        </fieldset>
        <label class="block"><span class="label">Motif de l'affectation ou du transfert</span><input v-model="assignmentDraft.reason" class="input w-full" /></label>
      </div><template #footer><button class="btn-secondary" @click="showAssignment = false">Annuler</button><button class="btn-primary" :disabled="assignmentSaving || assignmentLoading || !assignmentDraft.responsible_user_id || assignmentDraft.reason.trim().length < 3" @click="saveAssignment">{{ assignmentSaving ? 'Enregistrement…' : 'Appliquer l’affectation' }}</button></template>
    </BaseModal>
    <BaseModal v-model="showDeleteConfirm" title="Supprimer la RFQ" max-width="380px">
      <p class="text-sm text-slate-300">
        Supprimer « {{ deleteTargetLabel }} » ? Les réponses fournisseurs associées seront supprimées aussi. Cette action est irréversible.
      </p>
      <template #footer>
        <button class="btn-secondary text-sm" @click="showDeleteConfirm = false">Annuler</button>
        <button class="btn-danger text-sm" @click="confirmDeleteRfq">Supprimer</button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
import RfqCreateRequest from './rfq/RfqCreateRequest.vue'
import RfqCreateProduct from './rfq/RfqCreateProduct.vue'
import RfqDetailHeader from './rfq/RfqDetailHeader.vue'
import RfqDetailTerms from './rfq/RfqDetailTerms.vue'
import RfqDetailPricing from './rfq/RfqDetailPricing.vue'
import RfqQuotesCard from './rfq/RfqQuotesCard.vue'
import { RFQ_CONTEXT } from './rfq/context.js'
import BackLink from '../components/ui/BackLink.vue'
import SensitiveValue from '../components/SensitiveValue.vue'
import { ref, reactive, computed, watch, onMounted, onUnmounted, nextTick, provide } from 'vue'
import { RouterLink, useRouter, useRoute } from 'vue-router'
import { useRfqStore } from '../stores/rfq.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { useProductsStore } from '../stores/products.js'
import { useMarketAssumptions } from '../composables/useMarketAssumptions.js'
import { fractionToPercent, fractionToPercentExact } from '../utils/underlyingDefaults.js'
import { recordMarketReference } from '../utils/marketProvenance.js'
import { canonicalPayoffFamily, payoffFamilyForModel } from '../utils/payoffFamilies.js'
import { calibrateUnderlying } from '../utils/smileCalibration.js'
import { surfaceCalibrationKey } from '../utils/volSurface.js'
import { apiFetch } from '../utils/api.js'
import { fixingDate, parameterValues } from '../utils/payscriptEconomics.js'
import { templateMeta, examples } from '../data/payscriptTemplates.js'
import { ensureUnderlyings, selectCatalogUnderlying } from '../data/commonUnderlyings.js'
import {
  emptyRfqUnderlying, normaliseCorrelation, rfqBasketFromParams,
  rfqUnderlyingToParams,
} from '../utils/rfqBasket.js'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import BaseModal from '../components/ui/BaseModal.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import DataFilterBar from '../components/ui/DataFilterBar.vue'
import { useDataFilter } from '../composables/useDataFilter.js'
import RfqPricingPanel from '../components/RfqPricingPanel.vue'
import RfqExchangePanel from '../components/RfqExchangePanel.vue'
import CcrCreditCheck from '../components/CcrCreditCheck.vue'
import { formatDate, formatDateTime, formatPercent, formatInt, formatBps } from '../utils/format.js'
import {
  addYears, buildConstatsPayload, can, canonical, contractualSubset, kindBadge, kindLabel,
  normalizedFamily, replaceBasket, restoreConstatOverrides, sensBadge, sensHint, sensLabel,
  shareRights, statusBadge, statusLabel, syncConstatOverrides, toDatetimeLocal, todayIso,
  withDefaultValidity, yearsBetween,
} from './rfq/rfqLabels.js'

// Catalogue de sous-jacents : chargé depuis la base au montage.
onMounted(ensureUnderlyings)
const legalCounterparties = ref([]), legalDraft = reactive({}), legalReasons = reactive({})
onMounted(async () => {
  try { const res = await apiFetch('/api/deals/counterparties'); if (res.ok) legalCounterparties.value = await res.json() } catch { /* Qualification remains unavailable until the catalog can be loaded. */ }
})
async function qualifyQuote(quote) {
  if (!legalDraft[quote.id] || (legalReasons[quote.id] || '').trim().length < 3) { rfq.error = 'Choisissez une contrepartie active et renseignez un motif.'; return }
  await rfq.updateQuote(rfq.current.id, quote.id, { counterparty_id: legalDraft[quote.id], identity_reason: legalReasons[quote.id].trim() })
}

const rfq = useRfqStore()
const demoMode = useDemoModeStore()
const myDesks = ref([])
const organizationDesks = ref([])
const pilotDeskOptions = computed(() => myDesks.value.filter(d => d.rights.includes('prepare')))
const showShares = ref(false)
const rfqShares = ref([])
const shareError = ref('')
const shareDraft = reactive({ desk_id: null, rights: ['read'], reason: '', expires_at: '' })
const showAssignment = ref(false)
const assignmentMembers = ref([])
const assignmentError = ref('')
const assignmentLoading = ref(false)
const assignmentSaving = ref(false)
const assignmentSnapshot = ref(null)
const assignmentDraft = reactive({ pilot_desk_id: null, responsible_user_id: null, retained_share_desk_ids: [], reason: '' })
let assignmentGeneration = 0

async function openAssignment() {
  assignmentError.value = ''
  const source = rfq.current
  assignmentSnapshot.value = { id: source.id, pilot_desk_id: source.pilot_desk_id, responsible_user_id: source.responsible_user_id }
  const res = await apiFetch(`/api/rfq/${source.id}/shares`)
  if (!res.ok) { listError.value = 'Les partages du dossier n’ont pas pu être relus.'; return }
  rfqShares.value = await res.json()
  Object.assign(assignmentDraft, { pilot_desk_id: source.pilot_desk_id, responsible_user_id: source.responsible_user_id,
    retained_share_desk_ids: rfqShares.value.filter(s => s.active).map(s => s.desk_id), reason: '' })
  showAssignment.value = true
  await loadAssignmentMembers()
}

async function loadAssignmentMembers() {
  const ticket = ++assignmentGeneration
  assignmentLoading.value = true
  assignmentDraft.retained_share_desk_ids = assignmentDraft.retained_share_desk_ids.filter(id => id !== assignmentDraft.pilot_desk_id)
  try {
    const res = await apiFetch(`/api/rfq-desks/${assignmentDraft.pilot_desk_id}/members`)
    if (!res.ok) throw new Error('Les responsables habilités ne peuvent pas être chargés.')
    const members = await res.json()
    if (ticket !== assignmentGeneration) return
    assignmentMembers.value = members
    if (!members.some(m => m.id === assignmentDraft.responsible_user_id)) assignmentDraft.responsible_user_id = null
  } catch (failure) { if (ticket === assignmentGeneration) assignmentError.value = failure.message }
  finally { if (ticket === assignmentGeneration) assignmentLoading.value = false }
}

async function saveAssignment() {
  assignmentSaving.value = true
  assignmentError.value = ''
  const snapshot = assignmentSnapshot.value
  try {
    const res = await apiFetch(`/api/rfq/${snapshot.id}/assignment`, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...assignmentDraft, expected_pilot_desk_id: snapshot.pilot_desk_id,
        expected_responsible_user_id: snapshot.responsible_user_id,
        expected_share_desk_ids: rfqShares.value.filter(s => s.active).map(s => s.desk_id) }) })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Affectation refusée')
    showAssignment.value = false
    await rfq.fetchList()
    if (rfq.list.some(row => row.id === snapshot.id)) {
      await rfq.fetchOne(snapshot.id)
      await refreshDetailParams()
    } else { rfq.current = null; selectedId.value = null }
    notice.value = 'Affectation enregistrée. Les accès ont été recalculés selon le desk et les partages conservés.'
  } catch (failure) { assignmentError.value = failure.message }
  finally { assignmentSaving.value = false }
}

async function openShares() {
  shareError.value = ''
  const res = await apiFetch(`/api/rfq/${rfq.current.id}/shares`)
  if (!res.ok) { shareError.value = 'Partages indisponibles'; return }
  rfqShares.value = await res.json()
  showShares.value = true
}

async function saveShare() {
  shareError.value = ''
  const res = await apiFetch(`/api/rfq/${rfq.current.id}/shares/${shareDraft.desk_id}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rights: shareDraft.rights, reason: shareDraft.reason,
      expires_at: shareDraft.expires_at ? new Date(shareDraft.expires_at).toISOString() : null }),
  })
  if (!res.ok) { shareError.value = (await res.json().catch(() => ({}))).detail || 'Partage refusé'; return }
  rfqShares.value = await (await apiFetch(`/api/rfq/${rfq.current.id}/shares`)).json()
  shareDraft.reason = ''
  notice.value = 'Partage enregistré'
}

async function revokeShare(share) {
  shareError.value = ''
  const res = await apiFetch(`/api/rfq/${rfq.current.id}/shares/${share.desk_id}`, { method: 'DELETE' })
  if (!res.ok) { shareError.value = (await res.json().catch(() => ({}))).detail || 'Retrait refusé'; return }
  rfqShares.value = rfqShares.value.filter(s => s.desk_id !== share.desk_id)
  notice.value = 'Partage retiré'
}
const mobilePanel = ref(rfq.current ? 'detail' : 'list')
const showExchange = ref(false)
const products = useProductsStore()
const router = useRouter()
const route = useRoute()
const sourceProduct = ref(null)
const sourceProductPricingInput = ref(null)

// Contexte commercial, quand on arrive depuis une fiche d'opportunité
// (`/rfq?opportunity=12`). Purement additif : sans ce paramètre, l'écran se
// comporte exactement comme avant, et le champ part à null.
const opportuniteContexte = ref(null)
const commercialLinkEnabled = ref(false)
const directClients = ref([])
const directMandates = ref([])
const directOpportunities = ref([])
const directContacts = ref([])
onMounted(async () => {
  const id = Number(route.query.opportunity)
  if (!id) return
  const reponse = await apiFetch(`/api/opportunities/${id}`)
  if (reponse.ok) opportuniteContexte.value = await reponse.json()
})

const loadingList    = ref(true)
const listError      = ref('')
const notice         = ref('')
const selectedId     = ref(null)
let responseTimer = null
let responseRefreshRunning = false
onMounted(() => {
  responseTimer = setInterval(async () => {
    if (responseRefreshRunning || !rfq.current?.exchange_round || rfq.current.booked_deal || document.hidden
        || document.activeElement?.matches('input,select,textarea')) return
    responseRefreshRunning = true
    try { await rfq.refreshNetworkQuotes(rfq.current.id) } catch { /* Retain the last received snapshot during a temporary interruption. */ }
    finally { responseRefreshRunning = false }
  }, 5000)
})
onUnmounted(() => clearInterval(responseTimer))

const showCreateForm = ref(false)
const creating       = ref(false)
const createError    = ref('')
const computing      = ref(false)
let computeRevision=0
const computeError   = ref('')
const addingQuote    = ref(false)
const scripts        = ref([])
// Booked deals, used only to offer their frozen PayScript as an
// alternative source in the "Script de la bibliothèque" picker below — a
// desk often already has the exact precise calendar it wants sitting on a
// past deal rather than saved separately in the script library.
const dealsForScripts = ref([])
const scriptedDeals = computed(() =>
  dealsForScripts.value.filter(d => d.script_snapshot?.includes('CONSTAT'))
)

const groupedTemplates = computed(() => {
  const groups = {}
  for (const t of templateMeta) {
    (groups[t.group] ||= []).push(t)
  }
  return groups
})

const form = reactive({
  pilot_desk_id: null,
  previous_round_id: null,
  name: '',
  ao_date: todayIso(),
  pricing_date: todayIso(),
  kind: 'indicatif',
  sens: 'achat',
  source: 'template',
  template_type: '',
  transaction_format: '',
  instrument_family: '',
  payoff_family: '',
  payoff_description: '',
  documentation_reference: '',
  opportunity_id: null,
  client_id: null,
  mandate_id: null,
  primary_affiliation_id: null,
  script_id: null,
  source_deal_id: null,  // set instead of script_id when sourced from scriptedDeals
  currency: 'CHF',
  T: 3,
  // Aucune date par défaut : elles viennent du term sheet, pas d'une règle
  // T+2 qui aurait l'air juste sans l'être. Saisie obligatoire.
  strike_date: '',
  value_date: '',
  payment_date: '',
  // Une convention par date, sans défaut global : une date fixée par un term
  // sheet un jour fermé y reste tant que personne n'a dit comment la traiter.
  strike_date_convention: 'none',
  value_date_convention: 'none',
  payment_date_convention: 'none',
})
const legacyPayoffFamily = computed(() => form.payoff_family
  && !canonicalPayoffFamily(form.payoff_family) ? form.payoff_family : '')
let lastSuggestedFamily = ''
const dateNotices = reactive({ strike_date: '', value_date: '', payment_date: '' })

// Vrai dès que l'utilisateur saisit la date de paiement lui-même.
//
// Sans ce drapeau, le seul garde-fou de la proposition était « le champ est-il
// vide » — qui ne distingue pas une saisie d'une proposition faite depuis une
// maturité qui a bougé depuis. La date se verrouillait donc sur la première
// maturité vue, souvent celle d'un calendrier CONSTAT à moitié rempli, et ne
// suivait plus jamais. C'est ce qui a produit un AO à maturité 2029 réglé en
// 2026.
const paymentDateSaisie = ref(false)

// Read-only preview of the maturity date, same rule DealTab.vue books with:
// the latest CONSTAT schedule end date if the script has one (to_trade),
// else value_date + T years.
const createMaturityDate = computed(() => {
  const ends = scriptConstats.value
    .filter(c => c.role !== 'initial_fixing')
    .map(c => c.kind === 'single' ? (typeof constatOverrides[c.name] === 'string' ? constatOverrides[c.name] : constatOverrides[c.name]?.date) : constatOverrides[c.name]?.end_date)
    .filter(Boolean)
  if (ends.length) return ends.reduce((max, d) => (d > max ? d : max))
  // Sans calendrier, la maturité se compte depuis le strike : T est l'horizon
  // de diffusion, et la diffusion démarre à la constatation initiale.
  if (!form.strike_date || !form.T) return ''
  return addYears(form.strike_date, form.T)
})

// Both RFQ kinds share the same generic catalogue and explicit calendars.
function onKindToggle(kind) {
  form.kind = kind
}

const advanced = reactive({ r: 3, N: 20000, model: 'constant' })
const createBasket = reactive(rfqBasketFromParams([], form.currency))
const createActiveUnderlyingIdx = ref(0)
const createCorrMatrix = ref([[1]])
const detailBasket = reactive(rfqBasketFromParams([], form.currency))
const detailActiveUnderlyingIdx = ref(0)
const detailCorrMatrix = ref([[1]])

function setCreateBasket(underlyings, correlation = null) {
  replaceBasket(createBasket, rfqBasketFromParams(underlyings, form.currency))
  createActiveUnderlyingIdx.value = 0
  createCorrMatrix.value = normaliseCorrelation(correlation, createBasket.length)
}

function setDetailBasket(underlyings, correlation = null) {
  replaceBasket(detailBasket, rfqBasketFromParams(underlyings, rfq.current?.params?.currency || 'EUR'))
  detailActiveUnderlyingIdx.value = 0
  detailCorrMatrix.value = normaliseCorrelation(correlation, detailBasket.length)
}

function addCreateUnderlying() {
  createBasket.push(emptyRfqUnderlying(createBasket.length, form.currency))
  createCorrMatrix.value = normaliseCorrelation(createCorrMatrix.value, createBasket.length)
  createActiveUnderlyingIdx.value = createBasket.length - 1
}

function removeCreateUnderlying(index) {
  if (createBasket.length <= 1 || sourceProduct.value) return
  createBasket.splice(index, 1)
  const reduced = createCorrMatrix.value
    .filter((_, i) => i !== index)
    .map(row => row.filter((_, j) => j !== index))
  createCorrMatrix.value = normaliseCorrelation(reduced, createBasket.length)
  createActiveUnderlyingIdx.value = Math.min(createActiveUnderlyingIdx.value, createBasket.length - 1)
}

// ── Hypothèses de marché de l'appel d'offres ──────────────────────
//
// LOCALES, pas celles du Pricer. Les trois cartes acceptent désormais leur état
// en prop et retombent sur le store quand on ne leur en donne pas : le Pricer
// n'a rien changé, et l'AO édite les siennes sans que les deux écrans se
// marchent dessus.
//
// Deux jeux indépendants — un pour la saisie, un pour le détail — rendus par
// la même fabrique, qui porte aussi la conversion vers le moteur et le chemin
// du retour. Voir `useMarketAssumptions`.
const ao = useMarketAssumptions(computed(() => createBasket.map(row => ({
  name: row.name || row.ticker || 'Sous-jacent', q: row.q,
}))))

// Le détail a son PROPRE jeu. Le partager avec le formulaire de création
// ferait qu'ouvrir un AO existant écrase les hypothèses d'un AO en cours de
// saisie — et l'inverse.
const aoDetail = useMarketAssumptions(computed(() => detailBasket.map(row => ({
  name: row.name || row.ticker || 'Sous-jacent', q: row.q,
}))))

function onUnderlyingSelect(index, ticker) {
  const row = createBasket[index]
  if (!row) return
  try { selectCatalogUnderlying(row, ticker) }
  catch (e) { createError.value = e.message }
}

// ── Termes du produit + calendrier(s) CONSTAT (dynamiques, extraits du script) ──
const parsedParams = ref([])
const paramOverrides = reactive({})
const scriptConstats = ref([])
const constatOverrides = reactive({})
// Set only while duplicating an existing RFQ: the frozen snapshot overrides
// whatever form.template_type/script_id would otherwise resolve to, so a
// duplicate always reproduces the exact script that was actually quoted.
const duplicateSourceScript = ref(null)

function currentScriptText() {
  if (duplicateSourceScript.value) return duplicateSourceScript.value
  if (form.source === 'template') {
    const lib = examples
    return lib[form.template_type] || ''
  }
  return scripts.value.find(x => x.id === form.script_id)?.script_text || ''
}

let createParseRevision = 0
async function refreshParsedParams(overrideValues = null, overrideConstats = null) {
  const revision = ++createParseRevision
  const script = currentScriptText()
  Object.keys(paramOverrides).forEach(k => delete paramOverrides[k])
  if (!script.trim()) { parsedParams.value = []; scriptConstats.value = []; return }
  try {
    const res = await apiFetch('/api/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script }),
    })
    const data = await res.json()
    if (revision !== createParseRevision || script !== currentScriptText()) return
    parsedParams.value = data.ok ? data.params : []
    for (const p of parsedParams.value) {
      const ov = overrideValues && (p.name in overrideValues) ? overrideValues[p.name] : null
      paramOverrides[p.name] = Array.isArray(ov) ? ov.map(v => p.is_pct ? fractionToPercent(v) : v) : ov !== null ? (p.is_pct ? fractionToPercent(ov) : ov) : p.kind === 'array' ? [p.display_default] : p.display_default
    }
    scriptConstats.value = data.ok ? (data.constats || []) : []
    if (overrideConstats) restoreConstatOverrides(scriptConstats.value, constatOverrides, overrideConstats)
    else syncConstatOverrides(scriptConstats.value, constatOverrides)
  } catch {
    if (revision !== createParseRevision) return
    parsedParams.value = []
    scriptConstats.value = []
  }
}

function applyCreatePreset(plan) {
  if (sourceProduct.value) throw Error('Cette RFQ utilise les termes figés d’un Product.')
  if (plan.currency !== form.currency) throw Error('La devise a changé. Préparez à nouveau l’exemple.')
  if (createBasket.length < plan.model.underlyings.min || createBasket.length > plan.model.underlyings.max)
    throw Error('Le panier a changé. Préparez à nouveau l’exemple.')
  createParseRevision += 1
  duplicateSourceScript.value = null
  form.source = 'template'; form.template_type = plan.model.key
  form.script_id = null; form.source_deal_id = null
  const suggested = payoffFamilyForModel(plan.model.key)
  if (!form.payoff_family || form.payoff_family === lastSuggestedFamily) form.payoff_family = suggested
  lastSuggestedFamily = suggested
  if (!form.name) form.name = plan.preset.label
  form.strike_date = plan.strikeDate; form.value_date = plan.strikeDate
  form.payment_date = plan.paymentDate; form.T = plan.T
  paymentDateSaisie.value = true
  parsedParams.value = plan.validation.data.params
  scriptConstats.value = plan.validation.data.constats
  for (const key of Object.keys(paramOverrides)) delete paramOverrides[key]
  Object.assign(paramOverrides, JSON.parse(JSON.stringify(plan.params)))
  for (const key of Object.keys(constatOverrides)) delete constatOverrides[key]
  restoreConstatOverrides(scriptConstats.value, constatOverrides, plan.constats)
}

function onSourceToggle(src) {
  form.source = src
  duplicateSourceScript.value = null
  sourceProduct.value = null
  sourceProductPricingInput.value = null
  refreshParsedParams()
}
function onTemplateChange() {
  const suggested = payoffFamilyForModel(form.template_type)
  if (!form.payoff_family || form.payoff_family === lastSuggestedFamily) {
    form.payoff_family = suggested
  }
  lastSuggestedFamily = suggested
  duplicateSourceScript.value = null
  sourceProduct.value = null
  sourceProductPricingInput.value = null
  refreshParsedParams()
}
// The picker offers two kinds of options in one <select>: rows from the
// saved script library (form.script_id) and PayScripts frozen on
// already-booked deals (form.source_deal_id, no Script row to point at —
// the deal's snapshot is handed to duplicateSourceScript instead, same
// override currentScriptText() already uses for RFQ duplication).
const librarySelectValue = computed(() => {
  if (form.script_id) return `script:${form.script_id}`
  if (form.source_deal_id) return `deal:${form.source_deal_id}`
  return ''
})
function onLibrarySelect(value) {
  duplicateSourceScript.value = null
  form.script_id = null
  form.source_deal_id = null
  if (value.startsWith('script:')) {
    form.script_id = Number(value.slice(7))
  } else if (value.startsWith('deal:')) {
    const dealId = Number(value.slice(5))
    form.source_deal_id = dealId
    const deal = dealsForScripts.value.find(d => d.id === dealId)
    duplicateSourceScript.value = deal?.script_snapshot || null
    if (!form.payoff_family && deal?.payoff_family) {
      form.payoff_family = normalizedFamily(deal.payoff_family)
    }
  }
  refreshParsedParams()
}

// ── Nominal formatting (séparateur de milliers, mirror de DealTab.vue) ──
const nominalRaw = ref('1 000 000')
const nominalValue = computed(() => {
  return parseFloat(nominalRaw.value.replace(/\s/g, '').replace(',', '.')) || 0
})
function formatNominal() {
  const n = nominalValue.value
  if (n) nominalRaw.value = n.toLocaleString('fr-FR').replace(/,/g, ' ')
}
function unformatNominal(event) {
  nominalRaw.value = String(nominalValue.value || '')
  // Select on focus so typing replaces the value instead of appending to it
  // (mirror of the same fix in DealTab.vue).
  const el = event?.target
  if (el) nextTick(() => el.select())
}
formatNominal()

const quoteForm = reactive({ provider: '', customProvider: '', contact: '' })

onMounted(async () => {
  loadingList.value = true
  try {
    // Le store Pinia survit à la navigation RFQ → Pricer → RFQ. Le détail
    // conservé peut donc dater d'avant le booking alors que la liste, elle,
    // vient d'être relue. On recharge explicitement l'AO courant pour ne pas
    // laisser apparaître une seconde fois le bouton de booking.
    const currentId = Number(route.query.rfq) || rfq.current?.id || null
    const [desksRes, organizationRes] = await Promise.all([
      apiFetch('/api/rfq-desks'), apiFetch('/api/rfq-desks/organization'),
    ])
    if (desksRes.ok) myDesks.value = await desksRes.json()
    if (organizationRes.ok) organizationDesks.value = await organizationRes.json()
    form.pilot_desk_id = pilotDeskOptions.value[0]?.id ?? null
    await Promise.all([rfq.fetchList(), rfq.fetchProviders(), fetchScripts(), fetchDealsForScripts()])
    if (currentId && rfq.list.some(item => item.id === currentId)) {
      selectedId.value = currentId
      await rfq.fetchOne(currentId)
      await refreshDetailParams()
    } else if (currentId) {
      selectedId.value = null
      rfq.current = null
    }
    const productId = Number(route.query.product)
    if (productId) await prefillFromProduct(productId)
  } finally {
    loadingList.value = false
  }
})

async function fetchScripts() {
  const res = await apiFetch('/api/db/scripts')
  if (res.ok) scripts.value = await res.json()
}

async function fetchDealsForScripts() {
  const res = await apiFetch('/api/deals')
  if (res.ok) dealsForScripts.value = await res.json()
}

function openCreateForm() {
  form.previous_round_id = null
  mobilePanel.value = 'detail'
  lastSuggestedFamily = ''
  showCreateForm.value = true
  selectedId.value = null
  rfq.current = null
  createError.value = ''
  notice.value = ''
  duplicateSourceScript.value = null
  sourceProduct.value = null
  sourceProductPricingInput.value = null
  commercialLinkEnabled.value = false
  Object.assign(form, {
    pilot_desk_id: pilotDeskOptions.value[0]?.id ?? null,
    name: '', ao_date: todayIso(), pricing_date: todayIso(), kind: 'indicatif', sens: 'achat', source: 'template', template_type: '',
    script_id: null, source_deal_id: null,
    transaction_format: opportuniteContexte.value?.transaction_format || '',
    instrument_family: opportuniteContexte.value?.instrument_family || '',
    payoff_family: normalizedFamily(opportuniteContexte.value?.payoff_family),
    payoff_description: opportuniteContexte.value?.payoff_description || '',
    documentation_reference: '',
    opportunity_id: opportuniteContexte.value?.id ?? null,
    client_id: opportuniteContexte.value?.client_id ?? null,
    mandate_id: opportuniteContexte.value?.mandate_id ?? null,
    primary_affiliation_id:
      opportuniteContexte.value?.primary_contact?.affiliation_id ?? null,
    currency: 'CHF', T: 3,
    // Aucune date inventee : ni a l ouverture du formulaire, ni en dupliquant,
    // ni en convertissant. Elles viennent du term sheet de l affaire en cours,
    // pas de celle d avant.
    strike_date: '', value_date: '', payment_date: '',
  })
  // Le drapeau de saisie suit les dates : sans ça, avoir saisi une date de
  // paiement sur une affaire empêcherait toute proposition sur la suivante.
  paymentDateSaisie.value = false
  Object.assign(advanced, { r: 3, N: 20000, model: 'constant' })
  setCreateBasket([], form.currency)
  ao.depuisParams({})
  nominalRaw.value = '1 000 000'
  parsedParams.value = []
}

async function prefillFromProduct(productId) {
  const loaded = await products.fetchOne(productId)
  if (!loaded) {
    listError.value = products.error || 'Produit introuvable.'
    return
  }
  openCreateForm()
  sourceProduct.value = loaded.product
  sourceProductPricingInput.value = loaded.calculationInput
  const terms = loaded.product.terms
  duplicateSourceScript.value = terms.script
  form.source = 'script'
  form.name = loaded.product.name
  const intent = loaded.product.intent || {}
  const commercial = loaded.product.commercial || {}
  Object.assign(form, {
    sens: intent.side === 'SELL' ? 'vente' : 'achat',
    template_type: intent.product_type || '',
    transaction_format: intent.transaction_format || '',
    instrument_family: intent.instrument_family || '',
    payoff_family: intent.payoff_family || '',
    payoff_description: intent.payoff_description || '',
    documentation_reference: intent.documentation_reference || '',
    client_id: commercial.client_id ?? null, mandate_id: commercial.mandate_id ?? null,
    opportunity_id: commercial.opportunity_id ?? null,
    primary_affiliation_id: commercial.primary_affiliation_id ?? null,
  })
  commercialLinkEnabled.value = !!(form.client_id || form.opportunity_id)
  form.T = terms.T
  form.currency = terms.settlement_ccy || 'EUR'
  form.strike_date = terms.strike_date || ''
  form.value_date = terms.value_date || ''
  form.payment_date = terms.payment_date || ''
  const productUnderlyings = terms.underlyings.map((identity, index) => ({
    ...(loaded.calculationInput?.underlyings?.[index] || {}), ...identity,
  }))
  setCreateBasket(productUnderlyings, loaded.calculationInput?.corr_matrix)
  ao.depuisParams({ underlyings: productUnderlyings, ...loaded.calculationInput })
  nominalRaw.value = String(loaded.product.intent?.nominal || 1_000_000)
  formatNominal()
  advanced.r = fractionToPercent(loaded.calculationInput?.r ?? 0.03)
  advanced.N = loaded.calculationInput?.N ?? 20000
  advanced.model = loaded.calculationInput?.model || 'constant'
  await refreshParsedParams()
  for (const parameter of terms.parameters || []) {
    paramOverrides[parameter.name] = Array.isArray(parameter.value)
      ? parameter.value.map(value => parameter.is_pct ? fractionToPercent(value) : value)
      : (parameter.is_pct ? fractionToPercent(parameter.value) : parameter.value)
  }
  restoreConstatOverrides(scriptConstats.value, constatOverrides, terms.constats || {})
  if (commercialLinkEnabled.value) {
    if (!directClients.value.length) {
      const response = await apiFetch('/api/clients')
      if (response.ok) directClients.value = await response.json()
    }
    await loadDirectCommercialOptions(form.client_id)
  }
}

async function toggleDirectCommercial() {
  commercialLinkEnabled.value = !commercialLinkEnabled.value
  if (!commercialLinkEnabled.value) {
    Object.assign(form, {
      client_id: null, mandate_id: null, opportunity_id: null,
      primary_affiliation_id: null,
    })
    directMandates.value = []
    directOpportunities.value = []
    directContacts.value = []
    return
  }
  if (!directClients.value.length) {
    const response = await apiFetch('/api/clients')
    if (response.ok) directClients.value = await response.json()
  }
}

async function loadDirectCommercialOptions(clientId) {
  directMandates.value = []
  directOpportunities.value = []
  directContacts.value = []
  if (!clientId) return
  const [mandates, opportunities, contacts] = await Promise.all([
    apiFetch(`/api/clients/${clientId}/mandates`),
    apiFetch(`/api/opportunities?client_id=${clientId}&open_only=true`),
    apiFetch(`/api/clients/${clientId}/contacts`),
  ])
  if (mandates.ok) directMandates.value = await mandates.json()
  if (opportunities.ok) directOpportunities.value = await opportunities.json()
  if (contacts.ok) directContacts.value = await contacts.json()
}

async function onDirectClientChange() {
  Object.assign(form, {
    mandate_id: null, opportunity_id: null, primary_affiliation_id: null,
  })
  await loadDirectCommercialOptions(form.client_id)
}

function onDirectOpportunityChange() {
  const selected = directOpportunities.value.find(opp => opp.id === form.opportunity_id)
  if (!selected) return
  form.mandate_id = selected.mandate_id ?? null
  form.primary_affiliation_id = selected.primary_contact?.affiliation_id ?? null
  form.transaction_format ||= selected.transaction_format || ''
  form.instrument_family ||= selected.instrument_family || ''
  form.payoff_family ||= normalizedFamily(selected.payoff_family)
  form.payoff_description ||= selected.payoff_description || ''
}

// Pre-fills the create form from an existing RFQ (new tender round on the
// same product, params free to adjust before submitting as a new RFQ).
async function duplicateRfq(source) {
  form.previous_round_id = null
  sourceProduct.value = null
  sourceProductPricingInput.value = null
  showCreateForm.value = true
  selectedId.value = null
  createError.value = ''
  const p = source.params || {}
  Object.assign(form, {
    name: `${source.name || source.reference} (copie)`,
    pilot_desk_id: source.pilot_desk_id ?? pilotDeskOptions.value[0]?.id ?? null,
    ao_date: todayIso(),
    pricing_date: todayIso(),
    kind: source.kind || 'indicatif',
    sens: source.sens || 'achat',
    source: source.script_id ? 'script' : 'template',
    template_type: source.template_type || '',
    opportunity_id: source.opportunity_id ?? null,
    client_id: source.client_id ?? null,
    mandate_id: source.mandate_id ?? null,
    primary_affiliation_id: source.primary_affiliation_id ?? null,
    transaction_format: source.transaction_format || '',
    instrument_family: source.instrument_family || '',
    payoff_family: normalizedFamily(source.payoff_family)
      || payoffFamilyForModel(source.template_type),
    payoff_description: source.payoff_description || '',
    documentation_reference: source.documentation_reference || '',
    script_id: source.script_id || null,
    source_deal_id: null,
    currency: p.currency || 'CHF',
    T: p.T ?? 3,
    // Aucune date inventee : ni a l ouverture du formulaire, ni en dupliquant,
    // ni en convertissant. Elles viennent du term sheet de l affaire en cours,
    // pas de celle d avant.
    strike_date: '', value_date: '', payment_date: '',
  })
  // Le drapeau de saisie suit les dates : sans ça, avoir saisi une date de
  // paiement sur une affaire empêcherait toute proposition sur la suivante.
  paymentDateSaisie.value = false
  Object.assign(advanced, {
    r: Math.round((p.r ?? 0.03) * 1000) / 10,
    N: p.N ?? 20000,
    model: p.model || 'constant',
  })
  setCreateBasket(p.underlyings, p.corr_matrix)
  ao.depuisParams(p)
  nominalRaw.value = String(p.notional ?? 1000000)
  formatNominal()
  duplicateSourceScript.value = source.script_snapshot
  if (source.client_id && !opportuniteContexte.value) {
    commercialLinkEnabled.value = true
    if (!directClients.value.length) {
      const response = await apiFetch('/api/clients')
      if (response.ok) directClients.value = await response.json()
    }
    await loadDirectCommercialOptions(source.client_id)
  }
  await refreshParsedParams(p.user_params || {}, p.constats || {})
  form.strike_date = fixingDate(scriptConstats.value, constatOverrides) || ''
}

async function openNewRound() {
  const source = rfq.current
  if (!source?.exchange_round || !can(source, 'prepare')) return
  showExchange.value = false
  await duplicateRfq(source)
  form.previous_round_id = source.exchange_round.id
  form.name = `${source.name || source.reference} · nouveau tour`
}

// Conversion preserves the quoted script, required values and explicit calendars.
async function convertToTrade(source) {
  await duplicateRfq(source)
  form.kind = 'to_trade'
  form.name = `${source.name || source.reference} (to trade)`
}

async function selectRfq(id) {
  mobilePanel.value = 'detail'
  showCreateForm.value = false
  selectedId.value = id
  computeError.value = ''
  try {
    const loaded=await rfq.fetchOne(id)
    if(!loaded || selectedId.value!==id || rfq.current?.id!==id) return
    await refreshDetailParams()
    if (selectedId.value === id && rfq.current?.id === id) {
      // A retained dossier replaces the one-shot Product creation intent.
      // Reload must reopen this RFQ rather than prepare a second request.
      await router.replace({ path: '/rfq', query: { rfq: String(id) } })
    }
  } catch(e) {if(selectedId.value===id) listError.value=e.message}
}

// Editable copy of the RFQ's pricing params, shown in the detail panel's
// "Paramètres de pricing" — separate reactive state from the create form's
// (paramOverrides/constatOverrides/advanced) so editing one never bleeds
// into the other. Le calcul du prix n'envoie QUE les hypothèses de modèle :
// les termes contractuels (échéancier, dates, termes du produit) ne sont
// persistés que par saveDetailTerms, via le bouton dédié.
const detailParsedParams    = ref([])
const detailParamOverrides  = reactive({})
const detailScriptConstats  = ref([])
const detailConstatOverrides = reactive({})
const detailAdvanced = reactive({
  r: 3, N: 20000, model: 'constant',
  strike_date: '', value_date: '', payment_date: '', valuation_date: todayIso(),
})

async function refreshDetailParams() {
  if(await _loadDetailParams()) termsBaseline.value = contractualSubset(detailTermsPayload())
}

let detailLoadRevision=0
async function _loadDetailParams() {
  const ticket=++detailLoadRevision,id=rfq.current?.id
  const script = rfq.current?.script_snapshot || ''
  const p = rfq.current?.params || {}
  setDetailBasket(p.underlyings, p.corr_matrix)
  Object.assign(detailAdvanced, {
    r: Math.round((p.r ?? 0.03) * 1000) / 10,
    N: p.N ?? 20000,
    model: p.model || 'constant',
    strike_date: p.strike_date || '',
    value_date: p.value_date || '',
    payment_date: p.payment_date || '',
    valuation_date: p.valuation_date || todayIso(),
  })
  // Les hypothèses de marché avec lesquelles cet AO a été pricé, remises dans
  // les cartes. Sans ce retour, elles rouvriraient décochées et le prochain
  // « Calculer prix modèle » les effacerait sans un mot.
  aoDetail.depuisParams(p)
  Object.keys(detailParamOverrides).forEach(k => delete detailParamOverrides[k])
  if (!script.trim()) { detailParsedParams.value = []; detailScriptConstats.value = []; return true }
  try {
    const res = await apiFetch('/api/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script }),
    })
    const data = await res.json()
    if(ticket!==detailLoadRevision || rfq.current?.id!==id) return false
    detailParsedParams.value = data.ok ? data.params : []
    const savedParams = p.user_params || {}
    for (const pp of detailParsedParams.value) {
      const ov = pp.name in savedParams ? savedParams[pp.name] : null
      detailParamOverrides[pp.name] = Array.isArray(ov) ? ov.map(v => pp.is_pct ? fractionToPercent(v) : v) : ov !== null ? (pp.is_pct ? fractionToPercent(ov) : ov) : pp.kind === 'array' ? [pp.display_default] : pp.display_default
    }
    detailScriptConstats.value = data.ok ? (data.constats || []) : []
    restoreConstatOverrides(detailScriptConstats.value, detailConstatOverrides, p.constats || {})
    return true
  } catch {
    if(ticket!==detailLoadRevision || rfq.current?.id!==id) return false
    detailParsedParams.value = []
    detailScriptConstats.value = []
    return false
  }
}

const savingTerms  = ref(false)
const termsError   = ref('')
// Photo des termes tels que l'éditeur les affichait au dernier chargement.
const termsBaseline = ref('')

// Termes contractuels tels que l'éditeur les tient en ce moment. On repart
// des params STOCKÉS et on n'écrase que ce que l'éditeur pilote : une
// reconstruction complète depuis le formulaire réduisait un panier worst-of
// à son premier sous-jacent et déclenchait le gel sur cinq termes auxquels
// personne n'avait touché.
function detailTermsPayload() {
  const stored = rfq.current?.params || {}
  const user_params = parameterValues(detailParsedParams.value, detailParamOverrides, { allowMissing: true })
  return {
    ...stored,
    user_params,
    constats: buildConstatsPayload(detailScriptConstats.value, detailConstatOverrides),
    strike_date: detailAdvanced.strike_date,
    value_date: detailAdvanced.value_date,
    payment_date: detailAdvanced.payment_date,
    // T suit le calendrier, comme à la création : déplacer la dernière
    // constatation sans bouger T laisserait la maturité affichée et
    // l'horizon de simulation raconter deux histoires différentes.
    T: detailCalendarEnd.value
      ? yearsBetween(detailAdvanced.strike_date, detailCalendarEnd.value)
      : (stored.T ?? null),
  }
}

// Le règlement final ne peut pas précéder la dernière constatation. Le serveur
// le refuse à l'écriture ; ici on le SIGNALE sur les AO déjà en base, que ce
// refus n'atteint plus — leurs termes sont gelés dès la première cotation.
const reglementIncoherent = computed(() => {
  const paiement = rfq.current?.params?.payment_date
  return !!(paiement && detailMaturityDate.value && paiement < detailMaturityDate.value)
})

const detailTermsDirty = computed(() => {
  if (!rfq.current || !termsBaseline.value) return false
  return contractualSubset(detailTermsPayload()) !== termsBaseline.value
})

async function saveDetailTerms() {
  termsError.value = ''
  savingTerms.value = true
  try {
    await rfq.update(rfq.current.id, { params: detailTermsPayload() })
    await refreshDetailParams()
    notice.value = 'Termes de l\'AO enregistrés'
  } catch (e) {
    termsError.value = e.message
  } finally {
    savingTerms.value = false
  }
}

// ── Filtres de la liste d'AO ────────────────────────────────────────────
// Même mécanisme que l'onglet Deals du Booking (composables/useDataFilter).
// Les libellés des selects passent par les mêmes fonctions que les badges de
// la liste, sinon on filtrerait sur « clos » en lisant « Bookée » à l'écran.
const rfqFilterFields = [
  { key: 'q', label: 'Nom / référence', kind: 'text', width: 'w-full',
    get: r => [r.name, r.reference, r.template_type] },
  { key: 'status', label: 'Statut', kind: 'select', optionLabel: statusLabel },
  { key: 'kind', label: 'Type', kind: 'select', optionLabel: kindLabel },
  { key: 'sens', label: 'Sens', kind: 'select', optionLabel: sensLabel },
]
// Pas de filtre par fournisseur ici : GET /api/rfq ne renvoie pas les
// cotations (elles n'arrivent qu'avec le détail), le select serait vide.
// C'est l'écran Analyse qui porte la lecture par banque.

const rfqSorts = [
  { key: 'ao_date', label: 'Date d\'AO' },
  { key: 'name', label: 'Nom' },
  { key: 'reference', label: 'Référence' },
  { key: 'status', label: 'Statut' },
  { key: 'model_price', label: 'Prix modèle' },
]

const rfqList = computed(() => rfq.list)
const rfqFilter = useDataFilter(rfqList, rfqFilterFields, { sorts: rfqSorts })
const filteredRfqs = computed(() => rfqFilter.filtered.value)

const underlyingSummary = computed(() =>
  detailBasket[detailActiveUnderlyingIdx.value] || detailBasket[0] || {})
const underlyingSummaries = computed(() => detailBasket.map(row =>
  row.ticker || row.name).filter(Boolean))

// Même source que le "📡 Yahoo" du Pricer (pricing.js:loadYfOne) : vol
// réalisée 1 an et rendement du dividende. Saisir ces deux nombres à la main
// dans une RFQ alors que le sous-jacent est renseigné n'a pas de sens — et
// une vol tapée de mémoire fait un prix modèle dont l'écart aux cotations ne
// veut plus rien dire.
const createYfStatus  = ref('')
const createYfLoading = ref(false)
const detailYfStatus  = ref('')
const detailYfLoading = ref(false)

const marketRequests = new WeakMap()
let createMarketRevision = 0, detailMarketRevision = 0
watch(() => JSON.stringify([createBasket, createActiveUnderlyingIdx.value, form.pricing_date]),
  () => { createMarketRevision++ }, { flush:'sync' })
watch(() => JSON.stringify([detailBasket, detailActiveUnderlyingIdx.value, detailAdvanced.valuation_date, rfq.current?.id]),
  () => { detailMarketRevision++ }, { flush:'sync' })
async function _loadUnderlyingParams(ticker, target, status, loading, liveContext) {
  const tk = (ticker || '').trim().toUpperCase()
  if (!tk) { status.value = '⚠ Aucun ticker de sous-jacent'; return }
  const context = liveContext(), request = Symbol('market-request')
  marketRequests.set(status, request)
  const current = () => marketRequests.get(status) === request && liveContext() === context
  const asof = JSON.parse(context).asof
  loading.value = true
  status.value = `Chargement ${tk}…`
  try {
    const res = await apiFetch(`/api/finance/hist_vol?tickers=${encodeURIComponent(tk)}&period=1y&asof=${encodeURIComponent(asof)}`)
    const data = await res.json()
    if (!current()) {
      if (marketRequests.get(status) === request) status.value = '⚠ Réponse ignorée : le contexte a changé.'
      return
    }
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Erreur HTTP ${res.status}`)
    if (data.error) { status.value = `⚠ ${tk} : ${data.error}`; return }
    const vol = data.vols?.[tk] ?? null
    if (vol == null) {
      status.value = `⚠ ${tk} : introuvable sur Yahoo Finance`
      if (data.missing?.includes(tk)) status.value += ' — vérifiez le ticker'
      return
    }
    const q = data.dividend_profiles?.[tk]?.ok === false ? null : data.div_yields?.[tk]
    target.vol_level_source = 'realized'
    target.sigma = fractionToPercentExact(vol)
    if (q != null && Number.isFinite(q)) target.q = fractionToPercentExact(q)
    recordMarketReference(target, data, tk)
    status.value = q != null && Number.isFinite(q)
      ? `✓ ${tk} — σ=${target.sigma}%, q=${target.q}% · ${data.n_obs} obs.`
      : `⚠ ${tk} — σ chargée ; dividende inconnu, hypothèse q conservée.`
  } catch (e) {
    if (current()) status.value = '⚠ ' + e.message
  } finally {
    if (marketRequests.get(status) === request) loading.value = false
  }
}

function loadCreateUnderlyingParams() {
  const row = createBasket[createActiveUnderlyingIdx.value]
  return _loadUnderlyingParams(row?.ticker, row, createYfStatus, createYfLoading,
    () => JSON.stringify({asof: form.pricing_date || todayIso(), rows: createBasket, active: createActiveUnderlyingIdx.value,
      revision: createMarketRevision}))
}
function loadDetailUnderlyingParams() {
  return _loadUnderlyingParams(underlyingSummary.value.ticker, underlyingSummary.value,
                               detailYfStatus, detailYfLoading,
    () => JSON.stringify({asof: detailAdvanced.valuation_date || todayIso(), rows: detailBasket,
      active: detailActiveUnderlyingIdx.value, rfq: rfq.current?.id, revision: detailMarketRevision}))
}

// Latest CONSTAT schedule end date — empty when the script has no calendar
// at all (simple-mode indicatif), which is what tells the tenor derivation
// below whether there is a real maturity date to price against.
const detailCalendarEnd = computed(() => {
  const ends = detailScriptConstats.value
    .filter(c => c.role !== 'initial_fixing')
    .map(c => c.kind === 'single' ? (typeof detailConstatOverrides[c.name] === 'string' ? detailConstatOverrides[c.name] : detailConstatOverrides[c.name]?.date) : detailConstatOverrides[c.name]?.end_date)
    .filter(Boolean)
  return ends.length ? ends.reduce((max, d) => (d > max ? d : max)) : ''
})

// Same derivation rule as createMaturityDate/DealTab.vue: latest CONSTAT
// schedule end date when the script has one, else strike + T years. The
// engine's time axis starts at the strike — counting from the value date put
// the detail's maturity a few days after the one the AO was created with.
// AOs stored before the strike date existed fall back to the value date.
const detailMaturityDate = computed(() => {
  if (detailCalendarEnd.value) return detailCalendarEnd.value
  const p = rfq.current?.params || {}
  const origin = p.strike_date || p.value_date
  if (!origin || !p.T) return ''
  return addYears(origin, p.T)
})

// L'horizon du détail, pour la courbe de dividende : la même règle que
// `detailTermsPayload` — le calendrier fait foi, le T stocké prend le relais.
const detailHorizon = computed(() => (
  detailCalendarEnd.value && detailAdvanced.strike_date
    ? yearsBetween(detailAdvanced.strike_date, detailCalendarEnd.value)
    : (rfq.current?.params?.T ?? 1)
))

const fmtNominal = formatInt

// Une date saisie ne se déplace jamais en silence : le serveur la résout sur
// le calendrier de la devise, l'écran dit d'où elle vient et où elle va.
async function resolveFormDate(field) {
  dateNotices[field] = ''
  const value = form[field]
  const convention = form[`${field}_convention`]
  if (!value || !convention || convention === 'none') return
  try {
    const res = await apiFetch('/api/calendar/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: value, currency: form.currency, convention }),
    })
    if (!res.ok) return
    const data = await res.json()
    if (data.moved) {
      form[field] = data.date
      dateNotices[field] = `Ajustée depuis le ${data.source}, jour fermé sur le calendrier ${form.currency}.`
    }
  } catch { /* le champ garde ce qui a été saisi */ }
}

// Trois jours ouvrés après la dernière constatation : l'usage courant. Une
// proposition, jamais un écrasement — un term sheet qui dit autre chose gagne.
// Vrai dès que l'utilisateur saisit la date lui-même. Sans ce drapeau, le seul
// garde-fou était « le champ est-il vide » — qui ne distingue pas une saisie
// d'une proposition faite depuis une maturité qui a bougé depuis. La date se
// verrouillait donc sur la première maturité vue, souvent celle d'un calendrier
// à moitié rempli, et ne suivait plus jamais.
async function proposePaymentDate() {
  if (paymentDateSaisie.value || !createMaturityDate.value) return
  const maturity = createMaturityDate.value, currency = form.currency
  try {
    const res = await apiFetch('/api/calendar/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: maturity, currency,
                             business_days: 3 }),
    })
    const data = res.ok ? await res.json() : null
    if (data && !paymentDateSaisie.value && createMaturityDate.value === maturity && form.currency === currency)
      form.payment_date = data.date
  } catch { /* rien à proposer, le champ reste à saisir */ }
}

watch(createMaturityDate, proposePaymentDate)

/**
 * Ce qui manque encore, dans l'ordre du formulaire.
 *
 * Une SEULE liste de règles, lue par la barre d'actions et par la soumission :
 * deux listes finiraient par diverger, et le bouton refuserait pour une raison
 * que l'écran n'annonce pas.
 */
const champsManquants = computed(() => {
  const trous = []
  if (!form.name.trim()) trous.push('nom')
  if (form.source === 'template' && !form.template_type && !duplicateSourceScript.value) {
    trous.push('template')
  }
  if (form.source === 'script' && !form.script_id && !form.source_deal_id
      && !duplicateSourceScript.value) {
    trous.push('script')
  }
  createBasket.forEach((underlying, index) => {
    if (!underlying.ticker?.trim()) trous.push(`ticker du sous-jacent ${index + 1}`)
    if (!underlying.name?.trim()) trous.push(`nom du sous-jacent ${index + 1}`)
  })
  for (const [champ, libelle] of [['strike_date', 'date de strike'],
                                  ['value_date', 'date de valeur'],
                                  ['payment_date', 'date de paiement']]) {
    if (!form[champ]) trous.push(libelle)
  }
  if (form.kind === 'to_trade') {
    for (const calendar of scriptConstats.value) {
      const value = constatOverrides[calendar.name]
      if (calendar.kind === 'single') {
        const day = typeof value === 'string' ? value : value?.date
        if (!day) trous.push(`date du calendrier ${calendar.name}`)
        continue
      }
      for (const [field, label] of [[scriptConstats.value.some(c => c.role === 'initial_fixing') ? 'first_observation_date' : 'start_date', 'première observation'], ['end_date', 'fin'], ['frequency', 'fréquence']]) {
        if (!value?.[field] || (field === 'frequency' && !value.frequency.value)) trous.push(`${label} du calendrier ${calendar.name}`)
      }
      if (calendar.kind === 'nested_schedule' && !value?.sub_frequency) {
        trous.push(`sous-fréquence du calendrier ${calendar.name}`)
      }
    }
  }
  try { parameterValues(parsedParams.value, paramOverrides) } catch (e) { trous.push(e.message) }
  return trous
})

async function submitCreate() {
  createError.value = ''
  if (legacyPayoffFamily.value) {
    createError.value = 'Choisissez une famille de payoff du catalogue pour remplacer l’ancien libellé.'
    return
  }
  if (form.payoff_family === 'Autre' && !form.payoff_description.trim()) {
    createError.value = 'Décrivez le payoff lorsque la famille « Autre » est choisie.'
    return
  }
  if (champsManquants.value.length) {
    createError.value = `À compléter : ${champsManquants.value.join(', ')}`
    return
  }
  if (form.payment_date < form.value_date) {
    createError.value = 'La date de paiement ne peut pas précéder la date de valeur'; return
  }
  // Et surtout pas la MATURITÉ. Le contrôle ci-dessus comparait à la date de
  // valeur, ce qui laissait passer une maturité 2029 réglée en 2026 : trois ans
  // d'écart, sans un mot, jusqu'au refus de booking — et l'AO était alors
  // impossible à corriger, ses termes gelés par la première cotation reçue.
  // Le serveur refuse aussi ; ici c'est pour le dire avant d'envoyer.
  if (createMaturityDate.value && form.payment_date < createMaturityDate.value) {
    createError.value = `Le règlement (${fmtDateOnly(form.payment_date)}) précède la maturité `
      + `(${fmtDateOnly(createMaturityDate.value)}). La date de paiement date l'échange final `
      + `des flux : elle suit la dernière constatation.`
    return
  }
  const script_snapshot = currentScriptText()
  if (form.kind === 'to_trade' && !script_snapshot.includes('CONSTAT')) {
    createError.value = "Une RFQ 'to trade' nécessite un calendrier CONSTAT complet — choisissez un modèle ci-dessus."
    return
  }

  let user_params
  try { user_params = parameterValues(parsedParams.value, paramOverrides) }
  catch (error) { createError.value = error.message; return }

  creating.value = true
  try {
    const productMarket = sourceProductPricingInput.value || {}
    const horizon = createMaturityDate.value
      ? yearsBetween(form.strike_date, createMaturityDate.value) : form.T
    const calibrationContext=()=>({model:advanced.model,
      horizon:createMaturityDate.value?yearsBetween(form.strike_date,createMaturityDate.value):form.T,rate:advanced.r})
    const signature=()=>JSON.stringify([form,advanced,paramOverrides,constatOverrides,createCorrMatrix.value,
      currentScriptText(),sourceProduct.value,createBasket.map(u=>[u.ticker,u.ccy,u.sigma,u.q,u.vol_surface,u.smile_parameter_mode])])
    const initial=signature(),inputs=createBasket.slice()
    if (!sourceProduct.value) await Promise.all(inputs.map(u=>
      calibrateUnderlying(u,advanced.model,horizon,advanced.r,calibrationContext)))
    if(signature()!==initial || inputs.some((u,i)=>u!==createBasket[i]
      || (!sourceProduct.value && u.vol_surface && ['heston','sabr','lsv'].includes(advanced.model)
        && u.smile_parameter_mode!=='manual' && (u.smile_calibration?.status!=='ready'
          || u.smile_calibration.key!==surfaceCalibrationKey(u,advanced.model,horizon,advanced.r)))))
      throw Error('Le contexte a changé pendant la préparation de la RFQ. Relancez la création.')
    const basketPayload = createBasket.map((underlying, index) =>
      rfqUnderlyingToParams(
        underlying, ao.dividendeDuSousJacent(index, horizon)))
    const rfqObj = await rfq.create({
      pilot_desk_id: form.pilot_desk_id,
      previous_round_id: form.previous_round_id,
      product_id: sourceProduct.value?.product_id || null,
      product_terms_version: sourceProduct.value?.terms_version || null,
      name: form.name,
      ao_date: form.ao_date,
      kind: form.kind,
      sens: form.sens,
      // Le besoin client à l'origine, s'il y en a un. Null sinon — le cas
      // courant, et celui de tout l'existant.
      opportunity_id: form.opportunity_id,
      client_id: form.client_id,
      mandate_id: form.mandate_id,
      primary_affiliation_id: form.primary_affiliation_id,
      transaction_format: form.transaction_format || null,
      instrument_family: form.instrument_family || null,
      payoff_family: form.payoff_family || null,
      payoff_description: form.payoff_description || null,
      documentation_reference: form.documentation_reference || null,
      template_type: sourceProduct.value ? (sourceProduct.value.intent?.product_type || '') : form.source === 'template' ? form.template_type : '',
      script_id: form.source === 'script' ? form.script_id : null,
      script_snapshot,
      params: {
        underlyings: basketPayload,
        corr_matrix: normaliseCorrelation(createCorrMatrix.value, basketPayload.length),
        // T dérivé du calendrier CONSTAT quand il y en a un, et non du ténor
        // tapé : c'est la fin de calendrier que l'écran affiche comme maturité.
        // Laisser les deux diverger obligeait à « corriger » T à chaque calcul
        // de prix modèle — donc à toucher un terme contractuel après
        // sollicitation. T est fixé une fois, à la création, où il est encore
        // librement modifiable.
        r: sourceProduct.value ? (productMarket.r ?? advanced.r / 100) : advanced.r / 100,
        // T est l'horizon de DIFFUSION : il se compte depuis le strike, pas
        // depuis le règlement. Deux jours ouvrés d'écart avec l'ancienne
        // définition, mais surtout deux définitions différentes du symbole.
        T: horizon,
        N: sourceProduct.value ? (productMarket.N ?? advanced.N) : advanced.N,
        model: sourceProduct.value ? (productMarket.model || advanced.model) : advanced.model,
        valuation_date: form.pricing_date || todayIso(),
        // Les trois hypothèses de marché saisies au-dessus. Sans elles dans le
        // payload, les cartes seraient éditables sans le moindre effet sur le
        // prix — le projet a déjà connu ça avec la courbe de dividende, qui vaut
        // pourtant −491,6 bps.
        ...ao.hypothesesDeMarche(),
        ...(sourceProduct.value ? {
          yield_curve: productMarket.yield_curve || [],
          funding_curve: productMarket.funding_curve || [],
          funding_spread: productMarket.funding_spread || 0,
          sigma_r: productMarket.sigma_r || 0,
          a_r: productMarket.a_r || 0,
          barrier_monitoring: productMarket.barrier_monitoring || 'weekly',
        } : {}),
        user_params,
        constats: buildConstatsPayload(scriptConstats.value, constatOverrides),
        notional: nominalValue.value, currency: form.currency,
        strike_date: form.strike_date, value_date: form.value_date,
        maturity_date: createMaturityDate.value || null,
        payment_date: form.payment_date,
        // Traçabilité : les dates stockées sont déjà les dates effectives, la
        // convention dit seulement comment on y est arrivé.
        date_conventions: {
          strike_date: form.strike_date_convention,
          value_date: form.value_date_convention,
          payment_date: form.payment_date_convention,
        },
      },
    })
    showCreateForm.value = false
    await selectRfq(rfqObj.id)
    notice.value = 'RFQ créée'
  } catch (e) {
    createError.value = e.message
  } finally {
    creating.value = false
  }
}

// The only status the desk poses by hand: an AO that led nowhere. "auto"
// hands the RFQ back to the server-side derivation, which puts it at the
// stage its quotes actually justify (see api/rfq.py _derive_status).
async function toggleSansSuite() {
  if (rfq.current.status === 'sans_suite' && rfq.current.exchange_round) return
  listError.value = ''
  try {
    await rfq.update(rfq.current.id, {
      status: rfq.current.status === 'sans_suite' ? 'auto' : 'sans_suite',
    })
  } catch (e) {
    listError.value = e.message || 'Erreur mise à jour du statut'
  }
}

// Custom confirmation modal (BaseModal) instead of the native confirm() —
// no more disorienting native-browser flash, matches the app's own dialogs.
const showDeleteConfirm = ref(false)
const deleteTargetId    = ref(null)
const deleteTargetLabel = computed(() => {
  const r = rfq.list.find(x => x.id === deleteTargetId.value)
  return r?.name || r?.reference || `#${deleteTargetId.value}`
})

function deleteRfq(id) {
  deleteTargetId.value = id
  showDeleteConfirm.value = true
}

async function confirmDeleteRfq() {
  const id = deleteTargetId.value
  showDeleteConfirm.value = false
  listError.value = ''
  notice.value = ''
  try {
    await rfq.remove(id)
    if (selectedId.value === id) selectedId.value = null
    notice.value = 'RFQ supprimée'
  } catch (e) {
    listError.value = e.message || 'Erreur suppression'
  }
}

async function computeModelPrice() {
  const ticket=++computeRevision
  const id=rfq.current.id,context=mutationContext
  const inputs=detailBasket.slice()
  const calibrationContext=()=>({model:detailAdvanced.model,horizon:detailHorizon.value,rate:detailAdvanced.r})
  const initial=JSON.stringify(calibrationContext())
  computing.value = true
  computeError.value = ''
  try {
    // On n'envoie QUE les hypothèses de modèle. Les termes contractuels
    // (constats, dates, sous-jacents, user_params, T) restent côté serveur et
    // ne transitent pas : c'est ce qui permet de recalculer le prix modèle à
    // tout moment de la vie de l'AO, cotations reçues ou non.
    //
    // Auparavant ce bouton renvoyait le bloc complet reconstruit depuis le
    // formulaire. Rien de tout cela n'était une modification voulue, mais la
    // re-sérialisation ne retombait pas sur la valeur stockée : le contrôle de
    // gel se déclenchait sur cinq termes auxquels personne n'avait touché, et
    // l'AO devenait impossible à re-pricer. Le même remaniement réduisait au
    // passage un panier worst-of à son premier sous-jacent.
    //
    // sigma/q sont fusionnés par INDICE sur le panier stocké (voir
    // _merge_pricing_params) : la taille du panier vient de l'AO, pas du
    // formulaire de pricing.
    await Promise.all(inputs.map(u=>
      calibrateUnderlying(u,detailAdvanced.model,detailHorizon.value,detailAdvanced.r,calibrationContext)))
    if(ticket!==computeRevision) return
    if(context!==mutationContext || JSON.stringify(calibrationContext())!==initial
      || inputs.some((u,i)=>u!==detailBasket[i] || (u.vol_surface && ['heston','sabr','lsv'].includes(detailAdvanced.model)
        && u.smile_parameter_mode!=='manual' && (u.smile_calibration?.status!=='ready'
          || u.smile_calibration.key!==surfaceCalibrationKey(u,detailAdvanced.model,detailHorizon.value,detailAdvanced.r)))))
      throw Error('Le contexte a changé pendant la calibration. Relancez le calcul.')
    const pricingUnderlyings = detailBasket.map((underlying, index) => {
      const { name, ticker, ccy, ...assumptions } = rfqUnderlyingToParams(
        underlying, aoDetail.dividendeDuSousJacent(index, detailHorizon.value))
      return assumptions
    })
    const saved=await rfq.update(id, {
      pricing_params: {
        underlyings: pricingUnderlyings,
        corr_matrix: normaliseCorrelation(detailCorrMatrix.value, pricingUnderlyings.length),
        r: detailAdvanced.r / 100,
        N: detailAdvanced.N,
        model: detailAdvanced.model,
        valuation_date: detailAdvanced.valuation_date || todayIso(),
        // Hypothèses de modèle, donc admises par `_merge_pricing_params` :
        // elles n'appartiennent pas au périmètre contractuel gelé.
        ...aoDetail.hypothesesDeMarche(),
      },
    })
    if(context!==mutationContext || ticket!==computeRevision) return
    await rfq.computeModelPrice(saved || rfq.current)
  } catch (e) {
    if(context===mutationContext && ticket===computeRevision) computeError.value = e.message
  } finally {
    if(context===mutationContext && ticket===computeRevision) computing.value = false
  }
}

function openAddQuote() {
  quoteForm.provider = rfq.providers[0]?.label || 'autre'
  quoteForm.customProvider = ''
  quoteForm.contact = ''
  addingQuote.value = true
}

const availableQuoteContacts = computed(() =>
  rfq.providers.find(provider => provider.label === quoteForm.provider)?.contacts || [])
watch(() => quoteForm.provider, () => { quoteForm.contact = '' })

async function submitAddQuote() {
  const provider = quoteForm.provider === 'autre' ? (quoteForm.customProvider.trim() || 'Autre') : quoteForm.provider
  const id=rfq.current.id
  return runRfqMutation(()=>rfq.addQuote(id,{provider,contact:quoteForm.contact || null}),
    {label:'Ajout de fournisseur',success:()=>{addingQuote.value=false}})
}

async function removeQuote(quoteId) {
  const id=rfq.current.id
  return runRfqMutation(()=>rfq.removeQuote(id,quoteId),{label:'Suppression de la cotation'})
}

function updateQuoteField(q, field, value, element) {
  return saveQuoteField(q,field,value,{[field]:value},element)
}

function onQuotePriceChange(q, value, element) {
  const price = value === '' ? null : Number(value)
  const payload = { price }
  // First time a price is entered, log the response as received now unless
  // a date was already set explicitly.
  if (price !== null && !q.quoted_at) {
    payload.quoted_at = new Date().toISOString()
    withDefaultValidity(q, payload.quoted_at, payload)
  }
  return saveQuoteField(q,'price',value,payload,element)
}

function onQuoteDateChange(q, value, element) {
  const quotedAt = value ? new Date(value).toISOString() : null
  return saveQuoteField(q,'quoted_at',value,withDefaultValidity(q, quotedAt, { quoted_at: quotedAt }),element)
}

function onQuoteValidityChange(q, value, element) {
  return saveQuoteField(q,'valid_until',value,{ valid_until: value ? new Date(value).toISOString() : null },element)
}

const fmtDateOnly = formatDate

function providerLabel(id) {
  return rfq.providers.find(p => p.id === id)?.label || id
}

function fmtPrice(v) {
  return formatPercent(v)
}

const fmtDate = formatDateTime

// Écart de la cotation au prix modèle, signé de NOTRE côté : positif = en
// notre faveur. À l'achat la bonne réponse est celle qui cote SOUS le prix
// modèle (on paie moins), à la vente celle qui cote au-dessus. Miroir exact
// de _edge_bps côté backend (api/rfq.py), sur lequel la vue Analyse agrège.
function edgeBps(q) {
  const model = rfq.current?.model_price
  if (q.price === null || q.price === undefined || !model) return null
  const diff = rfq.current?.sens === 'vente' ? (q.price - model) : (model - q.price)
  return diff / model * 10000
}

function spreadBps(q) {
  const e = edgeBps(q)
  if (e === null) return '—'
  return (e >= 0 ? '+' : '') + formatBps(e, 0)
}

function spreadClass(q) {
  const e = edgeBps(q)
  if (e === null) return 'text-slate-600'
  return e >= 0 ? 'text-green-400' : 'text-red-400'
}

async function updateSens(value,element) {
  const id=rfq.current.id
  return runRfqMutation(()=>rfq.update(id,{sens:value}),{label:'Sens de la RFQ',field:'sens',value,element})
}

const mutationError=ref(''),rejectedMutation=ref(null)
let mutationContext=0
const mutationTickets=new Map()
watch([()=>rfq.current?.id,()=>selectedId.value],()=>{
  mutationContext++;detailLoadRevision++;computing.value=false
  mutationError.value='';rejectedMutation.value=null;addingQuote.value=false
},{flush:'sync'})
async function runRfqMutation(action,{label,field,quoteId,value,element,success}={}) {
  const id=rfq.current?.id,context=mutationContext,key=`${id}:${quoteId}:${field || label}`,ticket=Symbol()
  mutationTickets.set(key,ticket);mutationError.value='';rejectedMutation.value=null
  const current=()=>context===mutationContext && mutationTickets.get(key)===ticket
  try { await action();if(current()) success?.();return true }
  catch(e) {
    if(current()) {
      mutationError.value=`${label} refusé : ${e.message}`
      let reloadFailed=false
      try {reloadFailed=!(await rfq.fetchOne(id))} catch {reloadFailed=true}
      if(!current()) return false
      if(field) rejectedMutation.value={label,value,quoteId,field,reloadFailed}
      else if(reloadFailed) mutationError.value+=' Le dossier n’a pas pu être rechargé ; dernière version connue conservée.'
      if(element && field) {
        const saved=quoteId==null?rfq.current?.[field]:rfq.current?.quotes?.find(q=>q.id===quoteId)?.[field]
        element.value=field==='last_look'?(saved?'oui':'non'):
          ['quoted_at','valid_until'].includes(field)?toDatetimeLocal(saved):(saved ?? '')
      }
    }
    return false
  } finally {if(mutationTickets.get(key)===ticket) mutationTickets.delete(key)}
}
function saveQuoteField(q,field,value,payload,element) {
  const id=rfq.current.id
  const label={price:'Prix',status:'Statut',firmness:'Fermeté',quoted_at:'Date de réponse',valid_until:'Validité'}[field] || field
  return runRfqMutation(()=>rfq.updateQuote(id,q.id,payload),{label,field,quoteId:q.id,value,element})
}

// ── Last look ─────────────────────────────────────────────────────────

// The best competing price to date — the reference an existing responder is
// invited to match (or the desk uses to judge "close enough, give them the
// deal at their own price"). Which extreme wins depends on our side of the
// trade: cheapest when we buy, richest when we sell. Assuming the latter
// unconditionally (the previous behaviour) designates the WORST offer as best
// on a buy tender — this module's normal direction.
const bestQuote = computed(() => {
  const priced = (rfq.current?.quotes || []).filter(q => q.comparable)
  if (!priced.length) return null
  const selling = rfq.current?.sens === 'vente'
  return priced.reduce((best, q) =>
    (selling ? q.price > best.price : q.price < best.price) ? q : best)
})
const selectedQuote = computed(() => (rfq.current?.quotes || []).find(
  q => q.id === rfq.current?.selected_quote_id) || null)
const activeExecution = computed(() => rfq.current?.execution_agreements?.find(item => item.state !== 'CANCELLED'))
const confirmedExecution = computed(() => activeExecution.value?.state === 'CONFIRMED' && !activeExecution.value.review_required_reason)
const selectedIsBest = computed(
  () => !!selectedQuote.value && !!bestQuote.value
        && Math.abs(selectedQuote.value.price - bestQuote.value.price) <= 1e-9)

const selectionReasonCode = ref('')
const selectionReasonNote = ref('')
const selectionReasonError = ref('')
watch([
  () => rfq.current?.id,
  () => rfq.current?.selection_reason_code,
  () => rfq.current?.selection_reason_note,
], () => {
  selectionReasonCode.value = rfq.current?.selection_reason_code || ''
  selectionReasonNote.value = rfq.current?.selection_reason_note || ''
})
const selectionReasonChanged = computed(() => (
  selectionReasonCode.value !== (rfq.current?.selection_reason_code || '')
  || selectionReasonNote.value.trim() !== (rfq.current?.selection_reason_note || '')
))

async function saveSelectionReason() {
  selectionReasonError.value = ''
  try {
    await rfq.update(rfq.current.id, {
      selection_reason_code: selectionReasonCode.value || null,
      selection_reason_note: selectionReasonNote.value.trim() || null,
    })
  } catch (e) {
    selectionReasonError.value = e.message || 'Le motif n’a pas pu être enregistré.'
  }
}

// Le backend refuse à juste titre un booking sans prix modèle horodaté et
// relié au snapshot RFQ. Ne pas annoncer « prête à booker » avant que ces deux
// faits visibles existent : le contrôle cryptographique final reste côté
// serveur, mais l'utilisateur n'entre plus dans un parcours condamné d'avance.
const modelPriceRecorded = computed(() =>
  Number(rfq.current?.model_price) > 0 && !!rfq.current?.model_price_at)

async function onLastLookToggle(q, value,element) {
  const id=rfq.current.id
  return runRfqMutation(()=>rfq.toggleLastLook(id,q.id,value),
    {label:'Last look',field:'last_look',quoteId:q.id,value,element})
}

async function onSelectQuote(q) {
  const id=rfq.current.id
  const alreadySelected = rfq.current.selected_quote_id === q.id && rfq.current.selected_quote_revision === q.revision
  return runRfqMutation(()=>rfq.selectQuote(id,alreadySelected ? null : q.id),{label:'Sélection de la cotation'})
}

function bookFromRfq() {
  router.push({ path: `/rfq/${rfq.current.id}/booking` })
}

function openRfqPricer() {
  showExchange.value = false
  router.push({ path: '/pricer', query: { fromRfq: rfq.current.id, tab: 'economics' } })
}

// Deep link vers la fiche du deal dans la liste des deals bookés
// (BookingView lit ?deal=<id> et ouvre le détail directement).
function openBookedDeal() {
  router.push({ path: '/booking', query: { deal: rfq.current.booked_deal.id } })
}
watch(() => fixingDate(scriptConstats.value, constatOverrides), value => {
  if (scriptConstats.value.some(c => c.role === 'initial_fixing')) form.strike_date = value
}, { flush: 'sync' })
watch(() => fixingDate(detailScriptConstats.value, detailConstatOverrides), value => {
  if (detailScriptConstats.value.some(c => c.role === 'initial_fixing')) detailAdvanced.strike_date = value
}, { flush: 'sync' })

// Shared with the panels extracted in P1-10 (U3). Declared last: every
// binding below exists by now, and provide() still runs during setup.
provide(RFQ_CONTEXT, {
  activeExecution, addCreateUnderlying, addingQuote, advanced, ao, aoDetail, applyCreatePreset,
  availableQuoteContacts, bestQuote, bookFromRfq, commercialLinkEnabled, computeModelPrice,
  computing, confirmedExecution, constatOverrides, convertToTrade, createActiveUnderlyingIdx,
  createBasket, createCorrMatrix, createMaturityDate, createYfLoading, createYfStatus, dateNotices,
  deleteRfq, detailActiveUnderlyingIdx, detailAdvanced, detailBasket, detailConstatOverrides,
  detailCorrMatrix, detailHorizon, detailMaturityDate, detailParamOverrides, detailParsedParams,
  detailScriptConstats, detailTermsDirty, detailYfLoading, detailYfStatus, directClients,
  directContacts, directMandates, directOpportunities, duplicateRfq, fmtDate, fmtDateOnly,
  fmtNominal, fmtPrice, form, formatNominal, groupedTemplates, legacyPayoffFamily,
  legalCounterparties, legalDraft, legalReasons, librarySelectValue, loadCreateUnderlyingParams,
  loadDetailUnderlyingParams, modelPriceRecorded, mutationError, nominalRaw, onDirectClientChange,
  onDirectOpportunityChange, onKindToggle, onLastLookToggle, onLibrarySelect, onQuoteDateChange,
  onQuotePriceChange, onQuoteValidityChange, onSelectQuote, onSourceToggle, onTemplateChange,
  onUnderlyingSelect, openAddQuote, openAssignment, openBookedDeal, openShares, opportuniteContexte,
  paramOverrides, parsedParams, paymentDateSaisie, providerLabel, qualifyQuote, quoteForm,
  refreshDetailParams, reglementIncoherent, rejectedMutation, removeCreateUnderlying, removeQuote,
  resolveFormDate, rfq, saveDetailTerms, saveSelectionReason, savingTerms, scriptConstats,
  scriptedDeals, scripts, selectedIsBest, selectedQuote, selectionReasonChanged,
  selectionReasonCode, selectionReasonError, selectionReasonNote, showExchange, sourceProduct,
  spreadBps, spreadClass, submitAddQuote, termsError, toggleDirectCommercial, toggleSansSuite,
  underlyingSummaries, underlyingSummary, unformatNominal, updateQuoteField, updateSens,
})
</script>
