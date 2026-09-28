const VARIANTS = {
  error: 'border-fail/40 bg-fail/10 text-fail',
  warning: 'border-partial/40 bg-partial/10 text-partial',
  success: 'border-pass/40 bg-pass/10 text-pass',
  info: 'border-surface-600 bg-surface-800 text-slate-300',
}

export default function Alert({ variant = 'info', title, children }) {
  if (!children && !title) return null
  return (
    <div role="alert" className={`rounded-md border px-3 py-2 text-sm ${VARIANTS[variant]}`}>
      {title ? <p className="font-semibold">{title}</p> : null}
      {children ? <div className="whitespace-pre-wrap font-mono text-xs">{children}</div> : null}
    </div>
  )
}
