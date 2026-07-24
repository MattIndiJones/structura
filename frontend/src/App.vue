<template>
  <div class="min-h-screen flex flex-col">
    <AppHeader v-if="!route.meta.public" />
    <RouterView />
    <ToastHost />
  </div>
</template>

<script setup>
import { RouterView, useRoute } from 'vue-router'
import AppHeader from './components/AppHeader.vue'
import ToastHost from './components/ui/ToastHost.vue'

const route = useRoute()
</script>
