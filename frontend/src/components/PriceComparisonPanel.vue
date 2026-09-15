<template>
  <section class="comparison-workspace">
    <header class="comparison-header">
      <div>
        <div class="comparison-eyebrow">{{ eyebrow }}</div>
        <h2>{{ title }}</h2>
        <p>{{ orderedItems.length }} calculs, classés par date de valorisation.</p>
      </div>
      <button v-if="collapsible" class="btn-secondary text-xs" @click="$emit('close')">Réduire</button>
    </header>

    <div v-if="displayedWarnings.length" class="comparison-warnings">
      <span v-for="warning in displayedWarnings" :key="warning">⚠ {{ warning }}</span>
    </div>

    <div class="comparison-summary">
      <article>
        <span>Mouvement total</span>
        <strong :class="movementTone(totalMovement)">{{ formatMovement(totalMovement) }}</strong>
        <small>{{ formatDate(orderedItems[0]?.valuationDate) }} → {{ formatDate(orderedItems.at(-1)?.valuationDate) }}</small>
      </article>
      <article>
        <span>Plus fort mouvement</span>
        <strong :class="movementTone(largestMovement?.delta)">{{ formatMovement(largestMovement?.delta) }}</strong>
        <small v-if="largestMovement">au {{ formatDate(largestMovement.item.valuationDate) }}</small>
        <small v-else>—</small>
      </article>
      <article>
        <span>Étendue des prix</span>
        <strong>{{ formatNumber(priceRange, 2) }} pts</strong>
        <small>minimum à maximum</small>
      </article>
    </div>

    <section class="price-chart-card">
      <header>
        <h3>Trajectoire des prix</h3>
        <span v-if="Number.isFinite(referencePrice)">{{ referenceLabel }} : {{ formatPercent(referencePrice) }}</span>
      </header>
      <div class="price-chart-scroll">
        <svg class="price-chart" :style="{ width: `${chart.width}px` }"
          :viewBox="`0 0 ${chart.width} ${chart.height}`" role="img"
          :aria-label="`Évolution des ${priceLabel} sélectionnés`">
          <line v-for="tick in chart.ticks" :key="tick.value" class="chart-grid"
            :x1="chart.left" :x2="chart.width - chart.right" :y1="tick.y" :y2="tick.y" />
          <text v-for="tick in chart.ticks" :key="`label-${tick.value}`" class="chart-axis-label"
            :x="chart.left - 8" :y="tick.y + 4" text-anchor="end">{{ formatNumber(tick.value, 1) }}%</text>
          <line v-if="chart.referenceY != null" class="chart-reference"
            :x1="chart.left" :x2="chart.width - chart.right" :y1="chart.referenceY" :y2="chart.referenceY" />
          <text v-if="chart.referenceY != null" class="chart-reference-label"
            :x="chart.width - chart.right" :y="chart.referenceY - 6" text-anchor="end">{{ referenceLabel.toLowerCase() }}</text>
          <path class="chart-line" :d="chart.path" />
          <g v-for="point in chart.points" :key="point.item.id">
            <circle class="chart-point" :cx="point.x" :cy="point.y" r="5" />
            <text class="chart-value" :x="point.x" :y="point.y - 12" text-anchor="middle">
              {{ formatNumber(point.value, 2) }}%
            </text>
            <text class="chart-date" :x="point.x" :y="chart.height - 12" text-anchor="middle">
              {{ chartDateLabel(point.item) }}
            </text>
          </g>
        </svg>
      </div>
    </section>

    <section class="parameter-comparison">
      <header>
        <div>
          <h3>Mouvements des paramètres</h3>
          <p>La variation de chaque colonne est calculée contre la date sélectionnée précédente.</p>
        </div>
      </header>
      <div class="comparison-table-scroll">
        <table class="comparison-table">
          <thead>
            <tr>
              <th>Paramètre</th>
              <th v-for="item in orderedItems" :key="item.id" class="is-number">
                <span>{{ formatDate(item.valuationDate) }}</span>
                <small>{{ timeLabel(item) }}<template v-if="item.basis"> · {{ item.basis }}</template></small>
              </th>
              <th class="is-number comparison-total-column">Mouvement total</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="group in normalizedGroups" :key="group.label">
              <tr class="comparison-group"><td :colspan="orderedItems.length + 2">{{ group.label }}</td></tr>
              <tr v-for="row in group.rows" :key="row.key">
                <td class="comparison-param-name">{{ row.label }}</td>
                <td v-for="(value, index) in row.values" :key="index" class="is-number">
                  <strong>{{ formatParameterValue(row, value) }}</strong>
                  <small v-if="index && parameterDelta(row, index) != null"
                    :class="movementTone(parameterDelta(row, index))">
                    {{ formatParameterChange(row, parameterDelta(row, index)) }}
                  </small>
                </td>
                <td class="is-number comparison-total-column" :class="movementTone(parameterTotal(row))">
                  {{ formatParameterChange(row, parameterTotal(row)) }}
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { formatDate, formatDateTime, formatNumber, formatPercent } from '../utils/format.js'

const props = defineProps({
  items: { type: Array, required: true },
  groups: { type: Array, default: () => [] },
  warnings: { type: Array, default: () => [] },
  versionWarning: { type: String, default: 'Les calculs portent sur plusieurs versions du contrat.' },
  title: { type: String, default: 'Évolution du prix entre les dates sélectionnées' },
  eyebrow: { type: String, default: 'Comparaison enregistrée' },
  priceLabel: { type: String, default: 'prix' },
  referencePrice: { type: Number, default: null },
  referenceLabel: { type: String, default: 'Prix traité' },
  collapsible: { type: Boolean, default: true },
})

defineEmits(['close'])

const orderedItems = computed(() => [...props.items].sort((left, right) => {
  const byValueDate = String(left.valuationDate || '').localeCompare(String(right.valuationDate || ''))
  if (byValueDate) return byValueDate
  const byCalculation = String(left.calculatedAt || '').localeCompare(String(right.calculatedAt || ''))
  return byCalculation || Number(left.id || 0) - Number(right.id || 0)
}))

const displayedWarnings = computed(() => {
  const warnings = [...props.warnings]
  const dates = props.items.map(item => item.valuationDate).filter(Boolean)
  const versions = props.items.map(item => item.version).filter(value => value != null)
  if (new Set(versions).size > 1) warnings.push(props.versionWarning)
  if (new Set(dates).size < dates.length) warnings.push('Plusieurs calculs ont la même date de valorisation.')
  return [...new Set(warnings)]
})

const normalizedGroups = computed(() => props.groups.map(group => ({
  ...group,
  rows: group.rows.map(row => ({
    ...row,
    values: orderedItems.value.map(item => row.values[itemOrderFromSource(item.id)] ?? null),
  })).filter(row => row.values.some(Number.isFinite)),
})).filter(group => group.rows.length))

function itemOrderFromSource(id) {
  return props.items.findIndex(item => item.id === id)
}

const movements = computed(() => orderedItems.value.map((item, index) => {
  const previous = orderedItems.value[index - 1]
  const delta = index && Number.isFinite(item.price) && Number.isFinite(previous?.price)
    ? item.price - previous.price
    : null
  return { item, delta }
}))

const totalMovement = computed(() => {
  const first = orderedItems.value[0]?.price
  const last = orderedItems.value.at(-1)?.price
  return Number.isFinite(first) && Number.isFinite(last) ? last - first : null
})

const largestMovement = computed(() => movements.value
  .filter(item => item.delta != null)
  .reduce((largest, item) => !largest || Math.abs(item.delta) > Math.abs(largest.delta) ? item : largest, null))

const priceRange = computed(() => {
  const values = orderedItems.value.map(item => item.price).filter(Number.isFinite)
  return values.length ? Math.max(...values) - Math.min(...values) : null
})

const chart = computed(() => {
  const values = orderedItems.value.map(item => item.price).filter(Number.isFinite)
  const width = Math.max(760, orderedItems.value.length * 125)
  const height = 245
  const left = 58
  const right = 24
  if (!values.length) return { width, height, left, right, points: [], ticks: [], path: '', referenceY: null }
  const domain = Number.isFinite(props.referencePrice) ? [...values, props.referencePrice] : values
  const minimum = Math.min(...domain)
  const maximum = Math.max(...domain)
  const rawRange = Math.max(maximum - minimum, 1)
  const padding = Math.max(rawRange * .14, .5)
  const low = minimum - padding
  const high = maximum + padding
  const top = 24
  const bottom = 42
  const y = value => top + (high - value) / (high - low) * (height - top - bottom)
  const points = orderedItems.value.map((item, index) => ({
    item,
    value: item.price,
    x: orderedItems.value.length === 1 ? width / 2 : left + index * (width - left - right) / (orderedItems.value.length - 1),
    y: y(item.price),
  }))
  const ticks = Array.from({ length: 5 }, (_, index) => {
    const value = low + (high - low) * index / 4
    return { value, y: y(value) }
  }).reverse()
  return {
    width, height, left, right, points, ticks,
    path: points.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' '),
    referenceY: Number.isFinite(props.referencePrice) ? y(props.referencePrice) : null,
  }
})

function timeLabel(item) {
  return formatDateTime(item.calculatedAt).split(' ')[1] || '—'
}

function chartDateLabel(item) {
  const sameDateCount = orderedItems.value.filter(other => other.valuationDate === item.valuationDate).length
  const date = formatDate(item.valuationDate).slice(0, 5)
  return sameDateCount > 1 ? `${date} ${timeLabel(item)}` : date
}

function movementTone(value) {
  if (value == null || value === 0) return 'tone-neutral'
  return value > 0 ? 'tone-positive' : 'tone-negative'
}

function formatMovement(value) {
  if (value == null) return '—'
  const normalized = Math.abs(value) < .005 ? 0 : value
  return `${normalized > 0 ? '+' : ''}${formatNumber(normalized, 2)} pts`
}

function parameterDelta(row, index) {
  const current = row.values[index]
  const previous = row.values[index - 1]
  return Number.isFinite(current) && Number.isFinite(previous) ? current - previous : null
}

function parameterTotal(row) {
  if (row.values.length < 2) return null
  const first = row.values[0]
  const last = row.values.at(-1)
  return Number.isFinite(first) && Number.isFinite(last) ? last - first : null
}

function formatParameterValue(row, value) {
  if (!Number.isFinite(value)) return '—'
  if (row.unit === '%' || row.unit === 'percent') return `${formatNumber(value, row.decimals ?? 2)} %`
  if (row.unit === 'bps') return `${formatNumber(value, row.decimals ?? 1)} bps`
  if (row.unit === 'an') return `${formatNumber(value, row.decimals ?? 2)} an`
  return formatNumber(value, row.decimals ?? 2)
}

function parameterSuffix(row) {
  if (row.unit === '%' || row.unit === 'percent') return ' pts'
  if (row.unit === 'bps') return ' bps'
  if (row.unit === 'an') return ' an'
  return ''
}

function formatParameterChange(row, value) {
  if (value == null) return '—'
  const decimals = row.decimals ?? (row.unit === 'bps' ? 1 : 2)
  const threshold = .5 * 10 ** -decimals
  const normalized = Math.abs(value) < threshold ? 0 : value
  return `${normalized > 0 ? '+' : ''}${formatNumber(normalized, decimals)}${parameterSuffix(row)}`
}
</script>

<style scoped>
.comparison-workspace { scroll-margin-top: 1rem; overflow: hidden; border: 1px solid #b7cfeb; border-radius: 16px; background: var(--surface); box-shadow: 0 14px 34px -24px rgba(22, 71, 125, .5); }
.comparison-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding: 1rem 1.15rem; border-bottom: 1px solid var(--border); background: linear-gradient(115deg, #f5f9ff 0%, var(--surface) 65%); }
.comparison-eyebrow { color: var(--accent); font-size: .65rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.comparison-header h2 { margin-top: .18rem; font-size: 1rem; font-weight: 750; }
.comparison-header p, .parameter-comparison header p { margin-top: .2rem; color: var(--muted); font-size: .7rem; }
.comparison-warnings { display: flex; flex-wrap: wrap; gap: .4rem; padding: .65rem 1rem; border-bottom: 1px solid #ead9a6; background: #fffaf0; }
.comparison-warnings span { color: #79570a; font-size: .67rem; }
.comparison-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-bottom: 1px solid var(--border); }
.comparison-summary article { padding: .8rem 1rem; border-right: 1px solid var(--border); }
.comparison-summary article:last-child { border-right: 0; }
.comparison-summary span { display: block; color: var(--muted); font-size: .6rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; }
.comparison-summary strong { display: block; margin: .25rem 0 .1rem; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 1.1rem; }
.comparison-summary small { color: var(--muted); font-size: .65rem; }
.price-chart-card { padding: 1rem 1rem .6rem; border-bottom: 1px solid var(--border); }
.price-chart-card > header, .parameter-comparison > header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.price-chart-card h3, .parameter-comparison h3 { font-size: .75rem; font-weight: 750; }
.price-chart-card header span { color: var(--muted); font-size: .68rem; }
.price-chart-scroll, .comparison-table-scroll { overflow-x: auto; }
.price-chart { display: block; height: 245px; max-width: none; margin-top: .3rem; }
.chart-grid { stroke: #e8e4dc; stroke-width: 1; }
.chart-axis-label, .chart-date, .chart-reference-label { fill: #777168; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 10px; }
.chart-reference { stroke: #aa7c13; stroke-width: 1.5; stroke-dasharray: 5 5; }
.chart-reference-label { fill: #8a6508; }
.chart-line { fill: none; stroke: var(--accent); stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }
.chart-point { fill: var(--surface); stroke: var(--accent); stroke-width: 3; }
.chart-value { fill: var(--accent); font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; font-weight: 700; }
.parameter-comparison { padding: 1rem; }
.comparison-table-scroll { margin-top: .7rem; border: 1px solid var(--border); border-radius: 10px; }
.comparison-table { min-width: 760px; width: 100%; border-collapse: collapse; font-size: .68rem; }
.comparison-table th { min-width: 8.4rem; padding: .55rem .65rem; background: var(--surface2); color: var(--muted); text-align: left; white-space: nowrap; }
.comparison-table th:first-child { position: sticky; left: 0; z-index: 2; min-width: 14rem; }
.comparison-table th span, .comparison-table th small { display: block; }
.comparison-table th small { margin-top: .12rem; font-size: .57rem; font-weight: 500; }
.comparison-table td { padding: .55rem .65rem; border-top: 1px solid var(--border); background: var(--surface); }
.comparison-table td strong, .comparison-table td small { display: block; white-space: nowrap; }
.comparison-table td strong { color: var(--text); font-family: 'JetBrains Mono', Consolas, monospace; font-weight: 600; }
.comparison-table td small { min-height: .9rem; margin-top: .12rem; font-family: 'JetBrains Mono', Consolas, monospace; font-size: .58rem; }
.comparison-param-name { position: sticky; left: 0; z-index: 1; color: var(--text); font-weight: 650; }
.comparison-group td { position: static; padding: .35rem .65rem; background: #f3f6fa; color: #4f6278; font-size: .59rem; font-weight: 750; letter-spacing: .07em; text-transform: uppercase; }
.comparison-total-column { border-left: 2px solid #c9d8e9 !important; background: #f7faff !important; font-weight: 700; }
.tone-positive { color: var(--positive) !important; }
.tone-negative { color: var(--negative) !important; }
.tone-neutral { color: var(--muted) !important; }

@media (max-width: 700px) {
  .comparison-summary { grid-template-columns: 1fr; }
  .comparison-summary article { border-right: 0; border-bottom: 1px solid var(--border); }
}
</style>
