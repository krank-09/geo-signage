"""Predefined city boundaries (built by scripts/build_cities.py from OpenStreetMap; see DOCUMENTATION.md for attribution)."""
import json
from functools import lru_cache
from pathlib import Path

_FILE = Path(__file__).resolve().parent.parent / "data" / "cities.json"


@lru_cache(maxsize=1)
def _load() -> dict[str, dict]:
    return {c["id"]: c for c in json.loads(_FILE.read_text(encoding="utf-8"))}


def all_cities() -> list[dict]:
    return sorted(_load().values(), key=lambda c: c["name"])


def get_city(city_id: str) -> dict | None:
    return _load().get(city_id)


def summary(c: dict) -> dict:
    """Everything except the polygon (which can be fetched separately when a city is selected)."""
    return {k: c[k] for k in ("id", "name", "state", "center", "source", "area_km2") if k in c} | {"vertices": len(c["polygon"])}
