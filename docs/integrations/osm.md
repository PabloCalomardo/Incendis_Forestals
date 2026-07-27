# OpenStreetMap

## Estat

Connector implementat a `app.ingestion.osm.OsmRoadConnector`.

## Estrategia

- Per importacions petites i reproduibles per area: Overpass amb `bbox`, timeout i limit. La bbox per defecte es petita expressament per no fer carrega massiva.
- Per importacions grans: extractes Geofabrik `.osm.pbf` o `.gpkg.zip`; no s'ha d'usar l'API publica principal d'OSM per lectura massiva.

Fonts:

- https://operations.osmfoundation.org/policies/api/
- https://www.geofabrik.de/data/download.html
- https://download.geofabrik.de/europe/spain.html

## Tags conservats

- `highway`
- `surface`
- `width`
- `access`
- `maxweight`
- `incline`
- `tracktype`
- `smoothness`

Els tags complets es conserven dins `original_metadata.all_tags`.

## Configuracio

- `OSM_OVERPASS_URL`
- `OSM_AREA_BBOX`
- `OSM_TIMEOUT_SECONDS`
- `OSM_MAX_RETRIES`
- `OSM_FEATURE_LIMIT`

## Limitacions

- Overpass no substitueix una importacio nacional completa.
- El connector aplica `User-Agent` identificable.
- Les dades OSM tenen llicencia ODbL 1.0 i requereixen atribucio.
