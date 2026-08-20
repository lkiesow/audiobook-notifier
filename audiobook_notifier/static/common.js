'use strict';

// Helpers shared by every page. Loaded before the page's own script.

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
