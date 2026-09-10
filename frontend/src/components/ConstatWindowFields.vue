<template>
  <!-- Fenêtre de constatation — commune aux deux formes de CONSTAT.
       Sa place est à côté de la FRÉQUENCE, pas après les réglages de
       règlement : la fréquence de relevé décrit le calendrier, elle ne décrit
       pas comment le cash bouge. -->
  <template v-if="valeurs && typeof valeurs === 'object' && valeurs.window_frequency">
    <div v-if="scope !== 'period' && valeurs.window_length">
      <label class="label">Longueur de fenêtre
        <HelpTip text="Durée sur laquelle chaque constatation est réduite. En jours ouvrés (D), c'est un NOMBRE d'observations, la date de constatation comprise : 30D à la fréquence 1D fait 30 fixings. En semaines, mois ou années, c'est une durée calendaire." />
      </label>
      <div class="flex gap-1">
        <input type="number" min="1" class="input w-14"
               v-model.number="valeurs.window_length.value" />
        <select v-model="valeurs.window_length.unit" class="select">
          <option value="D">D</option>
          <option value="W">W</option>
          <option value="M">M</option>
          <option value="Y">Y</option>
        </select>
      </div>
    </div>

    <div>
      <label class="label">Fréquence de relevé
        <HelpTip v-if="scope === 'period'" text="Pas d'échantillonnage DANS la période. Une fréquence trimestrielle sur un calendrier annuel donne une constatation par an, moyennée sur ses 4 relevés." />
        <HelpTip v-else text="Pas d'échantillonnage DANS la fenêtre. « 3 derniers mois relevés chaque jour » et « chaque mois » sont deux produits distincts." />
      </label>
      <div class="flex gap-1">
        <input type="number" min="1" class="input w-14"
               v-model.number="valeurs.window_frequency.value" />
        <select v-model="valeurs.window_frequency.unit" class="select">
          <option value="D">D</option>
          <option value="W">W</option>
          <option value="M">M</option>
          <option value="Y">Y</option>
        </select>
      </div>
    </div>

    <p v-if="scope === 'period'" class="text-[11px] text-slate-400 self-end pb-1.5 max-w-[12rem]">
      Fenêtre = <span class="text-slate-200 font-semibold">la période</span>,
      d'une constatation à la suivante — pas de longueur à saisir.
    </p>

    <!-- Aperçu : ce que la fenêtre retient VRAIMENT, avant tout pricing.
         Toujours un résumé, jamais une liste : un calendrier mal saisi ne doit
         pas pouvoir déverser des milliers de lignes dans le panneau. -->
    <p v-if="apercu" class="basis-full text-[11px] font-mono -mt-1"
       :class="apercu.erreur ? 'text-amber-400' : 'text-slate-300'">
      <template v-if="apercu.erreur">⚠ {{ apercu.erreur }}</template>
      <template v-else-if="apercu.periode">
        {{ apercu.periode.count }} constatation(s) · {{ resumeReleves }} relevé(s) chacune
        <span class="text-slate-500">— dépliez l'échéancier pour les voir toutes</span>
      </template>
      <template v-else>
        du <SensitiveValue>{{ apercu.first }}</SensitiveValue>
        au <SensitiveValue>{{ apercu.last }}</SensitiveValue>
        · {{ apercu.count }} relevé(s)
      </template>
    </p>
  </template>
</template>

<script setup>
import { computed } from 'vue'
import HelpTip from './HelpTip.vue'
import SensitiveValue from './SensitiveValue.vue'

const props = defineProps({
  /** 'length' (une durée, saisie ici) ou 'period' (la période du calendrier). */
  scope: { type: String, default: 'length' },
  /** L'entrée de constatOverrides — mutée directement, comme les autres champs. */
  valeurs: { type: Object, default: null },
  /** Réponse de /api/schedule/window ou /period-window, ou { erreur }. */
  apercu: { type: Object, default: null },
})

/** « 4 » quand toutes les périodes se valent, « 3 à 5 » sinon. */
const resumeReleves = computed(() => {
  const p = props.apercu?.periode
  if (!p) return ''
  return p.releves_min === p.releves_max
    ? String(p.releves_min)
    : `${p.releves_min} à ${p.releves_max}`
})
</script>
