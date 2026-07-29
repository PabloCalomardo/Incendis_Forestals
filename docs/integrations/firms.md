# NASA FIRMS

## Estat

Connector implementat a `app.ingestion.firms.FirmsConnector`.

## Font oficial

NASA FIRMS API Area CSV:

- endpoint: `/api/area/csv/[MAP_KEY]/[SOURCE]/[AREA_COORDINATES]/[DAY_RANGE]`
- `DAY_RANGE`: 1..5
- `AREA_COORDINATES`: `west,south,east,north`
- requereix `MAP_KEY`

Fonts consultades:

- https://firms.modaps.eosdis.nasa.gov/api/area/
- https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html

## Configuracio

- `FIRMS_MAP_KEY`
- `FIRMS_SOURCE` (font unica o llista separada per comes)
- `FIRMS_AREA_SPAIN`
- `FIRMS_DAY_RANGE`
- `FIRMS_BASE_URL`
- `FIRMS_TIMEOUT_SECONDS`
- `FIRMS_MAX_RETRIES`

## Abast inicial

- area limitada a Espanya amb bounding box;
- fonts per defecte `VIIRS_NOAA20_NRT`, `VIIRS_SNPP_NRT`, `VIIRS_NOAA21_NRT` i `MODIS_NRT`;
- cada peticio NASA FIRMS Area CSV nomes accepta una font; el connector fa una peticio per font configurada i fusiona
  els CSV en un payload unic amb la columna interna `firms_source`;
- resposta original CSV desada a object storage;
- normalitzacio a `FireDetection`;
- deduplicacio per hash estable que inclou `firms_source`, satel.lit, instrument, coordenades, data i hora;
- registre a `DataIngestionRun`;
- endpoints interns protegits:
  - `POST /internal/ingestion/firms/run`
  - `POST /internal/ingestion/firms/reprocess`
  - `GET /internal/ingestion/firms/status`
- tasca Celery beat `ingestion.run_firms` cada 15 minuts.

## Camps conservats

- `latitude`
- `longitude`
- `acq_date`
- `acq_time`
- `satellite`
- `instrument`
- `confidence`
- `frp`
- fila original completa a `original_metadata`

## Operacio

- L'API Area CSV no exposa paginacio explicita; el contracte queda preparat per connectors paginats futurs.
- Les respostes invalides es desen a `firms/dead-letter/...` i la run queda `failed`.
- El reprocessament accepta el CSV original conservat i aplica la mateixa validacio, normalitzacio i deduplicacio.
- La font `NASA FIRMS` conserva a `source_metadata.sources` la llista de productes actius.
- Les URLs FIRMS inclouen la `MAP_KEY`; els logs `httpx/httpcore` estan a nivell `WARNING` per no escriure-la en
  logs normals.

## Limitacions

- Sense `FIRMS_MAP_KEY`, el connector no s'executa.
- Si `FIRMS_SOURCE` nomes inclou `VIIRS_NOAA20_NRT`, la plataforma queda per sota del visor FIRMS oficial quan aquest mostra diverses capes.
- La interpretacio de confianca FIRMS pot ser lletra (`l`, `n`, `h`) o numerica segons producte.
- La UI mostra per defecte totes les deteccions de l'ultim dia disponible i agrupa l'historic per dia al slider temporal.
- La capa `Punts FIRMS` esta apagada inicialment; grups i deteccions associades continuen disponibles.
- Les deteccions proxim es vinculen a incidents EFFIS canonics, pero no s'eliminen ni s'oculten quan queden dins d'un poligon.
- Per Espanya peninsular/Balears el bbox operatiu compartit amb el frontend es `-10.0,35.5,4.5,44.5`.
