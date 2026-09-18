<template>
  <main class="explain-page">
    <header class="explain-header">
      <div><RouterLink :to="{ path: '/', query: { category: 'life_cycle' } }" class="eyebrow">← Life Cycle</RouterLink>
        <h1>Valo Explain</h1><p>Comprendre, commenter et partager une valorisation.</p></div>
      <RouterLink :to="bookingTarget" class="btn-secondary">Booking</RouterLink>
    </header>

    <div v-if="busy" class="progress-panel" role="status" aria-live="polite" :aria-busy="true">
      <span class="spinner" aria-hidden="true"></span><div><strong>{{ phase }}</strong>
        <p>{{ seconds }} s · Le traitement est en cours, vous pouvez suivre son étape ici.</p></div>
    </div>
    <p v-if="error" class="message error" role="alert">{{ error }}</p>
    <p v-if="saveError" class="message error" role="alert">{{ saveError }} Vos modifications restent dans l’éditeur.
      <button @click="saveNow" :disabled="busy || saving">Réessayer l’enregistrement</button></p>

    <section class="setup card">
      <div class="source-header">
        <label>Deal<select v-model="dealId" :disabled="busy" @change="loadRuns">
          <option value="">Sélectionner un deal</option>
          <option v-for="d in deals" :key="d.id" :value="String(d.id)">{{ d.reference }} · {{ d.contrepartie || d.product_type }}</option>
        </select></label>
        <div class="new-mtm"><button class="btn-secondary" :disabled="busy || !dealId" @click="calculateToday">Calculer un MtM du jour</button><small>Marché actuel · {{ localDay() }}</small></div>
      </div>
      <template v-if="dealId">
        <div class="source-toolbar"><div><h2>MtM enregistrés</h2><p>Du calcul le plus récent au plus ancien. Sélectionnez un calcul pour une note, deux pour une explication.</p></div>
          <div class="source-filters"><label>Base<select v-model="basisFilter" :disabled="busy"><option value="">Toutes</option><option value="booking">Paramètres du booking</option><option value="current">Marché actualisé</option></select></label>
            <label>Du<input v-model="dateFrom" type="date" :disabled="busy" /></label><label>Au<input v-model="dateTo" type="date" :disabled="busy" /></label></div>
        </div>
        <div v-if="!runs.length" class="empty">{{ busy ? 'Chargement des MtM…' : 'Aucun MtM enregistré pour ce deal. Lancez un calcul du jour pour commencer.' }}</div>
        <div v-else-if="!filteredRuns.length" class="empty">Aucun calcul ne correspond aux filtres. <button class="btn-secondary" @click="clearFilters">Réinitialiser les filtres</button></div>
        <div v-else class="source-table-wrap">
          <table class="source-table"><thead><tr><th scope="col" aria-label="Sélection"></th><th scope="col">Date du calcul</th><th scope="col">Date de valorisation</th><th scope="col" class="number">MtM (% du nominal)</th><th scope="col">Base de marché</th><th scope="col">Modèle</th></tr></thead>
            <tbody><tr v-for="r in filteredRuns" :key="r.id" :class="{ selected: selectedIds.includes(r.id) }" @click="!busy && toggleRun(r.id)">
              <td><input type="checkbox" :checked="selectedIds.includes(r.id)" :disabled="busy || (selectedIds.length === 2 && !selectedIds.includes(r.id))" :aria-label="`Sélectionner le calcul VR-${r.id}`" @click.stop @change="toggleRun(r.id)" /></td>
              <td>{{ dateTime(r.created_at) }}<small>VR-{{ r.id }}</small></td><td>{{ r.result.valuation_date || '—' }}</td>
              <td class="number"><SensitiveValue>{{ percent(r.result.mtm) }}</SensitiveValue></td><td><span class="badge">{{ basisLabel(r) }}</span></td><td>{{ modelLabel(r.result.market_used?.model) }}</td>
            </tr></tbody>
          </table>
        </div>
        <div class="source-selection" aria-live="polite">
          <div class="selection-top"><strong>{{ selectedRuns.length }} calcul{{ selectedRuns.length > 1 ? 's' : '' }} sélectionné{{ selectedRuns.length > 1 ? 's' : '' }} <span v-if="selectedRuns.length === 2">· maximum 2</span></strong>
            <button v-if="selectedRuns.length" class="btn-ghost" :disabled="busy" @click="resetSelection()">Effacer la sélection</button></div>
          <div v-if="selectedRuns.length" class="selection-flow">
            <template v-for="(r, i) in selectedRuns" :key="r.id">
              <button v-if="i === 1" class="btn-secondary invert" :disabled="busy" @click="invertSelection">⇄ Inverser</button>
              <article><span>{{ selectedRuns.length === 1 ? 'Valorisation retenue' : i === 0 ? 'Départ' : 'Arrivée' }} · VR-{{ r.id }}</span><strong><SensitiveValue>{{ percent(r.result.mtm) }}</SensitiveValue></strong><small>Au {{ r.result.valuation_date }} · calculé le {{ dateTime(r.created_at) }}</small></article>
            </template>
          </div>
          <p v-if="selectionChecking" role="status">Vérification des modèles et paramètres enregistrés…</p>
          <p v-if="selectionError" class="warn">{{ selectionError }} <button class="btn-ghost" @click="checkSelection">Réessayer</button></p>
          <ul v-if="selectionWarnings.length" class="warnings"><li v-for="w in selectionWarnings" :key="w">{{ w }}</li></ul>
          <div class="setup-footer"><p>{{ selectedRuns.length === 2 ? 'Le sens départ → arrivée définit la variation. La compatibilité complète sera contrôlée lors du calcul.' : selectedRuns.length === 1 ? 'La note reprendra ce calcul à sa date de valorisation.' : 'Cochez un ou deux calculs dans le tableau.' }}</p>
            <button class="btn-primary" :disabled="busy || selectionChecking || !!selectionError || !canGenerate" @click="generate">{{ selectedRuns.length === 2 ? 'Expliquer la variation' : 'Générer la note de valorisation' }}</button></div>
        </div>
      </template>
    </section>

    <section class="note-library card" v-if="notes.length">
      <label>Reprendre une note<select :value="note?.id || ''" :disabled="busy || saving" @change="openNote($event.target.value)">
        <option value="" disabled>Choisir parmi les 100 notes les plus récentes</option>
        <option v-for="n in notes" :key="n.id" :value="n.id">#{{ n.id }} · {{ n.title }} · {{ dealReference(n.deal_id) }} · {{ dateTime(n.updated_at) }}</option>
      </select></label><span>Les notes restent archivées indépendamment des MtM du jour affichés dans Booking.</span>
    </section>

    <template v-if="note">
      <section class="evidence card">
        <div class="section-title"><h2>{{ currentEvidence.data.deal.reference }}</h2><span class="badge">Chiffres archivés · non éditables</span></div>
        <div class="facts">
          <article v-for="r in note.evidence.runs" :key="r.run_id"><span>Valorisation au {{ r.data.mtm.valuation_date }}</span>
            <strong><SensitiveValue>{{ percent(r.data.mtm.mtm) }}</SensitiveValue></strong>
            <small>VR-{{ r.run_id }} · enregistré le {{ dateTime(r.created_at) }}</small>
            <small>{{ marketLabel(r.data.mtm.market_used) }}</small></article>
          <article v-if="comparison"><span>Variation du MtM</span><strong><SensitiveValue>{{ signed(comparison.delta_pts) }} pts</SensitiveValue></strong><small>Hors flux déjà payés · ce n’est pas le P&amp;L total</small></article>
        </div>
        <details v-if="comparison" class="method"><summary>{{ comparison.available ? 'Voir l’attribution calculée et sa méthode' : 'Attribution indisponible · consulter les limites' }}</summary>
          <table v-if="comparison.available"><thead><tr><th>Effet</th><th>Contribution (points)</th></tr></thead><tbody>
            <tr v-for="s in comparison.steps" :key="s.label"><td>{{ s.label }}</td><td>{{ signed(s.delta_pts, 4) }}</td></tr>
            <tr><td>Résidu non attribué</td><td>{{ signed(comparison.residual_pts, 4) }}</td></tr>
          </tbody></table><p>{{ comparison.methodology }}</p></details>
        <ul v-if="note.evidence.warnings.length" class="warnings"><li v-for="w in note.evidence.warnings" :key="w">{{ w }}</li></ul>
      </section>

      <div class="workspace">
        <section class="editor card">
          <div class="section-title"><h2>Commentaire de la note</h2><span role="status">{{ saving ? 'Enregistrement…' : dirty ? 'Modifications non enregistrées' : `Brouillon enregistré · révision ${note.revision}` }}</span></div>
          <label>Titre<input v-model="title" maxlength="160" :disabled="busy" /></label>
          <label v-for="s in sections" :key="s.key">{{ s.label }}
            <textarea v-model="draft[s.key]" :rows="s.key === 'analyse' ? 8 : 4" maxlength="12000" :disabled="busy" />
          </label>
          <div class="editor-actions"><button class="btn-secondary" :disabled="busy || saving || !dirty" @click="saveNow">Enregistrer</button>
            <button class="btn-primary" :disabled="busy || saving || !title.trim()" @click="freeze">Figer une version PDF</button></div>

          <details class="ai-panel"><summary>Aide à la rédaction par IA</summary>
            <p>Le passage sélectionné et les chiffres utiles seront envoyés au fournisseur choisi. Les champs client, contrepartie et nominal sont exclus du contexte automatique ; vérifiez les informations présentes dans votre texte.</p>
            <div class="ai-fields">
              <label>Passage<select v-model="ai.section" :disabled="busy"><option v-for="s in sections" :key="s.key" :value="s.key">{{ s.label }}</option></select></label>
              <label>Action<select v-model="ai.action" :disabled="busy"><option value="expliquer">Expliquer à partir des chiffres</option><option value="simplifier">Simplifier</option><option value="reformuler">Reformuler</option></select></label>
            </div>
            <AiWorkbench :key="note.id" :endpoint="`/api/valuation-notes/${note.id}/assist`" :payload="aiPayload"
              :context-key="signature" :before-prepare="flush" :disabled="busy || saving"
              action-label="Proposer un texte" @busy="busy = $event" @result="receiveAiSuggestion" />
            <div v-if="suggestion" class="suggestion"><strong>Proposition IA · à relire</strong><p>{{ suggestion.text }}</p>
              <small v-if="!canAccept">Le passage a changé depuis cette proposition. Relancez l’aide pour préserver vos modifications.</small>
              <div><button class="btn-primary" :disabled="busy || !canAccept" @click="acceptSuggestion">Accepter dans le passage</button><button class="btn-secondary" @click="suggestion = null">Écarter</button></div>
            </div>
          </details>
        </section>
        <section class="preview card">
          <div class="section-title"><h2>Aperçu PDF</h2><span v-if="previewStale" class="badge warn">Aperçu à actualiser</span></div>
          <div class="preview-actions"><button class="btn-secondary" :disabled="busy || saving" @click="refreshPreview">Actualiser le brouillon</button>
            <button class="btn-primary" :disabled="busy || !pdfUrl || previewStale" @click="download">Télécharger ce PDF</button></div>
          <label v-if="versions.length">Versions figées<select :value="previewVersion || ''" :disabled="busy" @change="showVersion($event.target.value)">
            <option value="">Brouillon actuel</option><option v-for="v in versions" :key="v.id" :value="v.id">Révision {{ v.revision }} · {{ dateTime(v.created_at) }}</option>
          </select></label>
          <p class="preview-caption">{{ previewVersion ? 'Version figée : le PDF téléchargé est celui affiché, conservé à l’identique.' : 'Brouillon : vérifiez le texte et les chiffres avant de figer une version.' }}</p>
          <p v-if="demo.enabled" class="empty">Aperçu masqué en mode démo.</p>
          <iframe v-else-if="pdfUrl" :src="pdfUrl" title="Aperçu de la note de valorisation" />
          <div v-else class="empty">{{ busy ? 'Préparation du document…' : 'Actualisez l’aperçu pour afficher votre note.' }}</div>
        </section>
      </div>
    </template>
    <section v-else-if="!busy" class="empty card">{{ dealId ? 'Le document apparaîtra ici après génération. Vous pouvez aussi reprendre un brouillon enregistré.' : 'Sélectionnez un deal pour préparer une note, ou reprenez un brouillon enregistré.' }}</section>
  </main>
</template>

<script setup>
import AiWorkbench from '../components/AiWorkbench.vue'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, RouterLink, useRoute, useRouter } from 'vue-router'
import SensitiveValue from '../components/SensitiveValue.vue'
import { useDemoModeStore } from '../stores/demoMode'
import { apiFetch } from '../utils/api'
import { localDay, readMtmResponse, runTimestamp } from '../composables/useBookingMtm'
import { noteJson, useValuationNoteDraft } from '../composables/useValuationNoteDraft'
import { useValuationRunSelection, runSelectionWarnings } from '../composables/useValuationRunSelection'

const route = useRoute(), router = useRouter(), demo = useDemoModeStore()
const { note, title, draft, dirty, saving, saveError, signature, load, flush, dispose } = useValuationNoteDraft()
const deals = ref([]), runs = ref([]), notes = ref([]), versions = ref([])
const dealId = ref(String(route.query.deal || ''))
const { ids: selectedIds, selected: selectedRuns, reset: resetSelection, toggle: toggleRun, invert: invertSelection } = useValuationRunSelection(runs)
const basisFilter = ref(''), dateFrom = ref(''), dateTo = ref('')
const selectionChecking = ref(false), selectionError = ref(''), selectionDetails = ref([])
let selectionEpoch = 0
const basisLabel = r => r.result.market_used?.source === 'booking' ? 'Paramètres du booking' : r.result.market_used?.source ? 'Marché actualisé' : 'Non renseignée'
const modelLabel = m => ({ constant: 'GBM', heston: 'Heston', sabr: 'SABR', localvol: 'Local Vol', lsv: 'LSV' }[m] || m || '—')
const filteredRuns = computed(() => runs.value.filter(r => {
  const date = r.result.valuation_date || ''
  return (!basisFilter.value || (basisFilter.value === 'booking' ? r.result.market_used?.source === 'booking' : r.result.market_used?.source && r.result.market_used.source !== 'booking'))
    && (!dateFrom.value || date >= dateFrom.value) && (!dateTo.value || date <= dateTo.value)
}).sort((a, b) => (runTimestamp(b.created_at)?.getTime() || 0) - (runTimestamp(a.created_at)?.getTime() || 0) || b.id - a.id))
const selectionWarnings = computed(() => runSelectionWarnings(selectionDetails.value.length === 2 ? selectionDetails.value : selectedRuns.value))
function clearFilters() { basisFilter.value = ''; dateFrom.value = ''; dateTo.value = '' }
async function checkSelection() {
  const epoch = ++selectionEpoch
  selectionDetails.value = []; selectionError.value = ''; selectionChecking.value = false
  if (selectedRuns.value.length !== 2) return
  selectionChecking.value = true
  try {
    const details = await Promise.all(selectedRuns.value.map(r => noteJson(`/api/deals/valuation-runs/${r.id}`)))
    if (epoch === selectionEpoch) selectionDetails.value = details
  } catch {
    if (epoch === selectionEpoch) selectionError.value = 'Impossible de vérifier les paramètres des deux calculs.'
  } finally { if (epoch === selectionEpoch) selectionChecking.value = false }
}
watch(() => selectedIds.value.slice().sort().join(','), checkSelection)
const busy = ref(false), phase = ref(''), seconds = ref(0), error = ref('')
const pdfUrl = ref(''), previewSignature = ref(''), previewVersion = ref(null)
const suggestion = ref(null)
let alive = true, clock, requestKey = '', requestInputs = ''
const sections = [{ key: 'synthese', label: 'Synthèse' }, { key: 'analyse', label: 'Analyse' }, { key: 'contexte', label: 'Contexte et limites' }, { key: 'conclusion', label: 'Conclusion' }]
const ai = reactive({ section: 'analyse', action: 'expliquer' })
const aiPayload = computed(() => ({ ...ai, revision: note.value?.revision }))
const currentEvidence = computed(() => note.value?.evidence.runs.at(-1))
const comparison = computed(() => note.value?.evidence.comparison)
const bookingTarget = computed(() => ({
  path: '/booking',
  query: dealId.value ? { deal: dealId.value } : {},
}))
const previewStale = computed(() => !!note.value && !previewVersion.value && previewSignature.value !== signature.value)
const canGenerate = computed(() => !!dealId.value && selectedRuns.value.length > 0)
const canAccept = computed(() => suggestion.value && suggestion.value.noteId === note.value?.id && suggestion.value.original === draft.value[suggestion.value.section])
const percent = v => `${(v * 100).toFixed(2)}%`
const signed = (v, n = 2) => `${v >= 0 ? '+' : ''}${v.toFixed(n)}`
const dateTime = v => runTimestamp(v)?.toLocaleString('fr-FR') || '—'
const dealReference = id => deals.value.find(d => d.id === id)?.reference || `Deal ${id}`
const marketLabel = m => `${m?.source === 'booking' ? 'Paramètres du booking' : m?.source ? 'Marché actualisé' : 'Source non renseignée'} · ${m?.model || 'Modèle non renseigné'}`
async function perform(label, action) {
  if (busy.value) return
  busy.value = true; error.value = ''; phase.value = label; seconds.value = 0
  clock = setInterval(() => seconds.value++, 1000)
  try { await action() } catch (e) { if (alive) error.value = e.message }
  finally { clearInterval(clock); busy.value = false }
}
async function fetchRuns() {
  runs.value = dealId.value ? await noteJson(`/api/valuation-notes/sources/${dealId.value}`) : []
}
async function loadRuns() {
  await perform('Lecture des calculs disponibles', async () => { resetSelection(); runs.value = []; clearFilters(); await fetchRuns() })
}
async function refreshLibrary() { notes.value = await noteJson('/api/valuation-notes') }
function clearPreview() {
  if (pdfUrl.value) URL.revokeObjectURL(pdfUrl.value)
  pdfUrl.value = ''; previewSignature.value = ''; previewVersion.value = null
}
async function fetchPdf(version = null) {
  phase.value = 'Mise en page de la note PDF'
  const snapshot = signature.value
  const response = await apiFetch(`/api/valuation-notes/${note.value.id}/pdf?${version ? `version_id=${version}` : `revision=${note.value.revision}`}`)
  if (!response.ok) { const e = await response.json(); throw new Error(e.detail || 'Erreur de génération du PDF') }
  const blob = await response.blob()
  if (!alive) return
  clearPreview()
  pdfUrl.value = URL.createObjectURL(blob); previewSignature.value = snapshot; previewVersion.value = version
}
async function selectNote(value) {
  clearPreview(); suggestion.value = null; load(value)
  dealId.value = String(value.deal_id)
  clearFilters()
  await fetchRuns()
  resetSelection(value.evidence.runs.map(r => r.run_id), true)
  versions.value = await noteJson(`/api/valuation-notes/${value.id}/versions`)
  await router.replace({
    path: '/valo-explain',
    query: { note: String(value.id), deal: String(value.deal_id) },
  })
  await fetchPdf()
}
async function openNote(id) {
  if (!id) return
  await perform('Ouverture de la note enregistrée', async () => { await flush(); await selectNote(await noteJson(`/api/valuation-notes/${id}`)) })
}
async function calculateToday() {
  await perform('Chargement des paramètres du marché du jour', async () => {
    await flush()
      phase.value = 'Chargement des paramètres du marché du jour'
      const labels = { history: 'Chargement des historiques', calibration: 'Chargement et calibration des paramètres du jour', pricing: 'Calcul de la valorisation', saving: 'Enregistrement du calcul' }
      const response = await apiFetch(`/api/deals/${dealId.value}/mtm?stream=true`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ recalibrate: 'realized', valuation_date: localDay() }) })
      const result = await readMtmResponse(response, p => phase.value = labels[p] || p)
      if (!result.valuation_run_id || result.resolved_pending || result.error) throw new Error(result.message || result.error || 'Ce deal ne dispose pas de valorisation exploitable.')
      await fetchRuns()
      clearFilters()
      resetSelection([result.valuation_run_id])
  })
}
async function generate() {
  if (!canGenerate.value) return
  await perform('Préparation de la note', async () => {
    await flush()
    await checkSelection()
    if (selectionError.value) throw new Error(selectionError.value)
    const ids = selectedRuns.value.map(r => r.id)
    const inputs = JSON.stringify([dealId.value, ids])
    if (inputs !== requestInputs) { requestInputs = inputs; requestKey = crypto.randomUUID() }
    const response = await apiFetch('/api/valuation-notes?stream=true', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ deal_id: Number(dealId.value), run_ids: ids, request_key: requestKey }) })
    const value = await readMtmResponse(response, p => phase.value = p, 'La préparation a été interrompue. Relancez la génération pour retrouver la note sans créer de doublon.')
    await selectNote(value); await refreshLibrary()
  })
}
async function saveNow() { await perform('Enregistrement du brouillon', async () => { await flush(); await refreshLibrary() }) }
async function refreshPreview() { await perform('Enregistrement et préparation du PDF', async () => { await flush(); await fetchPdf() }) }
async function showVersion(id) {
  await perform('Ouverture de la version PDF', async () => { await flush(); await fetchPdf(id ? Number(id) : null) })
}
async function freeze() {
  await perform('Création de la version PDF figée', async () => {
    await flush()
    const v = await noteJson(`/api/valuation-notes/${note.value.id}/versions`, { method: 'POST', body: JSON.stringify({ revision: note.value.revision }) })
    versions.value = await noteJson(`/api/valuation-notes/${note.value.id}/versions`)
    await fetchPdf(v.id); await refreshLibrary()
  })
}
function download() {
  const a = document.createElement('a'); a.href = pdfUrl.value
  a.download = `Valo_Explain_${note.value.id}_${previewVersion.value ? `version_${previewVersion.value}` : `revision_${note.value.revision}`}.pdf`; a.click()
}
function receiveAiSuggestion(data) {
  suggestion.value = { text: data.suggestion, section: data.section,
    original: draft.value[data.section], noteId: note.value.id }
}
function acceptSuggestion() { if (canAccept.value) { draft.value[suggestion.value.section] = suggestion.value.text; suggestion.value = null } }
function beforeUnload(e) { if (dirty.value || busy.value) { e.preventDefault(); e.returnValue = '' } }
onBeforeRouteLeave(async () => {
  if (busy.value) return false
  try { await flush(); return true } catch { return window.confirm('Le brouillon n’a pas été enregistré. Quitter et perdre les dernières modifications ?') }
})
onMounted(async () => {
  window.addEventListener('beforeunload', beforeUnload)
  await perform('Chargement de Valo Explain', async () => {
    const results = await Promise.all([noteJson('/api/deals'), noteJson('/api/valuation-notes')])
    deals.value = results[0]; notes.value = results[1]
    if (route.query.note) await selectNote(await noteJson(`/api/valuation-notes/${route.query.note}`))
    else if (dealId.value) {
      await fetchRuns()
      const ids = [route.query.run, route.query.run2].filter(Boolean).map(Number)
      resetSelection(ids, true)
      if (ids.some(id => !selectedIds.value.includes(id))) throw new Error('Un des calculs demandés est indisponible. Sélectionnez les MtM dans le tableau.')
    }
  })
  if (!error.value && !note.value && route.query.auto === '1' && canGenerate.value) await generate()
})
onBeforeUnmount(() => { alive = false; selectionEpoch++; clearInterval(clock); dispose(); clearPreview(); window.removeEventListener('beforeunload', beforeUnload) })
</script>

<style scoped>
.explain-page{flex:1;overflow-y:auto;width:100%;max-width:1520px;margin:auto;padding:28px 32px 60px;color:var(--text)}
.explain-header,.section-title,.setup-footer,.preview-actions,.editor-actions{display:flex;align-items:center;justify-content:space-between;gap:14px}
.explain-header{margin-bottom:24px}.explain-header h1{font-size:26px;font-weight:700;margin:5px 0}.eyebrow{font-size:11px;letter-spacing:.08em;color:var(--muted)}
p,small,.section-title>span,.note-library>span{font-size:12px;color:var(--muted);line-height:1.6}h2{font-size:14px;font-weight:650}
.card{padding:20px;border:1px solid var(--border);border-radius:12px;background:var(--surface);margin-bottom:18px}
.setup-fields,.ai-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.source-header,.source-toolbar,.selection-top{display:flex;align-items:center;justify-content:space-between;gap:18px}.source-header>label{flex:1;max-width:780px}.new-mtm{display:flex;flex-direction:column;align-items:flex-end;gap:5px}.source-toolbar{margin:22px 0 14px;align-items:flex-end}.source-filters{display:flex;gap:10px;flex-shrink:0}.source-filters input{max-width:145px}.source-table-wrap{overflow:auto;max-height:380px;border:1px solid var(--border);border-radius:8px}.source-table{width:100%;min-width:760px;border-collapse:separate;border-spacing:0;font-size:12px}.source-table th{position:sticky;top:0;z-index:1;background:var(--surface2);color:var(--muted);font-size:10px;letter-spacing:.04em;text-transform:uppercase;text-align:left;padding:11px 12px;white-space:nowrap}.source-table td{padding:11px 12px;border-top:1px solid var(--border);vertical-align:middle}.source-table td small{display:block;font-size:10px}.source-table .number{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.source-table tbody tr{cursor:pointer}.source-table tbody tr:hover{background:var(--surface2)}.source-table tr.selected{background:var(--accent-light)}.source-table input[type=checkbox]{width:15px;height:15px;accent-color:var(--accent);cursor:pointer}.source-selection{margin-top:14px;padding-top:14px;border-top:1px solid var(--border)}.selection-top{font-size:12px}.selection-top span{color:var(--muted);font-weight:400}.selection-flow{display:flex;align-items:center;gap:16px;margin:12px 0}.selection-flow article{flex:1;display:flex;flex-direction:column;gap:5px;border:1px solid var(--border);border-radius:8px;padding:12px;background:var(--surface2)}.selection-flow article>span{font-size:11px;color:var(--muted)}.selection-flow article>strong{font-size:20px;font-variant-numeric:tabular-nums}.selection-flow small{font-size:11px}
label{display:flex;flex-direction:column;gap:6px;font-size:11px;color:var(--muted)}
input,select,textarea{width:100%;min-width:0;background:var(--surface2);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:9px 10px;font-size:12px}
textarea{resize:vertical;line-height:1.65}input:focus,select:focus,textarea:focus{outline:2px solid #64748b;outline-offset:1px}
.setup-footer{margin-top:16px}.btn-primary,.btn-secondary{font-size:12px;white-space:nowrap}button:disabled{opacity:.45;cursor:not-allowed}
.note-library{display:flex;align-items:center;gap:22px}.note-library label{flex:1}.badge{font-size:10px;padding:4px 8px;border:1px solid var(--border);border-radius:5px}.warn,.warnings{color:#b77925}
.facts{display:flex;gap:40px;flex-wrap:wrap;margin-top:16px}.facts article{display:flex;flex-direction:column;gap:5px}.facts article>span{font-size:11px}.facts strong{font-size:27px;font-variant-numeric:tabular-nums}.warnings{font-size:11px;margin-top:16px;line-height:1.8;padding-left:18px;list-style:disc}
.method{margin-top:18px}.method table{width:100%;margin:12px 0;font-size:12px}.method th,.method td{text-align:left;padding:7px;border-bottom:1px solid var(--border)}.method th:last-child,.method td:last-child{text-align:right;font-variant-numeric:tabular-nums}
.workspace{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px}.workspace .card{min-width:0}.editor>label{margin-top:16px}.editor-actions{margin-top:18px}.preview{align-self:start;position:sticky;top:76px}.preview-actions{margin:16px 0;flex-wrap:wrap}.preview iframe{width:100%;height:820px;border:0;background:#fff;border-radius:6px}.preview-caption{margin:10px 0}
summary{cursor:pointer;font-size:12px;font-weight:600}.ai-panel{border-top:1px solid var(--border);margin-top:22px;padding-top:18px}.ai-panel>p{margin:12px 0}.ai-fields{margin:12px 0}.suggestion{margin-top:14px;padding:14px;border:1px solid var(--border);border-radius:8px}.suggestion p{white-space:pre-wrap;margin:10px 0}.suggestion>div{display:flex;gap:10px;margin-top:12px}
.progress-panel{position:sticky;top:0;z-index:20;box-shadow:var(--shadow-sm);display:flex;align-items:center;gap:14px;padding:16px 20px;background:var(--surface);border:1px solid #64748b;border-radius:10px;margin-bottom:18px}.progress-panel strong{font-size:13px}.spinner{width:22px;height:22px;border:2px solid #64748b;border-top-color:transparent;border-radius:50%;animation:spin 1s linear infinite;flex-shrink:0}@keyframes spin{to{transform:rotate(360deg)}}
.message{padding:14px;border-radius:8px;margin:12px 0}.error{color:#dc6565;border:1px solid #dc6565}.message button{text-decoration:underline;margin-left:12px}.empty{padding:40px;text-align:center;font-size:13px}
@media(max-width:1100px){.workspace{grid-template-columns:1fr}.preview{position:static}.preview iframe{height:700px}}
@media(max-width:1100px){.source-toolbar{align-items:flex-start;flex-direction:column}.source-filters{flex-wrap:wrap}}
@media(max-width:700px){.source-header,.selection-flow{align-items:stretch;flex-direction:column}.new-mtm{align-items:flex-start}.selection-flow .invert{align-self:center}.source-filters{width:100%}.source-filters label{flex:1;min-width:120px}.source-filters input{max-width:none}.source-table-wrap{max-height:340px}}
@media(max-width:700px){.explain-page{padding:18px 12px}.setup-fields,.ai-fields{grid-template-columns:1fr}.setup-footer,.note-library,.section-title{align-items:flex-start;flex-direction:column}.note-library label{width:100%}.facts{gap:20px}.explain-header{align-items:flex-start}.card{padding:15px}}
</style>
