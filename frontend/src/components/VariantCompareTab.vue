<!-- Roll quantities and recovery use the original holder's nominal basis. -->
<template>
  <div class="flex flex-col gap-4">
    <div class="card">
      <div class="flex items-center gap-3 flex-wrap">
        <div>
          <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">
            ⑂ Comparaison des déclinaisons
            <HelpTip width="w-[26rem]" text="Chaque variante est valorisée sur la MÊME base de marché que l'origine — mêmes spots, mêmes vols, même date. C'est la raison d'être du modèle en delta : ce qu'une variante ne dit pas, elle l'hérite, donc l'écart de prix mesure la restructuration et rien d'autre. Le tirage est plus petit que celui de l'onglet Résultats : ce tableau classe, il ne publie pas." />
          </div>
          <div class="text-xs text-slate-600 mt-0.5 italic">
            Comparez les flux futurs ramenés au nominal d’origine, avec les hypothèses de financement affichées.
          </div>
        </div>
        <div class="ml-auto flex items-center gap-2">
          <select v-model.number="N" class="select text-xs w-28">
            <option :value="4000">4 000 chemins</option>
            <option :value="8000">8 000 chemins</option>
            <option :value="20000">20 000 chemins</option>
          </select>
          <button v-if="resultat?.preview && !archiveId" class="btn-secondary text-xs" :disabled="occupe" @click="figer">Figer l'étude</button>
          <span v-if="archiveId" class="text-xs text-green-400">Étude figée</span>
          <select v-if="archives.length" class="select text-xs" @change="ouvrirArchive($event.target.value)">
            <option value="">Études archivées…</option>
            <option v-for="archive in archives" :key="archive.archive_id" :value="archive.archive_id">{{ archive.created_at }}</option>
          </select>
          <button class="btn-primary text-xs px-4" :disabled="occupe || !variantes.length"
                  @click="comparer">
            <span v-if="occupe" class="w-3 h-3 border border-white border-t-transparent
                                        rounded-full animate-spin inline-block mr-1"></span>
            ▶ Comparer
          </button>
        </div>
      </div>
    </div>

    <fieldset v-if="variantes.some(v => v.variant_mode === 'roll')" class="card grid grid-cols-2 lg:grid-cols-4 gap-3"
              :disabled="occupe || !!archiveId">
      <legend class="text-xs font-semibold px-1">Financement des notes neuves</legend>
      <label class="text-xs">Sortie de l’origine
        <select v-model="financing.exit_basis" class="select w-full mt-1">
          <option value="model">Hypothèse au modèle</option>
          <option value="model_haircut">Modèle avec décote</option>
          <option value="observed_bid">Bid observé saisi</option>
        </select>
      </label>
      <label v-if="financing.exit_basis === 'model_haircut'" class="text-xs">Décote (points de prix)
        <input v-model.number="financing.haircut_points" type="number" min="0" step="0.01" class="input w-full mt-1" />
      </label>
      <template v-if="financing.exit_basis === 'observed_bid'">
        <label class="text-xs">Bid de cession hors frais (% du nominal d’origine)
          <input v-model.number="financing.bid_pct" type="number" min="0" step="0.01" class="input w-full mt-1" />
        </label>
        <label class="text-xs">Source du bid
          <input v-model.trim="financing.bid_source" class="input w-full mt-1" placeholder="Banque, référence de cotation…" />
        </label>
        <label class="text-xs">Bid observé le (heure locale)
          <input v-model="financing.bid_observed_at" type="datetime-local" step="0.001" class="input w-full mt-1" />
        </label>
      </template>
      <label class="text-xs">Frais de sortie (points du nominal d’origine)
        <input v-model.number="financing.exit_cost_points" type="number" min="0" step="0.01" class="input w-full mt-1" />
      </label>
      <label class="text-xs">Marge et frais d’entrée (points du nouveau nominal)
        <input v-model.number="financing.entry_cost_points" type="number" min="0" step="0.01" class="input w-full mt-1" />
      </label>
      <p class="col-span-full text-[11px] text-slate-500">Bid tout compris sur les droits cédés, avant les frais indiqués, dans la même devise et la même convention de valeur que le prix modèle. Le produit net de cession finance la nouvelle note au prix modèle augmenté de la marge et des frais d’entrée. Zéro signifie une hypothèse sans frais. Ces hypothèses ne modifient pas les avenants.</p>
    </fieldset>

    <AlertMessage v-if="erreur" kind="error" dismissible @dismiss="erreur = ''">{{ erreur }}</AlertMessage>
    <p v-if="resultat && resultat.comparison_schema_version !== 2" class="text-xs text-amber-500" role="status">Étude ancienne : les probabilités et prix archivés restent consultables. L’ancien « plafond » n’est pas qualifié et n’est pas présenté comme une borne contractuelle.</p>

    <div v-if="!variantes.length"
         class="flex flex-col items-center justify-center h-52 text-slate-600 gap-2">
      <div class="text-3xl">⑂</div>
      <div class="text-sm font-medium">Aucune déclinaison à comparer</div>
      <div class="text-xs">Créez-en une depuis la barre « Déclinaisons »</div>
    </div>

    <div v-else-if="!lignes.length"
         class="flex flex-col items-center justify-center h-52 text-slate-600 gap-2">
      <div class="text-3xl">📊</div>
      <div class="text-sm font-medium">
        Cliquez « Comparer » pour situer les {{ variantes.length }} déclinaison(s)
      </div>
      <div class="text-xs">L'origine est repricée en même temps, sur la même base</div>
    </div>

    <div v-else class="card overflow-x-auto">
      <table class="w-full text-xs">
        <thead>
          <tr class="text-slate-500 border-b border-slate-800">
            <th class="text-left py-2 pr-3 font-medium">Déclinaison</th>
            <th class="text-right py-2 px-3 font-medium">Prix modèle</th>
            <th class="text-right py-2 px-3 font-medium">
              Écart modèle
              <HelpTip text="Écart entre les prix modèle, avant bid et frais. Le financement du roll est calculé séparément avec le produit net de cession et le prix d’entrée, frais compris." />
            </th>
            <th class="text-right py-2 px-3 font-medium">
              P(pair d'origine)
              <HelpTip width="w-[26rem]" text="Probabilité que la somme des flux futurs non actualisés, multipliée par la quantité détenue, atteigne le nominal d’origine. La quantité d’une note neuve dépend du produit net de cession et de son prix d’entrée, frais compris. Ce n’est pas sa probabilité de rendre son propre pair." />
            </th>
            <th class="text-right py-2 px-3 font-medium">Nominal réinvesti
              <HelpTip text="Nouveau nominal divisé par le nominal d’origine. Produit net de cession / prix d’entrée. Ce rapport peut être inférieur ou supérieur à 100 % ; il ne plafonne pas le payoff." />
            </th>
            <th class="text-right py-2 px-3 font-medium">Récupération moyenne
              <HelpTip text="Moyenne simulée des flux futurs non actualisés, rapportés au nominal d’origine. Elle comprend les coupons futurs et le remboursement ; elle n’est ni une garantie, ni une valeur actuelle." />
            </th>
            <th class="text-right py-2 px-3 font-medium">
              Plafond contractuel établi
              <HelpTip text="Borne démontrée à partir du payoff, multipliée par la quantité détenue. Elle reste non établie lorsque cette démonstration n’est pas disponible. Le meilleur scénario Monte Carlo n’est jamais un plafond contractuel." />
            </th>
            <th class="text-right py-2 px-3 font-medium">Durée</th>
            <th class="text-right py-2 pl-3 font-medium">Δ</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(l, i) in classees" :key="l.id ?? 'origine'"
              class="border-b border-slate-800/50"
              :class="l.id === null ? 'bg-slate-800/30' : 'hover:bg-slate-800/20'">
            <td class="py-2 pr-3">
              <button v-if="l.id" class="text-slate-300 hover:text-blue-400 hover:underline text-left"
                      @click="router.push(`/pricer/v/${l.id}`)">{{ l.titre }}</button>
              <span v-else class="text-slate-400 font-medium">{{ l.titre }}</span>
              <span v-if="l.mode" class="ml-1.5 text-[9px] px-1 py-px rounded uppercase tracking-wide"
                    :class="l.mode === 'roll'
                      ? 'bg-violet-500/20 text-violet-300' : 'bg-slate-700 text-slate-400'">
                {{ l.mode === 'roll' ? 'note neuve' : 'avenant' }}
              </span>
              <div v-if="l.refus" class="text-[10px] text-red-400 mt-0.5">{{ l.refus }}</div>
              <div v-if="l.roll_financing" class="text-[10px] text-slate-500 mt-1">
                <template v-if="l.roll_financing.exit_evidence === 'OBSERVED_BID_INPUT'">
                  Bid saisi : <SensitiveValue>{{ pct(l.roll_financing.gross_exit_price) }}</SensitiveValue> · {{ l.roll_financing.bid_source }} · {{ l.roll_financing.bid_observed_at }}
                  <span v-if="l.roll_financing.bid_age_calendar_days"> · {{ l.roll_financing.bid_age_calendar_days }} jour(s) avant la valorisation</span>
                </template>
                <template v-else>Hypothèse modèle · {{ l.roll_financing.model_calculated_at }} · décote {{ l.roll_financing.haircut_points }} point(s)</template>
                <br />Net de cession : <SensitiveValue>{{ pct(l.roll_financing.net_exit_proceeds) }}</SensitiveValue> · entrée : <SensitiveValue>{{ pct(l.roll_financing.entry_unit_price) }}</SensitiveValue> · frais sortie {{ l.roll_financing.exit_cost_points }} / entrée {{ l.roll_financing.entry_cost_points }} point(s)
              </div>
            </td>
            <td class="text-right py-2 px-3 font-mono">
              <SensitiveValue>{{ pct(l.prix) }}</SensitiveValue>
            </td>
            <td class="text-right py-2 px-3 font-mono"
                :class="l.ecart == null ? 'text-slate-600'
                        : l.ecart < 0 ? 'text-green-400' : l.ecart > 0 ? 'text-red-400' : 'text-slate-500'">
              <SensitiveValue>{{ l.ecart == null ? '—' : signe(l.ecart) }}</SensitiveValue>
            </td>
            <td class="text-right py-2 px-3 font-mono"
                :class="meilleure === i ? 'text-amber-400 font-bold' : 'text-slate-300'">
              <SensitiveValue>{{ pct(l.proba_pair_origine, 1) }}</SensitiveValue>
            </td>
            <td class="text-right py-2 px-3 font-mono"><SensitiveValue>{{ pct(l.reinvested_notional) }}</SensitiveValue></td>
            <td class="text-right py-2 px-3 font-mono"><SensitiveValue>{{ pct(l.recovery_mean) }}</SensitiveValue></td>
            <td class="text-right py-2 px-3 font-mono"
                :class="l.plafond != null && l.plafond < 0.999 ? 'text-red-400' : 'text-slate-500'">
              <SensitiveValue>{{ l.plafond == null ? 'Non établi' : pct(l.plafond, 1) }}</SensitiveValue>
            </td>
            <td class="text-right py-2 px-3 font-mono text-slate-400">
              {{ l.duree == null ? '—' : nb(l.duree) + ' ans' }}
            </td>
            <td class="text-right py-2 pl-3 text-slate-600">{{ l.ecarts || '—' }}</td>
          </tr>
        </tbody>
      </table>

      <p class="text-[10px] text-slate-600 mt-3 leading-relaxed">
        Classé par probabilité de récupérer le pair d'origine.
        {{ resultat.N.toLocaleString('fr-FR') }} tirages demandés par ligne — tirage dédié,
        plus petit que celui de l'onglet Résultats : ce tableau classe, il ne publie pas.
        <span v-if="aUnRoll" class="block mt-1 text-amber-500/80">
          Le nominal réinvesti dépend des prix nets. La récupération porte sur les flux futurs du nouveau payoff ; un nominal inférieur au pair n’exclut pas une récupération supérieure à 100 %.
        </span>
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePricingStore } from '../stores/pricing.js'
import { apiFetch, apiErrorMessage } from '../utils/api.js'
import { comparisonRows, defaultRollFinancing, rollFinancingForm, rollFinancingPayload } from '../utils/rollEconomics.js'
import AlertMessage from './ui/AlertMessage.vue'
import SensitiveValue from './SensitiveValue.vue'
import HelpTip from './HelpTip.vue'

const store = usePricingStore()
const router = useRouter()

const N = ref(8000)
const variantes = ref([])
const resultat = ref(null)
const erreur = ref('')
const occupe = ref(false)
const archiveId = ref(null)
const archives = ref([])
let generation = 0
const financing = reactive(defaultRollFinancing())
let restoringInputs = false

function restoreInputs(values, paths = N.value) {
  restoringInputs = true
  try { Object.assign(financing, values); N.value = paths }
  finally { restoringInputs = false }
}

const parentId = computed(() =>
  store.variantInfo?.parent_id ?? store.currentScriptId ?? null)

async function charger() {
  const version = ++generation
  archiveId.value = null; archives.value = []; variantes.value = []; occupe.value = false
  resultat.value = null
  const saved = store.variantComparisonInputs
  if (saved && saved.parentId !== parentId.value) store.variantComparisonInputs = null
  restoreInputs(saved?.parentId === parentId.value ? saved.values : defaultRollFinancing(),
    saved?.parentId === parentId.value ? saved.N : 8000)
  if (!parentId.value) { variantes.value = []; return }
  try {
    const res = await apiFetch(`/api/db/scripts/${parentId.value}/variants`)
    const data = res.ok ? await res.json() : []
    if (version !== generation) return
    variantes.value = data
    await chargerArchives()
  } catch (e) { if (version === generation) erreur.value = e.message }
}
watch(parentId, charger, { immediate: true })

const lignes = computed(() => comparisonRows(resultat.value))

function retainInputs() {
  const values = JSON.parse(JSON.stringify(financing))
  store.variantComparisonInputs = JSON.stringify(values) === JSON.stringify(defaultRollFinancing()) && N.value === 8000
    ? null : { parentId: parentId.value, values, N: N.value }
}

watch(() => [JSON.stringify(financing), N.value], () => {
  if (restoringInputs || archiveId.value) return
  retainInputs()
  generation++; resultat.value = null; occupe.value = false; erreur.value = ''
}, { flush: 'sync' })

// Classé par ce qui décide : la probabilité de récupérer le pair d'origine.
// L'origine reste dans le classement — c'est la référence à battre, pas une
// ligne d'en-tête.
const classees = computed(() =>
  [...lignes.value].sort((a, b) => (b.proba_pair_origine ?? -1) - (a.proba_pair_origine ?? -1)))

const meilleure = computed(() =>
  classees.value.findIndex(l => l.proba_pair_origine != null))

const aUnRoll = computed(() => classees.value.some(l => l.mode === 'roll'))

async function comparer() {
  const version = ++generation
  if (!(await store.ensureScriptValidated())) {
    erreur.value = 'Le script ne valide pas : corrigez-le dans l’onglet Script.'
    return
  }
  if (version !== generation) return
  occupe.value = true; erreur.value = ''
  try {
    const res = await apiFetch('/api/variants/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // Le corps du PARENT tel que l'écran l'envoie pour son propre prix : les
      // variantes se posent dessus. Le reconstruire ici classerait des produits
      // que l'écran ne price pas.
      body: JSON.stringify({ base: store.inLifeBody(),
                              // L'origine que `base` décrit : le serveur refuse
                              // toute déclinaison qui n'en descend pas.
                              parent_id: parentId.value,
                              variant_ids: variantes.value.map(v => v.id),
                              N: N.value, roll_financing: rollFinancingPayload(financing) }),
    })
    const data = await res.json()
    if (version !== generation) return
    if (!res.ok) { erreur.value = apiErrorMessage(data, 'Comparaison impossible.'); return }
    resultat.value = data
    archiveId.value = null
    retainInputs()
  } catch (e) { if (version === generation) erreur.value = e.message }
  finally { if (version === generation) occupe.value = false }
}

async function chargerArchives() {
  const id = parentId.value
  const res = await apiFetch(`/api/variants/archives/${id}`)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Archives indisponibles.')
  if (parentId.value === id) archives.value = data
}

async function figer() {
  const preview = resultat.value?.preview
  if (!preview) return
  occupe.value = true; erreur.value = ''
  try {
    const res = await apiFetch('/api/variants/archives', {method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({preview})})
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Gel de l’étude impossible.')
    if (resultat.value?.preview !== preview) return
    archiveId.value = data.archive_id
    await chargerArchives()
  } catch (e) { if (resultat.value?.preview === preview) erreur.value = e.message }
  finally { occupe.value = false }
}

function ouvrirArchive(id) {
  const row = archives.value.find(item => item.archive_id === id)
  if (!row) return
  generation++
  restoreInputs(rollFinancingForm(row.evidence.request?.roll_financing || {}), row.evidence.result.N || 8000)
  resultat.value = row.evidence.result
  archiveId.value = row.archive_id
  erreur.value = ''
}

const pct = (v, d = 2) =>
  v == null ? '—' : `${(v * 100).toLocaleString('fr-FR',
    { minimumFractionDigits: d, maximumFractionDigits: d })} %`
const signe = v =>
  `${v >= 0 ? '+' : ''}${(v * 100).toLocaleString('fr-FR',
    { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const nb = v => Number(v).toLocaleString('fr-FR',
  { minimumFractionDigits: 2, maximumFractionDigits: 2 })
</script>
