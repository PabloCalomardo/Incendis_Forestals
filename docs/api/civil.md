# API Civil

Base publica: `/civil`. No exposa payloads bruts, secrets, hashes interns ni dades d'auditoria.

## Endpoints

```text
GET /civil/incidents
GET /civil/incidents/{incident_id}
GET /civil/incidents/{incident_id}/timeline
GET /civil/detections
GET /civil/detections/timeline
GET /civil/perimeters
GET /civil/evacuations
GET /civil/es-alerts
GET /civil/restrictions
GET /civil/roads
GET /civil/roads/incidents
GET /civil/notices
GET /civil/risk
GET /civil/smoke
GET /civil/aircraft/live
GET /civil/search/geographic
GET /civil/search/municipality
GET /civil/municipalities/search
GET /civil/osint/incidents
GET /civil/osint/incidents/{incident_id}
GET /civil/osint/review-queue
GET /civil/osint/x-accounts
```

`/detections/timeline` retorna els dies FIRMS disponibles. `/perimeters` accepta `perimeter_period=current|year|historic`. `/roads` conserva el contracte de xarxa; el dashboard representa les afectacions amb `/restrictions`.

`/aircraft/live` retorna GeoJSON amb aeronaus publiques o contractades d'emergencia que estan volant i coincideixen amb el dataset OSINT local. Consulta OpenSky `/states/all` i Airplanes.live `/hex`/`/reg`; inclou `icao24`, callsign o vol ADS-B, matricula, operador, model, servei, altitud, velocitat, rumb, squawk, font live, precisio de posicio i enllacos de revisio quan existeixen.

## Filtres comuns

```text
bbox=west,south,east,north
latitude=40.4&longitude=-3.7&radius_meters=10000
municipality=Madrid
observed_from=2026-07-26T00:00:00Z
observed_to=2026-07-26T23:59:59Z
status=active
source=NASA
min_confidence=0.6
limit=50&offset=0
sort=updated_desc|observed_desc|confidence_desc
format=json|geojson
only_current=true
```

Els filtres espacials utilitzen PostGIS i indexs GiST.

`/aircraft/live` accepta `bbox=west,south,east,north`; si no s'indica, usa el bbox operatiu d'Espanya incloent Canaries. El frontend no passa el viewport actual a aquesta capa per no perdre aeronaus actives fora de la vista.

## Incidents canonics

Els incidents EFFIS poden agrupar diversos poligons proxims segons area, distancia, temps, municipis, hashtags i evidencies OSINT. El detall retorna totes les fonts i la cronologia associades. Una data final nomes es publica amb evidencia confirmada i una actualitzacio del poligon dins dels tres dies anteriors.

## OSINT i ES-Alert

`/civil/osint/incidents` retorna incidents actius o detectats dins la finestra `window_hours`, en JSON o GeoJSON. Cada resultat diferencia ES-Alert anunciat, enviat, presumptament rebut i no verificat; inclou risc, instruccions, ubicacions, durada, fonts i confiança.

`/civil/osint/review-queue` exposa casos dubtosos per revisio humana. `/civil/osint/x-accounts` documenta els perfils socials monitorats i la passarel.la utilitzada.

## Traçabilitat

Cada element public inclou font, autoritat, temps observat/actualitzat, edat, confiança, procedencia, vigencia, advertiments i propietats especifiques. Els registres estimats antics queden marcats amb `is_current=false` i s'oculten per defecte amb `only_current=true`.

## HTTP

```text
ETag: ...
Cache-Control: public, max-age=30
x-correlation-id: ...
```

Redis aporta cache i limit per client. Si Redis falla, l'API continua servint sense cache. Els errors mantenen `{ "error": { "code", "message", "correlation_id" } }`.
