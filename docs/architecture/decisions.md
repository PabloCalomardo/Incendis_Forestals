# Decisions d'arquitectura

Aquest registre conte decisions inicials i provisionals preses durant el Prompt inicial. Les decisions marcades com a provisionals s'han de revisar quan existeixi documentacio oficial, entorn de proves o implementacio real.

## ADR-001: Monorepo

Estat: provisional

Decisio:
El projecte s'organitzara com a monorepo amb `apps`, `workers`, `packages`, `infrastructure`, `docs` i `tests`.

Motiu:
L'especificacio demana frontend, API, workers, paquets compartits i infraestructura coordinats. Un monorepo facilita contractes compartits, CI i execucio local.

Conseqüencies:
Caldran eines comunes de lint, test i format per TypeScript i Python.

## ADR-002: Frontend amb Next.js App Router

Estat: acceptada per especificacio

Decisio:
El frontend utilitzara Next.js amb App Router, TypeScript estricte, Tailwind CSS, TanStack Query, Zustand per estat local i MapLibre GL JS.

Motiu:
Es requisit explicit de la Fase 1.

## ADR-003: Backend amb FastAPI i PostGIS

Estat: acceptada per especificacio

Decisio:
L'API utilitzara FastAPI, Pydantic Settings, SQLAlchemy asíncron, Alembic i PostgreSQL amb PostGIS.

Motiu:
Es requisit explicit i encaixa amb consultes espacials, traçabilitat i contractes OpenAPI.

## ADR-004: Workers amb Celery i Redis

Estat: acceptada per especificacio

Decisio:
Els workers inicials d'ingestio, geoprocessament i prediccio s'executaran amb Celery i Redis com a broker inicial.

Motiu:
Es requisit explicit de la Fase 1 i permet separar processos llargs de l'API.

## ADR-005: Object storage compatible S3

Estat: provisional

Decisio:
S'utilitzara MinIO en desenvolupament local com a emmagatzematge compatible S3 per respostes originals i artefactes.

Motiu:
L'especificacio demana MinIO o S3 compatible i prohibeix credencials reals al repositori.

## ADR-006: Motor de routing pendent

Estat: provisional

Decisio:
No es tria encara entre Valhalla, GraphHopper o OpenRouteService. La decisio queda diferida fins al desenvolupament del portal professional.

Motiu:
Cal triar-ne un i justificar-lo a partir de dades viaries i requisits operatius reals; encara no forma part del Dashboard Civil.

## ADR-007: Proveidor OIDC pendent

Estat: provisional

Decisio:
L'arquitectura reservara una capa OIDC configurable, pero no fixa proveidor.

Motiu:
L'especificacio exigeix OpenID Connect, pero no defineix proveidor, tenant, entorn de proves ni politiques corporatives.

## ADR-008: APIs externes no inventades

Estat: acceptada per especificacio

Decisio:
No es definiran formats, credencials ni camps concrets de fonts externes fins revisar documentacio oficial o fixtures representatives.

Motiu:
El pla prohibeix inventar APIs, credencials, formats o camps que no constin a l'especificacio o documentacio oficial.

## ADR-009: Separacio estricta de dades oficials i estimades

Estat: acceptada per especificacio

Decisio:
El domini i l'API mantindran tipus de procedencia `official`, `observed`, `estimated` i `unverified`.

Motiu:
Evita falsa precisio i protegeix el portal Civil de presentar inferencies com a ordres oficials.

## ADR-010: Geometria interna EPSG:4326

Estat: acceptada per implementacio Fase 2

Decisio:
Les geometries persistents utilitzen PostGIS amb SRID 4326 i cada registre conserva `original_crs`.

Motiu:
L'especificacio demana PostGIS i conservacio del sistema de coordenades original. EPSG:4326 simplifica API, GeoJSON i MapLibre.

## ADR-011: Prediccions mai oficials a nivell de base de dades

Estat: acceptada per implementacio Fase 2

Decisio:
`smoke_forecasts` i `risk_forecasts` incorporen restriccions per impedir `provenance = official`.

Motiu:
La regla "una prediccio no pot convertir-se automaticament en dada oficial" ha de quedar protegida al domini i a la base de dades.

## ADR-012: Soft delete generalitzat

Estat: provisional

Decisio:
Les entitats principals incorporen `deleted_at`.

Motiu:
Permet auditar, reprocessar i evitar perdua d'originals. La politica exacta de retencio queda pendent de fases de seguretat, backups i hardening.

## ADR-013: Prioritzar el producte Civil abans del professional

Estat: acceptada el 27-07-2026

Decisio:
El desenvolupament deixa de seguir fases numeriques. S'ha de completar i acceptar una versio publicable del Dashboard Civil abans de començar el Dashboard per a Professionals.

Motiu:
Permet estabilitzar primer la proposta publica, les dades, el rendiment i el desplegament, i evita repartir esforç entre dues experiencies amb requisits de seguretat molt diferents.

## ADR-014: Xarxa viaria estatal CNIG local

Estat: acceptada el 27-07-2026

Decisio:
La geometria DATEX es resol primer contra IGR-RT de CNIG importat localment a PostGIS. El graf per `road_ref` i PK es complementa amb una fusio/subseccio PostGIS que suporta taules sense clau primaria. Un lock consultiu coordina ingestio i reparacio. DGT PK, Overpass, OSRM i coordenades DATEX son fallbacks etiquetats.

Motiu:
Evita linies rectes, desviaments per carreteres veines, limits de peticions i processament manual carretera per carretera. Les dades pesades queden fora de Git i es carreguen amb `npm run roads:import`.

## ADR-015: El viewport no provoca recarrega de dades

Estat: acceptada el 27-07-2026

Decisio:
El pan i zoom de MapLibre actualitzen `lng`, `lat` i `z` amb `history.replaceState`, sense navegacio de Next.js. Les consultes de capes nomes depenen dels filtres de dades i tenen una finestra de cache de cinc minuts.

Motiu:
El viewport es estat de presentacio. Remuntar la ruta o tornar a consultar la mateixa cobertura en cada `moveend` empitjora latencia, carrega de l'API i experiencia d'usuari sense aportar dades noves.

## ADR-016: Incident d'incendi canonic centrat en EFFIS

Estat: acceptada el 29-07-2026

Decisio:
Els perimetres EFFIS recents son la identitat espacial principal. Poligons contemporanis es poden agrupar amb un llindar dependent de l'area i evidencies de hashtag, territori i temps. FIRMS i OSINT s'hi associen sense ocultar ni eliminar els originals.

Motiu:
Un incendi gran pot tenir diversos focus i poligons. Centralitzar-ne el detall evita duplicats, pero exigeix conservar la procedencia i rebutjar coincidencies febles.

## ADR-017: ES-Alert com a registre d'evidencies

Estat: acceptada el 29-07-2026

Decisio:
Sense feed public complet, el sistema diferencia `announced`, `confirmed_sent`, `presumed_received`, `cancelled`, `test` i no verificat. Comunicacions oficials tenen prioritat; casos ambigus entren a revisio humana.

Motiu:
Una publicacio individual o una recepcio percebuda no demostren un enviament oficial.

## ADR-018: Instantania bona protegida

Estat: acceptada el 29-07-2026

Decisio:
Una ingestio fallida, parcial, bloquejada o sospitosament buida no substitueix ni desactiva l'ultima instantania valida.

Motiu:
Deadlocks i fallades temporals de fonts externes no han de fer desapareixer dades actives del dashboard.
