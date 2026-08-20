'use strict';

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
    // Back to the overview, where the new card shows up as "Scraping…"
    window.location.href = '/';
  } catch (err) {
    errorEl.textContent = err.status === 409 ? 'This series is already being tracked.' : (err.message || 'Something went wrong.');
    btn.disabled = false;
  }
});
