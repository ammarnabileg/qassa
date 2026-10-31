/* Offline shell for the back-office till (D-013): the app opens without internet. API responses are never cached. */
// Served from the build base (/_q/sw.js); its scope is the app root: / on the platform address, /dashboard/ on a salon's.
const CACHE = 'qassa-shell-v2'
const SHELL = new URL(self.registration.scope).pathname
const FILES = new URL('./', location.href).pathname   // /_q/
self.addEventListener('install', (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll([SHELL, FILES + 'icons/sprite.svg']))); self.skipWaiting() })
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()))
})
self.addEventListener('fetch', (e) => {
  const req = e.request
  const url = new URL(req.url)
  if (req.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return
  if (req.mode === 'navigate') {   // newest app when online, last one when not
    e.respondWith(fetch(req).then((r) => { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(SHELL, copy)); return r })
      .catch(() => caches.match(SHELL)))
    return
  }
  if (url.pathname.startsWith(FILES) && /^(assets|fonts|icons)\//.test(url.pathname.slice(FILES.length))) {   // fingerprinted files: cache first
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((r) => { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); return r })))
  }
})
