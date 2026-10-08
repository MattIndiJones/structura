<template>
  <main class="p-6 w-full max-w-5xl mx-auto">
    <div class="page-header"><div><h1 class="page-title">Structuring Intelligence</h1><p class="page-subtitle">Explorer des structures à partir d'objectifs et de contraintes.</p></div></div>
    <div class="grid md:grid-cols-3 gap-4 mt-6">
      <RouterLink to="/structuring/optimizer" class="card hover:border-blue-500">
        <h2 class="text-lg font-semibold">Product Optimizer</h2>
        <p class="text-sm mt-3">Optimiser coupon, participation ou cap ; filtrer et comparer les structures confirmées.</p>
        <p class="text-xs text-slate-500 mt-3">V1 · 8 familles · GBM · mono-actif / worst-of</p>
        <span class="btn-primary mt-5 inline-block">Explorer les solutions →</span>
      </RouterLink>
      <RouterLink to="/structuring/researches" class="card hover:border-blue-500">
        <h2 class="text-lg font-semibold">Recherches & pricings</h2>
        <p class="text-sm mt-3">Retrouver vos demandes, les prix calculés et leurs diagnostics, puis reprendre une recherche.</p>
        <p class="text-xs text-slate-500 mt-3">Marché figé · historique des calculs · versions liées</p>
        <span class="btn-secondary mt-5 inline-block">Ouvrir les dossiers →</span>
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
