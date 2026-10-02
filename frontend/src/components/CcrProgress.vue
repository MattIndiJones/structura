<template>
  <div v-if="progress" class="card text-xs ccr-progress" aria-live="polite" role="status">
    <b>{{ labels[progress.stage] || progress.stage }}</b>
    <span v-if="progress.total != null && progress.stage !== 'common_market'"> · {{ number(progress.completed || 0) }} / {{ number(progress.total) }} deals traités</span>
    <span v-if="progress.horizons"> · {{ number(progress.horizon) }} / {{ number(progress.horizons) }} horizons calculés</span>
    <p v-if="progress.source_run_id">Source : calcul CCR #{{ progress.source_run_id }}.</p>
    <p v-if="progress.reference" class="mt-1">{{ progress.reference }} · {{ phaseLabel(progress) }}</p>
    <p v-if="progress.stage === 'completed'" class="mt-1">{{ progress.status === 'MISSING_DATA' ? 'Terminé avec données manquantes — consulter les motifs.' : 'Résultats et hypothèses enregistrés.' }}</p>
    <details v-if="deals.length" class="mt-2"><summary>Avancement des MtM par deal</summary>
      <div class="ccr-progress-rows"><p v-for="d in deals" :key="d.id">{{ d.reference }} · {{ d.error || phaseLabel(d) }}</p></div>
    </details>
  </div>
</template>
<script setup>
import { valuationSources, number } from '../utils/ccr.js'
defineProps({ progress: Object, deals: { type: Array, default: () => [] } })
const labels = { reuse: 'Base MtM compatible réutilisée', starting: 'Initialisation', scope: 'Périmètre identifié', common_market: 'Calibration du marché commun et recalcul des MtM', mtm: 'Préparation des MtM', projection: 'Projection des expositions', stress: 'Projection sous stress', aggregation: 'Agrégation, CVA et limites', saving: 'Enregistrement du dossier', completed: 'Calcul terminé', failed: 'Calcul interrompu' }
const phases = { waiting: 'En attente', preparing: 'Vérification du contexte', market_data: 'Données de marché', residual: 'Payoff résiduel', pricing: 'Valorisation', repricing: 'Valorisation sous les hypothèses CCR', failed: 'Échec', loading: 'Chargement', history: 'Historique' }
const phaseLabel = p => p.error || valuationSources[p.phase] || phases[p.phase] || p.phase || 'En cours'
</script>
<style scoped>
.ccr-progress { flex-shrink: 0; min-width: 0; max-height: 12rem; overflow: auto; overscroll-behavior: auto; }
.ccr-progress p { overflow-wrap: anywhere; }
.ccr-progress-rows { max-height: 6rem; overflow: auto; overscroll-behavior: auto; padding-top: .5rem; }
</style>
