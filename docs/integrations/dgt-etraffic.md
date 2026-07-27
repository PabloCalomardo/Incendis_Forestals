# NAP Mapa de Trafico

Connector implementat a `app.ingestion.etraffic.DgtEtrafficConnector`.

## Font

Dataset NAP: `https://nap.dgt.es/dataset/mapa-de-trafico`

Aplicacio oficial: `https://etraffic.dgt.es/etrafficWEB/`

Endpoint utilitzat per la web oficial:

`POST https://etraffic.dgt.es/etrafficWEB/api/cache/getFilteredData`

## Sortida

Persisteix:

- `RestrictionZone` amb geometria `LineString` o `MultiLineString`;
- `RoadSegment` per cada linia del tracat;
- `RoadIncident` vinculat al primer segment.

## Configuracio

```env
ETRAFFIC_BASE_URL=https://etraffic.dgt.es/etrafficWEB/api
ETRAFFIC_PUBLIC_URL=https://etraffic.dgt.es/etrafficWEB/
ETRAFFIC_FILTERS_VIA=Carreteras cortadas,Tráfico lento,Circulación restringida,Desvíos y embolsamientos,Otras vialidades
ETRAFFIC_TIMEOUT_SECONDS=30
ETRAFFIC_MAX_RETRIES=3
```

No cal API key.
