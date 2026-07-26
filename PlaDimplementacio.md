# Prompts d’implementació per a Codex

## Regla d’ús

Abans de començar, desa l’especificació completa del projecte al fitxer:

```text
EspecificacioProjecte.md
```

Aquest fitxer serà la font principal de requisits funcionals, arquitectura, terminologia, fonts de dades, funcionalitats dels portals Civil i Bomber i principis de confiança de la informació.

Comença executant primer el **Prompt Inicial** i ves marcant els promts que s'han anat resolent en aquest mateix fitxer, JO et diré quan un promt està resolt i podem seguir endevant executant els següents promts un per un, sempre sobre el mateix repositori.

---

# Prompt inicial — Anàlisi, planificació i preparació del repositori

Estat: completat

```text
Actua com a arquitecte de software principal, enginyer backend, enginyer frontend, especialista GIS i responsable DevOps del projecte.

Abans de fer qualsevol canvi, obre i llegeix completament el fitxer:

EspecificacioProjecte.md

Aquest fitxer és la font de veritat del projecte. No dupliquis els seus requisits en altres documents tret que sigui necessari per a documentació tècnica específica.

L’objectiu d’aquesta primera tasca no és implementar encara totes les funcionalitats, sinó analitzar l’especificació, inspeccionar l’estat actual del repositori i preparar un pla d’implementació executable.

Realitza les accions següents:

1. Inspecciona tot el repositori.
2. Identifica:
   - fitxers existents;
   - llenguatges i frameworks actuals;
   - configuracions;
   - dependències;
   - infraestructura disponible;
   - codi reutilitzable;
   - conflictes amb EspecificacioProjecte.md.
3. Resumeix els requisits principals de l’especificació sense copiar-la sencera.
4. Divideix el sistema en mòduls tècnics:
   - frontend Civil;
   - frontend Bomber;
   - API;
   - autenticació;
   - ingestió;
   - normalització;
   - domini;
   - processament geoespacial;
   - predicció de fum;
   - detecció de carreteres afectades;
   - routing;
   - notificacions;
   - observabilitat;
   - infraestructura.
5. Identifica dependències entre mòduls.
6. Proposa l’ordre exacte d’implementació.
7. Identifica riscos:
   - disponibilitat de dades externes;
   - qualitat i retard de dades;
   - llicències;
   - rendiment geoespacial;
   - seguretat;
   - falsa precisió dels models;
   - integració amb APIs sense entorn de proves.
8. Crea o actualitza aquests documents:
   - docs/architecture/overview.md
   - docs/architecture/modules.md
   - docs/architecture/data-flow.md
   - docs/architecture/decisions.md
   - docs/implementation-plan.md
9. Inclou diagrames Mermaid als documents d’arquitectura.
10. No implementis encara funcionalitats de negoci.
11. No inventis APIs, credencials, formats ni camps que no apareguin a l’especificació o documentació oficial.
12. Quan falti informació, crea una decisió provisional explícita a docs/architecture/decisions.md.

En finalitzar:

- mostra l’estat actual del repositori;
- resumeix els documents creats;
- enumera les decisions preses;
- enumera els riscos;
- indica si el repositori està preparat per començar la fase 1;
- no avancis automàticament a la fase següent.
```

---

# Fase 1 — Bootstrap complet del monorepo

Estat: completat

```text
Llegeix completament EspecificacioProjecte.md i docs/implementation-plan.md abans de modificar res.

Implementa la base executiva del projecte com un monorepo preparat per contenir tots els components descrits a l’especificació.

No et limitis a crear carpetes buides. Cada aplicació i paquet ha de quedar inicialitzat, executable, connectat i documentat.

Crea una estructura equivalent a:

apps/
  web/
  api/

workers/
  ingestion/
  geospatial/
  predictions/

packages/
  shared-types/
  config/
  ui/

infrastructure/
  docker/
  monitoring/

docs/
tests/

Requisits del frontend:

- inicialitza Next.js amb App Router;
- utilitza TypeScript estricte;
- configura Tailwind CSS;
- crea una estructura preparada per als portals Civil i Bomber;
- crea layouts diferenciats per a /civil i /bomber;
- configura TanStack Query;
- configura Zustand només per a estat local;
- prepara MapLibre GL JS sense afegir encara cap font externa;
- crea una pàgina inicial que permeti entrar al portal Civil o Bomber;
- crea una capa de client API centralitzada;
- configura variables públiques i privades correctament;
- evita claus externes al navegador.

Requisits del backend:

- inicialitza FastAPI;
- separa configuració, domini, infraestructura, API i serveis;
- configura Pydantic Settings;
- configura SQLAlchemy asíncron;
- configura Alembic;
- configura PostgreSQL i PostGIS;
- configura Redis;
- configura MinIO o emmagatzematge S3 compatible;
- crea endpoints:
  - GET /health
  - GET /ready
  - GET /version
- retorna errors amb una estructura consistent;
- afegeix correlation IDs;
- configura logging estructurat.

Requisits dels workers:

- crea workers separats per ingestió, geoprocessament i predicció;
- configura Celery;
- configura Redis com a broker inicial;
- crea una tasca de prova per cada worker;
- comprova que les tasques s’executen correctament;
- no implementis encara lògica real d’incendis.

Requisits d’infraestructura:

- crea docker-compose.yml;
- inclou:
  - frontend;
  - API;
  - PostgreSQL amb PostGIS;
  - Redis;
  - MinIO;
  - workers;
- afegeix health checks;
- afegeix volums persistents;
- configura xarxes internes;
- crea .env.example complet;
- no introdueixis credencials reals.

Qualitat:

- ESLint;
- Prettier;
- Ruff;
- mypy;
- pytest;
- tests frontend;
- pre-commit;
- scripts o Makefile per:
  - install;
  - dev;
  - build;
  - lint;
  - typecheck;
  - test;
  - migrate;
  - reset-db.

Documentació:

- actualitza README.md;
- explica com iniciar el sistema;
- explica els serveis;
- explica les variables d’entorn;
- documenta els ports;
- documenta errors habituals.

Criteris d’acceptació obligatoris:

- tot el sistema arrenca amb una sola ordre;
- frontend i backend es comuniquen;
- PostGIS està habilitat;
- Redis respon;
- MinIO respon;
- els workers executen una tasca de prova;
- les migracions funcionen;
- lint, tipatge i tests passen;
- no hi ha carpetes importants completament buides;
- no hi ha funcionalitats simulades presentades com a implementades.

En finalitzar:

1. executa totes les comprovacions;
2. corregeix els errors;
3. mostra l’arbre principal del repositori;
4. resumeix els fitxers creats;
5. indica les ordres d’execució;
6. enumera qualsevol limitació pendent;
7. no avancis a la fase 2.
```

---

# Fase 2 — Domini, base de dades i traçabilitat

Estat: completat

```text
Llegeix EspecificacioProjecte.md, especialment els apartats de fonts, confiança, dades oficials, observades i estimades.

Inspecciona també la implementació actual i les migracions existents.

Implementa el model de domini principal de la plataforma.

No modelis les dades únicament segons la UI. Dissenya un domini que permeti conservar dades originals, versions, fonts, observacions, estimacions i contradiccions.

Implementa com a mínim:

- DataSource
- DataIngestionRun
- Incident
- IncidentVersion
- IncidentStatus
- FireDetection
- FirePerimeter
- OfficialNotice
- EvacuationZone
- RestrictionZone
- RoadSegment
- RoadIncident
- WeatherObservation
- WeatherForecast
- SmokeForecast
- RiskForecast
- ModelExecution
- User
- Role
- AuditEvent

Totes les entitats geogràfiques han d’utilitzar PostGIS.

Implementa camps comuns quan siguin aplicables:

- UUID;
- geometria;
- sistema de coordenades;
- font;
- identificador extern;
- tipus de font;
- data observada;
- data publicada;
- data rebuda;
- data de caducitat;
- estat de verificació;
- confiança;
- versió;
- metadades originals;
- hash de deduplicació;
- dates de creació i actualització.

Implementa aquests tipus de procedència:

- official;
- observed;
- estimated;
- unverified.

Implementa aquests principis:

- una predicció no pot convertir-se automàticament en dada oficial;
- la dada original no s’ha de sobreescriure;
- qualsevol canvi rellevant ha de generar una versió;
- totes les prediccions han d’estar associades a una execució de model;
- les execucions han de guardar inputs, versió del model i timestamps;
- les contradiccions entre fonts han de poder coexistir.

Tasques tècniques:

- crea models SQLAlchemy;
- crea esquemes Pydantic diferenciats per creació, lectura i resposta;
- crea repositoris;
- crea serveis de domini;
- crea migracions Alembic;
- crea índexs GIST;
- crea índexs temporals;
- crea restriccions d’integritat;
- crea enums compartits;
- crea fixtures de prova;
- crea factories de test;
- crea tests unitaris;
- crea tests de persistència;
- prova inserció, consulta, actualització, versionat i soft delete;
- documenta el model amb Mermaid ER.

No implementis encara connectors externs.

Criteris d’acceptació:

- totes les migracions apliquen i reverteixen;
- les geometries es poden consultar espacialment;
- els registres crítics queden versionats;
- no es perd la dada original;
- totes les dades tenen procedència;
- les prediccions tenen traçabilitat;
- els tests passen.

Actualitza:

- docs/architecture/data-model.md
- docs/architecture/data-lineage.md
- docs/architecture/decisions.md

En finalitzar, mostra:

- resum del model;
- migracions creades;
- índexs;
- tests executats;
- decisions provisionals;
- limitacions.
```

---

# Fase 3 — Framework d’ingestió i connector NASA FIRMS

```text
Llegeix EspecificacioProjecte.md i identifica totes les fonts externes previstes.

En aquesta fase implementa una arquitectura genèrica d’ingestió i un únic connector complet de producció: NASA FIRMS.

No implementis connectors incomplets fingint que són funcionals.

Crea un contracte base de connector amb operacions equivalents a:

- fetch;
- validate;
- normalize;
- deduplicate;
- persist;
- report_metrics.

Cada connector ha de suportar:

- autenticació;
- timeouts;
- retries amb backoff exponencial;
- rate limiting;
- paginació;
- idempotència;
- registre d’execució;
- persistència de la resposta original;
- reprocessament;
- dead-letter handling;
- mètriques;
- errors parcials;
- cancel·lació segura.

Implementa una configuració central de connectors.

Per al connector FIRMS:

- utilitza credencials només des de variables d’entorn;
- no exposis la clau al frontend;
- implementa consulta per àrea geogràfica;
- limita inicialment l’àrea a Espanya;
- desa la resposta original;
- transforma les deteccions al model FireDetection;
- conserva:
  - sensor;
  - satèl·lit;
  - latitud;
  - longitud;
  - data;
  - hora;
  - confiança;
  - FRP;
  - atributs originals;
- calcula una clau de deduplicació;
- evita insercions duplicades;
- registra cada execució a DataIngestionRun;
- desa nombre de registres rebuts, descartats, duplicats i persistits.

Configura una tasca Celery programada.

Afegeix:

- endpoint intern per executar manualment el connector;
- endpoint intern per consultar l’estat;
- protecció perquè aquests endpoints no siguin públics;
- fixtures representatives;
- mocks de l’API;
- tests de timeout;
- tests de retry;
- tests de resposta invàlida;
- tests de duplicació;
- tests de reprocessament.

Per a EFFIS, AEMET, DGT, MITECO, IGN i OSM:

- crea només les interfícies i documents de planificació;
- no afirmis que estan integrats;
- crea fitxers TODO estructurats amb prerequisits i documentació requerida.

Actualitza:

- docs/integrations/README.md
- docs/integrations/firms.md
- docs/runbooks/ingestion.md

Criteris d’acceptació:

- el connector FIRMS pot executar-se completament;
- cap duplicat s’insereix dues vegades;
- els errors queden registrats;
- la resposta original es conserva;
- el connector es pot reprocessar;
- els tests passen;
- les altres integracions no apareixen com a finalitzades.
```

---

# Fase 4 — Connectors meteorològics i geogràfics

```text
Llegeix EspecificacioProjecte.md i la documentació d’integracions existent.

Implementa els connectors següents:

- AEMET OpenData;
- IGN/CNIG;
- OpenStreetMap.

No implementis encara DGT, CAMS, EFFIS ni fonts autonòmiques.

AEMET:

- implementa autenticació per variable d’entorn;
- ingestió d’observacions;
- ingestió de prediccions;
- vent;
- direcció;
- ratxes;
- temperatura;
- humitat;
- precipitació;
- timestamps;
- localització;
- resolució;
- horitzó de predicció;
- desa resposta original;
- normalitza unitats;
- registra la qualitat;
- gestiona estacions absents;
- gestiona dades retardades;
- diferencia observació i predicció.

IGN:

- implementa descàrrega o consum dels serveis necessaris;
- prepara ingestió de:
  - límits administratius;
  - models d’elevació;
  - carreteres oficials;
  - cartografia base;
- desa metadades de l’origen;
- mantén el CRS original;
- transforma a EPSG:4326 per al model intern quan sigui necessari;
- no descarreguis dades massives sense mecanismes de control;
- implementa importacions per àrea.

OpenStreetMap:

- implementa una estratègia d’importació reproduïble;
- separa carreteres, pistes i camins;
- conserva tags rellevants:
  - highway;
  - surface;
  - width;
  - access;
  - maxweight;
  - incline;
  - tracktype;
  - smoothness;
- no utilitzis l’API pública principal per importacions massives;
- prepara una estratègia basada en extractes o eines adequades.

Integra totes les fonts amb el framework d’ingestió existent.

Afegeix tests i fixtures realistes.

Implementa validació geogràfica i temporal.

Actualitza la documentació i indica clarament:

- freqüència de sincronització;
- limitacions;
- cobertura;
- llicència;
- retard esperat;
- confiança inicial.

Criteris d’acceptació:

- les dades AEMET es poden relacionar amb ubicacions;
- els datasets IGN es poden importar per àrea;
- la xarxa OSM conté atributs operatius;
- la ingestió és idempotent;
- els errors no bloquegen altres fonts;
- els tests passen.
```

---

# Fase 5 — Normalització, fusió i puntuació de confiança

```text
Llegeix EspecificacioProjecte.md, especialment els principis de desinformació, retard, confiança i separació entre dades oficials i estimades.

Implementa una capa de normalització i qualitat independent dels connectors.

Objectius:

- unificar formats;
- conservar originals;
- detectar duplicats;
- relacionar observacions;
- registrar contradiccions;
- calcular edat i retard;
- generar confiança explicable.

Implementa:

1. Normalització temporal:
   - UTC;
   - zona horària original;
   - data observada;
   - data publicada;
   - data ingerida;
   - retard.

2. Normalització espacial:
   - transformació a EPSG:4326;
   - reparació de geometries;
   - validació;
   - simplificació només en còpies derivades.

3. Deduplicació:
   - identificador extern;
   - hash;
   - proximitat espacial;
   - proximitat temporal;
   - sensor;
   - font.

4. Agrupació d’incidents:
   - associa deteccions pròximes;
   - no fusionis automàticament incidents oficials diferents;
   - registra l’explicació de cada agrupació;
   - permet revisió manual futura.

5. Confiança:
   - autoritat de la font;
   - antiguitat;
   - resolució;
   - coherència;
   - coincidència;
   - qualitat de geometria;
   - oficialitat;
   - disponibilitat d’inputs.

La confiança ha de retornar:

- valor numèric;
- categoria;
- factors;
- penalitzacions;
- timestamp de càlcul;
- versió de l’algoritme.

6. Contradiccions:
   - estat diferent;
   - perímetres incompatibles;
   - carreteres amb estats oposats;
   - timestamps inconsistents;
   - ordres oficials incompatibles.

No eliminis cap informació contradictòria.

Crea serveis, workers i tests.

Crea una API interna per inspeccionar la traçabilitat d’un registre.

Actualitza:

- docs/domain/confidence-model.md
- docs/domain/deduplication.md
- docs/domain/conflict-resolution.md

Criteris d’acceptació:

- els càlculs són reproduïbles;
- la confiança és explicable;
- les dades antigues són penalitzades;
- les contradiccions queden visibles;
- cap predicció es converteix en dada oficial;
- els tests passen.
```

---

# Fase 6 — API Civil

```text
Llegeix EspecificacioProjecte.md i implementa exclusivament l’API destinada al portal Civil.

L’API Civil ha de prioritzar claredat, seguretat i informació pública.

No exposis:

- dades internes de model;
- credencials;
- informació operativa sensible;
- ubicacions de recursos;
- informació restringida;
- camps interns innecessaris.

Implementa endpoints per:

- incidents;
- detall d’incident;
- cronologia;
- deteccions;
- perímetres;
- evacuacions;
- restriccions;
- carreteres;
- avisos;
- risc;
- fum simplificat;
- cerca geogràfica;
- cerca per municipi.

Funcionalitats:

- bounding box;
- radi;
- municipi;
- interval temporal;
- estat;
- font;
- confiança mínima;
- paginació;
- ordenació;
- GeoJSON;
- ETags;
- cache Redis;
- OpenAPI;
- rate limiting;
- correlation IDs;
- errors consistents.

Cada resposta ha d’incloure:

- tipus de dada;
- font;
- hora observada;
- hora actualitzada;
- antiguitat;
- confiança;
- oficial, observada o estimada;
- advertiments;
- enllaç a la font quan existeixi.

Implementa polítiques per no mostrar estimacions antigues com a actuals.

Crea tests de contracte.

Crea tests de permisos.

Crea tests de rendiment bàsics sobre consultes espacials.

Actualitza:

- docs/api/civil.md
- OpenAPI;
- exemples de resposta.

Criteris d’acceptació:

- l’API Civil no exposa dades sensibles;
- totes les respostes tenen traçabilitat;
- les consultes espacials utilitzen índexs;
- els errors són predictibles;
- els tests passen.
```

---

# Fase 7 — Portal Civil complet

```text
Llegeix EspecificacioProjecte.md i la documentació de l’API Civil.

Implementa el portal Civil complet.

No utilitzis dades simulades tret de fixtures en mode desenvolupament.

Pantalles:

- portada;
- mapa;
- llista d’incidents;
- detall d’incident;
- cronologia;
- evacuacions;
- restriccions;
- carreteres;
- metodologia;
- fonts;
- estat de dades.

Mapa:

- MapLibre GL JS;
- clustering;
- deteccions satel·litàries;
- perímetres oficials;
- perímetres estimats;
- evacuacions;
- restriccions;
- carreteres tallades;
- risc;
- fum simplificat.

Regles visuals:

- oficial i estimat han de ser visualment diferents;
- no utilitzis només color;
- utilitza patrons, línies, icones i etiquetes;
- les dades antigues han de perdre opacitat;
- cada capa ha de mostrar font i actualització;
- sempre hi ha una llegenda;
- les estimacions han de mostrar advertiment.

UX:

- mobile first;
- cerca per municipi;
- filtres;
- deep links;
- URL sincronitzada amb el mapa;
- panell inferior en mòbil;
- panell lateral en escriptori;
- estats de càrrega;
- estats sense dades;
- gestió d’errors;
- degradació si falla el mapa.

Accessibilitat:

- WCAG AA;
- navegació per teclat;
- focus visible;
- contrast;
- alternatives textuals;
- no dependre només del mapa.

Rendiment:

- càrrega diferida;
- tiles;
- simplificació;
- virtualització;
- evitar descarregar geometries innecessàries.

Crea tests:

- components;
- integració;
- navegació;
- accessibilitat;
- fluxos principals.

Actualitza:

- docs/frontend/civil.md
- docs/design/civil-ui.md

Criteris d’acceptació:

- el portal funciona en mòbil i escriptori;
- les dades oficials i estimades no es poden confondre;
- el mapa continua sent usable amb volum elevat;
- la informació essencial és accessible sense mapa;
- els tests passen.
```

---

# Fase 8 — Autenticació, permisos i Portal Bomber base

```text
Llegeix EspecificacioProjecte.md i implementa la base segura del portal Bomber.

Aquesta part és operativa i no pot reutilitzar sense control els permisos del portal Civil.

Implementa:

- OpenID Connect;
- sessions segures;
- tokens curts;
- refresh segur;
- revocació;
- RBAC;
- auditoria;
- preparació per MFA;
- protecció de login;
- bloqueig progressiu;
- cookies segures;
- CSRF quan sigui aplicable.

Rols:

- firefighter;
- analyst;
- incident_commander;
- administrator.

Defineix permisos explícits per:

- visualitzar incidents;
- visualitzar prediccions;
- consultar carreteres;
- calcular rutes;
- exportar;
- administrar usuaris;
- veure auditoria.

Portal Bomber:

- dashboard;
- selector d’incident;
- mapa tècnic;
- control temporal;
- panell de fonts;
- retard de dades;
- capes meteorològiques;
- perímetres;
- deteccions;
- relleu;
- carreteres;
- prediccions disponibles;
- historial d’execucions.

Cada dada ha de mostrar:

- font;
- hora;
- retard;
- confiança;
- tipus;
- versió;
- advertiment.

No implementis encara el model de fum ni el routing complet.

Crea tests de:

- autenticació;
- permisos;
- denegació;
- revocació;
- auditoria;
- accés directe a URLs.

Criteris d’acceptació:

- cap usuari Civil entra al portal Bomber;
- cada endpoint professional valida permisos;
- les accions sensibles queden auditades;
- les prediccions mostren traçabilitat;
- els tests passen.
```

---

# Fase 9 — Motor geoespacial

```text
Llegeix EspecificacioProjecte.md i implementa el motor geoespacial com un servei modular executable per workers.

Implementa operacions reals, no simples wrappers sense ús.

Funcionalitats:

- intersecció de perímetres amb carreteres;
- intersecció amb municipis;
- intersecció amb infraestructures;
- buffers segons incertesa;
- distàncies;
- càlcul de pendent;
- orientació;
- elevació;
- validació;
- reparació;
- simplificació;
- union;
- difference;
- clipping;
- vector tiles.

Entrades:

- GeoJSON;
- GeoPackage;
- Shapefile;
- GeoTIFF;
- WFS;
- WMS/WMTS només per visualització o processos compatibles.

Requisits:

- processos grans en workers;
- idempotència;
- cancel·lació;
- timeouts;
- límits de memòria;
- metadades;
- versionat;
- reproducció;
- logs;
- mètriques.

Crea casos de prova geogràfics amb resultats coneguts.

Comprova:

- geometries invàlides;
- multipolígons;
- antimeridià si aplica;
- CRS incorrectes;
- geometries buides;
- interseccions massives.

Documenta:

- precisió;
- CRS;
- toleràncies;
- simplificació;
- limitacions.

Criteris d’acceptació:

- els resultats són reproduïbles;
- les operacions grans no bloquegen l’API;
- els resultats queden versionats;
- els tests espacials passen.
```

---

# Fase 10 — Model inicial de fum

```text
Llegeix EspecificacioProjecte.md, especialment la part del núvol de fum, retard de dades, carreteres potencialment afectades i advertiments.

Implementa un primer model operacional de fum substituïble.

No presentis aquest model com un model físic certificat.

Defineix una interfície de model que permeti substituir-lo posteriorment per CAMS, HYSPLIT o FLEXPART.

Entrades mínimes:

- focus o perímetre;
- potència radiativa;
- vent;
- direcció;
- ratxes;
- humitat;
- temperatura;
- altitud;
- relleu;
- edat de cada input;
- resolució de cada input.

Sortides:

- polígon probabilístic;
- horitzons 1h, 3h, 6h i 12h;
- intensitat relativa;
- possible afectació de visibilitat;
- incertesa;
- confidence score;
- advertiments;
- inputs;
- versió;
- timestamp.

Implementa:

- servei de predicció;
- worker;
- persistència;
- historial;
- API Bomber;
- visualització;
- comparació entre execucions;
- expiració;
- invalidació si canvien inputs;
- recàlcul.

Tests:

- mateix input, mateix resultat;
- canvi de vent;
- vent nul;
- dades antigues;
- falta d’humitat;
- geometria invàlida;
- diferents horitzons;
- reexecució.

Criteris d’acceptació:

- el model és determinista;
- el resultat és explicable;
- la incertesa és visible;
- els inputs queden guardats;
- cap resultat es mostra com a oficial;
- els tests passen.
```

---

# Fase 11 — Carreteres afectades i motor de rutes

```text
Llegeix EspecificacioProjecte.md i utilitza les dades viàries, geoespacials i de fum existents.

Implementa el sistema de classificació de carreteres i routing operatiu.

Classificacions:

- accessible;
- tall oficial;
- dins del perímetre;
- fum probable;
- visibilitat reduïda;
- dades insuficients;
- informació caducada.

La classificació ha de diferenciar clarament:

- restricció oficial;
- observació;
- estimació;
- inferència.

Càlcul de risc:

- distància al perímetre;
- intersecció;
- intensitat;
- fum;
- visibilitat;
- edat;
- retard;
- font;
- tipus de via;
- superfície;
- amplada;
- pendent;
- sentit;
- restriccions de vehicle.

Integra un motor autoallotjat:

- Valhalla;
- GraphHopper;
- o OpenRouteService.

Tria’n un, justifica la decisió i documenta-la.

Implementa:

- perfil de vehicle d’emergència;
- exclusió de polígons;
- penalització de trams;
- rutes alternatives;
- explicació del cost;
- recalcul;
- detecció de dades massa antigues;
- resposta segura quan no existeix ruta fiable.

Cada ruta ha de conservar:

- inputs;
- exclusions;
- penalitzacions;
- hora;
- versió;
- alternatives;
- confiança;
- advertiments.

Crea interfície al portal Bomber.

Tests:

- carretera tancada;
- carretera afectada només per fum;
- múltiples alternatives;
- ruta sense sortida;
- dades antigues;
- vehicle amb restriccions;
- canvi de predicció.

Criteris d’acceptació:

- una estimació no apareix com a tall oficial;
- les rutes són explicables;
- les dades antigues poden invalidar una ruta;
- les alternatives es comparen;
- els tests passen.
```

---

# Fase 12 — Temps real, alertes i notificacions

```text
Llegeix EspecificacioProjecte.md i implementa el sistema de canvis en temps real.

Utilitza Server-Sent Events o WebSockets segons la necessitat real. Justifica la decisió.

Esdeveniments:

- incident nou;
- canvi d’estat;
- nou perímetre;
- nova detecció;
- evacuació;
- restricció;
- tall;
- predicció completada;
- canvi de risc;
- canvi de ruta.

Requisits:

- idempotència;
- ordenació;
- timestamps;
- retries;
- reconnexió;
- deduplicació;
- agrupació;
- prioritat;
- traçabilitat;
- permisos.

Portal Civil:

- només alertes públiques;
- prioritat a fonts oficials;
- etiquetatge d’estimacions.

Portal Bomber:

- alertes operatives;
- finalització de models;
- canvis de risc;
- canvis de rutes.

No enviïs una predicció com si fos una ordre oficial.

Implementa preferències d’usuari, silenciament i subscripció.

Crea tests de concurrència, reconnect, duplicació i permisos.

Criteris d’acceptació:

- actualització sense recarregar;
- cap alerta duplicada;
- cada alerta té font i hora;
- les alertes restringides no arriben a civils;
- els tests passen.
```

---

# Fase 13 — Integracions oficials restants

```text
Llegeix EspecificacioProjecte.md i la documentació creada per a integracions.

Implementa progressivament:

- Copernicus EFFIS;
- CAMS/GFAS;
- DGT DATEX II;
- MITECO;
- Servei Català de Trànsit;
- Trafikoa;
- fonts 112 i autonòmiques disponibles.

Per cada font:

1. revisa la documentació oficial;
2. revisa les condicions d’ús;
3. documenta cobertura;
4. documenta freqüència;
5. documenta retard;
6. documenta camps;
7. crea connector;
8. crea fixtures;
9. crea tests;
10. crea monitoratge;
11. crea runbook.

No implementis scraping fràgil sense documentar-lo.

Si una font no té API:

- documenta alternatives;
- separa HTML parser de la lògica;
- crea detecció de canvis d’estructura;
- crea alertes quan falla;
- conserva la font original.

No barregis fonts sense conservar procedència.

Criteris d’acceptació:

- cada connector és idempotent;
- cada connector té monitoratge;
- cada connector conserva originals;
- cada connector documenta limitacions;
- els tests passen.
```

---

# Fase 14 — Observabilitat, seguretat i hardening

```text
Llegeix EspecificacioProjecte.md i revisa tot el sistema com si s’hagués de desplegar en una prova pilot amb serveis d’emergència.

Implementa observabilitat completa:

- logs estructurats;
- OpenTelemetry;
- traces;
- Prometheus;
- Grafana;
- mètriques de connectors;
- mètriques de models;
- mètriques GIS;
- cues;
- latència;
- errors;
- dades antigues;
- dades absents.

Crea alertes operatives per:

- connector caigut;
- font retardada;
- cues acumulades;
- models fallits;
- base de dades lenta;
- geometries invàlides;
- rutes sense resposta;
- errors d’autenticació.

Seguretat:

- revisa secrets;
- CORS;
- CSP;
- HTTPS;
- headers;
- SSRF;
- SQL injection;
- XSS;
- CSRF;
- validació de fitxers;
- rate limiting;
- permisos;
- dependències;
- contenidors;
- backups;
- restauració;
- auditoria.

Executa:

- SAST;
- escaneig de dependències;
- escaneig d’imatges;
- tests de permisos;
- tests de càrrega bàsics;
- tests de recuperació.

Actualitza runbooks.

Criteris d’acceptació:

- dashboards funcionals;
- alertes provades;
- secrets fora del repositori;
- restauració documentada i provada;
- vulnerabilitats altes resoltes;
- tests passen.
```

---

# Fase 15 — CI/CD i desplegament

```text
Llegeix EspecificacioProjecte.md i prepara desplegaments reproduïbles.

Implementa CI/CD amb GitHub Actions.

Pipeline de pull request:

- lint;
- format;
- typecheck;
- tests;
- tests d’integració;
- migracions;
- build;
- escaneig;
- artefactes.

Pipeline de staging:

- build d’imatges;
- versionat;
- desplegament;
- migracions;
- smoke tests;
- rollback.

Producció:

- aprovació manual;
- backup previ;
- migracions segures;
- desplegament progressiu;
- verificació;
- rollback automàtic quan sigui possible.

Crea:

- configuració staging;
- configuració production;
- secrets documentats;
- estratègia de backup;
- estratègia de rollback;
- health checks;
- readiness;
- liveness;
- zero-downtime quan sigui viable.

No bloquegis el projecte en una plataforma cloud concreta si l’especificació no ho exigeix.

Criteris d’acceptació:

- staging es desplega automàticament;
- producció requereix aprovació;
- rollback documentat;
- migracions controlades;
- smoke tests funcionals.
```

---

# Prompt final — Auditoria tècnica completa

```text
Llegeix completament EspecificacioProjecte.md.

Revisa tot el repositori com si fossis responsable de donar l’aprovació tècnica per a una prova pilot amb ciutadania i serveis d’emergència.

No assumeixis que una funcionalitat funciona perquè existeix un fitxer o endpoint. Executa les comprovacions.

Avalua:

- compliment funcional;
- arquitectura;
- dades;
- traçabilitat;
- confiança;
- diferenciació oficial/observat/estimat;
- retard;
- connectors;
- backend;
- frontend Civil;
- frontend Bomber;
- GIS;
- fum;
- carreteres;
- routing;
- permisos;
- auditoria;
- seguretat;
- observabilitat;
- rendiment;
- accessibilitat;
- CI/CD;
- backups;
- documentació.

Executa:

- lint;
- tipatge;
- tests;
- integració;
- migracions;
- build;
- escaneig;
- smoke tests.

Crea un informe a:

docs/reviews/final-technical-review.md

Per cada problema indica:

- severitat;
- component;
- fitxer;
- impacte;
- reproducció;
- proposta;
- test necessari.

Corregeix els problemes crítics i alts quan no impliquin modificar els requisits.

Finalitza amb:

- estat general;
- completat;
- parcial;
- no implementat;
- riscos;
- deute tècnic;
- resultats dels tests;
- preparació per staging;
- preparació per pilot;
- veredicte:
  - aprovat;
  - aprovat amb condicions;
  - no aprovat.
```

---

# Prompt reutilitzable per a qualsevol fase

```text
Abans de treballar:

1. Llegeix EspecificacioProjecte.md.
2. Llegeix la documentació relacionada amb aquesta fase.
3. Inspecciona el codi actual.
4. Comprova què ja està implementat.
5. No reimplementis funcionalitats existents.
6. No modifiquis fora de l’abast sense necessitat.

Abans de codificar, mostra un pla breu amb:

- components afectats;
- fitxers previstos;
- migracions;
- riscos;
- tests.

Durant la implementació:

- mantén compatibilitat;
- conserva traçabilitat;
- afegeix tests;
- actualitza documentació;
- no introdueixis mocks a producció;
- no marquis stubs com a completats.

En finalitzar:

- executa lint;
- executa tipatge;
- executa tests;
- executa build;
- comprova migracions;
- corregeix errors;
- resumeix canvis;
- indica limitacions;
- no avancis de fase.
```
