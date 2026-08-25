module.exports = (req, res) => {
  if (req.method !== 'POST' && req.method !== 'PATCH') return res.status(405).json({ error: 'method_not_allowed' });
  return res.status(200).json({ id: req.query.id, ...(req.body || {}) });
};
