"""Location providers: simulated route, fixed point, or a real gpsd receiver."""
import threading

WAYPOINTS = {
    "chandigarh": (30.7333, 76.7794),
    "delhi": (28.6139, 77.2090),
    "jaipur": (26.9124, 75.7873),
    "mumbai": (19.0760, 72.8777),
    "ahmedabad": (23.0225, 72.5714),
}


def place_coords(name: str) -> tuple[float, float]:
    """Coordinates of a known place name (case-insensitive)."""
    key = name.strip().lower()
    if key not in WAYPOINTS:
        raise ValueError(f"Unknown place '{name}'. Choose one of: {', '.join(sorted(WAYPOINTS))}")
    return WAYPOINTS[key]


class GpsProvider:
    def read(self):
        """Return (lat, lng) or None when there is no fix."""
        raise NotImplementedError


class FixedGPS(GpsProvider):
    def __init__(self, lat: float, lng: float):
        self.pos = (lat, lng)

    def read(self):
        return self.pos


class SimulatedGPS(GpsProvider):
    """Walks a route of named waypoints; `dwell` extra ticks are spent at each waypoint
    (so the device visibly sits in a zone) and `steps` ticks are spent between waypoints."""

    def __init__(self, route: list[str], steps: int = 10, dwell: int = 4, loop: bool = True):
        self.names = [r.strip().lower() for r in route]
        unknown = [n for n in self.names if n not in WAYPOINTS]
        if unknown:
            raise ValueError(f"Unknown waypoint(s) {unknown}. Known: {sorted(WAYPOINTS)}")
        self.path: list[tuple[float, float]] = []
        self.waypoint_index: dict[str, int] = {}
        for i, name in enumerate(self.names):
            lat, lng = WAYPOINTS[name]
            self.waypoint_index.setdefault(name, len(self.path))
            self.path.extend([(lat, lng)] * max(dwell, 1))
            if i + 1 < len(self.names) or loop:
                nlat, nlng = WAYPOINTS[self.names[(i + 1) % len(self.names)]]
                for s in range(1, steps):
                    t = s / steps
                    self.path.append((lat + (nlat - lat) * t, lng + (nlng - lng) * t))
        self.route_path = list(self.path)      # kept so a jump to an off-route place can be undone by jumping back
        self.i = 0
        self.loop = loop
        self.moving = len(self.path) > 1
        self.lock = threading.Lock()

    def read(self):
        with self.lock:
            pos = self.path[self.i]
            if self.moving:
                self.i += 1
                if self.i >= len(self.path):
                    self.i = 0 if self.loop else len(self.path) - 1
                    if not self.loop:
                        self.moving = False
            return pos

    def goto(self, name: str) -> bool:
        name = name.lower()
        with self.lock:
            if name in self.waypoint_index:
                self.path = list(self.route_path)
                self.i = self.waypoint_index[name]
            elif name in WAYPOINTS:
                self.path = [WAYPOINTS[name]]
                self.i = 0
            else:
                return False
            self.moving = False  # manual override; resume with set_moving(True)
            return True

    def set_moving(self, moving: bool) -> None:
        with self.lock:
            self.moving = moving


class GpsdGPS(GpsProvider):
    """Real GPS via gpsd (Raspberry Pi + USB/serial receiver). Requires `pip install gps3`."""

    def __init__(self):
        from gps3.agps3threaded import AGPS3mechanism

        self.agps = AGPS3mechanism()
        self.agps.stream_data()
        self.agps.run_thread()

    def read(self):
        lat, lng = self.agps.data_stream.lat, self.agps.data_stream.lon
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            return lat, lng
        return None
