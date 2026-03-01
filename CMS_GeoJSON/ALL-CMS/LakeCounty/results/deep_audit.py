#!/usr/bin/env python3
"""
Deep Audit: Check EVERY route point (not just endpoints) against
the actual Lake County polygon. Fix any segment where route points
stray significantly outside the county.
"""

import json
import math
import time
import urllib.request
import urllib.parse
import sys


# ── Geometry helpers ────────────────────────────────────────

def pip(x, y, poly):
    n = len(poly); inside = False; j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def in_county(lon, lat, county_poly):
    for polygon in county_poly:
        outer = polygon[0]
        if pip(lon, lat, outer):
            in_hole = False
            for hole in polygon[1:]:
                if pip(lon, lat, hole): in_hole = True; break
            if not in_hole: return True
    return False

def haversine(lon1, lat1, lon2, lat2):
    R = 6371
    dlat = math.radians(lat2 - lat1); dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


# ── Geocoding ───────────────────────────────────────────────

ARCGIS_URL = ("https://geocode.arcgis.com/arcgis/rest/services/World/"
              "GeocodeServer/findAddressCandidates")

def geocode_in_county(address, county_poly, max_results=10):
    params = urllib.parse.urlencode({
        "SingleLine": address, "f": "json",
        "outFields": "Match_addr,Addr_type",
        "maxLocations": max_results,
        "searchExtent": "-82.05,28.35,-81.20,29.10",
        "location": "-81.6,28.7", "distance": 80000,
    })
    url = f"{ARCGIS_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        for c in data.get("candidates", []):
            lon, lat = c["location"]["x"], c["location"]["y"]
            score = c.get("score", 0)
            if in_county(lon, lat, county_poly) and score >= 65:
                return lon, lat, score
    except: pass
    return None


# ── OSRM ────────────────────────────────────────────────────

OSRM_URL = "http://router.project-osrm.org/route/v1/driving"

def get_route(f_lon, f_lat, t_lon, t_lat):
    url = (f"{OSRM_URL}/{f_lon},{f_lat};{t_lon},{t_lat}"
           f"?overview=full&geometries=geojson&steps=false")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LakeCountyCMS/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        if data.get("code") == "Ok" and data.get("routes"):
            r = data["routes"][0]
            return r["geometry"]["coordinates"], r["distance"]
    except: pass
    return None


def main():
    # Load data
    print("Loading Lake County boundary...")
    with open("/Users/pg/Documents/S/FL_Counties.geojson") as f:
        counties = json.load(f)
    county_poly = None
    for feat in counties["features"]:
        if "Lake" in feat["properties"].get("NAME", ""):
            county_poly = feat["geometry"]["coordinates"]; break

    print("Loading routed GeoJSON...")
    with open("/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS_routed.geojson") as f:
        geojson = json.load(f)

    features = geojson["features"]
    total = len(features)

    # ── Phase 1: Audit every route point ────────────────────
    print(f"\n{'='*60}")
    print(f"DEEP AUDIT: Checking all route points in {total} segments")
    print(f"{'='*60}\n")

    problems = []  # segments with >10% of route points outside county

    for feat in features:
        p = feat["properties"]
        sid = p["SEGMENT_ID"]
        coords = feat["geometry"]["coordinates"][0]
        n = len(coords)

        outside_count = 0
        for c in coords:
            if not in_county(c[0], c[1], county_poly):
                outside_count += 1

        pct = (outside_count / n * 100) if n > 0 else 0

        if outside_count > 0:
            problems.append({
                "idx": features.index(feat),
                "sid": sid,
                "road": p["RoadName"],
                "from": p["From"],
                "to": p["To"],
                "total_pts": n,
                "outside_pts": outside_count,
                "pct_outside": round(pct, 1),
            })

    # Sort by severity
    problems.sort(key=lambda x: x["pct_outside"], reverse=True)

    print(f"Segments with route points outside Lake County: {len(problems)}")
    print()

    # Categorize
    severe = [p for p in problems if p["pct_outside"] > 25]
    moderate = [p for p in problems if 5 < p["pct_outside"] <= 25]
    minor = [p for p in problems if p["pct_outside"] <= 5]

    print(f"SEVERE (>25% outside):   {len(severe)}")
    for p in severe:
        print(f"  Seg {p['sid']:>5}: {p['road'][:35]:35s} {p['outside_pts']:>4}/{p['total_pts']:>4} pts ({p['pct_outside']:.0f}%)")

    print(f"\nMODERATE (5-25% outside): {len(moderate)}")
    for p in moderate:
        print(f"  Seg {p['sid']:>5}: {p['road'][:35]:35s} {p['outside_pts']:>4}/{p['total_pts']:>4} pts ({p['pct_outside']:.0f}%)")

    print(f"\nMINOR (<5% outside):     {len(minor)}")
    for p in minor[:10]:
        print(f"  Seg {p['sid']:>5}: {p['road'][:35]:35s} {p['outside_pts']:>4}/{p['total_pts']:>4} pts ({p['pct_outside']:.0f}%)")
    if len(minor) > 10:
        print(f"  ... and {len(minor)-10} more minor cases")

    # ── Phase 2: Fix severe + moderate cases ────────────────
    to_fix = severe + moderate
    print(f"\n{'='*60}")
    print(f"FIXING {len(to_fix)} segments with significant OOB routes")
    print(f"{'='*60}\n")

    fixed = 0
    still_bad = 0

    for prob in to_fix:
        feat = features[prob["idx"]]
        p = feat["properties"]
        sid = p["SEGMENT_ID"]
        road = p["RoadName"]
        from_s = p["From"]
        to_s = p["To"]
        coords = feat["geometry"]["coordinates"][0]

        print(f"Seg {sid}: {road} ({from_s} -> {to_s}) — {prob['pct_outside']:.0f}% outside")

        # Re-geocode both endpoints to ensure they're inside Lake County
        # Try multiple strategies
        clean_road = road
        if "(" in road:
            clean_road = road[:road.index("(")].strip()
        first_road = road.split("/")[0].strip() if "/" in road else road

        # FROM queries
        from_queries = [
            f"{road} & {from_s}, Lake County, FL",
            f"{from_s} & {road}, Lake County, FL",
            f"{clean_road} & {from_s}, Lake County, FL",
            f"{first_road} & {from_s}, Lake County, FL",
        ]
        for town in ["Leesburg", "Eustis", "Mount Dora", "Tavares", "Clermont",
                     "Lady Lake", "Minneola", "Groveland", "Umatilla", "Montverde",
                     "Sorrento", "Fruitland Park", "Howey-in-the-Hills"]:
            from_queries.append(f"{road} & {from_s}, {town}, FL")
        from_queries.append(f"{from_s}, Lake County, FL")

        # TO queries
        to_queries = [
            f"{road} & {to_s}, Lake County, FL",
            f"{to_s} & {road}, Lake County, FL",
            f"{clean_road} & {to_s}, Lake County, FL",
            f"{first_road} & {to_s}, Lake County, FL",
        ]
        for town in ["Leesburg", "Eustis", "Mount Dora", "Tavares", "Clermont",
                     "Lady Lake", "Minneola", "Groveland", "Umatilla", "Montverde",
                     "Sorrento", "Fruitland Park", "Howey-in-the-Hills"]:
            to_queries.append(f"{road} & {to_s}, {town}, FL")
        to_queries.append(f"{to_s}, Lake County, FL")

        new_from = None
        for q in from_queries:
            time.sleep(0.3)
            r = geocode_in_county(q, county_poly)
            if r:
                new_from = r
                break

        new_to = None
        for q in to_queries:
            time.sleep(0.3)
            r = geocode_in_county(q, county_poly)
            if r:
                # Ensure different from FROM
                if new_from and abs(r[0]-new_from[0]) + abs(r[1]-new_from[1]) > 0.001:
                    new_to = r
                    break
                elif not new_from:
                    new_to = r
                    break

        if new_from and new_to:
            print(f"  FROM: ({new_from[0]:.5f}, {new_from[1]:.5f}) score={new_from[2]:.0f}")
            print(f"  TO:   ({new_to[0]:.5f}, {new_to[1]:.5f}) score={new_to[2]:.0f}")

            # Route
            time.sleep(0.55)
            route = get_route(new_from[0], new_from[1], new_to[0], new_to[1])
            if route:
                route_coords, route_dist = route
                route_km = route_dist / 1000.0
                straight_km = haversine(new_from[0], new_from[1], new_to[0], new_to[1])
                detour = route_km / straight_km if straight_km > 0.05 else 1.0

                # Check new route
                new_outside = sum(1 for c in route_coords if not in_county(c[0], c[1], county_poly))
                new_pct = new_outside / len(route_coords) * 100 if route_coords else 0

                if new_pct < prob["pct_outside"]:
                    feat["geometry"]["coordinates"] = [route_coords]
                    p["Route_Distance_km"] = round(route_km, 2)
                    p["Straight_Distance_km"] = round(straight_km, 2)
                    p["Detour_Ratio"] = round(detour, 2)
                    p["Route_Points"] = len(route_coords)
                    p["Route_Status"] = f"DEEP_AUDIT_FIXED (was {prob['pct_outside']:.0f}% OOB, now {new_pct:.0f}%)"
                    fixed += 1
                    print(f"  FIXED: {len(route_coords)} pts, {route_km:.1f} km, {new_pct:.0f}% OOB (was {prob['pct_outside']:.0f}%)")
                else:
                    still_bad += 1
                    p["Route_Status"] = f"AUDIT_FLAGGED ({prob['pct_outside']:.0f}% OOB)"
                    print(f"  NOT IMPROVED: still {new_pct:.0f}% OOB")
            else:
                still_bad += 1
                p["Route_Status"] = f"AUDIT_FLAGGED ({prob['pct_outside']:.0f}% OOB)"
                print(f"  ROUTING FAILED")
        else:
            still_bad += 1
            p["Route_Status"] = f"AUDIT_FLAGGED ({prob['pct_outside']:.0f}% OOB)"
            print(f"  GEOCODING FAILED (from={new_from is not None}, to={new_to is not None})")

    # Save
    with open("/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS_routed.geojson", "w") as f:
        json.dump(geojson, f)

    # ── Final recount ───────────────────────────────────────
    print(f"\n{'='*60}")
    print("FINAL DEEP AUDIT RECOUNT")
    print(f"{'='*60}\n")

    total_outside = 0
    segs_with_oob = 0
    for feat in features:
        coords = feat["geometry"]["coordinates"][0]
        oob = sum(1 for c in coords if not in_county(c[0], c[1], county_poly))
        if oob > 0:
            segs_with_oob += 1
            total_outside += oob

    total_pts = sum(len(f["geometry"]["coordinates"][0]) for f in features)
    print(f"Total route points: {total_pts}")
    print(f"Points outside county: {total_outside} ({total_outside/total_pts*100:.1f}%)")
    print(f"Segments with any OOB: {segs_with_oob}")
    print(f"Fixed in this pass: {fixed}")
    print(f"Still flagged: {still_bad}")


if __name__ == "__main__":
    main()
