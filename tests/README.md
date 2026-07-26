# Tests

Els tests de Fase 1 viuen a:

- `apps/api/tests`: endpoints de salut, readiness i versionat.
- `workers/tests`: tasques Celery de prova.
- `apps/web/src/**/*.test.tsx`: components i pagines del frontend.

Les proves d'integracio amb serveis reals s'executen amb Docker Compose un cop instal·lades les dependecies.
