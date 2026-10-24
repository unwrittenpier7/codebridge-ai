import ProgressBar from './ProgressBar.jsx'
import StatCard from './StatCard.jsx'
import StatusBadge from './StatusBadge.jsx'

export default function VerificationSummary({
  result,
  sourceLanguage,
  targetLanguage,
  migrationStatus,
  stale = false,
}) {
  if (!result) return null

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total tests" value={result.total_tests} />
        <StatCard label="Passed" value={result.passed_tests} />
        <StatCard label="Failed" value={result.failed_tests} />
        <StatCard label="Behavior match" value={`${result.behavior_match_percentage}%`} />
      </div>
      <div className="card space-y-3">
        {stale ? (
          <p className="text-xs text-warn">
            This result describes an earlier version of the code and is kept for history only.
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="text-slate-400">
            {sourceLanguage} → {targetLanguage}
          </span>
          {migrationStatus ? (
            <span className="text-slate-400">
              Migration: <span className="text-slate-200">{migrationStatus}</span>
            </span>
          ) : null}
          <span className="flex items-center gap-2">
            Compilation <StatusBadge status={result.compilation_status} />
          </span>
          <span className="flex items-center gap-2">
            Runtime <StatusBadge status={result.runtime_status} />
          </span>
          <span className="flex items-center gap-2">
            Behavior <StatusBadge status={result.overall_status} />
          </span>
        </div>
        <ProgressBar value={result.behavior_match_percentage} label="Behavioral match" />
        {result.error_tests ? (
          <p className="text-xs text-slate-500">
            {result.error_tests} test(s) could not be counted because the original program did not
            produce a valid reference result.
          </p>
        ) : null}
        {result.infrastructure_error ? (
          <pre className="whitespace-pre-wrap rounded border border-fail/40 bg-fail/10 p-2 font-mono text-xs text-fail">
            Infrastructure error: {result.infrastructure_error}
          </pre>
        ) : null}
        {result.compiler_error ? (
          <pre className="whitespace-pre-wrap rounded border border-fail/40 bg-fail/10 p-2 font-mono text-xs text-fail">
            {result.compiler_error}
          </pre>
        ) : null}
      </div>
    </div>
  )
}
