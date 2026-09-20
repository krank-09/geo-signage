import { useCallback, useEffect, useState } from 'react'
import { api, isAdmin } from '../services/api'
import type { Assignment } from '../types'
import AssignmentForm from '../components/AssignmentForm'
import { Badge, Button, Card, Empty, PageHeader } from '../components/ui'

export default function Schedules() {
  const [items, setItems] = useState<Assignment[]>([])
  const admin = isAdmin()
  const load = useCallback(() => api.get('/assignments').then((r) => setItems(r.data)), [])
  useEffect(() => { load() }, [load])

  const toggle = (a: Assignment) => api.put(`/assignments/${a.id}`, {
    content_id: a.content_id, zone_id: a.zone_id, group_id: a.group_id, start_time: a.start_time, end_time: a.end_time,
    priority: a.priority, is_emergency: a.is_emergency, active: !a.active,
  }).then(load)

  return (
    <div className="stagger space-y-6">
      <PageHeader title="Schedules & assignments" subtitle="Emergency beats priority; higher priority beats lower; a specific zone or group beats “everywhere”. Equal winners play as a playlist. Time windows use server time (IST) and may cross midnight." />
      {admin && <Card title="New assignment"><AssignmentForm onDone={load} /></Card>}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-ink-400"><tr><th className="py-2">Content</th><th>Zone</th><th>Group</th><th>Window</th><th>Priority</th><th>State</th><th /></tr></thead>
            <tbody className="divide-y divide-ink-100/70">
              {items.map((a) => (
                <tr key={a.id} className={a.active ? '' : 'text-ink-400'}>
                  <td className="py-2 font-medium">{a.content_name} {a.is_emergency && <Badge tone="red">emergency</Badge>}</td>
                  <td>{a.zone_name || 'Everywhere'}</td><td>{a.group_name || 'All'}</td>
                  <td>{a.start_time ? `${a.start_time} – ${a.end_time}` : 'Always'}</td><td>{a.priority}</td>
                  <td><Badge tone={a.active ? 'green' : 'gray'}>{a.active ? 'active' : 'paused'}</Badge></td>
                  <td className="space-x-1 text-right">{admin && <><Button variant="secondary" className="!px-2 !py-1 text-xs" onClick={() => toggle(a)}>{a.active ? 'Pause' : 'Resume'}</Button>
                    <Button variant="ghost" className="!px-2 !py-1 text-xs !text-red-600" onClick={async () => { await api.delete(`/assignments/${a.id}`); load() }}>Delete</Button></>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!items.length && <Empty>No assignments</Empty>}
        </div>
      </Card>
    </div>
  )
}
