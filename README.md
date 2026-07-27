# Wildfire Intelligence Platform

Plataforma per integrar informacio d'incendis forestals, conservar-ne la procedencia i servir-la a dos portals: Civil i Bomber.

## Prioritat actual

El desenvolupament per fases ha finalitzat. Primer es completara una versio publicable del Dashboard Civil (`/civil`). El Dashboard per a Professionals queda ajornat fins que la versio Civil sigui acceptada. L'estat consolidat es a `docs/project-status.md`.

## Serveis

- `frontend`: Next.js App Router a `http://localhost:3000`.
- `api`: FastAPI a `http://localhost:8000`.
- `postgres`: PostgreSQL 16 amb PostGIS a `localhost:5432`.
- `redis`: broker/cache inicial a `localhost:6379`.
- `minio`: object storage S3 compatible a `http://localhost:9000`, consola a `http://localhost:9001`.
- `worker-ingestion`: worker Celery per ingestio.
- `worker-geospatial`: worker Celery per processos GIS.
- `worker-predictions`: worker Celery per prediccions.

## Inici rapid

1. Instal·la Node.js 22 LTS o superior.
2. Revisa `.env.example` i copia'l a `.env` si vols valors locals propis.
3. Instal·la dependències:

```bash
npm install
npm run install:all
```

4. Executa en local, sense Docker:

```bash
npm run dev
```

Aquesta ordre arrenca l'API FastAPI i el frontend Next.js. Per arrencar tota la pila amb PostgreSQL/PostGIS, Redis, MinIO i workers cal Docker:

```bash
npm run dev:docker
```

Per Fase 2 i migracions PostGIS reals, instal·la Docker Desktop o una base PostgreSQL amb PostGIS equivalent. Sense Docker, el portal i l'API poden arrencar, però `/ready` i `npm run migrate` no tindran base de dades completa.

`npm run migrate` executa Alembic dins Docker Compose. Usa `npm run migrate:local` nomes si tens una base local i has ajustat `DATABASE_URL` perquè apunti a `localhost`.

## Ordres

```bash
make install
make dev
make build
make lint
make typecheck
make test
make migrate
make reset-db
```

Equivalents amb npm:

```bash
npm run dev
npm run dev:docker
npm run lint
npm run typecheck
npm run test
npm run migrate
npm run migrate:local
```

En Windows no cal `make`; les ordres `npm run ...` son la via suportada.
Si vols una drecera semblant a make sense instal·lar GNU make:

```powershell
.\make.ps1 dev
.\make.ps1 test
```

## Variables d'entorn

Les variables estan documentades a `.env.example`. Les claus reals no s'han de commitar.

- `NEXT_PUBLIC_API_BASE_URL`: URL publica del backend per al navegador.
- `API_INTERNAL_BASE_URL`: URL interna del backend per renderitzat server-side dins Docker.
- `DATABASE_URL`: connexio SQLAlchemy async.
- `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`: Redis per API i workers.
- `MINIO_*`, `S3_*`: object storage compatible S3.
- `OIDC_*`: reservades per a l'autenticacio del portal Bomber.

## Ports

- `3000`: frontend.
- `8000`: API.
- `5432`: PostgreSQL/PostGIS.
- `6379`: Redis.
- `9000`: MinIO API.
- `9001`: MinIO Console.

## Endpoints de sistema

- `GET /health`: vida del proces API.
- `GET /ready`: readiness de PostgreSQL/PostGIS, Redis i MinIO.
- `GET /version`: nom, versio i entorn.

## Errors habituals

- Avisos `EBADENGINE`: actualitza a Node.js 22 LTS. Amb Node 20.11 algunes dependències funcionen però avisen perquè demanen Node més nou.
- `"docker" no se reconoce`: instal·la Docker Desktop i torna a obrir la terminal. Després comprova `docker compose version`.
- `npm run migrate:local` no troba `postgres`: usa `npm run migrate` amb Docker, o canvia `DATABASE_URL` a un host local real.
- `GET /ready` retorna `503`: algun servei dependent encara no esta llest.
- En mode `npm run dev` local, `/ready` pot retornar `503` si PostgreSQL, Redis o MinIO no estan arrencats.
- El frontend no mostra l'API com a connectada: comprova `API_INTERNAL_BASE_URL` dins Docker i `NEXT_PUBLIC_API_BASE_URL` al navegador.
- Les migracions fallen amb PostGIS: comprova que el servei `postgres` usa la imatge `postgis/postgis`.
- MinIO no esta ready: espera que `minio-init` hagi creat el bucket definit a `MINIO_BUCKET_RAW`.

## Estat

La plataforma executable inclou el Dashboard Civil, API publica, ingestio real NASA FIRMS, AEMET, IGN, DGT/NAP DATEX, Proteccio Civil/CECAT i xarxa viaria CNIG local a PostGIS. El portal professional, autenticacio OIDC i eines operatives avancades continuen pendents.

## Preparacio GitHub

S'han de pujar el codi, documentacio, migracions, configuracions i `.env.example`.

No s'han de pujar secrets, `.env`, entorns virtuals, `node_modules`, caches, builds, dades locals, dumps ni volums.
