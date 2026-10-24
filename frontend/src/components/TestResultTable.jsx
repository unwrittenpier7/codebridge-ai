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
      {results.map((result) => {
        // `reference_valid === false` means the ORIGINAL program failed, so there
        // is no trustworthy reference output to compare against. Saying so
        // explicitly prevents a "both failed the same way" pair from reading as a
        // behavioral match.
        const referenceMissing = result.reference_valid === false
        return (
          <article key={result.id ?? result.test_number} className="card">
            <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h4 className="text-sm font-semibold text-slate-200">Test #{result.test_number}</h4>
                <p className="text-xs text-slate-500">{result.description}</p>
              </div>
              <div className="flex items-center gap-2">
                {referenceMissing ? (
                  <span className="text-xs text-warn" title="The original program did not produce a usable reference result">
                    no valid reference
                  </span>
                ) : null}
                <StatusBadge status={result.status} />
              </div>
            </header>
            {referenceMissing ? (
              <p className="mb-3 rounded border border-warn/40 bg-warn/10 px-2 py-1 text-xs text-warn">
                {result.failure_reason === 'ORIGINAL_TIMEOUT'
                  ? 'The original program timed out, so this test could not be used as a reference.'
                  : 'The original program failed to run cleanly, so this test is not evidence of equivalence.'}
              </p>
            ) : null}
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
            {result.original_stderr ? (
              <details className="mt-2">
                <summary className="cursor-pointer text-xs text-slate-400">
                  Original stderr (exit code {result.original_exit_code})
                </summary>
                <Pre>{result.original_stderr}</Pre>
              </details>
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
              {result.failure_reason ? ` · ${result.failure_reason}` : ''}
            </p>
          </article>
        )
      })}
    </div>
  )
}
