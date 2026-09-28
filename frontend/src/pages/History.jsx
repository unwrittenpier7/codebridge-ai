import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Alert from '../components/Alert.jsx'
import Spinner from '../components/Spinner.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { describeError } from '../api/client.js'
import { migrationsApi } from '../api/endpoints.js'

export default function History() {
  const [migrations, setMigrations] = useState(null)
  const [error, setError] = useState('')

  const load = () => {
    migrationsApi
      .list()
      .then(setMigrations)
      .catch((err) => setError(describeError(err)))
  }

  useEffect(load, [])

  const remove = async (id) => {
    try {
      await migrationsApi.remove(id)
      setMigrations((current) => current.filter((item) => item.id !== id))
    } catch (err) {
      setError(describeError(err))
    }
  }

  if (error) return <Alert variant="error">{error}</Alert>
  if (!migrations) return <Spinner label="Loading history" />

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-slate-100">Migration history</h1>
        <p className="text-sm text-slate-500">Every migration you ran, with its verification score.</p>
      </header>

      {migrations.length === 0 ? (
        <p className="text-sm text-slate-500">
          No migrations yet — <Link to="/workspace" className="text-accent">create one</Link>.
        </p>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="py-2 pr-3">Title</th>
                <th className="py-2 pr-3">Source</th>
                <th className="py-2 pr-3">Target</th>
                <th className="py-2 pr-3">Date</th>
                <th className="py-2 pr-3">Verification</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-800">
              {migrations.map((migration) => (
                <tr key={migration.id}>
                  <td className="py-2 pr-3">
                    <Link to={`/migrations/${migration.id}`} className="text-slate-200 hover:text-accent">
                      {migration.title}
                    </Link>
                  </td>
                  <td className="py-2 pr-3 text-slate-400">{migration.source_language}</td>
                  <td className="py-2 pr-3 text-slate-400">{migration.target_language}</td>
                  <td className="py-2 pr-3 text-slate-500">
                    {new Date(migration.created_at).toLocaleString()}
                  </td>
                  <td className="py-2 pr-3 text-slate-300">
                    {migration.latest_behavior_match != null ? `${migration.latest_behavior_match}%` : '—'}
                  </td>
                  <td className="py-2 pr-3">
                    <StatusBadge status={migration.latest_overall_status || migration.status} />
                  </td>
                  <td className="py-2 text-right">
                    <Link to={`/workspace/${migration.id}`} className="btn px-2 py-1 text-xs">
                      Open
                    </Link>
                    <button
                      type="button"
                      className="btn ml-2 px-2 py-1 text-xs"
                      onClick={() => remove(migration.id)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
