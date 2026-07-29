# Monitor OSINT d'emergencies

## Abast

Reconstrueix incidents a partir de publicacions publiques. No afirma que existeixi un registre oficial complet
d'ES-Alert. Conserva cada evidencia, l'agrupa en incidents i en calcula la cronologia.

Fonts per defecte:

- sala de premsa del Ministeri de l'Interior;
- portals oficials de Proteccio Civil o 112 de les 17 comunitats i Ceuta/Melilla;
- X API v2, si `X_BEARER_TOKEN` esta configurat;
- feeds RSS de Nitter per als perfils institucionals catalogats, com a passarel·la automatica principal;
- ingesta normalitzada per incorporar RSS, APIs, notes de premsa, ajuntaments, policies i mitjans addicionals.

El cataleg editable es `apps/api/app/ingestion/osint_sources.json`. Una font que falla queda registrada com a error
parcial i no elimina ni invalida dades anteriors.

## Classificacio

Idiomes: catala, castella, eusquera i gallec, amb `und` quan no hi ha prou senyal.

Esdeveniments: ordres/ampliacions/aixecaments de confinament o evacuacio, activacions i desactivacions de plans,
declaracions d'emergencia i estats ES-Alert.

Estats ES-Alert separats: `announced`, `confirmed_sent`, `presumed_received`, `cancelled`, `test` i `not_applicable`.
Una recepcio individual mai es converteix en enviament oficial confirmat.

Prioritat: oficial (`1`), mitja fiable (`2`), testimonis independents coincidents (`3`) i publicacio individual (`4`).
Els nivells 3/4 i els casos ambigus entren a revisio humana.

## Geometria

Els toponims explicits es resolen contra limits municipals oficials IGN. Es desen geometria, metode d'inferencia,
precisio i identificadors administratius. Sense coincidencia exacta, la geometria queda `null`: no es generen buffers,
centroides ni poligons artificials.

La resolucio prioritza el nom compost mes llarg i el context provincia/comunitat. Una mencio a `Santa Coloma de Queralt`
no genera coincidencies per altres municipis `Santa Coloma`. Capitals provincials utilitzades com a capçalera en resums
no es confonen amb els municipis descrits despres de la fletxa. `Agost` esta exclosa del reconeixement textual per evitar
interpretar el mes com el municipi valencia.

## Execucio

Celery Beat executa `ingestion.run_emergency_osint` cada 300 segons.

```env
X_BEARER_TOKEN=
OSINT_X_OFFICIAL_ACCOUNTS=proteccioncivil,interiorgob,emergenciescat,112cv,112_sosdeiak
OSINT_X_QUERY=("ES-Alert" OR confinamiento OR confinament OR evacuacion OR evacuacio) -is:retweet
```

X necessita una aplicacio de desenvolupador i Bearer Token. Sense credencial, la resta de fonts continua funcionant.
Nitter no necessita credencial i es consulta per `/{handle}/rss`; la URL publica apunta a Nitter i la URL canonica de X
es conserva nomes com a metadada interna.

Les publicacions no vinculades a un incendi es mostren en blau amb descripcio breu i dades operatives extretes, com el
nombre de dotacions mobilitzades. TwitterViewer es nomes una ajuda manual quan Nitter o X no son accessibles.

## Reconciliacio amb EFFIS i FIRMS

Els perimetres EFFIS recents son la identitat canonica de l'incendi. Cada publicacio es puntua individualment contra
tots els perimetres recents mitjancant hashtag especific `#IF...`, municipi o zona afectada exactes, interseccio
geografica i proximitat temporal. La proximitat o la provincia per si soles no son suficients.

Les deteccions FIRMS situades fins a 5 km del perimetre i dins la finestra temporal queden vinculades al mateix
incident. Les publicacions i deteccions vinculades deixen de representar-se com incidents independents, pero es
conserven a la cronologia i al detall del poligon. Cada execucio reconstrueix les associacions recents des de zero per
evitar que sobrevisquin vincles obsolets.

## API

```text
GET   /civil/osint/incidents?window_hours=24&active_or_recent=true
GET   /civil/osint/incidents?window_hours=24&format=geojson
GET   /civil/osint/incidents/{incident_id}
GET   /civil/osint/review-queue
POST  /internal/ingestion/osint/run
POST  /internal/ingestion/osint/publications
GET   /internal/ingestion/osint/review
PATCH /internal/ingestion/osint/review/{publication_id}
GET   /internal/ingestion/emergency_osint/status
```

## Limitacions

- X no es consulta sense credencial i esta subjecte als limits i al pla de l'API.
- TwitterViewer nomes s'utilitza per revisio humana. Els seus termes prohibeixen l'scraping automatitzat i la recollida massiva.
- Alguns portals oficials bloquegen robots o canvien HTML; la ingesta queda `partial` i no substitueix dades bones per un buit.
- El monitor reconstrueix evidencia publica; no equival al registre intern dels centres 112.
