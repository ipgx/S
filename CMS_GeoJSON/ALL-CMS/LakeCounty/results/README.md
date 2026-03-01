# Lake County Congestion Management System (CMS) – Routed Segments

## Overview

This project maps **452 road segments** from the Lake County Congestion Management System into GeoJSON format with accurate, road-following geometries. Starting from a flat CSV of segment IDs, road names, and intersection descriptions, the pipeline geocodes endpoints, routes along actual road centerlines, clips to the county boundary, and validates through an 8-stage QA/QC process.

**Geography**: Lake County, Florida (FIPS 12069)
**Source**: [github.com/ipgx/Lake-Cty-CMS](https://github.com/ipgx/Lake-Cty-CMS)

---

## Quick Stats

| Metric | Value |
|--------|-------|
| Total segments | 452 |
| Total route kilometers | 3,186.4 km |
| Total route points | 59,321 |
| Average segment length | 7.07 km |
| Average points per segment | 131 |
| Geocoding success rate | 100% (452/452) |
| Routing success rate | 100% (452/452) |
| Route points inside county | 99.97% (59,303/59,321) |
| Clean QA status (OK) | 93.8% (425/452) |

---

## Pipeline

The processing pipeline has 7 stages, each with its own script:

```
CSV (452 segments)
  |
  v
[1] build_geojson.py ---- ArcGIS geocoding --> 2-point straight lines
  |
  v
[2] fix_zero_length.py -- Fix 22 collapsed segments
  |
  v
[3] route_segments.py --- OSRM routing --> road-following geometry
  |
  v
[4] thorough_qa.py ------ Fix 12 out-of-county endpoints
  |
  v
[5] fix_collapsed.py ---- Fix 5 re-collapsed segments
  |
  v
[6] deep_audit.py ------- Full route point audit (58K points)
  |
  v
[7] clip_routes.py ------ Clip routes to county boundary
  |
  v
[8] reroute_shortest.py - Re-route with Valhalla (shortest distance)
  |
  v
Final GeoJSON (452 segments, 59K route points, 99.97% in-county)
```

### Stage 1: Intersection Geocoding

Each segment's FROM and TO intersections are geocoded via the **ArcGIS World Geocoding Service**. Query format: `"{RoadName} & {Intersection}, Lake County, FL"` with a geographic bias toward Lake County.

- 452/452 geocoded (100%)
- 22 zero-length segments (FROM = TO)
- 10 low-confidence points (score < 80)

### Stage 2: Zero-Length Repair

22 segments where both endpoints geocoded identically were fixed using alternative queries: simplified road names, reversed intersection order, and town-specific queries. All 22 resolved.

### Stage 3: Road Routing

Straight-line segments replaced with actual road geometry via **OSRM** (Open Source Routing Machine). Later re-routed with **Valhalla** using shortest-distance optimization (431/452 segments). 21 segments retained OSRM routes where Valhalla couldn't find a path.

### Stage 4: Out-of-County Endpoint Fix

Point-in-polygon testing against the actual Lake County boundary (447-vertex MultiPolygon from FL_Counties.geojson) found 12 endpoints outside the county. All re-geocoded with county-constrained queries.

### Stage 5: Collapsed Segment Repair

5 segments collapsed to zero-length after endpoint corrections. Fixed with distinct geocoding ensuring minimum 0.001-degree separation.

### Stage 6: Full Route Point Audit

Every route point (~58,000) checked against the county polygon. Found 16 segments with points outside the county where routes crossed into neighboring counties.

### Stage 7: Route Clipping

Routes clipped to the county boundary using ray-casting PIP and line-segment intersection:

| Metric | Before | After |
|--------|--------|-------|
| Points outside county | 2,463 (4.1%) | 18 (0.031%) |
| Segments with OOB | 16 | 11 |

Residual 18 points are at exact boundary crossings (floating-point precision).

### Stage 8: Shortest-Distance Re-Routing

All segments re-routed via **Valhalla** (FOSSGIS instance) with `shortest: true` costing. 102 segments got shorter routes compared to OSRM's fastest-time routing.

---

## Output Files

| File | Size | Description |
|------|------|-------------|
| `Lake_County_CMS_routed.geojson` | 1.9 MB | **Production file** — 452 routed segments with road-following geometry |
| `Lake_County_CMS.geojson` | 311 KB | Intermediate — 2-point straight-line segments (ArcGIS endpoints) |
| `Lake_County_Boundary.geojson` | 39 KB | Lake County boundary polygon (FIPS 12069) |
| `index.html` | 15 KB | Interactive Leaflet map with editor (search, delete, download) |
| `server.py` | 3.8 KB | Python dev server with delete/undo/backup API |
| `cross_validation_results.json` | 30 KB | ArcGIS vs Nominatim comparison (60-segment sample) |
| `qa_report.json` | 3.3 KB | Initial geocoding QA report |
| `qa_routing_report.json` | 1.0 KB | Routing QA report |

### Processing Scripts

| Script | Description |
|--------|-------------|
| `build_geojson.py` | Step 1 — ArcGIS geocoding of 452 segments |
| `fix_zero_length.py` | Step 2 — Fix 22 zero-length segments |
| `route_segments.py` | Step 3 — OSRM road routing |
| `thorough_qa.py` | Step 4 — PIP endpoint check + fix 12 OOB endpoints |
| `fix_collapsed.py` | Step 5 — Fix 5 re-collapsed segments |
| `deep_audit.py` | Step 6 — Full route point audit |
| `clip_routes.py` | Step 7 — Clip routes to county boundary |
| `reroute_shortest.py` | Step 8 — Valhalla shortest-distance re-routing |
| `cross_validate_sample.py` | Cross-validation via Nominatim (60-segment sample) |

---

## GeoJSON Feature Properties

Each feature in `Lake_County_CMS_routed.geojson` includes:

| Property | Type | Description |
|----------|------|-------------|
| `SEGMENT_ID` | string | Unique CMS segment identifier |
| `RoadName` | string | Road name (e.g., "SR 19", "CR 466A (PICCIOLA RD)") |
| `From` | string | FROM intersection description |
| `To` | string | TO intersection description |
| `Route_Distance_km` | float | Routed road distance in kilometers |
| `Straight_Distance_km` | float | Haversine straight-line distance |
| `Detour_Ratio` | float | Route / straight-line distance ratio |
| `Route_Points` | int | Number of coordinate points in the geometry |
| `Route_Status` | string | QA flag (OK, CLIPPED_TO_COUNTY, FIXED_OOB, etc.) |
| `Routing_Engine` | string | "Valhalla (shortest)" or "OSRM (fastest)" |

### Route Status Values

| Status | Count | Description |
|--------|-------|-------------|
| `OK` | 425 | Clean — no issues detected |
| `CLIPPED_TO_COUNTY` | 16 | Route clipped at county boundary |
| `FIXED_COLLAPSED` | 5 | Re-geocoded after zero-length collapse |
| `FIXED_OOB` | 4 | Endpoint re-geocoded from outside county |
| `MODERATE_DETOUR` | 2 | Detour ratio 3-5x (verified correct) |

---

## Interactive Map

The Leaflet web map (`index.html`) provides:

- **Search** — filter by road name, segment ID, or intersection
- **Layer toggles** — county boundary, OK segments, flagged segments, FROM/TO points
- **Click to inspect** — route distance, detour ratio, point count, QA status
- **Hover highlight** — dark red highlight on mouseover
- **Delete segments** — remove unwanted segments with confirmation
- **Undo** — restore all deletions from backup
- **Download** — export current GeoJSON (with deletions applied)

### Running the Map

```bash
cd Lake_County_CMS
python3 server.py
# Open http://localhost:8090
```

---

## QA/QC Summary

An 8-check validation pipeline was applied:

1. **Geocode score validation** — flagged points with ArcGIS confidence < 80
2. **Zero-length detection** — identified and fixed 22 segments with FROM = TO
3. **Bounding box check** — all coordinates within Lake County bbox
4. **Point-in-polygon (endpoints)** — all FROM/TO inside county polygon
5. **Point-in-polygon (full route)** — all 59K route points checked
6. **Detour ratio analysis** — flagged routes > 3x straight-line distance
7. **Route clipping** — trimmed routes at county boundary with interpolated crossings
8. **Cross-validation** — independent geocoding via Nominatim/OSM

See [QA_QC_REPORT.md](QA_QC_REPORT.md) for full details.

---

## Cross-Validation

A stratified sample of 60 segments (120 endpoints) was cross-checked against **Nominatim (OpenStreetMap)** as an independent geocoding source.

| Metric | Value |
|--------|-------|
| Nominatim found | 91/120 (76%) |
| Agreement < 500m | 12 (13% of found) |
| Agreement 500-2000m | 26 (29% of found) |
| Divergence > 2000m | 53 (58% of found) |
| Not found | 29 (24%) |

The high divergence is **expected** — Nominatim struggles with intersection-based queries, compound Florida road names (e.g., "US 27/SR 25"), and rural intersections. Where Nominatim correctly identifies the intersection, it converges with ArcGIS (< 500m). The cross-validation confirms ArcGIS as the stronger geocoder for this use case.

See [CROSS_VALIDATION.md](CROSS_VALIDATION.md) for full analysis.

---

## Tools & Services

| Tool | Purpose |
|------|---------|
| ArcGIS World Geocoding Service | Primary intersection geocoding |
| Valhalla (FOSSGIS) | Shortest-distance road routing (431 segments) |
| OSRM Demo Server | Fastest-time road routing (21 segments, fallback) |
| Nominatim (OpenStreetMap) | Cross-validation geocoding |
| Python 3 (stdlib only) | All scripts — zero external dependencies |
| Leaflet.js + OpenStreetMap | Interactive web map |
| FL_Counties.geojson | County boundary for PIP checks and clipping |

---

## Documentation

| Document | Description |
|----------|-------------|
| [README.md](README.md) | This file — project overview |
| [METHODOLOGY.md](METHODOLOGY.md) | Detailed pipeline documentation |
| [QA_QC_REPORT.md](QA_QC_REPORT.md) | Full QA/QC findings and fixes |
| [CROSS_VALIDATION.md](CROSS_VALIDATION.md) | ArcGIS vs Nominatim comparison |
