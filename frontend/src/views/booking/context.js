import { inject } from 'vue'

// State of BookingView, shared with the panels extracted from it (P1-10, U3).
// The view owns every value; a panel only reads or updates it, so moving a
// section of the template never moves its behaviour.
export const BOOKING_CONTEXT = Symbol('BookingView')

export function useBookingContext() {
  const context = inject(BOOKING_CONTEXT, null)
  if (!context) throw new Error('BookingView : ce panneau ne s’affiche que dans sa vue.')
  return context
}
