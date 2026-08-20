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
  list.innerHTML = data.map(b => bookRow(b)).join('');
  section.style.display = '';
}

loadBacklog();
