// App bootstrap: router, shell, global events, capture, search, offline mode.
import { api, offline } from './api.js';
import { $, $$, esc, toast, relTime, title as entityTitle } from './ui.js';
import { renderCommand } from './views/command.js';
import { bindTaskRowEvents } from './views/tasks.js';
import { renderTasks } from './views/tasks.js';
import { renderProjects } from './views/projects.js';
import { renderPeople } from './views/people.js';
import { renderIdeas } from './views/ideas.js';
import { renderResearch } from './views/research.js';
import { renderReviews } from './views/reviews.js';
import { renderMemory } from './views/memory.js';
import { renderAgents } from './views/agents.js';
import { renderWorkflows } from './views/workflows.js';
import { renderNotifications } from './views/notifications.js';
import { renderSettings } from './views/settings.js';
import { openEntity } from './detail.js';

const store = {
  view: 'command',
  data: null,
  captureType: '',
};

const TITLES = {
  command: ['COMMAND CENTER', 'What matters now?'],
  tasks: ['OPEN LOOPS', 'Tasks'],
  projects: ['PORTFOLIO', 'Projects'],
  people: ['RELATIONSHIPS', 'People & attention'],
  ideas: ['IDEA GARDEN', 'Ideas'],
  research: ['RESEARCH OS', 'Research & knowledge'],
  reviews: ['REVIEWS', 'Weekly & monthly'],
  workflows: ['AUTOMATION', 'Workflows & approvals'],
  memory: ['MEMORY', 'Memory governance'],
  agents: ['CAPABILITIES', 'Agents & skills'],
  notifications: ['ATTENTION', 'Notifications'],
  settings: ['SYSTEM', 'Settings & health'],
};

const OFFLINE_SNAPSHOT = {
  date: new Date().toISOString().slice(0, 10),
  objective: { title: 'Offline — reconnect to plan', why: 'showing the last known shape of your OS', estimate: 0 },
  today_plan: { items: [], planned_minutes: 0, slack_hours: '—', deliberately_skipped: [] },
  tasks: [], projects: [], people: [], ideas: [], research: [], questions: [],
  decisions: [], learning: [], calendar: [], goals: [], insights: [],
  recent_changes: [], pending_decisions: [], relationship_attention: [],
  state: { cognitive_load: { score: 0, band: 'unknown', factors: [] }, life_debt: { total: 0, items: [] },
           energy: { level: '—' }, attention_budget: {}, calendar_density: {}, workload: { open_tasks: 0, overdue: 0 } },
  recommended_next_action: { action: 'Reconnect', reason: 'live planning needs the API' },
  pending_approvals: [],
};

async function loadState() {
  try {
    store.data = await api.state();
    $('#offlineBanner').hidden = true;
  } catch (err) {
    store.data = JSON.parse(JSON.stringify(OFFLINE_SNAPSHOT));
    $('#offlineBanner').hidden = false;
  }
  renderShell();
  render();
}

function renderShell() {
  const d = store.data;
  const load = d.state?.cognitive_load || {};
  $('#loadScore').innerHTML = `${load.score ?? '—'} <small>/ 100</small>`;
  $('#loadMeter').style.width = `${load.score || 0}%`;
  $('#loadMeter').parentElement.classList.toggle('hot', (load.score || 0) >= 75);
  $('#loadNote').textContent = load.explanation || '—';
  const openTasks = (d.tasks || []).filter((t) => !['done', 'completed', 'archived', 'cancelled'].includes(t.status)).length;
  const badgeTasks = $('[data-badge="tasks"]');
  if (badgeTasks) badgeTasks.textContent = openTasks || '';
  const badgeProjects = $('[data-badge="projects"]');
  if (badgeProjects) badgeProjects.textContent = (d.projects || []).filter((p) => p.status === 'active').length || '';
  const badgeApprovals = $('[data-badge="approvals"]');
  if (badgeApprovals) badgeApprovals.textContent = (d.pending_approvals || []).length || '';
  $('#bellDot').hidden = !(d.pending_approvals || []).length;
}

function render() {
  const [kicker, titleText] = TITLES[store.view] || TITLES.command;
  $('#view-kicker').textContent = kicker;
  $('#view-title').textContent = titleText;
  $$('#nav a, .sidebar nav a, .bottom-nav a').forEach((a) => a.classList.toggle('active', a.dataset.view === store.view));
  const root = $('#app');
  const d = store.data;
  const reload = () => loadState();
  const renderers = {
    command: () => renderCommand(root, d),
    tasks: () => renderTasks(root, d, reload),
    projects: () => renderProjects(root, d, reload),
    people: () => renderPeople(root, d, reload),
    ideas: () => renderIdeas(root, d, reload),
    research: () => renderResearch(root, d, reload),
    reviews: () => renderReviews(root),
    workflows: () => renderWorkflows(root, d, reload),
    memory: () => renderMemory(root, d, reload),
    agents: () => renderAgents(root, d, reload),
    notifications: () => renderNotifications(root, d, reload),
    settings: () => renderSettings(root, d, reload),
  };
  (renderers[store.view] || renderers.command)().then?.(() => bindGlobalRowEvents()).catch?.((e) => {
    root.innerHTML = `<div class="error-box">${esc(e.message || e)}</div>`;
  });
  bindGlobalRowEvents();
}

// Global event delegation: nav, capture buttons, task toggles, follow-ups, detail opens.
function bindGlobalRowEvents() {
  $$('[data-nav]').forEach((b) => b.onclick = () => go(b.dataset.nav));
  $$('[data-action="capture"]').forEach((b) => b.onclick = openCapture);
  bindTaskRowEvents($('#app'), () => loadState());
  $$('[data-followup]').forEach((b) => b.onclick = async () => {
    const name = b.dataset.followup;
    try {
      const person = (store.data.people || []).find((p) => p.name === name);
      const task = await api.createEntity('task', {
        title: `Follow up with ${name}`, project: 'Relationships',
        priority: 'medium', status: 'open', estimate: 15, energy: 'light',
        due: new Date().toISOString().slice(0, 10),
      });
      if (person) await api.link(task.id, 'follows_up', person.id).catch(() => {});
      toast(`Follow-up task created for ${name}`);
      loadState();
    } catch (err) { toast(err.message, 'error'); }
  });
}

function go(view) {
  store.view = view;
  closeSidebar();
  render();
  $('#main').focus({ preventScroll: true });
}

// --------------------------------------------------------------- capture
function openCapture() {
  $('#captureModal').classList.remove('hidden');
  $('#captureText').focus();
}

function bindCapture() {
  $('#closeModal').onclick = () => $('#captureModal').classList.add('hidden');
  $$('.capture-types button').forEach((b) => b.onclick = () => {
    $$('.capture-types button').forEach((x) => x.classList.remove('selected'));
    b.classList.add('selected');
    store.captureType = b.dataset.type;
  });
  const save = async () => {
    const text = $('#captureText').value.trim();
    if (!text) return;
    const btn = $('#saveCapture');
    btn.disabled = true;
    try {
      const res = await api.capture(text, store.captureType || undefined);
      const c = res.classification || {};
      toast(`Captured as ${res.entity.kind} — ${c.reason || 'filed'}${res.links_created?.length ? ` · linked to ${res.links_created[0].title}` : ''}`);
      $('#captureText').value = '';
      $('#captureModal').classList.add('hidden');
      $('#captureHint').textContent = `Next: ${res.next_step}`;
      loadState();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false;
    }
  };
  $('#saveCapture').onclick = save;
  $('#captureText').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save();
  });
}

// ---------------------------------------------------------------- search
function bindSearch() {
  const open = () => { $('#searchModal').classList.remove('hidden'); $('#searchInput').focus(); };
  const close = () => $('#searchModal').classList.add('hidden');
  $('#searchBtn').onclick = open;
  $('#closeSearch').onclick = close;
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); open(); }
    if (e.key === 'Escape') { $$('.modal').forEach((m) => m.classList.add('hidden')); }
  });
  let debounce;
  $('#searchInput').addEventListener('input', (e) => {
    clearTimeout(debounce);
    const q = e.target.value.trim();
    debounce = setTimeout(async () => {
      const box = $('#searchResults');
      if (q.length < 2) { box.innerHTML = '<p class="muted">Type at least 2 characters. Filters: kind:, status:, project:, due:, priority:</p>'; return; }
      box.innerHTML = '<div class="skel" style="width:50%"></div>';
      try {
        const res = await api.search(q);
        const results = res.results || [];
        box.innerHTML = `
          ${results.length ? results.slice(0, 12).map((r) => `<article class="entity" data-open="${esc(r.id)}" style="cursor:pointer">
            <div class="entity-top"><h3>${esc(r.title)}</h3><span class="pill grey">${esc(r.kind)}</span></div>
            <p class="muted">${esc(r.snippet || '')}</p>
            <p class="tiny muted">${r.status ? `status ${esc(r.status)} · ` : ''}${r.why?.length ? `matched: ${esc(r.why.join('; '))}` : ''}</p>
          </article>`).join('') : '<p class="muted">No matches. Try different words or a filter like <code>kind:task</code>.</p>'}
          ${res.memory_matches?.length ? `<div class="label" style="margin-top:10px">_MEMORY_${''}</div>${res.memory_matches.map((m) => `<p class="muted tiny">◈ ${esc(m.content.slice(0, 100))} <span class="reasoning">(${esc(m.retrieval_reason || '')})</span></p>`).join('')}` : ''}
          <p class="tiny muted">${res.total} matches · ${esc(res.explainability)}</p>`;
        $$('#searchResults [data-open]').forEach((n) => n.onclick = () => { close(); openEntity(n.dataset.open, { onChange: () => loadState() }); });
      } catch (err) {
        box.innerHTML = `<div class="error-box">${esc(err.message)}</div>`;
      }
    }, 250);
  });
}

// ------------------------------------------------------------ sidebar/nav
function bindSidebar() {
  $$('[data-view]').forEach((a) => {
    if (a.tagName === 'A' || a.tagName === 'BUTTON') {
      a.addEventListener('click', () => a.dataset.view && go(a.dataset.view));
    }
  });
  $('#hamburger').onclick = () => {
    $('#sidebar').classList.add('open');
    $('#backdrop').hidden = false;
    $('#hamburger').setAttribute('aria-expanded', 'true');
  };
  const close = () => closeSidebar();
  $('#sidebarClose').onclick = close;
  $('#backdrop').onclick = close;
}

function closeSidebar() {
  $('#sidebar').classList.remove('open');
  $('#backdrop').hidden = true;
  $('#hamburger').setAttribute('aria-expanded', 'false');
}

// ------------------------------------------------------------------ misc
function bindChrome() {
  $('#theme').onclick = () => {
    document.body.classList.toggle('dark');
    localStorage.setItem('ourex.theme', document.body.classList.contains('dark') ? 'dark' : 'light');
  };
  if (localStorage.getItem('ourex.theme') === 'dark') document.body.classList.add('dark');
  $('#bellBtn').onclick = () => go('notifications');
  $('#fabCapture').onclick = openCapture;
  const hour = new Date().getHours();
  $('#greeting').textContent = hour < 12 ? 'Good morning.' : hour < 18 ? 'Good afternoon.' : 'Good evening.';
  $('#todayLine').textContent = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
}

// Escaping closes modals when clicking backdrop shadows.
document.addEventListener('click', (e) => {
  if (e.target.classList?.contains('modal')) e.target.classList.add('hidden');
});

bindChrome();
bindSidebar();
bindCapture();
bindSearch();
loadState();
