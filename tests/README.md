# Proves

- `apps/api/tests`: API Civil, domini, migracions, connectors, EFFIS, OSINT i reconciliacio.
- `workers/tests`: registre i comportament de tasques Celery.
- `apps/web/src/**/*.test.tsx|ts`: portal Civil, client API i interaccions.

Ordres principals:

```powershell
npm test
npm run lint
npm run typecheck
```

Ultima validacio completa documentada: [`../docs/current-state.md`](../docs/current-state.md). Les proves que necessiten PostgreSQL/PostGIS, Redis o MinIO s'han d'executar amb Docker Compose.
