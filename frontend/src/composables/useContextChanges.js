// Conservative guard for edited controls without their own draft store.
const edited = new Set(), initial = new WeakMap()
let approvedReload = false
export function prepareContextReload() { approvedReload = true }
export function installContextReloadGuard() {
  // Confirmation has already been resolved before replacing the identity.
  // A later native prompt must not leave the old document on the new session.
  window.addEventListener('beforeunload', event => { if (approvedReload) event.stopImmediatePropagation() }, true)
}
function value(element) { return element.type === 'checkbox' || element.type === 'radio' ? element.checked : element.value }
function editable(element) { return element?.matches?.('input:not([type="password"]):not([type="hidden"]),textarea,select') && !element.closest('[data-context-selector]') }
function focus(event) { if (editable(event.target) && !initial.has(event.target)) initial.set(event.target, value(event.target)) }
function change(event) { if (editable(event.target) && initial.has(event.target)) edited.add(event.target) }
export function hasContextChanges() { return [...edited].some(el => el.isConnected && value(el) !== initial.get(el)) }
export function trackContextChanges() {
  document.addEventListener('focusin', focus, true); document.addEventListener('input', change, true); document.addEventListener('change', change, true)
  return () => { document.removeEventListener('focusin', focus, true); document.removeEventListener('input', change, true); document.removeEventListener('change', change, true); edited.clear() }
}
