// Tasks: one calm workbench — quick add, filters, tag/project slicing, bulk close.
import { api } from '../api.js';
import { $, $$, esc, toast, formDialog, emptyState, DONE } from '../ui.js';
import { taskRow, parseQuickAdd } from './command.js';
import { openEntity } from '../detail.js';

const NEW_TASK_FIELDS = [
  { name: 'title', label: 'Title', placeholder: 'What needs doing?' },
  { name: 'project', label: 'Project', placeholder: 'Optional' },
  { name: 'priority', label: 'Priority', type: 'select', options: ['low', 'medium', 'high', 'urgent'] },
  { name: 'due', label: 'Due (YYYY-MM-DD)', placeholder: 'e.g. 2026-09-01' },
  { name: 'start', label: 'Start (YYYY-MM-DD)' },
  { name: 'estimate', label: 'Estimate (min)', type: 'number' },
  { name: 'energy', label: 'Energy', type: 'select', options: ['light', 'deep'] },
  { name: 'recurrence', label: 'Repeat', placeholder: 'daily / weekly on Mon — optional' },
  { name: 'notes', label: 'Notes', type: 'textarea' },
  { name: 'tags', label: 'Tags (comma separated)', list: true },
];

const FILTERS = [
  { id: 'open', label: 'Open' },
  { id: 'today', label: 'Today' },
  { id: 'overdue', label: 'Overdue' },
  { id: 'done', label: 'Done' },
];

function matchFilter(t, filter) {
  if (filter === 'open') return !DONE.has(t.status);
  if (filter === 'done') return DONE.has(t.status);
  if (DONE.has(t.status)) return false;
  const due = String(t.due || '').slice(0, 10);
  const today = new Date().toISOString().slice(0, 10);
  if (filter === 'today') return due === today || String(t.due || '').toLowerCase() === 'today';
  if (filter === 'overdue') return /^\d{4}-\d{2}-\d{2}/.test(due) && due < today;
  return true;
}

export async function renderTasks(root, data, reload) {
  const all = (data.tasks || []).slice();
  let filter = 'open';
  let project = '';
  let tag = '';

  const projects = [...new Set(all.map((t) => t.project).filter(Boolean))].sort();
  const tags = [...new Set(all.flatMap((t) => t.tags || []))].sort();

  const draw = () => {
    let list = all.filter((t) => matchFilter(t, filter));
    if (project) list = list.filter((t) => t.project === project);
    if (tag) list = list.filter((t) => (t.tags || []).includes(tag));

    const groups = {};
    list.forEach((t) => { (groups[t.project || 'Inbox'] ||= []).push(t); });
    const doneCount = all.filter((t) => DONE.has(t.status)).length;

    root.innerHTML = `<div class="card full">
      <div class="card-head"><div><span class="label">OPEN LOOPS</span>
        <h2 style="margin-top:4px">${list.length} shown · ${all.filter((t) => !DONE.has(t.status)).length} open total</h2></div>
        <div style="display:flex;gap:8px">
          ${filter === 'done' && doneCount ? '<button class="secondary" data-clear-done>Clear done</button>' : ''}
          <button class="primary" data-new>+ Add task</button>
        </div></div>

      <div class="quickadd">
        <input id="taskQuick" placeholder="Quick add task…  #tag  +Project  !high priority  ⏎" aria-label="Quick add task">
        <button class="primary" id="taskQuickGo">Add</button>
      </div>

      <div class="toolbar">
        <div class="filters" role="tablist" aria-label="Task filter">
          ${FILTERS.map((f) => `<button role="tab" data-filter="${f.id}" class="${f.id === filter ? 'active' : ''}">${f.label}</button>`).join('')}
        </div>
        <select class="select" id="projectFilter" aria-label="Filter by project">
          <option value="">all projects</option>
          ${projects.map((p) => `<option value="${esc(p)}" ${p === project ? 'selected' : ''}>${esc(p)}</option>`).join('')}
        </select>
        ${tags.length ? `<select class="select" id="tagFilter" aria-label="Filter by tag">
          <option value="">all tags</option>
          ${tags.map((tg) => `<option value="${esc(tg)}" ${tg === tag ? 'selected' : ''}>#${esc(tg)}</option>`).join('')}
        </select>` : ''}
      </div>

      <div id="list">
        ${list.length ? Object.entries(groups).map(([g, items]) => `
          <div class="label" style="margin:14px 0 2px">${esc(g.toUpperCase())} · ${items.length}</div>
          ${items.map(taskRow).join('')}`).join('')
        : emptyState(filter === 'open' ? 'No open loops.' : 'Nothing matches this filter.',
            'Capture something — your future self says thanks.')}
      </div>
    </div>`;

    // quick add with !priority syntax
    const quick = async () => {
      const input = $('#taskQuick', root);
      let raw = input.value.trim();
      if (!raw) return;
      let priority;
      raw = raw.replace(/(^|\s)!(urgent|high|medium|low)\b/gi, (_, sp, p) => { priority = p.toLowerCase(); return sp; }).trim();
      const { text, extra } = parseQuickAdd(raw);
      if (!text) return;
      try {
        await api.createEntity('task', { status: 'open', title: text,
          ...(priority ? { priority } : {}), ...extra });
        toast('Task created — event logged');
        reload();
      } catch (err) { toast(err.message, 'error'); }
    };
    $('#taskQuickGo', root)?.addEventListener('click', quick);
    $('#taskQuick', root)?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); quick(); }
    });

    $$('[data-filter]', root).forEach((b) => b.addEventListener('click', () => { filter = b.dataset.filter; draw(); }));
    $('#projectFilter', root)?.addEventListener('change', (e) => { project = e.target.value; draw(); });
    $('#tagFilter', root)?.addEventListener('change', (e) => { tag = e.target.value; draw(); });

    $('[data-new]', root)?.addEventListener('click', async () => {
      const values = await formDialog({ title: 'New task', eyebrow: 'CREATE TASK', fields: NEW_TASK_FIELDS, submitLabel: 'Create task' });
      if (!values) return;
      try {
        await api.createEntity('task', { status: 'open', ...values });
        toast('Task created — every field stored, event logged');
        reload();
      } catch (err) { toast(err.message, 'error'); }
    });

    $('[data-clear-done]', root)?.addEventListener('click', async () => {
      const doneIds = all.filter((t) => DONE.has(t.status)).map((t) => t.id);
      const yes = confirm(`Archive ${doneIds.length} completed tasks? (soft delete, event-sourced, recoverable from audit)`);
      if (!yes) return;
      try {
        await api.post('/api/core/entities/bulk', { action: 'delete', ids: doneIds, confirm: true });
        toast(`${doneIds.length} closed tasks cleared`);
        reload();
      } catch (err) { toast(err.message, 'error'); }
    });
  };

  draw();
}

// Row-level actions (task toggles, open drawer) — delegated by the app shell.
export function bindTaskRowEvents(root, reload) {
  $$('[data-task-toggle]', root).forEach((b) => b.onclick = async (e) => {
    e.stopPropagation();
    const id = b.dataset.taskToggle;
    const nowDone = !b.classList.contains('done');
    try {
      await api.updateEntity(id, { status: nowDone ? 'done' : 'open' });
      toast(nowDone ? 'Completed — event emitted, memory updated' : 'Reopened');
      reload();
    } catch (err) { toast(err.message, 'error'); }
  });
  $$('[data-open]', root).forEach((b) => b.onclick = (e) => {
    e.stopPropagation();
    openEntity(b.dataset.open, { onChange: reload });
  });
}
