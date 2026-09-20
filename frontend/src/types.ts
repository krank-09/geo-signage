export interface Device {
  id: number; device_id: string; name: string; status: 'online' | 'offline'; registered: boolean
  group_id: number | null; group: string | null; latitude: number | null; longitude: number | null
  last_seen: string | null; zone_id: number | null; zone: string | null; content_version: string | null
  current_content: string | null; software_version: string | null; cpu: number | null; memory: number | null
  network: string | null; gps_ok: boolean; ws_connected: boolean
  config: { heartbeat_interval: number; location_interval: number; mute: boolean; fit: 'contain' | 'cover' }
  resolved?: { items: { name: string }[]; reason: string; emergency: boolean }
}
export interface Content { id: number; name: string; type: 'image' | 'video'; mime: string; size: number; duration: number; version: number; created_at: string }
export interface Zone { id: number; name: string; polygon: [number, number][]; priority: number; color: string }
export interface Assignment {
  id: number; content_id: number; content_name: string; content_type: string; zone_id: number | null; zone_name: string | null
  group_id: number | null; group_name: string | null; start_time: string | null; end_time: string | null
  priority: number; is_emergency: boolean; active: boolean
}
export interface Group { id: number; name: string; device_count: number }
export interface LogEntry { id: number; ts: string; kind: string; message: string; device_id: string }
