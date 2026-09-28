import { Link } from 'react-router-dom'

const FEATURES = [
  {
    title: 'AI-powered migration',
    body: 'Translate whole programs between languages with an LLM that is prompted with real static analysis of your source.',
  },
  {
    title: 'Multi-language support',
    body: 'Python, JavaScript, Java, C++ and Go — each with its own compilation and execution container.',
  },
  {
    title: 'Automated testing',
    body: 'Test cases are generated from your code, then the expected output is produced by running your original program.',
  },
  {
    title: 'Behavioral verification',
    body: 'Both programs run in isolated sandboxes and their real outputs are compared. Compiling is not enough.',
  },
]

export default function Landing() {
  return (
    <div className="min-h-screen bg-surface-950">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <span className="text-lg font-semibold text-slate-100">
          CodeBridge <span className="text-accent">AI</span>
        </span>
        <nav className="flex items-center gap-2">
          <Link to="/login" className="btn">
            Log in
          </Link>
          <Link to="/register" className="btn btn-primary">
            Get started
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-6 pb-20">
        <section className="py-16">
          <p className="mb-3 font-mono text-sm uppercase tracking-[0.3em] text-accent">
            Convert. Test. Verify.
          </p>
          <h1 className="max-w-3xl text-4xl font-semibold leading-tight text-slate-100 md:text-5xl">
            Migrate source code between languages — and prove the behavior did not change.
          </h1>
          <p className="mt-5 max-w-2xl text-slate-400">
            CodeBridge AI migrates your program with an LLM, generates test cases, executes the
            original and the migrated program inside isolated Docker containers, and compares their
            real outputs to produce a behavioral match score.
          </p>
          <div className="mt-8 flex gap-3">
            <Link to="/register" className="btn btn-primary px-5 py-2">
              Start migrating
            </Link>
            <Link to="/login" className="btn px-5 py-2">
              I already have an account
            </Link>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          {FEATURES.map((feature) => (
            <article key={feature.title} className="card">
              <h2 className="text-base font-semibold text-slate-100">{feature.title}</h2>
              <p className="mt-2 text-sm text-slate-400">{feature.body}</p>
            </article>
          ))}
        </section>

        <section className="mt-12 card font-mono text-xs text-slate-400">
          <p className="mb-3 text-slate-500"># verification pipeline</p>
          <pre className="whitespace-pre-wrap">{`source code
  -> static analysis
  -> AI migration
  -> compilation / syntax validation
  -> test-case generation (reference outputs from the original program)
  -> docker execution of both programs
  -> output normalization + comparison
  -> behavior match %  ->  PASS / PARTIAL / FAILED / ERROR
  -> AI correction loop (max 3 attempts)`}</pre>
        </section>
      </main>
    </div>
  )
}
