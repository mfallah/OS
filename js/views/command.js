// Command Center: answers "What matters now?" — calm by default, tools at hand.
// Structure: quick-add bar → objective hero → today plan → priorities →
// up to 3 signals → one collapsed context drawer (everything else).
import { api } from '../api.js';
import { $, $$, esc, title, pill, relTime, dueLabel, DONE, errorBox, toast } from '../ui.js';
import { openEntity } from '../detail.js';

// Inline quick-capture syntax: "#tag #tag2" → tags, "+Project" → project.
function parseQuickAdd(text) {
  const tags = [];
  let project;
  const stripped = text
    .replace(/(^|\s)#([^\s#]+)/g, (_, sp, tag) => { tags.push(tag); return sp; })
    .replace(/(^|\s)\+([^\s+]+)/g, (_, sp, proj) => { project = proj; return sp; })
    .trim();
  const extra = {};
  if (tags.length) extra.tags = tags;
  if (project) extra.project = project;
  return { text: stripped, extra };
}

function nowBar(d) {
  const load = d.state?.cognitive_load || {};
  return `<div class="quickadd">
    <input id="quickAdd" placeholder="Add anything…  #tag for labels  +Project to file it  ⏎"
      aria-label="Quick capture">
    <button class="primary" id="quickAddGo">Add</button>
  </div>
  <div class="toolbar" style="margin-bottom:12px">
    <span class="label">TODAY · ${esc(d.date)}</span>
    <span class="spacer"></span>
    <span class="pill grey">load ${load.score ?? '—'}/100 · ${esc(load.band || '—')}</span>
    <span class="pill grey">energy ${esc(d.state?.energy?.level || '—')}</span>
    <span class="pill grey">${d.state?.attention_budget?.deep_work_hours_available ?? '—'}h deep work</span>
  </div>`;
}

function heroCard(d) {
  const rec = d.recommended_next_action || {};
  return `<section class="card full hero" style="display:flex;flex-direction:column;gap:14px">
    <div class="hero-row"><div class="orb">◆</div>
      <div style="min-width:0"><span class="label">MAIN OBJECTIVE</span>
        <strong>${esc(d.objective?.title)}</strong>
        <small>${esc(d.objective?.why || '')}${d.objective?.estimate ? ` · ~${d.objective.estimate} min` : ''}</small></div>
    </div>
    ${rec.action ? `<div class="hero-row"><div class="orb">→</div>
      <div style="min-width:0"><span class="label">RECOMMENDED NEXT ACTION</span>
        <strong>${esc(rec.action)}</strong><small>${esc(rec.reason || '')}</small></div></div>` : ''}
    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button class="primary" data-action="capture">+ Capture</button>
      <button class="secondary" data-nav="tasks">Open tasks</button>
      <button class="secondary" data-nav="projects">Portfolio</button>
    </div>
  </section>`;
}

function planCard(d) {
  const plan = d.today_plan || { items: [] };
  const items = plan.items?.length ? plan.items.slice(0, 6).map((i) => `
    <div class="task"><button class="check" data-start-task="${esc(i.task_id)}"
      aria-label="Start ${esc(i.title)}">▸</button>
      <div style="flex:1;min-width:0"><div class="title">${esc(i.title)}</div>
        <div class="meta"><span>${i.estimate} min</span>${i.energy ? `<span>${esc(i.energy)}</span>` : ''}<span class="reasoning">${esc(i.why)}</span></div></div>
    </div>`).join('') : '<p class="muted">Nothing scheduled — the day is genuinely open.</p>';
  return `<section class="card">
    <div class="card-head"><div><span class="label">TODAY'S PLAN</span>
      <h2 style="margin-top:4px">${plan.planned_minutes ?? 0} min planned</h2></div>
      <span class="pill grey">${plan.slack_hours ?? '—'}h slack kept</span></div>
    ${items}
    ${plan.deliberately_skipped?.length ? `<p class="muted tiny">Deliberately skipped: ${plan.deliberately_skipped.map((s) => esc(s.task)).join(' · ')}</p>` : ''}
  </section>`;
}

export function taskRow(t) {
  const done = DONE.has(t.status);
  const prio = ['high', 'urgent'].includes(t.priority) ? 'high'
    : t.priority === 'medium' ? 'medium' : '';
  return `<div class="task ${done ? 'done-style' : ''}"><span class="prio-flag ${prio}"></span>
    <button class="check ${done ? 'done' : ''}" data-task-toggle="${esc(t.id)}"
      aria-label="${done ? 'Reopen' : 'Complete'} ${esc(t.title)}">${done ? '✓' : ''}</button>
    <div style="flex:1;min-width:0"><div class="title">${esc(t.title)}</div>
      <div class="meta">${t.project ? `<span>${esc(t.project)}</span>` : ''}${t.estimate ? `<span>${t.estimate}min</span>` : ''}${t.due ? `<span>${esc(dueLabel(t))}</span>` : ''}</div></div>
    <button class="quiet" data-open="${esc(t.id)}" aria-label="Open task">›</button>
  </div>`;
}

function prioritiesCard(d) {
  const open = (d.tasks || []).filter((t) => !DONE.has(t.status));
  const overdue = open.filter((t) => dueLabel(t) === 'Overdue');
  const today = open.filter((t) => ['Today', 'Overdue'].includes(dueLabel(t)));
  const list = [...overdue, ...today.filter((t) => !overdue.includes(t))].slice(0, 4);
  return `<section class="card">
    <div class="card-head"><div><span class="label">DUE TODAY</span>
      <h2 style="margin-top:4px">${today.length} due · ${open.length} open</h2></div>
      <button class="quiet" data-nav="tasks">all →</button></div>
    ${list.length ? list.map(taskRow).join('') : '<p class="muted">Nothing due today — protect the space.</p>'}
  </section>`;
}

function signalsCard(d) {
  const items = (d.insights || []).slice(0, 3);
  return `<section class="card">
    <div class="card-head"><div><span class="label">SIGNALS</span>
      <h2 style="margin-top:4px">What your OS sees</h2></div></div>
    ${items.length ? items.map((i) => `
      <div class="insight ${i.kind === 'Risk' ? 'risk' : ''} ${i.kind === 'Decision required' ? 'decision' : ''}">
        <div class="dot"></div><div style="flex:1;min-width:0">
          <strong>${esc(i.title)}</strong><p>${esc(i.body)}</p>
          <span class="confidence">${esc(i.kind)} · ${Math.round((i.confidence || 0) * 100)}%</span>
        </div></div>`).join('') : '<p class="muted">No strong signals right now. Clear board.</p>'}
  </section>`;
}

function askCard() {
  return `<section class="card full">
    <div class="card-head"><div><span class="label">ASK MYOS</span>
      <h2 style="margin-top:4px">One question, one explained answer</h2></div></div>
    <form id="askForm" class="quickadd" style="margin-bottom:0">
      <input id="askInput" placeholder="Try “plan my day” or “what matters now”" aria-label="Ask myos">
      <button class="primary" type="submit">Ask</button>
    </form>
    <div id="askAnswer" style="margin-top:10px"></div>
  </section>`;
}

// Everything non-essential lives here: open only when you want the wider picture.
function contextDrawer(d) {
  const projects = (d.projects || []).slice(0, 3);
  const people = d.relationship_attention || [];
  const events = (d.calendar || []).slice(0, 4);
  const decisions = d.pending_decisions || [];
  const changes = (d.recent_changes || []).slice(0, 6);
  return `<details class="ctx full">
    <summary>CONTEXT — projects · people · calendar · decisions · changes</summary>
    <div class="ctx-grid">
      <div class="card"><div class="label" style="margin-bottom:8px">PROJECT HEALTH</div>
        ${projects.map((p) => { const h = p.health || {};
          return `<div class="bar-row"><div class="bar-label"><span>${esc(title(p))}</span>
            <b>${h.score ?? '—'}/100</b></div>
            <div class="bar ${h.status === 'at-risk' ? 'red' : h.status === 'watch' ? 'amber' : ''}"><i style="width:${h.score || 0}%"></i></div></div>`;
        }).join('') || '<p class="muted">No active projects.</p>'}
        <button class="quiet" data-nav="projects">portfolio →</button></div>
      <div class="card"><div class="label" style="margin-bottom:8px">PEOPLE NEEDING ATTENTION</div>
        ${people.length ? people.map((p) => `
          <div class="people"><div class="avatar">${esc((p.name || '?')[0])}</div>
            <div style="flex:1;min-width:0"><strong>${esc(p.name)}</strong>
              <small>${esc(p.need || 'check in')} · ${esc(p.last_contact || 'a while ago')}</small></div>
            <button class="quiet" data-followup="${esc(p.name)}">follow up</button></div>`).join('')
          : '<p class="muted">Everyone important is within reach.</p>'}</div>
      <div class="card"><div class="label" style="margin-bottom:8px">CALENDAR</div>
        <div class="schedule">${events.length ? events.map((e) => `
          <div class="event"><time>${esc((e.start || '').slice(11, 16) || '––:––')}</time>
            <div><strong>${esc(title(e))}</strong></div></div>`).join('')
          : '<p class="muted">No events loaded.</p>'}</div></div>
      ${decisions.length ? `<div class="card"><div class="label" style="margin-bottom:8px">DECISIONS WAITING</div>
        ${decisions.map((dec) => `<div class="insight decision"><div class="dot"></div>
          <div style="flex:1"><strong>${esc(title(dec))}</strong>
          <button class="quiet" data-open="${esc(dec.id)}">open record →</button></div></div>`).join('')}</div>` : ''}
      <div class="card"><div class="label" style="margin-bottom:8px">RECENT CHANGES</div>
        ${changes.length ? changes.map((e) => `
          <div class="factor"><span>${esc(e.type)} · ${esc(e.payload?.title || e.payload?.entity_id || '')}</span>
            <b>${relTime(e.created_at)}</b></div>`).join('') : '<p class="muted">No events yet.</p>'}</div>
    </div>
  </details>`;
}

export async function renderCommand(root, data, reload = () => {}) {
  root.innerHTML = `<div class="grid command" style="grid-template-columns:1fr">
    ${nowBar(data)}
    ${heroCard(data)}
    ${planCard(data)}
    ${prioritiesCard(data)}
    ${signalsCard(data)}
    ${contextDrawer(data)}
    ${askCard()}
  </div>`;

  // quick add — capture with #tags and +project, auto-classified by the core
  const quickAdd = async () => {
    const input = $('#quickAdd', root);
    const raw = input.value.trim();
    if (!raw) return;
    const { text, extra } = parseQuickAdd(raw);
    try {
      const res = await api.capture(text, undefined, extra);
      toast(`Captured as ${res.entity.kind}${extra.project ? ` · +${extra.project}` : ''}${extra.tags?.length ? ` · ${extra.tags.map((t) => '#' + t).join(' ')}` : ''}`);
      input.value = '';
      reload();
    } catch (err) { toast(err.message, 'error'); }
  };
  $('#quickAddGo', root)?.addEventListener('click', quickAdd);
  $('#quickAdd', root)?.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); quickAdd(); } });

  // start a planned task
  $$('[data-start-task]', root).forEach((b) => b.addEventListener('click', async () => {
    try {
      await api.updateEntity(b.dataset.startTask, { status: 'in-progress' });
      toast('Started — task is now in-progress');
      reload();
    } catch (err) { toast(err.message, 'error'); }
  }));

  $$('[data-open]', root).forEach((b) => b.addEventListener('click', () =>
    openEntity(b.dataset.open, { onChange: reload })));

  $('#askForm', root)?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = $('#askInput', root);
    const message = input.value.trim();
    if (!message) return;
    const box = $('#askAnswer', root);
    box.innerHTML = '<div class="skel" style="width:60%"></div>';
    try {
      const res = await api.ask(message);
      if (res.status === 'approval_required') {
        box.innerHTML = `<div class="error-box"><b>Approval needed (risk ${res.policy.risk}).</b> ${esc(res.answer)}
          <div style="margin-top:10px"><button class="primary" data-nav="workflows">Open approvals inbox</button></div>
          <p class="muted tiny">${esc(res.explanation || '')} · every action stays in the audit log</p></div>`;
      } else {
        box.innerHTML = `<div class="insight"><div class="dot"></div><div style="flex:1;min-width:0"><p>${esc(res.answer)}</p>
          <span class="confidence">${esc(res.provider || '')} · ${res.context_summary.entities_used} entities ·
            ${res.context_summary.memories_used} memories · ${Math.round((res.context_summary.confidence || 0) * 100)}%</span>
          <div class="reasoning">Intent ${esc(res.plan?.intent?.intent || '—')} · agent ${esc(res.plan?.agent || '—')} · risk ${res.policy?.risk}</div>
          ${res.verification ? `<div class="reasoning">Verified: ${esc(res.verification.join(' · '))}</div>` : ''}
        </div></div>`;
      }
    } catch (err) {
      box.innerHTML = errorBox(err);
    }
  });
}
