const state = {
  constitution: { values: ['Clarity', 'Craft', 'Relationships'], nonNegotiables: ['Protect deep work', 'Leave room for recovery'], activeLimit: 3 },
  tasks: [
    { id: 't1', title: 'Review Ourex architecture', project: 'Ourex', priority: 'high', status: 'in-progress', estimate: 90, due: 'Today', energy: 'deep' },
    { id: 't2', title: 'Send follow-up to Sara', project: 'Relationships', priority: 'medium', status: 'open', estimate: 15, due: 'Today', energy: 'light' },
    { id: 't3', title: 'Synthesize MCP research', project: 'Ourex', priority: 'high', status: 'open', estimate: 60, due: 'Tomorrow', energy: 'deep' },
    { id: 't4', title: 'Book quarterly review', project: 'Personal', priority: 'low', status: 'open', estimate: 10, due: 'This week', energy: 'light' }
  ],
  projects: [
    { id: 'p1', name: 'Ourex', description: 'Personal OS architecture', progress: 68, risk: 31, clarity: 82, momentum: 74, next: 'Resolve integration boundary', status: 'active' },
    { id: 'p2', name: 'Learning systems', description: 'Build a sustainable research practice', progress: 35, risk: 18, clarity: 71, momentum: 48, next: 'Complete knowledge review', status: 'active' },
    { id: 'p3', name: 'Home studio', description: 'A calm space for deep work', progress: 18, risk: 62, clarity: 44, momentum: 22, next: 'Decide on scope', status: 'at-risk' }
  ],
  people: [
    { id: 'r1', name: 'Sara Rahimi', role: 'Product collaborator', lastContact: '6 days ago', importance: 'high', need: 'Follow up on Ourex research' },
    { id: 'r2', name: 'Mina', role: 'Family', lastContact: '2 days ago', importance: 'high', need: 'Meaningful contact' }
  ],
  ideas: [
    { id: 'i1', title: 'MCP as a universal connection layer', summary: 'Connect Ourex to external AI systems without coupling the core.', status: 'developing', potential: 'high' },
    { id: 'i2', title: 'Attention budget as a first-class resource', summary: 'Plan time, energy and focus together.', status: 'captured', potential: 'medium' }
  ],
  insights: [
    { id: 'n1', kind: 'Focus', title: 'Your active portfolio is within your preferred limit', body: 'Three active projects match your constitution. Protect the next deep-work window for Ourex.', confidence: 0.91 },
    { id: 'n2', kind: 'Risk', title: 'Home studio needs a decision', body: 'Clarity is low and momentum has fallen. A 20-minute scope decision can unblock it.', confidence: 0.78 }
  ],
  events: []
};
module.exports = state;
