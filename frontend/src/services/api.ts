import axios from 'axios'

export const api = axios.create({ baseURL: '/api' })

export const getToken = () => localStorage.getItem('token')
export const getRole = () => localStorage.getItem('role') || 'viewer'
export const isAdmin = () => getRole() === 'admin'

api.interceptors.request.use((cfg) => {
  const t = getToken()
  if (t) cfg.headers.Authorization = `Bearer ${t}`
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
