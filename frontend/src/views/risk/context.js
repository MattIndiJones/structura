import { inject } from 'vue'

// State of RiskManagementView, shared with the panels extracted from it (P1-10, U3).
// The view owns every value; a panel only reads or updates it, so moving a
// section of the template never moves its behaviour.
export const RISK_CONTEXT = Symbol('RiskManagementView')

export function useRiskContext() {
  const context = inject(RISK_CONTEXT, null)
  if (!context) throw new Error('RiskManagementView : ce panneau ne s’affiche que dans sa vue.')
  return context
}
