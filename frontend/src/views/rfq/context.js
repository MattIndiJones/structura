import { inject } from 'vue'

// State of RfqView, shared with the panels extracted from it (P1-10, U3).
// The view owns every value; a panel only reads or updates it, so moving a
// section of the template never moves its behaviour.
export const RFQ_CONTEXT = Symbol('RfqView')

export function useRfqContext() {
  const context = inject(RFQ_CONTEXT, null)
  if (!context) throw new Error('RfqView : ce panneau ne s’affiche que dans sa vue.')
  return context
}
