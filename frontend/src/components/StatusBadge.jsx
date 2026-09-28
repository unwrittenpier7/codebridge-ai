const STYLES = {
  PASS: 'border-pass/40 bg-pass/10 text-pass',
  VERIFIED: 'border-pass/40 bg-pass/10 text-pass',
  PARTIAL: 'border-partial/40 bg-partial/10 text-partial',
  FAIL: 'border-fail/40 bg-fail/10 text-fail',
  FAILED: 'border-fail/40 bg-fail/10 text-fail',
  ERROR: 'border-fail/40 bg-fail/10 text-fail',
}

export default function StatusBadge({ status, className = '' }) {
  const value = (status || 'UNKNOWN').toString().toUpperCase()
  const style = STYLES[value] || 'border-surface-600 bg-surface-800 text-slate-300'
  return (
    <span
      data-testid="status-badge"
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-semibold tracking-wide ${style} ${className}`}
    >
      {value}
    </span>
  )
}
