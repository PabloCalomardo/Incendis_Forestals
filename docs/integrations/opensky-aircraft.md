# OpenSky aeronaus d'emergencia

## Objectiu

Mostrar al mapa Civil les aeronaus publiques o contractades per rescat, extincio, policia, vigilancia ambiental i serveis d'emergencia quan estan volant.

## Fonts live

- Endpoint principal: `GET https://opensky-network.org/api/states/all`
- Endpoints complementaris:
  - `GET https://api.airplanes.live/v2/hex/[icao24]`
  - `GET https://api.airplanes.live/v2/reg/[reg]`
- Filtre: bbox EPSG:4326, per defecte Espanya incloent Canaries.
- Actualitzacio UI: cada 20 segons quan la capa esta activa.
- Dades mostrades: posicio, callsign/vol, altitud, velocitat, rumb, squawk i hora d'ultima recepcio.

OpenSky no dona registre public complet de matricules ni rutes comercials. El portal mostra el callsign ADS-B com a vol actiu i enllaca el perfil/track OpenSky quan hi ha `icao24`. Airplanes.live s'usa com a complement quan OpenSky no retorna l'aeronau concreta o quan nomes hi ha posicio aproximada `rr_lat`/`rr_lon`.

## Dataset OSINT

El fitxer `apps/api/app/data/emergency_aircraft_spain.json` deriva de `dataset_aeronaus_emergencies_espanya_exhaustiu_public.xlsx`.

Matching:

- OpenSky: `icao24` exacte quan el dataset el te.
- OpenSky: fallback per `callsign` normalitzat igual a matricula/identificador.
- Airplanes.live: `icao24` exacte via `/hex`.
- Airplanes.live: matricula exacta via `/reg`.

El dataset actual conte 122 registres OSINT i 61 `icao24` completats. Els `icao24` s'han enriquit manualment a partir de fonts publiques com OpenSky aircraft database, Flightradar24, ADS-B.NL, Live Mobile Mode-S, Planespotters i fonts d'operadors. Les entrades mantenen `icao24_source_url`, `icao24_verified_at`, `icao24_review_status` i notes de revisio quan hi ha evidencia.

Quan el matching no es fa per `icao24`, l'element porta l'advertiment `matched_by_callsign_or_registration` o `matched_by_registration`.

## API i render

`GET /civil/aircraft/live` retorna una `FeatureCollection` GeoJSON amb nomes aeronaus del dataset que estan actives en fonts ADS-B. La resposta inclou metadades `dataset_aircraft_count`, `matched_aircraft_count`, `observed_at`, `bbox` i la font agregada.

El frontend consulta aquesta capa sense limitar-la al viewport visible: demana el bbox operatiu per defecte d'Espanya per evitar perdre aeronaus quan l'usuari mira una zona concreta del mapa. El refresc de la capa no mostra el popup central `Carregant dades al mapa`; a la capcalera superior es mostra `Refrescant Aeronaus`.

Les capes `aircraft-point`, `aircraft-heading` i `aircraft-label` es mouen explicitament al final de l'ordre de render de MapLibre. Aixo garanteix que les aeronaus quedin visualment per sobre de restriccions de carreteres, perimetres i deteccions.

## Limitacions

- Una aeronau visible a Flightradar24 pot no apareixer a OpenSky o Airplanes.live per cobertura, retard, bloqueig, filtratge, MLAT o disponibilitat del feed public.
- Si no hi ha coordenades `lat`/`lon`, Airplanes.live pot aportar `rr_lat`/`rr_lon`; aquestes posicions es mostren com aproximades amb `position_precision=range_ring`.
- Els callsigns poden canviar durant l'operatiu i no sempre coincideixen amb la matricula.
- El dataset no identifica aeronaus privades o militars no relacionades amb serveis d'emergencia.
