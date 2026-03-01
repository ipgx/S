#!/usr/bin/env python3
"""Simple HTTP server for the combined CMS map. Serves from ALL-CMS directory."""
import http.server, os, functools

PORT = 8091
DIR = os.path.dirname(os.path.abspath(__file__))

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DIR)

print(f"Serving combined CMS map at http://localhost:{PORT}/combined_map.html")
print(f"Root: {DIR}")
http.server.HTTPServer(("", PORT), Handler).serve_forever()
