<!--
  Le tableau comparatif des déclinaisons.

  À iso-valeur, le prix ne départage plus rien — c'est même le but d'une
  restructuration réussie. La colonne qui décide est P(récupérer le pair
  D'ORIGINE), et elle ne veut pas dire la même chose selon le mode : un avenant
  garde le nominal, une note neuve le réduit. C'est pourquoi le plafond de
  récupération est affiché à côté, et jamais séparé d'elle : une probabilité
  sans son plafond n'est pas comparable.
-->
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
            À iso-valeur le prix ne départage rien — c'est la colonne
            « pair d'origine » qui décide.
          </div>
        </div>
        <div class="ml-auto flex items-center gap-2">
          <select v-model.number="N" class="select text-xs w-28">
            <option :value="4000">4 000 chemins</option>
            <option :value="8000">8 000 chemins</option>
            <option :value="20000">20 000 chemins</option>
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

    <AlertMessage v-if="erreur" kind="error" dismissible @dismiss="erreur = ''">{{ erreur }}</AlertMessage>

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
            <th class="text-right py-2 px-3 font-medium">Prix</th>
            <th class="text-right py-2 px-3 font-medium">
              Écart
              <HelpTip text="Contre l'origine repricée dans le même appel. Un écart négatif veut dire que la restructuration se finance : elle vaut moins cher que ce que le détenteur abandonne." />
            </th>
            <th class="text-right py-2 px-3 font-medium">
              P(pair d'origine)
              <HelpTip width="w-[26rem]" text="Probabilité de récupérer 100 % du nominal D'ORIGINE. Sur un avenant le nominal ne bouge pas, c'est donc la probabilité que la jambe résiduelle rende le pair. Sur une note neuve, le détenteur débouclé à P₀ n'achète que P₀/P_neuve unités : récupérer son pair d'origine exigerait que la note neuve rende bien plus que le sien. Afficher la P(≥100 %) brute de la note neuve ici donnerait le roll gagnant à tort." />
            </th>
            <th class="text-right py-2 px-3 font-medium">
              Plafond
              <HelpTip text="Ce que le détenteur peut récupérer au mieux, en % du nominal d'origine. 100 % sur un avenant, qui conserve le nominal. Moins sur une note neuve, qui le réduit du rapport des prix — une probabilité sans son plafond n'est pas comparable." />
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
            <td class="text-right py-2 px-3 font-mono"
                :class="l.plafond != null && l.plafond < 0.999 ? 'text-red-400' : 'text-slate-500'">
              <SensitiveValue>{{ pct(l.plafond, 1) }}</SensitiveValue>
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
        {{ resultat.N.toLocaleString('fr-FR') }} chemins par ligne — tirage dédié,
        plus petit que celui de l'onglet Résultats : ce tableau classe, il ne publie pas.
        <span v-if="aUnRoll" class="block mt-1 text-amber-500/80">
          ⚠ Une note neuve réduit le nominal du rapport des prix. Sa colonne
          « pair d'origine » n'est donc pas sa P(≥100 %) propre — comparer les
          deux directement donnerait le roll gagnant à tort.
        </span>
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePricingStore } from '../stores/pricing.js'
import { apiFetch } from '../utils/api.js'
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

const parentId = computed(() =>
  store.variantInfo?.parent_id ?? store.currentScriptId ?? null)

async function charger() {
  resultat.value = null
  if (!parentId.value) { variantes.value = []; return }
  try {
    const res = await apiFetch(`/api/db/scripts/${parentId.value}/variants`)
    variantes.value = res.ok ? await res.json() : []
  } catch { variantes.value = [] }
}
watch(parentId, charger, { immediate: true })

const lignes = computed(() => resultat.value?.lignes || [])

// Classé par ce qui décide : la probabilité de récupérer le pair d'origine.
// L'origine reste dans le classement — c'est la référence à battre, pas une
// ligne d'en-tête.
const classees = computed(() =>
  [...lignes.value].sort((a, b) => (b.proba_pair_origine ?? -1) - (a.proba_pair_origine ?? -1)))

const meilleure = computed(() =>
  classees.value.findIndex(l => l.proba_pair_origine != null))

const aUnRoll = computed(() => classees.value.some(l => l.mode === 'roll'))

async function comparer() {
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
                              N: N.value }),
    })
    const data = await res.json()
    if (!res.ok) { erreur.value = data.detail || 'Comparaison impossible.'; return }
    resultat.value = data
  } catch (e) { erreur.value = e.message }
  finally { occupe.value = false }
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
