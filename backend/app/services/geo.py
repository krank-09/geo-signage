"""Geofencing. Polygons are [[lat, lng], ...]; plain ray-casting (no PostGIS needed for the prototype)."""


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
