#!/usr/bin/env python3
"""
Fix zero-length segments by trying alternative geocoding queries.
For segments where From and To geocoded to same point, try:
1. Simplified road name (strip parenthetical aliases)
2. Just the cross-street name in Lake County
3. Slight fallback queries
"""

import json
import time
import urllib.request
import urllib.parse

ARCGIS_GEOCODE_URL = (
    "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer"
    "/findAddressCandidates"
)
SEARCH_EXTENT = "-82.05,28.35,-81.20,29.10"
LAKE_COUNTY_BOUNDS = {"xmin": -82.05, "ymin": 28.35, "xmax": -81.20, "ymax": 29.10}


def geocode(address):
    params = urllib.parse.urlencode({
        "SingleLine": address,
        "f": "json",
        "outFields": "Match_addr,Addr_type",
        "maxLocations": 5,
        "searchExtent": SEARCH_EXTENT,
        "location": "-81.6,28.7",
        "distance": 80000,
    })
    url = f"{ARCGIS_GEOCODE_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        return data.get("candidates", [])
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def simplify_road(road):
    """Remove parenthetical aliases from road name."""
    if "(" in road:
        return road[:road.index("(")].strip()
    if "/" in road:
        parts = road.split("/")
        return parts[0].strip()
    return road


def try_alternative_geocodes(road, intersection, current_lon, current_lat):
    """Try multiple geocoding strategies to get a different/better point."""
    strategies = []

    # Strategy 1: Use simplified road name
    simple_road = simplify_road(road)
    if simple_road != road:
        strategies.append(f"{simple_road} & {intersection}, Lake County, FL")

    # Strategy 2: Use the cross-street + road in different order
    strategies.append(f"{intersection} & {road}, Lake County, FL")

    # Strategy 3: Cross-street alone
    strategies.append(f"{intersection}, Lake County, FL")

    # Strategy 4: Simple road + intersection with town names for known areas
    for town in ["Leesburg", "Eustis", "Mount Dora", "Tavares", "Clermont",
                 "Lady Lake", "Minneola", "Groveland", "Mascotte", "Umatilla"]:
        strategies.append(f"{road} & {intersection}, {town}, FL")

    for addr in strategies:
        time.sleep(0.3)
        candidates = geocode(addr)
        if not candidates:
            continue
        best = candidates[0]
        lon = best["location"]["x"]
        lat = best["location"]["y"]
        score = best.get("score", 0)
        # Check it's in Lake County and different from current
        b = LAKE_COUNTY_BOUNDS
        if b["xmin"] <= lon <= b["xmax"] and b["ymin"] <= lat <= b["ymax"]:
            dist = abs(lon - current_lon) + abs(lat - current_lat)
            if dist > 0.001 and score >= 70:
                return lon, lat, score, addr
    return None


def main():
    geojson_path = "/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS.geojson"
    with open(geojson_path) as f:
        geojson = json.load(f)

    zero_length = []
    for feat in geojson["features"]:
        if "ZERO_LENGTH" in feat["properties"]["QA_Flag"]:
            zero_length.append(feat)

    print(f"Found {len(zero_length)} zero-length segments to fix.\n")

    fixed = 0
    still_zero = 0

    for feat in zero_length:
        props = feat["properties"]
        coords = feat["geometry"]["coordinates"][0]
        from_lon, from_lat = coords[0]
        to_lon,   to_lat   = coords[1]

        seg_id = props["SEGMENT_ID"]
        road   = props["RoadName"]
        from_s = props["From"]
        to_s   = props["To"]

        print(f"Seg {seg_id}: {road} ({from_s} -> {to_s})")
        print(f"  Current: ({from_lon:.5f},{from_lat:.5f}) -> ({to_lon:.5f},{to_lat:.5f})")

        # Try to fix the TO point first (keep FROM, move TO)
        result = try_alternative_geocodes(road, to_s, from_lon, from_lat)
        if result:
            new_lon, new_lat, score, addr = result
            print(f"  FIXED TO: ({new_lon:.5f},{new_lat:.5f}) score={score:.1f} via '{addr}'")
            feat["geometry"]["coordinates"][0][1] = [new_lon, new_lat]
            feat["properties"]["To_Score"] = round(score, 1)
            feat["properties"]["QA_Flag"] = f"FIXED_TO (was ZERO_LENGTH)"
            fixed += 1
            continue

        # Try fixing FROM point instead
        result = try_alternative_geocodes(road, from_s, to_lon, to_lat)
        if result:
            new_lon, new_lat, score, addr = result
            print(f"  FIXED FROM: ({new_lon:.5f},{new_lat:.5f}) score={score:.1f} via '{addr}'")
            feat["geometry"]["coordinates"][0][0] = [new_lon, new_lat]
            feat["properties"]["From_Score"] = round(score, 1)
            feat["properties"]["QA_Flag"] = f"FIXED_FROM (was ZERO_LENGTH)"
            fixed += 1
            continue

        print(f"  STILL ZERO - could not resolve")
        feat["properties"]["QA_Flag"] = "ZERO_LENGTH_UNRESOLVED"
        still_zero += 1

    # Save fixed GeoJSON
    with open(geojson_path, "w") as f:
        json.dump(geojson, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Fixed: {fixed}/{len(zero_length)}")
    print(f"Still zero: {still_zero}")
    print(f"Saved to: {geojson_path}")


if __name__ == "__main__":
    main()
