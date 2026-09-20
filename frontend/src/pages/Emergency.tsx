import { useCallback, useEffect, useState } from 'react'
import { api, errMsg, isAdmin } from '../services/api'
import type { Assignment, Content, Group, Zone } from '../types'
import { Badge, Button, Card, ErrorNote, Field, inputCls, PageHeader } from '../components/ui'

export default function Emergency() {
  const [content, setContent] = useState<Content[]>([])
  const [zones, setZones] = useState<Zone[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [active, setActive] = useState<Assignment[]>([])
  const [f, setF] = useState({ content_id: '', zone_id: '', group_id: '' })
  const [err, setErr] = useState('')
  const admin = isAdmin()

  const load = useCallback(() => api.get('/emergency').then((r) => setActive(r.data)), [])
  useEffect(() => {
    load()
    api.get('/content').then((r) => { setContent(r.data); const a = r.data.find((c: Content) => /alert|emergency/i.test(c.name)); if (a) setF((p) => ({ ...p, content_id: String(a.id) })) })
    api.get('/zones').then((r) => setZones(r.data)); api.get('/groups').then((r) => setGroups(r.data))
  }, [load])

  const trigger = async () => {
    setErr('')
    if (!confirm('Push this emergency content to the selected displays now?')) return
    try { await api.post('/emergency', { content_id: +f.content_id, zone_id: f.zone_id ? +f.zone_id : null, group_id: f.group_id ? +f.group_id : null }); load() }
    catch (e) { setErr(errMsg(e)) }
  }

  return (
    <div className="stagger space-y-6">
      <PageHeader title={<span className="text-red-700">Emergency override</span>} subtitle="Highest priority: interrupts whatever else is scheduled and reaches online devices immediately." />
      {admin && (
        <Card title="Broadcast alert" className="ring-red-200">
          <ErrorNote msg={err} />
          <div className="grid gap-x-3 md:grid-cols-3">
            <Field label="Alert content"><select className={inputCls} value={f.content_id} onChange={(e) => setF({ ...f, content_id: e.target.value })}><option value="">Select…</option>{content.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
            <Field label="Target zone" hint="Empty = every zone"><select className={inputCls} value={f.zone_id} onChange={(e) => setF({ ...f, zone_id: e.target.value })}><option value="">All zones</option>{zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}</select></Field>
            <Field label="Target group" hint="Empty = every group"><select className={inputCls} value={f.group_id} onChange={(e) => setF({ ...f, group_id: e.target.value })}><option value="">All groups</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></Field>
          </div>
          <Button variant="danger" disabled={!f.content_id} onClick={trigger}>⚠ Send emergency alert</Button>
        </Card>
      )}
      <Card title="Active alerts" actions={admin && active.length > 0 && <Button variant="secondary" onClick={async () => { await api.delete('/emergency'); load() }}>Clear all alerts</Button>}>
        {active.length ? <ul className="space-y-2 text-sm">{active.map((a) => <li key={a.id}><Badge tone="red">LIVE</Badge> <b>{a.content_name}</b> → {a.zone_name || 'all zones'} / {a.group_name || 'all groups'}</li>)}</ul>
          : <p className="text-sm text-ink-400">No active alerts</p>}
      </Card>
    </div>
  )
}
