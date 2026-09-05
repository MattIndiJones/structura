<!--
  Import d'historique commercial.

  Le parcours en trois temps est délibéré : on télécharge le modèle, on regarde
  ce que l'import ferait, on valide. L'étape du milieu est celle qui compte —
  sans elle, on découvre après coup qu'une colonne décalée a créé quatre-vingts
  sociétés.

  Le bouton de versement reste inactif tant qu'un aperçu n'a pas été fait : ce
  n'est pas une contrainte administrative, c'est la seule façon de garantir que
  personne ne verse un fichier sans l'avoir vu.
-->
<template>
  <div class="flex flex-col gap-5">

    <!-- Le modèle -->
    <div class="card flex flex-col gap-3">
      <div class="card-title mb-0">1. Partir du modèle</div>
      <p class="text-sm" style="color: var(--muted)">
        Une feuille par type d'objet, dans l'ordre où elles se lisent : sociétés,
        personnes, parcours professionnels, transactions passées, échanges. Ne
        remplissez que ce que vous avez — une feuille vide est ignorée.
      </p>
      <div class="flex items-center gap-2 flex-wrap">
        <button class="btn-secondary" @click="telecharger('xlsx')">
          Modèle Excel
        </button>
        <button class="btn-ghost" @click="telecharger('json')">
          Modèle JSON
        </button>
      </div>
      <details class="text-xs">
        <summary class="cursor-pointer font-semibold" style="color: var(--muted)">
          Ce que chaque feuille attend
        </summary>
        <div v-if="schema" class="mt-2 flex flex-col gap-2">
          <div v-for="feuille in schema.sheets" :key="feuille.key">
            <div class="font-semibold">{{ feuille.label }}
              <span class="font-mono" style="color: var(--subtle)">
                ({{ feuille.key }})</span>
            </div>
            <div style="color: var(--muted)">
              <span v-for="colonne in feuille.columns" :key="colonne">
                <span :class="{ 'font-semibold': feuille.required.includes(colonne) }">
                  {{ colonne }}</span><span
                  v-if="feuille.required.includes(colonne)"
                  style="color: var(--negative)">*</span><!--
                -->{{ colonne === feuille.columns[feuille.columns.length - 1] ? '' : ' · ' }}
              </span>
            </div>
          </div>
          <p style="color: var(--subtle)">
            * champ requis. L'ordre des colonnes est libre, la casse et les
            accents sont tolérés.
          </p>
        </div>
      </details>
    </div>

    <!-- L'aperçu -->
    <div class="card flex flex-col gap-3">
      <div class="card-title mb-0">2. Voir ce que ça ferait</div>
      <p class="text-sm" style="color: var(--muted)">
        Rien n'est écrit à cette étape. Le fichier est lu, validé et rapproché de
        ce qui existe déjà.
      </p>
      <div class="flex items-center gap-3 flex-wrap">
        <input ref="champFichier" type="file" accept=".xlsx,.xlsm,.json"
               class="input" style="max-width: 22rem" @change="fichierChoisi" />
        <button class="btn-secondary" :disabled="!fichier || enCours"
                @click="apercu">
          {{ enCours ? 'Lecture…' : 'Analyser' }}
        </button>
      </div>

      <AlertMessage v-if="erreur" kind="error">{{ erreur }}</AlertMessage>

      <template v-if="rapport">
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="stat-box">
            <div class="text-xs" style="color: var(--muted)">À créer</div>
            <div class="text-xl font-bold tabular-nums" style="color: var(--positive)">
              {{ rapport.total_created }}
            </div>
          </div>
          <div class="stat-box">
            <div class="text-xs" style="color: var(--muted)">À compléter</div>
            <div class="text-xl font-bold tabular-nums">{{ rapport.total_updated }}</div>
          </div>
          <div class="stat-box">
            <div class="text-xs" style="color: var(--muted)">Déjà connues</div>
            <div class="text-xl font-bold tabular-nums">{{ rapport.total_skipped }}</div>
          </div>
          <div class="stat-box">
            <div class="text-xs" style="color: var(--muted)">Anomalies</div>
            <div class="text-xl font-bold tabular-nums"
                 :style="rapport.issues.length ? 'color: var(--negative)' : ''">
              {{ rapport.issues.length }}
            </div>
          </div>
        </div>

        <div class="tablewrap overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left" style="border-bottom: 1px solid var(--border)">
                <th class="py-2 pr-4 font-semibold">Section</th>
                <th class="py-2 pr-4 font-semibold text-right">Créées</th>
                <th class="py-2 pr-4 font-semibold text-right">Complétées</th>
                <th class="py-2 font-semibold text-right">Déjà connues</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="section in sections" :key="section"
                  style="border-bottom: 1px solid var(--border)">
                <td class="py-2 pr-4">{{ libelleSection(section) }}</td>
                <td class="py-2 pr-4 text-right tabular-nums">
                  {{ rapport.created[section] || 0 }}
                </td>
                <td class="py-2 pr-4 text-right tabular-nums">
                  {{ rapport.updated[section] || 0 }}
                </td>
                <td class="py-2 text-right tabular-nums">
                  {{ rapport.skipped[section] || 0 }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <AlertMessage v-if="rapport.unknown_sheets.length" kind="info">
          Section(s) ignorée(s) car non reconnue(s) :
          {{ rapport.unknown_sheets.join(', ') }}.
        </AlertMessage>

        <div v-if="rapport.issues.length" class="flex flex-col gap-2">
          <div class="text-sm font-semibold" style="color: var(--negative)">
            {{ rapport.issues.length }} ligne(s) à corriger
          </div>
          <ul class="flex flex-col gap-1 max-h-64 overflow-y-auto rounded-[10px] p-3"
              style="background: var(--surface2); border: 1px solid var(--border)">
            <li v-for="(anomalie, i) in rapport.issues" :key="i" class="text-xs">
              <span class="font-mono font-semibold">
                {{ anomalie.feuille }} · ligne {{ anomalie.ligne }}</span>
              <span v-if="anomalie.champ" class="font-mono"
                    style="color: var(--subtle)"> ({{ anomalie.champ }})</span>
              — {{ anomalie.message }}
            </li>
          </ul>
        </div>
      </template>
    </div>

    <!-- Le versement -->
    <div class="card flex flex-col gap-3">
      <div class="card-title mb-0">3. Verser</div>
      <p v-if="!rapport" class="text-sm" style="color: var(--subtle)">
        Analysez d'abord un fichier : on ne verse pas ce qu'on n'a pas vu.
      </p>
      <template v-else>
        <p class="text-sm" style="color: var(--muted)">
          Les transactions versées alimentent l'analyse commerciale — cadence,
          comportement observé. Ce ne sont pas des positions : elles n'entrent ni
          dans le book, ni dans le risque, ni dans le MtM.
        </p>
        <label v-if="rapport.issues.length"
               class="flex items-center gap-2 text-sm cursor-pointer">
          <input v-model="ignorerFautives" type="checkbox" />
          <span>Importer quand même les lignes valides, en ignorant les
            {{ rapport.issues.length }} en anomalie</span>
        </label>
        <button class="btn-primary self-start"
                :disabled="enCours || (rapport.issues.length && !ignorerFautives)"
                @click="verser">
          {{ enCours ? 'Import…' : `Importer ${rapport.total_created} ligne(s)` }}
        </button>
      </template>

      <AlertMessage v-if="succes" kind="success">{{ succes }}</AlertMessage>
    </div>

    <!-- L'historique des versements -->
    <div class="card flex flex-col gap-3">
      <div class="card-title mb-0">Versements précédents</div>
      <EmptyState v-if="!lots.length" icon="📥" title="Aucun import à ce jour" />
      <ul v-else class="flex flex-col divide-y" style="border-color: var(--border)">
        <li v-for="lot in lots" :key="lot.id"
            class="py-2.5 flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="text-sm font-semibold truncate">
              {{ lot.filename || '(sans nom)' }}
              <span v-if="lot.status === 'reverted'" class="badge badge-muted ml-1">
                annulé
              </span>
            </div>
            <div class="text-xs" style="color: var(--muted)">
              {{ formaterDate(lot.created_at) }} ·
              {{ lot.rows_created }} créée(s) ·
              {{ lot.rows_updated }} complétée(s) ·
              {{ lot.rows_skipped }} ignorée(s)
            </div>
          </div>
          <button v-if="lot.status === 'applied'" class="btn-ghost btn-sm shrink-0"
                  @click="annuler(lot)">
            Annuler
          </button>
        </li>
      </ul>
      <p class="text-xs" style="color: var(--subtle)">
        Annuler retire les transactions versées par le lot. Les sociétés,
        personnes et parcours créés sont conservés : ils ont pu recevoir depuis
        des saisies faites à la main.
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { apiFetch } from '../../utils/api.js'
import { lireErreur } from '../../stores/clients.js'
import { confirmer } from '../../composables/useConfirm.js'
import AlertMessage from '../ui/AlertMessage.vue'
import EmptyState from '../ui/EmptyState.vue'
import { formatDate } from '../../utils/format.js'

const emit = defineEmits(['importe'])

const LIBELLES = {
  clients: 'Sociétés clientes', contacts: 'Personnes',
  affiliations: 'Parcours professionnels', transactions: 'Transactions passées',
  interactions: 'Échanges passés',
}
const sections = Object.keys(LIBELLES)
const libelleSection = (cle) => LIBELLES[cle] || cle

const champFichier = ref(null)
const fichier = ref(null)
const rapport = ref(null)
const schema = ref(null)
const lots = ref([])
const erreur = ref('')
const succes = ref('')
const enCours = ref(false)
const ignorerFautives = ref(false)

function fichierChoisi(evenement) {
  fichier.value = evenement.target.files?.[0] || null
  // Un nouveau fichier invalide l'aperçu précédent : laisser le bouton actif
  // permettrait de verser un fichier en ayant lu le rapport d'un autre.
  rapport.value = null
  succes.value = ''
  erreur.value = ''
  ignorerFautives.value = false
}

async function telecharger(format) {
  const reponse = await apiFetch(`/api/client-import/template.${format}`)
  if (!reponse.ok) { erreur.value = 'Modèle indisponible.'; return }
  const blob = await reponse.blob()
  const url = URL.createObjectURL(blob)
  const lien = document.createElement('a')
  lien.href = url
  lien.download = `structura_import_clients.${format}`
  lien.click()
  URL.revokeObjectURL(url)
}

async function _envoyer(route, extra = {}) {
  const corps = new FormData()
  corps.append('file', fichier.value)
  Object.entries(extra).forEach(([cle, valeur]) => corps.append(cle, valeur))
  // Pas de Content-Type posé à la main : le navigateur doit écrire lui-même la
  // frontière multipart, et l'imposer casse l'envoi.
  const reponse = await apiFetch(`/api/client-import/${route}`,
                                 { method: 'POST', body: corps })
  if (!reponse.ok) {
    const details = await lireErreur(reponse)
    throw Object.assign(new Error(details.message), details)
  }
  return reponse.json()
}

async function apercu() {
  enCours.value = true
  erreur.value = ''
  succes.value = ''
  try {
    rapport.value = await _envoyer('preview')
  } catch (e) {
    erreur.value = e.message
    rapport.value = null
  } finally {
    enCours.value = false
  }
}

async function verser() {
  enCours.value = true
  erreur.value = ''
  try {
    const resultat = await _envoyer('apply', {
      skip_invalid: ignorerFautives.value ? 'true' : 'false' })
    succes.value = (`${resultat.total_created} ligne(s) créée(s), `
                    + `${resultat.total_updated} complétée(s). `
                    + `L'analyse commerciale en tient compte immédiatement.`)
    rapport.value = null
    fichier.value = null
    if (champFichier.value) champFichier.value.value = ''
    await chargerLots()
    emit('importe', resultat)
  } catch (e) {
    erreur.value = e.message
  } finally {
    enCours.value = false
  }
}

async function annuler(lot) {
  if (!await confirmer({
    titre: 'Annuler ce versement ?',
    message: "Les transactions importées par ce lot seront retirées, et la "
           + "cadence des clients concernés recalculée sans elles. Les sociétés, "
           + "personnes et parcours créés sont conservés.",
    confirmer: 'Annuler le versement', danger: true })) return
  try {
    const reponse = await apiFetch(
      `/api/client-import/batches/${lot.id}/revert`, { method: 'POST' })
    if (!reponse.ok) throw new Error((await lireErreur(reponse)).message)
    succes.value = (await reponse.json()).message
    await chargerLots()
    emit('importe', null)
  } catch (e) {
    erreur.value = e.message
  }
}

async function chargerLots() {
  const reponse = await apiFetch('/api/client-import/batches')
  lots.value = reponse.ok ? await reponse.json() : []
}

// Delegue a utils/format.js : separateur de milliers normalise, date lue
// en calendrier local. Un formateur local re-introduirait l'espace fine
// insecable d'Intl, invisible a l'ecran.
const formaterDate = formatDate

onMounted(async () => {
  const reponse = await apiFetch('/api/client-import/schema')
  if (reponse.ok) schema.value = await reponse.json()
  await chargerLots()
})
</script>
