# Civil UI

The Civil UI prioritizes clear public information over operational detail.

## Visual Rules

- Official data uses solid shapes or lines.
- Estimated data uses dashed lines, hollow/neutral symbols, warning copy, and lower opacity when stale.
- Observed satellite detections use fixed sensor-footprint polygons, interior group pins and an optional original-hotspot layer.
- Old data is dimmed and labelled through traceability warnings.
- Color is never the only signal: line style, text labels, opacity, and badges reinforce meaning.

## Layout

Mobile first:

- map first;
- controls and detail remain available below as a bottom-flow panel;
- all essential information is present in lists.

Desktop:

- compact 300 px left-side controls that fit their content without vertical stretching;
- map and public sections on the right, with the map occupying about 72% of viewport height;
- dense but readable operational-public layout.

## Legend

The legend is always rendered next to the map controls. It explains:

- observed detections;
- official perimeters;
- estimated perimeters;
- FIRMS areas, red group pins and original hotspots;
- road restrictions: orange for fire/environmental obstruction and translucent purple for all others;
- stale data.

The dashed contextual road network is intentionally absent. Roads and restrictions share the public category `Restriccions a Carreteres`.

## Interaction And Performance

- Feature details open in a popup anchored to the selected map geometry.
- Municipality search performs a map zoom and does not filter other records.
- Layer toggles update MapLibre source visibility in place.
- Pan and zoom do not trigger API reloads or Next.js navigation.
- Public responses are cached client-side for five minutes.

## Copy

The portal avoids presenting estimates as facts. When an item is estimated or has warnings, the detail panel states that
it must not be treated as an official notice.
