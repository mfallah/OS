// Workflows & Approvals: first-class automation with a real approval inbox.
import { api } from '../api.js';
import { $, $$, esc, pill, toast, relTime, emptyState } from '../ui.js';

let tab = 'workflows';

export async function renderWorkflows(root, data, reload) {
  root.innerHTML = `<div class="card full">
    <div class="card-head"><div><h2>Workflows & approvals</h2>
      <span class="muted">Trigger → context → conditions → action → verification → notification. Risk 2+ stops here until you approve.</span></div></div>
    <div class="tabs" role="tablist">
      <button class="${tab === 'workflows' ? 'active' : ''}" data-tab="workflows" role="tab">Workflows</button>
      <button class="${tab === 'approvals' ? 'active' : ''}" data-tab="approvals" role="tab">Approvals inbox</button>
      <button class="${tab === 'runs' ? 'active' : ''}" data-tab="runs" role="tab">Run history</button>
    </div>
    <div id="wfBody"><div class="loading">Loading…</div></div>
  </div>`;
  $$('[data-tab]', root).forEach((b) => b.onclick = () => { tab = b.dataset.tab; renderWorkflows(root, data, reload); });
  const body = $('#wfBody', root);
  try {
    const res = await api.workflows();
    if (tab === 'workflows') renderWfList(body, res.items, reload);
    else if (tab === 'approvals') await renderApprovals(body, reload);
    else renderRuns(body, res.runs);
  } catch (err) {
    body.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
  }
}

function renderWfList(body, items, reload) {
  body.innerHTML = `<div class="view-list">${items.map((w) => `
    <article class="entity">
      <div class="entity-top"><div><h3>⚡ ${esc(w.name)}</h3>
        <span class="muted">${esc(w.description || '')}</span></div>
        <span class="pill ${w.risk === 'external' ? 'amber' : w.risk === 'sensitive' ? 'red' : ''}">${esc(w.risk)} risk · ${esc(w.status)}</span></div>
      <p class="tiny muted">trigger ${esc(w.trigger)} · approval policy ${esc(w.approval_policy)} · notify ${esc(w.notification_policy)} · timeout ${w.timeout_seconds}s · v${esc(w.version)}</p>
      <div class="chip-row">${(w.steps || []).map((s) => `<span class="chip">${esc(s.action)}</span>`).join('')}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="primary" data-run="${esc(w.id)}">Run now</button>
        <span class="muted tiny" style="align-self:center">${w.risk === 'external' || w.risk === 'sensitive' ? 'will ask for approval (risk 2+)' : 'runs immediately, audited'}</span>
      </div>
    </article>`).join('') || emptyState('No workflows.')}</div>`;

  $$('[data-run]', body).forEach((b) => b.onclick = async () => {
    try {
      const res = await api.runWorkflow(b.dataset.run);
      if (res.status === 'approval_required') {
        toast('Approval request created — risk 2+ never runs silently', 'error');
        tab = 'approvals';
        renderWorkflows(body.closest('#app') || body, {}, reload);
      } else {
        toast(`Workflow ${res.status}: ${res.workflow}`);
        reload();
      }
    } catch (err) { toast(err.message, 'error'); }
  });
}

async function renderApprovals(body, reload) {
  const { items } = await api.approvals();
  body.innerHTML = `
    <p class="muted" style="margin-bottom:12px">Every risk-2+ action (send, external write, finance) parks here with its reason, payload and context — nothing happens until you decide. Approving re-executes through the same audited engine.</p>
    <div class="view-list">${items.length ? items.map((a) => `
      <article class="entity">
        <div class="entity-top"><div><h3>${esc(a.action)}</h3>
          <span class="muted">${esc(a.reason)}</span></div>
          <span class="pill ${a.risk >= 3 ? 'red' : 'amber'}">risk ${a.risk} · ${esc(a.permission)}</span></div>
        <p class="tiny muted">requested ${relTime(a.created_at)} · payload: <code>${esc(JSON.stringify(a.payload).slice(0, 120))}</code></p>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="primary" data-approve="${esc(a.id)}">Approve & execute</button>
          <button class="secondary" data-deny="${esc(a.id)}">Deny</button>
        </div>
      </article>`).join('') : emptyState('No pending approvals.', 'When a risky action needs you, it shows up here.')}</div>`;

  $$('[data-approve]', body).forEach((b) => b.onclick = async () => {
    try {
      const res = await api.decide(b.dataset.approve, true);
      toast(res.execution ? `Approved — workflow ${res.execution.status}` : 'Approved');
    } catch (err) { toast(err.message, 'error'); }
    reload();
  });
  $$('[data-deny]', body).forEach((b) => b.onclick = async () => {
    await api.decide(b.dataset.deny, false);
    toast('Denied — action cancelled and audited'); reload();
  });
}

function renderRuns(body, runs) {
  body.innerHTML = `<div class="view-list">${runs?.length ? runs.map((r) => `
    <article class="entity">
      <div class="entity-top"><h3>${esc(r.workflow_id)}</h3>
        <span class="pill ${r.status === 'failed' ? 'red' : r.status === 'approval_required' ? 'amber' : ''}">${esc(r.status)}</span></div>
      <p class="tiny muted">started ${relTime(r.started_at)} · ${r.steps?.length ?? 0} steps${r.error ? ` · error: ${esc(r.error)}` : ''}</p>
    </article>`).join('') : emptyState('No workflow runs yet.')}</div>`;
}
