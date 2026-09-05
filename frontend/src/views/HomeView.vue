<template>
  <div class="flex-1 flex flex-col min-h-0">

    <!-- Landing -->
    <main class="flex-1 flex flex-col items-center justify-center gap-10 px-6 py-16">

      <Transition name="category-switch" mode="out-in" @after-enter="onAfterEnter">
        <div :key="selectedCategory || 'level1'" tabindex="0"
          class="outline-none flex flex-col items-center gap-10 w-full" @keyup.esc="revenirAuxCategories">

          <!-- Titre : accueil ou catégorie sélectionnée -->
          <div v-if="!selectedCategory" class="text-center">
            <h1 class="font-display text-2xl font-black tracking-tight bg-gradient-to-r from-slate-100 to-slate-400 bg-clip-text text-transparent">Bonjour, {{ auth.user?.username }}</h1>
            <p class="text-sm text-slate-500 mt-1">Que voulez-vous faire ?</p>
          </div>
          <!-- Le même bouton que partout ailleurs : il revient en arrière, et
               retombe sur l'accueil principal quand il n'y a pas d'historique
               — arrivée par la barre du haut, un signet ou un lien direct. -->
          <div v-else class="flex items-center gap-3 w-full" :class="largeurCategorie">
            <BackLink fallback="/" />
            <h1 class="font-display text-xl font-black tracking-tight bg-gradient-to-r from-slate-100 to-slate-400 bg-clip-text text-transparent">{{ categoryTitle }}</h1>
          </div>

          <!-- Niveau 1 : les 4 grandes catégories -->
          <div v-if="!selectedCategory" class="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">

            <div class="card flex flex-col gap-3
                       border-t-2 border-t-blue-600 hover:border-blue-700 hover:bg-blue-950/20
                       hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200
                       cursor-pointer group"
              @click="openCategory('pricing')">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-blue-900/50 flex items-center justify-center text-xl">📁</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-blue-300 transition-colors">Pricing</div>
                  <div class="text-xs text-slate-500">Scripts · Pricer · Documentation</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Structurez, pricez et documentez vos produits.</p>
            </div>

            <div class="card flex flex-col gap-3
                       border-t-2 border-t-yellow-600 hover:border-yellow-700 hover:bg-yellow-950/20
                       hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200
                       cursor-pointer group"
              @click="openCategory('life_cycle')">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-yellow-900/50 flex items-center justify-center text-xl">📒</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-yellow-300 transition-colors">Life Cycle</div>
                  <div class="text-xs text-slate-500">Produits bookés en vie</div>
                </div>
                <span v-if="unreadAlerts > 0"
                  class="ml-auto px-2 py-0.5 rounded-full bg-red-900/60 text-red-300 text-xs font-bold pulse-ring"
                  :title="`${unreadAlerts} alerte(s) non lue(s)`">
                  🔔 {{ unreadAlerts }}
                </span>
              </div>
              <p class="text-xs text-slate-600">Suivi des produits structurés : nominaux, strikes, dates d'observation, statut de rappel/KI.</p>
            </div>

            <div class="card flex flex-col gap-3
                       border-t-2 border-t-red-700 hover:border-red-700 hover:bg-red-950/20
                       hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200
                       cursor-pointer group"
              @click="openCategory('risk_management')">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-red-900/50 flex items-center justify-center text-xl">🛡️</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-red-300 transition-colors">Risk Management</div>
                  <div class="text-xs text-slate-500">Portefeuilles · Chocs · P&amp;L</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Créez vos portefeuilles et analysez leur risque : Greeks agrégés, stress-tests et P&amp;L explain.</p>
            </div>

            <div class="card flex flex-col gap-3
                       border-t-2 border-t-amber-600 hover:border-amber-600 hover:bg-amber-950/20
                       hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200
                       cursor-pointer group"
              @click="openCategory('studies')">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-amber-900/50 flex items-center justify-center text-xl">📐</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-amber-300 transition-colors">Studies</div>
                  <div class="text-xs text-slate-500">Fama-French · Carnet d'ordres</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Analyse de performance et reconstruction FIFO des carnets d'ordres.</p>
            </div>

            <div class="card flex flex-col gap-3
                       border-t-2 border-t-pink-600 hover:border-pink-700 hover:bg-pink-950/20
                       hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200
                       cursor-pointer group"
              @click="openCategory('competitive_bidding')">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-pink-900/50 flex items-center justify-center text-xl">📨</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-pink-300 transition-colors">Competitive Bidding</div>
                  <div class="text-xs text-slate-500">RFQ · Analyse contreparties</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Comparez les prix reçus des banques au prix modèle Structura.</p>
            </div>

            <div class="card flex flex-col gap-3
                       border-t-2 border-t-emerald-600 hover:border-emerald-700 hover:bg-emerald-950/20
                       hover:shadow-xl hover:shadow-black/30 hover:-translate-y-0.5 transition-all duration-200
                       cursor-pointer group"
              @click="openCategory('clients')">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-emerald-900/50 flex items-center justify-center text-xl">🤝</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-emerald-300 transition-colors">Clients</div>
                  <div class="text-xs text-slate-500">Sociétés · Contacts · Opportunités</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Qui vous couvrez, qui y travaille et ce qu'ils achètent réellement.</p>
            </div>

          </div>

          <!-- Niveau 2 : sous-cards de la catégorie sélectionnée -->
          <div v-else-if="selectedCategory === 'pricing'" class="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">

            <!-- Mes Scripts -->
            <RouterLink to="/scripts"
              class="card flex flex-col gap-3
                     hover:border-blue-700 hover:bg-blue-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
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
              class="card flex flex-col gap-3
                     hover:border-green-700 hover:bg-green-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
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
              class="card flex flex-col gap-3
                     hover:border-purple-700 hover:bg-purple-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-purple-900/50 flex items-center justify-center text-xl">📚</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-purple-300 transition-colors">Documentation</div>
                  <div class="text-xs text-slate-500">KID PRIIPs · Term Sheets · Bibliothèque</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Générez et archivez vos documents réglementaires et commerciaux.</p>
            </RouterLink>

          </div>

          <div v-else-if="selectedCategory === 'life_cycle'" class="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">

            <!-- Booking -->
            <RouterLink to="/booking"
              class="card flex flex-col gap-3
                     hover:border-yellow-700 hover:bg-yellow-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-yellow-900/50 flex items-center justify-center text-xl">📒</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-yellow-300 transition-colors">Booking</div>
                  <div class="text-xs text-slate-500">Produits bookés</div>
                </div>
                <span v-if="unreadAlerts > 0"
                  class="ml-auto px-2 py-0.5 rounded-full bg-red-900/60 text-red-300 text-xs font-bold pulse-ring"
                  :title="`${unreadAlerts} alerte(s) non lue(s)`">
                  🔔 {{ unreadAlerts }}
                </span>
              </div>
              <p class="text-xs text-slate-600">Suivi des produits structurés en vie : nominaux, strikes, dates d'observation, statut de rappel/KI.</p>
            </RouterLink>

            <!-- Réinvestissement -->
            <RouterLink to="/reinvest"
              class="card flex flex-col gap-3
                     hover:border-orange-700 hover:bg-orange-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-orange-900/50 flex items-center justify-center text-xl">🔄</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-orange-300 transition-colors">Réinvestissement</div>
                  <div class="text-xs text-slate-500">Alternatives à un produit en vie</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Espace de travail interne : partez d'un deal client en vie et cherchez le meilleur sous-jacent de remplacement.</p>
            </RouterLink>

          </div>

          <div v-else-if="selectedCategory === 'risk_management'" class="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">

            <!-- Création de portefeuille -->
            <RouterLink to="/risk?tab=portfolios"
              class="card flex flex-col gap-3
                     hover:border-red-700 hover:bg-red-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-red-900/50 flex items-center justify-center text-xl">📁</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-red-300 transition-colors">Création de portefeuille</div>
                  <div class="text-xs text-slate-500">Gestion des books &amp; composition</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Créez, renommez et organisez vos portefeuilles ; affectez chaque deal à son book.</p>
            </RouterLink>

            <!-- Contreparties -->
            <RouterLink to="/risk?tab=contreparties"
              class="card flex flex-col gap-3
                     hover:border-sky-700 hover:bg-sky-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-sky-900/50 flex items-center justify-center text-xl">🏦</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-sky-300 transition-colors">Contreparties</div>
                  <div class="text-xs text-slate-500">Concentration &amp; limites par émetteur</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Nominal par contrepartie, indice de concentration (HHI) et alerte de dépassement de limite.</p>
            </RouterLink>

            <!-- Chocs -->
            <RouterLink to="/risk?tab=chocs"
              class="card flex flex-col gap-3
                     hover:border-orange-700 hover:bg-orange-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-orange-900/50 flex items-center justify-center text-xl">⚡</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-orange-300 transition-colors">Chocs</div>
                  <div class="text-xs text-slate-500">Stress-tests spot / vol / taux / corrélation</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Full reprice du portefeuille sous scénario choqué — pas une approximation par les Greeks.</p>
            </RouterLink>

            <!-- VaR / Expected Shortfall -->
            <RouterLink to="/risk?tab=var"
              class="card flex flex-col gap-3
                     hover:border-fuchsia-700 hover:bg-fuchsia-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-fuchsia-900/50 flex items-center justify-center text-xl">📉</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-fuchsia-300 transition-colors">VaR / Expected Shortfall</div>
                  <div class="text-xs text-slate-500">Historique &amp; paramétrique, côte à côte</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Rejoue le book sous des centaines de scénarios de marché — étude asynchrone via le module de calcul.</p>
            </RouterLink>

            <!-- Explication de P&L -->
            <RouterLink to="/risk?tab=pnl"
              class="card flex flex-col gap-3
                     hover:border-emerald-700 hover:bg-emerald-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-emerald-900/50 flex items-center justify-center text-xl">📊</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-emerald-300 transition-colors">Explication de P&amp;L</div>
                  <div class="text-xs text-slate-500">Waterfall temps · spot · vol · corrélation</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Expliquez le P&amp;L du portefeuille entre deux dates, agrégé en EUR deal par deal.</p>
            </RouterLink>

            <!-- Proximité aux barrières -->
            <RouterLink to="/risk?tab=barrieres"
              class="card flex flex-col gap-3
                     hover:border-amber-700 hover:bg-amber-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-amber-900/50 flex items-center justify-center text-xl">📍</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-amber-300 transition-colors">Proximité aux barrières</div>
                  <div class="text-xs text-slate-500">Autocall &amp; KI classés par urgence</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Classe les deals actifs par écart entre le worst-of actuel et leur prochaine barrière.</p>
            </RouterLink>

          </div>

          <div v-else-if="selectedCategory === 'studies'" class="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">

            <!-- Étude Fama-French -->
            <RouterLink to="/amc"
              class="card flex flex-col gap-3
                     hover:border-amber-600 hover:bg-amber-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-amber-900/50 flex items-center justify-center text-xl">📐</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-amber-300 transition-colors">Étude Fama-French</div>
                  <div class="text-xs text-slate-500">Analyse AMC · Dépendance gérant</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Décomposez la performance d'un AMC en facteurs de risque et mesurez la valeur ajoutée du gérant.</p>
            </RouterLink>

            <!-- Charger une étude -->
            <div class="card flex flex-col gap-3">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-indigo-900/50 flex items-center justify-center text-xl">📂</div>
                <div>
                  <div class="font-bold text-slate-100">Charger une étude</div>
                  <div class="text-xs text-slate-500">Études AMC sauvegardées</div>
                </div>
              </div>
              <div v-if="recentStudiesLoading" class="text-xs text-slate-600">Chargement…</div>
              <div v-else-if="!recentStudies.length" class="text-xs text-slate-600">Aucune étude sauvegardée pour l'instant. Lancez une étude dans le module AMC puis sauvegardez-la.</div>
              <ul v-else class="flex flex-col gap-1.5">
                <li v-for="s in recentStudies" :key="s.id" @click="openStudy(s.id)"
                  class="flex items-center justify-between gap-2 text-xs px-2.5 py-2 rounded-lg border border-slate-800 hover:border-indigo-600 hover:bg-indigo-950/20 cursor-pointer transition-colors">
                  <div class="min-w-0">
                    <div class="text-slate-200 truncate">{{ s.label }}</div>
                    <div class="text-[10px] text-slate-600 font-mono">{{ s.isin }} · {{ new Date(s.updated_at).toLocaleDateString('fr-FR') }}</div>
                  </div>
                  <span class="text-indigo-400 shrink-0">→</span>
                </li>
              </ul>
            </div>

            <!-- Carnet d'ordres FIFO -->
            <RouterLink to="/fifo"
              class="card flex flex-col gap-3
                     hover:border-cyan-700 hover:bg-cyan-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-cyan-900/50 flex items-center justify-center text-xl">📋</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-cyan-300 transition-colors">Carnet d'ordres</div>
                  <div class="text-xs text-slate-500">FIFO · P&amp;L réalisé &amp; latent</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Compilez les carnets d'ordres de fonds et AMC. Reconstruction FIFO avec modes actions ou cert-units.</p>
            </RouterLink>

          </div>

          <div v-else-if="selectedCategory === 'competitive_bidding'" class="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-xl">

            <!-- RFQ Fournisseurs -->
            <RouterLink to="/rfq"
              class="card flex flex-col gap-3
                     hover:border-pink-700 hover:bg-pink-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-pink-900/50 flex items-center justify-center text-xl">📨</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-pink-300 transition-colors">RFQ Fournisseurs</div>
                  <div class="text-xs text-slate-500">Comparer les prix des contreparties</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Collectez les prix reçus des banques pour un produit et comparez-les au prix modèle Structura.</p>
            </RouterLink>

            <!-- Analyse Contreparties -->
            <RouterLink to="/rfq/analyse"
              class="card flex flex-col gap-3
                     hover:border-rose-700 hover:bg-rose-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-rose-900/50 flex items-center justify-center text-xl">📈</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-rose-300 transition-colors">Analyse Contreparties</div>
                  <div class="text-xs text-slate-500">Écarts de prix par banque &amp; produit</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Suivez dans le temps comment chaque contrepartie se positionne, par type de produit, vs le prix modèle Structura.</p>
            </RouterLink>

          </div>

          <!-- Le menu du module Clients : une carte par sous-module.
               C'est ICI qu'on choisit, et non dans une barre d'onglets une fois
               entré — sept sections empilées dans une barre se lisent mal et
               n'annoncent rien de ce qu'elles contiennent. -->
          <div v-else-if="selectedCategory === 'clients'" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 w-full" :class="largeurCategorie">

            <RouterLink to="/clients/apercu"
              class="card flex flex-col gap-3
                     hover:border-emerald-700 hover:bg-emerald-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-emerald-900/50 flex items-center justify-center text-xl">📊</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-emerald-300 transition-colors">Vue d’ensemble</div>
                  <div class="text-xs text-slate-500">Relances dues · signaux · volumes</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Ce qui demande une action aujourd’hui, tous clients confondus — les relances échues, les fenêtres de contact ouvertes et les silences anormaux.</p>
            </RouterLink>

            <RouterLink to="/clients/liste"
              class="card flex flex-col gap-3
                     hover:border-sky-700 hover:bg-sky-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-sky-900/50 flex items-center justify-center text-xl">🏢</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-sky-300 transition-colors">Clients</div>
                  <div class="text-xs text-slate-500">Sociétés couvertes · politique déclarée</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Les maisons que vous couvrez, leur statut, leurs bornes d’investissement et ce qu’elles acceptent de traiter.</p>
            </RouterLink>

            <RouterLink to="/clients/contacts"
              class="card flex flex-col gap-3
                     hover:border-indigo-700 hover:bg-indigo-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-indigo-900/50 flex items-center justify-center text-xl">👤</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-indigo-300 transition-colors">Contacts</div>
                  <div class="text-xs text-slate-500">Personnes · parcours professionnel</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Les personnes, leur poste actuel et l’historique qui les suit d’une maison à l’autre — leurs trades restent chez l’employeur d’alors.</p>
            </RouterLink>

            <RouterLink to="/clients/opportunites"
              class="card flex flex-col gap-3
                     hover:border-amber-700 hover:bg-amber-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-amber-900/50 flex items-center justify-center text-xl">🎯</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-amber-300 transition-colors">Opportunités</div>
                  <div class="text-xs text-slate-500">En cours · gagnées · perdues et pourquoi</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Les affaires en cours et leur issue. Une perte porte son motif : c’est lui qui dit si le prix, le timing ou le produit était en cause.</p>
            </RouterLink>

            <RouterLink to="/clients/signaux"
              class="card flex flex-col gap-3
                     hover:border-violet-700 hover:bg-violet-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-violet-900/50 flex items-center justify-center text-xl">📡</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-violet-300 transition-colors">Cycles &amp; Signaux</div>
                  <div class="text-xs text-slate-500">Cadence · fenêtres de contact</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Le rythme d’investissement observé de chaque client, et le moment où le rappeler — jamais une date précise, toujours une fenêtre.</p>
            </RouterLink>

            <RouterLink to="/clients/analytics"
              class="card flex flex-col gap-3
                     hover:border-cyan-700 hover:bg-cyan-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-cyan-900/50 flex items-center justify-center text-xl">📈</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-cyan-300 transition-colors">Analytics</div>
                  <div class="text-xs text-slate-500">Espace négatif · comportement observé</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Le déclaré et l’observé superposés : émetteurs jamais servis, produits traités hors politique, niveaux réellement acceptés.</p>
            </RouterLink>

            <RouterLink to="/clients/import"
              class="card flex flex-col gap-3
                     hover:border-rose-700 hover:bg-rose-950/20 hover:shadow-xl hover:shadow-black/30
                     hover:-translate-y-0.5 transition-all duration-200 cursor-pointer group">
              <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-lg bg-rose-900/50 flex items-center justify-center text-xl">📥</div>
                <div>
                  <div class="font-bold text-slate-100 group-hover:text-rose-300 transition-colors">Import d’historique</div>
                  <div class="text-xs text-slate-500">Excel · JSON · rapport d’anomalies</div>
                </div>
              </div>
              <p class="text-xs text-slate-600">Verser l’historique qu’un client vous transmet. L’aperçu annonce ce qui passera avant d’écrire quoi que ce soit.</p>
            </RouterLink>

          </div>

        </div>
      </Transition>

    </main>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import BackLink from '../components/ui/BackLink.vue'
import { apiFetch } from '../utils/api.js'

const auth   = useAuthStore()
const route  = useRoute()
const router = useRouter()

const recentStudies        = ref([])
const recentStudiesLoading = ref(true)

async function fetchRecentStudies() {
  recentStudiesLoading.value = true
  try {
    const res = await apiFetch('/api/amc/studies')
    if (res.ok) recentStudies.value = (await res.json()).slice(0, 5)
  } catch { /* ignore */ } finally {
    recentStudiesLoading.value = false
  }
}
fetchRecentStudies()

const unreadAlerts = ref(0)

async function fetchUnreadAlerts() {
  try {
    const res = await apiFetch('/api/alerts?unread_only=true&limit=1')
    if (res.ok) unreadAlerts.value = (await res.json()).unread
  } catch { /* ignore */ }
}
fetchUnreadAlerts()

function openStudy(id) {
  router.push({ path: '/amc', query: { study_id: id } })
}

// ── Accueil en 4 catégories + drill-down (HOME_REDESIGN_DESIGN.md) ────────
const CATEGORY_TITLES = {
  pricing: 'Pricing',
  life_cycle: 'Life Cycle',
  risk_management: 'Risk Management',
  studies: 'Studies',
  competitive_bidding: 'Competitive Bidding',
  clients: 'Clients',
}
const selectedCategory = ref(route.query.category || null)
const categoryTitle = computed(() => CATEGORY_TITLES[selectedCategory.value] || '')

// La largeur du bandeau doit suivre celle de la grille, sinon le titre et les
// cartes ne s'alignent pas. Clients en compte sept, les autres deux à quatre.
const largeurCategorie = computed(() =>
  selectedCategory.value === 'clients' ? 'max-w-4xl' : 'max-w-xl')

/**
 * Échap ramène à l'accueil, avec la même sémantique que le bouton.
 *
 * Le garde n'est pas décoratif : l'écouteur est posé sur les DEUX niveaux, et
 * depuis que le retour passe par l'historique, un Échap sur l'accueil principal
 * ferait sortir de l'application — vers la page précédente du navigateur.
 * Avant, il ne faisait rien.
 */
function revenirAuxCategories() {
  if (!selectedCategory.value) return
  if (window.history.state?.back) router.back()
  else router.push('/')
}

// L'onglet de navigation du haut route vers /?category=... — permet d'arriver
// directement sur le menu de la catégorie plutôt que sur une sous-page précise.
watch(() => route.query.category, (cat) => {
  selectedCategory.value = cat || null
})

/**
 * Ouvrir le menu d'un module.
 *
 * `router.push`, et non une simple variable : le menu du module doit exister
 * dans l'HISTORIQUE. Sans cela il n'y a que deux entrées — l'accueil et la
 * sous-page — et le bouton retour d'un sous-module saute par-dessus le menu du
 * module pour retomber sur l'accueil principal. Le niveau intermédiaire
 * existait à l'écran sans exister dans la navigation.
 *
 * Trois autres choses en découlent, toutes attendues d'une application web :
 * le menu d'un module se partage par son lien, se met en signet, et le bouton
 * retour DU NAVIGATEUR fait la même chose que le nôtre.
 */
function openCategory(key) {
  router.push({ path: '/', query: { category: key } })
}
function onAfterEnter(el) {
  // el.focus() called synchronously from the transitionend-driven after-enter
  // hook doesn't reliably stick (observed: activeElement stays <body>) —
  // deferring one frame lets the browser settle after the transition before
  // taking focus, which is what makes Échap work right after a drill-down.
  requestAnimationFrame(() => el.focus())
}
</script>
