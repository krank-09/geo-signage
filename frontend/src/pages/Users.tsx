import { FormEvent, useCallback, useEffect, useState } from 'react'
import { api, errMsg, isAdmin } from '../services/api'
import { Avatar, Badge, Button, Card, ErrorNote, Field, inputCls, PageHeader } from '../components/ui'

interface U { id: number; username: string; role: string; created_at: string }

function ChangePassword() {
  const [f, setF] = useState({ current_password: '', new_password: '', confirm: '' })
  const [err, setErr] = useState('')
  const [ok, setOk] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr(''); setOk(false)
    if (f.new_password !== f.confirm) { setErr('The new passwords do not match'); return }
    try {
      await api.post('/users/me/password', { current_password: f.current_password, new_password: f.new_password })
      setF({ current_password: '', new_password: '', confirm: '' }); setOk(true)
    } catch (e) { setErr(errMsg(e)) }
  }
  return (
    <Card title="Change my password">
      <ErrorNote msg={err} />
      {ok && <p role="status" className="mb-3 rounded-2xl bg-emerald-500/12 px-4 py-2.5 text-sm font-medium text-emerald-700">Password updated. Use it the next time you sign in.</p>}
      <form onSubmit={submit} className="grid items-end gap-x-3 md:grid-cols-4">
        <Field label="Current password"><input name="current-password" type="password" autoComplete="current-password" className={inputCls} value={f.current_password} onChange={(e) => setF({ ...f, current_password: e.target.value })} required /></Field>
        <Field label="New password" hint="min. 8 characters"><input name="new-password" type="password" autoComplete="new-password" className={inputCls} value={f.new_password} onChange={(e) => setF({ ...f, new_password: e.target.value })} required minLength={8} /></Field>
        <Field label="Repeat new password"><input name="confirm-password" type="password" autoComplete="new-password" className={inputCls} value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} required /></Field>
        <div className="mb-3"><Button>Update password</Button></div>
      </form>
    </Card>
  )
}

export default function Users() {
  const [users, setUsers] = useState<U[]>([])
  const [f, setF] = useState({ username: '', password: '', role: 'admin' })
  const [err, setErr] = useState('')
  const admin = isAdmin()
  const load = useCallback(() => { if (admin) api.get('/users').then((r) => setUsers(r.data)) }, [admin])
  useEffect(() => { load() }, [load])

  const add = async (e: FormEvent) => {
    e.preventDefault(); setErr('')
    try { await api.post('/users', f); setF({ username: '', password: '', role: 'admin' }); load() } catch (e) { setErr(errMsg(e)) }
  }
  if (!admin) return (
    <div className="stagger space-y-6">
      <PageHeader title="Account" subtitle="Only administrators can manage other users." />
      <ChangePassword />
    </div>
  )
  return (
    <div className="stagger space-y-6">
      <PageHeader title="Users" subtitle="Administrators can change everything; viewers are read-only." />
      <ChangePassword />
      <Card title="Add user">
        <ErrorNote msg={err} />
        <form onSubmit={add} className="grid items-end gap-x-3 md:grid-cols-4">
          <Field label="Username"><input className={inputCls} value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} required /></Field>
          <Field label="Password" hint="min. 8 characters"><input type="password" className={inputCls} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} required /></Field>
          <Field label="Role"><select className={inputCls} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option value="admin">Administrator</option><option value="viewer">Viewer (read-only)</option></select></Field>
          <div className="mb-3"><Button>Add</Button></div>
        </form>
      </Card>
      <Card>
        <ul className="divide-y divide-ink-100/70 text-sm">{users.map((u) => (
          <li key={u.id} className="flex items-center gap-3 py-2.5"><Avatar label={u.username} text={u.username.slice(0, 2).toUpperCase()} size={36} /><b>{u.username}</b><Badge tone={u.role === 'admin' ? 'blue' : 'gray'}>{u.role}</Badge>
            <Button variant="ghost" className="ml-auto !text-red-600" onClick={async () => { if (confirm(`Delete ${u.username}?`)) { try { await api.delete(`/users/${u.id}`); load() } catch (e) { setErr(errMsg(e)) } } }}>Delete</Button></li>
        ))}</ul>
      </Card>
    </div>
  )
}
