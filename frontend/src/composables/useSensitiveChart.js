// Demo-aware Chart.js options. All charts in the app are built imperatively
// (new Chart(canvas, {...})), so there's no declarative <SensitiveChart>
// element that could intercept rendering — instead, each chart's options
// object is passed through demoChartOptions() before construction, which
// strips axis tick labels and disables tooltips while leaving the shape of
// the chart (bars/lines/heatmap colors) fully visible. This keeps shape
// (the thing useful for a demo) without leaking exact numbers.
//
// Shallow-merge only (never JSON-clone): Chart.js options routinely carry
// callback functions (color scales, tooltip formatters) that a clone would
// silently drop.
export function demoChartOptions(base = {}, enabled) {
  if (!enabled) return base

  // Always mask the default cartesian axes ('x'/'y') even when a chart's
  // options don't declare a `scales` block at all (e.g. after a styling
  // cleanup removes a now-redundant color-only scales entry) — Chart.js
  // still renders real tick labels on its implicit default scales, and an
  // empty `base.scales` here would otherwise silently stop masking them.
  // Non-cartesian charts (doughnut, etc.) simply ignore unknown scale ids,
  // so this fallback is a no-op for them.
  const declaredKeys = Object.keys(base.scales || {})
  const keys = declaredKeys.length ? declaredKeys : ['x', 'y']

  const scales = {}
  for (const key of keys) {
    const scale = (base.scales || {})[key] || {}
    scales[key] = { ...scale, ticks: { ...(scale.ticks || {}), display: false } }
  }

  return {
    ...base,
    scales,
    plugins: {
      ...base.plugins,
      tooltip: { ...(base.plugins?.tooltip), enabled: false },
    },
  }
}
