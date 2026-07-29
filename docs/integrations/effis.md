# EFFIS Burnt Areas

Connector: `app.ingestion.effis.EffisBurntAreasConnector`.

## Producte triat

Descarrega SHAPEZIP oficial d'EFFIS, capa `ms:modis.ba.poly` de Rapid Damage Assessment / Burnt Areas:

`https://maps.effis.emergency.copernicus.eu/effis`

Proporciona poligons d'area cremada, superficie, dates, localitzacio administrativa i distribucio de cobertes del sol. El connector descarrega el Shapefile complet i conserva tots els camps DBF a `original_metadata.shapefile_attributes`.

Es un producte oficial de Copernicus/EFFIS, pero no un comunicat de Bombers o 112. No representa necessiariament el front actiu i no publica mitjans, maniobres ni estat operatiu de les tasques d'extincio. Es desa amb procedencia `official`, verificacio `partial` i `perimeter_kind=effis_official_burnt_area`.

## Configuracio

- `EFFIS_WFS_URL`: endpoint WFS.
- `EFFIS_TYPE_NAME`: `ms:modis.ba.poly`.
- `EFFIS_AREA_BBOX`: `west,south,east,north`; per defecte, Espanya.
- `EFFIS_TIMEOUT_SECONDS`: 300 segons; la descarrega completa supera els 200 MB.
- `EFFIS_MAX_RETRIES`: 3.

La seleccio espacial d'Espanya es fa localment contra `EFFIS_AREA_BBOX`. No es descarten registres per antiguitat: la interfície els separa en actuals, d'aquest any i historics.

- `Incendis actuals`: `FIREDATE` inferior a 7 dies; visible per defecte.
- `Incendis d'aquest any`: entre 7 i 365 dies; ocult per defecte.
- `Historic d'incendis`: 365 dies o mes; ocult per defecte.

Les franges es filtren a PostGIS abans de retornar GeoJSON. L'historic complet no es descarrega al navegador fins que l'usuari activa la capa.

## Execucio

Manual:

```http
POST /internal/ingestion/effis/burnt-areas/run
X-Internal-Token: ...
```

Celery: `ingestion.run_effis_burnt_areas`, cada dia, alineat amb l'actualitzacio del producte.

La ingesta es idempotent per identificador EFFIS. Una geometria o `LASTUPDATE` nou actualitza el perimetre existent. Una resposta buida no elimina dades previes. Errors HTTP, timeouts o SHAPEZIP invalid generen una execucio fallida i no substitueixen els perimetres guardats.

Els perimetres recents formen incidents canonics. Poligons contemporanis i proxims es poden agrupar segons una distancia
que creix amb l'area agregada, coincidencia territorial, hashtags i evidencies OSINT. La distancia sola no es suficient.
El reconciliador agrega publicacions i FIRMS compatibles, mantenint totes les evidencies originals.

La data d'extincio nomes es mostra quan una font valida confirma l'estat extingit i el poligon ha estat actualitzat dins
dels tres dies anteriors. L'antiguitat o falta d'actualitzacio mai crea una extincio. Popup i detall mostren resum, hashtags, cronologia, FIRMS, fonts i tots els
atributs originals del Shapefile. El farciment gris permet seleccionar qualsevol punt interior del perimetre.

## Llicencia i atribucio

Contingut de la Unio Europea sota Creative Commons Attribution 4.0, llevat que el producte indiqui una altra cosa. Atribucio desada: `European Forest Fire Information System (EFFIS), European Commission`.

Referencies:

- https://forest-fire.emergency.copernicus.eu/applications/data-and-services
- https://forest-fire.emergency.copernicus.eu/downloads-instructions
- https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/rapid-damage-assessment
- https://forest-fire.emergency.copernicus.eu/about-effis/data-license
