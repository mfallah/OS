// Shared UI primitives: small, composable, reused by every view.
export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];

export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function el(html) {
  const tpl = document.createElement('template');
  tpl.innerHTML = html.trim();
  return tpl.content.firstElementChild;
}

let toastTimer;
export function toast(message, kind = 'ok') {
  const t = $('#toast');
  if (!t) return;
  t.textContent = message;
  t.style.background = kind === 'error' ? 'var(--red)' : '';
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2600);
}

export function emptyState(text, hint = '') {
  return `<div class="empty"><div>${esc(text)}</div>${hint ? `<small class="muted">${esc(hint)}</small>` : ''}</div>`;
}

export function errorBox(error) {
  return `<div class="error-box"><b>Something went wrong.</b> ${esc(error.message || error)}
    ${error.setup ? `<small class="muted">Setup: ${esc(error.setup)}</small>` : ''}</div>`;
}

export function pill(text, cls = '') {
  return text ? `<span class="pill ${cls}">${esc(text)}</span>` : '';
}

export function badgeForStatus(status) {
  const s = String(status || '');
  if (['at-risk', 'blocked', 'overdue'].includes(s)) return pill(s, 'red');
  if (['watch', 'pending', 'open'].includes(s)) return pill(s, 'amber');
  if (['archived', 'disabled', 'draft'].includes(s)) return pill(s, 'grey');
  return pill(s);
}

// Generic confirm dialog — destructives never happen silently.
export function confirmDialog({ title, body, confirmLabel = 'Confirm', danger = false }) {
  return new Promise((resolve) => {
    const host = $('#detailModal'); const card = $('#detailCard');
    card.innerHTML = `
      <button class="close" data-x aria-label="Close">×</button>
      <div class="eyebrow">${danger ? 'DESTRUCTIVE ACTION' : 'PLEASE CONFIRM'}</div>
      <h2>${esc(title)}</h2><p class="muted">${esc(body)}</p>
      <div style="display:flex;gap:8px;margin-top:18px;flex-wrap:wrap">
        <button class="${danger ? 'danger' : 'primary'}" data-yes>${esc(confirmLabel)}</button>
        <button class="secondary" data-x>Cancel</button>
      </div>`;
    host.classList.remove('hidden');
    const done = (value) => { host.classList.add('hidden'); resolve(value); };
    $$('[data-x]', card).forEach((b) => b.addEventListener('click', () => done(false)));
    $('[data-yes]', card).addEventListener('click', () => done(true));
  });
}

// Schema-driven mini form inside the shared detail modal.
export function formDialog({ title, eyebrow, fields, values = {}, submitLabel = 'Save' }) {
  return new Promise((resolve) => {
    const host = $('#detailModal'); const card = $('#detailCard');
    const fieldHtml = fields.map((f) => {
      const v = values[f.name] ?? f.value ?? '';
      if (f.type === 'textarea') {
        return `<div class="field"><label for="f_${f.name}">${esc(f.label)}</label>
          <textarea id="f_${f.name}" name="${f.name}" placeholder="${esc(f.placeholder || '')}">${esc(v)}</textarea></div>`;
      }
      if (f.type === 'select') {
        const opts = f.options.map((o) => `<option value="${esc(o)}" ${o === v ? 'selected' : ''}>${esc(o)}</option>`).join('');
        return `<div class="field"><label for="f_${f.name}">${esc(f.label)}</label>
          <select id="f_${f.name}" name="${f.name}">${opts}</select></div>`;
      }
      return `<div class="field"><label for="f_${f.name}">${esc(f.label)}</label>
        <input id="f_${f.name}" name="${f.name}" type="${f.type || 'text'}" value="${esc(v)}" placeholder="${esc(f.placeholder || '')}"></div>`;
    }).join('');
    card.innerHTML = `
      <button class="close" data-x aria-label="Close">×</button>
      <div class="eyebrow">${esc(eyebrow || 'EDIT')}</div><h2>${esc(title)}</h2>
      <form id="miniForm" novalidate>${fieldHtml}
        <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
          <button class="primary" type="submit">${esc(submitLabel)}</button>
          <button class="secondary" type="button" data-x>Cancel</button>
        </div></form>`;
    host.classList.remove('hidden');
    const done = (value) => { host.classList.add('hidden'); resolve(value); };
    $$('[data-x]', card).forEach((b) => b.addEventListener('click', () => done(null)));
    $('#miniForm', card).addEventListener('submit', (e) => {
      e.preventDefault();
      const data = {};
      fields.forEach((f) => {
        const node = $(`#f_${f.name}`, card);
        let value = node.value;
        if (f.type === 'number') value = Number(value);
        if (f.list) value = value.split(',').map((x) => x.trim()).filter(Boolean);
        if (value !== '' && value != null) data[f.name] = value;
      });
      done(data);
    });
  });
}

export function title(entity) {
  return entity?.title || entity?.name || entity?.question || '(untitled)';
}

export function relTime(isoString) {
  if (!isoString) return '';
  const diff = Date.now() - Date.parse(isoString);
  if (Number.isNaN(diff)) return String(isoString);
  const mins = Math.round(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? 'yesterday' : `${days}d ago`;
}

export function dueLabel(task) {
  const due = String(task.due || '');
  if (!due) return '';
  const today = new Date().toISOString().slice(0, 10);
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  if (due.slice(0, 10) === today) return 'Today';
  if (due.slice(0, 10) === tomorrow) return 'Tomorrow';
  if (/^\d{4}-\d{2}-\d{2}/.test(due) && due.slice(0, 10) < today) return 'Overdue';
  return due;
}

export const DONE = new Set(['done', 'completed', 'archived', 'cancelled']);
