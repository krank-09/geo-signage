import { FormEvent, useCallback, useEffect, useState } from 'react'
import { CircleNotch, Plugs, WifiHigh } from '@phosphor-icons/react'
import { api, errMsg } from '../../services/api'
import { CONNECTION_LABELS } from '../../types'
import type { City, ConnectionType, DiscoveredAgent, Group, Zone } from '../../types'
import { Badge, Button, ErrorNote, Field, inputCls, Modal } from '../ui'
import { TokenBox } from './TokenBox'

interface Created { device_id: string; name: string; registration_token: string; claimed_agent: boolean }

/** Waits for a claimed display to pick up its credentials and come online. */
function Connecting({ created }: { created: Created }) {
  const [state, setState] = useState<{ status: string; zone: string | null } | null>(null)
  useEffect(() => {
    const t = setInterval(() => api.get(`/devices/${created.device_id}`).then((r) => setState({ status: r.data.status, zone: r.data.zone })), 2000)
    return () => clearInterval(t)
  }, [created.device_id])
  const online = state?.status === 'online'
  return (
    <div className="rounded-2xl bg-brand-50 p-5 text-sm">
      <p className="flex items-center gap-2 text-base font-bold">{online ? <WifiHigh size={20} weight="bold" className="text-emerald-600" aria-hidden="true" /> : <CircleNotch size={20} className="animate-spin text-brand-600" aria-hidden="true" />}{online ? `${created.name} is connected` : `Waiting for ${created.name} to connect…`}</p>
      <p className="mt-2 text-ink-600">{online
        ? <>It is online{state?.zone ? <> in <b>{state.zone}</b></> : ''} and will start playing its content.</>
        : 'You do not need to copy any token. The display collects its credentials itself; this usually takes a few seconds.'}</p>
    </div>
  )
}

export function AddDeviceModal({ groups, onClose, onDone }: { groups: Group[]; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ device_id: '', name: '', group_id: '', connection_type: 'wifi' as ConnectionType, latitude: '', longitude: '' })
  const [area, setArea] = useState('')                 // '' | 'zone:<id>' | 'city:<id>'
  const [zones, setZones] = useState<Zone[]>([])
  const [cities, setCities] = useState<City[]>([])
  const [agents, setAgents] = useState<DiscoveredAgent[]>([])
  const [areaName, setAreaName] = useState<string | null>(null)
  const [loadedAgents, setLoadedAgents] = useState(false)
  const [pick, setPick] = useState<DiscoveredAgent | null>(null)
  const [err, setErr] = useState('')
  const [created, setCreated] = useState<Created | null>(null)

  useEffect(() => {
    api.get('/zones').then((r) => setZones(r.data))
    api.get('/cities').then((r) => setCities(r.data))
  }, [])

  const loadAgents = useCallback(async () => {
    const [kind, id] = area.split(':')
    const qs = kind === 'zone' ? `?zone_id=${id}` : kind === 'city' ? `?city_id=${id}` : ''
    try {
      const { data } = await api.get(`/discovery/agents${qs}`)
      setAgents(data.agents); setAreaName(data.area); setLoadedAgents(true)
      setPick((p) => (p && data.agents.some((a: DiscoveredAgent) => a.id === p.id) ? p : null))   // the chosen one may have gone quiet
    } catch { /* keep the last list */ }
  }, [area])
  useEffect(() => {
    if (created) return
    loadAgents()
    const t = setInterval(loadAgents, 4000)
    return () => clearInterval(t)
  }, [loadAgents, created])

  const choose = (a: DiscoveredAgent) => {
    setPick(a)
    setF((p) => ({
      ...p, name: p.name || a.name, connection_type: a.connection_type ?? p.connection_type,
      device_id: p.device_id || `DEV-${a.id.slice(0, 6).toUpperCase()}`, latitude: '', longitude: '',
    }))
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr('')
    try {
      const { data } = await api.post('/devices', {
        device_id: f.device_id, name: f.name, group_id: f.group_id ? +f.group_id : null, connection_type: f.connection_type,
        latitude: !pick && f.latitude ? +f.latitude : null, longitude: !pick && f.longitude ? +f.longitude : null,
        discovery_id: pick?.id ?? null,
      })
      setCreated(data); onDone()
    } catch (x) { setErr(errMsg(x)); if (pick) loadAgents() }
  }

  return (
    <Modal title={created ? 'Device created' : 'Add device'} onClose={onClose} wide>
      {created ? (
        created.claimed_agent ? <Connecting created={created} /> : <TokenBox deviceId={created.device_id} token={created.registration_token} />
      ) : (
        <form onSubmit={submit} className="grid gap-x-6 md:grid-cols-2">
          <div>
            <ErrorNote msg={err} />
            <Field label="Device ID" hint="Letters, digits, - and _"><input name="device-id" autoComplete="off" className={inputCls} value={f.device_id} onChange={(e) => setF({ ...f, device_id: e.target.value })} placeholder="DEV-004" required /></Field>
            <Field label="Name"><input name="device-name" autoComplete="off" className={inputCls} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Airport lobby screen" required /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Connection type"><select className={inputCls} value={f.connection_type} onChange={(e) => setF({ ...f, connection_type: e.target.value as ConnectionType })}>
                {(Object.keys(CONNECTION_LABELS) as ConnectionType[]).map((c) => <option key={c} value={c}>{CONNECTION_LABELS[c]}</option>)}</select></Field>
              <Field label="Group"><select className={inputCls} value={f.group_id} onChange={(e) => setF({ ...f, group_id: e.target.value })}><option value="">None</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></Field>
            </div>
            {!pick && (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Initial latitude"><input className={inputCls} inputMode="decimal" value={f.latitude} onChange={(e) => setF({ ...f, latitude: e.target.value })} placeholder="optional" /></Field>
                <Field label="Initial longitude"><input className={inputCls} inputMode="decimal" value={f.longitude} onChange={(e) => setF({ ...f, longitude: e.target.value })} placeholder="optional" /></Field>
              </div>
            )}
            <Button className="mt-1 w-full">{pick ? `Create and connect ${pick.name}` : 'Create device'}</Button>
            {!pick && <p className="mt-2 text-xs text-ink-400">Without picking a display, you get a registration token to enter on the display yourself.</p>}
          </div>

          <div className="mt-4 md:mt-0">
            <Field label="Look for displays in">
              <select className={inputCls} value={area} onChange={(e) => { setArea(e.target.value); setPick(null); setLoadedAgents(false) }}>
                <option value="">Anywhere</option>
                <optgroup label="Zones">{zones.map((z) => <option key={z.id} value={`zone:${z.id}`}>{z.name}</option>)}</optgroup>
                <optgroup label="Cities">{cities.map((c) => <option key={c.id} value={`city:${c.id}`}>{c.name}, {c.state}</option>)}</optgroup>
              </select>
            </Field>
            <div className="rounded-2xl border border-ink-200 bg-white/60 p-3">
              <p className="mb-2 flex items-center justify-between text-xs font-semibold text-ink-500"><span className="flex items-center gap-1.5"><Plugs size={14} aria-hidden="true" />Available to connect{areaName ? ` in ${areaName}` : ''}</span><span>{agents.length}</span></p>
              <ul className="max-h-56 space-y-1 overflow-auto" aria-label="Available displays">
                {agents.map((a) => (
                  <li key={a.id}>
                    <label className={`flex cursor-pointer items-start gap-2.5 rounded-xl p-2.5 text-sm transition ${pick?.id === a.id ? 'bg-brand-600 text-white' : 'hover:bg-brand-50'}`}>
                      <input type="radio" name="agent" className="mt-1" checked={pick?.id === a.id} onChange={() => choose(a)} />
                      <span className="min-w-0 flex-1">
                        <b className="block truncate">{a.name}</b>
                        <span className={`text-xs ${pick?.id === a.id ? 'text-white/75' : 'text-ink-400'}`}>code {a.id.slice(0, 6)} · {a.zones.length ? a.zones.join(', ') : a.latitude != null ? 'outside zones' : 'no location'} · seen {a.seconds_ago}s ago</span>
                      </span>
                      {a.connection_type && <Badge tone="gray">{CONNECTION_LABELS[a.connection_type]}</Badge>}
                    </label>
                  </li>
                ))}
              </ul>
              {loadedAgents && !agents.length && (
                <p className="py-5 text-center text-xs text-ink-400">No unclaimed displays are announcing{areaName ? ` in ${areaName}` : ''}. On a display laptop run <code>./start.sh</code> and press Enter at the Device ID question, then it appears here within seconds.</p>
              )}
              {!loadedAgents && <p className="py-5 text-center text-xs text-ink-400">Looking…</p>}
            </div>
          </div>
        </form>
      )}
    </Modal>
  )
}
