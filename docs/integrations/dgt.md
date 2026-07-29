# DGT/NAP

## Connectors actius

- `app.ingestion.datex.DatexTrafficConnector`: DATEX II d'incidencies DGT, SCT i DT-GV.
- `app.ingestion.etraffic.DgtEtrafficConnector`: NAP Mapa de Trafico.

## Datasets NAP utilitzats

- Incidencias DGT DATEX2 v3.7.
- Incidencias SCT.
- Incidencias DT-GV.
- Mapa de Trafico.
- Mapa de Movilidad, registrat com a recurs web.

## Configuracio

```env
DATEX_FEED_URLS=https://nap.dgt.es/dataset/77be854a-6911-47dc-ba4c-b13067a50552/resource/1d36ea74-593d-4e45-acfa-fb8db5a460bc/download/datex2_v37.xml,https://infocar.dgt.es/datex2/sct/SituationPublication/all/content.xml,https://infocar.dgt.es/datex2/dt-gv/SituationPublication/all/content.xml
DATEX_TIMEOUT_SECONDS=30
DATEX_MAX_RETRIES=3
ETRAFFIC_BASE_URL=https://etraffic.dgt.es/etrafficWEB/api
ETRAFFIC_PUBLIC_URL=https://etraffic.dgt.es/etrafficWEB/
MOBILITY_MAP_URL=http://mapamovilidad.dgt.es/
```

No cal API key.

## Geometria i proteccio de dades

La instantania DATEX nomes es publica quan la ingestio acaba coherentment. Errors de xarxa, parsing, deadlock o un buit
anomal no desactiven les restriccions de l'ultima execucio valida.

Les linies es reconstrueixen amb IGR-RT/CNIG local per carretera i PK. Un worker d'enriquiment revisa geometries de baixa
fidelitat cada minut, amb lock consultiu per `road_ref`. El fallback PostGIS fusiona trams i extreu la subseccio natural;
les coordenades inicial/final DATEX son l'ultim recurs i queden identificades a `geometry_strategy`.
