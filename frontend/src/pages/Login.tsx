import { FormEvent, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'motion/react'
import { ArrowRight, GoogleLogo, MapPin, Television, WifiSlash } from '@phosphor-icons/react'
import { api, errMsg } from '../services/api'
import type { AuthConfig } from '../types'
import { Button, ErrorNote, Field, inputCls } from '../components/ui'

const points = [
  { icon: MapPin, title: 'Geofenced playlists', text: 'Content follows the display across city boundaries.' },
  { icon: WifiSlash, title: 'Keeps playing offline', text: 'Cached media until the network returns.' },
  { icon: Television, title: 'One control room', text: 'Devices, zones, schedules and alerts together.' },
]

export default function Login() {
  const navigate = useNavigate()
  const [cfg, setCfg] = useState<AuthConfig | null>(null)
  const [view, setView] = useState<'firebase' | 'local'>('local')
  const [mode, setMode] = useState<'signin' | 'register'>('signin')
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [needsVerify, setNeedsVerify] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.get<AuthConfig>('/auth/config').then((r) => { setCfg(r.data); if (r.data.firebase) setView('firebase') }).catch(() => {}) }, [])
  const fb = cfg?.firebase ?? null

  const finish = (data: { access_token: string; role: string; username: string }) => {
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('role', data.role)
    localStorage.setItem('username', data.username)
    navigate('/')
    window.location.reload()
  }
  const run = async (fn: () => Promise<void>) => { setBusy(true); setError(''); setNotice(''); setNeedsVerify(false); try { await fn() } finally { setBusy(false) } }

  const exchange = async (idToken: string) => {
    try { finish((await api.post('/auth/firebase', { id_token: idToken })).data) }
    catch (e: any) {
      const detail = e?.response?.data?.detail ?? errMsg(e)
      if (e?.response?.status === 403 && /approval/i.test(detail)) setNotice('Your account was created. An administrator has to approve it before you can sign in. Ask them to open Users and give you a role.')
      else { setError(detail); setNeedsVerify(/verify your email/i.test(detail)) }
    }
  }
  const submitLocal = (e: FormEvent) => { e.preventDefault(); run(async () => { try { finish((await api.post('/auth/login', { username, password })).data) } catch (x) { setError(errMsg(x)) } }) }
  const google = () => run(async () => { try { const { googleIdToken } = await import('../services/firebase'); await exchange(await googleIdToken(fb!)) } catch (x) { const { firebaseError } = await import('../services/firebase'); setError(firebaseError(x)) } })
  const submitEmail = (e: FormEvent) => {
    e.preventDefault()
    return run(async () => {
    const svc = await import('../services/firebase')
    try {
      if (mode === 'register') { await svc.registerEmail(fb!, email, password); setNotice('Account created. We sent a verification link to your email. Click it, then come back and sign in.'); setMode('signin') }
      else await exchange(await svc.emailIdToken(fb!, email, password))
    } catch (x) { setError(svc.firebaseError(x)) }
    })
  }
  const resend = () => run(async () => {
    const svc = await import('../services/firebase')
    try { await svc.resendVerification(fb!, email, password); setNotice('Verification email sent again. Check your inbox (and spam).') } catch (x) { setError(svc.firebaseError(x)) }
  })

  return (
    <div className="grid min-h-screen place-items-center p-4">
      <motion.div initial={{ opacity: 0, y: 24, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="glass grid w-full max-w-4xl overflow-hidden rounded-[36px] p-2 md:grid-cols-[1.1fr_1fr]">
        <div className="relative hidden overflow-hidden rounded-[30px] bg-ink-900 p-9 text-white md:block">
          <div className="pointer-events-none absolute -bottom-24 -left-16 size-80 rounded-full bg-brand-600/50 blur-3xl" />
          <div className="pointer-events-none absolute -right-16 -top-20 size-64 rounded-full bg-brand-400/30 blur-3xl" />
          <span className="relative grid size-12 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 shadow-[var(--shadow-brand)]"><Television size={24} weight="fill" aria-hidden="true" /></span>
          <h1 className="relative mt-8 text-[34px] font-extrabold leading-[1.1] tracking-tight">Every screen shows the right thing, wherever it is.</h1>
          <ul className="relative mt-9 space-y-5">
            {points.map(({ icon: Icon, title, text }, i) => (
              <motion.li key={title} initial={{ opacity: 0, x: -14 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.35 + i * 0.12, duration: 0.5, ease: [0.22, 1, 0.36, 1] }} className="flex gap-3.5">
                <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/10"><Icon size={19} weight="bold" aria-hidden="true" /></span>
                <span><b className="block text-sm">{title}</b><span className="text-sm text-ink-300">{text}</span></span>
              </motion.li>
            ))}
          </ul>
        </div>

        <div className="p-7 md:p-10">
          <h2 className="text-2xl font-extrabold tracking-tight">{view === 'firebase' ? (mode === 'register' ? 'Create account' : 'Sign in') : 'Sign in'}</h2>
          <p className="mb-5 mt-1.5 text-sm text-ink-500">Geo Signage administration</p>
          <ErrorNote msg={error} />
          {notice && <p role="status" className="mb-3 rounded-2xl bg-emerald-500/12 px-4 py-2.5 text-sm font-medium text-emerald-700">{notice}</p>}
          {needsVerify && <button type="button" onClick={resend} disabled={busy} className="mb-3 text-sm font-semibold text-brand-600 hover:underline">Resend the verification email</button>}

          {view === 'firebase' && fb ? (
            <>
              <Button type="button" variant="secondary" className="w-full !py-2.5" onClick={google} disabled={busy}><GoogleLogo size={18} weight="bold" aria-hidden="true" />Continue with Google</Button>
              <div className="my-4 flex items-center gap-3 text-xs text-ink-400"><span className="h-px flex-1 bg-ink-200" />or with email<span className="h-px flex-1 bg-ink-200" /></div>
              <form onSubmit={submitEmail}>
                <Field label="Email"><input name="email" type="email" className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" spellCheck={false} required /></Field>
                <Field label="Password"><input name="password" type="password" className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} required minLength={6} /></Field>
                <Button className="mt-2 w-full !py-2.5" disabled={busy}>{busy ? 'Please wait…' : mode === 'register' ? 'Create account' : <>Sign in <ArrowRight size={16} weight="bold" aria-hidden="true" /></>}</Button>
              </form>
              <div className="mt-4 flex justify-between text-xs">
                <button type="button" className="font-semibold text-brand-600 hover:underline" onClick={() => { setMode(mode === 'signin' ? 'register' : 'signin'); setError(''); setNotice('') }}>{mode === 'signin' ? 'New here? Create an account' : 'Have an account? Sign in'}</button>
                {cfg?.local_login && <button type="button" className="text-ink-500 hover:underline" onClick={() => { setView('local'); setError(''); setNotice('') }}>Use a local admin login</button>}
              </div>
              <p className="mt-4 text-center text-xs text-ink-400">New accounts need an administrator's approval before they can use the dashboard.</p>
            </>
          ) : (
            <form onSubmit={submitLocal}>
              <Field label="Username"><input name="username" className={inputCls} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" spellCheck={false} autoFocus /></Field>
              <Field label="Password"><input name="password" className={inputCls} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></Field>
              <Button className="mt-3 w-full !py-2.5" disabled={busy}>{busy ? 'Signing in…' : <>Sign in <ArrowRight size={16} weight="bold" aria-hidden="true" /></>}</Button>
              {fb && <button type="button" className="mt-4 block w-full text-center text-xs font-semibold text-brand-600 hover:underline" onClick={() => { setView('firebase'); setError(''); setNotice('') }}>Sign in with Google or email instead</button>}
              <p className="mt-5 text-center text-xs text-ink-400">Demo account: admin / admin123</p>
            </form>
          )}
        </div>
      </motion.div>
    </div>
  )
}
