// Tasks / open loops: real CRUD against the entity store.
import { api } from '../api.js';
import { $, $$, esc, toast, formDialog, emptyState, errorBox, DONE } from '../ui.js';
import { taskRow } from './command.js';
import { openEntity } from '../detail.js';

const FIELDS = [
  { name: 'title', label: 'Title', placeholder: 'What needs doing?' },
  { name: 'project', label: 'Project', placeholder: 'Optional' },
  { name: 'priority', label: 'Priority', type: 'select', options: ['low', 'medium', 'high'] },
  { name: 'estimate', label: 'Estimate (min)', type: 'number' },
  { name: 'due', label: 'Due', placeholder: 'YYYY-MM-DD or Today' },
  { name: 'energy', label: 'Energy', type: 'select', options: ['light', 'deep'] },
];

export async function renderTasks(root, data, reload) {
  const tasks = (data.tasks || []).slice();
  const open = tasks.filter((t) => !DONE.has(t.status));
  const done = tasks.filter((t) => DONE.has(t.status));
  const groups = {};
  open.forEach((t) => { (groups[t.project || 'Inbox'] ||= []).push(t); });

  root.innerHTML = `<div class="card full">
    <div class="card-head"><div><h2>Open loops</h2>
      <span class="muted">${open.length} open · prioritized by strategic value, urgency and capacity</span></div>
      <button class="primary" data-new>＋ Add task</button></div>
    <div id="list">
      ${open.length ? Object.entries(groups).map(([project, items]) => `
        <div class="label" style="margin:14px 0 4px">${esc(project.toUpperCase())}</div>
        ${items.map(taskRow).join('')}`).join('') : emptyState('No open loops.', 'Capture something — your future self says thanks.')}
      ${done.length ? `<div class="label" style="margin:18px 0 4px">RECENTLY CLOSED (${done.length})</div>${done.slice(0, 5).map(taskRow).join('')}` : ''}
    </div></div>`;

  $('[data-new]', root).addEventListener('click', async () => {
    const values = await formDialog({ title: 'New task', eyebrow: 'CREATE', fields: FIELDS });
    if (!values) return;
    try {
      await api.createEntity('task', { status: 'open', ...values });
      toast('Task created and event logged');
      reload();
    } catch (err) { toast(err.message, 'error'); }
  });
}

export function bindTaskRowEvents(root, reload) {
  $$('[data-task-toggle]', root).forEach((b) => b.onclick = async (e) => {
    e.stopPropagation();
    const id = b.dataset.taskToggle;
    const row = b.closest('.task');
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
