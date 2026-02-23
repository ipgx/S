<div align="center">

# S

**Interactive GIS Road Segment Analyzer for Orange County, Florida**

[![MapLibre](https://img.shields.io/badge/MapLibre_GL_JS-4.7.1-blue?logo=mapbox&logoColor=white)](#tech-stack)
[![Tabulator](https://img.shields.io/badge/Tabulator-6.3.0-green)](#tech-stack)
[![Turf.js](https://img.shields.io/badge/Turf.js-7.x-orange)](#tech-stack)
[![Electron](https://img.shields.io/badge/Electron-33+-purple?logo=electron&logoColor=white)](#tech-stack)
[![License](https://img.shields.io/badge/License-MIT-yellow)](#license)

*839 road segments &bull; Real-time spatial analysis &bull; CC classification coloring &bull; Dark & Light themes*

---

</div>

## Overview

**S** is a desktop GIS application for selecting, visualizing, and analyzing Orange County, Florida road segments from the OC CMS (Congestion Management System) dataset. It pairs an interactive map with a full-featured data table, giving transportation planners a single-screen workflow for road network analysis.

Roads are color-coded by their **Context Classification** (C2, C2T, C3C, C3R, C4, C5, C6, LA) and every segment carries traffic, capacity, and level-of-service attributes visible on hover.

---

## Features

### Map & Visualization

| Feature | Description |
|---------|-------------|
| **5 Basemaps** | Dark, Grey, Voyager, Satellite, Topo &mdash; switch via toolbar dropdown |
| **CC Classification Coloring** | Road segments colored by Context Classification with interactive legend |
| **Hover Info Popup** | Hover any segment to see all attributes: Name, ID, From/To, Lanes, Capacity, AADT, PM Peak, LOS, and more |
| **Click to Select** | Click any road segment to toggle selection |
| **Double-Click Editor** | Double-click a segment to edit custom column values in a popup |
| **Intersection Nodes** | Deduplicated endpoint nodes rendered with theme-aware colors |
| **Layer Panel** | Toggle visibility of roads, county boundaries, labels, and nodes |
| **County Selector** | Jump between Orange, Lake, Martin, Hillsborough counties and City of Apopka |

### Spatial Selection Tools

| Tool | How to Use | Measurements |
|------|-----------|-------------|
| **Circle** | Click + drag from center to edge | Radius, Diameter, Area |
| **Rectangle** | Click + drag opposite corners | Width, Height, Perimeter, Area |
| **Polygon (Lasso)** | Click vertices, double-click to close | Vertices, Perimeter, Area |

All measurements display in **imperial units** (feet, miles, acres). Click the measurement title to center the map on the drawn shape.

### Data Table

| Feature | Description |
|---------|-------------|
| **16 Base Columns** | ID, Name, From, To, CC, Cap Group, Lanes, LOS, Capacity, AADT, PM Peak, Pk Dir, Comm Trips, Available, Cap LOS |
| **Resizable Columns** | Drag column borders to resize (col-resize cursor) |
| **Sortable** | Click headers to sort &mdash; sort arrows appear only when active |
| **Movable Columns** | Drag headers to rearrange &mdash; order persists across rebuilds |
| **Column Visibility** | Show/hide columns via the Columns dropdown or right-click header |
| **Search** | Real-time filter across Name, ID, From, To, CC, LOS, Cap Group |
| **Pagination** | 25 / 50 / 100 / 200 rows per page |
| **Right-Click Menu** | Zoom, Select/Deselect, Copy Name, Clear All |
| **CSV Export** | Export selected segments with all visible columns |

### CC Classification Legend

A horizontal pill-bar at the top of the map displays all 8 Context Classification categories:

| Code | Color | Segments |
|------|-------|----------|
| `C2` | Orange | 15 |
| `C2T` | Amber | 5 |
| `C3C` | Cyan | 309 |
| `C3R` | Violet | 318 |
| `C4` | Emerald | 126 |
| `C5` | Pink | 8 |
| `C6` | Orange-light | 4 |
| `LA` | Yellow | 54 |

**Click any category** to hide those segments on the map. Click again to show them.

### Custom Columns & Column Math

**Add Column** &mdash; create custom data columns (Text, Number, Percentage, Dropdown).

**Column Math** &mdash; create computed columns with formulas:

```
Operations:  +  −  ×  ÷  %
Operands:    Any numeric column  OR  a constant value
Precision:   0–4 decimal places
```

Computed columns auto-recalculate when source data changes. Chain multiple formulas together (Column C = A &times; B, Column D = C + constant).

Base numeric columns available for math: **Lanes, Capacity, AADT, PM Peak, Comm Trips, Available**.

### Themes

| | Dark Mode (Default) | Light Mode |
|---|---|---|
| **Accent** | Yellow `#facc15` | Pink `#E91E63` |
| **Background** | Zinc `#09090b` | Light `#fafafa` |
| **Auto Basemap** | Dark | Voyager |
| **Favicon** | Yellow circle | Pink circle |

Toggle with the moon/sun icon in the titlebar. All map layers, popups, and UI elements adapt instantly.

---

## Quick Start

### Standalone (Browser)

Open `index.html` in any modern browser. No installation required &mdash; all data is inlined.

### Electron Desktop App

```bash
cd occms-road-selector
npm install
npm start
```

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Arrow Keys` | Navigate between table cells |
| `Enter` | Edit focused cell / save and move down |
| `Tab` / `Shift+Tab` | Move right / left |
| `Escape` | Close modal / cancel tool / deselect |
| `F12` | Toggle DevTools (Electron only) |

---

## Data Source

**OC_CMS.geojson** &mdash; Orange County Congestion Management System

| Property | Type | Example |
|----------|------|---------|
| `ID` | String | `"3.1"` |
| `Name` | String | `"Alafaya Tr"` |
| `From` / `To` | String | `"University Blvd"` |
| `CC` | String | `"C3C"` |
| `Capacity_Group` | String | `"Urban - Class I"` |
| `Ln` | Number | `6` |
| `LOS` | String | `"E"` |
| `Cap` | Number | `3020` |
| `AADT` | Number | `39414` |
| `PmPk` | Number | `1835` |
| `PkDir` | String | `"NB"` |
| `Comm_Trips` | Number | `47` |
| `Avail` | Number | `1138` |
| `Cap_LOS` | String | `"C"` |

839 features &bull; MultiLineString geometry &bull; WGS84 (EPSG:4326)

---

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Map Engine | [MapLibre GL JS](https://maplibre.org/) | 4.7.1 |
| Data Table | [Tabulator](https://tabulator.info/) | 6.3.0 |
| Spatial Analysis | [Turf.js](https://turfjs.org/) | 7.x |
| Desktop Shell | [Electron](https://electronjs.org/) | 33+ |
| Fonts | Inter + JetBrains Mono | Google Fonts |

---

## Architecture

Single HTML file with **13 JavaScript modules**:

```
State ─── Config ─── Utils
  │
MapManager ─── SpatialTools
  │
Selection ─── TableManager ─── Columns
  │
CellNav ─── UI ─── Theme ─── Export ─── Boot
```

| # | Module | Responsibility |
|---|--------|----------------|
| 1 | `State` | Global state container |
| 2 | `Config` | Basemaps, colors, CC classification, field names |
| 3 | `Utils` | Formatting, helpers, accent color |
| 4 | `MapManager` | Map init, layers, hover popup, legend, interactions |
| 5 | `SpatialTools` | Circle, rectangle, polygon tools + measurements |
| 6 | `Selection` | Toggle, bulk add, clear all, refresh UI |
| 7 | `TableManager` | Table build/rebuild, column defs, row data, filtering |
| 8 | `Columns` | Custom columns, Column Math, computed values |
| 9 | `CellNav` | Arrow key navigation, auto-advance editing |
| 10 | `UI` | Dropdowns, context menu, modals, resizer |
| 11 | `Theme` | Dark/light mode with auto basemap switch |
| 12 | `Export` | CSV download of selected segments |
| 13 | `Boot` | Event wiring, initialization, error handling |

See `CLAUDE.md` for full technical architecture and `FEATURES.md` for detailed feature reference.

---

## Project Structure

```
S/files/
  index.html                    # Standalone (inline data)
  OC_CMS.geojson                # Road segment data source
  HELP.md                       # User-facing how-to guide
  occms-road-selector/
    public/
      index.html                # Electron version
      OC_CMS.geojson            # Road segment data
    electron-map-app/
      main.js                   # Electron main process
      package.json
    README.md                   # This file
    CLAUDE.md                   # Technical architecture
    FEATURES.md                 # Complete feature reference
    TESTS.md                    # Test coverage
```

---

## Author

**Parag Gupta**
[LinkedIn](https://www.linkedin.com/in/parag-gupta-ptp-rsp1-29413214a)

---

## License

MIT
