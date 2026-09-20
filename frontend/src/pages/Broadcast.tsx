import { FormEvent, useCallback, useEffect, useState } from 'react'
import { Megaphone, Rows, Stop, TextAa } from '@phosphor-icons/react'
import { api, errMsg, isAdmin } from '../services/api'
import type { Broadcast as BroadcastT, Group, Zone } from '../types'
import { useDevices } from '../hooks/useDevices'
import { useLive } from '../hooks/useLive'
import { useToast } from '../components/Toasts'
import { Badge, Button, Card, Empty, ErrorNote, Field, inputCls, PageHeader } from '../components/ui'

type Style = BroadcastT['style']
type Severity = BroadcastT['severity']
const STYLES: { id: Style; label: string; hint: string; icon: typeof Rows }[] = [
  { id: 'ticker', label: 'Ticker', hint: 'Scrolls along the bottom', icon: TextAa },
  { id: 'banner', label: 'Banner', hint: 'A bar at the top', icon: Rows },
  { id: 'fullscreen', label: 'Fullscreen', hint: 'Replaces the screen', icon: Megaphone },
]
const SEVERITY_BG: Record<Severity, string> = { info: 'bg-indigo-700', warning: 'bg-amber-700', critical: 'bg-red-700' }
const DURATIONS: [string, number | null][] = [['Until I end it', null], ['30 seconds', 30], ['1 minute', 60], ['5 minutes', 300], ['15 minutes', 900], ['1 hour', 3600]]

function Preview({ message, style, severity }: { message: string; style: Style; severity: Severity }) {
  const text = message.trim() || 'Your announcement appears here'
  return (
    <div className="relative aspect-video overflow-hidden rounded-2xl bg-gradient-to-br from-emerald-500 to-lime-500 text-white shadow-inner" aria-label="Preview of the display">
      <div className="absolute inset-0 grid place-items-center text-center"><div><div className="text-4xl font-light">Delhi</div><div className="text-xs opacity-80">Advertisement for Delhi</div></div></div>
      {style === 'banner' && <div className={`absolute left-1/2 top-3 max-w-[85%] -translate-x-1/2 rounded-full px-5 py-2 text-center text-sm font-bold shadow-lg ${SEVERITY_BG[severity]}`}>{text}</div>}
      {style === 'ticker' && (
        <div className={`absolute inset-x-0 bottom-0 flex h-9 items-center overflow-hidden whitespace-nowrap text-sm font-bold ${SEVERITY_BG[severity]}`}>
          <span className="inline-block pl-[100%]" style={{ animation: 'marquee 14s linear infinite' }}>{text}</span>
        </div>
      )}
      {style === 'fullscreen' && <div className={`absolute inset-0 grid place-items-center p-6 text-center text-xl font-extrabold leading-tight ${SEVERITY_BG[severity]}`}>{text}</div>}
    </div>
  )
}

const target = (b: BroadcastT) => [b.zone_name && `zone ${b.zone_name}`, b.group_name && `group ${b.group_name}`, b.device_id && `display ${b.device_id}`].filter(Boolean).join(' · ') || 'Everyone'
const countdown = (s: number | null) => (s === null ? 'until ended' : s >= 3600 ? `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m left` : s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s left` : `${s}s left`)

export default function Broadcast() {
  const admin = isAdmin()
  const toast = useToast()
  const { devices } = useDevices()
  const [zones, setZones] = useState<Zone[]>([])
  const [groups, setGroups] = useState<Group[]>([])
  const [list, setList] = useState<BroadcastT[]>([])
  const [message, setMessage] = useState('')
  const [style, setStyle] = useState<Style>('ticker')
  const [severity, setSeverity] = useState<Severity>('info')
  const [audience, setAudience] = useState<'all' | 'zone' | 'group' | 'device'>('all')
  const [targetId, setTargetId] = useState('')
  const [duration, setDuration] = useState<number | null>(60)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [, tick] = useState(0)

  const load = useCallback(() => api.get('/broadcasts?limit=30').then((r) => setList(r.data)), [])
  useEffect(() => { load(); api.get('/zones').then((r) => setZones(r.data)); api.get('/groups').then((r) => setGroups(r.data)) }, [load])
  useLive((e) => { if (e.event === 'broadcasts_changed') load() })
  useEffect(() => { const t = setInterval(() => { tick((n) => n + 1); load() }, 5000); return () => clearInterval(t) }, [load])

  const go = async (e: FormEvent) => {
    e.preventDefault(); setErr(''); setBusy(true)
    try {
      await api.post('/broadcasts', {
        message, style, severity, duration_seconds: duration,
        zone_id: audience === 'zone' ? +targetId : null, group_id: audience === 'group' ? +targetId : null, device_id: audience === 'device' ? targetId : null,
      })
      setMessage(''); toast('ok', 'Broadcast is live'); load()
    } catch (x) { setErr(errMsg(x)) } finally { setBusy(false) }
  }
  const end = async (id: number) => { await api.delete(`/broadcasts/${id}`); load() }

  const active = list.filter((b) => b.active)
  const past = list.filter((b) => !b.active).slice(0, 8)
  const needsTarget = audience !== 'all'

  return (
    <div className="stagger space-y-6">
      <PageHeader title="Live broadcast" subtitle="Push an announcement to displays right now. It overlays what is playing, without interrupting the playlist, and disappears when it ends."
        actions={admin && active.length > 0 && <Button variant="secondary" onClick={async () => { await api.delete('/broadcasts'); load() }}><Stop size={16} weight="fill" aria-hidden="true" />End all ({active.length})</Button>} />

      {admin ? (
        <div className="grid gap-6 xl:grid-cols-[1.15fr_1fr]">
          <Card title="Compose">
            <form onSubmit={go}>
              <ErrorNote msg={err} />
              <Field label={`Message (${message.length}/280)`}>
                <textarea className={inputCls + ' min-h-24 resize-y'} maxLength={280} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Flash sale in Delhi: 30% off until 6 pm…" required />
              </Field>
              <fieldset className="mb-3"><legend className="mb-1.5 text-xs font-semibold text-ink-500">How it appears</legend>
                <div className="grid grid-cols-3 gap-2">
                  {STYLES.map(({ id, label, hint, icon: Icon }) => (
                    <label key={id} className={`cursor-pointer rounded-2xl border p-3 text-sm transition ${style === id ? 'border-brand-500 bg-brand-50 ring-2 ring-brand-100' : 'border-ink-200 bg-white/70 hover:border-brand-300'}`}>
                      <input type="radio" name="style" className="sr-only" checked={style === id} onChange={() => setStyle(id)} />
                      <Icon size={18} aria-hidden="true" className="mb-1 text-brand-600" /><div className="font-semibold">{label}</div><div className="text-xs text-ink-500">{hint}</div>
                    </label>
                  ))}
                </div>
              </fieldset>
              <fieldset className="mb-3"><legend className="mb-1.5 text-xs font-semibold text-ink-500">Importance</legend>
                <div className="flex gap-2">
                  {(['info', 'warning', 'critical'] as Severity[]).map((s) => (
                    <label key={s} className={`cursor-pointer rounded-full px-4 py-1.5 text-sm font-semibold capitalize text-white transition ${SEVERITY_BG[s]} ${severity === s ? 'ring-4 ring-ink-900/15' : 'opacity-55 hover:opacity-90'}`}>
                      <input type="radio" name="severity" className="sr-only" checked={severity === s} onChange={() => setSeverity(s)} />{s}
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="grid gap-x-3 md:grid-cols-2">
                <Field label="Who sees it">
                  <select className={inputCls} value={audience} onChange={(e) => { setAudience(e.target.value as typeof audience); setTargetId('') }}>
                    <option value="all">Everyone</option><option value="zone">A zone</option><option value="group">A device group</option><option value="device">One display</option>
                  </select>
                </Field>
                <Field label="Lasts">
                  <select className={inputCls} value={duration ?? ''} onChange={(e) => setDuration(e.target.value ? +e.target.value : null)}>
                    {DURATIONS.map(([label, v]) => <option key={label} value={v ?? ''}>{label}</option>)}
                  </select>
                </Field>
              </div>
              {needsTarget && (
                <Field label={audience === 'zone' ? 'Zone' : audience === 'group' ? 'Group' : 'Display'}>
                  <select className={inputCls} value={targetId} onChange={(e) => setTargetId(e.target.value)} required>
                    <option value="">Select…</option>
                    {audience === 'zone' && zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
                    {audience === 'group' && groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                    {audience === 'device' && (devices ?? []).map((d) => <option key={d.device_id} value={d.device_id}>{d.device_id} · {d.name}</option>)}
                  </select>
                </Field>
              )}
              <Button disabled={busy || !message.trim() || (needsTarget && !targetId)} className="mt-1"><Megaphone size={16} weight="fill" aria-hidden="true" />{busy ? 'Going live…' : 'Go live'}</Button>
            </form>
          </Card>
          <Card title="Preview"><Preview message={message} style={style} severity={severity} />
            <p className="mt-3 text-xs text-ink-500">Several broadcasts can run at once. If two of the same style overlap, the more important one is shown; tickers are joined into one line.</p></Card>
        </div>
      ) : <p className="text-sm text-ink-500">Only administrators can start a broadcast.</p>}

      <Card title={`On air now (${active.length})`}>
        <ul className="divide-y divide-ink-100">
          {active.map((b) => (
            <li key={b.id} className="flex flex-wrap items-center gap-3 py-3">
              <span className="relative flex size-2.5"><span className="absolute inset-0 rounded-full bg-red-500" style={{ animation: 'ping-soft 1.6s ease-out infinite' }} /><span className="relative size-2.5 rounded-full bg-red-500" /></span>
              <div className="min-w-0 flex-1"><p className="truncate font-semibold">{b.message}</p>
                <p className="text-xs text-ink-500">{target(b)} · {countdown(b.remaining_seconds)} · by {b.created_by}</p></div>
              <Badge tone="gray">{b.style}</Badge><Badge tone={b.severity === 'critical' ? 'red' : b.severity === 'warning' ? 'amber' : 'blue'}>{b.severity}</Badge>
              {admin && <Button variant="secondary" className="!px-3 !py-1 text-xs" onClick={() => end(b.id)}>End</Button>}
            </li>
          ))}
        </ul>
        {!active.length && <Empty>Nothing is on air. Compose a message above to go live.</Empty>}
      </Card>

      {past.length > 0 && (
        <Card title="Recent">
          <ul className="space-y-1.5 text-sm text-ink-500">{past.map((b) => <li key={b.id} className="flex gap-3"><span className="truncate">{b.message}</span><span className="ml-auto shrink-0 text-xs">{target(b)}</span></li>)}</ul>
        </Card>
      )}
    </div>
  )
}
