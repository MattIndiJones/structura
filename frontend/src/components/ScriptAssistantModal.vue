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
        <div class="flex items-center gap-2 flex-wrap mb-1">
          <label class="label !mb-0">Décrivez le produit en français</label>
          <MicDictation v-model="description" :target-el="descriptionEl" class="ml-auto" />
        </div>
        <textarea ref="descriptionEl" v-model="description" rows="4" class="input font-normal"
                  :placeholder="placeholder"></textarea>
        <div class="text-[11px] text-slate-500 mt-1">
          Précisez maturité, fréquence d'observation, niveaux de barrière et coupon.
          Dites si une barrière est observée <strong>à tout moment</strong> ou
          seulement <strong>aux dates de constatation</strong> — c'est la
          différence entre deux produits qui ne valent pas le même prix.
        </div>
      </div>

      <AiWorkbench v-if="modelValue" ref="aiPanel" endpoint="/api/script/generate" preview-endpoint="/api/script/prompt"
        :payload="aiPayload" :disabled="aiPayload.description.trim().length < 3"
        :action-label="refinement.trim() && gen?.script ? 'Affiner le script' : 'Générer le script'"
        @busy="store.scriptGenLoading = $event" @result="store.scriptGen = $event" />
    </div>

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
          {{ gen.provider }} · {{ gen.effective_model || gen.model }} ·
          {{ Math.round(gen.elapsed_ms / 100) / 10 }} s
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
            <div class="flex items-center gap-1.5 mb-2 flex-wrap">
              <span class="badge" :class="gen.compiles ? 'badge-positive' : 'badge-negative'">
                {{ gen.compiles ? 'Compilation réussie' : 'Compilation échouée' }}
              </span>
              <span class="badge" :class="statutClasse(gen.pricing_check)">
                Contrôle financier · {{ statutLibelle(gen.pricing_check) }}
              </span>
              <span class="badge" :class="statutClasse(gen.checks_status)">
                Revue · {{ statutLibelle(gen.checks_status) }}
              </span>
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

    <label v-if="gen?.adoption_requires_acknowledgement && !gen.parse_error"
           class="flex items-start gap-2 rounded-lg px-3 py-2 text-xs cursor-pointer"
           style="background: var(--gold-light); border: 1px solid var(--gold);">
      <input v-model="warningsAcknowledged" type="checkbox" class="mt-0.5" />
      <span>
        J’ai lu les avertissements de la fiche de contrôle et je confirme que
        le script correspond au payoff demandé. Cette confirmation sera conservée
        dans sa provenance.
      </span>
    </label>

    <!-- Affinage -->
    <div v-if="gen && !gen.parse_error" class="flex flex-col gap-2 pt-1">
      <div class="flex items-center gap-2 flex-wrap">
        <label class="label !mb-0">Affiner sans repartir de zéro</label>
        <MicDictation v-model="refinement" :target-el="refinementEl" class="ml-auto" />
      </div>
      <div class="flex gap-2">
        <input ref="refinementEl" v-model="refinement" type="text" class="input text-xs"
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
      <button class="btn-primary text-xs" :disabled="loading || !canAdopt" @click="adopt">
        Adopter dans l'éditeur
      </button>
    </template>
  </BaseModal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import BaseModal from './ui/BaseModal.vue'
import AiWorkbench from './AiWorkbench.vue'
import HelpTip from './HelpTip.vue'
import MicDictation from './MicDictation.vue'
import { formatPercent, formatNumber } from '../utils/format.js'

const props = defineProps({ modelValue: { type: Boolean, required: true } })
const emit = defineEmits(['update:modelValue', 'adopted'])

const store = usePricingStore()
const description = ref('')
const refinement = ref('')
// Les champs eux-mêmes : la dictée s'insère à la position du curseur, elle a
// donc besoin de l'élément, pas seulement de sa valeur.
const descriptionEl = ref(null)
const refinementEl = ref(null)
const aiPanel = ref(null)
const warningsAcknowledged = ref(false)

const placeholder =
  'ex. : un autocall 3 ans sur le Nikkei, observation annuelle, rappel si '
  + "l'indice est au-dessus de son niveau initial, coupon 8 % par an cumulé, "
  + 'capital protégé sauf si le sous-jacent passe sous 60 % à un moment quelconque.'

const gen = computed(() => store.scriptGen)
const loading = computed(() => store.scriptGenLoading)
const canAdopt = computed(() => !!gen.value?.script && !gen.value?.parse_error
  && (!gen.value?.adoption_requires_acknowledgement || warningsAcknowledged.value))
const aiPayload = computed(() => store.scriptAssistantPayload({
  description: refinement.value.trim() && gen.value?.script ? refinement.value : description.value,
  refine: !!(refinement.value.trim() && gen.value?.script), currentScript: gen.value?.script || '',
}))

const icon = l => ({ ok: '✅', attention: '⚠️', info: 'ℹ️' }[l] || '•')
const cls = l => ({
  ok: 'text-[var(--positive)]',
  attention: 'text-[var(--gold)]',
  info: 'text-slate-400',
}[l] || '')
const statutClasse = s => ({
  passed: 'badge-positive', warning: 'badge-gold', failed: 'badge-negative',
  not_run: 'badge-muted',
}[s] || 'badge-muted')
const statutLibelle = s => ({
  passed: 'réussi', warning: 'à contrôler', failed: 'échoué',
  not_run: 'non exécuté',
}[s] || s)

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

watch(() => gen.value?.generation_id, () => { warningsAcknowledged.value = false; refinement.value = '' })
function runRefine() { if (refinement.value.trim()) aiPanel.value?.run() }

function adopt() {
  store.adoptGeneratedScript({ warningsAcknowledged: warningsAcknowledged.value })
  emit('adopted')
  emit('update:modelValue', false)
}
</script>
