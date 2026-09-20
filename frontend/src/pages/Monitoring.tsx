import { useCallback, useEffect, useState } from 'react'
import { api, errMsg, isAdmin } from '../services/api'
import type { Alert, LogEntry, ZoneVisit } from '../types'
import { HealthBar } from '../components/HealthBar'
import { useToast } from '../components/Toasts'
import { useDevices } from '../hooks/useDevices'
import { useHealthThreshold } from '../hooks/useHealthThreshold'
import { ago, Badge, Button, Card, Empty, ErrorNote, PageHeader, StatusBadge } from '../components/ui'

interface Analytics {
  content: { content_id: number; name: string; views: number; seconds: number }[]
  uptime: { device_id: string; name: string; uptime_24h: number }[]
  zone_visits: { event: string; count: number }[]
}

function Bar({ value, max, tone = 'bg-brand-500' }: { value: number; max: number; tone?: string }) {
  return <div className="h-2 w-full overflow-hidden rounded-full bg-brand-100/60"><div className={`h-2 origin-left rounded-full ${tone}`} style={{ width: `${max ? (value / max) * 100 : 0}%`, animation: 'grow-x 0.9s var(--ease-out-expo) 0.2s both' }} /></div>
}

export default function Monitoring() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [threshold, setThreshold] = useHealthThreshold()
  const [draft, setDraft] = useState<number | null>(null)
  const [thErr, setThErr] = useState('')
  const toast = useToast()
  const admin = isAdmin()
  const [stats, setStats] = useState<Analytics | null>(null)
  const [visits, setVisits] = useState<ZoneVisit[]>([])
  const loadLogs = useCallback(() => api.get('/monitoring/logs?limit=40').then((r) => setLogs(r.data)), [])
  const loadAlerts = useCallback(() => api.get('/alerts?state=all&limit=25').then((r) => setAlerts(r.data)), [])
  useEffect(() => { loadAlerts() }, [loadAlerts])
  const saveThreshold = async () => {
    if (draft === null) return
    setThErr('')
    try { await api.put('/settings/health', { threshold: draft }); setThreshold(draft); setDraft(null); toast('ok', `Alerts now fire below ${draft}% health`); loadAlerts() } catch (e) { setThErr(errMsg(e)) }
  }
  const loadStats = useCallback(() => { api.get('/monitoring/analytics').then((r) => setStats(r.data)); api.get('/monitoring/zone-visits?hours=24').then((r) => setVisits(r.data)) }, [])
  useEffect(() => { loadLogs(); loadStats() }, [loadLogs, loadStats])
  useEffect(() => { const t = setInterval(loadStats, 20000); return () => clearInterval(t) }, [loadStats])
  const { devices: deviceList } = useDevices({ pollMs: 20000, onEvent: (e) => { if (e.event === 'device_update') loadLogs(); else if (e.event === 'alert' || e.event === 'alert_resolved' || e.event === 'alerts_changed') loadAlerts() } })
  const devices = deviceList ?? []
  const maxViews = Math.max(1, ...(stats?.content.map((c) => c.views) ?? [1]))

  return (
    <div className="stagger space-y-6">
      <PageHeader title="Monitoring & analytics" subtitle="Heartbeats, resource use, content views, uptime and the full event log." />
      <Card title="Fleet health">
        <div className="overflow-x-auto"><table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-ink-400"><tr><th className="py-2">Device</th><th>Status</th><th>Health</th><th>Heartbeat</th><th>CPU</th><th>Memory</th><th>Network</th><th>GPS</th><th>Content sync</th></tr></thead>
          <tbody className="divide-y divide-ink-100/70">
            {devices.map((d) => (
              <tr key={d.device_id}><td className="py-2"><b>{d.device_id}</b></td><td><StatusBadge status={d.status} /></td><td className="min-w-32"><HealthBar health={d.health} threshold={threshold} reasons={d.health_reasons} /></td><td>{ago(d.last_seen)}</td>
                <td>{d.cpu != null ? `${d.cpu.toFixed(0)}%` : '—'}</td><td>{d.memory != null ? `${d.memory.toFixed(0)}%` : '—'}</td><td>{d.network || '—'}</td>
                <td>{d.gps_ok ? <Badge tone="green">fix</Badge> : <Badge tone="gray">none</Badge>}</td><td className="text-xs text-ink-500">{d.current_content || '—'}</td></tr>
            ))}
          </tbody></table>{!devices.length && <Empty>No devices</Empty>}</div>
      </Card>
      <Card title="Health alerts">
        <div className="mb-4 flex flex-wrap items-end gap-4">
          <div className="min-w-64 max-w-md flex-1">
            <label htmlFor="threshold" className="mb-1.5 block text-xs font-semibold text-ink-500">Alert me when a device's health drops below <b className="text-ink-900">{draft ?? threshold}%</b></label>
            <input id="threshold" type="range" min={0} max={100} step={5} disabled={!admin} value={draft ?? threshold} onChange={(e) => setDraft(+e.target.value)} className="w-full accent-brand-600" />
            <p className="mt-1 text-xs text-ink-400">Health = 100 minus penalties for high CPU (over 60%), high memory (over 70%), no GPS fix and late heartbeats. Offline devices score 0.</p>
          </div>
          {admin && draft !== null && draft !== threshold && <Button onClick={saveThreshold}>Save threshold</Button>}
        </div>
        <ErrorNote msg={thErr} />
        <ul className="divide-y divide-ink-100/70 text-sm">
          {alerts.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-3 py-2.5">
              <Badge tone={a.resolved_at ? 'green' : a.acknowledged_at ? 'amber' : 'red'}>{a.resolved_at ? 'resolved' : a.acknowledged_at ? 'acknowledged' : 'open'}</Badge>
              <div className="min-w-0 flex-1"><b>{a.device_name || a.device_id}</b> <span className="text-ink-500">{a.message}</span></div>
              <span className="text-xs text-ink-400">{ago(a.created_at)}</span>
              {admin && !a.resolved_at && !a.acknowledged_at && <Button variant="secondary" className="!px-3 !py-1 text-xs" onClick={() => api.post(`/alerts/${a.id}/ack`).then(loadAlerts)}>Acknowledge</Button>}
            </li>
          ))}
        </ul>
        {!alerts.length && <Empty>No alerts yet. Devices below the threshold will show up here and in the bell.</Empty>}
      </Card>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Content views">
          <ul className="space-y-3 text-sm">{stats?.content.map((c) => (
            <li key={c.content_id}><div className="mb-1 flex justify-between"><span>{c.name}</span><span className="text-ink-500">{c.views} views · {Math.round(c.seconds / 60)} min</span></div><Bar value={c.views} max={maxViews} /></li>
          ))}{!stats?.content.length && <li className="text-ink-400">No impressions yet — displays report each play.</li>}</ul>
        </Card>
        <Card title="Device uptime (24h)">
          <ul className="space-y-3 text-sm">{stats?.uptime.map((u) => (
            <li key={u.device_id}><div className="mb-1 flex justify-between"><span>{u.device_id}</span><span className="text-ink-500">{u.uptime_24h}%</span></div>
              <Bar value={u.uptime_24h} max={100} tone={u.uptime_24h > 90 ? 'bg-emerald-500' : u.uptime_24h > 50 ? 'bg-amber-500' : 'bg-red-500'} /></li>
          ))}</ul>
        </Card>
        <Card title="Zone visits (24 h)">
          <ul className="space-y-2 text-sm">{visits.map((z) => <li key={z.zone_id} className="flex justify-between"><span>{z.zone_name} <span className="text-xs text-ink-400">· {z.devices} display{z.devices === 1 ? '' : 's'}</span></span><b>{z.visits}</b></li>)}
            {!visits.length && <li className="text-ink-400">No zone entries yet</li>}</ul>
        </Card>
      </div>
      <Card title="Event log">
        <ul className="max-h-96 space-y-1 overflow-auto text-sm">{logs.map((l) => (
          <li key={l.id} className="flex gap-3"><span className="w-16 shrink-0 text-xs text-ink-400">{ago(l.ts)}</span><Badge tone={l.kind === 'offline' ? 'red' : l.kind === 'online' ? 'green' : 'gray'}>{l.kind}</Badge><b>{l.device_id}</b><span className="text-ink-500">{l.message}</span></li>
        ))}</ul>
      </Card>
    </div>
  )
}
