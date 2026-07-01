<template>
  <div class="min-h-screen bg-slate-950 flex flex-col">

    <!-- Header -->
    <header class="border-b border-slate-800 px-6 py-3 flex items-center gap-4">
      <div class="flex items-center gap-2.5 mr-auto">
        <img src="/tp_logo.png" alt="TP Advisory" class="h-7 w-7 rounded-sm bg-white object-contain p-0.5">
        <span class="font-bold text-slate-100 tracking-tight">Structura</span>
      </div>
      <span class="text-xs text-slate-500">{{ auth.user?.username }}</span>
      <button class="btn-secondary text-xs" @click="logout">Déconnexion</button>
    </header>

    <!-- Landing -->
    <main class="flex-1 flex flex-col items-center justify-center gap-10 px-6 py-16">

      <div class="text-center">
        <h1 class="text-2xl font-black text-slate-100 tracking-tight">Bonjour, {{ auth.user?.username }}</h1>
        <p class="text-sm text-slate-500 mt-1">Que voulez-vous faire ?</p>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">

        <!-- Mes Scripts -->
        <RouterLink to="/scripts"
          class="card flex flex-col gap-3 hover:border-blue-700 hover:bg-blue-950/20 transition-colors cursor-pointer group">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-blue-900/50 flex items-center justify-center text-xl">📁</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-blue-300 transition-colors">Mes Scripts</div>
              <div class="text-xs text-slate-500">Bibliothèque de PayScripts</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Gérez, organisez et partagez vos scripts de pricing dans des dossiers.</p>
        </RouterLink>

        <!-- Nouveau script -->
        <RouterLink to="/pricer"
          class="card flex flex-col gap-3 hover:border-green-700 hover:bg-green-950/20 transition-colors cursor-pointer group">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-green-900/50 flex items-center justify-center text-xl">✏️</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-green-300 transition-colors">Nouveau Script</div>
              <div class="text-xs text-slate-500">Pricer — éditeur vide</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Ouvrez le pricer avec un éditeur vide et commencez à structurer.</p>
        </RouterLink>

        <!-- Documentation -->
        <RouterLink to="/documentation"
          class="card flex flex-col gap-3 hover:border-purple-700 hover:bg-purple-950/20 transition-colors cursor-pointer group">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-purple-900/50 flex items-center justify-center text-xl">📚</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-purple-300 transition-colors">Documentation</div>
              <div class="text-xs text-slate-500">KID PRIIPs · Term Sheets · Bibliothèque</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Générez et archivez vos documents réglementaires et commerciaux.</p>
        </RouterLink>

        <!-- Étude Fama-French -->
        <RouterLink to="/amc"
          class="card flex flex-col gap-3 hover:border-amber-600 hover:bg-amber-950/20 transition-colors cursor-pointer group">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-amber-900/50 flex items-center justify-center text-xl">📐</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-amber-300 transition-colors">Étude Fama-French</div>
              <div class="text-xs text-slate-500">Analyse AMC · Dépendance gérant</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Décomposez la performance d'un AMC en facteurs de risque et mesurez la valeur ajoutée du gérant.</p>
        </RouterLink>

        <!-- Booking (bientôt) -->
        <div class="card flex flex-col gap-3 opacity-40 cursor-not-allowed">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-slate-800 flex items-center justify-center text-xl">📒</div>
            <div>
              <div class="font-bold text-slate-400">Booking</div>
              <div class="text-xs text-slate-600">Produits bookés — bientôt</div>
            </div>
          </div>
          <p class="text-xs text-slate-700">Suivi des produits structurés en vie : nominaux, strikes, dates d'observation.</p>
        </div>

        <!-- Admin (admin seulement) -->
        <div v-if="auth.isAdmin"
          class="card flex flex-col gap-3 hover:border-amber-700 hover:bg-amber-950/20 transition-colors cursor-pointer group opacity-40 cursor-not-allowed">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-amber-900/50 flex items-center justify-center text-xl">⚙️</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-amber-300 transition-colors">Administration</div>
              <div class="text-xs text-slate-500">Utilisateurs & entités — bientôt</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Gérez les utilisateurs, les entités et les droits d'accès.</p>
        </div>

      </div>
    </main>
  </div>
</template>

<script setup>
import { RouterLink, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const auth   = useAuthStore()
const router = useRouter()

function logout() {
  auth.logout()
  router.push('/login')
}
</script>
