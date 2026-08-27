// Entity detail drawer: view fields, graph neighbors, link/unlink, edit, delete.
import { api } from './api.js';
import { $, $$, esc, title, pill, badgeForStatus, relTime, toast, confirmDialog, formDialog } from './ui.js';

const FIELD_LABELS = {
  title: 'Title', name: 'Name', description: 'Description', status: 'Status',
  priority: 'Priority', estimate: 'Estimate (min)', due: 'Due', energy: 'Energy',
  project: 'Project', importance: 'Importance', role: 'Role', summary: 'Summary',
  potential: 'Potential', next_action: 'Next action', vision: 'Vision', context: 'Context',
};

function fieldRows(entity) {
  return Object.entries(entity)
    .filter(([key, value]) => !['kind', 'metadata', 'created_at', 'updated_at', 'graph'].includes(key)
      && value != null && typeof value !== 'object')
    .map(([key, value]) => `<div class="factor"><span>${esc(FIELD_LABELS[key] || key)}</span><b>${esc(value)}</b></div>`)
    .join('');
}

function metaRows(entity) {
  const rows = [`<div class="factor"><span>ID</span><b class="tiny">${esc(entity.id)}</b></div>`,
    `<div class="factor"><span>Type</span><b>${esc(entity.kind || '')}</b></div>`,
    `<div class="factor"><span>Updated</span><b>${relTime(entity.updated_at)}</b></div>`,
    `<div class="factor"><span>Source</span><b>${esc(entity.source || 'user')}</b></div>`];
  return rows.join('');
}

function neighborRows(graph) {
  if (!graph?.length) return '<p class="muted">Not connected to anything yet.</p>';
  return graph.map((edge) => {
    const other = edge.entity || {};
    return `<div class="graph-edge">
      <span class="rel">${esc(edge.relation)}</span>
      <span class="muted">${edge.edge_direction === 'outgoing' ? '→' : '←'}</span>
      <button class="quiet" data-open="${esc(other.id)}">${esc(title(other))}</button>
      <span class="pill grey">${esc(other.kind || '')}</span>
      <button class="quiet" data-unlink='${esc(JSON.stringify({ source: edge.source, relation: edge.relation, target: edge.target }))}' aria-label="Remove link">✕</button>
    </div>`;
  }).join('');
}

const EDIT_FIELDS = {
  task: [
    { name: 'title', label: 'Title' }, { name: 'project', label: 'Project' },
    { name: 'priority', label: 'Priority', type: 'select', options: ['low', 'medium', 'high'] },
    { name: 'estimate', label: 'Estimate (min)', type: 'number' },
    { name: 'due', label: 'Due' }, { name: 'status', label: 'Status', type: 'select', options: ['open', 'in-progress', 'done', 'archived'] },
  ],
  project: [
    { name: 'name', label: 'Name' }, { name: 'description', label: 'Description', type: 'textarea' },
    { name: 'status', label: 'Status', type: 'select', options: ['active', 'at-risk', 'paused', 'done', 'archived'] },
    { name: 'next_action', label: 'Next action' }, { name: 'vision', label: 'Vision' },
  ],
  person: [
    { name: 'name', label: 'Name' }, { name: 'role', label: 'Role' },
    { name: 'importance', label: 'Importance', type: 'select', options: ['low', 'medium', 'high'] },
    { name: 'need', label: 'Current need' }, { name: 'last_contact', label: 'Last contact (date)' },
  ],
  idea: [
    { name: 'title', label: 'Title' }, { name: 'summary', label: 'Summary', type: 'textarea' },
    { name: 'status', label: 'Status', type: 'select', options: ['captured', 'developing', 'validated', 'parked', 'done'] },
    { name: 'potential', label: 'Potential', type: 'select', options: ['unknown', 'low', 'medium', 'high'] },
  ],
  decision: [
    { name: 'title', label: 'Question' }, { name: 'context', label: 'Context', type: 'textarea' },
    { name: 'options', label: 'Options (comma separated)', list: true },
    { name: 'status', label: 'Status', type: 'select', options: ['open', 'decided', 'reviewed'] },
    { name: 'decision', label: 'Chosen option' }, { name: 'confidence', label: 'Confidence (0-1)', type: 'number' },
  ],
  default: [
    { name: 'title', label: 'Title' }, { name: 'description', label: 'Description', type: 'textarea' },
    { name: 'status', label: 'Status' },
  ],
};

export async function openEntity(id, { onChange } = {}) {
  const host = $('#detailModal'); const card = $('#detailCard');
  card.innerHTML = '<div class="loading">Loading entity…</div>';
  host.classList.remove('hidden');
  try {
    const entity = await api.entity(id);
    await renderDetail(card, entity, onChange);
  } catch (err) {
    card.innerHTML = `<button class="close" data-x>×</button><div class="error-box">${esc(err.message)}</div>`;
    $('[data-x]', card)?.addEventListener('click', () => host.classList.add('hidden'));
  }
}

async function renderDetail(card, entity, onChange) {
  const host = $('#detailModal');
  const all = await api.get('/api/core/entities?limit=200');
  const candidates = (all.items || []).filter((e) => e.id !== entity.id).slice(0, 60);
  card.innerHTML = `
    <button class="close" data-x aria-label="Close">×</button>
    <div class="eyebrow">${esc((entity.kind || 'entity').toUpperCase())}</div>
    <h2>${esc(title(entity))}</h2>
    <div class="chip-row">${badgeForStatus(entity.status)}${pill(`${entity.confidence != null ? `confidence ${entity.confidence}` : ''}`)}</div>
    ${entity.description ? `<p class="muted">${esc(entity.description)}</p>` : ''}
    <div class="detail-section">${fieldRows(entity)}</div>
    <div class="detail-section"><div class="label">GRAPH CONNECTIONS</div>${neighborRows(entity.graph)}</div>
    <div class="detail-section">
      <div class="label">CONNECT TO ANOTHER ENTITY</div>
      <form id="linkForm" style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">
        <select id="linkRel" aria-label="Relation" style="min-height:44px;border:1px solid var(--line);border-radius:8px">
          ${['supports', 'blocks', 'depends_on', 'related_to', 'derived_from', 'belongs_to', 'contributes_to', 'follows_up', 'conflicts_with', 'learned_from'].map((r) => `<option>${r}</option>`).join('')}
        </select>
        <select id="linkTarget" aria-label="Target entity" style="flex:1;min-width:160px;min-height:44px;border:1px solid var(--line);border-radius:8px">
          ${candidates.map((c) => `<option value="${esc(c.id)}">[${esc(c.kind)}] ${esc(title(c))}</option>`).join('')}
        </select>
        <button class="secondary" type="submit">Link</button>
      </form>
    </div>
    <div class="detail-section"><div class="label">RECORD</div>${metaRows(entity)}</div>
    <div style="display:flex;gap:8px;margin-top:18px;flex-wrap:wrap">
      <button class="primary" data-edit>Edit</button>
      <button class="danger" data-delete>Delete…</button>
    </div>`;

  const host_ = $('#detailModal');
  $$('[data-x]', card).forEach((b) => b.addEventListener('click', () => host_.classList.add('hidden')));
  $$('[data-open]', card).forEach((b) => b.addEventListener('click', () => openEntity(b.dataset.open, { onChange })));
  $$('[data-unlink]', card).forEach((b) => b.addEventListener('click', async () => {
    const { source, relation, target } = JSON.parse(b.dataset.unlink);
    await api.unlink(source, relation, target);
    toast('Link removed');
    openEntity(entity.id, { onChange });
    onChange?.();
  }));
  $('#linkForm', card).addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await api.link(entity.id, $('#linkRel', card).value, $('#linkTarget', card).value);
      toast('Connected in the graph');
      openEntity(entity.id, { onChange });
      onChange?.();
    } catch (err) { toast(err.message, 'error'); }
  });
  $('[data-edit]', card).addEventListener('click', async () => {
    const fields = EDIT_FIELDS[entity.kind] || EDIT_FIELDS.default;
    const patch = await formDialog({ title: title(entity), eyebrow: `EDIT ${entity.kind?.toUpperCase()}`, fields, values: entity });
    if (!patch) return;
    try {
      await api.updateEntity(entity.id, patch);
      toast('Saved');
      host_.classList.add('hidden');
      onChange?.();
    } catch (err) { toast(err.message, 'error'); }
  });
  $('[data-delete]', card).addEventListener('click', async () => {
    const yes = await confirmDialog({
      title: `Delete “${title(entity)}”?`,
      body: 'Soft-deleted with an event. Graph links are kept dormant so a future restore can recover them. Restore is available through the data API.',
      confirmLabel: 'Delete', danger: true,
    });
    if (!yes) { openEntity(entity.id, { onChange }); return; }
    try {
      await api.deleteEntity(entity.id);
      toast('Deleted with audit record');
      host_.classList.add('hidden');
      onChange?.();
    } catch (err) { toast(err.message, 'error'); }
  });
}
