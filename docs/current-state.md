# Estat de continuacio

Actualitzat: 29-07-2026.

Aquest document es la font canonica per reprendre el desenvolupament. L'especificacio de producte continua a
`EspecificacioProjecte.md`; `PlaDimplementacio.md` i les fases antigues son registre historic.

## Objectiu actiu

Completar i estabilitzar el Dashboard Civil public abans de reprendre el portal professional. L'aplicacio integra
incendis, deteccions satel·litaries, perimetres cremats, avisos d'emergencia i restriccions viaries amb procedencia i
confiança visibles. Tambe mostra aeronaus publiques o contractades d'emergencia quan estan volant i apareixen en fonts
ADS-B publiques.

## Pila executable

- Next.js 15, React 19, TypeScript, Tailwind, TanStack Query, Zustand i MapLibre GL JS.
- FastAPI, SQLAlchemy asincron, Alembic, PostgreSQL 16 i PostGIS.
- Redis per cache, rate limiting, broker i resultats Celery.
- MinIO per originals i dead-letter.
- Workers Celery d'ingestio, geoespacial i prediccio; Celery Beat programa les ingestes.
- Docker Compose exposa frontend `3000` i API `8000`.

La migracio mes recent es `0004_emergency_osint.py`, que afegeix `emergency_publications` i permet incidents sense
geometria quan la font no dona una ubicacio oficial prou precisa.

## Dashboard Civil

- El mapa, capes, cerca municipal, incidents, avisos i cronologia formen una sola experiencia.
- La cerca municipal usa limits IGN i nomes centra el mapa; no filtra silenciosament les dades.
- El carregador inicial es un dialeg centrat sobre el mapa.
- `Incidents` i `Avisos i cronologia` son llistes independents, internes al mapa i amb scroll.
- `Capes` es a la part superior dreta amb marge respecte als controls `+` i `-` de MapLibre.
- La llegenda s'obre per defecte a baix a la dreta, es pot tancar i reobrir.
- El detall complet de l'incendi es mostra sota el mapa. El popup EFFIS nomes mostra inici, extincio confirmada,
  hashtags, resum curt i l'accio per anar al detall.
- Les publicacions X/Nitter independents es mostren en blau; un incendi canonic EFFIS conserva el color d'incendi.
- `Punts FIRMS` esta desactivat inicialment. Les arees FIRMS i la resta de capes continuen actives. El farciment FIRMS
  es pinta amb geometria visual unificada per evitar acumulacio de transparencia quan MODIS i VIIRS se solapen; els
  contadors de grups/sensors se separen lleument per llegibilitat.
- `Aeronaus` consulta OpenSky i Airplanes.live cada 20 segons quan la capa esta activa. Les aeronaus es dibuixen per
  sobre de restriccions, perimetres i deteccions.
- El refresc d'aeronaus no obre el popup central de carrega; la capcalera del mapa mostra `Refrescant Aeronaus`.
- Clicar una carretera o restriccio conserva la seva geometria i enfoca el tram. Un avis sense geometria ni `bbox`
  no modifica el zoom.
- El viewport es conserva a la URL sense provocar refetch de dades en cada moviment.

## Aeronaus d'emergencia

- `apps/api/app/data/emergency_aircraft_spain.json` conte el dataset OSINT local derivat del full public aportat.
- Estat actual: 122 aeronaus candidates i 61 `icao24` verificats o completats amb fonts publiques.
- `GET /civil/aircraft/live` creua el dataset amb OpenSky `/states/all` i Airplanes.live `/hex`/`/reg`.
- El matching prioritza `icao24`; si no existeix, prova callsign o matricula normalitzada i marca l'advertiment
  corresponent.
- Airplanes.live pot aportar `rr_lat`/`rr_lon`; aquestes posicions es publiquen com aproximades amb precisio
  `range_ring`.
- La capa pot ser buida encara que una aeronau surti a Flightradar24, per diferencies de cobertura o disponibilitat
  entre feeds ADS-B publics.

## FIRMS

- Connector real NASA FIRMS Area CSV amb `FIRMS_MAP_KEY`, originals, deduplicacio i dead-letter. `FIRMS_SOURCE`
  accepta llista separada per comes i ara cobreix `VIIRS_NOAA20_NRT`, `VIIRS_SNPP_NRT`, `VIIRS_NOAA21_NRT` i
  `MODIS_NRT`.
- La vista inicial mostra totes les deteccions de l'ultim dia disponible agrupades espacialment. El bbox civil/FIRMS
  per defecte es `-10.0,35.5,4.5,44.5`.
- La cronologia agrupa per dia, no per instant. El slider mostra simultaniament totes les deteccions del dia triat.
- Els punts originals es poden activar amb `Punts FIRMS`.
- Les deteccions no s'oculten quan coincideixen amb un perimetre EFFIS.
- Les deteccions relacionades amb un incendi canonic s'afegeixen al seu detall i metadades, pero la capa FIRMS es
  manté independent.
- La paginacio publica de deteccions usa ordre estable amb `id` com a desempat; el frontend permet fins a 10.000
  features FIRMS per carregar dies amb milers de deteccions.

## EFFIS i incidents canonics

- EFFIS Burnt Areas consumeix el SHAPEZIP WFS `ms:modis.ba.poly` i conserva tots els atributs DBF.
- Menys de 7 dies: `Incendis actuals`, visible per defecte.
- Entre 7 dies i 1 any: `Incendis d'aquest any`, desactivat per defecte.
- Mes d'1 any: `Historic d'incendis`, desactivat per defecte.
- Els poligons tenen contorn i farciment gris clicable d'area cremada.
- Poligons propers es poden fusionar en un incident canonic amb un llindar de veïnatge dependent de l'area, la
  compatibilitat temporal, hashtags i evidencies geografiques.
- La data d'extincio nomes es publica quan hi ha confirmacio explicita i l'actualitzacio no supera 3 dies.
- EFFIS descriu area cremada; no informa de dotacions ni tasques operatives d'extincio.

## OSINT d'emergencies

- Consulta fonts oficials i fiables configurades a `osint_sources.json` cada 5 minuts.
- Nitter es la passarel·la principal per perfils institucionals. X API v2 s'usa si hi ha `X_BEARER_TOKEN`.
- TwitterViewer queda limitat a revisio humana pels seus termes d'us.
- Classifica confinaments, evacuacions, plans, extincio i estats ES-Alert en catala, castella, eusquera i gallec.
- Conserva text original, URL, autoritat, dates, instruccions, ubicacions, geometria, precisio i confiança.
- Publicacions relacionades s'agrupen en incidents i cronologies. El detall canonic mostra totes les evidencies.
- La reconciliacio amb EFFIS combina hashtag, municipi exacte, geometria, distancia, temps i area. La provincia o la
  proximitat soles no son suficients.
- Els resums multiincident amb fletxes separen regió administrativa i municipi objectiu.
- Els noms municipals exactes i llargs tenen prioritat sobre suggeriments parcials. `Santa Coloma de Queralt` no es
  replica a altres `Santa Coloma`.
- `Agost` esta exclòs deliberadament del geocodificador i de la cerca municipal per evitar confondre el municipi amb
  el mes.
- Una font parcial o bloquejada no esborra dades bones anteriors.

## Avisos i ES-Alert

- Proteccio Civil/CECAT aporta plans actius de Catalunya.
- AEMET CAP aporta avisos oficials groc, taronja i vermell per tot Espanya.
- No existeix un registre public complet de totes les emissions ES-Alert.
- `POST /internal/ingestion/es-alert/sync` permet sincronitzar un proveidor autenticat. Els simulacres no es
  publiquen com alertes reals i un snapshot buit necessita confirmacio explicita.
- El monitor OSINT diferencia `announced`, `confirmed_sent`, `presumed_received`, `cancelled`, `test` i
  `not_applicable`.

## Transit i geometria viaria

- DATEX II combina DGT estatal, SCT i DT-GV cada 5 minuts.
- eTraffic aporta geometries detallades del Mapa de Trafico quan el servei respon.
- La ingesta de transit usa un advisory lock compartit. Una execucio amb deadlock o error sospitos no substitueix la
  darrera instantania bona.
- Incendi o obstacle ambiental es taronja; la resta d'afectacions es lila.
- DATEX sovint aporta nomes inici i final. El resolutor prioritza la xarxa oficial CNIG IGR-RT local:
  1. PK oficials quan existeixen.
  2. Graf de trams amb el mateix `road_ref`.
  3. Fusio PostGIS i `ST_LineSubstring` sobre la carretera oficial, inclosos casos sense PK.
  4. Geometria anterior, mostreig DGT PK, xarxa local, Overpass i OSRM.
- `ingestion.enrich_datex_roads` revisa cada minut les geometries de dos punts. El procés usa lock per evitar lots
  solapats i actualitza `RestrictionZone` i `RoadSegment` junts.
- Cas verificat: `TV-2042` va passar de 2 punts/3.963 m rectes a 963 punts/4.032 m sobre CNIG.
- Si cap font pot resoldre una carretera, es conserva `geometry_strategy=nap_datex_coordinates`; no s'afirma que la
  linia recta sigui el traçat oficial.

## API publica principal

- `GET /civil/incidents` i `GET /civil/incidents/{id}`.
- `GET /civil/detections` i `GET /civil/detections/timeline`.
- `GET /civil/perimeters?perimeter_period=current,year,historic`.
- `GET /civil/es-alerts`, `/civil/restrictions`, `/civil/notices`, `/civil/risk` i `/civil/smoke`.
- `GET /civil/municipalities/search?q=...`.
- `GET /civil/osint/incidents`, `/civil/osint/incidents/{id}`, `/civil/osint/review-queue` i
  `/civil/osint/x-accounts`.

Les llistes suporten GeoJSON, filtres espacials/temporals, paginacio, ETag, cache publica curta, rate limiting i
`x-correlation-id`.

## Programacio Celery

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

## Estat de validacio

Ultima validacio completa executada el 29-07-2026:

- API: Ruff correcte, mypy correcte, `82` proves superades.
- Frontend: ESLint sense errors, TypeScript correcte, `10` proves superades.
- Avisos coneguts: 3 warnings preexistents de hooks React i 3 warnings Pydantic sobre el prefix `model_`.
- Serveis verificats: API healthy i frontend HTTP 200.

## Limitacions i pendents

- Diversos portals oficials bloquegen robots, fallen intermitentment o canvien l'HTML; una ingesta OSINT pot acabar
  `partial`.
- Nitter no te SLA i pot fallar. X complet requereix credencial i pla d'API.
- ES-Alert no te feed public estatal complet; el registre actual es reconstruït i ha d'explicitar el grau d'evidencia.
- El mapa base public OSM es nomes per desenvolupament; produccio necessita proveidor o tiles propis.
- Queden geometries DATEX de dos punts en reparacio progressiva; no totes tenen correspondencia CNIG/OSM fiable.
- Falta una pantalla operativa de revisio humana completa, tot i que API i estat de revisio existeixen.
- Falta observabilitat de produccio, backups provats, CI/CD final, hardening i desplegament public.
- Portal Bomber, OIDC, routing d'emergencia i prediccions operatives continuen ajornats.

## Com reprendre

1. Executar `docker compose ps` i comprovar `GET /health` i `GET /ready`.
2. Revisar `git status`; el worktree conte la implementacio acumulada encara no consolidada en commit.
3. Executar proves frontend i API abans de continuar.
4. Consultar les darreres ingestes a `/internal/ingestion/{connector_name}/status`.
5. No esborrar dades bones per una resposta buida, timeout, deadlock o execucio parcial.
6. Actualitzar aquest document quan canviïn contractes, fonts, heuristiques o limitacions.
