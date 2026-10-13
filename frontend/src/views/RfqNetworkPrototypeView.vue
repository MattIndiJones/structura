<script setup>
import { computed, reactive, ref, shallowRef, watch } from 'vue'
import { RouterLink } from 'vue-router'
import AlertMessage from '../components/ui/AlertMessage.vue'
import BaseModal from '../components/ui/BaseModal.vue'
import { applyRfqPrototypeAction, createRfqPrototype, prototypeBestQuoteIds, prototypeCanSelect, prototypeEvents,
  prototypeQuoteStatus, prototypeRequestForBank } from '../utils/rfqNetworkPrototype.js'

const props = defineProps({ initialState: { type: Object, default: createRfqPrototype },
  initialPerspective: { type: String, default: 'requester' } })
const state = shallowRef(props.initialState)
const perspective = ref(props.initialPerspective)
const workspaceTab = ref('workflow')
const bankId = ref('bank-a')
const bank = computed(() => state.value.banks.find(item => item.id === bankId.value))
const selectedBanks = ref(['bank-a', 'bank-b'])
const notional = ref(1_000_000)
const side = ref('BUY')
const draft = reactive({ ...bank.value.draft })
const manual = reactive({ price: 98.7, firmness: 'FIRM', validityMinutes: 5, conditions: '', contact: 'Contact manuel démo' })
const confirmation = reactive({ source: 'BANK_MESSAGE', contact: '', executionReference: '' })
const busy = ref(false)
const error = ref('')
const showSend = ref(false)
const showManual = ref(false)
const showConfirmation = ref(false)
const withdrawal = ref(null)
const withdrawalReason = ref('')
const sharedContent = ref(null)
const selectedQuote = computed(() => state.value.quotes.find(quote => quote.id === state.value.selectedId))
const bestQuoteIds = computed(() => prototypeBestQuoteIds(state.value))
const bankQuotes = computed(() => state.value.quotes.filter(quote => quote.bankId === bankId.value))
const bankRequest = computed(() => prototypeRequestForBank(state.value, bankId.value))
const currentEvents = computed(() => prototypeEvents(state.value, perspective.value === 'bank' ? bankId.value : null).toReversed())
const draftChanged = computed(() => JSON.stringify(draft) !== JSON.stringify(bank.value.draft))
const reserved = computed(() => bankQuotes.value.some(quote => ['RESERVED', 'CONFIRMED'].includes(quote.status)))
const requesterStatus = computed(() => {
  if (state.value.booking) return 'Booké localement (simulé)'
  if (state.value.agreement?.status === 'CONFIRMED') return 'Traitement confirmé'
  if (state.value.agreement) return 'Confirmation attendue'
  if (selectedQuote.value) return prototypeCanSelect(selectedQuote.value, state.value.now) ? 'Réponse retenue' : 'Réponse à revoir'
  if (state.value.quotes.length) return 'Réponses reçues'
  return state.value.request ? 'Consultation envoyée' : 'Brouillon'
})
const labels = { ACTIVE: 'Active', EXPIRED: 'Expirée', WITHDRAWN: 'Retirée', REPLACED: 'Remplacée', RESERVED: 'Prix réservé',
  CONFIRMED: 'Traitement confirmé', NOT_SENT: 'Non sollicitée', RECEIVED: 'Demande reçue', QUOTED: 'Réponse publiée', DECLINED: 'Déclinée' }
const price = value => Number(value).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const amount = value => Number(value).toLocaleString('fr-FR')
const time = value => new Date(value).toLocaleTimeString('fr-FR', { timeZone: 'Europe/Berlin', hour: '2-digit', minute: '2-digit' })
const status = quote => prototypeQuoteStatus(quote, state.value.now)
watch(bankId, () => Object.assign(draft, bank.value.draft))

async function run(actions) {
  if (busy.value) return false
  busy.value = true
  error.value = ''
  try {
    for (const action of Array.isArray(actions) ? actions : [actions]) state.value = await applyRfqPrototypeAction(state.value, action)
    return true
  } catch (failure) {
    error.value = failure.message
    return false
  } finally { busy.value = false }
}
async function send() {
  if (await run({ type: 'SEND', bankIds: [...selectedBanks.value], notional: notional.value, side: side.value })) showSend.value = false
}
function validateBank() {
  const actions = draftChanged.value ? [{ type: 'SAVE_DRAFT', bankId: bankId.value, draft: { ...draft } }] : []
  return run([...actions, { type: 'VALIDATE', bankId: bankId.value, actor: 'PREPARER' }])
}
async function saveManual() {
  const { contact, ...quoteDraft } = manual
  if (await run({ type: 'MANUAL', contact, draft: { ...quoteDraft } })) showManual.value = false
}
async function withdraw() {
  if (await run({ type: 'WITHDRAW', bankId: bankId.value, quoteId: withdrawal.value.id, reason: withdrawalReason.value })) withdrawal.value = null
}
async function confirm() {
  if (await run({ type: 'CONFIRM', ...confirmation })) showConfirmation.value = false
}
function reset() {
  state.value = createRfqPrototype()
  perspective.value = 'requester'
  workspaceTab.value = 'workflow'
  bankId.value = 'bank-a'
  selectedBanks.value = ['bank-a', 'bank-b']
  notional.value = 1_000_000
  side.value = 'BUY'
  Object.assign(draft, bank.value.draft)
  Object.assign(manual, { price: 98.7, firmness: 'FIRM', validityMinutes: 5, conditions: '', contact: 'Contact manuel démo' })
  Object.assign(confirmation, { source: 'BANK_MESSAGE', contact: '', executionReference: '' })
  error.value = ''
  showSend.value = false
  showManual.value = false
  showConfirmation.value = false
  withdrawal.value = null
  sharedContent.value = null
}
</script>

<template>
  <div class="flex-1 min-h-0 flex flex-col overflow-hidden">
    <div class="shrink-0 max-h-[45%] overflow-y-auto overscroll-contain px-4 sm:px-6 pt-4 pb-3 space-y-3">
      <div class="page-header flex-wrap gap-3">
        <div>
          <h1 class="page-title">Parcours RFQ réseau</h1>
          <p class="text-xs text-slate-400 mt-1">Lot 0 · Maquette fonctionnelle sur données fictives</p>
        </div>
        <div class="page-actions flex-wrap">
          <RouterLink to="/rfq" class="btn-ghost btn-sm">RFQ Fournisseurs</RouterLink>
          <button class="btn-secondary btn-sm" :disabled="busy" @click="reset">Recommencer l’exercice</button>
        </div>
      </div>
      <AlertMessage kind="info">Exercice local : aucun message externe, calcul moteur ou booking réel. Les réponses manuelles restent disponibles dans le parcours RFQ habituel.</AlertMessage>
      <AlertMessage v-if="error" kind="error" dismissible @dismiss="error = ''">{{ error }}</AlertMessage>

      <section class="card flex flex-wrap items-end gap-4" aria-label="Perspective et horloge de l’exercice">
        <div class="flex gap-2" role="group" aria-label="Perspective de l’exercice">
          <button :class="perspective === 'requester' ? 'btn-primary' : 'btn-secondary'" :aria-pressed="perspective === 'requester'" @click="perspective = 'requester'; error = ''">Demandeur</button>
          <button :class="perspective === 'bank' ? 'btn-primary' : 'btn-secondary'" :aria-pressed="perspective === 'bank'" @click="perspective = 'bank'; error = ''">Banque</button>
        </div>
        <label v-if="perspective === 'bank'" class="space-y-1">
          <span class="label">Organisation bancaire fictive</span>
          <select v-model="bankId" class="select"><option v-for="item in state.banks" :key="item.id" :value="item.id">{{ item.name }}</option></select>
        </label>
        <div class="ml-auto flex flex-wrap items-center gap-2 text-xs">
          <span>Horloge de l’exercice : <strong>{{ time(state.now) }}</strong> · Paris</span>
          <button class="btn-ghost btn-sm" :disabled="busy" @click="run({ type: 'ADVANCE', minutes: 6 })">Avancer de 6 min</button>
        </div>
      </section>
      <div class="flex gap-2 xl:hidden" role="group" aria-label="Panneau de l’exercice">
        <button class="btn-ghost btn-sm" :aria-pressed="workspaceTab === 'workflow'" @click="workspaceTab = 'workflow'">Parcours</button>
        <button class="btn-ghost btn-sm" :aria-pressed="workspaceTab === 'context'" @click="workspaceTab = 'context'">Produit et historique</button>
      </div>
    </div>
    <main class="flex-1 min-h-0 overflow-hidden px-4 sm:px-6 pb-4">
      <div class="h-full min-h-0 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(300px,0.65fr)] gap-4">
        <div :class="['space-y-4 min-w-0 min-h-0 overflow-auto overscroll-contain pr-1', workspaceTab !== 'workflow' ? 'hidden xl:block' : '']">
          <template v-if="perspective === 'requester'">
            <section class="card space-y-4" aria-label="Préparer la consultation">
              <div class="flex items-center justify-between gap-3"><h2 class="font-semibold">ClientTech démo · Sales</h2><span class="badge badge-accent">{{ requesterStatus }}</span></div>
              <div class="grid sm:grid-cols-3 gap-3">
                <label><span class="label">Nominal (EUR)</span><input v-model.number="notional" type="number" min="1" class="input" :disabled="!!state.request" /></label>
                <label><span class="label">Sens du demandeur</span><select v-model="side" class="select" :disabled="!!state.request"><option value="BUY">Achat</option><option value="SELL">Vente</option></select></label>
                <div><span class="label">Limite de réponse · Paris</span><p class="text-sm py-2">{{ time(state.deadline) }}</p></div>
              </div>
              <fieldset class="space-y-2"><legend class="label mb-2">Destinataires de cette organisation fictive</legend>
                <label v-for="item in state.banks" :key="item.id" class="flex items-center gap-2 text-sm">
                  <input v-model="selectedBanks" type="checkbox" :value="item.id" :disabled="!!state.request" />
                  {{ item.name }} · {{ item.desk }} <span class="text-xs text-slate-400 ml-auto">{{ labels[item.status] }}</span>
                </label>
              </fieldset>
              <div class="flex flex-wrap gap-2">
                <button class="btn-primary" :disabled="busy || !!state.request || !selectedBanks.length" @click="showSend = true">Vérifier et envoyer la RFQ</button>
                <button class="btn-secondary" :disabled="!state.request || busy || !!state.agreement" @click="showManual = true">Saisir une réponse manuelle</button>
              </div>
              <p class="text-xs text-slate-400">L’envoi fige les termes du tour. Un accusé de réception n’est pas une cotation.</p>
            </section>

            <section class="card space-y-3" aria-label="Comparer les réponses">
              <h2 class="font-semibold">Réponses et sélection</h2>
              <p v-if="!state.quotes.length" class="text-sm text-slate-400">Aucun prix reçu. Passez côté banque pour contrôler puis publier une réponse.</p>
              <div v-else class="table-shell overflow-x-auto"><table>
                <thead><tr><th>Fournisseur / origine</th><th class="num">Prix all-in (%)</th><th>Fermeté / validité</th><th>État</th><th>Choix</th></tr></thead>
                <tbody><tr v-for="quote in state.quotes" :key="quote.id">
                  <td><strong>{{ quote.provider }}</strong><div>{{ quote.origin === 'MANUAL' ? 'Saisie manuelle' : 'Réception automatique' }} · v{{ quote.revision }}</div><p v-if="quote.conditions" class="text-amber-400 mt-1">Conditionnelle : {{ quote.conditions }}</p></td>
                  <td class="num font-mono">{{ price(quote.price) }}<div v-if="bestQuoteIds.includes(quote.id)" class="text-green-400 text-[10px]">Meilleur prix ferme actif</div></td>
                  <td>{{ quote.firmness === 'FIRM' ? 'Ferme' : 'Indicative' }}<div>Jusqu’à {{ time(quote.validUntil) }}</div></td>
                  <td>{{ labels[status(quote)] }}</td>
                  <td><button class="btn-ghost btn-sm" :disabled="busy || !!state.agreement || !prototypeCanSelect(quote, state.now)" @click="run({ type: 'SELECT', quoteId: quote.id })">{{ state.selectedId === quote.id ? 'Retenue' : 'Retenir' }}</button></td>
                </tr></tbody>
              </table></div>
              <p class="text-xs text-slate-400">La sélection reste locale et ne réserve pas le prix. Les révisions ne déplacent pas automatiquement le choix.</p>
            </section>

            <section v-if="selectedQuote" class="card space-y-3" aria-label="Traitement et confirmation">
              <h2 class="font-semibold">Traitement de la réponse retenue</h2>
              <p class="text-sm">{{ selectedQuote.provider }} · {{ price(selectedQuote.price) }} % · {{ amount(selectedQuote.notional) }} {{ selectedQuote.currency }} · réponse v{{ selectedQuote.revision }}</p>
              <AlertMessage v-if="state.agreement" :kind="state.agreement.status === 'CONFIRMED' ? 'success' : 'warning'">
                <template v-if="state.agreement.status === 'REQUESTED'">Acceptation reçue simulée à {{ time(state.agreement.acceptedAt) }}. Prix réservé, confirmation attendue.</template>
                <template v-else>{{ state.agreement.source === 'PHONE_DECLARED' ? 'Accord téléphonique déclaré' : 'Confirmation reçue de la banque' }} · {{ state.agreement.executionReference }}.<span v-if="state.agreement.writtenFollowUp"> Confirmation écrite à suivre.</span></template>
              </AlertMessage>
              <p v-if="!state.agreement && selectedQuote.firmness !== 'FIRM'" class="text-xs text-amber-400">Un indicatif nécessite un nouvel accord ; sa qualification bancaire ne sera pas modifiée.</p>
              <div class="flex flex-wrap gap-2">
                <button class="btn-primary" :disabled="busy || !!state.agreement || !prototypeCanSelect(selectedQuote, state.now) || selectedQuote.firmness !== 'FIRM' || !!selectedQuote.conditions"
                  @click="run({ type: 'ACCEPT' })">Simuler l’acceptation reçue</button>
                <button class="btn-secondary" :disabled="busy || state.agreement?.status !== 'REQUESTED'" @click="showConfirmation = true">Consigner la confirmation</button>
                <button class="btn-secondary" :disabled="busy || state.agreement?.status !== 'CONFIRMED' || !!state.booking" @click="run({ type: 'BOOK' })">Simuler le booking local</button>
              </div>
              <p v-if="state.booking" class="text-sm text-green-400">{{ state.booking.reference }} · booking local simulé à {{ time(state.booking.bookedAt) }}. Aucun rapprochement bancaire déduit.</p>
              <p class="text-xs text-slate-400">Validité contrôlée à l’acceptation. Un accord confirmé peut ensuite être inscrit après l’expiration de l’offre.</p>
            </section>
          </template>

          <template v-else>
            <section class="card space-y-3" aria-label="RFQ reçues par la banque">
              <div class="flex items-center justify-between gap-3"><h2 class="font-semibold">{{ bank.name }} · RFQ reçues</h2><span class="badge badge-muted">{{ labels[bank.status] }}</span></div>
              <p v-if="!bankRequest" class="text-sm text-slate-400">Aucune demande adressée à cette banque. Préparez puis envoyez la consultation côté demandeur.</p>
              <template v-else><p class="text-sm">{{ bankRequest.sender.organization }} · {{ bankRequest.title }}</p>
                <p class="text-sm">{{ bankRequest.side === 'BUY' ? 'Le demandeur achète ; la banque vend' : 'Le demandeur vend ; la banque achète' }} · {{ amount(bankRequest.notional) }} {{ bankRequest.currency }}</p>
                <div class="flex flex-wrap gap-2"><button class="btn-ghost btn-sm" @click="sharedContent = bankRequest">Inspecter la demande partagée</button>
                  <button class="btn-ghost btn-sm" :disabled="busy || bank.status !== 'RECEIVED'" @click="run({ type: 'DECLINE', bankId })">Décliner sans prix</button></div>
              </template>
            </section>

            <section v-if="bankRequest && bank.status !== 'DECLINED'" class="card space-y-4" aria-label="Préparer et publier la cotation">
              <h2 class="font-semibold">Calcul privé et réponse commerciale</h2>
              <div class="flex flex-wrap items-center gap-3"><button class="btn-secondary" :disabled="busy || reserved" @click="run({ type: 'CALCULATE', bankId })">Préparer le calcul fictif</button>
                <span v-if="bank.calculated" class="text-sm">Résultat fictif privé : <strong>{{ price(bank.modelPrice) }} %</strong></span></div>
              <p class="text-xs text-slate-400">Résultat d’exercice, sans calcul moteur ni données marché. Fraîcheur maximale du calcul dans cet exercice : {{ bank.freshnessMinutes }} min. Ce résultat privé ne part pas avec la réponse commerciale.</p>
              <div class="grid sm:grid-cols-3 gap-3">
                <label><span class="label">Prix commercial all-in (%)</span><input v-model.number="draft.price" type="number" min="0.01" step="0.01" class="input" :disabled="reserved" /></label>
                <label><span class="label">Fermeté publiée</span><select v-model="draft.firmness" class="select" :disabled="reserved"><option value="FIRM">Ferme</option><option value="INDICATIVE">Indicative</option></select></label>
                <label><span class="label">Validité (minutes)</span><input v-model.number="draft.validityMinutes" type="number" min="1" max="60" class="input" :disabled="reserved" /></label>
              </div>
              <label class="block"><span class="label">Conditions publiées · vide = aucune</span><textarea v-model="draft.conditions" class="input" rows="2" :disabled="reserved" /></label>
              <label class="flex items-center gap-2 text-sm"><input type="checkbox" :checked="bank.secondValidation" :disabled="busy || reserved" @change="run({ type: 'SECOND_VALIDATION', bankId, enabled: $event.target.checked })" />Seconde validation dans cet exercice</label>
              <AlertMessage v-if="reserved" kind="warning">Acceptation reçue : prix réservé. Révision et retrait RFQ ordinaires ne sont plus disponibles.</AlertMessage>
              <p v-else class="text-xs text-slate-400">{{ draftChanged ? 'Contenu modifié : nouveau contrôle nécessaire.' : bank.review?.publishedQuoteId ? 'Cette préparation a déjà été publiée ; un nouveau contrôle ouvre une révision.' : bank.review ? 'Contenu exact contrôlé ; publication humaine encore nécessaire.' : bank.awaitingReview ? 'En attente du second validateur.' : 'Aucun prix transmis avant contrôle et publication.' }}</p>
              <div class="flex flex-wrap gap-2">
                <button class="btn-secondary" :disabled="busy || !bank.calculated || reserved" @click="validateBank">{{ bank.secondValidation ? 'Soumettre à validation' : 'Contrôler la préparation' }}</button>
                <button v-if="bank.secondValidation" class="btn-secondary" :disabled="busy || !bank.awaitingReview || draftChanged || reserved" @click="run({ type: 'VALIDATE', bankId, actor: 'CHECKER' })">Simuler le second validateur</button>
                <button class="btn-primary" :disabled="busy || !bank.review || draftChanged || reserved || !!bank.review.publishedQuoteId" @click="run({ type: 'PUBLISH', bankId })">Publier la cotation</button>
              </div>
            </section>

            <section v-if="bankQuotes.length" class="card space-y-3" aria-label="Publications de cette banque">
              <h2 class="font-semibold">Publications de {{ bank.name }}</h2>
              <div v-for="quote in bankQuotes" :key="quote.id" class="border-t border-slate-800 pt-3 space-y-2">
                <p class="text-sm">v{{ quote.revision }} · {{ price(quote.price) }} % · {{ labels[status(quote)] }} · validité {{ time(quote.validUntil) }}</p>
                <div class="flex flex-wrap gap-2"><button class="btn-ghost btn-sm" @click="sharedContent = quote">Inspecter la réponse</button>
                  <button class="btn-danger btn-sm" :disabled="busy || status(quote) !== 'ACTIVE'" @click="withdrawal = quote; withdrawalReason = ''">Retirer avec motif</button></div>
              </div>
            </section>
          </template>
        </div>

        <aside :class="['min-w-0 min-h-0 flex-col gap-4', workspaceTab !== 'context' ? 'hidden xl:flex' : 'flex']">
          <section v-if="perspective === 'requester' || bankRequest" class="card space-y-3 shrink-0 max-h-[45%] overflow-auto overscroll-contain" aria-label="Termes communs du produit">
            <h2 class="font-semibold">Produit commun · termes v1</h2>
            <p class="text-sm">Athena LVMH · 3 ans · coupon fixé à 8 %</p>
            <dl class="terms-grid"><dt>Barrière de rappel</dt><dd>100 %</dd><dt>Protection à maturité</dt><dd>60 %</dd>
              <dt>Strike</dt><dd>{{ state.terms.dates.strike }}</dd><dt>Valeur</dt><dd>{{ state.terms.dates.value }}</dd>
              <dt>Maturité</dt><dd>{{ state.terms.dates.maturity }}</dd><dt>Paiement final</dt><dd>{{ state.terms.dates.payment }}</dd>
              <dt>Prix demandé</dt><dd>% du nominal · all-in</dd><dt>Calendrier</dt><dd>TARGET · Following · J+3 ouvrés</dd></dl>
            <p class="text-xs text-slate-400">Définition issue du modèle Athena du catalogue. Le script, les paramètres effectifs et les calendriers sont communiqués ; les hypothèses privées restent séparées.</p>
          </section>
          <section class="card flex-1 min-h-0 flex flex-col gap-3 overflow-hidden" aria-label="Historique du parcours">
            <h2 class="font-semibold">{{ perspective === 'bank' ? 'Historique de cette banque' : 'Historique du demandeur' }}</h2>
            <p v-if="!currentEvents.length" class="text-sm text-slate-400">Aucun événement dans cette perspective.</p>
            <ol v-else class="space-y-3 flex-1 min-h-0 overflow-auto overscroll-contain"><li v-for="event in currentEvents" :key="event.id" class="text-xs border-l-2 border-blue-800 pl-3">
              <time class="font-mono text-slate-400">{{ time(event.time) }} · #{{ event.id }}</time><p class="mt-1">{{ event.label }}</p>
            </li></ol>
          </section>
        </aside>
      </div>
    </main>

    <BaseModal v-model="showSend" title="Récapitulatif de la demande" max-width="640px">
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <p>Athena LVMH · termes v1 · coupon 8 % · nominal {{ amount(notional) }} EUR · {{ side === 'BUY' ? 'achat' : 'vente' }} du demandeur.</p>
      <p>Destinataires : {{ state.banks.filter(item => selectedBanks.includes(item.id)).map(item => item.name).join(', ') }}. Limite de publication : {{ time(state.deadline) }}.</p>
      <p class="text-xs text-slate-400">Chaque banque reçoit le même contrat, sans liste des concurrents ni données privées. Cet envoi reste fictif.</p>
      <template #footer><button class="btn-secondary" @click="showSend = false">Revenir</button><button class="btn-primary" :disabled="busy" @click="send">Envoyer dans l’exercice</button></template>
    </BaseModal>
    <BaseModal v-model="showManual" title="Réponse manuelle fictive" max-width="560px">
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <label class="block"><span class="label">Interlocuteur</span><input v-model="manual.contact" class="input" /></label>
      <label class="block"><span class="label">Prix all-in (% du nominal)</span><input v-model.number="manual.price" class="input" type="number" min="0.01" step="0.01" /></label>
      <label class="block"><span class="label">Fermeté déclarée</span><select v-model="manual.firmness" class="select"><option value="FIRM">Ferme</option><option value="INDICATIVE">Indicative</option></select></label>
      <label class="block"><span class="label">Validité déclarée (minutes)</span><input v-model.number="manual.validityMinutes" class="input" type="number" min="1" max="60" /></label>
      <template #footer><button class="btn-secondary" @click="showManual = false">Annuler</button><button class="btn-primary" :disabled="busy" @click="saveManual">Consigner la réponse</button></template>
    </BaseModal>
    <BaseModal v-model="showConfirmation" title="Confirmation économique fictive" max-width="560px">
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <p v-if="selectedQuote">{{ selectedQuote.provider }} · {{ price(selectedQuote.price) }} % · {{ amount(selectedQuote.notional) }} EUR · termes v1.</p>
      <label class="block"><span class="label">Provenance de l’accord</span><select v-model="confirmation.source" class="select"><option value="BANK_MESSAGE">Confirmation reçue de la banque</option><option value="PHONE_DECLARED">Accord téléphonique déclaré</option></select></label>
      <label class="block"><span class="label">Interlocuteur bancaire</span><input v-model="confirmation.contact" class="input" /></label>
      <label class="block"><span class="label">Référence d’exécution fictive</span><input v-model="confirmation.executionReference" class="input" placeholder="Ex. DEMO-EXEC-001" /></label>
      <p class="text-xs text-slate-400">Un accusé de livraison ne suffit pas. L’accord téléphonique conserve son origine et le suivi de confirmation écrite.</p>
      <template #footer><button class="btn-secondary" @click="showConfirmation = false">Revenir</button><button class="btn-primary" :disabled="busy" @click="confirm">Consigner l’accord fictif</button></template>
    </BaseModal>
    <BaseModal :model-value="!!withdrawal" title="Retirer la cotation" max-width="520px" @update:model-value="withdrawal = $event ? withdrawal : null">
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <p v-if="withdrawal">{{ withdrawal.provider }} · réponse v{{ withdrawal.revision }} · {{ price(withdrawal.price) }} %.</p>
      <label class="block"><span class="label">Motif communiqué</span><textarea v-model="withdrawalReason" class="input" rows="3" /></label>
      <template #footer><button class="btn-secondary" @click="withdrawal = null">Conserver</button><button class="btn-danger" :disabled="busy || !withdrawalReason.trim()" @click="withdraw">Retirer et notifier</button></template>
    </BaseModal>
    <BaseModal :model-value="!!sharedContent" title="Contenu partagé dans l’exercice" max-width="800px" @update:model-value="sharedContent = $event ? sharedContent : null">
      <p class="text-xs text-slate-400">Projection fictive visible par son destinataire. Les calculs privés ne sont pas inclus.</p>
      <pre class="payload">{{ JSON.stringify(sharedContent, null, 2) }}</pre>
    </BaseModal>
  </div>
</template>

<style scoped>
.terms-grid { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: .45rem 1rem; font-size: .75rem; }
.terms-grid dt { color: var(--muted); }
.terms-grid dd { font-variant-numeric: tabular-nums; text-align: right; }
.payload { background: var(--surface2); padding: 1rem; border-radius: var(--radius-sm); font-size: .72rem; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
