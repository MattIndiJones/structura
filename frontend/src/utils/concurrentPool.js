/** Run independent async jobs with bounded concurrency and settle every job. */
export async function runConcurrentPool(
  items,
  worker,
  { concurrency = 2, onSettled = () => {} } = {},
) {
  const values = Array.from(items)
  const results = new Array(values.length)
  const limit = Math.max(1, Math.min(values.length || 1, Math.floor(concurrency)))
  let cursor = 0

  async function runNext() {
    while (cursor < values.length) {
      const index = cursor++
      try {
        results[index] = { status: 'fulfilled', value: await worker(values[index], index) }
      } catch (reason) {
        results[index] = { status: 'rejected', reason }
      }
      onSettled(results[index], index)
    }
  }

  await Promise.all(Array.from({ length: limit }, runNext))
  return results
}
