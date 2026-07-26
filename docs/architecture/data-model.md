# Model de dades

Fase 2 implementa el domini persistent base. El model preserva originals, versions, procedencia i prediccions traçables. Les geometries internes usen PostGIS amb SRID 4326, mantenint `original_crs` quan la font arriba amb un CRS diferent.

## Entitats

```mermaid
erDiagram
    DataSource ||--o{ DataIngestionRun : records
    DataSource ||--o{ Incident : provides
    DataSource ||--o{ FireDetection : provides
    DataSource ||--o{ FirePerimeter : provides
    DataSource ||--o{ OfficialNotice : publishes
    DataSource ||--o{ RoadSegment : provides
    Incident ||--o{ IncidentVersion : versions
    Incident ||--o{ FireDetection : groups
    Incident ||--o{ FirePerimeter : has
    Incident ||--o{ OfficialNotice : references
    Incident ||--o{ EvacuationZone : affects
    Incident ||--o{ RestrictionZone : restricts
    Incident ||--o{ RoadIncident : affects
    RoadSegment ||--o{ RoadIncident : has
    ModelExecution ||--o{ SmokeForecast : produces
    ModelExecution ||--o{ RiskForecast : produces
    Role ||--o{ User : grants
    User ||--o{ AuditEvent : performs

    DataSource {
      uuid id
      string name
      enum source_type
      string authority
      jsonb source_metadata
    }
    Incident {
      uuid id
      geometry geometry
      enum provenance
      enum status
      float confidence
      int version
      jsonb original_metadata
    }
    IncidentVersion {
      uuid id
      uuid incident_id
      int version
      jsonb snapshot
    }
    ModelExecution {
      uuid id
      string model_name
      string model_version
      jsonb input_refs
      string input_hash
    }
    SmokeForecast {
      uuid id
      uuid model_execution_id
      geometry geometry
      enum provenance
      int horizon_hours
      float uncertainty
    }
```

## Camps comuns

Les entitats amb traçabilitat incorporen:

- `id`
- `source_id`
- `external_id`
- `provenance`
- `observed_at`
- `published_at`
- `received_at`
- `expires_at`
- `verification_status`
- `confidence`
- `version`
- `original_metadata`
- `deduplication_hash`
- `created_at`
- `updated_at`
- `deleted_at`

Les entitats geoespacials incorporen:

- `geometry`
- `original_crs`
- index GIST sobre `geometry`

## Regles d'integritat

- `provenance` admet `official`, `observed`, `estimated` i `unverified`.
- `confidence` queda acotada entre 0 i 1 quan existeix.
- `smoke_forecasts` i `risk_forecasts` no poden tenir procedencia oficial.
- Totes les prediccions apunten a `model_executions`.
- `incident_versions` conserva snapshots per no sobreescriure historia.
- `deleted_at` habilita soft delete sense perdre originals.

## Indexs

- GIST: totes les taules amb `geometry`.
- Temporals: `observed_at`, `published_at`, `received_at`, `expires_at`.
- Procedencia: `provenance`.
- Deduplicacio: `deduplication_hash`.
- Model: `model_name`, `model_version`, `input_hash`.
- Auditoria: `user_id`, `occurred_at`, `resource_type`, `resource_id`.
