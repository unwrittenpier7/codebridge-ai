export default function ProgressBar({ value = 0, label }) {
  const percentage = Math.max(0, Math.min(100, Number(value) || 0))
  const color = percentage === 100 ? 'bg-pass' : percentage >= 50 ? 'bg-partial' : 'bg-fail'
  return (
    <div>
      {label ? (
        <div className="mb-1 flex justify-between text-xs text-slate-400">
          <span>{label}</span>
          <span>{percentage}%</span>
        </div>
      ) : null}
      <div className="h-2 w-full overflow-hidden rounded bg-surface-700">
        <div
          role="progressbar"
          aria-valuenow={percentage}
          aria-valuemin={0}
          aria-valuemax={100}
          className={`h-full ${color}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  )
}
