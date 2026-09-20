import { FormEvent, useCallback, useEffect, useState } from 'react'
import { api, errMsg, isAdmin } from '../services/api'
import type { City, RouteInfo, Waypoint, Zone } from '../types'
import MapView from '../components/MapView'
import { useLive } from '../hooks/useLive'
import { Badge, Button, Card, Empty, ErrorNote, Field, inputCls, PageHeader } from '../components/ui'

const blank = { id: 0, name: '', corridor_km: 25, color: '#e0662b', waypoints: [] as Waypoint[] }

export default function Routes() {
  const [routes, setRoutes] = useState<RouteInfo[]>([])
  const [zones, setZones] = useState<Zone[]>([])
  const [cities, setCities] = useState<City[]>([])
  const [form, setForm] = useState(blank)
  const [picked, setPicked] = useState<number | null>(null)
  const [err, setErr] = useState('')
  const admin = isAdmin()

  const load = useCallback(() => api.get<RouteInfo[]>('/routes').then((r) => setRoutes(r.data)), [])
  useEffect(() => { load(); api.get('/zones').then((r) => setZones(r.data)); api.get('/cities').then((r) => setCities(r.data)).catch(() => {}) }, [load])
  useLive((e) => { if (e.event === 'device_update') load() })

  const addStop = (w: Waypoint) => setForm((f) => ({ ...f, waypoints: [...f.waypoints, w] }))
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr('')
    const body = { name: form.name, corridor_km: form.corridor_km, color: form.color, waypoints: form.waypoints }
    try { form.id ? await api.put(`/routes/${form.id}`, body) : await api.post('/routes', body); setForm(blank); load() } catch (x) { setErr(errMsg(x)) }
  }
  const remove = async (r: RouteInfo) => {
    if (!confirm(`Delete route ${r.name}? Content assigned to it is removed and its displays are freed.`)) return
    try { await api.delete(`/routes/${r.id}`); if (picked === r.id) setPicked(null); load() } catch (x) { setErr(errMsg(x)) }
  }
  const shown = routes.filter((r) => picked == null || r.id === picked)
  const draft = form.waypoints.map((w) => [w.lat, w.lng] as [number, number])

  return (
    <div className="stagger space-y-6">
      <PageHeader title="Routes" subtitle="An ordered path for displays on vehicles. Assign content to a whole route or to one leg, and get an alert when a display leaves the path." />
      <ErrorNote msg={err} />
      <Card pad={false}><div className="p-3"><MapView zones={zones} routes={shown} draft={admin ? draft : undefined} onMapClick={admin && (form.name || form.waypoints.length) ? (p) => addStop({ name: `Stop ${form.waypoints.length + 1}`, lat: +p[0].toFixed(4), lng: +p[1].toFixed(4) }) : undefined} height={380} /></div></Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Your routes">
          <ul className="divide-y divide-ink-100/70 text-sm">
            {routes.map((r) => (
              <li key={r.id} className="py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="size-3 rounded-full" style={{ background: r.color }} />
                  <button className="font-bold hover:underline" onClick={() => setPicked(picked === r.id ? null : r.id)}>{r.name}</button>
                  <span className="text-xs text-ink-500">{r.waypoints.map((w) => w.name).join(' → ')}</span>
                  {admin && <span className="ml-auto space-x-1"><Button variant="secondary" className="!px-2 !py-0.5 text-xs" onClick={() => setForm({ id: r.id, name: r.name, corridor_km: r.corridor_km, color: r.color, waypoints: r.waypoints })}>Edit</Button>
                    <Button variant="ghost" className="!px-2 !py-0.5 text-xs !text-red-600" onClick={() => remove(r)}>Delete</Button></span>}
                </div>
                <p className="mt-1 text-xs text-ink-500">{r.legs} legs · corridor {r.corridor_km} km</p>
                <ul className="mt-1 space-y-1">
                  {r.devices.map((d) => (
                    <li key={d.device_id} className="flex flex-wrap items-center gap-2 text-xs"><b>{d.device_id}</b><span className="text-ink-500">{d.leg_label ?? 'no position yet'}{d.progress != null ? ` · ${d.progress}%` : ''}</span>
                      {d.off_route && <Badge tone="red">off route · {d.offset_km} km</Badge>}</li>
                  ))}
                  {!r.devices.length && <li className="text-xs text-ink-400">No display follows this route. Open a device and choose it under Route.</li>}
                </ul>
              </li>
            ))}
          </ul>
          {!routes.length && <Empty>No routes yet</Empty>}
        </Card>
        {admin && (
          <Card title={form.id ? `Edit ${form.name}` : 'New route'}>
            <form onSubmit={submit}>
              <div className="grid gap-x-3 sm:grid-cols-3">
                <Field label="Name"><input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required minLength={2} placeholder="e.g. Delhi to Jaipur run" /></Field>
                <Field label="Corridor (km)" hint="Farther than this = off route"><input type="number" min={1} className={inputCls} value={form.corridor_km} onChange={(e) => setForm({ ...form, corridor_km: +e.target.value })} /></Field>
                <Field label="Colour"><input type="color" className={inputCls + ' !p-1'} value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} /></Field>
              </div>
              <p className="mb-2 text-xs font-semibold text-ink-500">Stops, in order ({form.waypoints.length}). Click the map to add one, or pick a city.</p>
              <ol className="mb-2 space-y-1.5">
                {form.waypoints.map((w, i) => (
                  <li key={i} className="flex items-center gap-2 text-sm">
                    <span className="w-5 text-xs text-ink-400">{i + 1}</span>
                    <input aria-label={`Stop ${i + 1} name`} className={inputCls + ' !py-1'} value={w.name} onChange={(e) => setForm({ ...form, waypoints: form.waypoints.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })} required />
                    <span className="w-36 shrink-0 text-xs text-ink-500">{w.lat.toFixed(3)}, {w.lng.toFixed(3)}</span>
                    <button type="button" aria-label={`Move stop ${i + 1} up`} disabled={i === 0} className="text-ink-400 disabled:opacity-30" onClick={() => setForm({ ...form, waypoints: form.waypoints.map((x, j, a) => (j === i - 1 ? a[i] : j === i ? a[i - 1] : x)) })}>↑</button>
                    <button type="button" aria-label={`Remove stop ${i + 1}`} className="text-red-500" onClick={() => setForm({ ...form, waypoints: form.waypoints.filter((_, j) => j !== i) })}>×</button>
                  </li>
                ))}
              </ol>
              <div className="mb-3 flex flex-wrap gap-2">
                <select aria-label="Add a city as a stop" className={inputCls + ' max-w-56 !py-1'} value="" onChange={(e) => { const c = cities.find((x) => x.id === e.target.value); if (c) addStop({ name: c.name, lat: c.center[0], lng: c.center[1] }) }}>
                  <option value="">+ Add a city…</option>{cities.map((c) => <option key={c.id} value={c.id}>{c.name}, {c.state}</option>)}
                </select>
              </div>
              <div className="flex gap-2"><Button disabled={form.waypoints.length < 2}>{form.id ? 'Save route' : 'Create route'}</Button>{(form.id || form.waypoints.length > 0 || form.name) && <Button type="button" variant="ghost" onClick={() => setForm(blank)}>Clear</Button>}</div>
              {form.waypoints.length < 2 && <p className="mt-2 text-xs text-ink-400">A route needs at least two stops.</p>}
            </form>
          </Card>
        )}
      </div>
    </div>
  )
}
