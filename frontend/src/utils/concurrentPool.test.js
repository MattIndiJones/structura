import { describe, expect, it } from 'vitest'
import { runConcurrentPool } from './concurrentPool.js'

describe('pool de calculs portefeuille', () => {
  it('borne la concurrence et poursuit après l’échec d’un deal', async () => {
    let active = 0
    let peak = 0
    let settled = 0
    const results = await runConcurrentPool([1, 2, 3, 4, 5], async value => {
      active += 1
      peak = Math.max(peak, active)
      await new Promise(resolve => setTimeout(resolve, 5))
      active -= 1
      if (value === 3) throw new Error('deal invalide')
      return value * 2
    }, {
      concurrency: 2,
      onSettled: () => { settled += 1 },
    })

    expect(peak).toBe(2)
    expect(settled).toBe(5)
    expect(results.map(result => result.status)).toEqual([
      'fulfilled', 'fulfilled', 'rejected', 'fulfilled', 'fulfilled',
    ])
    expect(results[4].value).toBe(10)
  })
})
