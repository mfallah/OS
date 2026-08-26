// Projects: portfolio view with explainable health + goal alignment.
import { api } from '../api.js';
import { $, $$, esc, title, pill, toast, formDialog, emptyState } from '../ui.js';
import { openEntity } from '../detail.js';

const FIELDS = [
  { name: 'name', label: 'Project name' },
  { name: 'description', label: 'Description', type: 'textarea' },
  { name: 'vision', label: 'Vision', placeholder: 'What does done look like?' },
  { name: 'next_action', label: 'Next concrete action' },
  { name: 'status', label: 'Status', type: 'select', options: ['active', 'at-risk', 'paused', 'done'] },
];

function healthBadge(h) {
  const cls = h.status === 'at-risk' ? 'red' : h.status === 'watch' ? 'amber' : '';
  return pill(`${h.status ?? '—'} · ${h.score ?? '—'}/100`, cls);
}

function projectCard(p) {
  const h = p.health || {};
  return `<article class="entity">
    <div class="entity-top"><div><h3>${esc(title(p))}</h3>
      <span class="muted">${esc(p.description || '')}</span></div>${healthBadge(h)}</div>
    <div class="bar-row"><div class="bar-label"><span>Progress</span><b>${h.progress ?? p.progress ?? 0}%</b></div>
      <div class="bar"><i style="width:${h.progress ?? p.progress ?? 0}%"></i></div></div>
    <div class="bar-row"><div class="bar-label"><span>Momentum</span><b>${h.momentum ?? '—'}/100</b></div>
      <div class="bar ${h.momentum < 40 ? 'amber' : ''}"><i style="width:${h.momentum || 0}%"></i></div></div>
    <div class="bar-row"><div class="bar-label"><span>Clarity</span><b>${h.clarity ?? '—'}/100</b></div>
      <div class="bar ${h.clarity < 50 ? 'amber' : ''}"><i style="width:${h.clarity || 0}%"></i></div></div>
    <p class="muted">Next action: <b>${esc(p.next_action || p.next || '— not defined —')}</b> · Risk ${h.risk ?? '—'}/100
      · ${h.open_tasks ?? 0} open / ${h.done_tasks ?? 0} done tasks</p>
    <p class="reasoning">Why this status: ${esc(h.explanation || 'no health data')}</p>
    ${h.suggestion ? `<p class="muted">→ Suggested: ${esc(h.suggestion)}</p>` : ''}
    <button class="secondary" data-open="${esc(p.id)}">Open project</button>
  </article>`;
}

export async function renderProjects(root, data, reload) {
  const projects = data.projects || [];
  const constitution = data.constitution || {};
  const limit = constitution.active_project_limit;
  root.innerHTML = `<div class="card full">
    <div class="card-head"><div><h2>Project portfolio</h2>
      <span class="muted">${projects.filter((p) => p.status === 'active').length} active${limit ? ` · constitution limit: ${limit}` : ''} · health is explained, not just colored</span></div>
      <button class="primary" data-new>＋ New project</button></div>
    <div class="view-list">
      ${projects.length ? projects.map(projectCard).join('') : emptyState('No projects yet.', 'Projects give your tasks a reason to exist.')}
    </div></div>`;
  $('[data-new]', root).addEventListener('click', async () => {
    const values = await formDialog({ title: 'New project', eyebrow: 'CREATE', fields: FIELDS });
    if (!values) return;
    try {
      await api.createEntity('project', values);
      toast('Project created and linked to your graph');
      reload();
    } catch (err) { toast(err.message, 'error'); }
  });
  $$('[data-open]', root).forEach((b) => b.onclick = () => openEntity(b.dataset.open, { onChange: reload }));
}
