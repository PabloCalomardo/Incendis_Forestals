from __future__ import annotations

import json
import math
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


def geojson_geometry_to_polygon_wkt(geometry: dict[str, Any]) -> str | None:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon" and isinstance(coordinates, list | tuple):
        polygon = _polygon_coordinates_wkt(coordinates)
        return f"POLYGON({polygon})" if polygon else None
    if geometry_type == "MultiPolygon" and isinstance(coordinates, list | tuple):
        polygons = [
            _polygon_coordinates_wkt(polygon)
            for polygon in coordinates
            if isinstance(polygon, list | tuple)
        ]
        valid = [polygon for polygon in polygons if polygon]
        return f"MULTIPOLYGON({', '.join(f'({polygon})' for polygon in valid)})" if valid else None
    return None


def _polygon_coordinates_wkt(coordinates: list[Any] | tuple[Any, ...]) -> str | None:
    rings: list[str] = []
    for raw_ring in coordinates:
        if not isinstance(raw_ring, list | tuple):
            continue
        points: list[tuple[float, float]] = []
        for coordinate in raw_ring:
            if not isinstance(coordinate, list | tuple) or len(coordinate) < 2:
                continue
            try:
                longitude = float(coordinate[0])
                latitude = float(coordinate[1])
            except (TypeError, ValueError):
                continue
            if math.isfinite(longitude) and math.isfinite(latitude):
                points.append((longitude, latitude))
        if len(points) < 3:
            continue
        if points[0] != points[-1]:
            points.append(points[0])
        if len(points) >= 4:
            rings.append(f"({', '.join(f'{longitude} {latitude}' for longitude, latitude in points)})")
    return ", ".join(rings) if rings else None


def geometry_hash_payload(geometry: dict[str, Any]) -> str:
    return json.dumps(geometry, sort_keys=True, separators=(",", ":"))


def bbox_to_overpass_tuple(bbox: str) -> str:
    west, south, east, north = (part.strip() for part in bbox.split(","))
    return f"{south},{west},{north},{east}"
