import { useEffect, useState } from 'react'
import { systemApi } from '../api/endpoints.js'

function Dot({ ok }) {
  return <span className={`h-2 w-2 rounded-full ${ok ? 'bg-pass' : 'bg-fail'}`} />
}

/** Surfaces missing AI keys / unavailable Docker instead of silently faking results. */
export default function HealthIndicator() {
  const [health, setHealth] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let active = true
    systemApi
      .health()
      .then((data) => {
        if (active) setHealth(data)
      })
      .catch(() => {
        if (active) setFailed(true)
      })
    return () => {
      active = false
    }
  }, [])

  // A backend that cannot answer /health is itself a finding worth showing.
  if (failed) {
    return (
      <div className="rounded-md border border-fail/40 bg-fail/10 p-2 text-xs text-fail">
        <p className="mb-1 font-semibold uppercase tracking-wide">Services</p>
        <p>Backend unreachable.</p>
      </div>
    )
  }
  if (!health) return null

  return (
    <div className="rounded-md border border-surface-700 bg-surface-800 p-2 text-xs text-slate-400">
      <p className="mb-1 font-semibold uppercase tracking-wide text-slate-500">Services</p>
      <p className="flex items-center gap-2" title={health.ai_configured ? undefined : 'Set the provider API key in the backend environment'}>
        <Dot ok={health.ai_configured} />
        AI: {health.ai_provider} {health.ai_configured ? 'ready' : 'unavailable (no API key)'}
      </p>
      <p className="mt-1 flex items-center gap-2" title={health.docker_detail || undefined}>
        <Dot ok={health.docker_available} />
        Docker executor {health.docker_available ? 'ready' : 'unavailable'}
      </p>
      {!health.docker_available && health.docker_detail ? (
        <p className="mt-1 text-[11px] text-slate-500">{health.docker_detail}</p>
      ) : null}
    </div>
  )
}
