import { useCallback, useEffect, useState } from 'react'
import { api } from '../services/api'
import type { LogEntry } from '../types'
import { useDevices } from '../hooks/useDevices'
import { ago, Badge, Card, Empty, PageHeader, StatusBadge } from '../components/ui'

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
  const [stats, setStats] = useState<Analytics | null>(null)
  const loadLogs = useCallback(() => api.get('/monitoring/logs?limit=40').then((r) => setLogs(r.data)), [])
  const loadStats = useCallback(() => api.get('/monitoring/analytics').then((r) => setStats(r.data)), [])
  useEffect(() => { loadLogs(); loadStats() }, [loadLogs, loadStats])
  useEffect(() => { const t = setInterval(loadStats, 20000); return () => clearInterval(t) }, [loadStats])
  const { devices: deviceList } = useDevices({ pollMs: 20000, onEvent: (e) => { if (e.event === 'device_update') loadLogs() } })
  const devices = deviceList ?? []
  const maxViews = Math.max(1, ...(stats?.content.map((c) => c.views) ?? [1]))

  return (
    <div className="stagger space-y-6">
      <PageHeader title="Monitoring & analytics" subtitle="Heartbeats, resource use, content views, uptime and the full event log." />
      <Card title="Fleet health">
        <div className="overflow-x-auto"><table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-ink-400"><tr><th className="py-2">Device</th><th>Status</th><th>Heartbeat</th><th>CPU</th><th>Memory</th><th>Network</th><th>GPS</th><th>Content sync</th></tr></thead>
          <tbody className="divide-y divide-ink-100/70">
            {devices.map((d) => (
              <tr key={d.device_id}><td className="py-2"><b>{d.device_id}</b></td><td><StatusBadge status={d.status} /></td><td>{ago(d.last_seen)}</td>
                <td>{d.cpu != null ? `${d.cpu.toFixed(0)}%` : '—'}</td><td>{d.memory != null ? `${d.memory.toFixed(0)}%` : '—'}</td><td>{d.network || '—'}</td>
                <td>{d.gps_ok ? <Badge tone="green">fix</Badge> : <Badge tone="gray">none</Badge>}</td><td className="text-xs text-ink-500">{d.current_content || '—'}</td></tr>
            ))}
          </tbody></table>{!devices.length && <Empty>No devices</Empty>}</div>
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
        <Card title="Zone visits">
          <ul className="space-y-2 text-sm">{stats?.zone_visits.map((z) => <li key={z.event} className="flex justify-between"><span>{z.event}</span><b>{z.count}</b></li>)}
            {!stats?.zone_visits.length && <li className="text-ink-400">No zone events yet</li>}</ul>
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
