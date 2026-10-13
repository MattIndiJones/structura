// Several overlays can coexist; closing one must not unlock the others.
let locks = 0
let restore = null

export function lockDocumentScroll() {
  if (typeof document === 'undefined') return () => {}
  if (locks++ === 0) {
    const body = document.body
    const root = document.documentElement
    const previousBody = body.style.overflow
    const previousRoot = root.style.overflow
    body.style.overflow = 'hidden'
    root.style.overflow = 'hidden'
    restore = () => { body.style.overflow = previousBody; root.style.overflow = previousRoot }
  }
  let released = false
  return () => {
    if (released) return
    released = true
    if (--locks === 0) { restore(); restore = null }
  }
}
