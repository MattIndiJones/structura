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

  const scales = {}
  for (const [key, scale] of Object.entries(base.scales || {})) {
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
