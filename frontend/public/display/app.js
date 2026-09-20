// Geo Signage web display: turns a phone or tablet browser into a display device.
// Same protocol as the Python agent: register with a signed request, report GPS and heartbeats, receive a signed playlist,
// verify and cache each file, play from the cache (also offline), report tamper detections and screenshots.
// Needs a secure context (HTTPS, or localhost) for WebCrypto, geolocation and the service worker.

const VERSION = '1.3.0'                 // keep in step with device/VERSION so the fleet policy treats web and Python displays alike
const API = '/api'
const SHOT_EVERY = 60, VERIFY_EVERY = 60, CLOCK_ROLLBACK = 120
const PLACES = { chandigarh: [30.7333, 76.7794], delhi: [28.6139, 77.2090], jaipur: [26.9124, 75.7873], mumbai: [19.0760, 72.8777], ahmedabad: [23.0225, 72.5714] }
const $ = (id) => document.getElementById(id)
const enc = (s) => new TextEncoder().encode(s)

// ---------------------------------------------------------------------------------------------- small helpers
const LS = {
  get: (k, d = null) => { try { const v = localStorage.getItem('gs.' + k); return v === null ? d : JSON.parse(v) } catch { return d } },
  set: (k, v) => localStorage.setItem('gs.' + k, JSON.stringify(v)),
  del: (k) => localStorage.removeItem('gs.' + k),
}
const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)))
const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0))
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('')
const sha256 = async (bytes) => hex(await crypto.subtle.digest('SHA-256', bytes))
const rand = (n) => hex(crypto.getRandomValues(new Uint8Array(n)))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const idb = (() => {                     // tiny promise wrapper: two stores, "keys" (identity) and "media" (verified files)
  let db
  const open = () => db || (db = new Promise((res, rej) => {
    const r = indexedDB.open('gs-display', 1)
    r.onupgradeneeded = () => { r.result.createObjectStore('keys'); r.result.createObjectStore('media') }
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error)
  }))
  const run = async (store, mode, fn) => { const d = await open(); return new Promise((res, rej) => { const t = d.transaction(store, mode); const q = fn(t.objectStore(store)); t.oncomplete = () => res(q && q.result); t.onerror = () => rej(t.error) }) }
  return {
    get: (s, k) => run(s, 'readonly', (o) => o.get(k)), put: (s, k, v) => run(s, 'readwrite', (o) => o.put(v, k)),
    del: (s, k) => run(s, 'readwrite', (o) => o.delete(k)), keys: (s) => run(s, 'readonly', (o) => o.getAllKeys()),
    clear: async () => { const d = await open(); d.close(); db = null; await new Promise((r) => { const q = indexedDB.deleteDatabase('gs-display'); q.onsuccess = q.onerror = q.onblocked = () => r() }) },
  }
})()

// ---------------------------------------------------------------------------------------------- state
const cfg = { id: LS.get('id'), token: LS.get('token'), regToken: LS.get('regToken'), loc: LS.get('loc', 'gps') }
let state = {
  device_id: cfg.id, online: true, ws: false, items: [], broadcasts: [], zone: null, reason: '', emergency: false, position: null,
  config: { heartbeat_interval: 10, location_interval: 3, mute: true, fit: 'contain' }, manifest_version: null, signed: false, verified: false,
}
let ident = null                         // { priv, pubB64 } when Ed25519 is available, else null (runs unsigned)
let clockOffset = 0, serverKey = LS.get('server_key'), stopped = false
let impressions = [], tamperQueue = LS.get('tamper_queue', []), seen = {}
let shotWanted = false, lastShot = 0, codeHash = ''
const urls = new Map()                   // cache key -> object URL for the media element

// ---------------------------------------------------------------------------------------------- identity + signing
async function loadIdentity() {
  try {
    let pair = await idb.get('keys', 'device')
    if (!pair) {
      pair = await crypto.subtle.generateKey({ name: 'Ed25519' }, false, ['sign', 'verify'])   // private key is non-extractable
      await idb.put('keys', 'device', pair)
    }
    ident = { priv: pair.privateKey, pubB64: b64(await crypto.subtle.exportKey('raw', pair.publicKey)) }
  } catch (e) { ident = null }           // browser without Ed25519 (older Safari/Chrome): fine while the server allows unsigned displays
  return ident
}
async function signHeaders(method, path, body) {
  if (!ident) return {}
  const ts = String(Math.floor(Date.now() / 1000 + clockOffset)), nonce = rand(12)
  const msg = `${method.toUpperCase()}\n${path}\n${ts}\n${nonce}\n${await sha256(body)}`
  return { 'X-Signature': b64(await crypto.subtle.sign('Ed25519', ident.priv, enc(msg))), 'X-Timestamp': ts, 'X-Nonce': nonce }
}

class Offline extends Error {}
let registering = null
async function call(method, path, { json, body, ctype, auth = true, retry = true } = {}) {
  const bytes = body ?? (json !== undefined ? enc(JSON.stringify(json)) : new Uint8Array())
  const headers = { ...(auth && cfg.token ? { Authorization: `Bearer ${cfg.token}` } : {}), ...(await signHeaders(method, path, bytes)) }
  if (bytes.length) headers['Content-Type'] = ctype || 'application/json'
  let res
  try { res = await fetch(API + path, { method, headers, body: bytes.length ? bytes : undefined, cache: 'no-store' }) }
  catch (e) { state.online = false; throw new Offline(String(e)) }
  const d = res.headers.get('Date'); if (d) clockOffset = new Date(d).getTime() / 1000 - Date.now() / 1000   // sign with the server's clock
  state.online = true
  if (res.status === 401 && auth && retry && cfg.regToken) {          // token revoked or expired: register again once
    await (registering ||= register().finally(() => { registering = null }))
    return call(method, path, { json, body, ctype, auth, retry: false })
  }
  return res
}

// ---------------------------------------------------------------------------------------------- inventory
function inventory() {
  const ua = navigator.userAgent
  let os = 'Unknown', ver = ''
  let m
  if ((m = /Android (\d+(?:\.\d+)*)/.exec(ua))) { os = 'Android'; ver = m[1] }
  else if ((m = /(?:iPhone|iPad|CPU) OS (\d+(?:_\d+)*)/.exec(ua))) { os = 'iOS'; ver = m[1].replace(/_/g, '.') }
  else if (/Windows/.test(ua)) { os = 'Windows'; ver = (/Windows NT ([\d.]+)/.exec(ua) || [])[1] || '' }
  else if ((m = /Mac OS X (\d+(?:[._]\d+)*)/.exec(ua))) { os = 'macOS'; ver = m[1].replace(/_/g, '.') }
  else if (/Linux|X11/.test(ua)) os = 'Linux'
  const br = /Edg\/([\d.]+)/.exec(ua) || /Firefox\/([\d.]+)/.exec(ua) || /(?:Chrome|CriOS)\/([\d.]+)/.exec(ua) || /Version\/([\d.]+).*Safari/.exec(ua)
  const name = /Edg\//.test(ua) ? 'Edge' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome|CriOS/.test(ua) ? 'Chrome' : /Safari/.test(ua) ? 'Safari' : 'Browser'
  const caps = ['web-display', 'signed-manifests', 'media-hash', 'tamper-report', 'screenshots', cfg.loc === 'gps' ? 'gps' : 'fixed-location']
  if (ident) caps.push('signed-requests')
  return {
    os_name: os, os_version: ver.slice(0, 64), os_arch: state.arch || 'unknown', runtime_version: `${name} ${(br ? br[1] : '').split('.')[0]}`.trim().slice(0, 32),
    software_version: VERSION, capabilities: caps, code_hash: codeHash,
  }
}
async function learnArch() {
  try {
    const h = await navigator.userAgentData?.getHighEntropyValues(['architecture', 'bitness'])
    if (h?.architecture) state.arch = `${h.architecture}${h.bitness === '64' ? '64' : ''}`.toLowerCase().slice(0, 24)
  } catch { /* not available in this browser */ }
}
async function hashOwnCode() {
  try { codeHash = await sha256(new Uint8Array(await (await fetch('/display/app.js', { cache: 'force-cache' })).arrayBuffer())) } catch { codeHash = '' }
}

// ---------------------------------------------------------------------------------------------- tamper reporting
function report(kind, detail) {
  const key = kind + detail.slice(0, 40)
  if (Date.now() - (seen[key] || 0) < 60000) return
  seen[key] = Date.now()
  console.warn('TAMPER', kind, detail)
  tamperQueue.push({ kind, detail: detail.slice(0, 500), at: new Date().toISOString() }); tamperQueue = tamperQueue.slice(-50)
  LS.set('tamper_queue', tamperQueue)
}
async function flushTamper() {
  if (!tamperQueue.length) return
  const batch = tamperQueue.slice(0, 50)
  const r = await call('POST', '/device/tamper', { json: { events: batch } })
  if (r.ok) { tamperQueue = tamperQueue.slice(batch.length); LS.set('tamper_queue', tamperQueue) }
}
function watchClock() {
  const last = LS.get('last_clock'), now = Date.now() / 1000
  if (last && now < last - CLOCK_ROLLBACK) report('clock_rollback', `System clock is ${Math.round(last - now)}s behind where it was`)
  LS.set('last_clock', now)
}

// ---------------------------------------------------------------------------------------------- registration
async function register() {
  await call('GET', '/health', { auth: false })                       // learn the server's clock before the first signed request
  const r = await call('POST', '/device/register', { auth: false, retry: false, json: {
    device_id: cfg.id, registration_token: cfg.regToken, ...(ident ? { public_key: ident.pubB64 } : {}),
    hw_fingerprint: (await sha256(enc('web/' + (LS.get('install') || (LS.set('install', rand(16)), LS.get('install')))))).slice(0, 32), ...inventory() } })
  if (!r.ok) {
    let detail = ''; try { detail = (await r.json()).detail } catch { /* not json */ }
    const e = new Error(r.status === 409 ? `${detail} Ask the administrator to open this device and choose "Revoke and re-issue token".` : (detail || `Registration failed (${r.status})`))
    e.status = r.status; throw e
  }
  const body = await r.json()
  cfg.token = body.access_token; LS.set('token', cfg.token)
  state.config = body.config || state.config; state.signed = !!body.signed
  if (body.server_public_key) {
    if (!serverKey) { serverKey = body.server_public_key; LS.set('server_key', serverKey) }      // trust on first use, as the agent does
    else if (serverKey !== body.server_public_key) report('manifest_signature_invalid', "The server's signing key changed since this display was set up")
  }
}

// ---------------------------------------------------------------------------------------------- playlist verification + media cache
async function verifyManifest(env) {
  const key = await crypto.subtle.importKey('raw', unb64(serverKey), { name: 'Ed25519' }, false, ['verify'])
  const ok = await crypto.subtle.verify('Ed25519', key, unb64(env.sig), enc(env.payload))
  const payload = JSON.parse(env.payload)
  if (!ok || payload.device_id !== cfg.id) throw new Error('playlist is not signed by the pinned server key')
  return payload
}
const cacheKey = (i) => `${i.content_id}-v${i.version}`

async function ensureMedia(item) {
  const key = cacheKey(item)
  const rec = await idb.get('media', key)
  if (rec && (!item.sha256 || rec.sha256 === item.sha256) && (!item.sha256 || await sha256(await rec.blob.arrayBuffer()) === item.sha256)) return
  if (rec) { await idb.del('media', key); report('cache_tampered', `${item.name} in the local cache was modified; removed and re-downloading`) }
  const r = await call('GET', item.url || `/device/${cfg.id}/media/${item.content_id}`)
  if (!r.ok) throw new Offline(`download failed: ${r.status}`)
  const buf = await r.arrayBuffer()
  if (item.sha256 && await sha256(buf) !== item.sha256) { report('media_hash_mismatch', `${item.name} did not match the signed hash; download discarded`); throw new Offline('integrity check failed') }
  await idb.put('media', key, { blob: new Blob([buf], { type: item.mime || 'application/octet-stream' }), sha256: item.sha256 || await sha256(buf), name: item.name })
}
async function srcFor(item) {
  const key = cacheKey(item)
  if (urls.has(key)) return urls.get(key)
  const rec = await idb.get('media', key)
  if (!rec) return null
  const u = URL.createObjectURL(rec.blob); urls.set(key, u); return u
}
async function gc(items) {
  const keep = new Set(items.map(cacheKey))
  for (const k of await idb.keys('media')) if (!keep.has(k)) { await idb.del('media', k); const u = urls.get(k); if (u) { URL.revokeObjectURL(u); urls.delete(k) } }
}
async function applyManifest(p) {
  const now = Date.now() / 1000
  const items = []
  for (const it of p.items) { const src = await srcFor(it); if (src) items.push({ ...it, src }) }
  state.items = items; state.zone = p.zone; state.reason = p.reason; state.emergency = !!p.emergency; state.manifest_version = p.manifest_version
  state.config = { ...state.config, ...(p.config || {}) }
  state.broadcasts = (p.broadcasts || []).map((b) => ({ ...b, deadline: b.remaining_seconds == null ? null : now + b.remaining_seconds }))
}

async function sync() {
  const r = await call('GET', `/device/${cfg.id}/content`)
  if (!r.ok) throw new Offline(`content fetch failed: ${r.status}`)
  let remote = await r.json()
  state.verified = false
  if (serverKey && ident) {
    if (!remote.signed) { report('manifest_signature_invalid', 'playlist arrived without a signature'); throw new Offline('unsigned playlist rejected') }
    try { remote = await verifyManifest(remote.signed); state.verified = true }
    catch (e) { report('manifest_signature_invalid', String(e.message || e)); throw new Offline('rejected a wrongly signed playlist; keeping the last good one') }
  }
  for (const it of remote.items) await ensureMedia(it)
  await applyManifest(remote)
  await gc(remote.items)
  LS.set('manifest', { ...remote, broadcasts: undefined })
}
let syncing = false
async function syncSafe() { if (syncing) return; syncing = true; try { await sync() } catch (e) { if (!(e instanceof Offline)) console.error(e) } finally { syncing = false } }

async function verifyLoop() {
  while (!stopped) {
    await sleep(VERIFY_EVERY * 1000)
    await verifyNow()
  }
}
async function verifyNow() {
  let bad = 0
  for (const it of state.items) {
    if (!it.sha256) continue
    const rec = await idb.get('media', cacheKey(it))
    if (!rec || await sha256(await rec.blob.arrayBuffer()) !== it.sha256) {
      bad++; if (rec) { await idb.del('media', cacheKey(it)); report('cache_tampered', `${it.name} in the local cache was modified; removed and re-downloading`) }
      urls.delete(cacheKey(it))
    }
  }
  if (bad) syncSafe()
  return bad
}

// ---------------------------------------------------------------------------------------------- loops: location, heartbeat, websocket
let watchId = null
function startLocation() {
  if (cfg.loc !== 'gps') { state.position = PLACES[cfg.loc] || PLACES.delhi; return }
  if (!navigator.geolocation) { state.gpsError = 'This browser has no geolocation'; return }
  watchId = navigator.geolocation.watchPosition(
    (p) => { state.position = [p.coords.latitude, p.coords.longitude]; state.gpsError = null },
    (e) => { state.gpsError = e.code === 1 ? 'Location permission denied' : 'No GPS fix' }, { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 })
}
async function locationLoop() {
  while (!stopped) {
    if (state.position && cfg.token) {
      try {
        const r = await call('POST', '/device/location', { json: { latitude: state.position[0], longitude: state.position[1], device_id: cfg.id } })
        if (r.ok) noteServer(await r.json())
      } catch { /* offline: keep playing */ }
    }
    await sleep((state.config.location_interval || 3) * 1000)
  }
}
function noteServer(b) {
  if (b.config) state.config = { ...state.config, ...b.config }
  if (b.manifest_version !== state.manifest_version) syncSafe()      // the server's playlist hash differs from ours: fetch the new one
}
async function heartbeatLoop() {
  while (!stopped) {
    try {
      watchClock()
      const conn = navigator.connection
      const r = await call('POST', '/device/heartbeat', { json: {
        network: conn?.effectiveType ? `connected (${conn.effectiveType})` : 'connected', gps: state.position != null,
        content_version: state.manifest_version || '', content_names: state.items.map((i) => i.name).join(', ').slice(0, 480), ...inventory(),
        ...(state.position ? { latitude: state.position[0], longitude: state.position[1] } : {}) } })
      if (r.ok) noteServer(await r.json())
      await flushImpressions(); await flushTamper()
    } catch { /* offline */ }
    await sleep((state.config.heartbeat_interval || 10) * 1000)
  }
}
let ws, wsBackoff = 1
function connectWs() {
  if (stopped || !cfg.token) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}${API}/ws/device/${cfg.id}?token=${cfg.token}`)
  ws.onopen = () => { state.ws = true; wsBackoff = 1 }
  ws.onmessage = (m) => { try { const d = JSON.parse(m.data); if (d.type === 'sync') { if (d.reason === 'screenshot') shotWanted = true; else syncSafe() } } catch { /* ignore */ } }
  ws.onclose = () => { state.ws = false; setTimeout(connectWs, wsBackoff * 1000); wsBackoff = Math.min(wsBackoff * 2, 15) }
}
async function pollLoop() { while (!stopped) { await sleep(5000); if (!syncing) await syncSafe() } }

async function flushImpressions() {
  const batch = impressions.slice(0, 200)
  if (!batch.length) return
  const r = await call('POST', '/device/impressions', { json: { items: batch } })
  if (r.ok) impressions = impressions.slice(batch.length)
}

// ---------------------------------------------------------------------------------------------- screenshots
async function capture() {
  if (document.visibilityState !== 'visible') return
  const W = 640, H = 360, c = document.createElement('canvas'); c.width = W; c.height = H
  const g = c.getContext('2d'), s = state
  g.fillStyle = s.items.length ? '#000' : '#0f172a'; g.fillRect(0, 0, W, H)
  const w = current && (current.videoWidth || current.naturalWidth), h = current && (current.videoHeight || current.naturalHeight)
  if (s.items.length && w && h) {
    const r = (s.config.fit === 'cover' ? Math.max : Math.min)(W / w, H / h)
    g.drawImage(current, (W - w * r) / 2, (H - h * r) / 2, w * r, h * r)
  } else { g.fillStyle = '#fff'; g.font = 'bold 26px system-ui'; g.textAlign = 'center'; g.fillText(s.items.length ? 'Loading content' : s.device_id + ' - waiting for content', W / 2, H / 2) }
  if (s.emergency) { g.strokeStyle = '#ef4444'; g.lineWidth = 8; g.strokeRect(4, 4, W - 8, H - 8) }
  const b = (s.broadcasts || [])[0]
  if (b) { g.fillStyle = { info: '#4338ca', warning: '#b45309', critical: '#b91c1c' }[b.severity] || '#4338ca'; g.fillRect(0, H - 40, W, 40); g.fillStyle = '#fff'; g.font = 'bold 20px system-ui'; g.textAlign = 'left'; g.fillText(b.message.slice(0, 48), 12, H - 14) }
  g.fillStyle = 'rgba(15,23,42,.75)'; g.fillRect(8, 8, 200, 24); g.fillStyle = '#fff'; g.font = '13px system-ui'; g.textAlign = 'left'
  g.fillText((s.online ? 'ONLINE' : 'OFFLINE (cached)') + '  ' + s.device_id, 16, 25)
  const blob = await new Promise((res) => c.toBlob(res, 'image/jpeg', 0.6))
  if (!blob) return
  const r = await call('POST', '/device/screenshot', { body: new Uint8Array(await blob.arrayBuffer()), ctype: 'image/jpeg' })
  if (r.ok) { lastShot = Date.now(); shotWanted = false }
}
async function shotLoop() { while (!stopped) { await sleep(1000); if (cfg.token && (shotWanted || Date.now() - lastShot > SHOT_EVERY * 1000)) { try { await capture() } catch { lastShot = Date.now() - (SHOT_EVERY - 10) * 1000 } } } }

// ---------------------------------------------------------------------------------------------- playback (same behaviour as the desktop display page)
const stage = $('stage')
let idx = 0, timer = null, current = null, epoch = 0, signature = ''
function impression(item, startedAt) {
  const dur = (Date.now() - startedAt) / 1000
  if (dur < 0.5) return
  impressions.push({ content_id: item.content_id, duration: dur, zone_id: state.zone?.id ?? null, started_at: new Date(startedAt).toISOString() }); impressions = impressions.slice(-1000)
}
function clearPlayback() { clearTimeout(timer); timer = null; epoch++ }
function playNext(myEpoch) {
  if (myEpoch !== epoch || !state.items.length) return
  const items = state.items
  idx = idx % items.length
  const item = items[idx], startedAt = Date.now()
  const advance = () => { if (myEpoch !== epoch) return; impression(item, startedAt); idx++; playNext(myEpoch) }
  let el
  if (item.type === 'video') {
    el = document.createElement('video'); el.src = item.src; el.autoplay = true; el.muted = state.config.mute !== false; el.playsInline = true
    el.onended = advance; el.onerror = () => { timer = setTimeout(advance, 1500) }
    if (items.length === 1) el.loop = true
  } else {
    el = document.createElement('img'); el.src = item.src; el.onerror = () => { timer = setTimeout(advance, 1500) }
    timer = setTimeout(advance, Math.max(item.duration, 1) * 1000)
  }
  el.style.objectFit = state.config.fit === 'cover' ? 'cover' : 'contain'
  stage.appendChild(el)
  requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('show')))
  const old = current; current = el
  if (old) { old.classList.remove('show'); setTimeout(() => old.remove(), 700) }
  if (item.type === 'video' && items.length === 1) el.play().catch(() => {})
}
let broadcastSig = ''
const SEV = { info: 0, warning: 1, critical: 2 }
function renderBroadcasts(list) {
  const sig = JSON.stringify(list.map((b) => [b.id, b.message, b.style, b.severity]))
  if (sig === broadcastSig) return
  broadcastSig = sig
  const top = (a) => a.reduce((x, y) => (SEV[y.severity] >= SEV[x.severity] ? y : x), a[0])
  const by = (st) => list.filter((b) => b.style === st)
  const show = (el, sev) => { el.className = 'sev-' + sev; el.style.display = el.id === 'banner' ? 'block' : 'flex' }
  const [bn, tk, fl] = [by('banner'), by('ticker'), by('fullscreen')]
  const B = $('banner'), T = $('ticker'), F = $('fullscreen')
  if (bn.length) { const x = top(bn); B.textContent = x.message; show(B, x.severity) } else B.style.display = 'none'
  if (fl.length) { const x = top(fl); F.textContent = x.message; show(F, x.severity) } else F.style.display = 'none'
  if (tk.length) { const t = tk.map((x) => x.message).join('      •      '), sp = $('ticker-text'); sp.textContent = t; sp.style.animationDuration = Math.max(12, t.length * 0.22) + 's'; show(T, top(tk).severity) } else T.style.display = 'none'
  document.body.classList.toggle('has-ticker', tk.length > 0)
}
function render() {
  const s = state, live = s.broadcasts.filter((b) => b.deadline == null || b.deadline > Date.now() / 1000)
  renderBroadcasts(live)
  $('empty').style.display = s.items.length ? 'none' : 'flex'
  $('e-id').textContent = s.gpsError ? s.gpsError : `${s.device_id} - waiting for content`
  $('emergency').style.display = s.emergency ? 'block' : 'none'
  $('status').classList.toggle('off', !s.online)
  $('status-text').textContent = s.online ? 'ONLINE' + (s.ws ? ' - live' : '') : 'OFFLINE - playing cached content'
  $('info').textContent = `${s.device_id}  |  ${s.reason || (s.zone ? s.zone.name : 'no zone')}` + (s.gpsError ? `  |  ${s.gpsError}` : '') + (impressions.length > 20 ? `  |  ${impressions.length} queued` : '')
  const sig = s.items.map((i) => i.src).join(',') + '|' + s.config.fit + '|' + s.config.mute
  if (sig !== signature) { signature = sig; idx = 0; clearPlayback(); if (s.items.length) playNext(epoch); else if (current) { current.remove(); current = null } }
  else if (!timer && !current && s.items.length) playNext(epoch)
}

// ---------------------------------------------------------------------------------------------- screen wake lock, fullscreen, menu
let wake = null
async function keepAwake() { try { wake = await navigator.wakeLock?.request('screen'); wake?.addEventListener('release', () => { wake = null }) } catch { /* not allowed right now */ } }
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && !wake && cfg.token) keepAwake() })
const goFull = () => document.documentElement.requestFullscreen?.().catch(() => {})
function menu() {
  const rows = [['Device', cfg.id], ['Status', state.online ? 'Online' : 'Offline (cached)'], ['Identity', ident ? 'Key bound (protected)' : 'No key (browser lacks Ed25519)'],
    ['Playlist', state.verified ? 'Signature verified' : 'Not verified'], ['Location', cfg.loc === 'gps' ? (state.position ? state.position.map((n) => n.toFixed(4)).join(', ') : state.gpsError || 'waiting') : `Fixed: ${cfg.loc}`], ['Version', VERSION]]
  $('menu-info').innerHTML = ''
  for (const [k, v] of rows) { const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = k; dd.textContent = v; $('menu-info').append(dt, dd) }
  $('menu').style.display = 'flex'
}
$('gear').onclick = menu
$('m-close').onclick = () => { $('menu').style.display = 'none' }
$('m-full').onclick = () => { goFull(); $('menu').style.display = 'none' }
$('m-reset').onclick = async () => {
  if (!confirm('Forget this display? It will need its registration token again.')) return
  stopped = true; if (watchId != null) navigator.geolocation.stopWatching?.(watchId)
  for (const k of ['id', 'token', 'regToken', 'loc', 'manifest', 'server_key', 'tamper_queue', 'install', 'last_clock']) LS.del(k)
  await idb.clear(); location.href = '/display/'
}

// ---------------------------------------------------------------------------------------------- start
async function start() {
  await Promise.all([hashOwnCode(), learnArch()])
  const saved = LS.get('manifest')
  if (saved) { try { await applyManifest(saved) } catch { /* nothing cached yet */ } }      // offline start: play what we have
  render(); setInterval(render, 1000)
  startLocation()
  if (!cfg.token) { try { await register() } catch (e) { if (!(e instanceof Offline)) { showSetup(e.message); return false } } }
  connectWs(); syncSafe(); locationLoop(); heartbeatLoop(); pollLoop(); verifyLoop(); shotLoop()
  keepAwake()
  return true
}
function showSetup(message = '') { $('setup').style.display = 'flex'; $('err').textContent = message }
async function boot() {
  if (!window.isSecureContext || !crypto?.subtle) { document.body.innerHTML = '<p style="padding:24px;font:16px system-ui">This page needs a secure connection. Open it over <b>https://</b> (the tunnel address), or on <b>localhost</b>.</p>'; return }
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/display/sw.js', { scope: '/display/' }).catch(() => {})
  await loadIdentity()
  const h = new URLSearchParams(location.hash.slice(1))                                    // link from the dashboard: /display/#id=DEV-004&token=XXXX
  if (h.get('id') && h.get('token') && !cfg.id) { $('f-id').value = h.get('id'); $('f-token').value = h.get('token'); history.replaceState(null, '', '/display/') }
  if (cfg.id && (cfg.token || cfg.regToken)) { $('setup').style.display = 'none'; await start(); return }
  showSetup()
}
$('setup-form').onsubmit = async (e) => {
  e.preventDefault()
  cfg.id = $('f-id').value.trim().toUpperCase(); cfg.regToken = $('f-token').value.trim().toUpperCase(); cfg.loc = $('f-loc').value; cfg.token = null
  state.device_id = cfg.id; LS.set('id', cfg.id); LS.set('regToken', cfg.regToken); LS.set('loc', cfg.loc); LS.del('token')
  $('f-go').disabled = true; $('err').textContent = ''
  goFull()                                                                                 // the tap is the user gesture browsers require for fullscreen and wake lock
  try { await register(); $('setup').style.display = 'none'; await start() }
  catch (err) { LS.del('id'); LS.del('regToken'); cfg.id = cfg.regToken = null; showSetup(err.message || String(err)) }
  finally { $('f-go').disabled = false }
}
window.__display = { get state() { return state }, get ident() { return !!ident }, verifyNow, syncNow: syncSafe, capture }   // read-only hooks for tests
boot()
