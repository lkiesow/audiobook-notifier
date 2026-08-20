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
