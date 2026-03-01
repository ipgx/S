#!/usr/bin/env python3
"""
Fix segments that collapsed to zero-length after the OOB fix.
These are segments where the re-geocoded FROM and TO ended up at the same point.
We need to re-geocode the endpoints separately with better distinction.
"""

import json
import time
import urllib.request
import urllib.parse
import math


def point_in_polygon(x, y, polygon):
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


def point_in_multipolygon(lon, lat, mp):
    for polygon in mp:
        outer = polygon[0]
        if point_in_polygon(lon, lat, outer):
            in_hole = False
            for hole in polygon[1:]:
                if point_in_polygon(lon, lat, hole):
                    in_hole = True
                    break
            if not in_hole:
                return True
    return False


ARCGIS_URL = ("https://geocode.arcgis.com/arcgis/rest/services/World/"
              "GeocodeServer/findAddressCandidates")


def geocode_in_county(address, county_poly, max_results=10):
    """Geocode and return best candidate inside Lake County."""
    params = urllib.parse.urlencode({
        "SingleLine": address,
        "f": "json",
        "outFields": "Match_addr,Addr_type",
        "maxLocations": max_results,
        "searchExtent": "-82.05,28.35,-81.20,29.10",
        "location": "-81.6,28.7",
        "distance": 80000,
    })
    url = f"{ARCGIS_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        for c in data.get("candidates", []):
            lon = c["location"]["x"]
            lat = c["location"]["y"]
            score = c.get("score", 0)
            if point_in_multipolygon(lon, lat, county_poly) and score >= 70:
                return lon, lat, score
    except:
        pass
    return None


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
    except:
        pass
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
    with open("/Users/pg/Documents/S/FL_Counties.geojson") as f:
        counties = json.load(f)
    county_poly = None
    for feat in counties["features"]:
        if "Lake" in feat["properties"].get("NAME", ""):
            county_poly = feat["geometry"]["coordinates"]
            break

    with open("/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS_routed.geojson") as f:
        geojson = json.load(f)

    # Find collapsed segments (2 points, 0 km)
    collapsed = []
    for feat in geojson["features"]:
        coords = feat["geometry"]["coordinates"][0]
        if len(coords) <= 2:
            c0, c1 = coords[0], coords[-1]
            dist = abs(c0[0] - c1[0]) + abs(c0[1] - c1[1])
            if dist < 0.0001:
                collapsed.append(feat)

    print(f"Found {len(collapsed)} collapsed segments to fix:\n")

    for feat in collapsed:
        p = feat["properties"]
        sid = p["SEGMENT_ID"]
        road = p["RoadName"]
        from_s = p["From"]
        to_s = p["To"]
        print(f"Seg {sid}: {road}  ({from_s} -> {to_s})")

        # Geocode FROM and TO separately with very specific queries
        # For FROM: use the exact road + from intersection
        from_queries = [
            f"{road} & {from_s}, Lake County, FL",
            f"{from_s} & {road}, Lake County, FL",
        ]
        if "(" in road:
            base = road[:road.index("(")].strip()
            from_queries.append(f"{base} & {from_s}, Lake County, FL")
        if "/" in road:
            parts = road.split("/")
            for part in parts:
                from_queries.append(f"{part.strip()} & {from_s}, Lake County, FL")

        # For TO: use the exact road + to intersection
        to_queries = [
            f"{road} & {to_s}, Lake County, FL",
            f"{to_s} & {road}, Lake County, FL",
        ]
        if "(" in road:
            base = road[:road.index("(")].strip()
            to_queries.append(f"{base} & {to_s}, Lake County, FL")
        if "/" in road:
            parts = road.split("/")
            for part in parts:
                to_queries.append(f"{part.strip()} & {to_s}, Lake County, FL")

        # Also try specific town-based queries
        for town in ["Leesburg", "Eustis", "Mount Dora", "Tavares", "Clermont",
                     "Lady Lake", "Minneola", "Groveland", "Umatilla"]:
            from_queries.append(f"{road} & {from_s}, {town}, FL")
            to_queries.append(f"{road} & {to_s}, {town}, FL")

        # Try to get distinct FROM point
        from_result = None
        for q in from_queries:
            time.sleep(0.3)
            r = geocode_in_county(q, county_poly)
            if r:
                from_result = r
                print(f"  FROM: ({r[0]:.5f}, {r[1]:.5f}) score={r[2]:.0f}")
                break
        if not from_result:
            time.sleep(0.3)
            r = geocode_in_county(f"{from_s}, Lake County, FL", county_poly)
            if r:
                from_result = r
                print(f"  FROM (fallback): ({r[0]:.5f}, {r[1]:.5f})")

        # Try to get distinct TO point
        to_result = None
        for q in to_queries:
            time.sleep(0.3)
            r = geocode_in_county(q, county_poly)
            if r:
                # Make sure it's different from FROM
                if from_result and abs(r[0] - from_result[0]) + abs(r[1] - from_result[1]) > 0.001:
                    to_result = r
                    print(f"  TO:   ({r[0]:.5f}, {r[1]:.5f}) score={r[2]:.0f}")
                    break
                elif not from_result:
                    to_result = r
                    print(f"  TO:   ({r[0]:.5f}, {r[1]:.5f}) score={r[2]:.0f}")
                    break
        if not to_result:
            # Try the cross-street alone
            time.sleep(0.3)
            r = geocode_in_county(f"{to_s}, Lake County, FL", county_poly)
            if r and from_result and abs(r[0] - from_result[0]) + abs(r[1] - from_result[1]) > 0.001:
                to_result = r
                print(f"  TO (fallback): ({r[0]:.5f}, {r[1]:.5f})")

        if from_result and to_result:
            # Route between them
            time.sleep(0.55)
            route = get_route(from_result[0], from_result[1], to_result[0], to_result[1])
            if route:
                route_coords, route_dist = route
                route_km = route_dist / 1000.0
                straight_km = haversine(from_result[0], from_result[1],
                                        to_result[0], to_result[1])
                detour = route_km / straight_km if straight_km > 0.05 else 1.0
                feat["geometry"]["coordinates"] = [route_coords]
                p["Route_Distance_km"] = round(route_km, 2)
                p["Straight_Distance_km"] = round(straight_km, 2)
                p["Detour_Ratio"] = round(detour, 2)
                p["Route_Points"] = len(route_coords)
                p["Route_Status"] = "FIXED_COLLAPSED"
                print(f"  ROUTED: {len(route_coords)} pts, {route_km:.1f} km")
            else:
                # At least update to straight line
                feat["geometry"]["coordinates"] = [
                    [list(from_result[:2]), list(to_result[:2])]
                ]
                p["Route_Status"] = "FIXED_COLLAPSED_STRAIGHT"
                print(f"  Set as straight line (routing failed)")
        else:
            print(f"  !! Could not fix — keeping as-is")

        print()

    # Save
    with open("/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS_routed.geojson", "w") as f:
        json.dump(geojson, f)
    print(f"Saved. Fixed {len(collapsed)} collapsed segments.")

    # Final count of remaining collapsed
    remaining = 0
    for feat in geojson["features"]:
        coords = feat["geometry"]["coordinates"][0]
        if len(coords) <= 2:
            c0, c1 = coords[0], coords[-1]
            if abs(c0[0] - c1[0]) + abs(c0[1] - c1[1]) < 0.0001:
                remaining += 1
                p = feat["properties"]
                print(f"  Still collapsed: Seg {p['SEGMENT_ID']} {p['RoadName']}")
    print(f"\nRemaining collapsed: {remaining}")


if __name__ == "__main__":
    main()
