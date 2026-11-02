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

// --- Push notifications ---

self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {};
  event.waitUntil(self.registration.showNotification(data.title || 'Audiobook Notifier', {
    body: data.body,
    // Same tag replaces an earlier notification, so a redelivery does not stack.
    tag: data.tag,
    icon: '/icon-192.png',
    data: { url: data.url || '/' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || '/', self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    const open = windows.find(w => new URL(w.url).origin === self.location.origin);
    if (open) return open.focus();
    return self.clients.openWindow(url);
  })());
});

// The push service may rotate a subscription. Re-subscribe with the same key
// and tell the server; it drops the old endpoint on the next 404/410.
self.addEventListener('pushsubscriptionchange', (event) => {
  const applicationServerKey = event.oldSubscription?.options.applicationServerKey;
  if (!applicationServerKey) return;
  event.waitUntil((async () => {
    const subscription = await self.registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey,
    });
    await fetch('/api/push/subscriptions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(subscription),
    });
  })());
});
