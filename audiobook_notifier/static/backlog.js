'use strict';

async function loadBacklog() {
  const loadingEl = document.getElementById('backlog-loading');
  const section = document.getElementById('backlog-section');
  const list = document.getElementById('backlog-list');
  const stats = document.getElementById('backlog-stats');

  const data = await apiFetch('/api/backlog');
  loadingEl.style.display = 'none';

  if (!data.length) {
    loadingEl.textContent = 'Nothing released yet.';
    loadingEl.style.display = '';
    return;
  }

  stats.textContent = `${data.length} book${data.length !== 1 ? 's' : ''}`;
  list.innerHTML = data.map(b => `
    <li>
      ${coverThumb(b.cover_image_url, b.title, 160)}
      <div class="upcoming-text">
        <span class="upcoming-date">${formatDate(b.release_date)}</span>
        ${b.book_url ? `<a href="${escHtml(b.book_url)}" target="_blank" rel="noopener noreferrer">${escHtml(b.title || '—')}</a>` : escHtml(b.title || '—')}
        ${b.author ? `<span class="backlog-author">${escHtml(b.author)}</span>` : ''}
        <span class="upcoming-series">— ${escHtml(b.series_title)}</span>
      </div>
    </li>`).join('');
  section.style.display = '';
}

loadBacklog();
