<!--
  Motif de perte — obligatoire, et c'est délibéré.

  Le serveur refuse un passage à « perdue » sans raison. L'écran ne se contente
  donc pas de proposer le champ : il le rend requis, pour que le refus n'arrive
  jamais après coup.

  La justification est métier, pas administrative. Savoir qu'un client a refusé
  n'apprend rien ; savoir qu'il a refusé quatre fois sur cinq pour un coupon
  trop faible dit quoi lui proposer la prochaine fois.
-->
<template>
  <BaseModal :model-value="true" max-width="480px" title="Opportunité perdue"
             @close="$emit('ferme')">
    <form class="flex flex-col gap-4" @submit.prevent="confirmer">
      <p class="text-sm" style="color: var(--muted)">
        Pourquoi ce dossier n'a-t-il pas abouti ? Cette information alimentera
        l'analyse des refus de ce client.
      </p>

      <div>
        <label class="label">
          Motif <span style="color: var(--negative)">*</span>
        </label>
        <select v-model="raison" class="select" required>
          <option value="">— Choisir —</option>
          <option v-for="r in RAISONS_PERTE" :key="r.value" :value="r.value">
            {{ r.label }}
          </option>
        </select>
      </div>

      <div>
        <label class="label">Précision</label>
        <textarea v-model="commentaire" class="input" rows="3"
                  placeholder="Ex : 5 % attendu, 3,2 % proposé par la meilleure banque"></textarea>
      </div>

      <div class="flex items-center justify-end gap-2 pt-1">
        <button type="button" class="btn-ghost" @click="$emit('ferme')">Annuler</button>
        <button type="submit" class="btn-danger" :disabled="!raison">
          Marquer perdue
        </button>
      </div>
    </form>
  </BaseModal>
</template>

<script setup>
import { ref } from 'vue'
import { RAISONS_PERTE } from '../../stores/clients.js'
import BaseModal from '../ui/BaseModal.vue'

const emit = defineEmits(['ferme', 'confirme'])

const raison = ref('')
const commentaire = ref('')

function confirmer() {
  if (!raison.value) return
  emit('confirme', { raison: raison.value, commentaire: commentaire.value || null })
}
</script>
