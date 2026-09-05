<!--
  Choisir des valeurs dans un catalogue — ou en saisir une qui n'y est pas.

  Remplace la saisie « EUR, USD, CHF » séparée par des virgules. Ce n'était pas
  qu'une gêne : « SX5E » tapé à la main ne rencontre jamais « ^STOXX50E », et
  l'univers déclaré du client ne correspondait donc à aucune de ses transactions.

  **La saisie libre reste possible, et c'est délibéré.** L'historique d'un client
  nomme « Citi » ce que notre catalogue appelle « Citigroup » ; la superposition
  déclaré / observé compare des LIBELLÉS. Interdire la saisie libre casserait la
  lecture pour laquelle le champ existe. Sur un vocabulaire fermé (types de
  produits, classes d'actifs), `freeEntry` est faux et rien ne s'ajoute hors liste.

  Deux formes de valeur, transparentes pour l'appelant : chaîne nue, ou référence
  `{id, label}` — le pointeur pour résoudre, le libellé pour rester lisible si la
  ligne disparaît du catalogue.
-->
<template>
  <div ref="racine" class="picker" :class="{ ouvert }">
    <!-- Les valeurs retenues -->
    <div class="chips" @click="ouvrir">
      <span v-for="(valeur, i) in modelValue" :key="i" class="chip"
            :class="{ 'chip-libre': estLibre(valeur) }"
            :title="estLibre(valeur) ? 'Saisie libre : absente du catalogue' : ''">
        {{ libelleDe(valeur) }}
        <button type="button" class="chip-x" :aria-label="`Retirer ${libelleDe(valeur)}`"
                @click.stop="retirer(i)">×</button>
      </span>
      <input ref="champ" v-model="recherche" class="chips-saisie"
             :placeholder="modelValue.length ? '' : placeholder"
             @focus="ouvert = true" @keydown="auClavier" />
    </div>

    <!-- Les propositions -->
    <div v-if="ouvert" class="menu">
      <p v-if="!propositions.length && !peutAjouterLibre" class="menu-vide">
        {{ recherche ? 'Aucune correspondance.' : 'Tout est déjà retenu.' }}
      </p>

      <template v-for="groupe in propositions" :key="groupe.nom">
        <div v-if="groupe.nom" class="menu-groupe">{{ groupe.nom }}</div>
        <button v-for="option in groupe.options" :key="option.value" type="button"
                class="menu-ligne" @mousedown.prevent="ajouter(option)">
          {{ option.label }}
        </button>
      </template>

      <!-- La saisie libre est une action explicite, jamais un effet de bord
           d'une frappe : on ne veut pas qu'un mot à moitié tapé se range dans
           la liste parce que l'utilisateur a cliqué ailleurs. -->
      <button v-if="peutAjouterLibre" type="button" class="menu-ligne menu-libre"
              @mousedown.prevent="ajouterLibre">
        Ajouter « {{ recherche.trim() }} » — hors catalogue
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  options: { type: Array, default: () => [] },   // {value, label, group, id}
  freeEntry: { type: Boolean, default: true },
  storage: { type: String, default: 'list_str' }, // list_str | list_ref
  placeholder: { type: String, default: 'Rechercher ou saisir…' },
})
const emit = defineEmits(['update:modelValue'])

const ouvert = ref(false)
const recherche = ref('')
const champ = ref(null)
const racine = ref(null)

function libelleDe(valeur) {
  return typeof valeur === 'string' ? valeur : (valeur?.label ?? '')
}
function estLibre(valeur) {
  if (typeof valeur !== 'string') return valeur?.id == null
  return !props.options.some(o => o.value === valeur)
}
const retenus = computed(() => props.modelValue.map(libelleDe))

const propositions = computed(() => {
  const terme = recherche.value.trim().toLowerCase()
  const groupes = new Map()
  for (const option of props.options) {
    if (retenus.value.includes(option.value)) continue
    if (terme && !`${option.value} ${option.label}`.toLowerCase().includes(terme)) continue
    const nom = option.group || ''
    if (!groupes.has(nom)) groupes.set(nom, [])
    groupes.get(nom).push(option)
  }
  // Sans recherche, un catalogue de cinquante tickers à plat est aussi peu
  // utilisable qu'un champ vide : on borne, le terme de recherche fait le reste.
  let restant = terme ? 200 : 40
  const sortie = []
  for (const [nom, options] of groupes) {
    if (restant <= 0) break
    sortie.push({ nom, options: options.slice(0, restant) })
    restant -= options.length
  }
  return sortie
})

const peutAjouterLibre = computed(() => {
  const terme = recherche.value.trim()
  if (!props.freeEntry || !terme) return false
  if (retenus.value.some(v => v.toLowerCase() === terme.toLowerCase())) return false
  return !props.options.some(o => o.value.toLowerCase() === terme.toLowerCase())
})

function ouvrir() {
  ouvert.value = true
  nextTick(() => champ.value?.focus())
}

function emettre(liste) {
  emit('update:modelValue', liste)
  recherche.value = ''
}

function ajouter(option) {
  const valeur = props.storage === 'list_ref'
    ? { id: option.id ?? null, label: option.value }
    : option.value
  emettre([...props.modelValue, valeur])
}

function ajouterLibre() {
  const terme = recherche.value.trim()
  emettre([...props.modelValue,
           props.storage === 'list_ref' ? { id: null, label: terme } : terme])
}

function retirer(index) {
  emettre(props.modelValue.filter((_, i) => i !== index))
}

function auClavier(evenement) {
  if (evenement.key === 'Enter') {
    evenement.preventDefault()
    const premiere = propositions.value[0]?.options?.[0]
    if (premiere) ajouter(premiere)
    else if (peutAjouterLibre.value) ajouterLibre()
    return
  }
  if (evenement.key === 'Escape') { ouvert.value = false; return }
  // Retour arrière sur un champ vide retire la dernière valeur — le geste
  // attendu de tout champ à jetons.
  if (evenement.key === 'Backspace' && !recherche.value && props.modelValue.length) {
    retirer(props.modelValue.length - 1)
  }
}

// Fermer au clic extérieur. Un SEUL écouteur, posé à l'ouverture et retiré à
// la fermeture quelle qu'en soit la cause — sinon une fermeture au clavier
// (Échap) laisse l'écouteur en place et la réouverture suivante en empile un
// second. Retiré aussi au démontage : le composant vit dans un onglet qu'on
// quitte.
function auClicExterieur(evenement) {
  if (!racine.value?.contains(evenement.target)) ouvert.value = false
}

watch(ouvert, (actif) => {
  if (actif) document.addEventListener('mousedown', auClicExterieur)
  else document.removeEventListener('mousedown', auClicExterieur)
})

onBeforeUnmount(() => document.removeEventListener('mousedown', auClicExterieur))
</script>

<style scoped>
.picker { position: relative; }
.chips {
  display: flex; flex-wrap: wrap; gap: .35rem; align-items: center;
  min-height: 2.4rem; padding: .35rem .5rem; cursor: text;
  background: var(--surface); border: 1px solid var(--border); border-radius: .5rem;
}
.picker.ouvert .chips { border-color: var(--accent); }
.chip {
  display: inline-flex; align-items: center; gap: .3rem;
  padding: .12rem .45rem; font-size: .78rem; font-weight: 600;
  background: var(--accent-light); color: var(--accent);
  border: 1px solid transparent; border-radius: .3rem;
}
/* Une valeur hors catalogue se voit : c'est souvent voulu (« Citi » plutôt que
   « Citigroup »), mais parfois c'est une faute de frappe. */
.chip-libre {
  background: var(--surface2); color: var(--muted);
  border-color: var(--border); border-style: dashed;
}
.chip-x { line-height: 1; font-size: .95rem; opacity: .55; }
.chip-x:hover { opacity: 1; }
.chips-saisie {
  flex: 1; min-width: 7rem; border: 0; outline: none; background: transparent;
  font-size: .82rem; color: var(--text);
}
.menu {
  position: absolute; z-index: 30; left: 0; right: 0; top: calc(100% + .25rem);
  max-height: 16rem; overflow-y: auto; padding: .25rem;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: .5rem; box-shadow: 0 8px 24px rgba(0, 0, 0, .12);
}
.menu-groupe {
  padding: .35rem .5rem .15rem; font-size: .66rem; font-weight: 700;
  letter-spacing: .06em; text-transform: uppercase; color: var(--subtle);
}
.menu-ligne {
  display: block; width: 100%; text-align: left; padding: .3rem .5rem;
  font-size: .82rem; color: var(--text); border-radius: .3rem;
}
.menu-ligne:hover { background: var(--surface2); }
.menu-libre { color: var(--muted); font-style: italic; }
.menu-vide { padding: .5rem; font-size: .78rem; color: var(--subtle); }
</style>
