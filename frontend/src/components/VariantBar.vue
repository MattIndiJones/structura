<!--
  La barre de déclinaison — les variantes d'un deal, en sous-onglets.

  « Origine » est toujours en premier et toujours présente : on doit pouvoir
  revenir à la référence sans la chercher, sinon on finit par comparer une
  variante à une autre en croyant la comparer au deal.

  Le compteur de modifications ouvre le détail. Il est là parce qu'un champ
  coloré, isolé au milieu d'un écran, se remarque mal — il faut pouvoir lire la
  liste complète de ce qui a bougé, en une fois.
-->
<template>
  <div v-if="parentId" class="flex flex-col gap-2 border-b border-slate-800 px-5 py-2">
    <div class="flex items-center gap-2 flex-wrap">
      <span class="text-[10px] font-bold text-slate-500 uppercase tracking-widest shrink-0">
        Déclinaisons
        <HelpTip width="w-96" text="Les variantes d'un même deal. Chacune ne stocke que ses écarts et hérite le reste de l'origine : repricer l'origine les déplace toutes, ce qui est la seule façon de les comparer à marché constant. Un avenant garde le contrat en vie et ne change que l'avenir ; une note neuve est strikée aujourd'hui, sans passé." />
      </span>

      <button class="onglet" :class="!store.variantInfo ? 'onglet-actif' : ''"
              @click="ouvrirOrigine">
        Origine
      </button>

      <span v-for="v in variantes" :key="v.id"
            class="onglet inline-flex items-center gap-1.5 group"
            :class="store.variantInfo?.id === v.id ? 'onglet-actif' : ''">
        <button class="inline-flex items-center gap-1.5" @click="ouvrir(v)">
          {{ v.variant_title }}
          <span class="text-[9px] px-1 py-px rounded uppercase tracking-wide"
                :class="v.variant_mode === 'roll'
                  ? 'bg-violet-500/20 text-violet-300' : 'bg-slate-700 text-slate-400'">
            {{ v.variant_mode === 'roll' ? 'note neuve' : 'avenant' }}
          </span>
        </button>
        <button class="opacity-0 group-hover:opacity-100 transition-opacity
                       text-slate-500 hover:text-red-400 text-[10px] leading-none"
                :title="`Supprimer « ${v.variant_title} »`"
                @click.stop="supprimer(v)">✕</button>
      </span>

      <button class="onglet text-slate-500" title="Décliner ce deal"
              @click="ouvrirCreation">+ Décliner</button>

      <div class="ml-auto flex items-center gap-2">
        <button v-if="store.variantInfo" class="btn-primary text-[10px] px-2.5 py-1"
                :disabled="enregistre"
                title="Écrit les écarts de cette déclinaison. Sans ça, ils sont perdus au prochain changement d'onglet."
                @click="enregistrer">
          {{ enregistre ? '✓ Enregistré' : '💾 Enregistrer' }}
        </button>
        <button v-if="marque.nbEcarts.value" class="text-[10px] text-amber-400 hover:underline"
                @click="detailOuvert = !detailOuvert">
          {{ marque.nbEcarts.value }} modification{{ marque.nbEcarts.value > 1 ? 's' : '' }}
          {{ detailOuvert ? '▲' : '▼' }}
        </button>
      </div>
    </div>

    <!-- Le détail de ce qui a bougé. -->
    <div v-if="detailOuvert && marque.nbEcarts.value"
         class="rounded border border-slate-800 bg-slate-900/50 p-2 flex flex-col gap-1">
      <div v-for="e in store.variantInfo.ecarts" :key="e.chemin"
           class="flex items-baseline gap-2 text-[11px]">
        <span class="w-2 h-2 rounded-full shrink-0"
              :class="e.etat === 'retire' ? 'bg-slate-600' : 'bg-amber-500'"></span>
        <span class="text-slate-400 flex-1 truncate">{{ libelleChemin(e.chemin) }}</span>
        <span class="font-mono text-slate-500">{{ valeurLisible(e.avant) }}</span>
        <span class="text-slate-600">→</span>
        <span class="font-mono"
              :class="e.etat === 'retire' ? 'text-slate-600 italic' : 'text-amber-400'">
          {{ e.etat === 'retire' ? 'retiré' : valeurLisible(e.apres) }}
        </span>
      </div>
    </div>

    <AlertMessage v-if="erreur" kind="error" dismissible @dismiss="erreur = ''">{{ erreur }}</AlertMessage>

    <!-- Création d'une déclinaison. Le delta se remplit ensuite à l'écran ;
         ici on ne demande que ce qui n'est pas devinable : un titre et le mode. -->
    <BaseModal v-model="creation.ouvert" title="Décliner ce deal" max-width="440px">
      <div class="flex flex-col gap-3">
        <div>
          <label class="label">Titre de la variante</label>
          <input v-model="creation.titre" type="text" class="input text-xs"
                 placeholder="Ex : Capital — PDI 30 %"
                 @keyup.enter="creer" />
          <p class="text-[10px] text-slate-500 mt-1">
            C'est ce qui permet de s'y retrouver entre cinq déclinaisons.
          </p>
        </div>
        <div>
          <label class="label">Mode</label>
          <div class="flex flex-col gap-1.5">
            <label v-for="m in MODES" :key="m.id"
                   class="flex items-start gap-2 text-xs cursor-pointer p-2 rounded border transition-colors"
                   :class="creation.mode === m.id
                     ? 'border-blue-600 bg-blue-600/10' : 'border-slate-700 hover:border-slate-600'">
              <input type="radio" :value="m.id" v-model="creation.mode" class="mt-0.5 accent-blue-600" />
              <span>
                <span class="text-slate-200 font-medium">{{ m.label }}</span>
                <span class="block text-[10px] text-slate-500 mt-0.5">{{ m.aide }}</span>
              </span>
            </label>
          </div>
        </div>
      </div>
      <template #footer>
        <button class="btn-secondary text-xs" @click="creation.ouvert = false">Annuler</button>
        <button class="btn-primary text-xs" :disabled="!creation.titre.trim()" @click="creer">
          Créer
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePricingStore } from '../stores/pricing.js'
import { apiFetch } from '../utils/api.js'
import { confirmer } from '../composables/useConfirm.js'
import { useVariantMark, libelleChemin, valeurLisible } from '../composables/useVariantMark.js'
import AlertMessage from './ui/AlertMessage.vue'
import BaseModal from './ui/BaseModal.vue'
import HelpTip from './HelpTip.vue'

const store = usePricingStore()
const router = useRouter()
const marque = useVariantMark(store)

const variantes = ref([])
const detailOuvert = ref(false)
const erreur = ref('')
const creation = ref({ ouvert: false, titre: '', mode: 'avenant' })
const enregistre = ref(false)

async function enregistrer() {
  erreur.value = ''
  try {
    await store.saveVariant()
    enregistre.value = true
    setTimeout(() => { enregistre.value = false }, 1800)
    await charger()
  } catch (e) { erreur.value = e.message }
}

const MODES = [
  { id: 'avenant', label: 'Avenant — le contrat continue',
    aide: "Le passé reste rejoué aux termes d'origine ; seule la vie restante prend les nouveaux. Le panier et le strike sont figés." },
  { id: 'roll', label: 'Note neuve — débouclage et réémission',
    aide: "Strikée aujourd'hui, sans passé : les cours du jour deviennent le nouveau 100 %. Panier, calendrier et payoff redeviennent libres." },
]

// L'origine, quelle que soit la page ouverte : sur une variante c'est son
// parent, sur un deal c'est lui-même.
const parentId = computed(() =>
  store.variantInfo?.parent_id ?? store.currentScriptId ?? null)

async function charger() {
  if (!parentId.value) { variantes.value = []; return }
  try {
    const res = await apiFetch(`/api/db/scripts/${parentId.value}/variants`)
    variantes.value = res.ok ? await res.json() : []
  } catch { variantes.value = [] }
}
watch(parentId, charger, { immediate: true })

// Changer d'onglet recharge l'écran depuis le serveur : ce qui n'a pas été
// enregistré disparaît. On le dit AVANT plutôt que de le laisser découvrir en
// revenant — c'est exactement comme ça qu'on perd une demi-heure de travail.
//
// La question ne se pose plus que s'il y a VRAIMENT quelque chose à perdre :
// demander à chaque changement d'onglet apprend à répondre oui sans lire, et
// l'avertissement ne protège plus rien le jour où il compte.
async function _peutQuitter() {
  if (!store.variantDirty) return true
  return confirmer({
    titre: 'Quitter sans enregistrer ?',
    message: 'Cette déclinaison porte des modifications qui ne sont pas encore '
           + "écrites. Changer d'onglet la recharge depuis le serveur : elles "
           + 'seront perdues.',
    confirmer: 'Quitter sans enregistrer', danger: true,
  })
}

async function ouvrirOrigine() {
  if (!store.variantInfo) return
  if (!await _peutQuitter()) return
  router.push(`/pricer/${parentId.value}`)
}

async function ouvrir(v) {
  if (store.variantInfo?.id === v.id) return
  if (!await _peutQuitter()) return
  // On NAVIGUE plutôt que d'échanger l'état en place : changer de déclinaison,
  // c'est changer de produit. Garder à l'écran le prix de la précédente le
  // ferait lire comme celui de la nouvelle, et l'URL désigne enfin ce qu'on
  // regarde.
  router.push(`/pricer/v/${v.id}`)
}

async function supprimer(v) {
  // Une déclinaison ne stocke que ses écarts : la supprimer ne touche ni son
  // origine ni ses sœurs. C'est ce qui permet de le faire sans cérémonie.
  if (!await confirmer({
    titre: `Supprimer « ${v.variant_title} » ?`,
    message: "Son origine et les autres déclinaisons ne sont pas affectées : "
           + 'une déclinaison ne stocke que ses écarts.',
    confirmer: 'Supprimer', danger: true })) return
  erreur.value = ''
  try {
    const res = await apiFetch(`/api/db/scripts/${v.id}`, { method: 'DELETE' })
    if (!res.ok && res.status !== 204) {
      erreur.value = (await res.json().catch(() => ({}))).detail || 'Suppression refusée.'
      return
    }
    // Si c'était celle qu'on regardait, on retombe sur l'origine plutôt que
    // sur un écran qui décrit un produit qui n'existe plus.
    if (store.variantInfo?.id === v.id) { router.push(`/pricer/${parentId.value}`); return }
    await charger()
  } catch (e) { erreur.value = e.message }
}

function ouvrirCreation() {
  creation.value = { ouvert: true, titre: '', mode: 'avenant' }
}

async function creer() {
  const titre = creation.value.titre.trim()
  if (!titre) return
  erreur.value = ''
  try {
    const res = await apiFetch(`/api/db/scripts/${parentId.value}/variants`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // Delta vide : la déclinaison naît identique à son origine, et se
      // différencie ensuite à l'écran. Naître avec des écarts qu'on n'a pas
      // saisis serait le contraire de ce qu'on cherche.
      body: JSON.stringify({ variant_title: titre, variant_mode: creation.value.mode,
                              delta: {} }),
    })
    const data = await res.json()
    if (!res.ok) { erreur.value = data.detail || 'Création refusée.'; return }
    creation.value.ouvert = false
    router.push(`/pricer/v/${data.id}`)
  } catch (e) { erreur.value = e.message }
}
</script>

<style scoped>
.onglet {
  @apply text-xs px-2.5 py-1 rounded border border-slate-700 bg-slate-800 text-slate-400
         transition-colors hover:border-slate-500;
}
.onglet-actif {
  @apply bg-blue-600/20 border-blue-500 text-blue-300;
}
</style>
