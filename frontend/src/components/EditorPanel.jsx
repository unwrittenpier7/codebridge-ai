import CodeEditor from './CodeEditor.jsx'

function IconButton({ onClick, title, children, disabled }) {
  return (
    <button type="button" className="btn px-2 py-1 text-xs" onClick={onClick} title={title} disabled={disabled}>
      {children}
    </button>
  )
}

export default function EditorPanel({
  title,
  language,
  monacoLanguage,
  languages = [],
  onLanguageChange,
  value,
  onChange,
  readOnly = false,
  extension = 'txt',
}) {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value || '')
    } catch {
      /* clipboard unavailable (e.g. insecure context) */
    }
  }

  const download = () => {
    const blob = new Blob([value || ''], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `codebridge-${title.toLowerCase().replace(/\s+/g, '-')}.${extension}`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-surface-700 bg-surface-900">
      <header className="flex items-center justify-between gap-2 border-b border-surface-700 bg-surface-800 px-3 py-2">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-slate-200">{title}</h2>
          <select
            aria-label={`${title} language`}
            className="rounded border border-surface-600 bg-surface-950 px-2 py-1 text-xs text-slate-300"
            value={language}
            onChange={(event) => onLanguageChange(event.target.value)}
          >
            {languages.map((item) => (
              <option key={item.key} value={item.key}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-1">
          <IconButton onClick={copy} title="Copy code">
            Copy
          </IconButton>
          <IconButton onClick={download} title="Download code">
            Download
          </IconButton>
          {!readOnly && onChange ? (
            <IconButton onClick={() => onChange('')} title="Clear editor">
              Clear
            </IconButton>
          ) : null}
        </div>
      </header>
      <div className="min-h-[320px] flex-1">
        <CodeEditor language={monacoLanguage} value={value} onChange={onChange} readOnly={readOnly} />
      </div>
    </section>
  )
}
