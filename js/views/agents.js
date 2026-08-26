// Agents & Skills & Tools: inspectable registries with real enable/test flows.
import { api } from '../api.js';
import { $, $$, esc, pill, toast, formDialog, confirmDialog, emptyState } from '../ui.js';

let tab = 'agents';

export async function renderAgents(root, data, reload) {
  root.innerHTML = `<div class="card full">
    <div class="card-head"><div><h2>Agents, skills & tools</h2>
      <span class="muted">Specialized capabilities over one shared context — inspectable, tunable, yours</span></div>
      <button class="primary" data-new-skill>＋ Create skill</button></div>
    <div class="tabs" role="tablist">
      ${['agents', 'skills', 'tools & integrations'].map((t) => `<button class="${tab === t ? 'active' : ''}" data-tab="${t}" role="tab">${t[0].toUpperCase() + t.slice(1)}</button>`).join('')}
    </div>
    <div id="tabBody"><div class="loading">Loading registry…</div></div>
  </div>`;
  $$('[data-tab]', root).forEach((b) => b.onclick = () => { tab = b.dataset.tab; renderAgents(root, data, reload); });
  $('[data-new-skill]', root).onclick = () => createSkill(reload);

  const body = $('#tabBody', root);
  try {
    if (tab === 'agents') await renderAgentsTab(body, reload);
    else if (tab === 'skills') await renderSkillsTab(body, reload);
    else await renderToolsTab(body);
  } catch (err) {
    body.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
  }
}

async function renderAgentsTab(body, reload) {
  const { items } = await api.agents();
  body.innerHTML = `<div class="view-list">${items.map((a) => `
    <article class="entity">
      <div class="entity-top"><div><h3>◎ ${esc(a.name)}</h3>
        <span class="muted">${esc(a.description || '')}</span></div>
        <span class="pill ${a.status === 'disabled' ? 'grey' : ''}">${esc(a.status)}</span></div>
      <div class="chip-row">${(a.allowed_skills || []).slice(0, 4).map((s) => `<span class="chip">${esc(s)}</span>`).join('')}</div>
      <p class="tiny muted">Domain ${esc(a.domain)} · risk policy: ${esc(a.risk_policy)} · memory scope: ${(a.memory_scope || []).join(', ')} · v${esc(a.version)}</p>
      <p class="reasoning">Instructions: ${esc(a.instructions || '')}</p>
      <p class="tiny muted">Evaluated on: ${(a.eval || []).map(esc).join(' · ')}</p>
      <button class="${a.status === 'disabled' ? 'secondary' : 'quiet'}" data-toggle-agent='${esc(JSON.stringify({ id: a.id, status: a.status }))}'>
        ${a.status === 'disabled' ? 'Enable' : 'Disable'}</button>
    </article>`).join('') || emptyState('No agents registered.')}</div>`;
  $$('[data-toggle-agent]', body).forEach((b) => b.onclick = async () => {
    const a = JSON.parse(b.dataset.toggleAgent);
    await api.agentStatus(a.id, a.status === 'disabled' ? 'active' : 'disabled');
    toast(`Agent ${a.status === 'disabled' ? 'enabled' : 'disabled'}`);
    reload();
  });
}

const SKILL_FIELDS = [
  { name: 'name', label: 'Name (kebab-case)' },
  { name: 'purpose', label: 'Purpose' },
  { name: 'instructions', label: 'Instructions', type: 'textarea' },
  { name: 'domain', label: 'Domain' },
  { name: 'tools', label: 'Tools (comma separated)', list: true },
  { name: 'guardrails', label: 'Guardrails (comma separated)', list: true },
];

async function createSkill(reload) {
  const v = await formDialog({ title: 'Create skill', eyebrow: 'SKILL BUILDER', fields: SKILL_FIELDS });
  if (!v) return;
  try {
    await api.createSkill({ permissions: ['READ_DATA'], ...v });
    toast('Skill created at v1.0.0'); reload();
  } catch (err) { toast(err.message, 'error'); }
}

async function renderSkillsTab(body, reload) {
  const { items } = await api.skills();
  body.innerHTML = `<div class="view-list">${items.map((s) => `
    <article class="entity">
      <div class="entity-top"><div><h3>⚒ ${esc(s.name)}</h3>
        <span class="muted">${esc(s.purpose || '')}</span></div>
        <span class="pill ${s.status !== 'active' ? 'grey' : ''}">v${esc(s.version)} · ${esc(s.status)}${s.builtin ? ' · builtin' : ''}</span></div>
      <p class="reasoning">${esc(s.instructions || '')}</p>
      <div class="chip-row">${(s.tools || []).map((t) => `<span class="chip">${esc(t)}</span>`).join('')}</div>
      ${(s.composed_of || []).length ? `<p class="tiny muted">Composes: ${s.composed_of.map(esc).join(' → ')}</p>` : ''}
      <p class="tiny muted">${(s.changelog || []).length} versions · guardrails: ${(s.guardrails || []).map(esc).join(' · ') || 'none'}</p>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="secondary" data-test-skill="${esc(s.id)}">Test</button>
        <button class="quiet" data-edit-skill='${esc(JSON.stringify(s))}'>Edit</button>
        <button class="quiet" data-dup-skill="${esc(s.id)}">Duplicate</button>
        <button class="quiet" data-toggle-skill='${esc(JSON.stringify({ id: s.id, status: s.status }))}'>${s.status === 'active' ? 'Disable' : 'Enable'}</button>
        ${!s.builtin ? `<button class="quiet" data-del-skill="${esc(s.id)}" style="color:var(--red)">Delete</button>` : ''}
      </div>
    </article>`).join('') || emptyState('No skills yet.')}</div>`;

  $$('[data-test-skill]', body).forEach((b) => b.onclick = async () => {
    const result = await api.testSkill(b.dataset.testSkill, {});
    toast(result.ok ? `Test passed — tools: ${result.would_use_tools.join(', ') || 'none'}` : `Missing inputs: ${result.missing_inputs.join(', ') || result.reason}`, result.ok ? 'ok' : 'error');
  });
  $$('[data-toggle-skill]', body).forEach((b) => b.onclick = async () => {
    const s = JSON.parse(b.dataset.toggleSkill);
    await api.updateSkill(s.id, { status: s.status === 'active' ? 'disabled' : 'active' });
    reload();
  });
  $$('[data-dup-skill]', body).forEach((b) => b.onclick = async () => {
    await api.duplicateSkill(b.dataset.dupSkill);
    toast('Duplicated as a new draft skill'); reload();
  });
  $$('[data-del-skill]', body).forEach((b) => b.onclick = async () => {
    const yes = await confirmDialog({ title: 'Delete this skill?', body: 'Custom skill removed with audit. Builtin skills can only be disabled.', confirmLabel: 'Delete', danger: true });
    if (!yes) return reload();
    try { await api.deleteSkill(b.dataset.delSkill); toast('Skill deleted'); } catch (err) { toast(err.message, 'error'); }
    reload();
  });
  $$('[data-edit-skill]', body).forEach((b) => b.onclick = async () => {
    const s = JSON.parse(b.dataset.editSkill);
    const v = await formDialog({ title: `Edit ${s.name}`, eyebrow: `SKILL v${s.version}`, fields: SKILL_FIELDS, values: s });
    if (!v) return;
    await api.updateSkill(s.id, { ...v, bump_version: true, changelog_note: 'edited in UI' });
    toast('Saved as new minor version'); reload();
  });
}

async function renderToolsTab(body) {
  const [toolsRes, integrations] = await Promise.all([api.tools(), api.integrations()]);
  const integ = [
    { name: 'Telegram', info: integrations.telegram },
    { name: 'Bale', info: integrations.bale },
    { name: 'Voice pipeline', info: integrations.voice },
  ];
  body.innerHTML = `
    <div class="label">INTEGRATION ADAPTERS</div>
    <div class="view-list" style="margin:10px 0 18px">
      ${integ.map((i) => `<article class="entity">
        <div class="entity-top"><h3>${esc(i.name)}</h3>
          <span class="pill ${i.info.configured || i.info.stt_configured ? '' : 'amber'}">${i.info.mode || (i.info.stt_configured ? 'live' : 'simulated')}</span></div>
        <p class="tiny muted">${i.info.missing_env?.length ? `Setup: set ${i.info.missing_env.map(esc).join(', ')} as environment variables — never in the repo.` : 'Configured and live.'}</p>
        ${i.info.capabilities ? `<div class="chip-row">${i.info.capabilities.slice(0, 6).map((c) => `<span class="chip">${esc(c)}</span>`).join('')}</div>` : ''}
      </article>`).join('')}
    </div>
    <div class="label">CORE TOOLS</div>
    <div class="view-list" style="margin-top:10px">
      ${(toolsRes.items || []).map((t) => `<article class="entity">
        <div class="entity-top"><h3>⚙ ${esc(t.tool)}</h3>
          <span class="pill ${t.configured ? '' : 'grey'}">${esc(t.mode)}${t.configured ? ' · configured' : ''}</span></div>
        <p class="tiny muted">permissions: ${(t.permissions || []).map(esc).join(', ') || 'internal'} · read ${t.capabilities?.read ? '✓' : '✗'} · write ${t.capabilities?.write ? '✓' : '✗'}</p>
        <p class="reasoning">${t.mode === 'simulated' ? 'No credentials configured — writes are held in a simulated outbox instead of pretending to succeed.' : 'Live and permission-checked.'}</p>
      </article>`).join('')}
    </div>
    <p class="muted tiny" style="margin-top:14px">MCP servers register as extensions with their own discovery, permissions, timeouts and idempotency — the core never blocks on them.</p>`;
}
