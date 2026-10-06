<template>
  <main class="p-6 w-full max-w-5xl mx-auto">
    <div class="page-header"><div><h1 class="page-title">Structuring Intelligence</h1><p class="page-subtitle">Explorer des structures à partir d'objectifs et de contraintes.</p></div></div>
    <div class="grid md:grid-cols-2 gap-4 mt-6">
      <RouterLink to="/structuring/optimizer" class="card hover:border-blue-500">
        <h2 class="text-lg font-semibold">Product Optimizer</h2>
        <p class="text-sm mt-3">Résoudre le coupon, filtrer les structures et comparer les solutions admissibles.</p>
        <p class="text-xs text-slate-500 mt-3">V1 · Autocall Athena · GBM · mono-actif / worst-of</p>
        <span class="btn-primary mt-5 inline-block">Explorer les solutions →</span>
      </RouterLink>
      <section class="card" aria-label="Structuring Copilot — à venir">
        <h2 class="text-lg font-semibold">Structuring Copilot <span class="text-xs text-slate-500">À venir</span></h2>
        <p class="text-sm mt-3">Traduire une intention de structuration en contraintes explicites.</p>
        <p class="text-xs text-slate-500 mt-3">Ce service n'est pas disponible dans cette version.</p>
      </section>
    </div>
  </main>
</template>
<script setup>
import { RouterLink } from 'vue-router'
</script>
