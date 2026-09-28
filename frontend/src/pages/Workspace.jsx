import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Alert from '../components/Alert.jsx'
import CorrectionHistory from '../components/CorrectionHistory.jsx'
import EditorPanel from '../components/EditorPanel.jsx'
import Spinner from '../components/Spinner.jsx'
import TestCaseList from '../components/TestCaseList.jsx'
import TestResultTable from '../components/TestResultTable.jsx'
import VerificationSummary from '../components/VerificationSummary.jsx'
import { describeError } from '../api/client.js'
import { migrationsApi, systemApi } from '../api/endpoints.js'
import { SAMPLES } from '../data/samples.js'

const TABS = ['Test cases', 'Verification', 'Corrections']

export default function Workspace() {
  const { migrationId: routeMigrationId } = useParams()
  const navigate = useNavigate()

  const [languages, setLanguages] = useState([])
  const [migrationId, setMigrationId] = useState(routeMigrationId ? Number(routeMigrationId) : null)
  const [sourceLanguage, setSourceLanguage] = useState('java')
  const [targetLanguage, setTargetLanguage] = useState('python')
  const [sourceCode, setSourceCode] = useState(SAMPLES[0].code)
  const [migratedCode, setMigratedCode] = useState('')
  const [testCases, setTestCases] = useState([])
  const [result, setResult] = useState(null)
  const [corrections, setCorrections] = useState([])
  const [migrationStatus, setMigrationStatus] = useState('draft')
  const [validation, setValidation] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [tab, setTab] = useState(TABS[0])

  const monacoFor = useCallback(
    (key) => languages.find((item) => item.key === key)?.monaco_id || key,
    [languages],
  )
  const extensionFor = useCallback((key) => {
    const map = { python: 'py', javascript: 'js', java: 'java', cpp: 'cpp', go: 'go' }
    return map[key] || 'txt'
  }, [])

  useEffect(() => {
    systemApi.languages().then(setLanguages).catch(() => setLanguages([]))
  }, [])

  const applyMigration = useCallback((migration) => {
    setMigrationId(migration.id)
    setSourceLanguage(migration.source_language)
    setTargetLanguage(migration.target_language)
    setSourceCode(migration.source_code || '')
    setMigratedCode(migration.migrated_code || '')
    setTestCases(migration.test_cases || [])
    setCorrections(migration.correction_attempts || [])
    setMigrationStatus(migration.status)
    const results = migration.verification_results || []
    setResult(results.length ? results[results.length - 1] : null)
  }, [])

  useEffect(() => {
    if (!routeMigrationId) return
    migrationsApi
      .get(routeMigrationId)
      .then(applyMigration)
      .catch((err) => setError(describeError(err)))
  }, [routeMigrationId, applyMigration])

  const ensureMigration = useCallback(async () => {
    if (migrationId) {
      await migrationsApi.update(migrationId, {
        source_code: sourceCode,
        source_language: sourceLanguage,
        target_language: targetLanguage,
      })
      return migrationId
    }
    const created = await migrationsApi.create({
      title: `${sourceLanguage} → ${targetLanguage}`,
      source_language: sourceLanguage,
      target_language: targetLanguage,
      source_code: sourceCode,
    })
    setMigrationId(created.id)
    navigate(`/workspace/${created.id}`, { replace: true })
    return created.id
  }, [migrationId, navigate, sourceCode, sourceLanguage, targetLanguage])

  const run = useCallback(
    async (label, action) => {
      setBusy(label)
      setError('')
      setNotice('')
      try {
        await action()
      } catch (err) {
        setError(describeError(err))
      } finally {
        setBusy('')
      }
    },
    [],
  )

  const handleMigrate = () =>
    run('Migrating', async () => {
      const id = await ensureMigration()
      const migration = await migrationsApi.migrate(id, {
        source_code: sourceCode,
        source_language: sourceLanguage,
        target_language: targetLanguage,
      })
      applyMigration(migration)
      setValidation(null)
      setNotice('Migration completed. Generate tests to verify behavior.')
    })

  const handleValidate = () =>
    run('Validating', async () => {
      const id = await ensureMigration()
      const response = await migrationsApi.validate(id, { migrated_code: migratedCode })
      setValidation(response)
    })

  const handleGenerateTests = () =>
    run('Generating tests', async () => {
      const id = await ensureMigration()
      const cases = await migrationsApi.generateTests(id, {})
      setTestCases(cases)
      setTab('Test cases')
      setNotice(`${cases.length} test cases generated; reference outputs came from your original program.`)
    })

  const handleVerify = () =>
    run('Verifying', async () => {
      const id = await ensureMigration()
      const response = await migrationsApi.verify(id, { migrated_code: migratedCode })
      setResult(response.result)
      setMigrationStatus(response.migration_status)
      setTab('Verification')
    })

  const handleFix = () =>
    run('Fixing with AI', async () => {
      const id = await ensureMigration()
      const response = await migrationsApi.fix(id, {})
      setMigratedCode(response.migrated_code || '')
      setCorrections((current) => [...current, ...response.corrections])
      setResult(response.final_result)
      setMigrationStatus(response.migration_status)
      setTab('Corrections')
      setNotice(`AI used ${response.attempts_used} correction attempt(s).`)
    })

  const loadSample = (sampleId) => {
    const sample = SAMPLES.find((item) => item.id === sampleId)
    if (!sample) return
    setMigrationId(null)
    navigate('/workspace', { replace: true })
    setSourceLanguage(sample.sourceLanguage)
    setTargetLanguage(sample.targetLanguage)
    setSourceCode(sample.code)
    setMigratedCode('')
    setTestCases([])
    setResult(null)
    setCorrections([])
    setValidation(null)
    setMigrationStatus('draft')
  }

  const canVerify = useMemo(
    () => Boolean(migratedCode.trim()) && testCases.length > 0,
    [migratedCode, testCases],
  )
  const canFix = Boolean(result) && result?.overall_status !== 'PASS'

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Migration workspace</h1>
          <p className="text-sm text-slate-500">
            {migrationId ? `Migration #${migrationId} · ${migrationStatus}` : 'Unsaved migration'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Load sample"
            className="rounded border border-surface-600 bg-surface-900 px-2 py-1.5 text-xs text-slate-300"
            defaultValue=""
            onChange={(event) => loadSample(event.target.value)}
          >
            <option value="" disabled>
              Load sample…
            </option>
            {SAMPLES.map((sample) => (
              <option key={sample.id} value={sample.id}>
                {sample.name}
              </option>
            ))}
          </select>
          <button type="button" className="btn btn-primary" onClick={handleMigrate} disabled={Boolean(busy)}>
            Migrate
          </button>
          <button type="button" className="btn" onClick={handleValidate} disabled={Boolean(busy) || !migratedCode}>
            Validate
          </button>
          <button type="button" className="btn" onClick={handleGenerateTests} disabled={Boolean(busy)}>
            Generate tests
          </button>
          <button type="button" className="btn" onClick={handleVerify} disabled={Boolean(busy) || !canVerify}>
            Run verification
          </button>
          <button type="button" className="btn" onClick={handleFix} disabled={Boolean(busy) || !canFix}>
            Fix with AI
          </button>
        </div>
      </header>

      {busy ? <Spinner label={`${busy}…`} /> : null}
      {error ? (
        <Alert variant="error" title="Operation failed">
          {error}
        </Alert>
      ) : null}
      {notice ? <Alert variant="info">{notice}</Alert> : null}
      {validation ? (
        <Alert variant={validation.compilation_status === 'PASS' ? 'success' : 'error'} title={`Compilation ${validation.compilation_status}`}>
          {validation.error}
        </Alert>
      ) : null}

      <div className="grid min-h-[420px] flex-1 gap-4 lg:grid-cols-2">
        <EditorPanel
          title="Source code"
          language={sourceLanguage}
          monacoLanguage={monacoFor(sourceLanguage)}
          languages={languages}
          onLanguageChange={setSourceLanguage}
          value={sourceCode}
          onChange={setSourceCode}
          extension={extensionFor(sourceLanguage)}
        />
        <EditorPanel
          title="Migrated code"
          language={targetLanguage}
          monacoLanguage={monacoFor(targetLanguage)}
          languages={languages}
          onLanguageChange={setTargetLanguage}
          value={migratedCode}
          onChange={setMigratedCode}
          extension={extensionFor(targetLanguage)}
        />
      </div>

      <section className="card">
        <nav className="mb-4 flex gap-2 border-b border-surface-800 pb-2">
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
        {tab === 'Test cases' ? <TestCaseList testCases={testCases} /> : null}
        {tab === 'Verification' ? (
          result ? (
            <div className="space-y-4">
              <VerificationSummary
                result={result}
                sourceLanguage={sourceLanguage}
                targetLanguage={targetLanguage}
                migrationStatus={migrationStatus}
              />
              <TestResultTable results={result.test_results} />
            </div>
          ) : (
            <p className="text-sm text-slate-500">Run verification to compare real program behavior.</p>
          )
        ) : null}
        {tab === 'Corrections' ? <CorrectionHistory attempts={corrections} /> : null}
      </section>
    </div>
  )
}
