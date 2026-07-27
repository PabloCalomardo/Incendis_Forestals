# Deduplicacio

## Nivells

1. Connector: hash estable per font i payload.
2. Persistencia: consulta de `deduplication_hash` abans d'inserir.
3. Qualitat: relacions per proximitat sense fusionar originals.

## Proximitat

Per deteccions FIRMS, la Fase 5 crea `ObservationLink` quan dues deteccions:

- estan a menys de 2.5 km;
- estan separades per menys de 180 minuts.

Aixo no crea un incident oficial. Es una agrupacio per revisio i futures fases.

## Conservacio

Els originals queden a `original_metadata` i raw object storage. La deduplicacio evita duplicats evidents, pero no elimina contradiccions.
