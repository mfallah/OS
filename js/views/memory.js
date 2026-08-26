// Memory Governance: you own what myos remembers — see, edit, correct,
// delete, export, disable categories, and always know *why* it was remembered.
import { api } from '../api.js';
import { $, $$, esc, pill, toast, formDialog, confirmDialog, relTime, emptyState } from '../ui.js';

const CATEGORIES = ['identity', 'preference', 'goal', 'project', 'relationship', 'knowledge',
  'research', 'decision', 'pattern', 'episodic', 'temporary'];

let activeCategory = null;

export async function renderMemory(root, data, reload) {
  let payload;
  try {
    payload = await api.memories(activeCategory ? { category: activeCategory } : {});
  } catch (err) {
    root.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
    return;
  }
  const { items, stats } = payload;
  const disabled = new Set(stats.disabled_categories || []);

  root.innerHTML = `<div class="card full">
    <div class="card-head"><div><h2>Memory governance</h2>
      <span class="muted">Every memory shows its source, confidence and reason. Low-confidence assumptions are never silently treated as fact.</span></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="secondary" data-new>＋ Remember</button>
        <button class="secondary" data-export>Export</button>
        <button class="danger" data-clear>Clear all…</button>
      </div></div>

    <div class="chip-row" role="tablist" aria-label="Memory categories">
      <button class="chip ${!activeCategory ? 'active' : ''}" data-cat="" style="${!activeCategory ? 'background:var(--accent-soft)' : ''}">All</button>
      ${CATEGORIES.map((c) => `<button class="chip" data-cat="${c}" style="${activeCategory === c ? 'background:var(--accent-soft)' : ''}">
        ${c} ${stats.by_category?.[c] ? `(${stats.by_category[c]})` : ''}${disabled.has(c) ? ' ⏸' : ''}</button>`).join('')}
    </div>

    ${stats.unconfirmed ? `<div class="objective warm"><div class="orb">?</div>
      <div><span class="label">UNCONFIRMED ASSUMPTIONS</span>
        <strong>${stats.unconfirmed} memor${stats.unconfirmed === 1 ? 'y' : 'ies'} need your confirmation</strong>
        <small>Confirm to promote them, correct them, or delete. Uncertain extraction never becomes identity fact on its own.</small></div></div>` : ''}

    <div class="view-list">
      ${items.length ? items.map((m) => `
        <article class="entity">
          <div class="entity-top"><h3>${esc(m.content.slice(0, 90))}${m.content.length > 90 ? '…' : ''}</h3>
            <span class="pill ${m.status === 'unconfirmed' ? 'amber' : ''}">${esc(m.category)}${m.status === 'unconfirmed' ? ' · unconfirmed' : ''}</span></div>
          <p class="tiny muted">source ${esc(m.source)} · provenance ${esc(m.provenance || '—')} · confidence ${Math.round(m.confidence * 100)}%
            · importance ${m.importance}/10 · scope ${esc(m.scope)} · ${relTime(m.created_at)}${m.corrected_by_user ? ' · corrected by you' : ''}</p>
          <p class="reasoning">Why remembered: ${esc(m.why || 'no reason stored')}</p>
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            ${m.status === 'unconfirmed' ? `<button class="secondary" data-confirm="${m.id}">Confirm</button>` : ''}
            <button class="secondary" data-correct='${esc(JSON.stringify({ id: m.id, content: m.content }))}'>Edit / Correct</button>
            <button class="quiet" data-delete="${m.id}" style="color:var(--red)">Delete</button>
            <button class="quiet" data-cat-off="${m.category}">Disable “${m.category}”</button>
          </div>
        </article>`).join('') : emptyState('Nothing remembered here.', 'Capture or talk to myos — episodic notes appear automatically.')}
    </div>
    ${disabled.size ? `<p class="muted tiny" style="margin-top:12px">Disabled categories: ${[...disabled].map((c) => `<button class="quiet" data-cat-on="${c}">re-enable “${c}”</button>`).join(' · ')}</p>` : ''}
  </div>`;

  $$('[data-cat]', root).forEach((b) => b.onclick = () => {
    activeCategory = b.dataset.cat || null;
    renderMemory(root, data, reload);
  });
  $('[data-new]', root).onclick = async () => {
    const v = await formDialog({
      title: 'Remember explicitly', eyebrow: 'MEMORY',
      fields: [
        { name: 'category', label: 'Category', type: 'select', options: CATEGORIES },
        { name: 'content', label: 'Content', type: 'textarea' },
        { name: 'importance', label: 'Importance (1-10)', type: 'number' },
        { name: 'why', label: 'Why should myos remember this?' },
      ],
    });
    if (!v?.content) return;
    await api.remember(v.category || 'preference', v.content, { importance: v.importance || 5, why: v.why, source: 'user' });
    toast('Remembered with your provenance'); renderMemory(root, data, reload);
  };
  $('[data-export]', root).onclick = async () => {
    const dump = await api.exportMemory();
    download(`ourex-memory-${Date.now()}.json`, dump);
    toast(`Exported ${dump.memories.length} memories`);
  };
  $('[data-clear]', root).onclick = async () => {
    const yes = await confirmDialog({
      title: 'Clear ALL memories?',
      body: 'Every memory is marked deleted (audit-logged). Entities and graph stay intact. This is how forgetting should work: explicit and recorded.',
      confirmLabel: 'Clear memory', danger: true,
    });
    if (!yes) { renderMemory(root, data, reload); return; }
    await fetch('/api/core/memory/clear?confirm=true', { method: 'POST' });
    toast('Memory cleared with audit record'); renderMemory(root, data, reload);
  };
  $$('[data-confirm]', root).forEach((b) => b.onclick = async () => {
    await api.confirmMemory(b.dataset.confirm);
    toast('Confirmed — now treated as reliable'); renderMemory(root, data, reload);
  });
  $$('[data-correct]', root).forEach((b) => b.onclick = async () => {
    const m = JSON.parse(b.dataset.correct);
    const v = await formDialog({
      title: 'Correct this memory', eyebrow: 'CORRECTION',
      fields: [{ name: 'content', label: 'Corrected content', type: 'textarea' }],
      values: { content: m.content },
    });
    if (!v?.content) { renderMemory(root, data, reload); return; }
    await api.correctMemory(m.id, v.content);
    toast('Corrected — confidence set to 100%, provenance: you'); renderMemory(root, data, reload);
  });
  // Content edits go through "Correct" so provenance stays truthful.
  $$('[data-delete]', root).forEach((b) => b.onclick = async () => {
    const yes = await confirmDialog({ title: 'Delete this memory?', body: 'Marked deleted, event-logged. It stops influencing every future answer.', confirmLabel: 'Delete', danger: true });
    if (!yes) { renderMemory(root, data, reload); return; }
    await api.deleteMemory(b.dataset.delete);
    toast('Forgotten'); renderMemory(root, data, reload);
  });
  $$('[data-cat-off]', root).forEach((b) => b.onclick = async () => {
    await api.memoryCategory(b.dataset.catOff, 'disable');
    toast(`Category “${b.dataset.catOff}” disabled — it no longer feeds answers`); renderMemory(root, data, reload);
  });
  $$('[data-cat-on]', root).forEach((b) => b.onclick = async () => {
    await api.memoryCategory(b.dataset.catOn, 'enable');
    toast(`Category re-enabled`); renderMemory(root, data, reload);
  });
}

function download(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}
