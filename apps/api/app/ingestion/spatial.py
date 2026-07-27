from __future__ import annotations

import json
from typing import Any


def point_wkt(longitude: float, latitude: float) -> str:
    return f"POINT({longitude} {latitude})"


def linestring_wkt(coordinates: list[list[float]]) -> str | None:
    if len(coordinates) < 2:
        return None
    points = [f"{coord[0]} {coord[1]}" for coord in coordinates if len(coord) >= 2]
    if len(points) < 2:
        return None
    return f"LINESTRING({', '.join(points)})"


def geojson_geometry_to_linestring_wkt(geometry: dict[str, Any]) -> str | None:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "LineString" and isinstance(coordinates, list):
        return linestring_wkt(coordinates)
    if geometry_type == "MultiLineString" and isinstance(coordinates, list) and coordinates:
        first_line = coordinates[0]
        if isinstance(first_line, list):
            return linestring_wkt(first_line)
    return None


def geometry_hash_payload(geometry: dict[str, Any]) -> str:
    return json.dumps(geometry, sort_keys=True, separators=(",", ":"))


def bbox_to_overpass_tuple(bbox: str) -> str:
    west, south, east, north = (part.strip() for part in bbox.split(","))
    return f"{south},{west},{north},{east}"
