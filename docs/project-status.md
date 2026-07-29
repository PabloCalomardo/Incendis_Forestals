# Estat actual del projecte

Actualitzat: 29-07-2026.

L'estat operatiu complet i les instruccions de continuacio es mantenen a [`current-state.md`](current-state.md).

## Resum

- Prioritat: Dashboard Civil publicable; Portal Bomber ajornat.
- Pila completa executable amb Next.js, FastAPI, PostGIS, Redis, MinIO i Celery.
- Integracions actives: FIRMS, EFFIS, AEMET, AEMET CAP, DATEX DGT/SCT/DT-GV, eTraffic, IGN/CNIG, OSM,
  Proteccio Civil/CECAT, registre ES-Alert autenticat, monitor OSINT/Nitter i aeronaus d'emergencia via OpenSky/Airplanes.live.
- Incendis canonics: perimetres EFFIS reconciliats amb FIRMS i publicacions OSINT.
- Dashboard: capes dins del mapa, llistes amb scroll, cronologia FIRMS diaria, llegenda tancable, detall complet sota
  el mapa, aeronaus sempre per sobre de la resta de capes i focus geografic en seleccionar elements.
- Transit: geometria DATEX enriquida sobre CNIG, incloses carreteres sense PK; reparacio automatica de línies de dos
  punts.
- Validacio: API `82` proves; frontend `10` proves; Ruff, mypy i TypeScript correctes.

## Pendents prioritaris

1. Acabar la reparacio progressiva de geometries DATEX i monitorar-ne la taxa d'exit.
2. Reforçar cobertura i disponibilitat de fonts OSINT/Nitter.
3. Construir la pantalla de revisio humana.
4. Preparar tiles, observabilitat, backups, CI/CD, seguretat i desplegament de produccio.
