import { FormEvent, useCallback, useEffect, useState } from 'react'
import { api, errMsg, isAdmin, isPlatform } from '../services/api'
import type { AppUser, ClientInfo } from '../types'
import { Avatar, Badge, Button, Card, ErrorNote, Field, inputCls, PageHeader } from '../components/ui'

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
  const [users, setUsers] = useState<AppUser[]>([])
  const [f, setF] = useState({ username: '', password: '', role: 'admin', client_id: '' })
  const [clients, setClients] = useState<ClientInfo[]>([])
  const platform = isPlatform()
  useEffect(() => { if (platform) api.get<ClientInfo[]>('/clients').then((r) => setClients(r.data)) }, [platform])
  const clientName = (id?: number | null) => (id == null ? 'Platform' : clients.find((c) => c.id === id)?.name ?? `Client ${id}`)
  const [err, setErr] = useState('')
  const admin = isAdmin()
  const me = localStorage.getItem('username')
  const load = useCallback(() => { if (admin) api.get('/users').then((r) => setUsers(r.data)) }, [admin])
  const pending = users.filter((u) => u.role === 'pending')
  const people = users.filter((u) => u.role !== 'pending')
  const [approveFor, setApproveFor] = useState('')
  const setRole = async (u: AppUser, role: AppUser['role'], client_id?: number | null) => { try { await api.put(`/users/${u.id}/role`, client_id === undefined ? { role } : { role, client_id }); load() } catch (e) { setErr(errMsg(e)) } }
  const remove = async (u: AppUser) => { if (confirm(`Remove ${u.username}?`)) { try { await api.delete(`/users/${u.id}`); load() } catch (e) { setErr(errMsg(e)) } } }
  useEffect(() => { load() }, [load])

  const add = async (e: FormEvent) => {
    e.preventDefault(); setErr('')
    try { await api.post('/users', { ...f, client_id: f.client_id ? +f.client_id : null }); setF({ username: '', password: '', role: 'admin', client_id: '' }); load() } catch (e) { setErr(errMsg(e)) }
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
        <form onSubmit={add} className={`grid items-end gap-x-3 ${platform ? 'md:grid-cols-5' : 'md:grid-cols-4'}`}>
          <Field label="Username"><input className={inputCls} value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} required /></Field>
          <Field label="Password" hint="min. 8 characters"><input type="password" className={inputCls} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} required /></Field>
          <Field label="Role"><select className={inputCls} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option value="admin">Administrator</option><option value="viewer">Viewer (read-only)</option></select></Field>
          {platform && <Field label="Belongs to" hint="Pick a client, or Platform for staff who manage every client"><select className={inputCls} value={f.client_id} onChange={(e) => setF({ ...f, client_id: e.target.value })}><option value="">Platform (all clients)</option>{clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>}
          <div className="mb-3"><Button>Add</Button></div>
        </form>
      </Card>
      {pending.length > 0 && (
        <Card title={`Waiting for approval (${pending.length})`} className="ring-2 ring-amber-300/60">
          <p className="mb-3 text-sm text-ink-500">These people signed in with Firebase but have no access yet. Give each a role, or remove them.</p>
          {platform && <Field label="Approve into" hint="The client the approved person will belong to. Platform means access to every client."><select className={inputCls + ' max-w-xs'} value={approveFor} onChange={(e) => setApproveFor(e.target.value)}><option value="">Platform (all clients)</option>{clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>}
          <ul className="divide-y divide-ink-100/70 text-sm">
            {pending.map((u) => (
              <li key={u.id} className="flex flex-wrap items-center gap-3 py-2.5">
                <Avatar label={u.username} text={u.username.slice(0, 2).toUpperCase()} size={36} />
                <div className="min-w-0 flex-1"><b>{u.username}</b><div className="truncate text-xs text-ink-500">{u.email}</div></div>
                <Button className="!px-3 !py-1 text-xs" onClick={() => setRole(u, 'viewer', platform ? (approveFor ? +approveFor : null) : undefined)}>Approve as viewer</Button>
                <Button variant="secondary" className="!px-3 !py-1 text-xs" onClick={() => setRole(u, 'admin', platform ? (approveFor ? +approveFor : null) : undefined)}>Approve as admin</Button>
                <Button variant="ghost" className="!px-3 !py-1 text-xs !text-red-600" onClick={() => remove(u)}>Remove</Button>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card title="People">
        <ul className="divide-y divide-ink-100/70 text-sm">{people.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center gap-3 py-2.5">
            <Avatar label={u.username} text={u.username.slice(0, 2).toUpperCase()} size={36} />
            <div className="min-w-0 flex-1"><b>{u.username}</b>{u.email && <div className="truncate text-xs text-ink-500">{u.email}</div>}</div>
            {platform && <Badge tone={u.client_id == null ? 'blue' : 'gray'}>{clientName(u.client_id)}</Badge>}
            <Badge tone={u.source === 'firebase' ? 'amber' : 'gray'}>{u.source === 'firebase' ? 'Firebase' : 'Local'}</Badge>
            {u.username === me ? <Badge tone="blue">{u.role} (you)</Badge> : (
              <select aria-label={`Role for ${u.username}`} className={inputCls + ' !w-auto !py-1'} value={u.role} onChange={(e) => setRole(u, e.target.value as AppUser['role'])}>
                <option value="admin">Administrator</option><option value="viewer">Viewer</option><option value="pending">No access</option>
              </select>
            )}
            {u.username !== me && <Button variant="ghost" className="!px-3 !py-1 text-xs !text-red-600" onClick={() => remove(u)}>Delete</Button>}
          </li>
        ))}</ul>
      </Card>
    </div>
  )
}
