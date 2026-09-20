import { useCallback, useEffect, useState } from 'react'
import { api, errMsg, isAdmin } from '../services/api'
import type { SecurityStatus, TamperEvent } from '../types'
import { useLive } from '../hooks/useLive'
import { ago, Badge, Button, Card, Empty, ErrorNote, PageHeader } from '../components/ui'

const TONE = { critical: 'red', warning: 'amber', info: 'gray' } as const
const LABEL: Record<string, string> = {
  cache_tampered: 'Cached media modified', media_hash_mismatch: 'Downloaded media did not match', manifest_signature_invalid: 'Playlist not signed by the server',
  config_tampered: 'Saved settings edited', code_modified: 'Agent code changed', clock_rollback: 'Clock set back', unexpected_restart: 'Unexpected restart',
  restart_loop: 'Restart loop', system_clock_wrong: 'Clock skew', bad_signature: 'Bad request signature', replayed_request: 'Replayed request',
  unsigned_downgrade: 'Unsigned request from a protected display', clone_attempt: 'Clone attempt (same credentials, other machine)',
  hw_fingerprint_changed: 'Hardware fingerprint changed', flag_cleared: 'Flag cleared by an administrator',
}

export default function Security() {
  const [status, setStatus] = useState<SecurityStatus | null>(null)
  const [events, setEvents] = useState<TamperEvent[]>([])
  const [audit, setAudit] = useState<string>('')
  const [err, setErr] = useState('')
  const admin = isAdmin()

  const load = useCallback(() => {
    api.get<SecurityStatus>('/security/status').then((r) => setStatus(r.data)).catch((e) => setErr(errMsg(e)))
    api.get<TamperEvent[]>('/security/events?limit=100').then((r) => setEvents(r.data)).catch(() => {})
  }, [])
  useEffect(() => { load() }, [load])
  useLive((e) => { if (e.event === 'tamper' || e.event === 'alerts_changed') load() })

  const verify = async () => {
    try { const r = await api.post('/security/audit/verify'); setAudit(r.data.ok ? `Record intact: ${r.data.events} events, chain verified.` : `TAMPERED: the record was altered at event #${r.data.broken_at}.`) } catch (e) { setErr(errMsg(e)) }
  }
  const clear = async (id: string) => {
    if (!confirm(`Clear the tamper flag on ${id}? Do this after you have checked the display.`)) return
    try { await api.post(`/devices/${id}/tamper/clear`); load() } catch (e) { setErr(errMsg(e)) }
  }

  return (
    <div className="stagger space-y-6">
      <PageHeader title="Security" subtitle="Tamper detections from displays and the server. A flagged display keeps working; nothing is switched off automatically." />
      <ErrorNote msg={err} />
      {status && (
        <div className="grid gap-4 md:grid-cols-4">
          <Card><p className="text-xs text-ink-500">Flagged displays</p><p className={`text-3xl font-extrabold ${status.flagged.length ? 'text-red-600' : ''}`}>{status.flagged.length}</p></Card>
          <Card><p className="text-xs text-ink-500">Key-bound displays</p><p className="text-3xl font-extrabold">{status.protected}</p><p className="text-xs text-ink-400">{status.unprotected} without a key (older agent)</p></Card>
          <Card><p className="text-xs text-ink-500">Device authentication</p><p className="text-lg font-extrabold capitalize">{status.mode}</p><p className="text-xs text-ink-400">{status.mode === 'required' ? 'unsigned displays are refused' : 'older agents still accepted'}</p></Card>
          <Card><p className="text-xs text-ink-500">Playlist signing key</p><code className="text-sm font-bold">{status.server_key_fingerprint}</code><p className="text-xs text-ink-400">displays pin this on first registration</p></Card>
        </div>
      )}
      {status && status.flagged.length > 0 && (
        <Card title="Flagged displays" className="ring-2 ring-red-300/60">
          <ul className="divide-y divide-ink-100/70 text-sm">
            {status.flagged.map((id) => (
              <li key={id} className="flex items-center gap-3 py-2.5"><b className="flex-1">{id}</b>
                {admin && <Button variant="secondary" className="!px-3 !py-1 text-xs" onClick={() => clear(id)}>Clear flag</Button>}</li>
            ))}
          </ul>
        </Card>
      )}
      <Card title="Tamper events" actions={admin ? <Button variant="secondary" className="!px-3 !py-1 text-xs" onClick={verify}>Verify record</Button> : undefined}>
        {audit && <p role="status" className={`mb-3 rounded-2xl px-4 py-2 text-sm font-medium ${audit.startsWith('TAMPERED') ? 'bg-red-500/10 text-red-700' : 'bg-emerald-500/12 text-emerald-700'}`}>{audit}</p>}
        <ul className="divide-y divide-ink-100/70 text-sm">
          {events.map((e) => (
            <li key={e.id} className="flex flex-wrap items-start gap-3 py-2.5">
              <span className="w-16 shrink-0 pt-0.5 text-xs text-ink-400">{ago(e.created_at)}</span>
              <Badge tone={TONE[e.severity]}>{e.severity}</Badge>
              <div className="min-w-0 flex-1"><b>{e.device_id}</b> · {LABEL[e.kind] ?? e.kind}<div className="text-xs text-ink-500">{e.detail}</div></div>
              <Badge tone="gray">{e.source}</Badge>
            </li>
          ))}
        </ul>
        {!events.length && <Empty>No tamper events. That is the good outcome.</Empty>}
      </Card>
    </div>
  )
}
