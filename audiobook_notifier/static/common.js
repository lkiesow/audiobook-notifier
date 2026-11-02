'use strict';

// Helpers shared by every page. Loaded before the page's own script.

// --- PWA ---

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js');
}

// An installed app can sit in memory for days. Reload when it comes back
// after a while so it does not show stale data.
const STALE_AFTER_MS = 10 * 60 * 1000;
let hiddenSince = null;
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    hiddenSince = Date.now();
  } else if (hiddenSince && Date.now() - hiddenSince > STALE_AFTER_MS) {
    location.reload();
  }
});

// --- Push notifications ---

// Only rendered when the server has VAPID keys. Stays hidden in browsers
// without push support, which includes iOS Safari outside the installed app.
const pushButton = document.getElementById('push-toggle');

const PUSH_TITLES = {
  on: 'Notifications are on for this device. Click to turn them off.',
  off: 'Get notifications on this device',
  blocked: 'Notifications are blocked in this browser\'s settings',
};

function setPushState(state) {
  pushButton.hidden = false;
  pushButton.dataset.state = state;
  pushButton.disabled = state === 'blocked';
  pushButton.title = PUSH_TITLES[state];
  pushButton.setAttribute('aria-label', PUSH_TITLES[state]);
  pushButton.setAttribute('aria-pressed', String(state === 'on'));
}

function base64UrlToBytes(b64) {
  const raw = atob(b64.replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(raw, c => c.charCodeAt(0));
}

function sameKey(buffer, b64) {
  const a = new Uint8Array(buffer);
  const b = base64UrlToBytes(b64);
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

function saveSubscription(subscription) {
  return apiFetch('/api/push/subscriptions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(subscription),
  });
}

async function initPush() {
  if (!pushButton || !('serviceWorker' in navigator) || !('PushManager' in window)) return;
  if (Notification.permission === 'denied') { setPushState('blocked'); return; }

  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  setPushState(subscription && Notification.permission === 'granted' ? 'on' : 'off');
  if (!subscription) return;

  // Re-send the subscription so the server catches up after losing it, and
  // drop it if the server's key changed: a subscription is bound to the key.
  try {
    const { publicKey } = await apiFetch('/api/push/key');
    if (sameKey(subscription.options.applicationServerKey, publicKey)) {
      await saveSubscription(subscription);
    } else {
      await subscription.unsubscribe();
      setPushState('off');
    }
  } catch (err) {
    console.warn('Could not sync push subscription', err);
  }
}

async function enablePush() {
  // Ask first: some browsers only allow the prompt directly in a click.
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') {
    setPushState(permission === 'denied' ? 'blocked' : 'off');
    return;
  }
  const { publicKey } = await apiFetch('/api/push/key');
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: base64UrlToBytes(publicKey),
  });
  await saveSubscription(subscription);
  setPushState('on');
}

async function disablePush() {
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  if (subscription) {
    await apiFetch('/api/push/subscriptions', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: subscription.endpoint }),
    });
    await subscription.unsubscribe();
  }
  setPushState('off');
}

pushButton?.addEventListener('click', async () => {
  const wasOn = pushButton.dataset.state === 'on';
  pushButton.disabled = true;
  try {
    await (wasOn ? disablePush() : enablePush());
  } catch (err) {
    console.error('Changing push notifications failed', err);
    pushButton.title = `Could not turn notifications ${wasOn ? 'off' : 'on'}: ${err.message}`;
  } finally {
    pushButton.disabled = pushButton.dataset.state === 'blocked';
  }
});

// Browsers can expose PushManager without a working push service (some
// privacy settings, automated browsers). The bell then just stays hidden.
initPush().catch(err => console.warn('Push notifications unavailable', err));

// --- API ---

async function apiFetch(path, options = {}) {
  const res = await fetch(path, options);
  if (res.status === 401) { window.location.href = '/login'; return; }
  if (res.status === 204) return null;
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw Object.assign(new Error(data?.error || res.statusText), { status: res.status });
  return data;
}

// --- Render ---

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function coverThumb(url, title, size) {
  if (!url) return '';
  const src = escHtml(url.replace(/_SL\d+_/, `_SL${size}_`));
  return `<img class="cover-thumb" src="${src}" alt="${escHtml(title || '')}" loading="lazy">`;
}

// One row shape for every book list — Out today, Upcoming and the Backlog.
// Title, author and series are separated by "·" on desktop and stack onto
// their own lines without it on narrow screens; both are CSS, see .book-line.
function bookRow(b, { showDate = true } = {}) {
  const title = escHtml(b.title || '—');
  return `
    <li>
      ${coverThumb(b.cover_image_url, b.title, 160)}
      <div class="book-info">
        ${showDate ? `<span class="book-date">${formatDate(b.release_date)}</span>` : ''}
        <div class="book-line">
          <span class="book-title">${b.book_url ? `<a href="${escHtml(b.book_url)}" target="_blank" rel="noopener noreferrer">${title}</a>` : title}</span>
          ${b.author ? `<span class="book-author">${escHtml(b.author)}</span>` : ''}
          <span class="book-series">${escHtml(b.series_title || '')}</span>
        </div>
      </div>
    </li>`;
}
