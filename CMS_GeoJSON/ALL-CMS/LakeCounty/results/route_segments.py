#!/usr/bin/env python3
"""
Lake County CMS – Route Segments via OSRM
Replaces straight-line segments with actual road-following geometries
using the OSRM (Open Source Routing Machine) free demo API.

QA/QC checks:
  1. Route found? (OSRM returns a valid route)
  2. Detour ratio: route_distance / straight_line_distance
     - Good: < 3.0
     - Warning: 3.0 – 6.0
     - Bad: > 6.0 (likely wrong route)
  3. Route stays within Lake County bounding box (with buffer)
  4. Route distance sanity (not too short, not too long)
"""

import json
import math
import time
import urllib.request
import urllib.parse
import sys

OSRM_URL = "http://router.project-osrm.org/route/v1/driving"
DELAY = 0.55  # seconds between requests (respect OSRM demo limits)

# Lake County bounding box with generous buffer for routes near borders
BOUNDS = {"xmin": -82.20, "ymin": 28.20, "xmax": -81.05, "ymax": 29.20}


def haversine(lon1, lat1, lon2, lat2):
    """Distance in km between two points."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_route(from_lon, from_lat, to_lon, to_lat):
    """Query OSRM for a driving route. Returns (geometry_coords, distance_m) or None."""
    url = (f"{OSRM_URL}/{from_lon},{from_lat};{to_lon},{to_lat}"
           f"?overview=full&geometries=geojson&steps=false")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LakeCountyCMS/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        route = data["routes"][0]
        coords = route["geometry"]["coordinates"]  # [[lon,lat], ...]
        distance = route["distance"]  # meters
        return coords, distance
    except Exception as e:
        print(f"    ROUTE ERROR: {e}")
        return None


def coords_in_bounds(coords):
    """Check if all route coordinates are within the extended bounding box."""
    for lon, lat in coords:
        if not (BOUNDS["xmin"] <= lon <= BOUNDS["xmax"] and
                BOUNDS["ymin"] <= lat <= BOUNDS["ymax"]):
            return False
    return True


def main():
    input_path = "/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS.geojson"
    output_path = "/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS_routed.geojson"
    qa_path = "/Users/pg/Documents/S/Lake_County_CMS/qa_routing_report.json"

    with open(input_path) as f:
        geojson = json.load(f)

    features = geojson["features"]
    total = len(features)
    print(f"Routing {total} segments via OSRM...\n")

    stats = {
        "total": total,
        "routed_ok": 0,
        "route_failed": 0,
        "high_detour": 0,
        "out_of_bounds": 0,
        "very_short": 0,
    }
    qa_issues = []

    for i, feat in enumerate(features):
        p = feat["properties"]
        seg_id = p["SEGMENT_ID"]
        road = p["RoadName"]
        coords = feat["geometry"]["coordinates"][0]
        from_lon, from_lat = coords[0][0], coords[0][1]
        to_lon, to_lat = coords[1][0], coords[1][1]

        straight_km = haversine(from_lon, from_lat, to_lon, to_lat)

        sys.stdout.write(f"[{i+1}/{total}] Seg {seg_id}: {road[:45]} ... ")
        sys.stdout.flush()

        result = get_route(from_lon, from_lat, to_lon, to_lat)
        time.sleep(DELAY)

        if result is None:
            print("FAILED (no route)")
            stats["route_failed"] += 1
            p["Route_Status"] = "FAILED"
            p["Route_Distance_km"] = None
            p["Straight_Distance_km"] = round(straight_km, 2)
            p["Detour_Ratio"] = None
            qa_issues.append({
                "id": seg_id, "road": road,
                "issue": "OSRM returned no route",
            })
            continue

        route_coords, route_dist_m = result
        route_km = route_dist_m / 1000.0

        # QA checks
        flags = []

        # 1. Detour ratio
        if straight_km > 0.05:
            detour = route_km / straight_km
        else:
            detour = 1.0  # very short segments

        if detour > 6.0:
            flags.append(f"HIGH_DETOUR:{detour:.1f}x")
            stats["high_detour"] += 1
        elif detour > 3.0:
            flags.append(f"MODERATE_DETOUR:{detour:.1f}x")

        # 2. Out of bounds
        if not coords_in_bounds(route_coords):
            flags.append("ROUTE_OOB")
            stats["out_of_bounds"] += 1

        # 3. Very short route (< 50m for segments that should be longer)
        if route_km < 0.05 and straight_km > 0.1:
            flags.append("VERY_SHORT_ROUTE")
            stats["very_short"] += 1

        # Update geometry with routed coordinates
        feat["geometry"] = {
            "type": "MultiLineString",
            "coordinates": [route_coords],
        }

        # Update properties
        route_status = "OK" if not flags else "; ".join(flags)
        p["Route_Status"] = route_status
        p["Route_Distance_km"] = round(route_km, 2)
        p["Straight_Distance_km"] = round(straight_km, 2)
        p["Detour_Ratio"] = round(detour, 2)
        p["Route_Points"] = len(route_coords)

        if flags:
            qa_issues.append({
                "id": seg_id, "road": road,
                "issue": "; ".join(flags),
                "route_km": round(route_km, 2),
                "straight_km": round(straight_km, 2),
                "detour": round(detour, 2),
            })

        stats["routed_ok"] += 1
        pts = len(route_coords)
        print(f"OK  {pts} pts  {route_km:.1f} km  (detour {detour:.1f}x)")

    # Save routed GeoJSON
    geojson["name"] = "Lake_County_CMS_Routed"
    with open(output_path, "w") as f:
        json.dump(geojson, f)  # no indent to keep file smaller

    # Save QA report
    qa_report = {
        "stats": stats,
        "issues": qa_issues,
    }
    with open(qa_path, "w") as f:
        json.dump(qa_report, f, indent=2)

    print(f"\n{'='*60}")
    print(f"ROUTING QA/QC SUMMARY")
    print(f"{'='*60}")
    print(f"Total segments:    {stats['total']}")
    print(f"Routed OK:         {stats['routed_ok']}")
    print(f"Route failed:      {stats['route_failed']}")
    print(f"High detour (>6x): {stats['high_detour']}")
    print(f"Out of bounds:     {stats['out_of_bounds']}")
    print(f"Very short:        {stats['very_short']}")
    print(f"\nIssues: {len(qa_issues)}")
    for iss in qa_issues:
        print(f"  Seg {iss['id']}: {iss['road'][:40]} — {iss['issue']}")
    print(f"\nOutput: {output_path}")
    print(f"QA Report: {qa_path}")


if __name__ == "__main__":
    main()
