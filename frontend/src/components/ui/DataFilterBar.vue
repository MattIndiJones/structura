<template>
  <div class="card flex flex-wrap gap-3 items-end">
    <div v-for="f in fields" :key="f.key" class="flex flex-col gap-1" :class="f.width || 'min-w-[130px]'">
      <label class="text-[10px] text-slate-500 uppercase tracking-wider">{{ f.label }}</label>
      <input v-if="f.kind === 'text'" :value="state[f.key]" type="search"
             :placeholder="f.placeholder || 'Filtrer…'" class="input text-xs py-1.5"
             @input="state[f.key] = $event.target.value" />
      <select v-else :value="state[f.key]" class="select text-xs py-1.5"
              @change="state[f.key] = $event.target.value">
        <option value="">Tous</option>
        <option v-for="o in fieldOptions[f.key] || []" :key="o" :value="o">
          {{ f.optionLabel ? f.optionLabel(o) : o }}
        </option>
      </select>
    </div>

    <div v-if="sorts.length" class="flex flex-col gap-1">
      <label class="text-[10px] text-slate-500 uppercase tracking-wider">Trier par</label>
      <div class="flex items-center gap-1">
        <select :value="sortBy" class="select text-xs py-1.5" @change="$emit('update:sortBy', $event.target.value)">
          <option value="">Ordre d'origine</option>
          <option v-for="s in sorts" :key="s.key" :value="s.key">{{ s.label }}</option>
        </select>
        <button v-if="sortBy" class="btn-secondary text-xs px-2 py-1.5"
                :title="sortDir === 'asc' ? 'Croissant' : 'Décroissant'"
                @click="$emit('toggle-dir')">
          {{ sortDir === 'asc' ? '↑' : '↓' }}
        </button>
      </div>
    </div>

    <div class="flex items-center gap-3 self-end ml-auto">
      <span class="text-[10px] text-slate-500 whitespace-nowrap">
        <b class="text-slate-300">{{ count }}</b> / {{ total }} {{ noun }}
      </span>
      <button v-if="hasActiveFilters" class="btn-secondary text-xs px-3 py-1.5" @click="$emit('reset')">
        ✕ Réinitialiser
      </button>
    </div>
  </div>
</template>

<script setup>
// Barre de filtres partagée — reprend telle quelle l'ergonomie de l'onglet
// Deals du Booking (options issues des données, tri + sens, compteur
// « affichés / total », remise à zéro qui n'apparaît que si elle sert), pour
// que tous les écrans qui listent des enregistrements se manipulent pareil.
// La logique vit dans composables/useDataFilter.js ; ce composant n'est que
// son rendu.
defineProps({
  fields:           { type: Array, required: true },
  state:            { type: Object, required: true },
  fieldOptions:     { type: Object, default: () => ({}) },
  hasActiveFilters: { type: Boolean, default: false },
  sorts:            { type: Array, default: () => [] },
  sortBy:           { type: String, default: '' },
  sortDir:          { type: String, default: 'asc' },
  count:            { type: Number, default: 0 },
  total:            { type: Number, default: 0 },
  noun:             { type: String, default: 'élément(s)' },
})
defineEmits(['update:sortBy', 'toggle-dir', 'reset'])
</script>
