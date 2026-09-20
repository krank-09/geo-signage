import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { api, errMsg, isAdmin, isPlatform } from '../services/api'
import type { FleetInventory, Release } from '../types'
import { Badge, Button, Card, Empty, ErrorNote, Field, inputCls, PageHeader, StatusBadge } from '../components/ui'

const COMPAT = {
  ok: ['green', 'Up to date'], outdated: ['amber', 'Update recommended'], unsupported: ['red', 'Unsupported'], unknown: ['gray', 'Unknown'],
} as const

function Tally({ title, data, onPick, active }: { title: string; data: Record<string, number>; onPick: (k: string) => void; active: string }) {
  return (
    <Card title={title}>
      <ul className="space-y-1.5 text-sm">
        {Object.entries(data).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
          <li key={k}><button onClick={() => onPick(active === k ? '' : k)} className={`flex w-full items-center justify-between rounded-xl px-2.5 py-1 text-left transition hover:bg-white/70 ${active === k ? 'bg-brand-600/10 font-bold text-brand-700' : ''}`}><span>{k}</span><b>{n}</b></button></li>
        ))}
        {!Object.keys(data).length && <li className="text-ink-400">—</li>}
      </ul>
    </Card>
  )
}

export default function Fleet() {
  const [inv, setInv] = useState<FleetInventory | null>(null)
  const [releases, setReleases] = useState<Release[]>([])
  const [filter, setFilter] = useState({ os: '', version: '', arch: '', compat: '' })
  const [policy, setPolicy] = useState({ recommended_version: '', supported_version: '' })
  const [rel, setRel] = useState({ version: '', code_hash: '', note: '' })
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const admin = isAdmin()

  const load = useCallback(async () => {
    const r = await api.get<FleetInventory>('/fleet/inventory')
    setInv(r.data); setPolicy({ recommended_version: r.data.policy.recommended_version ?? '', supported_version: r.data.policy.supported_version ?? '' })
    api.get<Release[]>('/fleet/releases').then((x) => setReleases(x.data)).catch(() => {})
  }, [])
  useEffect(() => { load().catch((e) => setErr(errMsg(e))) }, [load])

  const rows = useMemo(() => (inv?.devices ?? []).filter((d) =>
    (!filter.os || (d.os_name || 'unknown') === filter.os) && (!filter.version || (d.software_version || 'unknown') === filter.version)
    && (!filter.arch || (d.os_arch || 'unknown') === filter.arch) && (!filter.compat || d.compatibility === filter.compat)), [inv, filter])

  const savePolicy = async (e: FormEvent) => {
    e.preventDefault(); setMsg(''); setErr('')
    try { await api.put('/fleet/policy', { recommended_version: policy.recommended_version || null, supported_version: policy.supported_version || null }); setMsg('Policy saved'); load() } catch (x) { setErr(errMsg(x)) }
  }
  const addRelease = async (e: FormEvent) => {
    e.preventDefault(); setErr('')
    try { await api.post('/fleet/releases', rel); setRel({ version: '', code_hash: '', note: '' }); load() } catch (x) { setErr(errMsg(x)) }
  }
  const s = inv?.summary
  const set = (k: keyof typeof filter) => (v: string) => setFilter((f) => ({ ...f, [k]: v }))

  return (
    <div className="stagger space-y-6">
      <PageHeader title="Fleet" subtitle="Which operating system and agent version every display runs, and whether it meets your minimum-version policy." />
      <ErrorNote msg={err} />
      {s && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Tally title="Operating system" data={s.by_os} onPick={set('os')} active={filter.os} />
          <Tally title="Agent version" data={s.by_version} onPick={set('version')} active={filter.version} />
          <Tally title="Architecture" data={s.by_arch} onPick={set('arch')} active={filter.arch} />
          <Tally title="Compatibility" data={Object.fromEntries(Object.entries(s.by_compatibility).map(([k, v]) => [k, v]))} onPick={set('compat')} active={filter.compat} />
        </div>
      )}
      <Card title={`Displays (${rows.length}${rows.length !== inv?.devices.length ? ` of ${inv?.devices.length}` : ''})`}
        actions={Object.values(filter).some(Boolean) ? <Button variant="ghost" className="!px-3 !py-1 text-xs" onClick={() => setFilter({ os: '', version: '', arch: '', compat: '' })}>Clear filters</Button> : undefined}>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-ink-400"><tr><th className="py-2">Display</th><th>Status</th><th>OS</th><th>Arch</th><th>Runtime</th><th>Agent</th><th>Compatibility</th><th>Protection</th></tr></thead>
            <tbody className="divide-y divide-ink-100/70">
              {rows.map((d) => (
                <tr key={d.device_id}>
                  <td className="py-2.5"><b>{d.device_id}</b><div className="text-xs text-ink-500">{d.name}</div></td>
                  <td><StatusBadge status={d.status} /></td>
                  <td>{d.os_name ? `${d.os_name} ${d.os_version ?? ''}` : <span className="text-ink-400">not reported</span>}</td>
                  <td>{d.os_arch || '—'}</td><td>{d.runtime_version ? `Python ${d.runtime_version}` : '—'}</td>
                  <td>{d.software_version ? `v${d.software_version}` : '—'}</td>
                  <td><Badge tone={COMPAT[d.compatibility][0]}>{COMPAT[d.compatibility][1]}</Badge></td>
                  <td className="space-x-1"><Badge tone={d.protection === 'protected' ? 'green' : 'amber'}>{d.protection === 'protected' ? 'Key bound' : 'No key (old agent)'}</Badge>{d.tamper_state && <Badge tone="red">Flagged</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <Empty>No displays match</Empty>}
        </div>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Minimum-version policy">
          <p className="mb-3 text-sm text-ink-500">Displays below <b>supported</b> show as Unsupported; below <b>recommended</b> as Update recommended. Older agents keep working either way.</p>
          {msg && <p role="status" className="mb-3 rounded-2xl bg-emerald-500/12 px-4 py-2 text-sm text-emerald-700">{msg}</p>}
          <form onSubmit={savePolicy} className="grid items-end gap-x-3 sm:grid-cols-3">
            <Field label="Recommended"><input disabled={!admin} className={inputCls} placeholder="1.2.0" value={policy.recommended_version} onChange={(e) => setPolicy({ ...policy, recommended_version: e.target.value })} /></Field>
            <Field label="Supported (minimum)"><input disabled={!admin} className={inputCls} placeholder="1.1.0" value={policy.supported_version} onChange={(e) => setPolicy({ ...policy, supported_version: e.target.value })} /></Field>
            {admin && <div className="mb-3"><Button>Save</Button></div>}
          </form>
        </Card>
        <Card title="Trusted agent builds">
          <p className="mb-3 text-sm text-ink-500">Once any build is listed, a display whose code hash is not listed is flagged as tampered. Empty list: each display is compared with its own first report.</p>
          <ul className="mb-3 divide-y divide-ink-100/70 text-sm">
            {releases.map((r) => (
              <li key={r.id} className="flex items-center gap-2 py-2"><Badge tone="blue">v{r.version}</Badge><code className="min-w-0 flex-1 truncate text-xs" title={r.code_hash}>{r.code_hash}</code>
                {isPlatform() && admin && <Button variant="ghost" className="!px-2 !py-0.5 text-xs !text-red-600" onClick={async () => { await api.delete(`/fleet/releases/${r.id}`); load() }}>Remove</Button>}</li>
            ))}
            {!releases.length && <li className="py-2 text-ink-400">None listed</li>}
          </ul>
          {isPlatform() && admin && (
            <form onSubmit={addRelease} className="grid gap-x-3 sm:grid-cols-[6rem_1fr_auto] sm:items-end">
              <Field label="Version"><input className={inputCls} value={rel.version} onChange={(e) => setRel({ ...rel, version: e.target.value })} required placeholder="1.2.0" /></Field>
              <Field label="Code hash" hint="printed by scripts/make-device-kit.sh"><input className={inputCls} value={rel.code_hash} onChange={(e) => setRel({ ...rel, code_hash: e.target.value.trim() })} required minLength={16} /></Field>
              <div className="mb-3"><Button>Trust</Button></div>
            </form>
          )}
        </Card>
      </div>
    </div>
  )
}
