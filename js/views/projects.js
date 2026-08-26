// Projects: portfolio workbench — status slices, angular cards, explained health.
import { api } from '../api.js';
import { $, $$, esc, title, toast, formDialog, emptyState, DONE } from '../ui.js';
import { taskRow } from './command.js';
import { openEntity } from '../detail.js';

const NEW_PROJECT_FIELDS = [
  { name: 'name', label: 'Name', placeholder: 'What is this project?' },
  { name: 'description', label: 'Description', type: 'textarea' },
  { name: 'vision', label: 'Vision — what does done look like?', type: 'textarea' },
  { name: 'next_action', label: 'Next concrete action', placeholder: 'The smallest real step' },
  { name: 'status', label: 'Status', type: 'select', options: ['active', 'at-risk', 'paused', 'done'] },
  { name: 'deadline', label: 'Target date (YYYY-MM-DD)' },
  { name: 'area', label: 'Life area', placeholder: 'work / home / health …' },
  { name: 'tags', label: 'Tags (comma separated)', list: true },
];

const FILTERS = ['all', 'active', 'at-risk', 'paused', 'done'];

function healthEdge(h) {
  return h.status === 'at-risk' ? 'var(--red)' : h.status === 'watch' ? 'var(--amber)' : 'var(--ink)';
}

function projectCard(p) {
  const h = p.health || {};
  const progress = h.progress ?? p.progress ?? 0;
  return `<article class="entity" style="border-left:3px solid ${healthEdge(h)};cursor:pointer" data-open="${esc(p.id)}">
    <div class="entity-top"><div style="min-width:0"><h3>${esc(title(p))}</h3>
      <span class="muted">${esc(p.area ? p.area + ' · ' : '')}${esc(p.description || '')}</span></div>
      <span class="pill ${h.status === 'at-risk' ? 'red' : h.status === 'watch' || p.status === 'paused' ? 'amber' : p.status === 'done' ? 'grey' : ''}">${esc(p.status || '—')}</span></div>
    <div class="bar-row" style="margin:10px 0 6px"><div class="bar-label"><span>progress</span><b>${progress}%</b></div>
      <div class="bar ${h.status === 'at-risk' ? 'red' : ''}"><i style="width:${progress}%"></i></div></div>
    <p class="mono tiny muted" style="margin:2px 0">
      health ${h.score ?? '—'}/100 · ${h.open_tasks ?? 0} open / ${h.done_tasks ?? 0} done · momentum ${h.momentum ?? '—'}</p>
    <p class="muted" style="margin:4px 0 0">next: <b style="color:var(--ink);font-weight:500">${esc(p.next_action || '— not defined —')}</b></p>
    <p class="reasoning" style="margin:6px 0 0">${esc(h.explanation || '')}</p>
  </article>`;
}

export async function renderProjects(root, data, reload) {
  const projects = (data.projects || []).slice();
  const constitution = data.constitution || {};
  const limit = constitution.active_project_limit;
  let filter = 'all';

  const draw = () => {
    const list = filter === 'all' ? projects : projects.filter((p) => p.status === filter);
    const counts = Object.fromEntries(FILTERS.map((f) => [f,
      f === 'all' ? projects.length : projects.filter((p) => p.status === f).length]));

    root.innerHTML = `<div class="card full">
      <div class="card-head"><div><span class="label">PORTFOLIO</span>
        <h2 style="margin-top:4px">${counts.active} active${limit ? ` of ${limit} allowed` : ''} · health is explained, not colored</h2></div>
        <button class="primary" data-new>+ New project</button></div>

      <div class="stat-grid" style="margin-bottom:14px">
        ${['active', 'at-risk', 'paused', 'done'].map((s) => `
          <div class="stat"><b>${counts[s]}</b><span>${s}</span></div>`).join('')}
      </div>

      <div class="toolbar">
        <div class="filters" role="tablist" aria-label="Project filter">
          ${FILTERS.map((f) => `<button role="tab" data-filter="${f}" class="${f === filter ? 'active' : ''}">${f}</button>`).join('')}
        </div>
      </div>

      <div class="view-list" style="gap:10px">
        ${list.length ? list.map(projectCard).join('')
          : emptyState('No projects here.', 'Projects give your tasks a reason to exist.')}
      </div>
    </div>`;

    $$('[data-filter]', root).forEach((b) => b.addEventListener('click', () => { filter = b.dataset.filter; draw(); }));

    $('[data-new]', root).addEventListener('click', async () => {
      const values = await formDialog({ title: 'New project', eyebrow: 'CREATE PROJECT', fields: NEW_PROJECT_FIELDS, submitLabel: 'Create project' });
      if (!values) return;
      try {
        await api.createEntity('project', values);
        toast('Project created and linked to your graph');
        reload();
      } catch (err) { toast(err.message, 'error'); }
    });
    $$('[data-open]', root).forEach((n) => n.addEventListener('click', () =>
      openEntity(n.dataset.open, { onChange: reload })));
  };

  draw();
}
