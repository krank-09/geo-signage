import { FormEvent, useCallback, useEffect, useState } from 'react'
import { api, errMsg, isAdmin } from '../services/api'
import type { Group } from '../types'
import { AddDeviceModal } from '../components/devices/AddDeviceModal'
import { DeviceDetailModal } from '../components/devices/DeviceDetailModal'
import { useDevices } from '../hooks/useDevices'
import { HealthBar } from '../components/HealthBar'
import { useHealthThreshold } from '../hooks/useHealthThreshold'
import { ago, Avatar, Badge, Button, Card, Empty, ErrorNote, inputCls, PageHeader, StatusBadge } from '../components/ui'
import { CONNECTION_LABELS } from '../types'

export default function Devices() {
  const { devices: deviceList, refresh } = useDevices()
  const devices = deviceList ?? []
  const [groups, setGroups] = useState<Group[]>([])
  const [threshold] = useHealthThreshold()
  const [adding, setAdding] = useState(false)
  const [open, setOpen] = useState<string | null>(null)
  const [newGroup, setNewGroup] = useState('')
  const [err, setErr] = useState('')

  const load = useCallback(() => {
    refresh()
    api.get('/groups').then((r) => setGroups(r.data))
  }, [refresh])
  useEffect(() => { load() }, [load])

  const addGroup = async (e: FormEvent) => {
    e.preventDefault()
    try { await api.post('/groups', { name: newGroup }); setNewGroup(''); setErr(''); load() } catch (e) { setErr(errMsg(e)) }
  }

  return (
    <div className="stagger space-y-6">
      <PageHeader title="Devices" subtitle="Register displays, group them, and push configuration remotely."
        actions={isAdmin() && <Button onClick={() => setAdding(true)}>+ Add device</Button>} />
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-ink-400"><tr><th className="py-2">Device</th><th>Status</th><th>Health</th><th>Connection</th><th>Group</th><th>Location</th><th>Zone</th><th>Now playing</th><th>Last seen</th></tr></thead>
            <tbody className="divide-y divide-ink-100/70">
              {devices.map((d) => (
                <tr key={d.device_id} onClick={() => setOpen(d.device_id)} className="cursor-pointer hover:bg-white/60">
                  <td className="py-2.5"><div className="flex items-center gap-3"><Avatar label={d.device_id} size={38} /><div><b>{d.device_id}</b><div className="text-xs text-ink-500">{d.name}</div></div></div></td>
                  <td><StatusBadge status={d.status} /></td>
                  <td className="min-w-32"><HealthBar health={d.health} threshold={threshold} reasons={d.health_reasons} /></td>
                  <td>{d.connection_type ? <Badge tone="gray">{CONNECTION_LABELS[d.connection_type]}</Badge> : '—'}</td><td>{d.group || '—'}</td>
                  <td className="text-xs">{d.latitude != null ? `${d.latitude.toFixed(3)}, ${d.longitude!.toFixed(3)}` : '—'}</td>
                  <td>{d.zone || '—'}</td><td>{d.current_content || '—'}</td><td className="text-ink-500">{ago(d.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!devices.length && <Empty>No devices yet</Empty>}
        </div>
      </Card>
      <Card title="Device groups">
        <ErrorNote msg={err} />
        <div className="flex flex-wrap gap-2">
          {groups.map((g) => (
            <Badge key={g.id} tone="blue">{g.name} · {g.device_count}
              {isAdmin() && <button className="ml-1 text-blue-400 hover:text-red-600" onClick={async () => { if (confirm(`Delete group ${g.name}? Its assignments are removed too.`)) { await api.delete(`/groups/${g.id}`); load() } }}>×</button>}</Badge>
          ))}
          {!groups.length && <span className="text-sm text-ink-400">No groups</span>}
        </div>
        {isAdmin() && <form onSubmit={addGroup} className="mt-3 flex gap-2"><input className={inputCls + ' max-w-xs'} placeholder="New group name" value={newGroup} onChange={(e) => setNewGroup(e.target.value)} required /><Button variant="secondary">Add group</Button></form>}
      </Card>
      {adding && <AddDeviceModal groups={groups} onClose={() => setAdding(false)} onDone={load} />}
      {open && <DeviceDetailModal id={open} groups={groups} onClose={() => setOpen(null)} onChanged={load} />}
    </div>
  )
}
