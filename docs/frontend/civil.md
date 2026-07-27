# Civil Portal

The Civil portal is implemented at `/civil` and consumes only the public Civil API under `/civil/*`.

This portal is the active product priority. Development of the professional dashboard remains deferred until the Civil portal is accepted as publishable.

## Data Flow

The page uses TanStack Query to load:

- `/civil/incidents`
- `/civil/notices`
- `/civil/detections?format=geojson`
- `/civil/perimeters?format=geojson`
- `/civil/evacuations?format=geojson`
- `/civil/restrictions?format=geojson`
- `/civil/risk?format=geojson`
- `/civil/smoke?format=geojson`

No simulated data is rendered in production. Empty API responses become explicit empty states. The separate road-network layer is not requested or rendered by the current UI; public road impacts are presented under `Restriccions a Carreteres`.

## Map Layers

- FIRMS detections are static sensor footprints grouped into polygons that retain internal holes.
- A red, clickable FIRMS group pin is placed at an interior point and exposes count, oldest/newest detection and area in the popup.
- Original FIRMS hotspots can be enabled independently.
- Road restrictions follow locally resolved CNIG road geometry.
- Fire and environmental-obstruction restrictions are bright orange; other restrictions are translucent purple.
- The former dashed contextual road line is intentionally not displayed.
- Layer visibility is applied directly through MapLibre without reconstructing the map.

## Map Tiles

The default development basemap uses:

```text
NEXT_PUBLIC_MAP_TILE_URL=https://tile.openstreetmap.org/{z}/{x}/{y}.png
```

This is suitable for local development and modest testing. The URL is configurable because public production traffic
should use a tile provider with quotas, support, and a service-level expectation, or a self-hosted tile service.

## URL State

The portal synchronizes public state into the URL:

```text
/civil?bbox=-10,35,5,44&municipality=Girona&selected=...&lng=2.82&lat=41.98&z=8
```

The map viewport also writes `lng`, `lat`, and `z` so links preserve context. Viewport changes use the browser History API rather than Next.js navigation, so pan and zoom do not remount the page or refetch layers. TanStack Query keeps layer data fresh for five minutes and does not refetch on window focus.

## Municipality Search

Municipality search uses the public IGN-based ArcGIS service `municipios_espana`. The Civil API proxies this as:

```text
GET /civil/municipalities/search?q=Molins&limit=8
```

Each match returns the official name, INE code, centroid coordinates, attribution, and a padded `bbox`. Searching changes the map focus only; it does not hide or filter the statewide data already shown.

## Accessibility

Essential information is available outside the map:

- incident list;
- notices and timeline area;
- evacuation, restriction, and road counts;
- clickable map popups;
- source status;
- methodology;
- legend.

Interactive controls are native inputs and buttons with visible focus styles inherited from the global CSS.

## Degraded States

If a layer request fails, the portal keeps the rest of the page usable and shows a predictable error message. If a layer has no data, the corresponding panel stays visible with a zero count. A loading overlay communicates initial map-data loading.
