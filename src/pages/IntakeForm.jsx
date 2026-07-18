import { useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import DocumentUpload from './DocumentUpload'
import './IntakeForm.css'

const MATTER_TYPES = ['Family Law', 'Contract', 'Estate Planning', 'Other']

export default function IntakeForm() {
  const [form, setForm] = useState({
    name: '',
    email: '',
    phone: '',
    matterType: '',
    description: '',
  })
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [finished, setFinished] = useState(false)
  const [matterId, setMatterId] = useState(null)
  const [submitError, setSubmitError] = useState(null)

  function handleChange(e) {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: null }))
    }
  }

  function validate() {
    const next = {}
    if (!form.name.trim()) next.name = 'Name is required.'
    if (!form.email.trim()) next.email = 'Email is required.'
    if (!form.matterType) next.matterType = 'Please select a matter type.'
    return next
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitError(null)

    const validationErrors = validate()
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors)
      return
    }

    setSubmitting(true)

    try {
      const { data: newMatterId, error: intakeErr } = await supabase.rpc('submit_intake', {
        client_name: form.name.trim(),
        client_email: form.email.trim(),
        client_phone: form.phone.trim() || null,
        selected_matter_type: form.matterType,
        matter_description: form.description.trim() || null,
      })

      if (intakeErr) throw intakeErr

      setMatterId(newMatterId)
      setSubmitted(true)
    } catch (err) {
      setSubmitError(err.message || 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (finished) {
    return (
      <div className="intake-container">
        <div className="intake-success">
          <h1>Thank you!</h1>
          <p>Your intake form has been submitted. We will be in touch shortly.</p>
        </div>
      </div>
    )
  }

  if (submitted && matterId) {
    return (
      <div className="intake-container">
        <h1>Upload Documents</h1>
        <p className="intake-subtitle">
          Your information has been received. You may now upload any supporting documents.
        </p>
        <DocumentUpload matterId={matterId} supabase={supabase} />
        <button
          type="button"
          className="intake-submit upload-done-btn"
          onClick={() => setFinished(true)}
        >
          Done, finish
        </button>
      </div>
    )
  }

  return (
    <div className="intake-container">
      <h1>Client Intake</h1>
      <p className="intake-subtitle">
        Fill out the form below and our team will follow up with you.
      </p>

      {submitError && <div className="intake-error-banner">{submitError}</div>}

      <form className="intake-form" onSubmit={handleSubmit} noValidate>
        <label className="intake-label">
          Name <span className="required">*</span>
          <input
            type="text"
            name="name"
            value={form.name}
            onChange={handleChange}
            className={errors.name ? 'intake-input error' : 'intake-input'}
          />
          {errors.name && <span className="intake-field-error">{errors.name}</span>}
        </label>

        <label className="intake-label">
          Email <span className="required">*</span>
          <input
            type="email"
            name="email"
            value={form.email}
            onChange={handleChange}
            className={errors.email ? 'intake-input error' : 'intake-input'}
          />
          {errors.email && <span className="intake-field-error">{errors.email}</span>}
        </label>

        <label className="intake-label">
          Phone
          <input
            type="tel"
            name="phone"
            value={form.phone}
            onChange={handleChange}
            className="intake-input"
          />
        </label>

        <label className="intake-label">
          Matter Type <span className="required">*</span>
          <select
            name="matterType"
            value={form.matterType}
            onChange={handleChange}
            className={errors.matterType ? 'intake-input error' : 'intake-input'}
          >
            <option value="">— Select —</option>
            {MATTER_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          {errors.matterType && <span className="intake-field-error">{errors.matterType}</span>}
        </label>

        <label className="intake-label">
          Description
          <textarea
            name="description"
            value={form.description}
            onChange={handleChange}
            rows={4}
            className="intake-input"
          />
        </label>

        <button type="submit" className="intake-submit" disabled={submitting}>
          {submitting ? 'Submitting…' : 'Submit'}
        </button>
      </form>
    </div>
  )
}
