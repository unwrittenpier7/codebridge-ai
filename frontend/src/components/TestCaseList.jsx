export default function TestCaseList({ testCases = [] }) {
  if (!testCases.length) return <p className="text-sm text-slate-500">No test cases generated yet.</p>

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="py-2 pr-3">#</th>
            <th className="py-2 pr-3">Category</th>
            <th className="py-2 pr-3">Description</th>
            <th className="py-2 pr-3">Input</th>
            <th className="py-2 pr-3">Reference output</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-800">
          {testCases.map((testCase, index) => (
            <tr key={testCase.id} className="align-top">
              <td className="py-2 pr-3 text-slate-500">{index + 1}</td>
              <td className="py-2 pr-3 text-slate-400">{testCase.category}</td>
              <td className="py-2 pr-3 text-slate-300">{testCase.description}</td>
              <td className="py-2 pr-3">
                <pre className="max-w-xs overflow-auto whitespace-pre-wrap font-mono text-xs text-slate-400">
                  {testCase.input || '<empty>'}
                </pre>
              </td>
              <td className="py-2 pr-3">
                <pre className="max-w-xs overflow-auto whitespace-pre-wrap font-mono text-xs text-slate-400">
                  {testCase.expected_output || '<empty>'}
                </pre>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
