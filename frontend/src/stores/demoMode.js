// Demo Mode — pure presentation layer. Never read by pricing logic or API
// calls: toggling this store cannot change a single computed price. It only
// controls whether components show real values or placeholders.
//
// This is the Vue/Pinia equivalent of what a React app would build as a
// Context + hook: global reactive state, persisted so a reload during a
// live demo doesn't flip back to showing real numbers.
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'structura_demo_mode'

function loadPersisted() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { enabled: false, linkedinMode: false }
    const parsed = JSON.parse(raw)
    return { enabled: !!parsed.enabled, linkedinMode: !!parsed.linkedinMode }
  } catch {
    return { enabled: false, linkedinMode: false }
  }
}

export const useDemoModeStore = defineStore('demoMode', () => {
  const initial = loadPersisted()
  const enabled = ref(initial.enabled)
  const linkedinMode = ref(initial.linkedinMode)

  watch([enabled, linkedinMode], ([e, l]) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ enabled: e, linkedinMode: l }))
    } catch { /* localStorage unavailable (private mode, etc.) — non-fatal */ }
  })

  function toggle() {
    enabled.value = !enabled.value
    if (!enabled.value) linkedinMode.value = false
  }
  function enable() { enabled.value = true }
  function disable() { enabled.value = false; linkedinMode.value = false }
  // Bonus: one click to mask everything AND trim technical clutter, ready
  // for a screenshot to share publicly (e.g. LinkedIn).
  function prepareForLinkedIn() { enabled.value = true; linkedinMode.value = true }

  // Stable, deterministic anonymization for an underlying: same position in
  // the list always maps to the same letter, regardless of its real
  // name/ticker. Falls back to a number past 26 (no realistic deal has that
  // many legs).
  function underlyingLabel(realName, index) {
    if (!enabled.value) return realName
    const letter = index < 26 ? String.fromCharCode(65 + index) : `#${index + 1}`
    return `Sous-jacent ${letter}`
  }

  return { enabled, linkedinMode, toggle, enable, disable, prepareForLinkedIn, underlyingLabel }
})
