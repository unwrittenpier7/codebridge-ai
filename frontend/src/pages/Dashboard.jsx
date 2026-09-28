import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Alert from '../components/Alert.jsx'
import Spinner from '../components/Spinner.jsx'
import StatCard from '../components/StatCard.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { describeError } from '../api/client.js'
import { migrationsApi } from '../api/endpoints.js'

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    migrationsApi.stats().then(setStats).catch((err) => setError(describeError(err)))
  }, [])

  if (error) return <Alert variant="error">{error}</Alert>
  if (!stats) return <Spinner label="Loading dashboard" />

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Dashboard</h1>
          <p className="text-sm text-slate-500">Migration and behavioral verification overview.</p>
        </div>
        <Link to="/workspace" className="btn btn-primary">
          New migration
        </Link>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total migrations" value={stats.total_migrations} />
        <StatCard label="Verified (PASS)" value={stats.successful_migrations} />
        <StatCard label="Partial" value={stats.partial_migrations} hint={`${stats.failed_migrations} failed`} />
        <StatCard
          label="Avg. verification score"
          value={`${stats.average_verification_score}%`}
          hint="Mean behavioral match across verified migrations"
        />
      </div>

      <section className="card">
        <h2 className="mb-3 text-sm font-semibold text-slate-200">Recent migrations</h2>
        {stats.recent_migrations.length === 0 ? (
          <p className="text-sm text-slate-500">
            Nothing yet — <Link to="/workspace" className="text-accent">start your first migration</Link>.
          </p>
        ) : (
          <ul className="divide-y divide-surface-800">
            {stats.recent_migrations.map((migration) => (
              <li key={migration.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <div>
                  <Link to={`/migrations/${migration.id}`} className="text-sm text-slate-200 hover:text-accent">
                    {migration.title}
                  </Link>
                  <p className="text-xs text-slate-500">
                    {migration.source_language} → {migration.target_language} ·{' '}
                    {new Date(migration.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-slate-400">
                    {migration.latest_behavior_match ?? '—'}
                    {migration.latest_behavior_match != null ? '%' : ''}
                  </span>
                  <StatusBadge status={migration.latest_overall_status || migration.status} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
