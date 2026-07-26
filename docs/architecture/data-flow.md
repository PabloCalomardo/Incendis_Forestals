# Flux de dades

## Flux principal

```mermaid
sequenceDiagram
    participant Source as Font externa
    participant Connector as Connector d'ingestio
    participant Raw as Object storage
    participant Run as DataIngestionRun
    participant Normalize as Normalitzacio
    participant DB as PostgreSQL/PostGIS
    participant Model as Models GIS/prediccio
    participant API as API
    participant UI as Portals

    Connector->>Source: fetch amb autenticacio i rate limit
    Source-->>Connector: resposta original
    Connector->>Raw: desa resposta original
    Connector->>Run: registra execucio, metriques i errors
    Connector->>Normalize: valida i transforma
    Normalize->>DB: persisteix dades amb procedencia
    DB->>Model: inputs versionats
    Model->>DB: resultats estimats amb execucio de model
    API->>DB: consulta filtrada per portal i permisos
    UI->>API: peticions amb filtres espacials/temporals
    API-->>UI: resposta amb font, edat, confiança i advertiments
```

## Etapes

1. Captura:
   Cada connector recupera dades externes amb autenticacio per variables d'entorn, timeouts, retries i idempotencia.

2. Conservacio original:
   La resposta bruta es desa abans de normalitzar-la per permetre auditoria, reprocessament i verificacio.

3. Validacio:
   Es comproven camps obligatoris, geometries, timestamps, unitats i cobertura.

4. Normalitzacio:
   Les dades es converteixen a formats interns, preservant CRS original, zona horaria original, data observada, publicada, rebuda i caducitat.

5. Persistencia:
   El domini conserva versions, procedencia, confidence score, metadades originals, hash de deduplicacio i timestamps.

6. Derivacio:
   Els motors geoespacials, de fum i routing creen resultats derivats. Aquests resultats no sobreescriuen dades originals ni oficials.

7. Publicacio:
   L'API exposa nomes els camps adequats a cada portal. El portal Civil rep informacio publica i el portal Bomber rep informacio operativa segons permisos.

## Procedencia i confiança

```mermaid
flowchart TD
    official[Official] --> confidence[Calcul de confiança]
    observed[Observed] --> confidence
    estimated[Estimated] --> confidence
    unverified[Unverified] --> confidence
    age[Edat i retard] --> confidence
    geometry[Qualitat geometrica] --> confidence
    agreement[Coherencia entre fonts] --> confidence
    confidence --> response[Resposta amb valor, categoria, factors i advertiments]
```

Les contradiccions entre fonts han de coexistir. La normalitzacio pot relacionar observacions, pero no ha d'eliminar registres contradictoris ni promoure estimacions a oficials.
