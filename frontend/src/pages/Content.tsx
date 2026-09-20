import { FormEvent, useCallback, useEffect, useRef, useState } from 'react'
import { api, errMsg, isAdmin, mediaUrl } from '../services/api'
import type { Content } from '../types'
import { Badge, Button, Card, Empty, ErrorNote, Field, inputCls, Modal, PageHeader } from '../components/ui'

const fmtSize = (b: number) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`)

export default function ContentPage() {
  const [items, setItems] = useState<Content[]>([])
  const [preview, setPreview] = useState<Content | null>(null)
  const [edit, setEdit] = useState<Content | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [duration, setDuration] = useState(10)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const replaceRef = useRef<HTMLInputElement>(null)
  const [replacing, setReplacing] = useState<number | null>(null)
  const admin = isAdmin()

  const load = useCallback(() => api.get('/content').then((r) => setItems(r.data)), [])
  useEffect(() => { load() }, [load])

  const upload = async (e: FormEvent) => {
    e.preventDefault(); if (!file) return
    setBusy(true); setErr('')
    const fd = new FormData(); fd.append('file', file); fd.append('name', name || file.name); fd.append('duration', String(duration))
    try { await api.post('/content/upload', fd); setFile(null); setName(''); if (fileRef.current) fileRef.current.value = ''; load() }
    catch (e) { setErr(errMsg(e)) } finally { setBusy(false) }
  }
  const replace = async (f: File) => {
    if (replacing == null) return
    const fd = new FormData(); fd.append('file', f)
    try { await api.post(`/content/${replacing}/replace`, fd); load() } catch (e) { setErr(errMsg(e)) }
    setReplacing(null)
  }
  const saveEdit = async () => {
    if (!edit) return
    try { await api.put(`/content/${edit.id}`, { name: edit.name, duration: edit.duration }); setEdit(null); load() } catch (e) { setErr(errMsg(e)) }
  }

  return (
    <div className="stagger space-y-6">
      <PageHeader title="Content library" subtitle="Images and videos your displays can play. Replacing a file bumps its version so every device re-downloads it." />
      {admin && (
        <Card title="Upload">
          <ErrorNote msg={err} />
          <form onSubmit={upload} className="grid items-end gap-3 md:grid-cols-[2fr_2fr_1fr_auto]">
            <Field label="File (.jpg .png .mp4 .webm)"><input ref={fileRef} type="file" accept=".jpg,.jpeg,.png,.mp4,.webm" className={inputCls + ' file:mr-3 file:cursor-pointer file:rounded-full file:border-0 file:bg-brand-50 file:px-3 file:py-1 file:text-xs file:font-semibold file:text-brand-700 hover:file:bg-brand-100'} onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
            <Field label="Display name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder={file?.name} /></Field>
            <Field label="Seconds (images)"><input type="number" min={1} className={inputCls} value={duration} onChange={(e) => setDuration(+e.target.value)} /></Field>
            <div className="mb-3"><Button disabled={!file || busy}>{busy ? 'Uploading…' : 'Upload'}</Button></div>
          </form>
        </Card>
      )}
      <input ref={replaceRef} type="file" hidden accept=".jpg,.jpeg,.png,.mp4,.webm" onChange={(e) => { const f = e.target.files?.[0]; if (f) replace(f); e.target.value = '' }} />
      {!admin && <ErrorNote msg={err} />}
      <div className="stagger grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {items.map((c) => (
          <div key={c.id} className="overflow-hidden glass lift rounded-[24px]">
            <button className="block aspect-video w-full bg-ink-900" onClick={() => setPreview(c)}>
              {c.type === 'image'
                ? <img src={mediaUrl(c.id, c.version)} className="h-full w-full object-cover" alt={c.name} />
                : <video src={mediaUrl(c.id, c.version)} className="h-full w-full object-cover" muted preload="metadata" />}
            </button>
            <div className="p-3">
              <div className="truncate font-medium" title={c.name}>{c.name}</div>
              <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-ink-500">
                <Badge tone={c.type === 'video' ? 'blue' : 'gray'}>{c.type}</Badge><span>v{c.version}</span><span>· {fmtSize(c.size)}</span>{c.type === 'image' && <span>· {c.duration}s</span>}
              </div>
              {admin && (
                <div className="mt-3 flex gap-1">
                  <Button variant="secondary" className="!px-2 !py-1 text-xs" onClick={() => setEdit(c)}>Edit</Button>
                  <Button variant="secondary" className="!px-2 !py-1 text-xs" onClick={() => { setReplacing(c.id); replaceRef.current?.click() }}>Replace file</Button>
                  <Button variant="ghost" className="ml-auto !px-2 !py-1 text-xs !text-red-600" onClick={async () => { if (confirm(`Delete "${c.name}" and its assignments?`)) { await api.delete(`/content/${c.id}`); load() } }}>Delete</Button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
      {!items.length && <Empty>No content uploaded</Empty>}
      {preview && (
        <Modal title={preview.name} onClose={() => setPreview(null)} wide>
          {preview.type === 'image' ? <img src={mediaUrl(preview.id, preview.version)} className="w-full rounded-lg" /> : <video src={mediaUrl(preview.id, preview.version)} controls autoPlay className="w-full rounded-lg" />}
        </Modal>
      )}
      {edit && (
        <Modal title="Edit content" onClose={() => setEdit(null)}>
          <Field label="Name"><input className={inputCls} value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
          <Field label="Seconds on screen" hint="Videos play to their end; changing this bumps the version so devices resync."><input type="number" min={1} className={inputCls} value={edit.duration} onChange={(e) => setEdit({ ...edit, duration: +e.target.value })} /></Field>
          <Button onClick={saveEdit}>Save</Button>
        </Modal>
      )}
    </div>
  )
}
