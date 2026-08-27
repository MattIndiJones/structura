<template>
  <div class="flex-1 flex flex-col min-h-0">

    <main class="flex-1 flex flex-col items-center gap-10 px-6 py-16">
      <div class="w-full max-w-xl">
        <RouterLink to="/" class="btn-secondary text-xs px-3 py-1.5">← Retour</RouterLink>
      </div>
      <div class="text-center">
        <h1 class="page-title text-2xl">Administration</h1>
        <p class="page-subtitle">Réglages accessibles aux administrateurs</p>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">
        <RouterLink to="/admin/rfq-providers"
          class="card flex flex-col gap-3 hover:border-amber-700 hover:bg-amber-950/20 hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-amber-900/50 flex items-center justify-center text-xl">🏦</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-amber-300 transition-colors">Fournisseurs RFQ</div>
              <div class="text-xs text-slate-500">Banques contreparties</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Ajoutez, renommez ou désactivez les banques proposées dans le module RFQ.</p>
        </RouterLink>

        <RouterLink to="/admin/counterparties"
          class="card flex flex-col gap-3 hover:border-yellow-700 hover:bg-yellow-950/20 hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-yellow-900/50 flex items-center justify-center text-xl">🤝</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-yellow-300 transition-colors">Contreparties deals</div>
              <div class="text-xs text-slate-500">Banques éligibles au booking</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Gérez la liste des contreparties éligibles à faire face à un deal booké.</p>
        </RouterLink>

        <RouterLink to="/admin/users"
          class="card flex flex-col gap-3 hover:border-blue-700 hover:bg-blue-950/20 hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-blue-900/50 flex items-center justify-center text-xl">👤</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-blue-300 transition-colors">Utilisateurs</div>
              <div class="text-xs text-slate-500">Comptes &amp; rôles</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Créez des comptes, changez un rôle ou une entité, activez/désactivez un accès.</p>
        </RouterLink>

        <RouterLink to="/admin/entities"
          class="card flex flex-col gap-3 hover:border-green-700 hover:bg-green-950/20 hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-green-900/50 flex items-center justify-center text-xl">🏢</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-green-300 transition-colors">Entités</div>
              <div class="text-xs text-slate-500">Organisations</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Créez ou renommez les entités auxquelles les utilisateurs sont rattachés.</p>
        </RouterLink>

        <RouterLink to="/admin/browse"
          class="card flex flex-col gap-3 hover:border-purple-700 hover:bg-purple-950/20 hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-purple-900/50 flex items-center justify-center text-xl">🗄️</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-purple-300 transition-colors">Données de l'application</div>
              <div class="text-xs text-slate-500">Scripts · Deals · AMC · RFQ...</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Parcourez et nettoyez les enregistrements métier (lecture seule + suppression).</p>
        </RouterLink>

        <RouterLink to="/admin/underlyings"
          class="card flex flex-col gap-3 hover:border-emerald-700 hover:bg-emerald-950/20 hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-emerald-900/50 flex items-center justify-center text-xl">🏷️</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-emerald-300 transition-colors">Sous-jacents</div>
              <div class="text-xs text-slate-500">Catalogue des titres et indices</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Cherchez un titre chez Yahoo, vérifiez qu'il cote, ajoutez-le aux listes du Pricer et des AO.</p>
        </RouterLink>

        <RouterLink to="/admin/market-data"
          class="card flex flex-col gap-3 hover:border-cyan-700 hover:bg-cyan-950/20 hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-cyan-900/50 flex items-center justify-center text-xl">📈</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-cyan-300 transition-colors">Données de marché</div>
              <div class="text-xs text-slate-500">Cache Yahoo Finance</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Chargez ou rafraîchissez les historiques de prix des sous-jacents majeurs.</p>
        </RouterLink>

        <RouterLink to="/admin/compute"
          class="card flex flex-col gap-3 hover:border-indigo-700 hover:bg-indigo-950/20 hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-indigo-900/50 flex items-center justify-center text-xl">⚙️</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-indigo-300 transition-colors">Files de calcul</div>
              <div class="text-xs text-slate-500">Batches VaR &amp; repricing</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Supprimez, arrêtez ou relancez un batch de calcul, pour tous les comptes.</p>
        </RouterLink>

        <RouterLink to="/admin/uat-generator"
          class="card flex flex-col gap-3 hover:border-emerald-700 hover:bg-emerald-950/20 hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-emerald-900/50 flex items-center justify-center text-xl">🧪</div>
            <div>
              <div class="font-bold text-slate-100 group-hover:text-emerald-300 transition-colors">Générateur UAT</div>
              <div class="text-xs text-slate-500">RFQ · booking · lifecycle</div>
            </div>
          </div>
          <p class="text-xs text-slate-600">Prévisualisez et créez à la demande des lots de RFQ et deals de test reproductibles.</p>
        </RouterLink>
      </div>
    </main>
  </div>
</template>

<script setup>
import { RouterLink } from 'vue-router'
</script>
