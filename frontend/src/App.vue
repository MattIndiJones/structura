<template>
  <div class="min-h-screen flex flex-col">
    <AppHeader v-if="!route.meta.public" />
    <RouterView />
  </div>
</template>

<script setup>
import { RouterView, useRoute } from 'vue-router'
import AppHeader from './components/AppHeader.vue'

const route = useRoute()
</script>
