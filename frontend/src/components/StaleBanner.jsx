/**
 * Warns that displayed results no longer describe the code in the editors.
 *
 * Without this, a PASS earned by an older version of the code would still read
 * as a PASS after the user edits either editor.
 */
export default function StaleBanner({ kind = 'verification', reasons = [], actionLabel, onAction }) {
  const label = kind === 'tests' ? 'Generated tests are out of date' : 'Verification result is out of date'
  const explanation =
    reasons.length > 0 ? `This was produced before ${reasons.join(' and ')}.` : 'The code changed since this ran.'

  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-sm text-warn"
    >
      <span>
        <strong className="font-semibold">{label}.</strong> {explanation}
      </span>
      {actionLabel && onAction ? (
        <button type="button" className="btn" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  )
}
