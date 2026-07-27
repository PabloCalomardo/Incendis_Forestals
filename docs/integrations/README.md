# Integracions

Aquest document reflecteix l'estat consolidat de les integracions. El desenvolupament ja no avanca per fases; la prioritat actual es el Dashboard Civil publicable.

## Estat

- NASA FIRMS: implementat amb API Area CSV, MAP_KEY per variable d'entorn, persistencia d'originals, dead-letter, reprocessament, deduplicacio i registre d'execucio.
- EFFIS: planificat, no implementat.
- AEMET: implementat amb OpenData, observacions, prediccio municipal horaria, raw i deduplicacio.
- DGT/NAP DATEX II: implementat com a connector principal estatal per restriccions/incidencies viaries; combina DGT v3.7, SCT i DT-GV.
- DGT/NAP Mapa de Trafico: implementat via connector eTraffic.
- DGT/NAP Mapa de Movilidad: recurs web registrat; pendent de connector descarregable estable.
- MITECO: planificat, no implementat.
- IGN/CNIG: cerca estatal de municipis i xarxa viaria IGR-RT 2026 local importada a PostGIS, amb trams i punts quilometrics oficials.
- OpenStreetMap: implementat connector Overpass per carreteres per area petita; extractes Geofabrik documentats per importacions grans.
- Proteccio Civil / CECAT: implementat connector d'avisos oficials de plans actius; no genera geometria d'evacuacio.

La implementacio de carreteres/restriccions queda tancada temporalment: DATEX aporta les afectacions i CNIG resol localment la forma de la carretera per nom i PK. Els serveis externs nomes actuen com a fallback.

## Requisits comuns

- credencials via variables d'entorn;
- retries i timeouts;
- persistencia de resposta original;
- deduplicacio;
- metriques;
- documentacio de llicencia, cobertura, retard i limitacions.
