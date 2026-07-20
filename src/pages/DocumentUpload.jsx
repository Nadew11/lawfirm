import { useEffect, useRef, useState } from 'react'

const DOC_TYPES = ['ID', 'Supporting document', 'Other']
const MAX_FILE_SIZE = 10 * 1024 * 1024
const ALLOWED_TYPES = new Set(['application/pdf', 'image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'])

function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function safeExtension(file) {
  const extension = file.name.split('.').pop()?.toLowerCase().replace(/[^a-z0-9]/g, '')
  return extension ? `.${extension.slice(0, 8)}` : ''
}

export default function DocumentUpload({ matterId, supabase, onUploadsChange }) {
  const [uploads, setUploads] = useState([])
  const [docType, setDocType] = useState('Supporting document')
  const [queueError, setQueueError] = useState(null)
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => {
    onUploadsChange?.({
      total: uploads.length,
      done: uploads.filter((u) => u.status === 'done').length,
      active: uploads.filter((u) => u.status === 'uploading').length,
    })
  }, [uploads, onUploadsChange])

  function queueFiles(fileList) {
    const files = Array.from(fileList || [])
    if (!files.length) return
    const accepted = []
    const rejected = []

    files.forEach((file) => {
      if (!ALLOWED_TYPES.has(file.type)) rejected.push(`${file.name}: unsupported file type`)
      else if (file.size > MAX_FILE_SIZE) rejected.push(`${file.name}: larger than 10 MB`)
      else accepted.push({
        id: crypto.randomUUID(),
        file,
        docType,
        path: `${matterId}/${crypto.randomUUID()}${safeExtension(file)}`,
        status: 'pending',
        error: null,
        storageUploaded: false,
      })
    })

    if (accepted.length) setUploads((prev) => [...prev, ...accepted])
    setQueueError(rejected.length ? rejected.join('. ') : null)
    if (fileRef.current) fileRef.current.value = ''
  }

  async function uploadFile(id) {
    const entry = uploads.find((item) => item.id === id)
    if (!entry || entry.status === 'uploading' || entry.status === 'done') return
    let storageUploaded = entry.storageUploaded
    setUploads((prev) => prev.map((u) => u.id === id ? { ...u, status: 'uploading', error: null } : u))

    try {
      if (!storageUploaded) {
        const { error: storageErr } = await supabase.storage
          .from('client-documents')
          .upload(entry.path, entry.file, { contentType: entry.file.type, upsert: false })
        if (storageErr) throw storageErr
        storageUploaded = true
      }

      const { error: docErr } = await supabase.from('documents').insert({
        matter_id: matterId,
        file_url: entry.path,
        doc_type: entry.docType,
      })
      if (docErr) throw docErr
      setUploads((prev) => prev.map((u) => u.id === id ? { ...u, status: 'done', storageUploaded: true } : u))
    } catch (err) {
      setUploads((prev) => prev.map((u) => u.id === id
        ? { ...u, status: 'error', storageUploaded, error: err.message || 'Upload failed' }
        : u))
    }
  }

  function removeFile(id) {
    setUploads((prev) => prev.filter((u) => u.id !== id || u.status === 'uploading'))
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragging(false)
    queueFiles(e.dataTransfer.files)
  }

  return (
    <div className="upload-section">
      <div className="upload-type-row">
        <label htmlFor="document-type">Document category</label>
        <select id="document-type" value={docType} onChange={(e) => setDocType(e.target.value)}>
          {DOC_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
        </select>
      </div>

      <div
        className={dragging ? 'upload-dropzone dragging' : 'upload-dropzone'}
        onDragEnter={(e) => { e.preventDefault(); setDragging(true) }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <div className="upload-icon">↑</div>
        <strong>Drop documents here</strong>
        <p>or <button type="button" onClick={() => fileRef.current?.click()}>browse your files</button></p>
        <small>PDF, JPG, PNG, WEBP or HEIC · 10 MB maximum per file</small>
        <input ref={fileRef} type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.webp,.heic,.heif" onChange={(e) => queueFiles(e.target.files)} />
      </div>

      {queueError && <div className="upload-queue-error" role="alert">{queueError}</div>}

      {uploads.length > 0 && (
        <ul className="upload-list">
          {uploads.map((upload) => (
            <li className={`upload-row ${upload.status}`} key={upload.id}>
              <div className="upload-file-icon">{upload.file.type === 'application/pdf' ? 'PDF' : 'IMG'}</div>
              <div className="upload-file-info">
                <strong title={upload.file.name}>{upload.file.name}</strong>
                <span>{upload.docType} · {formatSize(upload.file.size)}</span>
                {upload.error && <small>{upload.error}</small>}
              </div>
              <div className="upload-actions">
                {upload.status === 'pending' && <button type="button" className="upload-action-btn" onClick={() => uploadFile(upload.id)}>Upload</button>}
                {upload.status === 'uploading' && <span className="upload-progress"><i /> Uploading</span>}
                {upload.status === 'done' && <span className="upload-complete">✓ Uploaded</span>}
                {upload.status === 'error' && <button type="button" className="upload-action-btn" onClick={() => uploadFile(upload.id)}>Retry</button>}
                {upload.status !== 'uploading' && upload.status !== 'done' && <button type="button" className="upload-remove" onClick={() => removeFile(upload.id)} aria-label={`Remove ${upload.file.name}`}>×</button>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
