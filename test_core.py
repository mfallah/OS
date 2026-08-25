import tempfile, unittest
from personal_os_core import PersonalOS, Orchestrator, WorkflowEngine

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.NamedTemporaryFile(suffix='.sqlite3'); self.os=PersonalOS(self.tmp.name)
    def tearDown(self): self.os.close(); self.tmp.close()
    def test_entity_graph_and_context(self):
        p=self.os.create('project', {'name':'Ourex','status':'active'})
        t=self.os.create('task', {'title':'Review Ourex','project':p['id']})
        self.os.link(t['id'],'supports',p['id'])
        self.assertEqual(self.os.get(t['id'])['title'],'Review Ourex')
        self.assertTrue(self.os.search('Ourex'))
        self.assertTrue(self.os.neighbors(t['id']))
    def test_memory_provenance(self):
        m=self.os.remember('preference','Prefers concise weekly reviews',confidence=.9,source='user')
        self.assertEqual(self.os.memory(m['id'])['source'],'user')
    def test_high_risk_requires_approval(self):
        result=WorkflowEngine(self.os).run({'name':'send email','risk':'external','action':'send'},approved=False)
        self.assertFalse(result['allowed']); self.assertEqual(result['status'],'approval_required')
    def test_orchestration_has_context_contract(self):
        plan=Orchestrator(self.os).plan('What matters today?')
        self.assertIn('context',plan); self.assertIn('verification',plan)

if __name__=='__main__': unittest.main()
