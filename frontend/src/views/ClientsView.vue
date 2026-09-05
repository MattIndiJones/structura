<!--
  Clients — le hub du module commercial.

  Sept SOUS-MODULES, et chacun est une ROUTE : `/clients/apercu`,
  `/clients/contacts`… La première version en faisait des onglets locaux, ce qui
  paraissait plus simple mais cassait trois choses à la fois — le retour du
  navigateur sortait du module, une section ne se partageait pas par son lien,
  et revenir d'une fiche retombait toujours sur le premier onglet.

  **Il n'y a plus de barre d'onglets.** Le choix se fait dans la grille du menu
  (l'accueil, catégorie Clients) : sept sections empilées dans une barre se
  lisent mal et n'annoncent rien de ce qu'elles contiennent, là où une carte
  porte son titre, son sous-titre et une phrase. Passer de Contacts à
  Opportunités repasse donc par le menu — c'est voulu.

  Ajouter un sous-module : une entrée dans `SOUS_MODULES`, une carte dans la
  grille du menu, et son segment dans le motif du routeur.
-->
<template>
  <div class="min-h-screen" style="background: var(--bg)">
    <div class="max-w-7xl mx-auto px-6 py-8 flex flex-col gap-6">

      <!-- En-tête : la page porte le nom du SOUS-MODULE, pas celui du module.
           On n'est pas « sur Clients, onglet Contacts » ; on est sur Contacts,
           et le retour ramène au menu du module. -->
      <div class="flex flex-col gap-1">
        <!-- Pas de libellé sur mesure : ce bouton revient EN ARRIÈRE, la
             destination du fallback ne s'applique que sans historique. Lui
             faire annoncer « Menu Clients » serait une promesse qu'il ne tient
             pas quand on arrive depuis une fiche. -->
        <BackLink class="self-start" :fallback="{ path: '/', query: { category: 'clients' } }" />
        <h1 class="font-display text-2xl font-black tracking-tight">
          {{ sousModule.libelle }}
        </h1>
        <p class="text-sm" style="color: var(--muted)">{{ sousModule.sous_titre }}</p>
      </div>

      <AlertMessage v-if="store.erreur" kind="error" dismissible
                    @dismiss="store.reinitialiserErreur()">
        {{ store.erreur }}
      </AlertMessage>

      <!-- ── Aperçu ────────────────────────────────────────────────── -->
      <div v-if="section === 'apercu'" class="flex flex-col gap-5">
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div v-for="tuile in tuiles" :key="tuile.libelle" class="stat-box">
            <div class="text-xs font-semibold uppercase tracking-wider"
                 style="color: var(--muted)">{{ tuile.libelle }}</div>
            <div class="text-2xl font-bold mt-1 tabular-nums">{{ tuile.valeur }}</div>
            <div class="text-xs mt-0.5" style="color: var(--subtle)">{{ tuile.detail }}</div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <!-- Relances dues -->
          <div class="card flex flex-col gap-3">
            <div class="card-title mb-0">Relances dues</div>
            <p class="text-xs" style="color: var(--muted)">
              Les prochaines actions dont la date est arrivée ou passée.
            </p>
            <EmptyState v-if="!relancesDues.length" icon="✓"
                        title="Aucune relance en retard"
                        hint="Les prochaines actions saisies sur une interaction apparaîtront ici le jour venu." />
            <ul v-else class="flex flex-col divide-y" style="border-color: var(--border)">
              <li v-for="item in relancesDues" :key="item.id"
                  class="py-2.5 flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="text-sm font-semibold truncate">{{ item.next_action }}</div>
                  <div class="text-xs" style="color: var(--muted)">
                    {{ item.client_name }} · {{ formaterDate(item.next_action_date) }}
                  </div>
                </div>
                <span class="badge" :class="item.enRetard ? 'badge-negative' : 'badge-gold'">
                  {{ item.enRetard ? 'En retard' : "Aujourd'hui" }}
                </span>
              </li>
            </ul>
          </div>

          <!-- Activité récente -->
          <div class="card flex flex-col gap-3">
            <div class="card-title mb-0">Activité récente</div>
            <p class="text-xs" style="color: var(--muted)">
              Les dernières interactions enregistrées, toutes sociétés confondues.
            </p>
            <EmptyState v-if="!store.interactions.length" icon="🗒"
                        title="Aucune interaction enregistrée"
                        hint="Un appel, une réunion ou une idée envoyée se note depuis la fiche d'un client." />
            <ul v-else class="flex flex-col divide-y" style="border-color: var(--border)">
              <li v-for="item in store.interactions.slice(0, 8)" :key="item.id"
                  class="py-2.5 flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="text-sm truncate">{{ item.summary || '(sans résumé)' }}</div>
                  <div class="text-xs" style="color: var(--muted)">
                    {{ item.client_name }} · {{ libelleTypeInteraction(item.interaction_type) }}
                  </div>
                </div>
                <span class="text-xs tabular-nums shrink-0" style="color: var(--subtle)">
                  {{ formaterDate(item.interaction_date) }}
                </span>
              </li>
            </ul>
          </div>
        </div>

        <!-- Clients dormants -->
        <div class="card flex flex-col gap-3">
          <div class="card-title mb-0">Clients dormants</div>
          <p class="text-xs" style="color: var(--muted)">
            Marqués « dormant » ou « inactif ». Le repérage automatique par
            rupture de cadence arrive avec le moteur de cycles.
          </p>
          <EmptyState v-if="!dormants.length" icon="🌙" title="Aucun client dormant" />
          <div v-else class="flex flex-wrap gap-2">
            <button v-for="client in dormants" :key="client.id"
                    class="badge badge-muted hover:opacity-80"
                    @click="ouvrirClient(client.id)">
              {{ client.name }}
            </button>
          </div>
        </div>
      </div>

      <!-- ── Clients ───────────────────────────────────────────────── -->
      <div v-else-if="section === 'liste'" class="flex flex-col gap-4">
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <DataFilterBar class="flex-1" :fields="champsClients"
                         :state="filtreClients.state"
                         :field-options="filtreClients.fieldOptions.value"
                         :has-active-filters="filtreClients.hasActiveFilters.value"
                         :sorts="trisClients" :sort-by="filtreClients.sortBy.value"
                         :sort-dir="filtreClients.sortDir.value"
                         :count="clientsAffiches.length" :total="store.clients.length"
                         noun="client(s)"
                         @update:sort-by="filtreClients.sortBy.value = $event"
                         @toggle-dir="filtreClients.toggleSortDir()"
                         @reset="filtreClients.reset()" />
          <button class="btn-primary" @click="ouvrirCreationClient">
            + Nouveau client
          </button>
        </div>

        <LoadingSpinner v-if="store.chargement" />
        <EmptyState v-else-if="!clientsAffiches.length"
                    icon="🏛" title="Aucun client"
                    hint="Créez une première société pour commencer à suivre vos contacts et vos opportunités.">
          <button class="btn-primary" @click="ouvrirCreationClient">
            + Nouveau client
          </button>
        </EmptyState>

        <div v-else class="card p-0 overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left" style="border-bottom: 1px solid var(--border)">
                <th class="px-4 py-3 font-semibold">Nom</th>
                <th class="px-4 py-3 font-semibold">Type</th>
                <th class="px-4 py-3 font-semibold">Pays</th>
                <th class="px-4 py-3 font-semibold">Statut</th>
                <th class="px-4 py-3 font-semibold">Couverture</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="client in clientsAffiches" :key="client.id"
                  class="cursor-pointer transition-colors hover:bg-[var(--surface2)]"
                  style="border-bottom: 1px solid var(--border)"
                  @click="ouvrirClient(client.id)">
                <td class="px-4 py-3 font-semibold">{{ client.name }}</td>
                <td class="px-4 py-3" style="color: var(--muted)">
                  {{ libelleTypeClient(client.client_type) }}
                </td>
                <td class="px-4 py-3" style="color: var(--muted)">{{ client.country || '—' }}</td>
                <td class="px-4 py-3">
                  <span class="badge" :class="classeStatut(client.status)">
                    {{ libelleStatutClient(client.status) }}
                  </span>
                </td>
                <td class="px-4 py-3 text-xs" style="color: var(--muted)">
                  {{ (client.coverage_usernames || []).join(', ') || '—' }}
                </td>
                <td class="px-4 py-3 text-right">
                  <span class="text-xs" style="color: var(--subtle)">Ouvrir →</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── Import ────────────────────────────────────────────────── -->
      <div v-else-if="section === 'import'" class="flex flex-col gap-4">
        <p class="text-sm max-w-3xl" style="color: var(--muted)">
          Verser un historique commercial existant — sociétés, personnes,
          parcours professionnels et transactions passées. C'est ce qui permet au
          moteur de cadence de dire quelque chose dès le premier jour, plutôt que
          d'attendre des mois de trades bookés ici.
        </p>
        <ImportPanel @importe="apresImport" />
      </div>

      <!-- ── Analytics ─────────────────────────────────────────────── -->
      <div v-else-if="section === 'analytics'" class="flex flex-col gap-5">
        <LoadingSpinner v-if="!analytics" />
        <template v-else>
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="stat-box">
              <div class="text-xs" style="color: var(--muted)">Clients actifs</div>
              <div class="text-2xl font-bold tabular-nums">
                {{ analytics.clients.active }}
              </div>
              <div class="text-xs" style="color: var(--subtle)">
                sur {{ analytics.clients.total }} · {{ analytics.clients.dormant }} dormants
              </div>
            </div>
            <div class="stat-box">
              <div class="text-xs" style="color: var(--muted)">Contacts en poste</div>
              <div class="text-2xl font-bold tabular-nums">
                {{ analytics.contacts.affiliated }}
              </div>
              <div class="text-xs" style="color: var(--subtle)">
                sur {{ analytics.contacts.total }} connus
              </div>
            </div>
            <div class="stat-box">
              <div class="text-xs" style="color: var(--muted)">Pipeline ouvert</div>
              <div class="text-2xl font-bold tabular-nums">
                {{ formaterMontant(analytics.opportunities.pipeline_amount) }}
              </div>
              <div class="text-xs" style="color: var(--subtle)">
                {{ analytics.opportunities.open }} dossier(s)
              </div>
            </div>
            <div class="stat-box">
              <div class="text-xs" style="color: var(--muted)">Taux de conversion</div>
              <div class="text-2xl font-bold tabular-nums">
                {{ analytics.opportunities.conversion_rate === null
                   ? '—'
                   : Math.round(analytics.opportunities.conversion_rate * 100) + ' %' }}
              </div>
              <div class="text-xs" style="color: var(--subtle)">
                {{ analytics.opportunities.conversion_rate === null
                   ? 'aucun dossier tranché'
                   : `sur ${analytics.opportunities.decided} dossier(s) tranché(s)` }}
              </div>
            </div>
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div class="card flex flex-col gap-3">
              <div class="card-title mb-0">Pourquoi on perd</div>
              <p class="text-xs" style="color: var(--muted)">
                Les motifs saisis à la clôture des dossiers perdus.
              </p>
              <EmptyState v-if="!analytics.lost_reasons.length" icon="—"
                          title="Aucun dossier perdu documenté" />
              <ul v-else class="flex flex-col gap-2">
                <li v-for="([motif, compte]) in analytics.lost_reasons" :key="motif"
                    class="flex items-center gap-3">
                  <span class="text-sm w-44 shrink-0">{{ libelleRaisonPerte(motif) }}</span>
                  <div class="flex-1 h-2 rounded-full overflow-hidden"
                       style="background: var(--surface2)">
                    <div class="h-full" style="background: var(--negative)"
                         :style="{ width: partDeMotif(compte) }"></div>
                  </div>
                  <span class="text-sm tabular-nums w-6 text-right">{{ compte }}</span>
                </li>
              </ul>
            </div>

            <div class="card flex flex-col gap-3">
              <div class="card-title mb-0">Délais observés</div>
              <p class="text-xs" style="color: var(--muted)">
                Médianes, pas moyennes : un dossier qui a traîné six mois ne doit
                pas déplacer la lecture de tous les autres.
              </p>
              <div class="flex flex-col gap-3">
                <div class="flex items-center justify-between">
                  <span class="text-sm" style="color: var(--muted)">
                    Ouverture du dossier → transaction
                  </span>
                  <span class="text-lg font-bold tabular-nums">
                    {{ analytics.timing.median_opportunity_to_trade_days === null
                       ? '—'
                       : Math.round(analytics.timing.median_opportunity_to_trade_days) + ' j' }}
                  </span>
                </div>
                <div class="flex items-center justify-between">
                  <span class="text-sm" style="color: var(--muted)">
                    Première discussion → transaction
                  </span>
                  <span class="text-lg font-bold tabular-nums">
                    {{ analytics.timing.median_discussion_lead_days === null
                       ? '—'
                       : Math.round(analytics.timing.median_discussion_lead_days) + ' j' }}
                  </span>
                </div>
              </div>
              <p v-if="analytics.timing.median_discussion_lead_days === null"
                 class="text-xs" style="color: var(--subtle)">
                Pas encore d'historique exploitable : le délai par défaut
                ({{ store.seuils.default_contact_lead_days }} jours) est utilisé
                pour les fenêtres de contact.
              </p>
            </div>
          </div>

          <div class="card flex flex-col gap-3">
            <div class="card-title mb-0">Ce qui se traite</div>
            <EmptyState v-if="!analytics.trades.by_product.length" icon="—"
                        title="Aucune transaction rattachée à un client"
                        hint="Les trades bookés depuis une opportunité alimenteront cette lecture." />
            <div v-else class="flex flex-wrap gap-2">
              <span v-for="([produit, compte]) in analytics.trades.by_product"
                    :key="produit" class="badge badge-muted">
                {{ produit }} · {{ compte }}
              </span>
            </div>
          </div>
        </template>
      </div>

      <!-- ── Cycles & Signaux ──────────────────────────────────────── -->
      <div v-else-if="section === 'signaux'" class="flex flex-col gap-5">
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <label class="flex items-center gap-2 text-sm cursor-pointer">
            <input v-model="mesDossiers" type="checkbox" />
            <span>Mes dossiers seulement</span>
          </label>
          <div class="text-xs" style="color: var(--subtle)">
            Sommeil au-delà de {{ store.seuils.opportunity_stale_days }} j ·
            événements produits à {{ store.seuils.lifecycle_event_horizon_days
                                      ?? store.seuils.maturity_horizon_days }} j ·
            contact par défaut {{ store.seuils.default_contact_lead_days }} j avant
          </div>
        </div>

        <EmptyState v-if="!store.signaux.length" icon="✓"
                    title="Rien à signaler"
                    hint="Les relances échues, les fenêtres de contact, les clients dormants et les prochains événements produits apparaîtront ici." />

        <div v-else class="flex flex-col gap-4">
          <div v-for="groupe in signauxGroupes" :key="groupe.kind"
               class="card flex flex-col gap-3">
            <div class="flex items-center gap-2">
              <div class="card-title mb-0">{{ groupe.titre }}</div>
              <span class="badge badge-muted">{{ groupe.items.length }}</span>
            </div>
            <p class="text-xs" style="color: var(--muted)">{{ groupe.aide }}</p>
            <ul class="flex flex-col divide-y" style="border-color: var(--border)">
              <li v-for="(signal, i) in groupe.items" :key="i"
                  class="py-2.5 flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="text-sm font-semibold">{{ signal.title }}</div>
                  <div class="text-xs" style="color: var(--muted)">
                    {{ signal.reason }}
                  </div>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                  <span class="badge" :class="classeSeverite(signal.severity)">
                    {{ libelleSeverite(signal.severity) }}
                  </span>
                  <RouterLink v-if="signal.deal_id"
                              :to="{ path: '/pricer', query: { dealId: signal.deal_id } }"
                              class="btn-ghost btn-sm">Life Cycle →</RouterLink>
                  <button v-if="signal.client_id" class="btn-ghost btn-sm"
                          @click="ouvrirClient(signal.client_id)">Client →</button>
                </div>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <!-- ── Opportunités ──────────────────────────────────────────── -->
      <div v-else-if="section === 'opportunites'" class="flex flex-col gap-4">
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <label class="flex items-center gap-2 text-sm cursor-pointer">
            <input v-model="ouvertesSeules" type="checkbox" />
            <span>Dossiers ouverts seulement</span>
          </label>
          <button class="btn-primary" @click="modaleOpportunite = true">
            + Nouvelle opportunité
          </button>
        </div>

        <LoadingSpinner v-if="store.chargement" />
        <EmptyState v-else-if="!store.opportunites.length"
                    icon="🎯" title="Aucune opportunité"
                    hint="Une opportunité porte un besoin client. C'est elle qui devient ensuite un appel d'offres, puis un trade.">
          <button class="btn-primary" @click="modaleOpportunite = true">
            + Nouvelle opportunité
          </button>
        </EmptyState>

        <div v-else class="card p-0 overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left" style="border-bottom: 1px solid var(--border)">
                <th class="px-4 py-3 font-semibold">Référence</th>
                <th class="px-4 py-3 font-semibold">Intitulé</th>
                <th class="px-4 py-3 font-semibold">Client</th>
                <th class="px-4 py-3 font-semibold">Contact</th>
                <th class="px-4 py-3 font-semibold text-right">Montant</th>
                <th class="px-4 py-3 font-semibold">Statut</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="opp in store.opportunites" :key="opp.id"
                  class="cursor-pointer transition-colors hover:bg-[var(--surface2)]"
                  style="border-bottom: 1px solid var(--border)"
                  @click="$router.push(`/clients/opportunites/${opp.id}`)">
                <td class="px-4 py-3 font-mono text-xs">{{ opp.reference }}</td>
                <td class="px-4 py-3 font-semibold">{{ opp.title || '—' }}</td>
                <td class="px-4 py-3" style="color: var(--muted)">{{ opp.client_name }}</td>
                <td class="px-4 py-3" style="color: var(--muted)">
                  {{ opp.primary_contact?.name || '—' }}
                </td>
                <td class="px-4 py-3 text-right tabular-nums">
                  {{ opp.amount ? formaterMontant(opp.amount) + ' ' + opp.currency : '—' }}
                </td>
                <td class="px-4 py-3">
                  <span class="badge" :class="classeStatutOpp(opp.status)">
                    {{ libelleStatutOpportunite(opp.status) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ── Contacts ──────────────────────────────────────────────── -->
      <div v-else class="flex flex-col gap-4">
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <DataFilterBar class="flex-1" :fields="champsContacts"
                         :state="filtreContacts.state"
                         :field-options="filtreContacts.fieldOptions.value"
                         :has-active-filters="filtreContacts.hasActiveFilters.value"
                         :sorts="trisContacts" :sort-by="filtreContacts.sortBy.value"
                         :sort-dir="filtreContacts.sortDir.value"
                         :count="contactsAffiches.length" :total="store.personnes.length"
                         noun="contact(s)"
                         @update:sort-by="filtreContacts.sortBy.value = $event"
                         @toggle-dir="filtreContacts.toggleSortDir()"
                         @reset="filtreContacts.reset()" />
          <button class="btn-primary" @click="ouvrirCreationPersonne">
            + Nouveau contact
          </button>
        </div>

        <LoadingSpinner v-if="store.chargement" />
        <EmptyState v-else-if="!contactsAffiches.length"
                    icon="👤" title="Aucun contact"
                    hint="Une personne existe indépendamment de son employeur : elle garde son historique quand elle change de société.">
          <button class="btn-primary" @click="ouvrirCreationPersonne">
            + Nouveau contact
          </button>
        </EmptyState>

        <div v-else class="card p-0 overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left" style="border-bottom: 1px solid var(--border)">
                <th class="px-4 py-3 font-semibold">Nom</th>
                <th class="px-4 py-3 font-semibold">Société actuelle</th>
                <th class="px-4 py-3 font-semibold">Fonction</th>
                <th class="px-4 py-3 font-semibold">Rôle</th>
                <th class="px-4 py-3 font-semibold">E-mail</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="personne in contactsAffiches" :key="personne.id"
                  class="cursor-pointer transition-colors hover:bg-[var(--surface2)]"
                  style="border-bottom: 1px solid var(--border)"
                  @click="ouvrirPersonne(personne.id)">
                <td class="px-4 py-3 font-semibold">
                  {{ personne.first_name }} {{ personne.last_name }}
                  <span v-if="!personne.is_active" class="badge badge-muted ml-2">Inactif</span>
                </td>
                <td class="px-4 py-3">
                  <span v-if="personne.current_affiliation">
                    {{ personne.current_affiliation.client_name }}
                  </span>
                  <span v-else class="text-xs" style="color: var(--subtle)">
                    Sans affiliation
                  </span>
                </td>
                <td class="px-4 py-3" style="color: var(--muted)">
                  {{ personne.current_affiliation?.job_title || '—' }}
                </td>
                <td class="px-4 py-3" style="color: var(--muted)">
                  {{ personne.current_affiliation
                     ? libelleRole(personne.current_affiliation.commercial_role) : '—' }}
                </td>
                <td class="px-4 py-3 text-xs" style="color: var(--muted)">
                  {{ personne.email || '—' }}
                </td>
                <td class="px-4 py-3 text-right">
                  <span class="text-xs" style="color: var(--subtle)">Ouvrir →</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

    </div>

    <ClientFormModal v-if="modaleClient" :client="null"
                     @ferme="modaleClient = false"
                     @enregistre="apresCreationClient" />
    <PersonFormModal v-if="modalePersonne" :clients="store.clientsActifs"
                     :client-prefill="null"
                     @ferme="modalePersonne = false"
                     @enregistre="apresCreationPersonne" />
    <OpportunityFormModal v-if="modaleOpportunite" :clients="store.clientsActifs"
                          @ferme="modaleOpportunite = false"
                          @enregistre="apresCreationOpportunite" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute, RouterLink } from 'vue-router'
import {
  useClientsStore, STATUTS_CLOS, libelleTypeClient, libelleStatutClient,
  libelleRole, libelleTypeInteraction, libelleStatutOpportunite,
  libelleRaisonPerte,
} from '../stores/clients.js'
import { useDataFilter } from '../composables/useDataFilter.js'
import AlertMessage from '../components/ui/AlertMessage.vue'
import BackLink from '../components/ui/BackLink.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import LoadingSpinner from '../components/ui/LoadingSpinner.vue'
import DataFilterBar from '../components/ui/DataFilterBar.vue'
import ClientFormModal from '../components/clients/ClientFormModal.vue'
import PersonFormModal from '../components/clients/PersonFormModal.vue'
import OpportunityFormModal from '../components/clients/OpportunityFormModal.vue'
import ImportPanel from '../components/clients/ImportPanel.vue'
import { formatDate, formatInt } from '../utils/format.js'

// Les clés sont les segments d'URL : ajouter une section, c'est une entrée ici
// et un motif dans le routeur. « liste » plutôt que « clients » pour ne pas
// écrire /clients/clients.
// Le registre des sous-modules. Il ne sert plus à dessiner une barre d'onglets
// — c'est la grille du menu qui les propose — mais à nommer la page en cours.
// Le libellé et le sous-titre sont les MÊMES que sur la carte du menu :
// arriver sur une page dont le titre ne reprend pas celui de la carte cliquée
// donne l'impression de s'être trompé d'endroit.
const SOUS_MODULES = [
  { cle: 'apercu', libelle: 'Vue d’ensemble',
    sous_titre: 'Ce qui demande une action aujourd’hui, tous clients confondus.' },
  { cle: 'liste', libelle: 'Clients',
    sous_titre: 'Les sociétés que vous couvrez, leur statut et leur politique déclarée.' },
  { cle: 'contacts', libelle: 'Contacts',
    sous_titre: 'Les personnes, leur poste actuel et leur parcours d’une maison à l’autre.' },
  { cle: 'opportunites', libelle: 'Opportunités',
    sous_titre: 'Les affaires en cours, celles gagnées, et le motif de celles perdues.' },
  { cle: 'signaux', libelle: 'Cycles & Signaux',
    sous_titre: 'La cadence observée de chaque client et la fenêtre où le rappeler.' },
  { cle: 'analytics', libelle: 'Analytics',
    sous_titre: 'Le déclaré et l’observé superposés, dimension par dimension.' },
  { cle: 'import', libelle: 'Import d’historique',
    sous_titre: 'Verser un historique client depuis un fichier Excel ou JSON.' },
]

// Les six familles de signaux, avec ce qu'elles veulent dire. Le libellé ne
// suffit pas : « en sommeil » n'est actionnable que si on sait depuis quand.
const FAMILLES_SIGNAUX = [
  { kind: 'follow_up_due', titre: 'Relances échues',
    aide: 'Une action notée sur un échange, dont la date est arrivée.' },
  { kind: 'contact_soon', titre: 'Fenêtre de contact ouverte',
    aide: "C'est le moment d'appeler pour être dans le cycle habituel de ce client." },
  { kind: 'prepare_idea', titre: 'Idées à préparer',
    aide: 'La fenêtre de contact approche : il reste le temps de construire une proposition.' },
  { kind: 'dormant', titre: 'Clients dormants',
    aide: 'Anormalement silencieux par rapport à leur propre cadence — jamais un seuil absolu.' },
  { kind: 'upcoming_lifecycle_event', titre: 'Événements produits proches',
    aide: 'Prochaine constatation du Life Cycle. Coupon et rappel restent conditionnels au fixing et au script.' },
  { kind: 'opportunity_stale', titre: 'Dossiers en sommeil',
    aide: 'Ouverts, mais sans activité depuis un moment.' },
]

const router = useRouter()
const store = useClientsStore()
// La section vient de l'URL — pas d'un état local. C'est ce qui fait
// fonctionner le retour du navigateur sans une ligne de code de plus.
const route = useRoute()
const section = computed(() => route.params.section || 'apercu')

// La page se nomme d'après la carte qui y mène. Un repli est nécessaire : un
// segment inconnu dans l'URL ne doit pas produire un titre vide.
const sousModule = computed(() =>
  SOUS_MODULES.find(m => m.cle === section.value)
  || { libelle: 'Clients', sous_titre: 'Section inconnue.' })
const modaleClient = ref(false)
const modalePersonne = ref(false)
const modaleOpportunite = ref(false)
const ouvertesSeules = ref(true)
const mesDossiers = ref(true)
const analytics = ref(null)

// Part relative d'un motif de perte, pour la barre. Rapportée au motif le plus
// fréquent et non au total : c'est la comparaison entre motifs qui intéresse,
// pas leur poids dans un ensemble dont on connaît déjà le compte.
function partDeMotif(compte) {
  const maximum = Math.max(...(analytics.value?.lost_reasons || [[null, 1]])
    .map(([, n]) => n))
  return `${Math.round((compte / maximum) * 100)}%`
}

// Groupés par famille, dans l'ordre d'urgence des familles — et les familles
// vides ne s'affichent pas du tout : un bloc « 0 » est du bruit.
const signauxGroupes = computed(() => FAMILLES_SIGNAUX
  .map(famille => ({
    ...famille,
    items: store.signaux.filter(s => s.kind === famille.kind),
  }))
  .filter(groupe => groupe.items.length))

function classeSeverite(severite) {
  return { urgent: 'badge-negative', warning: 'badge-gold',
           info: 'badge-accent' }[severite] || 'badge-muted'
}

function libelleSeverite(severite) {
  return { urgent: 'Urgent', warning: 'À suivre', info: 'Info' }[severite] || severite
}

// Les libellés passent dans les accesseurs plutôt que les codes : le filtre
// doit proposer « Société de gestion », pas « asset_manager ».
const champsClients = [
  { key: 'name', label: 'Nom', kind: 'text' },
  { key: 'client_type', label: 'Type', kind: 'select',
    get: c => libelleTypeClient(c.client_type) },
  { key: 'status', label: 'Statut', kind: 'select',
    get: c => libelleStatutClient(c.status) },
  { key: 'country', label: 'Pays', kind: 'select' },
]
const trisClients = [
  { key: 'name', label: 'Nom' },
  { key: 'status', label: 'Statut', get: c => libelleStatutClient(c.status) },
]
const filtreClients = useDataFilter(
  computed(() => store.clients), champsClients, { defaultSort: 'name' })
const clientsAffiches = computed(() => filtreClients.filtered.value)

const champsContacts = [
  { key: 'name', label: 'Nom', kind: 'text',
    get: p => `${p.first_name} ${p.last_name}` },
  { key: 'client', label: 'Société', kind: 'select',
    get: p => p.current_affiliation?.client_name || 'Sans affiliation' },
  { key: 'role', label: 'Rôle', kind: 'select',
    get: p => p.current_affiliation
      ? libelleRole(p.current_affiliation.commercial_role) : '—' },
]
const trisContacts = [
  { key: 'name', label: 'Nom', get: p => `${p.last_name} ${p.first_name}` },
  { key: 'client', label: 'Société',
    get: p => p.current_affiliation?.client_name || '' },
]
const filtreContacts = useDataFilter(
  computed(() => store.personnes), champsContacts, { defaultSort: 'name' })
const contactsAffiches = computed(() => filtreContacts.filtered.value)

const tuiles = computed(() => [
  { libelle: 'Clients', valeur: store.clientsActifs.length,
    detail: `${store.clients.filter(c => c.status === 'active').length} actifs` },
  { libelle: 'Contacts', valeur: store.personnes.length,
    detail: `${store.personnes.filter(p => p.current_affiliation).length} en poste` },
  { libelle: 'Relances dues', valeur: relancesDues.value.length,
    detail: relancesDues.value.filter(r => r.enRetard).length + ' en retard' },
  { libelle: 'Interactions', valeur: store.interactions.length,
    detail: '30 derniers jours' },
])

// Une relance est due dès que sa date est atteinte. La comparaison se fait sur
// des chaînes ISO (AAAA-MM-JJ), qui s'ordonnent lexicographiquement — pas de
// Date() ni de fuseau, donc pas de décalage d'un jour selon l'heure locale.
const aujourdhui = new Date().toISOString().slice(0, 10)
const relancesDues = computed(() =>
  store.interactions
    .filter(i => i.next_action && i.next_action_date
                 && i.next_action_date <= aujourdhui)
    .map(i => ({ ...i, enRetard: i.next_action_date < aujourdhui }))
    .sort((a, b) => a.next_action_date.localeCompare(b.next_action_date)))

const dormants = computed(
  () => store.clients.filter(c => c.status === 'dormant' || c.status === 'inactive'))

function classeStatut(statut) {
  if (statut === 'active') return 'badge-positive'
  if (statut === 'prospect') return 'badge-accent'
  if (statut === 'dormant' || statut === 'inactive') return 'badge-gold'
  return 'badge-muted'
}

function classeStatutOpp(statut) {
  if (statut === 'won') return 'badge-positive'
  if (statut === 'lost') return 'badge-negative'
  if (STATUTS_CLOS.includes(statut)) return 'badge-muted'
  return 'badge-accent'
}

const formaterMontant = formatInt

// Delegue a utils/format.js : separateur de milliers normalise, date lue
// en calendrier local. Un formateur local re-introduirait l'espace fine
// insecable d'Intl, invisible a l'ecran.
const formaterDate = formatDate

function ouvrirClient(id) { router.push(`/clients/fiche/${id}`) }
function ouvrirPersonne(id) { router.push(`/clients/contacts/${id}`) }

function ouvrirCreationClient() { modaleClient.value = true }
function ouvrirCreationPersonne() { modalePersonne.value = true }

async function apresCreationClient(cree) {
  modaleClient.value = false
  await store.chargerClients()
  router.push(`/clients/fiche/${cree.id}`)
}

async function apresCreationPersonne(creee) {
  modalePersonne.value = false
  await store.chargerPersonnes()
  router.push(`/clients/contacts/${creee.id}`)
}

// Un versement change le référentiel ET les analyses : les listes en mémoire
// ne décrivent plus la base. On recharge plutôt que de laisser un écran obsolète.
async function apresImport() {
  await store.chargerClients()
  await store.chargerPersonnes()
}

async function apresCreationOpportunite(creee) {
  modaleOpportunite.value = false
  router.push(`/clients/opportunites/${creee.id}`)
}

// Les listes se rechargent au changement de section plutôt qu'une fois pour
// toutes : revenir sur l'onglet après avoir modifié une fiche doit montrer
// l'état à jour, pas une copie prise à l'ouverture de l'écran.
watch(section, charger, { immediate: false })
onMounted(charger)

watch(ouvertesSeules, () => {
  if (section.value === 'opportunites') charger()
})
watch(mesDossiers, () => {
  if (section.value === 'signaux') charger()
})

async function charger() {
  if (section.value === 'liste' || section.value === 'apercu') {
    await store.chargerClients()
  }
  if (section.value === 'contacts' || section.value === 'apercu') {
    await store.chargerPersonnes()
  }
  if (section.value === 'opportunites' || section.value === 'apercu') {
    await store.chargerOpportunites(
      ouvertesSeules.value ? { open_only: true } : {})
  }
  if (section.value === 'signaux' || section.value === 'apercu') {
    try {
      await store.chargerSignaux({ mineOnly: mesDossiers.value })
    } catch {
      // Les signaux sont un enrichissement de l'écran, pas sa condition : leur
      // absence ne doit pas vider la liste des clients au-dessus.
    }
  }
  if (section.value === 'analytics') {
    try {
      analytics.value = await store.chargerAnalytics()
      await store.chargerSignaux({ mineOnly: mesDossiers.value })
    } catch (e) {
      analytics.value = null
    }
  }
  if (section.value === 'apercu') {
    await store.chargerInteractions({ limit: 50 })
    await store.chargerClients()
  }
}
</script>
