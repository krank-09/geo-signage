import { FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'motion/react'
import { ArrowRight, MapPin, Television, WifiSlash } from '@phosphor-icons/react'
import { api, errMsg } from '../services/api'
import { Button, ErrorNote, Field, inputCls } from '../components/ui'

const points = [
  { icon: MapPin, title: 'Geofenced playlists', text: 'Content follows the display across city boundaries.' },
  { icon: WifiSlash, title: 'Keeps playing offline', text: 'Cached media until the network returns.' },
  { icon: Television, title: 'One control room', text: 'Devices, zones, schedules and alerts together.' },
]

export default function Login() {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const { data } = await api.post('/auth/login', { username, password })
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('role', data.role)
      localStorage.setItem('username', data.username)
      navigate('/')
      window.location.reload()
    } catch (err) { setError(errMsg(err)) } finally { setBusy(false) }
  }

  return (
    <div className="grid min-h-screen place-items-center p-4">
      <motion.div initial={{ opacity: 0, y: 24, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="glass grid w-full max-w-4xl overflow-hidden rounded-[36px] p-2 md:grid-cols-[1.1fr_1fr]">
        <div className="relative hidden overflow-hidden rounded-[30px] bg-ink-900 p-9 text-white md:block">
          <div className="pointer-events-none absolute -bottom-24 -left-16 size-80 rounded-full bg-brand-600/50 blur-3xl" />
          <div className="pointer-events-none absolute -right-16 -top-20 size-64 rounded-full bg-brand-400/30 blur-3xl" />
          <span className="relative grid size-12 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 shadow-[var(--shadow-brand)]"><Television size={24} weight="fill" /></span>
          <h1 className="relative mt-8 text-[34px] font-extrabold leading-[1.1] tracking-tight">Every screen shows the right thing, wherever it is.</h1>
          <ul className="relative mt-9 space-y-5">
            {points.map(({ icon: Icon, title, text }, i) => (
              <motion.li key={title} initial={{ opacity: 0, x: -14 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.35 + i * 0.12, duration: 0.5, ease: [0.22, 1, 0.36, 1] }} className="flex gap-3.5">
                <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white/10"><Icon size={19} weight="bold" /></span>
                <span><b className="block text-sm">{title}</b><span className="text-sm text-ink-300">{text}</span></span>
              </motion.li>
            ))}
          </ul>
        </div>
        <form onSubmit={submit} className="p-7 md:p-10">
          <h2 className="text-2xl font-extrabold tracking-tight">Sign in</h2>
          <p className="mb-6 mt-1.5 text-sm text-ink-500">Geo Signage administration</p>
          <ErrorNote msg={error} />
          <Field label="Username"><input name="username" className={inputCls} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" spellCheck={false} autoFocus /></Field>
          <Field label="Password"><input name="password" className={inputCls} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></Field>
          <Button className="mt-3 w-full !py-2.5" disabled={busy}>{busy ? 'Signing in…' : <>Sign in <ArrowRight size={16} weight="bold" /></>}</Button>
          <p className="mt-5 text-center text-xs text-ink-400">Demo account: admin / admin123</p>
        </form>
      </motion.div>
    </div>
  )
}
