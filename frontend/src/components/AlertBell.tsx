import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell, CheckCircle } from '@phosphor-icons/react'
import { api, isAdmin } from '../services/api'
import type { Alert } from '../types'
import { ago } from './ui'

/** Bell with a count of open health alerts; the popover lists them and lets an admin acknowledge each. */
export function AlertBell({ alerts, onChange }: { alerts: Alert[]; onChange: () => void }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const unacked = alerts.filter((a) => !a.acknowledged_at).length

  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', away); document.removeEventListener('keydown', esc) }
  }, [open])

  const ack = async (id: number) => { await api.post(`/alerts/${id}/ack`); onChange() }

  return (
    <div ref={box} className="relative shrink-0">
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="dialog" aria-expanded={open}
        aria-label={alerts.length ? `${alerts.length} open health alert${alerts.length > 1 ? 's' : ''}` : 'No health alerts'}
        className="glass relative grid size-11 place-items-center rounded-full text-ink-700 transition hover:text-brand-600">
        <Bell size={19} weight={alerts.length ? 'fill' : 'bold'} aria-hidden="true" className={alerts.length ? 'text-red-600' : ''} />
        {alerts.length > 0 && (
          <span className={`absolute -right-0.5 -top-0.5 grid min-w-5 place-items-center rounded-full px-1 text-[11px] font-bold text-white ring-2 ring-white ${unacked ? 'bg-red-600' : 'bg-amber-500'}`}>{alerts.length}</span>
        )}
      </button>
      {open && (
        <div role="dialog" aria-label="Health alerts" className="modal-panel absolute right-0 top-14 z-[1200] w-[380px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-3xl bg-white/95 shadow-2xl ring-1 ring-ink-100 backdrop-blur">
          <div className="flex items-center justify-between px-5 pb-2 pt-4"><h2 className="text-sm font-bold">Health alerts</h2><span className="text-xs text-ink-500">{alerts.length} open</span></div>
          <ul className="max-h-[380px] divide-y divide-ink-100 overflow-auto">
            {alerts.map((a) => (
              <li key={a.id} className="px-5 py-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <div><b>{a.device_name || a.device_id}</b> <span className="text-xs text-ink-400">{a.device_id}</span>
                    <p className="mt-0.5 text-ink-600">{a.kind === 'offline' ? 'Went offline' : a.kind === 'tamper' ? 'Possible tampering' : a.kind === 'off_route' ? 'Left its route' : `Health ${a.health}%`}</p></div>
                  <span className="shrink-0 text-xs text-ink-400">{ago(a.created_at)}</span>
                </div>
                <p className="mt-1 text-xs text-ink-500">{a.message}</p>
                {a.acknowledged_at
                  ? <p className="mt-1.5 flex items-center gap-1 text-xs text-emerald-600"><CheckCircle size={14} weight="fill" aria-hidden="true" />Acknowledged by {a.acknowledged_by}</p>
                  : isAdmin() && <button onClick={() => ack(a.id)} className="mt-2 rounded-full bg-ink-900 px-3 py-1 text-xs font-semibold text-white hover:bg-ink-800">Acknowledge</button>}
              </li>
            ))}
            {!alerts.length && <li className="px-5 py-8 text-center text-sm text-ink-400">All devices are healthy.</li>}
          </ul>
          <Link to="/monitoring" onClick={() => setOpen(false)} className="block border-t border-ink-100 px-5 py-3 text-center text-xs font-bold text-brand-600 hover:bg-brand-50">Open monitoring &amp; alert settings</Link>
        </div>
      )}
    </div>
  )
}
