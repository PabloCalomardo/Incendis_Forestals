# Fase 1: bootstrap del monorepo

## Abast implementat

- Monorepo amb `apps/web`, `apps/api`, `workers`, `packages`, `infrastructure`, `docs` i `tests`.
- Frontend Next.js App Router amb TypeScript estricte, Tailwind CSS, TanStack Query, Zustand i MapLibre GL JS sense fonts externes.
- Backend FastAPI amb endpoints `/health`, `/ready` i `/version`.
- Configuracio amb Pydantic Settings, SQLAlchemy async, Alembic, Redis i MinIO.
- Workers Celery separats per ingestio, geoespacial i prediccions, cadascun amb tasca `ping`.
- Docker Compose amb frontend, API, PostgreSQL/PostGIS, Redis, MinIO i workers.
- Qualitat base: ESLint, Prettier, Ruff, mypy, pytest, Vitest i pre-commit.

## No implementat en aquesta fase

- Models de domini d'incendis.
- Connectors externs.
- Autenticacio OIDC real.
- Logica GIS, fum o routing.
- Observabilitat completa.

Aquestes absencies son intencionades i corresponen a fases posteriors del pla.
