<template>
  <div class="flex-1 flex flex-col min-h-0">

    <!-- Barre d'outils : titre + switch de mode (reste local, pas d'état
         cross-vue dans le shell) -->
    <div class="border-b px-5 py-2.5 flex items-center gap-4 shrink-0" style="border-color: var(--border);">
      <RouterLink :to="{ path: '/', query: { category: 'studies' } }" class="btn-secondary text-xs px-3 py-1.5 shrink-0">← Retour</RouterLink>
      <h1 class="page-title text-lg shrink-0">Analyse AMC</h1>
      <div class="tabs shrink-0">
        <button @click="mainTab = 'classic'" class="tab-btn" :class="{ active: mainTab === 'classic' }">
          Analyse FF classique
        </button>
        <button @click="mainTab = 'study'" class="tab-btn" :class="{ active: mainTab === 'study' }">
          Étude complète A/B/C/D
        </button>
      </div>
      <div class="ml-auto flex items-center gap-2">
        <span v-if="mainTab === 'classic' && result" class="text-xs" style="color: var(--muted);">
          {{ result.ff_series }} · {{ result.benchmark }} · {{ result.regression?.n_obs }} obs.
        </span>
        <span v-if="mainTab === 'study' && studyResult" class="text-xs" style="color: var(--muted);">
          {{ demo.enabled ? '••• AMC' : studyResult.meta?.isin }} · {{ studyResult.meta?.currency }}
        </span>
      </div>
    </div>

    <!-- Main 2-col -->
    <main class="flex-1 grid grid-cols-[380px_1fr] min-h-0">

      <!-- ── LEFT: Config ──────────────────────────────────────────── -->
      <aside class="border-r border-slate-800 flex flex-col overflow-y-auto p-5 gap-5">

        <!-- ══════════════════════════════════════════════════════════ -->
        <!-- MODE CLASSIQUE                                             -->
        <!-- ══════════════════════════════════════════════════════════ -->
        <template v-if="mainTab === 'classic'">

        <!-- Upload -->
        <div class="card">
          <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">1. Fichier diagnostique AMC</h3>
          <label
            class="block border-2 border-dashed rounded-lg p-5 text-center cursor-pointer transition-colors"
            :class="uploadedFile
              ? 'border-emerald-600 bg-emerald-950/20'
              : 'border-slate-700 hover:border-slate-500 bg-slate-800/20'"
            @dragover.prevent @drop.prevent="onDrop">
            <input type="file" accept=".xlsx,.xls" class="hidden" @change="onFileChange" />
            <div v-if="!uploadedFile" class="text-slate-500 text-sm">
              <div class="text-2xl mb-2">📂</div>
              Glissez votre fichier Excel AMC ici<br>
              <span class="text-xs">ou cliquez pour sélectionner</span>
            </div>
            <div v-else class="text-emerald-400 text-sm">
              <div class="text-2xl mb-1">✅</div>
              <strong>{{ uploadedFile.name }}</strong>
              <div class="text-xs text-slate-500 mt-1" v-if="parsed">
                {{ parsed.nav?.length || 0 }} NAV · {{ parsed.transactions?.length || 0 }} trades
              </div>
            </div>
          </label>
          <div v-if="uploadError" class="text-red-400 text-xs mt-2">⚠ {{ uploadError }}</div>
          <div v-if="uploadLoading" class="text-slate-400 text-xs mt-2 flex items-center gap-2">
            <span class="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin"></span>
            Analyse du fichier…
          </div>
          <!-- Meta card -->
          <div v-if="parsed?.meta?.product_name" class="mt-3 bg-slate-800/40 rounded-lg p-3 text-xs">
            <div class="font-semibold text-slate-200 truncate">{{ parsed.meta.product_name }}</div>
            <div class="text-slate-500 mt-1">{{ parsed.meta.isin }} · {{ parsed.meta.currency }}</div>
          </div>
        </div>

        <!-- FF Series -->
        <div class="card">
          <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">2. Série Fama-French</h3>
          <select v-model="config.ff_series" class="select text-xs w-full" @change="onSeriesChange">
            <option v-for="s in ffSeries" :key="s.key" :value="s.key">{{ s.label }}</option>
          </select>
          <!-- Factor checkboxes -->
          <div v-if="availableFactors.length" class="mt-3">
            <div class="text-xs text-slate-500 mb-2">Facteurs à inclure dans la régression :</div>
            <div class="flex flex-wrap gap-2">
              <label v-for="f in availableFactors" :key="f"
                class="flex items-center gap-1.5 text-xs cursor-pointer px-2 py-1 rounded border transition-colors"
                :class="config.selected_factors.includes(f)
                  ? 'border-blue-600 bg-blue-950/40 text-blue-300'
                  : 'border-slate-700 text-slate-500 hover:border-slate-500'">
                <input type="checkbox" class="hidden" :value="f" v-model="config.selected_factors" />
                {{ f }}
              </label>
            </div>
          </div>
        </div>

        <!-- FF Data status -->
        <div class="card">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Données FF stockées</h3>
            <button class="text-[10px] text-slate-500 hover:text-slate-300 transition-colors" @click="loadFfStatus">↻ actualiser</button>
          </div>
          <div v-if="ffStatus.length === 0" class="text-xs text-slate-600 italic">Chargement…</div>
          <div v-else class="space-y-1.5">
            <div v-for="s in ffStatus" :key="s.key"
              class="flex items-center gap-2 text-xs rounded px-2 py-1.5"
              :class="s.key === config.ff_series ? 'bg-slate-800/60 ring-1 ring-slate-700' : ''">
              <span class="text-base leading-none">{{ s.available ? '✅' : '⬜' }}</span>
              <div class="flex-1 min-w-0">
                <div class="text-slate-300 truncate">{{ s.key }}</div>
                <div v-if="s.available" class="text-[10px]"
                  :class="ffDataAge(s.date_max) > 45 ? 'text-amber-500' : 'text-slate-600'">
                  {{ s.date_min }} → {{ s.date_max }}
                  <span v-if="ffDataAge(s.date_max) > 45"> · ⚠ {{ ffDataAge(s.date_max) }}j</span>
                </div>
                <div v-else class="text-amber-600 text-[10px]">Non importé</div>
              </div>
              <button
                class="shrink-0 text-[10px] px-2 py-0.5 rounded border transition-colors"
                :class="refreshing === s.key
                  ? 'border-blue-700 text-blue-400'
                  : 'border-slate-700 text-slate-500 hover:border-slate-500 hover:text-slate-300'"
                :disabled="refreshing === s.key"
                @click="doRefresh(s.key)">
                <span v-if="refreshing === s.key" class="inline-block w-2.5 h-2.5 border border-blue-400 border-t-transparent rounded-full animate-spin"></span>
                <span v-else>↓ MAJ</span>
              </button>
            </div>
          </div>
          <div v-if="refreshError" class="text-red-400 text-[10px] mt-2">⚠ {{ refreshError }}</div>
        </div>

        <!-- Overlap preview -->
        <div v-if="overlapInfo" class="card text-xs"
          :class="overlapInfo.status === 'ok' ? 'border-emerald-800/60' : overlapInfo.status === 'warn' ? 'border-amber-700/60' : 'border-red-800/60'">
          <h3 class="font-bold uppercase tracking-wider mb-2"
            :class="overlapInfo.status === 'ok' ? 'text-emerald-500' : overlapInfo.status === 'warn' ? 'text-amber-500' : 'text-red-500'">
            {{ overlapInfo.status === 'ok' ? '✓' : overlapInfo.status === 'warn' ? '⚠' : '✗' }}
            Période d'analyse
          </h3>
          <div v-if="overlapInfo.overlap > 0" class="space-y-1 text-slate-400">
            <div class="flex justify-between">
              <span class="text-slate-500">NAV</span>
              <span class="font-mono">{{ overlapInfo.navStart }} → {{ overlapInfo.navEnd }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-500">FF {{ config.ff_series }}</span>
              <span class="font-mono">{{ overlapInfo.ffStart }} → {{ overlapInfo.ffEnd }}</span>
            </div>
            <div class="border-t border-slate-800 pt-1 mt-1 flex justify-between font-semibold"
              :class="overlapInfo.status === 'ok' ? 'text-emerald-400' : 'text-amber-400'">
              <span>Intersection</span>
              <span class="font-mono">{{ overlapInfo.overlapStart }} → {{ overlapInfo.overlapEnd }}</span>
            </div>
            <div class="flex justify-between text-slate-500">
              <span>Observations estimées</span>
              <span class="font-semibold" :class="overlapInfo.overlap < 20 ? 'text-red-400' : overlapInfo.overlap < 60 ? 'text-amber-400' : 'text-emerald-400'">
                ~{{ overlapInfo.overlap }} jours
              </span>
            </div>
          </div>
          <div v-else class="text-red-400">
            Aucune période commune — choisissez une autre série FF
            (US_3F/EU_3F couvrent jusqu'en 2026).
          </div>
        </div>

        <!-- Benchmark -->
        <div class="card">
          <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">3. Benchmark</h3>
          <select v-model="config.benchmark_ticker" class="select text-xs w-full">
            <optgroup v-for="(items, group) in benchmarkGroups" :key="group" :label="group">
              <option v-for="b in items" :key="b.ticker" :value="b.ticker">{{ b.label }}</option>
            </optgroup>
          </select>
          <div v-if="config.benchmark_ticker === 'CUSTOM'" class="mt-2">
            <input v-model="customTicker" class="input text-xs w-full" placeholder="Ex: NFRA.L, INFR..." />
          </div>
        </div>

        <!-- Rolling window -->
        <div class="card">
          <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">4. Analyse rolling</h3>
          <div class="flex items-center gap-3">
            <input v-model.number="config.rolling_window" type="number" min="20" max="120"
              class="input text-xs w-24" />
            <span class="text-xs text-slate-500">jours de fenêtre glissante</span>
          </div>
        </div>

        <!-- Analyze button -->
        <button
          class="btn-primary text-sm py-3 flex items-center justify-center gap-2"
          :disabled="!parsed || analyzing || config.selected_factors.length === 0"
          @click="analyze">
          <span v-if="analyzing" class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
          {{ analyzing ? 'Calcul en cours… (10-30s)' : '▶ Lancer l\'analyse FF' }}
        </button>

        <!-- Export PDF button -->
        <button v-if="result"
          class="w-full text-sm py-2.5 rounded-lg border border-slate-600 text-slate-300 hover:border-blue-500 hover:text-blue-300 flex items-center justify-center gap-2 transition-colors"
          :disabled="pdfLoading"
          @click="exportPdf">
          <span v-if="pdfLoading" class="w-4 h-4 border-2 border-slate-400 border-t-transparent rounded-full animate-spin"></span>
          <span v-else>📄</span>
          {{ pdfLoading ? 'Génération PDF…' : 'Exporter rapport PDF' }}
        </button>

        <div v-if="analyzeError" class="text-red-400 text-xs p-3 bg-red-950/30 rounded-lg border border-red-900">
          ⚠ {{ analyzeError }}
        </div>

        </template><!-- /MODE CLASSIQUE -->

        <!-- ══════════════════════════════════════════════════════════ -->
        <!-- MODE ÉTUDE COMPLÈTE                                        -->
        <!-- ══════════════════════════════════════════════════════════ -->
        <template v-if="mainTab === 'study'">

        <!-- Études sauvegardées -->
        <div class="card" v-if="savedStudies.length || savedStudiesLoading">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Études sauvegardées</h3>
            <button class="text-[10px] text-slate-500 hover:text-slate-300" @click="fetchSavedStudies">↻</button>
          </div>
          <div v-if="savedStudiesLoading" class="text-xs text-slate-600">Chargement…</div>
          <ul v-else class="flex flex-col gap-1.5 max-h-64 overflow-y-auto">
            <li v-for="s in savedStudies" :key="s.id"
              class="flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded border border-slate-800 hover:border-emerald-700 transition-colors">
              <div class="min-w-0">
                <div class="text-slate-300 truncate">{{ s.label }}</div>
                <div class="text-[10px] text-slate-600 font-mono">{{ s.isin }} · {{ new Date(s.updated_at).toLocaleDateString('fr-FR') }}</div>
              </div>
              <div class="flex items-center gap-1 shrink-0">
                <button @click="loadStudyById(s.id)" :disabled="loadStudyLoadingId === s.id"
                  title="Charger"
                  class="w-6 h-6 flex items-center justify-center rounded border border-emerald-800 text-emerald-400 hover:border-emerald-500 hover:text-emerald-300 transition-colors">
                  <span v-if="loadStudyLoadingId === s.id" class="w-3 h-3 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin"></span>
                  <span v-else>↩</span>
                </button>
                <button @click="deleteStudy(s.id)" title="Supprimer"
                  class="w-6 h-6 flex items-center justify-center rounded text-slate-600 hover:text-red-400 transition-colors">✕</button>
              </div>
            </li>
          </ul>
        </div>

        <!-- FF Series étude -->
        <div class="card">
          <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">1. Série Fama-French</h3>
          <select v-model="studyConfig.ff_series" class="select text-xs w-full" @change="onStudySeriesChange">
            <option v-for="s in ffSeries" :key="s.key" :value="s.key">{{ s.label }}</option>
          </select>
          <div v-if="studyAvailableFactors.length" class="mt-3">
            <div class="text-xs text-slate-500 mb-2">Facteurs à inclure :</div>
            <div class="flex flex-wrap gap-2">
              <label v-for="f in studyAvailableFactors" :key="f"
                class="flex items-center gap-1.5 text-xs cursor-pointer px-2 py-1 rounded border transition-colors"
                :class="studyConfig.selected_factors.includes(f)
                  ? 'border-blue-600 bg-blue-950/40 text-blue-300'
                  : 'border-slate-700 text-slate-500 hover:border-slate-500'">
                <input type="checkbox" class="hidden" :value="f" v-model="studyConfig.selected_factors" />
                {{ f }}
              </label>
            </div>
          </div>
        </div>

        <!-- Benchmark étude -->
        <div class="card">
          <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">2. Benchmark</h3>
          <select v-model="studyConfig.benchmark_ticker" class="select text-xs w-full">
            <optgroup v-for="(items, group) in benchmarkGroups" :key="group" :label="group">
              <option v-for="b in items" :key="b.ticker" :value="b.ticker">{{ b.label }}</option>
            </optgroup>
          </select>
          <div v-if="studyConfig.benchmark_ticker === 'CUSTOM'" class="mt-2">
            <input v-model="studyCustomTicker" class="input text-xs w-full font-mono" placeholder="Ex: EUFN, KBE…" />
          </div>
        </div>

        <!-- Rolling window étude -->
        <div class="card">
          <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">3. Fenêtre rolling</h3>
          <div class="flex items-center gap-3">
            <input v-model.number="studyConfig.rolling_window" type="number" min="20" max="120" class="input text-xs w-24" />
            <span class="text-xs text-slate-500">jours de fenêtre glissante</span>
          </div>
        </div>

        <!-- FF Data status (compact) -->
        <div class="card">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Données FF stockées</h3>
            <button class="text-[10px] text-slate-500 hover:text-slate-300" @click="loadFfStatus">↻</button>
          </div>
          <template v-for="s in ffSeries" :key="s.key">
            <div v-if="ffStatus.find(x => x.key === s.key)"
              class="flex items-center gap-2 text-xs py-1"
              :class="s.key === studyConfig.ff_series ? 'text-slate-200' : 'text-slate-600'">
              <span>{{ ffStatus.find(x => x.key === s.key)?.available ? '✅' : '⬜' }}</span>
              <span class="truncate flex-1">{{ s.key }}</span>
              <button class="text-[10px] border border-slate-700 px-1.5 py-0.5 rounded hover:border-slate-500"
                :disabled="refreshing === s.key"
                @click="doRefresh(s.key)">
                <span v-if="refreshing === s.key" class="inline-block w-2 h-2 border border-blue-400 border-t-transparent rounded-full animate-spin"></span>
                <span v-else>↓</span>
              </button>
            </div>
          </template>
          <div v-if="refreshError" class="text-red-400 text-[10px] mt-1">⚠ {{ refreshError }}</div>
        </div>

        <!-- Source de données -->
        <div class="card border border-blue-900/40">
          <h3 class="text-xs font-bold text-blue-400 uppercase tracking-wider mb-3">4. Source de données</h3>

          <!-- Client selector -->
          <div class="flex flex-col gap-2 mb-3">
            <div>
              <label class="text-xs text-slate-400 mb-1 block">Client</label>
              <select v-model="selectedClient" class="select text-xs w-full"
                @change="selectedUtiIsin = ''">
                <option value="">— Sélectionner —</option>
                <option value="UTI">UTI</option>
                <option value="manual">Chemin manuel</option>
              </select>
            </div>

            <!-- UTI ISIN selector (visible only when UTI is selected) -->
            <div v-if="selectedClient === 'UTI'">
              <label class="text-xs text-slate-400 mb-1 block">AMC UTI</label>
              <select v-model="selectedUtiIsin" class="select text-xs w-full">
                <option value="">— Sélectionner un AMC —</option>
                <option v-for="p in UTI_ISINS" :key="p.isin" :value="p.isin">
                  {{ p.label }} · {{ p.isin }}
                </option>
              </select>
            </div>
          </div>

          <div v-if="selectedClient !== 'UTI' || !selectedUtiIsin">
            <label class="text-xs text-slate-400 mb-1 block">Chemin du dossier ISIN</label>
            <input v-model="studyFolder" class="input text-xs w-full font-mono"
              placeholder="C:\Users\...\Data\CH1352587708" />
          </div>
          <div v-else class="text-[10px] text-slate-500 font-mono truncate mb-1 px-1">{{ studyFolder }}</div>

          <button class="btn-primary text-xs py-2 flex items-center justify-center gap-2 mt-2 w-full"
            :disabled="!studyFolder.trim() || studyLoading"
            @click="detectFolder">
            <span v-if="studyLoading && !manifestData" class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
            {{ (studyLoading && !manifestData) ? 'Scan…' : '🔍 Scanner le dossier' }}
          </button>

          <!-- Manifest -->
          <div v-if="manifestData" class="flex flex-col gap-2 mt-3">
            <div class="text-xs font-bold text-slate-300">Manifeste détecté</div>
            <div class="bg-slate-900 rounded p-2 text-xs space-y-1">
              <div class="flex justify-between">
                <span class="text-slate-500">ISIN</span>
                <span class="text-slate-300 font-mono">{{ manifestData.manifest?.product?.isin }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-500">Devise</span>
                <span class="text-slate-300">{{ manifestData.manifest?.product?.currency }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-500">Thème</span>
                <span class="text-slate-300">{{ manifestData.manifest?.product?.theme || '—' }}</span>
              </div>
            </div>

            <div v-if="manifestData.missing_manual_fields?.length" class="bg-amber-950/30 border border-amber-800 rounded p-2 text-xs">
              <div class="font-bold text-amber-400 mb-1">⚠ Champs manuels requis</div>
              <div v-for="f in manifestData.missing_manual_fields" :key="f" class="text-amber-300/80 text-[10px] py-0.5">• {{ f }}</div>
            </div>

            <div class="bg-slate-900 rounded p-2 text-xs space-y-2">
              <div class="grid grid-cols-3 gap-2">
                <div>
                  <label class="text-slate-500 block mb-0.5">Frais gestion (% p.a.)</label>
                  <input type="number" step="0.1" min="0" max="5"
                    :value="manifestData.manifest?.params?.management_fee_pct || ''"
                    @input="manifestData.manifest.params.management_fee_pct = parseFloat($event.target.value) || null"
                    class="input text-xs w-full" placeholder="ex: 0.75" />
                </div>
                <div>
                  <label class="text-slate-500 block mb-0.5">Frais perf. (% HWM)</label>
                  <input type="number" step="0.1" min="0" max="30"
                    :value="manifestData.manifest?.params?.perf_fee_pct || ''"
                    @input="manifestData.manifest.params.perf_fee_pct = parseFloat($event.target.value) || null"
                    class="input text-xs w-full" placeholder="ex: 10" />
                </div>
                <div>
                  <label class="text-slate-500 block mb-0.5">Coût transac. (%)</label>
                  <input type="number" step="0.01" min="0" max="2"
                    :value="manifestData.manifest?.params?.txn_cost_pct || ''"
                    @input="manifestData.manifest.params.txn_cost_pct = parseFloat($event.target.value) || null"
                    class="input text-xs w-full" placeholder="ex: 0.10" />
                </div>
              </div>
              <div class="text-[10px] text-slate-600 leading-relaxed">
                Frais de performance : prélevés quotidiennement sur chaque nouveau plus-haut historique de la NAV (High Water Mark), pas annuellement. Coût de transaction : % du notionnel à chaque rebalancement (achat/vente carnet).
              </div>

              <!-- FIFO mode selector -->
              <div>
                <label class="text-slate-500 block mb-1.5">Mode reconstruction FIFO</label>
                <div class="flex flex-col gap-1.5">
                  <label class="flex items-start gap-2 cursor-pointer group">
                    <input type="radio" name="recon_mode"
                      value="strict"
                      :checked="(manifestData.manifest?.params?.recon_mode ?? 't0_synthetic') === 'strict'"
                      @change="manifestData.manifest.params.recon_mode = 'strict'"
                      class="mt-0.5 shrink-0" />
                    <div>
                      <div class="text-slate-300 font-medium">Strict</div>
                      <div class="text-[10px] text-slate-600 leading-relaxed">
                        P&amp;L = 0 pour les ventes sans lot connu. Auditoriable, 100% issu du carnet réel.
                      </div>
                    </div>
                  </label>
                  <label class="flex items-start gap-2 cursor-pointer group">
                    <input type="radio" name="recon_mode"
                      value="t0_synthetic"
                      :checked="(manifestData.manifest?.params?.recon_mode ?? 't0_synthetic') === 't0_synthetic'"
                      @change="manifestData.manifest.params.recon_mode = 't0_synthetic'"
                      class="mt-0.5 shrink-0" />
                    <div>
                      <div class="text-slate-300 font-medium">Reconstitution T0 <span class="text-emerald-400 font-normal">(défaut)</span> <span class="text-amber-400 font-normal">estimé</span></div>
                      <div class="text-[10px] text-slate-600 leading-relaxed">
                        BUY synthétiques injectés à la date de 1ère NAV au prix yfinance. Plus précis, mais estimé — usage analyse interne.
                      </div>
                    </div>
                  </label>
                </div>
                <div v-if="(manifestData.manifest?.params?.recon_mode ?? 't0_synthetic') === 't0_synthetic'"
                  class="mt-2 px-2 py-1.5 bg-amber-950/40 border border-amber-800/60 rounded text-[10px] text-amber-300 leading-relaxed">
                  ⚠ Les entrées synthétiques sont estimées (yfinance close price à T0). Non auditoriables par le gérant. Les round-trips concernés sont flaggés <code class="font-mono">synthetic_entry=true</code> dans les données.
                </div>
              </div>

              <div class="flex gap-3 flex-wrap">
                <label class="text-slate-500 text-[10px] mt-0.5">Blocs :</label>
                <label v-for="bl in ['A_factor','B_attribution','C_trading','D_behaviour','F_replicability','K_marketshocks']" :key="bl"
                  class="flex items-center gap-1 cursor-pointer text-[10px] text-slate-400">
                  <input type="checkbox"
                    :checked="manifestData.manifest?.blocks?.[bl]"
                    @change="manifestData.manifest.blocks[bl] = $event.target.checked" />
                  {{ bl.split('_')[0] }}
                </label>
              </div>

              <!-- Positions Term Sheet -->
              <div class="border-t border-slate-800 pt-2 mt-1">
                <div class="flex items-center gap-2 mb-1.5">
                  <span class="text-emerald-400 text-[10px] font-bold uppercase tracking-wider">Positions TS</span>
                  <span v-if="manifestData.manifest?.params?.termsheet_positions?.length"
                    class="text-[9px] px-1.5 py-0.5 rounded bg-emerald-950/50 border border-emerald-800/50 text-emerald-500">
                    {{ manifestData.manifest.params.termsheet_positions.length }} lignes ·
                    {{ formatPercent(manifestData.manifest.params.termsheet_positions.reduce((s,p) => s+(p.weight_pct||0), 0), 1) }}
                  </span>
                  <span v-else class="text-[9px] text-amber-500">⚠ non configuré</span>
                  <button class="ml-auto text-[9px] text-slate-500 hover:text-slate-300 underline"
                    @click="openTsEditor">
                    {{ showTsEditor ? 'Fermer' : 'Éditer' }}
                  </button>
                </div>

                <div v-if="showTsEditor" class="flex flex-col gap-2">
                  <div class="text-[9px] text-slate-500 leading-relaxed">
                    JSON array — chaque objet : <code class="font-mono">{"isin","name","weight_pct","qty_per_cert","fixing_price","ccy"}</code>.
                    Sauvegarder comme <code class="font-mono">termsheet_positions.json</code> dans le dossier ISIN pour auto-chargement.
                  </div>
                  <textarea rows="8"
                    class="w-full bg-slate-900 border border-slate-700 rounded p-1.5 text-[9px] font-mono text-slate-300 resize-y focus:outline-none focus:border-emerald-700"
                    :value="tsEditorJson"
                    @input="tsEditorJson = $event.target.value"
                    placeholder='[{"isin":"US0404131064","name":"Arista Networks","weight_pct":5.0,"qty_per_cert":2389,"fixing_price":297.6641,"ccy":"USD"}]'>
                  </textarea>
                  <div v-if="tsEditorError" class="text-[9px] text-red-400">⚠ {{ tsEditorError }}</div>
                  <div class="flex gap-2">
                    <button class="flex-1 text-[10px] py-1 rounded bg-emerald-900/40 border border-emerald-800/60 text-emerald-400 hover:bg-emerald-900/60"
                      @click="applyTsPositions">Appliquer</button>
                    <button class="flex-1 text-[10px] py-1 rounded bg-slate-800 border border-slate-700 text-slate-400 hover:text-slate-300"
                      @click="exportTsJson">Exporter JSON</button>
                  </div>
                </div>
              </div>
            </div>

            <button class="btn-primary text-xs py-2.5 flex items-center justify-center gap-2 w-full mt-1"
              :disabled="studyLoading || studyConfig.selected_factors.length === 0"
              @click="runStudy">
              <span v-if="studyLoading" class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
              {{ studyLoading ? 'Étude en cours…' : '▶ Lancer l\'étude complète' }}
            </button>
          </div>

          <div v-if="studyError" class="text-red-400 text-xs p-2 bg-red-950/30 rounded border border-red-900 mt-2">
            ⚠ {{ studyError }}
          </div>

          <div v-if="studyResult" class="flex flex-col gap-1.5 mt-2">
            <label class="flex items-center gap-2 text-[11px] text-slate-400 cursor-pointer select-none px-0.5">
              <input type="checkbox" v-model="includeBrinsonInPdf" class="w-3.5 h-3.5 accent-blue-500" />
              Inclure Brinson dans le PDF
            </label>
            <label class="flex items-center gap-2 text-[11px] text-slate-400 cursor-pointer select-none px-0.5">
              <input type="checkbox" v-model="includeMarketShocksInPdf" class="w-3.5 h-3.5 accent-blue-500" />
              Inclure Chocs de Marché (K) dans le PDF
            </label>
            <button
              class="w-full text-xs py-2 rounded-lg border border-slate-600 text-slate-300 hover:border-blue-500 hover:text-blue-300 flex items-center justify-center gap-2 transition-colors"
              :disabled="studyPdfLoading || studyPdfSimpleLoading"
              @click="exportStudyPdf(true)">
              <span v-if="studyPdfLoading" class="w-3.5 h-3.5 border-2 border-slate-400 border-t-transparent rounded-full animate-spin"></span>
              <span v-else>📄</span>
              {{ studyPdfLoading ? 'Génération…' : 'PDF complet (avec annexes)' }}
            </button>
            <button
              class="w-full text-xs py-2 rounded-lg border border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-300 flex items-center justify-center gap-2 transition-colors"
              :disabled="studyPdfLoading || studyPdfSimpleLoading"
              @click="exportStudyPdf(false)">
              <span v-if="studyPdfSimpleLoading" class="w-3.5 h-3.5 border-2 border-slate-400 border-t-transparent rounded-full animate-spin"></span>
              <span v-else>📋</span>
              {{ studyPdfSimpleLoading ? 'Génération…' : 'PDF simplifié (sans annexes)' }}
            </button>
          </div>
        </div>

        </template><!-- /MODE ÉTUDE -->


      </aside>

      <!-- ── RIGHT: Results ─────────────────────────────────────────── -->
      <section class="flex flex-col overflow-hidden">

        <!-- ══ CLASSIC MODE panel ══ -->
        <template v-if="mainTab === 'classic'">

        <!-- No result yet -->
        <div v-if="!result && !analyzing" class="flex-1 flex items-center justify-center text-center p-10">
          <div class="text-slate-700">
            <div class="text-5xl mb-4">📐</div>
            <div class="text-lg font-bold text-slate-500">Analyse Fama-French AMC</div>
            <div class="text-sm text-slate-600 mt-2 max-w-sm">
              Chargez un fichier diagnostique Excel et configurez les paramètres<br>pour décomposer la performance de l'AMC en facteurs de risque.
            </div>
          </div>
        </div>

        <!-- Loading -->
        <div v-else-if="analyzing" class="flex-1 flex items-center justify-center">
          <div class="text-center">
            <div class="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
            <div class="text-slate-400 text-sm">Téléchargement facteurs FF + benchmark · Régression OLS…</div>
          </div>
        </div>

        <!-- Results -->
        <template v-else-if="result">
          <!-- Warnings -->
          <div v-if="result.warnings?.length" class="mx-5 mt-4 p-3 bg-amber-950/40 border border-amber-800 rounded-lg text-xs text-amber-300">
            <div v-for="w in result.warnings" :key="w">⚠ {{ w }}</div>
          </div>

          <!-- Tabs -->
          <div class="flex border-b border-slate-800 bg-slate-900/50 overflow-x-auto">
            <button v-for="tab in tabs" :key="tab.id"
              class="px-5 py-3 text-xs font-semibold border-b-2 -mb-px whitespace-nowrap transition-colors"
              :class="activeTab === tab.id
                ? 'text-blue-400 border-blue-500'
                : 'text-slate-500 border-transparent hover:text-slate-300'"
              @click="activeTab = tab.id">
              {{ tab.label }}
            </button>
          </div>

          <div class="flex-1 overflow-y-auto p-5">

            <!-- ── TAB: Synthèse ────────────────────────────────── -->
            <div v-if="activeTab === 'synthese'" class="flex flex-col gap-5">

              <!-- Dependency Score -->
              <div class="card">
                <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-1">
                  Score de Dépendance au Gérant
                  <span class="group relative inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700/80 text-slate-400 text-[8px] cursor-help ml-0.5 shrink-0">?<span class="pointer-events-none absolute bottom-full left-0 mb-2 w-64 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2.5 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Score composite 0-100 mesurant dans quelle mesure la performance dépend des décisions du gérant plutôt que de l'exposition aux facteurs de marché. 0 = pur factoriel · 100 = totalement idiosyncratique.</span></span>
                </h3>
                <div class="flex items-center gap-6 mb-4">
                  <!-- Gauge -->
                  <div class="relative w-28 h-28 shrink-0">
                    <svg viewBox="0 0 120 120" class="w-full h-full -rotate-90">
                      <circle cx="60" cy="60" r="50" fill="none" stroke="#1e293b" stroke-width="12"/>
                      <circle cx="60" cy="60" r="50" fill="none"
                        :stroke="scoreColor" stroke-width="12" stroke-linecap="round"
                        :stroke-dasharray="`${dep.total * 3.14} 314`"/>
                    </svg>
                    <div class="absolute inset-0 flex flex-col items-center justify-center">
                      <span class="text-2xl font-black" :class="scoreTextColor">{{ dep.total }}</span>
                      <span class="text-[9px] text-slate-500">/100</span>
                    </div>
                  </div>
                  <div>
                    <div class="text-sm font-bold" :class="scoreTextColor">
                      {{ dep.level === 'high' ? 'Forte dépendance' : dep.level === 'medium' ? 'Dépendance modérée' : 'Faible dépendance' }}
                    </div>
                    <div class="text-xs text-slate-500 mt-1 max-w-xs">{{ dep.interpretation }}</div>
                  </div>
                </div>
                <!-- Score bars -->
                <div class="grid grid-cols-2 gap-3">
                  <div v-for="(comp, key) in dep.components" :key="key" class="bg-slate-800/40 rounded-lg p-3">
                    <div class="flex justify-between text-xs mb-1.5">
                      <span class="text-slate-400 flex items-center gap-1">{{ comp.label }}
                        <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-slate-400 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-0 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ compDesc[key] }}</span></span>
                      </span>
                      <span class="font-bold text-slate-200">{{ comp.score }}pts</span>
                    </div>
                    <div class="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                      <div class="h-full bg-blue-500 rounded-full transition-all"
                        :style="{ width: (comp.score / scoreMax[key] * 100) + '%' }"></div>
                    </div>
                    <div class="text-[10px] text-slate-600 mt-1">{{ fmtCompValue(key, comp.value) }}</div>
                  </div>
                </div>
              </div>

              <!-- Performance: full NAV vs overlap period -->
              <div class="card text-xs">
                <div class="flex items-center gap-2 mb-3">
                  <span class="font-bold text-slate-300 uppercase tracking-wider text-[10px]">Performances</span>
                </div>
                <div class="grid grid-cols-3 gap-0 text-center mb-1">
                  <div></div>
                  <div class="text-[10px] font-bold text-blue-400 pb-1 border-b border-slate-700">Vie entière du fonds</div>
                  <div class="text-[10px] font-bold text-amber-400 pb-1 border-b border-slate-700">Période étudiée (FF)</div>
                </div>
                <div class="text-[10px] text-slate-600 text-center grid grid-cols-3 mb-2">
                  <div></div>
                  <div>{{ formatDate(result.performance.full_nav_start) }} → {{ formatDate(result.performance.full_nav_end) }}</div>
                  <div>{{ formatDate(result.period?.overlap_start) }} → {{ formatDate(result.period?.overlap_end) }}</div>
                </div>
                <div v-for="row in [
                  ['Rendement total', result.performance.full_total_ret_pct, result.performance.total_ret_pct, true, 'NAV_fin / NAV_début − 1. ⚠ La colonne «Vie entière» couvre tout le timeseries, la colonne «Période étudiée» est tronquée à la fin des données Ken French. Un écart important entre les deux indique une forte performance hors fenêtre FF.'],
                  ['Rendement ann.', result.performance.full_ann_ret_pct, result.performance.ann_ret_pct, true, 'Rendement total élevé à une puissance de 252/N pour exprimer un équivalent annuel. Permet de comparer des produits de durées différentes. Sensible aux effets de début/fin de période.'],
                  ['Volatilité ann.', result.performance.full_ann_vol_pct, result.performance.ann_vol_pct, false, 'Écart-type des rendements journaliers × √252. Mesure la dispersion des performances. Élevée = risque de fluctuations importantes. 10-15% = actions normales, >25% = produit très concentré ou levier.'],
                  ['Sharpe', null, result.performance.sharpe, false, '(Rendement ann. − taux sans risque) / Volatilité ann. Mesure le rendement obtenu par unité de risque. >1 = bon, >2 = excellent, <0 = sous-performance nette du taux sans risque. Calculé sur la période de régression uniquement.'],
                  ['Max Drawdown', null, result.performance.max_dd_pct, true, 'Perte maximale depuis un pic (pic-à-creux). Mesure le pire scénario historique pour un investisseur entré au pire moment. -30% = perte de 30% entre le plus haut et le plus bas atteints.'],
                ]" :key="row[0]" class="grid grid-cols-3 gap-0 py-1 border-b border-slate-800/50 items-center">
                  <div class="text-slate-500 flex items-center gap-1">{{ row[0] }}
                    <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-0 mb-1.5 w-64 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ row[4] }}</span></span>
                  </div>
                  <div class="text-center font-mono font-semibold"
                    :class="row[1] != null ? (row[2] !== false && row[1] >= 0 ? 'text-emerald-400' : 'text-red-400') : 'text-slate-600'">
                    {{ row[1] != null ? ((row[1] >= 0 && row[2] !== false ? '+' : '') + formatPercentRaw(row[1])) : '—' }}
                  </div>
                  <div class="text-center font-mono font-semibold"
                    :class="row[2] != null ? (row[2] !== false && row[2] >= 0 ? 'text-emerald-300' : 'text-red-300') : 'text-slate-600'">
                    {{ row[2] != null ? ((row[2] >= 0 && row[2] !== false ? '+' : '') + (row[0]==='Sharpe' ? formatNumber(row[2], 2) : formatPercentRaw(row[2]))) : '—' }}
                  </div>
                </div>
                <div v-if="result.performance.full_total_ret_pct !== result.performance.total_ret_pct"
                  class="mt-2 text-[10px] text-amber-500/80 italic">
                  ⚠ L'écart entre les deux colonnes est dû à la troncature de la période au {{ formatDate(result.period?.overlap_end) }}
                  (fin des données FF disponibles). La vie entière du fonds est la référence correcte pour la performance client.
                </div>
              </div>

              <!-- Regression summary -->
              <div class="card">
                <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Résumé régression FF</h3>
                <div class="grid grid-cols-3 gap-4 text-xs">
                  <div class="text-center">
                    <div class="text-slate-500 flex items-center justify-center gap-1">R²
                      <span class="group relative inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700/80 text-slate-400 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2.5 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Coefficient de détermination : part de la variance du fonds expliquée par les facteurs. R² = 80% → les facteurs expliquent 80% des mouvements. R² faible = forte composante gérant.</span></span>
                    </div>
                    <div class="text-2xl font-black text-blue-400">{{ formatPercent(result.regression.r2 * 100, 1) }}</div>
                    <div class="text-slate-600">Adj. R² = {{ formatPercent(result.regression.adj_r2 * 100, 1) }}</div>
                  </div>
                  <div class="text-center">
                    <div class="text-slate-500 flex items-center justify-center gap-1">Alpha ann.
                      <span class="group relative inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700/80 text-slate-400 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2.5 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Rendement excédentaire annualisé non expliqué par les facteurs (constante de la régression × 252). Représente la création ou destruction de valeur propre du gérant. Statistiquement significatif si p &lt; 0.05.</span></span>
                    </div>
                    <div class="text-2xl font-black" :class="result.regression.alpha_ann_pct >= 0 ? 'text-emerald-400' : 'text-red-400'">
                      {{ result.regression.alpha_ann_pct >= 0 ? '+' : '' }}{{ formatPercent(result.regression.alpha_ann_pct, 2) }}
                    </div>
                    <div class="text-slate-600">t = {{ formatNumber(result.regression.alpha_tstat, 2) }} · p = {{ fmtPVal(result.regression.alpha_pvalue) }}</div>
                    <div class="text-[10px] font-semibold mt-0.5" :class="alphaSignifClass(result.regression.alpha_pvalue)">
                      {{ alphaSignifLabel(result.regression.alpha_pvalue) }}
                    </div>
                  </div>
                  <div class="text-center">
                    <div class="text-slate-500 flex items-center justify-center gap-1">Risque idio.
                      <span class="group relative inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700/80 text-slate-400 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2.5 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Part de la variance (1 − R²) non capturée par les facteurs systématiques. Reflète le risque spécifique lié aux décisions du gérant. Élevé = forte dépendance au gérant, diversification factorielle insuffisante.</span></span>
                    </div>
                    <div class="text-2xl font-black text-amber-400">{{ formatPercent((1 - result.regression.r2) * 100, 1) }}</div>
                    <div class="text-slate-600">de la variance</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- ── TAB: Performance ────────────────────────────── -->
            <div v-if="activeTab === 'performance'" class="flex flex-col gap-5">
              <div class="card">
                <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Performance cumulée</h3>
                <canvas ref="perfChartRef" height="200"></canvas>
                <div class="flex gap-4 mt-3 text-xs">
                  <span class="flex items-center gap-1.5"><span class="w-3 h-0.5 bg-blue-500 inline-block"></span>AMC</span>
                  <span v-if="result.performance.cum_bm?.length" class="flex items-center gap-1.5"><span class="w-3 h-0.5 bg-orange-400 inline-block"></span>{{ result.benchmark }}</span>
                </div>
              </div>
              <div class="card">
                <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Drawdown</h3>
                <canvas ref="ddChartRef" height="120"></canvas>
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div class="card text-center">
                  <div class="text-slate-500 mb-1 flex items-center justify-center gap-1">Rend. ann.
                    <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Rendement annualisé sur la période de régression (FF overlap). ⚠ Période tronquée à la fin des données Ken French — peut différer significativement de la performance totale vie entière.</span></span>
                  </div>
                  <div class="font-bold text-base" :class="result.performance.ann_ret_pct >= 0 ? 'text-emerald-400' : 'text-red-400'">
                    {{ result.performance.ann_ret_pct >= 0 ? '+' : '' }}{{ formatPercentRaw(result.performance.ann_ret_pct) }}
                  </div>
                  <div class="text-[10px] text-slate-600 mt-0.5">{{ formatDate(result.period?.overlap_start) }} → {{ formatDate(result.period?.overlap_end) }}</div>
                </div>
                <div class="card text-center">
                  <div class="text-slate-500 mb-1 flex items-center justify-center gap-1">Tracking Error
                    <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Écart-type annualisé des rendements actifs (AMC − benchmark). Mesure à quel point le fonds s'éloigne de son benchmark. &lt;5% = proche du benchmark (quasi-passif), >15% = très actif.</span></span>
                  </div>
                  <div class="font-bold text-base text-slate-200">{{ result.performance.tracking_err_pct ?? '—' }}{{ result.performance.tracking_err_pct != null ? '%' : '' }}</div>
                </div>
                <div class="card text-center">
                  <div class="text-slate-500 mb-1 flex items-center justify-center gap-1">Info Ratio
                    <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Rendement actif annualisé divisé par la tracking error. Mesure la valeur ajoutée du gérant par unité de risque actif. >0.5 = bon gérant actif, >1 = excellent. Négatif = sous-performance vs benchmark.</span></span>
                  </div>
                  <div class="font-bold text-base text-slate-200">{{ result.performance.info_ratio ?? '—' }}</div>
                </div>
                <div class="card text-center">
                  <div class="text-slate-500 mb-1 flex items-center justify-center gap-1">Obs. alignées
                    <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full right-0 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Nombre de jours où NAV, facteurs FF et benchmark sont disponibles simultanément. Détermine la puissance statistique de la régression. &lt;120 obs. = régression peu fiable.</span></span>
                  </div>
                  <div class="font-bold text-base text-slate-200">{{ result.regression.n_obs }}</div>
                </div>
              </div>
            </div>

            <!-- ── TAB: Facteurs ───────────────────────────────── -->
            <div v-if="activeTab === 'facteurs'" class="flex flex-col gap-5">

              <!-- Regression table -->
              <div class="card">
                <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Coefficients OLS</h3>
                <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                <table class="w-full text-xs border-collapse">
                  <thead>
                    <tr class="border-b border-slate-700 text-slate-500 text-left">
                      <th class="py-2 pr-4 font-medium">Facteur</th>
                      <th class="py-2 px-3 font-medium text-right" title="Sensibilité du fonds au facteur. Beta = 1 → le fonds évolue point pour point avec le facteur. Beta > 1 = surexposition, < 0 = exposition inverse.">Beta</th>
                      <th class="py-2 px-3 font-medium text-right" title="Intervalle de confiance à 95% du beta. Si l'intervalle ne contient pas 0, le beta est statistiquement significatif. Les bornes inf et sup délimitent la fourchette probable du beta réel.">IC 95% inf</th>
                      <th class="py-2 px-3 font-medium text-right text-slate-600 text-[10px]">sup</th>
                      <th class="py-2 px-3 font-medium text-right" title="Statistique de Student : beta divisé par son erreur standard. |t| > 2 indique généralement une significativité à 5%. Plus |t| est grand, plus le beta est fiable.">t-stat</th>
                      <th class="py-2 px-3 font-medium text-right" title="Probabilité d'obtenir un beta aussi extrême si le vrai beta était zéro. p < 0.05 = significatif à 5%. p < 0.10 = limite. p ≥ 0.10 = non significatif.">p-value</th>
                      <th class="py-2 px-3 font-medium text-center" title="Codes de significativité : *** p<0.001 · ** p<0.01 · * p<0.05 · · p<0.10 (limite) · n.s. non significatif">Signif.</th>
                      <th class="py-2 pl-3 font-medium">Exposition</th>
                    </tr>
                  </thead>
                  <tbody>
                    <!-- Alpha row -->
                    <tr class="border-b border-slate-800/60 hover:bg-slate-800/20">
                      <td class="py-3 pr-4 font-semibold text-amber-400">Alpha (ann.)</td>
                      <td class="py-3 px-3 font-mono text-right font-bold"
                        :class="result.regression.alpha_ann_pct >= 0 ? 'text-emerald-400' : 'text-red-400'">
                        {{ result.regression.alpha_ann_pct >= 0 ? '+' : '' }}{{ formatPercentRaw(result.regression.alpha_ann_pct) }}
                      </td>
                      <td class="py-3 px-3 font-mono text-right text-slate-500">{{ formatPercentRaw(result.regression.alpha_ci_low) }}</td>
                      <td class="py-3 px-3 font-mono text-right text-slate-500">{{ formatPercentRaw(result.regression.alpha_ci_high) }}</td>
                      <td class="py-3 px-3 font-mono text-right text-slate-300">{{ result.regression.alpha_tstat }}</td>
                      <td class="py-3 px-3 font-mono text-right" :class="pvalClass(result.regression.alpha_pvalue)">{{ fmtPVal(result.regression.alpha_pvalue) }}</td>
                      <td class="py-3 px-3 text-center font-bold" :class="pvalClass(result.regression.alpha_pvalue)">{{ sigStars(result.regression.alpha_pvalue) }}</td>
                      <td class="py-3 pl-3"></td>
                    </tr>
                    <!-- Factor rows -->
                    <tr v-for="f in result.regression.factors" :key="f.name"
                      class="border-b border-slate-800/60 hover:bg-slate-800/20">
                      <td class="py-3 pr-4 font-semibold text-slate-200">{{ f.name }}</td>
                      <td class="py-3 px-3 font-mono text-right font-bold text-slate-100">{{ f.beta }}</td>
                      <td class="py-3 px-3 font-mono text-right text-slate-500">{{ f.ci_low }}</td>
                      <td class="py-3 px-3 font-mono text-right text-slate-500">{{ f.ci_high }}</td>
                      <td class="py-3 px-3 font-mono text-right text-slate-300">{{ f.tstat }}</td>
                      <td class="py-3 px-3 font-mono text-right" :class="pvalClass(f.pvalue)">{{ fmtPVal(f.pvalue) }}</td>
                      <td class="py-3 px-3 text-center font-bold" :class="pvalClass(f.pvalue)">{{ sigStars(f.pvalue) }}</td>
                      <td class="py-3 pl-3 w-28">
                        <div class="h-1.5 bg-slate-700 rounded overflow-hidden">
                          <div class="h-full rounded transition-all"
                            :class="f.beta >= 0 ? 'bg-blue-500' : 'bg-orange-500'"
                            :style="{ width: Math.min(Math.abs(f.beta) / 1.5 * 100, 100) + '%', marginLeft: f.beta < 0 ? 'auto' : '0' }">
                          </div>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
                </div>
                <div class="mt-3 pt-3 border-t border-slate-800 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500 items-center">
                  <span class="inline-flex items-center gap-1">R² = <strong class="text-slate-300">{{ formatPercent(result.regression.r2 * 100, 2) }}</strong>
                    <span class="text-slate-600 text-[10px]">(variance expliquée)</span></span>
                  <span>Adj. R² = <strong class="text-slate-300">{{ formatPercent(result.regression.adj_r2 * 100, 2) }}</strong></span>
                  <span class="inline-flex items-center gap-1">N = <strong class="text-slate-300">{{ formatInt(result.regression.n_obs) }}</strong>
                    <span class="text-slate-600 text-[10px]">(observations)</span></span>
                  <span class="inline-flex items-center gap-1">Durbin-Watson = <strong class="text-slate-300">{{ formatNumber(result.regression.dw, 2) }}</strong>
                    <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Test d'autocorrélation des résidus. Valeur ≈ 2 = pas d'autocorrélation (idéal). &lt; 1.5 ou &gt; 2.5 signale une autocorrélation pouvant biaiser les erreurs standard et donc les p-values.</span></span>
                  </span>
                </div>
                <!-- Significance legend -->
                <div class="mt-2 pt-2 border-t border-slate-800/60 text-[10px] text-slate-500 flex flex-wrap gap-x-4 gap-y-1 items-center">
                  <span class="font-semibold text-slate-400">Codes de significativité :</span>
                  <span><span class="text-emerald-400 font-bold">***</span> p&lt;0.001</span>
                  <span><span class="text-emerald-400 font-bold">**</span> p&lt;0.01</span>
                  <span><span class="text-emerald-400 font-bold">*</span> p&lt;0.05</span>
                  <span><span class="text-amber-400 font-bold">·</span> p&lt;0.10 (limite)</span>
                  <span><span class="text-red-400 font-bold">n.s.</span> non significatif</span>
                </div>
              </div>

              <!-- Rolling betas chart -->
              <div v-if="result.rolling?.length > 5" class="card">
                <div class="flex items-center justify-between mb-3">
                  <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Betas glissants ({{ config.rolling_window }}j)</h3>
                  <div class="flex gap-2">
                    <button v-for="f in result.factors_used" :key="f"
                      class="text-[10px] px-2 py-0.5 rounded-full border transition-colors"
                      :class="rollingVisible.includes(f)
                        ? 'border-blue-500 text-blue-300 bg-blue-950/40'
                        : 'border-slate-700 text-slate-600'"
                      @click="toggleRolling(f)">{{ f }}</button>
                  </div>
                </div>
                <canvas ref="rollingChartRef" height="180"></canvas>
              </div>

              <!-- Rolling R² chart -->
              <div v-if="result.rolling?.length > 5" class="card">
                <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">R² glissant</h3>
                <canvas ref="r2ChartRef" height="100"></canvas>
                <p class="text-[10px] text-slate-600 mt-2">
                  Un R² élevé indique que les facteurs expliquent bien la performance (gestion factorielle). Un R² faible signale une forte composante idiosyncratique (gestion active / dépendance gérant).
                </p>
              </div>
            </div>

            <!-- ── TAB: Activité ───────────────────────────────── -->
            <div v-if="activeTab === 'activite'" class="flex flex-col gap-5">
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div class="card text-center">
                  <div class="text-slate-500 mb-1 flex items-center justify-center gap-1">Total trades
                    <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Nombre total de lignes d'ordres exécutés (achats + ventes) sur toute la vie du produit. Un ordre partiellement exécuté compte comme 1 ligne.</span></span>
                  </div>
                  <div class="text-xl font-black text-slate-200">{{ act.total_trades }}</div>
                </div>
                <div class="card text-center">
                  <div class="text-slate-500 mb-1 flex items-center justify-center gap-1">Jours actifs
                    <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-52 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Nombre de jours calendaires distincts où au moins un ordre a été passé. Indicateur de la fréquence d'intervention du gérant.</span></span>
                  </div>
                  <div class="text-xl font-black text-slate-200">{{ act.trading_days }}</div>
                </div>
                <div class="card text-center">
                  <div class="text-slate-500 mb-1 flex items-center justify-center gap-1">Titres tradés
                    <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-52 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Nombre de sous-jacents distincts ayant fait l'objet d'au moins un ordre. À comparer au nombre de sous-jacents en portefeuille pour mesurer l'activité de rotation.</span></span>
                  </div>
                  <div class="text-xl font-black text-slate-200">{{ act.unique_securities }}</div>
                </div>
                <div class="card text-center">
                  <div class="text-slate-500 mb-1 flex items-center justify-center gap-1">Turnover cumulé
                    <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full right-0 mb-1.5 w-64 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Notionnel brut total échangé (achats + ventes) divisé par l'AUM moyen estimé. Exprimé en % cumulé depuis le lancement. 200% = l'équivalent du portefeuille a été rebalancé 2× depuis le début. ⚠ Peut être biaisé si l'AUM estimé est imprécis (outstanding_quantity manquant).</span></span>
                  </div>
                  <div class="text-xl font-black"
                    :class="act.turnover_rate > 1 ? 'text-amber-400' : 'text-slate-200'">
                    {{ formatPercent(act.turnover_rate * 100, 1) }}
                  </div>
                  <div class="text-slate-600 text-[10px]">depuis lancement</div>
                </div>
              </div>

              <!-- Notional summary -->
              <div class="card">
                <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Flux notionnels</h3>
                <div class="grid grid-cols-3 gap-4 text-xs text-center">
                  <div class="bg-emerald-950/30 rounded-lg p-3">
                    <div class="text-slate-500 mb-1 flex items-center justify-center gap-1">Achats
                      <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-52 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Somme des notionnels absolus des ordres d'achat (BUY), dans la devise du produit (CHF/USD selon disponibilité).</span></span>
                    </div>
                    <div class="font-bold text-emerald-400">{{ fmtUSD(act.buy_notional) }}</div>
                  </div>
                  <div class="bg-red-950/30 rounded-lg p-3">
                    <div class="text-slate-500 mb-1 flex items-center justify-center gap-1">Ventes
                      <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-52 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Somme des notionnels absolus des ordres de vente (SELL). Un déséquilibre achats/ventes peut indiquer des souscriptions nettes ou des rachats partiels dans la période.</span></span>
                    </div>
                    <div class="font-bold text-red-400">{{ fmtUSD(act.sell_notional) }}</div>
                  </div>
                  <div class="bg-slate-800/40 rounded-lg p-3">
                    <div class="text-slate-500 mb-1 flex items-center justify-center gap-1">Gross traded
                      <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full right-0 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Total des notionnels achats + ventes. Numérateur du turnover. Divisé par l'AUM moyen estimé pour obtenir le taux de rotation brut.</span></span>
                    </div>
                    <div class="font-bold text-slate-200">{{ fmtUSD(act.gross_traded) }}</div>
                  </div>
                </div>
              </div>

              <!-- Monthly activity -->
              <div v-if="Object.keys(act.monthly || {}).length" class="card">
                <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Activité mensuelle</h3>
                <div class="space-y-2">
                  <div v-for="(m, month) in act.monthly" :key="month"
                    class="flex items-center gap-3 text-xs">
                    <span class="text-slate-500 w-16 shrink-0">{{ month }}</span>
                    <div class="flex-1 h-4 bg-slate-800 rounded overflow-hidden">
                      <div class="h-full bg-blue-600 rounded"
                        :style="{ width: (m.trades / maxMonthlyTrades * 100) + '%' }"></div>
                    </div>
                    <span class="text-slate-300 w-12 text-right">{{ m.trades }} tx</span>
                    <span class="text-slate-500 w-24 text-right">{{ fmtUSD(m.notional) }}</span>
                  </div>
                </div>
              </div>

              <!-- Composition -->
              <div v-if="result.concentration?.top_holdings?.length" class="card">
                <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2 flex-wrap">
                  Composition actuelle
                  <span class="flex items-center gap-1">· HHI = {{ formatNumber(result.concentration.hhi, 3) }}
                    <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-0 mb-1.5 w-64 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Indice Herfindahl-Hirschman (somme des carrés des poids). Mesure la concentration du portefeuille. 0 = diversification parfaite, 1 = une seule ligne. HHI &gt; 0.15 = portefeuille concentré. HHI &gt; 0.25 = très concentré (risque de ligne directrice).</span></span>
                  </span>
                  <span class="flex items-center gap-1">· Top-5 = {{ formatPercent(result.concentration.top5_weight * 100, 1) }}
                    <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-0 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Poids cumulé des 5 premières positions. Un portefeuille concentré a souvent Top-5 &gt; 50-60%. Indicateur de risque de concentration réglementaire (UCITS 5/10/40 rule).</span></span>
                  </span>
                </h3>
                <div class="space-y-1.5">
                  <div v-for="h in result.concentration.top_holdings" :key="h.name"
                    class="flex items-center gap-3 text-xs">
                    <span class="text-slate-400 truncate w-48 shrink-0">{{ h.name }}</span>
                    <div class="flex-1 h-2 bg-slate-800 rounded overflow-hidden">
                      <div class="h-full bg-blue-500 rounded"
                        :style="{ width: (h.weight * 100 / result.concentration.top_holdings[0].weight) + '%' }"></div>
                    </div>
                    <span class="text-slate-300 w-10 text-right">{{ formatPercent(h.weight * 100, 1) }}</span>
                  </div>
                </div>
              </div>

              <!-- Exposures -->
              <div v-if="result.concentration?.sectors?.length" class="grid grid-cols-3 gap-3">
                <div class="card">
                  <h4 class="text-xs font-bold text-slate-500 mb-2">Secteurs</h4>
                  <div v-for="s in result.concentration.sectors" :key="s.name" class="flex justify-between text-xs py-0.5">
                    <span class="text-slate-400 truncate">{{ s.name }}</span>
                    <span class="text-slate-300 ml-2">{{ formatPercent(s.weight * 100, 1) }}</span>
                  </div>
                </div>
                <div class="card">
                  <h4 class="text-xs font-bold text-slate-500 mb-2">Pays</h4>
                  <div v-for="c in result.concentration.countries" :key="c.name" class="flex justify-between text-xs py-0.5">
                    <span class="text-slate-400">{{ c.name }}</span>
                    <span class="text-slate-300">{{ formatPercent(c.weight * 100, 1) }}</span>
                  </div>
                </div>
                <div class="card">
                  <h4 class="text-xs font-bold text-slate-500 mb-2">Devises</h4>
                  <div v-for="c in result.concentration.currencies" :key="c.name" class="flex justify-between text-xs py-0.5">
                    <span class="text-slate-400">{{ c.name }}</span>
                    <span class="text-slate-300">{{ formatPercent(c.weight * 100, 1) }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- ── TAB: Données utilisées ──────────────────────── -->
            <div v-if="activeTab === 'donnees'" class="flex flex-col gap-5">
              <div class="card">
                <div class="flex items-center justify-between mb-3">
                  <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Données de régression</h3>
                  <div class="text-[10px] text-slate-500">
                    {{ result.data_used?.length || 0 }} observations ·
                    {{ formatDate(result.period?.overlap_start) }} → {{ formatDate(result.period?.overlap_end) }}
                  </div>
                </div>
                <div class="text-[10px] text-slate-500 mb-3">
                  Toutes les valeurs sont des rendements journaliers en décimales (ex: 0.01 = +1%).
                  <strong class="text-slate-400">amc_ret</strong> = rendement journalier de l'AMC ·
                  <strong class="text-slate-400">RF</strong> = taux sans risque ·
                  <strong class="text-slate-400">bm_ret</strong> = rendement benchmark (si disponible)
                </div>
                <div class="overflow-auto max-h-[500px] rounded border border-slate-800 table-shell" tabindex="0" role="region">
                  <table class="w-full text-[10px] border-collapse">
                    <thead class="sticky top-0 bg-slate-900 z-10">
                      <tr>
                        <th v-for="col in dataUsedCols" :key="col"
                          class="px-3 py-2 text-right text-slate-500 font-bold border-b border-slate-700 whitespace-nowrap first:text-left">
                          {{ col }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, i) in result.data_used" :key="i"
                        class="border-b border-slate-800/40 hover:bg-slate-800/20">
                        <td v-for="col in dataUsedCols" :key="col"
                          class="px-3 py-1.5 font-mono text-right first:text-left"
                          :class="col === 'date' ? 'text-slate-400' :
                                  col === 'amc_ret' ? (row[col] >= 0 ? 'text-emerald-400' : 'text-red-400') :
                                  'text-slate-300'">
                          {{ col === 'date' ? formatDate(row[col]) : (row[col] != null ? formatPercent(row[col] * 100, 4) : '—') }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <!-- Summary stats on the data -->
              <div class="card text-xs">
                <h3 class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Statistiques descriptives (période étudiée)</h3>
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                  <div class="bg-slate-800/40 rounded-lg p-3">
                    <div class="text-slate-500 mb-1">Rendement moy. / jour</div>
                    <div class="font-mono font-bold text-slate-200">
                      {{ result.data_used?.length ? formatPercent((result.data_used.reduce((s,r)=>s+(r.amc_ret||0),0)/result.data_used.length)*100, 4) : '—' }}
                    </div>
                  </div>
                  <div class="bg-slate-800/40 rounded-lg p-3">
                    <div class="text-slate-500 mb-1">Jours positifs</div>
                    <div class="font-mono font-bold text-emerald-400">
                      {{ result.data_used?.length ? formatPercent(result.data_used.filter(r=>r.amc_ret>0).length/result.data_used.length*100, 0) : '—' }}
                    </div>
                  </div>
                  <div class="bg-slate-800/40 rounded-lg p-3">
                    <div class="text-slate-500 mb-1">Meilleur jour</div>
                    <div class="font-mono font-bold text-emerald-400">
                      {{ result.data_used?.length ? '+' + formatPercent(Math.max(...result.data_used.map(r=>r.amc_ret||0))*100, 2) : '—' }}
                    </div>
                  </div>
                  <div class="bg-slate-800/40 rounded-lg p-3">
                    <div class="text-slate-500 mb-1">Pire jour</div>
                    <div class="font-mono font-bold text-red-400">
                      {{ result.data_used?.length ? formatPercent(Math.min(...result.data_used.map(r=>r.amc_ret||0))*100, 2) : '—' }}
                    </div>
                  </div>
                </div>
              </div>
            </div>

          </div><!-- /tab content -->
        </template><!-- /results -->

        </template><!-- /CLASSIC MODE panel -->

        <!-- ══ STUDY MODE panel ══ -->
        <template v-if="mainTab === 'study'">

        <!-- Study: no result yet -->
        <div v-if="!studyResult && !studyLoading" class="flex-1 flex items-center justify-center text-center p-10">
          <div class="text-slate-700">
            <div class="text-5xl mb-4">🔬</div>
            <div class="text-lg font-bold text-slate-500">Étude complète AMC</div>
            <div class="text-sm text-slate-600 mt-2 max-w-sm">
              Configurez la série FF, le benchmark et les blocs à gauche,<br>
              puis scannez un dossier ISIN et lancez l'étude.
            </div>
          </div>
        </div>

        <!-- Study: loading -->
        <div v-else-if="studyLoading" class="flex-1 flex items-center justify-center">
          <div class="text-center">
            <div class="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
            <div class="text-slate-400 text-sm">Reconstruction FIFO · Régression OLS · Blocs B/C/D…</div>
          </div>
        </div>

        <!-- Study: results -->
        <template v-if="studyResult">
          <div class="flex flex-col flex-1 overflow-hidden">
            <!-- Study tabs -->
            <div class="flex gap-0.5 px-5 pt-3 border-b border-slate-800 bg-slate-950/80 flex-wrap">
              <button v-for="tab in studyTabs" :key="tab.id"
                class="px-3 py-2 text-xs rounded-t-md transition-colors font-medium"
                :class="activeStudyTab === tab.id
                  ? 'bg-blue-900/40 text-blue-300 border-b-2 border-blue-500'
                  : 'text-slate-500 hover:text-slate-300'"
                @click="activeStudyTab = tab.id">
                {{ tab.label }}
              </button>
            </div>

            <div class="flex-1 overflow-y-auto p-5">

              <!-- ── MÉTHODOLOGIE & BUT (en tête de chaque bloc analytique) ── -->
              <div v-if="activeStudyTab !== 'synthese' && activeStudyTab !== 'payload_ai' && activeStudyTab !== 'meta'"
                class="mb-5 rounded-lg border border-blue-900/60 bg-blue-950/20 overflow-hidden">
                <button @click="showMethodology = !showMethodology"
                  class="w-full flex items-center justify-between px-4 py-2.5 text-xs group hover:bg-blue-900/20 transition-colors">
                  <span class="flex items-center gap-2">
                    <span class="text-blue-400 font-bold text-sm leading-none">ℹ</span>
                    <span class="font-semibold text-blue-300">Méthodologie &amp; But</span>
                    <span class="text-[10px] text-blue-500/70">— {{ currentMethodology?.label }}</span>
                  </span>
                  <span class="text-blue-600 group-hover:text-blue-400 transition-colors text-[10px]">
                    {{ showMethodology ? '▲ réduire' : '▼ voir' }}
                  </span>
                </button>
                <div v-if="showMethodology" class="px-4 pb-4 grid grid-cols-1 gap-2.5 border-t border-slate-800/60 pt-3">
                  <div class="bg-blue-950/25 border border-blue-900/30 rounded-lg p-3">
                    <div class="text-[9px] font-bold text-blue-500 uppercase tracking-widest mb-1.5">But</div>
                    <div class="text-xs text-slate-300 leading-relaxed">{{ currentMethodology?.but }}</div>
                  </div>
                  <div class="bg-slate-800/30 border border-slate-700/40 rounded-lg p-3">
                    <div class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Méthode</div>
                    <div class="text-xs text-slate-400 leading-relaxed">{{ currentMethodology?.methode }}</div>
                  </div>
                  <div class="grid grid-cols-2 gap-2.5">
                    <div class="bg-amber-950/15 border border-amber-900/25 rounded-lg p-3">
                      <div class="text-[9px] font-bold text-amber-700 uppercase tracking-widest mb-1.5">Limites</div>
                      <div class="text-xs text-slate-500 leading-relaxed">{{ currentMethodology?.limites }}</div>
                    </div>
                    <div class="bg-slate-800/20 border border-slate-700/30 rounded-lg p-3">
                      <div class="text-[9px] font-bold text-slate-600 uppercase tracking-widest mb-1.5">Sources</div>
                      <div class="text-xs text-slate-600 leading-relaxed">{{ currentMethodology?.sources }}</div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- SYNTHÈSE -->
              <div v-if="activeStudyTab === 'synthese'" class="flex flex-col gap-5">
                <div class="card flex flex-col gap-4">
                  <div>
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Synthèse</div>
                    <div class="text-xs text-slate-600">Texte libre — apparaîtra en tête du rapport PDF, avant les tableaux de données.</div>
                  </div>
                  <textarea v-model="syntheseText" rows="18"
                    placeholder="Rédigez ici votre synthèse sur la gestion, le positionnement, les points clés de l'analyse…"
                    class="w-full bg-slate-900 border border-slate-700 rounded-lg p-4 text-sm text-slate-200 placeholder-slate-600 resize-y focus:outline-none focus:border-blue-500 leading-relaxed font-sans"></textarea>
                  <div class="flex items-center gap-3">
                    <input v-model="saveLabel" type="text" placeholder="Nom de la sauvegarde (optionnel)"
                      class="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500" />
                    <button @click="saveStudy" :disabled="saveLoading"
                      class="py-2 px-4 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-lg transition-colors flex items-center justify-center gap-2 shrink-0">
                      <span v-if="saveLoading" class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                      <span v-else>💾</span>
                      {{ saveLoading ? 'Sauvegarde…' : "Sauvegarder l'étude" }}
                    </button>
                  </div>
                  <div v-if="saveError" class="text-[10px] text-red-400">{{ saveError }}</div>
                  <div class="text-[10px] text-slate-600 border-t border-slate-800 pt-3">
                    Chaque sauvegarde crée une nouvelle entrée (historique conservé). Retrouvez-les dans "Études sauvegardées" en haut du panneau gauche, ou depuis l'accueil.
                  </div>
                </div>

                <!-- ── Génération IA ───────────────────────────────── -->
                <div class="card flex flex-col gap-4">
                  <div class="flex items-center justify-between">
                    <div>
                      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-0.5 flex items-center gap-1">
                        Générer avec l'IA
                        <span class="group relative inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700/80 text-slate-400 text-[8px] cursor-help ml-0.5 shrink-0">?<span class="pointer-events-none absolute top-full left-0 mt-1.5 w-72 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2.5 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Envoie la totalité des données de l'étude (blocs A/B/C/D/H, méta-données, catalogue) à un LLM. Le modèle rédige une synthèse selon le template éditorial défini pour l'audience choisie (committee / investor / due_diligence). La synthèse générée est éditable et peut être intégrée au rapport PDF.</span></span>
                      </div>
                      <div class="text-xs text-slate-600">La totalité des données de l'étude sera envoyée au modèle choisi.</div>
                    </div>
                  </div>

                  <!-- Provider selector -->
                  <div class="flex gap-2">
                    <button v-for="p in [{id:'ollama',label:'Ollama'},{id:'claude',label:'Claude'},{id:'openai',label:'OpenAI'}]"
                      :key="p.id"
                      @click="aiProvider = p.id; aiPersist()"
                      class="px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors"
                      :class="aiProvider === p.id
                        ? 'bg-blue-600 border-blue-500 text-white'
                        : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'">
                      {{ p.label }}
                      <span v-if="p.id !== 'ollama'" class="ml-1 text-[9px] opacity-60">premium</span>
                    </button>
                  </div>

                  <!-- Ollama config -->
                  <div v-if="aiProvider === 'ollama'" class="flex flex-col gap-2">
                    <div class="flex gap-2">
                      <input v-model="aiOllamaUrl" @blur="aiPersist"
                        placeholder="http://localhost:11434"
                        class="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500" />
                      <button @click="fetchOllamaModels"
                        class="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs rounded transition-colors shrink-0">
                        Détecter modèles
                      </button>
                    </div>
                    <div v-if="aiOllamaModelsError" class="text-red-400 text-xs">⚠ {{ aiOllamaModelsError }}</div>
                    <div v-if="aiOllamaModels.length">
                      <select v-model="aiOllamaModel" @change="aiPersist"
                        class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500">
                        <option v-for="m in aiOllamaModels" :key="m" :value="m">{{ m }}</option>
                      </select>
                    </div>
                    <div v-else>
                      <input v-model="aiOllamaModel" @blur="aiPersist"
                        placeholder="ex: llama3.3:70b"
                        class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500" />
                    </div>
                  </div>

                  <!-- Claude config -->
                  <div v-if="aiProvider === 'claude'" class="flex flex-col gap-2">
                    <input v-model="aiClaudeKey" @blur="aiPersist" type="password"
                      placeholder="sk-ant-api03-…"
                      class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500" />
                    <select v-model="aiClaudeModel" @change="aiPersist"
                      class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500">
                      <option value="claude-sonnet-4-6">claude-sonnet-4-6 (recommandé)</option>
                      <option value="claude-opus-4-8">claude-opus-4-8</option>
                      <option value="claude-haiku-4-5-20251001">claude-haiku-4-5 (rapide)</option>
                    </select>
                  </div>

                  <!-- OpenAI config -->
                  <div v-if="aiProvider === 'openai'" class="flex flex-col gap-2">
                    <input v-model="aiOpenAiKey" @blur="aiPersist" type="password"
                      placeholder="sk-…"
                      class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500" />
                    <select v-model="aiOpenAiModel" @change="aiPersist"
                      class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500">
                      <option value="gpt-4o">gpt-4o (recommandé)</option>
                      <option value="gpt-4o-mini">gpt-4o-mini (rapide)</option>
                    </select>
                  </div>

                  <!-- Actions -->
                  <div class="flex gap-2">
                    <button @click="generateSynthesisAI"
                      :disabled="aiGenerating || !studyResult"
                      class="flex-1 py-2 px-4 text-xs font-semibold rounded-lg transition-colors flex items-center justify-center gap-2"
                      :class="aiGenerating || !studyResult
                        ? 'bg-slate-700 text-slate-500 cursor-not-allowed'
                        : 'bg-emerald-700 hover:bg-emerald-600 text-white'">
                      <span v-if="aiGenerating" class="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                      {{ aiGenerating ? 'Génération en cours…' : '✨ Générer la synthèse' }}
                    </button>
                    <button @click="activeStudyTab = 'payload_ai'; fetchAIPayload()"
                      :disabled="!studyResult"
                      class="px-3 py-2 text-xs font-semibold rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors disabled:opacity-40">
                      📋 Voir données envoyées
                    </button>
                  </div>

                  <div v-if="aiError" class="text-red-400 text-xs bg-red-950/30 rounded p-2">⚠ {{ aiError }}</div>

                  <!-- Generated text output -->
                  <div v-if="aiGeneratedText" class="flex flex-col gap-2">
                    <div class="text-xs text-slate-500 font-semibold">Texte généré :</div>
                    <div class="bg-slate-900 border border-emerald-800/40 rounded-lg p-4 text-sm text-slate-200 leading-relaxed whitespace-pre-wrap font-sans max-h-80 overflow-y-auto">{{ aiGeneratedText }}</div>
                    <div class="flex gap-2">
                      <button @click="insertGeneratedSynthesis"
                        class="flex-1 py-1.5 px-3 bg-blue-700 hover:bg-blue-600 text-white text-xs font-semibold rounded-lg transition-colors">
                        ↑ Insérer dans la synthèse
                      </button>
                      <button @click="copyAiText(aiGeneratedText)"
                        class="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs rounded-lg transition-colors">
                        Copier
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <!-- DONNÉES IA -->
              <div v-if="activeStudyTab === 'payload_ai'" class="flex flex-col gap-5">
                <div class="card flex flex-col gap-4">
                  <div class="flex items-center justify-between">
                    <div>
                      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-0.5">Données envoyées à l'IA</div>
                      <div class="text-xs text-slate-600">Totalité des données de l'étude mises en forme — copiez pour utiliser dans n'importe quel chat IA.</div>
                    </div>
                    <div class="flex gap-2 shrink-0">
                      <button @click="fetchAIPayload"
                        :disabled="aiPayloadLoading || !studyResult"
                        class="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs rounded transition-colors disabled:opacity-40">
                        {{ aiPayloadLoading ? '…' : '↻ Actualiser' }}
                      </button>
                      <button @click="copyAiText(aiPayloadText)"
                        :disabled="!aiPayloadText"
                        class="px-3 py-1.5 bg-blue-700 hover:bg-blue-600 text-white text-xs font-semibold rounded transition-colors disabled:opacity-40">
                        Copier tout
                      </button>
                    </div>
                  </div>
                  <div v-if="aiPayloadLoading" class="flex items-center gap-2 text-xs text-slate-500">
                    <span class="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin"></span>
                    Chargement…
                  </div>
                  <div v-else-if="!aiPayloadText && studyResult">
                    <button @click="fetchAIPayload"
                      class="w-full py-2 px-4 bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs font-semibold rounded-lg transition-colors">
                      Charger les données
                    </button>
                  </div>
                  <div v-else-if="!studyResult" class="text-slate-600 text-xs">
                    Lancez d'abord une étude pour voir les données.
                  </div>
                  <pre v-else class="bg-slate-900 border border-slate-800 rounded-lg p-4 text-xs text-slate-300 leading-relaxed overflow-auto max-h-[70vh] font-mono whitespace-pre">{{ aiPayloadText }}</pre>
                </div>
              </div>

              <!-- META & BLOCS -->
              <div v-if="activeStudyTab === 'meta'" class="flex flex-col gap-5">

                <!-- Identification -->
                <div class="card">
                  <div class="font-bold text-slate-200 text-sm mb-0.5"><SensitiveValue placeholder="Produit confidentiel">{{ studyResult.meta?.product_name }}</SensitiveValue></div>
                  <div class="text-xs text-slate-500 mb-4">{{ studyResult.meta?.theme || 'Thème non renseigné' }}</div>
                  <div class="grid grid-cols-2 gap-2 text-xs">
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        ISIN
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Code ISIN international identifiant le produit AMC">?</span>
                      </div>
                      <div class="font-mono text-slate-300 tracking-wide"><SensitiveValue placeholder="CH••••••••••">{{ studyResult.meta?.isin }}</SensitiveValue></div>
                    </div>
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        Devise
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Devise de libellé de la NAV. Tous les montants P&L sont dans cette devise sauf mention contraire.">?</span>
                      </div>
                      <div class="font-bold text-slate-200">{{ studyResult.meta?.currency || '—' }}</div>
                    </div>
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        Commission de gestion
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Frais de gestion annuels (% p.a.) issus de la term sheet. Utilisés pour le calcul de la NAV brute dans l'analyse factorielle.">?</span>
                      </div>
                      <div class="font-bold" :class="studyResult.meta?.management_fee_pct != null ? 'text-slate-200' : 'text-amber-400'">
                        {{ studyResult.meta?.management_fee_pct != null ? studyResult.meta.management_fee_pct + '% p.a.' : '⚠ Non renseigné' }}
                      </div>
                    </div>
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        Sous-jacents
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Nombre de lignes dans le snapshot de composition (Def.txt). Représente le nombre d'actifs détenus à la date du snapshot.">?</span>
                      </div>
                      <div class="font-bold text-emerald-400">{{ studyResult.meta?.n_underlyings }}</div>
                    </div>
                  </div>
                </div>

                <!-- NAV -->
                <div class="card">
                  <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Historique NAV (timeseries)</div>
                  <div class="grid grid-cols-3 gap-2 text-xs mb-3">
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        NAV de départ
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Première valeur de NAV disponible dans le fichier timeseries. Base de calcul de la performance totale.">?</span>
                      </div>
                      <div class="font-bold text-slate-200">{{ formatNumber(studyResult.meta?.nav_start_value, 2) }}</div>
                      <div class="text-slate-600 mt-0.5">{{ formatDate(studyResult.meta?.nav_start_date) }}</div>
                    </div>
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        NAV actuelle
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Dernière valeur de NAV dans le timeseries (peut être antérieure au snapshot si le fichier n'est pas à jour).">?</span>
                      </div>
                      <div class="font-bold" :class="(studyResult.meta?.nav_current_value ?? 0) >= (studyResult.meta?.nav_start_value ?? 0) ? 'text-emerald-400' : 'text-red-400'">
                        {{ formatNumber(studyResult.meta?.nav_current_value, 2) }}
                      </div>
                      <div class="text-slate-600 mt-0.5">{{ formatDate(studyResult.meta?.nav_current_date) }}</div>
                    </div>
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        Performance totale
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="(NAV actuelle / NAV de départ − 1) sur l'intégralité du timeseries. ⚠ Diffère du rendement annualisé FF qui est tronqué à la fin des données Ken French. Un écart important entre les deux est normal si le produit a eu de la performance récemment (hors fenêtre FF).">?</span>
                      </div>
                      <div v-if="studyResult.meta?.nav_start_value && studyResult.meta?.nav_current_value" class="font-bold"
                        :class="studyResult.meta.nav_current_value >= studyResult.meta.nav_start_value ? 'text-emerald-400' : 'text-red-400'">
                        {{ formatPercent((studyResult.meta.nav_current_value / studyResult.meta.nav_start_value - 1) * 100, 2) }}
                      </div>
                      <div v-else class="text-slate-600">—</div>
                      <div class="text-[10px] text-slate-600 mt-0.5">vie entière · {{ formatDate(studyResult.meta?.nav_start_date) }} → {{ formatDate(studyResult.meta?.nav_current_date) }}</div>
                    </div>
                  </div>
                  <div class="grid grid-cols-2 gap-2 text-xs">
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        Observations NAV
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Nombre de points de NAV quotidiens disponibles dans le timeseries.">?</span>
                      </div>
                      <div class="font-bold text-blue-400">{{ studyResult.meta?.nav_n_obs ?? '—' }}</div>
                    </div>
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        Ordres analysés
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Nombre total d'ordres dans le(s) fichier(s) JSON du carnet d'ordres, après dédoublonnage.">?</span>
                      </div>
                      <div class="font-bold text-blue-400">{{ studyResult.meta?.n_orders ?? '—' }}</div>
                    </div>
                  </div>
                </div>

                <!-- Snapshot composition -->
                <div class="card">
                  <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Snapshot composition (Def.txt)</div>
                  <div class="grid grid-cols-3 gap-2 text-xs">
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        Date snapshot
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Date de la NAV dans le fichier Def.txt. C'est la date à laquelle les poids et positions sont arrêtés.">?</span>
                      </div>
                      <div class="font-mono text-slate-300">{{ formatDate(studyResult.meta?.nav_snapshot_date) }}</div>
                    </div>
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        NAV snapshot
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Valeur de la NAV par certificat à la date du snapshot (Def.txt). Sert de mark courant pour le calcul du P&L latent (Bloc B).">?</span>
                      </div>
                      <div class="font-bold text-slate-200">{{ studyResult.meta?.nav_snapshot_value ?? '—' }}</div>
                    </div>
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        AUM estimé
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="NAV × certificats en circulation à la date du snapshot. Estimation de l'actif total géré dans le produit.">?</span>
                      </div>
                      <div class="font-bold text-slate-200"><SensitiveValue>{{ studyResult.meta?.total_aum != null ? fmtPnl(studyResult.meta.total_aum, studyResult.meta.currency) : '—' }}</SensitiveValue></div>
                    </div>
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        Certificats en circulation
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Nombre de certificats (outstandingQuantity) du Def.txt. Multiplicateur entre NAV unitaire et AUM total.">?</span>
                      </div>
                      <div class="font-bold text-slate-200"><SensitiveValue>{{ formatInt(studyResult.meta?.outstanding) }}</SensitiveValue></div>
                    </div>
                    <div class="bg-slate-900 rounded p-3 col-span-2">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        Poids sous-jacents
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Les poids sont issus directement du Def.txt (champ 'weight'). Ils représentent la fraction de l'AUM total (= NAV × certificats), donc sont bien relatifs à la NAV. Leur somme est ~1 (100%).">?</span>
                      </div>
                      <div class="text-slate-300">Relatifs à la NAV — fraction de l'AUM (NAV × certificats)</div>
                    </div>
                  </div>
                </div>

                <!-- Configuration analyse -->
                <div class="card">
                  <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Configuration analyse</div>
                  <div class="grid grid-cols-2 gap-2 text-xs">
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        Série Fama-French
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Bibliothèque Ken French utilisée pour les facteurs. 'Developed_5F' couvre les marchés développés (USD) jusqu'à 2026. 'EU_5F' couvre la zone euro.">?</span>
                      </div>
                      <div class="font-mono text-blue-300">{{ studyResult.meta?.ff_series || '—' }}</div>
                    </div>
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        Modèle factoriel
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="FF3 = 3 facteurs (marché, taille, valeur). FF5 = + profitabilité + investissement. FF5+MOM = + momentum (Carhart).">?</span>
                      </div>
                      <div class="font-mono text-blue-300">{{ studyResult.meta?.factor_model || '—' }}</div>
                    </div>
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        Benchmark
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="ETF utilisé comme benchmark sectoriel pour la 2e régression et le calcul de la tracking error et de l'information ratio.">?</span>
                      </div>
                      <div class="font-mono text-blue-300">{{ studyResult.meta?.benchmark_ticker || '—' }}</div>
                    </div>
                    <div class="bg-slate-900 rounded p-3">
                      <div class="flex items-center gap-1 text-slate-500 mb-1">
                        Fenêtre rolling
                        <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700 text-slate-400 text-[9px] cursor-help ml-0.5" title="Nombre de jours de trading utilisé pour la régression glissante. 60j ≈ 3 mois. Une fenêtre plus large lisse les betas mais réduit la réactivité.">?</span>
                      </div>
                      <div class="font-mono text-blue-300">{{ studyResult.meta?.rolling_window ?? '—' }} jours</div>
                    </div>
                  </div>
                </div>

                <!-- Warnings -->
                <div v-if="studyResult.warnings?.length" class="p-3 bg-amber-950/40 border border-amber-800 rounded-lg text-xs text-amber-300">
                  <div v-for="w in studyResult.warnings" :key="w">⚠ {{ w }}</div>
                </div>

                <!-- ── Baskets T0 et actuel ─────────────────────────── -->
                <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">

                  <!-- Basket T0 — Term Sheet -->
                  <div class="card border border-slate-700/50">
                    <div class="flex items-center gap-2 mb-3">
                      <span class="text-emerald-400 text-sm">📋</span>
                      <div class="text-xs font-bold text-slate-300 uppercase tracking-wider">Basket T0 — Term Sheet</div>
                      <span class="ml-auto text-[10px] px-2 py-0.5 rounded bg-emerald-950/40 border border-emerald-800/40 text-emerald-400">
                        {{ formatDate(studyResult.meta?.nav_start_date) }}
                      </span>
                    </div>
                    <div v-if="!studyResult.termsheet_basket?.length" class="text-xs text-slate-500 italic py-4 text-center">
                      Aucune position TS configurée — renseignez <code>termsheet_positions</code> dans le manifest.
                    </div>
                    <div v-else class="overflow-x-auto table-shell" tabindex="0" role="region">
                      <table class="w-full text-[10px]">
                        <thead>
                          <tr class="text-slate-600 border-b border-slate-800">
                            <th class="text-left pb-1.5 pr-2">Titre</th>
                            <th class="text-right pb-1.5 pr-2">Poids TS %</th>
                            <th class="text-right pb-1.5 pr-2">Qté/cert</th>
                            <th class="text-right pb-1.5 pr-2">Prix fixing</th>
                            <th class="text-right pb-1.5">Devise</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="p in studyResult.termsheet_basket" :key="p.isin"
                            class="border-b border-slate-900 hover:bg-slate-800/30">
                            <td class="py-1 pr-2 text-slate-300"><SensitiveValue mode="blur">{{ p.name }}</SensitiveValue></td>
                            <td class="py-1 pr-2 text-right font-mono text-emerald-400">{{ formatPercent(p.weight_pct, 2) }}</td>
                            <td class="py-1 pr-2 text-right font-mono text-slate-400">{{ formatNumber(p.qty_per_cert, 4) }}</td>
                            <td class="py-1 pr-2 text-right font-mono text-slate-300">
                              {{ p.fixing_price > 0 ? formatNumber(p.fixing_price, 3) : '—' }}
                            </td>
                            <td class="py-1 text-right text-slate-500">{{ p.ccy }}</td>
                          </tr>
                        </tbody>
                        <tfoot>
                          <tr class="border-t border-slate-700">
                            <td class="pt-1.5 text-slate-500 text-[10px]">{{ studyResult.termsheet_basket.length }} titres</td>
                            <td class="pt-1.5 text-right font-mono font-bold text-emerald-400">
                              {{ formatPercent(studyResult.termsheet_basket.reduce((s, p) => s + (p.weight_pct || 0), 0), 2) }}
                            </td>
                            <td colspan="3"></td>
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  </div>

                  <!-- Basket actuel — Composition Def.txt -->
                  <div class="card border border-slate-700/50">
                    <div class="flex items-center gap-2 mb-3">
                      <span class="text-blue-400 text-sm">📊</span>
                      <div class="text-xs font-bold text-slate-300 uppercase tracking-wider">Basket actuel — Composition</div>
                      <span class="ml-auto text-[10px] px-2 py-0.5 rounded bg-blue-950/40 border border-blue-800/40 text-blue-400">
                        {{ formatDate(studyResult.meta?.nav_snapshot_date) }}
                      </span>
                    </div>
                    <div v-if="!studyResult.current_basket?.length" class="text-xs text-slate-500 italic py-4 text-center">
                      Composition non disponible.
                    </div>
                    <div v-else class="overflow-x-auto table-shell" tabindex="0" role="region">
                      <table class="w-full text-[10px]">
                        <thead>
                          <tr class="text-slate-600 border-b border-slate-800">
                            <th class="text-left pb-1.5 pr-2">Titre</th>
                            <th class="text-right pb-1.5 pr-2">Poids %</th>
                            <th class="text-right pb-1.5 pr-2">Position</th>
                            <th class="text-right pb-1.5 pr-2">Valeur</th>
                            <th class="text-right pb-1.5">Devise</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="c in [...studyResult.current_basket].sort((a,b) => (b.weight||0)-(a.weight||0))" :key="c.isin"
                            class="border-b border-slate-900 hover:bg-slate-800/30">
                            <td class="py-1 pr-2 text-slate-300"><SensitiveValue mode="blur">{{ c.name }}</SensitiveValue></td>
                            <td class="py-1 pr-2 text-right font-mono text-blue-400">
                              {{ c.weight != null ? formatPercent(c.weight * 100, 2) : '—' }}
                            </td>
                            <td class="py-1 pr-2 text-right font-mono text-slate-400">
                              {{ formatInt(c.position) }}
                            </td>
                            <td class="py-1 pr-2 text-right font-mono text-slate-300">
                              {{ formatInt(c.value_prod) }}
                            </td>
                            <td class="py-1 text-right text-slate-500">{{ c.currency }}</td>
                          </tr>
                        </tbody>
                        <tfoot>
                          <tr class="border-t border-slate-700">
                            <td class="pt-1.5 text-slate-500 text-[10px]">{{ studyResult.current_basket.length }} titres</td>
                            <td class="pt-1.5 text-right font-mono font-bold text-blue-400">
                              {{ formatPercent(studyResult.current_basket.reduce((s,c) => s + (c.weight||0), 0) * 100, 2) }}
                            </td>
                            <td colspan="3"></td>
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  </div>
                </div>

                <!-- Reconstitution synthétique (debug, collapsible) -->
                <details v-if="studyResult.meta?.recon_mode === 't0_synthetic' && studyResult.synthetic_report?.length"
                  class="card border border-amber-900/30">
                  <summary class="cursor-pointer flex items-center gap-2 text-xs text-amber-600 select-none py-0.5">
                    <span>⚗</span>
                    <span class="font-medium">Reconstitution T0 synthétique (debug)</span>
                    <span class="ml-auto text-[10px] px-2 py-0.5 rounded bg-amber-950/60 border border-amber-800/50 text-amber-500">
                      {{ studyResult.synthetic_report.filter(r => r.injected).length }} injectés ·
                      {{ studyResult.synthetic_report.filter(r => !r.injected).length }} échecs
                    </span>
                  </summary>
                  <div class="mt-3 text-[10px] text-slate-500 mb-2">
                    BUY synthétiques injectés à T0 = {{ formatDate(studyResult.meta.nav_start_date) }}. Prix source : yfinance close ou proxy ordre. Non auditoriables — à titre de diagnostic uniquement.
                  </div>
                  <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                    <table class="w-full text-[10px]">
                      <thead>
                        <tr class="text-slate-600 border-b border-slate-800">
                          <th class="text-left pb-1.5 pr-2">Titre</th>
                          <th class="text-right pb-1.5 pr-2">Qté injectée</th>
                          <th class="text-right pb-1.5 pr-2">Prix local T0</th>
                          <th class="text-right pb-1.5 pr-2">FX T0</th>
                          <th class="text-right pb-1.5 pr-2">Prix prod.</th>
                          <th class="text-left pb-1.5">Source</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="r in studyResult.synthetic_report" :key="r.isin"
                          class="border-b border-slate-900"
                          :class="r.injected ? '' : 'opacity-40'">
                          <td class="py-1 pr-2 text-slate-300"><SensitiveValue mode="blur">{{ r.name }}</SensitiveValue></td>
                          <td class="py-1 pr-2 text-right font-mono text-slate-400">{{ r.excess_qty }}</td>
                          <td class="py-1 pr-2 text-right font-mono text-slate-300">
                            {{ formatNumber(r.price_local, 3) }}
                          </td>
                          <td class="py-1 pr-2 text-right font-mono text-slate-500">
                            {{ formatNumber(r.fx, 4) }}
                          </td>
                          <td class="py-1 pr-2 text-right font-mono text-amber-300">
                            {{ formatNumber(r.price_prod, 3) }}
                          </td>
                          <td class="py-1 text-slate-500">
                            <span v-if="!r.injected" class="text-red-500">✗ indisponible</span>
                            <span v-else-if="r.source?.includes('yfinance')" class="text-emerald-500">✓ yfinance</span>
                            <span v-else class="text-amber-500">~ proxy ordre</span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </details>

                <!-- Bloc catalog -->
                <div v-if="studyResult.block_catalog?.length" class="card">
                  <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Blocs exécutés</div>
                  <div v-for="bl in studyResult.block_catalog" :key="bl.key" class="mb-3 pb-3 border-b border-slate-800 last:border-0">
                    <div class="flex items-center gap-2 mb-1">
                      <span :class="studyResult.meta?.blocks_run?.includes(bl.key) ? 'text-emerald-400' : 'text-slate-600'">
                        {{ studyResult.meta?.blocks_run?.includes(bl.key) ? '✓' : '—' }}
                      </span>
                      <span class="text-xs font-bold text-slate-300">{{ bl.title }}</span>
                    </div>
                    <div class="text-[11px] text-slate-500 pl-4">{{ bl.what }}</div>
                    <div class="text-[11px] text-slate-600 pl-4">Avec : {{ bl.inputs }}</div>
                  </div>
                </div>
              </div>

              <!-- FACTORIEL (A) -->
              <div v-if="activeStudyTab === 'factoriel'" class="flex flex-col gap-5">

                <!-- Bloc A non disponible -->
                <div v-if="!studyResult.block_a" class="card text-center py-8">
                  <div class="text-3xl mb-3">⏭</div>
                  <div class="text-slate-400 text-sm font-bold mb-1">Bloc A désactivé</div>
                  <div class="text-slate-500 text-xs">Cochez "A" dans le manifeste et relancez l'étude.</div>
                </div>

                <div v-else-if="!studyResult.block_a.available" class="card">
                  <div class="text-amber-400 font-bold text-sm mb-2">⚠ Analyse factorielle indisponible</div>
                  <div class="text-slate-400 text-xs mb-3">{{ studyResult.block_a.error }}</div>
                  <div class="text-slate-500 text-xs bg-slate-900 rounded p-3">
                    Les facteurs Fama-French doivent être téléchargés au préalable via le bouton
                    <span class="text-blue-400 font-mono">↻ Mettre à jour</span> dans la section
                    "2. Série de facteurs" de la config FF (partie supérieure de la page).
                    Série utilisée : <span class="font-mono text-slate-300">{{ studyResult.block_a.ff_series || '—' }}</span>
                  </div>
                </div>

                <template v-else>
                  <!-- Modèle utilisé -->
                  <div class="flex items-center gap-3 text-xs text-slate-500">
                    <span>Modèle : <strong class="text-slate-300">{{ studyResult.block_a.factor_model }}</strong></span>
                    <span>·</span>
                    <span>Série FF : <strong class="text-slate-300">{{ studyResult.block_a.ff_series }}</strong></span>
                    <span v-if="studyResult.block_a.fee_drag_pct">·</span>
                    <span v-if="studyResult.block_a.fee_drag_pct">
                      Frais gross add-back : <strong class="text-slate-300">{{ formatPercentRaw(studyResult.block_a.fee_drag_pct) }} p.a.</strong>
                    </span>
                  </div>

                  <!-- Benchmark synthétique — composition -->
                  <div v-if="studyResult.block_a.benchmark_composition"
                    class="rounded-lg border border-indigo-800/50 bg-indigo-950/20 px-4 py-3">
                    <div class="flex items-center gap-2 mb-2">
                      <span class="text-[10px] font-bold uppercase tracking-wider text-indigo-400">Benchmark synthétique</span>
                      <span class="text-xs text-slate-300 font-medium">{{ studyResult.block_a.benchmark_composition.label }}</span>
                    </div>
                    <div class="text-[10px] text-slate-500 mb-2 leading-relaxed">
                      {{ studyResult.block_a.benchmark_composition.description }}
                    </div>
                    <div class="flex flex-wrap gap-2">
                      <div v-for="c in studyResult.block_a.benchmark_composition.components" :key="c.ticker"
                        class="flex items-center gap-1.5 bg-slate-800/60 rounded px-2 py-1">
                        <span class="text-[10px] font-mono font-bold text-indigo-300">{{ c.ticker }}</span>
                        <span class="text-[10px] text-slate-400">{{ c.label }}</span>
                        <span class="text-[10px] font-bold text-slate-200">{{ formatPercent(c.weight * 100, 0) }}</span>
                      </div>
                    </div>
                  </div>

                  <!-- Warnings -->
                  <div v-if="studyResult.block_a.net?.warnings?.length"
                    class="p-3 bg-amber-950/40 border border-amber-800 rounded-lg text-xs text-amber-300">
                    <div v-for="w in studyResult.block_a.net.warnings" :key="w">⚠ {{ w }}</div>
                  </div>

                  <!-- KPIs performance -->
                  <div class="grid grid-cols-4 gap-3">
                    <div v-for="([label, val, cls, tip]) in [
                      ['Rendement ann.', formatPercent(studyResult.block_a.net?.performance?.ann_ret_pct ?? 0, 1),
                        (studyResult.block_a.net?.performance?.ann_ret_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400',
                        'Rendement annualisé sur la période de recouvrement FF (tronquée à la fin des données Ken French). Peut différer de la performance totale vie entière.'],
                      ['Volatilité ann.', formatPercent(studyResult.block_a.net?.performance?.ann_vol_pct ?? 0, 1), 'text-slate-300',
                        'Écart-type des rendements journaliers × √252. Mesure la dispersion des performances. >25% = produit très concentré ou à levier.'],
                      ['Sharpe', formatNumber(studyResult.block_a.net?.performance?.sharpe ?? 0, 2),
                        (studyResult.block_a.net?.performance?.sharpe ?? 0) >= 1 ? 'text-emerald-400' : 'text-amber-400',
                        '(Rendement ann. − taux sans risque) / Volatilité ann. Mesure le rendement par unité de risque. >1 = bon, >2 = excellent, <0 = sous le taux sans risque.'],
                      ['Max Drawdown', formatPercent(studyResult.block_a.net?.performance?.max_dd_pct ?? 0, 1), 'text-red-400',
                        'Perte maximale pic-à-creux sur la période analysée. Représente le pire scénario pour un investisseur entré au plus haut.'],
                    ]" :key="label" class="bg-slate-800/60 rounded-lg p-3 text-center">
                      <div class="text-xs text-slate-500 mb-1 flex items-center justify-center gap-1">{{ label }}
                        <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ tip }}</span></span>
                      </div>
                      <div class="text-base font-bold" :class="cls">{{ val }}</div>
                    </div>
                  </div>

                  <!-- Brut vs Net (si frais fournis) -->
                  <div v-if="studyResult.block_a.gross?.regression" class="card">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                      Alpha brut (gérant) vs net (client)
                    </div>
                    <table class="w-full text-xs">
                      <thead>
                        <tr class="text-slate-500 border-b border-slate-700">
                          <th class="text-left py-2 px-2">Métrique</th>
                          <th class="text-right py-2 px-2">
                            <span class="inline-flex items-center gap-1 justify-end">Net
                              <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full right-0 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Alpha/R² calculés sur la NAV telle que reçue par l'investisseur (après déduction des frais de gestion).</span></span>
                            </span>
                          </th>
                          <th class="text-right py-2 px-2">
                            <span class="inline-flex items-center gap-1 justify-end">Brut
                              <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full right-0 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">NAV re-grossie des frais (accrual quotidien = frais p.a. / 252). Représente la performance du gérant avant imputation des coûts.</span></span>
                            </span>
                          </th>
                          <th class="text-right py-2 px-2">
                            <span class="inline-flex items-center gap-1 justify-end">Delta (frais)
                              <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full right-0 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Différence Brut − Net = drag des frais de gestion sur l'alpha annualisé. Doit être ≈ la commission p.a. renseignée dans le manifeste.</span></span>
                            </span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr class="border-b border-slate-800/50">
                          <td class="py-1.5 px-2 text-slate-400">Alpha ann.</td>
                          <td class="py-1.5 px-2 text-right font-mono"
                            :class="(studyResult.block_a.net.regression.alpha_ann_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                            {{ (studyResult.block_a.net.regression.alpha_ann_pct ?? 0) >= 0 ? '+' : '' }}{{ formatPercent(studyResult.block_a.net.regression.alpha_ann_pct, 2) }}
                          </td>
                          <td class="py-1.5 px-2 text-right font-mono"
                            :class="(studyResult.block_a.gross.regression.alpha_ann_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                            {{ (studyResult.block_a.gross.regression.alpha_ann_pct ?? 0) >= 0 ? '+' : '' }}{{ formatPercent(studyResult.block_a.gross.regression.alpha_ann_pct, 2) }}
                          </td>
                          <td class="py-1.5 px-2 text-right font-mono text-amber-400">
                            +{{ formatPercent((studyResult.block_a.gross.regression.alpha_ann_pct ?? 0) - (studyResult.block_a.net.regression.alpha_ann_pct ?? 0), 2) }}
                          </td>
                        </tr>
                        <tr class="border-b border-slate-800/50">
                          <td class="py-1.5 px-2 text-slate-400">t-stat α</td>
                          <td class="py-1.5 px-2 text-right font-mono text-slate-300">{{ formatNumber(studyResult.block_a.net.regression.alpha_tstat, 2) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono text-slate-300">{{ formatNumber(studyResult.block_a.gross.regression.alpha_tstat, 2) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono text-slate-500">—</td>
                        </tr>
                        <tr>
                          <td class="py-1.5 px-2 text-slate-400">R²</td>
                          <td class="py-1.5 px-2 text-right font-mono text-blue-400">{{ formatPercent((studyResult.block_a.net.regression.r2 ?? 0)*100, 2) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono text-blue-400">{{ formatPercent((studyResult.block_a.gross.regression.r2 ?? 0)*100, 2) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono text-slate-500">—</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- Résumé régression -->
                  <div class="card">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Régression OLS</div>
                    <div class="grid grid-cols-3 gap-3 text-xs mb-4">
                      <div class="bg-slate-900 rounded p-3">
                        <div class="text-slate-500 mb-1 flex items-center gap-1">R² / Adj. R²
                          <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-0 mb-1.5 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Part de la variance du fonds expliquée par les facteurs FF. R² = 80% → les facteurs expliquent 80% des mouvements. Adj. R² pénalise les facteurs superflus.</span></span>
                        </div>
                        <div class="font-bold text-blue-400 text-base">{{ formatPercent((studyResult.block_a.net.regression.r2 ?? 0)*100, 1) }}</div>
                        <div class="text-slate-500 text-[10px]">Adj. {{ formatPercent((studyResult.block_a.net.regression.adj_r2 ?? 0)*100, 1) }}</div>
                      </div>
                      <div class="bg-slate-900 rounded p-3">
                        <div class="text-slate-500 mb-1 flex items-center gap-1">Alpha ann.
                          <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-0 mb-1.5 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Rendement excédentaire annualisé non expliqué par les facteurs. Alpha > 0 = valeur ajoutée gérant. Significatif si p &lt; 0.05 (voir t-stat et p-value sous la valeur).</span></span>
                        </div>
                        <div class="font-bold text-base"
                          :class="(studyResult.block_a.net.regression.alpha_ann_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                          {{ (studyResult.block_a.net.regression.alpha_ann_pct ?? 0) >= 0 ? '+' : '' }}{{ formatPercent(studyResult.block_a.net.regression.alpha_ann_pct, 2) }}
                        </div>
                        <div class="text-slate-500 text-[10px]">
                          t = {{ formatNumber(studyResult.block_a.net.regression.alpha_tstat, 2) }}
                          · p = {{ formatNumber(studyResult.block_a.net.regression.alpha_pvalue, 4) }}
                        </div>
                      </div>
                      <div class="bg-slate-900 rounded p-3">
                        <div class="text-slate-500 mb-1 flex items-center gap-1">Risque idiosync.
                          <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-0 mb-1.5 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Part de la variance (1 − R²) non captée par les facteurs systématiques. Élevée = forte dépendance aux décisions du gérant. DW = Durbin-Watson (autocorrélation résidus, idéal ≈ 2). N = observations.</span></span>
                        </div>
                        <div class="font-bold text-amber-400 text-base">{{ formatPercent(100 - (studyResult.block_a.net.regression.r2 ?? 0)*100, 1) }}</div>
                        <div class="text-slate-500 text-[10px]">DW = {{ formatNumber(studyResult.block_a.net.regression.dw, 2) }} · N = {{ formatInt(studyResult.block_a.net.regression.n_obs) }}</div>
                      </div>
                    </div>

                    <!-- Table des facteurs -->
                    <table class="w-full text-xs" v-if="studyResult.block_a.net.regression.factors?.length">
                      <thead>
                        <tr class="text-slate-500 border-b border-slate-700">
                          <th class="text-left py-2 px-2">Facteur</th>
                          <th class="text-right py-2 px-2"><span class="inline-flex items-center gap-1 justify-end">Beta<span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full right-0 mb-1.5 w-52 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Sensibilité du fonds au facteur. Beta = 1 → évolue point pour point avec le facteur. Beta &lt; 0 = exposition inverse.</span></span></span></th>
                          <th class="text-right py-2 px-2"><span class="inline-flex items-center gap-1 justify-end">IC 95% inf<span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full right-0 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Borne inférieure de l'intervalle de confiance à 95% du beta. Si l'IC ne contient pas 0, le beta est statistiquement significatif.</span></span></span></th>
                          <th class="text-right py-2 px-2"><span class="inline-flex items-center gap-1 justify-end">IC 95% sup<span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full right-0 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Borne supérieure de l'intervalle de confiance à 95% du beta.</span></span></span></th>
                          <th class="text-right py-2 px-2"><span class="inline-flex items-center gap-1 justify-end">t-stat<span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full right-0 mb-1.5 w-52 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Statistique de Student : beta / erreur standard. |t| &gt; 2 → significatif à ~5%. Plus |t| est grand, plus le beta est fiable.</span></span></span></th>
                          <th class="text-right py-2 px-2"><span class="inline-flex items-center gap-1 justify-end">p-value<span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full right-0 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Probabilité d'obtenir un beta aussi extrême si le vrai beta était 0. p &lt; 0.05 = significatif. p ≥ 0.10 = non significatif.</span></span></span></th>
                          <th class="text-center py-2 px-2"><span class="inline-flex items-center gap-1 justify-center">Sig.<span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help">?<span class="pointer-events-none absolute bottom-full left-0 mb-1.5 w-48 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">*** p&lt;0.001 · ** p&lt;0.01 · * p&lt;0.05 · · p&lt;0.10 · n.s. non significatif</span></span></span></th>
                        </tr>
                      </thead>
                      <tbody>
                        <!-- Alpha -->
                        <tr class="border-b border-slate-700 bg-slate-800/30">
                          <td class="py-1.5 px-2 font-bold text-amber-400">Alpha (ann.)</td>
                          <td class="py-1.5 px-2 text-right font-mono font-bold"
                            :class="(studyResult.block_a.net.regression.alpha_ann_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                            {{ (studyResult.block_a.net.regression.alpha_ann_pct ?? 0) >= 0 ? '+' : '' }}{{ formatPercentRaw(studyResult.block_a.net.regression.alpha_ann_pct) }}
                          </td>
                          <td class="py-1.5 px-2 text-right font-mono text-slate-400">{{ formatPercentRaw(studyResult.block_a.net.regression.alpha_ci_low) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono text-slate-400">{{ formatPercentRaw(studyResult.block_a.net.regression.alpha_ci_high) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono text-slate-300">{{ formatNumber(studyResult.block_a.net.regression.alpha_tstat, 2) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono" :class="pvalClass(studyResult.block_a.net.regression.alpha_pvalue)">
                            {{ fmtPVal(studyResult.block_a.net.regression.alpha_pvalue) }}
                          </td>
                          <td class="py-1.5 px-2 text-center font-bold" :class="pvalClass(studyResult.block_a.net.regression.alpha_pvalue)">
                            {{ sigStars(studyResult.block_a.net.regression.alpha_pvalue) }}
                          </td>
                        </tr>
                        <!-- Facteurs -->
                        <tr v-for="f in studyResult.block_a.net.regression.factors" :key="f.name"
                          class="border-b border-slate-800/50 hover:bg-slate-800/30">
                          <td class="py-1.5 px-2 font-bold text-slate-300">{{ f.name }}</td>
                          <td class="py-1.5 px-2 text-right font-mono font-bold"
                            :class="f.beta >= 0 ? 'text-blue-400' : 'text-red-400'">
                            {{ f.beta >= 0 ? '+' : '' }}{{ f.beta }}
                          </td>
                          <td class="py-1.5 px-2 text-right font-mono text-slate-500">{{ f.ci_low }}</td>
                          <td class="py-1.5 px-2 text-right font-mono text-slate-500">{{ f.ci_high }}</td>
                          <td class="py-1.5 px-2 text-right font-mono text-slate-300">{{ f.tstat }}</td>
                          <td class="py-1.5 px-2 text-right font-mono" :class="pvalClass(f.pvalue)">{{ fmtPVal(f.pvalue) }}</td>
                          <td class="py-1.5 px-2 text-center font-bold" :class="pvalClass(f.pvalue)">{{ sigStars(f.pvalue) }}</td>
                        </tr>
                      </tbody>
                    </table>
                    <div class="text-[10px] text-slate-600 mt-2">*** p&lt;0.001 · ** p&lt;0.01 · * p&lt;0.05 · · p&lt;0.10</div>
                  </div>

                  <!-- Momentum MOM -->
                  <div v-if="momFactor" class="card border border-slate-700/60">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
                      Exposition Momentum — Carhart MOM
                      <span class="text-[10px] font-normal normal-case tracking-normal text-slate-600">(facteur Winners Minus Losers)</span>
                    </div>
                    <div class="grid grid-cols-3 gap-4">
                      <!-- Bêta MOM -->
                      <div class="bg-slate-900 rounded-lg p-4 text-center">
                        <div class="text-xs text-slate-500 mb-2">Bêta MOM</div>
                        <div class="text-2xl font-black"
                          :class="momFactor.beta >= 0 ? 'text-violet-400' : 'text-orange-400'">
                          {{ momFactor.beta >= 0 ? '+' : '' }}{{ formatNumber(momFactor.beta, 3) }}
                        </div>
                        <div class="text-[10px] text-slate-600 mt-1">
                          IC 95% [{{ formatNumber(momFactor.ci_low, 3) }} ; {{ formatNumber(momFactor.ci_high, 3) }}]
                        </div>
                      </div>
                      <!-- Significativité -->
                      <div class="bg-slate-900 rounded-lg p-4 text-center">
                        <div class="text-xs text-slate-500 mb-2">Significativité</div>
                        <div class="text-2xl font-black" :class="pvalClass(momFactor.pvalue)">
                          {{ sigStars(momFactor.pvalue) || 'n.s.' }}
                        </div>
                        <div class="text-[10px] text-slate-600 mt-1">
                          t = {{ momFactor.tstat }} · p = {{ fmtPVal(momFactor.pvalue) }}
                        </div>
                      </div>
                      <!-- Style détecté -->
                      <div class="bg-slate-900 rounded-lg p-4 text-center">
                        <div class="text-xs text-slate-500 mb-2">Style détecté</div>
                        <div class="text-sm font-bold"
                          :class="momFactor.pvalue < 0.05 ? (momFactor.beta > 0 ? 'text-violet-400' : 'text-orange-400') : 'text-slate-500'">
                          {{ momFactor.pvalue >= 0.05 ? 'Neutre' : momFactor.beta > 0 ? 'Momentum' : 'Contrarian' }}
                        </div>
                        <div class="text-[10px] text-slate-600 mt-1 leading-relaxed">
                          {{ momFactor.pvalue >= 0.05
                            ? 'Pas de biais momentum significatif'
                            : momFactor.beta > 0
                              ? 'Tend à acheter les titres en tendance haussière'
                              : 'Tend à acheter les titres en baisse (anti-momentum)' }}
                        </div>
                      </div>
                    </div>
                    <!-- Barre IC 95% visuelle -->
                    <div class="mt-4 px-1">
                      <div class="flex items-center justify-between text-[10px] text-slate-600 mb-1">
                        <span>{{ momFactor.ci_low }}</span>
                        <span class="text-slate-500">Intervalle de confiance 95%</span>
                        <span>{{ momFactor.ci_high }}</span>
                      </div>
                      <div class="relative h-2 bg-slate-800 rounded-full overflow-hidden">
                        <div class="absolute inset-y-0 left-1/2 w-px bg-slate-600"></div>
                        <div class="absolute inset-y-0 rounded-full"
                          :class="momFactor.pvalue < 0.05 ? (momFactor.beta > 0 ? 'bg-violet-500/60' : 'bg-orange-500/60') : 'bg-slate-600/60'"
                          :style="{
                            left: Math.max(0, Math.min(100, 50 + (momFactor.ci_low / Math.max(Math.abs(momFactor.ci_low), Math.abs(momFactor.ci_high))) * 50)) + '%',
                            right: Math.max(0, Math.min(100, 50 - (momFactor.ci_high / Math.max(Math.abs(momFactor.ci_low), Math.abs(momFactor.ci_high))) * 50)) + '%'
                          }">
                        </div>
                        <div class="absolute inset-y-0 w-1 -ml-0.5 rounded-full bg-white/80"
                          :style="{left: Math.max(0, Math.min(100, 50 + (momFactor.beta / Math.max(Math.abs(momFactor.ci_low), Math.abs(momFactor.ci_high))) * 50)) + '%'}">
                        </div>
                      </div>
                      <div class="text-[10px] text-slate-600 mt-2">
                        {{ momFactor.ci_low > 0
                          ? 'L\'IC ne contient pas 0 — bêta MOM significativement positif (biais momentum confirmé)'
                          : momFactor.ci_high < 0
                            ? 'L\'IC ne contient pas 0 — bêta MOM significativement négatif (biais contrarian confirmé)'
                            : 'L\'IC contient 0 — bêta MOM non significativement différent de zéro' }}
                      </div>
                    </div>
                  </div>

                  <!-- Période -->
                  <div class="text-xs text-slate-600">
                    Période analysée : {{ formatDate(studyResult.block_a.net?.period?.overlap_start) }} → {{ formatDate(studyResult.block_a.net?.period?.overlap_end) }}
                    · {{ studyResult.block_a.net?.period?.n_obs }} observations
                  </div>

                  <!-- Rolling alpha / betas -->
                  <div v-if="studyResult.block_a.net?.rolling?.length > 5" class="card">
                    <div class="flex items-center justify-between mb-3">
                      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Alpha glissant (60j) et bêtas facteurs</div>
                      <div class="flex gap-2 flex-wrap">
                        <button v-for="f in (studyResult.block_a.net?.factors_used || [])" :key="f"
                          @click="studyRollingVisible.includes(f) ? studyRollingVisible.splice(studyRollingVisible.indexOf(f),1) : studyRollingVisible.push(f)"
                          class="px-2 py-0.5 text-[10px] rounded border transition-colors"
                          :class="studyRollingVisible.includes(f) ? 'bg-blue-600 border-blue-500 text-white' : 'border-slate-600 text-slate-500'">
                          {{ f }}
                        </button>
                      </div>
                    </div>
                    <canvas :ref="el => { studyRollingChartRef = el; renderStudyRolling() }" height="180"></canvas>
                  </div>

                  <!-- Courbe de performance -->
                  <div v-if="studyResult.block_a.net?.performance?.cum_amc?.length" class="card">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Performance cumulée (période overlappée)</div>
                    <canvas :ref="el => { studyPerfChartRef = el; renderStudyPerf() }" height="160"></canvas>
                  </div>

                  <!-- Dependency score -->
                  <div v-if="studyResult.block_a.net?.dependency_score" class="card">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1">Score de dépendance au gérant
                      <span class="group relative inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-700/80 text-[8px] cursor-help ml-0.5 shrink-0">?<span class="pointer-events-none absolute bottom-full left-0 mb-2 w-64 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2.5 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Score composite 0-10 : risque idiosyncratique (40pts) + turnover (30pts) + concentration HHI (20pts) + significativité alpha (10pts) / 10. Élevé = gestion très active.</span></span>
                    </div>
                    <div class="grid grid-cols-4 gap-3">
                      <div v-for="([label, val, cls, tip]) in [
                        ['Score global', studyResult.block_a.net.dependency_score.score + '/10',
                          studyResult.block_a.net.dependency_score.score >= 7 ? 'text-emerald-400' : studyResult.block_a.net.dependency_score.score >= 4 ? 'text-amber-400' : 'text-red-400',
                          'Score composite 0-10 mesurant la dépendance aux décisions du gérant vs les facteurs de marché.'],
                        ['R²', formatPercent((studyResult.block_a.net.regression.r2||0)*100, 1), 'text-blue-400',
                          'Part de variance expliquée par les facteurs FF. 1 − R² = risque idiosyncratique entrant dans le score.'],
                        ['Turnover ann.', studyResult.block_a.net.activity?.turnover_ann_pct != null ? formatPercent(studyResult.block_a.net.activity.turnover_ann_pct, 0) : '—', 'text-slate-300',
                          'Turnover annualisé : notionnel brut échangé / AUM moyen × (252 / N jours). 100% = l\'équivalent du portefeuille rebalancé une fois par an.'],
                        ['Trades total', studyResult.block_a.net.activity?.total_trades ?? '—', 'text-slate-300',
                          'Nombre d\'ordres exécutés (état Done) dans le(s) fichier(s) JSON du carnet d\'ordres.'],
                      ]" :key="label" class="bg-slate-900 rounded p-3 text-center">
                        <div class="text-xs text-slate-500 mb-1 flex items-center justify-center gap-1">{{ label }}
                          <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ tip }}</span></span>
                        </div>
                        <div class="text-base font-bold" :class="cls">{{ val }}</div>
                      </div>
                    </div>
                    <div v-if="studyResult.block_a.net.dependency_score.label" class="mt-2 text-xs text-slate-400 italic">
                      {{ studyResult.block_a.net.dependency_score.label }}
                    </div>
                  </div>

                  <!-- Concentration -->
                  <div v-if="studyResult.block_a.net?.concentration?.top_holdings?.length" class="card">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                      Composition actuelle · HHI = {{ formatNumber(studyResult.block_a.net.concentration.hhi, 3) }}
                      · Top-5 = {{ formatPercent((studyResult.block_a.net.concentration.top5_weight||0)*100, 1) }}
                    </div>
                    <div class="space-y-1 mb-4">
                      <div v-for="h in studyResult.block_a.net.concentration.top_holdings" :key="h.name"
                        class="flex items-center gap-2 text-xs">
                        <div class="text-slate-400 w-36 truncate"><SensitiveValue mode="blur">{{ h.name }}</SensitiveValue></div>
                        <div class="flex-1 h-2 bg-slate-800 rounded overflow-hidden">
                          <div class="h-full bg-blue-600 rounded"
                            :style="{ width: (h.weight * 100 / studyResult.block_a.net.concentration.top_holdings[0].weight) + '%' }"></div>
                        </div>
                        <div class="text-slate-300 w-12 text-right font-mono">{{ formatPercent((h.weight||0)*100, 1) }}</div>
                      </div>
                    </div>
                    <div v-if="studyResult.block_a.net.concentration.sectors?.length" class="grid grid-cols-3 gap-3 text-xs">
                      <div>
                        <div class="text-slate-500 mb-1 font-bold">Secteurs</div>
                        <div v-for="s in studyResult.block_a.net.concentration.sectors" :key="s.name"
                          class="flex justify-between text-xs py-0.5 border-b border-slate-800">
                          <span class="text-slate-400 truncate w-28">{{ s.name }}</span>
                          <span class="text-slate-300 font-mono">{{ formatPercent((s.weight||0)*100, 1) }}</span>
                        </div>
                      </div>
                      <div>
                        <div class="text-slate-500 mb-1 font-bold">Pays</div>
                        <div v-for="c in studyResult.block_a.net.concentration.countries" :key="c.name"
                          class="flex justify-between text-xs py-0.5 border-b border-slate-800">
                          <span class="text-slate-400 w-28">{{ c.name }}</span>
                          <span class="text-slate-300 font-mono">{{ formatPercent((c.weight||0)*100, 1) }}</span>
                        </div>
                      </div>
                      <div>
                        <div class="text-slate-500 mb-1 font-bold">Devises</div>
                        <div v-for="c in studyResult.block_a.net.concentration.currencies" :key="c.name"
                          class="flex justify-between text-xs py-0.5 border-b border-slate-800">
                          <span class="text-slate-400 w-28">{{ c.name }}</span>
                          <span class="text-slate-300 font-mono">{{ formatPercent((c.weight||0)*100, 1) }}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                </template>
              </div>
              <!-- /FACTORIEL -->

              <!-- ATTRIBUTION (B) -->
              <div v-if="activeStudyTab === 'attribution' && studyResult.block_b" class="flex flex-col gap-5">
                <!-- Période -->
                <div v-if="studyResult.meta?.nav_start_date" class="text-[10px] text-slate-500 -mb-2">
                  Période d'étude : {{ formatDate(studyResult.meta.nav_start_date) }} → {{ formatDate(studyResult.meta.nav_current_date) }}
                  · {{ studyResult.meta.nav_n_obs }} observations NAV
                </div>
                <div v-if="studyResult.meta?.recon_mode === 't0_synthetic'" class="flex items-start gap-3 rounded-lg bg-amber-950/30 border border-amber-500/30 px-4 py-3 text-sm text-amber-200">
                  <span class="text-amber-400 text-base leading-none mt-0.5 shrink-0">⚠</span>
                  <span>Les positions initiales ont été reconstruites par BUY synthétiques à T0. Les métriques de P&amp;L réalisé et de round trips sont donc plus cohérentes qu'en mode inventaire clampé, mais restent dépendantes des hypothèses de reconstruction du stock initial.</span>
                </div>
                <div class="grid grid-cols-4 gap-3">
                  <div v-for="([label, val, cls, tip]) in [
                    ['P&L réalisé', fmtPnl(studyResult.block_b.totals?.realized_pnl, studyResult.meta?.currency), studyResult.block_b.totals?.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400',
                      'P&L effectivement encaissé sur les positions clôturées (aller-retours complets). Calculé par reconstruction FIFO des ordres exécutés.'],
                    ['P&L latent', fmtPnl(studyResult.block_b.totals?.unreal_pnl, studyResult.meta?.currency), studyResult.block_b.totals?.unreal_pnl >= 0 ? 'text-emerald-400' : 'text-red-400',
                      'Plus/moins-value non réalisée sur les positions encore ouvertes. Valorisée au prix du snapshot (Def.txt). Ne tient pas compte de l\'évolution du prix depuis le snapshot.'],
                    ['P&L total', fmtPnl(studyResult.block_b.totals?.total_pnl, studyResult.meta?.currency), studyResult.block_b.totals?.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400',
                      'P&L réalisé + P&L latent. Couvre l\'intégralité du carnet d\'ordres (pas uniquement la période FF). Exprimé dans la devise du produit.'],
                    ['Part FX', studyResult.block_b.totals?.fx_share_of_realized_pct != null ? formatPercent(studyResult.block_b.totals.fx_share_of_realized_pct, 1) : '—', 'text-amber-400',
                      'Fraction du P&L réalisé attribuable à la variation des taux de change (effet FX), calculée sur les aller-retours clôturés avec conversion de devise.'],
                  ]" :key="label" class="bg-slate-800/60 rounded-lg p-3 text-center">
                    <div class="text-xs text-slate-500 mb-1 flex items-center justify-center gap-1">{{ label }}
                      <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ tip }}</span></span>
                    </div>
                    <div class="text-base font-bold" :class="cls">
                      <SensitiveValue v-if="isSensitiveAmt(label)">{{ val }}</SensitiveValue>
                      <template v-else>{{ val }}</template>
                    </div>
                  </div>
                </div>

                <div v-if="studyResult.block_b.totals?.reconciliation" class="card">
                  <div class="flex items-center justify-between mb-3">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Réconciliation NAV</div>
                    <div class="text-[10px] text-slate-600 font-mono">as of {{ formatDate(studyResult.block_b.totals.reconciliation.as_of) }}</div>
                  </div>
                  <div class="grid grid-cols-5 gap-2">
                    <div v-for="([label, val, cls, tip]) in [
                      ['P&L FIFO (brut)', fmtPnl(studyResult.block_b.totals?.total_pnl, studyResult.meta?.currency), 'text-slate-200',
                        'P&L total reconstruit par le FIFO, brut de frais de gestion.'],
                      ['Frais cumulés (est.)', fmtPnl(studyResult.block_b.totals?.fee_drag_prod, studyResult.meta?.currency), 'text-red-300',
                        'Frais de gestion estimés (accrual quotidien sur l\'AUM, au taux du termsheet) cumulés depuis la date de fixing jusqu\'à la date du dernier ordre du carnet.'],
                      ['P&L net estimé', fmtPnl(studyResult.block_b.totals?.total_pnl_net_of_fees, studyResult.meta?.currency), 'text-slate-200',
                        'P&L FIFO brut moins les frais de gestion cumulés estimés — comparable à la performance NAV publiée.'],
                      ['P&L implicite NAV', fmtPnl(studyResult.block_b.totals.reconciliation.nav_implied_pnl_prod, studyResult.meta?.currency), 'text-emerald-400',
                        'P&L réel du fonds calculé directement depuis la NAV quotidienne et les flux de souscription/rachat (Δ Outstanding × NAV à chaque mouvement). Indépendant du carnet d\'ordres et du FIFO.'],
                      ['Écart résiduel', studyResult.block_b.totals.reconciliation.gap_pct != null ? (studyResult.block_b.totals.reconciliation.gap_pct >= 0 ? '+' : '') + formatPercent(studyResult.block_b.totals.reconciliation.gap_pct, 1) : '—',
                        Math.abs(studyResult.block_b.totals.reconciliation.gap_pct || 0) > 15 ? 'text-amber-400' : 'text-emerald-400',
                        'Écart entre le P&L net estimé et le P&L implicite NAV, en % du P&L implicite NAV. Un écart résiduel traduit des opérations sur titre non résolues, un cash drag non modélisé, ou des différences de source de valorisation (yfinance vs valorisateur du fonds).'],
                    ]" :key="label" class="bg-slate-800/60 rounded-lg p-3 text-center">
                      <div class="text-[10px] text-slate-500 mb-1 flex items-center justify-center gap-1">{{ label }}
                        <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ tip }}</span></span>
                      </div>
                      <div class="text-sm font-bold" :class="cls">
                        <SensitiveValue>{{ val }}</SensitiveValue>
                      </div>
                    </div>
                  </div>
                  <div v-if="!studyResult.block_b.totals?.fee_drag_prod" class="text-[10px] text-amber-500/80 mt-3">
                    ⚠ Aucun frais renseigné (params.management_fee_pct / perf_fee_pct / txn_cost_pct dans le manifest) — le P&L net estimé n'inclut aucun add-back de frais, l'écart résiduel affiché est donc probablement surestimé.
                  </div>

                  <div v-if="studyResult.block_b.totals?.reconciliation?.fee_breakdown" class="mt-3 pt-3 border-t border-slate-800">
                    <div class="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Décomposition des frais</div>
                    <div class="grid grid-cols-3 gap-2">
                      <div v-for="([label, val, tip]) in [
                        ['Gestion (' + (studyResult.block_b.totals.reconciliation.fee_breakdown.management_fee_pct ?? '—') + '% p.a.)',
                          studyResult.block_b.totals.reconciliation.fee_breakdown.management_fee_prod,
                          'Accrual quotidien sur l\'AUM (taux annuel ÷ 252), cumulé sur toute la période.'],
                        ['Performance (' + (studyResult.block_b.totals.reconciliation.fee_breakdown.performance_fee_pct ?? '—') + '% HWM' + (studyResult.block_b.totals.reconciliation.fee_breakdown.performance_fee_events != null ? ', ' + studyResult.block_b.totals.reconciliation.fee_breakdown.performance_fee_events + ' plus-hauts' : '') + ')',
                          studyResult.block_b.totals.reconciliation.fee_breakdown.performance_fee_prod,
                          'Prélevé uniquement les jours où la NAV atteint un nouveau plus haut historique — 10% du gain brut ce jour-là, pas un accrual continu. Plus haut final atteint : ' + (studyResult.block_b.totals.reconciliation.fee_breakdown.performance_fee_hwm_final ?? '—') + '.'],
                        ['Transaction (' + (studyResult.block_b.totals.reconciliation.fee_breakdown.transaction_cost_pct ?? '—') + '% notionnel)',
                          studyResult.block_b.totals.reconciliation.fee_breakdown.transaction_cost_prod,
                          'Coût appliqué au notionnel de chaque ordre du carnet (achat et vente), à chaque rebalancement.'],
                      ]" :key="label" class="bg-slate-800/40 rounded-lg p-2.5 text-center">
                        <div class="text-[9px] text-slate-500 mb-1 flex items-center justify-center gap-1">{{ label }}
                          <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ tip }}</span></span>
                        </div>
                        <div class="text-xs font-bold" :class="val ? 'text-red-300' : 'text-slate-600'">
                          <SensitiveValue>{{ val ? fmtPnl(val, studyResult.meta?.currency) : 'non renseigné' }}</SensitiveValue>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="card">
                  <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">P&L par sous-jacent</div>
                  <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                  <table class="w-full text-xs min-w-[600px]">
                    <thead>
                      <tr class="text-slate-500 border-b border-slate-700">
                        <th class="text-left py-2 px-2">Titre</th>
                        <th class="text-right py-2 px-2" title="P&L encaissé sur les aller-retours clôturés pour ce titre (FIFO). Inclut l'effet prix et l'effet FX.">P&L réalisé</th>
                        <th class="text-right py-2 px-2" title="Composante de change du P&L réalisé : q × Prix_entrée × (FX_sortie − FX_entrée). Isole l'effet devise de l'effet prix.">Dont FX</th>
                        <th class="text-right py-2 px-2" title="Plus/moins-value sur la position encore ouverte, valorisée au prix courant du snapshot (Def.txt).">P&L latent</th>
                        <th class="text-right py-2 px-2">Total</th>
                        <th class="text-right py-2 px-2" title="Poids du titre dans le portefeuille au snapshot (Def.txt). Fraction de l'AUM total.">Poids %</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="r in studyResult.block_b.per_name" :key="r.isin"
                        class="border-b border-slate-800/50 hover:bg-slate-800/30">
                        <td class="py-1.5 px-2 text-slate-300"><SensitiveValue mode="blur">{{ r.name }}</SensitiveValue></td>
                        <td class="py-1.5 px-2 text-right font-mono"
                          :class="(r.realized_pnl||0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                          <SensitiveValue>{{ fmtPnl(r.realized_pnl) }}</SensitiveValue>
                        </td>
                        <td class="py-1.5 px-2 text-right font-mono text-amber-300/70"><SensitiveValue>{{ fmtPnl(r.fx_pnl) }}</SensitiveValue></td>
                        <td class="py-1.5 px-2 text-right font-mono text-slate-400"><SensitiveValue>{{ fmtPnl(r.unreal_pnl) }}</SensitiveValue></td>
                        <td class="py-1.5 px-2 text-right font-mono font-bold"
                          :class="(r.total_pnl||0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                          <SensitiveValue>{{ fmtPnl(r.total_pnl) }}</SensitiveValue>
                        </td>
                        <td class="py-1.5 px-2 text-right text-slate-400">{{ formatPercent((r.weight||0)*100, 2) }}</td>
                      </tr>
                    </tbody>
                  </table>
                  </div>
                </div>

                <div v-if="studyResult.block_b.quarterly_realized?.length" class="card">
                  <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">P&L réalisé par trimestre</div>
                  <div class="flex items-end gap-1 h-20">
                    <div v-for="q in studyResult.block_b.quarterly_realized" :key="q.quarter"
                      class="flex flex-col items-center gap-0.5 flex-1 min-w-0">
                      <div class="text-[9px] font-mono truncate w-full text-center"
                        :class="q.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'">
                        <SensitiveValue>{{ fmtPnl(q.realized_pnl) }}</SensitiveValue>
                      </div>
                      <div class="w-full rounded-sm"
                        :class="q.realized_pnl >= 0 ? 'bg-emerald-500/60' : 'bg-red-500/60'"
                        :style="{height: Math.max(4, Math.abs(q.realized_pnl) / Math.max(...studyResult.block_b.quarterly_realized.map(x=>Math.abs(x.realized_pnl))) * 52) + 'px'}">
                      </div>
                      <div class="text-[9px] text-slate-600 truncate w-full text-center">{{ q.quarter }}</div>
                    </div>
                  </div>
                </div>

                <div v-if="studyResult.block_b.per_name?.some(r => r.unreal_pnl && r.unreal_pnl !== 0)" class="card">
                  <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">P&L latent par sous-jacent <span class="text-slate-600 font-normal normal-case tracking-normal">(positions ouvertes)</span></div>
                  <div class="flex items-end gap-1 h-20">
                    <div v-for="r in studyResult.block_b.per_name.filter(x => x.unreal_pnl && x.unreal_pnl !== 0).sort((a,b) => Math.abs(b.unreal_pnl) - Math.abs(a.unreal_pnl))"
                      :key="r.isin" class="flex flex-col items-center gap-0.5 flex-1 min-w-0">
                      <div class="text-[9px] font-mono truncate w-full text-center"
                        :class="r.unreal_pnl >= 0 ? 'text-sky-400' : 'text-orange-400'">
                        <SensitiveValue>{{ fmtPnl(r.unreal_pnl) }}</SensitiveValue>
                      </div>
                      <div class="w-full rounded-sm"
                        :class="r.unreal_pnl >= 0 ? 'bg-sky-500/50' : 'bg-orange-500/50'"
                        :style="{height: Math.max(4, Math.abs(r.unreal_pnl) / Math.max(...studyResult.block_b.per_name.filter(x => x.unreal_pnl).map(x => Math.abs(x.unreal_pnl))) * 52) + 'px'}">
                      </div>
                      <div class="text-[9px] text-slate-600 truncate w-full text-center"><SensitiveValue mode="blur">{{ r.name }}</SensitiveValue></div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- TRADING (C) -->
              <div v-if="activeStudyTab === 'trading' && studyResult.block_c" class="flex flex-col gap-5">
                <!-- Période -->
                <div v-if="studyResult.meta?.nav_start_date" class="text-[10px] text-slate-500 -mb-2">
                  Période d'étude : {{ formatDate(studyResult.meta.nav_start_date) }} → {{ formatDate(studyResult.meta.nav_current_date) }}
                  · {{ studyResult.meta.nav_n_obs }} observations NAV
                  · {{ studyResult.block_c.turnover?.period_days ?? '—' }} jours
                </div>
                <div v-if="studyResult.meta?.recon_mode === 't0_synthetic'" class="flex items-start gap-3 rounded-lg bg-amber-950/30 border border-amber-500/30 px-4 py-3 text-sm text-amber-200">
                  <span class="text-amber-400 text-base leading-none mt-0.5 shrink-0">⚠</span>
                  <span>Les positions initiales ont été reconstruites par BUY synthétiques à T0. Les métriques de P&amp;L réalisé et de round trips sont donc plus cohérentes qu'en mode inventaire clampé, mais restent dépendantes des hypothèses de reconstruction du stock initial.</span>
                </div>
                <div class="grid grid-cols-4 gap-3">
                  <div v-for="([label, val, cls, tip]) in [
                    ['Round-trips', studyResult.block_c.round_trips?.count ?? '—', 'text-slate-300',
                      'Nombre d\'aller-retours complets (achat + vente) identifiés par appariement FIFO. Chaque round-trip clôturé génère un P&L réalisé.'],
                    ['Hit ratio', formatPercent(studyResult.block_c.round_trips?.win_rate_pct ?? 0, 1), studyResult.block_c.round_trips?.win_rate_pct >= 50 ? 'text-emerald-400' : 'text-amber-400',
                      'Pourcentage de round-trips gagnants (P&L réalisé > 0). 50% = autant de gains que de pertes. >60% = bonne qualité de sélection.'],
                    ['Profit factor', formatNumber(studyResult.block_c.round_trips?.profit_factor ?? 0, 2), studyResult.block_c.round_trips?.profit_factor >= 1 ? 'text-emerald-400' : 'text-red-400',
                      'Somme des P&L gagnants / valeur absolue des P&L perdants. >1 = l\'argent gagné dépasse l\'argent perdu. >2 = excellent. <1 = destruction de valeur.'],
                    ['Durée médiane', formatNumber(studyResult.block_c.round_trips?.median_holding_days ?? 0, 0)+'j', 'text-blue-400',
                      'Durée médiane de détention des positions clôturées (en jours calendaires). Distingue les paris de conviction long terme des positions tactiques courtes.'],
                  ]" :key="label" class="bg-slate-800/60 rounded-lg p-3 text-center">
                    <div class="text-xs text-slate-500 mb-1 flex items-center justify-center gap-1">{{ label }}
                      <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ tip }}</span></span>
                    </div>
                    <div class="text-xl font-bold" :class="cls">{{ val }}</div>
                  </div>
                </div>
                <div class="grid grid-cols-2 gap-5">
                  <div class="card">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Statistiques de trading</div>
                    <table class="w-full text-xs">
                      <tr v-for="([k,v,tip]) in [
                        ['P&L moyen (gain)', fmtPnl(studyResult.block_c.round_trips?.avg_win, studyResult.meta?.currency), 'P&L réalisé moyen des round-trips gagnants (P&L > 0). Indicateur de l\'ampleur typique des gains.'],
                        ['P&L moyen (perte)', fmtPnl(studyResult.block_c.round_trips?.avg_loss, studyResult.meta?.currency), 'P&L réalisé moyen des round-trips perdants (en valeur absolue). Indicateur de l\'ampleur typique des pertes.'],
                        ['P&L réalisé total', fmtPnl(studyResult.block_c.round_trips?.realized_pnl, studyResult.meta?.currency), 'Somme du P&L réalisé sur tous les round-trips clôturés, dans la devise du produit.'],
                        ['Durée moy.', formatNumber(studyResult.block_c.round_trips?.avg_holding_days ?? 0, 1)+' j', 'Durée moyenne de détention de toutes les positions clôturées en jours calendaires. Complément de la durée médiane (sensible aux extrêmes).'],
                      ]" :key="k" class="border-b border-slate-800/50">
                        <td class="py-1.5 text-slate-500">
                          <span class="inline-flex items-center gap-1">{{ k }}
                            <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-0 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ tip }}</span></span>
                          </span>
                        </td>
                        <td class="py-1.5 text-right text-slate-300 font-mono">
                          <SensitiveValue v-if="isSensitiveAmt(k)">{{ v }}</SensitiveValue>
                          <template v-else>{{ v }}</template>
                        </td>
                      </tr>
                    </table>
                  </div>
                  <div class="card">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Turnover</div>
                    <table class="w-full text-xs">
                      <tr v-for="([k,v,tip]) in [
                        ['Gross traded', fmtPnl(studyResult.block_c.turnover?.gross_traded_prod, studyResult.meta?.currency), 'Notionnel brut total échangé (achats + ventes) sur toute la période du carnet d\'ordres, dans la devise du produit.'],
                        ['AUM moyen', fmtPnl(studyResult.block_c.turnover?.avg_aum_prod, studyResult.meta?.currency), 'AUM moyen estimé sur la période : NAV × certificats en circulation, moyenné sur les observations disponibles.'],
                        ['Turnover (période)', formatPercent((studyResult.block_c.turnover?.turnover_rate ?? 0)*100, 1), 'Gross traded / AUM moyen sur toute la période du carnet d\'ordres. Non annualisé — dépend de la durée couverte.'],
                        ['Turnover annualisé', formatPercent((studyResult.block_c.turnover?.turnover_annualized ?? 0)*100, 1), 'Turnover rapporté à une année (× 252 / N jours). Permet la comparaison entre produits de durées différentes. 100% = l\'équivalent du portefeuille rebalancé 1× par an.'],
                        ['Période', (studyResult.block_c.turnover?.period_days ?? '—')+' jours', 'Nombre de jours calendaires couverts par le carnet d\'ordres (du premier au dernier ordre exécuté).'],
                      ]" :key="k" class="border-b border-slate-800/50">
                        <td class="py-1.5 text-slate-500">
                          <span class="inline-flex items-center gap-1">{{ k }}
                            <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-0 mb-1.5 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ tip }}</span></span>
                          </span>
                        </td>
                        <td class="py-1.5 text-right text-slate-300 font-mono">
                          <SensitiveValue v-if="isSensitiveAmt(k)">{{ v }}</SensitiveValue>
                          <template v-else>{{ v }}</template>
                        </td>
                      </tr>
                    </table>
                  </div>
                </div>
                <div v-if="studyResult.block_c.trading_vs_hold?.note" class="text-xs text-slate-600 italic">
                  {{ studyResult.block_c.trading_vs_hold.note }}
                </div>
              </div>

              <!-- BEHAVIOUR (D) -->
              <div v-if="activeStudyTab === 'behaviour' && studyResult.block_d" class="flex flex-col gap-5">
                <!-- Période -->
                <div v-if="studyResult.meta?.nav_start_date" class="text-[10px] text-slate-500 -mb-2">
                  Période d'étude : {{ formatDate(studyResult.meta.nav_start_date) }} → {{ formatDate(studyResult.meta.nav_current_date) }}
                  · {{ studyResult.meta.n_orders }} ordres
                </div>

                <!-- Explication du concept -->
                <div class="card border border-slate-700/50 text-xs text-slate-400 leading-5">
                  <div class="font-semibold text-slate-300 mb-1">💡 Lecture du Bloc D</div>
                  Ce bloc classe chaque position clôturée selon <strong class="text-slate-200">deux axes</strong> :
                  <span class="text-violet-300">la conviction</span> (poids &gt; {{ formatPercentRaw(studyResult.block_d.conviction_matrix?.params?.conviction_weight_pct) }} du portefeuille
                  ET durée &gt; {{ studyResult.block_d.conviction_matrix?.params?.long_term_days }}j) et
                  <span class="text-violet-300">le résultat</span> (P&L positif ou négatif).
                  Un bon gérant a un maximum de positions en haut à gauche (conviction → profit) et un minimum en bas à droite (incertitude → pertes).
                </div>

                <!-- KPI row — libellés contextualisés -->
                <div class="grid grid-cols-4 gap-3 items-stretch">
                  <div v-for="([val, label, sub, cls, tip]) in [
                    [studyResult.block_d.holding_distribution?.long_term_count ?? '—',
                      'Long terme', `> ${studyResult.block_d.conviction_matrix?.params?.long_term_days ?? 180}j`,
                      'text-emerald-400',
                      'Positions clôturées dont la durée dépasse le seuil long terme du manifeste. Reflet de la conviction du gérant à tenir ses positions.'],
                    [studyResult.block_d.holding_distribution?.tactical_count ?? '—',
                      'Tactique', 'court terme',
                      'text-amber-400',
                      'Positions clôturées avant le seuil long terme. Repositionnements rapides ou opérations de court terme.'],
                    [formatPercent(studyResult.block_d.order_hygiene?.discarded_ratio_pct ?? 0, 1),
                      'Ordres annulés', 'taux Discarded',
                      studyResult.block_d.order_hygiene?.discarded_ratio_pct > 15 ? 'text-amber-400' : 'text-slate-300',
                      'Discarded / (Done + Discarded). > 15% : signal d\'hésitation ou difficultés d\'exécution.'],
                    [formatNumber(studyResult.block_d.holding_distribution?.avg_holding_days ?? 0, 0)+'j',
                      'Durée moy.', 'positions clôturées',
                      'text-blue-400',
                      'Durée moyenne de détention de toutes les positions clôturées en jours calendaires.'],
                  ]" :key="label" class="bg-slate-800/60 rounded-lg p-3 flex flex-col items-center justify-center text-center min-h-[72px]">
                    <div class="text-2xl font-black leading-none mb-1.5" :class="cls">{{ val }}</div>
                    <div class="text-[10px] text-slate-400 font-medium leading-tight flex items-center gap-1">
                      {{ label }}
                      <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ tip }}</span></span>
                    </div>
                    <div class="text-[9px] text-slate-600 mt-0.5">{{ sub }}</div>
                  </div>
                </div>

                <!-- Matrice conviction 2×2 — layout visuel clair -->
                <div v-if="studyResult.block_d.conviction_matrix" class="card">
                  <div class="text-xs font-bold text-slate-300 mb-1 flex items-center gap-2">
                    Matrice conviction × résultat
                    <span class="font-normal text-slate-600 text-[10px]">
                      seuil poids {{ formatPercentRaw(studyResult.block_d.conviction_matrix.params?.conviction_weight_pct) }} · seuil durée {{ studyResult.block_d.conviction_matrix.params?.long_term_days }}j
                    </span>
                  </div>
                  <div class="text-[10px] text-slate-600 mb-4">
                    Chaque position clôturée est placée dans un des 4 quadrants selon sa conviction (poids ET durée) et son résultat (P&L +/−).
                  </div>

                  <!-- Axes labels + 2×2 grid -->
                  <div class="flex gap-3">
                    <!-- Axe vertical -->
                    <div class="flex flex-col justify-center items-center w-4 shrink-0 gap-1">
                      <div class="text-[9px] text-emerald-500 font-bold rotate-[-90deg] whitespace-nowrap leading-none">P&L +</div>
                      <div class="w-px flex-1 bg-slate-700"></div>
                      <div class="text-[9px] text-red-500 font-bold rotate-[-90deg] whitespace-nowrap leading-none">P&L −</div>
                    </div>
                    <div class="flex-1">
                      <!-- Axe horizontal -->
                      <div class="flex justify-between text-[9px] mb-1 px-2">
                        <span class="text-violet-400 font-bold">← Forte conviction</span>
                        <span class="text-slate-600 font-bold">Faible conviction →</span>
                      </div>
                      <!-- 2×2 grid -->
                      <div class="grid grid-cols-2 border border-slate-700 rounded-lg overflow-hidden">
                        <!-- Top-left: conviction_winners -->
                        <div class="p-3 border-r border-b border-slate-700 bg-emerald-950/40">
                          <div class="text-[10px] font-bold text-emerald-400 mb-1">✓ Paris gagnants assumés</div>
                          <div class="text-[9px] text-slate-600 mb-2">Forte conviction · gain réalisé</div>
                          <div class="text-2xl font-black text-emerald-400 leading-none">
                            {{ studyResult.block_d.conviction_matrix.counts?.conviction_winners ?? 0 }}
                          </div>
                          <div class="text-xs font-mono text-emerald-400 mt-0.5">
                            <SensitiveValue>{{ fmtPnl(studyResult.block_d.conviction_matrix.pnl?.conviction_winners, studyResult.meta?.currency) }}</SensitiveValue>
                          </div>
                          <div class="mt-2 space-y-0.5">
                            <div v-for="pos in (studyResult.block_d.conviction_matrix.quadrants?.conviction_winners || []).slice(0,3)"
                              :key="pos.isin" class="text-[9px] flex justify-between text-slate-500">
                              <span class="truncate max-w-[65%]"><SensitiveValue mode="blur">{{ pos.name }}</SensitiveValue></span>
                              <span class="font-mono text-emerald-500/70"><SensitiveValue>{{ fmtPnl(pos.total_pnl) }}</SensitiveValue></span>
                            </div>
                          </div>
                        </div>
                        <!-- Top-right: tactical_winners -->
                        <div class="p-3 border-b border-slate-700 bg-blue-950/30">
                          <div class="text-[10px] font-bold text-blue-400 mb-1">✓ Coups tactiques réussis</div>
                          <div class="text-[9px] text-slate-600 mb-2">Faible conviction · gain réalisé</div>
                          <div class="text-2xl font-black text-blue-400 leading-none">
                            {{ studyResult.block_d.conviction_matrix.counts?.tactical_winners ?? 0 }}
                          </div>
                          <div class="text-xs font-mono text-blue-400 mt-0.5">
                            <SensitiveValue>{{ fmtPnl(studyResult.block_d.conviction_matrix.pnl?.tactical_winners, studyResult.meta?.currency) }}</SensitiveValue>
                          </div>
                          <div class="mt-2 space-y-0.5">
                            <div v-for="pos in (studyResult.block_d.conviction_matrix.quadrants?.tactical_winners || []).slice(0,3)"
                              :key="pos.isin" class="text-[9px] flex justify-between text-slate-500">
                              <span class="truncate max-w-[65%]"><SensitiveValue mode="blur">{{ pos.name }}</SensitiveValue></span>
                              <span class="font-mono text-emerald-500/70"><SensitiveValue>{{ fmtPnl(pos.total_pnl) }}</SensitiveValue></span>
                            </div>
                          </div>
                        </div>
                        <!-- Bottom-left: stubborn_losers -->
                        <div class="p-3 border-r border-slate-700 bg-red-950/30">
                          <div class="text-[10px] font-bold text-red-400 mb-1">✗ Entêtements coûteux</div>
                          <div class="text-[9px] text-slate-600 mb-2">Forte conviction · perte réalisée</div>
                          <div class="text-2xl font-black text-red-400 leading-none">
                            {{ studyResult.block_d.conviction_matrix.counts?.stubborn_losers ?? 0 }}
                          </div>
                          <div class="text-xs font-mono text-red-400 mt-0.5">
                            <SensitiveValue>{{ fmtPnl(studyResult.block_d.conviction_matrix.pnl?.stubborn_losers, studyResult.meta?.currency) }}</SensitiveValue>
                          </div>
                          <div class="mt-2 space-y-0.5">
                            <div v-for="pos in (studyResult.block_d.conviction_matrix.quadrants?.stubborn_losers || []).slice(0,3)"
                              :key="pos.isin" class="text-[9px] flex justify-between text-slate-500">
                              <span class="truncate max-w-[65%]"><SensitiveValue mode="blur">{{ pos.name }}</SensitiveValue></span>
                              <span class="font-mono text-red-500/70"><SensitiveValue>{{ fmtPnl(pos.total_pnl) }}</SensitiveValue></span>
                            </div>
                          </div>
                        </div>
                        <!-- Bottom-right: uncertainty -->
                        <div class="p-3 bg-amber-950/20">
                          <div class="text-[10px] font-bold text-amber-400 mb-1">⚠ Positions d'incertitude</div>
                          <div class="text-[9px] text-slate-600 mb-2">Faible conviction · perte réalisée</div>
                          <div class="text-2xl font-black text-amber-400 leading-none">
                            {{ studyResult.block_d.conviction_matrix.counts?.uncertainty ?? 0 }}
                          </div>
                          <div class="text-xs font-mono text-amber-400 mt-0.5">
                            <SensitiveValue>{{ fmtPnl(studyResult.block_d.conviction_matrix.pnl?.uncertainty, studyResult.meta?.currency) }}</SensitiveValue>
                          </div>
                          <div class="mt-2 space-y-0.5">
                            <div v-for="pos in (studyResult.block_d.conviction_matrix.quadrants?.uncertainty || []).slice(0,3)"
                              :key="pos.isin" class="text-[9px] flex justify-between text-slate-500">
                              <span class="truncate max-w-[65%]"><SensitiveValue mode="blur">{{ pos.name }}</SensitiveValue></span>
                              <span class="font-mono text-red-500/70"><SensitiveValue>{{ fmtPnl(pos.total_pnl) }}</SensitiveValue></span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Auto-interprétation -->
                  <div class="mt-4 text-[11px] text-slate-400 leading-5 border-t border-slate-800 pt-3">
                    <template v-if="studyResult.block_d.conviction_matrix.counts">
                      {{
                        (() => {
                          const c = studyResult.block_d.conviction_matrix.counts
                          const p = studyResult.block_d.conviction_matrix.pnl
                          const total = (c.conviction_winners||0) + (c.tactical_winners||0) + (c.stubborn_losers||0) + (c.uncertainty||0)
                          const winners = (c.conviction_winners||0) + (c.tactical_winners||0)
                          const losers  = (c.stubborn_losers||0)  + (c.uncertainty||0)
                          const pctUncert = total > 0 ? Math.round((c.uncertainty||0)/total*100) : 0
                          const pctConvWin = total > 0 ? Math.round((c.conviction_winners||0)/total*100) : 0
                          let msg = `Sur ${total} positions clôturées : ${winners} gagnantes (${Math.round(winners/Math.max(total,1)*100)}%), ${losers} perdantes. `
                          if (pctConvWin >= 30) msg += `Bon signal : ${pctConvWin}% des positions sont des paris gagnants avec forte conviction. `
                          if (pctUncert > 40) msg += `⚠ Attention : ${pctUncert}% des positions sont en zone d'incertitude (faible conviction + perte) — signal de prises de décision non structurées. `
                          else if (pctUncert < 20) msg += `Le taux d'incertitude (${pctUncert}%) est faible — signe d'un processus de décision discipliné. `
                          if ((c.stubborn_losers||0) > 0 && (p?.stubborn_losers||0) < -50000) msg += `Les entêtements coûteux (forte conviction malgré pertes) représentent ${fmtPnl(p?.stubborn_losers)} — biais comportemental à surveiller. `
                          return msg
                        })()
                      }}
                    </template>
                  </div>
                </div>

                <!-- Order hygiene -->
                <div class="grid grid-cols-2 gap-5">
                  <div class="card">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Hygiène des ordres</div>
                    <table class="w-full text-xs">
                      <tr v-for="([k,v,tip]) in [
                        ['Done', studyResult.block_d.order_hygiene?.n_done ?? '—', 'Ordres avec état Done (exécutés). Seuls ceux-ci entrent dans les calculs de P&L et de turnover.'],
                        ['Discarded', studyResult.block_d.order_hygiene?.n_discarded ?? '—', 'Ordres annulés ou rejetés. Ils ne génèrent pas de P&L mais signalent de l\'hésitation ou des difficultés d\'exécution.'],
                        ['Ratio annulation', formatPercent(studyResult.block_d.order_hygiene?.discarded_ratio_pct ?? 0, 1), 'Discarded / (Done + Discarded). >15% est un signal d\'alerte de qualité d\'exécution ou d\'indécision.'],
                        ['Fills partiels', studyResult.block_d.order_hygiene?.n_partial_fills ?? '—', 'Ordres partiellement exécutés. Indique des difficultés de liquidité ou des ordres à limite non totalement remplis.'],
                      ]" :key="k" class="border-b border-slate-800/50">
                        <td class="py-1.5 text-slate-500">
                          <span class="inline-flex items-center gap-1">{{ k }}
                            <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-0 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ tip }}</span></span>
                          </span>
                        </td>
                        <td class="py-1.5 text-right text-slate-300 font-mono">{{ v }}</td>
                      </tr>
                    </table>
                  </div>
                  <div v-if="studyResult.block_d.order_hygiene?.discarded_top?.length" class="card">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Top annulations</div>
                    <div v-for="r in studyResult.block_d.order_hygiene.discarded_top.slice(0,6)" :key="r.name"
                      class="flex justify-between text-xs py-1 border-b border-slate-800/50">
                      <span class="text-slate-400 truncate max-w-[70%]">{{ r.name }}</span>
                      <span class="text-amber-400 font-mono">{{ r.discarded }}×</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- E — RÉFÉRENTIEL INERTIEL -->
              <div v-if="activeStudyTab === 'bh'" class="flex flex-col gap-5">
                <!-- Période -->
                <div v-if="studyResult.meta?.nav_start_date" class="text-[10px] text-slate-500 -mb-2">
                  Période B&amp;H : {{ formatDate(studyResult.meta.nav_start_date) }} → {{ formatDate(studyResult.meta.nav_current_date) }}
                  · {{ studyResult.meta.nav_n_obs }} observations NAV
                </div>

                <!-- Not available -->
                <div v-if="!studyResult.block_e?.available" class="card">
                  <div class="text-amber-400 text-xs font-semibold mb-1">⚠ Référentiel Inertiel non disponible</div>
                  <div class="text-slate-500 text-xs">{{ studyResult.block_e?.error ?? 'Données insuffisantes.' }}</div>
                </div>

                <template v-else>

                  <!-- Price quality warning (informational only) -->
                  <div v-if="studyResult.block_e.n_price_warnings > 0"
                    class="rounded-lg border border-amber-700/40 bg-amber-950/15 px-4 py-2.5 text-[11px] text-amber-300/80">
                    ⚠ {{ studyResult.block_e.n_price_warnings }} position(s) avec prix yfinance T0 potentiellement incorrect —
                    incluses dans le calcul mais signalées dans le tableau ci-dessous.
                  </div>

                  <!-- Source badge + explanation -->
                  <div class="card border border-slate-700/50 text-xs text-slate-400 leading-5">
                    <div class="flex items-center gap-3 mb-2">
                      <div class="font-semibold text-slate-300">💡 Référentiel Inertiel (Bloc E)</div>
                      <span v-if="studyResult.block_e.source === 'termsheet'"
                        class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-900/40 text-emerald-400 border border-emerald-700/40">
                        ✓ Term sheet · {{ formatInt(studyResult.block_e.n_certs) }} certificats
                      </span>
                      <span v-else
                        class="text-[10px] px-2 py-0.5 rounded-full bg-amber-900/40 text-amber-400 border border-amber-700/40">
                        ⚠ Identité comptable (fallback)
                      </span>
                    </div>
                    Ce bloc répond à la question :
                    <strong class="text-slate-200">« Si le gérant n'avait rien fait depuis l'émission, quelle serait la performance aujourd'hui ? »</strong>
                    <br/><br/>
                    Le portefeuille initial de la term sheet est maintenu sans aucun trade depuis le lancement.
                    <strong>VAG = NAV réelle − Référentiel Inertiel.</strong>
                    <br/><br/>
                    <span :class="studyResult.block_e.value_added_pct >= 0 ? 'text-emerald-400' : 'text-amber-400'">
                      VAG <strong>positif</strong> → le gérant a créé de la valeur vs l'inertie totale.
                      VAG <strong>négatif</strong> → l'inertie depuis l'émission aurait été préférable.
                    </span>
                  </div>

                  <!-- KPI row -->
                  <div class="grid grid-cols-3 gap-3">
                    <div class="card border border-blue-800/40 text-center">
                      <div class="text-2xl font-bold"
                        :class="studyResult.block_e.bh_perf_pct >= 0 ? 'text-blue-400' : 'text-red-400'">
                        {{ studyResult.block_e.bh_perf_pct >= 0 ? '+' : '' }}{{ formatPercent(studyResult.block_e.bh_perf_pct, 1) }}
                      </div>
                      <div class="text-[10px] text-slate-500 mt-1">Référentiel Inertiel</div>
                      <div class="text-xs text-slate-400 font-mono mt-0.5">{{ formatNumber(studyResult.block_e.bh_nav, 2) }}</div>
                    </div>
                    <div class="card border border-slate-700/40 text-center">
                      <div class="text-2xl font-bold"
                        :class="studyResult.block_e.actual_perf_pct >= 0 ? 'text-emerald-400' : 'text-red-400'">
                        {{ studyResult.block_e.actual_perf_pct >= 0 ? '+' : '' }}{{ formatPercent(studyResult.block_e.actual_perf_pct, 1) }}
                      </div>
                      <div class="text-[10px] text-slate-500 mt-1">NAV réelle (gestion active)</div>
                      <div class="text-xs text-slate-400 font-mono mt-0.5">{{ formatNumber(studyResult.block_e.actual_nav, 2) }}</div>
                    </div>
                    <div class="card text-center"
                      :class="studyResult.block_e.value_added_pct >= 0
                        ? 'border border-emerald-800/50 bg-emerald-950/20'
                        : 'border border-red-800/50 bg-red-950/20'">
                      <div class="text-2xl font-bold"
                        :class="studyResult.block_e.value_added_pct >= 0 ? 'text-emerald-400' : 'text-red-400'">
                        {{ studyResult.block_e.value_added_pct >= 0 ? '+' : '' }}{{ formatPercent(studyResult.block_e.value_added_pct, 2) }}
                      </div>
                      <div class="text-[10px] text-slate-500 mt-1">Valeur ajoutée par la gestion</div>
                      <div class="text-[10px] mt-1"
                        :class="studyResult.block_e.value_added_pct >= 0 ? 'text-emerald-500' : 'text-red-500'">
                        {{ studyResult.block_e.value_added_pct >= 0
                          ? 'Le gérant a créé de la valeur'
                          : "L'inertie aurait été préférable" }}
                      </div>
                    </div>
                  </div>

                  <!-- Positions table -->
                  <div class="card border border-slate-700/50">
                    <div class="text-xs font-semibold text-slate-300 mb-3">
                      Référentiel Inertiel — composition initiale ({{ studyResult.block_e.n_positions }} sous-jacents)
                    </div>
                    <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                      <table class="w-full text-xs">
                        <thead>
                          <tr class="text-[10px] text-slate-500 uppercase tracking-wider border-b border-slate-700">
                            <th class="text-left py-2 pr-3">Sous-jacent</th>
                            <th class="text-right py-2 px-2">Poids T0</th>
                            <th class="text-right py-2 px-2">Retour total</th>
                            <th class="text-right py-2 px-2">Contribution</th>
                            <th class="text-right py-2 pl-2">Source T0</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="pos in studyResult.block_e.positions" :key="pos.isin"
                            class="border-b border-slate-800/50 hover:bg-slate-800/30"
                            :class="pos.coherence_warning ? 'bg-amber-950/10' : ''">
                            <td class="py-1.5 pr-3">
                              <div class="text-slate-200 flex items-center gap-1">
                                {{ pos.name }}
                                <span v-if="pos.coherence_warning"
                                  class="group relative inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-amber-900/60 text-amber-400 text-[8px] cursor-help shrink-0">
                                  ?<span class="pointer-events-none absolute bottom-full left-0 mb-1.5 w-64 bg-slate-900 border border-amber-800/50 text-amber-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ pos.coherence_warning }}</span>
                                </span>
                              </div>
                              <div class="text-[10px] text-slate-600 font-mono">{{ pos.isin }}</div>
                            </td>
                            <td class="text-right px-2 text-slate-300 font-mono">{{ formatPercent(pos.initial_weight_pct, 1) }}</td>
                            <td class="text-right px-2 font-mono font-semibold"
                              :class="pos.coherence_warning ? 'text-amber-400' : pos.total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'">
                              {{ pos.total_return_pct >= 0 ? '+' : '' }}{{ formatPercent(pos.total_return_pct, 1) }}
                              <span v-if="pos.coherence_warning" class="text-[9px] text-amber-600/80 ml-0.5">⚠</span>
                            </td>
                            <td class="text-right px-2 font-mono"
                              :class="pos.bh_contribution_pts >= 0 ? 'text-emerald-300' : 'text-red-300'">
                              {{ pos.bh_contribution_pts >= 0 ? '+' : '' }}{{ formatNumber(pos.bh_contribution_pts, 2) }} pts
                            </td>
                            <td class="text-right pl-2 text-slate-600 text-[10px]">{{ pos.initial_price_source }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <!-- Methodology -->
                  <div class="text-[10px] text-slate-600 leading-4 border-t border-slate-800/50 pt-2">
                    <span class="text-slate-500 font-semibold">Méthodologie :</span>
                    {{ studyResult.block_e.methodology }}
                  </div>
                </template>
              </div>

              <!-- TIMING SCORE -->
              <div v-if="activeStudyTab === 'timing'" class="flex flex-col gap-5">
                <!-- Période -->
                <div v-if="studyResult.meta?.nav_start_date" class="text-[10px] text-slate-500 -mb-2">
                  Période d'étude : {{ formatDate(studyResult.meta.nav_start_date) }} → {{ formatDate(studyResult.meta.nav_current_date) }}
                  · {{ formatInt(studyResult.block_h?.n_trades_total ?? studyResult.meta.n_orders) }} ordres
                  · couverture {{ formatPercent(studyResult.block_h?.coverage_pct ?? 0, 0) }}
                </div>
                <template v-if="studyResult.block_h">

                  <!-- Unavailable -->
                  <div v-if="!studyResult.block_h.available" class="card">
                    <div class="text-amber-400 text-xs mb-2">⚠ {{ studyResult.block_h.error }}</div>
                    <div class="text-slate-600 text-xs">
                      Chargez les séries de prix des sous-jacents dans le module
                      <strong class="text-slate-400">onglet Sous-jacents</strong>
                      pour activer le Timing Score.
                    </div>
                    <!-- trades without prices -->
                    <div v-if="studyResult.block_h.trades?.length" class="mt-3">
                      <div class="text-[10px] text-slate-600 mb-1">Ordres sans données de prix :</div>
                      <div v-for="t in studyResult.block_h.trades.slice(0,8)" :key="t.date+t.name"
                        class="text-[10px] text-slate-700 font-mono">
                        {{ formatDate(t.date) }} {{ t.side }} {{ t.name }} — {{ t.reason }}
                      </div>
                    </div>
                  </div>

                  <template v-else>
                    <!-- Warning -->
                    <div v-if="studyResult.block_h.warning" class="text-amber-400 text-xs px-1">
                      ⚠ {{ studyResult.block_h.warning }}
                    </div>

                    <!-- KPI row -->
                    <div class="grid grid-cols-4 gap-3">
                      <div v-for="kpi in [
                        { label: 'Score Entrées', value: studyResult.block_h.entry_score_mean, sub: studyResult.block_h.n_buy + ' BUY',
                          tip: 'Entry Score (achats). 1.0 = acheté exactement au plus bas local sur ±30 j. 0.5 = trader aléatoire. Formule : (max_local − prix_achat) / (max_local − min_local).' },
                        { label: 'Score Sorties', value: studyResult.block_h.exit_score_mean,  sub: studyResult.block_h.n_sell + ' SELL',
                          tip: 'Exit Score (ventes). 1.0 = vendu exactement au plus haut local sur ±30 j. 0.5 = trader aléatoire. Formule : (prix_vente − min_local) / (max_local − min_local).' },
                        { label: 'Score Global',  value: studyResult.block_h.global_score_mean, sub: 'baseline = 0.50',
                          tip: 'Moyenne de tous les scores (achats + ventes). Baseline aléatoire = 0.50. Un t-test (one-sample, µ₀=0.5) évalue si l\'écart est statistiquement significatif.' },
                        { label: 'Couverture',    value: null, raw: formatPercent(studyResult.block_h.coverage_pct, 0), sub: studyResult.block_h.n_trades_analyzed + '/' + studyResult.block_h.n_trades_total + ' trades',
                          tip: '% des ordres pour lesquels un historique de prix était disponible dans le Price Store. Couverture faible = résultats indicatifs uniquement. Chargez les prix via l\'onglet Sous-jacents.' },
                      ]" :key="kpi.label"
                        class="card text-center py-4">
                        <div class="text-2xl font-black mb-1"
                          :class="kpi.value === null ? 'text-slate-400'
                            : kpi.value >= 0.60 ? 'text-emerald-400'
                            : kpi.value >= 0.45 ? 'text-amber-400' : 'text-red-400'">
                          {{ kpi.raw ?? formatNumber(kpi.value, 3) }}
                        </div>
                        <div class="text-[10px] text-slate-500 uppercase tracking-wider flex items-center justify-center gap-1">
                          {{ kpi.label }}
                          <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ kpi.tip }}</span></span>
                        </div>
                        <div class="text-[9px] text-slate-600 mt-0.5">{{ kpi.sub }}</div>
                      </div>
                    </div>

                    <!-- Stats table -->
                    <div class="card">
                      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Statistiques</div>
                      <table class="w-full text-xs">
                        <thead>
                          <tr class="text-slate-600 text-[10px] border-b border-slate-800">
                            <th class="text-left pb-2">Métrique</th>
                            <th class="text-right pb-2" title="Score de timing des achats (BUY) uniquement.">Entrées (BUY)</th>
                            <th class="text-right pb-2" title="Score de timing des ventes (SELL) uniquement.">Sorties (SELL)</th>
                            <th class="text-right pb-2" title="Moyenne de tous les trades (achats + ventes). C'est sur ce score que le t-test est effectué.">Global</th>
                          </tr>
                        </thead>
                        <tbody class="text-slate-300">
                          <tr class="border-b border-slate-900">
                            <td class="py-1.5 text-slate-500" title="Score moyen de timing sur la dimension. 1.0 = timing parfait, 0.5 = trader aléatoire, 0.0 = pire timing possible.">Score moyen</td>
                            <td class="text-right font-mono">{{ formatNumber(studyResult.block_h.entry_score_mean, 3) }}</td>
                            <td class="text-right font-mono">{{ formatNumber(studyResult.block_h.exit_score_mean, 3) }}</td>
                            <td class="text-right font-mono">{{ formatNumber(studyResult.block_h.global_score_mean, 3) }}</td>
                          </tr>
                          <tr class="border-b border-slate-900">
                            <td class="py-1.5 text-slate-500" title="Score moyen − 0.500. Positif = meilleur que le hasard, négatif = moins bon. Un écart de 0.05+ peut être significatif si l'échantillon est suffisant.">vs hasard (0.500)</td>
                            <td class="text-right font-mono"
                              :class="(studyResult.block_h.entry_score_mean ?? 0.5) >= 0.5 ? 'text-emerald-400' : 'text-red-400'">
                              {{ studyResult.block_h.entry_score_mean != null ? ((studyResult.block_h.entry_score_mean - 0.5) >= 0 ? '+' : '') + formatNumber(studyResult.block_h.entry_score_mean - 0.5, 3) : '—' }}
                            </td>
                            <td class="text-right font-mono"
                              :class="(studyResult.block_h.exit_score_mean ?? 0.5) >= 0.5 ? 'text-emerald-400' : 'text-red-400'">
                              {{ studyResult.block_h.exit_score_mean != null ? ((studyResult.block_h.exit_score_mean - 0.5) >= 0 ? '+' : '') + formatNumber(studyResult.block_h.exit_score_mean - 0.5, 3) : '—' }}
                            </td>
                            <td class="text-right font-mono"
                              :class="(studyResult.block_h.global_score_mean ?? 0.5) >= 0.5 ? 'text-emerald-400' : 'text-red-400'">
                              {{ studyResult.block_h.global_score_mean != null ? ((studyResult.block_h.global_score_mean - 0.5) >= 0 ? '+' : '') + formatNumber(studyResult.block_h.global_score_mean - 0.5, 3) : '—' }}
                            </td>
                          </tr>
                          <tr class="border-b border-slate-900">
                            <td class="py-1.5 text-slate-500" title="One-sample t-test vs µ₀=0.5 (baseline aléatoire). |t| > 1.96 = significatif à 5%. Positif = score supérieur à 0.5. Puissance faible si n < 20 trades.">t-stat (vs µ₀=0.5)</td>
                            <td class="text-right font-mono">{{ formatNumber(studyResult.block_h.tstat_entry, 3) }}</td>
                            <td class="text-right font-mono">{{ formatNumber(studyResult.block_h.tstat_exit, 3) }}</td>
                            <td class="text-right font-mono">{{ formatNumber(studyResult.block_h.tstat_global, 3) }}</td>
                          </tr>
                          <tr>
                            <td class="py-1.5 text-slate-500" title="Probabilité d'obtenir ce score si le gérant n'avait aucune compétence de timing (H₀ : µ = 0.5). p &lt; 0.05 = rejet de H₀ à 5%. Calculé uniquement sur le score global (tous trades).">p-value global</td>
                            <td class="text-right text-slate-600">—</td>
                            <td class="text-right text-slate-600">—</td>
                            <td class="text-right font-mono">{{ formatNumber(studyResult.block_h.pvalue_global, 4) }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>

                    <!-- Interpretation -->
                    <div v-if="studyResult.block_h.interpretation" class="card border border-slate-700">
                      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Interprétation automatique</div>
                      <div class="text-sm text-slate-200 leading-relaxed">{{ studyResult.block_h.interpretation }}</div>
                    </div>

                    <!-- Pattern cards -->
                    <div class="grid grid-cols-2 gap-3">
                      <div v-for="pattern in [
                        { key: 'near_lows_buys',   label: 'Achats près des plus bas',    color: 'emerald', icon: '✓', desc: 'score ≥ 0.70' },
                        { key: 'near_highs_buys',  label: 'Achats près des plus hauts',  color: 'red',     icon: '✗', desc: 'score ≤ 0.25' },
                        { key: 'near_highs_sells', label: 'Ventes bien timées',           color: 'emerald', icon: '✓', desc: 'score ≥ 0.70' },
                        { key: 'early_sells',       label: 'Ventes prématurées',           color: 'amber',   icon: '⚠', desc: 'score ≤ 0.30' },
                      ]" :key="pattern.key" class="card">
                        <div class="flex items-center justify-between mb-2">
                          <div class="text-xs font-semibold text-slate-300">{{ pattern.label }}</div>
                          <div class="text-[10px] font-mono px-1.5 py-0.5 rounded"
                            :class="`bg-${pattern.color}-950/40 text-${pattern.color}-400 border border-${pattern.color}-800/30`">
                            {{ (studyResult.block_h[pattern.key] || []).length }} trades · {{ pattern.desc }}
                          </div>
                        </div>
                        <div v-if="(studyResult.block_h[pattern.key] || []).length === 0"
                          class="text-slate-700 text-xs">Aucun</div>
                        <div v-for="t in (studyResult.block_h[pattern.key] || []).slice(0,5)" :key="t.date+t.name"
                          class="flex justify-between text-[10px] py-0.5 border-b border-slate-900 last:border-0">
                          <span class="text-slate-500 font-mono shrink-0 mr-2">{{ formatDate(t.date) }}</span>
                          <span class="text-slate-400 truncate flex-1"><SensitiveValue mode="blur">{{ t.name }}</SensitiveValue></span>
                          <span class="font-mono ml-2"
                            :class="t.score >= 0.60 ? 'text-emerald-400' : t.score < 0.40 ? 'text-red-400' : 'text-amber-400'">
                            {{ formatNumber(t.score, 3) }}
                          </span>
                        </div>
                      </div>
                    </div>

                    <!-- Full trades table -->
                    <div class="card">
                      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                        Détail des trades analysés
                        <span class="text-slate-600 font-normal ml-2">
                          ({{ (studyResult.block_h.trades || []).filter(t => t.available).length }} avec prix disponibles)
                        </span>
                      </div>
                      <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                        <table class="w-full text-[10px]">
                          <thead>
                            <tr class="text-slate-600 border-b border-slate-800">
                              <th class="text-left pb-1.5 pr-2">Date</th>
                              <th class="text-left pb-1.5 pr-2">Côté</th>
                              <th class="text-left pb-1.5 pr-2">Titre</th>
                              <th class="text-right pb-1.5 pr-2">Prix exec.</th>
                              <th class="text-right pb-1.5 pr-2">Min 30j</th>
                              <th class="text-right pb-1.5 pr-2">Max 30j</th>
                              <th class="text-right pb-1.5 pr-2">Score</th>
                              <th class="text-right pb-1.5">Verdict</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr v-for="t in (studyResult.block_h.trades || []).filter(t => t.available)"
                              :key="t.date+t.isin"
                              class="border-b border-slate-900 hover:bg-slate-800/30">
                              <td class="py-1 pr-2 font-mono text-slate-500">{{ formatDate(t.date) }}</td>
                              <td class="py-1 pr-2"
                                :class="t.side === 'BUY' ? 'text-blue-400' : 'text-orange-400'">
                                {{ t.side }}
                              </td>
                              <td class="py-1 pr-2 text-slate-300 max-w-[140px] truncate"><SensitiveValue mode="blur">{{ t.name }}</SensitiveValue></td>
                              <td class="py-1 pr-2 text-right font-mono text-slate-400">{{ formatNumber(t.price_local, 3) }}</td>
                              <td class="py-1 pr-2 text-right font-mono text-slate-600">{{ formatNumber(t.price_min_window, 3) }}</td>
                              <td class="py-1 pr-2 text-right font-mono text-slate-600">{{ formatNumber(t.price_max_window, 3) }}</td>
                              <td class="py-1 pr-2 text-right font-mono font-bold"
                                :class="t.score >= 0.60 ? 'text-emerald-400' : t.score < 0.40 ? 'text-red-400' : 'text-amber-400'">
                                {{ formatNumber(t.score, 3) }}
                              </td>
                              <td class="py-1 text-right"
                                :class="t.score >= 0.60 ? 'text-emerald-400' : t.score < 0.40 ? 'text-red-400' : 'text-amber-400'">
                                {{ t.label }}
                              </td>
                            </tr>
                            <!-- Unavailable trades -->
                            <tr v-for="t in (studyResult.block_h.trades || []).filter(t => !t.available)"
                              :key="t.date+t.isin+'na'"
                              class="border-b border-slate-900 opacity-40">
                              <td class="py-1 pr-2 font-mono text-slate-600">{{ formatDate(t.date) }}</td>
                              <td class="py-1 pr-2 text-slate-600">{{ t.side }}</td>
                              <td class="py-1 pr-2 text-slate-600 max-w-[140px] truncate">{{ t.name }}</td>
                              <td colspan="5" class="py-1 text-right text-slate-700 italic">{{ t.reason }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </template>

                </template>
                <div v-else class="card text-slate-600 text-sm text-center py-8">
                  Lancez une étude pour afficher le Timing Score.
                </div>
              </div>

              <!-- STOCK PICKING SCORE -->
              <div v-if="activeStudyTab === 'stockpicking'" class="flex flex-col gap-5">
                <!-- Période -->
                <div v-if="studyResult.meta?.nav_start_date" class="text-[10px] text-slate-500 -mb-2">
                  Période d'étude : {{ formatDate(studyResult.meta.nav_start_date) }} → {{ formatDate(studyResult.meta.nav_current_date) }}
                  · {{ studyResult.block_i?.n_buys_analyzed ?? '—' }} achats analysés
                  · couverture {{ formatPercent(studyResult.block_i?.coverage_pct ?? 0, 0) }}
                </div>
                <template v-if="studyResult.block_i">

                  <!-- Unavailable -->
                  <div v-if="!studyResult.block_i.available" class="card">
                    <div class="text-amber-400 text-xs mb-2">⚠ {{ studyResult.block_i.error }}</div>
                    <div class="text-slate-600 text-xs">
                      Chargez les séries de prix des sous-jacents dans le module
                      <strong class="text-slate-400">onglet Sous-jacents</strong>
                      pour activer le Stock Picking Score.
                    </div>
                    <div v-if="studyResult.block_i.trades?.length" class="mt-3">
                      <div class="text-[10px] text-slate-600 mb-1">Achats sans données de prix :</div>
                      <div v-for="t in studyResult.block_i.trades.slice(0,8)" :key="t.date+t.name"
                        class="text-[10px] text-slate-700 font-mono">
                        {{ formatDate(t.date) }} BUY {{ t.name }} — {{ t.reason }}
                      </div>
                    </div>
                  </div>

                  <template v-else>
                    <!-- Warning -->
                    <div v-if="studyResult.block_i.warning" class="text-amber-400 text-xs px-1">
                      ⚠ {{ studyResult.block_i.warning }}
                    </div>

                    <!-- Score + KPI row -->
                    <div class="grid grid-cols-4 gap-3">
                      <div class="card text-center py-4 col-span-1">
                        <div class="text-4xl font-black mb-1"
                          :class="studyResult.block_i.score >= 60 ? 'text-emerald-400'
                            : studyResult.block_i.score >= 45 ? 'text-amber-400' : 'text-red-400'">
                          {{ studyResult.block_i.score }}
                        </div>
                        <div class="text-[10px] text-slate-500 uppercase tracking-wider flex items-center justify-center gap-1">
                          Score /100
                          <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-60 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">Score composite 0-100 = 40% × alpha moyen + 35% × taux de succès + 25% × information ratio. 60+ = bon, 45-60 = neutre, &lt;45 = faible.</span></span>
                        </div>
                        <div class="text-[9px] text-slate-600 mt-0.5">{{ studyResult.block_i.score_label }}</div>
                      </div>
                      <div v-for="kpi in [
                        { label: 'Alpha moyen', value: null, raw: formatPercent((studyResult.block_i.global_alpha_mean ?? 0) * 100, 2), sub: 'benchmark-adjusted', positive: (studyResult.block_i.global_alpha_mean ?? 0) >= 0,
                          tip: 'Alpha moyen global pondéré par horizon (poids : 1M×15%, 3M×25%, 6M×30%, 12M×30%). Positif = sélection surperforme le benchmark en moyenne post-achat.' },
                        { label: 'Taux de succès', value: null, raw: formatPercent((studyResult.block_i.global_success_rate ?? 0) * 100, 0), sub: '% achats α > 0', positive: (studyResult.block_i.global_success_rate ?? 0) >= 0.5,
                          tip: '% des achats pour lesquels le titre a surperformé le benchmark sur au moins un horizon. 50% = aléatoire. >60% = compétence de sélection.' },
                        { label: 'Couverture', value: null, raw: formatPercent(studyResult.block_i.coverage_pct ?? 0, 0), sub: studyResult.block_i.n_buys_analyzed + '/' + studyResult.block_i.n_buys_total + ' achats', positive: true,
                          tip: '% des ordres BUY pour lesquels un historique de prix était disponible dans le Price Store.' },
                      ]" :key="kpi.label"
                        class="card text-center py-4">
                        <div class="text-2xl font-black mb-1"
                          :class="kpi.positive ? 'text-emerald-400' : 'text-red-400'">
                          {{ kpi.raw }}
                        </div>
                        <div class="text-[10px] text-slate-500 uppercase tracking-wider flex items-center justify-center gap-1">
                          {{ kpi.label }}
                          <span class="group relative inline-flex items-center justify-center w-3 h-3 rounded-full bg-slate-700/80 text-[8px] cursor-help shrink-0">?<span class="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-56 bg-slate-900 border border-slate-700 text-slate-300 text-[10px] leading-relaxed rounded-lg p-2 z-[100] shadow-2xl whitespace-normal text-left font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity">{{ kpi.tip }}</span></span>
                        </div>
                        <div class="text-[9px] text-slate-600 mt-0.5">{{ kpi.sub }}</div>
                      </div>
                    </div>

                    <!-- Per-horizon stats table -->
                    <div class="card">
                      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Alpha par horizon</div>
                      <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                        <table class="w-full text-xs">
                          <thead>
                            <tr class="text-slate-600 text-[10px] border-b border-slate-800">
                              <th class="text-left pb-2">Horizon</th>
                              <th class="text-right pb-2" title="Nombre d'achats pour lesquels les données de prix sont disponibles sur cet horizon.">n achats</th>
                              <th class="text-right pb-2" title="Alpha moyen = moyenne(Retour titre − Retour benchmark) sur tous les achats analysés à cet horizon.">Alpha moyen</th>
                              <th class="text-right pb-2" title="Médiane des alphas — moins sensible aux outliers que la moyenne.">Alpha médian</th>
                              <th class="text-right pb-2" title="% des achats avec alpha positif (titre surperforme le benchmark post-achat). 50% = aléatoire.">Taux succès</th>
                              <th class="text-right pb-2" title="Écart-type des alphas à cet horizon. Mesure la dispersion de la compétence de sélection.">σ alpha</th>
                            </tr>
                          </thead>
                          <tbody class="text-slate-300">
                            <tr v-for="h in ['1M','3M','6M','12M']" :key="h"
                              class="border-b border-slate-900">
                              <template v-if="studyResult.block_i.stats_by_horizon?.[h]?.available">
                                <td class="py-1.5 font-semibold text-slate-400">{{ h }}</td>
                                <td class="text-right font-mono">{{ studyResult.block_i.stats_by_horizon[h].n }}</td>
                                <td class="text-right font-mono font-bold"
                                  :class="studyResult.block_i.stats_by_horizon[h].alpha_mean >= 0 ? 'text-emerald-400' : 'text-red-400'">
                                  {{ formatPercent((studyResult.block_i.stats_by_horizon[h].alpha_mean ?? 0) * 100, 2) }}
                                </td>
                                <td class="text-right font-mono"
                                  :class="studyResult.block_i.stats_by_horizon[h].alpha_median >= 0 ? 'text-emerald-400' : 'text-red-400'">
                                  {{ formatPercent((studyResult.block_i.stats_by_horizon[h].alpha_median ?? 0) * 100, 2) }}
                                </td>
                                <td class="text-right font-mono"
                                  :class="studyResult.block_i.stats_by_horizon[h].success_rate >= 0.5 ? 'text-emerald-400' : 'text-red-400'">
                                  {{ formatPercent((studyResult.block_i.stats_by_horizon[h].success_rate ?? 0) * 100, 0) }}
                                </td>
                                <td class="text-right font-mono text-slate-500">
                                  {{ formatPercent((studyResult.block_i.stats_by_horizon[h].alpha_std ?? 0) * 100, 2) }}
                                </td>
                              </template>
                              <template v-else>
                                <td class="py-1.5 font-semibold text-slate-600">{{ h }}</td>
                                <td colspan="5" class="text-right text-slate-700 italic text-[10px]">données insuffisantes</td>
                              </template>
                            </tr>
                            <!-- Global row -->
                            <tr class="border-t border-slate-700 font-semibold">
                              <td class="py-1.5 text-slate-300">Global pondéré</td>
                              <td class="text-right font-mono text-slate-400">{{ formatInt(studyResult.block_i.n_buys_analyzed) }}</td>
                              <td class="text-right font-mono font-bold"
                                :class="(studyResult.block_i.global_alpha_mean ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                                {{ formatPercent((studyResult.block_i.global_alpha_mean ?? 0) * 100, 2) }}
                              </td>
                              <td class="text-right text-slate-600">—</td>
                              <td class="text-right font-mono text-blue-400">
                                {{ formatPercent((studyResult.block_i.global_success_rate ?? 0) * 100, 0) }}
                              </td>
                              <td class="text-right font-mono text-slate-500"
                                title="Information Ratio = alpha moyen / écart-type alpha. IR > 0.5 est considéré bon.">
                                IR={{ formatNumber(studyResult.block_i.information_ratio ?? 0, 2) }}
                              </td>
                            </tr>
                            <!-- t-stat row -->
                            <tr>
                              <td class="py-1.5 text-slate-600 text-[10px]" title="Test t one-sample vs µ₀=0 (H₀ : alpha moyen = 0). |t| > 1.96 = significatif à 5%.">t-stat / p-value</td>
                              <td colspan="5" class="text-right font-mono text-[10px] text-slate-600">
                                t={{ formatNumber(studyResult.block_i.tstat_alpha ?? 0, 3) }}
                                · p={{ formatNumber(studyResult.block_i.pvalue_alpha ?? 1, 4) }}
                                · benchmark : {{ studyResult.block_i.benchmark_ticker }}
                                <span v-if="!studyResult.block_i.benchmark_available" class="text-amber-600 ml-1">(indisponible — retour brut)</span>
                              </td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>

                    <!-- Interpretation -->
                    <div v-if="studyResult.block_i.interpretation" class="card border border-slate-700">
                      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">Interprétation automatique</div>
                      <div class="text-sm text-slate-200 leading-relaxed">{{ studyResult.block_i.interpretation }}</div>
                    </div>

                    <!-- Best / worst ideas -->
                    <div class="grid grid-cols-2 gap-3">
                      <div v-for="section in [
                        { key: 'best_ideas',  label: 'Meilleures idées',  color: 'emerald', icon: '✓', desc: 'alpha pondéré le plus élevé' },
                        { key: 'worst_ideas', label: 'Pires idées',       color: 'red',     icon: '✗', desc: 'alpha pondéré le plus faible' },
                      ]" :key="section.key" class="card">
                        <div class="flex items-center justify-between mb-2">
                          <div class="text-xs font-semibold text-slate-300">{{ section.label }}</div>
                          <div class="text-[10px] font-mono px-1.5 py-0.5 rounded"
                            :class="`bg-${section.color}-950/40 text-${section.color}-400 border border-${section.color}-800/30`">
                            {{ section.desc }}
                          </div>
                        </div>
                        <div v-if="!(studyResult.block_i[section.key] || []).length"
                          class="text-slate-700 text-xs">Aucune donnée</div>
                        <div v-for="t in (studyResult.block_i[section.key] || []).slice(0,5)"
                          :key="t.date+t.name"
                          class="flex justify-between items-center text-[10px] py-0.5 border-b border-slate-900 last:border-0">
                          <span class="text-slate-500 font-mono shrink-0 mr-2">{{ formatDate(t.date) }}</span>
                          <span class="text-slate-400 truncate flex-1"><SensitiveValue mode="blur">{{ t.name }}</SensitiveValue></span>
                          <span class="font-mono ml-2 font-bold"
                            :class="(t.alpha_weighted ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                            {{ formatPercent((t.alpha_weighted ?? 0) * 100, 1) }}
                          </span>
                        </div>
                      </div>
                    </div>

                    <!-- Full trades table -->
                    <div class="card">
                      <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">
                        Détail des achats analysés
                        <span class="text-slate-600 font-normal ml-2">
                          ({{ (studyResult.block_i.trades || []).filter(t => t.available).length }} avec prix disponibles)
                        </span>
                      </div>
                      <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                        <table class="w-full text-[10px]">
                          <thead>
                            <tr class="text-slate-600 border-b border-slate-800">
                              <th class="text-left pb-1.5 pr-2">Date</th>
                              <th class="text-left pb-1.5 pr-2">Titre</th>
                              <th class="text-right pb-1.5 pr-2" title="Alpha à 1 mois (≈21 jours de trading) post-achat.">α 1M</th>
                              <th class="text-right pb-1.5 pr-2" title="Alpha à 3 mois post-achat.">α 3M</th>
                              <th class="text-right pb-1.5 pr-2" title="Alpha à 6 mois post-achat.">α 6M</th>
                              <th class="text-right pb-1.5 pr-2" title="Alpha à 12 mois post-achat.">α 12M</th>
                              <th class="text-right pb-1.5" title="Alpha pondéré sur tous les horizons disponibles (1M×15%+3M×25%+6M×30%+12M×30%).">α pondéré</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr v-for="t in (studyResult.block_i.trades || []).filter(t => t.available)"
                              :key="t.date+t.isin"
                              class="border-b border-slate-900 hover:bg-slate-800/30">
                              <td class="py-1 pr-2 font-mono text-slate-500">{{ formatDate(t.date) }}</td>
                              <td class="py-1 pr-2 text-slate-300 max-w-[140px] truncate"><SensitiveValue mode="blur">{{ t.name }}</SensitiveValue></td>
                              <template v-for="h in ['1M','3M','6M','12M']" :key="h">
                                <td class="py-1 pr-2 text-right font-mono"
                                  :class="t.horizons?.[h]?.available
                                    ? (t.horizons[h].alpha >= 0 ? 'text-emerald-400' : 'text-red-400')
                                    : 'text-slate-700'">
                                  {{ t.horizons?.[h]?.available
                                    ? formatPercent((t.horizons[h].alpha ?? 0) * 100, 1)
                                    : '—' }}
                                </td>
                              </template>
                              <td class="py-1 text-right font-mono font-bold"
                                :class="(t.alpha_weighted ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                                {{ formatPercent((t.alpha_weighted ?? 0) * 100, 1) }}
                              </td>
                            </tr>
                            <!-- Unavailable -->
                            <tr v-for="t in (studyResult.block_i.trades || []).filter(t => !t.available)"
                              :key="t.date+t.isin+'na'"
                              class="border-b border-slate-900 opacity-40">
                              <td class="py-1 pr-2 font-mono text-slate-600">{{ formatDate(t.date) }}</td>
                              <td class="py-1 pr-2 text-slate-600 max-w-[140px] truncate">{{ t.name }}</td>
                              <td colspan="5" class="py-1 text-right text-slate-700 italic">{{ t.reason }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </template>

                </template>
                <div v-else class="card text-slate-600 text-sm text-center py-8">
                  Lancez une étude pour afficher le Stock Picking Score.
                </div>
              </div>

              <!-- ╔══════════════════════════════════════════════════════════╗ -->
              <!-- ║  J — RISK MANAGEMENT SCORE                               ║ -->
              <!-- ╚══════════════════════════════════════════════════════════╝ -->
              <div v-if="activeStudyTab === 'riskmanagement'" class="flex flex-col gap-5">
                <!-- Période -->
                <div v-if="studyResult.meta?.nav_start_date" class="text-[10px] text-slate-500 -mb-2">
                  Période d'étude : {{ formatDate(studyResult.meta.nav_start_date) }} → {{ formatDate(studyResult.meta.nav_current_date) }}
                  · {{ studyResult.block_j?.n_obs ?? studyResult.meta.nav_n_obs }} observations NAV
                </div>
                <template v-if="studyResult.block_j && studyResult.block_j.available">

                  <!-- Warning -->
                  <div v-if="studyResult.block_j.warning"
                       class="card border border-amber-500/30 text-amber-400 text-xs py-3 px-4">
                    ⚠ {{ studyResult.block_j.warning }}
                  </div>

                  <!-- Global score row -->
                  <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div class="card text-center col-span-2 md:col-span-1">
                      <div class="text-5xl font-black mb-1"
                        :class="studyResult.block_j.score >= 65 ? 'text-emerald-400' : studyResult.block_j.score >= 50 ? 'text-amber-400' : 'text-red-400'">
                        {{ studyResult.block_j.score }}
                      </div>
                      <div class="text-xs text-slate-400">Score /100</div>
                      <div class="text-xs font-semibold mt-1"
                        :class="studyResult.block_j.score >= 65 ? 'text-emerald-400' : studyResult.block_j.score >= 50 ? 'text-amber-400' : 'text-red-400'">
                        {{ studyResult.block_j.score_label }}
                      </div>
                    </div>
                    <div class="card text-center">
                      <div class="text-2xl font-bold text-slate-200">{{ studyResult.block_j.score_raw }}</div>
                      <div class="text-xs text-slate-400">Score brut</div>
                    </div>
                    <div class="card text-center">
                      <div class="text-2xl font-bold text-slate-200">{{ studyResult.block_j.reliability_cap }}<span class="text-sm text-slate-400">/100</span></div>
                      <div class="text-xs text-slate-400">Cap fiabilité</div>
                    </div>
                    <div class="card text-center">
                      <div class="text-2xl font-bold text-slate-200">{{ studyResult.block_j.n_obs }}</div>
                      <div class="text-xs text-slate-400">Observations</div>
                    </div>
                  </div>

                  <!-- Sub-score cards -->
                  <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                    <div v-for="(label, key) in {
                        risk_adjusted: 'Perf. ajustée',
                        drawdown:      'Drawdown',
                        downside_risk: 'Risque baissier',
                        concentration: 'Concentration',
                        factor_risk:   'Facteurs'
                      }" :key="key" class="card text-center">
                      <div class="text-2xl font-bold"
                        :class="(studyResult.block_j.sub_scores[key]?.score ?? 0) >= 65 ? 'text-emerald-400'
                               : (studyResult.block_j.sub_scores[key]?.score ?? 0) >= 50 ? 'text-amber-400'
                               : 'text-red-400'">
                        {{ studyResult.block_j.sub_scores[key]?.score ?? 'N/A' }}
                      </div>
                      <div class="text-xs text-slate-400">{{ label }}</div>
                      <div class="text-xs text-slate-500 mt-0.5">
                        {{ formatPercent((studyResult.block_j.weights[key] ?? 0) * 100, 0) }}
                      </div>
                    </div>
                  </div>

                  <!-- Risk-adjusted detail -->
                  <div v-if="studyResult.block_j.sub_scores.risk_adjusted" class="card">
                    <div class="text-xs font-semibold text-slate-400 mb-3">
                      Performance Ajustée du Risque
                      <span class="text-emerald-400 ml-2">score {{ studyResult.block_j.sub_scores.risk_adjusted.score }}</span>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
                      <div>
                        <div class="text-lg font-bold text-slate-200">
                          {{ formatNumber(studyResult.block_j.sub_scores.risk_adjusted.sharpe_ratio, 3) }}
                        </div>
                        <div class="text-xs text-slate-400 flex items-center justify-center gap-1">
                          Sharpe Ratio
                          <div class="relative group inline-block">
                            <span class="cursor-help text-slate-500 hover:text-slate-300">?</span>
                            <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 z-50 w-56 bg-slate-800 border border-slate-600 rounded p-2 text-xs text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                              Rendement excédentaire annualisé divisé par la volatilité annualisée. &gt;1 = bon.
                            </div>
                          </div>
                        </div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-slate-200">
                          {{ formatNumber(studyResult.block_j.sub_scores.risk_adjusted.sortino_ratio, 3) }}
                        </div>
                        <div class="text-xs text-slate-400">Sortino Ratio</div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-slate-200">
                          {{ formatNumber(studyResult.block_j.sub_scores.risk_adjusted.calmar_ratio, 3) }}
                        </div>
                        <div class="text-xs text-slate-400 flex items-center justify-center gap-1">
                          Calmar Ratio
                          <div class="relative group inline-block">
                            <span class="cursor-help text-slate-500 hover:text-slate-300">?</span>
                            <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 z-50 w-56 bg-slate-800 border border-slate-600 rounded p-2 text-xs text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                              Rendement annualisé / Drawdown maximum absolu.
                            </div>
                          </div>
                        </div>
                      </div>
                      <div v-if="studyResult.block_j.sub_scores.risk_adjusted.information_ratio != null">
                        <div class="text-lg font-bold text-slate-200">
                          {{ formatNumber(studyResult.block_j.sub_scores.risk_adjusted.information_ratio, 3) }}
                        </div>
                        <div class="text-xs text-slate-400">Information Ratio</div>
                      </div>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-3 gap-3 text-center mt-3"
                         v-if="studyResult.block_j.sub_scores.risk_adjusted.upside_capture_pct != null">
                      <div>
                        <div class="text-lg font-bold text-emerald-400">
                          {{ formatPercent(studyResult.block_j.sub_scores.risk_adjusted.upside_capture_pct, 1) }}
                        </div>
                        <div class="text-xs text-slate-400 flex items-center justify-center gap-1">
                          Capture hausse
                          <div class="relative group inline-block">
                            <span class="cursor-help text-slate-500 hover:text-slate-300">?</span>
                            <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 z-50 w-64 bg-slate-800 border border-slate-600 rounded p-2 text-xs text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                              Upside Capture = % de la hausse du benchmark capturée. Downside Capture = % de la baisse subi. Idéal : Upside &gt; 100%, Downside &lt; 100%.
                            </div>
                          </div>
                        </div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-red-400">
                          {{ formatPercent(studyResult.block_j.sub_scores.risk_adjusted.downside_capture_pct, 1) }}
                        </div>
                        <div class="text-xs text-slate-400">Capture baisse</div>
                      </div>
                      <div v-if="studyResult.block_j.sub_scores.risk_adjusted.tracking_error_pct != null">
                        <div class="text-lg font-bold text-slate-200">
                          {{ formatPercent(studyResult.block_j.sub_scores.risk_adjusted.tracking_error_pct, 2) }}
                        </div>
                        <div class="text-xs text-slate-400">Tracking Error</div>
                      </div>
                    </div>
                  </div>

                  <!-- Drawdown detail -->
                  <div v-if="studyResult.block_j.sub_scores.drawdown" class="card">
                    <div class="text-xs font-semibold text-slate-400 mb-3">
                      Drawdown
                      <span class="ml-2"
                        :class="studyResult.block_j.sub_scores.drawdown.score >= 65 ? 'text-emerald-400' : studyResult.block_j.sub_scores.drawdown.score >= 50 ? 'text-amber-400' : 'text-red-400'">
                        score {{ studyResult.block_j.sub_scores.drawdown.score }}
                      </span>
                    </div>
                    <div class="grid grid-cols-3 md:grid-cols-5 gap-3 text-center">
                      <div>
                        <div class="text-lg font-bold text-red-400">
                          {{ formatPercent(studyResult.block_j.sub_scores.drawdown.max_drawdown_pct, 2) }}
                        </div>
                        <div class="text-xs text-slate-400">Max Drawdown</div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-slate-200">
                          {{ formatPercent(studyResult.block_j.sub_scores.drawdown.ulcer_index_pct, 2) }}
                        </div>
                        <div class="text-xs text-slate-400 flex items-center justify-center gap-1">
                          Ulcer Index
                          <div class="relative group inline-block">
                            <span class="cursor-help text-slate-500 hover:text-slate-300">?</span>
                            <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 z-50 w-64 bg-slate-800 border border-slate-600 rounded p-2 text-xs text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                              Mesure de la "douleur" des drawdowns : sqrt(moyenne des drawdowns²). Plus bas = mieux. Pénalise les drawdowns profonds ET durables.
                            </div>
                          </div>
                        </div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-slate-200">
                          {{ studyResult.block_j.sub_scores.drawdown.n_drawdown_episodes }}
                        </div>
                        <div class="text-xs text-slate-400">Épisodes DD</div>
                      </div>
                      <div v-if="studyResult.block_j.sub_scores.drawdown.avg_episode_duration_days">
                        <div class="text-lg font-bold text-slate-200">
                          {{ studyResult.block_j.sub_scores.drawdown.avg_episode_duration_days }}j
                        </div>
                        <div class="text-xs text-slate-400">Durée moy.</div>
                      </div>
                      <div v-if="studyResult.block_j.benchmark_available">
                        <div class="text-lg font-bold text-slate-200">
                          {{ formatPercent(studyResult.block_j.sub_scores.drawdown.benchmark_max_dd_pct, 2) }}
                        </div>
                        <div class="text-xs text-slate-400">Max DD bench.</div>
                      </div>
                    </div>
                    <!-- Worst episodes table -->
                    <div v-if="studyResult.block_j.sub_scores.drawdown.worst_episodes?.length" class="mt-4">
                      <div class="text-xs text-slate-500 mb-2">Pires épisodes de drawdown</div>
                      <table class="w-full text-xs">
                        <thead>
                          <tr class="text-slate-500 border-b border-slate-700">
                            <th class="text-left py-1">Rang</th>
                            <th class="text-right py-1">Profondeur</th>
                            <th class="text-right py-1">Durée (j)</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="(ep, idx) in studyResult.block_j.sub_scores.drawdown.worst_episodes"
                              :key="idx" class="border-b border-slate-800">
                            <td class="py-1 text-slate-400">#{{ idx + 1 }}</td>
                            <td class="py-1 text-right text-red-400">{{ formatPercent(ep.depth_pct, 2) }}</td>
                            <td class="py-1 text-right text-slate-300">{{ ep.duration_days ?? '—' }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <!-- Downside risk detail -->
                  <div v-if="studyResult.block_j.sub_scores.downside_risk" class="card">
                    <div class="text-xs font-semibold text-slate-400 mb-3">
                      Risque Baissier
                      <span class="ml-2"
                        :class="studyResult.block_j.sub_scores.downside_risk.score >= 65 ? 'text-emerald-400' : studyResult.block_j.sub_scores.downside_risk.score >= 50 ? 'text-amber-400' : 'text-red-400'">
                        score {{ studyResult.block_j.sub_scores.downside_risk.score }}
                      </span>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
                      <div>
                        <div class="text-lg font-bold text-red-400">
                          {{ formatPercent(studyResult.block_j.sub_scores.downside_risk.var_95_pct, 2) }}
                        </div>
                        <div class="text-xs text-slate-400 flex items-center justify-center gap-1">
                          VaR 95%
                          <div class="relative group inline-block">
                            <span class="cursor-help text-slate-500 hover:text-slate-300">?</span>
                            <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 z-50 w-64 bg-slate-800 border border-slate-600 rounded p-2 text-xs text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                              Value at Risk à 95% : la perte journalière qui ne sera dépassée que 5% du temps (méthode historique).
                            </div>
                          </div>
                        </div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-red-400">
                          {{ formatPercent(studyResult.block_j.sub_scores.downside_risk.es_95_pct, 2) }}
                        </div>
                        <div class="text-xs text-slate-400 flex items-center justify-center gap-1">
                          ES 95%
                          <div class="relative group inline-block">
                            <span class="cursor-help text-slate-500 hover:text-slate-300">?</span>
                            <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 z-50 w-64 bg-slate-800 border border-slate-600 rounded p-2 text-xs text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                              Expected Shortfall = perte moyenne dans les 5% pires journées. Plus conservateur que la VaR.
                            </div>
                          </div>
                        </div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-slate-200">
                          {{ formatPercent(studyResult.block_j.sub_scores.downside_risk.semi_deviation_pct, 2) }}
                        </div>
                        <div class="text-xs text-slate-400">Semi-déviation</div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-slate-200">
                          {{ formatNumber(studyResult.block_j.sub_scores.downside_risk.sortino_ratio, 3) }}
                        </div>
                        <div class="text-xs text-slate-400">Sortino</div>
                      </div>
                    </div>
                    <div class="grid grid-cols-3 gap-3 text-center mt-3"
                         v-if="studyResult.block_j.sub_scores.downside_risk.worst_day_pct != null">
                      <div>
                        <div class="text-lg font-bold text-red-400">
                          {{ formatPercent(studyResult.block_j.sub_scores.downside_risk.worst_day_pct, 2) }}
                        </div>
                        <div class="text-xs text-slate-400">Pire jour</div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-red-400">
                          {{ formatPercent(studyResult.block_j.sub_scores.downside_risk.worst_week_pct, 2) }}
                        </div>
                        <div class="text-xs text-slate-400">Pire semaine</div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-red-400">
                          {{ formatPercent(studyResult.block_j.sub_scores.downside_risk.worst_month_pct, 2) }}
                        </div>
                        <div class="text-xs text-slate-400">Pire mois</div>
                      </div>
                    </div>
                  </div>

                  <!-- Concentration detail -->
                  <div v-if="studyResult.block_j.sub_scores.concentration" class="card">
                    <div class="text-xs font-semibold text-slate-400 mb-3">
                      Concentration du Portefeuille
                      <span class="ml-2"
                        :class="studyResult.block_j.sub_scores.concentration.score >= 65 ? 'text-emerald-400' : studyResult.block_j.sub_scores.concentration.score >= 50 ? 'text-amber-400' : 'text-red-400'">
                        score {{ studyResult.block_j.sub_scores.concentration.score }}
                      </span>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
                      <div>
                        <div class="text-lg font-bold text-slate-200">
                          {{ studyResult.block_j.sub_scores.concentration.n_holdings }}
                        </div>
                        <div class="text-xs text-slate-400">Lignes</div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-amber-400">
                          {{ formatPercent(studyResult.block_j.sub_scores.concentration.max_weight_pct, 1) }}
                        </div>
                        <div class="text-xs text-slate-400">Max poids</div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-slate-200">
                          {{ formatNumber(studyResult.block_j.sub_scores.concentration.hhi, 4) }}
                        </div>
                        <div class="text-xs text-slate-400">HHI</div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-slate-200">
                          {{ formatNumber(studyResult.block_j.sub_scores.concentration.effective_n, 1) }}
                        </div>
                        <div class="text-xs text-slate-400 flex items-center justify-center gap-1">
                          Neff
                          <div class="relative group inline-block">
                            <span class="cursor-help text-slate-500 hover:text-slate-300">?</span>
                            <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 z-50 w-56 bg-slate-800 border border-slate-600 rounded p-2 text-xs text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                              1/HHI = nombre effectif de titres "indépendants". Plus élevé = plus diversifié.
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                    <!-- Top-5 holdings table -->
                    <div v-if="studyResult.block_j.sub_scores.concentration.top5_holdings?.length" class="mt-4">
                      <div class="text-xs text-slate-500 mb-2">Top 5 positions</div>
                      <table class="w-full text-xs">
                        <thead>
                          <tr class="text-slate-500 border-b border-slate-700">
                            <th class="text-left py-1">Titre</th>
                            <th class="text-right py-1">Poids (%)</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="pos in studyResult.block_j.sub_scores.concentration.top5_holdings"
                              :key="pos.name" class="border-b border-slate-800">
                            <td class="py-1 text-slate-300">{{ pos.name }}</td>
                            <td class="py-1 text-right text-amber-400">{{ formatPercent(pos.weight_pct, 2) }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <!-- Factor risk -->
                  <div v-if="studyResult.block_j.sub_scores.factor_risk" class="card">
                    <div class="text-xs font-semibold text-slate-400 mb-3">
                      Risque Factoriel (Bloc A)
                      <span class="ml-2"
                        :class="studyResult.block_j.sub_scores.factor_risk.score >= 65 ? 'text-emerald-400' : studyResult.block_j.sub_scores.factor_risk.score >= 50 ? 'text-amber-400' : 'text-red-400'">
                        score {{ studyResult.block_j.sub_scores.factor_risk.score }}
                      </span>
                    </div>
                    <div v-if="studyResult.block_j.sub_scores.factor_risk.available" class="grid grid-cols-3 gap-3 text-center">
                      <div>
                        <div class="text-lg font-bold text-slate-200">
                          {{ formatPercent(studyResult.block_j.sub_scores.factor_risk.r2_pct, 1) }}
                        </div>
                        <div class="text-xs text-slate-400">R²</div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-slate-200">
                          {{ studyResult.block_j.sub_scores.factor_risk.market_beta ?? '—' }}
                        </div>
                        <div class="text-xs text-slate-400">Beta marché</div>
                      </div>
                      <div>
                        <div class="text-lg font-bold text-slate-200">
                          {{ formatNumber(studyResult.block_j.sub_scores.factor_risk.alpha_tstat, 2) }}
                        </div>
                        <div class="text-xs text-slate-400">Alpha t-stat</div>
                      </div>
                    </div>
                    <div v-else class="text-xs text-slate-500">
                      Bloc A non disponible — facteur de risque non calculable.
                    </div>
                  </div>

                  <!-- Interpretation -->
                  <div v-if="studyResult.block_j.interpretation" class="card border border-slate-700">
                    <div class="text-xs font-semibold text-slate-400 mb-2">Interprétation</div>
                    <p class="text-xs text-slate-300 leading-5">{{ studyResult.block_j.interpretation }}</p>
                  </div>

                </template>
                <div v-else-if="studyResult.block_j && !studyResult.block_j.available"
                     class="card border border-red-500/30 text-red-400 text-sm py-4 px-4">
                  ⚠ {{ studyResult.block_j.error || 'Risk Management non disponible.' }}
                </div>
                <div v-else class="card text-slate-600 text-sm text-center py-8">
                  Lancez une étude pour afficher le Risk Management Score.
                </div>
              </div>

              <!-- ╔══════════════════════════════════════════════════════════╗ -->
              <!-- ║  BLOC K — RÉACTIVITÉ AUX CHOCS DE MARCHÉ                 ║ -->
              <!-- ╚══════════════════════════════════════════════════════════╝ -->
              <div v-if="activeStudyTab === 'marketshocks'" class="flex flex-col gap-5">

                <!-- No result yet — like Bloc G, computed on demand -->
                <div v-if="!studyResult.block_k && !marketShocksLoading" class="card text-center py-12">
                  <div class="text-4xl mb-3">🌍</div>
                  <div class="text-slate-400 text-sm mb-2">Réactivité aux Chocs de Marché</div>
                  <div class="text-slate-600 text-xs mb-5 max-w-md mx-auto leading-relaxed">
                    Juxtapose l'activité de trading avec les grands chocs de marché (subprimes, Chine, COVID, SVB...)
                    pour identifier une sur-réaction, une sous-réaction, ou une gestion disciplinée.
                  </div>
                  <button
                    class="mx-auto px-5 py-2.5 text-sm font-semibold bg-blue-700 hover:bg-blue-600 text-white rounded-lg transition-colors flex items-center gap-2"
                    :disabled="marketShocksLoading"
                    @click="computeMarketShocks">
                    <span v-if="marketShocksLoading" class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                    🌍 Calculer la Réactivité aux Chocs
                  </button>
                  <div v-if="marketShocksError" class="mt-3 text-red-400 text-xs">{{ marketShocksError }}</div>
                </div>

                <div v-if="marketShocksLoading && !studyResult.block_k" class="card text-center py-8 text-slate-500 text-xs">
                  <div class="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
                  Calcul en cours…
                </div>

                <template v-if="studyResult.block_k && studyResult.block_k.available">

                  <div class="flex items-center justify-between">
                    <div v-if="studyResult.meta?.nav_start_date" class="text-[10px] text-slate-500">
                      Période d'étude : {{ formatDate(studyResult.meta.nav_start_date) }} → {{ formatDate(studyResult.meta.nav_current_date) }}
                    </div>
                    <button
                      class="text-[10px] border border-slate-700 text-slate-500 hover:text-blue-300 hover:border-blue-700 px-2 py-1 rounded transition-colors"
                      :disabled="marketShocksLoading"
                      @click="computeMarketShocks">↻ Recalculer</button>
                  </div>

                  <div v-if="studyResult.block_k.warning"
                       class="card border border-amber-500/30 text-amber-400 text-xs py-3 px-4">
                    ⚠ {{ studyResult.block_k.warning }}
                  </div>

                  <div class="card border border-slate-700">
                    <div class="text-xs font-semibold text-slate-400 mb-2">Résumé</div>
                    <p class="text-xs text-slate-300 leading-5">{{ studyResult.block_k.interpretation }}</p>
                  </div>

                  <div v-if="studyResult.block_k.n_events_applicable === 0" class="card text-slate-600 text-sm text-center py-8">
                    Aucun choc de marché du calendrier ne chevauche l'historique de ce fonds.
                  </div>

                  <div v-else class="card overflow-x-auto table-shell" tabindex="0" role="region">
                    <table class="w-full text-xs">
                      <thead>
                        <tr class="border-b border-slate-800 text-slate-500">
                          <th class="text-left py-2 px-2">Événement</th>
                          <th class="text-left py-2 px-2">Période</th>
                          <th class="text-right py-2 px-2">Trades</th>
                          <th class="text-right py-2 px-2">Ratio activité</th>
                          <th class="text-right py-2 px-2">Flux net</th>
                          <th class="text-right py-2 px-2">Timing moy.</th>
                          <th class="text-left py-2 px-2">Diagnostic</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="e in studyResult.block_k.events" :key="e.id"
                            class="border-b border-slate-800/50">
                          <td class="py-2 px-2">
                            <div class="font-medium text-slate-200">{{ e.label }}</div>
                            <div class="text-slate-500">{{ e.category }}</div>
                          </td>
                          <td class="py-2 px-2 text-slate-400 font-mono">{{ e.start }} → {{ e.end }}</td>
                          <td class="py-2 px-2 text-right font-mono">{{ e.n_trades }}</td>
                          <td class="py-2 px-2 text-right font-mono"
                              :class="e.activity_ratio == null ? 'text-slate-500'
                                     : e.activity_ratio > 1.8 ? 'text-amber-400'
                                     : e.activity_ratio < 0.4 ? 'text-slate-500' : 'text-slate-300'">
                            {{ e.activity_ratio != null ? 'x' + formatNumber(e.activity_ratio, 2) : '—' }}
                          </td>
                          <td class="py-2 px-2 text-right font-mono"
                              :class="e.net_flow > 0 ? 'text-emerald-400' : e.net_flow < 0 ? 'text-red-400' : 'text-slate-500'">
                            {{ e.net_flow > 0 ? '+' : '' }}{{ formatInt(e.net_flow) }}
                          </td>
                          <td class="py-2 px-2 text-right font-mono text-slate-400">
                            {{ formatNumber(e.avg_timing_score, 2) }}
                          </td>
                          <td class="py-2 px-2 text-slate-300">{{ e.reaction_label }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                </template>
                <div v-else-if="studyResult.block_k && !studyResult.block_k.available"
                     class="card border border-red-500/30 text-red-400 text-sm py-4 px-4">
                  ⚠ {{ studyResult.block_k.error || 'Réactivité aux chocs de marché non disponible.' }}
                </div>
              </div>

              <!-- ╔══════════════════════════════════════════════════════════╗ -->
              <!-- ║  MANAGER SKILL SCORE                                     ║ -->
              <!-- ╚══════════════════════════════════════════════════════════╝ -->
              <div v-if="activeStudyTab === 'managerskill'" class="flex flex-col gap-5">
                <template v-if="studyResult.manager_skill_score && studyResult.manager_skill_score.available">

                  <!-- Score badge unique -->
                  <div class="flex justify-center">
                    <div class="card text-center py-6 w-64">
                      <div class="text-[10px] font-bold uppercase tracking-widest text-violet-400 mb-3">
                        Manager Skill Score
                      </div>
                      <div class="text-6xl font-black mb-1"
                        :style="{ color: studyResult.manager_skill_score.score_color }">
                        {{ studyResult.manager_skill_score.score }}
                      </div>
                      <div class="text-xs text-slate-500 mb-2">/100</div>
                      <div class="text-sm font-bold"
                        :style="{ color: studyResult.manager_skill_score.score_color }">
                        {{ studyResult.manager_skill_score.score_label }}
                      </div>
                      <div class="text-[10px] text-slate-600 mt-2">
                        {{ studyResult.manager_skill_score.n_dimensions_available }} dimensions disponibles
                      </div>
                    </div>
                  </div>

                  <!-- Dimension contribution table -->
                  <div class="card">
                    <div class="text-xs font-semibold text-slate-400 mb-3">Décomposition par Dimension</div>
                    <table class="w-full text-xs">
                      <thead>
                        <tr class="text-slate-500 border-b border-slate-700">
                          <th class="text-left py-1.5">Dimension</th>
                          <th class="text-right py-1.5">Poids</th>
                          <th class="text-right py-1.5 text-violet-400">Score</th>
                          <th class="text-right py-1.5">Contribution</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="dim in studyResult.manager_skill_score.dimensions"
                            :key="dim.key" class="border-b border-slate-800">
                          <td class="py-1.5"
                              :class="dim.available ? 'text-slate-300' : 'text-slate-600'">
                            {{ dim.label }}
                            <span v-if="dim.key === 'vag' && dim.vag_ann_pct != null"
                                  class="block text-[10px] text-slate-500">
                              VAG {{ dim.vag_ann_pct > 0 ? '+' : '' }}{{ formatNumber(dim.vag_ann_pct, 1) }}%/an vs B&H passif
                            </span>
                          </td>
                          <td class="py-1.5 text-right text-slate-400">{{ formatPercent(dim.weight_effective_pct, 0) }}</td>
                          <td class="py-1.5 text-right font-semibold"
                              :class="!dim.available ? 'text-slate-600'
                                     : dim.score >= 65 ? 'text-emerald-400'
                                     : dim.score >= 50 ? 'text-amber-400'
                                     : 'text-red-400'">
                            {{ dim.available ? formatNumber(dim.score, 0) : 'N/A' }}
                          </td>
                          <td class="py-1.5 text-right text-slate-300">
                            {{ formatNumber(dim.weighted_contribution, 1) }}
                          </td>
                        </tr>
                        <!-- Total row -->
                        <tr class="font-bold border-t border-slate-600 bg-slate-900/50">
                          <td class="py-1.5 text-slate-200">TOTAL</td>
                          <td class="py-1.5 text-right text-slate-400">100%</td>
                          <td class="py-1.5 text-right"
                              :style="{ color: studyResult.manager_skill_score.score_color }">
                            {{ studyResult.manager_skill_score.score }}
                          </td>
                          <td class="py-1.5 text-right text-slate-400">—</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- Progress bars (avec VAG) -->
                  <div class="card">
                    <div class="text-xs font-semibold text-slate-400 mb-3">Profil par dimension</div>
                    <div class="flex flex-col gap-2">
                      <div v-for="dim in studyResult.manager_skill_score.dimensions.filter(d => d.available)"
                           :key="dim.key">
                        <div class="flex justify-between text-xs mb-0.5">
                          <span class="text-slate-400">{{ dim.label }}</span>
                          <span :class="dim.score >= 65 ? 'text-emerald-400' : dim.score >= 50 ? 'text-amber-400' : 'text-red-400'">
                            {{ formatNumber(dim.score, 0) }}/100
                          </span>
                        </div>
                        <div class="h-2 bg-slate-700 rounded-full overflow-hidden">
                          <div class="h-2 rounded-full transition-all"
                               :class="dim.score >= 65 ? 'bg-emerald-500' : dim.score >= 50 ? 'bg-amber-500' : 'bg-red-500'"
                               :style="{ width: (dim.score ?? 0) + '%' }">
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Interpretation -->
                  <div v-if="studyResult.manager_skill_score.interpretation" class="card border border-slate-700">
                    <div class="text-xs font-semibold text-slate-400 mb-2">Interprétation</div>
                    <p class="text-xs text-slate-300 leading-5">{{ studyResult.manager_skill_score.interpretation }}</p>
                  </div>

                </template>
                <div v-else-if="studyResult.manager_skill_score && !studyResult.manager_skill_score.available"
                     class="card border border-amber-500/30 text-amber-400 text-sm py-4 px-4">
                  ⚠ {{ studyResult.manager_skill_score.error || 'Blocs insuffisants pour calculer le Manager Skill Score.' }}
                </div>
                <div v-else class="card text-slate-600 text-sm text-center py-8">
                  Lancez une étude pour afficher le Manager Skill Score.
                </div>
              </div>

              <!-- CONFIDENCE -->
              <div v-if="activeStudyTab === 'confidence' && studyResult.confidence" class="flex flex-col gap-5">
                <div class="card text-center">
                  <div class="text-5xl font-black mb-2"
                    :class="studyResult.confidence.overall_pct >= 80 ? 'text-emerald-400' : studyResult.confidence.overall_pct >= 60 ? 'text-amber-400' : 'text-red-400'">
                    {{ formatPercent(studyResult.confidence.overall_pct, 0) }}
                  </div>
                  <div class="text-xs text-slate-400">Confiance globale dans les résultats</div>
                  <p class="text-xs text-slate-500 mt-3 max-w-lg mx-auto leading-5">
                    {{ studyResult.confidence.narrative }}
                  </p>
                </div>

                <div class="card">
                  <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Tableau de confiance par dimension</div>
                  <div class="overflow-x-auto table-shell" tabindex="0" role="region">
                  <table class="w-full text-xs min-w-[700px]">
                    <thead>
                      <tr class="text-slate-500 border-b border-slate-700">
                        <th class="text-left py-2 px-2">Dimension</th>
                        <th class="text-center py-2 px-2" title="✓ = l'analyse a pu être réalisée avec les données disponibles. — = donnée source manquante, bloc non exécuté.">Faisable</th>
                        <th class="text-right py-2 px-2" title="Score de confiance (%) dans les résultats de cette dimension. Tient compte du volume de données, de la qualité des données source et de la robustesse de la méthode.">Confiance</th>
                        <th class="text-left py-2 px-2" title="Information non disponible dans les fichiers source actuels (LUKB) et qui limiterait la qualité ou la portée de cette dimension d'analyse.">Donnée manquante</th>
                        <th class="text-left py-2 px-2" title="Analyse ou métriques supplémentaires qui deviendraient possibles si la donnée manquante était disponible.">Ce que ça débloquerait</th>
                      </tr>
                    </thead>
                    <tbody>
                      <!-- Static rows from build_confidence (inclut Bloc E — Référentiel Inertiel) -->
                      <tr v-for="r in studyResult.confidence.rows" :key="r.dimension"
                        class="border-b border-slate-800/50">
                        <td class="py-1.5 px-2 text-slate-300">{{ r.dimension }}</td>
                        <td class="py-1.5 px-2 text-center"
                          :class="r.feasible ? 'text-emerald-400' : 'text-slate-600'">
                          {{ r.feasible ? '✓' : '—' }}
                        </td>
                        <td class="py-1.5 px-2 text-right font-mono font-bold"
                          :class="r.confidence_pct >= 80 ? 'text-emerald-400' : r.confidence_pct >= 60 ? 'text-amber-400' : 'text-slate-500'">
                          {{ r.confidence_pct > 0 ? r.confidence_pct+'%' : 'N/A' }}
                        </td>
                        <td class="py-1.5 px-2 text-slate-600 text-[10px]">{{ r.missing_data || '—' }}</td>
                        <td class="py-1.5 px-2 text-slate-500 text-[10px]">{{ r.unlocks || '—' }}</td>
                      </tr>

                      <!-- G — Brinson : ligne dynamique selon brinsonResult -->
                      <tr v-if="!brinsonResult" class="border-b border-slate-800/50 bg-blue-950/10">
                        <td class="py-1.5 px-2 text-slate-400">Attribution Brinson-Fachler (Bloc G)</td>
                        <td class="py-1.5 px-2 text-center text-slate-600">—</td>
                        <td class="py-1.5 px-2 text-right font-mono text-slate-600">N/C</td>
                        <td class="py-1.5 px-2 text-slate-600 text-[10px]">Rendements sectoriels via ETFs SPDR US (biais USD). Benchmark snapshot actuel supposé stable.</td>
                        <td class="py-1.5 px-2 text-blue-500 text-[10px]">
                          <button @click="activeStudyTab = 'brinson'"
                            class="underline hover:text-blue-400">→ Aller à l'onglet H</button>
                        </td>
                      </tr>
                      <tr v-else-if="brinsonResult.available" class="border-b border-slate-800/50 bg-blue-950/10">
                        <td class="py-1.5 px-2 text-slate-300">Attribution Brinson-Fachler par secteur (Bloc G)</td>
                        <td class="py-1.5 px-2 text-center text-emerald-400">✓</td>
                        <td class="py-1.5 px-2 text-right font-mono font-bold"
                          :class="brinsonResult.bench_return_estimated ? 'text-amber-400' : 'text-emerald-400'">
                          {{ brinsonResult.bench_return_estimated ? '60%' : '70%' }}
                        </td>
                        <td class="py-1.5 px-2 text-slate-600 text-[10px]">Biais ETFs SPDR US · benchmark snapshot actuel{{ brinsonResult.bench_return_estimated ? ' · retour benchmark estimé' : '' }}</td>
                        <td class="py-1.5 px-2 text-slate-500 text-[10px]">
                          Retour actif =
                          <span :class="(brinsonResult.active_return_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'">
                            {{ (brinsonResult.active_return_pct >= 0 ? '+' : '') }}{{ formatPercentRaw(brinsonResult.active_return_pct) }}
                          </span>
                          · {{ brinsonResult.n_holdings }} titres · {{ brinsonResult.sector_rows?.length }} secteurs
                        </td>
                      </tr>
                    </tbody>
                  </table>
                  </div>
                </div>

                <div v-if="studyResult.confidence.roadmap?.length" class="card">
                  <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Feuille de route — Développements futurs</div>
                  <div v-for="r in studyResult.confidence.roadmap" :key="r.item"
                    class="mb-3 pb-3 border-b border-slate-800 last:border-0">
                    <div class="text-xs font-bold text-blue-400 mb-1">{{ r.item }}</div>
                    <div class="text-xs text-slate-500">{{ r.unlocks }}</div>
                  </div>
                </div>

                <div class="text-xs text-slate-600 italic">{{ studyResult.confidence.coverage_note }}</div>
              </div>

              <!-- ── SOUS-JACENTS — Price Store ─────────────────────── -->
              <div v-if="activeStudyTab === 'prices'" class="flex flex-col gap-5">

                <div class="card">
                  <div class="flex items-center justify-between mb-3">
                    <div>
                      <div class="text-sm font-semibold text-slate-200">📦 Price Store — Séries de prix par sous-jacent</div>
                      <div class="text-xs text-slate-500 mt-0.5">Utilisées par les Blocs G (Brinson), H (Timing) et I (Stock Picking).</div>
                    </div>
                    <div class="flex gap-2">
                      <button
                        class="text-xs border border-slate-700 text-slate-400 hover:text-blue-300 hover:border-blue-700 px-3 py-1.5 rounded transition-colors"
                        :disabled="tickerResolving || !priceStatusList.length"
                        @click="resolveAllTickers">
                        <span v-if="tickerResolving" class="w-3 h-3 border border-blue-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                        🔍 Résoudre les tickers
                      </button>
                      <button
                        class="text-xs border border-slate-700 text-slate-400 hover:text-green-300 hover:border-green-700 px-3 py-1.5 rounded transition-colors"
                        :disabled="fetchingAll || !priceStatusList.some(u => u.ticker)"
                        @click="fetchAllUnderlyings">
                        <span v-if="fetchingAll" class="w-3 h-3 border border-green-400 border-t-transparent rounded-full animate-spin inline-block mr-1"></span>
                        ⬇ Tout télécharger
                      </button>
                    </div>
                  </div>

                  <div v-if="priceStatusLoading" class="text-slate-500 text-xs py-4 text-center">
                    Chargement…
                  </div>
                  <div v-else-if="!priceStatusList.length" class="text-slate-600 text-xs py-4 text-center">
                    Lancez d'abord l'étude pour charger la liste des sous-jacents.
                  </div>
                  <table v-else class="w-full text-xs">
                    <thead>
                      <tr class="border-b border-slate-800 text-slate-500">
                        <th class="text-left py-2 pr-3 font-normal">Sous-jacent</th>
                        <th class="text-left py-2 pr-3 font-normal w-28">Ticker Yahoo</th>
                        <th class="text-center py-2 pr-3 font-normal w-16">Statut</th>
                        <th class="text-right py-2 font-normal w-36">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="u in priceStatusList" :key="u.key"
                        class="border-b border-slate-800/50 hover:bg-slate-800/20">
                        <td class="py-1.5 pr-3">
                          <div class="text-slate-300">{{ u.name }}</div>
                          <div class="text-slate-600 font-mono text-[10px]">{{ u.isin }}</div>
                        </td>
                        <td class="py-1.5 pr-3">
                          <div class="flex items-center gap-1">
                            <input
                              v-model="u.ticker"
                              type="text"
                              placeholder="ex: ANET"
                              class="bg-slate-800 border border-slate-700 rounded px-1.5 py-0.5 text-xs text-slate-200 w-20 focus:border-blue-600 focus:outline-none font-mono"
                            />
                            <span v-if="tickerResolved[u.key] === 'high'"   class="text-green-400 text-[10px]">✓</span>
                            <span v-else-if="tickerResolved[u.key] === 'low'" class="text-amber-400 text-[10px]">~</span>
                            <span v-else-if="tickerResolved[u.key] === 'not_found'" class="text-red-400 text-[10px]">✗</span>
                          </div>
                        </td>
                        <td class="py-1.5 pr-3 text-center">
                          <span v-if="u.available"
                            class="px-1.5 py-0.5 rounded text-[10px] bg-green-900/40 text-green-400 border border-green-800/40">
                            ✓ {{ u.n_rows }} pts
                          </span>
                          <span v-else class="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-500">
                            —
                          </span>
                        </td>
                        <td class="py-1.5 text-right">
                          <div class="flex items-center justify-end gap-1">
                            <span v-if="priceErrors[u.key]" class="text-red-400 text-[10px] mr-1">{{ priceErrors[u.key] }}</span>
                            <button
                              class="px-2 py-0.5 rounded border border-slate-700 text-slate-400 hover:text-blue-300 hover:border-blue-700 transition-colors text-[10px]"
                              :disabled="priceRefreshing === u.key || !u.ticker"
                              @click="fetchUnderlying(u)">
                              <span v-if="priceRefreshing === u.key" class="w-2.5 h-2.5 border border-blue-400 border-t-transparent rounded-full animate-spin inline-block"></span>
                              <span v-else>⬇ Yahoo</span>
                            </button>
                            <label class="px-2 py-0.5 rounded border border-slate-700 text-slate-400 hover:text-purple-300 hover:border-purple-700 transition-colors text-[10px] cursor-pointer">
                              📁 Upload
                              <input type="file" accept=".xlsx,.json" class="hidden" @change="uploadUnderlying(u, $event)" />
                            </label>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>

                  <!-- Coverage summary -->
                  <div v-if="priceStatusList.length" class="mt-3 pt-3 border-t border-slate-800 flex items-center gap-4 text-xs text-slate-500">
                    <span>
                      <span class="text-green-400 font-semibold">{{ priceStatusList.filter(u => u.available).length }}</span>
                      / {{ priceStatusList.length }} séries disponibles
                    </span>
                    <span class="text-slate-600">
                      Couverture : {{ formatPercent(priceStatusList.length ? priceStatusList.filter(u => u.available).length / priceStatusList.length * 100 : 0, 0) }}
                    </span>
                  </div>
                </div>

              </div>

              <!-- ── BLOC F — Réplicabilité ──────────────────────────── -->
              <div v-if="activeStudyTab === 'replicability'" class="flex flex-col gap-5">

                <!-- Block F non disponible -->
                <div v-if="!studyResult.block_f" class="card text-center py-8">
                  <div class="text-3xl mb-3">🔁</div>
                  <div class="text-slate-300 text-sm mb-1 font-semibold">Bloc F — Réplicabilité non calculé</div>
                  <div class="text-slate-500 text-xs">Le Bloc A (régression Fama-French) est requis. Relancez l'étude avec le Bloc A activé.</div>
                </div>

                <div v-else-if="!studyResult.block_f.available" class="card border border-amber-900/50">
                  <div class="text-amber-400 text-xs font-bold mb-1">⚠ Bloc F indisponible</div>
                  <div class="text-slate-400 text-xs">{{ studyResult.block_f.error }}</div>
                </div>

                <template v-else>
                  <!-- Période -->
                  <div class="text-[10px] text-slate-500">
                    Période : {{ formatDate(studyResult.block_f.period_start) }} → {{ formatDate(studyResult.block_f.period_end) }}
                    · {{ studyResult.block_f.n_obs }} observations
                    · Facteurs : {{ (studyResult.block_f.factors_used || []).join(' · ') }}
                  </div>

                  <!-- Score + profil -->
                  <div class="grid grid-cols-2 gap-4">
                    <div class="card text-center py-6"
                      :class="{
                        'border border-emerald-700/50 bg-emerald-950/10': studyResult.block_f.score < 40,
                        'border border-amber-700/50 bg-amber-950/10':    studyResult.block_f.score >= 40 && studyResult.block_f.score < 70,
                        'border border-blue-700/50 bg-blue-950/10':      studyResult.block_f.score >= 70,
                      }">
                      <div class="flex items-center justify-center gap-1.5 mb-0.5">
                        <div class="text-6xl font-black"
                          :class="{
                            'text-emerald-400': studyResult.block_f.score < 40,
                            'text-amber-400':   studyResult.block_f.score >= 40 && studyResult.block_f.score < 70,
                            'text-blue-400':    studyResult.block_f.score >= 70,
                          }">
                          {{ studyResult.block_f.score }}
                        </div>
                        <span title="Score de réplicabilité STRUCTURA (méthodologie interne). Mesure la proportion de la stratégie explicable par des facteurs passifs. Intervalle de confiance à 95% basé sur l'erreur d'échantillonnage du R²." class="cursor-help text-[8px] text-slate-600 hover:text-slate-400 border border-slate-700 rounded-full w-3.5 h-3.5 flex items-center justify-center leading-none transition-colors self-center">?</span>
                      </div>
                      <div class="text-slate-500 text-xs mb-1">/ 100 — Score de réplicabilité</div>
                      <!-- Intervalle de confiance -->
                      <div class="text-[10px] text-slate-600 mb-2 font-mono">
                        IC 95% : [{{ studyResult.block_f.score_ci_low }} — {{ studyResult.block_f.score_ci_high }}]
                      </div>
                      <div class="font-bold text-sm"
                        :class="{
                          'text-emerald-400': studyResult.block_f.score < 40,
                          'text-amber-400':   studyResult.block_f.score >= 40 && studyResult.block_f.score < 70,
                          'text-blue-400':    studyResult.block_f.score >= 70,
                        }">
                        {{ studyResult.block_f.profile }}
                      </div>
                    </div>

                    <div class="card flex flex-col gap-3 justify-center py-4">
                      <div class="flex items-center gap-1.5 mb-1">
                        <div class="text-[9px] text-slate-500 uppercase tracking-wider font-bold">Décomposition du score</div>
                        <span title="Méthodologie interne STRUCTURA — non standardisée. Formule : Score = 40% × R² + 35% × min(Perf_réplicant / Perf_AMC, 1) + 25% × (1 − min(|t_alpha| / 3, 1)). Le R² mesure la variance expliquée, le ratio de performance mesure la couverture des rendements, et le terme alpha pénalise les stratégies avec un alpha statistiquement significatif (qui déviait des facteurs)." class="cursor-help text-[8px] text-slate-600 hover:text-slate-400 border border-slate-700 rounded-full w-3.5 h-3.5 flex items-center justify-center leading-none transition-colors">?</span>
                      </div>
                      <div class="text-[9px] text-amber-600/80 mb-2">⚙ Score STRUCTURA interne</div>
                      <div v-for="(item, key) in {
                        'R² (variance expliquée) × 40%': formatNumber(studyResult.block_f.score_components?.r2_component, 1),
                        'Couverture performance × 35%': formatNumber(studyResult.block_f.score_components?.perf_coverage, 1),
                        'Alpha non-significatif × 25%': formatNumber(studyResult.block_f.score_components?.alpha_insig, 1),
                      }" :key="key" class="flex items-center gap-2">
                        <div class="text-[10px] text-slate-400 flex-1">{{ key }}</div>
                        <div class="text-[10px] font-bold text-slate-300">{{ item }}/100</div>
                        <div class="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                          <div class="h-full bg-blue-500 rounded-full" :style="{width: item + '%'}"></div>
                        </div>
                      </div>
                      <!-- Formule -->
                      <div class="mt-2 text-[9px] text-slate-700 font-mono border-t border-slate-800 pt-2 leading-relaxed">
                        Score = 40% × R² + 35% × cov_perf + 25% × (1 − |t|/3)<br>
                        IC 95% calculé sur se(R²) = 2√R²×(1−R²)/√n
                      </div>
                    </div>
                  </div>

                  <!-- KPI row -->
                  <div class="grid grid-cols-4 gap-3">
                    <div v-for="(item, idx) in [
                      { label: 'AMC réel', value: (studyResult.block_f.amc_total_pct >= 0 ? '+' : '') + studyResult.block_f.amc_total_pct + '%', color: studyResult.block_f.amc_total_pct >= 0 ? 'text-emerald-400' : 'text-red-400', tip: 'Performance cumulée de la NAV réelle de l\'AMC sur la période d\'overlap avec les facteurs FF.' },
                      { label: 'Réplicant factoriel', value: (studyResult.block_f.replicant_total_pct >= 0 ? '+' : '') + studyResult.block_f.replicant_total_pct + '%', color: 'text-violet-400', tip: 'Performance cumulée théorique du portefeuille réplicant RF + Σβi×Fi. Construit ex-post — non investissable tel quel (les facteurs FF sont long-short dollar-neutres).' },
                      { label: 'Écart (alpha gap)', value: (studyResult.block_f.alpha_gap_pct >= 0 ? '+' : '') + studyResult.block_f.alpha_gap_pct + '%', color: studyResult.block_f.alpha_gap_pct >= 0 ? 'text-emerald-400' : 'text-red-400', tip: 'Différence AMC − Réplicant. Si positif : le gérant sur-performe sa réplication factorielle. Si négatif : les facteurs seuls auraient fait mieux.' },
                      { label: 'R² factoriel', value: studyResult.block_f.r2_pct + '%', color: 'text-blue-400', tip: 'Fraction de la variance des rendements journaliers expliquée par le modèle factoriel FF. R² = 72% signifie que 72% des mouvements de l\'AMC suivent les facteurs de marché.' },
                    ]" :key="idx" class="card text-center py-4">
                      <div class="text-xl font-black mb-1" :class="item.color">{{ item.value }}</div>
                      <div class="text-[9px] text-slate-500 uppercase tracking-wider flex items-center justify-center gap-1">
                        {{ item.label }}
                        <span :title="item.tip" class="cursor-help text-[8px] text-slate-600 hover:text-slate-400 border border-slate-700 rounded-full w-3 h-3 flex items-center justify-center leading-none transition-colors">?</span>
                      </div>
                    </div>
                  </div>

                  <!-- Alpha info -->
                  <div class="card text-xs" :class="Math.abs(studyResult.block_f.alpha_tstat) >= 2 ? 'border border-emerald-800/40 bg-emerald-950/10' : 'border border-amber-800/40 bg-amber-950/10'">
                    <div class="flex items-center gap-3">
                      <span class="text-base">{{ Math.abs(studyResult.block_f.alpha_tstat) >= 2 ? '✅' : '⚠' }}</span>
                      <div>
                        <span class="font-bold" :class="Math.abs(studyResult.block_f.alpha_tstat) >= 2 ? 'text-emerald-400' : 'text-amber-400'">
                          Alpha annualisé : {{ studyResult.block_f.alpha_ann_pct >= 0 ? '+' : '' }}{{ formatPercentRaw(studyResult.block_f.alpha_ann_pct) }}
                        </span>
                        <span class="text-slate-500 ml-2">t = {{ formatNumber(studyResult.block_f.alpha_tstat, 2) }}</span>
                        <span class="text-slate-600 ml-2">·</span>
                        <span class="ml-2" :class="Math.abs(studyResult.block_f.alpha_tstat) >= 2 ? 'text-emerald-500' : 'text-amber-500'">
                          {{ Math.abs(studyResult.block_f.alpha_tstat) >= 2 ? 'Statistiquement significatif (|t| ≥ 2)' : 'Non significatif (|t| < 2) — bruit possible' }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- Contributions factorielles -->
                  <div v-if="studyResult.block_f.factor_contributions?.length" class="card">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                      Contribution de chaque facteur à la performance du réplicant
                      <span title="Approximation additive : contribution_i ≈ β_i × (rendement cumulé du facteur F_i sur la période). Valide pour des périodes courtes et des bêtas modérés. Les facteurs sont les rendements excédentaires (au-dessus du taux sans risque) de Ken French." class="cursor-help text-[8px] text-slate-600 hover:text-slate-400 border border-slate-700 rounded-full w-3.5 h-3.5 flex items-center justify-center leading-none transition-colors">?</span>
                    </div>
                    <div class="flex flex-col gap-2">
                      <div v-for="fc in studyResult.block_f.factor_contributions" :key="fc.name"
                        class="flex items-center gap-3">
                        <div class="text-xs font-mono text-slate-400 w-16 shrink-0">{{ fc.name }}</div>
                        <div class="text-[10px] text-slate-600 w-16 shrink-0 text-right">β = {{ formatNumber(fc.beta, 3) }}</div>
                        <div class="flex-1 h-2 bg-slate-700 rounded-full overflow-hidden">
                          <div class="h-full rounded-full"
                            :class="fc.contribution_pct >= 0 ? 'bg-emerald-500' : 'bg-red-500'"
                            :style="{
                              width: Math.min(Math.abs(fc.contribution_pct) / Math.max(...studyResult.block_f.factor_contributions.map(x => Math.abs(x.contribution_pct))) * 100, 100) + '%',
                              marginLeft: fc.contribution_pct < 0 ? 'auto' : '0',
                            }">
                          </div>
                        </div>
                        <div class="text-xs font-mono font-bold shrink-0 w-16 text-right"
                          :class="fc.contribution_pct >= 0 ? 'text-emerald-400' : 'text-red-400'">
                          {{ fc.contribution_pct >= 0 ? '+' : '' }}{{ formatPercentRaw(fc.contribution_pct) }}
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Interprétation -->
                  <div v-if="studyResult.block_f.interpretation" class="card border border-slate-700/50 bg-slate-800/30">
                    <div class="text-[9px] text-slate-500 uppercase tracking-wider font-bold mb-2">Interprétation</div>
                    <div class="text-xs text-slate-300 leading-relaxed">{{ studyResult.block_f.interpretation }}</div>
                  </div>

                  <!-- Grille de lecture -->
                  <div class="card">
                    <div class="text-[9px] text-slate-500 uppercase tracking-wider font-bold mb-3">Grille de lecture du score</div>
                    <div class="grid grid-cols-5 gap-1 text-center text-[9px]">
                      <div v-for="band in [
                        { range: '0–20', label: 'Pur discrétionnaire', color: 'text-emerald-400', bg: 'bg-emerald-950/30 border-emerald-800/40' },
                        { range: '20–40', label: 'Principalement discrétionnaire', color: 'text-emerald-400', bg: 'bg-emerald-950/20 border-emerald-800/30' },
                        { range: '40–60', label: 'Mixte', color: 'text-amber-400', bg: 'bg-amber-950/30 border-amber-800/40' },
                        { range: '60–80', label: 'Principalement systématique', color: 'text-blue-400', bg: 'bg-blue-950/20 border-blue-800/30' },
                        { range: '80–100', label: 'Quasi-systématique', color: 'text-blue-400', bg: 'bg-blue-950/30 border-blue-800/40' },
                      ]" :key="band.range"
                      class="rounded p-2 border"
                      :class="[band.bg, studyResult.block_f.profile === band.label ? 'ring-1 ring-white/20' : '']">
                        <div class="font-mono font-bold" :class="band.color">{{ band.range }}</div>
                        <div class="text-slate-500 mt-0.5 leading-tight">{{ band.label }}</div>
                      </div>
                    </div>
                  </div>

                  <!-- Théorie, limites et méthodologie complète -->
                  <div class="card border border-slate-700/50 bg-slate-900/30">
                    <div class="text-[9px] text-slate-500 uppercase tracking-wider font-bold mb-3">Théorie & Limites — à lire avant toute interprétation</div>
                    <div class="grid grid-cols-2 gap-4 text-[10px] text-slate-400 leading-relaxed">
                      <div>
                        <div class="text-slate-300 font-semibold mb-1.5">Construction du réplicant</div>
                        <p class="mb-2">Le portefeuille réplicant est une <strong class="text-slate-300">reconstruction théorique ex-post</strong> basée sur la formule :</p>
                        <p class="font-mono bg-slate-800/60 rounded px-2 py-1 text-[9px] mb-2">R_rep(t) = RF(t) + β_mkt×(Mkt−RF)(t) + β_SMB×SMB(t) + β_HML×HML(t) + …</p>
                        <p class="mb-2">Les facteurs Fama-French sont des <strong class="text-slate-300">portefeuilles long-short dollar-neutres</strong>. SMB = long small caps / short large caps. HML = long value / short growth. Ils ne sont pas directement achetables en ETF.</p>
                        <p>L'approximation pratique serait un panier d'ETFs smart-beta (MTUM pour le momentum, VLUE pour la value, IWM pour le small) pondéré selon les bêtas — mais avec des coûts de transaction et des frais réels.</p>
                      </div>
                      <div>
                        <div class="text-slate-300 font-semibold mb-1.5">Limites importantes</div>
                        <ul class="space-y-1.5 list-none">
                          <li><span class="text-amber-500">⚠</span> <strong class="text-slate-300">Biais ex-post :</strong> les bêtas sont estimés sur la même période que la comparaison. En temps réel, un investisseur ne connaîtrait les bêtas qu'en décalé — la réplication aurait nécessité des rééquilibrages.</li>
                          <li><span class="text-amber-500">⚠</span> <strong class="text-slate-300">Facteurs en USD :</strong> les données Ken French sont en USD. Pour un AMC en CHF/EUR, les bêtas absorbent une part du risque de change, non séparable des expositions de style.</li>
                          <li><span class="text-amber-500">⚠</span> <strong class="text-slate-300">Bêtas statiques :</strong> la régression utilise la fenêtre entière. Si le gérant a changé de style en cours de route, les bêtas moyens masquent cette évolution. Les bêtas glissants (Bloc A, onglet Rolling) sont plus fidèles.</li>
                          <li><span class="text-amber-500">⚠</span> <strong class="text-slate-300">Score STRUCTURA interne :</strong> la pondération 40/35/25% entre R², couverture et signif. de l'alpha est une convention maison, non standardisée dans la littérature académique.</li>
                        </ul>
                      </div>
                    </div>
                    <div class="mt-3 pt-3 border-t border-slate-800 text-[10px] text-slate-500">
                      <strong class="text-slate-400">Interprétation recommandée :</strong> "Un panier d'ETFs factoriels aux mêmes expositions aurait réalisé
                      {{ (studyResult.block_f.replicant_total_pct >= 0 ? '+' : '') + formatPercentRaw(studyResult.block_f.replicant_total_pct) }} —
                      le gérant a {{ studyResult.block_f.alpha_gap_pct >= 0 ? 'ajouté' : 'détruit' }}
                      {{ formatPercentRaw(Math.abs(studyResult.block_f.alpha_gap_pct)) }} au-delà
                      {{ Math.abs(studyResult.block_f.alpha_tstat) >= 2 ? '(statistiquement significatif)' : '(non significatif statistiquement)' }}."
                    </div>
                  </div>

                </template>
              </div>

              <!-- ── BLOC G — Brinson-Fachler Attribution ───────────── -->
              <div v-if="activeStudyTab === 'brinson'" class="flex flex-col gap-5">

                <!-- No result yet -->
                <div v-if="!brinsonResult && !brinsonLoading" class="card text-center py-12">
                  <div class="text-4xl mb-3">🎯</div>
                  <div class="text-slate-400 text-sm mb-2">Attribution Brinson-Fachler</div>
                  <div class="text-slate-600 text-xs mb-5 max-w-md mx-auto leading-relaxed">
                    Décompose la surperformance en <strong class="text-slate-400">Allocation + Sélection + Interaction</strong>.
                    Utilise les prix déjà importés dans l'onglet Sous-jacents.
                  </div>
                  <div v-if="!priceStatusList.some(u => u.available)" class="text-amber-500 text-xs mb-4">
                    ⚠ Aucun prix disponible — importez les séries dans l'onglet Sous-jacents.
                  </div>
                  <button
                    class="mx-auto px-5 py-2.5 text-sm font-semibold bg-blue-700 hover:bg-blue-600 text-white rounded-lg transition-colors flex items-center gap-2"
                    :disabled="brinsonLoading || !priceStatusList.some(u => u.available)"
                    @click="computeBrinson">
                    <span v-if="brinsonLoading" class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                    🎯 Calculer l'Attribution Brinson
                  </button>
                  <div v-if="brinsonError" class="mt-3 text-red-400 text-xs">{{ brinsonError }}</div>
                </div>

                <div v-if="brinsonLoading && !brinsonResult" class="card text-center py-8 text-slate-500 text-xs">
                  <div class="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
                  Calcul en cours — téléchargement des données sectorielles…
                </div>

                <template v-if="brinsonResult && brinsonResult.available">

                  <!-- Benchmark estimation warning -->
                  <div v-if="brinsonResult.bench_return_estimated"
                    class="text-amber-400 text-xs px-2 py-2 bg-amber-950/20 border border-amber-800/30 rounded-lg">
                    ⚠ Le retour du benchmark <strong>{{ brinsonResult.benchmark_ticker }}</strong> n'a pas pu être téléchargé directement (benchmark composite ou ticker non standard). Le retour benchmark affiché est une estimation pondérée à partir des ETFs sectoriels — interpréter le retour actif avec prudence.
                  </div>

                  <!-- Header -->
                  <div class="flex items-center justify-between">
                    <div class="text-[10px] text-slate-500">
                      {{ formatInt(brinsonResult.n_obs) }} obs · {{ formatDate(brinsonResult.period_start) }} → {{ formatDate(brinsonResult.period_end) }}
                      · Benchmark : <span class="font-mono text-blue-400">{{ brinsonResult.benchmark_ticker }}</span>
                      · {{ brinsonResult.n_holdings }} titres
                    </div>
                    <button
                      class="text-[10px] border border-slate-700 text-slate-500 hover:text-blue-300 hover:border-blue-700 px-2 py-1 rounded transition-colors"
                      :disabled="brinsonLoading"
                      @click="computeBrinson">↻ Recalculer</button>
                  </div>

                  <!-- KPIs -->
                  <div class="grid grid-cols-4 gap-3">
                    <div v-for="([label, val, cls, tip]) in [
                      ['Portefeuille', (brinsonResult.port_return_pct >= 0 ? '+' : '') + brinsonResult.port_return_pct + '%', brinsonResult.port_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400', 'Performance totale de la composition initiale du portefeuille sur la période'],
                      ['Benchmark', (brinsonResult.bench_return_pct >= 0 ? '+' : '') + brinsonResult.bench_return_pct + '%', 'text-blue-400', 'Performance totale du benchmark sur la même période'],
                      ['Retour actif', (brinsonResult.active_return_pct >= 0 ? '+' : '') + brinsonResult.active_return_pct + '%', brinsonResult.active_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400', 'Portefeuille − Benchmark = valeur ajoutée active (doit égaler A + S + I)'],
                      ['A + S + I', (brinsonResult.check_pct >= 0 ? '+' : '') + brinsonResult.check_pct + '%', 'text-slate-400', 'Vérification : Allocation + Sélection + Interaction doit égaler le retour actif'],
                    ]" :key="label" class="card text-center">
                      <div class="text-[10px] text-slate-500 mb-1 flex items-center justify-center gap-1">
                        {{ label }}
                        <span :title="tip" class="cursor-help text-[8px] text-slate-600 hover:text-slate-400 border border-slate-700 rounded-full w-3.5 h-3.5 flex items-center justify-center leading-none">?</span>
                      </div>
                      <div class="text-lg font-black font-mono" :class="cls">{{ val }}</div>
                    </div>
                  </div>

                  <!-- Waterfall Brinson -->
                  <div class="card">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-1.5">
                      Décomposition Brinson-Fachler
                      <span title="Brinson-Fachler (1985) : Allocation = (w_p − w_b) × (r_b,s − R_b). Sélection = w_b × (r_p,s − r_b,s). Interaction = (w_p − w_b) × (r_p,s − r_b,s). Vérification : la somme des trois effets = retour actif total." class="cursor-help text-[8px] text-slate-600 hover:text-slate-400 border border-slate-700 rounded-full w-3.5 h-3.5 flex items-center justify-center leading-none">?</span>
                    </div>
                    <div class="flex flex-col gap-3">
                      <div v-for="([label, val, color, desc]) in [
                        ['Effet Allocation',   brinsonResult.allocation_pct,  '#3b82f6', 'Surpondérer les bons secteurs : (w_p − w_b) × (r_b,secteur − R_benchmark)'],
                        ['Effet Sélection',    brinsonResult.selection_pct,   '#10b981', 'Choisir de meilleurs titres dans chaque secteur : w_b × (r_p,secteur − r_b,secteur)'],
                        ['Effet Interaction',  brinsonResult.interaction_pct, '#f59e0b', 'Surpondérer là où on surperforme : (w_p − w_b) × (r_p,secteur − r_b,secteur)'],
                        ['Retour actif total', brinsonResult.active_return_pct, brinsonResult.active_return_pct >= 0 ? '#10b981' : '#ef4444', 'Somme des trois effets = performance portefeuille − performance benchmark'],
                      ]" :key="label" class="flex items-center gap-3">
                        <div class="text-xs text-slate-400 w-40 shrink-0 flex items-center gap-1">
                          {{ label }}
                          <span :title="desc" class="cursor-help text-[8px] text-slate-600 border border-slate-700 rounded-full w-3 h-3 flex items-center justify-center leading-none shrink-0">?</span>
                        </div>
                        <div class="flex-1 h-5 bg-slate-800 rounded overflow-hidden relative">
                          <div class="h-full rounded transition-all duration-500"
                            :style="{
                              width: Math.abs(val) / Math.max(0.01, Math.max(Math.abs(brinsonResult.allocation_pct), Math.abs(brinsonResult.selection_pct), Math.abs(brinsonResult.interaction_pct), Math.abs(brinsonResult.active_return_pct))) * 50 + '%',
                              marginLeft: val < 0 ? 'auto' : '0',
                              backgroundColor: val >= 0 ? color : '#ef4444',
                            }"></div>
                        </div>
                        <div class="text-xs font-mono font-bold w-14 text-right shrink-0"
                          :style="{ color: val >= 0 ? color : '#ef4444' }">
                          {{ val >= 0 ? '+' : '' }}{{ formatPercent(val, 2) }}
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Sector table -->
                  <div class="card overflow-x-auto table-shell" tabindex="0" role="region">
                    <div class="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                      Détail par secteur GICS
                      <span title="w_p = poids portefeuille, w_b = poids benchmark, Δw = poids actif (excès). r_p = rendement portefeuille dans ce secteur, r_b = rendement benchmark dans ce secteur (proxy ETF SPDR)." class="cursor-help text-[8px] text-slate-600 hover:text-slate-400 border border-slate-700 rounded-full w-3.5 h-3.5 flex items-center justify-center leading-none">?</span>
                    </div>
                    <table class="w-full text-xs min-w-[800px]">
                      <thead>
                        <tr class="text-slate-500 border-b border-slate-700">
                          <th class="text-left py-2 px-2">Secteur</th>
                          <th class="text-right py-2 px-2">w_p%</th>
                          <th class="text-right py-2 px-2">w_b%</th>
                          <th class="text-right py-2 px-2">Δw%</th>
                          <th class="text-right py-2 px-2">R_p%</th>
                          <th class="text-right py-2 px-2">R_b%</th>
                          <th class="text-right py-2 px-2">Allocation</th>
                          <th class="text-right py-2 px-2">Sélection</th>
                          <th class="text-right py-2 px-2">Interaction</th>
                          <th class="text-right py-2 px-2 font-bold">Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="row in brinsonResult.sector_rows" :key="row.sector"
                          class="border-b border-slate-800/50 hover:bg-slate-800/30">
                          <td class="py-1.5 px-2 text-slate-300 font-semibold">
                            {{ row.sector }}
                            <span class="text-slate-600 font-normal text-[10px] ml-1">({{ row.n_holdings }} titres)</span>
                          </td>
                          <td class="py-1.5 px-2 text-right font-mono text-slate-400">{{ formatNumber(row.w_p, 2) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono text-slate-500">{{ formatNumber(row.w_b, 2) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono font-bold"
                            :class="row.active_w > 0 ? 'text-blue-400' : row.active_w < 0 ? 'text-orange-400' : 'text-slate-500'">
                            {{ row.active_w > 0 ? '+' : '' }}{{ formatNumber(row.active_w, 2) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono"
                            :class="row.r_p >= 0 ? 'text-emerald-400' : 'text-red-400'">
                            {{ row.r_p >= 0 ? '+' : '' }}{{ formatNumber(row.r_p, 2) }}%</td>
                          <td class="py-1.5 px-2 text-right font-mono text-slate-500">
                            {{ row.r_b >= 0 ? '+' : '' }}{{ formatNumber(row.r_b, 2) }}%</td>
                          <td class="py-1.5 px-2 text-right font-mono"
                            :class="row.allocation > 0 ? 'text-blue-400' : row.allocation < 0 ? 'text-red-400' : 'text-slate-600'">
                            {{ row.allocation > 0 ? '+' : '' }}{{ formatPercentRaw(row.allocation) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono"
                            :class="row.selection > 0 ? 'text-emerald-400' : row.selection < 0 ? 'text-red-400' : 'text-slate-600'">
                            {{ row.selection > 0 ? '+' : '' }}{{ formatPercentRaw(row.selection) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono"
                            :class="row.interaction > 0 ? 'text-amber-400' : row.interaction < 0 ? 'text-red-400' : 'text-slate-600'">
                            {{ row.interaction > 0 ? '+' : '' }}{{ formatPercentRaw(row.interaction) }}</td>
                          <td class="py-1.5 px-2 text-right font-mono font-black"
                            :class="row.total > 0 ? 'text-emerald-400' : row.total < 0 ? 'text-red-400' : 'text-slate-500'">
                            {{ row.total > 0 ? '+' : '' }}{{ formatPercentRaw(row.total) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  <!-- Top / Bottom 5 -->
                  <div class="grid grid-cols-2 gap-4">
                    <div class="card">
                      <div class="text-xs font-bold text-emerald-400 mb-3">🏆 Top 5 contributeurs</div>
                      <div v-for="(item, i) in brinsonResult.top5" :key="item.name"
                        class="flex items-center gap-2 py-1.5 border-b border-slate-800/50 last:border-0">
                        <div class="text-slate-600 text-[10px] w-3 shrink-0">{{ i + 1 }}</div>
                        <div class="flex-1 min-w-0">
                          <div class="text-xs text-slate-200 font-semibold truncate">{{ item.name }}</div>
                          <div class="text-[10px] text-slate-500">{{ item.sector }} · w: {{ formatPercentRaw(item.weight_pct) }} · r: {{ item.return_pct >= 0 ? '+' : '' }}{{ formatPercentRaw(item.return_pct) }}</div>
                        </div>
                        <div class="text-sm font-black font-mono text-emerald-400 shrink-0">
                          +{{ formatPercentRaw(item.contribution_pct) }}
                        </div>
                      </div>
                    </div>
                    <div class="card">
                      <div class="text-xs font-bold text-red-400 mb-3">📉 Bottom 5 contributeurs</div>
                      <div v-for="(item, i) in brinsonResult.bottom5" :key="item.name"
                        class="flex items-center gap-2 py-1.5 border-b border-slate-800/50 last:border-0">
                        <div class="text-slate-600 text-[10px] w-3 shrink-0">{{ i + 1 }}</div>
                        <div class="flex-1 min-w-0">
                          <div class="text-xs text-slate-200 font-semibold truncate">{{ item.name }}</div>
                          <div class="text-[10px] text-slate-500">{{ item.sector }} · w: {{ formatPercentRaw(item.weight_pct) }} · r: {{ item.return_pct >= 0 ? '+' : '' }}{{ formatPercentRaw(item.return_pct) }}</div>
                        </div>
                        <div class="text-sm font-black font-mono text-red-400 shrink-0">
                          {{ formatPercentRaw(item.contribution_pct) }}
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Methodology note -->
                  <div class="card border border-slate-700/40 bg-slate-900/30">
                    <div class="text-[9px] text-slate-500 uppercase tracking-wider font-bold mb-2">Note méthodologique</div>
                    <div class="text-[10px] text-slate-500 leading-relaxed mb-2">{{ brinsonResult.methodology_note }}</div>
                    <div class="grid grid-cols-2 gap-3 text-[10px] mt-2">
                      <div><span class="text-slate-600">Poids portefeuille :</span> <span class="text-slate-400">{{ brinsonResult.weights_method }}</span></div>
                      <div><span class="text-slate-600">Poids benchmark :</span> <span class="text-slate-400">{{ brinsonResult.bench_weight_method }}</span></div>
                    </div>
                    <div class="mt-2 pt-2 border-t border-slate-800 text-[10px] text-amber-700/70 space-y-0.5">
                      <div>⚠ Rendements sectoriels benchmark = ETFs SPDR (XLK/XLF/XLV…) — biais US. Pour AMC international, l'effet Sélection est plus fiable que l'effet Allocation.</div>
                      <div>⚠ Benchmark snapshot actuel supposé stable sur la période (raccourci méthodologique noté dans le rapport).</div>
                    </div>
                  </div>

                </template>
              </div>


            </div>
          </div>
        </template><!-- /study results -->

        </template><!-- /STUDY MODE panel -->

      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { Chart, registerables } from 'chart.js'
import { apiFetch } from '../utils/api.js'
import { useDemoModeStore } from '../stores/demoMode.js'
import { chartTheme, applyChartTheme } from '../charts/theme.js'
import SensitiveValue from '../components/SensitiveValue.vue'
import { formatPercent, formatPercentRaw, formatNumber, formatInt, formatMoneyRound, formatDate } from '../utils/format.js'

Chart.register(...registerables)
applyChartTheme(Chart)

const demo = useDemoModeStore()

// Labels of absolute monetary amounts that must be masked in confidential mode
const SENSITIVE_AMT_LABELS = new Set([
  'P&L réalisé', 'P&L latent', 'P&L total',
  'Gross traded', 'AUM moyen',
  'P&L moyen (gain)', 'P&L moyen (perte)', 'P&L réalisé total',
])
function isSensitiveAmt(label) { return SENSITIVE_AMT_LABELS.has(label) }

// ── State ─────────────────────────────────────────────────────────────
const uploadedFile    = ref(null)
const uploadLoading   = ref(false)
const uploadError     = ref('')
const parsed          = ref(null)

const analyzing       = ref(false)
const analyzeError    = ref('')
const result          = ref(null)
const pdfLoading      = ref(false)

const ffSeries        = ref([])
const benchmarks          = ref([])
const isinBenchmarkMap    = ref({})
const customTicker    = ref('')
const studyCustomTicker = ref('')
const rollingVisible  = ref([])
const ffStatus        = ref([])

// Study mode — Factoriel (A) charts
const studyRollingVisible  = ref([])
let studyRollingChartRef   = null
let studyPerfChartRef      = null
let studyRollingChart      = null
let studyPerfChart         = null
const refreshing      = ref('')
const refreshError    = ref('')

// ── Main tab switcher ─────────────────────────────────────────────────
const mainTab = ref('classic')  // 'classic' | 'study'

// ── Classic mode config ───────────────────────────────────────────────
const config = ref({
  ff_series:         'Global_3F',
  selected_factors:  ['Mkt-RF', 'SMB', 'HML'],
  benchmark_ticker:  'IGF',
  rolling_window:    60,
})

// ── Study mode config (mirrors classic — kept independent) ────────────
const studyConfig = ref({
  ff_series:         'Developed_5F',
  selected_factors:  ['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA'],
  benchmark_ticker:  'IXG',
  rolling_window:    60,
})

const activeTab = ref('synthese')
const tabs = [
  { id: 'synthese',    label: '📊 Synthèse' },
  { id: 'performance', label: '📈 Performance' },
  { id: 'facteurs',    label: '🎯 Facteurs FF' },
  { id: 'activite',    label: '🔄 Activité & Portefeuille' },
  { id: 'donnees',     label: '📋 Données utilisées' },
]

// ── Chart refs ────────────────────────────────────────────────────────
const perfChartRef    = ref(null)
const ddChartRef      = ref(null)
const rollingChartRef = ref(null)
const r2ChartRef      = ref(null)
let charts = {}

// ── Load meta lists ───────────────────────────────────────────────────
async function loadFfStatus() {
  try {
    const res = await apiFetch('/api/amc/ff-status')
    if (res.ok) ffStatus.value = await res.json()
  } catch { /* ignore */ }
}

async function doRefresh(seriesKey) {
  refreshing.value = seriesKey
  refreshError.value = ''
  try {
    const res = await apiFetch(`/api/amc/ff-refresh?series_key=${encodeURIComponent(seriesKey)}`, { method: 'POST' })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Erreur ${res.status}`)
    }
    const data = await res.json()
    refreshError.value = ''
    await loadFfStatus()
    // Show inline success briefly
    const s = ffStatus.value.find(x => x.key === seriesKey)
    if (s) s._just_updated = true
    setTimeout(() => { if (s) delete s._just_updated }, 3000)
  } catch (e) {
    refreshError.value = `${seriesKey}: ${e.message}`
  } finally {
    refreshing.value = ''
  }
}

async function loadMeta() {
  try {
    const [fs, bmData] = await Promise.all([
      apiFetch('/api/amc/ff-series').then(r => r.json()),
      apiFetch('/api/amc/benchmarks').then(r => r.json()),
    ])
    ffSeries.value        = fs
    benchmarks.value      = bmData.items ?? bmData
    isinBenchmarkMap.value = bmData.isin_map ?? {}
  } catch { /* ignore if not logged in yet */ }
}
loadMeta()
loadFfStatus()

// ── Available factors for selected series ────────────────────────────
const availableFactors = computed(() => {
  const s = ffSeries.value.find(s => s.key === config.value.ff_series)
  return s?.factors || ['Mkt-RF', 'SMB', 'HML']
})

const studyAvailableFactors = computed(() => {
  const s = ffSeries.value.find(s => s.key === studyConfig.value.ff_series)
  return s?.factors || ['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA']
})

function onSeriesChange() {
  config.value.selected_factors = [...availableFactors.value]
}

function onStudySeriesChange() {
  studyConfig.value.selected_factors = [...studyAvailableFactors.value]
}

// Benchmarks grouped for display — UTI Benchmarks pinned first
const benchmarkGroups = computed(() => {
  const groups = {}
  for (const b of benchmarks.value) {
    const g = b.group || 'Autre'
    if (!groups[g]) groups[g] = []
    groups[g].push(b)
  }
  const PIN_FIRST = ['UTI Benchmarks']
  return Object.fromEntries(
    Object.entries(groups).sort(([a], [b]) => {
      const ai = PIN_FIRST.indexOf(a), bi = PIN_FIRST.indexOf(b)
      if (ai !== -1 && bi === -1) return -1
      if (ai === -1 && bi !== -1) return 1
      return 0
    })
  )
})

// ── File upload ───────────────────────────────────────────────────────
async function onFileChange(e) {
  const file = e.target.files?.[0]
  if (file) await doUpload(file)
}
function onDrop(e) {
  const file = e.dataTransfer.files?.[0]
  if (file) doUpload(file)
}

async function doUpload(file) {
  uploadedFile.value = file
  uploadLoading.value = true
  uploadError.value = ''
  parsed.value = null
  result.value = null

  const form = new FormData()
  form.append('file', file)
  try {
    const res = await apiFetch('/api/amc/upload', { method: 'POST', body: form })
    if (!res.ok) { const e = await res.json(); throw new Error(e.detail) }
    parsed.value = await res.json()
  } catch (e) {
    uploadError.value = e.message
    uploadedFile.value = null
  } finally {
    uploadLoading.value = false
  }
}

// ── Analyze ───────────────────────────────────────────────────────────
async function analyze() {
  if (!parsed.value) return
  analyzing.value = true
  analyzeError.value = ''
  result.value = null

  const ticker = config.value.benchmark_ticker === 'CUSTOM'
    ? customTicker.value.trim().toUpperCase()
    : config.value.benchmark_ticker

  const body = {
    nav:              parsed.value.nav,
    transactions:     parsed.value.transactions,
    composition:      parsed.value.composition,
    exposures:        parsed.value.exposures,
    ff_series:        config.value.ff_series,
    selected_factors: config.value.selected_factors,
    benchmark_ticker: ticker,
    rolling_window:   config.value.rolling_window,
  }

  try {
    const res = await apiFetch('/api/amc/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const text = await res.text()
      try { const err = JSON.parse(text); throw new Error(err.detail) }
      catch { throw new Error(text.slice(0, 300)) }
    }
    result.value = await res.json()
    rollingVisible.value = result.value.factors_used?.slice(0, 3) || []
    activeTab.value = 'synthese'
    await nextTick()
    buildCharts()
  } catch (e) {
    analyzeError.value = e.message
  } finally {
    analyzing.value = false
  }
}

// ── Charts ────────────────────────────────────────────────────────────
const FACTOR_COLORS = chartTheme.series

function destroyAll() {
  Object.values(charts).forEach(c => c?.destroy())
  charts = {}
}

function buildCharts() {
  destroyAll()
  if (!result.value) return
  const perf = result.value.performance

  // Performance chart
  if (perfChartRef.value) {
    const datasets = [{
      label: 'AMC', data: perf.cum_amc.map(v => +(v * 100).toFixed(2)),
      borderColor: chartTheme.primary, backgroundColor: 'transparent',
      borderWidth: 2, pointRadius: 0, tension: 0.3,
    }]
    if (perf.cum_bm?.length) {
      datasets.push({
        label: result.value.benchmark,
        data: perf.cum_bm.map(v => +(v * 100).toFixed(2)),
        borderColor: chartTheme.gold, backgroundColor: 'transparent',
        borderWidth: 1.5, borderDash: [4,2], pointRadius: 0, tension: 0.3,
      })
    }
    charts.perf = new Chart(perfChartRef.value, {
      type: 'line',
      data: { labels: perf.dates, datasets },
      options: chartOpts('%', 'Rendement cumulé (%)'),
    })
  }

  // Drawdown chart
  if (ddChartRef.value) {
    charts.dd = new Chart(ddChartRef.value, {
      type: 'line',
      data: {
        labels: perf.dates,
        datasets: [{
          label: 'Drawdown', data: perf.drawdown.map(v => +(v * 100).toFixed(2)),
          borderColor: chartTheme.negative, backgroundColor: chartTheme.negativeFill,
          borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.2,
        }]
      },
      options: chartOpts('%', 'Drawdown (%)', true),
    })
  }

  buildRollingCharts()
}

function buildRollingCharts() {
  if (!result.value?.rolling?.length) return
  const rolling = result.value.rolling

  // Rolling betas
  if (rollingChartRef.value) {
    charts.rolling?.destroy()
    const dates = rolling.map(r => formatDate(r.date))
    const datasets = result.value.factors_used
      .filter(f => rollingVisible.value.includes(f))
      .map((f, i) => ({
        label: f, data: rolling.map(r => r[f] ?? null),
        borderColor: FACTOR_COLORS[i % FACTOR_COLORS.length],
        backgroundColor: 'transparent',
        borderWidth: 2, pointRadius: 0, tension: 0.3,
      }))
    charts.rolling = new Chart(rollingChartRef.value, {
      type: 'line',
      data: { labels: dates, datasets },
      options: chartOpts('', 'Beta'),
    })
  }

  // Rolling R²
  if (r2ChartRef.value) {
    charts.r2?.destroy()
    charts.r2 = new Chart(r2ChartRef.value, {
      type: 'line',
      data: {
        labels: rolling.map(r => formatDate(r.date)),
        datasets: [{
          label: 'R²', data: rolling.map(r => +(r.r2 * 100).toFixed(1)),
          borderColor: chartTheme.series[4], backgroundColor: 'rgba(124,92,214,0.1)',
          borderWidth: 2, pointRadius: 0, fill: true, tension: 0.3,
        }]
      },
      options: chartOpts('%', 'R² (%)'),
    })
  }
}

function chartOpts(unit, label, invertY = false) {
  return {
    responsive: true, maintainAspectRatio: true,
    plugins: {
      legend: { display: true, labels: { font: { size: 10 }, boxWidth: 12 } },
      tooltip: {
        callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y}${unit}` },
      },
    },
    scales: {
      x: { ticks: { font: { size: 9 }, maxTicksLimit: 8 } },
      y: {
        ticks: { font: { size: 9 }, callback: v => v + unit },
        reverse: invertY,
        title: { display: false },
      },
    },
  }
}

async function exportPdf() {
  if (!result.value) return
  pdfLoading.value = true
  try {
    const res = await apiFetch('/api/amc/export-pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        result: result.value,
        meta: parsed.value?.meta || {},
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Erreur ${res.status}`)
    }
    const blob = await res.blob()
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    const isin = parsed.value?.meta?.isin || 'report'
    a.href     = url
    a.download = `AMC_FF_${isin}_${new Date().toISOString().slice(0,10)}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    analyzeError.value = `PDF : ${e.message}`
  } finally {
    pdfLoading.value = false
  }
}

function toggleRolling(factor) {
  const idx = rollingVisible.value.indexOf(factor)
  if (idx >= 0) rollingVisible.value.splice(idx, 1)
  else rollingVisible.value.push(factor)
  nextTick(buildRollingCharts)
}

// ── Study (manifest-based full pipeline) ──────────────────────────────
const studyMode       = ref(false)       // switch between FF-only and full study
const studyFolder     = ref('')          // absolute path on the server
const manifestData    = ref(null)        // pre-filled manifest from detect or template
const studyResult     = ref(null)        // run_study() output
const lastRunManifest = ref(null)        // exact manifest sent to /study/run (for save/reload)
const showTsEditor    = ref(false)
const tsEditorError   = ref('')
const tsEditorJson    = ref('')

function openTsEditor() {
  const pos = manifestData.value?.manifest?.params?.termsheet_positions || []
  tsEditorJson.value = pos.length ? JSON.stringify(pos, null, 2) : ''
  tsEditorError.value = ''
  showTsEditor.value = !showTsEditor.value
}

function applyTsPositions() {
  tsEditorError.value = ''
  try {
    const parsed = JSON.parse(tsEditorJson.value || '[]')
    if (!Array.isArray(parsed)) throw new Error('Doit être un tableau JSON []')
    manifestData.value.manifest.params.termsheet_positions = parsed
    showTsEditor.value = false
  } catch (e) {
    tsEditorError.value = e.message
  }
}

function exportTsJson() {
  const pos = manifestData.value?.manifest?.params?.termsheet_positions || []
  const blob = new Blob([JSON.stringify(pos, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'termsheet_positions.json'
  a.click()
  URL.revokeObjectURL(url)
}

// ── Client / ISIN quick-select ─────────────────────────────────────────
const selectedClient   = ref('')
const selectedUtiIsin  = ref('')
const UTI_BASE_PATH    = 'C:\\Users\\phili\\Downloads\\UTI\\Data\\'
const UTI_ISINS = [
  { isin: 'CH1352587708', label: 'New Financials — CHF', ccy: 'CHF' },
  { isin: 'CH1352587716', label: 'New Financials — EUR', ccy: 'EUR' },
  { isin: 'CH1352587724', label: 'New Financials — USD', ccy: 'USD' },
  { isin: 'CH1473731680', label: 'NEÜ Life — USD',        ccy: 'USD' },
  { isin: 'CH1473733934', label: 'NEÜ Infrastructures — CHF', ccy: 'CHF' },
  { isin: 'CH1473733959', label: 'NEÜ Infrastructures — USD', ccy: 'USD' },
  { isin: 'CH1473736143', label: 'NEÜ Infrastructures H — USD', ccy: 'USD' },
]
watch(selectedUtiIsin, (isin) => {
  if (isin) studyFolder.value = UTI_BASE_PATH + isin
})

// Auto-select UTI benchmark when an ISIN is detected
watch(manifestData, (data) => {
  if (!data) return
  const isin = data.manifest?.product?.isin
  if (isin && isinBenchmarkMap.value[isin]) {
    studyConfig.value.benchmark_ticker = isinBenchmarkMap.value[isin]
  }
})
const studyLoading    = ref(false)
const studyError      = ref('')
const studyPdfLoading       = ref(false)
const studyPdfSimpleLoading = ref(false)
const includeBrinsonInPdf   = ref(false)
const includeMarketShocksInPdf = ref(false)
const studyDoc        = ref(null)        // field doc + block catalog
const activeStudyTab  = ref('meta')
const studyTabs = [
  { id: 'synthese',   label: '✍️ Synthèse' },
  { id: 'payload_ai', label: '🤖 Données IA' },
  { id: 'meta',       label: '📋 Méta & Blocs' },
  { id: 'factoriel',  label: '🎯 A — Factoriel' },
  { id: 'attribution',label: '💰 B — Attribution' },
  { id: 'trading',    label: '🔄 C — Trading' },
  { id: 'behaviour',  label: '🧠 D — Comportement' },
  { id: 'bh',            label: '📈 E — Référentiel Inertiel' },
  { id: 'prices',        label: '📦 Sous-jacents' },
  { id: 'replicability', label: '🔁 F — Réplicabilité' },
  { id: 'brinson',       label: '🎯 G — Brinson' },
  { id: 'timing',        label: '⏱ H — Timing Score' },
  { id: 'stockpicking',  label: '🎯 I — Stock Picking' },
  { id: 'riskmanagement',label: '🛡 J — Risk Mgmt' },
  { id: 'marketshocks',  label: '🌍 K — Chocs de Marché' },
  { id: 'managerskill',  label: '⭐ Manager Skill' },
  { id: 'confidence',    label: '📊 Confiance & Limites' },
]

const syntheseText = ref('')

// ── Methodology box ───────────────────────────────────────────────────────
const showMethodology = ref(false)
watch(activeStudyTab, () => { showMethodology.value = false })

const blockMethodology = {
  factoriel: {
    label: 'A — Analyse factorielle Fama-French',
    but: 'Mesurer la part de performance expliquée par des facteurs de marché systématiques (taille, valeur, profitabilité, momentum) et isoler l\'alpha pur du gérant — ce que le marché ne lui "donne" pas gratuitement.',
    methode: 'Régression OLS des rendements journaliers de la NAV (nette de frais) sur les primes de facteurs Ken French. L\'alpha annualisé est la composante non expliquée par ces primes. La version brute (NAV re-grossie des frais) montre l\'alpha avant imputation des coûts.',
    limites: 'Nécessite au moins 30 observations. La série FF a une date de fin fixe — la performance récente hors fenêtre n\'est pas capturée dans l\'alpha. Le R² peut être élevé sans que le gérant soit réplicable (biais de sélection des facteurs).',
    sources: 'Kenneth French Data Library (dartmouth.edu). Rendements NAV journaliers depuis le fichier timeseries.',
  },
  attribution: {
    label: 'B — Attribution P&L par titre',
    but: 'Identifier quels titres ont contribué positivement ou négativement au P&L. Distinguer le gain réalisé (positions soldées) du gain latent (positions ouvertes). Répondre à : "qui a gagné de l\'argent pour le gérant ?"',
    methode: 'Reconstruction FIFO des round-trips. P&L réalisé = ventes × (prix_vente − coût_moyen_FIFO). P&L latent = positions ouvertes × (mark_actuel − coût_moyen_FIFO). Le coût moyen est recalculé à chaque achat.',
    limites: 'Les positions antérieures au premier ordre du carnet sont reconstruites synthétiquement (cours yfinance à T0). Le P&L de ces entrées synthétiques peut être approximatif si le prix yfinance à T0 est erroné.',
    sources: 'Carnet d\'ordres JSON. Snapshot composition Def.txt pour les marks courants.',
  },
  trading: {
    label: 'C — Analyse de l\'activité de trading',
    but: 'Évaluer l\'intensité et la cohérence des décisions de trading : combien le gérant trade-t-il ? À quelle fréquence ? Quel turnover génère-t-il ? Les durées de détention sont-elles cohérentes avec la stratégie affichée ?',
    methode: 'Agrégation des ordres exécutés par mois et par titre. Turnover = notionnel brut total (achats + ventes) / AUM estimé moyen. Durée de détention calculée par round-trip FIFO.',
    limites: 'Le turnover peut être surestimé si l\'AUM varie fortement (rachat de certificats non capturé). Les ordres synthétiques T0 sont exclus du calcul.',
    sources: 'Carnet d\'ordres JSON. AUM estimé depuis le snapshot Def.txt (NAV × certificats).',
  },
  behaviour: {
    label: 'D — Matrice comportementale conviction / résultat',
    but: 'Diagnostiquer les biais comportementaux du gérant : loss aversion (garder trop longtemps les perdants), overconfidence (trop de conviction sur des positions qui perdent), ou inversement une gestion disciplinée.',
    methode: 'Chaque position terminée est placée dans une matrice 2×2 : axe X = P&L réalisé, axe Y = score de conviction (poids × durée de détention normalisés). Quatre quadrants : Stars (bon P&L + haute conviction), Traps (bon P&L + faible conviction), Losers (mauvais P&L + haute conviction = loss aversion), Duds (mauvais P&L + faible conviction).',
    limites: 'Les seuils de conviction et de P&L sont configurables dans le manifeste AMC. Un quadrant "Losers" élevé peut refléter une stratégie long-term value plutôt que du loss aversion.',
    sources: 'Round-trips reconstruits (Bloc B). Paramètres de seuils dans le manifeste AMC.',
  },
  bh: {
    label: 'E — Référentiel Inertiel (Buy & Hold depuis l\'émission)',
    but: 'Répondre à : "Si le gérant n\'avait rien fait depuis l\'émission, quelle serait la performance ?" C\'est le plancher de toute gestion active. VAG = NAV réelle − Référentiel Inertiel. VAG > 0 → le gérant a créé de la valeur.',
    methode: 'Source primaire : poids de la term sheet (params.termsheet_positions). Performance = Σ(poids_TS × total_return_yfinance) / Σ(poids_TS). Fallback : identité comptable qty_initiale = position_actuelle + ventes − achats. Prix ajustés yfinance (dividendes inclus, total return). FX intégré.',
    limites: 'Méthode TS : immunisée aux splits. Méthode comptable : peut inclure des positions absentes du panier initial après 2+ ans de rebalancing. Renseignez params.termsheet_positions dans le manifeste pour la méthode exacte.',
    sources: 'params.termsheet_positions (recommandé) ou carnet d\'ordres + Def.txt (fallback). yfinance pour les prix ajustés T0 et actuels.',
  },
  replicability: {
    label: 'F — Réplicabilité par un ETF passif',
    but: 'Peut-on reproduire la stratégie avec un ETF passif à moindre coût ? Un R² élevé indique que le gérant "ressemble" à un indice — sa valeur ajoutée potentielle est faible relativement aux frais.',
    methode: 'Comparaison du R² factoriel avec un seuil de réplicabilité configuré. Calcul de l\'information ratio (alpha / tracking error vs benchmark). Analyse du gap de performance vs le benchmark défini.',
    limites: 'Un R² élevé n\'est pas nécessairement négatif pour une stratégie factor-based explicite. La réplicabilité dépend du benchmark choisi — un benchmark non adapté biaiserait le diagnostic.',
    sources: 'Résultats du Bloc A (régression OLS). Benchmark défini dans le manifeste AMC.',
  },
  brinson: {
    label: 'G — Attribution Brinson-Fachler (allocation + sélection)',
    but: 'Décomposer la sur- ou sous-performance en deux effets : Allocation (le gérant a-t-il surpondéré les bons secteurs ?) et Sélection (a-t-il choisi les meilleurs titres au sein de chaque secteur ?).',
    methode: 'Attribution Brinson-Fachler. Poids portefeuille = snapshot actuel Def.txt. Benchmark sectoriel = ETFs SPDR (XLK, XLF, XLV, XLE…). Rendements calculés sur la durée de vie du carnet d\'ordres.',
    limites: 'Benchmark sectoriel basé sur des ETFs US — biais pour les AMC à composantes non-US. Le snapshot de composition est figé (pas une série temporelle de poids). L\'effet Sélection est plus fiable que l\'effet Allocation pour les AMC internationaux.',
    sources: 'Composition Def.txt. ETFs SPDR sectoriels via yfinance. Carnet d\'ordres JSON.',
  },
  timing: {
    label: 'H — Timing Score',
    but: 'Le gérant achète-t-il à des prix bas et vend-il à des prix hauts ? Un score > 50% signifie un meilleur timing que le hasard. Répondre à : "est-ce que le gérant entre et sort au bon moment ?"',
    methode: 'Pour chaque trade, calcul du score positionnel dans le range [min, max] des 30 jours autour de l\'ordre (fenêtre ±15 jours). Score achat : position dans le range (0 = le moins cher, 1 = le plus cher). Score vente = 1 − score achat. Moyenne et test t vs 0.5 (hypothèse nulle = timing aléatoire).',
    limites: 'Utilise des prix ex-post (évaluation rétrospective). Significatif statistiquement seulement pour N > 30 trades. Ne capture pas la gestion du risque intraday ni les conditions de marché extraordinaires.',
    sources: 'Carnet d\'ordres JSON. Prix historiques yfinance (fenêtre ±15 jours autour de chaque trade).',
  },
  stockpicking: {
    label: 'I — Stock Picking Score',
    but: 'Les titres sélectionnés par le gérant ont-ils surperformé leur benchmark sectoriel pendant la période de détention ? Mesure la qualité de la sélection de titres indépendamment du timing.',
    methode: 'Pour chaque round-trip complet, comparaison du rendement du titre (prix entrée → prix sortie) vs rendement de l\'ETF sectoriel correspondant sur la même période. Score = fraction de positions ayant battu leur benchmark sectoriel.',
    limites: 'Dépend du mapping ISIN → secteur GICS (peut être imprécis pour les titres hors-US). Les positions toujours ouvertes à la date du snapshot sont évaluées au mark courant.',
    sources: 'Round-trips Bloc B. Rendements ETFs SPDR sectoriels via yfinance. Mapping GICS via yfinance ticker info.',
  },
  riskmanagement: {
    label: 'J — Risk Management Score',
    but: 'Le gérant gère-t-il correctement son exposition au risque ? Score de la discipline de construction de portefeuille : diversification, drawdowns, cohérence conviction/sizing.',
    methode: 'Score composite basé sur : concentration (indice HHI), diversification sectorielle et géographique, drawdown maximal, ratio Sharpe, et cohérence entre conviction affichée et taille réelle des positions.',
    limites: 'Évaluation rétroactive basée sur le snapshot actuel — ne capture pas la dynamique intra-période du risque. Un HHI élevé peut être intentionnel pour une stratégie concentrée assumée.',
    sources: 'Snapshot Def.txt. Carnet d\'ordres JSON. Résultats blocs B/C (P&L, durée de détention).',
  },
  marketshocks: {
    label: 'K — Réactivité aux Chocs de Marché',
    but: 'Juxtaposer l\'activité de trading avec les grands chocs de marché (subprimes, Chine 2015/2021/2023, COVID, SVB...) pour identifier une sur-réaction, une sous-réaction, ou une gestion disciplinée pendant ces épisodes de stress.',
    methode: 'Pour chaque événement chevauchant l\'historique du fonds : ratio d\'activité = volume tradé pendant la fenêtre / volume journalier moyen du fonds hors fenêtres d\'événements. Flux net acheteur/vendeur. Qualité de timing des trades exécutés dans la fenêtre (recoupée avec le Bloc H si disponible).',
    limites: 'Calendrier statique et non exhaustif. Un fonds émis après le dernier choc du calendrier n\'aura aucun événement applicable — cas fréquent pour les AMC récents. Échantillon parfois très faible (fenêtre courte, fonds peu actif) : chaque événement rapporte son propre nombre de trades pour juger la significativité.',
    sources: 'Carnet d\'ordres JSON (corrigé des splits). Résultat Bloc H (optionnel, pour la qualité de timing).',
  },
  managerskill: {
    label: 'Score Global Manager Skill',
    but: 'Agréger les dimensions de compétence du gérant en un score composite unique (0–100), comparable entre AMCs d\'un même univers. Répondre à : "ce gérant apporte-t-il de la valeur par ses décisions ?"',
    methode: 'Moyenne pondérée des scores normalisés des blocs H (timing), I (stock picking), J (risk management) et optionnellement E (valeur ajoutée de gestion). Les pondérations sont configurables dans le manifeste.',
    limites: 'La pondération des composantes est paramétrique — elle influence le classement. Interprétation prudente si N < 30 trades. La comparabilité inter-AMC n\'est valide que si les manifestes utilisent les mêmes pondérations.',
    sources: 'Blocs H, I, J, E (optionnel).',
  },
  confidence: {
    label: 'Confiance & Limites de l\'étude',
    but: 'Évaluer la fiabilité statistique globale de l\'étude, identifier les points de fragilité (peu de données, fenêtre FF courte, ordres manquants) et guider l\'interprétation avec les précautions appropriées.',
    methode: 'Score de confiance composite pondéré sur : nombre d\'observations NAV, nombre de trades réels, complétude du carnet d\'ordres, disponibilité des prix yfinance, overlap avec les données Ken French.',
    limites: 'Un score de confiance élevé garantit la robustesse des calculs, pas la qualité de la gestion. Un score faible ne signifie pas que les résultats sont faux — ils peuvent rester indicatifs.',
    sources: 'Tous les blocs exécutés.',
  },
}

const currentMethodology = computed(() => blockMethodology[activeStudyTab.value] || null)

// ── AI Synthesis state ────────────────────────────────────────────────────
const aiProvider     = ref(localStorage.getItem('ai_provider')     || 'ollama')
const aiOllamaUrl    = ref(localStorage.getItem('ai_ollama_url')   || 'http://localhost:11434')
const aiOllamaModel  = ref(localStorage.getItem('ai_ollama_model') || '')
const aiClaudeKey    = ref(localStorage.getItem('ai_claude_key')   || '')
const aiClaudeModel  = ref(localStorage.getItem('ai_claude_model') || 'claude-sonnet-4-6')
const aiOpenAiKey    = ref(localStorage.getItem('ai_openai_key')   || '')
const aiOpenAiModel  = ref(localStorage.getItem('ai_openai_model') || 'gpt-4o')
const aiGenerating   = ref(false)
const aiError        = ref('')
const aiGeneratedText = ref('')
const aiOllamaModels = ref([])
const aiOllamaModelsError = ref('')
const aiPayloadText  = ref('')
const aiPayloadLoading = ref(false)

function aiPersist() {
  localStorage.setItem('ai_provider',     aiProvider.value)
  localStorage.setItem('ai_ollama_url',   aiOllamaUrl.value)
  localStorage.setItem('ai_ollama_model', aiOllamaModel.value)
  localStorage.setItem('ai_claude_key',   aiClaudeKey.value)
  localStorage.setItem('ai_claude_model', aiClaudeModel.value)
  localStorage.setItem('ai_openai_key',   aiOpenAiKey.value)
  localStorage.setItem('ai_openai_model', aiOpenAiModel.value)
}

async function fetchOllamaModels() {
  aiOllamaModelsError.value = ''
  try {
    const url = encodeURIComponent(aiOllamaUrl.value || 'http://localhost:11434')
    const res  = await apiFetch(`/api/amc/synthesize/ollama-models?url=${url}`)
    const data = await res.json()
    if (data.error) { aiOllamaModelsError.value = data.error; return }
    aiOllamaModels.value = data.models || []
    if (aiOllamaModels.value.length && !aiOllamaModel.value) {
      aiOllamaModel.value = aiOllamaModels.value[0]
    }
  } catch (e) {
    aiOllamaModelsError.value = `Ollama inaccessible à ${aiOllamaUrl.value}`
  }
}

async function generateSynthesisAI() {
  if (!studyResult.value) return
  aiPersist()
  aiGenerating.value = true
  aiError.value = ''
  try {
    const res = await apiFetch('/api/amc/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        study_result:       studyResult.value,
        attribution_result: attrResult.value        || null,
        brinson_result:     brinsonResult.value     || null,
        provider:           aiProvider.value,
        ollama_url:         aiOllamaUrl.value,
        ollama_model:       aiOllamaModel.value,
        claude_key:         aiClaudeKey.value,
        claude_model:       aiClaudeModel.value,
        openai_key:         aiOpenAiKey.value,
        openai_model:       aiOpenAiModel.value,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Erreur ${res.status}`)
    }
    const data = await res.json()
    aiGeneratedText.value = data.synthesis || ''
    aiPayloadText.value   = data.payload   || ''
  } catch (e) {
    aiError.value = e.message || 'Erreur inconnue'
  } finally {
    aiGenerating.value = false
  }
}

async function fetchAIPayload() {
  if (!studyResult.value) return
  aiPayloadLoading.value = true
  try {
    const res = await apiFetch('/api/amc/synthesize/payload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        study_result:       studyResult.value,
        attribution_result: attrResult.value        || null,
        brinson_result:     brinsonResult.value     || null,
      }),
    })
    const data = await res.json()
    aiPayloadText.value = data.payload || ''
  } catch (e) {
    aiPayloadText.value = `Erreur : ${e.message}`
  } finally {
    aiPayloadLoading.value = false
  }
}

function copyAiText(text) {
  navigator.clipboard.writeText(text).catch(() => {})
}

function insertGeneratedSynthesis() {
  syntheseText.value = aiGeneratedText.value
}

// ── VAG / Underlying prices ───────────────────────────────────────────
const priceStatusList   = ref([])
const priceStatusLoading= ref(false)
const priceRefreshing   = ref(null)
const priceErrors       = ref({})
const tickerResolving   = ref(false)
const tickerResolved    = ref({})   // key → 'found'|'not_found'|'error'
const fetchingAll       = ref(false)
const attrResult        = ref(null)
const attrLoading       = ref(false)
const attrError         = ref('')
const brinsonResult     = ref(null)
const brinsonLoading    = ref(false)
const brinsonError      = ref('')
const marketShocksLoading = ref(false)
const marketShocksError   = ref('')

const momFactor = computed(() =>
  studyResult.value?.block_a?.net?.regression?.factors?.find(f => f.name === 'MOM') ?? null
)

// ── Saved studies (server-backed, multiple versions per ISIN) ─────────
const savedStudies        = ref([])    // GET /api/amc/studies — most recent first
const savedStudiesLoading = ref(false)
const saveLabel           = ref('')
const saveLoading         = ref(false)
const saveError           = ref('')
const loadStudyLoadingId  = ref(null)  // id currently being loaded, for spinner

async function fetchSavedStudies() {
  savedStudiesLoading.value = true
  try {
    const res = await apiFetch('/api/amc/studies')
    if (res.ok) savedStudies.value = await res.json()
  } catch { /* ignore */ } finally {
    savedStudiesLoading.value = false
  }
}

async function saveStudy() {
  if (!studyResult.value) return
  saveLoading.value = true
  saveError.value = ''
  try {
    const res = await apiFetch('/api/amc/studies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        isin:         studyResult.value?.meta?.isin || '',
        product_name: studyResult.value?.meta?.product_name || '',
        label:        saveLabel.value.trim(),
        folder:       studyFolder.value,
        manifest:     lastRunManifest.value || manifestData.value?.manifest || {},
        result:       studyResult.value,
        synthese:     syntheseText.value,
      }),
    })
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `Erreur ${res.status}`) }
    saveLabel.value = ''
    await fetchSavedStudies()
  } catch (e) {
    saveError.value = `Sauvegarde : ${e.message}`
  } finally {
    saveLoading.value = false
  }
}

async function loadStudyById(id) {
  if (!id) return
  loadStudyLoadingId.value = id
  studyError.value = ''
  try {
    const res = await apiFetch(`/api/amc/studies/${id}`)
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `Erreur ${res.status}`) }
    const data = await res.json()
    mainTab.value          = 'study'
    studyFolder.value      = data.folder || ''
    manifestData.value     = { manifest: data.manifest }
    lastRunManifest.value  = data.manifest
    studyResult.value      = data.result
    syntheseText.value     = data.synthese || ''
    activeStudyTab.value   = 'meta'
    studyRollingVisible.value = data.result?.block_a?.net?.factors_used?.slice(0, 3) || []
    brinsonResult.value    = null
    attrResult.value       = null
    priceStatusList.value  = []
    const p = data.manifest?.params
    if (p) {
      studyConfig.value = {
        ff_series:        p.ff_series        ?? studyConfig.value.ff_series,
        selected_factors: p.selected_factors ?? studyConfig.value.selected_factors,
        benchmark_ticker: p.benchmark_ticker ?? studyConfig.value.benchmark_ticker,
        rolling_window:   p.rolling_window   ?? studyConfig.value.rolling_window,
      }
    }
    loadPriceStatus()
  } catch (e) {
    studyError.value = `Chargement étude : ${e.message}`
  } finally {
    loadStudyLoadingId.value = null
  }
}

async function deleteStudy(id) {
  if (!confirm('Supprimer cette étude sauvegardée ?')) return
  try {
    await apiFetch(`/api/amc/studies/${id}`, { method: 'DELETE' })
    await fetchSavedStudies()
  } catch { /* ignore */ }
}

async function loadPriceStatus() {
  if (!studyResult.value) return
  priceStatusLoading.value = true
  try {
    const underlyings = (studyResult.value.block_b?.per_name || []).map(r => ({
      isin: r.isin, name: r.name,
    }))
    const res = await apiFetch('/api/amc/prices/status-for-study', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ underlyings }),
    })
    if (res.ok) {
      const data = await res.json()
      // Merge ticker from existing list to preserve edits
      const existing = Object.fromEntries(priceStatusList.value.map(u => [u.key, u.ticker]))
      priceStatusList.value = data.map(u => ({
        ...u,
        ticker: existing[u.key] ?? u.ticker ?? '',
      }))
    }
  } finally {
    priceStatusLoading.value = false
  }
}

async function computeAttribution() {
  if (!studyResult.value || !studyFolder.value) return
  attrLoading.value = true
  attrError.value   = ''
  try {
    const res = await apiFetch('/api/amc/prices/attribution', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        folder:       studyFolder.value,
        study_result: studyResult.value,
        amc_currency: studyResult.value?.meta?.currency || 'CHF',
      }),
    })
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || `Erreur ${res.status}`) }
    attrResult.value = await res.json()
  } catch(e) {
    attrError.value = e.message
  } finally {
    attrLoading.value = false
  }
}

async function resolveAllTickers() {
  if (!priceStatusList.value.length) return
  tickerResolving.value = true
  tickerResolved.value = {}
  try {
    const payload = priceStatusList.value.map(u => ({ key: u.key, isin: u.isin || '', name: u.name || '' }))
    const res = await apiFetch('/api/amc/prices/resolve-tickers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error(`Erreur ${res.status}`)
    const data = await res.json()
    data.forEach(r => {
      tickerResolved.value[r.key] = r.confidence
      if (r.ticker) {
        const u = priceStatusList.value.find(x => x.key === r.key)
        if (u && !u.ticker) u.ticker = r.ticker
      }
    })
  } catch(e) {
    // silent — individual badges show status
  } finally {
    tickerResolving.value = false
  }
}

async function fetchAllUnderlyings() {
  const withTicker = priceStatusList.value.filter(u => u.ticker?.trim())
  if (!withTicker.length) return
  fetchingAll.value = true
  for (const u of withTicker) {
    await fetchUnderlying(u)
  }
  fetchingAll.value = false
}

async function fetchUnderlying(u) {
  if (!u.ticker?.trim()) { priceErrors.value[u.key] = 'Ticker requis'; return }
  priceErrors.value[u.key] = ''
  priceRefreshing.value = u.key
  try {
    const res = await apiFetch('/api/amc/prices/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: u.key, ticker: u.ticker.trim() }),
    })
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || `Erreur ${res.status}`) }
    await loadPriceStatus()
  } catch(e) {
    priceErrors.value[u.key] = e.message
  } finally {
    priceRefreshing.value = null
  }
}

async function uploadUnderlying(u, event) {
  const file = event.target.files?.[0]
  if (!file) return
  priceErrors.value[u.key] = ''
  priceRefreshing.value = u.key
  try {
    const fd = new FormData()
    fd.append('key', u.key)
    fd.append('file', file)
    if (u.ticker) fd.append('ticker', u.ticker)
    const res = await apiFetch('/api/amc/prices/upload', { method: 'POST', body: fd })
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || `Erreur ${res.status}`) }
    await loadPriceStatus()
  } catch(e) {
    priceErrors.value[u.key] = e.message
  } finally {
    priceRefreshing.value = null
    event.target.value = ''
  }
}

async function computeBrinson() {
  if (!studyResult.value) return
  brinsonLoading.value = true
  brinsonError.value   = ''
  try {
    const priceKeys = priceStatusList.value.filter(u => u.available).map(u => u.key)
    if (!priceKeys.length) throw new Error('Aucun prix disponible — importez les séries dans l\'onglet F d\'abord.')
    const benchTicker = studyResult.value?.meta?.benchmark_ticker || 'ACWI'
    const res = await apiFetch('/api/amc/prices/brinson', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        study_result:     studyResult.value,
        price_keys:       priceKeys,
        amc_currency:     studyResult.value?.meta?.currency || 'CHF',
        folder:           studyFolder.value || '',
        benchmark_ticker: benchTicker,
      }),
    })
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || `Erreur ${res.status}`) }
    brinsonResult.value = await res.json()
    activeStudyTab.value = 'brinson'
  } catch(e) {
    brinsonError.value = e.message
  } finally {
    brinsonLoading.value = false
  }
}

async function computeMarketShocks() {
  if (!studyResult.value) return
  marketShocksLoading.value = true
  marketShocksError.value   = ''
  try {
    const res = await apiFetch('/api/amc/marketshocks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        study_result: studyResult.value,
        folder:       studyFolder.value || '',
      }),
    })
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail || `Erreur ${res.status}`) }
    studyResult.value.block_k = await res.json()
    activeStudyTab.value = 'marketshocks'
  } catch(e) {
    marketShocksError.value = e.message
  } finally {
    marketShocksLoading.value = false
  }
}

async function loadStudyDoc() {
  try {
    const res = await apiFetch('/api/amc/study/doc')
    if (res.ok) studyDoc.value = await res.json()
  } catch { /* ignore */ }
}

async function detectFolder() {
  if (!studyFolder.value.trim()) return
  studyError.value = ''
  studyLoading.value = true
  try {
    const res = await apiFetch('/api/amc/study/detect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: studyFolder.value.trim() }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Erreur ${res.status}`)
    }
    const data = await res.json()
    manifestData.value = data
  } catch (e) {
    studyError.value = `Scan : ${e.message}`
  } finally {
    studyLoading.value = false
  }
}

async function runStudy() {
  if (!manifestData.value?.manifest || !studyFolder.value.trim()) return
  studyError.value = ''
  studyLoading.value = true
  studyResult.value = null
  try {
    // Inject studyConfig FF params into manifest params
    const bm = studyConfig.value.benchmark_ticker === 'CUSTOM'
      ? studyCustomTicker.value
      : studyConfig.value.benchmark_ticker
    const manifestToSend = {
      ...manifestData.value.manifest,
      params: {
        ...manifestData.value.manifest.params,
        ff_series:        studyConfig.value.ff_series,
        selected_factors: studyConfig.value.selected_factors,
        benchmark_ticker: bm || manifestData.value.manifest.params?.benchmark_ticker || 'ACWI',
        rolling_window:   studyConfig.value.rolling_window,
      },
    }
    lastRunManifest.value = manifestToSend
    const res = await apiFetch('/api/amc/study/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        manifest: manifestToSend,
        folder: studyFolder.value.trim(),
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Erreur ${res.status}`)
    }
    studyResult.value = await res.json()
    activeStudyTab.value = 'meta'
    studyRollingVisible.value = studyResult.value?.block_a?.net?.factors_used?.slice(0, 3) || []
    brinsonResult.value = null
    loadPriceStatus()
  } catch (e) {
    studyError.value = `Étude : ${e.message}`
  } finally {
    studyLoading.value = false
  }
}

function renderStudyRolling() {
  const blockA = studyResult.value?.block_a?.net
  if (!blockA?.rolling?.length || !studyRollingChartRef) return
  import('chart.js').then(({ Chart, registerables }) => {
    Chart.register(...registerables)
    studyRollingChart?.destroy()
    const rolling = blockA.rolling
    const factors = (blockA.factors_used || []).filter(f => studyRollingVisible.value.includes(f))
    const COLORS = chartTheme.series
    const datasets = [
      {
        label: 'Alpha ann. (%)', yAxisID: 'y',
        data: rolling.map(r => r.alpha_ann_pct ?? null),
        borderColor: chartTheme.gold, backgroundColor: 'rgba(184,134,11,.12)',
        borderWidth: 1.5, pointRadius: 0, fill: true, tension: 0.3,
      },
      ...factors.map((f, i) => ({
        label: f, yAxisID: 'y2',
        data: rolling.map(r => r[f] ?? null),
        borderColor: COLORS[i % COLORS.length],
        borderWidth: 1.5, pointRadius: 0, tension: 0.3,
      })),
    ]
    studyRollingChart = new Chart(studyRollingChartRef, {
      type: 'line',
      data: { labels: rolling.map(r => formatDate(r.date)), datasets },
      options: {
        responsive: true,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { font: { size: 10 } } } },
        scales: {
          x: { ticks: { maxRotation: 0, maxTicksLimit: 8 } },
          y: { position: 'left', title: { display: true, text: 'Alpha %', color: chartTheme.gold, font: { size: 9 } },
               ticks: { color: chartTheme.gold } },
          y2: { position: 'right', title: { display: true, text: 'Beta', color: chartTheme.primary, font: { size: 9 } },
                ticks: { color: chartTheme.primary }, grid: { display: false } },
        },
      },
    })
  })
}

function renderStudyPerf() {
  const perf = studyResult.value?.block_a?.net?.performance
  if (!perf?.cum_amc?.length || !studyPerfChartRef) return
  import('chart.js').then(({ Chart, registerables }) => {
    Chart.register(...registerables)
    studyPerfChart?.destroy()
    const datasets = [
      { label: 'AMC (net)', data: perf.cum_amc.map(v => +(v * 100).toFixed(2)),
        borderColor: chartTheme.primary, borderWidth: 2, pointRadius: 0, tension: 0.2, fill: false },
    ]
    if (perf.cum_bm?.length) {
      datasets.push({
        label: 'Benchmark', data: perf.cum_bm.map(v => +(v * 100).toFixed(2)),
        borderColor: chartTheme.ticks, borderWidth: 1.5, borderDash: [4, 3],
        pointRadius: 0, tension: 0.2, fill: false,
      })
    }
    studyPerfChart = new Chart(studyPerfChartRef, {
      type: 'line',
      data: { labels: perf.dates, datasets },
      options: {
        responsive: true,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { font: { size: 10 } } } },
        scales: {
          x: { ticks: { maxRotation: 0, maxTicksLimit: 8 } },
          y: { ticks: { callback: v => v + '%' } },
        },
      },
    })
  })
}

async function exportStudyPdf(includeAnnexes = true) {
  if (!studyResult.value) return
  if (includeAnnexes) studyPdfLoading.value = true
  else studyPdfSimpleLoading.value = true
  try {
    const res = await apiFetch('/api/amc/study/export-pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        study_result:       {
          ...studyResult.value,
          meta: { ...(studyResult.value?.meta || {}), client_name: 'UTI' },
        },
        synthese_text:      syntheseText.value,
        attribution_result: attrResult.value    || null,
        brinson_result:     brinsonResult.value || null,
        market_shocks_result: studyResult.value?.block_k || null,
        company_name:       'TP Advisory Services',
        client_name:        'UTI',
        include_annexes:    includeAnnexes,
        include_brinson:    includeBrinsonInPdf.value,
        include_marketshocks: includeMarketShocksInPdf.value,
      }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Erreur ${res.status}`)
    }
    const blob = await res.blob()
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    const isin = studyResult.value?.meta?.isin || 'study'
    const suffix = includeAnnexes ? '' : '_simplifie'
    a.href     = url
    a.download = `AMC_Etude_${isin}${suffix}_${new Date().toISOString().slice(0,10)}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    studyError.value = `PDF étude : ${e.message}`
  } finally {
    studyPdfLoading.value       = false
    studyPdfSimpleLoading.value = false
  }
}

function fmtPnl(v, ccy) {
  if (v == null) return '—'
  const abs = Math.abs(v)
  const s = v >= 0 ? '+' : ''
  if (abs >= 1e6) return `${s}${formatNumber(v/1e6, 2)}M ${ccy||''}`
  if (abs >= 1e3) return `${s}${formatNumber(v/1e3, 1)}k ${ccy||''}`
  return `${s}${formatNumber(v, 0)} ${ccy||''}`
}

loadStudyDoc()
fetchSavedStudies()

// Deep-link from the Home "load a study" module: /amc?study_id=123
const route = useRoute()
if (route.query.study_id) {
  loadStudyById(Number(route.query.study_id))
}

// Rebuild charts when switching to performance or facteurs tab
watch(activeTab, async (tab) => {
  await nextTick()
  if (!result.value) return
  if (tab === 'performance') { destroyAll(); buildCharts() }
  else if (tab === 'facteurs') { destroyAll(); buildCharts() }
})

onUnmounted(destroyAll)

// ── Computed helpers ──────────────────────────────────────────────────
const dep  = computed(() => result.value?.dependency_score || { total: 0, components: {}, interpretation: '' })

const dataUsedCols = computed(() => {
  if (!result.value?.data_used?.length) return []
  return Object.keys(result.value.data_used[0])
})

const overlapInfo = computed(() => {
  if (!parsed.value?.nav?.length) return null
  const selectedStatus = ffStatus.value.find(s => s.key === config.value.ff_series)
  if (!selectedStatus?.available) return null

  const navDates = parsed.value.nav.map(r => r.date).sort()
  const navStart = navDates[0]
  const navEnd   = navDates[navDates.length - 1]
  const ffStart  = selectedStatus.date_min
  const ffEnd    = selectedStatus.date_max

  const overlapStart = navStart > ffStart ? navStart : ffStart
  const overlapEnd   = navEnd   < ffEnd   ? navEnd   : ffEnd

  if (overlapStart > overlapEnd) {
    return { status: 'error', overlap: 0, navStart, navEnd, ffStart, ffEnd, overlapStart, overlapEnd }
  }

  // Rough business-day count (×5/7)
  const days = Math.round((new Date(overlapEnd) - new Date(overlapStart)) / 86400000 * 5 / 7)
  const status = days < 20 ? 'error' : days < 60 ? 'warn' : 'ok'
  return { status, overlap: days, navStart, navEnd, ffStart, ffEnd, overlapStart, overlapEnd }
})
const act  = computed(() => result.value?.activity || {})

const scoreColor = computed(() => {
  const t = dep.value.total
  if (t >= 70) return '#ef4444'
  if (t >= 45) return '#f59e0b'
  return '#34d399'
})
const scoreTextColor = computed(() => {
  const t = dep.value.total
  if (t >= 70) return 'text-red-400'
  if (t >= 45) return 'text-amber-400'
  return 'text-emerald-400'
})

const scoreMax = { idiosyncratic: 40, turnover: 30, concentration: 20, alpha_signif: 10 }

const compDesc = {
  idiosyncratic: "Risque spécifique (1 − R²) non expliqué par les facteurs de marché. Plus il est élevé, plus la performance dépend des choix propres du gérant. Pondéré sur 40 pts (composante principale).",
  turnover: "Taux de rotation du portefeuille depuis le lancement. Un turnover élevé traduit une gestion active intensive et donc une forte dépendance aux décisions du gérant. Pondéré sur 30 pts.",
  concentration: "Indice Herfindahl-Hirschman (HHI) de concentration des positions. Un portefeuille concentré dépend davantage de quelques paris du gérant. Pondéré sur 20 pts.",
  alpha_signif: "Significativité statistique de l'alpha (|t-stat|). Un alpha significatif indique une création de valeur propre et active du gérant. Pondéré sur 10 pts.",
}

const maxMonthlyTrades = computed(() => {
  const vals = Object.values(act.value.monthly || {}).map(m => m.trades)
  return Math.max(...vals, 1)
})

function sigStars(p) {
  if (p == null) return ''
  if (p < 0.001) return '***'
  if (p < 0.01)  return '**'
  if (p < 0.05)  return '*'
  if (p < 0.10)  return '·'
  return 'n.s.'
}

function fmtPVal(p) {
  if (p == null) return '—'
  if (p < 0.0001) return '< 0,0001'
  return formatNumber(p, 4)
}

function pvalClass(p) {
  if (p == null) return 'text-slate-500'
  if (p < 0.05) return 'text-emerald-400'
  if (p < 0.10) return 'text-amber-400'
  return 'text-red-400'
}

function alphaSignifLabel(p) {
  if (p == null) return ''
  if (p < 0.01) return '✓ Significatif à 1%'
  if (p < 0.05) return '✓ Significatif à 5%'
  if (p < 0.10) return '~ Significatif à 10%'
  return '✗ Non significatif'
}

function alphaSignifClass(p) {
  if (p == null) return 'text-slate-600'
  if (p < 0.05) return 'text-emerald-400'
  if (p < 0.10) return 'text-amber-400'
  return 'text-red-400'
}

function ffDataAge(dateMax) {
  if (!dateMax) return 0
  const d = new Date(dateMax)
  const today = new Date()
  return Math.floor((today - d) / 86400000)
}

function fmtUSD(n) {
  if (!n) return '$0'
  if (n >= 1e6) return '$' + formatNumber(n / 1e6, 2) + 'M'
  if (n >= 1e3) return '$' + formatNumber(n / 1e3, 1) + 'k'
  return '$' + formatInt(n)
}

function fmtCompValue(key, val) {
  if (key === 'idiosyncratic') return `R² = ${formatPercent((1 - val) * 100, 1)}`
  if (key === 'turnover')      return `Turnover = ${formatPercent(val * 100, 1)}`
  if (key === 'concentration') return `HHI = ${formatNumber(val, 3)}`
  if (key === 'alpha_signif')  return `|t| = ${formatNumber(Math.abs(val), 2)}`
  return val
}
</script>
