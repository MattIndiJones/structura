<template>
  <div class="flex-1 flex flex-col min-h-0">
    <main class="flex-1 p-6 max-w-5xl w-full mx-auto flex flex-col gap-4">
      <div class="page-header">
        <div>
          <h1 class="page-title">Sous-jacents</h1>
        </div>
        <div class="page-actions">
          <RouterLink to="/admin" class="btn-ghost btn-sm">← Administration</RouterLink>
        </div>
      </div>

      <AlertMessage v-if="error" kind="error" dismissible @dismiss="error = ''">{{ error }}</AlertMessage>
      <AlertMessage v-if="notice" kind="success" dismissible @dismiss="notice = ''">{{ notice }}</AlertMessage>

      <!-- ── Ajouter : on cherche chez Yahoo plutôt que de taper un code ── -->
      <div class="card flex flex-col gap-3">
        <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">Ajouter un sous-jacent</div>
        <div class="flex flex-wrap items-end gap-2">
          <div class="flex flex-col gap-1 flex-1 min-w-[16rem]">
            <label class="label"
                   title="Nom ou fragment de symbole. « STM » rend les trois cotations de STMicroelectronics : New York, Paris et Milan — une note fixe sur une place, pas sur une autre.">Rechercher chez Yahoo ⓘ</label>
            <input v-model="query" type="text" class="input" placeholder="unicredit, STM, ^FCHI…"
                   @keyup.enter="search" />
          </div>
          <button class="btn-secondary text-xs px-3 py-2 shrink-0"
                  :disabled="searching || query.trim().length < 2" @click="search">
            {{ searching ? 'Recherche…' : '🔎 Chercher' }}
          </button>
        </div>

        <div v-if="results.length" class="table-shell max-h-64 overflow-auto" tabindex="0" role="region">
          <table class="w-full text-xs">
            <thead>
              <tr>
                <th>Symbole</th><th>Nom</th><th>Place</th><th>Type</th>
                <th>Groupe</th><th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in results" :key="r.ticker">
                <td class="font-mono text-slate-200 whitespace-nowrap">{{ r.ticker }}</td>
                <td class="text-slate-300">{{ r.label }}</td>
                <td class="text-slate-500 whitespace-nowrap">{{ r.exchange }}</td>
                <td class="text-slate-600 whitespace-nowrap">{{ r.type }}</td>
                <td>
                  <!-- Vide = ce que la place de cotation ne dit pas. Le
                       placeholder annonce alors « Autres », qui est ce que
                       l'ajout retiendra : le titre reste visible et se
                       reclasse d'un clic dans la liste du dessous. -->
                  <input v-model="r.group" type="text" class="input py-1 px-2 min-w-[10rem]"
                         :class="r.group ? '' : 'border-amber-700/50'"
                         placeholder="Autres — à classer" list="groupes-existants" />
                </td>
                <td class="text-right whitespace-nowrap">
                  <button class="btn-primary text-xs px-3 py-1" :disabled="adding === r.ticker"
                          @click="add(r)">
                    {{ adding === r.ticker ? '…' : 'Ajouter' }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <datalist id="groupes-existants">
          <option v-for="g in groups" :key="g" :value="g" />
        </datalist>

        <p class="text-[10px] text-slate-600">
          Le ticker est vérifié avant d'être inscrit : s'il ne rend aucune cotation, l'ajout est
          refusé. Un ticker muet enregistré en silence ne se découvre qu'au moment de pricer.
        </p>
      </div>

      <!-- ── Le catalogue ─────────────────────────────────────────────── -->
      <div class="card flex flex-col gap-3">
        <div class="flex items-center justify-between">
          <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">
            Catalogue — {{ rows.length }} entrée{{ rows.length > 1 ? 's' : '' }}
          </div>
          <input v-model="filtre" type="text" class="input py-1 px-2 text-xs max-w-[14rem]"
                 placeholder="Filtrer…" />
        </div>

        <LoadingSpinner v-if="loading" class="py-6" />
        <div v-else-if="!rows.length" class="text-xs text-slate-600 py-4">Aucun sous-jacent.</div>

        <div v-else v-for="groupe in groupesAffiches" :key="groupe.nom" class="flex flex-col gap-1">
          <div class="text-[11px] font-semibold text-slate-300">{{ groupe.nom }}</div>
          <div class="table-shell" tabindex="0" role="region">
            <table class="w-full text-xs">
              <thead>
                <tr>
                  <th class="w-32">Ticker</th><th>Libellé</th>
                  <th class="w-24">Devise</th><th class="w-40">Groupe</th>
                  <th class="w-20">Actif</th><th class="w-10"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="u in groupe.items" :key="u.id">
                  <td class="font-mono text-slate-300 whitespace-nowrap">{{ u.ticker }}</td>
                  <td>
                    <input class="input py-1 px-2" :value="u.label"
                           @change="update(u, { label: $event.target.value })" />
                  </td>
                  <td>
                    <input class="input py-1 px-2 w-20 font-mono" :value="u.ccy"
                           @change="update(u, { ccy: $event.target.value.toUpperCase() })" />
                  </td>
                  <td>
                    <input class="input py-1 px-2" :value="u.group" list="groupes-existants"
                           @change="update(u, { group: $event.target.value })" />
                  </td>
                  <td>
                    <select class="select py-1 px-2" :value="u.active ? 'oui' : 'non'"
                            title="Un sous-jacent inactif disparaît des listes déroulantes sans être supprimé — les produits qui s'y réfèrent restent lisibles."
                            @change="update(u, { active: $event.target.value === 'oui' })">
                      <option value="oui">Oui</option>
                      <option value="non">Non</option>
                    </select>
                  </td>
                  <td class="text-right">
                    <button class="icon-btn-danger" title="Supprimer" @click="remove(u)">🗑</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiFetch } from '../utils/api.js'
import AlertMessage from '../components/ui/AlertMessage.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'

const rows = ref([])
const loading = ref(true)
const error = ref('')
const notice = ref('')
const filtre = ref('')

const query = ref('')
const results = ref([])
const searching = ref(false)
const adding = ref('')

const groups = computed(() => [...new Set(rows.value.map(u => u.group))].sort())

// Groupes triés, et dans chaque groupe les libellés : c'est le tri qui rend
// une liste de soixante titres consultable.
const groupesAffiches = computed(() => {
  const terme = filtre.value.trim().toLowerCase()
  const gardees = terme
    ? rows.value.filter(u => u.ticker.toLowerCase().includes(terme)
                          || u.label.toLowerCase().includes(terme))
    : rows.value
  const parGroupe = {}
  for (const u of gardees) (parGroupe[u.group] ||= []).push(u)
  return Object.keys(parGroupe).sort().map(nom => ({
    nom,
    items: parGroupe[nom].sort((a, b) => a.label.localeCompare(b.label, 'fr')),
  }))
})

async function load() {
  loading.value = true
  try {
    const res = await apiFetch('/api/admin/underlyings')
    if (!res.ok) throw new Error('Chargement impossible')
    rows.value = await res.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// Place de cotation Yahoo → groupe du catalogue. Les codes sont ceux que la
// recherche renvoie réellement, relevés titre par titre : Yahoo dit NMS et NAS
// pour le Nasdaq, OSA pour le Nikkei, ZRH pour l'Euro Stoxx, FGI pour le
// FTSE — aucun ne s'invente. Ne couvre que ce qui se déduit de la cotation :
// un groupe sectoriel comme « Banques » ou « Luxe » ne se lit pas dans un code
// de place, et rien ne le devinera.
const GROUPE_PAR_PLACE = {
  PAR: 'Actions FR (CAC)',
  MIL: 'Actions IT (FTSE MIB)',
  NMS: 'Actions US', NAS: 'Actions US', NYQ: 'Actions US',
  NGM: 'Actions US', NCM: 'Actions US', ASE: 'Actions US', PCX: 'Actions US',
}

// Places des indices déjà au catalogue, vérifiées une à une sur la recherche.
const PLACES_INDICE = {
  'Indices Europe': ['PAR', 'GER', 'ZRH', 'FGI', 'MCE', 'EBS', 'MIL'],
  'Indices US':     ['SNP', 'DJI', 'NIM', 'WCB'],
  'Indices Asie':   ['OSA', 'HKG', 'SHH', 'SHZ', 'KSC', 'TAI'],
}

/** Groupe proposé pour un résultat de recherche, ou '' si rien ne se déduit.
 *
 *  Auparavant chaque résultat héritait du premier groupe de la liste, par
 *  ordre alphabétique : chercher UniCredit proposait de le classer dans le
 *  CAC 40. Un défaut faux est pire que pas de défaut, parce qu'il se valide
 *  sans qu'on le relise. Ce qui n'est pas déductible reste vide et tombera
 *  dans « Autres » — visible, et corrigeable d'un clic dans la liste. */
function groupeSuggere(r) {
  const type = (r.type || '').toUpperCase()
  const place = (r.exchange || '').toUpperCase()
  if (type === 'ETF') return 'ETF / Matières premières'
  if (type === 'INDEX') {
    return Object.keys(PLACES_INDICE).find(g => PLACES_INDICE[g].includes(place)) || ''
  }
  if (type !== 'EQUITY') return ''   // futures, fonds, obligations : à classer
  return GROUPE_PAR_PLACE[place] || ''
}

async function search() {
  const q = query.value.trim()
  if (q.length < 2) return
  searching.value = true
  error.value = ''
  try {
    const res = await apiFetch(`/api/admin/underlyings/search?q=${encodeURIComponent(q)}`)
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Recherche impossible')
    // Le groupe est proposé, pas imposé : c'est un classement de travail.
    results.value = (data.results || []).map(r => ({ ...r, group: groupeSuggere(r) }))
    if (!results.value.length) notice.value = `Aucun titre pour « ${q} ».`
  } catch (e) {
    error.value = e.message
    results.value = []
  } finally {
    searching.value = false
  }
}

async function add(r) {
  adding.value = r.ticker
  error.value = ''
  try {
    const res = await apiFetch('/api/admin/underlyings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker: r.ticker, label: r.label,
                             group: r.group || 'Autres', exchange: r.exchange }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || 'Ajout impossible')
    notice.value = `${data.ticker} ajouté — dernière cotation ${data.probe?.last_close} `
                 + `${data.ccy} le ${data.probe?.last_date}.`
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    adding.value = ''
  }
}

async function update(u, patch) {
  error.value = ''
  try {
    const res = await apiFetch(`/api/admin/underlyings/${u.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
    if (!res.ok) throw new Error((await res.json()).detail || 'Mise à jour impossible')
    Object.assign(u, await res.json())
  } catch (e) {
    error.value = e.message
    await load()
  }
}

async function remove(u) {
  error.value = ''
  try {
    const res = await apiFetch(`/api/admin/underlyings/${u.id}`, { method: 'DELETE' })
    if (!res.ok && res.status !== 204) throw new Error('Suppression impossible')
    rows.value = rows.value.filter(x => x.id !== u.id)
  } catch (e) {
    error.value = e.message
  }
}

onMounted(load)
</script>
