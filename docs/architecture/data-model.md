# Model de dades

PostgreSQL/PostGIS conserva dades originals, versions, procedencia i relacions derivades. Geometria interna: SRID 4326; `original_crs` preserva el sistema de la font.

## Nucli

- `DataSource`: font, autoritat, tipus i metadades.
- `DataIngestionRun`: estat, comptadors, errors i referencia al raw.
- `Incident` i `IncidentVersion`: identitat canonica i historial.
- `FireDetection`: deteccio FIRMS puntual i dades del sensor.
- `FirePerimeter`: poligon EFFIS i tots els atributs del shapefile.
- `OfficialNotice`, `EvacuationZone`, `RestrictionZone` i `EsAlertRecord`.
- `RoadSegment` i `RoadIncident`.
- `EmergencyPublication`: evidencia OSINT, text original, classificacio, ubicacions i revisio.
- `WeatherObservation`, `WeatherForecast`, `RiskForecast` i `SmokeForecast`.

## Relacions d'incendi

Un `Incident` pot agregar diversos perimetres EFFIS, deteccions FIRMS, avisos i publicacions. `original_metadata` conserva membres agrupats, area total, hashtags, municipis, evidencies d'extincio i motius d'associacio. La relacio es reversible i no elimina la font original.

`EmergencyPublication` conserva:

- tipus d'esdeveniment i risc;
- autoritat, URL i tipus de font;
- publicacio, inici i final de vigencia;
- instruccions i text literal disponible;
- estat ES-Alert;
- toponims, geometria oficial, metode d'inferencia i precisio;
- confiança i estat de revisio humana.

## Camps transversals

`source_id`, `external_id`, `provenance`, `observed_at`, `published_at`, `received_at`, `expires_at`, `verification_status`, `confidence`, `version`, `original_metadata`, `deduplication_hash`, `created_at`, `updated_at` i `deleted_at`.

## Integritat

- Procedencia limitada a `official`, `observed`, `estimated` o `unverified`.
- Confiança entre 0 i 1.
- Prediccions de risc i fum mai tenen procedencia oficial.
- Un poligon EFFIS antic no confirma per si sol l'extincio.
- Una zona administrativa utilitza el seu limit oficial; no es dibuixen poligons artificials si nomes es coneix el toponim.
- Soft delete i versions eviten perdre historial.

## Indexs

- GiST sobre geometries.
- Temps d'observacio, publicacio, recepcio i expiracio.
- Procedencia, estat i font.
- Hash de deduplicacio.
- Claus d'incident, revisio OSINT i identificadors externs.
