import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Alert from '../components/Alert.jsx'
import CodeEditor from '../components/CodeEditor.jsx'
import CorrectionHistory from '../components/CorrectionHistory.jsx'
import Spinner from '../components/Spinner.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import TestCaseList from '../components/TestCaseList.jsx'
import TestResultTable from '../components/TestResultTable.jsx'
import VerificationSummary from '../components/VerificationSummary.jsx'
import { describeError } from '../api/client.js'
import { migrationsApi } from '../api/endpoints.js'

const TABS = ['Code', 'Test cases', 'Verification', 'Corrections', 'Analysis']

export default function MigrationDetails() {
  const { migrationId } = useParams()
  const [migration, setMigration] = useState(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState(TABS[0])

  useEffect(() => {
    migrationsApi
      .get(migrationId)
      .then(setMigration)
      .catch((err) => setError(describeError(err)))
  }, [migrationId])

  if (error) return <Alert variant="error">{error}</Alert>
  if (!migration) return <Spinner label="Loading migration" />

  const results = migration.verification_results || []
  const latest = results.length ? results[results.length - 1] : null

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">{migration.title}</h1>
          <p className="text-sm text-slate-500">
            {migration.source_language} → {migration.target_language} ·{' '}
            {new Date(migration.created_at).toLocaleString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={latest?.overall_status || migration.status} />
          <Link to={`/workspace/${migration.id}`} className="btn">
            Open in workspace
          </Link>
          <Link to={`/migrations/${migration.id}/results`} className="btn">
            All runs
          </Link>
        </div>
      </header>

      <nav className="flex gap-2 border-b border-surface-800 pb-2">
        {TABS.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setTab(item)}
            className={`rounded px-3 py-1.5 text-sm ${
              tab === item ? 'bg-surface-800 text-slate-100' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {item}
          </button>
        ))}
      </nav>

      {tab === 'Code' ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card h-[460px] p-0">
            <p className="border-b border-surface-700 px-3 py-2 text-sm text-slate-300">
              Original ({migration.source_language})
            </p>
            <div className="h-[calc(100%-41px)]">
              <CodeEditor language={migration.source_language} value={migration.source_code} readOnly />
            </div>
          </div>
          <div className="card h-[460px] p-0">
            <p className="border-b border-surface-700 px-3 py-2 text-sm text-slate-300">
              Migrated ({migration.target_language})
            </p>
            <div className="h-[calc(100%-41px)]">
              <CodeEditor language={migration.target_language} value={migration.migrated_code || ''} readOnly />
            </div>
          </div>
        </div>
      ) : null}

      {tab === 'Test cases' ? (
        <div className="card">
          <TestCaseList testCases={migration.test_cases} />
        </div>
      ) : null}

      {tab === 'Verification' ? (
        latest ? (
          <div className="space-y-4">
            <VerificationSummary
              result={latest}
              sourceLanguage={migration.source_language}
              targetLanguage={migration.target_language}
              migrationStatus={migration.status}
            />
            <TestResultTable results={latest.test_results} />
          </div>
        ) : (
          <p className="text-sm text-slate-500">This migration has not been verified yet.</p>
        )
      ) : null}

      {tab === 'Corrections' ? (
        <div className="card">
          <CorrectionHistory attempts={migration.correction_attempts} />
        </div>
      ) : null}

      {tab === 'Analysis' ? (
        <div className="card">
          {migration.explanation ? (
            <>
              <h3 className="mb-2 text-sm font-semibold text-slate-200">Migration notes</h3>
              <p className="mb-4 whitespace-pre-wrap text-sm text-slate-400">{migration.explanation}</p>
            </>
          ) : null}
          <h3 className="mb-2 text-sm font-semibold text-slate-200">Static analysis</h3>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded bg-surface-950 p-3 font-mono text-xs text-slate-400">
            {JSON.stringify(migration.analysis || {}, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  )
}
