<div align="center">

# S-Preview

**Standalone GIS Road Segment Analyzer — Browser Preview**

[![MapLibre](https://img.shields.io/badge/MapLibre_GL_JS-4.7.1-blue?logo=mapbox&logoColor=white)](#tech-stack)
[![Tabulator](https://img.shields.io/badge/Tabulator-6.3.0-green)](#tech-stack)
[![Turf.js](https://img.shields.io/badge/Turf.js-7.x-orange)](#tech-stack)
[![License](https://img.shields.io/badge/License-Closed_Source-red)](#license)

*Interactive spatial analysis &bull; CC classification coloring &bull; Dark & Light themes*

---

</div>

## Overview

**S-Preview** is the standalone browser preview of **S**, an interactive GIS application for selecting, visualizing, and analyzing road segments from GeoJSON datasets. It runs entirely in the browser with no build step or installation required — just open `index.html`.

Roads are color-coded by **Context Classification** (C2, C2T, C3C, C3R, C4, C5, C6, LA), and every segment carries traffic, capacity, and level-of-service attributes visible on hover.

---

## Quick Start

Open `index.html` in any modern browser. The application loads `OC_CMS.geojson` and `FL_Counties.geojson` from the same directory.

```
S-Preview/
  index.html            # Single-file application
  OC_CMS.geojson        # Road segment data (Orange County CMS)
  FL_Counties.geojson   # Florida county boundaries
  README.md             # This file
```

---

## Features

- **5 Basemaps** — Dark, Grey, Voyager, Google Streets, Google Satellite
- **CC Classification Coloring** — Segments colored by Context Classification with interactive legend
- **Hover Info Popup** — Name, ID, From/To, Lanes, Capacity, AADT, PM Peak, LOS, and more
- **Spatial Selection Tools** — Circle, Rectangle, and Polygon (Lasso) with imperial measurements
- **Full Data Table** — Sortable, searchable, paginated with resizable and movable columns
- **Custom Columns & Formulas** — Add computed columns with free-form `[Column Name]` expressions
- **Data Labels** — Display selected column values (e.g., AADT, LOS) as additional lines on map segment labels
- **CSV Export** — Export selected segments
- **Dark & Light Themes** — Toggle via titlebar icon
- **County Selector** — Switch between loaded county datasets

---

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Map Engine | [MapLibre GL JS](https://maplibre.org/) | 4.7.1 |
| Data Table | [Tabulator](https://tabulator.info/) | 6.3.0 |
| Spatial Analysis | [Turf.js](https://turfjs.org/) | 7.x |
| Fonts | Inter + JetBrains Mono | Google Fonts |

---

## Author

**Parag Gupta**
[LinkedIn](https://www.linkedin.com/in/parag-gupta-ptp-rsp1-29413214a)

---

## License

This software is **closed source** and proprietary. All rights reserved.

Developed by **Parag Gupta**. Unauthorized copying, modification, distribution, or use of this software, in whole or in part, is strictly prohibited without prior written permission from the author.
