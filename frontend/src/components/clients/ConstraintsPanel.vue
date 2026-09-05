<!--
  Le profil de trading du client, rendu depuis le référentiel existant.

  **Cet écran ne connaît aucun champ à l'avance.** Il lit les définitions que le
  serveur lui décrit et choisit un contrôle par type. C'est la seule manière que
  le champ affiché et le champ validé ne divergent jamais — le défaut classique
  étant la liste déroulante côté écran et le texte libre côté serveur.

  C'est aussi ce qui permet d'ajouter « Poche défensive max » sans redéployer :
  un champ déclaré apparaît au rechargement suivant.
-->
<template>
  <div class="flex flex-col gap-5">

    <!-- ── Les repères, qui sont des colonnes et non le blob ──── -->
    <div v-if="isClientScope" class="card flex flex-col gap-4">
      <div class="card-title mb-0">Repères de taille et de maturité</div>
      <p class="card-hint">
        Fourchettes communiquées par le client ou retenues comme habitudes de
        travail. Elles servent de repères commerciaux : une transaction hors
        fourchette reste possible et doit simplement conduire à revalider le profil.
      </p>

      <div class="grid grid-cols-2 gap-3">
        <!-- Un champ numérique ne peut pas porter de séparateurs de milliers :
             le navigateur refuserait la saisie. On garde donc la frappe nue et
             on rend le montant lisible juste en dessous — c'est là que l'œil
             vérifie qu'il a tapé six zéros et non cinq. -->
        <div>
          <label class="label">Ticket min.</label>
          <input v-model.number="scalaires.ticket_min" type="number" class="input" />
          <p class="echo">{{ enClair(scalaires.ticket_min) }}</p>
        </div>
        <div>
          <label class="label">Ticket max.</label>
          <input v-model.number="scalaires.ticket_max" type="number" class="input" />
          <p class="echo">{{ enClair(scalaires.ticket_max) }}</p>
        </div>
        <div>
          <label class="label">Maturité min. (mois)</label>
          <input v-model.number="scalaires.maturity_min_months" type="number" class="input" />
        </div>
        <div>
          <label class="label">Maturité max. (mois)</label>
          <input v-model.number="scalaires.maturity_max_months" type="number" class="input" />
        </div>
        <div>
          <label class="label">Notation min.</label>
          <select v-model="scalaires.min_rating" class="select">
            <option :value="null">—</option>
            <option v-for="note in ECHELLE_RATING" :key="note" :value="note">{{ note }}</option>
          </select>
        </div>
        <div>
          <label class="label">Concentration max. (%)</label>
          <input v-model.number="scalaires.max_concentration_pct" type="number" class="input" />
        </div>
      </div>
      <button class="btn-secondary btn-sm self-start" @click="enregistrerScalaires">
        Enregistrer les repères
      </button>
    </div>

    <!-- ── Le référentiel ─────────────────────────────────────── -->
    <div class="card flex flex-col gap-4">
      <div class="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div class="card-title mb-0">Préférences et habitudes de trading</div>
          <p class="card-hint" style="margin-top: .35rem">
            Profil : <b>{{ scopeLabel }}</b>. Il exprime l'état courant connu et ne bloque
            ni RFQ ni Deal. L'aperçu le compare aux transactions observées afin
            de rendre visibles les habitudes qui évoluent.
          </p>
        </div>
        <button class="btn-secondary btn-sm shrink-0" @click="modaleChamp = true">
          + Ajouter un champ spécifique
        </button>
      </div>

      <LoadingSpinner v-if="chargement" />
      <template v-else>
        <div class="source-box">
          <div>
            <div class="label mb-1">Source de cette mise à jour</div>
            <p class="card-hint" style="margin: 0">
              La nature distingue ce que le Client a dit de ce que nous avons
              simplement noté. La préférence reste modifiable ; son histoire, elle, reste lisible.
            </p>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div>
              <label class="label">Nature</label>
              <select v-model="evidence.statement_kind" class="select">
                <option v-for="item in NATURES" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="label">Date</label>
              <input v-model="evidence.statement_date" type="date" class="input" />
            </div>
            <div>
              <label class="label">Contact source</label>
              <select v-model="evidence.source_affiliation_id" class="select">
                <option :value="null">Non précisé</option>
                <option v-for="contact in contacts" :key="contact.affiliation_id"
                        :value="contact.affiliation_id">
                  {{ contact.first_name }} {{ contact.last_name }}{{ contact.is_current ? '' : ' (ancien)' }}
                </option>
              </select>
            </div>
            <div>
              <label class="label">Canal</label>
              <select v-model="evidence.channel" class="select">
                <option :value="null">Non précisé</option>
                <option value="meeting">Réunion</option>
                <option value="phone">Téléphone</option>
                <option value="email">E-mail</option>
                <option value="other">Autre</option>
              </select>
            </div>
          </div>
          <div>
            <label class="label">Note de source</label>
            <input v-model="evidence.note" class="input"
                   placeholder="Ex : confirmé en comité d’investissement" />
          </div>
        </div>

        <div v-for="definition in definitionsVisibles" :key="definition.key"
             class="champ">
          <div class="flex items-baseline justify-between gap-2 flex-wrap">
            <label class="label mb-0">
              {{ definition.label }}
              <span v-if="definition.unit" style="color: var(--subtle)">
                ({{ definition.unit }})
              </span>
            </label>
            <span v-if="definition.scope !== 'standard'" class="badge badge-muted"
                  :title="definition.scope === 'client'
                          ? 'Nom convenu avec ce client — il n’apparaît que sur sa fiche.'
                          : 'Champ ajouté pour toute la maison.'">
              {{ definition.scope === 'client' ? 'propre à ce client' : 'maison' }}
            </span>
          </div>

          <!-- Listes : catalogue, vocabulaire fermé, ou références -->
          <ValuePicker
            v-if="definition.storage === 'list_str' || definition.storage === 'list_ref'"
            :model-value="listeDe(definition)"
            :options="optionsDe(definition)"
            :free-entry="definition.free_entry"
            :storage="definition.storage"
            :placeholder="definition.catalog ? 'Rechercher dans le catalogue…' : 'Saisir une valeur…'"
            @update:model-value="v => ecrire(definition, v)" />

          <select v-else-if="definition.kind === 'rating'" class="select"
                  :value="valeurs[definition.key] ?? ''"
                  @change="e => ecrire(definition, e.target.value || null)">
            <option value="">—</option>
            <option v-for="note in ECHELLE_RATING" :key="note" :value="note">{{ note }}</option>
          </select>

          <label v-else-if="definition.kind === 'bool'"
                 class="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" :checked="valeurs[definition.key] === true"
                   @change="e => ecrire(definition, e.target.checked ? true : null)" />
            <span>{{ valeurs[definition.key] === true ? 'Oui' : 'Non renseigné' }}</span>
          </label>

          <textarea v-else-if="definition.kind === 'text'" class="input" rows="2"
                    :value="valeurs[definition.key] ?? ''"
                    @input="e => ecrire(definition, e.target.value)"></textarea>

          <div v-else>
            <input type="number" class="input"
                   :value="valeurs[definition.key] ?? ''"
                   @input="e => ecrireNombre(definition, e.target.value)" />
            <p v-if="definition.kind === 'money'" class="echo">
              {{ enClair(valeurs[definition.key]) }}
            </p>
          </div>

          <p v-if="definition.help_text" class="card-hint" style="margin: .3rem 0 0">
            {{ definition.help_text }}
          </p>
        </div>

        <!-- Un champ retiré du référentiel dont ce client porte encore une
             valeur. L'omettre la laisserait vivre dans le blob sans que
             personne puisse la lire ni l'effacer. -->
        <div v-if="retires.length" class="retires">
          <div class="label mb-1">Champs retirés, encore renseignés</div>
          <p class="card-hint" style="margin: 0 0 .5rem">
            Ces champs ne sont plus proposés à la saisie. Leur ancienne valeur
            reste visible pour ne pas perdre d'information ; vous pouvez l'effacer.
          </p>
          <div v-for="definition in retires" :key="definition.key"
               class="flex items-center justify-between gap-3 py-1.5">
            <div class="text-sm">
              <span class="font-semibold">{{ definition.label }}</span>
              <span class="ml-2" style="color: var(--muted)">
                {{ enClairValeur(valeurs[definition.key]) }}
              </span>
            </div>
            <button class="btn-ghost btn-sm" @click="effacer(definition)">Effacer</button>
          </div>
        </div>

        <AlertMessage v-if="conflit" kind="warning">
          Ce profil a été modifié entre-temps par quelqu'un d'autre.
          Vos modifications n'ont pas été enregistrées — rechargez pour repartir
          de la version à jour.
          <button class="btn-secondary btn-sm mt-2" @click="charger">Recharger</button>
        </AlertMessage>
        <AlertMessage v-if="erreur" kind="error" dismissible @dismiss="erreur = ''">
          {{ erreur }}
        </AlertMessage>

        <div class="flex items-center gap-3 flex-wrap">
          <button class="btn-primary btn-sm" :disabled="conflit || !modifie"
                  @click="enregistrer">Enregistrer le profil</button>
          <span v-if="modifie" class="text-xs" style="color: var(--gold)">
            Modifications non enregistrées
          </span>
          <span class="text-xs" style="color: var(--subtle)">
            Version {{ version }}
          </span>
        </div>
      </template>
    </div>

    <div class="card flex flex-col gap-3">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="card-title mb-0">Historique des préférences</div>
          <p class="card-hint" style="margin-top: .35rem">
            Portée : {{ scopeLabel }}. Une correction ajoute une ligne ; elle ne réécrit pas le passé.
          </p>
        </div>
        <span class="badge badge-muted">{{ historique.length }}</span>
      </div>
      <EmptyState v-if="!historique.length" icon="—" title="Aucune évolution datée"
                  hint="La prochaine mise à jour documentée apparaîtra ici." />
      <ul v-else class="flex flex-col divide-y" style="border-color: var(--border)">
        <li v-for="ligne in historique.slice(0, 30)" :key="ligne.id"
            class="py-2.5 grid gap-2 history-row">
          <div>
            <div class="text-sm font-semibold">
              {{ libelleCle(ligne.preference_key) }}
              <span v-if="ligne.is_current" class="badge badge-positive ml-1">courant</span>
            </div>
            <div class="text-xs" style="color: var(--muted)">
              {{ enClairValeur(ligne.value) }}
            </div>
          </div>
          <div class="text-xs" style="color: var(--muted)">
            <div>{{ libelleNature(ligne.statement_kind) }} · {{ ligne.statement_date || 'date antérieure inconnue' }}</div>
            <div v-if="ligne.source_name || ligne.channel">
              {{ ligne.source_name || 'Source non précisée' }}<template v-if="ligne.channel"> · {{ libelleCanal(ligne.channel) }}</template>
            </div>
            <div v-if="ligne.note" class="mt-0.5">{{ ligne.note }}</div>
          </div>
        </li>
      </ul>
    </div>

    <ConstraintFieldModal v-if="modaleChamp" :client-id="clientId"
                          @close="modaleChamp = false"
                          @created="apresDeclaration" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useClientsStore } from '../../stores/clients.js'
import { formatInt, formatNumber } from '../../utils/format.js'
import AlertMessage from '../ui/AlertMessage.vue'
import EmptyState from '../ui/EmptyState.vue'
import LoadingSpinner from '../ui/LoadingSpinner.vue'
import ValuePicker from './ValuePicker.vue'
import ConstraintFieldModal from './ConstraintFieldModal.vue'

const props = defineProps({
  clientId: { type: [Number, String], required: true },
  client: { type: Object, default: null },
  scope: { type: Object, default: () => ({}) },
  contacts: { type: Array, default: () => [] },
})
const emit = defineEmits(['save-scalars', 'saved'])

const ECHELLE_RATING = [
  'AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', 'A-', 'BBB+', 'BBB', 'BBB-',
  'BB+', 'BB', 'BB-', 'B+', 'B', 'B-', 'CCC+', 'CCC', 'CCC-', 'CC', 'C', 'D',
]

const LIBELLES_OPTIONS = {
  phoenix_memory: 'Phoenix Memory',
  reverse_convertible: 'Reverse Convertible',
  barrier_reverse_convertible: 'Barrier Reverse Convertible',
  capital_protected: 'Capital garanti',
  twin_win: 'Twin Win',
  credit_linked: 'Credit-Linked Note',
  callable_note: 'Callable Note',
  structured_rates: 'Produits structurés de taux',
  equity_swap: 'Swap actions',
  rates_swap: 'Swap de taux',
  autocall: 'Autocall', phoenix: 'Phoenix', participation: 'Participation',
  shark: 'Shark Note', other: 'Autre',
}

const store = useClientsStore()
const chargement = ref(true)
const definitions = ref([])
const retires = ref([])
const catalogues = ref({})
const valeurs = reactive({})
const version = ref(0)
const modifie = ref(false)
const conflit = ref(false)
const erreur = ref('')
const modaleChamp = ref(false)
const historique = ref([])

const NATURES = [
  { value: 'sales_note', label: 'Note commerciale' },
  { value: 'client_declared', label: 'Déclaré par le Client' },
  { value: 'client_confirmed', label: 'Confirmé par le Client' },
  { value: 'client_contradicted', label: 'Contredit / mis à jour par le Client' },
]

function dateLocaleIso() {
  const maintenant = new Date()
  const decalage = maintenant.getTimezoneOffset() * 60_000
  return new Date(maintenant.getTime() - decalage).toISOString().slice(0, 10)
}

const evidence = reactive({
  statement_kind: 'sales_note',
  statement_date: dateLocaleIso(),
  source_affiliation_id: null,
  channel: null,
  note: '',
})

const scalaires = reactive({
  ticket_min: null, ticket_max: null, maturity_min_months: null,
  maturity_max_months: null, min_rating: null, max_concentration_pct: null,
})

const definitionsVisibles = computed(() => definitions.value)
const isClientScope = computed(
  () => !props.scope?.mandate_id && !props.scope?.affiliation_id)
const scopeLabel = computed(() => props.scope?.name || props.client?.name || 'Client')
const definitionLabels = computed(() => Object.fromEntries(
  [...definitions.value, ...retires.value].map(item => [item.key, item.label])))

function evidencePayload() {
  return {
    statement_kind: evidence.statement_kind,
    statement_date: evidence.statement_date,
    source_affiliation_id: evidence.source_affiliation_id || null,
    channel: evidence.channel || null,
    note: evidence.note.trim() || null,
  }
}

function reinitialiserEvidence() {
  Object.assign(evidence, {
    statement_kind: 'sales_note',
    statement_date: dateLocaleIso(),
    source_affiliation_id: null,
    channel: null,
    note: '',
  })
}

async function enregistrerScalaires() {
  erreur.value = ''
  try {
    await store.modifierScalaires(
      props.clientId, { ...scalaires, evidence: evidencePayload() })
    reinitialiserEvidence()
    emit('saved')
    await charger()
  } catch (e) {
    erreur.value = e.message || 'Enregistrement refusé.'
  }
}

function libelleCle(cle) { return definitionLabels.value[cle] || cle }
function libelleNature(code) {
  if (code === 'legacy_snapshot') return 'État antérieur repris'
  return NATURES.find(item => item.value === code)?.label || code
}
function libelleCanal(code) {
  return { meeting: 'réunion', phone: 'téléphone', email: 'e-mail', other: 'autre' }[code] || code
}

function listeDe(definition) {
  const valeur = valeurs[definition.key]
  return Array.isArray(valeur) ? valeur : []
}

function optionsDe(definition) {
  if (definition.catalog) return catalogues.value[definition.catalog] || []
  // Suggestions portées par la définition ; `free_entry` décide si la liste
  // reste ouverte à une appellation propre au client.
  return (definition.options || []).map(o => ({
    value: o, label: LIBELLES_OPTIONS[o] || o, group: '',
  }))
}

function ecrire(definition, valeur) {
  // Une liste vide et une absence sont le même état : « pas de politique ».
  // Les distinguer produirait une politique vide qui n'exclut rien mais que
  // l'écran présenterait comme une politique.
  if (valeur === null || valeur === '' || (Array.isArray(valeur) && !valeur.length)) {
    delete valeurs[definition.key]
  } else {
    valeurs[definition.key] = valeur
  }
  modifie.value = true
}

function ecrireNombre(definition, brut) {
  if (brut === '') return ecrire(definition, null)
  const nombre = Number(brut)
  ecrire(definition, Number.isFinite(nombre) ? nombre : null)
}

function effacer(definition) {
  delete valeurs[definition.key]
  modifie.value = true
}

function enClair(valeur) {
  if (valeur === null || valeur === undefined || valeur === '') return ' '
  const n = Number(valeur)
  if (!Number.isFinite(n)) return ' '
  const formate = formatInt(n)
  if (Math.abs(n) >= 1e6) return `${formate}  ·  ${formatNumber(n / 1e6, 2)} M`
  if (Math.abs(n) >= 1e3) return `${formate}  ·  ${formatInt(n / 1e3)} k`
  return formate
}

function enClairValeur(valeur) {
  if (Array.isArray(valeur)) {
    return valeur.map(v => (typeof v === 'string' ? v : v?.label)).join(', ')
  }
  if (typeof valeur === 'boolean') return valeur ? 'Oui' : 'Non'
  if (typeof valeur === 'number') return formatNumber(valeur, 2)
  return String(valeur ?? '—')
}

async function charger() {
  chargement.value = true
  conflit.value = false
  erreur.value = ''
  try {
    const scope = {
      mandate_id: props.scope?.mandate_id || null,
      affiliation_id: props.scope?.affiliation_id || null,
    }
    let schema
    let history = null
    if (isClientScope.value) {
      // L'historique enrichit le formulaire mais ne doit jamais empêcher de
      // lire/modifier le profil courant s'il est momentanément indisponible.
      schema = await store.lireSchemaContraintes(props.clientId)
      try { history = await store.lireHistoriquePreferences(props.clientId) }
      catch { history = [] }
    } else {
      schema = await store.lireSchemaPreferencesScope(props.clientId, scope)
    }
    definitions.value = schema.definitions || []
    retires.value = schema.retired || []
    catalogues.value = schema.catalogs || {}
    version.value = isClientScope.value
      ? schema.constraints_version : schema.preferences_version
    historique.value = history || schema.preference_history || []
    for (const cle of Object.keys(valeurs)) delete valeurs[cle]
    Object.assign(valeurs, JSON.parse(JSON.stringify(schema.values || {})))
    modifie.value = false
  } catch (e) {
    erreur.value = e.message || 'Le référentiel n’a pas pu être chargé.'
  } finally {
    chargement.value = false
  }
}

async function enregistrer() {
  erreur.value = ''
  try {
    if (isClientScope.value) {
      await store.enregistrerContraintes(
        props.clientId, { ...valeurs }, version.value, evidencePayload())
    } else {
      await store.enregistrerPreferencesScope(
        props.clientId, { ...valeurs }, props.scope, version.value,
        evidencePayload())
    }
    modifie.value = false
    reinitialiserEvidence()
    emit('saved')
    await charger()
  } catch (e) {
    if (e.status === 409) conflit.value = true
    else erreur.value = e.message || 'Enregistrement refusé.'
  }
}

async function apresDeclaration() {
  modaleChamp.value = false
  // Le champ déclaré doit apparaître SANS perdre la saisie en cours : on
  // recharge le schéma et on réapplique les valeurs de l'écran par-dessus.
  const enCours = JSON.parse(JSON.stringify(valeurs))
  await charger()
  Object.assign(valeurs, enCours)
  modifie.value = Object.keys(enCours).length > 0
}

watch(() => props.client, (client) => {
  if (!client) return
  for (const cle of Object.keys(scalaires)) scalaires[cle] = client[cle] ?? null
}, { immediate: true, deep: false })

watch([() => props.clientId, () => props.scope?.mandate_id,
       () => props.scope?.affiliation_id], () => {
  reinitialiserEvidence()
  charger()
})
onMounted(charger)
</script>

<style scoped>
.champ { display: flex; flex-direction: column; gap: .35rem; }
.echo { font-size: .7rem; color: var(--subtle); min-height: 1rem; margin-top: .15rem; }
.retires {
  padding: .75rem; border: 1px dashed var(--border); border-radius: .5rem;
  background: var(--surface2);
}
.source-box {
  display: flex; flex-direction: column; gap: .75rem; padding: .8rem;
  border: 1px solid var(--border); border-radius: .55rem;
  background: var(--surface2);
}
.history-row { grid-template-columns: minmax(0, 1fr) minmax(15rem, 1fr); }
@media (max-width: 640px) { .history-row { grid-template-columns: 1fr; } }
</style>
