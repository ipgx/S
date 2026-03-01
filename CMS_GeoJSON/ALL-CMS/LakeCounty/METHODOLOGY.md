# Lake County CMS – Methodology

## Overview

This project maps 452 road segments from the Lake County Congestion Management System (CMS) into GeoJSON format with accurate, road-following geometries. The input is a flat CSV with segment IDs, road names, and intersection-based FROM/TO descriptions. The output is a fully routed GeoJSON file where each segment follows actual road centerlines.

## Data Source

- **Input**: `Segments.csv` — 452 records with columns `SEGMENT_ID`, `RoadName`, `From`, `To`
- **Repository**: [github.com/ipgx/Lake-Cty-CMS](https://github.com/ipgx/Lake-Cty-CMS)
- **Geography**: Lake County, Florida (FIPS 12069)

## Pipeline

### Step 1: Intersection Geocoding (ArcGIS)

Each segment has two intersection endpoints (FROM and TO). These are geocoded using the **ArcGIS World Geocoding Service** REST API:

```
https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates
```

**Query format**: `"{RoadName} & {Intersection}, Lake County, FL"`

**Parameters**:
- `searchExtent`: `-82.05,28.35,-81.20,29.10` (Lake County bounding box)
- `location`: `-81.6,28.7` (Lake County centroid bias)
- `distance`: 80,000m (proximity radius)
- `maxLocations`: 5 (candidate pool)

**Result**: 452/452 segments geocoded (100% success rate). Initial geocoding produced 22 zero-length segments (FROM = TO) and 10 low-score points (score < 80).

**Script**: `build_geojson.py`

### Step 2: Zero-Length Segment Repair

22 segments where FROM and TO geocoded to identical coordinates were fixed using a multi-strategy approach:

1. Simplified road names (remove parentheticals, split compound names)
2. Reversed intersection order (`{To} & {Road}`)
3. Town-specific queries (Leesburg, Eustis, Mount Dora, Tavares, Clermont, etc.)
4. Cross-street-only queries as fallback

All 22 segments successfully resolved to distinct endpoints.

**Script**: `fix_zero_length.py`

### Step 3: Road Routing (OSRM)

Straight-line segments were replaced with actual road-following geometries using the **OSRM (Open Source Routing Machine)** demo API:

```
http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson
```

**Result**: 452/452 segments routed. Average ~128 route points per segment. 5 segments flagged for elevated detour ratios (route distance / straight-line distance > 3x).

**Script**: `route_segments.py`

### Step 4: Out-of-County Endpoint Correction

Point-in-polygon (PIP) testing against the actual Lake County boundary polygon (from `FL_Counties.geojson`, 447-vertex MultiPolygon) identified 12 endpoints geocoded outside the county.

These were re-geocoded using county-constrained queries with PIP validation on each candidate, then re-routed.

**Script**: `thorough_qa.py`

### Step 5: Collapsed Segment Repair

After endpoint corrections, 5 segments collapsed to zero-length (re-geocoded FROM and TO landed at the same point). These were fixed with distinct geocoding strategies ensuring minimum separation of 0.001 degrees between endpoints.

**Script**: `fix_collapsed.py`

### Step 6: Full Route Point Audit

A deep audit checked every one of the ~58,000 route points (not just endpoints) against the county boundary polygon. Found 16 segments with route points outside the county — roads near borders where OSRM routed through neighboring counties.

**Script**: `deep_audit.py`

### Step 7: Route Clipping to County Boundary

All routes were clipped to the Lake County boundary using:

- **Ray-casting PIP** for each route point
- **Line-segment intersection** to compute exact boundary crossing points
- Clipped routes retain the in-county portion with interpolated crossing points at the boundary

**Result**: Out-of-boundary points reduced from 2,463 (4.1%) to 18 (0.031%) — the residual 18 points sit right at boundary crossings within floating-point precision.

**Script**: `clip_routes.py`

## Output Files

| File | Description |
|------|-------------|
| `Lake_County_CMS_routed.geojson` | Final production GeoJSON — 452 MultiLineString features with OSRM road-following geometry, clipped to county boundary |
| `Lake_County_CMS.geojson` | Intermediate file — 2-point straight-line segments (ArcGIS endpoints only) |
| `Lake_County_Boundary.geojson` | Lake County boundary polygon extracted from FL_Counties.geojson |
| `cross_validation_results.json` | ArcGIS vs Nominatim cross-validation results |
| `qa_report.json` | Initial geocoding QA report |
| `qa_routing_report.json` | Routing QA report |
| `index.html` | Interactive Leaflet web map |

## Feature Properties

Each GeoJSON feature includes:

| Property | Description |
|----------|-------------|
| `SEGMENT_ID` | Unique segment identifier from the CMS |
| `RoadName` | Road name (e.g., "SR 19", "CR 466A") |
| `From` | FROM intersection description |
| `To` | TO intersection description |
| `Route_Distance_km` | OSRM-routed road distance in kilometers |
| `Straight_Distance_km` | Haversine straight-line distance |
| `Detour_Ratio` | Route distance / straight-line distance |
| `Route_Points` | Number of coordinate points in the route geometry |
| `Route_Status` | QA status flag (OK, CLIPPED_TO_COUNTY, FIXED_OOB, HIGH_DETOUR, etc.) |

## Tools and Services Used

| Tool | Purpose |
|------|---------|
| ArcGIS World Geocoding Service | Primary intersection geocoding |
| OSRM Demo Server | Road-following route geometry |
| Nominatim (OpenStreetMap) | Independent cross-validation geocoding |
| Python 3 (stdlib only) | All processing scripts — no external dependencies |
| Leaflet.js | Interactive web map visualization |
| FL_Counties.geojson | County boundary polygon for PIP checks and clipping |
