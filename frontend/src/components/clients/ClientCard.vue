<!--
  La fiche visuelle d'un client — un seul composant, deux états.

  Ce n'est PAS un écran riche et un écran dégradé : c'est le même écran dont le
  centre de gravité se déplace. Sur un client établi, il répond à « comment le
  piloter » ; sur un client à deux transactions, à « par où commencer », et le
  bloc des émetteurs jamais sollicités passe de complément à sujet principal.

  Une règle de forme porte toute l'honnêteté du composant : **l'absence a sa
  propre couleur**. Un tiret gris ne se confond ni avec un zéro ni avec un
  chiffre, et une bande large en pointillé ne se lit pas comme une bande étroite
  et pleine. La forme dit le degré de certitude avant que le texte ne l'explique.
-->
<template>
  <div v-if="fiche" class="flex flex-col gap-5">

    <!-- ── Carte d'identité ─────────────────────────────────── -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <div class="stat-box">
        <div class="lbl">Cadence</div>
        <div class="val" :class="{ vide: !cadenceLisible }">
          {{ cadenceLisible ? Math.round(cycle.median_interval_days) + ' j' : '—' }}
        </div>
        <div class="sub">{{ sousCadence }}</div>
      </div>
      <div class="stat-box">
        <div class="lbl">Dernière transaction</div>
        <div class="val" :class="{ vide: cycle.days_since_last === null }">
          {{ cycle.days_since_last !== null ? cycle.days_since_last + ' j' : '—' }}
        </div>
        <div class="sub">
          {{ cycle.last_trade_date ? 'le ' + jourCourt(cycle.last_trade_date)
             : 'aucune transaction' }}
        </div>
      </div>
      <div class="stat-box">
        <div class="lbl">Ticket</div>
        <div class="val" :class="{ vide: !ticketTexte }">{{ ticketTexte || '—' }}</div>
        <div class="sub">{{ sousTicket }}</div>
      </div>
      <div class="stat-box">
        <div class="lbl">Structure dominante</div>
        <div class="val" :class="{ vide: !dominante }" style="font-size:1.05rem">
          {{ dominante || '—' }}
        </div>
        <div class="sub">{{ sousDominante }}</div>
      </div>
    </div>

    <!-- ── Cadence : la frise, ou les transactions listées ───── -->
    <div class="card flex flex-col gap-3">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <div class="card-title mb-0">
          {{ assezPourUneFrise ? 'Rythme des transactions' : 'Les transactions' }}
        </div>
        <div class="flex items-center gap-1.5 flex-wrap">
          <span class="badge badge-gold">
            {{ fiche.behaviour.evidence?.label || 'Volume non qualifié' }}
          </span>
          <span class="badge badge-muted">
            {{ fiche.recency?.label || 'Récence inconnue' }}
          </span>
          <template v-if="fiche.behaviour.n_imported">
            <span class="badge badge-positive">
              {{ fiche.behaviour.n_trades - fiche.behaviour.n_imported }} bookées ici
            </span>
            <span class="badge badge-muted">
              {{ fiche.behaviour.n_imported }} importées
            </span>
          </template>
        </div>
      </div>

      <EmptyState v-if="!transactions.length" icon="—"
                  title="Aucune transaction rattachée"
                  hint="Un import d'historique, ou un premier deal booké depuis une opportunité, feront parler cet écran." />

      <!-- En dessous d'un seuil : les faits bruts, pas des parts.
           « 50 % d'autocalls » sur deux lignes habille un manque. -->
      <template v-else-if="!assezPourUneFrise">
        <p class="card-hint">
          En dessous de {{ SEUIL_FRISE }} transactions, l'écran montre les faits
          bruts plutôt que des proportions qui n'en seraient pas.
        </p>
        <ul class="flex flex-col">
          <li v-for="(t, i) in transactions" :key="i"
              class="py-2.5 grid gap-3 items-baseline txn-row"
              style="grid-template-columns: 6.5rem 1fr auto">
            <span class="text-xs tabular-nums" style="color: var(--muted)">
              {{ jourCourt(t.trade_date) }}
            </span>
            <span class="text-sm">
              {{ t.product_type || 'Structure non renseignée' }}
              <span class="block text-xs" style="color: var(--subtle)">
                {{ [t.issuer, t.underlyings.join(' / '), t.currency]
                     .filter(Boolean).join(' · ') }}
                <span v-if="t.imported"> · importée</span>
              </span>
            </span>
            <span class="text-sm font-bold tabular-nums whitespace-nowrap">
              {{ t.notional ? montantCourt(t.notional) : '—' }}
            </span>
          </li>
        </ul>
        <p v-if="cycle.n_intervals === 1" class="text-xs"
           style="color: var(--accent)">
          Un seul intervalle connu : {{ Math.round(cycle.median_interval_days) }} jours.
        </p>
      </template>

      <div v-else class="overflow-x-auto">
        <svg class="frise" :viewBox="`0 0 1000 96`" preserveAspectRatio="none"
             role="img" :aria-label="`Frise de ${transactions.length} transactions`">
          <rect v-if="fenetreAttendue" :x="fenetreAttendue.x"
                :width="fenetreAttendue.w" y="22" height="40"
                fill="var(--accent-light)" stroke="var(--accent)"
                stroke-opacity=".45" stroke-dasharray="3 2" rx="2" />
          <line x1="0" y1="62" x2="1000" y2="62" stroke="var(--border2)" />
          <line :x1="xAujourdhui" y1="20" :x2="xAujourdhui" y2="70"
                stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="2 2" />
          <g>
            <circle v-for="(pt, i) in pointsFrise" :key="i" :cx="pt.x" cy="62"
                    :r="pt.multi ? 7 : 5" fill="var(--positive)"
                    :stroke="pt.multi ? 'var(--surface)' : 'none'" stroke-width="2">
              <title>{{ pt.titre }}</title>
            </circle>
          </g>
          <text :x="xAujourdhui" y="86" text-anchor="end"
                style="font-size:11px;font-weight:700" fill="var(--muted)">
            aujourd'hui
          </text>
        </svg>
      </div>

      <p v-if="assezPourUneFrise && cycle.n_trading_days !== cycle.n_trades"
         class="card-hint" style="margin: 0">
        {{ cycle.n_trades }} transactions réparties sur {{ cycle.n_trading_days }}
        journées — les points épais portent plusieurs lignes le même jour, un
        panier alloué en plusieurs fois restant un seul épisode d'investissement.
      </p>
    </div>

    <!-- ── Fenêtre d'activité, à sa juste largeur ────────────── -->
    <div v-if="cycle.expected_window_start" class="card flex flex-col gap-3">
      <div class="card-title mb-0">
        Fenêtre d'activité{{ cycle.confidence === 'low' ? ' — à titre indicatif' : '' }}
      </div>
      <p class="card-hint">
        {{ cycle.confidence === 'low'
           ? "Trop peu d'intervalles pour mesurer une dispersion : la fenêtre est élargie par défaut, et sa largeur est le message."
           : "Dérivée de la dispersion observée, jamais d'une date choisie." }}
      </p>
      <CyclePanel :cycle="cycle" :contact-window="fiche.contact_window" />
    </div>

    <!-- Les habitudes sont des comptages explicables par dimension. Aucun
         score global ne transforme 3 observations en vérité sur le Client. -->
    <div v-if="habitsVisibles.length" class="card flex flex-col gap-3">
      <div class="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div class="card-title mb-0">Habitudes de trading observées</div>
          <p class="card-hint" style="margin-top: .35rem">
            Chaque part utilise uniquement les transactions où la dimension est renseignée.
            Ouvrez une valeur pour retrouver les lignes qui la justifient.
          </p>
        </div>
        <span class="badge badge-muted">{{ fiche.scope?.name || fiche.name }}</span>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div v-for="dimension in habitsVisibles" :key="dimension.key" class="habit-box">
          <div class="flex items-center justify-between gap-2">
            <span class="label mb-0">{{ dimension.label }}</span>
            <span class="text-xs tabular-nums" style="color: var(--subtle)">
              {{ dimension.coverage_count }}/{{ dimension.total_count }} renseignées
            </span>
          </div>
          <details v-for="item in dimension.values.slice(0, 5)"
                   :key="item.value" class="habit-line">
            <summary class="cursor-pointer">
              <span class="font-semibold">{{ item.value }}</span>
              <span class="ml-auto tabular-nums">{{ item.count }}</span>
              <span style="color: var(--subtle)">· {{ pourcentage(item.share) }}</span>
            </summary>
            <div class="habit-proof">
              {{ item.evidence_level.label }} · {{ item.recency.label }}
              <template v-if="item.last_observation"> · dernière le {{ jourCourt(item.last_observation) }}</template>
              <div v-for="preuve in item.evidence.slice(0, 6)"
                   :key="`${preuve.source_type}-${preuve.source_id}`">
                {{ jourCourt(preuve.trade_date) }} · {{ preuve.reference || `${preuve.source_type} #${preuve.source_id}` }}
                · {{ libelleOrigine(preuve.data_origin) }}
              </div>
            </div>
          </details>
        </div>
      </div>
    </div>

    <div v-if="fiche.mandate_divergences?.length" class="card flex flex-col gap-3">
      <div class="card-title mb-0">Différences entre mandats</div>
      <p class="card-hint">
        La vue Client ne les fusionne pas en une habitude moyenne. Sélectionnez un mandat
        au-dessus pour lire son profil propre.
      </p>
      <div v-for="divergence in fiche.mandate_divergences" :key="divergence.key"
           class="divergence-row">
        <span class="text-sm font-semibold">{{ divergence.label }}</span>
        <span v-for="item in divergence.values" :key="item.value" class="text-xs">
          <b>{{ item.value }}</b> — {{ item.mandates.join(', ') }}
        </span>
      </div>
    </div>

    <div v-if="providerStats.length || fiche.questions?.length"
         class="card flex flex-col gap-3">
      <div>
        <div class="card-title mb-0">Habitudes de sélection des fournisseurs</div>
        <p class="card-hint" style="margin-top: .35rem">
          RFQ exécutées seulement. « Meilleur non retenu » décrit le résultat observé ;
          il ne suppose ni interdiction ni cause.
        </p>
      </div>
      <div v-for="question in fiche.questions || []" :key="question.provider"
           class="question-box">
        <b>À revalider</b> — {{ question.message }}
      </div>
      <div v-if="providerStats.length" class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left" style="border-bottom: 1px solid var(--border)">
              <th class="py-2 pr-3 font-semibold">Fournisseur</th>
              <th class="py-2 px-2 text-right font-semibold">Sollicité</th>
              <th class="py-2 px-2 text-right font-semibold">Comparable</th>
              <th class="py-2 px-2 text-right font-semibold">Meilleur</th>
              <th class="py-2 px-2 text-right font-semibold">Retenu</th>
              <th class="py-2 pl-2 text-right font-semibold">Meilleur non retenu</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="provider in providerStats" :key="provider.provider"
                style="border-bottom: 1px solid var(--border)">
              <td class="py-2 pr-3">
                <span class="font-semibold">{{ provider.provider }}</span>
                <span class="block text-xs" style="color: var(--subtle)">
                  {{ provider.evidence_level.label }}<template v-if="provider.last_observation"> · {{ jourCourt(provider.last_observation) }}</template>
                </span>
              </td>
              <td class="py-2 px-2 text-right tabular-nums">{{ provider.solicited }}</td>
              <td class="py-2 px-2 text-right tabular-nums">{{ provider.comparable }}</td>
              <td class="py-2 px-2 text-right tabular-nums">{{ provider.best }}</td>
              <td class="py-2 px-2 text-right tabular-nums">{{ provider.selected }}</td>
              <td class="py-2 pl-2 text-right tabular-nums font-semibold"
                  :style="provider.best_not_selected ? 'color: var(--gold)' : ''">
                {{ provider.best_not_selected }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── Émetteurs : l'espace négatif ──────────────────────── -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <div class="card flex flex-col gap-3">
        <div class="card-title mb-0">
          Émetteurs — ce qui est traité, et ce qui ne l'est pas
        </div>
        <p class="card-hint">
          Le déclaré et l'observé superposés. Ce n'est pas un graphique : la
          question est l'appartenance, pas la magnitude.
        </p>
        <DimensionGrid :bloc="espace.issuers" dimension="issuer"
                       :avec-dates="true" />
        <p v-if="espace.issuers.to_check.length && espace.exclusion_dates_unknown"
           class="text-xs" style="color: var(--muted)">
          La date de début de l'habitude d'évitement n'est pas conservée : les
          transactions peuvent lui être antérieures ou montrer une évolution.
          Les dates restent visibles pour que le commercial revalide le profil.
        </p>
      </div>

      <div class="flex flex-col gap-5">
        <!-- Bornes -->
        <div class="card flex flex-col gap-4">
          <div class="card-title mb-0">L'observé face aux repères déclarés</div>
          <RangeRail titre="Ticket" :borne="fiche.ranges.ticket"
                     :format="montantCourt" />
          <RangeRail titre="Maturité" :borne="fiche.ranges.maturity_months"
                     :format="v => Math.round(v) + ' mois'" />
        </div>

        <!-- Structures et devises -->
        <div class="card flex flex-col gap-3">
          <div class="card-title mb-0">Structures et devises</div>
          <DimensionGrid :bloc="espace.product_types" dimension="product" />
          <div style="border-top: 1px solid var(--border)" class="pt-3">
            <DimensionGrid :bloc="espace.currencies" dimension="currency" />
          </div>
        </div>
      </div>
    </div>

    <!-- ── Conversion et refus ───────────────────────────────── -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <div class="card flex flex-col gap-3">
        <div class="card-title mb-0">Pourquoi ça n'aboutit pas</div>
        <EmptyState v-if="!fiche.lost_reasons.length" icon="—"
                    title="Aucun dossier perdu documenté"
                    hint="Le motif est demandé à la clôture d'une opportunité perdue." />
        <ul v-else class="flex flex-col gap-2">
          <li v-for="([motif, compte]) in fiche.lost_reasons" :key="motif"
              class="grid items-center gap-3" style="grid-template-columns: 11rem 1fr 2rem">
            <span class="text-sm">{{ libelleRaisonPerte(motif) }}</span>
            <div class="h-3.5 rounded-r" style="background: var(--surface2)">
              <div class="h-full rounded-r" style="background: var(--negative)"
                   :style="{ width: partRefus(compte) }"></div>
            </div>
            <span class="text-sm text-right tabular-nums"
                  style="color: var(--muted)">{{ compte }}</span>
          </li>
        </ul>
      </div>

      <div class="card flex flex-col gap-3">
        <div class="card-title mb-0">Conversion</div>
        <div class="flex items-baseline gap-3">
          <span class="text-3xl font-extrabold tracking-tight tabular-nums"
                :style="conversion.rate === null ? 'color: var(--subtle)' : ''">
            {{ conversion.rate === null ? '—'
               : Math.round(conversion.rate * 100) + ' %' }}
          </span>
          <span class="text-sm" style="color: var(--muted)">
            {{ conversion.decided
               ? `sur ${conversion.decided} dossier(s) tranché(s)`
               : 'aucun dossier tranché' }}
          </span>
        </div>
        <p class="card-hint" style="margin: 0">
          Les dossiers encore ouverts sont exclus du dénominateur : les inclure
          ferait baisser le taux à mesure qu'on prospecte. Et sans dossier
          tranché, le chiffre reste vide — jamais zéro, qui se lirait
          « on perd tout ».
        </p>
      </div>
    </div>

    <!-- ── Les seuils, quand l'écran ne peut pas tout dire ───── -->
    <div v-if="seuilsRestants.length" class="card flex flex-col gap-3">
      <div class="card-title mb-0">
        Ce que l'écran pourra dire, et à partir de quand
      </div>
      <p class="card-hint">
        Un écran vide qui n'explique pas son vide se fait ignorer. Ces seuils
        sont ceux du moteur, pas une promesse.
      </p>
      <ul class="flex flex-col">
        <li v-for="seuil in fiche.thresholds" :key="seuil.what"
            class="grid gap-3 py-2.5 seuil-row"
            style="grid-template-columns: 2.4rem 1fr">
          <span class="text-right font-bold tabular-nums text-sm"
                :style="seuil.reached ? 'color: var(--positive)' : 'color: var(--accent)'">
            {{ seuil.reached ? '✓' : (seuil.at ? '+' + seuil.at : '↺') }}
          </span>
          <span class="text-sm" :class="{ 'opacity-55': seuil.reached }">
            <span class="font-semibold">{{ seuil.label }}</span>
            <span class="block text-xs" style="color: var(--muted)">
              {{ seuil.detail }}
            </span>
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { libelleRaisonPerte } from '../../stores/clients.js'
import EmptyState from '../ui/EmptyState.vue'
import CyclePanel from './CyclePanel.vue'
import DimensionGrid from './DimensionGrid.vue'
import RangeRail from './RangeRail.vue'
import { formatInt, formatNumber } from '../../utils/format.js'

// En dessous de ce nombre, une frise et des proportions mentiraient : on liste.
const SEUIL_FRISE = 5

const props = defineProps({
  fiche: { type: Object, default: null },
})

const cycle = computed(() => props.fiche?.cycle || {})
const espace = computed(() => props.fiche?.negative_space || {})
const conversion = computed(() => props.fiche?.conversion || {})
const transactions = computed(() => props.fiche?.transactions || [])
const assezPourUneFrise = computed(() => transactions.value.length >= SEUIL_FRISE)
const habitsVisibles = computed(
  () => (props.fiche?.habits || []).filter(row => row.values?.length))
const providerStats = computed(
  () => props.fiche?.provider_selection?.providers || [])

function pourcentage(part) {
  return part === null || part === undefined ? '—' : `${Math.round(part * 100)} %`
}
function libelleOrigine(origin) {
  return { imported: 'historique importé', native: 'booké ici',
           demo: 'fictif / UAT' }[origin] || origin || 'origine inconnue'
}

// Une cadence ne se nomme qu'à partir d'un intervalle mesuré. Sous ce seuil, le
// tiret gris — qui ne se confond ni avec un zéro ni avec un chiffre.
const cadenceLisible = computed(
  () => cycle.value.median_interval_days !== null
        && cycle.value.median_interval_days !== undefined
        && cycle.value.n_intervals >= 1)

const sousCadence = computed(() => {
  if (!cadenceLisible.value) return 'aucun intervalle mesurable'
  if (cycle.value.n_intervals === 1) return '1 seul intervalle mesuré'
  return `médiane · ±${Math.round(cycle.value.dispersion_days)} j de dispersion`
})

// Sur peu d'observations, les montants eux-mêmes plutôt que leur milieu.
const ticketTexte = computed(() => {
  const t = props.fiche?.ranges?.ticket
  if (!t || !t.n) return null
  if (t.points.length) {
    const uniques = [...new Set(t.points.map(montantCourt))]
    return uniques.length === 1 ? uniques[0]
      : `${uniques[0]} – ${uniques[uniques.length - 1]}`
  }
  return montantCourt(t.median)
})

const sousTicket = computed(() => {
  const t = props.fiche?.ranges?.ticket
  if (!t || !t.n) return 'aucune transaction'
  if (t.points.length) return `les ${t.n} montants, pas une médiane`
  return 'médian'
})

// Une structure n'est « dominante » que si elle domine réellement quelque chose.
const dominante = computed(() => {
  const types = props.fiche?.behaviour?.product_types || []
  if (!types.length || transactions.value.length < 3) return null
  if (types.length > 1 && types[0][1] === types[1][1]) return null
  return types[0][0]
})

const sousDominante = computed(() => {
  const types = props.fiche?.behaviour?.product_types || []
  if (!transactions.value.length) return 'aucune transaction'
  if (!dominante.value) {
    return types.length > 1 ? 'aucune ne se dégage' : 'trop peu de transactions'
  }
  return `${qualification(types[0][1])} · ${types[0][1]} sur ${props.fiche.behaviour.n_trades}`
})

function qualification(n) {
  if (n <= 1) return 'observation isolée'
  if (n === 2) return 'répétition observée'
  if (n <= 4) return 'tendance émergente'
  if (n <= 9) return 'habitude observée'
  return 'habitude bien documentée'
}

const seuilsRestants = computed(
  () => (props.fiche?.thresholds || []).filter(s => !s.reached))

// ── Frise ────────────────────────────────────────────────────────────
const bornesTemps = computed(() => {
  const jours = transactions.value
    .map(t => t.trade_date).filter(Boolean).map(d => new Date(d).getTime())
  if (!jours.length) return null
  const fin = Math.max(Date.now(), ...jours,
    cycle.value.expected_window_end
      ? new Date(cycle.value.expected_window_end).getTime() : 0)
  const debut = Math.min(...jours)
  // Une marge de 4 % de part et d'autre pour que le premier point ne colle pas
  // au bord — sans elle, la première transaction paraît tronquée.
  const span = (fin - debut) || 1
  return { debut: debut - span * 0.04, fin: fin + span * 0.04 }
})

function x(iso) {
  const b = bornesTemps.value
  if (!b || !iso) return 0
  const t = new Date(iso).getTime()
  return Math.max(0, Math.min(1000, ((t - b.debut) / (b.fin - b.debut)) * 1000))
}

const xAujourdhui = computed(() => {
  const b = bornesTemps.value
  if (!b) return 0
  return Math.max(0, Math.min(1000,
    ((Date.now() - b.debut) / (b.fin - b.debut)) * 1000))
})

const pointsFrise = computed(() => {
  const parJour = new Map()
  for (const t of transactions.value) {
    if (!t.trade_date) continue
    const cle = t.trade_date.slice(0, 10)
    if (!parJour.has(cle)) parJour.set(cle, [])
    parJour.get(cle).push(t)
  }
  return [...parJour.entries()].map(([jour, lignes]) => ({
    x: x(jour),
    multi: lignes.length > 1,
    titre: `${jourCourt(jour)} — ${lignes.length > 1 ? lignes.length + ' lignes · ' : ''}`
      + lignes.map(l => [l.product_type, l.issuer,
                         l.notional ? montantCourt(l.notional) : null]
        .filter(Boolean).join(' · ')).join(' | '),
  }))
})

const fenetreAttendue = computed(() => {
  if (!cycle.value.expected_window_start) return null
  const debut = x(cycle.value.expected_window_start)
  const fin = x(cycle.value.expected_window_end)
  return { x: debut, w: Math.max(4, fin - debut) }
})

function partRefus(compte) {
  const max = Math.max(...(props.fiche?.lost_reasons || [[null, 1]]).map(([, n]) => n))
  return `${Math.round((compte / max) * 100)}%`
}

function jourCourt(iso) {
  if (!iso) return '—'
  const [a, m, j] = String(iso).slice(0, 10).split('-')
  return `${j}/${m}/${a.slice(2)}`
}

function montantCourt(v) {
  if (v === null || v === undefined) return '—'
  const abs = Math.abs(v)
  if (abs >= 1e6) {
    const millions = v / 1e6
    // Un compte rond de millions ne s'ecrit pas « 12,0 M ».
    return `${formatNumber(millions, Number.isInteger(millions) ? 0 : 1)} M`
  }
  if (abs >= 1e3) return `${formatInt(v / 1e3)} k`
  return formatInt(v)
}
</script>

<style scoped>
.lbl { font-size: .7rem; font-weight: 700; letter-spacing: .06em;
       text-transform: uppercase; color: var(--muted); }
.val { font-size: 1.7rem; font-weight: 800; letter-spacing: -.03em; line-height: 1.15; }
/* L'absence a sa propre couleur : un tiret gris ne se lit pas comme un zéro. */
.val.vide { color: var(--subtle); font-weight: 700; }
.sub { font-size: .74rem; color: var(--subtle); }

.frise { display: block; width: 100%; min-width: 34rem; height: 96px; }
.txn-row { border-bottom: 1px solid var(--border); }
.txn-row:last-child { border-bottom: 0; }
.seuil-row { border-bottom: 1px solid var(--border); }
.seuil-row:last-child { border-bottom: 0; }
.habit-box { border: 1px solid var(--border); border-radius: .55rem; padding: .7rem; }
.habit-line { border-top: 1px solid var(--border); padding: .45rem 0; }
.habit-line:first-of-type { margin-top: .45rem; }
.habit-line summary { display: flex; align-items: baseline; gap: .4rem; font-size: .8rem; }
.habit-proof { padding: .35rem 0 0 .7rem; font-size: .72rem; color: var(--muted); }
.divergence-row { display: grid; gap: .35rem; grid-template-columns: 10rem 1fr 1fr;
                  padding: .55rem 0; border-top: 1px solid var(--border); }
.question-box { padding: .65rem .8rem; border-radius: .55rem;
                background: var(--gold-light); border: 1px solid rgba(184,134,11,.35);
                font-size: .8rem; }
@media (max-width: 640px) { .divergence-row { grid-template-columns: 1fr; } }
</style>
