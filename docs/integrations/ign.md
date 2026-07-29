# IGN/CNIG

## Productes actius

- Servei oficial `municipios_espana`: cerca i geocodificacio municipal amb codi INE, centre i limits.
- IGR-RT 2026 `España por modos`: `rt_tramo_vial` i `rt_ppkk_p` importats a PostGIS com `cnig_road_segments` i `cnig_road_kilometers`.
- OGC API `roadlink`: connector complementari limitat per `bbox`.

Importacio local:

```powershell
npm run roads:import
```

La primera execucio descarrega aproximadament 500 MB comprimits i extreu aproximadament 1,5 GB. `data/cnig/` queda fora de Git.

## Resolucio DATEX

Les incidencies amb `road_ref` es resolen contra la xarxa local. Amb PK, els punts quilometrics fixen els extrems. El resolutor intenta el graf de trams de la mateixa carretera i, si cal, PostGIS fa `ST_LineMerge` i n'extreu la subseccio corresponent. Funciona encara que la taula importada no tingui clau primaria.

Un lock consultiu per carretera evita reparacions concurrents. La tasca d'enriquiment actualitza `RestrictionZone` i `RoadSegment`; DGT PK, Overpass, OSRM i les coordenades DATEX queden com a fallbacks etiquetats.

Cas verificat: `TV-2042` va passar d'una recta de 2 punts/3.963 m a una geometria CNIG de 963 punts/4.032 m.

## Configuracio

`IGN_WFS_BASE_URL`, `IGN_TRANSPORT_TYPENAME`, `IGN_AREA_BBOX`, `IGN_FEATURE_LIMIT`, `IGN_TIMEOUT_SECONDS` i `IGN_MAX_RETRIES`.

## Limitacions

- La importacio necessita diversos GB lliures.
- Elevacio, MDT i cartografia base requereixen pipelines separats.
- Els noms de col.leccions externes poden canviar; son configurables.
