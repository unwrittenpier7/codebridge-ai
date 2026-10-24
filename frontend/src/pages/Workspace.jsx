import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Alert from '../components/Alert.jsx'
import CorrectionHistory from '../components/CorrectionHistory.jsx'
import EditorPanel from '../components/EditorPanel.jsx'
import Spinner from '../components/Spinner.jsx'
import StaleBanner from '../components/StaleBanner.jsx'
import TestCaseList from '../components/TestCaseList.jsx'
import TestResultTable from '../components/TestResultTable.jsx'
import VerificationSummary from '../components/VerificationSummary.jsx'
import { describeError } from '../api/client.js'
import { migrationsApi, systemApi } from '../api/endpoints.js'
import { useAsyncAction } from '../hooks/useAsyncAction.js'
import { SAMPLES } from '../data/samples.js'
import { describeStaleness, verificationSnapshot } from '../utils/staleness.js'

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
  const [tab, setTab] = useState(TABS[0])
  //: Editor state that the currently displayed result was produced from.
  const [verifiedSnapshot, setVerifiedSnapshot] = useState(null)
  //: Hash of the source program the displayed test cases came from.
  const [testsSourceFingerprint, setTestsSourceFingerprint] = useState(null)

  const { busy, error, notice, run, setError, setNotice, isBusy } = useAsyncAction()
  const cancelled = useRef(false)

  useEffect(() => {
    cancelled.current = false
    return () => {
      cancelled.current = true
    }
  }, [])

  const monacoFor = useCallback(
    (key) => languages.find((item) => item.key === key)?.monaco_id || key,
    [languages],
  )
  const extensionFor = useCallback((key) => {
    const map = {
      python: 'py',
      javascript: 'js',
      java: 'java',
      cpp: 'cpp',
      c: 'c',
      go: 'go',
    }
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
    const latest = results.length ? results[results.length - 1] : null
    setResult(latest)
    // The stored result knows the code it tested; treat that as the baseline so
    // a reload does not immediately (and wrongly) show a stale banner.
    setVerifiedSnapshot(
      latest
        ? verificationSnapshot({
            sourceCode: migration.source_code || '',
            migratedCode: migration.migrated_code || '',
            sourceLanguage: migration.source_language,
            targetLanguage: migration.target_language,
          })
        : null,
    )
    const cases = migration.test_cases || []
    setTestsSourceFingerprint(
      cases.length
        ? verificationSnapshot({
            sourceCode: migration.source_code || '',
            migratedCode: '',
            sourceLanguage: migration.source_language,
            targetLanguage: migration.target_language,
          }).sourceCode
        : null,
    )
  }, [])

  useEffect(() => {
    if (!routeMigrationId) return
    migrationsApi
      .get(routeMigrationId)
      .then(applyMigration)
      .catch((err) => setError(describeError(err)))
  }, [routeMigrationId, applyMigration, setError])

  const currentSnapshot = useMemo(
    () => verificationSnapshot({ sourceCode, migratedCode, sourceLanguage, targetLanguage }),
    [sourceCode, migratedCode, sourceLanguage, targetLanguage],
  )

  const resultStaleness = useMemo(
    () => describeStaleness(currentSnapshot, verifiedSnapshot),
    [currentSnapshot, verifiedSnapshot],
  )
  const testsAreStale = useMemo(
    () =>
      Boolean(testsSourceFingerprint) &&
      testsSourceFingerprint !== currentSnapshot.sourceCode,
    [testsSourceFingerprint, currentSnapshot.sourceCode],
  )

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

  const handleMigrate = () =>
    run('Migrating', async () => {
      const id = await ensureMigration()
      const migration = await migrationsApi.migrate(id, {
        source_code: sourceCode,
        source_language: sourceLanguage,
        target_language: targetLanguage,
      })
      if (cancelled.current) return
      applyMigration(migration)
      setValidation(null)
      setVerifiedSnapshot(null)
      setNotice('Migration completed. Generate tests to verify behavior.')
    })

  const handleValidate = () =>
    run('Validating', async () => {
      const id = await ensureMigration()
      const response = await migrationsApi.validate(id, { migrated_code: migratedCode })
      if (cancelled.current) return
      setValidation(response)
    })

  const handleGenerateTests = () =>
    run('Generating tests', async () => {
      const id = await ensureMigration()
      const cases = await migrationsApi.generateTests(id, {})
      if (cancelled.current) return
      setTestCases(cases)
      setTestsSourceFingerprint(currentSnapshot.sourceCode)
      setTab('Test cases')
      setNotice(
        `${cases.length} test cases generated; reference outputs came from your original program.`,
      )
    })

  const handleVerify = () =>
    run('Verifying', async () => {
      const id = await ensureMigration()
      const response = await migrationsApi.verify(id, { migrated_code: migratedCode })
      if (cancelled.current) return
      setResult(response.result)
      setVerifiedSnapshot(currentSnapshot)
      setMigrationStatus(response.migration_status)
      setTab('Verification')
    })

  const handleFix = () =>
    run('Fixing with AI', async () => {
      const id = await ensureMigration()
      const response = await migrationsApi.fix(id, {})
      if (cancelled.current) return
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
    setVerifiedSnapshot(null)
    setTestsSourceFingerprint(null)
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
          <button type="button" className="btn btn-primary" onClick={handleMigrate} disabled={isBusy}>
            Migrate
          </button>
          <button
            type="button"
            className="btn"
            onClick={handleValidate}
            disabled={isBusy || !migratedCode}
          >
            Validate
          </button>
          <button type="button" className="btn" onClick={handleGenerateTests} disabled={isBusy}>
            Generate tests
          </button>
          <button
            type="button"
            className="btn"
            onClick={handleVerify}
            disabled={isBusy || !canVerify}
            title={canVerify ? undefined : 'Generate tests and migrate first'}
          >
            Run verification
          </button>
          <button type="button" className="btn" onClick={handleFix} disabled={isBusy || !canFix}>
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
        <Alert
          variant={validation.compilation_status === 'PASS' ? 'success' : 'error'}
          title={`Compilation ${validation.compilation_status}`}
        >
          {validation.error}
        </Alert>
      ) : null}
      {result && resultStaleness.stale ? (
        <StaleBanner
          kind="verification"
          reasons={resultStaleness.reasons}
          actionLabel="Re-run verification"
          onAction={canVerify && !isBusy ? handleVerify : undefined}
        />
      ) : null}
      {testsAreStale ? (
        <StaleBanner
          kind="tests"
          reasons={['the source code changed']}
          actionLabel="Regenerate tests"
          onAction={!isBusy ? handleGenerateTests : undefined}
        />
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
        {tab === 'Test cases' ? (
          <TestCaseList testCases={testCases} stale={testsAreStale} />
        ) : null}
        {tab === 'Verification' ? (
          result ? (
            <div className="space-y-4">
              <VerificationSummary
                result={result}
                sourceLanguage={sourceLanguage}
                targetLanguage={targetLanguage}
                migrationStatus={migrationStatus}
                stale={resultStaleness.stale}
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
