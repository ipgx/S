#!/usr/bin/env python3
"""
Dev server for Lake County CMS map with edit API.
Serves static files + handles segment deletion via POST /api/delete.
"""

import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler

GEOJSON_PATH = os.path.join(os.path.dirname(__file__), "Lake_County_CMS_routed.geojson")
PORT = 8090


class CMSHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/api/delete":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            seg_id = body.get("segment_id")

            if not seg_id:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "missing segment_id"}).encode())
                return

            # Load, filter, save
            with open(GEOJSON_PATH) as f:
                gj = json.load(f)

            before = len(gj["features"])
            gj["features"] = [
                feat for feat in gj["features"]
                if feat["properties"]["SEGMENT_ID"] != str(seg_id)
            ]
            after = len(gj["features"])

            if after == before:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"segment {seg_id} not found"}).encode())
                return

            with open(GEOJSON_PATH, "w") as f:
                json.dump(gj, f)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "deleted": str(seg_id),
                "remaining": after
            }).encode())
            print(f"  Deleted segment {seg_id} — {after} remaining")

        elif self.path == "/api/undo":
            # Restore from backup if exists
            backup = GEOJSON_PATH + ".bak"
            if os.path.exists(backup):
                os.replace(backup, GEOJSON_PATH)
                with open(GEOJSON_PATH) as f:
                    gj = json.load(f)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "ok": True,
                    "restored": len(gj["features"])
                }).encode())
                print(f"  Undo — restored {len(gj['features'])} features")
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "no backup found"}).encode())

        elif self.path == "/api/backup":
            # Create a backup before editing session
            import shutil
            shutil.copy2(GEOJSON_PATH, GEOJSON_PATH + ".bak")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
            print("  Backup created")

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Suppress GET logs, keep API logs
        if "POST" in str(args):
            super().log_message(format, *args)


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print(f"Lake County CMS Editor Server on http://localhost:{PORT}")
    print(f"GeoJSON: {GEOJSON_PATH}")
    HTTPServer(("", PORT), CMSHandler).serve_forever()
