# Model de confianca

## Objectiu

La confianca es calcula fora dels connectors. Cap connector converteix una dada en oficial ni valida una prediccio per si mateix.

## Versio

`confidence-v1`

## Factors

- `source_authority`: fiabilitat inicial de la font (`DataSource.reliability_score`).
- `officiality`: oficial, observada, estimada o no verificada.
- `freshness`: edat de la dada.
- `delay`: retard entre publicacio/observacio i recepcio.
- `geometry_quality`: geometria existent i coordenades valides.
- `input_availability`: camps de linatge disponibles.
- `coherence`: coherencia basica de valors.

## Penalitzacions

- dades antigues;
- retard elevat;
- geometria invalida;
- font no verificada.

## Categories

- `high`: >= 0.8
- `medium`: >= 0.55
- `low`: >= 0.3
- `very_low`: < 0.3

## Garanties

- Una dada `estimated` conserva `provenance=estimated`.
- Una prediccio no passa a `official` per tenir score alt.
- El resultat guarda factors, penalitzacions, avisos, timestamp i versio d'algoritme a `confidence_assessments`.
