import { useEffect, useState } from 'react'
import { api } from '../services/api'

/** The health level below which an alert is raised (used to colour health bars). */
export function useHealthThreshold(): [number, (value: number) => void] {
  const [threshold, setThreshold] = useState(50)
  useEffect(() => { api.get('/settings/health').then((r) => setThreshold(r.data.threshold)).catch(() => {}) }, [])
  return [threshold, setThreshold]
}
