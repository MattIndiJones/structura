// Keep leverage fit and absolute surface discretization diagnostics separate.
export function surfaceBenchmarkIssues(calibration) {
  return (calibration?.underlyings || []).flatMap(u => (u.controls || []).filter(row =>
    Number.isFinite(row.lsv_vs_surface_bp) && Number.isFinite(row.lsv_half_ci95_bp)
    && Math.abs(row.lsv_vs_surface_bp) > row.lsv_half_ci95_bp + row.limit_bp
  ).map(row => ({ ...row, underlying: u.underlying })))
}
