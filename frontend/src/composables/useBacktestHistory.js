import { computed, onUnmounted, ref, watch } from 'vue'
import { apiFetch, apiErrorMessage } from '../utils/api.js'

export function useBacktestHistory(store, form) {
  const bounds = ref(null), loading = ref(false), error = ref(''), manualStart = ref(false)
  const tickers = computed(() => [...new Set(store.underlyings.map(u => u.ticker?.trim().toUpperCase() || ''))])
  const suggestedStart = computed(() => bounds.value?.available ? bounds.value.start_effective : '')
  let sequence = 0, controller

  function useSuggestedStart() {
    manualStart.value = false
    form.value.start_date = suggestedStart.value || ''
  }

  watch(() => JSON.stringify([tickers.value, form.value.end_date]), async () => {
    const current = ++sequence
    controller?.abort()
    controller = new AbortController()
    bounds.value = null; error.value = ''; loading.value = false
    if (!manualStart.value) form.value.start_date = ''
    if (!tickers.value.length || tickers.value.includes('') || !form.value.end_date) return
    loading.value = true
    try {
      const query = new URLSearchParams({ tickers: tickers.value.join(','), end_date: form.value.end_date })
      const response = await apiFetch(`/api/backtest/history-bounds?${query}`, { signal: controller.signal })
      const result = await response.json()
      if (current !== sequence) return
      if (!response.ok) throw new Error(apiErrorMessage(result))
      bounds.value = result
      if (!manualStart.value) form.value.start_date = suggestedStart.value || ''
    } catch (failure) {
      if (current === sequence && failure.name !== 'AbortError') error.value = failure.message
    } finally {
      if (current === sequence) loading.value = false
    }
  }, { immediate: true })

  watch(() => store.backtest?.history_policy, policy => {
    if (policy && !manualStart.value) form.value.start_date = policy.effective_start
  })
  onUnmounted(() => { sequence++; controller?.abort() })
  return { bounds, loading, error, manualStart, suggestedStart, useSuggestedStart }
}
