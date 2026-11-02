'use strict';

// Network first for every same-origin GET; the cache only answers when the
// network is unreachable, so the installed app shows the last-known data
// offline. Because fresh responses always win, there is no precache list and
// no version to bump on release.

const CACHE = 'audiobook-notifier';

// Auth flows and the service worker itself must always hit the network.
const BYPASS = ['/login', '/logout', '/auth/', '/api/auth/', '/metrics', '/sw.js'];

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key !== CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  if (url.pathname === '/logout') {
    // Do not leave book data behind on a signed-out device.
    event.waitUntil(caches.delete(CACHE));
    return;
  }
  if (BYPASS.some(p => url.pathname.startsWith(p))) return;

  event.respondWith(networkFirst(event));
});

async function networkFirst(event) {
  const { request } = event;
  try {
    const response = await fetch(request);
    // A redirect or 401 means the session expired. Caching it would replace
    // the last good page with the login page.
    if (response.ok && !response.redirected && response.type === 'basic') {
      const copy = response.clone();
      event.waitUntil(caches.open(CACHE).then(cache => cache.put(request, copy)));
    }
    return response;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw err;
  }
}
