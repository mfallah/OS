// Notifications: deliverable vs held, with explainable policy per item.
import { api } from '../api.js';
import { $, $$, esc, pill, toast, relTime, emptyState } from '../ui.js';

export async function renderNotifications(root, data, reload) {
  let res;
  try { res = await api.notifications(); }
  catch (err) { root.innerHTML = `<div class="error-box">${esc(err.message)}</div>`; return; }

  const row = (n, held) => `
    <article class="entity">
      <div class="entity-top"><div><h3>${esc(n.title)}</h3>
        <span class="muted">${esc(n.body || '')}</span></div>
        <span class="pill ${n.category === 'Urgent' ? 'red' : n.category === 'Important' ? 'amber' : n.category === 'Noise' ? 'grey' : ''}">${esc(n.category)}</span></div>
      <p class="reasoning">${held ? `Held: ${esc(n.held_reason)}` : `Delivered: ${esc(n.delivered_reason || 'passes policy')}`}</p>
      <p class="tiny muted">Why it exists: ${esc(n.why || '—')} · ${relTime(n.created_at)}</p>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="quiet" data-read="${esc(n.id)}">Mark read</button>
        <button class="quiet" data-snooze="${esc(n.id)}">Snooze 1 day</button>
        <button class="quiet" data-archive="${esc(n.id)}">Archive</button>
      </div>
    </article>`;

  root.innerHTML = `<div class="card full">
    <div class="card-head"><div><h2>Notifications</h2>
      <span class="muted">Budget ${res.delivered.length}/${res.policy.daily_budget} used · quiet hours ${res.policy.quiet_hours.join('–')}${res.quiet_now ? ' · quiet NOW' : ''} · threshold ${esc(res.policy.urgency_threshold)}</span></div></div>
    <div class="tabs"><button class="active">Delivered (${res.delivered.length})</button><button disabled style="opacity:.6">Held for digest/quiet (${res.held.length})</button></div>
    <div class="view-list">
      ${res.delivered.map((n) => row(n, false)).join('') || emptyState('Nothing to deliver.', 'Your attention budget is intact.')}
      ${res.held.length ? `<div class="label" style="margin-top:14px">HELD — PROTECTED BY YOUR POLICY</div>` : ''}
      ${res.held.map((n) => row(n, true)).join('')}
    </div></div>`;

  $$('[data-read]', root).forEach((b) => b.onclick = async () => { await api.notificationAction(b.dataset.read, 'read'); renderNotifications(root, data, reload); });
  $$('[data-snooze]', root).forEach((b) => b.onclick = async () => {
    const until = new Date(Date.now() + 86400000).toISOString();
    await api.notificationAction(b.dataset.snooze, 'snooze', { until });
    toast('Snoozed until tomorrow'); renderNotifications(root, data, reload);
  });
  $$('[data-archive]', root).forEach((b) => b.onclick = async () => { await api.notificationAction(b.dataset.archive, 'archive'); renderNotifications(root, data, reload); });
}
