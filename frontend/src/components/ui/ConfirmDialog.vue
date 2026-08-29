<!--
  La modale de confirmation de l'application, montée une seule fois à la racine.

  Elle remplace le `confirm()` du navigateur, qui ouvrait une boîte étrangère à
  l'écran et ne savait ni mettre en forme un détail, ni signaler qu'une action
  détruit quelque chose.

  Le bouton de confirmation porte le VERBE de l'action — « Supprimer »,
  « Quitter » — jamais « OK » : au moment de trancher, on doit lire ce qui va se
  passer, pas une approbation abstraite.
-->
<template>
  <BaseModal :model-value="demande.ouvert" :title="demande.titre" max-width="440px"
             @update:model-value="v => { if (!v) repondre(false) }">
    <div class="flex flex-col gap-3">
      <p v-if="demande.message" class="text-sm text-slate-300 leading-relaxed">
        {{ demande.message }}
      </p>
      <!-- Le détail vient souvent d'un refus du serveur, qui nomme ce qui
           bloque. Le reproduire tel quel vaut mieux que le résumer. -->
      <pre v-if="demande.detail"
           class="text-[11px] leading-relaxed text-slate-400 whitespace-pre-wrap
                  bg-slate-900/50 border border-slate-800 rounded p-2.5
                  max-h-56 overflow-y-auto">{{ demande.detail }}</pre>
    </div>
    <template #footer>
      <button ref="btnAnnuler" class="btn-secondary text-xs" @click="repondre(false)">
        {{ demande.annuler }}
      </button>
      <button class="text-xs px-3 py-1.5 rounded font-medium transition-colors"
              :class="demande.danger
                ? 'bg-red-700 hover:bg-red-600 text-white'
                : 'btn-primary'"
              @click="repondre(true)">
        {{ demande.confirmer }}
      </button>
    </template>
  </BaseModal>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import BaseModal from './BaseModal.vue'
import { demande, repondre } from '../../composables/useConfirm.js'

const btnAnnuler = ref(null)

// Le focus part sur ANNULER, pas sur la confirmation : une modale destructrice
// qui s'ouvre sous une frappe d'Entrée ne doit pas détruire.
watch(() => demande.ouvert, async ouvert => {
  if (!ouvert) return
  await nextTick()
  btnAnnuler.value?.focus()
})
</script>
