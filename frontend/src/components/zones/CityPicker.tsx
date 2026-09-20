import { useCallback, useEffect, useMemo, useState } from 'react'
import { MagnifyingGlass, MapPinArea } from '@phosphor-icons/react'
import { api, errMsg } from '../../services/api'
import type { City, CityDetail, Zone } from '../../types'
import { useToast } from '../Toasts'
import { Badge, Button, ErrorNote, inputCls } from '../ui'

/** Pick a predefined city, preview its boundary on the map, create the zone in one click. */
export function CityPicker({ onPreview, onCreated }: { onPreview: (polygon: [number, number][] | null) => void; onCreated: (zone: Zone) => void }) {
  const toast = useToast()
  const [cities, setCities] = useState<City[]>([])
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState<City | null>(null)
  const [priority, setPriority] = useState(10)
  const [color, setColor] = useState('#3b82f6')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => api.get('/cities').then((r) => setCities(r.data)), [])
  useEffect(() => { load() }, [load])
  useEffect(() => () => onPreview(null), [onPreview])   // clear the outline when leaving

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return needle ? cities.filter((c) => c.name.toLowerCase().includes(needle) || c.state.toLowerCase().includes(needle)) : cities
  }, [cities, q])

  const choose = async (c: City) => {
    setSelected(c); setErr('')
    const { data } = await api.get<CityDetail>(`/cities/${c.id}`)
    onPreview(data.polygon)
  }
  const create = async () => {
    if (!selected) return
    setBusy(true); setErr('')
    try {
      const { data } = await api.post<Zone>(`/cities/${selected.id}/zone`, { priority, color })
      toast('ok', `${data.name} created`)
      setSelected(null); onPreview(null); await load(); onCreated(data)
    } catch (e) { setErr(errMsg(e)) } finally { setBusy(false) }
  }

  return (
    <div>
      <div className="glass mb-3 flex items-center gap-2 rounded-full px-4 py-2 focus-within:ring-2 focus-within:ring-brand-500">
        <MagnifyingGlass size={16} className="text-ink-400" aria-hidden="true" />
        <input value={q} onChange={(e) => setQ(e.target.value)} name="city-search" autoComplete="off" spellCheck={false} aria-label="Search cities"
          placeholder="Search city or state…" className="w-full bg-transparent text-sm outline-none placeholder:text-ink-300" />
      </div>
      <ul className="max-h-64 space-y-1 overflow-auto pr-1" aria-label="Cities">
        {shown.map((c) => (
          <li key={c.id}>
            <button onClick={() => choose(c)} disabled={c.zone_exists} aria-pressed={selected?.id === c.id}
              className={`flex w-full items-center gap-2 rounded-2xl px-3 py-2 text-left text-sm transition ${selected?.id === c.id ? 'bg-brand-600 text-white' : c.zone_exists ? 'text-ink-400' : 'hover:bg-white/80'}`}>
              <MapPinArea size={16} aria-hidden="true" className="shrink-0" />
              <span className="min-w-0 flex-1"><b className="font-semibold">{c.name}</b> <span className={selected?.id === c.id ? 'text-white/70' : 'text-ink-400'}>{c.state}</span></span>
              {c.zone_exists ? <Badge tone="green">Added</Badge> : (
                <span className={`shrink-0 text-xs ${selected?.id === c.id ? 'text-white/80' : 'text-ink-400'}`} title={c.source === 'osm' ? 'Boundary from OpenStreetMap' : 'A 15 km circle around the centre (no reliable boundary available)'}>
                  {c.source === 'osm' ? `boundary · ${c.area_km2.toLocaleString()} km²` : 'circle · approx'}
                </span>
              )}
            </button>
          </li>
        ))}
        {!shown.length && <li className="py-6 text-center text-sm text-ink-400">No city matches “{q}”.</li>}
      </ul>
      {selected && (
        <div className="mt-3 rounded-2xl bg-brand-50 p-3">
          <ErrorNote msg={err} />
          <p className="mb-2 text-sm"><b>{selected.name} Zone</b> will cover the outlined area{selected.source === 'approx' && ' (an approximate 15 km circle)'}.</p>
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs font-semibold text-ink-500">Priority<input type="number" className={inputCls + ' mt-1 !w-20'} value={priority} onChange={(e) => setPriority(+e.target.value)} /></label>
            <label className="text-xs font-semibold text-ink-500">Colour<input type="color" className="mt-1 block h-9 w-14 rounded" value={color} onChange={(e) => setColor(e.target.value)} /></label>
            <Button onClick={create} disabled={busy}>{busy ? 'Creating…' : 'Create zone'}</Button>
            <Button variant="ghost" onClick={() => { setSelected(null); onPreview(null) }}>Cancel</Button>
          </div>
        </div>
      )}
      <p className="mt-2 text-[11px] text-ink-400">Boundaries © OpenStreetMap contributors (ODbL).</p>
    </div>
  )
}
