export default function CorrectionHistory({ attempts = [] }) {
  if (!attempts.length) return <p className="text-sm text-slate-500">No AI corrections yet.</p>

  return (
    <ol className="space-y-3">
      {attempts.map((attempt) => (
        <li key={attempt.id ?? attempt.attempt_number} className="card">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-sm font-semibold text-slate-200">
              Correction attempt #{attempt.attempt_number}
            </h4>
            <span className="text-xs text-slate-400">
              {attempt.behavior_match_before ?? 0}% → {attempt.behavior_match_after ?? 0}%
            </span>
          </div>
          {attempt.reason ? (
            <p className="mt-2 whitespace-pre-wrap text-xs text-slate-400">{attempt.reason}</p>
          ) : null}
          <details className="mt-2">
            <summary className="cursor-pointer text-xs text-slate-400">Show corrected code</summary>
            <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded bg-surface-950 p-2 font-mono text-xs text-slate-300">
              {attempt.corrected_code}
            </pre>
          </details>
        </li>
      ))}
    </ol>
  )
}
