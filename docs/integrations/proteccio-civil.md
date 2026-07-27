# Proteccio Civil / CECAT

Connector implementat a `app.ingestion.proteccio_civil.ProteccioCivilPlansConnector`.

## Font

Dataset public de la Generalitat:

`https://analisi.transparenciacatalunya.cat/api/v3/views/wj9c-j6vf/query.json?accessType=DOWNLOAD`

Contingut: estat dels plans de Proteccio Civil en prealerta, alerta o emergencia, amb fase, descripcio i, quan existeix, comunicat oficial CECAT.

## Sortida

El connector persisteix `OfficialNotice`.

No crea `EvacuationZone` ni `RestrictionZone`, perque la font publica no publica geometries exactes. Les restriccions textuals queden al cos de l'avis i es podran convertir mes endavant amb un parser de comunicats/noticies oficials.

## Configuracio

```env
PROTECCIO_CIVIL_PLANS_URL=https://analisi.transparenciacatalunya.cat/api/v3/views/wj9c-j6vf/query.json?accessType=DOWNLOAD
PROTECCIO_CIVIL_TIMEOUT_SECONDS=30
PROTECCIO_CIVIL_MAX_RETRIES=3
```

No cal API key.
