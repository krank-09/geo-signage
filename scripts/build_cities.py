#!/usr/bin/env python3
"""Builds backend/app/data/cities.json: predefined city boundaries for one-click zone creation.

Boundaries come from OpenStreetMap via Nominatim (data (c) OpenStreetMap contributors, ODbL). Each polygon is simplified
to a modest vertex count. A city whose boundary is missing or implausible falls back to a circle around its centre and is
marked "approx". Run rarely (it makes ~1 request per second, as Nominatim's usage policy requires):

    python3 scripts/build_cities.py            # rebuilds the whole file
    python3 scripts/build_cities.py Jaipur     # adds/refreshes just one city
"""
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "cities.json"
UA = "geo-signage-city-builder/1.0 (hackathon project; boundaries for signage zones)"
MAX_VERTICES = 70
FALLBACK_RADIUS_KM = 15

# name, state, fallback centre (lat, lng)
CITIES = [
    ("Delhi", "Delhi", (28.6139, 77.2090)), ("Mumbai", "Maharashtra", (19.0760, 72.8777)),
    ("Bengaluru", "Karnataka", (12.9716, 77.5946)), ("Chennai", "Tamil Nadu", (13.0827, 80.2707)),
    ("Kolkata", "West Bengal", (22.5726, 88.3639)), ("Hyderabad", "Telangana", (17.3850, 78.4867)),
    ("Pune", "Maharashtra", (18.5204, 73.8567)), ("Ahmedabad", "Gujarat", (23.0225, 72.5714)),
    ("Jaipur", "Rajasthan", (26.9124, 75.7873)), ("Surat", "Gujarat", (21.1702, 72.8311)),
    ("Lucknow", "Uttar Pradesh", (26.8467, 80.9462)), ("Kanpur", "Uttar Pradesh", (26.4499, 80.3319)),
    ("Nagpur", "Maharashtra", (21.1458, 79.0882)), ("Indore", "Madhya Pradesh", (22.7196, 75.8577)),
    ("Bhopal", "Madhya Pradesh", (23.2599, 77.4126)), ("Visakhapatnam", "Andhra Pradesh", (17.6868, 83.2185)),
    ("Patna", "Bihar", (25.5941, 85.1376)), ("Vadodara", "Gujarat", (22.3072, 73.1812)),
    ("Ludhiana", "Punjab", (30.9010, 75.8573)), ("Agra", "Uttar Pradesh", (27.1767, 78.0081)),
    ("Nashik", "Maharashtra", (19.9975, 73.7898)), ("Chandigarh", "Chandigarh", (30.7333, 76.7794)),
    ("Coimbatore", "Tamil Nadu", (11.0168, 76.9558)), ("Kochi", "Kerala", (9.9312, 76.2673)),
    ("Thiruvananthapuram", "Kerala", (8.5241, 76.9366)), ("Guwahati", "Assam", (26.1445, 91.7362)),
    ("Bhubaneswar", "Odisha", (20.2961, 85.8245)), ("Dehradun", "Uttarakhand", (30.3165, 78.0322)),
    ("Amritsar", "Punjab", (31.6340, 74.8723)), ("Ranchi", "Jharkhand", (23.3441, 85.3096)),
    ("Raipur", "Chhattisgarh", (21.2514, 81.6296)), ("Jodhpur", "Rajasthan", (26.2389, 73.0243)),
    ("Madurai", "Tamil Nadu", (9.9252, 78.1198)), ("Varanasi", "Uttar Pradesh", (25.3176, 82.9739)),
    ("Mysuru", "Karnataka", (12.2958, 76.6394)), ("Srinagar", "Jammu and Kashmir", (34.0837, 74.7973)),
    ("Shimla", "Himachal Pradesh", (31.1048, 77.1734)), ("Gurugram", "Haryana", (28.4595, 77.0266)),
    ("Noida", "Uttar Pradesh", (28.5355, 77.3910)), ("Panaji", "Goa", (15.4909, 73.8278)),
    ("Udaipur", "Rajasthan", (24.5854, 73.7125)), ("Mangaluru", "Karnataka", (12.9141, 74.8560)),
    ("Vijayawada", "Andhra Pradesh", (16.5062, 80.6480)), ("Jalandhar", "Punjab", (31.3260, 75.5762)),
    ("Patiala", "Punjab", (30.3398, 76.3869)), ("Mohali", "Punjab", (30.7046, 76.7179)),
]


def simplify(points, tol):
    """Douglas-Peucker on (lat, lng) points (iterative, so deep rings cannot blow the stack)."""
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (ay, ax), (by, bx) = points[a], points[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1e-12
        far, far_d = -1, 0.0
        for i in range(a + 1, b):
            y, x = points[i]
            d = abs(dy * (x - ax) - dx * (y - ay)) / norm
            if d > far_d:
                far, far_d = i, d
        if far_d > tol:
            keep[far] = True
            stack += [(a, far), (far, b)]
    return [p for p, k in zip(points, keep) if k]


def fit(ring):
    """Simplify a closed boundary ring to at most MAX_VERTICES points."""
    if ring[0] == ring[-1]:
        ring = ring[:-1]
    # A closed ring has no usable start-to-end line, so split it at the point farthest from the start.
    far = max(range(len(ring)), key=lambda i: (ring[i][0] - ring[0][0]) ** 2 + (ring[i][1] - ring[0][1]) ** 2)
    first_half, second_half = ring[: far + 1], ring[far:] + [ring[0]]

    def run(tol):
        return simplify(first_half, tol)[:-1] + simplify(second_half, tol)[:-1]

    tol, pts = 0.0004, run(0.0004)
    while len(pts) > MAX_VERTICES:
        tol *= 1.3
        pts = run(tol)
    return [[round(y, 5), round(x, 5)] for y, x in pts]


def circle(center, km, n=32):
    lat0, lng0 = center
    return [[round(lat0 + (km / 111) * math.sin(2 * math.pi * i / n), 5),
             round(lng0 + (km / (111 * math.cos(math.radians(lat0)))) * math.cos(2 * math.pi * i / n), 5)] for i in range(n)]


CITY_TYPES = {"city", "town", "municipality", "municipal_corporation"}
MAX_AREA_KM2 = 1600      # larger than an Indian city proper; bigger means a district or state was matched
MIN_AREA_KM2 = 20        # smaller means a ward or a council area, not the city


def area_km2(pts):
    lat0 = sum(p[0] for p in pts) / len(pts)
    k = 111 * 111 * math.cos(math.radians(lat0))
    s = 0.0
    for i in range(len(pts)):
        (y1, x1), (y2, x2) = pts[i], pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2 * k


def query(name, state, city_only):
    params = {"q": f"{name}, {state}, India", "format": "jsonv2", "polygon_geojson": 1, "polygon_threshold": 0.001, "limit": 8}
    if city_only:
        params["featureType"] = "city"
    req = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{urllib.parse.urlencode(params)}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def pick(results):
    """A boundary polygon of plausible city size. City-typed results win; among equals the larger one (the city
    proper, not one of its council areas). Districts and states are rejected by the area window, not by name,
    because Nominatim types some cities oddly (Chandigarh is tagged as a state)."""
    best = None
    for res in results:
        g = res.get("geojson") or {}
        if g.get("type") not in ("Polygon", "MultiPolygon") or res.get("category") != "boundary":
            continue
        rings = [g["coordinates"][0]] if g["type"] == "Polygon" else [p[0] for p in g["coordinates"]]
        ring = max(rings, key=len)                          # the main body, not outlying islands
        pts = [(c[1], c[0]) for c in ring]                  # GeoJSON is [lng, lat]
        a = area_km2(pts)
        if len(pts) < 4 or not (MIN_AREA_KM2 <= a <= MAX_AREA_KM2):
            continue
        key = (res.get("addresstype") in CITY_TYPES, a)
        if best is None or key > best[0]:
            best = (key, a, pts, (float(res["lat"]), float(res["lon"])))
    return best


def fetch_boundary(name, state):
    for city_only in (False, True):                          # second try: ask Nominatim for settlements only
        best = pick(query(name, state, city_only))
        if best:
            return best
        time.sleep(1.1)
    return None


def build(name, state, fallback_center):
    try:
        found = fetch_boundary(name, state)
    except Exception as e:  # network or parse trouble: keep going with the fallback
        print(f"  {name}: lookup failed ({e})")
        found = None
    if found:
        _key, area, pts, _centre = found
        return {"id": name.lower().replace(" ", "-"), "name": name, "state": state, "center": [round(fallback_center[0], 5), round(fallback_center[1], 5)],
                "source": "osm", "area_km2": round(area), "polygon": fit(pts)}
    return {"id": name.lower().replace(" ", "-"), "name": name, "state": state, "center": list(fallback_center),
            "source": "approx", "area_km2": round(math.pi * FALLBACK_RADIUS_KM ** 2), "polygon": circle(fallback_center, FALLBACK_RADIUS_KM)}


def main():
    wanted = {a.lower() for a in sys.argv[1:]}
    existing = {c["name"].lower(): c for c in json.loads(OUT.read_text())} if OUT.exists() and wanted else {}
    out = []
    for name, state, centre in CITIES:
        if wanted and name.lower() not in wanted:
            if name.lower() in existing:
                out.append(existing[name.lower()])
            continue
        c = build(name, state, centre)
        print(f"{name:19s} {c['source']:6s} {len(c['polygon']):3d}v {c['area_km2']:5d}km2")
        out.append(c)
        time.sleep(1.1)
    out.sort(key=lambda c: c["name"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"wrote {len(out)} cities to {OUT} ({OUT.stat().st_size // 1024} KB); {sum(c['source'] == 'osm' for c in out)} from OpenStreetMap")


if __name__ == "__main__":
    main()
