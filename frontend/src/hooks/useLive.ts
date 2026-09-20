import { useEffect, useRef, useState } from 'react'
import { getToken } from '../services/api'

/** Subscribes to the backend's admin WebSocket; reconnects automatically. */
export function useLive(onEvent: (e: any) => void): boolean {
  const [connected, setConnected] = useState(false)
  const handler = useRef(onEvent)
  handler.current = onEvent

  useEffect(() => {
    let ws: WebSocket | null = null
    let closed = false
    let retry: number
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/api/ws/admin?token=${getToken()}`)
      ws.onopen = () => setConnected(true)
      ws.onmessage = (m) => { try { handler.current(JSON.parse(m.data)) } catch { /* ignore */ } }
      ws.onclose = () => { setConnected(false); if (!closed) retry = window.setTimeout(connect, 2000) }
    }
    connect()
    return () => { closed = true; clearTimeout(retry); ws?.close() }
  }, [])
  return connected
}
