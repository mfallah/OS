// Command Center: always answers "What matters now?" from live system state.
import { api } from '../api.js';
import { $, $$, esc, title, pill, relTime, dueLabel, DONE, errorBox, toast } from '../ui.js';
import { openEntity } from '../detail.js';

function objectiveCard(d) {
  const rec = d.recommended_next_action || {};
  return `<section class="card span-2">
    <div class="card-head">
      <div><div class="eyebrow">TODAY · ${esc(d.date)}</div>
        <h2 style="margin-top:6px">Your attention, intentionally allocated.</h2></div>
      <button class="primary" data-action="capture">＋ Capture</button>
    </div>
    <div class="objective"><div class="orb">✦</div>
      <div><span class="label">MAIN OBJECTIVE</span>
        <strong>${esc(d.objective?.title)}</strong>
        <small>${esc(d.objective?.why || '')} ${d.objective?.estimate ? `· ~${d.objective.estimate} min` : ''}</small></div>
    </div>
    ${rec.action ? `<div class="objective warm"><div class="orb">→</div>
      <div><span class="label">RECOMMENDED NEXT ACTION</span>
        <strong>${esc(rec.action)}</strong><small>${esc(rec.reason || '')}</small></div></div>` : ''}
  </section>`;
}

function planCard(d) {
  const plan = d.today_plan || { items: [] };
  const items = plan.items?.length ? plan.items.map((i) => `
    <div class="task"><div class="check" data-start-task="${esc(i.task_id)}" role="button" tabindex="0" aria-label="Start ${esc(i.title)}">▸</div>
      <div style="flex:1"><div class="title">${esc(i.title)}</div>
        <div class="meta">${i.estimate} min · ${esc(i.energy || '')} · <span class="reasoning">${esc(i.why)}</span></div></div>
    </div>`).join('') : '<p class="muted">Nothing scheduled — the day is genuinely open.</p>';
  return `<section class="card">
    <div class="card-head"><div><h2>Today's plan</h2>
      <span class="muted">${plan.planned_minutes ?? 0} min planned · ${plan.slack_hours ?? '—'}h slack protected</span></div>
      <span class="pill">${esc(plan.rule ? 'capacity-aware' : '')}</span></div>
    ${items}
    ${plan.deliberately_skipped?.length ? `<p class="muted tiny">Deliberately skipped: ${plan.deliberately_skipped.map((s) => esc(s.task)).join(' · ')}</p>` : ''}
  </section>`;
}

function capacityCard(d) {
  const s = d.state || {};
  const load = s.cognitive_load || { factors: [] };
  const debt = s.life_debt || { items: [] };
  return `<section class="card">
    <div class="card-head"><div><h2>Capacity & cognitive load</h2>
      <span class="muted">Explained, never just a number</span></div></div>
    <div class="bar-row"><div class="bar-label"><span>Cognitive load · ${esc(load.band || '')}</span><b>${load.score ?? '—'}/100</b></div>
      <div class="bar ${load.score >= 75 ? 'red' : load.score >= 50 ? 'amber' : ''}"><i style="width:${load.score || 0}%"></i></div></div>
    ${(load.factors || []).slice(0, 5).map((f) => `<div class="factor"><span>${f.count}× ${esc(f.factor)}</span><b>+${f.contribution}</b></div>`).join('')}
    <div class="detail-section">
      <div class="bar-label"><span>Energy (inferred)</span><b>${esc(s.energy?.level || '—')}</b></div>
      <div class="bar-label"><span>Attention budget</span><b>${s.attention_budget?.deep_work_hours_available ?? '—'}h deep work</b></div>
      <div class="bar-label"><span>Life debt</span><b>${debt.total ?? 0} obligations</b></div>
      ${(debt.items || []).slice(0, 3).map((i) => `<div class="factor"><span>${esc(i.detail)}</span><b>${i.count}</b></div>`).join('')}
      <p class="muted tiny">${esc(debt.explanation || '')}</p>
    </div>
  </section>`;
}

function insightsCard(d) {
  const items = (d.insights || []).slice(0, 5);
  return `<section class="card">
    <div class="card-head"><div><div class="eyebrow">EXECUTIVE SIGNAL</div>
      <h2 style="margin-top:6px">What your OS sees</h2></div><span class="pill">live context</span></div>
    ${items.length ? items.map((i) => `
      <div class="insight ${i.kind === 'Risk' ? 'risk' : ''} ${i.kind === 'Decision required' ? 'decision' : ''}">
        <div class="dot"></div><div style="flex:1">
          <strong>${esc(i.title)}</strong><p>${esc(i.body)}</p>
          ${i.action ? `<p class="muted">→ ${esc(i.action)}</p>` : ''}
          <span class="confidence">${esc(i.kind)} · confidence ${Math.round((i.confidence || 0) * 100)}%</span>
          <div class="reasoning">Why: ${esc(i.reasoning || '')}</div>
        </div></div>`).join('') : '<p class="muted">No strong signals right now. Clear board.</p>'}
  </section>`;
}

function prioritiesCard(d) {
  const open = (d.tasks || []).filter((t) => !DONE.has(t.status));
  const overdue = open.filter((t) => dueLabel(t) === 'Overdue');
  const today = open.filter((t) => ['Today', 'Overdue'].includes(dueLabel(t)));
  const list = [...overdue, ...today.filter((t) => !overdue.includes(t))].slice(0, 4);
  return `<section class="card">
    <div class="card-head"><div><h2>Top priorities</h2>
      <span class="muted">${open.length} open loops total</span></div>
      <button class="quiet" data-nav="tasks">View all →</button></div>
    ${list.length ? list.map(taskRow).join('') : '<p class="muted">Nothing due today — protect the space.</p>'}
  </section>`;
}

export function taskRow(t) {
  const done = DONE.has(t.status);
  return `<div class="task ${done ? 'done-style' : ''}">
    <button class="check ${done ? 'done' : ''}" data-task-toggle="${esc(t.id)}" aria-label="${done ? 'Reopen' : 'Complete'} ${esc(t.title)}">${done ? '✓' : ''}</button>
    <div style="flex:1;min-width:0"><div class="title">${esc(t.title)}</div>
      <div class="meta">${esc(t.project || 'Inbox')} · ${t.estimate ?? '—'} min · ${esc(t.energy || '')}${t.due ? ` · ${esc(dueLabel(t))}` : ''}</div></div>
    <span class="tag">${esc(t.priority || '')}</span>
    <button class="quiet" data-open="${esc(t.id)}" aria-label="Open task">›</button>
  </div>`;
}

function relationshipsCard(d) {
  const people = d.relationship_attention || [];
  return `<section class="card">
    <div class="card-head"><div><h2>People needing attention</h2>
      <span class="muted">Care, observed — not scored</span></div>
      <button class="quiet" data-nav="people">See relationships →</button></div>
    ${people.length ? people.map((p) => `
      <div class="people"><div class="avatar">${esc((p.name || '?')[0])}</div>
        <div style="flex:1"><strong>${esc(p.name)}</strong>
          <small>${esc(p.need || 'check in')} · last contact ${esc(p.last_contact || 'a while ago')}</small></div>
        <button class="quiet" data-followup="${esc(p.name)}">Follow up</button></div>`).join('')
      : '<p class="muted">Everyone important is within reach right now.</p>'}
  </section>`;
}

function projectsCard(d) {
  const projects = (d.projects || []).slice(0, 3);
  return `<section class="card">
    <div class="card-head"><div><h2>Project health</h2>
      <span class="muted">Status with reasoning</span></div>
      <button class="quiet" data-nav="projects">Portfolio →</button></div>
    ${projects.map((p) => {
      const h = p.health || {};
      return `<div class="bar-row">
        <div class="bar-label"><span><b>${esc(title(p))}</b> · ${esc(h.explanation?.split(';')[0] || '')}</span>
          <b>${h.score ?? '—'}/100 ${pill(h.status, h.status === 'at-risk' ? 'red' : h.status === 'watch' ? 'amber' : '')}</b></div>
        <div class="bar ${h.status === 'at-risk' ? 'red' : h.status === 'watch' ? 'amber' : ''}"><i style="width:${h.score || 0}%"></i></div>
      </div>`; }).join('') || '<p class="muted">No active projects yet.</p>'}
  </section>`;
}

function decisionsCard(d) {
  const pending = d.pending_decisions || [];
  if (!pending.length) return '';
  return `<section class="card">
    <div class="card-head"><div><h2>Decisions waiting on you</h2>
      <span class="muted">Unresolved decisions carry load</span></div></div>
    ${pending.map((dec) => `<div class="insight decision"><div class="dot"></div>
      <div style="flex:1"><strong>${esc(title(dec))}</strong>
        <p>${esc(dec.context || '')}</p>
        <button class="secondary" data-open="${esc(dec.id)}">Open decision record</button></div></div>`).join('')}
  </section>`;
}

function calendarCard(d) {
  const events = (d.calendar || []).slice(0, 4);
  const density = d.state?.calendar_density || {};
  return `<section class="card">
    <div class="card-head"><div><h2>Calendar context</h2>
      <span class="muted">${density.events_today ?? 0} events today · fragmentation ${esc(density.fragmentation || 'low')}</span></div></div>
    <div class="schedule">${events.length ? events.map((e) => `
      <div class="event"><time>${esc((e.start || '').slice(11, 16) || '––:––')}</time>
        <div><strong>${esc(title(e))}</strong><small>${esc(e.kind === 'calendar_event' ? (e.location || 'calendar') : '')}</small></div></div>`).join('')
      : '<p class="muted">No calendar events loaded. Connect a calendar integration in Settings or add events manually.</p>'}</div>
    <div class="objective" style="margin-top:16px"><div class="orb">◷</div>
      <div><span class="label">CAPACITY CHECK</span>
        <strong>${d.state?.attention_budget?.deep_work_hours_available ?? '—'}h unallocated deep work</strong>
        <small>${esc(d.state?.attention_budget?.note || '')}</small></div></div>
  </section>`;
}

function changesCard(d) {
  const changes = (d.recent_changes || []).slice(0, 6);
  return `<section class="card">
    <div class="card-head"><div><h2>Recent changes</h2><span class="muted">Event-sourced — everything leaves a trail</span></div></div>
    ${changes.length ? `<div class="view-list">${changes.map((e) => `
      <div class="factor"><span>${esc(e.type)} · ${esc(e.payload?.title || e.payload?.entity_id || '')}</span>
        <b>${relTime(e.created_at)}</b></div>`).join('')}</div>` : '<p class="muted">No events yet.</p>'}
  </section>`;
}

function askCard() {
  return `<section class="card span-2">
    <div class="card-head"><div><div class="eyebrow">ASK MYOS</div>
      <h2 style="margin-top:6px">Conversation through the real orchestrator</h2></div></div>
    <form id="askForm" style="display:flex;gap:8px;flex-wrap:wrap">
      <input id="askInput" style="flex:1;min-width:200px;min-height:44px;border:1px solid var(--line);border-radius:9px;padding:0 14px"
        placeholder='Try “plan my day”, “what matters now”, “send an email to Sara about the research”'>
      <button class="primary" type="submit">Ask</button>
    </form>
    <div id="askAnswer" style="margin-top:12px"></div>
  </section>`;
}

export async function renderCommand(root, data) {
  root.innerHTML = `<div class="grid command">
    ${objectiveCard(data)}
    ${prioritiesCard(data)}
    ${insightsCard(data)}
    ${planCard(data)}
    ${capacityCard(data)}
    ${decisionsCard(data)}
    ${relationshipsCard(data)}
    ${projectsCard(data)}
    ${calendarCard(data)}
    ${changesCard(data)}
    ${askCard()}
  </div>`;

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
        box.innerHTML = `<div class="insight"><div class="dot"></div><div style="flex:1"><p>${esc(res.answer)}</p>
          <span class="confidence">${esc(res.provider || '')} · ${res.context_summary.entities_used} entities ·
            ${res.context_summary.memories_used} memories · confidence ${Math.round((res.context_summary.confidence || 0) * 100)}%</span>
          <div class="reasoning">Intent ${esc(res.plan?.intent?.intent || '—')} · agent ${esc(res.plan?.agent || '—')} · risk ${res.policy?.risk}</div>
          ${res.verification ? `<div class="reasoning">Verified: ${esc(res.verification.join(' · '))}</div>` : ''}
        </div></div>`;
      }
    } catch (err) {
      box.innerHTML = errorBox(err);
    }
  });
}
