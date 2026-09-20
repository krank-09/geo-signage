import { FormEvent, useState } from 'react'
import { api, errMsg } from '../../services/api'
import type { Group } from '../../types'
import { Button, ErrorNote, Field, inputCls, Modal } from '../ui'
import { TokenBox } from './TokenBox'

export function AddDeviceModal({ groups, onClose, onDone }: { groups: Group[]; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ device_id: '', name: '', group_id: '', latitude: '', longitude: '' })
  const [err, setErr] = useState('')
  const [created, setCreated] = useState<{ device_id: string; registration_token: string } | null>(null)
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr('')
    try {
      const { data } = await api.post('/devices', {
        device_id: f.device_id, name: f.name, group_id: f.group_id ? +f.group_id : null,
        latitude: f.latitude ? +f.latitude : null, longitude: f.longitude ? +f.longitude : null,
      })
      setCreated(data); onDone()
    } catch (e) { setErr(errMsg(e)) }
  }
  return (
    <Modal title={created ? 'Device created' : 'Add device'} onClose={onClose}>
      {created ? <TokenBox deviceId={created.device_id} token={created.registration_token} /> : (
        <form onSubmit={submit}>
          <ErrorNote msg={err} />
          <Field label="Device ID" hint="Letters, digits, - and _"><input className={inputCls} value={f.device_id} onChange={(e) => setF({ ...f, device_id: e.target.value })} placeholder="DEV-004" required /></Field>
          <Field label="Name"><input className={inputCls} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Airport lobby screen" required /></Field>
          <Field label="Group"><select className={inputCls} value={f.group_id} onChange={(e) => setF({ ...f, group_id: e.target.value })}><option value="">— none —</option>{groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Initial latitude"><input className={inputCls} value={f.latitude} onChange={(e) => setF({ ...f, latitude: e.target.value })} placeholder="optional" /></Field>
            <Field label="Initial longitude"><input className={inputCls} value={f.longitude} onChange={(e) => setF({ ...f, longitude: e.target.value })} placeholder="optional" /></Field>
          </div>
          <Button className="w-full">Create device</Button>
        </form>
      )}
    </Modal>
  )
}
