// API client: one place for fetch, errors, idempotency and offline detection.
export class ApiError extends Error {
  constructor(status, code, message, setup) {
    super(message);
    this.status = status; this.code = code; this.setup = setup;
  }
}

export const offline = { active: false };

async function request(path, { method = 'GET', body, idempotencyKey } = {}) {
  const headers = { Accept: 'application/json' };
  if (body) headers['Content-Type'] = 'application/json';
  if (idempotencyKey) headers['X-Idempotency-Key'] = idempotencyKey;
  let res;
  try {
    res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch (networkError) {
    offline.active = true;
    throw new ApiError(0, 'offline', 'API unreachable — working from the last snapshot.');
  }
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (res.ok || res.status === 202) {
    offline.active = false;
    return data;
  }
  const err = data && data.error ? data.error : { code: 'http_' + res.status, message: res.statusText };
  throw new ApiError(res.status, err.code || 'error', err.message || 'Request failed', err.setup);
}

export const api = {
  get: (path) => request(path),
  post: (path, body, opts) => request(path, { method: 'POST', body, ...opts }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  del: (path) => request(path, { method: 'DELETE' }),

  state: () => request('/api/state'),
  createEntity: (kind, data) => request('/api/core/entities', { method: 'POST', body: { kind, ...data } }),
  updateEntity: (id, patch) => request(`/api/core/entities/${id}`, { method: 'POST', body: patch }),
  deleteEntity: (id) => request(`/api/core/entities/${id}?confirm=true`, { method: 'DELETE' }),
  link: (source, relation, target) => request('/api/core/graph/link', { method: 'POST', body: { source, relation, target } }),
  unlink: (source, relation, target) => request('/api/core/graph/unlink', { method: 'POST', body: { source, relation, target } }),
  entity: (id) => request(`/api/core/entities/${id}`),
  search: (q) => request(`/api/core/search?q=${encodeURIComponent(q)}`),
  capture: (text, entity) => request('/api/capture', { method: 'POST', body: { text, entity } }),
  ask: (message, extras = {}) => request('/api/core/plan', { method: 'POST', body: { message, ...extras } }),
  memories: (params = {}) => request('/api/core/memories?' + new URLSearchParams(params)),
  remember: (category, content, extra = {}) => request('/api/core/memory', { method: 'POST', body: { category, content, ...extra } }),
  correctMemory: (id, content) => request(`/api/core/memory/${id}/correct`, { method: 'POST', body: { content } }),
  confirmMemory: (id) => request(`/api/core/memory/${id}/confirm`, { method: 'POST', body: {} }),
  deleteMemory: (id) => request(`/api/core/memory/${id}?confirm=true`, { method: 'DELETE' }),
  exportMemory: () => request('/api/core/memory/export'),
  memoryCategory: (cat, action) => request(`/api/core/memory/category/${cat}/${action}`, { method: 'POST', body: {} }),
  runWorkflow: (id, opts = {}) => request('/api/core/workflows/run', { method: 'POST', body: { id, ...opts } }),
  workflows: () => request('/api/core/workflows'),
  approvals: () => request('/api/core/approvals'),
  decide: (id, approve) => request(`/api/core/approvals/${id}/decide`, { method: 'POST', body: { approve } }),
  agents: () => request('/api/core/agents'),
  agentStatus: (id, status) => request(`/api/core/agents/${id}/status`, { method: 'POST', body: { status } }),
  skills: () => request('/api/core/skills'),
  createSkill: (spec) => request('/api/core/skills', { method: 'POST', body: spec }),
  updateSkill: (id, patch) => request(`/api/core/skills/${id}`, { method: 'POST', body: patch }),
  testSkill: (id, input) => request(`/api/core/skills/${id}/test`, { method: 'POST', body: { input } }),
  duplicateSkill: (id) => request(`/api/core/skills/${id}/duplicate`, { method: 'POST', body: {} }),
  deleteSkill: (id) => request(`/api/core/skills/${id}?confirm=true`, { method: 'DELETE' }),
  tools: () => request('/api/core/tools'),
  integrations: () => request('/api/integrations/status'),
  notifications: () => request('/api/notifications'),
  notificationAction: (id, action, body = {}) => request(`/api/notifications/${id}/${action}`, { method: 'POST', body }),
  health: () => request('/api/health'),
  audit: () => request('/api/core/audit?limit=60'),
  events: () => request('/api/core/events?limit=60'),
  weekly: () => request('/api/core/reviews/weekly'),
  monthly: () => request('/api/core/reviews/monthly'),
  dailyPlan: () => request('/api/core/plans/daily'),
  priorResearch: (topic) => request('/api/core/research/check-prior', { method: 'POST', body: { topic } }),
  exportAll: () => request('/api/export'),
};
