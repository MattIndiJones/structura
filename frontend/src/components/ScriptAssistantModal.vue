<!--
  Assistant de scripting IA.

  L'utilisateur décrit son produit en français, un modèle propose un script.
  Le script n'est JAMAIS appliqué automatiquement : le panneau de droite existe
  pour qu'on puisse le refuser. On y compare sa propre description à celle que
  le modèle redonne — bien plus rapide et plus sûr que de relire du PayScript —
  et on lit la fiche de contrôle, qui dit ce que le script fait vraiment.

  Le danger n'est pas le script qui ne compile pas : c'est celui qui compile,
  price, et décrit un autre produit.
-->
<template>
  <BaseModal :model-value="modelValue" max-width="1100px"
             title="✨ Assistant de scripting"
             @update:model-value="$emit('update:modelValue', $event)">

    <!-- Saisie -->
    <div class="flex flex-col gap-3">
      <div>
        <label class="label">Décrivez le produit en français</label>
        <textarea v-model="description" rows="4" class="input font-normal"
                  :placeholder="placeholder"></textarea>
        <div class="text-[11px] text-slate-500 mt-1">
          Précisez maturité, fréquence d'observation, niveaux de barrière et coupon.
          Dites si une barrière est observée <strong>à tout moment</strong> ou
          seulement <strong>aux dates de constatation</strong> — c'est la
          différence entre deux produits qui ne valent pas le même prix.
        </div>
      </div>

      <div class="flex items-end gap-2 flex-wrap">
        <div>
          <label class="label">Moteur</label>
          <select v-model="provider" class="select !w-auto text-xs">
            <option v-for="p in providers" :key="p.key" :value="p.key">
              {{ p.label }}{{ p.ready ? '' : ' — indisponible' }}
            </option>
          </select>
        </div>
        <div>
          <label class="label">Modèle
            <HelpTip v-if="provider === 'ollama'"
                     text="Liste des modèles réellement installés sur cette machine, relevée auprès d'Ollama. Après un `ollama pull`, cliquez sur ↻ pour rafraîchir." />
          </label>
          <div class="flex items-center gap-1">
            <select v-model="model" class="select !w-auto text-xs" :disabled="!currentModels.length">
              <option v-for="m in currentModels" :key="m" :value="m">{{ m }}</option>
              <option v-if="!currentModels.length" value="">aucun modèle</option>
            </select>
            <button class="icon-btn icon-btn-neutral" title="Re-sonder les modèles installés"
                    @click="refreshProviders">↻</button>
          </div>
        </div>
        <button class="btn-primary text-xs px-4 py-2 ml-auto"
                :disabled="loading || description.trim().length < 3 || !currentProvider?.ready"
                @click="run">
          <span v-if="loading"
                class="w-3 h-3 border border-white/60 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
          {{ loading ? 'Génération…' : '▶ Générer le script' }}
        </button>
      </div>

      <div v-if="recommendedMissing" class="text-[11px] text-slate-500">
        Modèle recommandé pour cet usage : <code>{{ currentProvider.recommended }}</code>
        — non installé. <code>ollama pull {{ currentProvider.recommended }}</code>, puis ↻.
      </div>

      <div v-if="privacyWarning" class="text-[11px] rounded-lg px-3 py-2"
           style="background: var(--gold-light); border-left: 3px solid var(--gold);">
        ⚠ La description part chez un tiers ({{ currentProvider?.label }}). Une idée
        de structuration quitte alors le desk. <strong>Ollama</strong> tourne en
        local et ne fait sortir aucune donnée.
      </div>
      <div v-if="currentProvider && !currentProvider.ready" class="text-[11px] text-amber-600">
        {{ currentProvider.hint }}
      </div>
    </div>

    <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>

    <!-- Prompt intégral -->
    <details class="card !p-3 text-xs" @toggle="onPromptToggle">
      <summary class="font-bold cursor-pointer text-slate-500 select-none">
        ▸ Voir le prompt envoyé au modèle
        <span v-if="promptInfo" class="font-normal text-slate-400 ml-1">
          — {{ promptInfo.chars.toLocaleString('fr-FR') }} caractères,
          ~{{ promptInfo.approx_tokens.toLocaleString('fr-FR') }} jetons
        </span>
      </summary>
      <div v-if="promptLoading" class="text-slate-500 mt-2">Construction du prompt…</div>
      <div v-else-if="promptInfo" class="mt-3 flex flex-col gap-3">
        <div class="text-[11px] text-slate-500">
          Le prompt dépend de votre description : les exemples joints sont choisis
          selon la famille de produit détectée. Modifiez la description puis
          rouvrez ce panneau pour voir le prompt correspondant.
        </div>
        <div>
          <div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">
            Exemples joints ({{ promptInfo.examples.length }})
          </div>
          <div class="flex flex-wrap gap-1">
            <span v-for="e in promptInfo.examples" :key="e" class="badge badge-muted">{{ e }}</span>
          </div>
        </div>
        <div>
          <div class="flex items-center gap-2 mb-1">
            <span class="text-[10px] uppercase tracking-wider text-slate-500">Message système</span>
            <button class="btn-secondary text-[10px] px-2 py-0.5 ml-auto"
                    @click="copy(promptInfo.system)">Copier</button>
          </div>
          <pre class="code-editor !min-h-0 overflow-auto text-[11px] whitespace-pre-wrap"
               style="max-height: 300px;">{{ promptInfo.system }}</pre>
        </div>
        <div>
          <div class="flex items-center gap-2 mb-1">
            <span class="text-[10px] uppercase tracking-wider text-slate-500">Message utilisateur</span>
            <button class="btn-secondary text-[10px] px-2 py-0.5 ml-auto"
                    @click="copy(promptInfo.user)">Copier</button>
          </div>
          <pre class="code-editor !min-h-0 overflow-auto text-[11px] whitespace-pre-wrap"
               style="max-height: 160px;">{{ promptInfo.user }}</pre>
        </div>
      </div>
      <div v-else class="text-slate-500 mt-2">Prompt indisponible.</div>
    </details>

    <!-- Résultat -->
    <div v-if="gen" class="grid lg:grid-cols-2 gap-4">

      <!-- Script -->
      <div class="flex flex-col gap-2">
        <div class="text-xs font-bold text-slate-500 uppercase tracking-wide">
          Script proposé
          <span v-if="gen.repairs" class="badge badge-muted ml-1">
            {{ gen.repairs }} correction automatique
          </span>
        </div>
        <pre class="code-editor !min-h-0 overflow-auto text-xs" style="max-height: 340px;"><code>{{ gen.script || '—' }}</code></pre>
        <div class="text-[11px] text-slate-500">
          {{ gen.provider }} · {{ gen.model }} · {{ Math.round(gen.elapsed_ms / 100) / 10 }} s
        </div>
      </div>

      <!-- Revue -->
      <div class="flex flex-col gap-3">
        <div v-if="gen.parse_error">
          <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-1">
            Le script ne compile pas
          </div>
          <pre class="text-[11px] rounded-lg px-3 py-2 whitespace-pre-wrap"
               style="background: var(--negative-light); color: var(--negative);">{{ gen.parse_error }}</pre>
          <div class="text-[11px] text-slate-500 mt-1">
            Reformulez, ou demandez un affinage en décrivant ce qui manque.
          </div>
        </div>

        <template v-else>
          <!-- Écho d'intention -->
          <div>
            <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-1">
              Ce que le modèle dit avoir construit
              <HelpTip text="Comparez cette reformulation à VOTRE description. C'est la vérification la plus rapide et la plus sûre : lire deux textes en français plutôt que relire du code. Si les deux ne disent pas la même chose, le script est faux même s'il compile et price." />
            </div>
            <div class="text-xs leading-relaxed rounded-lg px-3 py-2"
                 style="background: var(--accent-light); border-left: 3px solid var(--accent);">
              {{ gen.explanation || 'Le modèle n\'a pas fourni de reformulation.' }}
            </div>
          </div>

          <!-- Fiche de contrôle -->
          <div>
            <div class="text-xs font-bold text-slate-500 uppercase tracking-wide mb-1">
              Fiche de contrôle
            </div>
            <div class="flex flex-col gap-1">
              <div v-for="(c, i) in gen.checks" :key="i"
                   class="flex items-start gap-2 text-[11px] leading-snug">
                <span class="shrink-0 mt-px">{{ icon(c.level) }}</span>
                <span>
                  <strong :class="cls(c.level)">{{ c.label }}</strong>
                  <span class="text-slate-500"> — {{ c.detail }}</span>
                </span>
              </div>
            </div>
          </div>

          <!-- Profil -->
          <div v-if="gen.proba" class="grid grid-cols-2 gap-2">
            <div v-for="t in probaTiles" :key="t.label" class="stat-box !p-2">
              <div class="text-[10px] text-slate-500">{{ t.label }}</div>
              <div class="text-sm font-bold font-mono">{{ t.val }}</div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- Affinage -->
    <div v-if="gen && !gen.parse_error" class="flex flex-col gap-2 pt-1">
      <label class="label">Affiner sans repartir de zéro</label>
      <div class="flex gap-2">
        <input v-model="refinement" type="text" class="input text-xs"
               placeholder="ex. : la barrière de protection doit être observée en continu"
               @keyup.enter="runRefine" />
        <button class="btn-secondary text-xs px-3 whitespace-nowrap"
                :disabled="loading || !refinement.trim()" @click="runRefine">
          ↻ Affiner
        </button>
      </div>
    </div>

    <template #footer>
      <button class="btn-secondary text-xs" @click="$emit('update:modelValue', false)">
        Fermer
      </button>
      <button class="btn-primary text-xs" :disabled="!canAdopt" @click="adopt">
        Adopter dans l'éditeur
      </button>
    </template>
  </BaseModal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import BaseModal from './ui/BaseModal.vue'
import AlertMessage from './ui/AlertMessage.vue'
import HelpTip from './HelpTip.vue'
import { formatPercent, formatNumber } from '../utils/format.js'

const props = defineProps({ modelValue: { type: Boolean, required: true } })
const emit = defineEmits(['update:modelValue', 'adopted'])

const store = usePricingStore()
const description = ref('')
const refinement = ref('')
const provider = ref('ollama')
const model = ref('')

const placeholder =
  'ex. : un autocall 3 ans sur le Nikkei, observation annuelle, rappel si '
  + "l'indice est au-dessus de son niveau initial, coupon 8 % par an cumulé, "
  + 'capital protégé sauf si le sous-jacent passe sous 60 % à un moment quelconque.'

const gen = computed(() => store.scriptGen)
const loading = computed(() => store.scriptGenLoading)
const error = computed(() => store.scriptGenError)
const providers = computed(() => store.scriptProviders?.providers || [
  { key: 'ollama', label: 'Ollama (local)', ready: true, models: [], default_model: '' },
])
const currentProvider = computed(() => providers.value.find(p => p.key === provider.value))
const currentModels = computed(() => currentProvider.value?.models || [])
const privacyWarning = computed(() => provider.value !== 'ollama')
const canAdopt = computed(() => !!gen.value?.script && !gen.value?.parse_error)
const recommendedMissing = computed(() => {
  const p = currentProvider.value
  return !!(p && p.key === 'ollama' && p.ready && p.recommended
            && !p.models.includes(p.recommended))
})

// ── Prompt intégral ────────────────────────────────────────────────
const promptInfo = ref(null)
const promptLoading = ref(false)
let promptFor = null            // description pour laquelle promptInfo est valide

async function onPromptToggle(e) {
  if (!e.target.open) return
  // Le prompt dépend de la description : le recharger si elle a changé depuis
  // la dernière ouverture, sinon on afficherait le prompt d'une autre demande.
  const d = description.value.trim()
  if (promptInfo.value && promptFor === d) return
  promptLoading.value = true
  promptInfo.value = await store.previewScriptPrompt(d)
  promptFor = d
  promptLoading.value = false
}

async function copy(text) {
  try { await navigator.clipboard.writeText(text) } catch { /* navigateur restrictif */ }
}

async function refreshProviders() {
  const data = await store.loadScriptProviders(true)
  const p = data?.providers?.find(x => x.key === provider.value)
  if (p) model.value = p.default_model || ''
}

const icon = l => ({ ok: '✅', attention: '⚠️', info: 'ℹ️' }[l] || '•')
const cls = l => ({
  ok: 'text-[var(--positive)]',
  attention: 'text-[var(--gold)]',
  info: 'text-slate-400',
}[l] || '')

const probaTiles = computed(() => {
  const p = gen.value?.proba
  if (!p) return []
  return [
    { label: 'Rappel anticipé', val: formatPercent(p.autocall_pct, 1) },
    { label: 'Barrière touchée', val: formatPercent(p.ki_pct, 1) },
    { label: 'Perte en capital', val: formatPercent(p.capital_loss_pct, 1) },
    { label: 'Vie espérée', val: `${formatNumber(p.expected_life, 2)} Y` },
  ]
})

watch(() => props.modelValue, async (open) => {
  if (!open) return
  // Re-sondé à chaque ouverture, pas mis en cache : un `ollama pull` entre deux
  // ouvertures doit se voir, et la sonde est instantanée quand Ollama tourne
  // (le délai de 2,5 s ne joue que s'il est éteint).
  const data = await store.loadScriptProviders(true)
  if (data?.default) provider.value = data.default
  // Le watcher sur `provider` ne se déclenche pas si le moteur n'a pas changé :
  // sans cette ligne, le modèle resterait vide au premier affichage.
  model.value = currentProvider.value?.default_model || ''
  promptInfo.value = null                 // le prompt suit la description
})

// Changer de moteur remet le modèle sur celui par défaut : un nom de modèle
// Ollama envoyé à OpenAI produirait une erreur incompréhensible.
watch(provider, () => { model.value = currentProvider.value?.default_model || '' })

function run() {
  if (!description.value.trim() || loading.value) return
  store.generateScript({ description: description.value, provider: provider.value,
                         model: model.value })
}

function runRefine() {
  if (!refinement.value.trim() || loading.value) return
  // L'affinage porte sur le script PROPOSÉ, pas sur celui de l'éditeur : rien
  // n'a encore été adopté à ce stade.
  store.generateScript({
    description: refinement.value, provider: provider.value, model: model.value,
    refine: true, currentScript: gen.value?.script || '',
  })
  refinement.value = ''
}

function adopt() {
  store.adoptGeneratedScript()
  emit('adopted')
  emit('update:modelValue', false)
}
</script>
