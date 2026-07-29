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

## Cobertura estatal

Connector implementat a `app.ingestion.aemet_alerts.AemetAlertsConnector`.

Font oficial AEMET Meteoalerta, cobertura de tot Espanya i format CAP 1.2:

`https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAE_wah_RSS.xml`

El connector desa titular, descripcio, instruccions, vigencia, nivell groc/taronja/vermell i el `bbox` calculat a partir del poligon CAP. S'executa cada 10 minuts.

```env
AEMET_ALERTS_FEED_URL=https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAE_wah_RSS.xml
AEMET_ALERTS_TIMEOUT_SECONDS=30
AEMET_ALERTS_MAX_RETRIES=3
```

Fonts complementaries revisades:

- Pais Basc: Euskalmet `Alerts / Forecast` requereix registre gratuit i claus API/JWT. AEMET ja cobreix el territori estatal complet; Euskalmet queda com a futura capa autonomica de mes detall.
- RAN del Ministerio del Interior/CENEM: visor public a `https://ran-vmap.proteccioncivil.es/`, sense endpoint public documentat. No se'n consumeixen serveis interns ni es fa scraping.
