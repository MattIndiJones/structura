import { describe, expect, it, vi } from 'vitest'
import {
  RELOAD_KEY, RELOAD_WINDOW_MS, breaksScreen, errorOrigin, installErrorHandling, isFragmentLoadError,
  mayReload, mountSafely, showError,
} from './appErrors.js'

// A few lines of DOM: enough for the error screen, which only creates
// elements, sets attributes and text, and listens to clicks. innerHTML
// throws, so an error message can never be parsed as markup.
function fakeDocument({ appText = 'Booking — produits bookés' } = {}) {
  const byParent = new WeakMap()
  const node = (tag) => {
    const n = {
      tagName: tag.toUpperCase(), attributes: new Map(), children: [], listeners: {}, textContent: '',
      setAttribute(k, v) { this.attributes.set(k, String(v)) },
      getAttribute(k) { return this.attributes.has(k) ? this.attributes.get(k) : null },
      appendChild(child) { this.children.push(child); byParent.set(child, this); return child },
      remove() { const p = byParent.get(this); if (p) p.children.splice(p.children.indexOf(this), 1) },
      addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn) },
      click() { (this.listeners.click || []).forEach(fn => fn()) },
      focus: vi.fn(),
    }
    Object.defineProperty(n, 'innerHTML', { set() { throw new Error('innerHTML is not allowed') } })
    return n
  }
  const body = node('body')
  const app = node('div'); app.setAttribute('id', 'app'); app.textContent = appText
  body.appendChild(app)
  const find = (root, id) => {
    if (root.getAttribute?.('id') === id) return root
    for (const c of root.children) { const hit = find(c, id); if (hit) return hit }
    return null
  }
  return { body, app, createElement: node, getElementById: id => find(body, id) }
}

function fakeWindow() {
  const listeners = {}
  return {
    listeners,
    location: { reload: vi.fn(), hash: '#/' },
    history: { state: { position: 3 }, replaceState: vi.fn() },
    addEventListener(type, fn) { (listeners[type] ||= []).push(fn) },
    dispatch(type, event) { (listeners[type] || []).forEach(fn => fn(event)) },
  }
}

function memoryStorage() {
  const data = new Map()
  return { getItem: k => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)) }
}

function install(options = {}) {
  const doc = fakeDocument(options), win = fakeWindow(), storage = memoryStorage()
  const app = { config: {} }
  let routerError
  const router = { onError: fn => { routerError = fn } }
  const log = { error: vi.fn() }
  installErrorHandling(app, router, { doc, win, storage, log })
  return { doc, win, storage, log, vueError: app.config.errorHandler, routerError: (...a) => routerError(...a) }
}

const shown = doc => doc.getElementById('app-error')
const buttons = root => {
  const out = []
  const walk = n => { if (n.tagName === 'BUTTON') out.push(n); n.children.forEach(walk) }
  walk(root)
  return out
}
const texts = root => {
  const out = []
  const walk = n => { if (n.textContent) out.push(n.textContent); n.children.forEach(walk) }
  walk(root)
  return out
}

describe('origine d’une erreur Vue', () => {
  it.each([
    ['https://vuejs.org/error-reference/#runtime-1', true],      // render, production
    ['https://vuejs.org/error-reference/#runtime-0', true],      // setup
    ['https://vuejs.org/error-reference/#runtime-15', true],     // component update
    ['https://vuejs.org/error-reference/#runtime-bm', true],     // beforeMount
    ['https://vuejs.org/error-reference/#runtime-6', false],     // component event handler
    ['https://vuejs.org/error-reference/#runtime-5', false],     // native event handler
    ['https://vuejs.org/error-reference/#runtime-m', false],     // mounted: a failed load, not a broken screen
    ['https://vuejs.org/error-reference/#runtime-3', false],     // watcher callback
    ['render function', true],                                   // development strings
    ['component event handler', false],
    [undefined, false],
  ])('%s → écran cassé : %s', (info, expected) => {
    expect(breaksScreen(info)).toBe(expected)
  })
  it('lit le code de production', () => {
    expect(errorOrigin('https://vuejs.org/error-reference/#runtime-14')).toBe('14')
  })
})

describe('fragment introuvable', () => {
  it.each([
    'Failed to fetch dynamically imported module: http://127.0.0.1:8000/assets/AmcView-x.js',   // Chromium
    'error loading dynamically imported module: http://127.0.0.1/assets/a.js',                  // Firefox
    'Importing a module script failed.',                                                          // Safari
    'Unable to preload CSS for /assets/BookingView-x.css',                                        // Vite
  ])('reconnaît « %s »', message => {
    expect(isFragmentLoadError(new TypeError(message))).toBe(true)
  })
  it('ne confond pas une erreur ordinaire', () => {
    expect(isFragmentLoadError(new TypeError("Cannot read properties of undefined (reading 'id')"))).toBe(false)
    expect(isFragmentLoadError(null)).toBe(false)
  })
  it('ne recharge qu’une fois par fenêtre', () => {
    const storage = memoryStorage()
    expect(mayReload(storage, 1_000)).toBe(true)
    expect(mayReload(storage, 1_000 + RELOAD_WINDOW_MS - 1)).toBe(false)
    expect(mayReload(storage, 1_000 + RELOAD_WINDOW_MS + 1)).toBe(true)
  })
  it('recharge malgré un stockage bloqué', () => {
    const blocked = { getItem() { throw new Error('blocked') }, setItem() { throw new Error('blocked') } }
    expect(mayReload(blocked)).toBe(true)
  })
})

describe('installErrorHandling', () => {
  it('un rendu cassé affiche l’écran d’erreur, refermable tant que la page a un contenu', () => {
    const { doc, vueError, log } = install()
    const error = new TypeError("Cannot read properties of undefined (reading 'deals')")
    vueError(error, null, 'https://vuejs.org/error-reference/#runtime-1')
    const root = shown(doc)
    expect(root.getAttribute('role')).toBe('alertdialog')
    expect(root.getAttribute('data-kind')).toBe('screen')
    expect(texts(root)).toContain('Cet écran a rencontré une erreur')
    expect(texts(root)).toContain(error.message)
    expect(buttons(root).map(b => b.textContent)).toEqual(['Recharger la page', 'Revenir à l’accueil', 'Fermer'])
    expect(log.error).toHaveBeenCalledWith(error)
  })
  it('une page restée vide ne se referme pas : il n’y a rien derrière', () => {
    const { doc, vueError } = install({ appText: '   ' })
    vueError(new Error('boom'), null, 'https://vuejs.org/error-reference/#runtime-6')
    const root = shown(doc)
    expect(root.getAttribute('data-kind')).toBe('screen')
    expect(buttons(root).map(b => b.textContent)).toEqual(['Recharger la page', 'Revenir à l’accueil'])
  })
  it('une action en échec laisse l’écran utilisable', () => {
    const { doc, win, vueError } = install()
    vueError(new Error('Calcul refusé'), null, 'https://vuejs.org/error-reference/#runtime-6')
    const root = shown(doc)
    expect(root.getAttribute('role')).toBe('status')
    expect(texts(root)).toContain('L’action n’a pas abouti')
    const [reload, close] = buttons(root)
    expect(close.textContent).toBe('Fermer')
    close.click()
    expect(shown(doc)).toBeNull()
    expect(win.location.reload).not.toHaveBeenCalled()
  })
  it('un avis ne masque pas un écran cassé, l’inverse oui', () => {
    const { doc, vueError } = install()
    vueError(new Error('a'), null, 'https://vuejs.org/error-reference/#runtime-6')
    vueError(new Error('b'), null, 'https://vuejs.org/error-reference/#runtime-1')
    expect(shown(doc).getAttribute('data-kind')).toBe('screen')
    vueError(new Error('c'), null, 'https://vuejs.org/error-reference/#runtime-6')
    expect(shown(doc).getAttribute('data-kind')).toBe('screen')
    expect(doc.body.children.filter(c => c.getAttribute('id') === 'app-error')).toHaveLength(1)
  })
  it('Recharger et Revenir à l’accueil rechargent la page', () => {
    const { doc, win, vueError } = install()
    vueError(new Error('x'), null, 'render function')
    const [reload, home] = buttons(shown(doc))
    reload.click()
    home.click()
    expect(win.location.hash).toBe('#/')
    expect(win.location.reload).toHaveBeenCalledTimes(2)
  })
  it('un fragment introuvable recharge une fois sur la route demandée, puis explique', () => {
    const { doc, win, storage, routerError } = install()
    const error = new TypeError('Failed to fetch dynamically imported module: /assets/BookingView-old.js')
    routerError(error, { fullPath: '/booking?deal=3' })
    expect(win.history.replaceState).toHaveBeenCalledWith({ position: 3 }, '', '#/booking?deal=3')
    expect(win.location.reload).toHaveBeenCalledTimes(1)
    expect(storage.getItem(RELOAD_KEY)).not.toBeNull()
    expect(shown(doc)).toBeNull()
    routerError(error, { fullPath: '/booking?deal=3' })
    expect(win.location.reload).toHaveBeenCalledTimes(1)
    expect(shown(doc).getAttribute('data-kind')).toBe('fragment')
    expect(texts(shown(doc))).toContain('Une nouvelle version de Structura est installée')
  })
  it('une erreur de navigation ordinaire est signalée sans rechargement', () => {
    const { doc, win, routerError } = install()
    routerError(new Error('Garde refusée'), { fullPath: '/admin' })
    expect(win.location.reload).not.toHaveBeenCalled()
    expect(shown(doc).getAttribute('data-kind')).toBe('action')
  })
  it('le signal de Vite recharge et neutralise l’erreur par défaut', () => {
    const { win } = install()
    const event = { preventDefault: vi.fn(), payload: new Error('Unable to preload CSS for /assets/x.css') }
    win.dispatch('vite:preloadError', event)
    expect(event.preventDefault).toHaveBeenCalled()
    expect(win.location.reload).toHaveBeenCalledTimes(1)
  })
  it('une promesse rejetée hors fragment reste au navigateur', () => {
    const { doc, win } = install()
    const event = { preventDefault: vi.fn(), reason: new Error('Réseau indisponible') }
    win.dispatch('unhandledrejection', event)
    expect(event.preventDefault).not.toHaveBeenCalled()
    expect(shown(doc)).toBeNull()
  })
  it('un message d’erreur reste du texte, jamais du balisage', () => {
    const { doc, vueError } = install()
    const message = '<img src=x onerror="alert(1)">'
    vueError(new Error(message), null, 'render function')
    expect(texts(shown(doc))).toContain(message)
  })
})

describe('mountSafely', () => {
  it('affiche l’écran d’erreur si le montage échoue', () => {
    const doc = fakeDocument({ appText: '' }), win = fakeWindow(), log = { error: vi.fn() }
    const app = { mount() { throw new Error('montage impossible') } }
    expect(mountSafely(app, '#app', { doc, win, log })).toBeNull()
    expect(shown(doc).getAttribute('data-kind')).toBe('screen')
  })
  it('rend l’instance quand tout va bien', () => {
    const app = { mount: () => 'root' }
    expect(mountSafely(app, '#app', { doc: fakeDocument(), win: fakeWindow(), log: console })).toBe('root')
  })
  it('showError rend un seul écran à la fois', () => {
    const doc = fakeDocument(), win = fakeWindow()
    showError(doc, win, { kind: 'screen', error: 'a' })
    showError(doc, win, { kind: 'fragment', error: 'b' })
    expect(doc.body.children.filter(c => c.getAttribute('id') === 'app-error')).toHaveLength(1)
    expect(shown(doc).getAttribute('data-kind')).toBe('fragment')
  })
})
