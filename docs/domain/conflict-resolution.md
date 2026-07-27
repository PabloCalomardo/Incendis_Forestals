# Resolucio de conflictes

## Principi

Les contradiccions no s'eliminen. Es registren a `data_conflicts` amb evidencies i severitat.

## Conflictes inicials

- `road_status_opposite`: un mateix tram te `official_closure` i `insufficient_data`.

## Politica

- La dada oficial no s'ha de substituir per una estimacio.
- La dada estimada no pot tapar una ordre oficial.
- Les contradiccions han de ser visibles per API interna de tracabilitat.

## Inspeccio

Endpoint intern:

```text
GET /internal/quality/trace/{resource_type}/{resource_id}
```

Retorna font, temporalitat, originals, confidence assessments, links i conflictes.
