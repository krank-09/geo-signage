import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'motion/react'
import { ArrowsClockwise, ArrowUpRight, Cpu, MapPin, MapTrifold, Memory, PlayCircle, WifiHigh } from '@phosphor-icons/react'
import { api, errMsg, isAdmin } from '../../services/api'
import type { Device } from '../../types'
import { CountUp } from '../charts'
import { healthTone } from '../HealthBar'
import { ago, Button } from '../ui'

function Tile({ label, icon, children }: { label: string; icon?: ReactNode; children: ReactNode }) {
  return (
    <div className="rounded-[20px] border border-white/15 bg-white/12 p-4 backdrop-blur-md">
      <div className="flex items-center gap-1.5 text-xs font-medium text-white/65">{icon}{label}</div>
      <div className="mt-1.5 text-[17px] font-bold leading-snug">{children}</div>
    </div>
  )
}

function Meter({ label, icon, value, unit = '%' }: { label: string; icon: ReactNode; value: number | null; unit?: string }) {
  return (
    <div className="rounded-[20px] border border-white/15 bg-white/12 p-4 backdrop-blur-md">
      <div className="flex items-center justify-between text-xs font-medium text-white/65"><span className="flex items-center gap-1.5">{icon}{label}</span><ArrowUpRight size={14} /></div>
      <div className="mt-1.5 text-2xl font-extrabold">{value != null ? <><CountUp value={value} />{unit}</> : '—'}</div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/15"><motion.div className="h-full origin-left rounded-full bg-white" initial={{ scaleX: 0 }} animate={{ scaleX: (value ?? 0) / 100 }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} /></div>
    </div>
  )
}

const TONE_BG = { red: 'bg-red-400', amber: 'bg-amber-300', green: 'bg-emerald-300' }

export function DeviceDetailPanel({ d, threshold }: { d: Device; threshold: number }) {
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const admin = isAdmin()
  const sync = async () => {
    setBusy(true)
    try { await api.post(`/devices/${d.device_id}/sync`); setNote('Sync command sent') } catch (e) { setNote(errMsg(e)) } finally { setBusy(false); setTimeout(() => setNote(''), 2500) }
  }
  return (
    <motion.div key={d.device_id} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="relative flex h-full flex-col overflow-hidden rounded-[28px] bg-gradient-to-br from-brand-500 via-brand-600 to-brand-800 p-6 text-white shadow-[0_30px_60px_-24px_rgb(59_44_168/0.8)]">
      <div className="pointer-events-none absolute -right-20 -top-24 size-72 rounded-full bg-white/10 blur-3xl" />
      <div className="relative grid gap-4 sm:grid-cols-[1.2fr_1fr_1fr]">
        <div><div className="text-xs font-medium text-white/65">Device details</div>
          <div className="mt-1 flex flex-wrap items-center gap-2"><h3 className="text-[28px] font-extrabold tracking-tight"># {d.device_id}</h3>
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${d.status === 'online' ? 'bg-emerald-400/20 text-emerald-100' : 'bg-red-400/25 text-red-100'}`}>{d.status === 'online' ? '● Online' : '● Offline'}</span></div></div>
        <div><div className="text-xs font-medium text-white/65">Name</div><div className="mt-1.5 text-lg font-bold">{d.name}</div></div>
        <div><div className="text-xs font-medium text-white/65">Group</div><div className="mt-1.5 text-lg font-bold">{d.group || 'Ungrouped'}</div></div>
      </div>
      <div className="relative mt-5 grid gap-3 sm:grid-cols-3">
        <Tile label="Zone" icon={<MapPin size={14} weight="bold" />}>{d.zone || <span className="text-white/60">Outside zones</span>}</Tile>
        <Tile label="Now playing" icon={<PlayCircle size={14} weight="bold" />}>{d.current_content || <span className="text-white/60">Nothing yet</span>}</Tile>
        <Tile label="GPS position" icon={<MapTrifold size={14} weight="bold" />}>{d.latitude != null ? `${d.latitude.toFixed(3)}, ${d.longitude!.toFixed(3)}` : <span className="text-white/60">No fix</span>}</Tile>
      </div>
      <div className="relative mt-3 grid gap-3 sm:grid-cols-3">
        <Meter label="CPU" icon={<Cpu size={14} weight="bold" />} value={d.cpu} />
        <Meter label="Memory" icon={<Memory size={14} weight="bold" />} value={d.memory} />
        <div className="rounded-[20px] border border-dashed border-white/30 p-4">
          <div className="flex items-center gap-1.5 text-xs font-medium text-white/65"><WifiHigh size={14} weight="bold" />Link</div>
          <div className="mt-1.5 text-lg font-bold">{d.ws_connected ? 'Live push' : d.status === 'online' ? 'Polling' : 'Disconnected'}</div>
          <div className="text-xs text-white/60">{d.network || 'network unknown'}</div>
        </div>
      </div>
      <div className="relative mt-3 rounded-[20px] border border-white/15 bg-white/12 p-4 backdrop-blur-md">
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-medium text-white/65">
          <span>Health · alert below {threshold}%</span><span>{d.health_reasons.length ? d.health_reasons.join(' · ') : 'All checks passing'}</span>
        </div>
        <div className="mt-2 flex items-center gap-3" role="meter" aria-label="Device health" aria-valuemin={0} aria-valuemax={100} aria-valuenow={d.health}>
          <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-white/15">
            <motion.div className={`h-full origin-left rounded-full ${TONE_BG[healthTone(d.health, threshold)]}`} initial={{ scaleX: 0 }} animate={{ scaleX: d.health / 100 }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} />
            <span className="absolute inset-y-0 w-px bg-white/50" style={{ left: `${threshold}%` }} aria-hidden="true" />
          </div>
          <span className="w-12 text-right text-xl font-extrabold tabular-nums">{d.health}%</span>
        </div>
      </div>
      <div className="relative mt-auto flex flex-wrap items-center gap-x-6 gap-y-3 rounded-[20px] bg-ink-900/25 px-5 py-4 pt-4" style={{ marginTop: 20 }}>
        <div><div className="text-xs text-white/60">Last heartbeat</div><div className="font-bold">{ago(d.last_seen)}</div></div>
        <div><div className="text-xs text-white/60">Agent</div><div className="font-bold">v{d.software_version || '—'}</div></div>
        <div><div className="text-xs text-white/60">Playlist</div><div className="font-bold">{d.content_version ? d.content_version.slice(0, 7) : '—'}</div></div>
        <div className="ml-auto flex items-center gap-2">
          {note && <span className="text-xs text-white/80">{note}</span>}
          <Link to="/devices" className="grid h-10 place-items-center rounded-full border border-white/25 px-4 text-sm font-semibold transition hover:bg-white/15">Manage</Link>
          {admin && <Button variant="light" disabled={busy} onClick={sync} className="!h-10"><ArrowsClockwise size={16} weight="bold" className={busy ? 'animate-spin' : ''} />Force sync</Button>}
        </div>
      </div>
    </motion.div>
  )
}
