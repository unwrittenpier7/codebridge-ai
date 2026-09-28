import Editor from '@monaco-editor/react'

/** Monaco editor wrapper with the shared dark developer theme. */
export default function CodeEditor({ language, value, onChange, readOnly = false, height = '100%' }) {
  return (
    <Editor
      height={height}
      theme="vs-dark"
      language={language || 'plaintext'}
      value={value || ''}
      onChange={(next) => onChange && onChange(next ?? '')}
      options={{
        readOnly,
        fontSize: 13,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        automaticLayout: true,
        tabSize: 2,
        renderWhitespace: 'selection',
        smoothScrolling: true,
      }}
    />
  )
}
