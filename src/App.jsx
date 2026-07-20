import { useState, useEffect } from 'react'
import { supabase } from './lib/supabaseClient'
import IntakeForm from './pages/IntakeForm'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import LandingPage from './pages/LandingPage'

function getHash() {
  return window.location.hash.replace('#', '') || ''
}

function App() {
  const [page, setPage] = useState(getHash)
  const [session, setSession] = useState(null)
  const [authReady, setAuthReady] = useState(false)

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session: s } }) => {
      setSession(s)
      setAuthReady(true)
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, s) => {
        setSession(s)
      },
    )

    return () => subscription.unsubscribe()
  }, [])

  useEffect(() => {
    function onHashChange() {
      setPage(getHash())
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  if (page === 'login') {
    return <Login />
  }

  if (page === 'intake') {
    return <IntakeForm />
  }

  if (page === 'dashboard') {
    if (!authReady) return null
    if (!session) {
      window.location.hash = '#login'
      return null
    }
    return <Dashboard session={session} />
  }

  return <LandingPage />
}

export default App
