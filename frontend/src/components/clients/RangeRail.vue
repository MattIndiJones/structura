<!--
  L'observé dans le déclaré — un rail, une bande ou des points.

  La distinction n'est pas cosmétique. Au-delà d'un seuil d'observations, la
  moitié centrale se dessine en bande : elle décrit une distribution qui existe.
  En dessous, on pose les points eux-mêmes — dessiner une bande sur deux
  observations inventerait une dispersion que rien ne mesure.

  Sans fourchette déclarée, il n'y a pas de rail : on ne peut pas situer un
  observé dans un déclaré qui n'existe pas, et un rail arbitraire ferait croire
  à une contrainte.
-->
<template>
  <div class="flex flex-col gap-1.5">
    <div class="flex justify-between items-baseline text-sm">
      <span>{{ titre }}</span>
      <span v-if="resume" class="font-extrabold tabular-nums">{{ resume }}</span>
      <span v-else class="text-xs" style="color: var(--subtle)">
        {{ borne.n ? `${borne.n} observation(s)` : 'aucune observation' }}
      </span>
    </div>

    <template v-if="aUnRail">
      <div class="rail" :title="infobulle">
        <div class="piste"></div>
        <div v-if="bande" class="bande"
             :style="{ left: bande.gauche, width: bande.largeur }"></div>
        <div v-for="(p, i) in pointsPositionnes" :key="i" class="point"
             :style="{ left: p }"></div>
        <div v-if="bande && mediane" class="mediane" :style="{ left: mediane }"></div>
      </div>
      <div class="bornes">
        <span class="tabular-nums">{{ format(borne.declared_min) }}</span>
        <span class="tabular-nums">{{ format(borne.declared_max) }}</span>
      </div>
      <p v-if="borne.n && !bande" class="note">
        {{ borne.n === 1 ? 'Une seule observation' : `${borne.n} observations` }} —
        les valeurs elles-mêmes plutôt qu'une bande, qui inventerait une
        dispersion.
      </p>
    </template>

    <p v-else class="note">
      Aucun repère déclaré : l'observé reste affiché sans inventer une
      fourchette de préférence.
      <span v-if="borne.n">
        Valeur{{ borne.n > 1 ? 's' : '' }} observée{{ borne.n > 1 ? 's' : '' }} :
        {{ (borne.points.length ? borne.points : [borne.median]).map(format).join(', ') }}.
      </span>
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  titre: { type: String, required: true },
  borne: { type: Object, required: true },
  format: { type: Function, default: v => String(v) },
})

const aUnRail = computed(
  () => props.borne.declared_min !== null && props.borne.declared_min !== undefined
     && props.borne.declared_max !== null && props.borne.declared_max !== undefined
     && props.borne.declared_max > props.borne.declared_min)

function position(valeur) {
  const { declared_min: min, declared_max: max } = props.borne
  const brut = ((valeur - min) / (max - min)) * 100
  // Une valeur hors fourchette existe — un ticket sous le plancher déclaré est
  // précisément ce qu'on veut voir. On la garde visible au bord plutôt que de
  // la faire disparaître du rail.
  return `${Math.max(0, Math.min(100, brut))}%`
}

const bande = computed(() => {
  if (!aUnRail.value || !props.borne.band) return null
  const [bas, haut] = props.borne.band
  const g = parseFloat(position(bas))
  const d = parseFloat(position(haut))
  return { gauche: `${g}%`, largeur: `${Math.max(1.5, d - g)}%` }
})

const mediane = computed(
  () => props.borne.median !== null && props.borne.median !== undefined
    ? position(props.borne.median) : null)

const pointsPositionnes = computed(
  () => aUnRail.value ? (props.borne.points || []).map(position) : [])

const resume = computed(() => {
  if (!props.borne.n) return null
  if (props.borne.band) return props.format(props.borne.median)
  const valeurs = [...new Set((props.borne.points || []).map(props.format))]
  return valeurs.length === 1 ? valeurs[0]
    : `${valeurs[0]} – ${valeurs[valeurs.length - 1]}`
})

const infobulle = computed(() => {
  const parts = [`Déclaré ${props.format(props.borne.declared_min)}`
                 + ` – ${props.format(props.borne.declared_max)}`]
  if (props.borne.band) {
    parts.push(`moitié centrale ${props.format(props.borne.band[0])}`
               + ` – ${props.format(props.borne.band[1])}`)
    parts.push(`médiane ${props.format(props.borne.median)}`)
  } else if (props.borne.points?.length) {
    parts.push(`observé ${props.borne.points.map(props.format).join(', ')}`)
  }
  return parts.join(' · ')
})
</script>

<style scoped>
.rail { position: relative; height: 24px; }
.piste { position: absolute; inset: 8px 0; background: var(--surface2);
         border: 1px solid var(--border2); border-radius: 4px; }
.bande { position: absolute; top: 5px; bottom: 5px; background: var(--accent-light);
         border: 1px solid rgba(26,95,160,.35); border-radius: 3px; }
.mediane { position: absolute; top: 2px; bottom: 2px; width: 3px;
           background: var(--accent); border-radius: 2px; margin-left: -1px; }
/* Des points, pas une bande : ils disent « voici ce qu'on a vu », pas
   « voici comment ça se distribue ». */
.point { position: absolute; top: 6px; width: 10px; height: 10px;
         margin-left: -5px; background: var(--positive);
         border: 2px solid var(--surface); border-radius: 50%; }
.bornes { display: flex; justify-content: space-between; font-size: .68rem;
          color: var(--subtle); }
.note { font-size: .74rem; color: var(--muted); margin: 0; }
</style>
