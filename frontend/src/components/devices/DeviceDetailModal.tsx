import { useCallback, useEffect, useState } from 'react'
import { api, errMsg, isAdmin } from '../../services/api'
import type { Device, Group, LogEntry } from '../../types'
import { useLive } from '../../hooks/useLive'
import { CONNECTION_LABELS } from '../../types'
import type { ConnectionType } from '../../types'
import { useHealthThreshold } from '../../hooks/useHealthThreshold'
import { HealthBar } from '../HealthBar'
import { ago, Badge, Button, Empty, Field, inputCls, Modal, StatusBadge } from '../ui'
import { TokenBox } from './TokenBox'

export function DeviceDetailModal({ id, groups, onClose, onChanged }: { id: string; groups: Group[]; onClose: () => void; onChanged: () => void }) {
  const [d, setD] = useState<Device | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [cfg, setCfg] = useState<Device['config'] | null>(null)
  const [name, setName] = useState('')
  const [group, setGroup] = useState('')
  const [conn, setConn] = useState<ConnectionType | ''>('')
  const [threshold] = useHealthThreshold()
  const [msg, setMsg] = useState('')
  const [token, setToken] = useState('')
  const admin = isAdmin()

  const load = useCallback(async () => {
    const [dev, lg] = await Promise.all([api.get(`/devices/${id}`), api.get(`/devices/${id}/logs?limit=15`)])
    setD(dev.data); setLogs(lg.data)
    setCfg((c) => c ?? dev.data.config); setName((n) => n || dev.data.name); setGroup((g) => (g === '' && dev.data.group_id ? String(dev.data.group_id) : g)); setConn((c) => c || dev.data.connection_type || '')
  }, [id])
  useEffect(() => { load() }, [load])
  useLive((e) => { if (e.event === 'device_update' && e.device.device_id === id) load() })

  const save = async () => {
    try {
      await api.put(`/devices/${id}`, { name, config: cfg, group_id: group ? +group : null, clear_group: !group, connection_type: conn || null })
      setMsg('Saved — pushed to the device'); onChanged(); load()
    } catch (e) { setMsg(errMsg(e)) }
  }
  const act = async (fn: () => Promise<any>, ok: string) => { try { await fn(); setMsg(ok) } catch (e) { setMsg(errMsg(e)) } }

  if (!d || !cfg) return <Modal title="Device" onClose={onClose}><Empty>Loading…</Empty></Modal>
  return (
    <Modal title={`${d.device_id} · ${d.name}`} onClose={onClose} wide>
      {msg && <p className="mb-3 rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-800">{msg}</p>}
      {token && <div className="mb-4"><TokenBox deviceId={d.device_id} token={token} /></div>}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-1 text-sm">
          <h4 className="mb-2 font-semibold">Status</h4>
          <div><StatusBadge status={d.status} /> {d.ws_connected && <Badge tone="blue">live link</Badge>} {!d.registered && <Badge tone="amber">not registered</Badge>}</div>
          <div className="my-1"><HealthBar health={d.health} threshold={threshold} reasons={d.health_reasons} />{d.health_reasons.length > 0 && <p className="mt-1 text-xs text-ink-500">{d.health_reasons.join(' · ')}</p>}</div>
          <p>Last heartbeat: <b>{ago(d.last_seen)}</b></p>
          <p>Location: <b>{d.latitude != null ? `${d.latitude.toFixed(4)}, ${d.longitude!.toFixed(4)}` : '—'}</b> {d.gps_ok ? '' : '(no GPS)'}</p>
          <p>Zone: <b>{d.zone || 'outside all zones'}</b></p>
          <p>Should play: <b>{d.resolved?.items.map((i) => i.name).join(', ') || '—'}</b> <span className="text-ink-500">({d.resolved?.reason})</span></p>
          <p>Reported playing: <b>{d.current_content || '—'}</b></p>
          <p>CPU {d.cpu ?? '—'}% · Mem {d.memory ?? '—'}% · {d.network || '—'} · v{d.software_version || '—'}</p>
        </div>
        <div>
          <h4 className="mb-2 font-semibold">Remote configuration</h4>
          <Field label="Name"><input disabled={!admin} className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Connection type"><select disabled={!admin} className={inputCls} value={conn} onChange={(e) => setConn(e.target.value as ConnectionType | '')}><option value="">Not set</option>{(Object.keys(CONNECTION_LABELS) as ConnectionType[]).map((c) => <option key={c} value={c}>{CONNECTION_LABELS[c]}</option>)}</select></Field>
          <Field label="Group"><select disabled={!admin} className={inputCls} value={group} onChange={(e) => setGroup(e.target.value)}><option value="">— none —</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Heartbeat (s)"><input disabled={!admin} type="number" min={2} className={inputCls} value={cfg.heartbeat_interval} onChange={(e) => setCfg({ ...cfg, heartbeat_interval: +e.target.value })} /></Field>
            <Field label="GPS report (s)"><input disabled={!admin} type="number" min={1} className={inputCls} value={cfg.location_interval} onChange={(e) => setCfg({ ...cfg, location_interval: +e.target.value })} /></Field>
            <Field label="Scaling"><select disabled={!admin} className={inputCls} value={cfg.fit} onChange={(e) => setCfg({ ...cfg, fit: e.target.value as any })}><option value="contain">Fit (letterbox)</option><option value="cover">Fill (crop)</option></select></Field>
            <Field label="Audio"><select disabled={!admin} className={inputCls} value={String(cfg.mute)} onChange={(e) => setCfg({ ...cfg, mute: e.target.value === 'true' })}><option value="true">Muted</option><option value="false">Sound on</option></select></Field>
          </div>
        </div>
      </div>
      {admin && (
        <div className="mt-2 flex flex-wrap gap-2">
          <Button onClick={save}>Save & push</Button>
          <Button variant="secondary" onClick={() => act(() => api.post(`/devices/${id}/sync`), 'Sync command sent')}>Force sync</Button>
          <Button variant="secondary" onClick={async () => { if (confirm('Revoke this device\'s credentials and issue a new registration token?')) { const r = await api.post(`/devices/${id}/rotate-token`); setToken(r.data.registration_token); onChanged() } }}>Revoke & re-issue token</Button>
          <Button variant="danger" className="ml-auto" onClick={async () => { if (confirm(`Remove ${id}?`)) { await api.delete(`/devices/${id}`); onChanged(); onClose() } }}>Remove device</Button>
        </div>
      )}
      <h4 className="mb-2 mt-5 font-semibold">Recent activity</h4>
      <ul className="max-h-40 space-y-1 overflow-auto text-sm">
        {logs.map((l) => <li key={l.id}><span className="mr-2 text-xs text-ink-400">{ago(l.ts)}</span>{l.message}</li>)}
        {!logs.length && <li className="text-ink-400">No activity</li>}
      </ul>
    </Modal>
  )
}
