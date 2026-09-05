<!--
  Lecture technique — niveaux, protections, exécution.

  Le DÉTAIL vient avant les moyennes, délibérément. Sur un portefeuille de dix
  transactions, la ligne à ligne est la vraie information et la moyenne n'en est
  qu'un résumé ; l'inverse ne devient vrai qu'à partir de plusieurs dizaines.
  Mettre la moyenne en tête inviterait à s'y fier trop tôt.

  Deux colonnes portent une information que rien d'autre dans l'application ne
  donne : **traité avec nous ou ailleurs**, et **à quel prix**. Trois états, pas
  deux — une case vide veut dire « on ne sait pas », jamais « ailleurs ».
-->
<template>
  <div v-if="tech" class="flex flex-col gap-5">

    <!-- ── Exécution : la part que nous avons servie ─────────── -->
    <div class="card flex flex-col gap-3">
      <div class="card-title mb-0">Avec nous, ou ailleurs</div>
      <p class="card-hint">
        Trois états et non deux : une transaction dont on ignore l'exécution
        n'est pas une transaction perdue. Les fondre gonflerait la part de
        marché qu'on croit ne pas avoir.
      </p>

      <div class="grid grid-cols-3 gap-3">
        <div class="stat-box">
          <div class="lbl">Avec nous</div>
          <div class="val" :class="{ vide: !exec.with_us }">{{ exec.with_us }}</div>
          <div class="sub">
            {{ exec.median_price_with_us !== null
               ? `prix médian ${pct(exec.median_price_with_us)}` : 'prix inconnu' }}
          </div>
        </div>
        <div class="stat-box">
          <div class="lbl">Ailleurs</div>
          <div class="val" :class="{ vide: !exec.elsewhere }">{{ exec.elsewhere }}</div>
          <div class="sub">
            {{ exec.median_price_elsewhere !== null
               ? `prix médian ${pct(exec.median_price_elsewhere)} sur ${exec.n_priced_elsewhere}`
               : 'aucun prix renseigné' }}
          </div>
        </div>
        <div class="stat-box">
          <div class="lbl">Inconnu</div>
          <div class="val vide">{{ exec.unknown }}</div>
          <div class="sub">à renseigner à l'import</div>
        </div>
      </div>

      <p v-if="ecartDePrix !== null" class="text-sm"
         :style="`color: ${ecartDePrix > 0 ? 'var(--negative)' : 'var(--positive)'}`">
        {{ ecartDePrix > 0
           ? `La concurrence a servi ${formatNumber(Math.abs(ecartDePrix), 2)} pt moins cher que nous en médiane.`
           : `Nous avons servi ${formatNumber(Math.abs(ecartDePrix), 2)} pt moins cher que la concurrence en médiane.` }}
        <span style="color: var(--muted)">
          Sur {{ exec.n_priced_elsewhere }} transaction(s) tarifée(s) ailleurs —
          {{ exec.n_priced_elsewhere < 3 ? 'trop peu pour en tirer une tendance'
             : 'de quoi commencer à lire une tendance' }}.
        </span>
      </p>
    </div>

    <!-- ── Moyennes par famille ──────────────────────────────── -->
    <div class="card flex flex-col gap-3">
      <div class="card-title mb-0">Niveaux par famille de sous-jacent</div>
      <p class="card-hint">
        Un coupon ne se compare qu'à famille égale : 14 % sur un panier
        d'actions et 6 % sur un mono-indice décrivent le même appétit. Médianes,
        et rien en dessous de deux observations.
      </p>

      <EmptyState v-if="!familles.length" icon="—"
                  title="Aucune transaction rattachée" />
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left" style="border-bottom: 1px solid var(--border)">
              <th class="py-2 pr-3 font-semibold">Famille</th>
              <th class="py-2 pr-3 font-semibold text-right">Trades</th>
              <th class="py-2 pr-3 font-semibold text-right">Coupon médian</th>
              <th class="py-2 font-semibold text-right">Protection médiane</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="f in familles" :key="f.label"
                style="border-bottom: 1px solid var(--border)">
              <td class="py-2 pr-3">
                {{ f.label }}
                <span v-if="f.partial" class="badge badge-muted ml-1"
                      title="Certains sous-jacents ne sont pas au catalogue : la famille est déduite de ceux qui le sont.">
                  partiel
                </span>
                <!-- La famille est celle du SOUS-JACENT : elle peut réunir
                     plusieurs payoffs, et une protection médiane calculée sur
                     un capital garanti et un autocall n'aurait aucun sens sans
                     que le lecteur voie ce qu'elle mélange. -->
                <span v-if="f.product_types?.length" class="block text-xs"
                      style="color: var(--subtle)">
                  {{ f.product_types.join(' · ') }}
                </span>
              </td>
              <td class="py-2 pr-3 text-right tabular-nums">{{ f.n_trades }}</td>
              <td class="py-2 pr-3 text-right tabular-nums">
                <template v-if="f.median_coupon_pct !== null">
                  {{ pct(f.median_coupon_pct) }}
                </template>
                <template v-else-if="f.single_coupon_pct !== null">
                  <span style="color: var(--muted)">
                    {{ pct(f.single_coupon_pct) }}
                    <span class="text-xs">(une seule)</span>
                  </span>
                </template>
                <span v-else style="color: var(--subtle)">—</span>
              </td>
              <td class="py-2 text-right tabular-nums">
                {{ f.median_protection_pct !== null
                   ? pct(f.median_protection_pct) : '—' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p v-if="couverture.unclassified_underlying" class="card-hint" style="margin:0">
        {{ couverture.unclassified_underlying }} transaction(s) portent un
        sous-jacent absent du catalogue : leur famille n'est pas déterminable, et
        elles sont regroupées à part plutôt que rangées au hasard.
      </p>
    </div>

    <!-- ── Le détail, deal par deal ──────────────────────────── -->
    <div class="card flex flex-col gap-3">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <div class="card-title mb-0">Détail transaction par transaction</div>
        <label class="flex items-center gap-2 text-sm cursor-pointer">
          <input v-model="ailleursSeulement" type="checkbox" />
          <span>Traitées ailleurs seulement</span>
        </label>
      </div>

      <EmptyState v-if="!lignesAffichees.length" icon="—"
                  :title="ailleursSeulement
                          ? 'Aucune transaction traitée ailleurs'
                          : 'Aucune transaction rattachée'" />
      <div v-else class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left" style="border-bottom: 1px solid var(--border)">
              <th class="py-2 pr-3 font-semibold">Date</th>
              <th class="py-2 pr-3 font-semibold">Structure</th>
              <th class="py-2 pr-3 font-semibold">Sous-jacent</th>
              <th class="py-2 pr-3 font-semibold">Émetteur</th>
              <th class="py-2 pr-3 font-semibold text-right">Nominal</th>
              <th class="py-2 pr-3 font-semibold text-right">Coupon</th>
              <th class="py-2 pr-3 font-semibold text-right">Protection</th>
              <th class="py-2 pr-3 font-semibold text-right">Prix</th>
              <th class="py-2 font-semibold">Exécution</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(l, i) in lignesAffichees" :key="i"
                style="border-bottom: 1px solid var(--border)">
              <td class="py-2 pr-3 tabular-nums whitespace-nowrap">
                {{ jour(l.trade_date) }}
              </td>
              <td class="py-2 pr-3">
                {{ l.product_type || '—' }}
                <span class="block text-xs" style="color: var(--subtle)">
                  {{ l.family_label }}
                </span>
              </td>
              <td class="py-2 pr-3" style="color: var(--muted)">
                {{ l.underlyings.join(' / ') || '—' }}
              </td>
              <td class="py-2 pr-3" style="color: var(--muted)">{{ l.issuer || '—' }}</td>
              <td class="py-2 pr-3 text-right tabular-nums">
                {{ l.notional ? montant(l.notional) : '—' }}
              </td>
              <td class="py-2 pr-3 text-right tabular-nums"
                  :class="{ absent: l.coupon_pct === null }">
                {{ l.coupon_pct !== null ? pct(l.coupon_pct) : '—' }}
              </td>
              <td class="py-2 pr-3 text-right tabular-nums"
                  :class="{ absent: l.protection_pct === null }"
                  :title="detailBarrieres(l)">
                {{ l.protection_pct !== null ? pct(l.protection_pct) : '—' }}
              </td>
              <td class="py-2 pr-3 text-right tabular-nums"
                  :class="{ absent: l.price_pct === null }">
                {{ l.price_pct !== null ? pct(l.price_pct) : '—' }}
              </td>
              <td class="py-2">
                <span class="badge" :class="classeExec(l.traded_with_us)">
                  {{ libelleExec(l.traded_with_us) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p class="card-hint" style="margin: 0">
        {{ couverture.with_coupon }} transaction(s) sur {{ couverture.n }} portent
        un coupon lisible, {{ couverture.with_protection }} une protection. Sur un
        deal booké ici, ces niveaux sont lus dans son script figé ; sur une ligne
        importée, ils viennent du fichier. Un tiret veut dire « non renseigné »,
        jamais zéro.
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import EmptyState from '../ui/EmptyState.vue'
import { formatDate, formatInt, formatNumber, formatPercent } from '../../utils/format.js'

const props = defineProps({
  tech: { type: Object, default: null },
})

const ailleursSeulement = ref(false)

const exec = computed(() => props.tech?.execution || {
  with_us: 0, elsewhere: 0, unknown: 0,
  median_price_elsewhere: null, median_price_with_us: null,
  n_priced_elsewhere: 0,
})
const familles = computed(() => props.tech?.by_family || [])
const couverture = computed(() => props.tech?.coverage || { n: 0 })

const lignesAffichees = computed(() => {
  const lignes = props.tech?.rows || []
  return ailleursSeulement.value
    ? lignes.filter(l => l.traded_with_us === false)
    : lignes
})

// L'écart de prix ne se calcule que si les DEUX médianes existent. Comparer
// notre prix à rien produirait un nombre qui ressemble à une mesure.
const ecartDePrix = computed(() => {
  const nous = exec.value.median_price_with_us
  const eux = exec.value.median_price_elsewhere
  if (nous === null || eux === null) return null
  return nous - eux
})

// Deux decimales fixes, pas « au plus deux » : dans une colonne alignee en
// tabular-nums, 8 % et 8,25 % doivent tomber sur la meme virgule.
const pct = (v) => formatPercent(v, 2)
const montant = formatInt
const jour = formatDate

function detailBarrieres(ligne) {
  if (!ligne.barriers?.length) return ''
  return ligne.barriers
    .map(b => `${b.name} · ${b.kind} · ${b.level_pct} %`)
    .join('\n')
}

function libelleExec(valeur) {
  return { true: 'Avec nous', false: 'Ailleurs' }[valeur] ?? 'Inconnu'
}

function classeExec(valeur) {
  return { true: 'badge-positive', false: 'badge-gold' }[valeur] ?? 'badge-muted'
}
</script>

<style scoped>
.lbl { font-size: .7rem; font-weight: 700; letter-spacing: .06em;
       text-transform: uppercase; color: var(--muted); }
.val { font-size: 1.7rem; font-weight: 800; letter-spacing: -.03em; line-height: 1.15; }
.val.vide { color: var(--subtle); font-weight: 700; }
.sub { font-size: .74rem; color: var(--subtle); }
/* Un niveau absent ne se lit pas comme un niveau nul. */
.absent { color: var(--subtle); }
</style>
