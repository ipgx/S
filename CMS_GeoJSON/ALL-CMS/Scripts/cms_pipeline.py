#!/usr/bin/env python3
"""
Reusable CMS Pipeline: Geocode + Route + Clip + QA + Map
Usage: python3 cms_pipeline.py <segments.json> [--skip-geocode]

Input JSON format: {"name": "...", "region": "...", "segments": [{"id","road","from","to","lat?","lon?"}]}
"""

import json
import math
import os
import re
import sys
import time
import urllib.request
import urllib.parse

# ─── CONFIG ────────────────────────────────────────────────────────
ARCGIS_URL = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
VALHALLA_URL = "https://valhalla1.openstreetmap.de/route"
FL_COUNTIES = "/Users/pg/Documents/S/FL_Counties.geojson"

# ─── HELPERS ───────────────────────────────────────────────────────
def haversine(lon1, lat1, lon2, lat2):
    R = 6371
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def pip(x, y, poly):
    n = len(poly); inside = False; j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def in_polygon(lon, lat, county_poly):
    for polygon in county_poly:
        outer = polygon[0]
        if pip(lon, lat, outer):
            in_hole = any(pip(lon, lat, hole) for hole in polygon[1:])
            if not in_hole:
                return True
    return False


def geocode_arcgis(address, bbox, center_lon, center_lat):
    """Geocode via ArcGIS with bbox and center bias."""
    params = urllib.parse.urlencode({
        "SingleLine": address,
        "f": "json",
        "outFields": "Score,Match_addr",
        "searchExtent": bbox,
        "location": f"{center_lon},{center_lat}",
        "distance": 80000,
        "maxLocations": 5,
    })
    url = f"{ARCGIS_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CMS-Pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        candidates = data.get("candidates", [])
        if candidates:
            best = candidates[0]
            loc = best["location"]
            return loc["x"], loc["y"], best["score"]
    except Exception:
        pass
    return None, None, 0


def decode_polyline(encoded, precision=6):
    inv = 1.0 / (10 ** precision)
    decoded = []; previous = [0, 0]; i = 0
    while i < len(encoded):
        for dim in range(2):
            shift = 0; result = 0
            while True:
                b = ord(encoded[i]) - 63; i += 1
                result |= (b & 0x1F) << shift; shift += 5
                if b < 0x20: break
            if result & 1: previous[dim] += ~(result >> 1)
            else: previous[dim] += (result >> 1)
        decoded.append([previous[1] * inv, previous[0] * inv])
    return decoded


def valhalla_route(f_lon, f_lat, t_lon, t_lat):
    """Route via Valhalla shortest distance."""
    payload = json.dumps({
        "locations": [{"lon": f_lon, "lat": f_lat}, {"lon": t_lon, "lat": t_lat}],
        "costing": "auto",
        "costing_options": {"auto": {"shortest": True}},
        "units": "kilometers"
    }).encode("utf-8")
    try:
        req = urllib.request.Request(VALHALLA_URL, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "CMS-Pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        trip = data.get("trip", {})
        legs = trip.get("legs", [])
        if not legs: return None
        coords = decode_polyline(legs[0].get("shape", ""), precision=6)
        dist_km = trip.get("summary", {}).get("length", 0)
        if len(coords) >= 2:
            return coords, dist_km
    except Exception:
        pass
    return None


def line_seg_intersect(p1, p2, p3, p4):
    """Find intersection point of two line segments, or None."""
    x1,y1 = p1; x2,y2 = p2; x3,y3 = p3; x4,y4 = p4
    denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
    if abs(denom) < 1e-12: return None
    t = ((x1-x3)*(y3-y4) - (y1-y3)*(x3-x4)) / denom
    u = -((x1-x2)*(y1-y3) - (y1-y2)*(x1-x3)) / denom
    if 0 <= t <= 1 and 0 <= u <= 1:
        return [x1 + t*(x2-x1), y1 + t*(y2-y1)]
    return None


def clip_route(coords, county_poly):
    """Clip route to county polygon, keeping in-county portions."""
    if not coords: return coords
    clipped = []
    boundary_edges = []
    for polygon in county_poly:
        outer = polygon[0]
        for i in range(len(outer)):
            boundary_edges.append((outer[i], outer[(i+1) % len(outer)]))

    for i, pt in enumerate(coords):
        inside = in_polygon(pt[0], pt[1], county_poly)
        if inside:
            # Check if we need a boundary crossing point from previous OOB
            if i > 0 and clipped and not in_polygon(coords[i-1][0], coords[i-1][1], county_poly):
                for e1, e2 in boundary_edges:
                    cross = line_seg_intersect(coords[i-1], pt, e1, e2)
                    if cross:
                        clipped.append(cross)
                        break
            clipped.append(pt)
        else:
            # Leaving county - add crossing point
            if i > 0 and clipped and in_polygon(coords[i-1][0], coords[i-1][1], county_poly):
                for e1, e2 in boundary_edges:
                    cross = line_seg_intersect(coords[i-1], pt, e1, e2)
                    if cross:
                        clipped.append(cross)
                        break
    return clipped if len(clipped) >= 2 else coords


def get_county_boundary(county_name, county_fips=None):
    """Extract county boundary from FL_Counties.geojson."""
    with open(FL_COUNTIES) as f:
        fc = json.load(f)
    for feat in fc["features"]:
        props = feat["properties"]
        name = props.get("NAME", "")
        geoid = props.get("GEOID", "")
        if county_fips and geoid == county_fips:
            return feat["geometry"]["coordinates"], feat
        if county_name.lower() in name.lower():
            return feat["geometry"]["coordinates"], feat
    return None, None


def get_bbox_and_center(county_poly):
    """Compute bounding box and center from county polygon."""
    lons, lats = [], []
    for polygon in county_poly:
        for ring in polygon:
            for pt in ring:
                lons.append(pt[0]); lats.append(pt[1])
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    bbox = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    c_lon = (min_lon + max_lon) / 2
    c_lat = (min_lat + max_lat) / 2
    return bbox, c_lon, c_lat


def generate_map_html(name, region):
    """Generate Leaflet map HTML with editor."""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{name} CMS – Routed Segments Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
    #map {{ width: 100vw; height: 100vh; }}
    .info-panel {{ position: absolute; top: 10px; right: 10px; z-index: 1000; background: #fff; border-radius: 8px; padding: 14px 18px; box-shadow: 0 2px 12px rgba(0,0,0,.25); max-width: 360px; font-size: 13px; line-height: 1.5; }}
    .info-panel h3 {{ margin: 0 0 6px; font-size: 15px; }}
    .info-panel .count {{ color: #555; margin-bottom: 8px; }}
    .info-panel .stat {{ display: flex; justify-content: space-between; }}
    .info-panel .stat span:last-child {{ font-weight: 600; }}
    .legend {{ position: absolute; bottom: 24px; left: 10px; z-index: 1000; background: #fff; border-radius: 8px; padding: 10px 14px; box-shadow: 0 2px 12px rgba(0,0,0,.25); font-size: 12px; }}
    .legend-item {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; }}
    .legend-dot {{ width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }}
    .legend-line {{ width: 24px; height: 3px; flex-shrink: 0; border-radius: 2px; }}
    .search-box {{ position: absolute; top: 10px; left: 54px; z-index: 1000; }}
    .search-box input {{ width: 280px; padding: 8px 12px; border: 2px solid #ccc; border-radius: 6px; font-size: 13px; outline: none; box-shadow: 0 2px 8px rgba(0,0,0,.15); }}
    .search-box input:focus {{ border-color: #2563eb; }}
    .leaflet-popup-content {{ font-size: 12px; line-height: 1.6; min-width: 220px; }}
    .leaflet-popup-content strong {{ color: #1e40af; }}
    .popup-flag {{ background: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 3px; font-size: 11px; }}
    .popup-ok {{ background: #dcfce7; color: #166534; padding: 2px 6px; border-radius: 3px; font-size: 11px; }}
    .btn-delete {{ display: inline-block; margin-top: 8px; padding: 5px 14px; background: #dc2626; color: #fff; border: none; border-radius: 5px; font-size: 12px; font-weight: 600; cursor: pointer; }}
    .btn-delete:hover {{ background: #b91c1c; }}
    .btn-undo {{ display: inline-block; margin-top: 4px; padding: 4px 12px; background: #6b7280; color: #fff; border: none; border-radius: 5px; font-size: 11px; cursor: pointer; }}
    .btn-download {{ display: inline-block; padding: 5px 12px; background: #2563eb; color: #fff; border: none; border-radius: 5px; font-size: 11px; font-weight: 600; cursor: pointer; }}
    .btn-download:hover {{ background: #1d4ed8; }}
    .toast {{ position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%); z-index: 9999; background: #1e293b; color: #fff; padding: 10px 24px; border-radius: 8px; font-size: 13px; font-weight: 500; box-shadow: 0 4px 16px rgba(0,0,0,.3); opacity: 0; transition: opacity 0.3s; pointer-events: none; }}
    .toast.show {{ opacity: 1; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="search-box"><input id="search" type="text" placeholder="Search road name or segment ID..." /></div>
  <div class="info-panel" id="info">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <h3 style="margin:0;">{name} CMS</h3>
      <button class="btn-download" onclick="downloadGeoJSON()">Download</button>
    </div>
    <div class="count" id="count">Loading...</div>
    <div class="count" id="edit-stats" style="display:none; color:#dc2626;"></div>
    <div id="details">Click a segment for details.</div>
  </div>
  <div class="toast" id="toast"></div>
  <div class="legend">
    <div class="legend-item"><div class="legend-line" style="background:#6366f1; height:2px; border: 1px dashed #6366f1;"></div> Boundary</div>
    <div class="legend-item"><div class="legend-dot" style="background:#2563eb;"></div> FROM</div>
    <div class="legend-item"><div class="legend-dot" style="background:#dc2626;"></div> TO</div>
    <div class="legend-item"><div class="legend-line" style="background:#16a34a;"></div> Routed (OK)</div>
    <div class="legend-item"><div class="legend-line" style="background:#f59e0b;"></div> Routed (flagged)</div>
  </div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const map = L.map('map', {{ zoomControl: true }}).setView([28.0, -81.5], 10);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 19, attribution: '&copy; OSM | Valhalla' }}).addTo(map);
    const bndLayer = L.layerGroup().addTo(map), okLayer = L.layerGroup().addTo(map), flagLayer = L.layerGroup().addTo(map), fromLayer = L.layerGroup().addTo(map), toLayer = L.layerGroup().addTo(map);
    L.control.layers(null, {{"Boundary": bndLayer, "Segments (OK)": okLayer, "Segments (flagged)": flagLayer, "FROM": fromLayer, "TO": toLayer}}, {{ collapsed: false, position: 'bottomright' }}).addTo(map);
    fetch('boundary.geojson').then(r=>r.json()).then(d=>{{ bndLayer.addLayer(L.geoJSON(d, {{ style: {{ color:'#6366f1', weight:2.5, opacity:0.8, fillColor:'#6366f1', fillOpacity:0.04, dashArray:'8,5' }} }})); }});
    let allFeatures=[], originalCount=0, selectedLayer=null;
    fetch('{name}_CMS_routed.geojson').then(r=>r.json()).then(data=>{{ allFeatures=data.features; originalCount=allFeatures.length; renderFeatures(allFeatures); updateCounts(); }});
    function renderFeatures(features, keepView) {{
      okLayer.clearLayers(); flagLayer.clearLayers(); fromLayer.clearLayers(); toLayer.clearLayers();
      features.forEach(feat=>{{
        const p=feat.properties, coords=feat.geometry.coordinates[0];
        if(!coords||coords.length<2) return;
        const fLL=[coords[0][1],coords[0][0]], tLL=[coords[coords.length-1][1],coords[coords.length-1][0]];
        const latlngs=coords.map(c=>[c[1],c[0]]);
        const flagged=p.Route_Status!=='OK';
        const color=flagged?'#f59e0b':'#16a34a';
        const line=L.polyline(latlngs, {{color, weight:4, opacity:0.8}}).bindPopup(
          `<strong>Seg ${{p.SEGMENT_ID}}</strong><br/><b>${{p.RoadName}}</b><br/>From: ${{p.From}}<br/>To: ${{p.To}}<br/>Route: ${{p.Route_Distance_km}} km | Detour: ${{p.Detour_Ratio}}x<br/>${{flagged?'<span class="popup-flag">\\u26a0 '+p.Route_Status+'</span>':'<span class="popup-ok">\\u2705 OK</span>'}}`
        );
        line.options._origColor=color;
        line.on('click', function(){{ if(selectedLayer) selectedLayer.setStyle({{color:selectedLayer.options._origColor,weight:4,opacity:0.8}}); this.setStyle({{color:'#8b0000',weight:7,opacity:1}}); selectedLayer=this; showInfo(p); }});
        line.on('mouseover', function(){{ if(this!==selectedLayer) this.setStyle({{color:'#8b0000',weight:6,opacity:1}}); }});
        line.on('mouseout', function(){{ if(this!==selectedLayer) this.setStyle({{color:this.options._origColor,weight:4,opacity:0.8}}); }});
        (flagged?flagLayer:okLayer).addLayer(line);
        fromLayer.addLayer(L.circleMarker(fLL,{{radius:5,color:'#1e40af',fillColor:'#2563eb',fillOpacity:0.9,weight:1.5}}).bindPopup(`<strong>FROM</strong><br/>Seg ${{p.SEGMENT_ID}}: ${{p.RoadName}}<br/>${{p.From}}`));
        toLayer.addLayer(L.circleMarker(tLL,{{radius:5,color:'#991b1b',fillColor:'#dc2626',fillOpacity:0.9,weight:1.5}}).bindPopup(`<strong>TO</strong><br/>Seg ${{p.SEGMENT_ID}}: ${{p.RoadName}}<br/>${{p.To}}`));
      }});
      if(!keepView && features.length>0) {{ const all=features.flatMap(f=>f.geometry.coordinates[0].map(c=>[c[1],c[0]])); map.fitBounds(L.latLngBounds(all).pad(0.03)); }}
    }}
    function updateCounts() {{
      const c=allFeatures.length, d=originalCount-c;
      document.getElementById('count').textContent=c+' of '+originalCount+' routed segments';
      const s=document.getElementById('edit-stats');
      if(d>0){{ s.textContent=d+' deleted ('+(d/originalCount*100).toFixed(1)+'%) | '+c+' remaining'; s.style.display=''; }} else {{ s.style.display='none'; }}
    }}
    function downloadGeoJSON() {{
      const blob=new Blob([JSON.stringify({{type:'FeatureCollection',features:allFeatures}})],{{type:'application/geo+json'}});
      const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='{name}_CMS_routed.geojson'; document.body.appendChild(a); a.click(); document.body.removeChild(a);
      showToast('Downloaded '+allFeatures.length+' segments');
    }}
    function showToast(m,d){{ const t=document.getElementById('toast'); t.textContent=m; t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),d||2500); }}
    fetch('/api/backup',{{method:'POST'}}).catch(()=>{{}});
    let lastDeleted=null;
    function deleteSegment(id){{ if(!confirm('Delete Segment '+id+'?')) return; fetch('/api/delete',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{segment_id:id}})}}).then(r=>r.json()).then(d=>{{ if(d.ok){{ allFeatures=allFeatures.filter(f=>f.properties.SEGMENT_ID!==String(id)); renderFeatures(allFeatures,true); updateCounts(); document.getElementById('details').innerHTML='<span style="color:#dc2626;">Segment '+id+' deleted.</span><br/><button class="btn-undo" onclick="undoDelete()">Undo all deletions</button>'; selectedLayer=null; showToast('Segment '+id+' deleted'); }} }}).catch(e=>showToast('Error: '+e.message)); }}
    function undoDelete(){{ fetch('/api/undo',{{method:'POST'}}).then(r=>r.json()).then(d=>{{ if(d.ok) fetch('{name}_CMS_routed.geojson').then(r=>r.json()).then(gj=>{{ allFeatures=gj.features; originalCount=allFeatures.length; renderFeatures(allFeatures); updateCounts(); document.getElementById('details').textContent='Restored. Click a segment.'; showToast('Restored '+d.restored); }}); }}).catch(e=>showToast('Undo failed')); }}
    function showInfo(p) {{
      const flagged=p.Route_Status!=='OK';
      document.getElementById('details').innerHTML=`
        <strong>Segment ${{p.SEGMENT_ID}}</strong><br/><b>${{p.RoadName}}</b><br/>
        <div class="stat"><span>From:</span> <span>${{p.From}}</span></div>
        <div class="stat"><span>To:</span> <span>${{p.To}}</span></div>
        <hr style="margin:6px 0;border:none;border-top:1px solid #e5e7eb;"/>
        <div class="stat"><span>Route distance:</span> <span>${{p.Route_Distance_km}} km</span></div>
        <div class="stat"><span>Straight-line:</span> <span>${{p.Straight_Distance_km}} km</span></div>
        <div class="stat"><span>Detour ratio:</span> <span>${{p.Detour_Ratio}}x</span></div>
        <div class="stat"><span>Route points:</span> <span>${{p.Route_Points}}</span></div>
        <div style="margin-top:6px;">${{flagged?'<span class="popup-flag">\\u26a0 '+p.Route_Status+'</span>':'<span class="popup-ok">\\u2705 Route OK</span>'}}</div>
        <button class="btn-delete" onclick="deleteSegment('${{p.SEGMENT_ID}}')">Delete Segment</button>`;
    }}
    document.getElementById('search').addEventListener('input', function(){{
      const q=this.value.trim().toLowerCase();
      if(!q){{ renderFeatures(allFeatures); updateCounts(); return; }}
      const f=allFeatures.filter(f=>{{ const p=f.properties; return p.RoadName.toLowerCase().includes(q)||p.SEGMENT_ID.toLowerCase().includes(q)||p.From.toLowerCase().includes(q)||p.To.toLowerCase().includes(q); }});
      renderFeatures(f); document.getElementById('count').textContent=f.length+' matching | '+allFeatures.length+' of '+originalCount+' total';
    }});
  </script>
</body>
</html>'''


def generate_server_py(name):
    """Generate server.py for the dataset."""
    return f'''#!/usr/bin/env python3
import json, os, shutil
from http.server import HTTPServer, SimpleHTTPRequestHandler
GEOJSON = os.path.join(os.path.dirname(__file__), "{name}_CMS_routed.geojson")
class H(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path=="/api/delete":
            body=json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))))
            sid=body.get("segment_id")
            if not sid: self.send_response(400); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({{"error":"missing id"}}).encode()); return
            with open(GEOJSON) as f: gj=json.load(f)
            b=len(gj["features"]); gj["features"]=[f for f in gj["features"] if f["properties"]["SEGMENT_ID"]!=str(sid)]; a=len(gj["features"])
            if a==b: self.send_response(404); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({{"error":"not found"}}).encode()); return
            with open(GEOJSON,"w") as f: json.dump(gj,f)
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({{"ok":True,"deleted":str(sid),"remaining":a}}).encode())
        elif self.path=="/api/undo":
            bak=GEOJSON+".bak"
            if os.path.exists(bak):
                os.replace(bak,GEOJSON)
                with open(GEOJSON) as f: gj=json.load(f)
                self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({{"ok":True,"restored":len(gj["features"])}}).encode())
            else: self.send_response(404); self.end_headers()
        elif self.path=="/api/backup":
            shutil.copy2(GEOJSON,GEOJSON+".bak")
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(json.dumps({{"ok":True}}).encode())
        else: self.send_response(404); self.end_headers()
    def log_message(self,*a): pass
if __name__=="__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print(f"{name} CMS Editor on http://localhost:8090")
    HTTPServer(("",8090),H).serve_forever()
'''


# ─── MAIN PIPELINE ────────────────────────────────────────────────
def run_pipeline(input_json, skip_geocode=False):
    with open(input_json) as f:
        data = json.load(f)

    name = data["name"]
    region = data["region"]
    segments = data["segments"]
    total = len(segments)

    # Import dataset config
    from extract_all import DATASETS
    cfg = DATASETS.get(name, {})
    county_name = cfg.get("county", name)
    county_fips = cfg.get("county_fips", "")
    geocode_suffix = cfg.get("geocode_suffix", f"{county_name} County, FL")

    print(f"\n{'='*60}")
    print(f"  {name} CMS Pipeline — {total} segments")
    print(f"  Region: {region}")
    print(f"{'='*60}\n")

    # ── Setup output directory ──
    out_dir = os.path.join(os.path.dirname(os.path.abspath(input_json)), name)
    os.makedirs(out_dir, exist_ok=True)
    results_dir = os.path.join(out_dir, "results")
    os.makedirs(results_dir, exist_ok=True)

    # ── Get county boundary ──
    print("[1/5] Loading county boundary...")
    county_poly, county_feat = get_county_boundary(county_name, county_fips)
    if not county_poly:
        print(f"  ERROR: Could not find boundary for {county_name}")
        return
    bbox, c_lon, c_lat = get_bbox_and_center(county_poly)
    print(f"  Found {county_name} boundary. BBox: {bbox}")

    # Save boundary
    boundary_gj = {"type": "FeatureCollection", "features": [county_feat]}
    for p in ["boundary.geojson"]:
        with open(os.path.join(out_dir, p), "w") as f:
            json.dump(boundary_gj, f)

    # ── Geocode ──
    print(f"\n[2/5] Geocoding {total} segments via ArcGIS...")
    features = []
    geocode_ok = 0
    geocode_fail = 0

    for idx, seg in enumerate(segments):
        sid = seg["id"]
        road = seg["road"]
        frm = seg["from"]
        to = seg["to"]

        # Check if already has coords (Apopka)
        if "lat" in seg and "lon" in seg and seg["lat"] and seg["lon"]:
            # Single point — need to geocode the other endpoint too
            pass

        if not skip_geocode:
            # Geocode FROM
            q_from = f"{road} & {frm}, {geocode_suffix}"
            time.sleep(0.12)
            f_lon, f_lat, f_score = geocode_arcgis(q_from, bbox, c_lon, c_lat)

            # Geocode TO
            q_to = f"{road} & {to}, {geocode_suffix}"
            time.sleep(0.12)
            t_lon, t_lat, t_score = geocode_arcgis(q_to, bbox, c_lon, c_lat)

            if f_lon is None or t_lon is None:
                geocode_fail += 1
                if (idx + 1) % 50 == 0:
                    print(f"  [{idx+1}/{total}] {road[:30]:30s} ** GEOCODE FAILED **")
                continue

            # Check for zero-length
            if abs(f_lon - t_lon) < 0.0001 and abs(f_lat - t_lat) < 0.0001:
                # Try alternative queries
                q_alt = f"{frm} & {road}, {geocode_suffix}"
                time.sleep(0.12)
                f_lon2, f_lat2, _ = geocode_arcgis(q_alt, bbox, c_lon, c_lat)
                if f_lon2 and (abs(f_lon2 - t_lon) > 0.0001 or abs(f_lat2 - t_lat) > 0.0001):
                    f_lon, f_lat = f_lon2, f_lat2

            geocode_ok += 1
            feat = {
                "type": "Feature",
                "geometry": {"type": "MultiLineString", "coordinates": [[[f_lon, f_lat], [t_lon, t_lat]]]},
                "properties": {
                    "SEGMENT_ID": str(sid), "RoadName": road, "From": frm, "To": to,
                    "From_Score": round(f_score, 1), "To_Score": round(t_score, 1),
                }
            }
            features.append(feat)

            if (idx + 1) % 50 == 0 or idx == 0:
                print(f"  [{idx+1}/{total}] {geocode_ok} ok, {geocode_fail} failed")

    print(f"  Geocoding complete: {geocode_ok}/{total} ({geocode_fail} failed)")

    # ── Route ──
    print(f"\n[3/5] Routing {len(features)} segments via Valhalla (shortest)...")
    route_ok = 0
    route_fail = 0

    for idx, feat in enumerate(features):
        coords = feat["geometry"]["coordinates"][0]
        f_lon, f_lat = coords[0]
        t_lon, t_lat = coords[-1]

        time.sleep(0.55)
        result = valhalla_route(f_lon, f_lat, t_lon, t_lat)

        if result:
            route_coords, route_km = result
            straight_km = haversine(f_lon, f_lat, t_lon, t_lat)
            detour = route_km / straight_km if straight_km > 0.05 else 1.0

            feat["geometry"]["coordinates"] = [route_coords]
            feat["properties"]["Route_Distance_km"] = round(route_km, 2)
            feat["properties"]["Straight_Distance_km"] = round(straight_km, 2)
            feat["properties"]["Detour_Ratio"] = round(detour, 2)
            feat["properties"]["Route_Points"] = len(route_coords)
            feat["properties"]["Route_Status"] = "OK" if detour < 5 else f"HIGH_DETOUR:{detour:.1f}x"
            route_ok += 1
        else:
            # Keep as straight line
            straight_km = haversine(f_lon, f_lat, t_lon, t_lat)
            feat["properties"]["Route_Distance_km"] = round(straight_km, 2)
            feat["properties"]["Straight_Distance_km"] = round(straight_km, 2)
            feat["properties"]["Detour_Ratio"] = 1.0
            feat["properties"]["Route_Points"] = 2
            feat["properties"]["Route_Status"] = "STRAIGHT_LINE"
            route_fail += 1

        if (idx + 1) % 50 == 0 or idx == 0:
            print(f"  [{idx+1}/{len(features)}] {route_ok} routed, {route_fail} straight-line")

    print(f"  Routing complete: {route_ok} routed, {route_fail} straight-line")

    # ── Clip ──
    print(f"\n[4/5] Clipping routes to {county_name} boundary...")
    clipped_count = 0
    total_pts_before = 0
    total_pts_after = 0
    oob_before = 0

    for feat in features:
        coords = feat["geometry"]["coordinates"][0]
        total_pts_before += len(coords)

        # Count OOB
        oob = sum(1 for c in coords if not in_polygon(c[0], c[1], county_poly))
        if oob > len(coords) * 0.02 and oob > 2:
            oob_before += oob
            new_coords = clip_route(coords, county_poly)
            if len(new_coords) >= 2:
                feat["geometry"]["coordinates"] = [new_coords]
                feat["properties"]["Route_Points"] = len(new_coords)
                feat["properties"]["Route_Status"] = "CLIPPED"
                clipped_count += 1
            total_pts_after += len(feat["geometry"]["coordinates"][0])
        else:
            total_pts_after += len(coords)

    # Final OOB count
    final_oob = 0
    final_total = 0
    for feat in features:
        coords = feat["geometry"]["coordinates"][0]
        for c in coords:
            final_total += 1
            if not in_polygon(c[0], c[1], county_poly):
                final_oob += 1

    pct = final_oob / final_total * 100 if final_total > 0 else 0
    print(f"  Clipped {clipped_count} segments")
    print(f"  Final: {final_oob}/{final_total} OOB points ({pct:.3f}%)")

    # ── Save outputs ──
    print(f"\n[5/5] Saving outputs to {out_dir}/...")

    geojson = {"type": "FeatureCollection", "features": features}
    gj_path = os.path.join(out_dir, f"{name}_CMS_routed.geojson")
    with open(gj_path, "w") as f:
        json.dump(geojson, f)
    print(f"  {gj_path} ({len(features)} features)")

    # QA report
    statuses = {}
    for feat in features:
        s = feat["properties"].get("Route_Status", "?")
        statuses[s] = statuses.get(s, 0) + 1
    qa = {
        "name": name, "region": region, "total_input": total,
        "geocoded": geocode_ok, "geocode_failed": geocode_fail,
        "routed": route_ok, "route_failed": route_fail,
        "clipped": clipped_count, "total_route_points": final_total,
        "oob_points": final_oob, "oob_pct": round(pct, 4),
        "statuses": statuses,
    }
    qa_path = os.path.join(out_dir, "qa_report.json")
    with open(qa_path, "w") as f:
        json.dump(qa, f, indent=2)

    # Map HTML
    html_path = os.path.join(out_dir, "index.html")
    with open(html_path, "w") as f:
        f.write(generate_map_html(name, region))

    # Server
    srv_path = os.path.join(out_dir, "server.py")
    with open(srv_path, "w") as f:
        f.write(generate_server_py(name))

    # Copy to results
    import shutil
    for fname in [f"{name}_CMS_routed.geojson", "boundary.geojson", "index.html",
                  "server.py", "qa_report.json"]:
        src = os.path.join(out_dir, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(results_dir, fname))

    print(f"\n{'='*60}")
    print(f"  {name} COMPLETE")
    print(f"  Segments: {len(features)}/{total}")
    print(f"  Route points: {final_total}")
    print(f"  OOB: {final_oob} ({pct:.3f}%)")
    print(f"  Statuses: {statuses}")
    print(f"  Output: {out_dir}/")
    print(f"  Results: {results_dir}/")
    print(f"{'='*60}\n")

    return qa


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 cms_pipeline.py <segments.json>")
        sys.exit(1)
    run_pipeline(sys.argv[1], skip_geocode="--skip-geocode" in sys.argv)
