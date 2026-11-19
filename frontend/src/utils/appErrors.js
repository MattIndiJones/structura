// Last line of defence against the white screen (P1-10, U1).
//
// Before this module, nothing caught an error Vue could not handle: a render
// exception, or a lazy fragment deleted by the next `npm run build`, left an
// empty page with the cause in the console only. Two kinds of failure, two
// answers:
//
// - the screen is broken (render, setup, update, a fragment that would not
//   load): an error screen that says so and offers to reload;
// - an action failed (a click handler, a load in onMounted, a watcher): a
//   notice the user can close, the screen stays usable.
//
// A fragment missing after a rebuild is the one case reloading fixes on its
// own: the page reloads once, on the route the user asked for. A second miss
// within RELOAD_WINDOW_MS is not retried — it would loop — and the error
// screen explains why instead.
//
// The screen is plain DOM, built outside Vue on purpose: it must survive an
// application whose root never mounted.

export const RELOAD_KEY = 'structura_fragment_reload_at'
export const RELOAD_WINDOW_MS = 20_000
const ROOT_ID = 'app-error'

// Vue passes the error origin as `info`: a readable string in development,
// `https://vuejs.org/error-reference/#runtime-<code>` in production.
// See ErrorCodes and LifecycleHooks in @vue/runtime-core.
const SCREEN_BREAKING = new Set([
  '0', '1', '13', '14', '15', 'bc', 'c', 'bm', 'sp',
  'setup function', 'render function', 'async component loader', 'scheduler flush', 'component update',
  'beforeCreate hook', 'created hook', 'beforeMount hook', 'serverPrefetch hook',
])

export function errorOrigin(info) {
  const text = String(info ?? '')
  const match = /#runtime-([\w]+)$/.exec(text)
  return match ? match[1] : text
}

export function breaksScreen(info) {
  return SCREEN_BREAKING.has(errorOrigin(info))
}

export function isFragmentLoadError(error) {
  const message = String(error?.message ?? error ?? '')
  return /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS|Loading (CSS )?chunk [\w-]+ failed/i.test(message)
}

export function errorMessage(error) {
  if (error == null) return 'Erreur inconnue'
  if (typeof error === 'string') return error
  return error.message || String(error)
}

// Reload once per window: true when a reload may be attempted now.
export function mayReload(storage, now = Date.now()) {
  let last = 0
  try { last = Number(storage?.getItem(RELOAD_KEY) || 0) } catch { /* storage blocked: allow once */ }
  if (last && now - last < RELOAD_WINDOW_MS) return false
  try { storage?.setItem(RELOAD_KEY, String(now)) } catch { /* the reload still helps */ }
  return true
}

function appIsEmpty(doc) {
  const root = doc.getElementById('app')
  return !root || !String(root.textContent || '').trim()
}

function element(doc, tag, attrs = {}, text) {
  const node = doc.createElement(tag)
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value)
  if (text != null) node.textContent = text
  return node
}

const COPY = {
  screen: {
    title: 'Cet écran a rencontré une erreur',
    body: 'L’affichage s’est interrompu. Vos données enregistrées ne sont pas touchées ; '
      + 'une saisie non enregistrée de cet écran peut être perdue au rechargement.',
  },
  fragment: {
    title: 'Une nouvelle version de Structura est installée',
    body: 'Une partie de l’écran n’a pas pu être chargée, même après un rechargement automatique. '
      + 'Rechargez la page ; si le message revient, le serveur ne sert plus l’interface attendue.',
  },
  action: {
    title: 'L’action n’a pas abouti',
    body: 'L’écran reste utilisable. Le détail de l’erreur est dans la console du navigateur.',
  },
}

/**
 * Show the error screen (`kind` = 'screen' | 'fragment') or the closable
 * notice ('action'). One at a time: a newer failure replaces the older one,
 * except that a notice never hides a screen error already shown.
 */
export function showError(doc, win, { kind, error }) {
  const existing = doc.getElementById(ROOT_ID)
  if (existing) {
    if (kind === 'action' && existing.getAttribute('data-kind') !== 'action') return existing
    existing.remove()
  }
  // A broken screen whose page is empty cannot be dismissed: there is nothing
  // to go back to.
  const blocking = kind !== 'action'
  const dismissible = !blocking || !appIsEmpty(doc)
  const copy = COPY[kind]
  const root = element(doc, 'div', {
    id: ROOT_ID, 'data-kind': kind, class: blocking ? 'app-error app-error--screen' : 'app-error app-error--notice',
    role: blocking ? 'alertdialog' : 'status', 'aria-labelledby': ROOT_ID + '-title',
  })
  const panel = element(doc, 'div', { class: 'app-error__panel' })
  panel.appendChild(element(doc, 'h2', { id: ROOT_ID + '-title', class: 'app-error__title' }, copy.title))
  panel.appendChild(element(doc, 'p', { class: 'app-error__body' }, copy.body))
  const details = element(doc, 'details', { class: 'app-error__details' })
  details.appendChild(element(doc, 'summary', {}, 'Détail technique'))
  details.appendChild(element(doc, 'pre', {}, errorMessage(error)))
  panel.appendChild(details)
  const actions = element(doc, 'div', { class: 'app-error__actions' })
  const reload = element(doc, 'button', { type: 'button', class: 'btn-primary' }, 'Recharger la page')
  reload.addEventListener('click', () => win.location.reload())
  actions.appendChild(reload)
  if (blocking) {
    const home = element(doc, 'button', { type: 'button', class: 'btn-secondary' }, 'Revenir à l’accueil')
    home.addEventListener('click', () => { win.location.hash = '#/'; win.location.reload() })
    actions.appendChild(home)
  }
  if (dismissible) {
    const close = element(doc, 'button', { type: 'button', class: 'btn-secondary' }, 'Fermer')
    close.addEventListener('click', () => root.remove())
    actions.appendChild(close)
  }
  panel.appendChild(actions)
  root.appendChild(panel)
  doc.body.appendChild(root)
  if (blocking) reload.focus?.()
  return root
}

/** A fragment that would not load: reload once on the target route, then explain. */
export function recoverFragment(doc, win, storage, error, targetPath) {
  if (mayReload(storage)) {
    // replaceState, not location.hash: changing the hash would make the
    // router navigate — and fail — once more before the reload.
    if (targetPath) win.history.replaceState(win.history.state, '', '#' + targetPath)
    win.location.reload()
    return 'reloading'
  }
  showError(doc, win, { kind: 'fragment', error })
  return 'shown'
}

export function installErrorHandling(app, router, { doc = document, win = window, storage = win.sessionStorage, log = console } = {}) {
  app.config.errorHandler = (error, _instance, info) => {
    log.error(error)
    if (isFragmentLoadError(error)) return recoverFragment(doc, win, storage, error)
    // A render that leaves nothing on screen is a broken screen, whatever its origin.
    const kind = breaksScreen(info) || appIsEmpty(doc) ? 'screen' : 'action'
    showError(doc, win, { kind, error })
  }
  router.onError((error, to) => {
    log.error(error)
    if (isFragmentLoadError(error)) return recoverFragment(doc, win, storage, error, to?.fullPath)
    showError(doc, win, { kind: appIsEmpty(doc) ? 'screen' : 'action', error })
  })
  // Vite's own signal for a module preload that failed (rebuilt bundle).
  win.addEventListener('vite:preloadError', event => {
    event.preventDefault?.()
    recoverFragment(doc, win, storage, event.payload || event)
  })
  win.addEventListener('unhandledrejection', event => {
    if (!isFragmentLoadError(event.reason)) return
    event.preventDefault?.()
    recoverFragment(doc, win, storage, event.reason)
  })
}

/** Mount, and show the error screen rather than nothing if mounting throws. */
export function mountSafely(app, selector, { doc = document, win = window, log = console } = {}) {
  try {
    return app.mount(selector)
  } catch (error) {
    log.error(error)
    showError(doc, win, { kind: 'screen', error })
    return null
  }
}
