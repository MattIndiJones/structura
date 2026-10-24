<template>
  <details class="text-left text-[10px]">
    <summary class="cursor-pointer rounded border border-slate-700 px-2 py-0.5 text-slate-400">Importer une série</summary>
    <div class="mt-2 grid min-w-56 gap-2 rounded border border-slate-700 bg-slate-900 p-2">
      <label>Devise des cours
        <input v-model.trim="conventions.currency" maxlength="3" placeholder="EUR" class="input text-xs" aria-label="Devise des cours importés" />
      </label>
      <label>Convention de la série
        <select v-model="conventions.price_type" class="select text-xs" aria-label="Convention des cours importés">
          <option value="">Choisir…</option>
          <option value="ADJUSTED_CLOSE">Cours ajustés des dividendes et splits</option>
          <option value="TOTAL_RETURN_NAV">NAV de rendement total</option>
        </select>
      </label>
      <label>Unité des valeurs
        <select v-model="conventions.unit" class="select text-xs" aria-label="Unité des cours importés">
          <option value="">Choisir…</option>
          <option value="CURRENCY">Unités de la devise indiquée</option>
        </select>
      </label>
      <label>Date des unités de titres, si colonne price_close
        <input v-model="conventions.adjustment_date" type="date" class="input text-xs" aria-label="Date de référence des unités de titres" />
      </label>
      <p class="text-slate-500">Dates AAAA-MM-JJ, cours positifs et finis, une ligne par date. Pour price_close, déclarez la date des unités de titres.</p>
      <input type="file" accept=".xlsx,.xls,.json" :disabled="busy || !complete" aria-label="Fichier de cours" @change="chooseFile" />
      <p v-if="error" class="text-red-400">{{ error }}</p>
    </div>
  </details>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'

defineProps({ busy: { type:Boolean, default:false } })
const emit = defineEmits(['upload'])
const conventions = reactive({ currency:'', price_type:'', unit:'', adjustment_date:'' })
const error = ref('')
const complete = computed(() => /^[A-Za-z]{3}$/.test(conventions.currency)
  && ['ADJUSTED_CLOSE','TOTAL_RETURN_NAV'].includes(conventions.price_type) && conventions.unit === 'CURRENCY')

function chooseFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (!complete.value) error.value = 'Précisez la devise, la convention et l’unité avant import.'
  else {
    error.value = ''
    emit('upload', { file, ...conventions, currency:conventions.currency.toUpperCase() })
  }
  event.target.value = ''
}
</script>
