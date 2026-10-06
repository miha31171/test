const CACHE = 'dayflow-v1';
const ASSETS = ['/', '/static/app.css', '/static/app.js', '/static/icon.svg', '/manifest.json'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS))));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  event.respondWith(fetch(event.request).then(response => {
    const clone = response.clone();
    caches.open(CACHE).then(c => c.put(event.request, clone));
    return response;
  }).catch(() => caches.match(event.request)));
});
