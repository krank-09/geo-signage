import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import { Eye, MagnifyingGlass, Plus, Television, WifiHigh, Warning, MapTrifold } from '@phosphor-icons/react'
import { api, isAdmin } from '../services/api'
import type { Assignment, LogEntry, Zone } from '../types'
import { useDevices } from '../hooks/useDevices'
import { useHealthThreshold } from '../hooks/useHealthThreshold'
import { HealthBar } from '../components/HealthBar'
import MapView from '../components/MapView'
import { Kpi } from '../components/dashboard/Kpi'
import { DeviceDetailPanel } from '../components/dashboard/DeviceDetailPanel'
import { BarChart, CountUp, LineChart } from '../components/charts'
import { ago, Avatar, Button, Card, Empty, inputCls, PageHeader, PulseDot, Skeleton } from '../components/ui'

interface Timeline { devices_total: number; online: { ts: string; value: number }[]; views: { ts: string; value: number }[] }

const hourLabel = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: 'numeric' }).replace(' ', '').toLowerCase()
const clockLabel = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

export default function Dashboard() {
  const [zones, setZones] = useState<Zone[]>([])
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [timeline, setTimeline] = useState<Timeline | null>(null)
  const [alerts, setAlerts] = useState<Assignment[]>([])
  const [healthAlerts, setHealthAlerts] = useState(0)
  const [threshold] = useHealthThreshold()
  const [selected, setSelected] = useState<string | null>(null)
  const [tab, setTab] = useState<'all' | 'online' | 'offline'>('all')
  const [query, setQuery] = useState('')
  const [group, setGroup] = useState('')
  const admin = isAdmin()

  const loadLogs = useCallback(() => api.get('/monitoring/logs?limit=8').then((r) => setLogs(r.data)), [])
  const loadTimeline = useCallback(() => api.get('/monitoring/timeline').then((r) => setTimeline(r.data)), [])
  const loadAlerts = useCallback(() => {
    api.get('/emergency').then((r) => setAlerts(r.data))
    api.get('/alerts').then((r) => setHealthAlerts(r.data.length))
  }, [])
  const loadZones = useCallback(() => api.get('/zones').then((r) => setZones(r.data)), [])
  useEffect(() => { loadZones(); loadLogs(); loadTimeline(); loadAlerts() }, [loadZones, loadLogs, loadTimeline, loadAlerts])
  useEffect(() => {
    const t = setInterval(loadTimeline, 15000)
    return () => clearInterval(t)
  }, [loadTimeline])

  const { devices, live } = useDevices({
    pollMs: 15000,
    onEvent: (e) => {
      if (e.event === 'device_update') loadLogs()
      else if (e.event === 'assignments_changed') { loadZones(); loadAlerts() }
      else if (e.event === 'alert' || e.event === 'alert_resolved' || e.event === 'alerts_changed') loadAlerts()
    },
  })

  const list = devices ?? []
  const online = list.filter((d) => d.status === 'online').length
  const groups = useMemo(() => [...new Set(list.map((d) => d.group).filter(Boolean))] as string[], [list])
  const filtered = list.filter((d) =>
    (tab === 'all' || d.status === tab) && (!group || d.group === group) &&
    (!query || `${d.device_id} ${d.name} ${d.zone ?? ''} ${d.current_content ?? ''}`.toLowerCase().includes(query.toLowerCase())))
  const current = list.find((d) => d.device_id === selected) ?? filtered[0] ?? null
  const totalViews = timeline?.views.reduce((a, b) => a + b.value, 0) ?? 0
  const peakOnline = timeline ? Math.max(...timeline.online.map((p) => p.value)) : 0

  return (
    <div className="stagger space-y-6">
      <PageHeader title="Overview" subtitle="Live status of every display, zone and content decision in one place."
        actions={<>
          {alerts.length > 0 && <Link to="/emergency" className="flex items-center gap-1.5 rounded-full bg-red-500/12 px-3.5 py-2 text-sm font-bold text-red-700"><Warning size={16} weight="fill" />{alerts.length} alert{alerts.length > 1 ? 's' : ''} live</Link>}
          {admin && <Link to="/devices"><Button><Plus size={16} weight="bold" />Add device</Button></Link>}
        </>} />

      {/* KPI row */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {devices === null ? [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[214px]" />) : (
          <>
            <Kpi title="Devices online" icon={<Television size={16} weight="bold" />}>
              <div className="flex items-baseline gap-1.5"><span className="text-[40px] font-extrabold leading-none tracking-tight"><CountUp value={online} /></span><span className="text-lg font-semibold text-ink-400">/ {list.length}</span></div>
              <div className={`mt-2 text-xs font-bold ${list.length - online ? 'text-red-600' : 'text-emerald-600'}`}>{list.length - online ? `▼ ${list.length - online} offline` : '▲ All displays healthy'}</div>
              <div className="mt-auto space-y-1.5 pt-4">
                {list.slice(0, 4).map((d) => (
                  <div key={d.device_id} className="flex items-center gap-2 text-xs"><PulseDot online={d.status === 'online'} /><span className="font-semibold">{d.device_id}</span><span className="truncate text-ink-400">{d.zone || 'outside zones'}</span></div>
                ))}
              </div>
            </Kpi>
            <Kpi title="Views · last 12 hours" icon={<Eye size={16} weight="bold" />}>
              <div className="text-[40px] font-extrabold leading-none tracking-tight"><CountUp value={totalViews} /></div>
              <div className="mt-2 text-xs font-semibold text-ink-400">Counted when a display finishes an item</div>
              <div className="mt-auto pt-3">{timeline && <BarChart values={timeline.views.map((v) => v.value)} labels={timeline.views.map((v, i) => (i % 3 === 0 ? hourLabel(v.ts) : ''))} height={64} />}</div>
            </Kpi>
            <Kpi title="Fleet online · last 3 hours" icon={<WifiHigh size={16} weight="bold" />}>
              <div className="flex items-baseline gap-2"><span className="text-[40px] font-extrabold leading-none tracking-tight"><CountUp value={online} /></span><span className="text-sm font-semibold text-ink-400">peak {peakOnline}</span></div>
              <div className="mt-auto pt-2">{timeline && <LineChart values={timeline.online.map((p) => p.value)} labels={timeline.online.map((p) => clockLabel(p.ts))} height={92} max={Math.max(list.length, 1)} />}</div>
            </Kpi>
            <Kpi title="Zones & alerts" icon={<MapTrifold size={16} weight="bold" />}>
              <div className="flex items-baseline gap-1.5"><span className="text-[40px] font-extrabold leading-none tracking-tight"><CountUp value={zones.length} /></span><span className="text-lg font-semibold text-ink-400">geofences</span></div>
              <div className={`mt-2 text-xs font-bold ${alerts.length ? 'text-red-600' : 'text-emerald-600'}`}>{alerts.length ? `${alerts.length} emergency override active` : 'No active emergency alerts'}</div>
              <Link to="/monitoring" className={`text-xs font-bold ${healthAlerts ? 'text-red-600' : 'text-ink-400'}`}>{healthAlerts ? `${healthAlerts} device health alert${healthAlerts > 1 ? 's' : ''} open` : 'All device health OK'}</Link>
              <div className="relative mt-auto flex items-end gap-2 pt-4">
                {zones.slice(0, 3).map((z, i) => (
                  <motion.div key={z.id} initial={{ y: 24, opacity: 0 }} animate={{ y: [0, 8, 0][i] ?? 0, opacity: 1 }} transition={{ delay: 0.3 + i * 0.1, type: 'spring', stiffness: 220, damping: 22 }}
                    className="flex-1 rounded-2xl p-2.5 text-white" style={{ background: `linear-gradient(160deg, ${z.color}, ${z.color}aa)`, height: 78 - i * 6 }}>
                    <div className="text-[10px] font-semibold opacity-80">{devices.filter((d) => d.zone_id === z.id).length} device(s)</div>
                    <div className="mt-1 truncate text-xs font-bold">{z.name.replace(' Zone', '')}</div>
                  </motion.div>
                ))}
                {!zones.length && <Link to="/zones" className="w-full rounded-2xl border border-dashed border-brand-300 p-3 text-center text-xs font-semibold text-brand-600">Draw your first zone</Link>}
              </div>
            </Kpi>
          </>
        )}
      </div>

      {/* filters */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex items-center gap-2 text-sm font-bold">Fleet<span className="grid size-6 place-items-center rounded-full bg-ink-900 text-xs text-white">{filtered.length}</span></span>
        <div className="glass flex min-w-[220px] flex-1 items-center gap-2 rounded-full px-4 py-2 focus-within:ring-2 focus-within:ring-brand-500 md:max-w-sm">
          <MagnifyingGlass size={16} className="text-ink-400" aria-hidden="true" /><input value={query} onChange={(e) => setQuery(e.target.value)} name="device-search" autoComplete="off" spellCheck={false} placeholder="Search device, zone or content…" aria-label="Search devices" className="w-full bg-transparent text-sm outline-none placeholder:text-ink-300 focus-visible:!outline-none" />
        </div>
        <div className="glass relative rounded-full">
          <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Filter by group" className={`${inputCls} !w-auto !rounded-full !border-0 !bg-transparent !py-2.5`}>
            <option value="">All groups</option>{groups.map((g) => <option key={g}>{g}</option>)}
          </select>
        </div>
      </div>

      {/* dark list + violet detail (Image 1) */}
      <section className="rounded-[36px] bg-ink-900 p-3 shadow-[0_40px_80px_-30px_rgb(20_22_43/0.7)] md:p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 px-2 pt-1">
          <h2 className="text-base font-bold text-white">Displays</h2>
          <div role="tablist" aria-label="Status filter" className="relative flex rounded-full bg-ink-800 p-1">
            {(['all', 'online', 'offline'] as const).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`relative rounded-full px-4 py-1.5 text-xs font-bold capitalize transition-colors ${tab === t ? 'text-white' : 'text-ink-300 hover:text-white'}`}>
                {tab === t && <motion.span layoutId="dash-tab" className="absolute inset-0 rounded-full bg-brand-600" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}
                <span className="relative">{t === 'all' ? 'All devices' : t}{t !== 'all' && <span className="ml-1 opacity-70">{list.filter((d) => d.status === t).length}</span>}</span>
              </button>
            ))}
          </div>
          <span className="w-16" />
        </div>
        <div className="grid gap-4 lg:grid-cols-[minmax(320px,380px)_1fr]">
          <ul className="space-y-1.5" aria-label="Devices">
            {filtered.map((d) => {
              const active = current?.device_id === d.device_id
              return (
                <li key={d.device_id}>
                  <button onClick={() => setSelected(d.device_id)} aria-pressed={active} className={`relative flex w-full items-center gap-3 rounded-[20px] p-3 text-left transition-colors ${active ? '' : 'hover:bg-ink-800'}`}>
                    {active && <motion.span layoutId="dash-row" className="absolute inset-0 rounded-[20px] bg-brand-600" transition={{ type: 'spring', stiffness: 420, damping: 36 }} />}
                    <span className="relative"><Avatar label={d.device_id} tint={zones.find((z) => z.id === d.zone_id)?.color} size={44} /></span>
                    <span className="relative min-w-0 flex-1">
                      <span className="block truncate text-sm font-bold text-white"># {d.device_id}</span>
                      <span className="block truncate text-xs text-ink-300">{d.zone || 'Outside zones'} · {ago(d.last_seen)}</span>
                      <HealthBar health={d.health} threshold={threshold} reasons={d.health_reasons} dark label={false} className="mt-1.5 max-w-[150px]" />
                    </span>
                    <span className="relative text-right">
                      <span className={`inline-block rounded-full px-2.5 py-0.5 text-[11px] font-bold ${active ? 'bg-white text-ink-900' : d.status === 'online' ? 'bg-emerald-400/15 text-emerald-300' : 'bg-red-400/15 text-red-300'}`}>{d.status === 'online' ? 'Online' : 'Offline'}</span>
                      <span className="mt-1 block max-w-[110px] truncate text-[11px] font-semibold text-white/80">{d.current_content || '—'}</span>
                    </span>
                  </button>
                </li>
              )
            })}
            {devices !== null && !filtered.length && <li className="rounded-[20px] bg-ink-800 py-10 text-center text-sm text-ink-300">No devices match these filters</li>}
            {devices === null && [0, 1, 2].map((i) => <li key={i} className="h-[68px] animate-pulse rounded-[20px] bg-ink-800" />)}
          </ul>
          <div className="min-h-[420px]">
            <AnimatePresence mode="wait">{current ? <DeviceDetailPanel key={current.device_id} d={current} threshold={threshold} /> : <div className="grid h-full place-items-center rounded-[28px] bg-ink-800 text-ink-300">Select a device</div>}</AnimatePresence>
          </div>
        </div>
      </section>

      {/* map + activity */}
      <div className="grid gap-6 xl:grid-cols-3">
        <Card title="Live map" className="xl:col-span-2" actions={<Link to="/zones" className="text-xs font-bold text-brand-600 hover:underline">Edit zones →</Link>}>
          <MapView zones={zones} devices={list} height={430} />
        </Card>
        <Card title="Recent activity" actions={<span className="flex items-center gap-1.5 text-xs font-semibold text-ink-500"><PulseDot online={live} />{live ? 'live' : 'reconnecting'}</span>}>
          <ol className="relative space-y-4 before:absolute before:bottom-1 before:left-[5px] before:top-1 before:w-px before:bg-ink-200">
            <AnimatePresence initial={false}>
              {logs.map((l) => (
                <motion.li key={l.id} layout initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} className="relative pl-6 text-sm">
                  <span className={`absolute left-0 top-1.5 size-[11px] rounded-full ring-4 ring-white/80 ${l.kind === 'offline' ? 'bg-red-500' : l.kind === 'online' ? 'bg-emerald-500' : 'bg-brand-500'}`} />
                  <b>{l.device_id}</b> <span className="text-ink-500">{l.message}</span><div className="text-xs text-ink-400">{ago(l.ts)}</div>
                </motion.li>
              ))}
            </AnimatePresence>
          </ol>
          {!logs.length && <Empty>No events yet</Empty>}
        </Card>
      </div>
    </div>
  )
}
