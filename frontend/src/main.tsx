import { FormEvent, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

type Format = 'chat' | 'json' | 'xml' | 'xlsx' | 'email'
type Message = { role: 'user' | 'assistant'; text: string; artifact?: { download_url: string; filename: string } }

const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

function App() {
  const [message, setMessage] = useState('')
  const [format, setFormat] = useState<Format>('chat')
  const [messages, setMessages] = useState<Message[]>([])
  const [busy, setBusy] = useState(false)
  const session = useMemo(() => crypto.randomUUID(), [])

  async function send(event: FormEvent) {
    event.preventDefault()
    const question = message.trim()
    if (!question || busy) return
    setMessages((current) => [...current, { role: 'user', text: question }])
    setMessage('')
    setBusy(true)
    try {
      const response = await fetch(`${apiUrl}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // Development-only identity. Production users authenticate through OIDC.
          'X-Dev-User': 'web-demo',
          'X-Dev-Roles': 'employee',
          'X-Dev-Domains': 'hr,finance,support,privacy,legal'
        },
        body: JSON.stringify({ session_id: session, message: question, output: { target_format: format } })
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'The assistant could not process this request.')
      const rendered = body.rendered_content ? `\n\n${typeof body.rendered_content === 'string' ? body.rendered_content : JSON.stringify(body.rendered_content, null, 2)}` : ''
      const escalation = body.escalation ? '\n\nA specialist review has been requested.' : ''
      setMessages((current) => [...current, { role: 'assistant', text: `${body.answer}${rendered}${escalation}`, artifact: body.artifact }])
    } catch (error) {
      setMessages((current) => [...current, { role: 'assistant', text: error instanceof Error ? error.message : 'Unexpected error.' }])
    } finally {
      setBusy(false)
    }
  }

  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadDomain, setUploadDomain] = useState<string>('support')
  const [uploading, setUploading] = useState(false)
  const [uploadMessage, setUploadMessage] = useState('')

  async function handleUpload(event: FormEvent) {
    event.preventDefault()
    if (!uploadFile || uploading) return
    setUploading(true)
    setUploadMessage('')
    
    const formData = new FormData()
    formData.append('file', uploadFile)
    formData.append('domain', uploadDomain)
    // Add allowed_roles if needed, or leave default empty string in backend

    try {
      const response = await fetch(`${apiUrl}/documents/upload`, {
        method: 'POST',
        headers: {
          // Note: Do not set Content-Type, let the browser set it with the boundary for FormData
          'X-Dev-User': 'knowledge-admin',
          'X-Dev-Roles': 'knowledge_admin,employee',
          'X-Dev-Domains': 'hr,finance,support,privacy,legal'
        },
        body: formData
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail ?? 'Upload failed.')
      setUploadMessage(`Success! Ingested as ${body.chunk_count} chunks.`)
      setUploadFile(null)
    } catch (error) {
      setUploadMessage(error instanceof Error ? error.message : 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  return <main>
    <header><span className="mark">E</span><div><h1>Enterprise AI Agent</h1><p>Grounded answers across approved knowledge domains.</p></div></header>
    <section className="notice">Demo mode has been granted access to all domains for testing purposes. Review AI-drafted outputs before use.</section>
    
    <details className="upload-section">
      <summary>Manage Knowledge Base (Upload PDF/DOCX)</summary>
      <form onSubmit={handleUpload} className="upload-form">
        <label>
          Domain: 
          <select value={uploadDomain} onChange={e => setUploadDomain(e.target.value)}>
            <option value="support">Support</option>
            <option value="privacy">Privacy</option>
            <option value="hr">HR</option>
            <option value="finance">Finance</option>
            <option value="legal">Legal</option>
          </select>
        </label>
        <input type="file" accept=".txt,.md,.pdf,.docx" onChange={e => setUploadFile(e.target.files?.[0] ?? null)} />
        <button disabled={!uploadFile || uploading}>{uploading ? 'Uploading...' : 'Upload Knowledge'}</button>
        {uploadMessage && <span className="upload-msg">{uploadMessage}</span>}
      </form>
    </details>

    <section className="thread" aria-live="polite">
      {messages.length === 0 && <p className="empty">Ask about a warranty, customer support, or privacy request.</p>}
      {messages.map((item, index) => <article key={index} className={item.role}><strong>{item.role === 'user' ? 'You' : 'UEAA'}</strong><pre>{item.text}</pre>{item.artifact && <a href={`${apiUrl}${item.artifact.download_url}`} target="_blank">Download {item.artifact.filename}</a>}</article>)}
    </section>
    <form onSubmit={send}>
      <label>Reply format <select value={format} onChange={(event) => setFormat(event.target.value as Format)}><option value="chat">Chat</option><option value="json">JSON</option><option value="xml">XML</option><option value="xlsx">Excel workbook</option><option value="email">Email draft</option></select></label>
      <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="How long is the warranty?" rows={4} />
      <button disabled={busy}>{busy ? 'Thinking…' : 'Send message'}</button>
    </form>
  </main>
}

createRoot(document.getElementById('root')!).render(<App />)

