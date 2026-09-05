<!--
  Affichage d'une cadence — et de ce qui la justifie.

  Le principe de tout ce panneau : **rien ne s'affiche sans son explication**.
  La confiance est une pastille, mais les observations qui l'ont produite sont
  juste en dessous, en français. Un « confiance haute » qu'on ne peut pas
  justifier vaut moins qu'un « historique insuffisant » honnête.

  Sur l'absence de données, l'écran ne montre pas un tableau vide avec des
  tirets : il dit pourquoi il n'y a rien à dire.
-->
<template>
  <div class="flex flex-col gap-3">
    <div v-if="!cycle || cycle.confidence === 'insufficient_history'"
         class="rounded-[10px] p-4"
         style="background: var(--surface2); border: 1px solid var(--border)">
      <div class="text-sm font-semibold">Historique insuffisant</div>
      <ul class="mt-1.5 flex flex-col gap-0.5">
        <li v-for="(ligne, i) in (cycle?.explanation || ['Aucune transaction connue.'])"
            :key="i" class="text-xs" style="color: var(--muted)">{{ ligne }}</li>
      </ul>
      <p class="text-xs mt-2" style="color: var(--subtle)">
        Aucune fenêtre n'est proposée : une prédiction sur si peu d'observations
        ne serait ni vérifiable ni contestable.
      </p>
    </div>

    <template v-else>
      <div class="flex items-center gap-2 flex-wrap">
        <span class="badge" :class="classeConfiance">
          Confiance {{ libelleConfiance }}
        </span>
        <span class="badge badge-muted">{{ libelleCadence }}</span>
        <span v-if="cycle.overdue" class="badge badge-negative">
          En retard de {{ cycle.overdue_by_days }} j
        </span>
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div class="stat-box">
          <div class="text-xs" style="color: var(--muted)">Intervalle médian</div>
          <div class="text-lg font-bold tabular-nums">
            {{ Math.round(cycle.median_interval_days) }} j
          </div>
        </div>
        <div class="stat-box">
          <div class="text-xs" style="color: var(--muted)">Transactions</div>
          <div class="text-lg font-bold tabular-nums">{{ cycle.n_trades }}</div>
          <!-- Les intervalles se comptent sur des JOURNÉES : trois lignes le
               même jour sont un épisode, pas trois. Sans cette précision,
               « 5 transactions, 2 intervalles » est impossible à réconcilier. -->
          <div v-if="cycle.n_trading_days !== cycle.n_trades" class="text-xs"
               style="color: var(--subtle)">
            sur {{ cycle.n_trading_days }} journées
          </div>
        </div>
        <div class="stat-box">
          <div class="text-xs" style="color: var(--muted)">Dispersion</div>
          <div class="text-lg font-bold tabular-nums">
            ± {{ Math.round(cycle.dispersion_days) }} j
          </div>
        </div>
        <div class="stat-box">
          <div class="text-xs" style="color: var(--muted)">Depuis la dernière</div>
          <div class="text-lg font-bold tabular-nums">{{ cycle.days_since_last }} j</div>
        </div>
      </div>

      <!-- Les deux fenêtres, l'une au-dessus de l'autre : celle où l'on attend
           la transaction, et celle où il faut appeler pour y être. -->
      <div class="rounded-[10px] p-4 flex flex-col gap-3"
           style="background: var(--surface2); border: 1px solid var(--border)">
        <div>
          <div class="text-xs font-semibold uppercase tracking-wider"
               style="color: var(--muted)">Activité attendue</div>
          <div class="text-sm font-semibold">
            {{ plage(cycle.expected_window_start, cycle.expected_window_end) }}
          </div>
        </div>
        <div v-if="contactWindow?.start" style="border-top: 1px solid var(--border)"
             class="pt-3">
          <div class="text-xs font-semibold uppercase tracking-wider"
               style="color: var(--accent)">Contacter entre le</div>
          <div class="text-sm font-semibold">
            {{ plage(contactWindow.start, contactWindow.end) }}
          </div>
          <ul class="mt-1 flex flex-col gap-0.5">
            <li v-for="(ligne, i) in contactWindow.explanation" :key="i"
                class="text-xs" style="color: var(--subtle)">{{ ligne }}</li>
          </ul>
        </div>
      </div>

      <details class="text-xs">
        <summary class="cursor-pointer font-semibold" style="color: var(--muted)">
          Sur quoi repose ce calcul
        </summary>
        <ul class="mt-1.5 flex flex-col gap-0.5 pl-3">
          <li v-for="(ligne, i) in cycle.explanation" :key="i"
              style="color: var(--muted)">{{ ligne }}</li>
        </ul>
      </details>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  cycle: { type: Object, default: null },
  contactWindow: { type: Object, default: null },
})

const LIBELLES_CADENCE = {
  hebdomadaire: 'Cadence hebdomadaire',
  mensuelle: 'Cadence mensuelle',
  trimestrielle: 'Cadence trimestrielle',
  semestrielle: 'Cadence semestrielle',
  annuelle: 'Cadence annuelle',
  pluriannuelle: 'Cadence pluriannuelle',
  irreguliere: 'Cadence irrégulière',
}

const libelleCadence = computed(
  () => LIBELLES_CADENCE[props.cycle?.cadence] || 'Cadence indéterminée')

const libelleConfiance = computed(
  () => ({ high: 'haute', medium: 'moyenne', low: 'basse' }[props.cycle?.confidence]
        || '—'))

const classeConfiance = computed(() => ({
  high: 'badge-positive', medium: 'badge-gold', low: 'badge-muted',
}[props.cycle?.confidence] || 'badge-muted'))

function jourMois(iso) {
  if (!iso) return '—'
  const [, m, j] = String(iso).slice(0, 10).split('-')
  const MOIS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.',
                'août', 'sept.', 'oct.', 'nov.', 'déc.']
  return `${Number(j)} ${MOIS[Number(m) - 1]}`
}

// « 15–30 octobre » plutôt que deux dates complètes : c'est une plage qu'on
// lit, pas deux échéances qu'on note.
function plage(debut, fin) {
  if (!debut || !fin) return '—'
  const annee = String(fin).slice(0, 4)
  return `${jourMois(debut)} – ${jourMois(fin)} ${annee}`
}
</script>
