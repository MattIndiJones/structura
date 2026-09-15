<template>
  <div class="flex-1 flex flex-col min-h-0">
    <div class="page-header px-6 pt-6 pb-4 mb-0">
      <div class="flex items-center gap-3">
        <BackLink :fallback="{ path: '/', query: { category: 'pricing' } }" />
        <div>
          <h1 class="page-title">Modèles de produits</h1>
          <p class="page-subtitle">
            Un produit, un nombre de sous-jacents et un ténor : le Pricer s'ouvre complété.
          </p>
        </div>
      </div>
    </div>

    <div class="px-6 pb-8 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_22rem] gap-6 items-start">
      <!-- Catalogue: one sheet per payoff, with no duration nor asset count. -->
      <div class="flex flex-col gap-6">
        <section v-for="family in families" :key="family.key" :aria-label="family.label">
          <h2 class="micro-label mb-2">{{ family.label }}</h2>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
            <button v-for="model in family.models" :key="model.key" type="button"
                    :id="`modele-${model.key}`"
                    class="model-option" :class="{ active: selectedKey === model.key }"
                    :aria-pressed="selectedKey === model.key"
                    @click="select(model)">
              <span class="text-sm font-semibold" style="color: var(--text);">{{ model.label }}</span>
              <span class="text-xs leading-relaxed" style="color: var(--muted);">{{ model.description }}</span>
              <span class="flex flex-wrap gap-1 mt-1">
                <span class="badge badge-muted">{{ underlyingsLabel(model) }}</span>
                <span class="badge badge-muted">{{ tenorsLabel(model) }}</span>
              </span>
            </button>
          </div>
        </section>
      </div>

      <!-- Opening: three choices, no field to type. -->
      <aside class="card lg:sticky lg:top-4 flex flex-col gap-4" aria-live="polite">
        <p v-if="!selected" class="card-hint">
          Choisissez un produit dans la liste. Ses calendriers seront générés depuis la date de
          strike du Pricer, aujourd'hui par défaut.
        </p>
        <template v-else>
          <div>
            <div class="micro-label">Produit</div>
            <div class="text-sm font-semibold mt-1" style="color: var(--text);">{{ selected.label }}</div>
          </div>

          <div>
            <div class="label">Nombre de sous-jacents</div>
            <div class="flex flex-wrap gap-1.5">
              <button v-for="n in counts" :key="n" type="button" :id="`sous-jacents-${n}`"
                      class="filter-btn num" :class="{ active: count === n }"
                      :aria-pressed="count === n" @click="count = n">
                {{ n }}
              </button>
            </div>
          </div>

          <div>
            <div class="label">Ténor</div>
            <div class="flex flex-wrap gap-1.5">
              <button v-for="option in tenors" :key="option.code" type="button"
                      :id="`tenor-${option.code}`"
                      class="filter-btn num" :class="{ active: tenor === option.code }"
                      :aria-pressed="tenor === option.code" :title="option.label"
                      @click="tenor = tenor === option.code ? null : option.code">
                {{ option.code }}
              </button>
            </div>
            <p class="text-[10px] mt-1.5" style="color: var(--subtle);">
              Sans ténor, le Pricer s'ouvre sans aucune date : tout reste à compléter.
            </p>
          </div>

          <div class="stat-box text-xs flex flex-col gap-1.5" style="color: var(--muted);">
            <div class="micro-label">Le Pricer s'ouvrira avec</div>
            <div>Le script générique, validé, aux valeurs initiales de ses paramètres.</div>
            <div>
              {{ count }} sous-jacent{{ count > 1 ? 's' : '' }} aux hypothèses par défaut
              ({{ count > 1 ? 'corrélation nulle, ' : '' }}tickers à choisir).
            </div>
            <template v-if="plan">
              <div>
                Strike le <span class="num" style="color: var(--text);">{{ frDate(strikeDate) }}</span>,
                maturité le <span class="num" style="color: var(--text);">{{ frDate(plan.maturity) }}</span>.
              </div>
              <div v-for="line in calendarLines" :key="line">{{ line }}</div>
              <div>Paiement proposé à maturité + 3 jours ouvrés, modifiable.</div>
            </template>
            <div v-else>Aucune date : strike, calendriers et maturité à compléter dans Economics.</div>
          </div>

          <button type="button" class="btn-primary" @click="open">Ouvrir dans le Pricer</button>
          <p class="text-[10px]" style="color: var(--subtle);">
            Session éphémère : rien n'est conservé sans action explicite. Une fois ouvertes, les
            dates ne suivent pas un changement de la date de strike.
          </p>
        </template>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import BackLink from '../components/ui/BackLink.vue'
import { confirmer } from '../composables/useConfirm.js'
import { usePricingStore } from '../stores/pricing.js'
import { CALCULATION_LIMITS } from '../utils/calculationBudget.js'
import {
  PRODUCT_MODEL_FAMILIES, buildModelCalendars, productModels, tenorsFor, underlyingCountsFor,
} from '../utils/productModels.js'

const router = useRouter()
const pricing = usePricingStore()

const families = PRODUCT_MODEL_FAMILIES
  .map(family => ({ ...family, models: productModels.filter(m => m.family === family.key) }))
  .filter(family => family.models.length)

const selectedKey = ref('')
const count = ref(1)
const tenor = ref(null)

const selected = computed(() => productModels.find(m => m.key === selectedKey.value) || null)
const counts = computed(() => underlyingCountsFor(selected.value, CALCULATION_LIMITS.maxUnderlyings))
const tenors = computed(() => tenorsFor(selected.value))

// The strike date of a fresh Pricer session: today (M8).
const strikeDate = new Date().toISOString().slice(0, 10)
const plan = computed(() => (selected.value && tenor.value
  ? buildModelCalendars(selected.value, { strikeDate, tenorCode: tenor.value })
  : null))

function select(model) {
  selectedKey.value = model.key
  const allowed = underlyingCountsFor(model, CALCULATION_LIMITS.maxUnderlyings)
  if (!allowed.includes(count.value)) count.value = allowed[0]
  if (tenor.value && !model.tenors.includes(tenor.value)) tenor.value = null
}

function frDate(iso) {
  const [year, month, day] = String(iso || '').split('-')
  return day ? `${day}/${month}/${year}` : '—'
}

const FREQUENCIES = { '1Y': 'annuelles', '6M': 'semestrielles', '3M': 'trimestrielles', '1M': 'mensuelles' }
const SAMPLINGS = { '1M': 'mensuels', '3M': 'trimestriels', '1D': 'quotidiens', '1W': 'hebdomadaires' }

function windowSize(code) {
  const match = /^(\d+)D$/i.exec(String(code || ''))
  return match ? `${match[1]} relevés` : code
}

const calendarLines = computed(() => Object.entries(selected.value?.constats || {}).map(([name, spec]) => {
  if (spec.role === 'observations') {
    const cadence = FREQUENCIES[spec.frequency] || `tous les ${spec.frequency}`
    const sampling = spec.window_frequency
      ? `, chacune moyennée sur ses relevés ${SAMPLINGS[spec.window_frequency] || spec.window_frequency}` : ''
    return `${name} : constatations ${cadence} jusqu'à maturité${sampling}.`
  }
  if (spec.role === 'strike_window') {
    return `${name} : fenêtre de départ de ${windowSize(spec.window_length)} depuis le strike.`
  }
  const window = spec.window_length ? `, fenêtre de ${windowSize(spec.window_length)}` : ''
  return `${name} : constatation à maturité${window}.`
}))

function underlyingsLabel(model) {
  const { min, max } = model.underlyings
  return min === max ? `${min} sous-jacent${min > 1 ? 's' : ''}` : `${min} à ${max} sous-jacents`
}

function tenorsLabel(model) {
  const allowed = tenorsFor(model)
  return allowed.length > 1 ? `${allowed[0].code} à ${allowed.at(-1).code}` : (allowed[0]?.code || '—')
}

async function open() {
  if (!selected.value) return
  if (pricing.hasUnsavedSession()) {
    const replace = await confirmer({
      titre: 'Remplacer la session de pricing ?',
      message: 'Le Pricer contient des modifications non enregistrées (script, valeurs, '
             + 'calendriers ou panier). Ouvrir ce modèle les remplace.',
      confirmer: 'Ouvrir le modèle',
      danger: true,
    })
    if (!replace) return
  }
  router.push({
    path: '/pricer',
    query: {
      modele: selected.value.key,
      sousJacents: String(count.value),
      ...(tenor.value ? { tenor: tenor.value } : {}),
    },
  })
}
</script>

<style scoped>
.model-option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: .25rem;
  text-align: left;
  padding: .75rem .9rem;
  border-radius: var(--radius-sm);
  background: var(--surface);
  border: 1.5px solid var(--border);
  transition: border-color .15s ease, background-color .15s ease;
}
.model-option:hover { border-color: var(--accent); }
.model-option.active {
  border-color: var(--accent);
  background: var(--accent-light);
}
@media (prefers-reduced-motion: reduce) {
  .model-option { transition: none; }
}
</style>
