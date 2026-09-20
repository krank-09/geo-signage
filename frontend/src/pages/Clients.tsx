import { FormEvent, useCallback, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { api, errMsg, isAdmin, isPlatform, setClientId } from '../services/api'
import type { ClientInfo } from '../types'
import { Badge, Button, Card, Empty, ErrorNote, Field, inputCls, PageHeader } from '../components/ui'

export default function Clients() {
  const [clients, setClients] = useState<ClientInfo[]>([])
  const [name, setName] = useState('')
  const [limit, setLimit] = useState('')
  const [err, setErr] = useState('')
  const [shown, setShown] = useState<number | null>(null)
  const load = useCallback(() => api.get<ClientInfo[]>('/clients').then((r) => setClients(r.data)), [])
  useEffect(() => { load() }, [load])
  if (!isPlatform() || !isAdmin()) return <Navigate to="/" replace />

  const run = async (fn: () => Promise<unknown>) => { try { await fn(); setErr(''); load() } catch (e) { setErr(errMsg(e)) } }
  const add = (e: FormEvent) => { e.preventDefault(); run(async () => { await api.post('/clients', { name, device_limit: limit ? +limit : null }); setName(''); setLimit('') }) }
  const work = (c: ClientInfo) => { setClientId(c.id); window.location.href = '/' }

  return (
    <div className="stagger space-y-6">
      <PageHeader title="Clients" subtitle="Each client is a separate customer: their own displays, content, zones, schedules, users and alerts. Nobody sees another client's data." />
      <ErrorNote msg={err} />
      <Card title="Add client">
        <form onSubmit={add} className="grid items-end gap-x-3 md:grid-cols-3">
          <Field label="Client name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} placeholder="e.g. Acme Retail" /></Field>
          <Field label="Display limit" hint="Optional cap on the number of displays"><input type="number" min={1} className={inputCls} value={limit} onChange={(e) => setLimit(e.target.value)} /></Field>
          <div className="mb-3"><Button>Add client</Button></div>
        </form>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        {clients.map((c) => (
          <Card key={c.id} title={<span className="flex items-center gap-2">{c.name} {!c.active && <Badge tone="red">Suspended</Badge>} {c.tampered > 0 && <Badge tone="red">{c.tampered} flagged</Badge>}</span>}
            actions={<Button variant="secondary" className="!px-3 !py-1 text-xs" onClick={() => work(c)}>Work in this client</Button>}>
            <dl className="grid grid-cols-4 gap-3 text-center text-sm">
              {([['Displays', `${c.devices_online}/${c.devices}`], ['Content', c.content], ['Zones', c.zones], ['Users', c.users]] as const).map(([k, v]) => (
                <div key={k} className="rounded-2xl bg-white/60 py-2"><dd className="text-lg font-bold">{v}</dd><dt className="text-xs text-ink-500">{k}</dt></div>
              ))}
            </dl>
            <p className="mt-3 text-xs text-ink-500">Display limit: <b>{c.device_limit ?? 'none'}</b></p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button variant="secondary" className="!px-3 !py-1 text-xs" onClick={() => setShown(shown === c.id ? null : c.id)}>{shown === c.id ? 'Hide' : 'Show'} enrollment key</Button>
              <Button variant="secondary" className="!px-3 !py-1 text-xs" onClick={() => { const v = prompt('Display limit (blank = none)', c.device_limit?.toString() ?? ''); if (v !== null) run(() => api.put(`/clients/${c.id}`, { device_limit: v ? +v : null, clear_device_limit: !v })) }}>Set limit</Button>
              <Button variant="secondary" className="!px-3 !py-1 text-xs" onClick={() => run(() => api.put(`/clients/${c.id}`, { active: !c.active }))}>{c.active ? 'Suspend' : 'Reactivate'}</Button>
              <Button variant="ghost" className="!px-3 !py-1 text-xs !text-red-600" onClick={() => { if (confirm(`Delete ${c.name}? Only possible when it has no data.`)) run(() => api.delete(`/clients/${c.id}`)) }}>Delete</Button>
            </div>
            {shown === c.id && c.enrollment_key && (
              <div className="mt-3 rounded-2xl bg-ink-900 p-3 text-xs text-white">
                <p className="mb-1 text-ink-300">Put this in a display's .env as <code>ENROLLMENT_KEY</code> so it only shows up for this client when it announces itself.</p>
                <code className="break-all select-all">{c.enrollment_key}</code>
                <div className="mt-2"><Button variant="light" className="!px-3 !py-1 text-xs" onClick={() => { if (confirm('Rotate the key? Displays waiting with the old key stop appearing.')) run(() => api.post(`/clients/${c.id}/rotate-key`)) }}>Rotate key</Button></div>
              </div>
            )}
          </Card>
        ))}
      </div>
      {!clients.length && <Empty>No clients</Empty>}
    </div>
  )
}
