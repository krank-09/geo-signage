import { FormEvent, useEffect, useState } from 'react'
import { api, errMsg } from '../services/api'
import type { Content, Group, Zone } from '../types'
import { Button, ErrorNote, Field, inputCls } from './ui'

export default function AssignmentForm({ zoneId, lockZone, onDone }: { zoneId?: number | null; lockZone?: boolean; onDone: () => void }) {
  const [content, setContent] = useState<Content[]>([])
  const [zones, setZones] = useState<Zone[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [f, setF] = useState({ content_id: '', zone_id: zoneId ? String(zoneId) : '', group_id: '', start_time: '', end_time: '', priority: 0 })
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get('/content').then((r) => setContent(r.data))
    api.get('/zones').then((r) => setZones(r.data))
    api.get('/groups').then((r) => setGroups(r.data))
  }, [])
  useEffect(() => { if (zoneId) setF((p) => ({ ...p, zone_id: String(zoneId) })) }, [zoneId])

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr('')
    try {
      await api.post('/assignments', {
        content_id: +f.content_id, zone_id: f.zone_id ? +f.zone_id : null, group_id: f.group_id ? +f.group_id : null,
        start_time: f.start_time || null, end_time: f.end_time || null, priority: f.priority,
      })
      onDone()
    } catch (e) { setErr(errMsg(e)) }
  }

  return (
    <form onSubmit={submit}>
      <ErrorNote msg={err} />
      <div className="grid gap-x-3 md:grid-cols-3">
        <Field label="Content"><select required className={inputCls} value={f.content_id} onChange={(e) => setF({ ...f, content_id: e.target.value })}><option value="">Select…</option>{content.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
        <Field label="Zone" hint={lockZone ? undefined : 'Empty = everywhere'}><select disabled={lockZone} className={inputCls} value={f.zone_id} onChange={(e) => setF({ ...f, zone_id: e.target.value })}><option value="">Any location</option>{zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}</select></Field>
        <Field label="Device group" hint="Empty = all devices"><select className={inputCls} value={f.group_id} onChange={(e) => setF({ ...f, group_id: e.target.value })}><option value="">All groups</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></Field>
        <Field label="From (HH:MM)" hint="Both times empty = always"><input type="time" className={inputCls} value={f.start_time} onChange={(e) => setF({ ...f, start_time: e.target.value })} /></Field>
        <Field label="Until"><input type="time" className={inputCls} value={f.end_time} onChange={(e) => setF({ ...f, end_time: e.target.value })} /></Field>
        <Field label="Priority" hint="Higher wins"><input type="number" min={0} className={inputCls} value={f.priority} onChange={(e) => setF({ ...f, priority: +e.target.value })} /></Field>
      </div>
      <Button>Assign content</Button>
    </form>
  )
}
