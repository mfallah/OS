// Entity drawer: overview / connections / activity — full editing freedom.
// Custom fields are first-class: any key/value can live on any entity.
import { api } from './api.js';
import { $, $$, esc, title, pill, badgeForStatus, relTime, toast, confirmDialog, formDialog } from './ui.js';

const CORE_KEYS = new Set(['kind', 'id', 'created_at', 'updated_at', 'metadata', 'graph',
  'title', 'name', 'description', 'status', 'confidence', 'source', 'tags', 'question']);

const EDIT_FIELDS = {
  task: [
    { name: 'title', label: 'Title' },
    { name: 'project', label: 'Project' },
    { name: 'priority', label: 'Priority', type: 'select', options: ['low', 'medium', 'high', 'urgent'] },
    { name: 'estimate', label: 'Estimate (min)', type: 'number' },
    { name: 'due', label: 'Due (YYYY-MM-DD)' },
    { name: 'start', label: 'Start (YYYY-MM-DD)' },
    { name: 'status', label: 'Status', type: 'select', options: ['open', 'in-progress', 'waiting', 'done', 'archived'] },
    { name: 'energy', label: 'Energy', type: 'select', options: ['light', 'deep'] },
    { name: 'recurrence', label: 'Repeat' },
    { name: 'notes', label: 'Notes', type: 'textarea' },
  ],
  project: [
    { name: 'name', label: 'Name' },
    { name: 'description', label: 'Description', type: 'textarea' },
    { name: 'status', label: 'Status', type: 'select', options: ['active', 'at-risk', 'paused', 'done', 'archived'] },
    { name: 'next_action', label: 'Next action' },
    { name: 'vision', label: 'Vision', type: 'textarea' },
    { name: 'progress', label: 'Progress %', type: 'number' },
    { name: 'deadline', label: 'Target date' },
    { name: 'area', label: 'Life area' },
  ],
  person: [
    { name: 'name', label: 'Name' },
    { name: 'role', label: 'Role' },
    { name: 'importance', label: 'Importance', type: 'select', options: ['low', 'medium', 'high'] },
    { name: 'need', label: 'Current need', type: 'textarea' },
    { name: 'communication_preference', label: 'Communication preference' },
    { name: 'last_contact', label: 'Last contact (date)' },
    { name: 'birthday', label: 'Birthday' },
  ],
  idea: [
    { name: 'title', label: 'Title' },
    { name: 'summary', label: 'Summary', type: 'textarea' },
    { name: 'status', label: 'Status', type: 'select', options: ['captured', 'developing', 'validated', 'parked', 'done'] },
    { name: 'potential', label: 'Potential', type: 'select', options: ['unknown', 'low', 'medium', 'high'] },
    { name: 'first_step', label: 'Smallest next experiment' },
  ],
  decision: [
    { name: 'title', label: 'Question' },
    { name: 'context', label: 'Context', type: 'textarea' },
    { name: 'options', label: 'Options (comma separated)', list: true },
    { name: 'status', label: 'Status', type: 'select', options: ['open', 'decided', 'reviewed'] },
    { name: 'decision', label: 'Chosen option' },
    { name: 'confidence', label: 'Confidence 0–1', type: 'number' },
  ],
  default: [
    { name: 'title', label: 'Title' },
    { name: 'description', label: 'Description', type: 'textarea' },
    { name: 'status', label: 'Status' },
  ],
};

const RELATIONS = ['supports', 'blocks', 'depends_on', 'related_to', 'derived_from',
  'belongs_to', 'contributes_to', 'follows_up', 'conflicts_with', 'learned_from'];

function fmtValue(value) {
  if (Array.isArray(value)) return value.join(', ');
  return String(value);
}

function fieldRows(entity) {
  return Object.entries(entity)
    .filter(([key, value]) => !CORE_KEYS.has(key) && value != null && typeof value !== 'object')
    .map(([key, value]) => `<div class="factor"><span class="mono tiny">${esc(key)}</span><b>${esc(fmtValue(value))}</b></div>`)
    .join('');
}

function tagsRow(entity, reload) {
  const tags = entity.tags || [];
  return `<div class="chip-row" id="tagRow">
    ${tags.map((t) => `<span class="chip">#${esc(t)} <button class="quiet" data-rm-tag="${esc(t)}" aria-label="Remove tag" style="padding:0 2px;min-height:auto">×</button></span>`).join('')}
    <span class="chip" style="border-style:dashed"><input id="newTag" placeholder="+ tag"
      style="border:0;background:none;font:inherit;color:inherit;width:60px;outline:none" aria-label="Add tag"></span>
  </div>`;
}

function metaRows(entity) {
  return `<div class="factor"><span class="mono tiny">id</span><b class="tiny">${esc(entity.id)}</b></div>
    <div class="factor"><span class="mono tiny">kind</span><b>${esc(entity.kind || '')}</b></div>
    <div class="factor"><span class="mono tiny">updated</span><b>${relTime(entity.updated_at)}</b></div>
    <div class="factor"><span class="mono tiny">source</span><b>${esc(entity.source || 'user')}</b></div>`;
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
      <button class="quiet" data-unlink='${esc(JSON.stringify({ source: edge.source, relation: edge.relation, target: edge.target }))}' aria-label="Remove link">×</button>
    </div>`;
  }).join('');
}

function activityRows(items) {
  if (!items.length) return '<p class="muted">No events recorded yet.</p>';
  return items.map((i) => `<div class="factor">
    <span class="mono tiny">${esc(i.type)} <span class="muted">by ${esc(i.actor)}</span></span>
    <b>${relTime(i.created_at)}</b></div>`).join('');
}

export async function openEntity(id, { onChange } = {}) {
  const host = $('#detailModal'); const card = $('#detailCard');
  card.innerHTML = '<div class="loading">LOADING…</div>';
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
  const [all, schemaRes] = await Promise.all([
    api.get('/api/core/entities?limit=200'),
    api.get('/api/core/schema').catch(() => null),
  ]);
  const candidates = (all.items || []).filter((e) => e.id !== entity.id).slice(0, 60);
  const suggested = schemaRes?.fields?.[entity.kind] || [];
  const baseFields = EDIT_FIELDS[entity.kind] || EDIT_FIELDS.default;
  // suggested fields not already covered become an expandable "more fields" set
  const extraFields = suggested.filter((f) => !baseFields.some((b) => b.name === f.name));
  const customEntries = Object.entries(entity)
    .filter(([k, v]) => !CORE_KEYS.has(k) && v != null && typeof v !== 'object');

  card.innerHTML = `
    <button class="close" data-x aria-label="Close">×</button>
    <div class="eyebrow">${esc((entity.kind || 'entity').toUpperCase())} · ${esc(entity.id)}</div>
    <h2>${esc(title(entity))}</h2>
    <div class="chip-row">${badgeForStatus(entity.status)}
      ${entity.confidence != null && entity.confidence !== 1 ? pill(`confidence ${entity.confidence}`, 'grey') : ''}</div>

    <div class="drawer-tabs" role="tablist">
      <button class="active" data-tab="overview" role="tab">Overview</button>
      <button data-tab="links" role="tab">Connections ${entity.graph?.length ? `(${entity.graph.length})` : ''}</button>
      <button data-tab="activity" role="tab">Activity</button>
    </div>

    <div id="tab-overview">
      ${entity.description ? `<p class="muted" style="margin:4px 0 8px">${esc(entity.description)}</p>` : ''}
      <div class="label">TAGS</div>${tagsRow(entity)}
      <div class="detail-section"><div class="label">CUSTOM FIELDS — yours, unlimited</div>
        ${fieldRows(entity) || '<p class="muted tiny" style="margin:6px 0">None yet. Add anything via Edit → custom fields.</p>'}
        ${customEntries.length ? `<button class="quiet" data-clear-custom style="margin-top:4px">remove all custom fields</button>` : ''}
      </div>
    </div>

    <div id="tab-links" class="hidden">
      <div class="detail-section" style="border:0;margin:0;padding:0">${neighborRows(entity.graph)}</div>
      <div class="detail-section">
        <div class="label">CONNECT TO ANOTHER ENTITY</div>
        <form id="linkForm" style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">
          <select id="linkRel" class="select" aria-label="Relation">
            ${RELATIONS.map((r) => `<option>${r}</option>`).join('')}
          </select>
          <select id="linkTarget" class="select" style="flex:1;min-width:160px" aria-label="Target entity">
            ${candidates.map((c) => `<option value="${esc(c.id)}">[${esc(c.kind)}] ${esc(title(c))}</option>`).join('')}
          </select>
          <button class="secondary" type="submit">Link</button>
        </form>
      </div>
    </div>

    <div id="tab-activity" class="hidden">
      <div class="detail-section" style="border:0;margin:0;padding:0" id="activityBox">
        <div class="loading">LOADING…</div>
      </div>
    </div>

    <div class="detail-section">${metaRows(entity)}</div>
    <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
      <button class="primary" data-edit>Edit — full freedom</button>
      <button class="danger" data-delete>Delete…</button>
    </div>`;

  const close = () => host.classList.add('hidden');
  $$('[data-x]', card).forEach((b) => b.addEventListener('click', close));

  // tabs
  const showTab = async (tab) => {
    $$('.drawer-tabs button', card).forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
    ['overview', 'links', 'activity'].forEach((t) => $(`#tab-${t}`, card).classList.toggle('hidden', t !== tab));
    if (tab === 'activity') {
      try {
        const res = await api.get(`/api/core/entities/${entity.id}/history`);
        $('#activityBox', card).innerHTML = activityRows(res.items);
      } catch (err) {
        $('#activityBox', card).innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
      }
    }
  };
  $$('.drawer-tabs button', card).forEach((b) => b.addEventListener('click', () => showTab(b.dataset.tab)));

  // tags
  const saveTags = async (tags) => {
    try {
      await api.updateEntity(entity.id, { tags });
      toast('Tags updated');
      openEntity(entity.id, { onChange });
      onChange?.();
    } catch (err) { toast(err.message, 'error'); }
  };
  $$('[data-rm-tag]', card).forEach((b) => b.addEventListener('click', () =>
    saveTags((entity.tags || []).filter((t) => t !== b.dataset.rmTag))));
  $('#newTag', card)?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const v = e.target.value.trim();
      if (v) saveTags([...(entity.tags || []), v]);
    }
  });

  // custom fields
  $('[data-clear-custom]', card)?.addEventListener('click', async () => {
    const yes = await confirmDialog({
      title: 'Remove all custom fields?',
      body: 'Only the extra key/value fields you added — standard fields are untouched.',
      confirmLabel: 'Remove',
    });
    if (!yes) return;
    try {
      const patch = Object.fromEntries(customEntries.map(([k]) => [k, '']));
      await api.updateEntity(entity.id, patch);
      toast('Custom fields cleared');
      openEntity(entity.id, { onChange });
      onChange?.();
    } catch (err) { toast(err.message, 'error'); }
  });

  // links
  $$('[data-open]', card).forEach((b) => b.addEventListener('click', () =>
    openEntity(b.dataset.open, { onChange })));
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

  // edit — schema suggestions + unlimited custom fields
  $('[data-edit]', card).addEventListener('click', async () => {
    const patch = await formDialog({
      title: title(entity), eyebrow: `EDIT ${entity.kind?.toUpperCase()}`,
      fields: baseFields, extraFields, values: entity, submitLabel: 'Save changes',
    });
    if (!patch) return;
    try {
      await api.updateEntity(entity.id, patch);
      toast('Saved — every field stored verbatim');
      close();
      onChange?.();
    } catch (err) { toast(err.message, 'error'); }
  });

  $('[data-delete]', card).addEventListener('click', async () => {
    const yes = await confirmDialog({
      title: `Delete “${title(entity)}”?`,
      body: 'Soft-deleted with an audit record and an event. Graph links are removed. Recoverable from the audit trail.',
      confirmLabel: 'Delete', danger: true,
    });
    if (!yes) { openEntity(entity.id, { onChange }); return; }
    try {
      await api.deleteEntity(entity.id);
      toast('Deleted with audit record');
      close();
      onChange?.();
    } catch (err) { toast(err.message, 'error'); }
  });
}
