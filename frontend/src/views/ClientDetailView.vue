<!--
  Fiche client — un en-tête, puis des onglets.

  La structure est un REGISTRE : ajouter un onglet coûte une entrée dans
  `ONGLETS` et un bloc dans le template. C'est délibéré — cet écran va grossir
  (documents, KID, valorisations…), et une fiche qui empile tout dans une seule
  colonne devient illisible bien avant d'être complète.

  L'onglet Aperçu porte `ClientCard`, qui se comporte honnêtement quel que soit
  l'historique : ce n'est pas un écran riche et un écran dégradé, c'est le même
  dont le centre de gravité se déplace.
-->
<template>
  <div class="min-h-screen" style="background: var(--bg)">
    <div class="max-w-6xl mx-auto px-6 py-8 flex flex-col gap-6">

      <LoadingSpinner v-if="store.chargement && !client" />
      <AlertMessage v-else-if="!client" kind="error">
        Ce client est introuvable.
      </AlertMessage>

      <template v-else>
        <!-- En-tête -->
        <div class="flex flex-col gap-2">
          <BackLink class="self-start" fallback="/clients/liste" />
          <div class="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 class="font-display text-2xl font-black tracking-tight">
                {{ client.name }}
              </h1>
              <div class="flex items-center gap-2 mt-1.5 flex-wrap text-xs">
                <span class="badge" :class="classeStatut(client.status)">
                  {{ libelleStatutClient(client.status) }}
                </span>
                <span class="badge badge-muted">
                  {{ libelleProvenance(client.data_origin) }}
                </span>
                <span style="color: var(--muted)">
                  {{ libelleTypeClient(client.client_type) }}
                  <template v-if="client.country"> · {{ client.country }}</template>
                  · Couvert par {{ noms(client.coverage) }}
                </span>
                <span v-if="badgeCadence" class="badge" :class="badgeCadence.classe">
                  {{ badgeCadence.texte }}
                </span>
              </div>
            </div>
            <div class="flex items-center gap-2 flex-wrap">
              <RouterLink :to="lifecycleRoute" class="btn-secondary">
                Voir le Life Cycle
              </RouterLink>
              <button class="btn-secondary" @click="modaleEdition = true">Modifier</button>
              <button v-if="client.status !== 'archived'" class="btn-ghost"
                      @click="archiver">Archiver</button>
              <button v-else class="btn-secondary" @click="reactiver">Réactiver</button>
              <button class="btn-danger" @click="supprimer">Supprimer</button>
            </div>
          </div>
        </div>

        <AlertMessage v-if="messageErreur" kind="error" dismissible
                      @dismiss="messageErreur = ''">{{ messageErreur }}</AlertMessage>

        <!-- Bande d'action : la fenêtre de contact, ou la relance notée -->
        <div v-if="action" class="action" :class="action.ton">
          <span class="action-icone" aria-hidden="true">{{ action.icone }}</span>
          <div class="flex-1" style="min-width: 18rem">
            <div class="text-sm font-bold">{{ action.titre }}</div>
            <div class="text-xs" style="color: var(--muted)">{{ action.pourquoi }}</div>
          </div>
          <span class="badge" :class="action.badgeClasse">{{ action.badge }}</span>
        </div>

        <!-- Un même Client peut abriter des habitudes opposées. Le sélecteur
             pilote l'aperçu, les transactions et les préférences sans créer
             une seconde fiche ni une route parallèle. -->
        <div class="scope-bar">
          <div class="min-w-0">
            <label class="label mb-1">Profil analysé</label>
            <select v-model="scopeKey" class="select scope-select">
              <option value="client">Client — vue agrégée</option>
              <optgroup v-if="mandatsActifs.length" label="Mandats / périmètres">
                <option v-for="mandat in mandatsActifs" :key="`m-${mandat.id}`"
                        :value="`mandate:${mandat.id}`">{{ mandat.name }}</option>
              </optgroup>
              <optgroup v-if="store.contacts.length" label="Contacts">
                <option v-for="contact in store.contacts" :key="`a-${contact.affiliation_id}`"
                        :value="`affiliation:${contact.affiliation_id}`">
                  {{ contact.first_name }} {{ contact.last_name }}{{ contact.is_current ? '' : ' (ancien)' }}
                </option>
              </optgroup>
            </select>
          </div>
          <div class="flex-1 text-xs" style="color: var(--muted); min-width: 16rem">
            <b>{{ intelligence?.scope?.name || scopeDescriptor.name }}</b>
            · les préférences guident la lecture et ne bloquent aucune transaction.
          </div>
          <span v-if="intelligence?.analysis_mode === 'demo'" class="badge badge-gold">
            données fictives
          </span>
          <span v-if="intelligence?.excluded_demo_count" class="badge badge-muted"
                :title="`${intelligence.excluded_demo_count} transaction(s) UAT exclue(s) du profil réel`">
            {{ intelligence.excluded_demo_count }} UAT exclue(s)
          </span>
        </div>

        <!-- Onglets -->
        <!-- Des liens : chaque onglet est une adresse. Revenir d'un contact
             ramène ainsi sur l'onglet d'où l'on venait, et non sur l'aperçu. -->
        <nav class="tabs self-start flex-wrap">
          <RouterLink v-for="onglet in ONGLETS" :key="onglet.cle" class="tab-btn"
                      :to="`/clients/fiche/${route.params.id}/${onglet.cle}`"
                      :class="{ active: ongletActif === onglet.cle }">
            {{ onglet.libelle }}
            <span v-if="compteur(onglet.cle) !== null" class="pastille">
              {{ compteur(onglet.cle) }}
            </span>
          </RouterLink>
        </nav>

        <!-- ── Aperçu ────────────────────────────────────────── -->
        <ClientCard v-if="ongletActif === 'apercu'" :fiche="intelligence" />
        <EmptyState v-if="ongletActif === 'apercu' && !intelligence" icon="⏳"
                    title="Analyse indisponible"
                    hint="La lecture analytique n'a pas pu être chargée. Le reste de la fiche reste utilisable." />
        <div v-if="ongletActif === 'apercu'" class="card flex flex-col gap-3">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="card-title mb-0">Mandats et périmètres</div>
              <p class="card-hint">Le périmètre concret dans lequel une RFQ Client sera traitée.</p>
            </div>
            <button class="btn-secondary btn-sm" @click="saisieMandat = !saisieMandat">
              {{ saisieMandat ? 'Annuler' : '+ Ajouter' }}
            </button>
          </div>
          <form v-if="saisieMandat" class="grid grid-cols-1 sm:grid-cols-4 gap-3"
                @submit.prevent="ajouterMandat">
            <div class="sm:col-span-2">
              <label class="label">Nom du périmètre</label>
              <input v-model="nouveauMandat.name" class="input" required
                     placeholder="Ex : Fonds Europe Rendement" />
            </div>
            <div>
              <label class="label">Type</label>
              <select v-model="nouveauMandat.mandate_type" class="select">
                <option v-for="type in TYPES_MANDAT" :key="type.value" :value="type.value">
                  {{ type.label }}
                </option>
              </select>
            </div>
            <div>
              <label class="label">Devise de référence</label>
              <input v-model="nouveauMandat.reference_currency" class="input" placeholder="EUR" />
            </div>
            <div class="sm:col-span-3">
              <label class="label">Commentaire</label>
              <input v-model="nouveauMandat.comment" class="input"
                     placeholder="Contraintes ou usage de ce périmètre" />
            </div>
            <div class="flex items-end">
              <button class="btn-primary w-full" type="submit">Créer</button>
            </div>
          </form>
          <EmptyState v-if="!mandatsActifs.length" icon="▣" title="Aucun mandat actif"
                      hint="Les opportunités peuvent rester en brouillon, mais une RFQ Client exigera un périmètre actif." />
          <ul v-else class="flex flex-col divide-y" style="border-color: var(--border)">
            <li v-for="mandat in mandatsActifs" :key="mandat.id"
                class="py-2.5 flex items-center justify-between gap-3">
              <div>
                <div class="text-sm font-semibold">{{ mandat.name }}</div>
                <div class="text-xs" style="color: var(--muted)">
                  {{ libelleTypeMandat(mandat.mandate_type) }}
                  <template v-if="mandat.reference_currency"> · {{ mandat.reference_currency }}</template>
                  <template v-if="mandat.comment"> · {{ mandat.comment }}</template>
                </div>
              </div>
              <div class="flex items-center gap-1">
                <button class="btn-ghost btn-sm" @click="scopeKey = `mandate:${mandat.id}`">
                  Analyser
                </button>
                <button class="btn-ghost btn-sm" @click="archiverMandat(mandat)">Archiver</button>
              </div>
            </li>
          </ul>
        </div>

        <!-- ── Contacts ──────────────────────────────────────── -->
        <div v-else-if="ongletActif === 'contacts'" class="flex flex-col gap-5">
          <div class="card flex flex-col gap-3">
            <div class="flex items-center justify-between gap-3">
              <div class="card-title mb-0">Contacts en poste</div>
              <button class="btn-secondary btn-sm" @click="modaleContact = true">
                + Ajouter un contact
              </button>
            </div>
            <EmptyState v-if="!contactsActuels.length" icon="👤"
                        title="Aucun contact en poste"
                        hint="Ajoutez la première personne que vous connaissez dans cette société." />
            <ul v-else class="flex flex-col divide-y" style="border-color: var(--border)">
              <li v-for="contact in contactsActuels" :key="contact.affiliation_id"
                  class="py-3 flex items-center justify-between gap-3 cursor-pointer"
                  @click="$router.push(`/clients/contacts/${contact.person_id}`)">
                <div class="min-w-0">
                  <div class="text-sm font-semibold">
                    {{ contact.first_name }} {{ contact.last_name }}
                  </div>
                  <div class="text-xs" style="color: var(--muted)">
                    {{ posteEtRole(contact) }}
                    · depuis {{ formaterDate(contact.start_date) }}
                  </div>
                </div>
                <span class="text-xs shrink-0" style="color: var(--subtle)">Ouvrir →</span>
              </li>
            </ul>
          </div>

          <div v-if="anciensContacts.length" class="card flex flex-col gap-3">
            <div class="card-title mb-0">Anciens contacts</div>
            <p class="text-xs" style="color: var(--muted)">
              Ces personnes ont quitté la société. Ce qu'elles y ont fait reste
              rattaché ici.
            </p>
            <ul class="flex flex-col divide-y" style="border-color: var(--border)">
              <li v-for="contact in anciensContacts" :key="contact.affiliation_id"
                  class="py-2.5 cursor-pointer"
                  @click="$router.push(`/clients/contacts/${contact.person_id}`)">
                <div class="text-sm" style="color: var(--muted)">
                  {{ contact.first_name }} {{ contact.last_name }}
                </div>
                <div class="text-xs" style="color: var(--subtle)">
                  {{ contact.job_title || '—' }}
                  · {{ formaterDate(contact.start_date) }}
                  → {{ formaterDate(contact.end_date) }}
                </div>
              </li>
            </ul>
          </div>
        </div>

        <!-- ── Opportunités ──────────────────────────────────── -->
        <div v-else-if="ongletActif === 'opportunites'" class="card flex flex-col gap-3">
          <div class="flex items-center justify-between gap-3">
            <div class="card-title mb-0">Opportunités ouvertes</div>
            <button class="btn-secondary btn-sm" @click="modaleOpportunite = true">
              + Nouvelle opportunité
            </button>
          </div>
          <EmptyState v-if="!opportunites.length" icon="🎯"
                      title="Aucune opportunité ouverte"
                      hint="Une opportunité porte un besoin client. C'est elle qui devient ensuite un appel d'offres, puis un trade." />
          <ul v-else class="flex flex-col divide-y" style="border-color: var(--border)">
            <li v-for="opp in opportunites" :key="opp.id"
                class="py-2.5 flex items-center justify-between gap-3 cursor-pointer"
                @click="$router.push(`/clients/opportunites/${opp.id}`)">
              <div class="min-w-0">
                <div class="text-sm font-semibold truncate">
                  {{ opp.title || opp.reference }}
                </div>
                <div class="text-xs" style="color: var(--muted)">
                  {{ opp.primary_contact?.name || 'Sans contact' }}
                  <span v-if="opp.amount">
                    · {{ montant(opp.amount) }} {{ opp.currency }}
                  </span>
                </div>
              </div>
              <span class="badge badge-accent shrink-0">
                {{ libelleStatutOpportunite(opp.status) }}
              </span>
            </li>
          </ul>
        </div>

        <!-- ── Appels d'offres ───────────────────────────────── -->
        <div v-else-if="ongletActif === 'rfq'" class="card flex flex-col gap-3">
          <div class="card-title mb-0">Appels d'offres</div>
          <p class="card-hint">
            Remontés par la chaîne RFQ → Opportunité → Client. Une consultation
            lancée hors de tout dossier n'apparaît pas ici : elle ne concerne
            personne en particulier.
          </p>
          <EmptyState v-if="!rfqs.length" icon="📨"
                      title="Aucun appel d'offres"
                      hint="Une consultation se lance depuis la fiche d'une opportunité." />
          <ul v-else class="flex flex-col divide-y" style="border-color: var(--border)">
            <li v-for="rfq in rfqs" :key="rfq.id"
                class="py-2.5 flex items-center justify-between gap-3">
              <div class="min-w-0">
                <div class="text-sm font-semibold truncate">{{ rfq.name }}</div>
                <div class="text-xs font-mono" style="color: var(--subtle)">
                  {{ rfq.reference }}
                  <span v-if="rfq.ao_date"> · {{ formaterDate(rfq.ao_date) }}</span>
                  <span v-if="rfq.model_price !== null">
                    · prix modèle {{ rfq.model_price.toFixed(2) }}
                  </span>
                </div>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <span class="badge badge-muted">{{ rfq.status }}</span>
                <RouterLink to="/rfq" class="btn-ghost btn-sm">Ouvrir →</RouterLink>
              </div>
            </li>
          </ul>
        </div>

        <!-- ── Trades ────────────────────────────────────────── -->
        <div v-else-if="ongletActif === 'trades'" class="card flex flex-col gap-3">
          <div class="flex items-center justify-between gap-3 flex-wrap">
            <div class="card-title mb-0">Transactions</div>
            <div v-if="intelligence?.behaviour?.n_imported" class="flex gap-1.5">
              <span class="badge badge-positive">
                {{ intelligence.behaviour.n_trades - intelligence.behaviour.n_imported }}
                bookées ici
              </span>
              <span class="badge badge-muted">
                {{ intelligence.behaviour.n_imported }} importées
              </span>
            </div>
          </div>
          <p class="card-hint">
            Les lignes importées ne sont pas des positions : elles alimentent
            l'analyse commerciale, jamais le book, le risque ni le MtM.
          </p>
          <EmptyState v-if="!transactions.length" icon="—"
                      title="Aucune transaction rattachée"
                      hint="Un import d'historique, ou un deal booké depuis une opportunité." />
          <div v-else class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-left" style="border-bottom: 1px solid var(--border)">
                  <th class="py-2 pr-3 font-semibold">Date</th>
                  <th class="py-2 pr-3 font-semibold">Périmètre</th>
                  <th class="py-2 pr-3 font-semibold">Cadre / instrument</th>
                  <th class="py-2 pr-3 font-semibold">Payoff</th>
                  <th class="py-2 pr-3 font-semibold">Émetteur</th>
                  <th class="py-2 pr-3 font-semibold">Sous-jacent</th>
                  <th class="py-2 pr-3 font-semibold">Maturité</th>
                  <th class="py-2 font-semibold text-right">Nominal</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(t, i) in transactions" :key="i"
                    style="border-bottom: 1px solid var(--border)">
                  <td class="py-2 pr-3 tabular-nums whitespace-nowrap">
                    {{ formaterDate(t.trade_date) }}
                    <span v-if="t.imported" class="badge badge-muted ml-1">imp.</span>
                  </td>
                  <td class="py-2 pr-3">{{ t.mandate_name || 'Non rattaché' }}</td>
                  <td class="py-2 pr-3">
                    {{ [t.transaction_format, t.instrument_family].filter(Boolean).join(' · ') || '—' }}
                    <div v-if="t.documentation_reference" class="text-xs"
                         style="color: var(--subtle)">{{ t.documentation_reference }}</div>
                  </td>
                  <td class="py-2 pr-3">
                    {{ t.payoff_family || t.product_type || '—' }}
                    <div v-if="t.payoff_description" class="text-xs"
                         style="color: var(--subtle)">{{ t.payoff_description }}</div>
                  </td>
                  <td class="py-2 pr-3" style="color: var(--muted)">{{ t.issuer || '—' }}</td>
                  <td class="py-2 pr-3" style="color: var(--muted)">
                    {{ t.underlyings.join(' / ') || '—' }}
                  </td>
                  <td class="py-2 pr-3 tabular-nums" style="color: var(--muted)">
                    {{ t.maturity_date ? formaterDate(t.maturity_date) : '—' }}
                    <div v-if="t.source_type === 'deal' && t.source_id" class="mt-0.5">
                      <RouterLink :to="{ path: '/pricer', query: { dealId: t.source_id } }"
                                  class="text-xs text-blue-400 hover:text-blue-300"
                                  @click.stop>
                        Événements Life Cycle →
                      </RouterLink>
                    </div>
                    <div v-else-if="t.imported" class="text-xs" style="color: var(--subtle)">
                      Historique importé
                    </div>
                  </td>
                  <td class="py-2 text-right tabular-nums font-semibold">
                    {{ t.notional ? montant(t.notional) + ' ' + (t.currency || '') : '—' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- ── Technique ────────────────────────── -->
        <div v-else-if="ongletActif === 'technique'">
          <TechnicalPanel v-if="intelligence?.technical" :tech="intelligence.technical" />
          <EmptyState v-else icon="—" title="Lecture technique indisponible"
                      hint="Les niveaux se lisent dans les deals bookés et les lignes importées ; aucune des deux sources n'a répondu." />
        </div>

        <!-- ── Interactions ──────────────────────────────────── -->
        <div v-else-if="ongletActif === 'interactions'" class="card flex flex-col gap-3">
          <div class="flex items-center justify-between gap-3">
            <div class="card-title mb-0">Échanges</div>
            <button class="btn-secondary btn-sm" @click="modaleInteraction = true">
              + Enregistrer
            </button>
          </div>
          <EmptyState v-if="!interactions.length" icon="🗒"
                      title="Aucune interaction"
                      hint="Notez un appel, une réunion ou une idée envoyée pour commencer à construire l'historique." />
          <ul v-else class="flex flex-col divide-y" style="border-color: var(--border)">
            <li v-for="item in interactions" :key="item.id" class="py-2.5">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="text-sm">{{ item.summary || '(sans résumé)' }}</div>
                  <div class="text-xs" style="color: var(--muted)">
                    {{ libelleTypeInteraction(item.interaction_type) }}
                    <span v-if="item.participants.length">
                      · {{ item.participants.map(p => p.name).join(', ') }}
                    </span>
                  </div>
                  <div v-if="item.next_action" class="text-xs mt-0.5"
                       style="color: var(--gold)">
                    À faire : {{ item.next_action }}
                    <span v-if="item.next_action_date">
                      ({{ formaterDate(item.next_action_date) }})
                    </span>
                  </div>
                </div>
                <span class="text-xs tabular-nums shrink-0" style="color: var(--subtle)">
                  {{ formaterDate(item.interaction_date) }}
                </span>
              </div>
            </li>
          </ul>
        </div>

        <!-- ── Contraintes ───────────────────────────────────── -->
        <div v-else-if="ongletActif === 'contraintes'" class="flex flex-col gap-5">
          <!-- Le panneau se décrit depuis le serveur : il ne connaît aucun
               champ à l'avance, ce qui est la seule manière que le contrôle
               affiché et la validation serveur ne divergent jamais. -->
          <ConstraintsPanel :client-id="client.id" :client="client"
                            :scope="scopeDescriptor" :contacts="store.contacts"
                            @saved="apresContraintes" />

          <div v-if="client.notes" class="card">
            <div class="label">Notes</div>
            <p class="text-sm whitespace-pre-line" style="color: var(--muted)">
              {{ client.notes }}
            </p>
          </div>
        </div>
      </template>
    </div>

    <ClientFormModal v-if="modaleEdition" :client="client"
                     @ferme="modaleEdition = false" @enregistre="modaleEdition = false" />
    <PersonFormModal v-if="modaleContact" :clients="[client]" :client-prefill="client.id"
                     @ferme="modaleContact = false" @enregistre="apresContact"
                     @rattacher="allerVersPersonne" />
    <InteractionFormModal v-if="modaleInteraction" :client="client"
                          :contacts="contactsActuels"
                          @ferme="modaleInteraction = false" @enregistre="apresInteraction" />
    <OpportunityFormModal v-if="modaleOpportunite" :clients="[client]"
                          :client-prefill="client.id"
                          @ferme="modaleOpportunite = false" @enregistre="apresOpportunite" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import {
  useClientsStore, libelleTypeClient, libelleStatutClient, libelleRole,
  libelleTypeInteraction, libelleStatutOpportunite, libelleRaisonPerte,
  libelleProvenance, TYPES_MANDAT, libelleTypeMandat,
} from '../stores/clients.js'
import { confirmer } from '../composables/useConfirm.js'
import AlertMessage from '../components/ui/AlertMessage.vue'
import BackLink from '../components/ui/BackLink.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import ClientFormModal from '../components/clients/ClientFormModal.vue'
import PersonFormModal from '../components/clients/PersonFormModal.vue'
import InteractionFormModal from '../components/clients/InteractionFormModal.vue'
import OpportunityFormModal from '../components/clients/OpportunityFormModal.vue'
import ClientCard from '../components/clients/ClientCard.vue'
import TechnicalPanel from '../components/clients/TechnicalPanel.vue'
import ConstraintsPanel from '../components/clients/ConstraintsPanel.vue'
import { formatDate, formatInt } from '../utils/format.js'

// Le registre. Ajouter un onglet = une entrée ici et un bloc dans le template.
const ONGLETS = [
  { cle: 'apercu', libelle: 'Aperçu' },
  { cle: 'contacts', libelle: 'Contacts' },
  { cle: 'opportunites', libelle: 'Opportunités' },
  { cle: 'rfq', libelle: "Appels d'offres" },
  { cle: 'trades', libelle: 'Trades' },
  { cle: 'technique', libelle: 'Technique' },
  { cle: 'interactions', libelle: 'Échanges' },
  { cle: 'contraintes', libelle: 'Préférences' },
]

// Échelle S&P/Fitch dans l'ordre de qualité — jamais triée alphabétiquement,
// ce qui placerait BBB avant A.
const ECHELLE_RATING = [
  'AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', 'A-', 'BBB+', 'BBB', 'BBB-',
  'BB+', 'BB', 'BB-', 'B+', 'B', 'B-', 'CCC+', 'CCC', 'CCC-', 'CC', 'C', 'D',
]

const route = useRoute()
const router = useRouter()
const store = useClientsStore()

// L'onglet vient de l'URL. Sans ça, le retour du navigateur sortait de la
// fiche au lieu de revenir à l'onglet précédent.
const ongletActif = computed(() => route.params.section || 'apercu')
const modaleEdition = ref(false)
const modaleContact = ref(false)
const modaleInteraction = ref(false)
const modaleOpportunite = ref(false)
const messageErreur = ref('')
const interactions = ref([])
const opportunites = ref([])
const intelligence = ref(null)
const scopeKey = ref('client')
const saisieMandat = ref(false)
const nouveauMandat = reactive({
  name: '', mandate_type: 'mandate', reference_currency: 'EUR', comment: '',
})

const client = computed(() => store.clientCourant)
const contactsActuels = computed(() => store.contacts.filter(c => c.is_current))
const anciensContacts = computed(() => store.contacts.filter(c => !c.is_current))
const rfqs = computed(() => intelligence.value?.rfqs || [])
const transactions = computed(() => intelligence.value?.transactions || [])
const mandatsActifs = computed(
  () => (client.value?.mandates || []).filter(mandat => mandat.status === 'active'))
const scopeParams = computed(() => {
  const [kind, rawId] = scopeKey.value.split(':')
  const id = Number(rawId)
  if (kind === 'mandate' && Number.isFinite(id)) return { mandate_id: id }
  if (kind === 'affiliation' && Number.isFinite(id)) return { affiliation_id: id }
  return {}
})
const scopeDescriptor = computed(() => {
  if (scopeParams.value.mandate_id) {
    const mandat = mandatsActifs.value.find(row => row.id === scopeParams.value.mandate_id)
    return { ...scopeParams.value, name: mandat?.name || 'Mandat' }
  }
  if (scopeParams.value.affiliation_id) {
    const contact = store.contacts.find(
      row => row.affiliation_id === scopeParams.value.affiliation_id)
    return {
      ...scopeParams.value,
      name: contact ? `${contact.first_name} ${contact.last_name}`.trim() : 'Contact',
    }
  }
  return { name: client.value?.name || 'Client' }
})
const lifecycleRoute = computed(() => {
  const query = {}
  if (client.value?.id) query.client_id = String(client.value.id)
  if (scopeParams.value.mandate_id) {
    query.mandate_id = String(scopeParams.value.mandate_id)
  }
  return { path: '/booking', query }
})

function compteur(cle) {
  const n = {
    contacts: contactsActuels.value.length,
    opportunites: opportunites.value.length,
    rfq: rfqs.value.length,
    trades: transactions.value.length,
    interactions: interactions.value.length,
  }[cle]
  // Zéro ne s'affiche pas : une pastille « 0 » est du bruit, l'état vide de
  // l'onglet dit déjà la même chose et en mieux.
  return n ? n : null
}

const badgeCadence = computed(() => {
  const cycle = intelligence.value?.cycle
  if (!cycle) return null
  if (cycle.confidence === 'insufficient_history') {
    return { texte: 'Cadence inconnue', classe: 'badge-muted' }
  }
  const noms = {
    hebdomadaire: 'hebdomadaire', mensuelle: 'mensuelle',
    trimestrielle: 'trimestrielle', semestrielle: 'semestrielle',
    annuelle: 'annuelle', pluriannuelle: 'pluriannuelle',
    irreguliere: 'irrégulière',
  }
  const classe = { high: 'badge-positive', medium: 'badge-gold', low: 'badge-muted' }
  return { texte: `Cadence ${noms[cycle.cadence] || '—'}`,
           classe: classe[cycle.confidence] || 'badge-muted' }
})

/**
 * L'action du jour.
 *
 * Sur un client à cadence connue, elle vient du moteur — la fenêtre de contact.
 * Sur un client sans cadence, aucun modèle ne peut la produire : c'est alors la
 * relance notée à la main qui reste actionnable, et l'écran doit le dire plutôt
 * que d'afficher une fenêtre inventée.
 */
const action = computed(() => {
  const aujourdhui = new Date().toISOString().slice(0, 10)
  const fenetre = intelligence.value?.contact_window
  const cycle = intelligence.value?.cycle

  if (fenetre?.start && fenetre.start <= aujourdhui && aujourdhui <= fenetre.end
      && cycle?.confidence !== 'low') {
    return {
      ton: 'action-accent', icone: '📞', badge: 'Priorité du jour',
      badgeClasse: 'badge-accent',
      titre: `Fenêtre de contact ouverte — jusqu'au ${formaterDate(fenetre.end)}.`,
      pourquoi: (fenetre.explanation || []).join(' '),
    }
  }

  const relance = interactions.value
    .filter(i => i.next_action && i.next_action_date
                 && i.next_action_date <= aujourdhui)
    .sort((a, b) => a.next_action_date.localeCompare(b.next_action_date))[0]
  if (relance) {
    const retard = Math.round(
      (new Date(aujourdhui) - new Date(relance.next_action_date)) / 86400000)
    return {
      ton: 'action-gold', icone: '📌', badge: 'Saisie manuelle',
      badgeClasse: 'badge-gold',
      titre: `Relance due${retard ? ` depuis ${retard} jour(s)` : " aujourd'hui"} — ${relance.next_action}`,
      pourquoi: cycle && cycle.confidence === 'insufficient_history'
        ? "Aucune fenêtre de contact n'est calculée pour ce client : son "
          + 'historique ne permet pas encore d\'établir une cadence.'
        : 'Notée à la clôture d\'un échange.',
    }
  }
  return null
})

/**
 * Poste et rôle, sans redite.
 *
 * `job_title` est libre (« Gérant »), `commercial_role` vient d'un vocabulaire
 * dont le libellé français est parfois le même mot. Les afficher tous deux
 * donnait « Gérant · Gérant », qui fait douter du reste de la fiche.
 */
function posteEtRole(contact) {
  const poste = (contact.job_title || '').trim()
  const role = libelleRole(contact.commercial_role)
  if (!poste) return role
  if (poste.toLowerCase() === role.toLowerCase()) return poste
  return `${poste} · ${role}`
}

function noms(couverture) {
  return (couverture || []).map(c => c.username).join(', ') || '—'
}
function classeStatut(statut) {
  if (statut === 'active') return 'badge-positive'
  if (statut === 'prospect') return 'badge-accent'
  if (statut === 'dormant' || statut === 'inactive') return 'badge-gold'
  return 'badge-muted'
}
// Delegue a utils/format.js : separateur de milliers normalise, date lue
// en calendrier local. Un formateur local re-introduirait l'espace fine
// insecable d'Intl, invisible a l'ecran.
const formaterDate = formatDate
const montant = formatInt

async function recharger() {
  await store.chargerClient(Number(route.params.id))
  interactions.value = await store.chargerInteractions({
    client_id: route.params.id, limit: 20 })
  await store.chargerOpportunites({ client_id: route.params.id, open_only: true })
  opportunites.value = [...store.opportunites]
  await rechargerIntelligence()
}

async function rechargerIntelligence() {
  try {
    intelligence.value = await store.lireIntelligenceClient(
      Number(route.params.id), null, scopeParams.value)
  } catch {
    // L'analyse enrichit la fiche, elle ne la conditionne pas : son échec ne
    // doit pas rendre les contacts et les contraintes inaccessibles.
    intelligence.value = null
  }
}

async function ajouterMandat() {
  messageErreur.value = ''
  try {
    await store.creerMandat(client.value.id, {
      ...nouveauMandat,
      reference_currency: nouveauMandat.reference_currency || null,
      comment: nouveauMandat.comment || null,
      data_origin: client.value.data_origin,
    })
    Object.assign(nouveauMandat, {
      name: '', mandate_type: 'mandate', reference_currency: 'EUR', comment: '',
    })
    saisieMandat.value = false
  } catch (e) { messageErreur.value = e.message }
}

async function archiverMandat(mandat) {
  messageErreur.value = ''
  try {
    await store.modifierMandat(client.value.id, mandat.id, { status: 'archived' })
  } catch (e) { messageErreur.value = e.message }
}

/** La politique vient de changer : l'espace négatif aussi. */
async function apresContraintes() {
  await store.chargerClient(client.value.id)
  await rechargerIntelligence()
}

async function archiver() {
  if (!await confirmer({
    titre: 'Archiver ce client ?',
    message: "Il sortira des listes de travail. Son historique reste consultable "
           + 'et il peut être réactivé à tout moment.',
    confirmer: 'Archiver' })) return
  try { await store.archiverClient(client.value.id) }
  catch (e) { messageErreur.value = e.message }
}

async function reactiver() {
  try { await store.reactiverClient(client.value.id) }
  catch (e) { messageErreur.value = e.message }
}

async function supprimer() {
  if (!await confirmer({
    titre: 'Supprimer définitivement ?',
    message: "Cette suppression est irréversible. Elle n'est possible que si "
           + "aucun contact, interaction, opportunité ni trade n'y est rattaché.",
    confirmer: 'Supprimer', danger: true })) return
  try {
    await store.supprimerClient(client.value.id)
    router.push('/clients/liste')
  } catch (e) { messageErreur.value = e.message }
}

async function apresContact() { modaleContact.value = false; await recharger() }
async function apresInteraction() { modaleInteraction.value = false; await recharger() }
function apresOpportunite(creee) {
  modaleOpportunite.value = false
  router.push(`/clients/opportunites/${creee.id}`)
}
function allerVersPersonne(personId) {
  modaleContact.value = false
  router.push(`/clients/contacts/${personId}`)
}

onMounted(recharger)
watch(() => route.params.id, async () => {
  scopeKey.value = 'client'
  await recharger()
})
watch(scopeKey, rechargerIntelligence)
</script>

<style scoped>
.action {
  border-radius: 10px; padding: .85rem 1.1rem;
  display: flex; align-items: center; gap: .9rem; flex-wrap: wrap;
}
.action-accent { background: var(--accent-light); border: 1px solid rgba(26,95,160,.3);
                 border-left: 4px solid var(--accent); }
.action-gold   { background: var(--gold-light); border: 1px solid rgba(184,134,11,.35);
                 border-left: 4px solid var(--gold); }
.action-icone { font-size: 1.1rem; line-height: 1; }
.scope-bar {
  display: flex; align-items: end; gap: .9rem; flex-wrap: wrap;
  padding: .75rem 1rem; border: 1px solid var(--border);
  border-radius: 10px; background: var(--surface);
}
.scope-select { min-width: 17rem; }

.echo {
  font-family: 'JetBrains Mono', monospace;
  font-size: .72rem; color: var(--muted);
  margin: .2rem 0 0; min-height: 1rem;
  font-variant-numeric: tabular-nums;
}
.pastille {
  margin-left: .35rem; padding: 0 .35rem; border-radius: 999px;
  font-size: .68rem; font-weight: 700;
  background: var(--surface2); color: var(--muted);
}
.tab-btn.active .echo {
  font-family: 'JetBrains Mono', monospace;
  font-size: .72rem; color: var(--muted);
  margin: .2rem 0 0; min-height: 1rem;
  font-variant-numeric: tabular-nums;
}
.pastille { background: var(--accent-light); color: var(--accent); }
</style>
