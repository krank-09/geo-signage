import { useCallback, useEffect, useState } from 'react'
import { api, errMsg, getToken, isAdmin } from '../../services/api'
import type { Device, Group, LogEntry, RouteInfo, TrackPoint, Zone } from '../../types'
import MapView from '../MapView'
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
  const [routes, setRoutes] = useState<RouteInfo[]>([])
  const [trail, setTrail] = useState<TrackPoint[] | null>(null)
  const [zones, setZones] = useState<Zone[]>([])
  const [noShot, setNoShot] = useState(false)
  const admin = isAdmin()

  const load = useCallback(async () => {
    const [dev, lg] = await Promise.all([api.get(`/devices/${id}`), api.get(`/devices/${id}/logs?limit=15`)])
    setD(dev.data); setLogs(lg.data)
    setCfg((c) => c ?? dev.data.config); setName((n) => n || dev.data.name); setGroup((g) => (g === '' && dev.data.group_id ? String(dev.data.group_id) : g)); setConn((c) => c || dev.data.connection_type || '')
  }, [id])
  useEffect(() => { load() }, [load])
  useEffect(() => { api.get('/routes').then((r) => setRoutes(r.data)).catch(() => {}) }, [])
  useEffect(() => { setNoShot(false) }, [d?.screenshot_at])
  useLive((e) => { if (e.event === 'device_update' && e.device.device_id === id) load() })

  const save = async () => {
    try {
      await api.put(`/devices/${id}`, { name, config: cfg, group_id: group ? +group : null, clear_group: !group, connection_type: conn || null })
      setMsg('Saved — pushed to the device'); onChanged(); load()
    } catch (e) { setMsg(errMsg(e)) }
  }
  const act = async (fn: () => Promise<any>, ok: string) => { try { await fn(); setMsg(ok) } catch (e) { setMsg(errMsg(e)) } }

  const showTrail = async () => {
    try {
      const [t, z] = await Promise.all([api.get<TrackPoint[]>(`/devices/${id}/track?hours=24`), api.get<Zone[]>('/zones')])
      setTrail(t.data); setZones(z.data)
    } catch (e) { setMsg(errMsg(e)) }
  }
  const setRoute = async (rid: string) => {
    try { await api.put(`/devices/${id}`, rid ? { route_id: +rid } : { clear_route: true }); setMsg(rid ? 'Route assigned' : 'Route removed'); load(); onChanged() } catch (e) { setMsg(errMsg(e)) }
  }

  if (!d || !cfg) return <Modal title="Device" onClose={onClose}><Empty>Loading…</Empty></Modal>
  return (
    <Modal title={`${d.device_id} · ${d.name}`} onClose={onClose} wide>
      {msg && <p className="mb-3 rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-800">{msg}</p>}
      {token && <div className="mb-4"><TokenBox deviceId={d.device_id} token={token} /></div>}
      {d.tamper_state && (
        <div role="alert" className="mb-4 flex flex-wrap items-center gap-3 rounded-2xl bg-red-500/10 px-4 py-3 text-sm text-red-800">
          <b>Possible tampering.</b> <span className="flex-1">Flagged {ago(d.tamper_flagged_at)}. The display keeps working. See Security for the details.</span>
          {admin && <Button variant="secondary" className="!px-3 !py-1 text-xs" onClick={() => act(async () => { await api.post(`/devices/${id}/tamper/clear`); load(); onChanged() }, 'Flag cleared')}>Clear flag</Button>}
        </div>
      )}
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
          <p>System: <b>{d.os_name ? `${d.os_name} ${d.os_version ?? ''} (${d.os_arch ?? '?'})` : 'not reported'}</b>{d.runtime_version ? ` · Python ${d.runtime_version}` : ''}</p>
          {d.route && (
            <div className="my-1 rounded-2xl bg-white/60 p-2.5">
              <div className="flex items-center justify-between text-xs"><b>{routes.find((r) => r.id === d.route!.route_id)?.name ?? 'Route'}</b>{d.route.off_route ? <Badge tone="red">off route · {d.route.offset_km} km</Badge> : <Badge tone="green">on route</Badge>}</div>
              <div className="my-1.5 h-2 overflow-hidden rounded-full bg-brand-100/70"><div className="h-2 rounded-full bg-brand-500" style={{ width: `${d.route.progress ?? 0}%` }} /></div>
              <p className="text-xs text-ink-500">{d.route.leg_label ?? '—'} · {d.route.progress ?? 0}% of the route</p>
            </div>
          )}
          <p>Identity: {d.protection === 'protected' ? <Badge tone="green">key bound {ago(d.key_bound_at)}</Badge> : <Badge tone="amber">no identity key (older agent)</Badge>}</p>
        </div>
        <div>
          <h4 className="mb-2 font-semibold">Remote configuration</h4>
          <Field label="Name"><input disabled={!admin} className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Connection type"><select disabled={!admin} className={inputCls} value={conn} onChange={(e) => setConn(e.target.value as ConnectionType | '')}><option value="">Not set</option>{(Object.keys(CONNECTION_LABELS) as ConnectionType[]).map((c) => <option key={c} value={c}>{CONNECTION_LABELS[c]}</option>)}</select></Field>
          {(routes.length > 0 || d.route_id) && <Field label="Route" hint="Content can be assigned to this route or to one of its legs"><select disabled={!admin} className={inputCls} value={d.route_id ?? ''} onChange={(e) => setRoute(e.target.value)}><option value="">— none —</option>{routes.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></Field>}
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
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div>
          <div className="mb-2 flex items-center justify-between"><h4 className="font-semibold">Screen right now</h4>
            {admin && <Button variant="secondary" className="!px-3 !py-1 text-xs" onClick={() => act(() => api.post(`/devices/${id}/screenshot/request`), 'Asked the display for a fresh picture')}>Capture now</Button>}</div>
          {d.screenshot_at && !noShot
            ? <img alt={`Latest screenshot of ${d.device_id}`} className="w-full rounded-2xl ring-1 ring-ink-100" src={`/api/devices/${id}/screenshot?token=${getToken()}&t=${encodeURIComponent(d.screenshot_at)}`} onError={() => setNoShot(true)} />
            : <div className="grid aspect-video place-items-center rounded-2xl bg-ink-100/60 p-3 text-center text-xs text-ink-500">No screenshot yet. It arrives within a minute while the display page is open{admin ? ', or press Capture now' : ''}.</div>}
          {d.screenshot_at && <p className="mt-1 text-xs text-ink-400">Taken {ago(d.screenshot_at)}</p>}
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between"><h4 className="font-semibold">Where it has been (24 h)</h4>
            <Button variant="secondary" className="!px-3 !py-1 text-xs" onClick={showTrail}>{trail ? 'Refresh trail' : 'Show trail'}</Button></div>
          {trail
            ? (trail.length > 1 ? <MapView zones={zones} routes={routes.filter((r) => r.id === d.route_id)} devices={[d]} trail={trail.map((p) => [p.lat, p.lng] as [number, number])} height={200} />
              : <div className="grid aspect-video place-items-center rounded-2xl bg-ink-100/60 p-3 text-center text-xs text-ink-500">Not enough movement recorded yet.</div>)
            : <div className="grid aspect-video place-items-center rounded-2xl bg-ink-100/60 p-3 text-center text-xs text-ink-500">Press Show trail to draw its route on the map.</div>}
        </div>
      </div>
      <h4 className="mb-2 mt-5 font-semibold">Recent activity</h4>
      <ul className="max-h-40 space-y-1 overflow-auto text-sm">
        {logs.map((l) => <li key={l.id}><span className="mr-2 text-xs text-ink-400">{ago(l.ts)}</span>{l.message}</li>)}
        {!logs.length && <li className="text-ink-400">No activity</li>}
      </ul>
    </Modal>
  )
}
