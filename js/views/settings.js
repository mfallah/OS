// Settings & System Health: automation level, notification policy, data
// ownership, observability (health, audit log, event stream, integrations).
import { api } from '../api.js';
import { $, $$, esc, pill, toast, relTime } from '../ui.js';

const AUTOMATION = [
  { id: 'observer', name: 'Observer', desc: 'Watch and recommend only' },
  { id: 'assistant', name: 'Assistant', desc: 'Perform low-risk internal actions' },
  { id: 'delegate', name: 'Delegate', desc: 'Run approved workflows on schedule' },
  { id: 'autopilot', name: 'Autopilot', desc: 'Strict predefined policies only — approvals still enforced' },
];

export async function renderSettings(root, data, reload) {
  const [health, audit, events, policy] = await Promise.all([
    api.health().catch((e) => ({ error: e.message })),
    api.audit().catch(() => ({ items: [] })),
    api.events().catch(() => ({ items: [] })),
    api.get('/api/notifications/policy').catch(() => ({})),
  ]);

  root.innerHTML = `<div class="grid">
    <section class="card">
      <div class="card-head"><div><h2>Automation level</h2>
        <span class="muted">Autonomy never overrides approvals — risk 2+ always asks</span></div></div>
      ${AUTOMATION.map((a, i) => `<div class="people">
        <button class="check ${i === 1 ? 'done' : ''}" data-auto="${a.id}" aria-label="Set ${a.name}">${i === 1 ? '✓' : ''}</button>
        <div><strong>${a.name}</strong><small>${a.desc}</small></div></div>`).join('')}
      <p class="reasoning">Stored locally as your preference; the permission engine always has the final word.</p>
    </section>

    <section class="card">
      <div class="card-head"><div><h2>System health</h2><span class="muted">Observability for every subsystem</span></div></div>
      ${health.error ? `<div class="error-box">${esc(health.error)}</div>` : `
        ${Object.entries(health.components || {}).map(([k, v]) => `
          <div class="bar-row"><div class="bar-label"><span>${esc(k)}</span>
            <b style="color:var(--accent-ink)">${typeof v === 'object' ? Object.values(v).join(' · ') : esc(v)}</b></div>
            <div class="bar"><i style="width:100%"></i></div></div>`).join('')}
        <p class="tiny muted">core v${esc(health.core_version)} · persistence: ${esc(health.persistence)} · auth: ${esc(health.auth)}</p>
        <p class="tiny muted">entities ${health.counts?.entities} · memories ${health.counts?.memories} · pending approvals ${health.counts?.pending_approvals}</p>`}
    </section>

    <section class="card">
      <div class="card-head"><div><h2>Notification policy</h2><span class="muted">Attention rules, in your hands</span></div></div>
      <form id="policyForm">
        <div class="field"><label>Daily notification budget</label>
          <input name="daily_budget" type="number" value="${esc(policy.daily_budget ?? 12)}"></div>
        <div class="field"><label>Urgency threshold</label>
          <select name="urgency_threshold">${['Urgent', 'Important', 'Useful', 'Interesting'].map((o) => `<option ${policy.urgency_threshold === o ? 'selected' : ''}>${o}</option>`).join('')}</select></div>
        <div class="field"><label><input type="checkbox" name="digest_mode" ${policy.digest_mode ? 'checked' : ''} style="width:auto;min-height:0;margin-right:8px">Digest mode (non-urgent → digest)</label></div>
        <button class="primary" type="submit">Save policy</button>
      </form>
    </section>

    <section class="card">
      <div class="card-head"><div><h2>Your data</h2><span class="muted">Ownership is the default</span></div></div>
      <div class="view-list">
        <div class="factor"><span>Export everything (entities, graph, memories, events)</span><button class="secondary" data-export-all>Export</button></div>
        <div class="factor"><span>Audit history — every sensitive decision, forever</span><b>${audit.items?.length ?? 0} records</b></div>
        <div class="factor"><span>Event stream — the source of truth</span><b>${events.items?.length ?? 0} recent</b></div>
      </div>
    </section>

    <section class="card span-2">
      <div class="card-head"><div><h2>Audit log</h2><span class="muted">Who did what, with which permission, at which risk</span></div></div>
      <div class="view-list">${(audit.items || []).slice(0, 12).map((a) => `
        <div class="factor"><span>${esc(a.action)} · ${esc(a.permission)} · risk ${a.risk}${a.approved ? ' · approved' : ''}</span>
          <b>${a.result?.allowed ? '✓ allowed' : '✗ blocked'} · ${relTime(a.created_at)}</b></div>`).join('') || '<p class="muted">No audit records yet.</p>'}</div>
    </section>

    <section class="card span-2">
      <div class="card-head"><div><h2>Event stream</h2><span class="muted">Every mutation is an event — the OS is replayable</span></div></div>
      <div class="view-list">${(events.items || []).slice(0, 12).map((e) => `
        <div class="factor"><span>${esc(e.type)} · ${esc(e.payload?.title || e.payload?.entity_id || '')}</span>
          <b>${relTime(e.created_at)}</b></div>`).join('') || '<p class="muted">No events yet.</p>'}</div>
    </section>
  </div>`;

  $$('[data-auto]', root).forEach((b) => b.onclick = () => {
    localStorage.setItem('myos.automation', b.dataset.auto);
    toast(`Automation set to ${b.dataset.auto} — grants nothing above approvals`);
    $$('[data-auto]', root).forEach((x) => { x.classList.remove('done'); x.textContent = ''; });
    b.classList.add('done'); b.textContent = '✓';
  });
  const savedAuto = localStorage.getItem('myos.automation') || 'assistant';
  const autoBtn = $(`[data-auto="${savedAuto}"]`, root);
  if (autoBtn) {
    $$('[data-auto]', root).forEach((x) => { x.classList.remove('done'); x.textContent = ''; });
    autoBtn.classList.add('done'); autoBtn.textContent = '✓';
  }

  $('#policyForm', root).onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    await api.post('/api/notifications/policy', {
      daily_budget: Number(f.daily_budget.value),
      urgency_threshold: f.urgency_threshold.value,
      digest_mode: f.digest_mode.checked,
    });
    toast('Notification policy saved');
  };
  $('[data-export-all]', root).onclick = async () => {
    const dump = await api.exportAll();
    const blob = new Blob([JSON.stringify(dump, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `myos-export-${Date.now()}.json`; a.click();
    URL.revokeObjectURL(url);
    toast(`Exported ${dump.counts.entities} entities, ${dump.counts.memories} memories`);
  };
}
