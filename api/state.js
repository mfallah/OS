const state = require('./_state');
module.exports = (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  res.status(200).json(state);
};
