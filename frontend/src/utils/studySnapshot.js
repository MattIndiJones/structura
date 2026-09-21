// Keep asynchronous outputs attached to the study that requested them.
export function createStudyEpoch() {
  let epoch = 0
  return { next: () => ++epoch, current: () => epoch, accepts: value => value === epoch }
}

export function snapshotStudy(result, artifacts) {
  return JSON.parse(JSON.stringify({ ...result, _artifacts: artifacts }))
}

export function restoreStudyArtifacts(result) {
  return { attribution: null, brinson: result?.block_g || null, synthesis: '', ai: null,
    company: '', client: '', ...(result?._artifacts || {}) }
}
