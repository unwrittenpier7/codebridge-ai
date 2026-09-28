import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Alert from '../components/Alert.jsx'
import { describeError } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await login(form)
      navigate(location.state?.from || '/dashboard', { replace: true })
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={handleSubmit} className="card w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Log in</h1>
          <p className="text-sm text-slate-500">Access your migrations and verification history.</p>
        </div>
        {error ? <Alert variant="error">{error}</Alert> : null}
        <div>
          <label className="label" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            className="input"
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
          />
        </div>
        <div>
          <label className="label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            className="input"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
          />
        </div>
        <button type="submit" className="btn btn-primary w-full" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Log in'}
        </button>
        <p className="text-center text-xs text-slate-500">
          No account?{' '}
          <Link to="/register" className="text-accent">
            Register
          </Link>
        </p>
      </form>
    </div>
  )
}
