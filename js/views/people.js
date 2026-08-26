// Relationships: long-lived people entities with attention intelligence.
import { api } from '../api.js';
import { $, $$, esc, pill, title, toast, formDialog, emptyState, relTime } from '../ui.js';
import { openEntity } from '../detail.js';

const PERSON_FIELDS = [
  { name: 'name', label: 'Name' }, { name: 'role', label: 'Role / relationship' },
  { name: 'importance', label: 'Importance', type: 'select', options: ['high', 'medium', 'low'] },
  { name: 'need', label: 'Current need / context' },
  { name: 'communication_preference', label: 'Communication preference' },
];

const INTERACTION_FIELDS = [
  { name: 'summary', label: 'What happened', type: 'textarea', placeholder: 'Coffee — talked about her new role…' },
  { name: 'follow_up', label: 'Promised follow-up (optional)' },
];

export async function logInteraction(person, reload) {
  const values = await formDialog({ title: `Log interaction with ${person.name}`, eyebrow: 'INTERACTION', fields: INTERACTION_FIELDS });
  if (!values) return;
  try {
    const interaction = await api.createEntity('interaction', {
      title: `With ${person.name}: ${values.summary.slice(0, 60)}`,
      person: person.name, date: new Date().toISOString(), ...values,
    });
    await api.link(interaction.id, 'mentioned_in', person.id);
    await api.updateEntity(person.id, { last_contact: new Date().toISOString().slice(0, 10) });
    if (values.follow_up) {
      const task = await api.createEntity('task', {
        title: `Follow up with ${person.name}: ${values.follow_up}`,
        project: 'Relationships', priority: 'medium', status: 'open', estimate: 15, energy: 'light',
      });
      await api.link(task.id, 'follows_up', person.id);
      toast('Interaction logged + follow-up task created');
    } else {
      toast('Interaction logged');
    }
    reload();
  } catch (err) { toast(err.message, 'error'); }
}

export async function renderPeople(root, data, reload) {
  const people = data.people || [];
  const attention = new Set((data.relationship_attention || []).map((p) => p.id));
  root.innerHTML = `<div class="card full">
    <div class="card-head"><div><h2>Relationship intelligence</h2>
      <span class="muted">${attention.size} need attention · attention is care, not a score</span></div>
      <button class="primary" data-new>＋ Add person</button></div>
    <div class="view-list">
      ${people.length ? people.map((p) => `
        <article class="entity">
          <div class="entity-top"><div><h3>${esc(p.name)}</h3>
            <span class="muted">${esc(p.role || '')}</span></div>
            <span class="pill ${attention.has(p.id) ? 'amber' : ''}">${esc(p.importance || 'medium')} importance${attention.has(p.id) ? ' · needs attention' : ''}</span></div>
          <p class="muted">${esc(p.need || '')} · last meaningful contact ${esc(p.last_contact || 'unknown')}</p>
          <p class="reasoning">Cadence: ${p.importance === 'high' ? 'weekly' : p.importance === 'low' ? 'monthly' : 'bi-weekly'} expectation · observation, not obligation</p>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="secondary" data-interact='${esc(JSON.stringify({ id: p.id, name: p.name }))}'>Log interaction</button>
            <button class="quiet" data-open="${esc(p.id)}">Open record</button>
          </div>
        </article>`).join('') : emptyState('No relationships tracked yet.', 'Add the people who matter.')}
    </div></div>`;

  $('[data-new]', root).addEventListener('click', async () => {
    const values = await formDialog({ title: 'Add person', eyebrow: 'RELATIONSHIP', fields: PERSON_FIELDS });
    if (!values) return;
    try {
      await api.createEntity('person', { last_contact: new Date().toISOString().slice(0, 10), ...values });
      toast('Person added');
      reload();
    } catch (err) { toast(err.message, 'error'); }
  });
  $$('[data-interact]', root).forEach((b) => b.onclick = () => logInteraction(JSON.parse(b.dataset.interact), reload));
  $$('[data-open]', root).forEach((b) => b.onclick = () => openEntity(b.dataset.open, { onChange: reload }));
}
