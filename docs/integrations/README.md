# Integracions

Estat detallat: [`../current-state.md`](../current-state.md).

## Actives

- **NASA FIRMS**: deteccions cada 15 minuts, raw, deduplicacio, reprocessament i cronologia diaria.
- **EFFIS Burnt Areas**: SHAPEZIP diari, atributs complets i perimetres canonics.
- **AEMET OpenData**: observacions i prediccio municipal horaria.
- **AEMET CAP/Meteoalerta**: avisos groc/taronja/vermell per tot Espanya.
- **DGT/SCT/DT-GV DATEX II**: incidencies viaries cada 5 minuts.
- **DGT eTraffic**: font complementaria de transit.
- **IGN/CNIG**: municipis oficials i xarxa IGR-RT local per geometria viaria.
- **OpenStreetMap**: fallback Overpass per arees petites.
- **Proteccio Civil/CECAT**: plans actius de Catalunya.
- **ES-Alert**: registre autenticat i reconstruccio OSINT d'evidencies publiques.
- **OSINT**: portals 112, organismes, RSS, Nitter, X amb credencials i revisio humana.
- **Aeronaus d'emergencia**: OpenSky i Airplanes.live creuats amb dataset OSINT local enriquit amb `icao24`.

## Pendents o limitades

- **MITECO**: no implementat; consulta [`miteco.todo.md`](miteco.todo.md).
- **Mapa de Movilidad DGT**: recurs registrat, sense endpoint descarregable estable.
- **X**: necessita Bearer Token; Nitter es la passarel.la principal i TwitterViewer queda per revisio humana.
- **ES-Alert**: no existeix un feed public complet; no es pot garantir exhaustivitat.
- **EFFIS**: no publica tasques d'extincio ni confirma l'estat operatiu.
- **Aeronaus**: la cobertura depen dels feeds ADS-B publics; Flightradar24 pot mostrar vols que OpenSky/Airplanes.live no exposen en aquell moment.

## Regles comunes

Credencials via entorn, raw preservat, retries/timeouts, deduplicacio, procedencia, metriques i registre d'execucio. Una execucio fallida, parcial o anormalment buida no reemplaça l'ultima instantania valida.
