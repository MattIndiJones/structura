<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute(), router = useRouter(), auth = useAuthStore()
const error = ref('')
onMounted(async () => {
  const token = route.query.token
  // Remove the bearer token from the address bar before any further navigation.
  window.history.replaceState(null, '', `${window.location.pathname}#/consultation`)
  try {
    if (typeof token !== 'string' || !token) throw new Error('Session absente. Rouvrez la consultation depuis la campagne.')
    await auth.openConsultation(token)
    await router.replace('/booking')
  } catch (e) { error.value = e.message }
})
</script>

<template>
  <main class="max-w-xl mx-auto p-8">
    <h1 class="page-title">Ouverture de Structura en consultation</h1>
    <p v-if="error" role="alert" class="text-red-600 mt-4">{{ error }}</p>
    <p v-else class="mt-4">Chargement du book sauvegardé…</p>
  </main>
</template>
