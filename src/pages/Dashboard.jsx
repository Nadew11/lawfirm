import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabaseClient'
import './Dashboard.css'

export default function Dashboard({ session }) {
  const [matters, setMatters] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)

  useEffect(() => {
    fetchMatters()
  }, [])

  async function fetchMatters() {
    setLoading(true)
    const { data, error: err } = await supabase
      .from('matters')
      .select('id, matter_type, status, esign_status, esign_reference, created_at, clients(name, email)')
      .order('created_at', { ascending: false })

    if (err) {
      setError(err.message)
    } else {
      setMatters(data || [])
    }
    setLoading(false)
  }

  async function handleSignOut() {
    await supabase.auth.signOut()
    window.location.hash = '#login'
  }

  return (
    <div className="dash-container">
      <header className="dash-header">
        <h1>Matters Dashboard</h1>
        <div className="dash-user">
          <span className="dash-email">{session?.user?.email}</span>
          <button type="button" className="dash-sign-out" onClick={handleSignOut}>
            Sign out
          </button>
        </div>
      </header>

      {error && <div className="dash-error">{error}</div>}

      {loading ? (
        <p className="dash-loading">Loading matters…</p>
      ) : matters.length === 0 ? (
        <p className="dash-empty">No matters found.</p>
      ) : (
        <table className="dash-table">
          <thead>
            <tr>
              <th>Client</th>
              <th>Email</th>
              <th>Matter Type</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {matters.map((m) => (
              <MatterRow
                key={m.id}
                matter={m}
                isOpen={selectedId === m.id}
                onToggle={() => setSelectedId(selectedId === m.id ? null : m.id)}
                session={session}
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function MatterRow({ matter, isOpen, onToggle, session }) {
  const client = matter.clients || {}
  const created = new Date(matter.created_at).toLocaleDateString()

  return (
    <>
      <tr className={`dash-row ${isOpen ? 'open' : ''}`} onClick={onToggle}>
        <td>{client.name || '—'}</td>
        <td>{client.email || '—'}</td>
        <td>{matter.matter_type || '—'}</td>
        <td><span className="dash-status">{matter.status}</span></td>
        <td>{created}</td>
      </tr>
      {isOpen && (
        <tr className="dash-detail-row">
          <td colSpan={5}>
            <MatterDetail
              matter={matter}
              userEmail={session?.user?.email || ''}
            />
          </td>
        </tr>
      )}
    </>
  )
}

function MatterDetail({ matter, userEmail }) {
  const matterId = matter.id
  const client = matter.clients || {}

  const [intakeData, setIntakeData] = useState(null)
  const [docs, setDocs] = useState([])
  const [conflictCheck, setConflictCheck] = useState(null)
  const [esignStatus, setEsignStatus] = useState(matter.esign_status || 'not_sent')
  const [esignRef, setEsignRef] = useState(matter.esign_reference || null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function load() {
      const [intakeRes, docsRes, conflictRes] = await Promise.all([
        supabase
          .from('intake_forms')
          .select('form_data, submitted_at')
          .eq('matter_id', matterId)
          .order('submitted_at', { ascending: false })
          .limit(1)
          .maybeSingle(),
        supabase
          .from('documents')
          .select('id, file_url, doc_type, uploaded_at')
          .eq('matter_id', matterId)
          .order('uploaded_at', { ascending: false }),
        supabase
          .from('conflict_checks')
          .select('checked_by, result, notes, checked_at')
          .eq('matter_id', matterId)
          .order('checked_at', { ascending: false })
          .limit(1)
          .maybeSingle(),
      ])

      if (cancelled) return

      if (intakeRes.data) setIntakeData(intakeRes.data)
      if (conflictRes.data) setConflictCheck(conflictRes.data)
      setDocs(docsRes.data || [])
      setLoading(false)
    }

    load()
    return () => { cancelled = true }
  }, [matterId])

  if (loading) return <p className="dash-detail-loading">Loading details…</p>

  async function openDocument(doc) {
    const marker = '/client-documents/'
    const markerIndex = doc.file_url?.indexOf(marker) ?? -1
    const storagePath = markerIndex >= 0
      ? decodeURIComponent(doc.file_url.slice(markerIndex + marker.length))
      : doc.file_url

    const { data, error } = await supabase.storage
      .from('client-documents')
      .createSignedUrl(storagePath, 60)

    if (error) {
      window.alert(`Could not open document: ${error.message}`)
      return
    }

    window.open(data.signedUrl, '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="dash-detail">
      <div className="dash-detail-section">
        <h3>Intake Form</h3>
        {intakeData ? (
          <>
            <dl className="dash-dl">
              {Object.entries(intakeData.form_data || {}).map(([key, val]) => (
                <div key={key} className="dash-dl-row">
                  <dt>{key}</dt>
                  <dd>{String(val || '—')}</dd>
                </div>
              ))}
            </dl>
            <p className="dash-meta">
              Submitted {new Date(intakeData.submitted_at).toLocaleString()}
            </p>
          </>
        ) : (
          <p className="dash-empty">No intake form data.</p>
        )}
      </div>

      <div className="dash-detail-section">
        <h3>Documents ({docs.length})</h3>
        {docs.length > 0 ? (
          <ul className="dash-doc-list">
            {docs.map((d) => {
              const fileName = d.file_url?.split('/').pop() || 'file'
              return (
                <li key={d.id} className="dash-doc-item">
                  <button type="button" className="dash-doc-link" onClick={() => openDocument(d)}>
                    {decodeURIComponent(fileName)}
                  </button>
                  <span className="dash-doc-type">{d.doc_type}</span>
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="dash-empty">No documents uploaded.</p>
        )}
      </div>

      <div className="dash-detail-section">
        <h3>Conflict Check</h3>
        {conflictCheck ? (
          <div className="conflict-display">
            <span className={`conflict-result-badge ${badgeClass(conflictCheck.result)}`}>
              {conflictCheck.result}
            </span>
            {conflictCheck.notes && (
              <p className="conflict-notes">{conflictCheck.notes}</p>
            )}
            <p className="dash-meta">
              Checked by {conflictCheck.checked_by} on{' '}
              {new Date(conflictCheck.checked_at).toLocaleString()}
            </p>
          </div>
        ) : (
          <ConflictCheckForm
            matterId={matterId}
            userEmail={userEmail}
            onSaved={setConflictCheck}
          />
        )}
      </div>

      <div className="dash-detail-section">
        <h3>Engagement Letter</h3>
        {esignStatus === 'sent' ? (
          <div className="esign-sent-display">
            <span className="conflict-result-badge badge-clear">Sent</span>
            <p className="dash-meta">
              Signature request: <code>{esignRef}</code>
            </p>
          </div>
        ) : canSendLetter ? (
          <EngagementLetterButton
            matterId={matterId}
            clientName={client.name || ''}
            clientEmail={client.email || ''}
            matterType={matter.matter_type || ''}
            attorneyEmail={userEmail}
            onSent={(refId) => {
              setEsignStatus('sent')
              setEsignRef(refId)
            }}
          />
        ) : (
          <p className="dash-empty">
            {conflictCheck
              ? 'Conflict check must be "Clear" to send an engagement letter.'
              : 'Complete a conflict check first.'}
          </p>
        )}
      </div>
    </div>
  )
}

function badgeClass(result) {
  if (result === 'Clear') return 'badge-clear'
  if (result === 'Conflict found') return 'badge-conflict'
  return 'badge-review'
}

const CONFLICT_RESULTS = ['Clear', 'Conflict found', 'Needs review']

function ConflictCheckForm({ matterId, userEmail, onSaved }) {
  const [checkedBy, setCheckedBy] = useState(userEmail)
  const [result, setResult] = useState('Clear')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)

    const { data, error: err } = await supabase
      .from('conflict_checks')
      .insert({
        matter_id: matterId,
        checked_by: checkedBy,
        result,
        notes: notes || null,
      })
      .select('checked_by, result, notes, checked_at')
      .single()

    if (err) {
      setError(err.message)
      setSaving(false)
      return
    }

    onSaved(data)
  }

  return (
    <form className="conflict-form" onSubmit={handleSubmit}>
      {error && <div className="dash-error">{error}</div>}

      <label className="conflict-label">
        Checked by
        <input
          type="text"
          className="conflict-input"
          value={checkedBy}
          onChange={(e) => setCheckedBy(e.target.value)}
          required
        />
      </label>

      <label className="conflict-label">
        Result
        <select
          className="conflict-input"
          value={result}
          onChange={(e) => setResult(e.target.value)}
        >
          {CONFLICT_RESULTS.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      </label>

      <label className="conflict-label">
        Notes
        <textarea
          className="conflict-input conflict-textarea"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
        />
      </label>

      <button type="submit" className="conflict-submit" disabled={saving}>
        {saving ? 'Saving…' : 'Save conflict check'}
      </button>
    </form>
  )
}

function EngagementLetterButton({ matterId, clientName, clientEmail, matterType, attorneyEmail, onSent }) {
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)

  async function handleSend() {
    setSending(true)
    setError(null)

    const { data, error: fnErr } = await supabase.functions.invoke(
      'send-engagement-letter',
      {
        body: {
          matter_id: matterId,
          client_name: clientName,
          client_email: clientEmail,
          matter_type: matterType,
          attorney_name: attorneyEmail,
        },
      },
    )

    if (fnErr) {
      setError(fnErr.message || 'Failed to send engagement letter')
      setSending(false)
      return
    }

    if (data?.error) {
      setError(data.error)
      setSending(false)
      return
    }

    onSent(data.signature_request_id)
  }

  return (
    <div className="esign-section">
      <p className="esign-description">
        Send an engagement letter to <strong>{clientName}</strong> ({clientEmail}) for signing via Dropbox Sign.
      </p>
      {error && <div className="dash-error">{error}</div>}
      <button
        type="button"
        className="esign-send-btn"
        onClick={handleSend}
        disabled={sending}
      >
        {sending ? 'Sending…' : 'Send engagement letter'}
      </button>
    </div>
  )
}
