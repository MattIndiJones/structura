<template>
  <div class="flex flex-col gap-6 p-1">

    <!-- Pas de résultat -->
    <div v-if="!store.result" class="text-center py-12 text-slate-600">
      <p class="text-sm">Lancez un pricing (▶ Pricer) pour calculer le marché cible.</p>
    </div>

    <!-- KID pas encore calculé — l'EMT dépend de son SRI, pas de recalcul indépendant -->
    <div v-else-if="!store.kid" class="text-center py-12 text-slate-600 flex flex-col items-center gap-3">
      <p class="text-sm max-w-md">
        Le marché cible reprend le SRI du KID PRIIPs (même risque affiché sur les deux documents).
        Calculez d'abord le KID.
      </p>
      <button class="btn-secondary text-xs px-4 py-2" @click="store.rightTab = 'kid'">
        ⚖ Aller au KID PRIIPs
      </button>
    </div>

    <template v-else>

      <!-- ── Paramètres (repris du KID) ────────────────────────── -->
      <div class="card">
        <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Paramètres EMT</h3>
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div class="bg-slate-800/40 rounded-lg px-3 py-2">
            <div class="text-slate-500 mb-1">SRI (repris du KID)</div>
            <div class="font-mono font-bold text-slate-200">{{ store.kid.sri }} / 7</div>
          </div>
          <div class="bg-slate-800/40 rounded-lg px-3 py-2">
            <div class="text-slate-500 mb-1">CRM (repris du KID)</div>
            <div class="font-mono font-bold text-slate-200">{{ store.kid.crm }} / 6</div>
          </div>
        </div>
        <div class="flex items-center gap-3 mt-3">
          <button class="btn-primary text-xs px-4 py-2" @click="compute" :disabled="loading">
            <span v-if="loading"
              class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1.5"></span>
            {{ loading ? 'Calcul…' : '🎯 Calculer le marché cible (EMT)' }}
          </button>
          <span v-if="error" class="text-xs text-red-400">⚠ {{ error }}</span>
        </div>
        <p class="text-[10px] text-slate-600 mt-3">
          Aide de desk — pas un export EMT FinDatEx conforme. Le type de client, le marché cible
          négatif et la stratégie de distribution restent des décisions commerciales à valider
          manuellement.
        </p>
      </div>

      <template v-if="emt">

        <!-- ── Profil auto-dérivé ───────────────────────────────── -->
        <div class="card">
          <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">
            Marché cible — profil auto-dérivé
          </h3>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">

            <div class="bg-slate-800/40 rounded-lg px-4 py-3">
              <div class="text-slate-500 mb-1">Connaissance &amp; expérience requise
                <HelpTip text="Déduit d'un score de complexité (rappel anticipé + multi-actifs + levier + barrière) croisé avec la capacité de perte — pas une catégorie officielle, une indication pour calibrer le test de connaissance/expérience du distributeur." />
              </div>
              <div class="font-semibold text-slate-100">{{ emt.knowledge_experience.label }}</div>
            </div>

            <div class="bg-slate-800/40 rounded-lg px-4 py-3">
              <div class="text-slate-500 mb-1">Capacité à supporter des pertes
                <HelpTip text="Dérivé du scénario de stress (P1) du KID à l'échéance — pas recalculé indépendamment, pour garantir que KID et EMT racontent la même histoire de risque sur ce produit." />
              </div>
              <div class="font-semibold" :class="capitalColorClass">{{ emt.capital_protection.label }}</div>
            </div>

            <div class="bg-slate-800/40 rounded-lg px-4 py-3">
              <div class="text-slate-500 mb-1">Tolérance au risque (SRI {{ emt.sri }}/7)
                <HelpTip text="Repris directement du SRI du KID — voir l'onglet KID PRIIPs pour le détail du calcul (VEV, MRM, CRM)." />
              </div>
              <div class="font-semibold text-slate-100">{{ emt.risk_tolerance }}</div>
            </div>

            <div class="bg-slate-800/40 rounded-lg px-4 py-3">
              <div class="text-slate-500 mb-1">Objectifs &amp; besoins
                <HelpTip text="Déduit de la présence ou non d'un mécanisme de rappel anticipé dans le script (recherche de rendement via coupon conditionnel vs recherche de performance pure sur le sous-jacent)." />
              </div>
              <div class="font-semibold text-slate-100">{{ emt.objective }}</div>
            </div>

            <div class="bg-slate-800/40 rounded-lg px-4 py-3 sm:col-span-2">
              <div class="text-slate-500 mb-1">Durée de détention recommandée
                <HelpTip text="Identique au T_rhp du KID (maturité du produit) — cohérence intentionnelle entre les deux documents." />
              </div>
              <div class="font-semibold text-slate-100">{{ formatNumber(emt.T_rhp, 1) }} an(s)</div>
            </div>
          </div>

          <!-- Caractéristiques détectées -->
          <div class="flex flex-wrap gap-2 mt-4 pt-4 border-t border-slate-800">
            <span v-for="f in featureTags" :key="f.label"
              class="text-[10px] px-2 py-1 rounded border"
              :class="f.on ? 'bg-amber-950/40 border-amber-800 text-amber-400' : 'bg-slate-800/40 border-slate-700 text-slate-600'">
              {{ f.on ? '✓' : '—' }} {{ f.label }}
            </span>
          </div>

          <p class="text-[10px] text-slate-600 mt-4 pt-3 border-t border-slate-800">
            SRI/CRM repris tels quels du KID déjà calculé — recalculez le KID si vous avez modifié
            les paramètres du produit, puis relancez l'EMT. Connaissance/expérience et capacité de
            perte sont des heuristiques basées sur la structure du script (rappel anticipé,
            multi-actifs, effet de levier, barrières) et le scénario de stress du KID — à valider
            par un compliance officer avant diffusion.
          </p>
        </div>

        <!-- ── Champs à compléter manuellement ─────────────────── -->
        <div class="card">
          <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
            À compléter — décisions commerciales
          </h3>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <div>
              <label class="label">Type de client cible
                <HelpTip text="Catégorie MiFID II du marché cible positif. Doit être cohérent avec la capacité de perte et le niveau de connaissance/expérience déterminés ci-dessus — un produit à capital non protégé et complexe se marie mal avec un marché cible 'Retail' sans réserve." />
              </label>
              <select v-model="manual.client_type" class="select text-xs">
                <option value="retail">Retail</option>
                <option value="professional">Professionnel</option>
                <option value="eligible">Contrepartie éligible</option>
                <option value="retail_professional">Retail + Professionnel</option>
              </select>
            </div>
            <div>
              <label class="label">Stratégie de distribution
                <HelpTip text="Canal(aux) via lesquels le produit peut être distribué. Impacte les obligations du distributeur (test d'adéquation en conseil vs simple test de pertinence en execution-only)." />
              </label>
              <select v-model="manual.distribution" class="select text-xs">
                <option value="advice">Avec conseil</option>
                <option value="advice_ni">Conseil non-indépendant</option>
                <option value="execution_only">Execution-only</option>
                <option value="portfolio_management">Gestion sous mandat</option>
              </select>
            </div>
            <div class="sm:col-span-2">
              <label class="label">Marché cible négatif
                <HelpTip width="w-72" text="Décrit explicitement pour qui ce produit n'est PAS adapté — l'exigence MiFID II symétrique au marché cible positif ci-dessus. Une omission ici n'est pas juste une case vide : c'est un vrai gap de gouvernance produit si le profil de risque du produit implique clairement des exclusions (ex: capital non garanti → exclure les clients sans tolérance à la perte)." />
              </label>
              <textarea v-model="manual.negative_target_market" rows="2" class="input text-xs"
                placeholder="Ex : clients ne pouvant supporter aucune perte en capital, horizon d'investissement inférieur à la maturité, absence d'expérience avec les produits dérivés…"></textarea>
            </div>
          </div>
        </div>

        <!-- ── Description du produit ──────────────────────────── -->
        <div class="card flex flex-col gap-4">
          <div>
            <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Description du produit</div>
            <div class="text-xs text-slate-600">Texte libre — sera intégré dans le PDF exporté.</div>
          </div>
          <textarea v-model="manual.description" rows="6"
            placeholder="Décrivez le mécanisme du produit (type de structure, sous-jacent(s), rappel anticipé, protection du capital…)…"
            class="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 text-xs text-slate-200 placeholder-slate-600 resize-y focus:outline-none focus:border-blue-500 leading-relaxed"></textarea>

          <!-- Génération IA -->
          <div class="border-t border-slate-800 pt-4 flex flex-col gap-3">
            <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Générer avec l'IA
              <HelpTip width="w-72" text="Envoie un résumé structuré du produit (paramètres, SRI, caractéristiques détectées) au provider choisi, avec une charte éditoriale dédiée à la rédaction de descriptions de payoff. Le texte généré est une proposition à relire, pas une description validée — vous gardez la main pour corriger avant de l'insérer." />
            </div>

            <div class="flex gap-2">
              <button v-for="p in [{id:'ollama',label:'Ollama'},{id:'claude',label:'Claude'},{id:'openai',label:'OpenAI'}]"
                :key="p.id"
                @click="aiProvider = p.id; aiPersist()"
                class="px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors"
                :class="aiProvider === p.id
                  ? 'bg-blue-600 border-blue-500 text-white'
                  : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'">
                {{ p.label }}
                <span v-if="p.id !== 'ollama'" class="ml-1 text-[9px] opacity-60">premium</span>
              </button>
            </div>

            <div v-if="aiProvider === 'ollama'" class="flex flex-col gap-2">
              <div class="flex gap-2">
                <input v-model="aiOllamaUrl" @blur="aiPersist" placeholder="http://localhost:11434"
                  class="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500" />
                <button @click="fetchOllamaModels"
                  class="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs rounded transition-colors shrink-0">
                  Détecter modèles
                </button>
              </div>
              <div v-if="aiOllamaModelsError" class="text-red-400 text-xs">⚠ {{ aiOllamaModelsError }}</div>
              <select v-if="aiOllamaModels.length" v-model="aiOllamaModel" @change="aiPersist"
                class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500">
                <option v-for="m in aiOllamaModels" :key="m" :value="m">{{ m }}</option>
              </select>
              <input v-else v-model="aiOllamaModel" @blur="aiPersist" placeholder="ex: llama3.3:70b"
                class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500" />
            </div>

            <div v-if="aiProvider === 'claude'" class="flex flex-col gap-2">
              <input v-model="aiClaudeKey" @blur="aiPersist" type="password" placeholder="sk-ant-api03-…"
                class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500" />
              <select v-model="aiClaudeModel" @change="aiPersist"
                class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500">
                <option value="claude-sonnet-4-6">claude-sonnet-4-6 (recommandé)</option>
                <option value="claude-opus-4-8">claude-opus-4-8</option>
                <option value="claude-haiku-4-5-20251001">claude-haiku-4-5 (rapide)</option>
              </select>
            </div>

            <div v-if="aiProvider === 'openai'" class="flex flex-col gap-2">
              <input v-model="aiOpenAiKey" @blur="aiPersist" type="password" placeholder="sk-…"
                class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500" />
              <select v-model="aiOpenAiModel" @change="aiPersist"
                class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500">
                <option value="gpt-4o">gpt-4o (recommandé)</option>
                <option value="gpt-4o-mini">gpt-4o-mini (rapide)</option>
              </select>
            </div>

            <div class="flex gap-2">
              <button @click="generateDescriptionAI" :disabled="aiGenerating"
                class="flex-1 py-2 px-4 text-xs font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
                :class="aiGenerating ? 'bg-slate-700 text-slate-500 cursor-not-allowed' : 'bg-emerald-700 hover:bg-emerald-600 text-white'">
                <span v-if="aiGenerating" class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                {{ aiGenerating ? 'Génération…' : '✨ Générer la description' }}
              </button>
              <button @click="copyBlockForExternalAI"
                class="px-3 py-2 text-xs font-semibold rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors">
                {{ copyBlockConfirm ? '✓ Copié' : '📋 Copier pour IA externe' }}
              </button>
              <HelpTip text="Copie dans le presse-papier la charte éditoriale + les données du produit en un seul bloc de texte, prêt à coller dans ChatGPT/Claude/Gemini web (ces interfaces n'ont pas de champ 'system prompt' séparé) — utile sans clé API ni Ollama local." />
            </div>

            <div v-if="aiError" class="text-red-400 text-xs bg-red-950/30 rounded p-2">⚠ {{ aiError }}</div>

            <div v-if="aiGeneratedText" class="flex flex-col gap-2">
              <div class="text-xs text-slate-500 font-semibold">Texte généré :</div>
              <div class="bg-slate-900 border border-emerald-800/40 rounded-lg p-3 text-xs text-slate-200 leading-relaxed whitespace-pre-wrap max-h-56 overflow-y-auto">{{ aiGeneratedText }}</div>
              <button @click="manual.description = aiGeneratedText"
                class="py-1.5 px-3 bg-blue-700 hover:bg-blue-600 text-white text-xs font-semibold rounded-lg transition-colors">
                ↑ Insérer dans la description
              </button>
            </div>
          </div>
        </div>

        <!-- ── Export ───────────────────────────────────────────── -->
        <div class="flex gap-3">
          <button class="btn-primary text-xs px-4 py-2 flex-1" @click="saveEmt" :disabled="saving">
            <span v-if="saving" class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin inline-block mr-1.5"></span>
            {{ saving ? 'Sauvegarde…' : (saveConfirm ? '✓ Sauvegardé' : '💾 Sauvegarder') }}
          </button>
          <button class="btn-secondary text-xs px-4 py-2 flex-1" @click="printEmt">
            🖨️ Imprimer / Exporter PDF
          </button>
        </div>
        <div v-if="saveError" class="text-xs text-red-400">⚠ {{ saveError }}</div>

      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { apiFetch } from '../utils/api.js'
import HelpTip from './HelpTip.vue'
import { formatNumber } from '../utils/format.js'

const store = usePricingStore()

const loading = ref(false)
const error   = ref('')
const emt     = ref(null)

const saving      = ref(false)
const saveError   = ref('')
const saveConfirm = ref(false)

const manual = ref({
  client_type: 'retail',
  distribution: 'advice',
  negative_target_market: '',
  description: '',
})

// ── AI generation state — shares the same localStorage keys as AmcView.vue
// so provider/keys configured there are already set here, no re-entry. ──
const aiProvider     = ref(localStorage.getItem('ai_provider')     || 'ollama')
const aiOllamaUrl    = ref(localStorage.getItem('ai_ollama_url')   || 'http://localhost:11434')
const aiOllamaModel  = ref(localStorage.getItem('ai_ollama_model') || '')
const aiClaudeKey    = ref(localStorage.getItem('ai_claude_key')   || '')
const aiClaudeModel  = ref(localStorage.getItem('ai_claude_model') || 'claude-sonnet-4-6')
const aiOpenAiKey    = ref(localStorage.getItem('ai_openai_key')   || '')
const aiOpenAiModel  = ref(localStorage.getItem('ai_openai_model') || 'gpt-4o')
const aiGenerating   = ref(false)
const aiError        = ref('')
const aiGeneratedText = ref('')
const aiOllamaModels  = ref([])
const aiOllamaModelsError = ref('')
const copyBlockConfirm = ref(false)

function aiPersist() {
  localStorage.setItem('ai_provider',     aiProvider.value)
  localStorage.setItem('ai_ollama_url',   aiOllamaUrl.value)
  localStorage.setItem('ai_ollama_model', aiOllamaModel.value)
  localStorage.setItem('ai_claude_key',   aiClaudeKey.value)
  localStorage.setItem('ai_claude_model', aiClaudeModel.value)
  localStorage.setItem('ai_openai_key',   aiOpenAiKey.value)
  localStorage.setItem('ai_openai_model', aiOpenAiModel.value)
}

async function fetchOllamaModels() {
  aiOllamaModelsError.value = ''
  try {
    const url = encodeURIComponent(aiOllamaUrl.value || 'http://localhost:11434')
    const res  = await apiFetch(`/api/amc/synthesize/ollama-models?url=${url}`)
    const data = await res.json()
    if (data.error) { aiOllamaModelsError.value = data.error; return }
    aiOllamaModels.value = data.models || []
    if (aiOllamaModels.value.length && !aiOllamaModel.value) {
      aiOllamaModel.value = aiOllamaModels.value[0]
    }
  } catch (e) {
    aiOllamaModelsError.value = `Ollama inaccessible à ${aiOllamaUrl.value}`
  }
}

function _synthesizeBody() {
  return {
    product_title:  productTitle.value,
    emt_result:     emt.value,
    script_params:  store.scriptParams,
    underlyings:    store.underlyings,
    provider:       aiProvider.value,
    ollama_url:     aiOllamaUrl.value,
    ollama_model:   aiOllamaModel.value,
    claude_key:     aiClaudeKey.value,
    claude_model:   aiClaudeModel.value,
    openai_key:     aiOpenAiKey.value,
    openai_model:   aiOpenAiModel.value,
  }
}

async function generateDescriptionAI() {
  if (!emt.value) return
  aiPersist()
  aiGenerating.value = true
  aiError.value = ''
  try {
    const res = await apiFetch('/api/emt/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(_synthesizeBody()),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Erreur ${res.status}`)
    }
    const data = await res.json()
    aiGeneratedText.value = data.synthesis || ''
  } catch (e) {
    aiError.value = e.message || 'Erreur inconnue'
  } finally {
    aiGenerating.value = false
  }
}

async function copyBlockForExternalAI() {
  if (!emt.value) return
  aiError.value = ''
  try {
    const res = await apiFetch('/api/emt/synthesize/payload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(_synthesizeBody()),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Erreur ${res.status}`)
    }
    const data = await res.json()
    await navigator.clipboard.writeText(data.copy_block || '')
    copyBlockConfirm.value = true
    setTimeout(() => { copyBlockConfirm.value = false }, 2000)
  } catch (e) {
    aiError.value = e.message || 'Erreur de copie'
  }
}

const capitalColorClass = computed(() => {
  const tier = emt.value?.capital_protection?.tier
  if (tier === 'garanti') return 'text-emerald-400'
  if (tier === 'partiel') return 'text-amber-400'
  if (tier === 'risque') return 'text-orange-400'
  return 'text-red-400'
})

const featureTags = computed(() => {
  if (!emt.value) return []
  const f = emt.value.features
  return [
    { label: 'Rappel anticipé (autocall)', on: f.has_autocall },
    { label: `Multi-actifs (${f.n_underlyings})`, on: f.has_worst_of },
    { label: 'Effet de levier', on: f.has_leverage },
    { label: 'Barrière', on: f.has_barrier },
  ]
})

const productTitle = computed(() => store.productTitle)

async function compute() {
  if (!store.result || !store.kid) return
  loading.value = true
  error.value = ''
  emt.value = null

  try {
    const lastHorizon = store.kid.horizons[store.kid.horizons.length - 1]
    const res = await apiFetch('/api/emt/compute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...store.pricingBody(),
        sri: store.kid.sri,
        mrm: store.kid.mrm,
        crm: store.kid.crm,
        stress_payoff_fraction: lastHorizon.stress.amount / 10000,
      }),
    })
    if (!res.ok) {
      const text = await res.text()
      try { const err = JSON.parse(text); throw new Error(err.detail || 'Erreur EMT') }
      catch { throw new Error(`Erreur ${res.status}: ${text.slice(0, 300)}`) }
    }
    emt.value = await res.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// ── Sauvegarde append-only — rattachée à la fiche Indicatif (créée à la
// volée au premier enregistrement, réutilisée ensuite pour ce pricing). ──
async function saveEmt() {
  if (!emt.value) return
  saving.value = true
  saveError.value = ''
  try {
    const indicativeId = await store.ensureIndicative()
    const res = await apiFetch('/api/emt/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        indicative_id: indicativeId,
        product_title: productTitle.value,
        sri: emt.value.sri, mrm: emt.value.mrm, crm: emt.value.crm, T_rhp: emt.value.T_rhp,
        capital_tier: emt.value.capital_protection.tier,
        capital_label: emt.value.capital_protection.label,
        knowledge_tier: emt.value.knowledge_experience.tier,
        knowledge_label: emt.value.knowledge_experience.label,
        risk_tolerance: emt.value.risk_tolerance,
        objective: emt.value.objective,
        features: emt.value.features,
        client_type: manual.value.client_type,
        distribution: manual.value.distribution,
        negative_target_market: manual.value.negative_target_market,
        description: manual.value.description,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Erreur ${res.status}`)
    }
    saveConfirm.value = true
    setTimeout(() => { saveConfirm.value = false }, 2000)
  } catch (e) {
    saveError.value = e.message || 'Erreur de sauvegarde'
  } finally {
    saving.value = false
  }
}

// ── Impression — document autonome, pas un screenshot de l'appli ──────
function printEmt() {
  if (!emt.value) return
  const e = emt.value
  const m = manual.value
  const today = new Date().toLocaleDateString('fr-FR')

  const clientTypeLabel = {
    retail: 'Retail', professional: 'Professionnel',
    eligible: 'Contrepartie éligible', retail_professional: 'Retail + Professionnel',
  }[m.client_type]

  const distributionLabel = {
    advice: 'Avec conseil', advice_ni: 'Conseil non-indépendant',
    execution_only: 'Execution-only', portfolio_management: 'Gestion sous mandat',
  }[m.distribution]

  const featureRows = featureTags.value
    .map(f => `<tr><td>${f.label}</td><td>${f.on ? 'Oui' : 'Non'}</td></tr>`)
    .join('')

  const html = `<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Marché cible — ${escapeHtml(productTitle.value)}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, Segoe UI, Arial, sans-serif; color: #1a1a1a;
         background: #fff; margin: 0; padding: 40px 56px; }
  header { display: flex; justify-content: space-between; align-items: baseline;
           border-bottom: 2px solid #1a1a1a; padding-bottom: 12px; margin-bottom: 24px; }
  header .brand { font-weight: 700; font-size: 14px; letter-spacing: .04em; }
  header .date { font-size: 11px; color: #555; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .subtitle { font-size: 12px; color: #555; margin-bottom: 28px; }
  h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: #444;
       border-bottom: 1px solid #ddd; padding-bottom: 6px; margin: 28px 0 12px; }
  table { width: 100%; border-collapse: collapse; font-size: 12.5px; margin-bottom: 4px; }
  td { padding: 7px 4px; border-bottom: 1px solid #eee; vertical-align: top; }
  td:first-child { color: #555; width: 46%; }
  td:last-child { font-weight: 600; }
  .description { font-size: 12.5px; line-height: 1.6; margin: 0 0 4px; }
  .disclaimer { font-size: 10px; color: #777; margin-top: 32px; padding-top: 12px;
                border-top: 1px solid #ddd; line-height: 1.5; }
  @media print { body { padding: 20px 32px; } }
</style>
</head>
<body>
  <header>
    <span class="brand">STRUCTURA</span>
    <span class="date">${today}</span>
  </header>
  <h1>Marché cible (EMT) — indicatif</h1>
  <div class="subtitle">${escapeHtml(productTitle.value)}</div>

  ${m.description ? `<h2>Description du produit</h2><p class="description">${escapeHtml(m.description)}</p>` : ''}

  <h2>Profil de marché cible</h2>
  <table>
    <tr><td>Connaissance &amp; expérience requise</td><td>${escapeHtml(e.knowledge_experience.label)}</td></tr>
    <tr><td>Capacité à supporter des pertes</td><td>${escapeHtml(e.capital_protection.label)}</td></tr>
    <tr><td>Indicateur de risque (SRI)</td><td>${e.sri} / 7</td></tr>
    <tr><td>Tolérance au risque</td><td>${escapeHtml(e.risk_tolerance)}</td></tr>
    <tr><td>Objectifs &amp; besoins</td><td>${escapeHtml(e.objective)}</td></tr>
    <tr><td>Durée de détention recommandée</td><td>${formatNumber(e.T_rhp, 1)} an(s)</td></tr>
  </table>

  <h2>Caractéristiques du produit</h2>
  <table>${featureRows}</table>

  <h2>Décisions commerciales</h2>
  <table>
    <tr><td>Type de client cible</td><td>${clientTypeLabel}</td></tr>
    <tr><td>Stratégie de distribution</td><td>${distributionLabel}</td></tr>
    <tr><td>Marché cible négatif</td><td>${escapeHtml(m.negative_target_market) || '—'}</td></tr>
  </table>

  <p class="disclaimer">
    Document indicatif généré à partir du script PayScript et du SRI du KID PRIIPs (CRM ${e.crm}/6).
    Ce n'est pas un export EMT FinDatEx conforme ni un document réglementaire final — le type de
    client, le marché cible négatif et la stratégie de distribution sont des décisions commerciales
    qui doivent être validées par la fonction compliance avant toute diffusion à un distributeur.
  </p>
</body>
</html>`

  const w = window.open('', '_blank')
  if (!w) return
  w.document.open()
  w.document.write(html)
  w.document.close()
  w.onload = () => w.print()
}

function escapeHtml(s) {
  if (!s) return ''
  return s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
}
</script>
