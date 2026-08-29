/**
 * Demander confirmation, partout, de la même façon.
 *
 * L'application posait ses questions avec le `confirm()` du navigateur : seize
 * appels dans onze fichiers. Chrome ouvre alors sa propre boîte, avec sa
 * typographie, ses boutons et son titre — « 127.0.0.1:8000 dit… » — qui n'ont
 * rien à voir avec le reste de l'écran. Et surtout, `confirm()` est BLOQUANT et
 * synchrone : il ne peut ni styler un choix destructeur, ni afficher un détail
 * mis en forme, ni être attendu depuis un garde de route.
 *
 * Ce service rend une promesse. Un seul `<ConfirmDialog>` monté à la racine de
 * l'application la résout. On peut donc écrire :
 *
 *     if (!await confirmer({ titre: 'Supprimer ?', danger: true })) return
 *
 * aussi bien dans un composant que dans `router.beforeEach`, où le `confirm()`
 * natif fonctionnait mais interdisait toute mise en forme.
 *
 * Une seule question à la fois : la demande en cours est remplacée et son
 * appelant reçoit `false`. Empiler des modales laisserait un appelant attendre
 * une réponse que personne ne lui donnera jamais.
 */
import { reactive } from 'vue'

export const demande = reactive({
  ouvert: false,
  titre: '',
  message: '',
  detail: '',
  confirmer: 'Confirmer',
  annuler: 'Annuler',
  danger: false,
  _resoudre: null,
})

/**
 * @param {object} o
 * @param {string} o.titre     la question, courte et directe
 * @param {string} [o.message] ce que l'action fait, ou ce qu'elle coûte
 * @param {string} [o.detail]  du texte préformaté (liste, motif du serveur)
 * @param {string} [o.confirmer] libellé du bouton — dis ce qui va se passer
 * @param {boolean} [o.danger] rouge, pour ce qui détruit
 * @returns {Promise<boolean>}
 */
export function confirmer(o = {}) {
  if (demande._resoudre) {
    // La question précédente n'a pas été tranchée : son appelant renonce.
    demande._resoudre(false)
  }
  demande.titre = o.titre || 'Confirmer ?'
  demande.message = o.message || ''
  demande.detail = o.detail || ''
  // Un bouton doit dire ce qu'il fait : « Supprimer », pas « OK ».
  demande.confirmer = o.confirmer || 'Confirmer'
  demande.annuler = o.annuler || 'Annuler'
  demande.danger = !!o.danger
  demande.ouvert = true
  return new Promise(resolve => { demande._resoudre = resolve })
}

export function repondre(valeur) {
  const resoudre = demande._resoudre
  demande._resoudre = null
  demande.ouvert = false
  if (resoudre) resoudre(!!valeur)
}
