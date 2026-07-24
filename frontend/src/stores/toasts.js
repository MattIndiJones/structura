import { defineStore } from 'pinia'
import { ref } from 'vue'

let nextId = 1

export const useToastsStore = defineStore('toasts', () => {
  const items = ref([])

  function push({ kind = 'info', text, timeout = 4000 }) {
    const id = nextId++
    items.value.push({ id, kind, text })
    if (timeout > 0) {
      setTimeout(() => dismiss(id), timeout)
    }
    return id
  }

  function dismiss(id) {
    items.value = items.value.filter(t => t.id !== id)
  }

  function success(text, timeout) { return push({ kind: 'success', text, timeout }) }
  function error(text, timeout)   { return push({ kind: 'error', text, timeout }) }
  function warning(text, timeout) { return push({ kind: 'warning', text, timeout }) }
  function info(text, timeout)    { return push({ kind: 'info', text, timeout }) }

  return { items, push, dismiss, success, error, warning, info }
})
