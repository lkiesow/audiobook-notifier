'use strict';

const expandedSeries = new Set();

// --- API helpers ---

async function apiFetch(path, options = {}) {
  const res = await fetch(path, options);
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

function renderBooks(books, containerEl) {
  if (!books.length) {
    containerEl.innerHTML = '<p class="empty-state">No books found.</p>';
    return;
  }
  const rows = books.map(b => `
    <tr>
      <td>${escHtml(b.title || '—')}</td>
      <td>${escHtml(b.author || '—')}</td>
      <td>${escHtml(b.narrator || '—')}</td>
      <td>${escHtml(b.duration || '—')}</td>
      <td>${formatDate(b.release_date)}</td>
      <td>${escHtml(b.language || '—')}</td>
    </tr>`).join('');
  containerEl.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Title</th><th>Author</th><th>Narrator</th>
          <th>Duration</th><th>Release date</th><th>Language</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
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
          <span class="series-title${titleClass}">${displayTitle}</span>
          <span class="series-meta">${bookCount} book${bookCount !== 1 ? 's' : ''} · scraped ${formatScraped(s.last_scraped_at)}</span>
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
}

// --- Actions ---

async function loadSeries() {
  document.getElementById('loading').style.display = '';
  try {
    const data = await apiFetch('/api/series');
    renderSeries(data);
  } finally {
    document.getElementById('loading').style.display = 'none';
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
  await loadSeries();
}

async function refreshSeries(btn, seriesId) {
  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = '…';
  try {
    await apiFetch(`/api/series/${seriesId}/refresh`, { method: 'POST' });
    // Reload books if expanded
    const card = document.querySelector(`[data-series-id="${seriesId}"]`);
    if (card) {
      const booksEl = card.querySelector('.books-container');
      if (booksEl && expandedSeries.has(seriesId)) {
        booksEl.dataset.booksLoaded = 'false';
        await loadBooks(seriesId, booksEl);
      }
    }
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
    await loadSeries();
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
