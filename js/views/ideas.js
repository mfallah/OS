// Idea Garden: capture freely, cluster deliberately, develop one step at a time.
import { api } from '../api.js';
import { $, $$, esc, pill, toast, formDialog, emptyState } from '../ui.js';
import { openEntity } from '../detail.js';

const NEXT_STEPS = {
  captured: 'Give it a one-line development step',
  developing: 'Connect it to a project or knowledge',
  validated: 'Turn it into a project or an experiment',
  parked: 'Revisit on the next idea digest',
};

export async function renderIdeas(root, data, reload) {
  const ideas = data.ideas || [];
  // Collision detection: ideas sharing meaningful title tokens.
  const clusters = [];
  const seen = new Set();
  ideas.forEach((idea, i) => {
    if (seen.has(idea.id)) return;
    const tokens = new Set(String(idea.title || '').toLowerCase().split(/\W+/).filter((w) => w.length > 4));
    const related = ideas.slice(i + 1).filter((other) => {
      const otherTokens = String(other.title || '').toLowerCase().split(/\W+/).filter((w) => w.length > 4);
      return otherTokens.some((t) => tokens.has(t));
    });
    if (related.length) {
      related.forEach((r) => seen.add(r.id));
      clusters.push([idea, ...related]);
    }
  });

  root.innerHTML = `<div class="card full">
    <div class="card-head"><div><h2>Idea garden</h2>
      <span class="muted">${ideas.length} ideas · capture freely, develop deliberately</span></div>
      <button class="primary" data-new>＋ Plant an idea</button></div>
    ${clusters.length ? `<div class="objective warm"><div class="orb">⇄</div>
      <div><span class="label">COLLISIONS DETECTED</span>
        <strong>${clusters.length} cluster${clusters.length > 1 ? 's' : ''} of related ideas</strong>
        <small>${clusters.map((c) => c.map((i) => `“${i.title}”`).join(' + ')).slice(0, 2).join(' · ')} — consider merging or linking</small></div></div>` : ''}
    <div class="view-list">
      ${ideas.length ? ideas.map((i) => `
        <article class="entity">
          <div class="entity-top"><h3>✦ ${esc(i.title)}</h3>
            <span class="pill">${esc(i.status || 'captured')}</span></div>
          <p class="muted">${esc(i.summary || i.raw_capture || '')}</p>
          <p class="muted tiny">Potential: <b>${esc(i.potential || 'unknown')}</b> · Next: ${esc(NEXT_STEPS[i.status] || NEXT_STEPS.captured)}</p>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="secondary" data-develop='${esc(JSON.stringify({ id: i.id, title: i.title, status: i.status }))}'>Develop</button>
            <button class="quiet" data-open="${esc(i.id)}">Open</button>
          </div>
        </article>`).join('') : emptyState('The garden is empty.', 'Plant the first seed.')}
    </div></div>`;

  $('[data-new]', root).addEventListener('click', async () => {
    const values = await formDialog({
      title: 'Plant an idea', eyebrow: 'IDEA',
      fields: [
        { name: 'title', label: 'Idea' },
        { name: 'raw_capture', label: 'Raw capture', type: 'textarea', placeholder: 'The unpolished thought…' },
        { name: 'origin', label: 'Where did it come from?' },
      ],
    });
    if (!values) return;
    try {
      const idea = await api.createEntity('idea', { status: 'captured', potential: 'unknown', ...values });
      for (const other of ideas.slice(0, 20)) {
        const shared = String(other.title).toLowerCase().split(/\W+/)
          .filter((w) => w.length > 4 && String(values.title).toLowerCase().includes(w));
        if (shared.length) { await api.link(idea.id, 'related_to', other.id).catch(() => {}); break; }
      }
      toast('Idea planted — related ideas auto-linked when tokens match');
      reload();
    } catch (err) { toast(err.message, 'error'); }
  });

  $$('[data-develop]', root).forEach((b) => b.onclick = async () => {
    const idea = JSON.parse(b.dataset.develop);
    const next = idea.status === 'captured' ? 'developing' : idea.status === 'developing' ? 'validated' : idea.status;
    if (next !== idea.status) {
      await api.updateEntity(idea.id, { status: next });
      toast(`Moved to “${next}”`);
      reload();
    } else {
      openEntity(idea.id, { onChange: reload });
    }
  });
  $$('[data-open]', root).forEach((b) => b.onclick = () => openEntity(b.dataset.open, { onChange: reload }));
}
