#!/usr/bin/env python3
"""
Cross-validation: Sample 60 key segments across the county and geocode
via Nominatim (OSM) to compare against ArcGIS results.
Uses a stratified sample: major highways, county roads, local streets.
"""

import json, math, time, urllib.request, urllib.parse, random

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
VIEWBOX = "-82.05,29.10,-81.20,28.35"
DELAY = 1.1

def nominatim_geocode(query):
    params = urllib.parse.urlencode({
        "q": query, "format": "json", "limit": 3,
        "viewbox": VIEWBOX, "bounded": "1", "countrycodes": "us",
    })
    url = f"{NOMINATIM_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "LakeCountyCMS-XV/1.0 (research)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        if data:
            return float(data[0]["lon"]), float(data[0]["lat"])
    except: pass
    return None

def haversine_m(lon1, lat1, lon2, lat2):
    R = 6371000
    dlat = math.radians(lat2 - lat1); dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def main():
    with open("/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS.geojson") as f:
        arcgis = json.load(f)

    features = arcgis["features"]

    # Stratified sample: pick segments from different road types
    sr_segs = [f for f in features if f["properties"]["RoadName"].startswith("SR ")]
    us_segs = [f for f in features if f["properties"]["RoadName"].startswith("US ")]
    cr_segs = [f for f in features if f["properties"]["RoadName"].startswith("CR ")]
    local = [f for f in features if f not in sr_segs + us_segs + cr_segs]

    random.seed(42)
    sample = []
    sample += random.sample(sr_segs, min(15, len(sr_segs)))
    sample += random.sample(us_segs, min(15, len(us_segs)))
    sample += random.sample(cr_segs, min(20, len(cr_segs)))
    sample += random.sample(local, min(10, len(local)))

    print(f"Cross-validating {len(sample)} segments (ArcGIS vs Nominatim)\n")
    print(f"{'Seg':>6} {'Road':<30} {'Endpt':5} {'ArcGIS':>22} {'Nominatim':>22} {'Delta(m)':>10} {'Match':>6}")
    print("-" * 110)

    results = []
    from_diffs = []
    to_diffs = []

    for feat in sample:
        p = feat["properties"]
        sid = p["SEGMENT_ID"]
        road = p["RoadName"]
        from_s = p["From"]
        to_s = p["To"]
        coords = feat["geometry"]["coordinates"][0]
        arc_from = (coords[0][0], coords[0][1])
        arc_to = (coords[1][0], coords[1][1])

        # Geocode FROM via Nominatim
        time.sleep(DELAY)
        nom_from = nominatim_geocode(f"{road} & {from_s}, Lake County, Florida")
        if not nom_from:
            time.sleep(DELAY)
            nom_from = nominatim_geocode(f"{from_s}, Lake County, Florida")

        # Geocode TO via Nominatim
        time.sleep(DELAY)
        nom_to = nominatim_geocode(f"{road} & {to_s}, Lake County, Florida")
        if not nom_to:
            time.sleep(DELAY)
            nom_to = nominatim_geocode(f"{to_s}, Lake County, Florida")

        # Compare FROM
        if nom_from:
            d = haversine_m(arc_from[0], arc_from[1], nom_from[0], nom_from[1])
            match = "OK" if d < 500 else "WARN" if d < 2000 else "BAD"
            from_diffs.append(d)
            print(f"{sid:>6} {road[:30]:<30} FROM  ({arc_from[0]:>9.5f},{arc_from[1]:>8.5f}) ({nom_from[0]:>9.5f},{nom_from[1]:>8.5f}) {d:>9.0f}m {match:>6}")
            results.append({"sid": sid, "road": road, "endpoint": "FROM",
                           "arc_lon": arc_from[0], "arc_lat": arc_from[1],
                           "nom_lon": nom_from[0], "nom_lat": nom_from[1],
                           "delta_m": round(d, 1), "match": match})
        else:
            print(f"{sid:>6} {road[:30]:<30} FROM  ({arc_from[0]:>9.5f},{arc_from[1]:>8.5f}) {'NOT FOUND':>22} {'—':>10} {'MISS':>6}")
            results.append({"sid": sid, "road": road, "endpoint": "FROM",
                           "arc_lon": arc_from[0], "arc_lat": arc_from[1],
                           "nom_lon": None, "nom_lat": None, "delta_m": None, "match": "MISS"})

        # Compare TO
        if nom_to:
            d = haversine_m(arc_to[0], arc_to[1], nom_to[0], nom_to[1])
            match = "OK" if d < 500 else "WARN" if d < 2000 else "BAD"
            to_diffs.append(d)
            print(f"{sid:>6} {road[:30]:<30} TO    ({arc_to[0]:>9.5f},{arc_to[1]:>8.5f}) ({nom_to[0]:>9.5f},{nom_to[1]:>8.5f}) {d:>9.0f}m {match:>6}")
            results.append({"sid": sid, "road": road, "endpoint": "TO",
                           "arc_lon": arc_to[0], "arc_lat": arc_to[1],
                           "nom_lon": nom_to[0], "nom_lat": nom_to[1],
                           "delta_m": round(d, 1), "match": match})
        else:
            print(f"{sid:>6} {road[:30]:<30} TO    ({arc_to[0]:>9.5f},{arc_to[1]:>8.5f}) {'NOT FOUND':>22} {'—':>10} {'MISS':>6}")
            results.append({"sid": sid, "road": road, "endpoint": "TO",
                           "arc_lon": arc_to[0], "arc_lat": arc_to[1],
                           "nom_lon": None, "nom_lat": None, "delta_m": None, "match": "MISS"})

    # Summary stats
    all_diffs = from_diffs + to_diffs
    matched = [r for r in results if r["delta_m"] is not None]
    ok = sum(1 for r in matched if r["match"] == "OK")
    warn = sum(1 for r in matched if r["match"] == "WARN")
    bad = sum(1 for r in matched if r["match"] == "BAD")
    miss = sum(1 for r in results if r["match"] == "MISS")

    print(f"\n{'='*60}")
    print(f"CROSS-VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"Sample size: {len(sample)} segments ({len(results)} endpoints)")
    print(f"Nominatim found: {len(matched)} / {len(results)} ({len(matched)/len(results)*100:.0f}%)")
    print(f"Match (<500m): {ok} ({ok/max(len(matched),1)*100:.0f}%)")
    print(f"Warn (500-2000m): {warn} ({warn/max(len(matched),1)*100:.0f}%)")
    print(f"Bad (>2000m): {bad} ({bad/max(len(matched),1)*100:.0f}%)")
    print(f"Not found: {miss}")
    if all_diffs:
        print(f"\nDistance stats (matched pairs):")
        print(f"  Median: {sorted(all_diffs)[len(all_diffs)//2]:.0f}m")
        print(f"  Mean: {sum(all_diffs)/len(all_diffs):.0f}m")
        print(f"  P90: {sorted(all_diffs)[int(len(all_diffs)*0.9)]:.0f}m")
        print(f"  Max: {max(all_diffs):.0f}m")

    # Save
    out = {"summary": {
        "sample_size": len(sample), "endpoints_compared": len(results),
        "nominatim_found": len(matched), "ok": ok, "warn": warn,
        "bad": bad, "miss": miss,
        "median_m": round(sorted(all_diffs)[len(all_diffs)//2], 1) if all_diffs else None,
        "mean_m": round(sum(all_diffs)/len(all_diffs), 1) if all_diffs else None,
        "p90_m": round(sorted(all_diffs)[int(len(all_diffs)*0.9)], 1) if all_diffs else None,
    }, "results": results}
    with open("/Users/pg/Documents/S/Lake_County_CMS/cross_validation_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: cross_validation_results.json")

if __name__ == "__main__":
    main()
