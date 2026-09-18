<!--
  Onglet Résumé — description écrite du produit, copiable.

  Brique 1 sur trois. Elle doit tenir debout SANS IA : c'est déjà le début
  d'un term sheet ou d'une note client. L'envoi à un modèle viendra se brancher
  sur exactement ce texte, sans le reconstruire — un résumé affiché et un
  résumé envoyé qui divergeraient seraient pires que pas de résumé du tout.
-->
<template>
  <div class="flex flex-col gap-4">
    <div v-if="!resume.ok"
         class="flex flex-col items-center justify-center h-64 text-slate-600 gap-3">
      <div class="text-4xl">📝</div>
      <div class="text-sm font-medium">{{ resume.raison }}</div>
    </div>

    <template v-else>
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">
            Résumé du produit
            <HelpTip width="w-96" text="Description écrite du produit tel qu'il a été pricé — payoff en PayScript, calendrier, sous-jacents et leur calibration, hypothèses de marché avec leur provenance, prix et risque. Générée depuis l'instantané qui a produit le prix affiché, jamais depuis l'écran courant : un paramètre modifié après le pricing rend le résumé périmé plutôt que faux." />
          </div>
          <p class="text-[11px] text-slate-500 mt-0.5">
            Destiné à être collé dans un e-mail, une note, ou soumis à un modèle
            de langage pour une analyse ou des pistes de restructuration.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <label class="flex items-center gap-1.5 text-[11px] text-slate-500 cursor-pointer select-none">
            <input type="checkbox" v-model="commercial" class="accent-blue-600" />
            Inclure les données commerciales
            <HelpTip text="Décoché par défaut. Ce texte est fait pour sortir du desk — analyser un payoff ne nécessite ni la contrepartie, ni le nominal, ni le prix traité, ni la marge." />
          </label>
          <button class="btn-primary text-xs px-3 py-1.5"
                  @click="copier('resume', resume.texte)">
            {{ copie === 'resume' ? '✓ Copié' : '📋 Copier' }}
          </button>
        </div>
      </div>

      <div class="card">
        <pre class="text-[11px] leading-relaxed text-slate-300 whitespace-pre-wrap font-mono
                    max-h-[50vh] overflow-y-auto">{{ resume.texte }}</pre>
      </div>

      <p class="text-[10px] text-slate-600">
        {{ resume.texte.length.toLocaleString('fr-FR') }} caractères ·
        généré depuis le pricing affiché
      </p>

      <!-- ── Second avis ─────────────────────────────────────────────
           C'est le texte AFFICHÉ ci-dessus qui part, pas une version
           reconstruite : ce que l'utilisateur a lu est ce que le modèle
           reçoit. -->
      <div class="card flex flex-col gap-3">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">
          Demander un second avis
          <HelpTip width="w-96" text="Envoie le résumé ci-dessus à un modèle de langage. Le prompt lui interdit explicitement de valider ou contester un chiffre : un modèle ne peut pas vérifier un Monte-Carlo. Il répond sur la structure et l'économie du produit. Sa réponse est un second avis, jamais un contrôle." />
        </div>

        <div class="flex flex-wrap gap-1.5">
          <button v-for="i in INTENTIONS" :key="i.id" @click="intention = i.id"
                  class="text-xs px-2.5 py-1 rounded border transition-colors"
                  :class="intention === i.id
                    ? 'bg-blue-600/20 border-blue-500 text-blue-400'
                    : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'">
            {{ i.label }}
          </button>
        </div>

        <div class="flex items-end gap-2 flex-wrap">
          <div class="flex-1 min-w-[240px]">
            <label class="label">
              {{ intention === 'libre' ? 'Votre question' : 'Précision (optionnel)' }}
            </label>
            <input v-model="question" type="text" class="input text-xs"
                   :placeholder="intention === 'libre'
                     ? 'Ex : ce produit convient-il à un profil défensif ?'
                     : 'Ex : concentre-toi sur le risque Stellantis'" />
          </div>
        </div>
        <p v-if="commercial" class="text-xs text-amber-600">Les données commerciales sont incluses dans le résumé envoyé.</p>
        <AiWorkbench endpoint="/api/product/analyse" :payload="aiPayload"
          :disabled="intention === 'libre' && !question.trim()" action-label="Demander un second avis"
          @result="avis = $event" />

        <div v-if="avis" class="flex flex-col gap-2 border-t border-slate-800 pt-3">
          <div class="flex items-center justify-between gap-2 flex-wrap">
            <span class="text-[10px] text-slate-500 uppercase tracking-wider">
              {{ avis.intention_label }} — second avis, pas un contrôle
            </span>
            <div class="flex items-center gap-3">
              <span class="text-[10px] text-slate-600 font-mono">
                {{ avis.provider }}{{ avis.model ? ' / ' + avis.model : '' }} ·
                {{ formatDate(avis.generated_at.slice(0, 10)) }} ·
                {{ Math.round(avis.elapsed_ms / 1000) }} s
              </span>
              <button class="btn-primary text-xs px-3 py-1"
                      @click="copier('avis', texteAvisCopiable)">
                {{ copie === 'avis' ? '✓ Copié' : '📋 Copier' }}
              </button>
            </div>
          </div>
          <pre class="text-[11px] leading-relaxed text-slate-300 whitespace-pre-wrap
                      max-h-[50vh] overflow-y-auto">{{ avis.texte }}</pre>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { buildProductSummary } from '../composables/useProductSummary.js'
import { formatDate } from '../utils/format.js'
import AiWorkbench from './AiWorkbench.vue'
import HelpTip from './HelpTip.vue'

const SAUT = String.fromCharCode(10)
const store = usePricingStore()
const commercial = ref(false)
// Quelle zone vient d'être copiée — une seule confirmation à la fois.
const copie = ref('')

// ── Second avis ───────────────────────────────────────────────────
const INTENTIONS = [
  { id: 'analyse',         label: 'Analyse du risque' },
  { id: 'restructuration', label: 'Pistes de restructuration' },
  { id: 'argumentaire',    label: 'Argumentaire client' },
  { id: 'critique',        label: 'Revue critique' },
  { id: 'libre',           label: 'Question libre' },
]
const intention = ref('analyse')
const question = ref('')
const avis = ref(null)
const resume = computed(() => buildProductSummary(store, { commercial: commercial.value }))
const aiPayload = computed(() => ({ resume: resume.value.texte, intention: intention.value, question: question.value }))

async function copier(cle, texte) {
  try {
    await navigator.clipboard.writeText(texte)
    copie.value = cle
    setTimeout(() => { if (copie.value === cle) copie.value = '' }, 1800)
  } catch {
    // Presse-papier refusé (contexte non sécurisé, permission) : la sélection
    // manuelle reste possible, chaque texte est affiché en entier à l'écran.
  }
}

// L'avis part rarement seul : collé dans un mail six mois plus tard, un texte
// de modèle sans sa provenance se relit comme une conclusion validée.
const texteAvisCopiable = computed(() => {
  const a = avis.value
  if (!a) return ''
  const entete = `${a.intention_label} — second avis d'un modèle, pas un contrôle`
  const prov = `${a.provider}${a.model ? ' / ' + a.model : ''}`
    + ` · ${formatDate(a.generated_at.slice(0, 10))}`
  return [entete, prov, '', a.texte].join(SAUT)
})

</script>
