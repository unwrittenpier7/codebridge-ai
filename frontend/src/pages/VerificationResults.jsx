import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Alert from '../components/Alert.jsx'
import Spinner from '../components/Spinner.jsx'
import TestResultTable from '../components/TestResultTable.jsx'
import VerificationSummary from '../components/VerificationSummary.jsx'
import { describeError } from '../api/client.js'
import { migrationsApi } from '../api/endpoints.js'

export default function VerificationResults() {
  const { migrationId } = useParams()
  const [state, setState] = useState({ migration: null, results: null })
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([migrationsApi.get(migrationId), migrationsApi.results(migrationId)])
      .then(([migration, results]) => setState({ migration, results }))
      .catch((err) => setError(describeError(err)))
  }, [migrationId])

  if (error) return <Alert variant="error">{error}</Alert>
  if (!state.results) return <Spinner label="Loading verification runs" />

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Verification runs</h1>
          <p className="text-sm text-slate-500">
            {state.migration.title} · {state.results.length} run(s)
          </p>
        </div>
        <Link to={`/migrations/${migrationId}`} className="btn">
          Back to migration
        </Link>
      </header>

      {state.results.length === 0 ? (
        <p className="text-sm text-slate-500">No verification has been run for this migration yet.</p>
      ) : (
        state.results
          .slice()
          .reverse()
          .map((result) => (
            <section key={result.id} className="space-y-3">
              <h2 className="text-sm font-semibold text-slate-300">
                Run #{result.attempt_number + 1} · {new Date(result.created_at).toLocaleString()}
              </h2>
              <VerificationSummary
                result={result}
                sourceLanguage={state.migration.source_language}
                targetLanguage={state.migration.target_language}
              />
              <TestResultTable results={result.test_results} />
            </section>
          ))
      )}
    </div>
  )
}
