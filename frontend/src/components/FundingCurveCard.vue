<!--
  Spread émetteur — le coût de crédit de celui qui doit payer la note.

  Volontairement séparé de la courbe de taux, et le libellé le dit : un spread
  émetteur n'entre que dans l'ACTUALISATION. Le crédit de l'émetteur ne déplace
  pas le forward du sous-jacent. Les fondre donnerait le signe inverse — la
  note vaudrait plus cher à mesure que son émetteur se dégrade.

  Ce n'est ni un coût de repo (celui-là déplace bien le forward, sa place est
  dans q) ni une actualisation collatéralisée. Le HelpTip le rappelle, sinon
  quelqu'un y mettra un coût d'emprunt de titre dans six mois.
-->
<template>
  <div class="card mt-4">
    <div class="flex items-center gap-3 mb-3 flex-wrap">
      <label class="flex items-center gap-2 cursor-pointer select-none">
        <div class="relative w-9 h-5">
          <input type="checkbox" class="sr-only" :checked="c.enabled"
                 @change="c.enabled = !c.enabled" />
          <div class="w-9 h-5 rounded-full transition-colors"
               :class="c.enabled ? 'bg-amber-600' : 'bg-slate-700'"></div>
          <div class="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform"
               :class="c.enabled ? 'translate-x-4' : 'translate-x-0'"></div>
        </div>
        <span class="text-xs font-bold text-slate-400 uppercase tracking-wider">Spread émetteur</span>
        <HelpTip width="w-96" text="Coût de crédit de l'émetteur de la note, en points de pourcentage annuels. Il s'ajoute à l'ACTUALISATION de tous les flux, et à elle seule : le crédit de l'émetteur ne déplace pas le forward des sous-jacents. À ne pas confondre avec le coût d'emprunt du titre (repo), qui lui modifie le forward et se saisit dans le dividende q, ni avec l'actualisation collatéralisée d'un swap sous CSA. Ordre de grandeur : un spread de 100 bps coûte environ le prix multiplié par la durée de vie moyenne — sur un produit à 46 % et 1,1 an de vie restante, environ 0,5 point." />
      </label>

      <span v-if="!c.enabled" class="ml-auto text-xs text-slate-600">
        Aucun spread — actualisation au taux sans risque
      </span>
      <span v-else class="ml-auto text-xs text-slate-500">
        <span class="text-amber-400 font-mono font-semibold">
          <SensitiveValue>{{ resume }}</SensitiveValue>
        </span>
      </span>
    </div>

    <template v-if="c.enabled">
      <!-- Les deux modes -->
      <div class="flex gap-1.5 mb-3">
        <button v-for="m in MODES" :key="m.id" @click="c.mode = m.id"
                class="text-xs px-2.5 py-1 rounded border transition-colors"
                :class="c.mode === m.id
                  ? 'bg-amber-600/20 border-amber-500 text-amber-400'
                  : 'bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500'">
          {{ m.label }}
        </button>
      </div>

      <!-- Niveau unique -->
      <div v-if="c.mode === 'flat'" class="flex items-end gap-3">
        <div>
          <label class="label">Niveau, tous piliers</label>
          <div class="relative w-40">
            <SensitiveValue mode="input" placeholder="••">
              <input type="number" step="0.05" min="-5" max="50"
                     v-model.number="c.level"
                     class="input pr-6 font-mono" />
            </SensitiveValue>
            <span class="absolute right-2 top-1/2 -translate-y-1/2 text-slate-600 text-xs pointer-events-none">%</span>
          </div>
        </div>
        <p class="text-[10px] text-slate-500 pb-2">
          {{ formatNumber(c.level * 100, 0) }} bps appliqués à toute la courbe d'actualisation.
        </p>
      </div>

      <!-- Un niveau par pilier -->
      <div v-else>
        <div class="grid grid-cols-8 gap-1 mb-2">
          <div v-for="p in c.pillars" :key="p.label" class="flex flex-col items-center gap-0.5">
            <label class="text-xs text-slate-600 leading-none">{{ p.label }}</label>
            <SensitiveValue mode="input" placeholder="••">
              <div class="relative w-full">
                <input type="number" step="0.05" min="-5" max="50"
                       v-model.number="p.spread"
                       class="w-full text-center text-xs bg-slate-900 border border-slate-700 rounded
                              px-0 py-1 text-slate-200 focus:border-amber-500 focus:outline-none"
                       style="padding-right:10px" />
                <span class="absolute right-0.5 top-1/2 -translate-y-1/2 text-slate-600 text-xs pointer-events-none">%</span>
              </div>
            </SensitiveValue>
          </div>
        </div>
        <button class="text-[10px] text-slate-500 hover:text-amber-400 underline"
                @click="aplatir">
          Aplatir sur le pilier 3Y ({{ formatNumber(pilier3Y, 2) }} %)
        </button>
      </div>
    </template>

    <!-- ── Le calcul à l'envers ─────────────────────────────────────
         Devant une ligne de secondaire, la question utile n'est pas « que
         vaut-elle pour moi » mais « à quel spread le marché la traite ».
         N'a de sens qu'en cours de vie : sans passé à rejouer, il n'y a pas
         de prix de marché à inverser. -->
    <div v-if="dansLePricer && enCoursDeVie" class="mt-4 pt-3 border-t border-slate-800">
      <div class="text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-2">
        Spread implicite d'un prix de marché
        <HelpTip width="w-96" text="Résout le spread émetteur qui reproduit exactement le prix saisi, toutes les autres hypothèses restant celles de l'écran. Attention à la lecture : ce spread absorbe TOUT ce que le modèle ne capture pas — smile en tête. C'est un spread implicite au sens propre, pas une mesure de crédit pure. S'il ressort très loin du funding connu de l'émetteur, c'est le modèle qu'il faut regarder, pas le crédit." />
      </div>
      <div class="flex items-end gap-2 flex-wrap">
        <div>
          <label class="label">Prix de marché</label>
          <div class="relative w-32">
            <input type="number" step="0.01" v-model.number="prixMarche"
                   class="input pr-6 font-mono" placeholder="45,07" />
            <span class="absolute right-2 top-1/2 -translate-y-1/2 text-slate-600 text-xs pointer-events-none">%</span>
          </div>
        </div>
        <button class="btn-secondary text-xs px-3 py-1.5 mb-0.5"
                :disabled="store.loading || !prixMarche"
                @click="store.runImpliedFunding(prixMarche)">
          {{ store.loading ? '…' : 'Extraire le spread' }}
        </button>
        <p class="text-[10px] text-slate-600 mb-1.5">
          En % du nominal — 45,07 pour un bid à 450,65 sur 1 000.
        </p>
      </div>

      <div v-if="store.impliedFunding" class="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span class="font-mono font-bold text-amber-300 text-lg">
          <SensitiveValue>{{ formatNumber(store.impliedFunding.funding_spread * 10000, 0) }} bps</SensitiveValue>
        </span>
        <span class="text-[11px] text-slate-500">
          prix reconstitué
          <span class="font-mono text-slate-300">
            <SensitiveValue>{{ formatNumber(store.impliedFunding.price * 100, 3) }} %</SensitiveValue>
          </span>
          · {{ store.impliedFunding.iterations.length }} itérations
        </span>
        <span v-if="!store.impliedFunding.converged" class="text-[11px] text-amber-500">
          ⚠ non convergé — resserrez la tolérance ou élargissez les bornes
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { usePricingStore } from '../stores/pricing.js'
import HelpTip from './HelpTip.vue'
import SensitiveValue from './SensitiveValue.vue'
import { formatNumber } from '../utils/format.js'

const store = usePricingStore()
const props = defineProps({
  // La courbe à éditer. Absente, celle du Pricer — les usages existants ne
  // changent pas, et l'appel d'offres passe la sienne.
  courbe: { type: Object, default: null },
})

// L'extraction du spread implicite reprice le produit à spread variable pour
// retrouver celui qui colle au marché : elle a besoin d'un contexte de pricing
// complet. Hors du Pricer, elle n'a pas de sens et le bloc disparaît, plutôt
// que d'offrir un bouton qui échouerait.
const dansLePricer = computed(() => !props.courbe)
const c = computed(() => props.courbe ?? store.fundingCurve)
const prixMarche = ref(null)
const enCoursDeVie = computed(() => store.isInLife())

const MODES = [
  { id: 'flat',    label: 'Niveau unique' },
  { id: 'pillars', label: 'Par pilier' },
]

const pilier3Y = computed(() => c.value.pillars.find(p => p.label === '3Y')?.spread ?? c.value.level)

const resume = computed(() => {
  if (c.value.mode === 'flat') return `${formatNumber(c.value.level * 100, 0)} bps, plat`
  const vals = c.value.pillars.map(p => Number(p.spread) || 0)
  const lo = Math.min(...vals), hi = Math.max(...vals)
  return lo === hi
    ? `${formatNumber(lo * 100, 0)} bps, plat`
    : `${formatNumber(lo * 100, 0)} – ${formatNumber(hi * 100, 0)} bps`
})

function aplatir() {
  const v = pilier3Y.value
  c.value.pillars.forEach(p => { p.spread = v })
}
</script>
