import { lazy } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { getToken } from './services/api'
import Layout from './components/Layout'
import Login from './pages/Login'

// Each page is its own chunk: the map/chart-heavy ones are only downloaded when visited.
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Devices = lazy(() => import('./pages/Devices'))
const ContentPage = lazy(() => import('./pages/Content'))
const Zones = lazy(() => import('./pages/Zones'))
const Schedules = lazy(() => import('./pages/Schedules'))
const Broadcast = lazy(() => import('./pages/Broadcast'))
const Emergency = lazy(() => import('./pages/Emergency'))
const Monitoring = lazy(() => import('./pages/Monitoring'))
const Users = lazy(() => import('./pages/Users'))

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={getToken() ? <Layout /> : <Navigate to="/login" replace />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/devices" element={<Devices />} />
        <Route path="/content" element={<ContentPage />} />
        <Route path="/zones" element={<Zones />} />
        <Route path="/schedules" element={<Schedules />} />
        <Route path="/broadcast" element={<Broadcast />} />
        <Route path="/emergency" element={<Emergency />} />
        <Route path="/monitoring" element={<Monitoring />} />
        <Route path="/users" element={<Users />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
