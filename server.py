#!/usr/bin/env python3
"""Personal OS reference server: dependency-free API + static app."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import json, uuid, datetime

ROOT = Path(__file__).parent
DATA = ROOT / "data.json"

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def seed():
    return {
      "constitution": {"values":["Clarity","Craft","Relationships"],"nonNegotiables":["Protect deep work","Leave room for recovery"],"activeLimit":3},
      "tasks": [
        {"id":"t1","title":"Review Ourex architecture","project":"Ourex","priority":"high","status":"in-progress","estimate":90,"due":"Today","energy":"deep"},
        {"id":"t2","title":"Send follow-up to Sara","project":"Relationships","priority":"medium","status":"open","estimate":15,"due":"Today","energy":"light"},
        {"id":"t3","title":"Synthesize MCP research","project":"Ourex","priority":"high","status":"open","estimate":60,"due":"Tomorrow","energy":"deep"},
        {"id":"t4","title":"Book quarterly review","project":"Personal","priority":"low","status":"open","estimate":10,"due":"This week","energy":"light"}
      ],
      "projects":[
        {"id":"p1","name":"Ourex","description":"Personal OS architecture","progress":68,"risk":31,"clarity":82,"momentum":74,"next":"Resolve integration boundary","status":"active"},
        {"id":"p2","name":"Learning systems","description":"Build a sustainable research practice","progress":35,"risk":18,"clarity":71,"momentum":48,"next":"Complete knowledge review","status":"active"},
        {"id":"p3","name":"Home studio","description":"A calm space for deep work","progress":18,"risk":62,"clarity":44,"momentum":22,"next":"Decide on scope","status":"at-risk"}
      ],
      "people":[{"id":"r1","name":"Sara Rahimi","role":"Product collaborator","lastContact":"6 days ago","importance":"high","need":"Follow up on Ourex research"},{"id":"r2","name":"Mina","role":"Family","lastContact":"2 days ago","importance":"high","need":"Meaningful contact"}],
      "ideas":[{"id":"i1","title":"MCP as a universal connection layer","summary":"Connect Ourex to external AI systems without coupling the core.","status":"developing","potential":"high"},{"id":"i2","title":"Attention budget as a first-class resource","summary":"Plan time, energy and focus together.","status":"captured","potential":"medium"}],
      "insights":[{"id":"n1","kind":"Focus","title":"Your active portfolio is within your preferred limit","body":"Three active projects match your constitution. Protect the next deep-work window for Ourex.","confidence":0.91},{"id":"n2","kind":"Risk","title":"Home studio needs a decision","body":"Clarity is low and momentum has fallen. A 20-minute scope decision can unblock it.","confidence":0.78}],
      "events":[]
    }

def load():
    if not DATA.exists(): DATA.write_text(json.dumps(seed(), indent=2), encoding="utf8")
    return json.loads(DATA.read_text(encoding="utf8"))
def save(db): DATA.write_text(json.dumps(db, indent=2), encoding="utf8")

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT),**kw)
    def json_headers(self, code=200):
        self.send_response(code); self.send_header("Content-Type","application/json"); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers()
    def do_OPTIONS(self): self.json_headers(204)
    def do_GET(self):
        path=urlparse(self.path).path
        if path == "/api/state": self.json_headers(); self.wfile.write(json.dumps(load()).encode()); return
        if path == "/api/health": self.json_headers(); self.wfile.write(json.dumps({"status":"operational","time":now(),"queue":"healthy"}).encode()); return
        return super().do_GET()
    def do_POST(self):
        path=urlparse(self.path).path; length=int(self.headers.get("Content-Length",0)); body=json.loads(self.rfile.read(length) or "{}")
        db=load()
        if path=="/api/capture":
            entity=body.get("entity","task"); item={"id":uuid.uuid4().hex[:8],"createdAt":now(),"status":"open",**body}
            collection={"task":"tasks","idea":"ideas","note":"notes"}.get(entity,"tasks"); db.setdefault(collection,[]).append(item)
            db["events"].append({"type":f"{entity}.created","at":now(),"entityId":item["id"]}); save(db); self.json_headers(201); self.wfile.write(json.dumps(item).encode()); return
        if path.startswith("/api/tasks/"):
            tid=path.split("/")[-1]; task=next((x for x in db["tasks"] if x["id"]==tid),None)
            if task: task.update(body); db["events"].append({"type":"task.updated","at":now(),"entityId":tid}); save(db); self.json_headers(); self.wfile.write(json.dumps(task).encode()); return
        self.json_headers(404); self.wfile.write(json.dumps({"error":"not found"}).encode())

if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(__import__('os').environ.get("PORT", "8000"))), Handler).serve_forever()
