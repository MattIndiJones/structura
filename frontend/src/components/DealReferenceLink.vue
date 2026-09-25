<template>
  <RouterLink v-if="dealId != null"
              :to="{ path: '/booking', query: { deal: dealId } }"
              :title="`Ouvrir le booking du deal ${reference}`"
              class="hover:underline focus-visible:underline"
              @click.stop>
    {{ reference }}
  </RouterLink>
  <span v-else>{{ reference }}</span>
</template>

<script setup>
import { RouterLink } from 'vue-router'

defineProps({
  dealId: { type: [Number, String], default: null },
  reference: { type: String, required: true },
})
</script>
