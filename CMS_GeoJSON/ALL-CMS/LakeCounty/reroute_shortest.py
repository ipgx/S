#!/usr/bin/env python3
"""
Re-route all 452 segments using Valhalla with shortest-distance costing.
Valhalla (FOSSGIS instance) supports costing_options.auto.shortest = true,
which optimizes for minimum distance rather than minimum time.
"""

import json
import math
import time
import urllib.request

VALHALLA_URL = "https://valhalla1.openstreetmap.de/route"


def decode_polyline(encoded, precision=6):
    """Decode a Valhalla encoded polyline into list of [lon, lat]."""
    inv = 1.0 / (10 ** precision)
    decoded = []
    previous = [0, 0]
    i = 0
    while i < len(encoded):
        for dim in range(2):  # lat, lon
            shift = 0
            result = 0
            while True:
                b = ord(encoded[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            if result & 1:
                previous[dim] += ~(result >> 1)
            else:
                previous[dim] += (result >> 1)
        decoded.append([previous[1] * inv, previous[0] * inv])  # [lon, lat]
    return decoded


def valhalla_route_shortest(f_lon, f_lat, t_lon, t_lat):
    """Route using Valhalla with shortest distance costing."""
    payload = json.dumps({
        "locations": [
            {"lon": f_lon, "lat": f_lat},
            {"lon": t_lon, "lat": t_lat}
        ],
        "costing": "auto",
        "costing_options": {
            "auto": {"shortest": True}
        },
        "units": "kilometers"
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            VALHALLA_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "LakeCountyCMS/1.0 (research)"
            }
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())

        trip = data.get("trip", {})
        legs = trip.get("legs", [])
        if not legs:
            return None

        shape_enc = legs[0].get("shape", "")
        dist_km = trip.get("summary", {}).get("length", 0)

        coords = decode_polyline(shape_enc, precision=6)
        if len(coords) < 2:
            return None

        return coords, dist_km
    except Exception as e:
        return None


def haversine(lon1, lat1, lon2, lat2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def main():
    with open("/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS_routed.geojson") as f:
        geojson = json.load(f)

    features = geojson["features"]
    total = len(features)
    print(f"Re-routing {total} segments with Valhalla (shortest distance)...\n")

    success = 0
    failed = 0
    improved = 0

    for idx, feat in enumerate(features):
        p = feat["properties"]
        sid = p["SEGMENT_ID"]
        road = p["RoadName"]
        coords = feat["geometry"]["coordinates"][0]
        from_pt = coords[0]
        to_pt = coords[-1]

        old_dist = p.get("Route_Distance_km", 0)

        # Rate limit: ~40 req/min for FOSSGIS
        time.sleep(0.55)

        result = valhalla_route_shortest(from_pt[0], from_pt[1], to_pt[0], to_pt[1])

        if result:
            route_coords, route_km = result
            straight_km = haversine(from_pt[0], from_pt[1], to_pt[0], to_pt[1])
            detour = route_km / straight_km if straight_km > 0.05 else 1.0

            feat["geometry"]["coordinates"] = [route_coords]
            p["Route_Distance_km"] = round(route_km, 2)
            p["Straight_Distance_km"] = round(straight_km, 2)
            p["Detour_Ratio"] = round(detour, 2)
            p["Route_Points"] = len(route_coords)
            p["Routing_Engine"] = "Valhalla (shortest)"

            # Keep existing status flags for clipped/fixed segments
            if p.get("Route_Status") not in ("CLIPPED_TO_COUNTY", "FIXED_OOB", "FIXED_COLLAPSED"):
                if detour > 5:
                    p["Route_Status"] = f"HIGH_DETOUR:{detour:.1f}x"
                elif detour > 3:
                    p["Route_Status"] = f"MODERATE_DETOUR:{detour:.1f}x"
                else:
                    p["Route_Status"] = "OK"

            delta = ""
            if old_dist and old_dist > 0:
                diff = route_km - old_dist
                if diff < -0.05:
                    improved += 1
                    delta = f"  ({diff:+.2f} km shorter)"

            success += 1
            if (idx + 1) % 20 == 0 or idx == 0:
                print(f"  [{idx+1:>3}/{total}] Seg {sid:>5}: {road[:35]:35s} {route_km:>7.2f} km  {len(route_coords):>4} pts  detour={detour:.2f}x{delta}")
        else:
            failed += 1
            print(f"  [{idx+1:>3}/{total}] Seg {sid:>5}: {road[:35]:35s} ** FAILED — keeping previous route **")

        if (idx + 1) % 50 == 0:
            print(f"\n  --- Progress: {idx+1}/{total} ({success} ok, {failed} failed) ---\n")

    print(f"\n{'='*60}")
    print(f"ROUTING COMPLETE")
    print(f"{'='*60}")
    print(f"Total: {total}")
    print(f"Successfully re-routed: {success}")
    print(f"Failed (kept previous): {failed}")
    print(f"Shorter than OSRM: {improved}")

    # Save
    out_path = "/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS_routed.geojson"
    with open(out_path, "w") as f:
        json.dump(geojson, f)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
