<template>
  <section class="ai-workbench" :aria-busy="working">
    <div class="ai-controls">
      <label class="label">Fournisseur
        <select v-model="settings.provider" class="select" :disabled="working">
          <option v-for="p in catalog.providers" :key="p.key" :value="p.key">{{ p.label }}</option>
          <option v-if="!catalog.providers.length" value="ollama">Ollama</option>
        </select>
      </label>
      <label class="label">Modèle
        <select v-model="selectedModel" class="select" :disabled="working || !models.length">
          <option v-if="selectedModel && !models.includes(selectedModel)" :value="selectedModel">{{ selectedModel }} · hors catalogue</option>
          <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
          <option v-if="!selectedModel" value="">Choisir un modèle</option>
        </select>
      </label>
      <button class="btn-secondary" :disabled="working || catalog.loading" @click="refreshAiCatalog">{{ catalog.loading ? 'Chargement…' : 'Actualiser les modèles' }}</button>
    </div>
    <details class="ai-connection">
      <summary>Connexion et modèle personnalisé</summary>
      <label v-if="settings.provider === 'ollama'" class="label">Adresse Ollama
        <input v-model.trim="settings.ollamaUrl" class="input" :disabled="working" @change="refreshAiCatalog" />
      </label>
      <label v-else class="label">Clé API pour cette session (facultative si configurée sur le serveur)
        <input v-model="credentials[settings.provider]" type="password" autocomplete="off" class="input" :disabled="working" />
      </label>
      <label class="label">Identifiant du modèle
        <input v-model.trim="selectedModel" class="input" :disabled="working" />
      </label>
      <small>Les choix sont partagés entre les modules. Les clés saisies ici restent en mémoire pendant la session.</small>
    </details>
    <p class="ai-disclosure">{{ settings.provider === 'ollama' ? 'Le prompt sera envoyé au service Ollama configuré.' : 'Le prompt et les données jointes seront envoyés au fournisseur distant sélectionné.' }}</p>
    <p v-if="provider && !provider.ready && !credentials[settings.provider]" class="ai-hint">{{ provider.needs_key ? 'Renseignez votre clé API dans « Connexion et modèle personnalisé », ou utilisez une clé configurée sur le serveur.' : provider.hint }}</p>
    <AlertMessage v-if="catalog.error || error" kind="error">{{ error || catalog.error }}</AlertMessage>
    <div class="ai-actions">
      <button class="btn-secondary" :disabled="working || disabled" @click="showPrompt">Voir / modifier le prompt</button>
      <button class="btn-primary" :disabled="working || disabled || !ready || stale" @click="run">{{ working ? 'Traitement en cours…' : actionLabel }}</button>
    </div>
    <p v-if="working" role="status" class="ai-status"><span class="ai-spinner"></span>{{ phase }} · {{ seconds }} s</p>
    <p v-if="stale" role="status" class="ai-hint">Le contexte a changé. Vos modifications sont conservées à l’écran ; reconstruisez le prompt avant de générer.</p>
    <div v-if="expanded && prompt" class="ai-prompt">
      <div class="ai-actions"><span class="badge badge-muted">{{ customized ? 'Prompt personnalisé' : 'Prompt par défaut' }}</span>
        <button class="btn-secondary" :disabled="working || disabled" @click="resetPrompt">{{ stale ? 'Reconstruire depuis le contexte actuel' : 'Rétablir le prompt par défaut' }}</button>
        <button class="btn-secondary" :disabled="working" @click="copyPrompt">{{ copied ? 'Copié' : 'Copier le prompt' }}</button>
      </div>
      <label class="label">Instructions du modèle<textarea v-model="draft.system" rows="8" class="input" :disabled="working" /></label>
      <label class="label">Demande et données jointes<textarea v-model="draft.user" rows="10" class="input" :disabled="working" /></label>
      <small>{{ draft.system.length + draft.user.length }} caractères · {{ prompt.prompt_version }}. Les modifications concernent cette demande.</small>
    </div>
    <details v-if="last" class="ai-history">
      <summary>Dernier appel · {{ last.provider }} / {{ last.effective_model || last.model }} · {{ Math.round(last.elapsed_ms / 1000) }} s</summary>
      <p>{{ new Date(last.generated_at).toLocaleString('fr-FR') }} · {{ last.prompt_version }}{{ last.prompt_customized ? ' · personnalisé' : '' }}</p>
      <div v-for="(attempt, i) in (last.attempts || [{ prompt: last.prompt }])" :key="i">
        <strong v-if="last.attempts">Tentative {{ i + 1 }}{{ attempt.kind === 'repair' ? ' · correction automatique' : '' }}</strong>
        <pre>{{ attempt.prompt?.system }}{{ '\n\n=== DEMANDE ===\n\n' }}{{ attempt.prompt?.user }}</pre>
      </div>
    </details>
  </section>
</template>

<script setup>
import AlertMessage from './ui/AlertMessage.vue'
import { useAiWorkbench } from '../composables/useAiWorkbench'
const props = defineProps({
  endpoint: { type: String, required: true }, previewEndpoint: String,
  payload: { type: Object, required: true }, contextKey: { type: String, default: '' },
  actionLabel: { type: String, default: 'Générer' }, disabled: Boolean,
  beforePrepare: Function,
})
const emit = defineEmits(['result', 'busy'])
const { settings, credentials, catalog, refreshAiCatalog, working, phase, seconds,
  error, expanded, copied, prompt, stale, last, draft, provider, models, selectedModel,
  ready, customized, showPrompt, resetPrompt, run, copyPrompt } = useAiWorkbench(props, emit)
defineExpose({ run })
</script>

<style scoped>
.ai-workbench{display:flex;flex-direction:column;gap:12px;font-size:12px;min-width:0}.ai-controls{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr));gap:10px;align-items:end}.label{margin:0;display:flex;flex-direction:column;gap:5px}.select,.input{width:100%;font-size:12px}.ai-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.ai-connection{border-bottom:1px solid var(--border);padding-bottom:10px}.ai-connection .label{margin-top:10px}summary{cursor:pointer;font-weight:600}.ai-disclosure,small,.ai-history p{color:var(--muted);font-size:11px}.ai-hint{color:var(--gold)}.ai-prompt{display:flex;flex-direction:column;gap:12px}.ai-prompt textarea{font-family:monospace;line-height:1.5;resize:vertical;min-height:100px}.ai-history pre{white-space:pre-wrap;overflow:auto;max-height:300px;font-size:11px;margin:10px 0}.ai-status{display:flex;align-items:center;gap:8px}.ai-spinner{width:13px;height:13px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:680px){.ai-controls{grid-template-columns:1fr}.ai-actions>*{max-width:100%}}
</style>
