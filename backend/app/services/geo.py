"""Geofencing. Polygons are [[lat, lng], ...]; plain ray-casting (no PostGIS needed for the prototype)."""
import math


def point_in_polygon(lat: float, lng: float, polygon: list[list[float]]) -> bool:
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if (xi > lng) != (xj > lng):
            crossing_lat = (yj - yi) * (lng - xi) / (xj - xi) + yi
            if lat < crossing_lat:
                inside = not inside
        j = i
    return inside


def zones_containing(lat: float | None, lng: float | None, zones) -> list:
    """All zones containing the point, highest priority first."""
    if lat is None or lng is None:
        return []
    hits = [z for z in zones if point_in_polygon(lat, lng, z.polygon)]
    return sorted(hits, key=lambda z: (-z.priority, z.id))


# ---- routes ---------------------------------------------------------------------------------------------

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def route_position(waypoints: list[dict], lat: float, lng: float) -> dict | None:
    """Where a point is along a route: current leg, percent covered, distance from the path and the next stop.

    Each leg is treated as a straight line (the simulator drives straight lines between places too). The distance to a leg is
    computed in a flat local frame centred on the point, which is accurate to a few km even over ~1000 km legs; the default
    corridor is 25 km, so that is well inside the tolerance."""
    if len(waypoints) < 2:
        return None
    kx, ky = 111.320 * math.cos(math.radians(lat)), 110.574
    pts = [((w["lng"] - lng) * kx, (w["lat"] - lat) * ky) for w in waypoints]          # km, point at the origin
    lengths = [haversine_km(a["lat"], a["lng"], b["lat"], b["lng"]) for a, b in zip(waypoints, waypoints[1:])]
    total = sum(lengths) or 1e-9
    best = None
    for i, ((x1, y1), (x2, y2)) in enumerate(zip(pts, pts[1:])):
        dx, dy = x2 - x1, y2 - y1
        seg2 = dx * dx + dy * dy
        t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(x1 * dx + y1 * dy) / seg2))
        dist = math.hypot(x1 + t * dx, y1 + t * dy)
        if best is None or dist < best[0]:
            best = (dist, i, t)
    dist, leg, t = best
    along = sum(lengths[:leg]) + t * lengths[leg]
    nxt = waypoints[leg + 1]
    return {"leg": leg, "progress": round(100 * along / total, 1), "offset_km": round(dist, 2), "total_km": round(total, 1),
            "next_stop": nxt["name"], "to_next_km": round(haversine_km(lat, lng, nxt["lat"], nxt["lng"]), 1)}
