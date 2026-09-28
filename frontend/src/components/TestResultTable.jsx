import StatusBadge from './StatusBadge.jsx'

function Pre({ children }) {
  return (
    <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-surface-950 p-2 font-mono text-xs text-slate-300">
      {children || '<empty>'}
    </pre>
  )
}

export default function TestResultTable({ results = [] }) {
  if (!results.length) {
    return <p className="text-sm text-slate-500">No test results yet.</p>
  }

  return (
    <div className="space-y-3">
      {results.map((result) => (
        <article key={result.id ?? result.test_number} className="card">
          <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h4 className="text-sm font-semibold text-slate-200">Test #{result.test_number}</h4>
              <p className="text-xs text-slate-500">{result.description}</p>
            </div>
            <StatusBadge status={result.status} />
          </header>
          <div className="grid gap-3 md:grid-cols-3">
            <div>
              <p className="label">Input</p>
              <Pre>{result.input}</Pre>
            </div>
            <div>
              <p className="label">Original output</p>
              <Pre>{result.original_output}</Pre>
            </div>
            <div>
              <p className="label">Migrated output</p>
              <Pre>{result.migrated_output}</Pre>
            </div>
          </div>
          {result.status !== 'PASS' && result.difference ? (
            <p className="mt-2 rounded border border-fail/40 bg-fail/10 px-2 py-1 font-mono text-xs text-fail">
              {result.difference}
            </p>
          ) : null}
          {result.migrated_stderr ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-slate-400">
                Migrated stderr (exit code {result.migrated_exit_code})
              </summary>
              <Pre>{result.migrated_stderr}</Pre>
            </details>
          ) : null}
          <p className="mt-2 text-[11px] text-slate-500">
            original {result.original_time_ms ?? 0} ms · migrated {result.migrated_time_ms ?? 0} ms
          </p>
        </article>
      ))}
    </div>
  )
}
