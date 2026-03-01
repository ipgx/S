#!/usr/bin/env python3
"""
Independent geocoding using Nominatim (OpenStreetMap) for cross-validation.
This is a COMPLETELY SEPARATE methodology from the ArcGIS geocoding pipeline.

Nominatim structured search:
  - Uses 'street' field for intersection query
  - Bounded to Lake County, FL via 'county' + 'state' fields
  - Falls back to free-form search with viewbox constraint
"""

import json
import time
import urllib.request
import urllib.parse
import csv
import sys

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Lake County viewbox: west,north,east,south
VIEWBOX = "-82.05,29.10,-81.20,28.35"
DELAY = 1.1  # Nominatim requires max 1 req/sec

LAKE_COUNTY_BOUNDS = {"xmin": -82.05, "ymin": 28.35, "xmax": -81.20, "ymax": 29.10}


def nominatim_search(query, bounded=True):
    """Free-form Nominatim search. Returns list of (lon, lat, display_name, osm_type)."""
    params = {
        "q": query,
        "format": "json",
        "limit": 5,
        "viewbox": VIEWBOX,
        "bounded": "1" if bounded else "0",
        "countrycodes": "us",
        "addressdetails": "1",
    }
    url = f"{NOMINATIM_URL}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "LakeCountyCMS-CrossValidation/1.0 (research)"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = []
        for r in data:
            lon = float(r["lon"])
            lat = float(r["lat"])
            display = r.get("display_name", "")
            osm_type = r.get("type", "")
            # Check if in Lake County area
            addr = r.get("address", {})
            county = addr.get("county", "").lower()
            results.append((lon, lat, display, osm_type, county))
        return results
    except Exception as e:
        return []


def nominatim_structured(road, cross_street):
    """Structured Nominatim search for an intersection."""
    # Strategy 1: "Road & Cross Street" as street in Lake County
    params = {
        "street": f"{road} and {cross_street}",
        "county": "Lake County",
        "state": "Florida",
        "country": "US",
        "format": "json",
        "limit": 5,
        "addressdetails": "1",
    }
    url = f"{NOMINATIM_URL}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "LakeCountyCMS-CrossValidation/1.0 (research)"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        results = []
        for r in data:
            lon = float(r["lon"])
            lat = float(r["lat"])
            display = r.get("display_name", "")
            county = r.get("address", {}).get("county", "").lower()
            results.append((lon, lat, display, county))
        return results
    except:
        return []


def best_in_lake_county(results):
    """Pick best result that's in Lake County."""
    for r in results:
        county = r[-1]  # last element is county
        if "lake" in county:
            return r
    # Fallback: pick first result in bounding box
    for r in results:
        lon, lat = r[0], r[1]
        if (LAKE_COUNTY_BOUNDS["xmin"] <= lon <= LAKE_COUNTY_BOUNDS["xmax"] and
                LAKE_COUNTY_BOUNDS["ymin"] <= lat <= LAKE_COUNTY_BOUNDS["ymax"]):
            return r
    return None


def geocode_intersection(road, cross_street):
    """Try multiple Nominatim strategies to geocode an intersection."""
    # Clean road name - remove parenthetical aliases
    clean_road = road
    if "(" in road:
        clean_road = road[:road.index("(")].strip()
    # Also get first part of slash-separated names
    first_road = road.split("/")[0].strip() if "/" in road else road

    strategies = [
        # 1. Free-form: "Road & Cross, Lake County, FL"
        f"{road} & {cross_street}, Lake County, Florida",
        # 2. Free-form: "Cross & Road, Lake County, FL"
        f"{cross_street} & {road}, Lake County, Florida",
        # 3. Cleaned road name
        f"{clean_road} & {cross_street}, Lake County, Florida",
        # 4. First road part
        f"{first_road} & {cross_street}, Lake County, Florida",
        # 5. Just the cross street
        f"{cross_street}, Lake County, Florida",
    ]

    for query in strategies:
        time.sleep(DELAY)
        results = nominatim_search(query, bounded=True)
        best = best_in_lake_county(results)
        if best:
            return best[0], best[1], query
        # Try unbounded if bounded returned nothing
        if not results:
            results = nominatim_search(query, bounded=False)
            best = best_in_lake_county(results)
            if best:
                return best[0], best[1], query

    return None


def main():
    # Load the original CSV data (same source)
    with open("/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS.geojson") as f:
        arcgis_data = json.load(f)

    segments = []
    for feat in arcgis_data["features"]:
        p = feat["properties"]
        segments.append({
            "id": p["SEGMENT_ID"],
            "road": p["RoadName"],
            "from_str": p["From"],
            "to_str": p["To"],
        })

    total = len(segments)
    print(f"Nominatim geocoding {total} segments ({total*2} intersection points)...\n")

    results = []
    success = 0
    failed = 0

    for i, seg in enumerate(segments):
        sid = seg["id"]
        road = seg["road"]
        from_s = seg["from_str"]
        to_s = seg["to_str"]

        sys.stdout.write(f"[{i+1}/{total}] Seg {sid}: {road[:40]}...")
        sys.stdout.flush()

        # Geocode FROM
        from_result = geocode_intersection(road, from_s)
        # Geocode TO
        to_result = geocode_intersection(road, to_s)

        from_lon = from_lat = to_lon = to_lat = None
        from_query = to_query = None

        if from_result:
            from_lon, from_lat, from_query = from_result
        if to_result:
            to_lon, to_lat, to_query = to_result

        status = "OK" if from_result and to_result else "PARTIAL" if from_result or to_result else "FAILED"
        if status == "OK":
            success += 1
        elif status == "FAILED":
            failed += 1
        else:
            success += 1  # partial is still useful

        print(f" {status}")

        results.append({
            "SEGMENT_ID": sid,
            "RoadName": road,
            "From": from_s,
            "To": to_s,
            "nom_from_lon": from_lon,
            "nom_from_lat": from_lat,
            "nom_to_lon": to_lon,
            "nom_to_lat": to_lat,
            "nom_from_query": from_query,
            "nom_to_query": to_query,
            "status": status,
        })

    # Save results
    out_path = "/Users/pg/Documents/S/Lake_County_CMS/nominatim_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print(f"NOMINATIM GEOCODING SUMMARY")
    print(f"{'='*60}")
    print(f"Total segments: {total}")
    print(f"Both endpoints found: {sum(1 for r in results if r['status'] == 'OK')}")
    print(f"Partial (one endpoint): {sum(1 for r in results if r['status'] == 'PARTIAL')}")
    print(f"Failed (no endpoints): {sum(1 for r in results if r['status'] == 'FAILED')}")
    from_found = sum(1 for r in results if r["nom_from_lon"] is not None)
    to_found = sum(1 for r in results if r["nom_to_lon"] is not None)
    print(f"FROM points found: {from_found}/{total}")
    print(f"TO points found: {to_found}/{total}")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
