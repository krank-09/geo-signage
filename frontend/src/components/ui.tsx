import { ReactNode, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Tray } from '@phosphor-icons/react'

export function Card({ title, actions, children, className = '', pad = true }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={`glass rounded-[28px] ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 px-5 pt-4">
          <h2 className="text-[15px] font-semibold text-ink-900">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className={pad ? 'p-5' : ''}>{children}</div>
    </section>
  )
}

export function PageHeader({ title, subtitle, actions, back }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; back?: boolean }) {
  const navigate = useNavigate()
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex items-center gap-4">
        {back && (
          <button onClick={() => navigate(-1)} aria-label="Go back" className="glass grid size-11 place-items-center rounded-full text-ink-700 transition hover:-translate-x-0.5 hover:text-brand-600">
            <ArrowLeft size={18} weight="bold" aria-hidden="true" />
          </button>
        )}
        <div>
          <h1 className="text-[34px] font-extrabold leading-none tracking-tight text-ink-950">{title}</h1>
          {subtitle && <p className="mt-2 max-w-2xl text-sm text-ink-500">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

const variants: Record<string, string> = {
  primary: 'bg-brand-600 text-white shadow-[var(--shadow-brand)] hover:bg-brand-700',
  secondary: 'bg-white/80 text-ink-800 ring-1 ring-ink-200 hover:bg-white hover:ring-brand-300',
  danger: 'bg-red-600 text-white shadow-[0_10px_24px_-8px_rgb(220_38_38/0.55)] hover:bg-red-700',
  ghost: 'text-ink-500 hover:bg-white/70 hover:text-ink-900',
  dark: 'bg-ink-900 text-white hover:bg-ink-800',
  light: 'bg-white text-ink-900 hover:bg-brand-50',
}
export function Button({ variant = 'primary', className = '', ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof variants }) {
  return (
    <button {...p} className={`inline-flex items-center justify-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold transition duration-200 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 ${variants[variant]} ${className}`} />
  )
}

const tones = {
  green: 'bg-emerald-500/12 text-emerald-700',
  red: 'bg-red-500/12 text-red-700',
  gray: 'bg-ink-900/6 text-ink-500',
  blue: 'bg-brand-600/10 text-brand-700',
  amber: 'bg-amber-500/15 text-amber-800',
}
export function Badge({ tone, children }: { tone: keyof typeof tones; children: ReactNode }) {
  return <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${tones[tone]}`}>{children}</span>
}

export function PulseDot({ online }: { online: boolean }) {
  return (
    <span className="relative inline-flex size-2">
      {online && <span className="absolute inset-0 rounded-full bg-emerald-500" style={{ animation: 'ping-soft 1.8s ease-out infinite' }} />}
      <span className={`relative size-2 rounded-full ${online ? 'bg-emerald-500' : 'bg-red-500'}`} />
    </span>
  )
}

export const StatusBadge = ({ status }: { status: string }) => (
  <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${status === 'online' ? tones.green : tones.red}`}>
    <PulseDot online={status === 'online'} />{status === 'online' ? 'Online' : 'Offline'}
  </span>
)

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div role="dialog" aria-modal="true" aria-label={title} className="modal-backdrop fixed inset-0 z-[2000] flex items-center justify-center overscroll-contain bg-ink-950/45 p-4 backdrop-blur-sm" onMouseDown={onClose}>
      <div className={`modal-panel max-h-[90vh] w-full overflow-auto rounded-[28px] bg-white/95 shadow-2xl ring-1 ring-white ${wide ? 'max-w-3xl' : 'max-w-md'}`} onMouseDown={(e) => e.stopPropagation()}>
        <header className="flex items-center justify-between px-6 pt-5">
          <h3 className="text-lg font-bold tracking-tight">{title}</h3>
          <button onClick={onClose} aria-label="Close" className="grid size-8 place-items-center rounded-full text-xl leading-none text-ink-400 transition hover:bg-ink-100 hover:text-ink-900">×</button>
        </header>
        <div className="p-6 pt-4">{children}</div>
      </div>
    </div>
  )
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="mb-3 block text-sm">
      <span className="mb-1.5 block text-xs font-semibold text-ink-500">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-ink-400">{hint}</span>}
    </label>
  )
}
export const inputCls = 'w-full rounded-2xl border border-ink-200 bg-white/80 px-3.5 py-2 text-sm text-ink-900 outline-none transition placeholder:text-ink-300 focus:border-brand-400 focus:bg-white focus:ring-4 focus:ring-brand-100 disabled:opacity-60'

export function ErrorNote({ msg }: { msg: string }) {
  return msg ? <p role="alert" className="mb-3 rounded-2xl bg-red-500/10 px-4 py-2.5 text-sm font-medium text-red-700">{msg}</p> : null
}

export const Empty = ({ children }: { children: ReactNode }) => (
  <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-ink-400">
    <span className="grid size-12 place-items-center rounded-2xl bg-brand-50 text-brand-500"><Tray size={22} aria-hidden="true" /></span>{children}
  </div>
)

export const Skeleton = ({ className = '' }: { className?: string }) => <div className={`skeleton ${className}`} />

const PALETTE = ['#5b49eb', '#0ea5a4', '#e0662b', '#c2418f', '#3b82f6', '#65a30d']
export function Avatar({ label, tint, size = 40, text }: { label: string; tint?: string; size?: number; text?: string }) {
  const idx = [...label].reduce((a, c) => a + c.charCodeAt(0), 0) % PALETTE.length
  const c = tint || PALETTE[idx]
  return (
    <span className="grid shrink-0 place-items-center rounded-[14px] font-bold text-white" style={{ width: size, height: size, background: `linear-gradient(135deg, ${c}, ${c}bb)`, fontSize: size * 0.34 }}>
      {text ?? label.replace(/[^A-Za-z0-9]/g, '').slice(-3).toUpperCase()}
    </span>
  )
}

export const ago = (iso: string | null) => {
  if (!iso) return 'never'
  // SQLite hands back UTC times without a zone marker; without this a browser reads them as local time and shows "6h ago"
  const s = Math.max(0, Math.round((Date.now() - new Date(/([zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : iso + 'Z').getTime()) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}
