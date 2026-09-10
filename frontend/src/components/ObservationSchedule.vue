<!--
  Échéancier d'observation d'un calendrier CONSTAT — replié par défaut.

  Un échéancier ne doit pas se lire différemment selon l'écran où on l'ouvre :
  ce composant sert le module RFQ et le Pricer, et toute vue qui génère des
  constatations à partir d'un calendrier.

  Replié, il tient sur une ligne : le résumé qu'on lirait au téléphone à une
  contrepartie. Déplié, un tableau dans un cadre à hauteur bornée — la page ne
  bouge donc jamais de plus de cette hauteur, quel que soit le nombre de dates.

  `request` est envoyé tel quel à /api/schedule/generate : chaque appelant y met
  ce que son propre éditeur détient, sans que le composant connaisse la forme de
  son état interne.
-->
<template>
  <div class="rounded-[10px] overflow-hidden" :style="{ border: '1px solid var(--border)' }">
    <!-- <details> et non un <button> : l éditeur de termes est enferme dans un
         <fieldset disabled> des qu une cotation existe, et un fieldset
         desactive TOUS les controles de formulaire qu il contient. Consulter
         un calendrier fige est precisement le moment ou on en a besoin. -->
    <details :open="open" @toggle="onToggle">
      <summary class="flex items-center gap-2 px-3 py-2 cursor-pointer select-none transition-colors hover:bg-slate-800/20 list-none">
        <span class="text-slate-500 text-[10px] transition-transform duration-150 inline-block"
              :class="open ? 'rotate-90' : ''">▶</span>
        <span class="text-[10px] font-bold uppercase tracking-wider text-slate-400 shrink-0">{{ label }}</span>
        <span v-if="summary" class="text-[11px] text-slate-500 truncate">{{ summary }}</span>
        <span v-else class="text-[11px] text-slate-600 truncate">déplier pour générer les dates</span>
        <span v-if="loading" class="ml-auto text-[10px] text-slate-500 shrink-0">calcul…</span>
      </summary>

    <div :style="{ borderTop: '1px solid var(--border)' }">
      <div v-if="error" class="px-3 py-2 text-[11px] text-red-400">⚠ {{ error }}</div>

      <div v-else-if="rows.length" class="table-shell max-h-72 overflow-auto" tabindex="0" role="region"
           :style="{ border: 'none', borderRadius: 0 }">
        <table class="w-full text-[11px]">
          <thead>
            <tr>
              <th class="num w-8">#</th>
              <th>Constatation</th>
              <th v-if="hasPayments">Paiement</th>
              <th class="num">Période</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in rows" :key="row.date">
            <tr :class="row.index === null ? 'opacity-60' : ''">
              <td class="num text-slate-600 tabular-nums">{{ row.index ?? '—' }}</td>
              <td class="whitespace-nowrap">
                <span class="font-mono" :class="row.index === null ? 'text-slate-500' : 'text-slate-200'">
                  <SensitiveValue>{{ row.date }}</SensitiveValue>
                </span>
                <span class="text-slate-600 ml-1.5">{{ row.weekday }}</span>
              </td>
              <td v-if="hasPayments" class="whitespace-nowrap font-mono text-slate-500">
                <SensitiveValue v-if="row.payment">{{ row.payment }}</SensitiveValue>
                <span v-else>—</span>
              </td>
              <td class="num text-slate-500 tabular-nums whitespace-nowrap">
                {{ row.days == null ? '—' : row.days + ' j' }}
              </td>
              <td class="whitespace-nowrap">
                <span v-if="row.index === null" class="text-slate-600 italic">début de période</span>
                <span v-if="row.adjustedFrom" class="text-amber-500"
                      :title="`Roulée au ${row.adjustedFrom}, jour fermé sur le calendrier ${request.currency || ''}`">
                  ⤴ {{ row.adjustedFrom }}
                </span>
                <span v-if="row.isStub" class="ml-1.5 text-[10px] rounded px-1 py-0.5 border border-amber-800/60 text-amber-500">stub</span>
                <span v-if="row.isLast" class="ml-1.5 text-[10px] rounded px-1 py-0.5 border border-slate-700 text-slate-400">maturité</span>
              </td>
            </tr>
            <!-- Les relevés que cette constatation moyenne. Repliés dans la
                 ligne plutôt qu'ailleurs : on les lit là où on lit la date. -->
            <tr v-if="row.fenetre">
              <td></td>
              <td :colspan="hasPayments ? 4 : 3" class="pb-1.5 pt-0">
                <span class="text-slate-600">↳ {{ row.fenetre.n }} relevé(s)</span>
                <span class="font-mono text-slate-500 ml-1.5">
                  <SensitiveValue>{{ row.fenetre.dates.slice(0, 6).join(' · ') }}</SensitiveValue>
                  <template v-if="row.fenetre.tronque">
                    <span class="text-slate-600"> … </span>
                    <SensitiveValue>{{ row.fenetre.dates.slice(-3).join(' · ') }}</SensitiveValue>
                  </template>
                </span>
              </td>
            </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div v-else-if="!loading" class="px-3 py-3 text-[11px] text-slate-600">
        Aucune date générée — vérifiez les bornes et la fréquence du calendrier.
      </div>
    </div>
    </details>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import SensitiveValue from './SensitiveValue.vue'

const props = defineProps({
  // Corps de requête de /api/schedule/generate, tel que l'appelant le compose.
  request: { type: Object, required: true },
  label:   { type: String, default: "Échéancier d'observation" },
  // Fréquence de relevé d'une constatation sur PÉRIODE ("3M"). Quand elle est
  // fournie, chaque constatation affiche les relevés qu'elle moyenne : c'est la
  // seule façon de vérifier qu'un calendrier annuel relevé trimestriellement
  // fait bien 3 constatations de 4 relevés, et non 12 observations.
  windowFrequency: { type: String, default: null },
})

const open    = ref(false)
const loading = ref(false)
const error   = ref('')
const data    = ref(null)
const fenetres = ref(null)

const STUB_LABELS = {
  short_last: 'stub court en fin', long_last: 'stub long en fin',
  short_first: 'stub court au début', long_first: 'stub long au début',
}
const CONVENTION_LABELS = {
  following: 'jour ouvré suivant',
  modified_following: 'suivant sauf changement de mois',
  preceding: 'jour ouvré précédent',
  modified_preceding: 'précédent sauf changement de mois',
}

// Paramètres ayant servi au dernier chargement. Se fier à la seule présence de
// `data` laissait afficher un échéancier périmé : replié, modifié, redéplié, il
// remontrait le calcul d'avant — des relevés qui ne correspondaient plus aux
// constatations affichées juste au-dessus.
let chargePour = null

function onToggle(event) {
  open.value = event.target.open
  if (open.value && (!data.value || chargePour !== signature.value)) load()
}

async function load() {
  const r = props.request
  if (!r?.start_date || !r?.end_date || !r?.frequency) {
    error.value = 'Calendrier incomplet — dates et fréquence requises.'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const res = await fetch('/api/schedule/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(r),
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Erreur serveur')
    data.value = await res.json()
    fenetres.value = props.windowFrequency ? await loadFenetres(r) : null
    chargePour = signature.value
  } catch (e) {
    error.value = e.message
    data.value = null
  } finally {
    loading.value = false
  }
}

/** Les relevés de chaque constatation. Un échec ici n'invalide pas
    l'échéancier : on perd le détail, pas les dates. */
async function loadFenetres(r) {
  try {
    const res = await fetch('/api/schedule/period-window', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_date: r.start_date, end_date: r.end_date, roll_date: r.roll_date,
        frequency: r.frequency, window_frequency: props.windowFrequency,
        stub: r.stub, currency: r.currency, convention: r.convention || 'none',
      }),
    })
    if (!res.ok) return null
    const d = await res.json()
    return Object.fromEntries((d.fenetres || []).map(f => [f.constatation, f]))
  } catch (e) {
    return null
  }
}

/** Signature des paramètres — scalaire, donc comparable. */
const signature = computed(() =>
  JSON.stringify(props.request) + '|' + (props.windowFrequency || ''))

// Ouvert, l'échéancier suit les champs qu'on modifie — après une pause, pour
// ne pas lancer un appel par frappe de clavier.
let timer = null
watch(signature, () => {
  if (!open.value) { data.value = null; fenetres.value = null; return }
  clearTimeout(timer)
  timer = setTimeout(load, 400)
})

const WEEKDAYS = ['dim.', 'lun.', 'mar.', 'mer.', 'jeu.', 'ven.', 'sam.']
const weekdayOf = iso => WEEKDAYS[new Date(iso + 'T12:00:00').getDay()]
const daysBetween = (a, b) =>
  Math.round((new Date(b + 'T12:00:00') - new Date(a + 'T12:00:00')) / 86400000)

const hasPayments = computed(() =>
  (data.value?.payment_dates || []).some((p, i) => p !== data.value.dates[i]))

const rows = computed(() => {
  const d = data.value
  if (!d?.dates?.length) return []
  const periods = d.dates.map((x, i) => (i === 0 ? null : daysBetween(d.dates[i - 1], x)))
  // Un stub se repère par rapport à la période TYPIQUE, pas à une moyenne : sur
  // douze périodes dont une courte, la médiane reste la période régulière.
  const regular = periods.filter(p => p != null).sort((a, b) => a - b)
  const median = regular.length ? regular[Math.floor(regular.length / 2)] : null

  return d.dates.map((date, i) => ({
    date,
    index: i === 0 ? null : i,
    weekday: weekdayOf(date),
    payment: d.payment_dates?.[i] !== date ? d.payment_dates?.[i] : null,
    days: periods[i],
    adjustedFrom: d.raw_dates?.[i] && d.raw_dates[i] !== date ? d.raw_dates[i] : null,
    isStub: median != null && periods[i] != null && Math.abs(periods[i] - median) > median * 0.2,
    isLast: i === d.dates.length - 1,
    fenetre: fenetres.value?.[date] || null,
  }))
})

const summary = computed(() => {
  const d = data.value
  if (!d?.dates?.length) return ''
  const r = props.request
  const parts = [
    `${d.dates.length - 1} constatation${d.dates.length > 2 ? 's' : ''}`,
    `${d.dates[1] || d.dates[0]} → ${d.dates[d.dates.length - 1]}`,
  ]
  if (r.frequency) parts.push(`tous les ${r.frequency}`)
  if (STUB_LABELS[r.stub]) parts.push(STUB_LABELS[r.stub])
  if (CONVENTION_LABELS[r.convention]) parts.push(CONVENTION_LABELS[r.convention])
  if (r.settlement_lag) parts.push(`règlement J+${r.settlement_lag}`)
  if (r.currency) parts.push(r.currency)
  return parts.join(' · ')
})
</script>

<style scoped>
/* Le chevron du composant remplace le marqueur natif : list-none suffit sur
   Firefox, WebKit demande son propre pseudo-element. */
summary::-webkit-details-marker { display: none; }
</style>
