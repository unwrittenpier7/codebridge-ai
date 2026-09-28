import ProgressBar from './ProgressBar.jsx'
import StatCard from './StatCard.jsx'
import StatusBadge from './StatusBadge.jsx'

export default function VerificationSummary({ result, sourceLanguage, targetLanguage, migrationStatus }) {
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
        {result.compiler_error ? (
          <pre className="whitespace-pre-wrap rounded border border-fail/40 bg-fail/10 p-2 font-mono text-xs text-fail">
            {result.compiler_error}
          </pre>
        ) : null}
      </div>
    </div>
  )
}
