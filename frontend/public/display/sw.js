// Keeps the display page itself available offline (stale-while-revalidate). API calls and media are never handled here:
// media is stored by the app in IndexedDB after its hash has been checked.
const CACHE = 'gs-display-v2'
const SHELL = ['/display/', '/display/index.html', '/display/app.js', '/display/manifest.webmanifest', '/display/icon-192.png', '/display/icon-512.png']

self.addEventListener('install', (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())) })
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()))
})
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url)
  if (e.request.method !== 'GET' || url.origin !== location.origin || !url.pathname.startsWith('/display/')) return
  e.respondWith(caches.open(CACHE).then(async (cache) => {
    const hit = await cache.match(e.request, { ignoreSearch: true, ignoreVary: true })
    const refresh = fetch(e.request).then((res) => { if (res.ok) cache.put(e.request, res.clone()); return res }).catch(() => null)
    return hit || (await refresh) || new Response('Offline', { status: 503 })
  }))
})
