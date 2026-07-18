import { useState, useRef } from 'react'

const DOC_TYPES = ['ID', 'Supporting document', 'Other']

export default function DocumentUpload({ matterId, supabase }) {
  const [uploads, setUploads] = useState([])
  const [docType, setDocType] = useState('ID')
  const fileRef = useRef(null)

  function addFile() {
    const file = fileRef.current?.files?.[0]
    if (!file) return

    setUploads((prev) => [
      ...prev,
      { file, docType, status: 'pending', error: null },
    ])
    fileRef.current.value = ''
  }

  async function uploadFile(index) {
    const entry = uploads[index]
    if (!entry || entry.status === 'uploading' || entry.status === 'done') return

    setUploads((prev) =>
      prev.map((u, i) => (i === index ? { ...u, status: 'uploading', error: null } : u))
    )

    const path = `${matterId}/${Date.now()}-${entry.file.name}`

    try {
      const { error: storageErr } = await supabase.storage
        .from('client-documents')
        .upload(path, entry.file)

      if (storageErr) throw storageErr

      const { error: docErr } = await supabase.from('documents').insert({
        matter_id: matterId,
        file_url: path,
        doc_type: entry.docType,
      })

      if (docErr) throw docErr

      setUploads((prev) =>
        prev.map((u, i) => (i === index ? { ...u, status: 'done' } : u))
      )
    } catch (err) {
      setUploads((prev) =>
        prev.map((u, i) =>
          i === index ? { ...u, status: 'error', error: err.message || 'Upload failed' } : u
        )
      )
    }
  }

  return (
    <div className="upload-section">
      <div className="upload-add-row">
        <select
          className="intake-input upload-type-select"
          value={docType}
          onChange={(e) => setDocType(e.target.value)}
        >
          {DOC_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <input
          ref={fileRef}
          type="file"
          accept="image/*,.pdf"
          className="upload-file-input"
        />
        <button type="button" className="upload-add-btn" onClick={addFile}>
          Add
        </button>
      </div>

      {uploads.length > 0 && (
        <ul className="upload-list">
          {uploads.map((u, i) => (
            <li key={i} className="upload-row">
              <span className="upload-filename">{u.file.name}</span>
              <span className="upload-doctype">{u.docType}</span>
              {u.status === 'pending' && (
                <button
                  type="button"
                  className="upload-action-btn"
                  onClick={() => uploadFile(i)}
                >
                  Upload
                </button>
              )}
              {u.status === 'uploading' && (
                <span className="upload-status uploading">Uploading…</span>
              )}
              {u.status === 'done' && (
                <span className="upload-status done">Done</span>
              )}
              {u.status === 'error' && (
                <span className="upload-status error-status">
                  {u.error}{' '}
                  <button
                    type="button"
                    className="upload-retry-btn"
                    onClick={() => uploadFile(i)}
                  >
                    Retry
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
