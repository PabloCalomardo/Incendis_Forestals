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
No es tria encara entre Valhalla, GraphHopper o OpenRouteService. La decisio queda diferida fins a la Fase 11.

Motiu:
La Fase 11 exigeix triar-ne un, justificar-lo i documentar-lo a partir de dades viaries i requisits operatius reals.

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
