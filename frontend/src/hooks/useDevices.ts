import { useCallback, useEffect, useRef, useState } from 'react'
import { api, getClientId } from '../services/api'
import type { Device } from '../types'
import { useLive } from './useLive'

/**
 * The device list, kept fresh over the admin WebSocket (with an optional poll as a safety net).
 * `onEvent` sees every live event, so a page that reacts to more than devices needs only one socket.
 */
export function useDevices({ pollMs = 0, onEvent }: { pollMs?: number; onEvent?: (e: any) => void } = {}) {
  const [devices, setDevices] = useState<Device[] | null>(null)
  const refresh = useCallback(() => api.get<Device[]>('/devices').then((r) => setDevices(r.data)), [])
  const extra = useRef(onEvent)
  extra.current = onEvent

  useEffect(() => { refresh() }, [refresh])
  useEffect(() => {
    if (!pollMs) return
    const t = setInterval(refresh, pollMs)
    return () => clearInterval(t)
  }, [pollMs, refresh])

  const live = useLive((e) => {
    if (e.event === 'device_update') {
      const cid = getClientId()
      if (cid && String(e.device.client_id) !== cid) return       // a platform user looking at one client ignores the others
      setDevices((prev) => {
        const list = prev ?? []
        return list.some((d) => d.device_id === e.device.device_id)
          ? list.map((d) => (d.device_id === e.device.device_id ? e.device : d))
          : [...list, e.device]
      })
    } else if (e.event === 'device_removed') {
      setDevices((prev) => (prev ?? []).filter((d) => d.device_id !== e.device_id))
    }
    extra.current?.(e)
  })

  return { devices, refresh, live }
}
