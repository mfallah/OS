// Reviews: weekly executive review + monthly state of life, from real data.
import { api } from '../api.js';
import { $, esc, pill, emptyState } from '../ui.js';

function listOr(items, render, empty = 'Nothing recorded.') {
  return items?.length ? items.map(render).join('') : `<p class="muted">${empty}</p>`;
}

export async function renderReviews(root) {
  root.innerHTML = '<div class="loading">Generating reviews from your event history…</div>';
  let weekly, monthly;
  try {
    [weekly, monthly] = await Promise.all([api.weekly(), api.monthly()]);
  } catch (err) {
    root.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
    return;
  }

  root.innerHTML = `<div class="grid">
    <section class="card span-2">
      <div class="card-head"><div><div class="eyebrow">WEEKLY EXECUTIVE REVIEW</div>
        <h2 style="margin-top:6px">A clear week starts here.</h2></div>
        <span class="pill">${esc(weekly.period)}</span></div>
      <div class="stat-grid">
        <div class="stat"><b>${weekly.counts.completed}</b><span>completed</span></div>
        <div class="stat"><b>${weekly.counts.created}</b><span>created</span></div>
        <div class="stat"><b>${weekly.unfinished.open_tasks}</b><span>open tasks</span></div>
        <div class="stat"><b>${weekly.unfinished.overdue}</b><span>overdue</span></div>
      </div>
      <div class="detail-section"><div class="label">WINS</div>
        ${listOr(weekly.wins, (w) => `<div class="factor"><span>✓ ${esc(w.title || 'untitled')}</span></div>`, 'No completions logged — an honest signal, not a failure.')}</div>
      <div class="detail-section"><div class="label">RISKS</div>
        ${listOr(weekly.risks, (r) => `<div class="insight risk"><div class="dot"></div><div><strong>${esc(r.title)}</strong><p>${esc(r.body)}</p></div></div>`, 'No active risks detected.')}</div>
      <div class="detail-section"><div class="label">OPPORTUNITIES</div>
        ${listOr(weekly.opportunities, (o) => `<div class="insight"><div class="dot"></div><div><strong>${esc(o.title)}</strong><p>${esc(o.body)}</p></div></div>`, 'No opportunities detected this week.')}</div>
      <div class="detail-section"><div class="label">RELATIONSHIPS NEEDING CARE</div>
        ${listOr(weekly.relationships, (r) => `<span class="chip">${esc(r)}</span>`, 'Everyone is within reach.')}</div>
      <div class="detail-section"><div class="label">NEXT WEEK STRATEGY</div>
        ${listOr(weekly.next_week_strategy, (s) => `<div class="factor"><span>→ ${esc(s)}</span></div>`)}</div>
    </section>

    <section class="card span-2">
      <div class="card-head"><div><div class="eyebrow">MONTHLY STATE OF LIFE</div>
        <h2 style="margin-top:6px">The whole board, honestly.</h2></div>
        <span class="pill">${esc(monthly.period)}</span></div>
      <div class="stat-grid">
        <div class="stat"><b>${monthly.state_of_life.work.completed_30d}</b><span>tasks done · 30d</span></div>
        <div class="stat"><b>${monthly.state_of_life.projects.length}</b><span>projects</span></div>
        <div class="stat"><b>${monthly.state_of_life.learning}</b><span>learning objectives</span></div>
        <div class="stat"><b>${monthly.state_of_life.relationships.needing_attention}</b><span>relationships need care</span></div>
        <div class="stat"><b>${monthly.state_of_life.ideas}</b><span>ideas</span></div>
        <div class="stat"><b>${monthly.state_of_life.decisions.open}</b><span>open decisions</span></div>
        <div class="stat"><b>${monthly.state_of_life.cognitive_load.score}</b><span>cognitive load</span></div>
        <div class="stat"><b>${monthly.state_of_life.life_debt.total}</b><span>life debt</span></div>
      </div>
      <div class="detail-section"><div class="label">PROJECTS</div>
        ${listOr(monthly.state_of_life.projects, (p) => `<div class="factor"><span>${esc(p.name)}</span><b>${esc(p.status)} · health ${p.health ?? '—'}</b></div>`)}</div>
      <div class="detail-section"><div class="label">LIFE DEBT BREAKDOWN</div>
        ${listOr(monthly.state_of_life.life_debt.items, (i) => `<div class="factor"><span>${esc(i.detail)}</span><b>${i.count}</b></div>`)}</div>
      <div class="detail-section"><div class="label">NEXT MONTH STRATEGY</div>
        ${listOr(monthly.strategy, (s) => `<div class="factor"><span>→ ${esc(s)}</span></div>`)}</div>
    </section>
  </div>`;
}
