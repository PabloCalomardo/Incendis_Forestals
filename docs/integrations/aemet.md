# AEMET OpenData

## Estat

Connector implementat a `app.ingestion.aemet.AemetConnector`.

## Font oficial

AEMET OpenData publica una API REST amb especificacio OpenAPI a:

- https://opendata.aemet.es/dist/
- https://opendata.aemet.es/AEMET_OpenData_specification.json

La resposta d'AEMET funciona amb doble crida: la primera resposta inclou una URL `datos`; la segona descarrega el dataset real.

## Configuracio

- `AEMET_API_KEY`
- `AEMET_BASE_URL`
- `AEMET_FORECAST_MUNICIPALITIES`
- `AEMET_FORECAST_LOCATIONS_JSON`
- `AEMET_TIMEOUT_SECONDS`
- `AEMET_MAX_RETRIES`

## Productes inicials

- Observacions convencionals: `/api/observacion/convencional/todas`
- Prediccio horaria municipal: `/api/prediccion/especifica/municipio/horaria/{municipio}`

## Normalitzacio

- Observacions a `WeatherObservation`.
- Prediccions a `WeatherForecast`.
- Coordenades AEMET en decimal o format sexagesimal amb hemisferi.
- Vent, direccio, ratxes, temperatura, humitat i precipitacio a unitats operatives.
- Raw complet a object storage i `original_metadata`.

## Limitacions

- Cal clau `AEMET_API_KEY`.
- La prediccio municipal requereix coordenades configurades a `AEMET_FORECAST_LOCATIONS_JSON`; l'endpoint de prediccio no dona una geometria directa.
- La qualitat i procedencia queden registrades; els avisos CAP estatals es documenten a `proteccio-civil.md`.
