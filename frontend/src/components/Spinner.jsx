export default function Spinner({ label }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-400">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-surface-600 border-t-accent" />
      {label}
    </span>
  )
}
