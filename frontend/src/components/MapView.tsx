import { useEffect } from 'react'
import { CircleMarker, MapContainer, Polygon, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import type { Device, RouteInfo, Zone } from '../types'

const INDIA: [number, number] = [23.5, 77]

function Fit({ zones, devices, routes, trail }: { zones: Zone[]; devices: Device[]; routes: RouteInfo[]; trail?: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    const pts: [number, number][] = [...zones.flatMap((z) => z.polygon), ...routes.flatMap((r) => r.waypoints.map((w) => [w.lat, w.lng] as [number, number])), ...(trail ?? []), ...devices.filter((d) => d.latitude != null).map((d) => [d.latitude!, d.longitude!] as [number, number])]
    if (pts.length) map.fitBounds(pts, { padding: [30, 30], maxZoom: 9 })
    // fit once on first data, not on every live update
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zones.length > 0, routes.length, trail?.length])
  return null
}

function FitPreview({ polygon }: { polygon: [number, number][] | null }) {
  const map = useMap()
  useEffect(() => { if (polygon && polygon.length) map.fitBounds(polygon, { padding: [40, 40], maxZoom: 12 }) }, [polygon, map])
  return null
}

function Clicks({ onClick }: { onClick: (p: [number, number]) => void }) {
  useMapEvents({ click: (e) => onClick([e.latlng.lat, e.latlng.lng]) })
  return null
}

export default function MapView({ zones, devices = [], routes = [], trail, draft, preview, onMapClick, selectedZone, onZoneClick, height = 420 }: {
  zones: Zone[]; devices?: Device[]; routes?: RouteInfo[]; trail?: [number, number][]; draft?: [number, number][]; preview?: [number, number][] | null; onMapClick?: (p: [number, number]) => void
  selectedZone?: number | null; onZoneClick?: (z: Zone) => void; height?: number
}) {
  return (
    <MapContainer center={INDIA} zoom={5} style={{ height, borderRadius: 12 }} className={onMapClick ? 'cursor-crosshair' : ''}>
      <TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <Fit zones={zones} devices={devices} routes={routes} trail={trail} />
      {onMapClick && <Clicks onClick={onMapClick} />}
      {preview && <><Polygon positions={preview} pathOptions={{ color: '#5b49eb', weight: 3, dashArray: '8 6', fillColor: '#5b49eb', fillOpacity: 0.18 }} /><FitPreview polygon={preview} /></>}
      {zones.map((z) => (
        <Polygon key={z.id} positions={z.polygon} eventHandlers={{ click: () => onZoneClick?.(z) }}
          pathOptions={{ color: z.color, weight: selectedZone === z.id ? 4 : 2, fillOpacity: selectedZone === z.id ? 0.35 : 0.15 }}>
          <Tooltip sticky>{z.name} (priority {z.priority})</Tooltip>
        </Polygon>
      ))}
      {routes.map((r) => (
        <span key={r.id}>
          <Polyline positions={r.waypoints.map((w) => [w.lat, w.lng] as [number, number])} pathOptions={{ color: r.color, weight: 4, dashArray: '10 6', opacity: 0.85 }}><Tooltip sticky>{r.name}</Tooltip></Polyline>
          {r.waypoints.map((w, i) => <CircleMarker key={i} center={[w.lat, w.lng]} radius={6} pathOptions={{ color: r.color, fillColor: '#fff', fillOpacity: 1, weight: 3 }}><Tooltip direction="top">{i + 1}. {w.name}</Tooltip></CircleMarker>)}
        </span>
      ))}
      {trail && trail.length > 1 && <Polyline positions={trail} pathOptions={{ color: '#0ea5a4', weight: 4, opacity: 0.9 }} />}
      {draft && draft.length > 0 && (
        <>
          <Polyline positions={draft} pathOptions={{ color: '#f59e0b', dashArray: '6' }} />
          {draft.map((p, i) => <CircleMarker key={i} center={p} radius={5} pathOptions={{ color: '#f59e0b', fillOpacity: 1 }} />)}
        </>
      )}
      {devices.filter((d) => d.latitude != null).map((d) => (
        <CircleMarker key={d.device_id} center={[d.latitude!, d.longitude!]} radius={9}
          pathOptions={{ color: '#fff', weight: 2, fillColor: d.status === 'online' ? '#16a34a' : '#dc2626', fillOpacity: 1 }}>
          <Tooltip direction="top" offset={[0, -8]}>
            <b>{d.device_id}</b> · {d.name}<br />{d.status} · {d.zone || 'no zone'}<br />{d.current_content || '—'}
          </Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  )
}
