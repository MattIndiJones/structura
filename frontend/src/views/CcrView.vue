<template>
  <main class="ccr-view flex-1 min-h-0 min-w-0 overflow-hidden p-3 lg:p-4">
    <div class="ccr-shell max-w-[1500px] mx-auto">
      <div class="page-header"><div><h1 class="page-title">Risque de crédit de contrepartie — CCR</h1><p class="page-subtitle">Exposition économique, accords juridiques et décision pré-trade</p></div><RouterLink to="/risk" class="btn-ghost btn-sm">← Risques</RouterLink></div>
      <AlertMessage v-if="error" kind="error">{{ error }}</AlertMessage>
      <div class="ccr-actions ccr-scopebar">
        <label class="text-xs"><span>Périmètre <HelpTip :text="ccrHelp.dataScope" /></span><select :disabled="calculating" v-model="dataScope" class="select"><option value="PRODUCTION">Production — deals réels</option><option value="UAT">Recette UAT — deals de test</option></select></label>
        <label v-if="dataScope === 'UAT' && tab !== 'monitor'" class="text-xs"><span>Lot de recette <HelpTip :text="ccrHelp.uatBatchId" /></span><select :disabled="calculating" v-model="uatBatchId" class="select"><option :value="null">Tous les lots UAT</option><option v-for="b in uatBatches" :key="b.id" :value="b.id">{{ b.label }}</option></select></label>
        <span v-if="dataScope === 'UAT'" class="text-xs text-amber-600">RECETTE · résultats séparés, limites simulées. Référentiel juridique/crédit commun.</span>
      </div>
      <div class="card ccr-context">
        <label class="text-xs"><span>Contrepartie <HelpTip :text="ccrHelp.cptyId" /></span><select :disabled="calculating" v-model="cptyId" class="select mt-1"><option :value="null">Choisir une contrepartie</option><option v-for="c in counterparties" :key="c.id" :value="c.id">{{ c.name }}{{ c.active ? '' : ' — inactive' }}</option></select></label>
        <label class="text-xs"><span>Date d’arrêté <HelpTip :text="ccrHelp.asOf" /></span><input :disabled="calculating" v-model="asOf" type="date" class="input mt-1" /></label>
        <label class="text-xs"><span>Devise de calcul <HelpTip :text="ccrHelp.currency" /></span><select :disabled="calculating" v-model="currency" class="select mt-1"><option v-for="c in ['EUR','USD','GBP','CHF','JPY','SGD']" :key="c">{{ c }}</option></select></label>
        <div class="flex items-end"><RouterLink to="/admin/counterparties" class="btn-secondary btn-sm">Gérer le catalogue existant</RouterLink></div>
      </div>
      <nav class="ccr-tabs" aria-label="Sections du risque de crédit">
        <button v-for="(label,key) in tabs" :key="key" :class="tab === key ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'" @click="tab = key">{{ label }}</button>
      </nav>
      <section v-if="tab === 'exposure'" class="ccr-panel" aria-label="Analyse des expositions">
        <div class="ccr-controls ccr-scroll">
        <div class="card text-xs">
          <div class="ccr-actions"><b>Diagnostic du périmètre</b><button class="btn-ghost btn-sm" :disabled="!cptyId || diagnosticBusy" @click="loadDiagnostic">{{ diagnosticBusy ? 'Vérification…' : 'Actualiser' }}</button></div>
          <p v-if="diagnosticError" class="text-amber-600">{{ diagnosticError }}</p>
          <template v-else-if="diagnostic">
            <p>{{ number(diagnostic.selected_count) }} deal(s) retenu(s) · {{ number(diagnostic.missing_valuation_count) }} MtM Booking non figé(s) au {{ asOf }} · {{ number(diagnostic.excluded_other_scope_count) }} deal(s) de l’autre périmètre exclu(s).</p>
            <p v-if="!diagnostic.selected_count" class="text-amber-600">Aucun deal à calculer. Vérifier Production / Recette UAT, le lot et le portefeuille.</p>
            <div v-if="diagnostic.common_valuation_dates.length" class="ccr-actions mt-2"><span>Dates avec MtM pour tous les deals :</span><button v-for="d in diagnostic.common_valuation_dates.slice(0, 5)" :key="d" class="btn-ghost btn-sm" :disabled="calculating" @click="asOf = d">{{ d }}</button></div>
            <details v-if="diagnostic.deals.length" class="mt-2"><summary>Deals et valorisations disponibles</summary>
              <p class="my-2">Le bouton de calcul prépare automatiquement les MtM manquants à la date choisie. La base CCR compatible du dernier calcul est réutilisée. Ce diagnostic inventorie les valorisations officielles Booking ; leur absence ne signifie pas que la base CCR est absente.</p>
              <div class="table-shell ccr-diagnostic-table"><table><thead><tr><th>Deal</th><th>MtM à la date choisie</th><th>Dernière date disponible</th><th>Action</th></tr></thead><tbody><tr v-for="d in diagnostic.deals" :key="d.deal_id"><td>{{ d.reference }}</td><td>{{ d.valuation_available ? 'Disponible' : d.reason }}</td><td>{{ d.available_dates[0] || 'Aucune' }}</td><td><RouterLink :to="d.booking_url" class="underline">Ouvrir dans Booking</RouterLink></td></tr></tbody></table></div>
            </details>
          </template>
          <p v-else>Choisir une contrepartie pour vérifier les deals et leurs valorisations.</p>
        </div>
        <div class="card ccr-calculation-grid">
          <label class="text-xs"><span>Portefeuille <HelpTip :text="ccrHelp.analysisPortfolio" /></span><select :disabled="calculating" v-model="analysisPortfolio" class="select mt-1"><option :value="null">Tous les portefeuilles</option><option v-for="p in portfolios" :key="p.id" :value="p.id">{{ p.name }}</option></select></label>
          <label class="text-xs"><span>Netting set <HelpTip :text="ccrHelp.analysisSet" /></span><select :disabled="calculating" v-model="analysisSet" class="select mt-1"><option :value="null">Tous — périmètre contrepartie</option><option v-for="s in configuration['netting-sets'] || []" :key="s.id" :value="s.id">{{ s.data.netting_set_id }}</option></select></label>
          <label class="text-xs"><span>Deal <HelpTip :text="ccrHelp.analysisDeal" /></span><select :disabled="calculating" v-model="analysisDeal" class="select mt-1"><option :value="null">Tous les deals</option><option v-for="d in scopedDeals" :key="d.id" :value="d.id">{{ d.reference }}</option></select></label>
          <div class="ccr-simulation-grid">
          <label class="text-xs"><span>Scénarios extérieurs <HelpTip :text="ccrHelp.nOuter" /></span><input :disabled="calculating" v-model.number="nOuter" type="number" min="32" max="5000" class="input mt-1 w-28" /><small class="text-slate-500">{{ number(nOuter) }} scénarios</small></label>
          <label class="text-xs"><span>Trajectoires intérieures <HelpTip :text="ccrHelp.nInner" /></span><input :disabled="calculating" v-model.number="nInner" type="number" min="32" max="5000" class="input mt-1 w-28" /><small class="text-slate-500">{{ number(nInner) }} trajectoires</small></label>
          <label class="text-xs"><span>Horizons <HelpTip :text="ccrHelp.nDates" /></span><input :disabled="calculating" v-model.number="nDates" type="number" min="2" max="60" class="input mt-1 w-20" /></label>
          <label class="text-xs"><span>Seed <HelpTip :text="ccrHelp.seed" /></span><input :disabled="calculating" v-model.number="seed" type="number" min="0" class="input mt-1 w-24" /></label>
          <button class="btn-primary btn-sm ccr-calculate" :disabled="busy || calculating || !cptyId" @click="calculate">{{ busy ? 'Calcul…' : 'Calculer MtM et CCR' }}</button>
          </div>
        </div>
        <div class="card text-xs">
          <b>Hypothèses de valorisation</b>
          <div class="ccr-market-grid mt-2">
            <label><span>Taux commun à tous les deals (%) <HelpTip :text="ccrHelp.commonRate" /></span><input v-model="commonRate" type="number" step="any" class="input" :disabled="calculating" placeholder="3 % par défaut" /></label>
            <label><span>Trajectoires MtM <HelpTip :text="ccrHelp.mtmPaths" /></span><input v-model.number="mtmPaths" type="number" min="1000" max="100000" class="input" :disabled="calculating" /><small class="text-slate-500">{{ number(mtmPaths) }} trajectoires</small></label>
          </div>
          <p class="mt-2 text-amber-700">{{ commonRate === '' || Number(commonRate) === 3 ? 'Taux harmonisé à 3 % — hypothèse provisoire en attendant les taux du jour.' : 'Taux commun saisi manuellement — surcharge pour tous les deals.' }} Appliqué au drift et à l’actualisation, à la place des taux et courbes du booking.</p>
          <label class="mt-2"><span><input v-model="commonMarket" type="checkbox" :disabled="calculating" /> Construire automatiquement un marché commun pour les MtM et PFE <HelpTip :text="ccrHelp.commonMarket" /></span></label>
          <p v-if="commonMarket" class="mt-2">MtM clean, sans funding émetteur. Marché commun : volatilités réalisées et corrélations estimées ensemble sur les 252 derniers rendements disponibles à l’arrêté. Dividende unique par ticker issu du booking le plus récent, utilisé comme hypothèse et identifié dans les résultats. Surcharges manuelles prioritaires. Projection GBM uniquement. Les dates de marché et paramètres effectivement utilisés figurent dans le résultat.</p>
          <p v-else class="mt-2">Paramètres des contextes enregistrés, sans recalibration. Les surcharges doivent rendre les hypothèses compatibles entre tous les deals pour calculer les PFE.</p>
          <label class="mt-2"><span><input v-model="allowMarketFetch" type="checkbox" :disabled="calculating" /> Compléter les historiques manquants via le fournisseur de marché (bruts pour les fixings, ajustés pour la calibration) <HelpTip :text="ccrHelp.allowMarketFetch" /></span></label>
          <p>Priorité aux données locales ; si décoché, aucune récupération externe. Un historique incomplet bloque le deal et reste visible.</p>
          <label class="mt-2"><span><input v-model="refreshMtm" type="checkbox" :disabled="calculating" /> Recalculer la base MtM au lieu de réutiliser le dernier dossier compatible <HelpTip :text="ccrHelp.refreshMtm" /></span></label>
          <p class="mt-1">Par défaut, marché et MtM figés réutilisés à date, contrats, fixings et hypothèses identiques. Les projections PFE et les scénarios de stress sont recalculés.</p>
          <details class="mt-2"><summary>Surcharges communes et historiques manuels</summary>
            <label class="mt-2"><span>Volatilités et dividendes par ticker (fractions : 0.20 = 20 %) <HelpTip :text="ccrHelp.marketOverrides" /></span><textarea v-model="marketOverrides" class="input font-mono" rows="2" :disabled="calculating" /></label>
            <p>Exemple : {"AAPL":{"sigma":0.20,"q":0.01}}. Sigma plat uniquement pour GBM.</p>
            <label class="mt-2"><span>Corrélations — paires triées, valeurs décimales <HelpTip :text="ccrHelp.correlations" /></span><textarea v-model="correlations" class="input font-mono" rows="2" :disabled="calculating" /></label>
            <p>Exemple : {"AAPL|MSFT":0.5}. Les paires saisies remplacent les valeurs existantes. Aucune indépendance implicite.</p>
            <label class="mt-2"><span>Historiques de clôtures brutes non ajustées <HelpTip :text="ccrHelp.priceHistories" /></span><textarea v-model="priceHistories" class="input font-mono" rows="2" :disabled="calculating" /></label>
            <p>Format : {"AAPL":{"dates":["2026-09-15","2026-09-16"],"closes":[230,231]}}. Couvrir la période du strike à l’arrêté pour tout le panier ; mêmes unités que le fixing contractuel.</p>
          </details>
        </div>
        <p class="text-xs text-slate-500">MtM puis expositions, CVA et limites en une seule action. Les valorisations officielles de Booking restent inchangées. Un périmètre partiel ne valide pas les limites globales de contrepartie. Sans contrepartie, l’analyse standalone est accessible depuis le Pricer.</p>
        </div>
        <div class="ccr-actions"><button v-if="progress || result" class="btn-secondary btn-sm" @click="resultsOpen = true">{{ calculating ? 'Voir la progression' : 'Ouvrir les résultats en grand' }}</button><span class="text-xs text-slate-500">Le calcul s’ouvre dans une fenêtre dédiée.</span></div>
      </section>
      <section v-else-if="tab === 'monitor'" class="ccr-panel" aria-label="Monitor contreparties">
        <div class="ccr-actions"><button class="btn-secondary btn-sm" @click="loadMonitor">Actualiser les derniers calculs</button><label class="text-xs ccr-sort"><span>Trier par <HelpTip :text="ccrHelp.sortKey" /></span><select v-model="sortKey" class="select"><option value="current_exposure">Exposition courante</option><option value="pfe95">PFE 95 %</option><option value="cva">CVA</option><option value="utilisation">Utilisation</option><option value="breach">Dépassement</option></select></label></div>
        <p class="text-xs text-slate-500">{{ dataScope === 'UAT' ? 'RECETTE UAT — tous les lots' : 'PRODUCTION — deals réels uniquement' }} : derniers calculs complets de contrepartie, sans filtre de lot ou de portefeuille. Aucune actualisation de marché implicite.</p>
        <div class="table-shell ccr-panel-body ccr-scroll ccr-monitor" tabindex="0" aria-label="Tableau des contreparties"><table class="w-full text-xs"><thead><tr><th>Contrepartie</th><th>Date</th><th>Rating</th><th v-for="k in monitorMetrics" :key="k" class="num">{{ metricLabels[k] }} <HelpTip :text="ccrHelp[k]" /></th><th class="num">Limite PFE95 <HelpTip :text="ccrHelp.pfe95" /></th><th class="num">Utilisation <HelpTip :text="ccrHelp.utilisation" /></th><th class="num">Capacité <HelpTip :text="ccrHelp.remaining_capacity" /></th><th>Statut</th></tr></thead><tbody>
          <tr v-for="m in sortedMonitor" :key="m.counterparty_id" class="border-b"><td class="p-2"><button class="underline" @click="cptyId = m.counterparty_id; tab = 'exposure'">{{ m.name }}</button></td><td>{{ m.as_of_date || 'Non calculé' }}</td><td>{{ m.result?.credit_profile?.internal_rating || '—' }}</td><td v-for="k in monitorMetrics" :key="k" class="text-right p-2"><SensitiveValue>{{ money(m.result?.after?.[k]) }}</SensitiveValue></td><td><SensitiveValue>{{ money(pfeLimit(m)?.limit) }}</SensitiveValue></td><td><SensitiveValue>{{ percent(pfeLimit(m)?.utilisation) }}</SensitiveValue></td><td><SensitiveValue>{{ money(pfeLimit(m)?.remaining_capacity) }}</SensitiveValue></td><td>{{ m.stale ? 'Historique — recalcul requis' : statusLabels[m.result?.decision?.status || 'MISSING_DATA'] }}</td></tr>
        </tbody></table></div>
      </section>
      <section v-else-if="tab === 'trades'" class="ccr-panel" aria-label="Rattachement des trades">
        <p class="text-xs text-slate-500">Rattachement juridique distinct des termes du payoff ; chaque modification exige un motif et reste auditée.</p>
        <div class="ccr-panel-body ccr-scroll ccr-trades" tabindex="0" aria-label="Liste des trades">
        <div v-for="d in scopedDeals" :key="d.id" class="card ccr-trade-row"><span class="text-sm">{{ d.reference }} · {{ d.product_type }}</span><select v-model="d.netting_set_id" class="select" :aria-label="`Netting set de ${d.reference}`" :disabled="!auth.isAdmin"><option :value="null">Aucun set</option><option v-for="s in configuration['netting-sets'] || []" :key="s.id" :value="s.id">{{ s.data.netting_set_id }}</option></select><input v-model="d.reason" class="input" :aria-label="`Motif pour ${d.reference}`" placeholder="Motif du rattachement" :disabled="!auth.isAdmin" /><button class="btn-secondary btn-sm" :disabled="busy || !auth.isAdmin || !d.reason" @click="assign(d)">Enregistrer</button></div>
        </div>
      </section>
      <section v-else-if="tab === 'stress'" class="ccr-panel" aria-label="Stress de crédit">
        <div class="card text-sm ccr-controls ccr-scroll"><h2 class="font-semibold">Wrong-Way Risk — corrélation défavorable crédit / exposition</h2><p class="mt-2">Stress conjoints explicites sur les facteurs de marché et le crédit. Cette analyse n’est pas un modèle stochastique joint de défaut. Les résultats de base restent distincts.</p>
          <div class="grid grid-cols-2 lg:grid-cols-5 gap-3 mt-3"><label class="text-xs"><span>Spot (%) <HelpTip :text="ccrHelp.spot_pct" /></span><input v-model.number="stress.spot_pct" type="number" min="-99" class="input" /></label><label class="text-xs"><span>Volatilité (points) <HelpTip :text="ccrHelp.vol_points" /></span><input v-model.number="stress.vol_points" type="number" class="input" /></label><label class="text-xs"><span>Taux (bp) <HelpTip :text="ccrHelp.rate_bp" /></span><input v-model.number="stress.rate_bp" type="number" class="input" /></label><label class="text-xs"><span>Corrélation (points) <HelpTip :text="ccrHelp.correlation_points" /></span><input v-model.number="stress.correlation_points" type="number" class="input" /></label><label class="text-xs"><span>Intensité crédit × <HelpTip :text="ccrHelp.creditMultiplier" /></span><input v-model.number="creditMultiplier" type="number" min="1" max="100" class="input" /></label></div>
          <p class="mt-3 text-xs">La base MtM compatible est réutilisée automatiquement. Sinon, elle est préparée ici avant le stress. Taux commun : {{ percent((commonRate === '' ? 3 : Number(commonRate)) / 100) }} · {{ commonMarket ? 'marché commun historique' : 'hypothèses figées' }}.</p>
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-2 mt-2 text-xs">
            <label><span><input v-model="refreshMtm" type="checkbox" :disabled="calculating" /> Recalculer la base MtM <HelpTip :text="ccrHelp.refreshMtm" /></span></label>
            <label><span><input v-model="allowMarketFetch" type="checkbox" :disabled="calculating" /> Compléter les historiques manquants via le fournisseur <HelpTip :text="ccrHelp.allowMarketFetch" /></span></label>
          </div>
          <button class="btn-ghost btn-sm mt-2" :disabled="calculating" @click="tab = 'exposure'">Paramètres du marché et des simulations</button>
          <button class="btn-primary btn-sm mt-3" :disabled="busy || calculating || !cptyId" @click="runStress">{{ busy ? 'Calcul…' : 'Calculer base et stress' }}</button>
          <RouterLink to="/risk?tab=chocs" class="btn-ghost btn-sm mt-3">Scénarios Market Risk</RouterLink>
        </div>
        <div class="ccr-actions"><button v-if="progress || stressResult" class="btn-secondary btn-sm" @click="resultsOpen = true">{{ calculating ? 'Voir la progression' : 'Ouvrir les résultats en grand' }}</button></div>
      </section>
      <section v-else-if="cptyId" class="ccr-panel" :aria-label="tabs[tab]">
        <div class="card ccr-editor">
          <div class="ccr-editor-heading ccr-scroll">
          <h2 class="font-semibold text-sm">{{ tabs[tab] }}</h2>
          <p class="text-xs text-slate-500">UNKNOWN signifie inconnu. Les anciennes contreparties ne reçoivent aucun accord, collatéral ou recouvrement présumé.</p>
          <p v-if="tab === 'agreements'" class="text-xs">ISDA — International Swaps and Derivatives Association : la présence d’un accord ne suffit pas à autoriser la compensation.</p>
          <p v-if="tab === 'csas'" class="text-xs">CSA — Credit Support Annex : les montants IM contractuels ne remplacent pas les positions effectivement reçues. Le calcul V1 utilise uniquement l’IM reçue reconnue et un modèle FIXED.</p>
          <p v-if="tab === 'overrides'" class="text-xs">Enregistrement d’une demande uniquement. Le circuit d’approbation à quatre yeux n’est pas encore disponible ; une demande ne lève jamais un blocage.</p>
          <p v-if="tab === 'profiles'" class="text-xs">Courbes au format [[année, fraction]], par exemple [[1, 0.01], [5, 0.05]] pour les PD cumulées. Saisir une seule courbe : PD ou spreads décimaux. Recouvrement en fraction (0.40 = 40 %).</p>
          <p v-if="tab === 'profiles' && draft.recovery != null" class="text-xs">LGD — Loss Given Default : {{ percent(1 - Number(draft.recovery)) }}</p>
          <div class="ccr-records ccr-scroll"><button class="btn-secondary btn-sm" @click="edit(null)">Nouvelle fiche</button><button v-for="r in configuration[tab] || []" :key="r.id" class="btn-ghost btn-sm" @click="edit(r)">#{{ r.id }} · {{ recordLabel(r) }} · v{{ r.version }}</button></div>
          </div>
          <form v-if="schemas[tab]" class="ccr-editor-form" @submit.prevent="save">
            <div class="ccr-fields ccr-scroll" tabindex="0" :aria-label="`Champs ${tabs[tab]}`">
            <label v-for="(raw,key) in schemas[tab].properties" :key="key" class="text-xs" :class="shape(raw).type === 'array' ? 'sm:col-span-2' : ''">
              <span class="ccr-field-label">{{ fieldLabels[key] || raw.title }} <HelpTip v-if="ccrHelp[key]" :text="ccrHelp[key]" /><span v-if="schemas[tab].required?.includes(key)"> *</span></span>
              <SensitiveValue mode="input">
                <select v-if="relation(key)" v-model="draft[key]" class="select mt-1" :disabled="!auth.isAdmin"><option :value="null">— Aucun / inconnu —</option><option v-for="r in configuration[relation(key)] || []" :key="r.id" :value="r.id">#{{ r.id }} · {{ recordLabel(r) }}</option></select>
                <select v-else-if="shape(raw).enum" v-model="draft[key]" class="select mt-1" :disabled="!auth.isAdmin"><option v-for="v in shape(raw).enum" :key="v" :value="v">{{ v }}</option></select>
                <select v-else-if="shape(raw).type === 'boolean'" v-model="draft[key]" class="select mt-1" :disabled="!auth.isAdmin"><option v-if="raw.anyOf" :value="null">UNKNOWN — inconnu</option><option :value="true">Oui</option><option :value="false">Non</option></select>
                <textarea v-else-if="shape(raw).type === 'array'" v-model="draft[key]" class="input mt-1 font-mono" rows="2" :disabled="!auth.isAdmin" />
                <input v-else v-model="draft[key]" class="input mt-1" :type="shape(raw).format === 'date' ? 'date' : ['number','integer'].includes(shape(raw).type) ? 'number' : 'text'" :step="shape(raw).type === 'integer' ? 1 : 'any'" :required="schemas[tab].required?.includes(key)" :disabled="!auth.isAdmin" />
                <small v-if="['amount','held','posted','im_held','mta','threshold_counterparty','threshold_our_side','independent_amount','im_amount','previous_limit','temporary_limit'].includes(key) && draft[key] !== '' && draft[key] != null" class="block mt-1 text-slate-500">{{ money(draft[key]) }} {{ draft.currency || draft.base_currency || currency }}</small>
              </SensitiveValue>
            </label>
            </div>
            <div class="ccr-actions ccr-editor-footer"><button class="btn-primary btn-sm" :disabled="busy || !auth.isAdmin">{{ busy ? 'Enregistrement…' : 'Enregistrer et auditer' }}</button></div>
          </form>
        </div>
      </section>
      <p v-else class="card text-sm">Sélectionner une contrepartie pour consulter son dossier crédit.</p>
    </div>
    <BaseModal v-model="resultsOpen" title="Calcul CCR — progression, résultats et hypothèses" fullscreen>
      <template #summary>
        <p class="text-sm mb-2">{{ calculationHeading }}</p>
        <CcrProgress :progress="progress" :deals="progressDeals" />
      </template>
      <AlertMessage v-if="error" kind="error" class="mb-3">{{ error }}</AlertMessage>
      <CcrResult v-if="displayResult" :result="displayResult" />
      <p v-else class="text-sm text-slate-500">{{ calculating ? 'Calcul en cours. Les résultats apparaîtront ici dès leur réception.' : 'Aucun résultat disponible. Consulter le message de calcul.' }}</p>
      <template #footer>
        <span class="text-xs self-center mr-auto">{{ replayMessage || (calculating ? 'Vous pouvez revenir aux paramètres ; le calcul continue.' : '') }}</span>
        <button v-if="displayResult?.run_id" class="btn-secondary btn-sm" :disabled="busy || calculating" @click="replay">Rejouer les entrées figées</button>
        <button v-if="displayResult?.run_id" class="btn-secondary btn-sm" :disabled="busy || calculating" @click="download">Exporter le dossier</button>
        <button class="btn-primary btn-sm" @click="resultsOpen = false">Retour aux paramètres</button>
      </template>
    </BaseModal>
  </main>
</template>
<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import HelpTip from '../components/HelpTip.vue'
import { ccrHelp } from '../utils/ccrHelp.js'
import CcrResult from '../components/CcrResult.vue'
import CcrProgress from '../components/CcrProgress.vue'
import BaseModal from '../components/ui/BaseModal.vue'
import SensitiveValue from '../components/SensitiveValue.vue'
import AlertMessage from '../components/ui/AlertMessage.vue'
import { ccrApi, ccrCalculate, metricLabels, fieldLabels, statusLabels, money, percent, number } from '../utils/ccr.js'
const auth = useAuthStore(), route = useRoute()
const tabs = { exposure: 'Exposition / CVA', monitor: 'Monitor contreparties', profiles: 'Profil crédit', agreements: 'Accords ISDA', csas: 'CSA', 'netting-sets': 'Netting sets', collateral: 'Collatéral', limits: 'Limites', trades: 'Trades', overrides: 'Demandes de dérogation', stress: 'Stress / WWR' }
const tab = ref('exposure'), cptyId = ref(Number(route.query.counterparty) || null), counterparties = ref([]), configuration = ref({}), schemas = ref({}), allDeals = ref([]), monitor = ref([])
const now = new Date(); const asOf = ref(new Date(now - now.getTimezoneOffset() * 60000).toISOString().slice(0,10))
const currency = ref('EUR'), analysisSet = ref(null), analysisDeal = ref(null), nOuter = ref(256), nInner = ref(128), nDates = ref(8), seed = ref(42), correlations = ref('{}')
const refreshMtm = ref(false)
const commonMarket = ref(true)
const commonRate = ref('3'), mtmPaths = ref(10000), allowMarketFetch = ref(false), marketOverrides = ref('{}'), priceHistories = ref('{}')
const resultsOpen = ref(false), calculationHeading = ref('')
const progress = ref(null), progressDeals = ref([]), calculating = ref(false)
const portfolios = ref([]), analysisPortfolio = ref(null)
const dataScope = ref('PRODUCTION'), uatBatchId = ref(null), uatBatches = ref([])
const diagnostic = ref(null), diagnosticBusy = ref(false), diagnosticError = ref('')
let diagnosticTimer, diagnosticGeneration = 0, dealListGeneration = 0
const result = ref(null), error = ref(''), busy = ref(false), selectedRecord = ref(null), draft = ref({}), replayMessage = ref(''), sortKey = ref('current_exposure')
const stress = ref({spot_pct:-20,vol_points:10,rate_bp:0,correlation_points:0}), creditMultiplier = ref(2), stressResult = ref(null)
const displayResult = computed(() => result.value || stressResult.value)
let uiRevision = 0
watch([cptyId, asOf, currency, analysisSet, analysisDeal, analysisPortfolio, dataScope, uatBatchId, nOuter, nInner, nDates, seed, correlations, stress, creditMultiplier, refreshMtm, commonMarket, commonRate, mtmPaths, allowMarketFetch, marketOverrides, priceHistories], () => { uiRevision++; result.value = null; stressResult.value = null; if (!calculating.value) { progress.value = null; progressDeals.value = [] } }, {deep:true})
const monitorMetrics = ['gross_notional','net_mtm','collateral','current_exposure','pfe95','pfe99','cva']
const scopedDeals = computed(() => allDeals.value.filter(d => d.counterparty_id === cptyId.value))
const pfeLimit = m => m.result?.limits?.find(l => l.metric === 'pfe95' && l.limit)
const sortedMonitor = computed(() => [...monitor.value].sort((a,b) => {
  const value = m => sortKey.value === 'utilisation' ? pfeLimit(m)?.utilisation ?? -1 : sortKey.value === 'breach' ? Number(m.result?.decision?.status === 'BREACH') : m.result?.after?.[sortKey.value] ?? -1
  return value(b) - value(a)
}))
const shape = s => s.anyOf?.find(t => t.type !== 'null') || s
function relation(key) {
  if (key === 'master_agreement_id') return 'agreements'
  if (key === 'csa_id' && tab.value === 'netting-sets') return 'csas'
  if (key === 'netting_set_id' && tab.value === 'collateral') return 'netting-sets'
  if (key === 'limit_id') return 'limits'
  return null
}
const recordLabel = r => r.data.agreement_id || r.data.csa_id || r.data.netting_set_id || r.data.metric || r.data.legal_name || r.data.as_of_date || 'Fiche'
function edit(record) {
  selectedRecord.value = record
  draft.value = Object.fromEntries(Object.entries(schemas.value[tab.value]?.properties || {}).map(([k,s]) => {
    const value = record ? record.data[k] : s.default ?? (shape(s).type === 'array' ? [] : null)
    return [k, shape(s).type === 'array' ? JSON.stringify(value || []) : value]
  }))
}
async function loadConfiguration() {
  if (!cptyId.value) { configuration.value = {}; return }
  const id = cptyId.value
  const response = await ccrApi(`/counterparties/${id}/configuration`)
  if (id !== cptyId.value) return
  configuration.value = response
  edit(configuration.value[tab.value]?.[0] || null)
}
async function guarded(fn) { error.value = ''; busy.value = true; try { await fn() } catch(e) { error.value = e.message } finally { busy.value = false } }
const scopeQuery = () => `data_scope=${dataScope.value}${uatBatchId.value ? `&uat_batch_id=${uatBatchId.value}` : ''}`
const scopeRequest = () => ({data_scope:dataScope.value, uat_batch_id:uatBatchId.value, counterparty_id:cptyId.value,
  netting_set_id:analysisSet.value, deal_id:analysisDeal.value, portfolio_id:analysisPortfolio.value, as_of_date:asOf.value, currency:currency.value})
async function loadDeals() {
  const generation = ++dealListGeneration
  const rows = await ccrApi(`/deals?${scopeQuery()}`)
  if (generation === dealListGeneration) allDeals.value = rows
}
async function loadDiagnostic() {
  clearTimeout(diagnosticTimer)
  const generation = ++diagnosticGeneration
  diagnostic.value = null; diagnosticError.value = ''
  if (!cptyId.value) { diagnosticBusy.value = false; return }
  diagnosticBusy.value = true
  try { const response = await ccrApi('/diagnostic', scopeRequest()); if (generation === diagnosticGeneration) diagnostic.value = response }
  catch(e) { if (generation === diagnosticGeneration) diagnosticError.value = e.message }
  finally { if (generation === diagnosticGeneration) diagnosticBusy.value = false }
}
watch(dataScope, () => { uatBatchId.value = null; monitor.value = []; if (tab.value === 'monitor') loadMonitor() })
watch([dataScope, uatBatchId], () => { allDeals.value = []; analysisDeal.value = null; guarded(loadDeals) })
watch([cptyId, asOf, currency, analysisSet, analysisDeal, analysisPortfolio, dataScope, uatBatchId], () => {
  diagnosticGeneration++; diagnostic.value = null; diagnosticError.value = ''; diagnosticBusy.value = false
  clearTimeout(diagnosticTimer); diagnosticTimer = setTimeout(loadDiagnostic, 250)
})
onBeforeUnmount(() => { clearTimeout(diagnosticTimer); diagnosticGeneration++; dealListGeneration++ })
watch(cptyId, () => { configuration.value = {}; edit(null); result.value = null; analysisSet.value = null; analysisDeal.value = null; guarded(loadConfiguration) })
watch(tab, () => { edit(configuration.value[tab.value]?.[0] || null); if (tab.value === 'monitor') loadMonitor() })
watch([asOf, currency, analysisSet, analysisDeal, nOuter, nInner, nDates, seed, correlations], () => { result.value = null })
async function save() { await guarded(async () => {
  const data = {}
  for (const [k,s] of Object.entries(schemas.value[tab.value].properties)) {
    const v = draft.value[k], type = shape(s).type
    data[k] = type === 'array' ? JSON.parse(v || '[]') : ['number','integer'].includes(type) ? v === '' || v == null ? null : Number(v) : shape(s).format === 'date' && !v ? null : v
    if (data[k] == null && !s.anyOf && !schemas.value[tab.value].required?.includes(k)) delete data[k]
  }
  const selected = selectedRecord.value
  await ccrApi(`/counterparties/${cptyId.value}/${tab.value}${selected ? `/${selected.id}` : ''}`, { data, expected_version: selected?.version }, selected ? 'PUT' : 'POST')
  await loadConfiguration(); uiRevision++; result.value = null; stressResult.value = null
}) }
function calculationRequest() {
  return { ...scopeRequest(), prepare_mtm:true, refresh_mtm:refreshMtm.value, common_market:commonMarket.value, mtm_paths:mtmPaths.value,
    common_rate:commonRate.value === '' ? null : Number(commonRate.value) / 100,
    common_rate_source:commonRate.value === '' || Number(commonRate.value) === 3 ? 'TEMPORARY_ASSUMPTION' : 'USER_OVERRIDE',
    allow_market_fetch:allowMarketFetch.value, market_overrides:JSON.parse(marketOverrides.value), price_histories:JSON.parse(priceHistories.value),
    n_outer:nOuter.value, n_inner:nInner.value, n_dates:nDates.value, seed:seed.value, correlations:JSON.parse(correlations.value) }
}
async function runCalculation(isStress = false) {
  if (calculating.value) return
  const revision = uiRevision
  calculating.value = true; progress.value = {stage:'starting'}; progressDeals.value = []; replayMessage.value = ''
  result.value = null; stressResult.value = null
  calculationHeading.value = `${counterparties.value.find(c => c.id === cptyId.value)?.name || ''} · ${dataScope.value === 'UAT' ? 'Recette UAT' : 'Production'} · ${asOf.value} · ${currency.value} · Taux commun ${commonRate.value === '' ? 3 : commonRate.value} %`
  resultsOpen.value = true
  try { await guarded(async () => {
    try {
      const request = calculationRequest()
      if (isStress) Object.assign(request, {stress:stress.value, credit_spread_multiplier:creditMultiplier.value, wwr:'STRESS'})
      const response = await ccrCalculate(request, event => {
        progress.value = event
        if (event.stage === 'scope') progressDeals.value = event.deals.map(d => ({...d, phase:'waiting'}))
        if (event.stage === 'reuse') progressDeals.value.forEach(d => { d.phase = 'CCR_BASE_REUSED' })
        if (event.stage === 'mtm') {
          const row = progressDeals.value.find(d => d.id === event.deal_id)
          if (row) Object.assign(row, {phase:event.phase, error:event.error})
        }
      })
      if (revision === uiRevision) { if (isStress) stressResult.value = response; else result.value = response }
      else error.value = 'Le contexte a changé pendant le calcul. Résultat archivé consultable dans le monitor ; relancer pour le nouveau périmètre.'
    } catch (e) { progress.value = {stage:'failed'}; throw e }
  }) } finally { calculating.value = false }
}
const calculate = () => runCalculation()
const runStress = () => runCalculation(true)
async function loadMonitor() { const scope = dataScope.value; await guarded(async () => { const rows = await ccrApi(`/monitor?data_scope=${scope}`); if (scope === dataScope.value) monitor.value = rows }) }
async function assign(d) { await guarded(async () => { await ccrApi(`/deals/${d.id}/assignment`, { netting_set_id: d.netting_set_id, reason: d.reason }, 'PUT'); d.reason = ''; uiRevision++; result.value = null; stressResult.value = null }) }
async function replay() { await guarded(async () => { const r = await ccrApi(`/runs/${displayResult.value.run_id}/replay`, {}); replayMessage.value = r.identical ? 'Résultat reproduit à l’identique.' : 'Résultat différent — vérifier la version du moteur.' }) }
async function download() { await guarded(async () => { const archive = await ccrApi(`/runs/${displayResult.value.run_id}`); const url = URL.createObjectURL(new Blob([JSON.stringify(archive,null,2)], {type:'application/json'})); const a = document.createElement('a'); a.href = url; a.download = `CCR-${displayResult.value.run_id}.json`; a.click(); URL.revokeObjectURL(url) }) }
onMounted(() => guarded(async () => { const [c,s,p,b] = await Promise.all([ccrApi('/counterparties'),ccrApi('/schemas'),ccrApi('/portfolios'),ccrApi('/uat-batches')]); counterparties.value=c; schemas.value=s; portfolios.value=p; uatBatches.value=b; await loadDeals(); await loadConfiguration(); await loadDiagnostic() }))
</script>

<style scoped>
.ccr-shell, .ccr-panel, .ccr-editor, .ccr-editor-form {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  gap: .75rem;
}
.ccr-shell { height: 100%; }
.ccr-panel, .ccr-editor, .ccr-editor-form { flex: 1; overflow: hidden; }
.ccr-shell > .page-header { flex-shrink: 0; margin-bottom: 0; gap: .5rem; }
.ccr-shell > :deep(.alert-message) { flex-shrink: 0; max-height: 6rem; overflow: auto; overscroll-behavior: contain; }
.ccr-context { display: grid; grid-template-columns: minmax(0, 1.5fr) repeat(2, minmax(0, 1fr)) auto; gap: .75rem; align-items: end; flex-shrink: 0; }
.ccr-view .card { padding: .875rem; }
.ccr-view label { display: flex; flex-direction: column; justify-content: flex-end; min-width: 0; gap: .25rem; }
.ccr-view :is(.input, .select) { width: 100%; min-width: 0; margin-top: 0; }
.ccr-view :is(input.input, .select) { height: 2.5rem; }
.ccr-view textarea { resize: vertical; min-height: 4.5rem; max-height: 12rem; }
.ccr-tabs, .ccr-records { display: flex; gap: .25rem; overflow-x: auto; flex-shrink: 0; }
.ccr-tabs { padding-bottom: .25rem; }
.ccr-tabs > button, .ccr-records > button { flex-shrink: 0; white-space: nowrap; }
.ccr-scroll { overflow: auto; overscroll-behavior: contain; scrollbar-gutter: stable; }
.ccr-scroll:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.ccr-panel-body { flex: 1; min-height: 0; min-width: 0; }
.ccr-controls { display: flex; flex-direction: column; gap: .5rem; flex: 1; max-height: none; min-height: 0; }
.ccr-controls > * { flex-shrink: 0; }
.ccr-calculation-grid { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); align-items: end; gap: .75rem; }
.ccr-calculation-grid > label { grid-column: span 2; }
.ccr-calculation-grid > label:nth-child(-n+3) { grid-column: span 4; }
/* Shared rows keep labels, controls and optional hints aligned independently. */
.ccr-simulation-grid, .ccr-market-grid {
  display: grid;
  grid-template-rows: auto 2.5rem auto;
  column-gap: .75rem;
  row-gap: .25rem;
  min-width: 0;
}
.ccr-simulation-grid { grid-column: 1 / -1; grid-template-columns: repeat(4, minmax(0, 1fr)) minmax(0, 2fr); }
.ccr-market-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.ccr-view .ccr-simulation-grid > label, .ccr-view .ccr-market-grid > label {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: subgrid;
  justify-content: stretch;
  grid-row: 1 / span 3;
  align-items: start;
}
.ccr-simulation-grid > label > span, .ccr-market-grid > label > span { align-self: end; }
.ccr-calculate { grid-column: 5; grid-row: 2; height: 2.5rem; align-self: stretch; }
.ccr-context .btn-secondary { min-height: 2.5rem; display: inline-flex; align-items: center; justify-content: center; }
.ccr-actions { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; flex-shrink: 0; }
.ccr-scopebar label { flex-direction: row; align-items: center; gap: .5rem; }
.ccr-scopebar .select { width: auto; max-width: 20rem; }
.ccr-diagnostic-table { max-height: 14rem; overscroll-behavior: contain; }
.ccr-diagnostic-table th { position: sticky; top: 0; background: var(--surface2); }
.ccr-sort { flex-direction: row !important; align-items: center; gap: .5rem !important; }
.ccr-sort .select { width: auto; }
.ccr-monitor table { min-width: 90rem; }
.ccr-monitor th { position: sticky; top: 0; z-index: 1; background: var(--surface2); }
.ccr-monitor td:nth-last-child(2), .ccr-monitor td:nth-last-child(3), .ccr-monitor td:nth-last-child(4) { text-align: right; }
.ccr-trades { display: flex; flex-direction: column; gap: .5rem; }
.ccr-trade-row { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr) minmax(0, 1.5fr) auto; gap: .75rem; align-items: center; flex-shrink: 0; }
.ccr-trade-row > span { overflow-wrap: anywhere; }
.ccr-editor-heading { display: flex; flex-direction: column; gap: .5rem; flex: 0 1 auto; max-height: 35%; }
.ccr-editor-heading > * { flex-shrink: 0; }
.ccr-fields { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); align-content: start; align-items: start; gap: 1rem .875rem; flex: 1; min-height: 0; padding: .25rem .25rem .5rem; }
.ccr-field-label { min-height: 2rem; display: flex; align-items: end; gap: .2rem; }
.ccr-editor-footer { padding-top: .75rem; border-top: 1px solid var(--border); }
@media (max-width: 1023px) {
  .ccr-context { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ccr-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ccr-calculation-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ccr-calculation-grid > label, .ccr-calculation-grid > label:nth-child(-n+3) { grid-column: span 1; }
  .ccr-simulation-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-rows: repeat(2, auto 2.5rem auto) 2.5rem; }
  .ccr-view .ccr-simulation-grid > label:nth-child(n+3) { grid-row: 4 / span 3; }
  .ccr-calculate { grid-column: 1 / -1; grid-row: 7; }
  .ccr-trade-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 639px) {
  .ccr-shell { gap: .5rem; }
  .ccr-shell .page-title { font-size: 1.1rem; }
  .ccr-context { gap: .5rem; }
  .ccr-context .btn-secondary { width: 100%; white-space: normal; }
  .ccr-fields, .ccr-trade-row { grid-template-columns: minmax(0, 1fr); }
  .ccr-field-label { min-height: auto; }
}
</style>
