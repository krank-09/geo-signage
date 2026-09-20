export type ConnectionType = 'wifi' | 'ethernet' | 'cellular_4g' | 'cellular_5g' | 'other'

export interface RouteStatus { route_id: number; leg: number; leg_label: string | null; progress: number | null; offset_km: number | null; off_route: boolean }
export interface Waypoint { name: string; lat: number; lng: number }
export interface RouteInfo {
  id: number; name: string; waypoints: Waypoint[]; corridor_km: number; color: string; legs: number
  devices: ({ device_id: string; name: string } & Partial<RouteStatus>)[]
}
export interface TrackPoint { lat: number; lng: number; ts: string; zone_id: number | null; entered: boolean }
export interface ZoneVisit { zone_id: number; zone_name: string; visits: number; devices: number }

export interface Device {
  route_id: number | null; route: RouteStatus | null; screenshot_at: string | null
  client_id: number | null
  os_name: string | null; os_version: string | null; os_arch: string | null; runtime_version: string | null; capabilities: string[]
  protection: 'protected' | 'unprotected'; key_bound_at: string | null; tamper_state: 'flagged' | null; tamper_flagged_at: string | null
  id: number; device_id: string; name: string; status: 'online' | 'offline'; registered: boolean
  group_id: number | null; group: string | null; latitude: number | null; longitude: number | null
  last_seen: string | null; zone_id: number | null; zone: string | null; content_version: string | null
  current_content: string | null; software_version: string | null; cpu: number | null; memory: number | null
  network: string | null; gps_ok: boolean; ws_connected: boolean
  config: { heartbeat_interval: number; location_interval: number; mute: boolean; fit: 'contain' | 'cover' }
  connection_type: ConnectionType | null; health: number; health_reasons: string[]
  resolved?: { items: { name: string }[]; reason: string; emergency: boolean }
}
export interface Content { id: number; name: string; type: 'image' | 'video'; mime: string; size: number; duration: number; version: number; created_at: string }
export interface Zone { id: number; name: string; polygon: [number, number][]; priority: number; color: string }
export interface Assignment {
  id: number; content_id: number; content_name: string; content_type: string; zone_id: number | null; zone_name: string | null
  group_id: number | null; group_name: string | null; route_id: number | null; route_name: string | null; route_leg: number | null
  start_time: string | null; end_time: string | null
  priority: number; is_emergency: boolean; active: boolean
}
export interface Group { id: number; name: string; device_count: number }
export interface LogEntry { id: number; ts: string; kind: string; message: string; device_id: string }

export interface Broadcast {
  id: number; message: string; style: 'ticker' | 'banner' | 'fullscreen'; severity: 'info' | 'warning' | 'critical'
  zone_id: number | null; zone_name: string | null; group_id: number | null; group_name: string | null; device_id: string | null
  created_by: string; created_at: string; expires_at: string | null; ended_at: string | null; active: boolean; remaining_seconds: number | null
}
export interface Alert {
  id: number; device_id: string; device_name?: string | null; kind: 'offline' | 'health_low' | 'tamper' | 'off_route'; message: string; health: number
  created_at: string; resolved_at: string | null; acknowledged_at: string | null; acknowledged_by: string | null
}
export interface City { id: string; name: string; state: string; center: [number, number]; source: 'osm' | 'approx'; area_km2: number; vertices: number; zone_exists: boolean }
export interface CityDetail extends Omit<City, 'zone_exists' | 'vertices'> { polygon: [number, number][] }
export interface DiscoveredAgent { id: string; name: string; latitude: number | null; longitude: number | null; connection_type: ConnectionType | null; software_version: string | null; seconds_ago: number; zones: string[] }
export interface AppUser { client_id?: number | null; id: number; username: string; role: 'admin' | 'viewer' | 'pending'; email: string | null; source: 'local' | 'firebase'; created_at: string }
export interface AuthConfig {
  local_login: boolean
  firebase: { apiKey: string; authDomain: string; projectId: string; appId: string; emulatorHost: string | null } | null
}

export const CONNECTION_LABELS: Record<ConnectionType, string> = { wifi: 'Wi-Fi', ethernet: 'Ethernet', cellular_4g: 'Cellular 4G', cellular_5g: 'Cellular 5G', other: 'Other' }

export interface ClientInfo {
  id: number; name: string; slug: string; active: boolean; device_limit: number | null; enrollment_key: string | null
  devices: number; devices_online: number; tampered: number; content: number; zones: number; users: number
}
export interface FleetRow {
  device_id: string; name: string; client_id: number | null; status: string; software_version: string | null; os_name: string | null
  os_version: string | null; os_arch: string | null; runtime_version: string | null; capabilities: string[]
  compatibility: 'ok' | 'outdated' | 'unsupported' | 'unknown'; protection: 'protected' | 'unprotected'; tamper_state: 'flagged' | null
}
export interface FleetInventory {
  policy: { recommended_version: string | null; supported_version: string | null }
  devices: FleetRow[]
  summary: { total: number; by_os: Record<string, number>; by_version: Record<string, number>; by_arch: Record<string, number>
    by_compatibility: Record<string, number>; by_protection: Record<string, number>; tampered: number }
}
export interface TamperEvent { id: number; client_id: number | null; device_id: string; kind: string; severity: 'info' | 'warning' | 'critical'; source: string; detail: string; created_at: string; hash: string }
export interface SecurityStatus { mode: string; server_key_fingerprint: string; protected: number; unprotected: number; flagged: string[]; audit: { ok: boolean; events: number; broken_at: number | null } | null }
export interface Release { id: number; version: string; code_hash: string; note: string; created_at: string }
