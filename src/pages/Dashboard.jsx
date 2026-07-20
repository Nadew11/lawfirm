import { useCallback, useEffect, useMemo, useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import './Dashboard.css'

const MATTER_FILTERS = ['All matters', 'New intake', 'Needs conflict check', 'Awaiting signature', 'Signed']

function Icon({ name }) {
  const paths = {
    grid: <><rect x="4" y="4" width="6" height="6" /><rect x="14" y="4" width="6" height="6" /><rect x="4" y="14" width="6" height="6" /><rect x="14" y="14" width="6" height="6" /></>,
    briefcase: <><rect x="3" y="7" width="18" height="13" rx="1" /><path d="M8 7V4h8v3M3 12h18M10 12v2h4v-2" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M18.2 9A7 7 0 0 0 6 6.6L4 9M5.8 15A7 7 0 0 0 18 17.4l2-2.4" /></>,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    expand: <><path d="M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5" /></>,
    collapse: <><path d="M4 9h5V4M20 9h-5V4M4 15h5v5M20 15h-5v5" /></>,
    arrow: <path d="M5 12h13M13 6l6 6-6 6" />,
    logout: <><path d="M10 4H5v16h5M14 8l4 4-4 4M8 12h10" /></>,
  }
  return <svg className="dash-icon" viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>
}

export default function Dashboard({ session }) {
  const [matters, setMatters] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('All matters')
  const [typeFilter, setTypeFilter] = useState('All practice areas')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [activeSection, setActiveSection] = useState('overview')

  const fetchMatters = useCallback(async () => {
    setLoading(true)
    setError(null)
    const { data, error: err } = await supabase
      .from('matters')
      .select('id, matter_type, status, esign_status, esign_reference, created_at, clients(name, email), conflict_checks(result, checked_at)')
      .order('created_at', { ascending: false })

    if (err) setError(err.message)
    else setMatters(data || [])
    setLoading(false)
  }, [])

  useEffect(() => { fetchMatters() }, [fetchMatters])

  const metrics = useMemo(() => ({
    active: matters.length,
    newIntakes: matters.filter((m) => m.status === 'intake_pending').length,
    conflicts: matters.filter((m) => !m.conflict_checks?.length).length,
    signatures: matters.filter((m) => m.esign_status === 'sent').length,
  }), [matters])

  const matterTypes = useMemo(() => [...new Set(matters.map((m) => m.matter_type).filter(Boolean))], [matters])

  const visibleMatters = useMemo(() => matters.filter((matter) => {
    const client = matter.clients || {}
    const query = search.trim().toLowerCase()
    const matchesSearch = !query || [client.name, client.email, matter.matter_type, matter.id]
      .some((value) => String(value || '').toLowerCase().includes(query))
    const matchesType = typeFilter === 'All practice areas' || matter.matter_type === typeFilter
    const matchesFilter = filter === 'All matters'
      || (filter === 'New intake' && matter.status === 'intake_pending')
      || (filter === 'Needs conflict check' && !matter.conflict_checks?.length)
      || (filter === 'Awaiting signature' && matter.esign_status === 'sent')
      || (filter === 'Signed' && matter.esign_status === 'signed')
    return matchesSearch && matchesType && matchesFilter
  }), [matters, search, filter, typeFilter])

  const selectedMatter = matters.find((matter) => matter.id === selectedId) || null
  const displayName = session?.user?.user_metadata?.full_name || session?.user?.email?.split('@')[0] || 'Counsel'

  function updateMatter(id, updates) {
    setMatters((current) => current.map((matter) => matter.id === id ? { ...matter, ...updates } : matter))
  }

  async function handleSignOut() {
    await supabase.auth.signOut()
    window.location.hash = '#login'
  }

  function navigateTo(section) {
    setActiveSection(section)
    setSidebarOpen(false)
    const target = section === 'matters' ? document.getElementById('matters-workspace') : document.getElementById('dashboard-overview')
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <main className="legal-dashboard">
      <aside className={sidebarOpen ? 'dash-sidebar open' : 'dash-sidebar'}>
        <div className="dash-brand">
          <span className="dash-monogram">A<span>S</span></span>
          <span><strong>Alder & Stone</strong><small>Legal workspace</small></span>
        </div>

        <nav className="dash-nav" aria-label="Dashboard navigation">
          <p>Workspace</p>
          <button type="button" className={activeSection === 'overview' ? 'active' : ''} onClick={() => navigateTo('overview')}><Icon name="grid" /> Overview</button>
          <button type="button" className={activeSection === 'matters' ? 'active' : ''} onClick={() => { setFilter('All matters'); navigateTo('matters') }}><Icon name="briefcase" /> Matters <span>{matters.length}</span></button>
        </nav>

        <div className="dash-sidebar-note">
          <span>Private system</span>
          <p>Client information is confidential. Access activity may be logged.</p>
        </div>

        <div className="dash-sidebar-user">
          <div className="dash-avatar">{displayName.slice(0, 2).toUpperCase()}</div>
          <div><strong>{displayName}</strong><span>{session?.user?.email}</span></div>
          <button type="button" onClick={handleSignOut} aria-label="Sign out"><Icon name="logout" /></button>
        </div>
      </aside>

      {sidebarOpen && <button className="dash-sidebar-scrim" type="button" onClick={() => setSidebarOpen(false)} aria-label="Close navigation" />}

      <section className="dash-main">
        <header className="dash-topbar">
          <button className="dash-menu-button" type="button" onClick={() => setSidebarOpen(true)} aria-label="Open navigation">☰</button>
          <div className="dash-topbar-title"><span>Attorney workspace</span><strong>{new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</strong></div>
          <div className="dash-topbar-account"><span className="dash-online"><i /> Secure session</span><div className="dash-avatar small">{displayName.slice(0, 2).toUpperCase()}</div></div>
        </header>

        <div className="dash-content" id="dashboard-overview">
          <div className="dash-page-heading">
            <div><p>Overview</p><h1>Good {dayPeriod()}, {displayName.split(' ')[0]}.</h1><span>Here’s what needs attention across your matters.</span></div>
            <button type="button" className="dash-refresh" onClick={fetchMatters} disabled={loading}><Icon name="refresh" /> {loading ? 'Refreshing' : 'Refresh data'}</button>
          </div>

          <section className="dash-metrics" aria-label="Matter overview">
            <MetricCard label="Total matters" value={metrics.active} detail="In the workspace" tone="navy" />
            <MetricCard label="New intakes" value={metrics.newIntakes} detail="Awaiting initial review" tone="brass" />
            <MetricCard label="Conflict checks" value={metrics.conflicts} detail="Require attention" tone="red" />
            <MetricCard label="Awaiting signature" value={metrics.signatures} detail="Engagements sent" tone="green" />
          </section>

          <section className="dash-matters-panel" id="matters-workspace">
            <div className="dash-panel-heading">
              <div><p>Client matters</p><h2>All matters</h2></div>
              <span>{visibleMatters.length} of {matters.length}</span>
            </div>

            <div className="dash-toolbar">
              <label className="dash-search"><Icon name="search" /><input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search client, email, or matter…" /></label>
              <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter by stage">{MATTER_FILTERS.map((item) => <option key={item}>{item}</option>)}</select>
              <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} aria-label="Filter by practice area"><option>All practice areas</option>{matterTypes.map((item) => <option key={item}>{item}</option>)}</select>
            </div>

            {error ? (
              <div className="dash-state error"><strong>Couldn’t load matters</strong><p>{error}</p><button type="button" onClick={fetchMatters}>Try again</button></div>
            ) : loading ? (
              <div className="dash-skeletons">{[1, 2, 3, 4].map((item) => <div key={item}><i /><span /><span /><span /></div>)}</div>
            ) : visibleMatters.length === 0 ? (
              <div className="dash-state"><strong>No matching matters</strong><p>Adjust your search or filters to see more results.</p><button type="button" onClick={() => { setSearch(''); setFilter('All matters'); setTypeFilter('All practice areas') }}>Clear filters</button></div>
            ) : (
              <MatterTable matters={visibleMatters} selectedId={selectedId} onSelect={setSelectedId} />
            )}
          </section>
        </div>
      </section>

      {selectedMatter && (
        <>
          <button className="dash-drawer-scrim" type="button" onClick={() => setSelectedId(null)} aria-label="Close matter" />
          <MatterDetail matter={selectedMatter} userEmail={session?.user?.email || ''} onClose={() => setSelectedId(null)} onMatterUpdate={updateMatter} />
        </>
      )}
    </main>
  )
}

function dayPeriod() {
  const hour = new Date().getHours()
  return hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'
}

function MetricCard({ label, value, detail, tone }) {
  return <article className={`dash-metric ${tone}`}><div><span>{label}</span><strong>{value}</strong></div><i /><p>{detail}</p></article>
}

function MatterTable({ matters, selectedId, onSelect }) {
  return (
    <div className="dash-table-wrap">
      <table className="dash-table">
        <thead><tr><th>Client</th><th>Practice area</th><th>Matter stage</th><th>E-sign</th><th>Received</th><th><span className="sr-only">Open</span></th></tr></thead>
        <tbody>{matters.map((matter) => {
          const client = matter.clients || {}
          return (
            <tr key={matter.id} className={selectedId === matter.id ? 'selected' : ''} onClick={() => onSelect(matter.id)}>
              <td><div className="dash-client-cell"><span>{(client.name || 'Client').slice(0, 2).toUpperCase()}</span><div><strong>{client.name || 'Unnamed client'}</strong><small>{client.email || 'No email'}</small></div></div></td>
              <td>{matter.matter_type || 'Other'}</td>
              <td><span className={`dash-stage ${!matter.conflict_checks?.length ? 'attention' : ''}`}>{!matter.conflict_checks?.length ? 'Conflict review' : formatStatus(matter.status)}</span></td>
              <td><span className={`esign-badge ${esignBadgeClass(matter.esign_status)}`}>{formatStatus(matter.esign_status || 'not_sent')}</span></td>
              <td>{new Date(matter.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</td>
              <td><button type="button" aria-label={`Open ${client.name || 'matter'}`}><Icon name="arrow" /></button></td>
            </tr>
          )
        })}</tbody>
      </table>
    </div>
  )
}

function MatterDetail({ matter, userEmail, onClose, onMatterUpdate }) {
  const matterId = matter.id
  const client = matter.clients || {}
  const [intakeData, setIntakeData] = useState(null)
  const [docs, setDocs] = useState([])
  const [conflictCheck, setConflictCheck] = useState(null)
  const [esignStatus, setEsignStatus] = useState(matter.esign_status || 'not_sent')
  const [esignRef, setEsignRef] = useState(matter.esign_reference || null)
  const [loading, setLoading] = useState(true)
  const [detailError, setDetailError] = useState(null)
  const [tab, setTab] = useState('overview')
  const [expanded, setExpanded] = useState(false)

  const loadDetail = useCallback(async () => {
    setLoading(true)
    setDetailError(null)
    const [intakeRes, docsRes, conflictRes] = await Promise.all([
      supabase.from('intake_forms').select('form_data, submitted_at').eq('matter_id', matterId).order('submitted_at', { ascending: false }).limit(1).maybeSingle(),
      supabase.from('documents').select('id, file_url, doc_type, uploaded_at').eq('matter_id', matterId).order('uploaded_at', { ascending: false }),
      supabase.from('conflict_checks').select('checked_by, result, notes, checked_at').eq('matter_id', matterId).order('checked_at', { ascending: false }).limit(1).maybeSingle(),
    ])
    const firstError = intakeRes.error || docsRes.error || conflictRes.error
    if (firstError) setDetailError(firstError.message)
    else {
      setIntakeData(intakeRes.data || null)
      setDocs(docsRes.data || [])
      setConflictCheck(conflictRes.data || null)
    }
    setLoading(false)
  }, [matterId])

  useEffect(() => { loadDetail() }, [loadDetail])
  useEffect(() => {
    function onKeyDown(e) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  async function openDocument(doc) {
    const marker = '/client-documents/'
    const markerIndex = doc.file_url?.indexOf(marker) ?? -1
    const storagePath = markerIndex >= 0 ? decodeURIComponent(doc.file_url.slice(markerIndex + marker.length)) : doc.file_url
    const { data, error } = await supabase.storage.from('client-documents').createSignedUrl(storagePath, 60)
    if (error) setDetailError(`Could not open document: ${error.message}`)
    else window.open(data.signedUrl, '_blank', 'noopener,noreferrer')
  }

  const canSendLetter = conflictCheck?.result === 'Clear' && esignStatus === 'not_sent'
  const tabs = ['overview', 'intake', 'documents', 'conflict', 'engagement']

  return (
    <aside className={expanded ? 'matter-drawer expanded' : 'matter-drawer'} aria-label={`${client.name || 'Client'} matter details`}>
      <header className="drawer-header">
        <div><p>Matter details</p><h2>{client.name || 'Unnamed client'}</h2><span>{matter.matter_type || 'Other'} · Ref {matter.id.slice(0, 8).toUpperCase()}</span></div>
        <div className="drawer-header-actions">
          <button type="button" onClick={() => setExpanded((current) => !current)} aria-label={expanded ? 'Restore matter panel' : 'Expand matter to full workspace'} title={expanded ? 'Restore panel' : 'Full workspace'}><Icon name={expanded ? 'collapse' : 'expand'} /></button>
          <button type="button" onClick={onClose} aria-label="Close matter details" title="Close"><Icon name="close" /></button>
        </div>
      </header>

      <div className="drawer-timeline">
        {['Intake', 'Conflict', 'Engagement', 'Active'].map((label, index) => {
          const complete = index === 0 || (index === 1 && conflictCheck) || (index === 2 && ['sent', 'signed'].includes(esignStatus)) || (index === 3 && esignStatus === 'signed')
          return <div className={complete ? 'complete' : ''} key={label}><span>{complete ? '✓' : index + 1}</span><small>{label}</small><i /></div>
        })}
      </div>

      <nav className="drawer-tabs">{tabs.map((item) => <button type="button" className={tab === item ? 'active' : ''} onClick={() => setTab(item)} key={item}>{item}<>{item === 'documents' && docs.length ? ` (${docs.length})` : ''}</></button>)}</nav>

      <div className="drawer-body">
        {loading ? <div className="drawer-loading"><i /><p>Loading matter details…</p></div> : detailError ? <div className="dash-state error"><strong>Something went wrong</strong><p>{detailError}</p><button type="button" onClick={loadDetail}>Try again</button></div> : (
          <>
            {tab === 'overview' && <OverviewTab matter={matter} client={client} intakeData={intakeData} conflictCheck={conflictCheck} esignStatus={esignStatus} docs={docs} onNavigate={setTab} />}
            {tab === 'intake' && <IntakeTab intakeData={intakeData} />}
            {tab === 'documents' && <DocumentsTab docs={docs} openDocument={openDocument} />}
            {tab === 'conflict' && <section className="drawer-section"><SectionHeading eyebrow="Risk review" title="Conflict check" />{conflictCheck ? <ConflictDisplay conflictCheck={conflictCheck} /> : <ConflictCheckForm matterId={matterId} userEmail={userEmail} clientName={client.name || ''} clientEmail={client.email || ''} matterType={matter.matter_type || ''} onSaved={(data) => { setConflictCheck(data); onMatterUpdate(matterId, { conflict_checks: [data] }) }} />}</section>}
            {tab === 'engagement' && <section className="drawer-section"><SectionHeading eyebrow="Client onboarding" title="Engagement letter" />{esignStatus === 'signed' ? <EngagementStatus status="signed" reference={esignRef} /> : esignStatus === 'sent' ? <EngagementStatus status="sent" reference={esignRef}><RefreshStatusButton matterId={matterId} signatureRequestId={esignRef} clientName={client.name || ''} clientEmail={client.email || ''} matterType={matter.matter_type || ''} onStatusUpdate={(newStatus) => { setEsignStatus(newStatus); onMatterUpdate(matterId, { esign_status: newStatus }) }} /></EngagementStatus> : canSendLetter ? <EngagementLetterButton matterId={matterId} clientName={client.name || ''} clientEmail={client.email || ''} matterType={matter.matter_type || ''} attorneyEmail={userEmail} onSent={(refId) => { setEsignStatus('sent'); setEsignRef(refId); onMatterUpdate(matterId, { esign_status: 'sent', esign_reference: refId }) }} /> : <div className="drawer-callout"><span>Next step</span><strong>{conflictCheck ? 'Resolve the conflict review' : 'Complete a conflict check first'}</strong><p>An engagement letter can be sent after the matter is cleared.</p></div>}</section>}
          </>
        )}
      </div>
    </aside>
  )
}

function SectionHeading({ eyebrow, title }) { return <div className="drawer-section-heading"><p>{eyebrow}</p><h3>{title}</h3></div> }

function OverviewTab({ matter, client, intakeData, conflictCheck, esignStatus, docs, onNavigate }) {
  return <div className="drawer-overview">
    <section className="drawer-section"><SectionHeading eyebrow="At a glance" title="Matter overview" /><dl className="overview-grid"><div><dt>Client email</dt><dd>{client.email || '—'}</dd></div><div><dt>Practice area</dt><dd>{matter.matter_type || '—'}</dd></div><div><dt>Received</dt><dd>{new Date(matter.created_at).toLocaleDateString()}</dd></div><div><dt>Matter status</dt><dd>{formatStatus(matter.status)}</dd></div></dl></section>
    <section className="drawer-section"><SectionHeading eyebrow="Workflow" title="Required actions" /><div className="action-list"><ActionRow complete={Boolean(intakeData)} label="Review client intake" action="intake" onNavigate={onNavigate} /><ActionRow complete={Boolean(conflictCheck)} label="Complete conflict check" action="conflict" onNavigate={onNavigate} /><ActionRow complete={['sent', 'signed'].includes(esignStatus)} label="Send engagement letter" action="engagement" onNavigate={onNavigate} /><ActionRow complete={esignStatus === 'signed'} label="Client signature received" action="engagement" onNavigate={onNavigate} /></div></section>
    <section className="drawer-section"><SectionHeading eyebrow="Files" title={`${docs.length} document${docs.length === 1 ? '' : 's'} on file`} /><button className="drawer-text-button" type="button" onClick={() => onNavigate('documents')}>Review documents <Icon name="arrow" /></button></section>
  </div>
}

function ActionRow({ complete, label, action, onNavigate }) { return <button type="button" onClick={() => onNavigate(action)}><span className={complete ? 'complete' : ''}>{complete ? '✓' : '·'}</span><strong>{label}</strong><small>{complete ? 'Complete' : 'Needs attention'}</small><Icon name="arrow" /></button> }

function IntakeTab({ intakeData }) {
  return <section className="drawer-section"><SectionHeading eyebrow="Submitted information" title="Client intake" />{intakeData ? <><dl className="drawer-intake-list">{Object.entries(intakeData.form_data || {}).map(([key, value]) => <div key={key}><dt>{formatStatus(key)}</dt><dd>{String(value || '—')}</dd></div>)}</dl><p className="dash-meta">Submitted {new Date(intakeData.submitted_at).toLocaleString()}</p></> : <div className="drawer-empty">No intake form data is available.</div>}</section>
}

function DocumentsTab({ docs, openDocument }) {
  return <section className="drawer-section"><SectionHeading eyebrow="Secure files" title={`Documents (${docs.length})`} />{docs.length ? <ul className="drawer-doc-list">{docs.map((doc) => <li key={doc.id}><span>{doc.file_url?.toLowerCase().endsWith('.pdf') ? 'PDF' : 'FILE'}</span><div><strong>{decodeURIComponent(doc.file_url?.split('/').pop() || 'Document')}</strong><small>{doc.doc_type} · {new Date(doc.uploaded_at).toLocaleDateString()}</small></div><button type="button" onClick={() => openDocument(doc)}>Open <Icon name="arrow" /></button></li>)}</ul> : <div className="drawer-empty">No documents have been uploaded for this matter.</div>}</section>
}

function ConflictDisplay({ conflictCheck }) { return <div className="conflict-display"><span className={`conflict-result-badge ${badgeClass(conflictCheck.result)}`}>{conflictCheck.result}</span>{conflictCheck.notes && <p className="conflict-notes">{conflictCheck.notes}</p>}<p className="dash-meta">Checked by {conflictCheck.checked_by} on {new Date(conflictCheck.checked_at).toLocaleString()}</p></div> }

function EngagementStatus({ status, reference, children }) { return <div className="engagement-status-card"><div><span className={`esign-badge ${esignBadgeClass(status)}`}>{formatStatus(status)}</span>{children}</div><p>Dropbox Sign request</p><code>{reference || 'Reference unavailable'}</code></div> }

function badgeClass(result) { return result === 'Clear' ? 'badge-clear' : result === 'Conflict found' ? 'badge-conflict' : 'badge-review' }
function esignBadgeClass(status) { return status === 'signed' ? 'esign-signed' : status === 'sent' ? 'esign-sent' : 'esign-not-sent' }
function formatStatus(value) { return String(value || '—').replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()) }

const CONFLICT_RESULTS = ['Clear', 'Conflict found', 'Needs review']

function ConflictCheckForm({ matterId, userEmail, clientName, clientEmail, matterType, onSaved }) {
  const [checkedBy, setCheckedBy] = useState(userEmail)
  const [result, setResult] = useState('Clear')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault(); setSaving(true); setError(null)
    const { data, error: err } = await supabase.from('conflict_checks').insert({ matter_id: matterId, checked_by: checkedBy, result, notes: notes || null }).select('checked_by, result, notes, checked_at').single()
    if (err) { setError(err.message); setSaving(false); return }
    if (result === 'Clear' && clientEmail) supabase.functions.invoke('send-notification-email', { body: { matter_id: matterId, email_type: 'conflict_clear', recipient_email: clientEmail, recipient_name: clientName, matter_type: matterType } }).catch(() => {})
    onSaved(data); setSaving(false)
  }

  return <form className="conflict-form" onSubmit={handleSubmit}>{error && <div className="dash-inline-error">{error}</div>}<label>Reviewed by<input value={checkedBy} onChange={(e) => setCheckedBy(e.target.value)} required /></label><label>Result<select value={result} onChange={(e) => setResult(e.target.value)}>{CONFLICT_RESULTS.map((item) => <option key={item}>{item}</option>)}</select></label><label>Internal notes<textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={5} placeholder="Document your review…" /></label><button type="submit" disabled={saving}>{saving ? 'Saving review…' : 'Save conflict check'}</button></form>
}

function EngagementLetterButton({ matterId, clientName, clientEmail, matterType, attorneyEmail, onSent }) {
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  async function handleSend() {
    setSending(true); setError(null)
    const { data, error: fnErr } = await supabase.functions.invoke('send-engagement-letter', { body: { matter_id: matterId, client_name: clientName, client_email: clientEmail, matter_type: matterType, attorney_name: attorneyEmail } })
    if (fnErr) { let message = fnErr.message || 'Failed to send engagement letter'; try { const body = await fnErr.context.json(); if (body?.error) message = body.error } catch { /* keep fallback */ } setError(message); setSending(false); return }
    if (data?.error) { setError(data.error); setSending(false); return }
    onSent(data.signature_request_id); setSending(false)
  }
  return <div className="esign-section"><div className="drawer-callout"><span>Ready to send</span><strong>Engagement letter</strong><p>Dropbox Sign will email the agreement to <b>{clientName}</b> at {clientEmail}.</p></div>{error && <div className="dash-inline-error">{error}</div>}<button type="button" className="esign-send-btn" onClick={handleSend} disabled={sending}>{sending ? 'Sending securely…' : 'Send engagement letter'} <Icon name="arrow" /></button></div>
}

function RefreshStatusButton({ matterId, signatureRequestId, clientName, clientEmail, matterType, onStatusUpdate }) {
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState(null)
  async function handleRefresh() {
    setChecking(true); setError(null)
    const { data, error: fnErr } = await supabase.functions.invoke('check-esign-status', { body: { signature_request_id: signatureRequestId, matter_id: matterId } })
    if (fnErr || data?.error) { setError(data?.error || fnErr.message || 'Failed to check status'); setChecking(false); return }
    if (data.esign_status === 'signed' && clientEmail) supabase.functions.invoke('send-notification-email', { body: { matter_id: matterId, email_type: 'engagement_signed', recipient_email: clientEmail, recipient_name: clientName, matter_type: matterType } }).catch(() => {})
    onStatusUpdate(data.esign_status); setChecking(false)
  }
  return <><button type="button" className="esign-refresh-btn" onClick={handleRefresh} disabled={checking}>{checking ? 'Checking…' : 'Refresh status'}</button>{error && <span className="esign-refresh-error">{error}</span>}</>
}
