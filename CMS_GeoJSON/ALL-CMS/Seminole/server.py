#!/usr/bin/env python3
import json, os, shutil
from http.server import HTTPServer, SimpleHTTPRequestHandler
GEOJSON = os.path.join(os.path.dirname(__file__), "Seminole_CMS_routed.geojson")
class H(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path=="/api/delete":
            body=json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))))
            sid=body.get("segment_id")
            if not sid: self.send_response(400); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"error":"missing id"}).encode()); return
            with open(GEOJSON) as f: gj=json.load(f)
            b=len(gj["features"]); gj["features"]=[f for f in gj["features"] if f["properties"]["SEGMENT_ID"]!=str(sid)]; a=len(gj["features"])
            if a==b: self.send_response(404); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"error":"not found"}).encode()); return
            with open(GEOJSON,"w") as f: json.dump(gj,f)
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"ok":True,"deleted":str(sid),"remaining":a}).encode())
        elif self.path=="/api/undo":
            bak=GEOJSON+".bak"
            if os.path.exists(bak):
                os.replace(bak,GEOJSON)
                with open(GEOJSON) as f: gj=json.load(f)
                self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"ok":True,"restored":len(gj["features"])}).encode())
            else: self.send_response(404); self.end_headers()
        elif self.path=="/api/backup":
            shutil.copy2(GEOJSON,GEOJSON+".bak")
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({"ok":True}).encode())
        else: self.send_response(404); self.end_headers()
    def log_message(self,*a): pass
if __name__=="__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print(f"Seminole CMS Editor on http://localhost:8090")
    HTTPServer(("",8090),H).serve_forever()
