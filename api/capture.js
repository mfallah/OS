module.exports = (req, res) => {
  if (req.method !== 'POST') return res.status(405).json({ error: 'method_not_allowed' });
  const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
  const item = { id: `v-${Date.now()}`, createdAt: new Date().toISOString(), status: 'open', ...body };
  return res.status(201).json(item);
};
