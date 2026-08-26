// Research & Knowledge: continue from what you know — prior-first protocol.
import { api } from '../api.js';
import { $, $$, esc, pill, title, toast, formDialog, emptyState, relTime } from '../ui.js';
import { openEntity } from '../detail.js';

export async function renderResearch(root, data, reload) {
  const research = data.research || [];
  const questions = (data.questions || []).filter((q) => !['done', 'answered'].includes(q.status));
  const knowledge = (await api.get('/api/core/entities?kind=knowledge&limit=50')).items || [];

  root.innerHTML = `<div class="grid">
    <section class="card">
      <div class="eyebrow">RESEARCH OS</div>
      <h2 style="margin:6px 0 10px">Continue from what you know.</h2>
      <p class="muted">Before starting something new, Ourex surfaces prior findings, stale threads and unanswered questions — so research compounds instead of restarting.</p>
      <form id="priorForm" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
        <input id="priorTopic" placeholder="Topic, e.g. MCP permissions" style="flex:1;min-width:180px;min-height:44px;border:1px solid var(--line);border-radius:9px;padding:0 12px">
        <button class="primary" type="submit">Check prior research</button>
      </form>
      <div id="priorResult" style="margin-top:12px"></div>
    </section>

    <section class="card">
      <div class="card-head"><div><h2>Open questions</h2>
        <span class="muted">${questions.length} unanswered — research starts here</span></div>
        <button class="quiet" data-new-question>＋ Question</button></div>
      ${questions.length ? questions.map((q) => `<div class="insight"><div class="dot"></div>
        <div style="flex:1"><strong>${esc(title(q))}</strong>
          <p>in: ${esc(q.research || 'general')} · asked ${relTime(q.created_at)}</p>
          <button class="quiet" data-answer='${esc(JSON.stringify({ id: q.id, title: title(q) }))}'>Mark answered →</button></div></div>`).join('')
        : '<p class="muted">No unanswered questions. That is rare and good.</p>'}
    </section>

    <section class="card">
      <div class="card-head"><div><h2>Research threads</h2>
        <span class="muted">${research.length} active threads</span></div>
        <button class="quiet" data-new-research>＋ New thread</button></div>
      <div class="view-list">
        ${research.map((r) => `<article class="entity">
          <div class="entity-top"><h3>${esc(title(r))}</h3>${pill(r.status)}</div>
          <p class="muted">${(r.objectives || []).map(esc).join(' · ') || 'No objectives recorded'}</p>
          <p class="tiny muted">${r.sources ?? '—'} sources · ${r.claims ?? '—'} claims · uncertainty ${esc(r.uncertainty || 'unknown')} · last activity ${relTime(r.last_activity || r.updated_at)}</p>
          <button class="quiet" data-open="${esc(r.id)}">Open thread</button>
        </article>`).join('') || emptyState('No research threads yet.')}
      </div>
    </section>

    <section class="card">
      <div class="card-head"><div><h2>Knowledge</h2>
        <span class="muted">${knowledge.length} distilled items with provenance</span></div>
        <button class="quiet" data-new-knowledge>＋ Add knowledge</button></div>
      <div class="view-list">
        ${knowledge.map((k) => `<article class="entity">
          <div class="entity-top"><h3>◈ ${esc(title(k))}</h3><span class="pill grey">confidence ${k.confidence ?? '—'}</span></div>
          <p class="muted">${esc(k.summary || '')}</p>
          <p class="tiny muted">Source: ${esc(k.source || 'unknown')}</p>
        </article>`).join('') || emptyState('No knowledge yet.', 'Distill research into durable knowledge.')}
      </div>
    </section>
  </div>`;

  $('#priorForm', root).addEventListener('submit', async (e) => {
    e.preventDefault();
    const topic = $('#priorTopic', root).value.trim();
    if (!topic) return;
    const box = $('#priorResult', root);
    box.innerHTML = '<div class="skel" style="width:70%"></div>';
    try {
      const res = await api.priorResearch(topic);
      box.innerHTML = `<div class="detail-section">
        <div class="label">PRIOR THREADS (${res.prior_research.length})</div>
        ${res.prior_research.map((r) => `<div class="factor"><span>${esc(r.title)}</span><b>${r.score}</b></div>`).join('') || '<p class="muted">None found.</p>'}
        <div class="label" style="margin-top:10px">OPEN QUESTIONS (${res.all_open_questions.length})</div>
        ${res.all_open_questions.slice(0, 4).map((q) => `<div class="factor"><span>${esc(q.title)}</span></div>`).join('') || '<p class="muted">None.</p>'}
        ${res.stale_threads.length ? `<div class="label" style="margin-top:10px">STALE (>30 days)</div>
          ${res.stale_threads.map((s) => `<div class="factor"><span>${esc(s.title)}</span><b>${esc(s.note)}</b></div>`).join('')}` : ''}
        <p class="reasoning">→ ${esc(res.recommendation)}</p></div>`;
    } catch (err) { box.innerHTML = `<div class="error-box">${esc(err.message)}</div>`; }
  });

  $('[data-new-question]', root).addEventListener('click', async () => {
    const v = await formDialog({ title: 'Open question', fields: [{ name: 'title', label: 'Question' }, { name: 'research', label: 'Research thread' }] });
    if (!v) return;
    await api.createEntity('question', { status: 'open', ...v });
    toast('Question attached to research'); reload();
  });
  $('[data-new-research]', root).addEventListener('click', async () => {
    const v = await formDialog({
      title: 'Start research', fields: [
        { name: 'title', label: 'Topic' },
        { name: 'objectives', label: 'Objectives (comma separated)', list: true },
        { name: 'questions_open', label: 'Key questions (comma separated)', list: true },
      ],
    });
    if (!v) return;
    await api.createEntity('research', { status: 'active', uncertainty: 'unknown', ...v });
    toast('Research thread started'); reload();
  });
  $('[data-new-knowledge]', root).addEventListener('click', async () => {
    const v = await formDialog({
      title: 'Add knowledge', fields: [
        { name: 'title', label: 'Statement' },
        { name: 'summary', label: 'Summary', type: 'textarea' },
        { name: 'source', label: 'Source (required for provenance)' },
      ],
    });
    if (!v) return;
    await api.createEntity('knowledge', { confidence: 0.7, ...v });
    toast('Knowledge stored with provenance'); reload();
  });
  $$('[data-answer]', root).forEach((b) => b.onclick = async () => {
    const q = JSON.parse(b.dataset.answer);
    await api.updateEntity(q.id, { status: 'answered' });
    toast('Question closed'); reload();
  });
  $$('[data-open]', root).forEach((b) => b.onclick = () => openEntity(b.dataset.open, { onChange: reload }));
}
