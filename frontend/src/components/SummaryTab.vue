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
          <div>
            <label class="label">Moteur</label>
            <select v-model="provider" class="select text-xs w-40">
              <option v-for="p in providers" :key="p.key" :value="p.key"
                      :disabled="!p.ready">
                {{ p.label }}{{ p.ready ? '' : ' — indisponible' }}
              </option>
            </select>
          </div>
          <div v-if="modelesDispo.length">
            <label class="label">Modèle
              <HelpTip text="Modèles réellement installés sur la machine. Le défaut de l'application est un modèle de code, choisi pour l'assistant de scripting — pour analyser un produit, un modèle généraliste convient mieux." />
            </label>
            <select v-model="model" class="select text-xs w-48">
              <option v-for="m in modelesDispo" :key="m" :value="m">{{ m }}</option>
            </select>
          </div>
          <button class="btn-primary text-xs px-3 py-1.5 mb-0.5"
                  :disabled="occupe || (intention === 'libre' && !question.trim())"
                  @click="demander">
            {{ occupe ? '…' : 'Demander' }}
          </button>
          <button class="btn-secondary text-xs px-3 py-1.5 mb-0.5"
                  :disabled="intention === 'libre' && !question.trim()"
                  @click="basculerPrompt">
            {{ prompt ? 'Masquer le prompt' : 'Voir le prompt' }}
          </button>
        </div>

        <p v-if="provider !== 'ollama'" class="text-[10px] text-amber-500">
          ⚠ Ce moteur est distant : le résumé affiché ci-dessus quitte la machine.
          {{ commercial ? 'Les données commerciales y sont incluses.'
                        : 'Les données commerciales en sont exclues.' }}
        </p>

        <AlertMessage v-if="erreur" kind="error">{{ erreur }}</AlertMessage>

        <!-- Le prompt exact, construit par le MEME code que l'envoi
             (construire_prompts cote serveur) : un apercu reconstruit a part
             finirait par decrire autre chose que ce qui part. -->
        <div v-if="prompt" class="flex flex-col gap-2 border-t border-slate-800 pt-3">
          <div class="flex items-center justify-between gap-2 flex-wrap">
            <span class="text-[10px] text-slate-500 uppercase tracking-wider">
              Prompt envoyé — {{ prompt.intention_label }}
              <HelpTip width="w-96" text="Les deux messages exacts qui partent au modèle : le cadre système, qui lui interdit de valider un chiffre, et la demande, qui porte la consigne d'intention suivie du résumé ci-dessus. Construits par le même code que l'envoi réel — aucun appel au modèle n'est fait pour les afficher." />
            </span>
            <button class="text-[10px] text-slate-500 hover:text-slate-300 underline"
                    @click="copier('prompt', prompt.system + separateurPrompt + prompt.user)">
              {{ copie === 'prompt' ? '✓ Copié' : '📋 Copier le prompt' }}
            </button>
          </div>

          <div>
            <div class="text-[10px] text-slate-600 uppercase tracking-wider mb-1">
              Système — le cadre imposé au modèle
            </div>
            <pre class="text-[10px] leading-relaxed text-slate-400 whitespace-pre-wrap font-mono
                        max-h-48 overflow-y-auto bg-slate-900/50 rounded p-2">{{ prompt.system }}</pre>
          </div>

          <div>
            <div class="text-[10px] text-slate-600 uppercase tracking-wider mb-1">
              Utilisateur — la consigne, puis le résumé
            </div>
            <pre class="text-[10px] leading-relaxed text-slate-400 whitespace-pre-wrap font-mono
                        max-h-48 overflow-y-auto bg-slate-900/50 rounded p-2">{{ prompt.user }}</pre>
          </div>

          <p class="text-[10px] text-slate-600">
            {{ (prompt.system.length + prompt.user.length).toLocaleString('fr-FR') }}
            caractères au total
          </p>
        </div>

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
import { computed, onMounted, ref, watch } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { buildProductSummary } from '../composables/useProductSummary.js'
import { apiFetch } from '../utils/api.js'
import { formatDate } from '../utils/format.js'
import AlertMessage from './ui/AlertMessage.vue'
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
// Ollama par défaut : local, sans clé, et le résumé ne quitte pas la machine.
const provider = ref('ollama')
const model = ref('')
const providers = ref([])
const avis = ref(null)
const prompt = ref(null)
const erreur = ref('')
const occupe = ref(false)

onMounted(async () => {
  try {
    const res = await apiFetch('/api/script/providers')
    if (!res.ok) return
    const data = await res.json()
    if (Array.isArray(data.providers) && data.providers.length) {
      providers.value = data.providers
      // On ne bascule sur un moteur distant que si le local est absent : le
      // défaut conservateur ne doit pas dépendre de l'ordre de la liste.
      const local = data.providers.find(p => p.key === 'ollama' && p.ready)
      provider.value = local ? 'ollama'
        : (data.providers.find(p => p.ready)?.key || data.default || 'ollama')
    }
  } catch { /* liste par défaut : Ollama seul */ }
})

async function demander() {
  occupe.value = true; erreur.value = ''; avis.value = null
  try {
    const res = await apiFetch('/api/product/analyse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // Le texte AFFICHÉ, pas une reconstruction.
      body: JSON.stringify({ resume: resume.value.texte, intention: intention.value,
                              question: question.value, provider: provider.value,
                              model: model.value }),
    })
    const data = await res.json()
    if (!res.ok) { erreur.value = data.detail || "Le moteur n'a pas répondu."; return }
    avis.value = data
  } catch (e) { erreur.value = e.message }
  finally { occupe.value = false }
}

const resume = computed(() => buildProductSummary(store, { commercial: commercial.value }))

const moteurCourant = computed(() => providers.value.find(p => p.key === provider.value))
const modelesDispo = computed(() => moteurCourant.value?.models || [])
// Le modèle suit le moteur : chacun a les siens, et garder celui d'avant
// enverrait un nom que le nouveau ne connaît pas.
watch(moteurCourant, m => { model.value = m?.default_model || '' }, { immediate: true })

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

const separateurPrompt = [SAUT, SAUT, '=== MESSAGE UTILISATEUR ===', SAUT, SAUT].join('')

// Le prompt se relit sans consommer de jeton : l'aperçu n'appelle pas le
// modèle, il demande au serveur ce qu'il ENVERRAIT.
async function basculerPrompt() {
  if (prompt.value) { prompt.value = null; return }
  erreur.value = ''
  try {
    const res = await apiFetch('/api/product/analyse/prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume: resume.value.texte, intention: intention.value,
                              question: question.value }),
    })
    const data = await res.json()
    if (!res.ok) { erreur.value = data.detail || "Prompt indisponible."; return }
    prompt.value = data
  } catch (e) { erreur.value = e.message }
}

// Changer d'intention ou de question change le prompt : le garder affiché
// montrerait une demande qui n'est plus celle qui partirait.
watch([intention, question, resume], () => { if (prompt.value) prompt.value = null })
</script>
