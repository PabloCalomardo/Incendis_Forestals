# Runbook d'ingestio

## Acces intern

Tots els endpoints requereixen `X-Internal-Token`:

```powershell
$token = ((Get-Content .env | Where-Object { $_ -match '^INTERNAL_API_TOKEN=' }) -split '=',2)[1]
$headers = @{ 'x-internal-token' = $token }
```

No publicar `.env` ni el token.

## Tasques programades

| Tasca | Freqüencia |
| --- | ---: |
| `ingestion.run_firms` | 15 min |
| `ingestion.run_emergency_osint` | 5 min |
| `ingestion.run_effis_burnt_areas` | 24 h |
| `ingestion.run_aemet` | 60 min |
| `ingestion.run_aemet_alerts` | 10 min |
| `ingestion.run_ign_transport` | 24 h |
| `ingestion.run_osm_roads` | 24 h |
| `ingestion.run_datex_traffic` | 5 min |
| `ingestion.enrich_datex_roads` | 1 min |
| `ingestion.run_proteccio_civil_plans` | 10 min |

## Execucio manual

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/firms/run -Headers $headers
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/effis/burnt-areas/run -Headers $headers
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/aemet/run -Headers $headers
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/aemet/alerts/run -Headers $headers
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/ign/transport/run -Headers $headers
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/osm/roads/run -Headers $headers
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/datex/traffic/run -Headers $headers
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/datex/traffic/enrich -Headers $headers
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/dgt/etraffic/run -Headers $headers
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/proteccio-civil/plans/run -Headers $headers
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/osint/run -Headers $headers
```

Estat de qualsevol connector:

```powershell
Invoke-RestMethod -Uri http://localhost:8000/internal/ingestion/firms/status -Headers $headers
Invoke-RestMethod -Uri http://localhost:8000/internal/ingestion/datex_traffic/status -Headers $headers
Invoke-RestMethod -Uri http://localhost:8000/internal/ingestion/emergency_osint/status -Headers $headers
```

## FIRMS

Requereix `FIRMS_MAP_KEY`. El CSV original queda a MinIO i les respostes invalides a dead-letter. Reprocessament:

```powershell
$body = @{ raw_csv = Get-Content .\apps\api\tests\fixtures\firms_viirs_sample.csv -Raw } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/ingestion/firms/reprocess -Headers $headers -Body $body -ContentType 'application/json'
```

## Carreteres

DATEX combina DGT, SCT i DT-GV. La xarxa oficial local s'importa amb:

```powershell
npm run roads:import
```

`datex/traffic/enrich` repara geometries de dos punts sobre CNIG. El resolutor usa PK/graf i despres `ST_LineMerge` + subseccio PostGIS, incloses taules sense clau primaria. Un lock consultiu evita reparar simultaniament la mateixa carretera. Comprovar `geometry_strategy` i el nombre de coordenades; `nap_datex_coordinates` indica fallback recte.

## OSINT i revisio

Nitter es la passarel.la automatica principal. X nomes s'activa amb `X_BEARER_TOKEN`; TwitterViewer es per comprovacio manual. Fonts bloquejades poden deixar la run `partial` sense invalidar dades anteriors.

```text
GET   /internal/ingestion/osint/review
PATCH /internal/ingestion/osint/review/{publication_id}
POST  /internal/ingestion/osint/publications
```

Revisar especialment toponims ambigus, testimonis individuals i estats ES-Alert no oficials.

## ES-Alert

`POST /internal/ingestion/es-alert/sync` sincronitza un proveidor autenticat. No hi ha feed public complet. Un snapshot buit requereix confirmacio explicita i els simulacres no es publiquen com alertes reals.

## Regla de seguretat

Mai desactivar ni substituir dades bones quan una run pateix timeout, HTTP incomplet, parsing, `DeadlockDetectedError`, cancel.lacio, resposta parcial o buit anormal. La run ha de quedar `failed`/`partial`, conservar el raw disponible i permetre reprocessament.

## Errors habituals

- `FIRMS_MAP_KEY is required`: falta clau NASA.
- `AEMET_API_KEY is required`: falta clau OpenData.
- `missing required columns`: contracte extern canviat; revisar dead-letter.
- `partial`: una o mes fonts han fallat; consultar errors abans de repetir.
- geometria de 2 punts: executar enriquiment i validar que la carretera existeix a CNIG.
- deadlock/lock ocupat: no forçar snapshot; esperar el següent cicle o reintentar manualment.
