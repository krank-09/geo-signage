import { useCallback, useEffect, useState } from 'react'
import { api, errMsg, isAdmin } from '../services/api'
import type { Assignment, Zone } from '../types'
import { useDevices } from '../hooks/useDevices'
import AssignmentForm from '../components/AssignmentForm'
import MapView from '../components/MapView'
import { CityPicker } from '../components/zones/CityPicker'
import { Badge, Button, Card, Empty, ErrorNote, Field, inputCls, PageHeader } from '../components/ui'

const circlePolygon = ([lat, lng]: [number, number], km: number, n = 32): [number, number][] =>
  Array.from({ length: n }, (_, i) => {
    const a = (2 * Math.PI * i) / n
    return [+(lat + (km / 111) * Math.sin(a)).toFixed(5), +(lng + (km / (111 * Math.cos((lat * Math.PI) / 180))) * Math.cos(a)).toFixed(5)] as [number, number]
  })

export default function Zones() {
  const [zones, setZones] = useState<Zone[]>([])
  const { devices: deviceList } = useDevices()
  const devices = deviceList ?? []
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [mode, setMode] = useState<'none' | 'polygon' | 'circle'>('none')
  const [draft, setDraft] = useState<[number, number][]>([])
  const [preview, setPreview] = useState<[number, number][] | null>(null)
  const [radius, setRadius] = useState(30)
  const [form, setForm] = useState({ name: '', priority: 10, color: '#3b82f6' })
  const [err, setErr] = useState('')
  const admin = isAdmin()

  const load = useCallback(() => {
    api.get('/zones').then((r) => setZones(r.data))
    api.get('/assignments').then((r) => setAssignments(r.data))
  }, [])
  useEffect(() => { load() }, [load])

  const onMapClick = (p: [number, number]) => {
    if (mode === 'polygon') setDraft((d) => [...d, p])
    else if (mode === 'circle') setDraft(circlePolygon(p, radius))
  }
  const cancel = () => { setMode('none'); setDraft([]); setErr('') }
  const create = async () => {
    setErr('')
    try {
      const { data } = await api.post('/zones', { name: form.name, polygon: draft, priority: form.priority, color: form.color })
      cancel(); setForm({ ...form, name: '' }); load(); setSelected(data.id)
    } catch (e) { setErr(errMsg(e)) }
  }
  const sel = zones.find((z) => z.id === selected)
  const zoneAssignments = assignments.filter((a) => a.zone_id === selected)

  return (
    <div className="stagger space-y-6">
      <PageHeader title="Zones & map" subtitle="Draw geofences, then decide what plays inside each one."
        actions={admin && mode === 'none' && <><Button onClick={() => setMode('polygon')}>✎ Draw polygon</Button><Button variant="secondary" onClick={() => setMode('circle')}>◯ Circle by radius</Button></>} />
      {mode !== 'none' && (
        <Card title={mode === 'polygon' ? 'Click the map to add corners (min. 3)' : 'Click the map to place the zone centre'}>
          <ErrorNote msg={err} />
          <div className="grid items-end gap-x-3 md:grid-cols-5">
            <Field label="Zone name"><input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Priority" hint="Higher wins where zones overlap"><input type="number" className={inputCls} value={form.priority} onChange={(e) => setForm({ ...form, priority: +e.target.value })} /></Field>
            <Field label="Colour"><input type="color" className="h-9 w-full rounded" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} /></Field>
            {mode === 'circle' && <Field label="Radius (km)"><input type="number" min={1} className={inputCls} value={radius} onChange={(e) => setRadius(+e.target.value)} /></Field>}
            <div className="mb-3 flex gap-2">
              <Button disabled={draft.length < 3 || !form.name} onClick={create}>Save zone</Button>
              {mode === 'polygon' && <Button variant="secondary" onClick={() => setDraft((d) => d.slice(0, -1))}>Undo</Button>}
              <Button variant="ghost" onClick={cancel}>Cancel</Button>
            </div>
          </div>
        </Card>
      )}
      <div className="grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2"><MapView zones={zones} devices={devices} draft={draft} preview={preview} height={520} selectedZone={selected}
          onMapClick={mode !== 'none' ? onMapClick : undefined} onZoneClick={(z) => mode === 'none' && setSelected(z.id)} /></Card>
        <div className="space-y-6">
          {admin && (
            <Card title="Add a city">
              <p className="mb-3 text-sm text-ink-500">Pick a city and its boundary becomes a zone instantly. No drawing needed.</p>
              <CityPicker onPreview={setPreview} onCreated={(z) => { load(); setSelected(z.id) }} />
            </Card>
          )}
          <Card title="Zones">
            <ul className="divide-y divide-ink-100/70">
              {zones.map((z) => (
                <li key={z.id} className={`flex cursor-pointer items-center gap-2 py-2 ${selected === z.id ? 'font-semibold' : ''}`} onClick={() => setSelected(z.id)}>
                  <span className="h-3 w-3 rounded-full" style={{ background: z.color }} />{z.name}
                  <Badge tone="gray">P{z.priority}</Badge>
                  <span className="text-xs text-ink-400">{devices.filter((d) => d.zone_id === z.id).length} device(s)</span>
                  {admin && <button className="ml-auto text-ink-400 hover:text-red-600" onClick={async (e) => { e.stopPropagation(); if (confirm(`Delete ${z.name} and its assignments?`)) { await api.delete(`/zones/${z.id}`); if (selected === z.id) setSelected(null); load() } }}>✕</button>}
                </li>
              ))}
            </ul>
            {!zones.length && <Empty>No zones — draw one on the map</Empty>}
          </Card>
          {sel && (
            <Card title={`Content for ${sel.name}`}>
              <ul className="mb-3 space-y-1 text-sm">
                {zoneAssignments.map((a) => (
                  <li key={a.id} className="flex items-center gap-2">
                    <span className={a.active ? '' : 'text-ink-400 line-through'}>{a.content_name}</span>
                    {a.start_time && <Badge tone="blue">{a.start_time}–{a.end_time}</Badge>}<Badge tone="gray">P{a.priority}</Badge>
                    {a.is_emergency && <Badge tone="red">emergency</Badge>}
                    {admin && <button className="ml-auto text-ink-400 hover:text-red-600" onClick={async () => { await api.delete(`/assignments/${a.id}`); load() }}>✕</button>}
                  </li>
                ))}
                {!zoneAssignments.length && <li className="text-ink-400">Nothing assigned — devices here get default content</li>}
              </ul>
              {admin && <AssignmentForm zoneId={sel.id} lockZone onDone={load} />}
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
