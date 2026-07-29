# ES-Alert

ES-Alert es el sistema oficial de difusio Cell Broadcast del Sistema Nacional de Proteccio Civil. Els centres d'emergencies defineixen el risc, l'area afectada, la vigencia i les instruccions.

No hi ha un feed o API publica documentada per consultar totes les emissions ES-Alert actives. El visor RAN public mostra productes de risc, pero no exposa un arxiu public complet d'emissions ES-Alert. Per aquest motiu no es deriven alertes ES-Alert a partir d'AEMET ni de noticies.

## Registre autenticat

L'API interna accepta snapshots procedents d'un adaptador oficial autoritzat:

```text
POST /internal/ingestion/es-alert/sync
X-Internal-Token: ...
```

Cada alerta inclou identificador oficial, titol, instruccions, tipus de restriccio, autoritat emissora, dates d'emissio i caducitat, nivell i geometria GeoJSON `Polygon` o `MultiPolygon`.

Els missatges de prova es descarten. Els snapshots complets caduquen registres que ja no apareixen. Un snapshot complet buit requereix `allow_empty_snapshot=true` per evitar una desactivacio massiva causada per una ingesta fallida.

La resposta publica nomes mostra restriccions vigents:

```text
GET /civil/es-alerts?format=geojson
```
