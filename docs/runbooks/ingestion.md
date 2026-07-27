# Runbook d'ingestio

## NASA FIRMS

Prerequisit:

- obtenir `FIRMS_MAP_KEY` a https://firms.modaps.eosdis.nasa.gov/api/map_key
- configurar-lo a `.env` com `FIRMS_MAP_KEY`
- canviar `INTERNAL_API_TOKEN` a `.env` abans de compartir entorn

## Execucio manual

Amb Docker arrencat:

```powershell
$headers = @{ "x-internal-token" = "change-me-local-internal-token" }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/firms/run -Headers $headers
```

Consultar estat:

```powershell
$headers = @{ "x-internal-token" = "change-me-local-internal-token" }
Invoke-RestMethod -Uri http://localhost:8000/internal/ingestion/firms/status -Headers $headers
```

## Reprocessament

El raw CSV queda a object storage `raw-ingestion/firms/...`.

```powershell
$headers = @{ "x-internal-token" = "change-me-local-internal-token" }
$body = @{ raw_csv = Get-Content .\apps\api\tests\fixtures\firms_viirs_sample.csv -Raw } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/firms/reprocess -Headers $headers -Body $body -ContentType "application/json"
```

## Programacio

`worker-beat` programa:

- `ingestion.run_firms` cada 15 minuts.
- `ingestion.run_aemet` cada 60 minuts.
- `ingestion.run_ign_transport` cada dia.
- `ingestion.run_osm_roads` cada dia.
- `ingestion.run_datex_traffic` cada 5 minuts.
- `ingestion.run_proteccio_civil_plans` cada 10 minuts.

Si falta una credencial, la tasca registra una fallada i no inserta registres.

## AEMET

Prerequisit:

- obtenir `AEMET_API_KEY` a https://opendata.aemet.es/
- configurar `AEMET_FORECAST_MUNICIPALITIES`
- configurar coordenades a `AEMET_FORECAST_LOCATIONS_JSON`

Execucio:

```powershell
$token = ((Get-Content .env | Where-Object { $_ -match '^INTERNAL_API_TOKEN=' }) -split '=',2)[1]
$headers = @{ "x-internal-token" = $token }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/aemet/run -Headers $headers
```

## IGN/CNIG

Execucio:

```powershell
$token = ((Get-Content .env | Where-Object { $_ -match '^INTERNAL_API_TOKEN=' }) -split '=',2)[1]
$headers = @{ "x-internal-token" = $token }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/ign/transport/run -Headers $headers
```

## OpenStreetMap

Execucio per area petita:

```powershell
$token = ((Get-Content .env | Where-Object { $_ -match '^INTERNAL_API_TOKEN=' }) -split '=',2)[1]
$headers = @{ "x-internal-token" = $token }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/osm/roads/run -Headers $headers
```

No utilitzis Overpass per importacions massives. Per Espanya completa cal extracte Geofabrik i pipeline dedicat.

## NAP DATEX II transit/restriccions

Font principal estatal per carreteres i restriccions viaries. Combina:

- DGT DATEX2 v3.7 per tota la xarxa estatal excepte Catalunya i Pais Basc.
- SCT DATEX2 per Catalunya.
- DT-GV DATEX2 per Pais Basc.

Execucio:

```powershell
$token = ((Get-Content .env | Where-Object { $_ -match '^INTERNAL_API_TOKEN=' }) -split '=',2)[1]
$headers = @{ "x-internal-token" = $token }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/datex/traffic/run -Headers $headers
```

El connector desa `RestrictionZone`, `RoadSegment` i `RoadIncident`, classificant les afectacions en:

- `CARRETERAS CORTADAS`
- `TRÁFICO LENTO`
- `CIRCULACIÓN RESTRINGIDA`
- `DESVÍOS Y EMBOLSAMIENTOS`
- `OTRAS AFECCIONES`

Quan DATEX nomes publica punt inicial/final, el connector intenta reconstruir el tracat sobre la xarxa `RoadSegment` existent per `road_ref`. Si no hi ha xarxa compatible, guarda la geometria DATEX original i marca `geometry_strategy=nap_datex_coordinates` al metadata.

La xarxa viaria estatal local s'inicialitza amb `npm run roads:import`. El resolutor prioritza IGR-RT/PostGIS (`geometry_strategy=cnig_local_road_network`) i nomes consulta serveis externs quan la carretera no existeix localment.

## NAP Mapa de Trafico

`/internal/ingestion/dgt/etraffic/run` consumeix les dades de la web oficial del dataset NAP Mapa de Trafico.

```powershell
$token = ((Get-Content .env | Where-Object { $_ -match '^INTERNAL_API_TOKEN=' }) -split '=',2)[1]
$headers = @{ "x-internal-token" = $token }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/dgt/etraffic/run -Headers $headers
```

## NAP Mapa de Movilidad

Configurat com a recurs web a `MOBILITY_MAP_URL=http://mapamovilidad.dgt.es/`. No hi ha connector d'ingestio activat fins tenir endpoint estable amb dades descarregables.

## Proteccio Civil / CECAT

Font publica:

- Plans de Proteccio Civil en fase de prealerta, alerta o emergencia: `https://analisi.transparenciacatalunya.cat/api/v3/views/wj9c-j6vf/query.json?accessType=DOWNLOAD`

Execucio:

```powershell
$token = ((Get-Content .env | Where-Object { $_ -match '^INTERNAL_API_TOKEN=' }) -split '=',2)[1]
$headers = @{ "x-internal-token" = $token }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/proteccio-civil/plans/run -Headers $headers
```

Aquest connector guarda avisos oficials. No genera zones d'evacuacio ni geometries de restriccio si la font no les publica.

## Errors habituals

- `FIRMS_MAP_KEY is required`: falta configurar clau.
- `timeout`: revisar connectivitat i reintentar.
- `missing required columns`: resposta inesperada; el raw es guarda a dead-letter.
- duplicats al payload o DB: el connector els compta i no reinserta.
