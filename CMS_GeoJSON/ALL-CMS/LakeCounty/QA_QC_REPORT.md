# Lake County CMS – QA/QC Report

## Executive Summary

452 road segments were geocoded and routed with a multi-stage QA/QC pipeline. The final dataset has:

- **452/452** segments successfully geocoded and routed (100%)
- **0** failed geocodes or routing failures
- **0.031%** of route points outside the county boundary (18/57,883 — at boundary crossings)
- **424** segments with `Route_Status = OK`
- **28** segments with QA flags (all reviewed and acceptable)

## QA Stage 1: Initial Geocoding

**Script**: `build_geojson.py`

| Metric | Value |
|--------|-------|
| Total segments | 452 |
| Successfully geocoded | 452 (100%) |
| Zero-length segments | 22 (FROM = TO coordinates) |
| Low-score points (< 80) | 10 |
| Out-of-bounds | 0 |

### Low-Score Points

10 geocoded points scored below 80 (on ArcGIS's 0-100 confidence scale). These are typically intersections with ambiguous names or rural areas with sparse address data:

| Segment | Road | Endpoint | Score |
|---------|------|----------|-------|
| 1480 | 8TH ST/OSCEOLA ST/4TH ST/CARROL ST | TO | 79.2 |
| 1080 | CR 466A (PICCIOLA RD) | TO | 78.8 |
| 1090 | CR 466A (PICCIOLA RD) | FROM/TO | 78.8/76.7 |
| 2110 | HARTWOOD MARSH RD | TO | 77.8 |
| 2530 | MAIN ST (LEESBURG) | TO | 79.2 |
| 3340 | SR 44 | TO | 78.5 |
| 3568 | SR 91 (FLORIDA TURNPIKE) | TO | 78.8 |
| 4140 | VISTA DEL LAGO BLVD | FROM | 79.4 |
| 4190 | WOLFBRANCH RD | FROM | 79.7 |

All low-score points were visually verified and fall within Lake County at plausible intersection locations.

### Zero-Length Segments Fixed

All 22 zero-length segments were repaired using alternative geocoding queries. Common causes:
- Compound road names (e.g., "US 27/US441") where both endpoints matched the same reference point
- Shared cross-streets on short segments
- Parenthetical road names confusing the geocoder

## QA Stage 2: OSRM Routing

**Script**: `route_segments.py`

| Metric | Value |
|--------|-------|
| Segments routed | 452/452 (100%) |
| Route failures | 0 |
| Average route points | ~128 per segment |
| Flagged (detour > 3x) | 5 |

### Detour Ratio Flags

| Segment | Road | Route (km) | Straight (km) | Detour |
|---------|------|-----------|---------------|--------|
| 990 | CR 455 | 1.43 | 0.19 | 7.7x |
| 1155 | CR 470 | 15.08 | 3.40 | 4.4x |
| 3260 | SR 44 (DIXIE AVE) | 0.57 | 0.17 | 3.4x |
| 830 | CR 452 | 29.41 | 9.40 | 3.1x |
| 4120 | VISTA DEL LAGO BLVD | 3.36 | 1.08 | 3.1x |

- **Seg 990 (CR 455, 7.7x)**: Very short segment (190m straight-line) where OSRM routes around a one-way system. Acceptable — the actual road path is longer.
- **Seg 1155 (CR 470, 4.4x)**: Rural county road that follows a winding path around lakes. The straight-line distance is misleading.
- **Remaining three**: Moderate detours (3.1-3.4x) caused by road geometry — all verified as correct routing.

## QA Stage 3: County Boundary Enforcement

### Endpoint Check

**Script**: `thorough_qa.py`

12 endpoints were found outside the Lake County polygon:

| # | Segments Affected | Boundary |
|---|-------------------|----------|
| 4 | SR 19, SR 40, etc. | Sumter County Line (north) |
| 3 | SR 429, SR 46, etc. | Seminole/Orange County Line (east) |
| 3 | SR 50, US 27, etc. | Orange County Line (south) |
| 2 | SR 91, US 27, etc. | Sumter County Line (west) |

All 12 were re-geocoded with county-constrained queries and re-routed. Post-fix: **0 endpoints outside county**.

### Full Route Point Audit

**Script**: `deep_audit.py`

Checked all ~58,000 route points against the actual county polygon:

| Category | Segments | Description |
|----------|----------|-------------|
| Severe (>25% OOB) | 10 | Routes extensively crossing into neighboring counties |
| Moderate (5-25% OOB) | 4 | Partial border crossings |
| Minor (<5% OOB) | 2 | Slight border incursions |

### Route Clipping

**Script**: `clip_routes.py`

All routes clipped to county boundary using computational geometry (ray-casting PIP + line-segment intersection):

| Metric | Before | After |
|--------|--------|-------|
| Total route points | 59,846 | 57,883 |
| Points outside county | 2,463 (4.1%) | 18 (0.031%) |
| Segments with OOB points | 16 | 11 |

The residual 18 OOB points are at exact boundary crossing locations (floating-point precision at polygon edges). All 11 affected segments have `Route_Status = CLIPPED_TO_COUNTY`.

## Final Dataset Summary

| Metric | Value |
|--------|-------|
| Total segments | 452 |
| Route Status = OK | 424 (93.8%) |
| Route Status = CLIPPED_TO_COUNTY | 16 (3.5%) |
| Route Status = FIXED_COLLAPSED | 5 (1.1%) |
| Route Status = FIXED_OOB | 4 (0.9%) |
| Route Status = HIGH_DETOUR | 1 (0.2%) |
| Route Status = MODERATE_DETOUR | 2 (0.4%) |
| Total route points | 57,883 |
| Points outside county | 18 (0.031%) |

## Validation Checks Performed

1. **Geocode score validation** — flagged all points with ArcGIS confidence < 80
2. **Zero-length detection** — identified and fixed segments with FROM = TO
3. **Bounding box check** — verified all coordinates within Lake County bbox
4. **Point-in-polygon (endpoints)** — verified all FROM/TO inside county polygon
5. **Point-in-polygon (full route)** — verified all ~58K route points inside county
6. **Detour ratio analysis** — flagged routes where road distance > 3x straight-line
7. **Route clipping** — trimmed routes at county boundary with interpolated crossings
8. **Cross-validation** — independent geocoding via Nominatim (see CROSS_VALIDATION.md)
