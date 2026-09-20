import axios from 'axios'

export const api = axios.create({ baseURL: '/api' })

export const getToken = () => localStorage.getItem('token')
export const getRole = () => localStorage.getItem('role') || 'viewer'
export const isAdmin = () => getRole() === 'admin'
/** Platform users (no client of their own) can look at one client at a time, or at all of them. */
export const isPlatform = () => localStorage.getItem('platform') === '1'
export const getClientId = () => (isPlatform() ? localStorage.getItem('client_id') : null)
export const setClientId = (id: number | null) => { if (id == null) localStorage.removeItem('client_id'); else localStorage.setItem('client_id', String(id)) }
export const saveSession = (d: { access_token: string; role: string; username: string; platform?: boolean; client_id?: number | null; client_name?: string | null }) => {
  localStorage.setItem('token', d.access_token); localStorage.setItem('role', d.role); localStorage.setItem('username', d.username)
  localStorage.setItem('platform', d.platform ? '1' : '0'); localStorage.setItem('client_name', d.client_name || '')
  localStorage.removeItem('client_id')
}

api.interceptors.request.use((cfg) => {
  const t = getToken()
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  const c = getClientId()
  if (c) cfg.headers['X-Client-Id'] = c
  return cfg
})
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && !err.config?.url?.includes('/auth/login')) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

export const errMsg = (e: any): string => {
  const d = e?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map((x) => x.msg).join('; ')
  return e?.message || 'Something went wrong'
}

/** URL for <img>/<video> that cannot send an Authorization header. */
export const mediaUrl = (id: number, version = 0) => `/api/content/${id}/file?token=${getToken()}&v=${version}`
