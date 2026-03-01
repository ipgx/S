# Florida CMS Multi-County Pipeline — Master Summary

## Overview

This project processed **2,785 roadway segments** across **7 Florida geographic regions** from Excel-based Congestion Management System (CMS) inventories into routed GeoJSON geometries with interactive Leaflet editor maps.

**Total processing time: ~106 minutes** (Apopka 7.6 min + remaining 6 in 98.7 min)

---

## Pipeline Architecture

### Stage 1: Extraction (`extract_all.py`)
- Parses 7 Excel files with unique structures (different header rows, column layouts, segment formats)
- Custom extractor per dataset handles format-specific parsing (e.g., "From to To" splitting, directional deduplication)
- Outputs standardized `{Name}_segments.json` files

### Stage 2: Processing (`cms_pipeline.py`)
5-stage pipeline per dataset:

| Stage | Process | Technology |
|-------|---------|------------|
| 1 | Load county boundary | FL_Counties.geojson (polygon extraction) |
| 2 | Geocode intersections | ArcGIS World Geocoding Service (REST, bbox-biased) |
| 3 | Route segments | Valhalla FOSSGIS (`shortest` distance mode) |
| 4 | Clip to boundary | Ray-casting PIP + line-segment intersection |
| 5 | Save outputs | GeoJSON, Leaflet HTML, server.py, QA report |

### Stage 3: Runner (`run_all.py`)
- Sequential execution of all datasets
- Progress reporting and final summary table

---

## Results Summary

| Dataset | Region | Segments | Geocoded | Routed | Straight-Line | Clipped | High Detour | OOB % | Route Points |
|---------|--------|----------|----------|--------|--------------|---------|-------------|-------|-------------|
| **Apopka** | City of Apopka, Orange County | 193 | 193 (100%) | 190 | 3 | 3 | 1 | 0.055% | 7,295 |
| **Osceola** | Osceola County | 246 | 246 (100%) | 239 | 7 | 15 | 5 | 0.096% | 21,822 |
| **Palm Beach** | Palm Beach County | 293 | 293 (100%) | 288 | 5 | 0 | 2 | 0.006% | 17,412 |
| **Seminole** | Seminole County | 488 | 488 (100%) | 475 | 13 | 11 | 5 | 0.136% | 25,743 |
| **St. Lucie** | St. Lucie County | 497 | 497 (100%) | 484 | 13 | 6 | 12 | 0.013% | 22,467 |
| **Hillsborough** | Hillsborough County | 507 | 507 (100%) | 496 | 11 | 10 | 10 | 0.063% | 55,450 |
| **Polk** | Polk County | 561 | 561 (100%) | 539 | 22 | 14 | 2 | 0.024% | 74,760 |
| **TOTAL** | — | **2,785** | **2,785 (100%)** | **2,711** | **74** | **59** | **37** | — | **224,949** |

### Key Metrics
- **Geocoding success rate**: 100% (2,785/2,785) — zero failures across all datasets
- **Routing success rate**: 97.3% (2,711/2,785) — 74 segments fell back to straight-line
- **Boundary compliance**: All datasets < 0.14% OOB (out-of-boundary) points
- **High detour flags**: 37 segments flagged (route > 5x straight-line distance) — candidates for manual review

---

## Segment Status Definitions

| Status | Description |
|--------|-------------|
| **OK** | Successfully geocoded, routed via Valhalla, all points within county boundary |
| **STRAIGHT_LINE** | Valhalla routing failed (private/restricted road); straight line drawn between endpoints |
| **CLIPPED** | Route extended beyond county boundary; trimmed at boundary crossing point |
| **HIGH_DETOUR:Nx** | Route distance is N times the straight-line distance (flagged at > 5x threshold) |

---

## Output Structure

Each dataset folder contains:

```
ALL-CMS/
  {Name}/
    {Name}_CMS_routed.geojson   # Routed MultiLineString features
    boundary.geojson             # County boundary polygon
    index.html                   # Interactive Leaflet map with editor
    server.py                    # Python dev server with delete/undo/backup API
    qa_report.json               # Machine-readable QA metrics
    results/                     # Backup copy of all deliverables
      (same 5 files)
```

### Leaflet Map Features
Each `index.html` provides:
- **Interactive map** with OpenStreetMap tiles and county boundary overlay
- **Search bar** — filter segments by road name, segment ID, or status
- **Color-coded segments** — OK (blue), STRAIGHT_LINE (orange), CLIPPED (purple), HIGH_DETOUR (red)
- **Dark red hover highlight** — segments highlight `#8b0000` on mouseover
- **Click info panel** — shows segment ID, road name, from/to intersections, status, route points
- **Delete segment** — remove segments from the dataset (button in info panel)
- **Undo all deletions** — restore all deleted segments
- **Download GeoJSON** — export current (edited) dataset
- **Deletion stats** — live counter showing deleted count, remaining, and percentage
- **Layer toggles** — toggle boundary, OK, STRAIGHT_LINE, CLIPPED, HIGH_DETOUR layers

### Running a Map
```bash
cd ALL-CMS/{Name}
python3 server.py
# Open http://localhost:8090
```

---

## Source Excel Files

| File | Dataset | Segments Extracted |
|------|---------|-------------------|
| `Apopka CMS Segment Inventory.xlsx` | Apopka | 193 |
| `Hillsborough CMS Segment Inventory.xlsx` | Hillsborough | 507 |
| `Osceola CMS Segment Inventory.xlsx` | Osceola | 246 |
| `Palm Beach CMS Segment Inventory.xlsx` | Palm Beach | 293 |
| `Polk CMS Segment Inventory.xlsx` | Polk | 561 (deduplicated from directional pairs) |
| `Seminole CMS Segment Inventory.xlsx` | Seminole | 488 |
| `St Lucie CMS Segment Inventory.xlsx` | St. Lucie | 497 |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `extract_all.py` | Parse all 7 Excel files into standardized segment JSON |
| `cms_pipeline.py` | 5-stage pipeline: boundary → geocode → route → clip → save |
| `run_all.py` | Master runner for batch processing all datasets |

---

## Technologies

| Component | Technology | Details |
|-----------|-----------|---------|
| Geocoding | ArcGIS World Geocoding Service | REST API, bounding-box biased to county |
| Routing | Valhalla (FOSSGIS) | `https://valhalla1.openstreetmap.de/route`, shortest distance |
| Boundary | FL_Counties.geojson | US Census TIGER county polygons |
| Mapping | Leaflet.js 1.9 | Interactive web map with editor |
| Server | Python 3 http.server | Custom POST API for segment editing |
| Excel parsing | openpyxl | Python library for .xlsx files |
| Geometry | Custom Python | Ray-casting PIP, line-segment intersection, polyline decoding |

---

## Processing Times

| Dataset | Segments | Time |
|---------|----------|------|
| Apopka | 193 | 7.6 min |
| Osceola | 246 | 9.3 min |
| Palm Beach | 293 | 10.9 min |
| Seminole | 488 | 18.1 min |
| St. Lucie | 497 | 18.9 min |
| Hillsborough | 507 | 19.4 min |
| Polk | 561 | 22.1 min |
| **Total** | **2,785** | **~106 min** |

*Rate-limited by ArcGIS (0.12s/request) and Valhalla (0.55s/request) API throttling to avoid rate limits.*
