import { useEffect, useState } from 'react'
import { systemApi } from '../api/endpoints.js'

function Dot({ ok }) {
  return <span className={`h-2 w-2 rounded-full ${ok ? 'bg-pass' : 'bg-fail'}`} />
}

/** Surfaces missing AI keys / unavailable Docker instead of silently faking results. */
export default function HealthIndicator() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    systemApi.health().then(setHealth).catch(() => setHealth(null))
  }, [])

  if (!health) return null

  return (
    <div className="rounded-md border border-surface-700 bg-surface-800 p-2 text-xs text-slate-400">
      <p className="mb-1 font-semibold uppercase tracking-wide text-slate-500">Services</p>
      <p className="flex items-center gap-2">
        <Dot ok={health.ai_configured} />
        AI: {health.ai_provider} {health.ai_configured ? '' : '(no key)'}
      </p>
      <p className="mt-1 flex items-center gap-2" title={health.docker_detail}>
        <Dot ok={health.docker_available} />
        Docker executor
      </p>
    </div>
  )
}
