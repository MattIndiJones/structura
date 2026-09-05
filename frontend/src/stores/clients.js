import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiFetch } from '../utils/api.js'

// Épine dorsale du module commercial : clients, personnes, opportunités et
// interactions. Un seul store plutôt que quatre parce que ces écrans se
// consomment les uns les autres en permanence — la fiche client affiche ses
// contacts et ses opportunités, la fiche personne affiche ses interactions —
// et les répartir obligerait chaque vue à en importer trois.
//
// Rien n'est mis en cache agressivement : les listes se rechargent à
// l'ouverture. À l'échelle de quelques centaines de fiches, une requête coûte
// moins cher qu'un cache qui ment.

// Vocabulaires — repris tels quels de core/client_controls.py. Les libellés
// sont en français (règle du projet), les valeurs restent les codes anglais
// que l'API attend.
export const TYPES_CLIENT = [
  { value: 'private_bank', label: 'Banque privée' },
  { value: 'asset_manager', label: 'Société de gestion' },
  { value: 'family_office', label: 'Family office' },
  { value: 'insurance', label: 'Assureur' },
  { value: 'corporate', label: 'Entreprise' },
  { value: 'institutional', label: 'Investisseur institutionnel' },
  { value: 'distributor', label: 'Distributeur' },
  { value: 'bank', label: 'Banque' },
  { value: 'other', label: 'Autre' },
]

export const STATUTS_CLIENT = [
  { value: 'prospect', label: 'Prospect' },
  { value: 'active', label: 'Actif' },
  { value: 'dormant', label: 'Dormant' },
  { value: 'inactive', label: 'Inactif' },
  { value: 'archived', label: 'Archivé' },
]

export const ROLES_COMMERCIAUX = [
  { value: 'decision_maker', label: 'Décisionnaire' },
  { value: 'cio', label: 'CIO' },
  { value: 'portfolio_manager', label: 'Gérant' },
  { value: 'investment_advisor', label: 'Conseiller en investissement' },
  { value: 'influencer', label: 'Prescripteur' },
  { value: 'execution', label: 'Contact exécution' },
  { value: 'originator', label: 'Apporteur' },
  { value: 'other', label: 'Autre' },
]

export const TYPES_INTERACTION = [
  { value: 'call', label: 'Appel' },
  { value: 'meeting', label: 'Réunion' },
  { value: 'email', label: 'E-mail' },
  { value: 'idea_sent', label: 'Idée envoyée' },
  { value: 'client_feedback', label: 'Retour client' },
  { value: 'indicative_request', label: "Demande d'indicatif" },
  { value: 'follow_up', label: 'Relance' },
  { value: 'other', label: 'Autre' },
]

export const STATUTS_OPPORTUNITE = [
  { value: 'lead', label: 'Piste' },
  { value: 'need_identified', label: 'Besoin identifié' },
  { value: 'idea', label: 'Idée' },
  { value: 'client_interest', label: 'Intérêt client' },
  { value: 'structuring', label: 'Structuration' },
  { value: 'rfq', label: "Appel d'offres" },
  { value: 'negotiation', label: 'Négociation' },
  { value: 'partially_won', label: 'Partiellement gagnée' },
  { value: 'won', label: 'Gagnée' },
  { value: 'lost', label: 'Perdue' },
  { value: 'cancelled', label: 'Annulée' },
  { value: 'archived', label: 'Archivée' },
]

export const RAISONS_PERTE = [
  { value: 'coupon_too_low', label: 'Coupon trop faible' },
  { value: 'barrier_too_high', label: 'Barrière trop haute' },
  { value: 'maturity_too_long', label: 'Maturité trop longue' },
  { value: 'issuer_rejected', label: 'Émetteur refusé' },
  { value: 'underlying_rejected', label: 'Sous-jacent refusé' },
  { value: 'product_complexity', label: 'Complexité du produit' },
  { value: 'competitor', label: 'Concurrent' },
  { value: 'client_changed_view', label: 'Vue de marché changée' },
  { value: 'timing', label: 'Timing' },
  { value: 'internal_approval', label: 'Validation interne' },
  { value: 'no_liquidity', label: 'Pas de liquidité' },
  { value: 'client_did_nothing', label: "Le client n'a rien fait" },
  { value: 'other', label: 'Autre' },
]

export const PRIORITES = [
  { value: 'high', label: 'Haute' },
  { value: 'medium', label: 'Moyenne' },
  { value: 'low', label: 'Basse' },
]

export const PROVENANCES_DONNEES = [
  { value: 'demo', label: 'Fictif / démonstration' },
  { value: 'imported', label: 'Historique importé' },
  { value: 'native', label: 'Structura natif' },
]

export const TYPES_MANDAT = [
  { value: 'mandate', label: 'Mandat' },
  { value: 'fund', label: 'Fonds / compartiment' },
  { value: 'account', label: 'Compte' },
  { value: 'desk', label: 'Desk / équipe' },
  { value: 'other', label: 'Autre périmètre' },
]

export const FORMATS_TRANSACTION = ['EMTN', 'BMTN', 'OTC']
export const FAMILLES_INSTRUMENT = ['Note', 'Certificat', 'Swap', 'Option', 'Dépôt structuré']
export const FAMILLES_PAYOFF = [
  'Autocall', 'Phoenix', 'Reverse Convertible', 'Participation',
  'Capital protégé', 'Coupon conditionnel', 'Swap', 'Autre',
]

export const ROLES_PARTICIPANT = [
  { value: 'originator', label: 'Apporteur' },
  { value: 'decision_maker', label: 'Décisionnaire' },
  { value: 'influencer', label: 'Prescripteur' },
  { value: 'advisor', label: 'Conseiller' },
  { value: 'execution', label: 'Exécution' },
  { value: 'other', label: 'Autre' },
]

function libelle(liste, valeur) {
  return liste.find(o => o.value === valeur)?.label || valeur || '—'
}
export const libelleTypeClient = v => libelle(TYPES_CLIENT, v)
export const libelleStatutClient = v => libelle(STATUTS_CLIENT, v)
export const libelleRole = v => libelle(ROLES_COMMERCIAUX, v)
export const libelleTypeInteraction = v => libelle(TYPES_INTERACTION, v)
export const libelleStatutOpportunite = v => libelle(STATUTS_OPPORTUNITE, v)
export const libelleRaisonPerte = v => libelle(RAISONS_PERTE, v)
export const libellePriorite = v => libelle(PRIORITES, v)
export const libelleProvenance = v => libelle(PROVENANCES_DONNEES, v)
export const libelleTypeMandat = v => libelle(TYPES_MANDAT, v)

// Statuts au-delà desquels un dossier ne bouge plus — même liste que
// OPPORTUNITY_TERMINAL côté serveur.
export const STATUTS_CLOS = ['won', 'lost', 'cancelled', 'archived']

/**
 * Remonte le message métier d'une réponse en erreur.
 *
 * L'API renvoie soit `{detail: "phrase"}`, soit `{detail: {code, message, …}}`
 * quand le refus porte de quoi agir (doublon détecté, historique bloquant,
 * conflit d'écriture). Cette fonction rend toujours un objet exploitable, pour
 * qu'aucun écran n'ait à afficher « [object Object] » — le genre de détail qui
 * transforme un refus utile en mur.
 */
export async function lireErreur(reponse) {
  let corps = null
  try { corps = await reponse.json() } catch { /* réponse sans corps */ }
  const detail = corps?.detail
  if (detail && typeof detail === 'object') {
    return { code: detail.code || null, message: detail.message || 'Erreur',
             duplicates: detail.duplicates || null, status: reponse.status }
  }
  return { code: null, message: detail || `Erreur ${reponse.status}`,
           duplicates: null, status: reponse.status }
}

export const useClientsStore = defineStore('clients', () => {
  const clients = ref([])
  const clientCourant = ref(null)
  const contacts = ref([])

  const personnes = ref([])
  const personneCourante = ref(null)

  const opportunites = ref([])
  const opportuniteCourante = ref(null)

  const interactions = ref([])

  const chargement = ref(false)
  const erreur = ref(null)

  const clientsActifs = computed(
    () => clients.value.filter(c => c.status !== 'archived'))

  function reinitialiserErreur() { erreur.value = null }

  async function _appel(url, options = {}) {
    const reponse = await apiFetch(url, {
      headers: { 'Content-Type': 'application/json' }, ...options,
    })
    if (!reponse.ok) {
      const details = await lireErreur(reponse)
      const boum = new Error(details.message)
      Object.assign(boum, details)
      throw boum
    }
    return reponse.status === 204 ? null : reponse.json()
  }

  // ── Clients ────────────────────────────────────────────────────────

  async function chargerClients(filtres = {}) {
    chargement.value = true
    erreur.value = null
    try {
      const params = new URLSearchParams()
      Object.entries(filtres).forEach(([cle, valeur]) => {
        if (valeur !== null && valeur !== undefined && valeur !== '') {
          params.append(cle, valeur)
        }
      })
      const suffixe = params.toString() ? `?${params}` : ''
      clients.value = await _appel(`/api/clients${suffixe}`)
    } catch (e) {
      erreur.value = e.message
      clients.value = []
    } finally {
      chargement.value = false
    }
  }

  async function chargerClient(id) {
    chargement.value = true
    erreur.value = null
    try {
      clientCourant.value = await _appel(`/api/clients/${id}`)
      contacts.value = await _appel(`/api/clients/${id}/contacts?include_former=true`)
    } catch (e) {
      erreur.value = e.message
      clientCourant.value = null
    } finally {
      chargement.value = false
    }
  }

  async function creerMandat(clientId, corps) {
    const cree = await _appel(`/api/clients/${clientId}/mandates`, {
      method: 'POST', body: JSON.stringify(corps),
    })
    if (clientCourant.value?.id === clientId) {
      clientCourant.value.mandates = [...(clientCourant.value.mandates || []), cree]
    }
    return cree
  }

  async function modifierMandat(clientId, mandatId, corps) {
    const modifie = await _appel(`/api/clients/${clientId}/mandates/${mandatId}`, {
      method: 'PATCH', body: JSON.stringify(corps),
    })
    if (clientCourant.value?.id === clientId) {
      const liste = clientCourant.value.mandates || []
      _remplacer(liste, modifie)
      clientCourant.value.mandates = [...liste]
    }
    return modifie
  }

  async function creerClient(corps) {
    const cree = await _appel('/api/clients', {
      method: 'POST', body: JSON.stringify(corps) })
    clients.value.push(cree)
    return cree
  }

  async function modifierClient(id, corps) {
    const modifie = await _appel(`/api/clients/${id}`, {
      method: 'PATCH', body: JSON.stringify(corps) })
    _remplacer(clients.value, modifie)
    if (clientCourant.value?.id === id) clientCourant.value = modifie
    return modifie
  }

  async function modifierScalaires(id, corps) {
    const modifie = await _appel(`/api/clients/${id}/scalar-constraints`, {
      method: 'PATCH', body: JSON.stringify(corps) })
    if (clientCourant.value?.id === id) clientCourant.value = modifie
    return modifie
  }

  /**
   * Écrit le blob de contraintes SOUS VERROU.
   *
   * La version envoyée est celle que l'écran avait sous les yeux. Si quelqu'un
   * a enregistré entre-temps, le serveur refuse en 409 et l'appelant doit
   * recharger — c'est voulu : mieux vaut redemander que d'écraser en silence
   * le travail d'un collègue.
   */
  async function enregistrerContraintes(id, contraintes, version, evidence = null) {
    const corps = { constraints: contraintes, constraints_version: version }
    if (evidence) corps.evidence = evidence
    const modifie = await _appel(`/api/clients/${id}/constraints`, {
      method: 'PUT',
      body: JSON.stringify(corps),
    })
    if (clientCourant.value?.id === id) clientCourant.value = modifie
    return modifie
  }

  // ── Référentiel de contraintes ────────────────────────────

  /**
   * Le schéma des contraintes de CE client.
   *
   * L'écran ne connaît aucun champ à l'avance : il rend ce que le serveur décrit.
   * C'est ce qui permet à un admin d'ajouter « Poche défensive max » sans qu'on
   * redéploie le frontend — et surtout ce qui empêche le champ d'être décrit
   * différemment des deux côtés.
   */
  async function lireSchemaContraintes(clientId) {
    return _appel(`/api/clients/${clientId}/constraints/schema`)
  }

  async function lireSchemaPreferencesScope(clientId, scope = {}) {
    const params = new URLSearchParams()
    if (scope.mandate_id) params.set('mandate_id', scope.mandate_id)
    if (scope.affiliation_id) params.set('affiliation_id', scope.affiliation_id)
    return _appel(`/api/clients/${clientId}/scoped-preferences/schema?${params}`)
  }

  async function enregistrerPreferencesScope(
    clientId, preferences, scope = {}, version = 0, evidence = null,
  ) {
    const corps = {
      preferences,
      preferences_version: version,
      mandate_id: scope.mandate_id || null,
      affiliation_id: scope.affiliation_id || null,
    }
    if (evidence) corps.evidence = evidence
    return _appel(`/api/clients/${clientId}/scoped-preferences`, {
      method: 'PUT', body: JSON.stringify(corps),
    })
  }

  async function lireHistoriquePreferences(clientId, scope = {}) {
    const params = new URLSearchParams()
    if (scope.mandate_id) params.set('mandate_id', scope.mandate_id)
    if (scope.affiliation_id) params.set('affiliation_id', scope.affiliation_id)
    const suffixe = params.toString() ? `?${params}` : ''
    return _appel(`/api/clients/${clientId}/preference-history${suffixe}`)
  }

  async function lireMetaContraintes() {
    return _appel('/api/constraint-definitions/meta')
  }

  async function lireDefinitions(clientId = null, avecArchivees = false) {
    const params = new URLSearchParams()
    if (clientId) params.set('client_id', clientId)
    if (avecArchivees) params.set('include_archived', 'true')
    const suffixe = params.toString() ? `?${params}` : ''
    const donnees = await _appel(`/api/constraint-definitions${suffixe}`)
    return donnees.definitions || []
  }

  async function declarerChamp(corps) {
    return _appel('/api/constraint-definitions', {
      method: 'POST', body: JSON.stringify(corps),
    })
  }

  async function modifierChamp(id, corps) {
    return _appel(`/api/constraint-definitions/${id}`, {
      method: 'PATCH', body: JSON.stringify(corps),
    })
  }

  async function archiverChamp(id, forcer = false) {
    return _appel(`/api/constraint-definitions/${id}${forcer ? '?force=true' : ''}`,
                  { method: 'DELETE' })
  }

  async function restaurerChamp(id) {
    return _appel(`/api/constraint-definitions/${id}/restore`, { method: 'POST' })
  }

  // ── Profil de trading — Lot 0 ─────────────────────────────────────

  async function archiverClient(id) {
    const modifie = await _appel(`/api/clients/${id}/archive`, { method: 'POST' })
    _remplacer(clients.value, modifie)
    if (clientCourant.value?.id === id) clientCourant.value = modifie
    return modifie
  }

  async function reactiverClient(id) {
    const modifie = await _appel(`/api/clients/${id}/reactivate`, { method: 'POST' })
    _remplacer(clients.value, modifie)
    if (clientCourant.value?.id === id) clientCourant.value = modifie
    return modifie
  }

  async function supprimerClient(id) {
    await _appel(`/api/clients/${id}`, { method: 'DELETE' })
    clients.value = clients.value.filter(c => c.id !== id)
    if (clientCourant.value?.id === id) clientCourant.value = null
  }

  async function definirCouverture(id, userId, role) {
    return _appel(`/api/clients/${id}/coverage`, {
      method: 'PUT',
      body: JSON.stringify({ user_id: userId, coverage_role: role }) })
  }

  // ── Personnes et affiliations ──────────────────────────────────────

  async function chargerPersonnes(filtres = {}) {
    chargement.value = true
    erreur.value = null
    try {
      const params = new URLSearchParams()
      Object.entries(filtres).forEach(([cle, valeur]) => {
        if (valeur !== null && valeur !== undefined && valeur !== '') {
          params.append(cle, valeur)
        }
      })
      const suffixe = params.toString() ? `?${params}` : ''
      personnes.value = await _appel(`/api/persons${suffixe}`)
    } catch (e) {
      erreur.value = e.message
      personnes.value = []
    } finally {
      chargement.value = false
    }
  }

  async function chargerPersonne(id) {
    chargement.value = true
    erreur.value = null
    try {
      personneCourante.value = await _appel(`/api/persons/${id}`)
    } catch (e) {
      erreur.value = e.message
      personneCourante.value = null
    } finally {
      chargement.value = false
    }
  }

  /** Interrogé AVANT la création — le cas d'une personne déjà connue qui
   *  rejoint une nouvelle société. */
  async function chercherDoublonsPersonne({ first_name, last_name, email }) {
    const params = new URLSearchParams()
    if (first_name) params.append('first_name', first_name)
    if (last_name) params.append('last_name', last_name)
    if (email) params.append('email', email)
    return _appel(`/api/persons/duplicates?${params}`)
  }

  async function creerPersonne(corps) {
    const creee = await _appel('/api/persons', {
      method: 'POST', body: JSON.stringify(corps) })
    personnes.value.push(creee)
    return creee
  }

  async function modifierPersonne(id, corps) {
    const modifiee = await _appel(`/api/persons/${id}`, {
      method: 'PATCH', body: JSON.stringify(corps) })
    _remplacer(personnes.value, modifiee)
    if (personneCourante.value?.id === id) personneCourante.value = modifiee
    return modifiee
  }

  async function ajouterAffiliation(personId, corps) {
    const creee = await _appel(`/api/persons/${personId}/affiliations`, {
      method: 'POST', body: JSON.stringify(corps) })
    await chargerPersonne(personId)
    return creee
  }

  /**
   * Changement de société : clôture l'affiliation en cours et en ouvre une
   * nouvelle, en une seule transaction serveur.
   *
   * Ce n'est PAS « changer l'employeur » d'une personne : l'ancienne
   * affiliation reste en base avec sa date de fin, et tout ce qui y pend —
   * interactions, opportunités, trades — reste rattaché à la société de
   * l'époque.
   */
  async function changerSociete(personId, corps) {
    const modifiee = await _appel(`/api/persons/${personId}/change-company`, {
      method: 'POST', body: JSON.stringify(corps) })
    personneCourante.value = modifiee
    _remplacer(personnes.value, modifiee)
    return modifiee
  }

  async function cloturerAffiliation(personId, affiliationId, endDate) {
    await _appel(
      `/api/persons/${personId}/affiliations/${affiliationId}/close`,
      { method: 'POST', body: JSON.stringify({ end_date: endDate }) })
    await chargerPersonne(personId)
  }

  async function desactiverPersonne(id) {
    const modifiee = await _appel(`/api/persons/${id}/deactivate`, { method: 'POST' })
    _remplacer(personnes.value, modifiee)
    if (personneCourante.value?.id === id) personneCourante.value = modifiee
    return modifiee
  }

  async function reactiverPersonne(id) {
    const modifiee = await _appel(`/api/persons/${id}/reactivate`, { method: 'POST' })
    _remplacer(personnes.value, modifiee)
    if (personneCourante.value?.id === id) personneCourante.value = modifiee
    return modifiee
  }

  async function supprimerPersonne(id) {
    await _appel(`/api/persons/${id}`, { method: 'DELETE' })
    personnes.value = personnes.value.filter(p => p.id !== id)
    if (personneCourante.value?.id === id) personneCourante.value = null
  }

  // ── Opportunités ───────────────────────────────────────────────────

  async function chargerOpportunites(filtres = {}) {
    chargement.value = true
    erreur.value = null
    try {
      const params = new URLSearchParams()
      Object.entries(filtres).forEach(([cle, valeur]) => {
        if (valeur !== null && valeur !== undefined && valeur !== '') {
          params.append(cle, valeur)
        }
      })
      const suffixe = params.toString() ? `?${params}` : ''
      opportunites.value = await _appel(`/api/opportunities${suffixe}`)
    } catch (e) {
      erreur.value = e.message
      opportunites.value = []
    } finally {
      chargement.value = false
    }
  }

  async function chargerOpportunite(id) {
    opportuniteCourante.value = await _appel(`/api/opportunities/${id}`)
    return opportuniteCourante.value
  }

  async function creerOpportunite(corps) {
    const creee = await _appel('/api/opportunities', {
      method: 'POST', body: JSON.stringify(corps) })
    opportunites.value.unshift(creee)
    return creee
  }

  async function modifierOpportunite(id, corps) {
    const modifiee = await _appel(`/api/opportunities/${id}`, {
      method: 'PATCH', body: JSON.stringify(corps) })
    _remplacer(opportunites.value, modifiee)
    if (opportuniteCourante.value?.id === id) opportuniteCourante.value = modifiee
    return modifiee
  }

  async function changerStatut(id, statut, raisonPerte = null, commentaire = null) {
    const modifiee = await _appel(`/api/opportunities/${id}/status`, {
      method: 'POST',
      body: JSON.stringify({ status: statut, lost_reason: raisonPerte,
                             lost_comment: commentaire }) })
    _remplacer(opportunites.value, modifiee)
    if (opportuniteCourante.value?.id === id) opportuniteCourante.value = modifiee
    return modifiee
  }

  async function supprimerOpportunite(id) {
    await _appel(`/api/opportunities/${id}`, { method: 'DELETE' })
    opportunites.value = opportunites.value.filter(o => o.id !== id)
  }

  // ── Interactions ───────────────────────────────────────────────────

  async function chargerInteractions(filtres = {}) {
    const params = new URLSearchParams()
    Object.entries(filtres).forEach(([cle, valeur]) => {
      if (valeur !== null && valeur !== undefined && valeur !== '') {
        params.append(cle, valeur)
      }
    })
    const suffixe = params.toString() ? `?${params}` : ''
    interactions.value = await _appel(`/api/interactions${suffixe}`)
    return interactions.value
  }

  async function creerInteraction(corps) {
    const creee = await _appel('/api/interactions', {
      method: 'POST', body: JSON.stringify(corps) })
    interactions.value.unshift(creee)
    return creee
  }

  async function supprimerInteraction(id) {
    await _appel(`/api/interactions/${id}`, { method: 'DELETE' })
    interactions.value = interactions.value.filter(i => i.id !== id)
  }

  // ── Client Intelligence ────────────────────────────────────────────
  // Lectures analytiques, en lecture seule. `asof` est exposé partout : rejouer
  // une analyse à une date passée est la seule façon de vérifier qu'un signal
  // levé la semaine dernière l'était à raison.

  const signaux = ref([])
  const seuils = ref({})

  async function lireIntelligenceClient(clientId, asof = null, scope = {}) {
    const params = new URLSearchParams()
    if (asof) params.set('asof', asof)
    if (scope.mandate_id) params.set('mandate_id', scope.mandate_id)
    if (scope.affiliation_id) params.set('affiliation_id', scope.affiliation_id)
    if (scope.include_demo !== null && scope.include_demo !== undefined) {
      params.set('include_demo', scope.include_demo)
    }
    const suffixe = params.toString() ? `?${params}` : ''
    return _appel(`/api/client-intelligence/clients/${clientId}${suffixe}`)
  }

  async function lireIntelligencePersonne(personId, asof = null) {
    const suffixe = asof ? `?asof=${asof}` : ''
    return _appel(`/api/client-intelligence/persons/${personId}${suffixe}`)
  }

  async function chargerSignaux({ asof = null, mineOnly = true } = {}) {
    const params = new URLSearchParams({ mine_only: mineOnly })
    if (asof) params.append('asof', asof)
    const reponse = await _appel(`/api/client-intelligence/signals?${params}`)
    signaux.value = reponse.signals
    seuils.value = reponse.thresholds
    return reponse
  }

  async function chargerAnalytics(asof = null) {
    const suffixe = asof ? `?asof=${asof}` : ''
    return _appel(`/api/client-intelligence/analytics${suffixe}`)
  }

  function _remplacer(liste, objet) {
    const index = liste.findIndex(e => e.id === objet.id)
    if (index >= 0) liste[index] = objet
  }

  return {
    clients, clientCourant, contacts, personnes, personneCourante,
    opportunites, opportuniteCourante, interactions,
    chargement, erreur, clientsActifs, reinitialiserErreur,
    chargerClients, chargerClient, creerClient, modifierClient,
    creerMandat, modifierMandat,
    modifierScalaires, enregistrerContraintes, archiverClient,
    lireSchemaContraintes, lireSchemaPreferencesScope,
    enregistrerPreferencesScope, lireHistoriquePreferences,
    lireMetaContraintes, lireDefinitions,
    declarerChamp, modifierChamp, archiverChamp, restaurerChamp,
    reactiverClient, supprimerClient, definirCouverture,
    chargerPersonnes, chargerPersonne, chercherDoublonsPersonne,
    creerPersonne, modifierPersonne, ajouterAffiliation, changerSociete,
    cloturerAffiliation, desactiverPersonne, reactiverPersonne,
    supprimerPersonne,
    chargerOpportunites, chargerOpportunite, creerOpportunite,
    modifierOpportunite, changerStatut, supprimerOpportunite,
    chargerInteractions, creerInteraction, supprimerInteraction,
    signaux, seuils, lireIntelligenceClient, lireIntelligencePersonne,
    chargerSignaux, chargerAnalytics,
  }
})
