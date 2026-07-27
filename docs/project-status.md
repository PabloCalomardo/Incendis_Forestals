# Estat actual del projecte

Actualitzat: 27-07-2026.

## Direccio de producte

El desenvolupament per fases ha finalitzat. La prioritat exclusiva actual es portar el **Dashboard Civil** a una versio publicable. El **Dashboard per a Professionals** queda ajornat fins que la versio Civil superi els criteris funcionals, visuals, de rendiment, accessibilitat, seguretat i desplegament.

## Plataforma disponible

- Monorepo executable amb Next.js, FastAPI, PostgreSQL/PostGIS, Redis, MinIO i workers Celery.
- Docker Compose, migracions, health checks, scripts d'instal·lacio, build, tests i ingestio.
- Domini persistent amb procedencia, originals, execucions, deduplicacio, qualitat i advertiments.
- API Civil publica amb GeoJSON, paginacio, filtres espacials i exposicio controlada de metadades.
- Portal Civil funcional a `/civil`; el portal professional encara no es la linia activa de producte.

## Dades i integracions

- NASA FIRMS: ingestio real amb clau privada, originals, reintents, deduplicacio i deteccions VIIRS/MODIS.
- AEMET: observacions i prediccio municipal.
- IGN: cerca estatal de municipis i centrament del mapa.
- DGT/NAP DATEX II: incidencies estatals, SCT i DT-GV, classificades per categoria i causa.
- Proteccio Civil/CECAT: plans i avisos publics disponibles; no s'infereixen evacuacions sense font oficial.
- CNIG IGR-RT: xarxa viaria estatal local a PostGIS amb 1.780.681 trams i 190.893 punts quilometrics.
- OSM/MapLibre: mapa base configurable; el servei public de tiles actual es adequat per desenvolupament, no es considera encara proveidor de produccio.

## Geometria implementada

- Les deteccions FIRMS es representen com petjades fixes de sensor, no com heatmap dependent del zoom.
- Els pixels actius es connecten per distancia de sensor, formen poligons detallats i preserven forats interns.
- Cada grup FIRMS mostra un pin vermell situat de manera conservadora dins del poligon, amb recompte, dates i superficie al popup.
- Els punts FIRMS originals es poden activar com una capa independent.
- Les restriccions DATEX segueixen la carretera oficial indicada, prioritzant nom i PK sobre una xarxa CNIG local.
- El resolutor construeix un graf exclusiu dels trams de la mateixa carretera; no pot desviar una afectacio per una via veina. DGT PK, Overpass i OSRM son fallbacks.

## Dashboard Civil actual

- Mapa MapLibre principal, ampli i responsive, amb popups clicables.
- Cerca de municipi que centra i amplia el mapa sense filtrar les dades visibles.
- Controls compactes de capes i filtre de vigencia; no hi ha filtre de confianca minima.
- Carreteres i afectacions s'exposen com una categoria unica, `Restriccions a Carreteres`.
- Incendis i obstacles ambientals es mostren en taronja brillant; la resta de restriccions, en lila translucid.
- La xarxa viaria discontinua de context no es visualitza.
- Les capes es poden activar i desactivar sense reconstruir el mapa.
- El zoom actualitza la URL amb `history.replaceState`, sense navegacio Next.js ni recarrega de dades. TanStack Query conserva les respostes durant cinc minuts i no refresca en recuperar el focus.
- La barra lateral s'ajusta al contingut; Filtres i Capes son compactes i el mapa ocupa aproximadament el 72% de l'altura de la finestra.

## Decisions tancades

- La implementacio de carreteres i restriccions queda tancada temporalment.
- Les dades viaries pesades es mantenen locals i fora de Git; es carreguen amb `npm run roads:import`.
- El fitxer `.env` i les claus no es versionen.
- No es presenten evacuacions inferides; una futura integracio requerira fonts oficials verificables.

## Proxim objectiu

Treballar exclusivament en la qualitat publicable del Dashboard Civil: UX, jerarquia visual, contingut public, accessibilitat, rendiment, proves, observabilitat, configuracio de tiles de produccio i desplegament. Despres d'una acceptacio explicita, s'obrira el treball del Dashboard per a Professionals.
