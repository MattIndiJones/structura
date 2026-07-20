<template>
  <div class="card">
    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
      🗺️ Grille de prix — heatmap 2 paramètres
    </div>

    <div v-if="store.scriptParams.length < 1" class="text-xs text-amber-500">
      Aucun PARAM détecté dans le script.
    </div>
    <div v-else-if="store.scriptParams.length < 2" class="text-xs text-amber-500">
      Au moins 2 PARAM distincts sont nécessaires pour une grille à deux axes.
    </div>

    <template v-else>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-3">
        <div class="grid grid-cols-3 gap-2 text-xs">
          <div class="col-span-3">
            <label class="label">Axe X
              <HelpTip text="PARAM du script balayé en colonnes. Les deux axes sont variés indépendamment l'un de l'autre — si les deux paramètres ont un lien économique dans le produit (ex: une barrière et un coupon censés bouger ensemble), la grille testera aussi des combinaisons qui n'ont pas de sens commercial." />
            </label>
            <select v-model="form.param_x" class="select" @change="prefillX">
              <option v-for="p in store.scriptParams" :key="p.name" :value="p.name">{{ p.name }}</option>
            </select>
          </div>
          <div>
            <label class="label">Min{{ xSuffix }}</label>
            <SensitiveValue mode="input"><input v-model.number="form.x_min" type="number" step="0.1" class="input" /></SensitiveValue>
          </div>
          <div>
            <label class="label">Max{{ xSuffix }}</label>
            <SensitiveValue mode="input"><input v-model.number="form.x_max" type="number" step="0.1" class="input" /></SensitiveValue>
          </div>
          <div>
            <label class="label">Pas
              <HelpTip text="Nombre de valeurs testées entre Min et Max sur cet axe — le nombre total de cellules calculées est Pas(X) × Pas(Y), chacune avec son propre pricing MC complet." />
            </label>
            <input v-model.number="form.x_steps" type="number" min="2" max="15" class="input" />
          </div>
        </div>
        <div class="grid grid-cols-3 gap-2 text-xs">
          <div class="col-span-3">
            <label class="label">Axe Y</label>
            <select v-model="form.param_y" class="select" @change="prefillY">
              <option v-for="p in store.scriptParams" :key="p.name" :value="p.name">{{ p.name }}</option>
            </select>
          </div>
          <div>
            <label class="label">Min{{ ySuffix }}</label>
            <SensitiveValue mode="input"><input v-model.number="form.y_min" type="number" step="0.1" class="input" /></SensitiveValue>
          </div>
          <div>
            <label class="label">Max{{ ySuffix }}</label>
            <SensitiveValue mode="input"><input v-model.number="form.y_max" type="number" step="0.1" class="input" /></SensitiveValue>
          </div>
          <div>
            <label class="label">Pas
              <HelpTip text="Nombre de valeurs testées entre Min et Max sur cet axe." />
            </label>
            <input v-model.number="form.y_steps" type="number" min="2" max="15" class="input" />
          </div>
        </div>
      </div>

      <div v-if="form.param_x === form.param_y" class="text-xs text-red-400 mb-2">
        Les deux axes doivent porter sur des paramètres différents.
      </div>

      <details class="mb-3">
        <summary class="text-xs text-slate-500 cursor-pointer hover:text-slate-300">Options avancées</summary>
        <div class="grid grid-cols-3 gap-3 text-xs mt-2">
          <div>
            <label class="label">N chemins / cellule
              <HelpTip text="Chemins MC par cellule de la grille — un pricing complet et indépendant par cellule, pas partagé entre elles. Baisser cette valeur accélère la grille mais augmente le bruit MC visible d'une cellule à l'autre (des variations qui peuvent sembler être un effet du paramètre alors que c'est juste du bruit d'échantillonnage)." />
            </label>
            <input v-model.number="form.N" type="number" step="500" min="500" max="20000" class="input" />
          </div>
        </div>
      </details>

      <div class="flex justify-end mb-4">
        <button class="btn-primary text-xs px-5" :disabled="store.loading || form.param_x === form.param_y" @click="launch">
          <span v-if="store.loading" class="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
          ▶ Calculer la grille
        </button>
      </div>

      <div v-if="!store.grid" class="text-xs text-slate-600 text-center py-6">
        Configurez les deux axes et lancez le calcul ({{ form.x_steps * form.y_steps }} cellules × {{ form.N }} chemins).
      </div>

      <div v-else class="overflow-x-auto">
        <table class="border-collapse text-xs mx-auto">
          <thead>
            <tr>
              <th class="p-1"></th>
              <th v-for="(x, i) in store.grid.x_values" :key="'hx' + i"
                  class="p-1 text-center text-slate-400 font-semibold whitespace-nowrap">
                <SensitiveValue>{{ displayAxisVal(store.grid.param_x, x) }}</SensitiveValue>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(y, j) in store.grid.y_values" :key="'row' + j">
              <th class="p-1 text-right text-slate-400 font-semibold whitespace-nowrap pr-2">
                <SensitiveValue>{{ displayAxisVal(store.grid.param_y, y) }}</SensitiveValue>
              </th>
              <td v-for="(x, i) in store.grid.x_values" :key="'cell' + i + '-' + j" class="p-0 text-center"
                  :title="demo.enabled ? '' : `${store.grid.param_x}=${displayAxisVal(store.grid.param_x, x)} · ${store.grid.param_y}=${displayAxisVal(store.grid.param_y, y)} -> ${(store.grid.prices[j][i] * 100).toFixed(2)}%`">
                <!-- Color (the heatmap "shape") stays visible even in demo mode — only the exact digits hide. -->
                <div class="w-16 h-9 flex items-center justify-center font-mono font-semibold rounded-sm text-slate-100"
                     :style="{ background: cellColor(store.grid.prices[j][i]) }">
                  <SensitiveValue>{{ (store.grid.prices[j][i] * 100).toFixed(1) }}</SensitiveValue>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="text-xs text-slate-600 mt-3 text-center">
          {{ store.grid.param_x }} (colonnes) × {{ store.grid.param_y }} (lignes) — prix en % du notionnel,
          référence <SensitiveValue>{{ (refPrice * 100).toFixed(2) }}%</SensitiveValue> ·
          <span class="text-red-400">rouge = sous la référence</span> ·
          <span class="text-green-400">vert = au-dessus</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { reactive, computed } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import SensitiveValue from './SensitiveValue.vue'
import HelpTip from './HelpTip.vue'

const store = usePricingStore()
const demo = useDemoModeStore()

const names = store.scriptParams.map(p => p.name)
const form = reactive({
  param_x: names[0] || '', x_min: 0, x_max: 0, x_steps: 9,
  param_y: names[1] || names[0] || '', y_min: 0, y_max: 0, y_steps: 9,
  N: 4000,
})

const xSuffix = computed(() => store.paramIsPct(form.param_x) ? ' (%)' : '')
const ySuffix = computed(() => store.paramIsPct(form.param_y) ? ' (%)' : '')

// Seed each axis range from that PARAM's own default (half to 1.5x), same
// convention as the solver's bound prefill.
function prefillX() {
  const p = store.scriptParams.find(p => p.name === form.param_x)
  if (!p) return
  form.x_min = +(p.raw_default * 0.5).toFixed(4)
  form.x_max = +(p.raw_default > 0 ? p.raw_default * 1.5 : p.raw_default + 1).toFixed(4)
}
function prefillY() {
  const p = store.scriptParams.find(p => p.name === form.param_y)
  if (!p) return
  form.y_min = +(p.raw_default * 0.5).toFixed(4)
  form.y_max = +(p.raw_default > 0 ? p.raw_default * 1.5 : p.raw_default + 1).toFixed(4)
}
prefillX()
prefillY()

function launch() {
  store.runGrid({ ...form })
}

function displayAxisVal(name, storedVal) {
  const v = store.fromStoredUnits(name, storedVal)
  return v.toFixed(2) + (store.paramIsPct(name) ? '%' : '')
}

// Diverging color scale centered on the current main price (or the grid's own
// midpoint if no pricing has run yet): red below reference, green above —
// same visual language as the rest of the app (red=bad/below, green=good/above).
const gridFlat = computed(() => store.grid ? store.grid.prices.flat() : [])
const gridRange = computed(() => gridFlat.value.length
  ? { min: Math.min(...gridFlat.value), max: Math.max(...gridFlat.value) }
  : { min: 0, max: 1 })
const refPrice = computed(() => store.result?.price ?? (gridRange.value.min + gridRange.value.max) / 2)

function cellColor(price) {
  const ref = refPrice.value
  const { min, max } = gridRange.value
  if (price >= ref) {
    const t = max > ref ? Math.min(1, (price - ref) / (max - ref)) : 0
    return `rgba(16,185,129,${0.12 + t * 0.55})`
  }
  const t = ref > min ? Math.min(1, (ref - price) / (ref - min)) : 0
  return `rgba(239,68,68,${0.12 + t * 0.55})`
}
</script>
