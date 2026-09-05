<!--
  Une dimension du déclaré/observé, en quatre états.

  Émetteurs, devises, structures, sous-jacents : la même grammaire partout, pour
  qu'on apprenne à lire une seule fois. Les groupes vides ne s'affichent pas —
  un bloc « aucun » est du bruit, sauf pour « à vérifier », dont l'absence est
  elle-même une information rassurante quand une politique existe.
-->
<template>
  <div class="flex flex-col gap-3">

    <div v-if="bloc.used?.length" class="flex flex-col gap-1.5">
      <div class="entete">
        <span class="puce" style="background: var(--positive)"></span>
        {{ mots.traites }}
      </div>
      <div class="chips">
        <span v-for="e in bloc.used" :key="e.label" class="chip"
              :class="e.unclassified ? 'chip-flou' : 'chip-used'"
              :title="titreDates(e)">
          {{ e.label }} <span class="compte">{{ e.count }}</span>
        </span>
      </div>
      <!-- Un libellé que le classifieur n'a pas su ranger n'est pas un écart :
           on ne sait simplement pas. Le dire vaut mieux que de le signaler à
           tort ou de le faire passer pour conforme. -->
      <p v-if="bloc.used.some(e => e.unclassified)" class="text-xs"
         style="color: var(--subtle)">
        Les entrées en gris n'ont pas pu être rattachées à une famille connue —
        elles ne sont ni confirmées conformes, ni signalées comme écarts.
      </p>
    </div>

    <div v-if="bloc.never_used?.length" class="flex flex-col gap-1.5">
      <div class="entete">
        <span class="puce" style="background: var(--accent)"></span>
        {{ mots.jamais }}
        <span class="aide">— {{ bloc.never_used.length }} {{ mots.aide }}</span>
      </div>
      <div class="chips">
        <span v-for="e in bloc.never_used" :key="e.label" class="chip chip-open">
          {{ e.label }}
        </span>
      </div>
    </div>

    <div v-if="bloc.excluded?.length" class="flex flex-col gap-1.5">
      <div class="entete">
        <span class="puce" style="background: var(--border2)"></span>
        Habituellement évités
      </div>
      <div class="chips">
        <span v-for="e in bloc.excluded" :key="e.label" class="chip chip-out">
          {{ e.label }}
        </span>
      </div>
    </div>

    <div v-if="bloc.to_check?.length" class="flex flex-col gap-1.5">
      <div class="entete">
        <span class="puce" style="background: var(--negative)"></span>
        Habitude à revalider
      </div>
      <div class="flex flex-col gap-1.5">
        <div v-for="e in bloc.to_check" :key="e.label" class="anomalie">
          <b>{{ e.label }} — {{ e.count }} transaction{{ e.count > 1 ? 's' : '' }}</b>
          <span v-if="e.first_date">
            {{ e.count > 1 ? `du ${jour(e.first_date)} au ${jour(e.last_date)}`
                           : `le ${jour(e.first_date)}` }}
          </span>
          <span class="motif">{{ MOTIFS[e.reason] || e.reason }}</span>
        </div>
      </div>
    </div>

    <!-- L'absence d'anomalie n'est rassurante que si une politique existe.
         Sans liste déclarée, il n'y a rien à respecter, donc rien à vérifier —
         et prétendre le contraire serait un faux calme. -->
    <p v-if="!bloc.has_policy" class="text-xs" style="color: var(--subtle)">
      Aucune préférence déclarée pour cette dimension. Les faits observés
      restent visibles sans être artificiellement qualifiés. Le profil courant
      se renseigne dans l'onglet Préférences.
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  bloc: { type: Object, required: true },
  // 'issuer' | 'product' | 'currency' | 'underlying'
  dimension: { type: String, default: 'issuer' },
  avecDates: { type: Boolean, default: false },
})

// On ne « sollicite » pas une devise ni une structure : on sollicite un
// émetteur. Un libellé générique appliqué partout donne des phrases qui
// sonnent faux, et une phrase qui sonne faux fait douter du chiffre à côté.
const VOCABULAIRE = {
  issuer: {
    traites: 'Sollicités',
    jamais: 'Habituellement retenus, jamais sollicités',
    aide: n => `${n} émetteur${n > 1 ? 's' : ''} à explorer`,
  },
  product: {
    traites: 'Traitées',
    jamais: 'Déclarées, jamais traitées',
    aide: n => `${n} structure${n > 1 ? 's' : ''} à proposer`,
  },
  currency: {
    traites: 'Traitées',
    jamais: 'Déclarées, jamais utilisées',
    aide: n => `${n} devise${n > 1 ? 's' : ''} ouverte${n > 1 ? 's' : ''}`,
  },
  underlying: {
    traites: 'Traités',
    jamais: 'Dans son univers, jamais utilisés',
    aide: n => `${n} sous-jacent${n > 1 ? 's' : ''} disponible${n > 1 ? 's' : ''}`,
  },
}

const mots = computed(() => {
  const v = VOCABULAIRE[props.dimension] || VOCABULAIRE.issuer
  return {
    traites: v.traites,
    jamais: v.jamais,
    aide: v.aide(props.bloc.never_used?.length || 0),
  }
})

const MOTIFS = {
  excluded: "a été traité malgré une habitude d'évitement — le profil a peut-être évolué",
  off_list: "n'apparaît pas dans les habitudes déclarées — le profil est peut-être incomplet ou a évolué",
}

function jour(iso) {
  if (!iso) return '—'
  const [a, m, j] = String(iso).slice(0, 10).split('-')
  return `${j}/${m}/${a}`
}

function titreDates(e) {
  if (!e.first_date) return `${e.count} transaction(s)`
  return e.first_date === e.last_date
    ? `1 transaction le ${jour(e.first_date)}`
    : `${e.count} transactions, du ${jour(e.first_date)} au ${jour(e.last_date)}`
}
</script>

<style scoped>
.entete { display: flex; align-items: center; gap: .45rem;
          font-size: .76rem; font-weight: 700; }
.entete .puce { width: 9px; height: 9px; border-radius: 2px; flex: none; }
.entete .aide { font-weight: 500; color: var(--muted); }

.chips { display: flex; flex-wrap: wrap; gap: .35rem; }
.chip { display: inline-flex; align-items: center; gap: .35rem;
        padding: .25rem .55rem; border-radius: 8px; font-size: .8rem;
        font-weight: 600; border: 1px solid var(--border);
        background: var(--surface2); }
.chip .compte { font-family: 'JetBrains Mono', monospace; font-size: .7rem;
                font-weight: 700; opacity: .75; }
.chip-used { background: var(--positive-light); border-color: rgba(26,122,74,.3);
             color: var(--positive); }
.chip-open { background: var(--accent-light); border-color: rgba(26,95,160,.3);
             color: var(--accent); }
.chip-out  { background: var(--surface2); color: var(--subtle);
             text-decoration: line-through; text-decoration-thickness: 1.5px; }
/* Ni vert ni rouge : l'incertitude a sa propre teinte, comme l'absence. */
.chip-flou { background: var(--surface2); color: var(--muted);
             border-style: dashed; }

.anomalie { background: var(--negative-light); border: 1px solid rgba(192,57,43,.3);
            border-radius: 10px; padding: .55rem .75rem; font-size: .8rem; }
.anomalie .motif { display: block; color: var(--muted); font-size: .76rem;
                   margin-top: .15rem; }
</style>
