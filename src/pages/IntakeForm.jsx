import { useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import DocumentUpload from './DocumentUpload'
import './IntakeForm.css'

const MATTER_TYPES = [
  { value: 'Family Law', label: 'Family Law', detail: 'Divorce, custody, support, and related matters' },
  { value: 'Contract', label: 'Business & Contracts', detail: 'Agreements, disputes, and business guidance' },
  { value: 'Estate Planning', label: 'Estate Planning', detail: 'Wills, trusts, and legacy planning' },
  { value: 'Other', label: 'Something Else', detail: 'Tell us briefly what you need help with' },
]

const INITIAL_FORM = { name: '', email: '', phone: '', matterType: '', description: '' }

function ArrowIcon({ back = false }) {
  return (
    <svg className={back ? 'intake-arrow back' : 'intake-arrow'} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12h13M13 6l6 6-6 6" />
    </svg>
  )
}

export default function IntakeForm() {
  const [form, setForm] = useState(INITIAL_FORM)
  const [step, setStep] = useState(1)
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [matterId, setMatterId] = useState(null)
  const [submitError, setSubmitError] = useState(null)
  const [notificationStatus, setNotificationStatus] = useState('idle')
  const [uploadSummary, setUploadSummary] = useState({ total: 0, done: 0, active: 0 })

  function handleChange(e) {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
    if (errors[name]) setErrors((prev) => ({ ...prev, [name]: null }))
  }

  function validateContact() {
    const next = {}
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!form.name.trim()) next.name = 'Please enter your full name.'
    else if (form.name.trim().length > 200) next.name = 'Name must be 200 characters or fewer.'
    if (!form.email.trim()) next.email = 'Please enter your email address.'
    else if (!emailPattern.test(form.email.trim())) next.email = 'Enter a valid email address.'
    else if (form.email.trim().length > 320) next.email = 'Email must be 320 characters or fewer.'
    if (form.phone.length > 50) next.phone = 'Phone number must be 50 characters or fewer.'
    return next
  }

  function validateMatter() {
    const next = {}
    if (!form.matterType) next.matterType = 'Choose the option that best fits your matter.'
    if (!form.description.trim()) next.description = 'Please share a brief description of your situation.'
    else if (form.description.length < 20) next.description = 'Please provide at least a few sentences so we can understand how to help.'
    else if (form.description.length > 10000) next.description = 'Description must be 10,000 characters or fewer.'
    return next
  }

  function continueFromContact(e) {
    e.preventDefault()
    const next = validateContact()
    setErrors(next)
    if (Object.keys(next).length === 0) {
      setStep(2)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  async function submitMatter(e) {
    e.preventDefault()
    setSubmitError(null)
    const next = { ...validateContact(), ...validateMatter() }
    setErrors(next)
    if (Object.keys(next).length > 0) return

    setSubmitting(true)
    try {
      const { data: newMatterId, error: intakeErr } = await supabase.rpc('submit_intake', {
        target_firm_id: import.meta.env.VITE_FIRM_ID,
        client_name: form.name.trim(),
        client_email: form.email.trim(),
        client_phone: form.phone.trim() || null,
        selected_matter_type: form.matterType,
        matter_description: form.description.trim(),
      })
      if (intakeErr) throw intakeErr

      setMatterId(newMatterId)
      setStep(3)
      setNotificationStatus('sending')
      window.scrollTo({ top: 0, behavior: 'smooth' })

      const { data: emailData, error: emailError } = await supabase.functions.invoke('send-notification-email', {
        body: {
          matter_id: newMatterId,
          email_type: 'intake_confirmation',
          recipient_email: form.email.trim(),
          recipient_name: form.name.trim(),
          matter_type: form.matterType,
        },
      })
      setNotificationStatus(emailError || emailData?.error ? 'failed' : 'sent')
    } catch (err) {
      setSubmitError(err.message || 'We could not save your intake. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  function finishIntake() {
    if (uploadSummary.active > 0) return
    setStep(4)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <main className="client-intake-page">
      <header className="intake-header">
        <a className="intake-brand" href="#" aria-label="Alder and Stone home">
          <span className="intake-monogram">A<span>S</span></span>
          <span><strong>Alder & Stone</strong><small>Attorneys at Law</small></span>
        </a>
        <a className="intake-home-link" href="#"><ArrowIcon back /> Back to firm website</a>
      </header>

      <div className="intake-shell">
        <aside className="intake-context">
          <p className="intake-kicker">Confidential client intake</p>
          <h1>{step === 4 ? 'Thank you for reaching out.' : 'Let’s understand what brings you here.'}</h1>
          <p className="intake-context-copy">
            {step === 4
              ? 'Your information is now with our team. We’ll review it carefully and follow up soon.'
              : 'Share a few details so our attorneys can review your needs and determine how we may be able to help.'}
          </p>

          <div className="intake-assurance">
            <span>✓</span>
            <div><strong>Private and secure</strong><p>Your submission is encrypted and reviewed only by authorized firm staff.</p></div>
          </div>
          <div className="intake-assurance">
            <span>◷</span>
            <div><strong>About 5 minutes</strong><p>You’ll receive a confirmation after your information is submitted.</p></div>
          </div>

          <div className="intake-help">
            <p>Need help completing this form?</p>
            <a href="tel:+15550147820">(555) 014-7820</a>
            <span>Mon–Fri · 9:00 AM–5:00 PM</span>
          </div>
        </aside>

        <section className="intake-workspace" aria-live="polite">
          <Progress step={step} />

          {step === 1 && (
            <form className="intake-form" onSubmit={continueFromContact} noValidate>
              <div className="intake-step-heading">
                <span>Step 1 of 3</span>
                <h2>Your information</h2>
                <p>First, tell us how to reach you. Fields marked with an asterisk are required.</p>
              </div>

              <Field label="Full name" required error={errors.name} hint="As it appears on your legal documents">
                <input autoFocus type="text" name="name" autoComplete="name" maxLength={200} value={form.name} onChange={handleChange} />
              </Field>
              <div className="intake-field-grid">
                <Field label="Email address" required error={errors.email} hint="We’ll send your confirmation here">
                  <input type="email" name="email" autoComplete="email" maxLength={320} value={form.email} onChange={handleChange} />
                </Field>
                <Field label="Phone number" error={errors.phone} hint="Optional">
                  <input type="tel" name="phone" autoComplete="tel" maxLength={50} value={form.phone} onChange={handleChange} />
                </Field>
              </div>

              <div className="intake-form-footer">
                <p>By continuing, you acknowledge that submitting this form does not create an attorney-client relationship.</p>
                <button className="intake-next" type="submit">Continue <ArrowIcon /></button>
              </div>
            </form>
          )}

          {step === 2 && (
            <form className="intake-form" onSubmit={submitMatter} noValidate>
              <div className="intake-step-heading">
                <span>Step 2 of 3</span>
                <h2>About your matter</h2>
                <p>Provide enough context for an initial review. Please avoid including anything not relevant to your inquiry.</p>
              </div>

              <fieldset className={`matter-options ${errors.matterType ? 'has-error' : ''}`}>
                <legend>What type of help are you looking for? <span>*</span></legend>
                <div className="matter-option-grid">
                  {MATTER_TYPES.map((type) => (
                    <label className={form.matterType === type.value ? 'matter-option selected' : 'matter-option'} key={type.value}>
                      <input type="radio" name="matterType" value={type.value} checked={form.matterType === type.value} onChange={handleChange} />
                      <span className="matter-radio" />
                      <strong>{type.label}</strong>
                      <small>{type.detail}</small>
                    </label>
                  ))}
                </div>
                {errors.matterType && <span className="intake-field-error">{errors.matterType}</span>}
              </fieldset>

              <Field label="Tell us what happened" required error={errors.description} hint="Include relevant dates, parties, and what outcome you’re seeking.">
                <textarea name="description" rows={7} maxLength={10000} value={form.description} onChange={handleChange} />
                <span className="intake-character-count">{form.description.length.toLocaleString()} / 10,000</span>
              </Field>

              {submitError && <div className="intake-error-banner" role="alert">{submitError}</div>}

              <div className="intake-form-footer split">
                <button className="intake-back" type="button" onClick={() => setStep(1)}><ArrowIcon back /> Back</button>
                <button className="intake-next" type="submit" disabled={submitting}>
                  {submitting ? <><span className="intake-spinner" /> Submitting securely</> : <>Submit & continue <ArrowIcon /></>}
                </button>
              </div>
            </form>
          )}

          {step === 3 && matterId && (
            <div className="intake-form">
              <div className="intake-step-heading">
                <span>Step 3 of 3</span>
                <h2>Supporting documents</h2>
                <p>Add any documents that may help us understand your matter. You can also skip this and provide them later.</p>
              </div>
              <DocumentUpload matterId={matterId} supabase={supabase} onUploadsChange={setUploadSummary} />
              <div className="intake-form-footer upload-footer">
                <p>{uploadSummary.done > 0 ? `${uploadSummary.done} document${uploadSummary.done === 1 ? '' : 's'} uploaded securely.` : 'Documents are optional at this stage.'}</p>
                <button className="intake-next" type="button" onClick={finishIntake} disabled={uploadSummary.active > 0}>
                  {uploadSummary.active > 0 ? 'Uploading…' : 'Finish intake'} <ArrowIcon />
                </button>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="intake-complete">
              <div className="intake-complete-mark">✓</div>
              <p className="intake-kicker">Submission received</p>
              <h2>We’ll take it from here.</h2>
              <p className="intake-complete-copy">Our team will review your information and typically respond within one business day.</p>

              <div className="intake-reference-card">
                <div><span>Reference number</span><strong>{matterId?.split('-')[0].toUpperCase()}</strong></div>
                <div><span>Matter type</span><strong>{form.matterType}</strong></div>
                <div><span>Documents</span><strong>{uploadSummary.done || 'None uploaded'}</strong></div>
              </div>

              <div className={`intake-email-status ${notificationStatus}`}>
                <span>{notificationStatus === 'failed' ? '!' : notificationStatus === 'sent' ? '✓' : '…'}</span>
                <p>
                  <strong>{notificationStatus === 'failed' ? 'Your intake is saved.' : notificationStatus === 'sent' ? 'Confirmation email sent.' : 'Preparing your confirmation email.'}</strong>
                  {notificationStatus === 'failed'
                    ? ` We could not send email to ${form.email}, but this does not affect your submission.`
                    : notificationStatus === 'sent' ? ` Check ${form.email} for a copy of your confirmation.` : ' You may leave this page; your submission is already secure.'}
                </p>
              </div>

              <a className="intake-next intake-home-button" href="#">Return to firm website <ArrowIcon /></a>
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

function Progress({ step }) {
  const activeStep = Math.min(step, 3)
  return (
    <div className="intake-progress" aria-label={`Intake progress: step ${activeStep} of 3`}>
      {[1, 2, 3].map((item) => (
        <div className={item <= activeStep ? 'active' : ''} key={item}><span>{item < activeStep || step === 4 ? '✓' : item}</span><i /></div>
      ))}
    </div>
  )
}

function Field({ label, required, error, hint, children }) {
  return (
    <label className={`intake-field ${error ? 'has-error' : ''}`}>
      <span className="intake-field-label">{label} {required && <b>*</b>}</span>
      {children}
      {error ? <span className="intake-field-error">{error}</span> : hint && <span className="intake-field-hint">{hint}</span>}
    </label>
  )
}
