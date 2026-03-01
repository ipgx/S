#!/usr/bin/env python3
"""
Clip all route geometries to Lake County boundary.
For segments near county borders, trim route points that fall outside.
Keeps the portion of the route inside the county + boundary crossing points.
"""

import json
import math


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

def line_segment_intersect_polygon_edge(p1, p2, poly):
    """Find intersection point of line segment p1-p2 with polygon edges."""
    x1, y1 = p1; x2, y2 = p2
    best = None
    best_t = float('inf')

    n = len(poly)
    for i in range(n):
        x3, y3 = poly[i]
        x4, y4 = poly[(i + 1) % n]

        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-12:
            continue

        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
        u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom

        if 0 <= t <= 1 and 0 <= u <= 1:
            if t < best_t:
                best_t = t
                ix = x1 + t * (x2 - x1)
                iy = y1 + t * (y2 - y1)
                best = [ix, iy]

    return best

def find_boundary_crossing(p_inside, p_outside, county_poly):
    """Find where a line from inside to outside crosses the county boundary."""
    for polygon in county_poly:
        outer = polygon[0]
        pt = line_segment_intersect_polygon_edge(p_inside, p_outside, outer)
        if pt:
            return pt
    # Fallback: return the inside point
    return list(p_inside)


def clip_route_to_county(coords, county_poly):
    """Clip a route (list of [lon,lat]) to the county boundary.
    Returns the clipped coords keeping only the inside portion,
    with boundary crossing points added at transitions."""

    n = len(coords)
    if n < 2:
        return coords

    # Check each point
    inside_flags = [in_county(c[0], c[1], county_poly) for c in coords]

    # If all inside, no clipping needed
    if all(inside_flags):
        return coords

    # If all outside, this is a problem (shouldn't happen after endpoint fixes)
    if not any(inside_flags):
        return coords  # return as-is, flag it

    # Build clipped route: keep inside segments, add boundary crossings
    clipped = []

    for i in range(n):
        curr_in = inside_flags[i]
        prev_in = inside_flags[i - 1] if i > 0 else None

        if i == 0:
            if curr_in:
                clipped.append(coords[i])
            else:
                # Start is outside — find where route enters county
                # Look ahead for first inside point
                for j in range(1, n):
                    if inside_flags[j]:
                        crossing = find_boundary_crossing(
                            coords[j], coords[i], county_poly)
                        clipped.append(crossing)
                        break
        else:
            if curr_in and prev_in:
                # Both inside — just add
                clipped.append(coords[i])
            elif curr_in and not prev_in:
                # Entering county — add crossing point then current
                crossing = find_boundary_crossing(
                    coords[i], coords[i-1], county_poly)
                clipped.append(crossing)
                clipped.append(coords[i])
            elif not curr_in and prev_in:
                # Leaving county — add crossing point
                crossing = find_boundary_crossing(
                    coords[i-1], coords[i], county_poly)
                clipped.append(crossing)
            # else: both outside — skip

    # Ensure we have at least 2 points
    if len(clipped) < 2:
        # Fallback: just keep the inside points
        clipped = [c for c, f in zip(coords, inside_flags) if f]
        if len(clipped) < 2:
            return coords  # give up

    return clipped


def haversine(lon1, lat1, lon2, lat2):
    R = 6371
    dlat = math.radians(lat2 - lat1); dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def route_length_km(coords):
    total = 0
    for i in range(1, len(coords)):
        total += haversine(coords[i-1][0], coords[i-1][1],
                          coords[i][0], coords[i][1])
    return total


def main():
    with open("/Users/pg/Documents/S/FL_Counties.geojson") as f:
        counties = json.load(f)
    county_poly = None
    for feat in counties["features"]:
        if "Lake" in feat["properties"].get("NAME", ""):
            county_poly = feat["geometry"]["coordinates"]; break

    with open("/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS_routed.geojson") as f:
        geojson = json.load(f)

    features = geojson["features"]
    total = len(features)

    print(f"Clipping {total} segment routes to Lake County boundary...\n")

    clipped_count = 0
    still_oob = 0

    for feat in features:
        p = feat["properties"]
        sid = p["SEGMENT_ID"]
        coords = feat["geometry"]["coordinates"][0]
        n_before = len(coords)

        # Check if any points are outside
        outside = sum(1 for c in coords if not in_county(c[0], c[1], county_poly))
        if outside == 0:
            continue

        pct_before = outside / n_before * 100

        # Clip
        clipped = clip_route_to_county(coords, county_poly)
        n_after = len(clipped)

        # Recheck
        outside_after = sum(1 for c in clipped if not in_county(c[0], c[1], county_poly))
        pct_after = outside_after / n_after * 100 if n_after > 0 else 0

        # Update geometry
        feat["geometry"]["coordinates"] = [clipped]
        route_km = route_length_km(clipped)
        p["Route_Distance_km"] = round(route_km, 2)
        p["Route_Points"] = n_after

        if pct_after < pct_before:
            clipped_count += 1
            p["Route_Status"] = "CLIPPED_TO_COUNTY"
            print(f"  Seg {sid:>5}: {p['RoadName'][:35]:35s} {n_before:>4}->{n_after:>4} pts  OOB: {pct_before:.0f}%->{pct_after:.0f}%")
        else:
            still_oob += 1

    # Final check
    print(f"\n{'='*60}")
    print("POST-CLIP VALIDATION")
    print(f"{'='*60}\n")

    total_pts = 0
    total_oob = 0
    segs_oob = 0
    oob_details = []

    for feat in features:
        p = feat["properties"]
        coords = feat["geometry"]["coordinates"][0]
        total_pts += len(coords)
        oob = sum(1 for c in coords if not in_county(c[0], c[1], county_poly))
        if oob > 0:
            segs_oob += 1
            total_oob += oob
            pct = oob / len(coords) * 100
            oob_details.append(f"  Seg {p['SEGMENT_ID']:>5}: {p['RoadName'][:35]:35s} {oob:>3}/{len(coords):>4} ({pct:.1f}%)")

    print(f"Total route points: {total_pts}")
    print(f"Points outside county: {total_oob} ({total_oob/total_pts*100:.2f}%)")
    print(f"Segments with any OOB: {segs_oob}")
    print(f"Clipped: {clipped_count}")

    if oob_details:
        print(f"\nRemaining OOB segments:")
        for d in oob_details:
            print(d)

    # Save
    out_path = "/Users/pg/Documents/S/Lake_County_CMS/Lake_County_CMS_routed.geojson"
    with open(out_path, "w") as f:
        json.dump(geojson, f)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
