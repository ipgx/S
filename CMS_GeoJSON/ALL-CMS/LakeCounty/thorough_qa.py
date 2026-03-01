#!/usr/bin/env python3
"""
Thorough QA/QC: Check every FROM/TO node against the actual Lake County polygon.
Identify all out-of-county points, re-geocode them, and re-route affected segments.
"""

import json
import math
import time
import urllib.request
import urllib.parse
import sys

# ── Point-in-polygon (ray casting) ──────────────────────────

def point_in_polygon(x, y, polygon):
    """Ray-casting algorithm for point-in-polygon test.
    polygon = list of [lon, lat] pairs forming a closed ring."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def point_in_multipolygon(lon, lat, multipolygon_coords):
    """Check if point is inside any polygon of a MultiPolygon."""
    for polygon in multipolygon_coords:
        outer_ring = polygon[0]
        if point_in_polygon(lon, lat, outer_ring):
            # Check it's not inside a hole
            in_hole = False
            for hole in polygon[1:]:
                if point_in_polygon(lon, lat, hole):
                    in_hole = True
                    break
            if not in_hole:
                return True
    return False


# ── Load Lake County boundary ───────────────────────────────

def load_lake_county_boundary():
    with open("/Users/pg/Documents/S/FL_Counties.geojson") as f:
        counties = json.load(f)
    for feat in counties["features"]:
        name = feat["properties"].get("NAME", "")
        if "Lake" in name:
            return feat["geometry"]["coordinates"]
    raise ValueError("Lake County not found")


# ── Geocoding ───────────────────────────────────────────────

ARCGIS_URL = ("https://geocode.arcgis.com/arcgis/rest/services/World/"
              "GeocodeServer/findAddressCandidates")
SEARCH_EXTENT = "-82.05,28.35,-81.20,29.10"


def geocode_candidates(address, max_results=5):
    """Return list of (lon, lat, score, match_addr) candidates."""
    params = urllib.parse.urlencode({
        "SingleLine": address,
        "f": "json",
        "outFields": "Match_addr,Addr_type",
        "maxLocations": max_results,
        "searchExtent": SEARCH_EXTENT,
        "location": "-81.6,28.7",
        "distance": 80000,
    })
    url = f"{ARCGIS_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        results = []
        for c in data.get("candidates", []):
            results.append((
                c["location"]["x"], c["location"]["y"],
                c.get("score", 0), c.get("attributes", {}).get("Match_addr", "")
            ))
        return results
    except Exception as e:
        print(f"    GEOCODE ERROR: {e}")
        return []


def find_best_in_county(candidates, county_poly):
    """From a list of geocode candidates, pick the best one inside Lake County."""
    for lon, lat, score, addr in candidates:
        if point_in_multipolygon(lon, lat, county_poly):
            return lon, lat, score, addr
    return None


# ── OSRM Routing ────────────────────────────────────────────

OSRM_URL = "http://router.project-osrm.org/route/v1/driving"


def get_route(from_lon, from_lat, to_lon, to_lat):
    url = (f"{OSRM_URL}/{from_lon},{from_lat};{to_lon},{to_lat}"
           f"?overview=full&geometries=geojson&steps=false")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LakeCountyCMS/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        route = data["routes"][0]
        return route["geometry"]["coordinates"], route["distance"]
    except Exception as e:
        print(f"    ROUTE ERROR: {e}")
        return None


def haversine(lon1, lat1, lon2, lat2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Main ────────────────────────────────────────────────────

def main():
    print("Loading Lake County boundary...")
    county_poly = load_lake_county_boundary()
    print("Loading routed GeoJSON...")
    with open("/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS_routed.geojson") as f:
        geojson = json.load(f)
    # Also load original geocoded file for FROM/TO raw coords
    with open("/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS.geojson") as f:
        original = json.load(f)
    # Build lookup by segment ID for original coords
    orig_lookup = {}
    for feat in original["features"]:
        sid = feat["properties"]["SEGMENT_ID"]
        coords = feat["geometry"]["coordinates"][0]
        orig_lookup[sid] = {
            "from": (coords[0][0], coords[0][1]),
            "to": (coords[1][0], coords[1][1]),
        }

    features = geojson["features"]
    total = len(features)

    # ── Phase 1: Identify all out-of-county FROM/TO nodes ───
    print(f"\n{'='*60}")
    print("PHASE 1: Point-in-polygon check on all {0} segments".format(total))
    print(f"{'='*60}\n")

    oob_from = []  # (index, seg_id, road, from_str, lon, lat)
    oob_to = []

    for idx, feat in enumerate(features):
        p = feat["properties"]
        sid = p["SEGMENT_ID"]
        road = p["RoadName"]
        coords = feat["geometry"]["coordinates"][0]
        from_lon, from_lat = coords[0][0], coords[0][1]
        to_lon, to_lat = coords[-1][0], coords[-1][1]

        # Check FROM (use original geocoded point)
        if sid in orig_lookup:
            ofrom = orig_lookup[sid]["from"]
            oto = orig_lookup[sid]["to"]
        else:
            ofrom = (from_lon, from_lat)
            oto = (to_lon, to_lat)

        if not point_in_multipolygon(ofrom[0], ofrom[1], county_poly):
            oob_from.append((idx, sid, road, p["From"], ofrom[0], ofrom[1]))

        if not point_in_multipolygon(oto[0], oto[1], county_poly):
            oob_to.append((idx, sid, road, p["To"], oto[0], oto[1]))

    print(f"OUT-OF-COUNTY FROM nodes: {len(oob_from)}")
    for _, sid, road, frm, lon, lat in oob_from:
        print(f"  Seg {sid}: {road} | FROM={frm} | ({lon:.5f}, {lat:.5f})")

    print(f"\nOUT-OF-COUNTY TO nodes: {len(oob_to)}")
    for _, sid, road, to, lon, lat in oob_to:
        print(f"  Seg {sid}: {road} | TO={to} | ({lon:.5f}, {lat:.5f})")

    total_oob = len(oob_from) + len(oob_to)
    print(f"\nTotal out-of-county nodes: {total_oob}")

    if total_oob == 0:
        print("All nodes are within Lake County! No fixes needed.")
        return

    # ── Phase 2: Re-geocode out-of-county nodes ────────────
    print(f"\n{'='*60}")
    print("PHASE 2: Re-geocoding {0} out-of-county nodes".format(total_oob))
    print(f"{'='*60}\n")

    # Collect all segments that need fixing
    fix_map = {}  # seg_id -> {"fix_from": (lon,lat), "fix_to": (lon,lat)}

    # Process FROM nodes
    for idx, sid, road, from_str, old_lon, old_lat in oob_from:
        print(f"FIX FROM | Seg {sid}: {road} & {from_str}")

        # Try multiple geocoding strategies
        queries = [
            f"{road} & {from_str}, Lake County, FL",
            f"{from_str} & {road}, Lake County, FL",
            f"{from_str}, Lake County, FL",
        ]
        # Strip parenthetical
        if "(" in road:
            base_road = road[:road.index("(")].strip()
            queries.insert(1, f"{base_road} & {from_str}, Lake County, FL")
        # Also try first part of slash-separated road names
        if "/" in road:
            first_road = road.split("/")[0].strip()
            queries.insert(1, f"{first_road} & {from_str}, Lake County, FL")

        # Try with specific towns
        for town in ["Leesburg", "Eustis", "Mount Dora", "Tavares", "Clermont",
                     "Lady Lake", "Minneola", "Groveland", "Mascotte", "Umatilla",
                     "Fruitland Park", "Howey-in-the-Hills", "Astatula", "Montverde"]:
            queries.append(f"{road} & {from_str}, {town}, FL")

        fixed = False
        for q in queries:
            time.sleep(0.3)
            candidates = geocode_candidates(q)
            result = find_best_in_county(candidates, county_poly)
            if result:
                new_lon, new_lat, score, addr = result
                print(f"  FIXED: ({new_lon:.5f}, {new_lat:.5f}) score={score:.1f} via '{q[:60]}'")
                fix_map.setdefault(sid, {})["fix_from"] = (new_lon, new_lat)
                fixed = True
                break

        if not fixed:
            # Last resort: try just the intersection name with county
            time.sleep(0.3)
            candidates = geocode_candidates(f"{from_str}, Lake County, Florida")
            result = find_best_in_county(candidates, county_poly)
            if result:
                new_lon, new_lat, score, addr = result
                print(f"  FIXED (fallback): ({new_lon:.5f}, {new_lat:.5f}) score={score:.1f}")
                fix_map.setdefault(sid, {})["fix_from"] = (new_lon, new_lat)
            else:
                print(f"  !! COULD NOT FIX — no candidate in Lake County")

    # Process TO nodes
    for idx, sid, road, to_str, old_lon, old_lat in oob_to:
        print(f"FIX TO   | Seg {sid}: {road} & {to_str}")

        queries = [
            f"{road} & {to_str}, Lake County, FL",
            f"{to_str} & {road}, Lake County, FL",
            f"{to_str}, Lake County, FL",
        ]
        if "(" in road:
            base_road = road[:road.index("(")].strip()
            queries.insert(1, f"{base_road} & {to_str}, Lake County, FL")
        if "/" in road:
            first_road = road.split("/")[0].strip()
            queries.insert(1, f"{first_road} & {to_str}, Lake County, FL")

        for town in ["Leesburg", "Eustis", "Mount Dora", "Tavares", "Clermont",
                     "Lady Lake", "Minneola", "Groveland", "Mascotte", "Umatilla",
                     "Fruitland Park", "Howey-in-the-Hills", "Astatula", "Montverde"]:
            queries.append(f"{road} & {to_str}, {town}, FL")

        fixed = False
        for q in queries:
            time.sleep(0.3)
            candidates = geocode_candidates(q)
            result = find_best_in_county(candidates, county_poly)
            if result:
                new_lon, new_lat, score, addr = result
                print(f"  FIXED: ({new_lon:.5f}, {new_lat:.5f}) score={score:.1f} via '{q[:60]}'")
                fix_map.setdefault(sid, {})["fix_to"] = (new_lon, new_lat)
                fixed = True
                break

        if not fixed:
            time.sleep(0.3)
            candidates = geocode_candidates(f"{to_str}, Lake County, Florida")
            result = find_best_in_county(candidates, county_poly)
            if result:
                new_lon, new_lat, score, addr = result
                print(f"  FIXED (fallback): ({new_lon:.5f}, {new_lat:.5f}) score={score:.1f}")
                fix_map.setdefault(sid, {})["fix_to"] = (new_lon, new_lat)
            else:
                print(f"  !! COULD NOT FIX — no candidate in Lake County")

    # ── Phase 3: Re-route fixed segments ────────────────────
    segments_to_reroute = set(fix_map.keys())
    print(f"\n{'='*60}")
    print(f"PHASE 3: Re-routing {len(segments_to_reroute)} segments")
    print(f"{'='*60}\n")

    reroute_ok = 0
    reroute_fail = 0

    for feat in features:
        sid = feat["properties"]["SEGMENT_ID"]
        if sid not in fix_map:
            continue

        p = feat["properties"]
        fixes = fix_map[sid]
        coords = feat["geometry"]["coordinates"][0]

        # Get current FROM/TO from original
        if sid in orig_lookup:
            cur_from = orig_lookup[sid]["from"]
            cur_to = orig_lookup[sid]["to"]
        else:
            cur_from = (coords[0][0], coords[0][1])
            cur_to = (coords[-1][0], coords[-1][1])

        new_from = fixes.get("fix_from", cur_from)
        new_to = fixes.get("fix_to", cur_to)

        print(f"  Re-routing Seg {sid}: {p['RoadName'][:40]}")
        print(f"    FROM: ({new_from[0]:.5f}, {new_from[1]:.5f})")
        print(f"    TO:   ({new_to[0]:.5f}, {new_to[1]:.5f})")

        time.sleep(0.55)
        result = get_route(new_from[0], new_from[1], new_to[0], new_to[1])

        if result:
            route_coords, route_dist = result
            route_km = route_dist / 1000.0
            straight_km = haversine(new_from[0], new_from[1], new_to[0], new_to[1])
            detour = route_km / straight_km if straight_km > 0.05 else 1.0

            feat["geometry"]["coordinates"] = [route_coords]
            p["Route_Distance_km"] = round(route_km, 2)
            p["Straight_Distance_km"] = round(straight_km, 2)
            p["Detour_Ratio"] = round(detour, 2)
            p["Route_Points"] = len(route_coords)
            p["Route_Status"] = "FIXED_OOB" if detour < 6 else f"FIXED_OOB;HIGH_DETOUR:{detour:.1f}x"
            reroute_ok += 1
            print(f"    OK: {len(route_coords)} pts, {route_km:.1f} km, detour {detour:.1f}x")
        else:
            reroute_fail += 1
            print(f"    FAILED to re-route")

    # ── Phase 4: Final validation ───────────────────────────
    print(f"\n{'='*60}")
    print("PHASE 4: Final validation — all nodes")
    print(f"{'='*60}\n")

    final_oob_from = 0
    final_oob_to = 0
    final_issues = []

    for feat in features:
        p = feat["properties"]
        sid = p["SEGMENT_ID"]
        coords = feat["geometry"]["coordinates"][0]
        from_lon, from_lat = coords[0][0], coords[0][1]
        to_lon, to_lat = coords[-1][0], coords[-1][1]

        from_in = point_in_multipolygon(from_lon, from_lat, county_poly)
        to_in = point_in_multipolygon(to_lon, to_lat, county_poly)

        if not from_in:
            final_oob_from += 1
            final_issues.append(f"Seg {sid} ({p['RoadName']}): FROM still out ({from_lon:.5f}, {from_lat:.5f}) — {p['From']}")
        if not to_in:
            final_oob_to += 1
            final_issues.append(f"Seg {sid} ({p['RoadName']}): TO still out ({to_lon:.5f}, {to_lat:.5f}) — {p['To']}")

    print(f"Final FROM out-of-county: {final_oob_from}")
    print(f"Final TO out-of-county: {final_oob_to}")
    for iss in final_issues:
        print(f"  {iss}")

    # ── Save ────────────────────────────────────────────────
    output_path = "/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS_routed.geojson"
    with open(output_path, "w") as f:
        json.dump(geojson, f)
    print(f"\nSaved: {output_path}")

    # QA summary
    print(f"\n{'='*60}")
    print("FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"Total segments: {total}")
    print(f"Nodes checked: {total * 2}")
    print(f"Initially out-of-county: {total_oob}")
    print(f"Re-geocoded: {len(fix_map)}")
    print(f"Re-routed OK: {reroute_ok}")
    print(f"Re-route failed: {reroute_fail}")
    print(f"Still out-of-county: {final_oob_from + final_oob_to}")


if __name__ == "__main__":
    main()
