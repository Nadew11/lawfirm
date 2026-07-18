import { useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import './Login.css'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)

    const { error: authErr } = await supabase.auth.signInWithPassword({
      email,
      password,
    })

    if (authErr) {
      setError(authErr.message)
      setLoading(false)
      return
    }

    window.location.hash = '#dashboard'
  }

  return (
    <div className="login-container">
      <h1>Staff Login</h1>
      <p className="login-subtitle">Sign in to access the dashboard.</p>

      {error && <div className="login-error-banner">{error}</div>}

      <form className="login-form" onSubmit={handleSubmit} noValidate>
        <label className="login-label">
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="login-input"
            autoComplete="email"
          />
        </label>

        <label className="login-label">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="login-input"
            autoComplete="current-password"
          />
        </label>

        <button type="submit" className="login-submit" disabled={loading}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
