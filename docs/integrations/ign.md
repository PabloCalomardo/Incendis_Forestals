# IGN/CNIG

## Estat

Connector implementat a `app.ingestion.ign.IgnTransportConnector`.

## Font oficial

CNIG publica serveis de descarrega interoperables, incloent OGC API, WFS, WCS i ATOM:

- https://centrodedescargas.cnig.es/CentroDescargas/servicios-web

## Producte local principal

- IGR-RT 2026 `España por modos`, capa viaria de carreteres.
- `rt_tramo_vial` s'importa com `cnig_road_segments`.
- `rt_ppkk_p` s'importa com `cnig_road_kilometers`.
- El GeoPackage queda a `data/cnig/`, fora de Git.

Importacio o actualitzacio:

```powershell
npm run roads:import
```

La primera execucio descarrega aproximadament 500 MB comprimits i extreu un GeoPackage d'aproximadament 1,5 GB. Les execucions seguents reutilitzen el fitxer local.

## Producte complementari

- Xarxa de transport via OGC API Features, col.leccio `roadlink`.
- Resposta esperada en GeoJSON.
- Importacio limitada per `bbox` i `limit`.

## Configuracio

- `IGN_WFS_BASE_URL` (base OGC API Features)
- `IGN_TRANSPORT_TYPENAME` (col.leccio, per defecte `roadlink`)
- `IGN_AREA_BBOX`
- `IGN_FEATURE_LIMIT`
- `IGN_TIMEOUT_SECONDS`
- `IGN_MAX_RETRIES`

## Cobertura preparada

- Xarxa de carreteres oficial a `RoadSegment`.
- Metadades originals preservades.
- CRS intern `EPSG:4326`.
- Lmits administratius, MDT i cartografia base documentats com a fonts CNIG preparades, pero no carregades massivament en aquesta fase.

## Resolucio DATEX local

Les restriccions amb `road_ref` es resolen primer sobre `cnig_road_segments`. Quan DATEX aporta PK, `cnig_road_kilometers` fixa els extrems oficials. L'API construeix un graf amb els trams del mateix nom de carretera i calcula el recorregut entre aquests extrems sense poder saltar a una via veina. Els trams es carreguen una sola vegada per carretera i ingestio. DGT PK, Overpass i OSRM queden com a fallback per carreteres absents del producte CNIG.

## Limitacions

- La primera importacio necessita diversos GB lliures entre ZIP, GeoPackage i taules PostGIS.
- WCS/ATOM per elevacio i cartografia base requereixen flux especific de fitxers en fase GIS.
- Els noms de col.leccions poden canviar segons servei; `IGN_TRANSPORT_TYPENAME` queda configurable.
