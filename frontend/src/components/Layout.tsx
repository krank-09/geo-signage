import { ReactNode, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate, useOutlet } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import { SignOut, Television } from '@phosphor-icons/react'
import { api, getRole } from '../services/api'
import type { Alert } from '../types'
import { useLive } from '../hooks/useLive'
import { AlertBell } from './AlertBell'
import { useToast } from './Toasts'
import { Avatar, PulseDot, Skeleton } from './ui'

const nav: [string, string][] = [
  ['/', 'Overview'], ['/devices', 'Devices'], ['/content', 'Content'], ['/zones', 'Zones & map'],
  ['/schedules', 'Schedules'], ['/broadcast', 'Broadcast'], ['/emergency', 'Emergency'], ['/monitoring', 'Monitoring'], ['/users', 'Users'],
]

/** Keeps the outgoing page's element alive while it animates out (otherwise it would flip to the new route instantly). */
function Frozen({ children }: { children: ReactNode }) {
  const [frozen] = useState(children)
  return <>{frozen}</>
}

function PageFallback() {
  return (
    <div className="space-y-6" aria-busy="true">
      <Skeleton className="h-12 w-72" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)}</div>
      <Skeleton className="h-72" />
    </div>
  )
}

function AnimatedOutlet() {
  const outlet = useOutlet()
  const { pathname } = useLocation()
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={pathname}
        initial={{ opacity: 0, y: 22, scale: 0.992 }}
        animate={{ opacity: 1, y: 0, scale: 1, transition: { duration: 0.42, ease: [0.22, 1, 0.36, 1] } }}
        exit={{ opacity: 0, y: -10, scale: 0.996, transition: { duration: 0.16, ease: 'easeIn' } }}
      >
        <Suspense fallback={<PageFallback />}>
          <Frozen>{outlet}</Frozen>
        </Suspense>
      </motion.div>
    </AnimatePresence>
  )
}

export default function Layout() {
  const navigate = useNavigate()
  const [alerts, setAlerts] = useState<Alert[]>([])
  const navRef = useRef<HTMLElement>(null)
  const toast = useToast()

  const loadAlerts = useCallback(() => api.get('/alerts').then((r) => setAlerts(r.data)).catch(() => {}), [])
  useEffect(() => { loadAlerts(); const t = setInterval(loadAlerts, 30000); return () => clearInterval(t) }, [loadAlerts])
  const live = useLive((e) => {
    if (e.event === 'alert') { toast('alert', e.alert.message); loadAlerts() }
    else if (e.event === 'alert_resolved') { toast('ok', `Recovered: ${e.alert.device_id} is healthy again (${e.alert.health}%)`); loadAlerts() }
    else if (e.event === 'alerts_changed') loadAlerts()
  })

  // keep the active pill in view on narrow screens
  const { pathname } = useLocation()
  useEffect(() => { navRef.current?.querySelector('[aria-current=page]')?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' }) }, [pathname])

  const logout = () => { localStorage.clear(); navigate('/login') }
  const username = localStorage.getItem('username') || 'admin'

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[3000] focus:rounded-full focus:bg-white focus:px-4 focus:py-2">Skip to content</a>
      <header className="sticky top-0 z-[1100] px-4 pt-4 md:px-8">
        <div className="mx-auto flex max-w-[1440px] items-center gap-3">
          <Link to="/" className="glass flex shrink-0 items-center gap-2.5 rounded-full py-1.5 pl-1.5 pr-4" aria-label="Geo Signage home">
            <span className="grid size-10 place-items-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-[var(--shadow-brand)]"><Television size={20} weight="fill" aria-hidden="true" /></span>
            <span className="hidden text-left leading-tight md:block"><span className="block text-sm font-extrabold tracking-tight">Geo Signage</span><span className="block text-[11px] text-ink-500">Location-aware displays</span></span>
          </Link>

          <nav ref={navRef} aria-label="Primary" className="no-scrollbar flex min-w-0 flex-1 items-center gap-1 overflow-x-auto rounded-full bg-ink-900 p-1.5 shadow-[0_18px_40px_-18px_rgb(20_22_43/0.8)]" style={{ scrollbarWidth: 'none' }}>
            {nav.map(([to, label]) => (
              <NavLink key={to} to={to} end={to === '/'} className="relative shrink-0 rounded-full px-4 py-2 text-[13px] font-semibold transition-colors">
                {({ isActive }) => (
                  <>
                    {isActive && <motion.span layoutId="nav-pill" className="absolute inset-0 rounded-full bg-brand-600 shadow-[var(--shadow-brand)]" transition={{ type: 'spring', stiffness: 420, damping: 34 }} />}
                    <span className={`relative z-10 flex items-center gap-1.5 ${isActive ? 'text-white' : to === '/emergency' ? 'text-red-300 hover:text-red-200' : 'text-ink-300 hover:text-white'}`}>
                      {label}
                    </span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="glass hidden shrink-0 items-center gap-2 rounded-full px-3.5 py-2.5 text-xs font-semibold lg:flex" title={live ? 'Receiving live updates' : 'Reconnecting…'}>
            <PulseDot online={live} />{live ? 'Live' : 'Reconnecting'}
          </div>
          <AlertBell alerts={alerts} onChange={loadAlerts} />
          <div className="glass group relative flex shrink-0 items-center gap-2 rounded-full py-1 pl-1 pr-1.5">
            <Avatar label={username} text={username.slice(0, 2).toUpperCase()} size={36} tint="#5b49eb" />
            <span className="hidden pr-1 text-left text-xs leading-tight md:block"><b className="block text-[13px]">{username}</b><span className="text-ink-500">{getRole()}</span></span>
            <button onClick={logout} aria-label="Log out" title="Log out" className="grid size-8 place-items-center rounded-full text-ink-500 transition hover:bg-red-50 hover:text-red-600"><SignOut size={17} weight="bold" aria-hidden="true" /></button>
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-[1440px] px-4 pb-16 pt-8 md:px-8"><AnimatedOutlet /></main>
    </div>
  )
}
