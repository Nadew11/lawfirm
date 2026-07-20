import { useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import heroImage from '../assets/landing-hero.png'
import './Login.css'

function ArrowIcon({ back = false }) {
  return (
    <svg className={back ? 'staff-arrow back' : 'staff-arrow'} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12h13M13 6l6 6-6 6" />
    </svg>
  )
}

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)

    if (!email.trim() || !password) {
      setError('Enter both your staff email and password.')
      return
    }

    setLoading(true)
    const { error: authErr } = await supabase.auth.signInWithPassword({
      email: email.trim(),
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
    <main className="staff-login-page">
      <section className="staff-login-visual">
        <img src={heroImage} alt="Sunlit columns in a courthouse corridor" />
        <div className="staff-visual-overlay" />

        <a className="staff-brand" href="#" aria-label="Alder and Stone home">
          <span className="staff-monogram">A<span>S</span></span>
          <span className="staff-brand-copy">
            <strong>Alder & Stone</strong>
            <small>Attorneys at Law</small>
          </span>
        </a>

        <div className="staff-visual-message">
          <p>Private staff access</p>
          <blockquote>Prepared counsel begins with a clear view of every matter.</blockquote>
          <span>Authorized personnel only</span>
        </div>
      </section>

      <section className="staff-login-panel">
        <div className="staff-panel-topbar">
          <a href="#"><ArrowIcon back /> Firm website</a>
          <span><i /> Secure portal</span>
        </div>

        <div className="staff-login-content">
          <p className="staff-eyebrow">Staff portal</p>
          <h1>Welcome back.</h1>
          <p className="staff-login-subtitle">Sign in with your authorized firm account to access matters and client intake records.</p>

          {error && <div className="staff-login-error" role="alert"><span>!</span>{error}</div>}

          <form className="staff-login-form" onSubmit={handleSubmit} noValidate>
            <label className="staff-login-field">
              <span>Email address</span>
              <input
                type="email"
                value={email}
                onChange={(e) => { setEmail(e.target.value); if (error) setError(null) }}
                autoComplete="email"
                autoFocus
                placeholder="name@firm.com"
              />
            </label>

            <label className="staff-login-field">
              <span>Password</span>
              <div className="staff-password-input">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => { setPassword(e.target.value); if (error) setError(null) }}
                  autoComplete="current-password"
                  placeholder="Enter your password"
                />
                <button type="button" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? 'Hide password' : 'Show password'}>
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
            </label>

            <div className="staff-login-support">
              <span>Having trouble signing in?</span>
              <a href="mailto:support@alderstone.demo">Contact administrator</a>
            </div>

            <button type="submit" className="staff-login-submit" disabled={loading}>
              {loading ? <><i className="staff-login-spinner" /> Verifying account</> : <>Sign in securely <ArrowIcon /></>}
            </button>
          </form>

          <div className="staff-security-note">
            <span>✓</span>
            <p><strong>Protected access</strong>Your session and credentials are encrypted. Never share your account with another person.</p>
          </div>
        </div>

        <footer className="staff-login-footer">
          <span>© 2026 Alder & Stone</span>
          <span>Confidential firm system</span>
        </footer>
      </section>
    </main>
  )
}
