'use strict';

const expandedSeries = new Set();
let pendingPollInterval = null;
const refreshingSeries = new Map(); // id → last_scraped_at snapshot

// --- API helpers ---

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

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatScraped(iso) {
  if (!iso) return 'never';
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString();
}

function coverThumb(url, title, size) {
  if (!url) return '';
  const src = escHtml(url.replace(/_SL\d+_/, `_SL${size}_`));
  return `<img class="cover-thumb" src="${src}" alt="${escHtml(title || '')}" loading="lazy">`;
}

function renderBooks(books, containerEl) {
  if (!books.length) {
    containerEl.innerHTML = '<p class="empty-state">No books found.</p>';
    return;
  }
  const rows = books.map(b => `
    <tr>
      <td class="col-cover">${coverThumb(b.cover_image_url, b.title, 80)}</td>
      <td>${b.book_url ? `<a href="${escHtml(b.book_url)}" target="_blank" rel="noopener noreferrer">${escHtml(b.title || '—')}</a>` : escHtml(b.title || '—')}</td>
      <td>${escHtml(b.author || '—')}</td>
      <td class="col-narrator">${escHtml(b.narrator || '—')}</td>
      <td class="col-duration">${escHtml(b.duration || '—')}</td>
      <td>${formatDate(b.release_date)}</td>
      <td class="col-language">${escHtml(b.language || '—')}</td>
    </tr>`).join('');
  containerEl.innerHTML = `
    <table>
      <thead>
        <tr>
          <th class="col-cover"></th>
          <th>Title</th><th>Author</th><th class="col-narrator">Narrator</th>
          <th class="col-duration">Duration</th><th>Release date</th><th class="col-language">Language</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function startPendingPoll() {
  if (pendingPollInterval) return;
  pendingPollInterval = setInterval(() => loadSeries(true), 3000);
}

function stopPendingPoll() {
  if (!pendingPollInterval) return;
  clearInterval(pendingPollInterval);
  pendingPollInterval = null;
}

function buildCoverStack(covers) {
  if (!covers || !covers.length) return '';
  const imgs = covers.map((url, i) => {
    const src = escHtml(url.replace(/_SL\d+_/, '_SL80_'));
    return `<img class="stack-thumb" src="${src}" alt="" loading="lazy" style="z-index:${covers.length - i}">`;
  }).join('');
  return `<div class="cover-stack" data-covers="${escHtml(covers.join('|'))}">${imgs}</div>`;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderSeries(seriesList) {
  const container = document.getElementById('series-container');
  if (!seriesList.length) {
    container.innerHTML = '<p style="color:#888;font-size:.9rem">No series tracked yet.</p>';
    stopPendingPoll();
    return;
  }
  container.innerHTML = seriesList.map(s => {
    const titleClass = s.title ? '' : ' pending';
    const displayTitle = escHtml(s.title || 'Scraping…');
    const bookCount = s.book_count ?? 0;
    const isOpen = expandedSeries.has(s.id) ? ' open' : '';
    return `
      <div class="series-card" data-series-id="${s.id}">
        <div class="series-header" data-action="toggle">
          ${buildCoverStack(s.cover_images || [])}
          <div class="series-title-wrap">
            <span class="series-title${titleClass}">${displayTitle}</span>
            <span class="series-meta" data-scraped-at="${s.last_scraped_at || ''}">${bookCount} book${bookCount !== 1 ? 's' : ''} · scraped ${formatScraped(s.last_scraped_at)}</span>
          </div>
          <button data-action="refresh" title="Refresh">↻</button>
          <button class="danger" data-action="delete" title="Untrack">✕</button>
        </div>
        <div class="books-container${isOpen}" data-books-loaded="${isOpen ? 'true' : 'false'}"></div>
      </div>`;
  }).join('');

  // Restore expanded state
  for (const id of expandedSeries) {
    const card = container.querySelector(`[data-series-id="${id}"]`);
    if (card) {
      const booksEl = card.querySelector('.books-container');
      if (booksEl && booksEl.dataset.booksLoaded !== 'true') {
        loadBooks(id, booksEl);
      }
    }
  }

  // Detect completed refreshes: timestamp changed → reload books if expanded
  for (const s of seriesList) {
    if (refreshingSeries.has(s.id) && s.last_scraped_at !== refreshingSeries.get(s.id)) {
      refreshingSeries.delete(s.id);
      const card = container.querySelector(`[data-series-id="${s.id}"]`);
      if (card && expandedSeries.has(s.id)) {
        const booksEl = card.querySelector('.books-container');
        if (booksEl) loadBooks(s.id, booksEl);
      }
    }
  }

  if (seriesList.some(s => !s.title) || refreshingSeries.size > 0) {
    startPendingPoll();
  } else {
    stopPendingPoll();
  }
}

// --- Actions ---

function patchSeries(seriesList) {
  const container = document.getElementById('series-container');

  // If the set of series ids changed, fall back to a full re-render
  const existingIds = new Set(
    [...container.querySelectorAll('[data-series-id]')]
      .map(el => parseInt(el.dataset.seriesId, 10))
  );
  const newIds = new Set(seriesList.map(s => s.id));
  const structureChanged =
    seriesList.some(s => !existingIds.has(s.id)) ||
    [...existingIds].some(id => !newIds.has(id));

  if (structureChanged) {
    renderSeries(seriesList);
    return;
  }

  // Snapshot which series are currently pending before we update the DOM
  const pendingBefore = new Set(
    [...container.querySelectorAll('.series-title.pending')]
      .map(el => parseInt(el.closest('[data-series-id]').dataset.seriesId, 10))
  );

  // Update only the mutable text/metadata; never touch .books-container
  for (const s of seriesList) {
    const card = container.querySelector(`[data-series-id="${s.id}"]`);
    if (!card) continue;

    const titleEl = card.querySelector('.series-title');
    if (titleEl) {
      titleEl.textContent = s.title || 'Scraping…';
      titleEl.classList.toggle('pending', !s.title);
    }

    const newCovers = (s.cover_images || []).join('|');
    const stackEl = card.querySelector('.cover-stack');
    if (stackEl && stackEl.dataset.covers !== newCovers) {
      stackEl.outerHTML = buildCoverStack(s.cover_images || []);
    } else if (!stackEl && newCovers) {
      card.querySelector('.series-header').insertAdjacentHTML('afterbegin', buildCoverStack(s.cover_images || []));
    }

    const metaEl = card.querySelector('.series-meta');
    if (metaEl) {
      const n = s.book_count ?? 0;
      metaEl.textContent = `${n} book${n !== 1 ? 's' : ''} · scraped ${formatScraped(s.last_scraped_at)}`;
      metaEl.dataset.scrapedAt = s.last_scraped_at || '';
    }
  }

  // If any previously-pending series just acquired a title, refresh upcoming
  if (seriesList.some(s => pendingBefore.has(s.id) && s.title)) {
    loadUpcoming();
  }

  // Detect completed refreshes: reload books for open cards whose timestamp changed
  for (const s of seriesList) {
    if (refreshingSeries.has(s.id) && s.last_scraped_at !== refreshingSeries.get(s.id)) {
      refreshingSeries.delete(s.id);
      loadUpcoming();
      if (expandedSeries.has(s.id)) {
        const card = container.querySelector(`[data-series-id="${s.id}"]`);
        if (card) loadBooks(s.id, card.querySelector('.books-container'));
      }
    }
  }

  if (seriesList.some(s => !s.title) || refreshingSeries.size > 0) {
    startPendingPoll();
  } else {
    stopPendingPoll();
  }
}

async function loadUpcoming() {
  const data = await apiFetch('/api/upcoming');
  const section = document.getElementById('upcoming-section');
  const list = document.getElementById('upcoming-list');
  if (!data.length) {
    section.style.display = 'none';
    return;
  }
  list.innerHTML = data.map(b => `
    <li>
      ${coverThumb(b.cover_image_url, b.title, 160)}
      <div class="upcoming-text">
        <span class="upcoming-date">${formatDate(b.release_date)}</span>
        ${b.book_url ? `<a href="${escHtml(b.book_url)}" target="_blank" rel="noopener noreferrer">${escHtml(b.title)}</a>` : escHtml(b.title)}
        <span class="upcoming-series">— ${escHtml(b.series_title)}</span>
      </div>
    </li>`).join('');
  section.style.display = '';
}

async function loadSeries(patch = false) {
  if (!patch) document.getElementById('loading').style.display = '';
  try {
    const data = await apiFetch('/api/series');
    if (patch) {
      patchSeries(data);
    } else {
      renderSeries(data);
    }
  } finally {
    if (!patch) document.getElementById('loading').style.display = 'none';
  }
}

async function loadBooks(seriesId, containerEl) {
  containerEl.innerHTML = '<p class="empty-state">Loading…</p>';
  const books = await apiFetch(`/api/series/${seriesId}/books`);
  renderBooks(books, containerEl);
  containerEl.dataset.booksLoaded = 'true';
}

async function toggleBooks(seriesId, containerEl) {
  if (expandedSeries.has(seriesId)) {
    expandedSeries.delete(seriesId);
    containerEl.classList.remove('open');
  } else {
    expandedSeries.add(seriesId);
    containerEl.classList.add('open');
    if (containerEl.dataset.booksLoaded !== 'true') {
      await loadBooks(seriesId, containerEl);
    }
  }
}

async function deleteSeries(seriesId) {
  if (!confirm('Stop tracking this series?')) return;
  await apiFetch(`/api/series/${seriesId}`, { method: 'DELETE' });
  expandedSeries.delete(seriesId);
  await Promise.all([loadSeries(), loadUpcoming()]);
}

async function refreshSeries(btn, seriesId) {
  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = '…';
  try {
    const card = document.querySelector(`[data-series-id="${seriesId}"]`);
    const snapshot = card?.querySelector('.series-meta')?.dataset.scrapedAt ?? null;
    refreshingSeries.set(seriesId, snapshot);
    await apiFetch(`/api/series/${seriesId}/refresh`, { method: 'POST' });
    startPendingPoll();
  } catch (err) {
    refreshingSeries.delete(seriesId);
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

// --- Form ---

document.getElementById('add-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById('add-error');
  const input = document.getElementById('url-input');
  const btn = e.target.querySelector('button[type="submit"]');
  errorEl.textContent = '';
  if (!input.value.includes('audible.') || !input.value.includes('/series/')) {
    errorEl.textContent = 'Please enter an Audible series URL';
    return;
  }
  btn.disabled = true;
  try {
    await apiFetch('/api/series', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: input.value.trim() }),
    });
    input.value = '';
    await Promise.all([loadSeries(), loadUpcoming()]);
  } catch (err) {
    errorEl.textContent = err.status === 409 ? 'This series is already being tracked.' : (err.message || 'Something went wrong.');
  } finally {
    btn.disabled = false;
  }
});

// --- Event delegation ---

document.getElementById('series-container').addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;

  const card = btn.closest('[data-series-id]');
  if (!card) return;
  const seriesId = parseInt(card.dataset.seriesId, 10);
  const action = btn.dataset.action;

  if (action === 'delete') {
    e.stopPropagation();
    await deleteSeries(seriesId);
  } else if (action === 'refresh') {
    e.stopPropagation();
    await refreshSeries(btn, seriesId);
  } else if (action === 'toggle') {
    const booksEl = card.querySelector('.books-container');
    await toggleBooks(seriesId, booksEl);
  }
});

// --- Init ---

loadSeries();
loadUpcoming();
