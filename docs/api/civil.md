# Civil API

The Civil API exposes public wildfire information for the Civil portal. It is intentionally simpler than internal
operational APIs: every response keeps traceability, but it never returns raw connector payloads, credentials, model
execution parameters, resource locations, audit data, deduplication hashes, or other internal fields.

Base prefix:

```text
/civil
```

## Endpoints

```text
GET /civil/incidents
GET /civil/incidents/{incident_id}
GET /civil/incidents/{incident_id}/timeline
GET /civil/detections
GET /civil/perimeters
GET /civil/evacuations
GET /civil/restrictions
GET /civil/roads
GET /civil/roads/incidents
GET /civil/notices
GET /civil/risk
GET /civil/smoke
GET /civil/search/geographic
GET /civil/search/municipality?municipality=...
```

`GET /civil/roads` continua disponible com a contracte public de xarxa viaria, pero el Dashboard Civil actual no descarrega aquesta capa de context. Les afectacions visibles provenen de `GET /civil/restrictions` i es presenten sota la categoria `Restriccions a Carreteres`.

## Common Filters

All list endpoints accept:

```text
bbox=west,south,east,north
latitude=40.4&longitude=-3.7&radius_meters=10000
municipality=Madrid
observed_from=2026-07-26T00:00:00Z
observed_to=2026-07-26T23:59:59Z
status=active
source=NASA
min_confidence=0.6
limit=50
offset=0
sort=updated_desc|observed_desc|confidence_desc
format=json|geojson
only_current=true
```

Spatial filters use PostGIS functions (`ST_Intersects`, `ST_DWithin`) over geometry columns prepared for GiST indexes.

## Traceability

Every public item includes:

```json
{
  "id": "7ee68e5b-5c4d-4c7c-8f1b-bf2d84f4ffbb",
  "data_type": "fire_detection",
  "source": {
    "name": "NASA FIRMS",
    "authority": "NASA",
    "url": "https://firms.modaps.eosdis.nasa.gov",
    "attribution": "NASA FIRMS"
  },
  "observed_at": "2026-07-26T12:00:00Z",
  "updated_at": "2026-07-26T12:05:00Z",
  "age_seconds": 300,
  "confidence": 0.76,
  "confidence_category": "medium",
  "provenance": "observed",
  "is_current": true,
  "warnings": [],
  "properties": {
    "sensor": "VIIRS",
    "satellite": "NOAA-20",
    "frp_mw": 9.2
  }
}
```

Old estimated records are not presented as current. When an estimated record is older than the public freshness window,
the response sets `is_current=false` and adds `old_estimate_not_current` to `warnings`; list endpoints hide those stale
estimates by default with `only_current=true`.

## GeoJSON

Use `format=geojson` to receive a `FeatureCollection`. Public traceability is preserved inside each feature's
`properties` object.

## Caching, ETags, Rate Limits

Responses include:

```text
ETag: ...
Cache-Control: public, max-age=30
x-correlation-id: ...
```

The API uses Redis for short public response caching and per-client rate limiting. If Redis is unavailable, requests are
still served without cache instead of exposing an internal failure.

## Error Shape

Errors use the shared predictable shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "correlation_id": "..."
  }
}
```
