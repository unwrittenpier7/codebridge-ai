import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Alert from '../components/Alert.jsx'
import { describeError } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'

export default function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await register(form)
      navigate('/dashboard', { replace: true })
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
          <h1 className="text-xl font-semibold text-slate-100">Create an account</h1>
          <p className="text-sm text-slate-500">Migrations and verification runs are saved to your account.</p>
        </div>
        {error ? <Alert variant="error">{error}</Alert> : null}
        <div>
          <label className="label" htmlFor="name">
            Name
          </label>
          <input
            id="name"
            required
            className="input"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
        </div>
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
            minLength={8}
            className="input"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
          />
          <p className="mt-1 text-xs text-slate-500">At least 8 characters.</p>
        </div>
        <button type="submit" className="btn btn-primary w-full" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Register'}
        </button>
        <p className="text-center text-xs text-slate-500">
          Already registered?{' '}
          <Link to="/login" className="text-accent">
            Log in
          </Link>
        </p>
      </form>
    </div>
  )
}
