"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type { StyleSpecification } from "maplibre-gl";
import type { CivilFeature, CivilFeatureCollection, CivilLayerName } from "@/lib/api/civil";
import { useMapViewportStore } from "@/lib/state/map-store";

type MapShellProps = {
  portal: "civil" | "bomber";
  civilLayers?: Partial<Record<CivilLayerName, CivilFeatureCollection>>;
  visibleLayers?: Partial<Record<CivilLayerName, boolean>>;
  bbox?: string;
  showFirmHotspots?: boolean;
  isLoading?: boolean;
  onFeatureSelect?: (featureId: string) => void;
};

const emptyFeatureCollection: CivilFeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

const MAP_TILE_URL =
  process.env.NEXT_PUBLIC_MAP_TILE_URL ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const MAP_TILE_ATTRIBUTION =
  process.env.NEXT_PUBLIC_MAP_TILE_ATTRIBUTION ?? "&copy; OpenStreetMap contributors";

const selectableLayers = [
  "detections-heat-area",
  "detections-pin",
  "detections-pin-label",
  "perimeters-official",
  "perimeters-estimated",
  "evacuations-fill",
  "restrictions-line",
  "restrictions-point",
  "risk-fill",
  "smoke-fill",
];

const layerIdsBySource: Record<CivilLayerName, string[]> = {
  detections: [
    "detections-heat-area",
    "detections-area-outline",
    "detections-pin",
    "detections-pin-label",
  ],
  perimeters: ["perimeters-official", "perimeters-estimated"],
  evacuations: ["evacuations-fill"],
  restrictions: ["restrictions-casing", "restrictions-line", "restrictions-point"],
  roads: [],
  risk: ["risk-fill"],
  smoke: ["smoke-fill"],
};

function getLayerData(
  civilLayers: Partial<Record<CivilLayerName, CivilFeatureCollection>> | undefined,
  layer: CivilLayerName,
) {
  return civilLayers?.[layer] ?? emptyFeatureCollection;
}

function sourceVisibility(
  visibleLayers: Partial<Record<CivilLayerName, boolean>> | undefined,
  layer: CivilLayerName,
) {
  return visibleLayers?.[layer] === false ? "none" : "visible";
}

function isLayerVisible(
  visibleLayers: Partial<Record<CivilLayerName, boolean>> | undefined,
  layer: CivilLayerName,
) {
  return visibleLayers?.[layer] !== false;
}

type FirmPoint = {
  id?: string;
  longitude: number;
  latitude: number;
  footprint_size_meters?: number;
};

function firmPoints(feature: CivilFeature): FirmPoint[] {
  const rawPoints = feature.properties.properties.firm_points_json;
  if (typeof rawPoints === "string") {
    try {
      const parsed = JSON.parse(rawPoints) as unknown;
      if (Array.isArray(parsed)) {
        return parsed.flatMap((point) => {
          if (
            typeof point === "object" &&
            point !== null &&
            Number.isFinite(Number((point as FirmPoint).longitude)) &&
            Number.isFinite(Number((point as FirmPoint).latitude))
          ) {
            return [
              {
                id: String((point as FirmPoint).id ?? feature.properties.id),
                longitude: Number((point as FirmPoint).longitude),
                latitude: Number((point as FirmPoint).latitude),
                footprint_size_meters: Number((point as FirmPoint).footprint_size_meters ?? 700),
              },
            ];
          }
          return [];
        });
      }
    } catch {
      return [];
    }
  }

  const longitude = Number(feature.properties.properties.longitude);
  const latitude = Number(feature.properties.properties.latitude);
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) {
    return [];
  }
  return [
    {
      id: feature.properties.id,
      longitude,
      latitude,
      footprint_size_meters: Number(feature.properties.properties.footprint_size_meters ?? 700),
    },
  ];
}

function detectionPointCollection(collection: CivilFeatureCollection): CivilFeatureCollection {
  const features: CivilFeature[] = [];
  collection.features.forEach((feature) => {
    firmPoints(feature).forEach((point, index) => {
      features.push({
        ...feature,
        id: `${feature.id ?? feature.properties.id}-point-${index}`,
        properties: {
          ...feature.properties,
          id: String(point.id ?? `${feature.properties.id}-point-${index}`),
          properties: {
            ...feature.properties.properties,
            longitude: point.longitude,
            latitude: point.latitude,
            footprint_size_meters: point.footprint_size_meters ?? 700,
          },
        },
        geometry: { type: "Point", coordinates: [point.longitude, point.latitude] },
      });
    });
  });
  return {
    type: "FeatureCollection",
    features,
  };
}

function ringAreaAndCentroid(ring: number[][]) {
  let twiceArea = 0;
  let centroidX = 0;
  let centroidY = 0;
  for (let index = 0; index < ring.length - 1; index += 1) {
    const current = ring[index];
    const next = ring[index + 1];
    const cross = current[0] * next[1] - next[0] * current[1];
    twiceArea += cross;
    centroidX += (current[0] + next[0]) * cross;
    centroidY += (current[1] + next[1]) * cross;
  }
  if (twiceArea === 0) {
    return null;
  }
  return {
    area: twiceArea / 2,
    centroid: [centroidX / (3 * twiceArea), centroidY / (3 * twiceArea)] as [number, number],
  };
}

function polygonCentroid(rings: number[][][]) {
  let weightedX = 0;
  let weightedY = 0;
  let totalWeight = 0;
  rings.forEach((ring, index) => {
    const result = ringAreaAndCentroid(ring);
    if (!result) {
      return;
    }
    const weight = (index === 0 ? 1 : -1) * Math.abs(result.area);
    weightedX += result.centroid[0] * weight;
    weightedY += result.centroid[1] * weight;
    totalWeight += weight;
  });
  if (totalWeight === 0) {
    return rings[0]?.[0] as [number, number] | undefined;
  }
  return [weightedX / totalWeight, weightedY / totalWeight] as [number, number];
}

function featureCentroid(feature: CivilFeature) {
  const labelLongitude = Number(feature.properties.properties.label_longitude);
  const labelLatitude = Number(feature.properties.properties.label_latitude);
  if (Number.isFinite(labelLongitude) && Number.isFinite(labelLatitude)) {
    return [labelLongitude, labelLatitude] as [number, number];
  }
  if (feature.geometry?.type === "Point") {
    return feature.geometry.coordinates as [number, number];
  }
  if (feature.geometry?.type === "Polygon") {
    return polygonCentroid(feature.geometry.coordinates);
  }
  if (feature.geometry?.type === "MultiPolygon") {
    let bestPolygon = feature.geometry.coordinates[0];
    let bestArea = 0;
    feature.geometry.coordinates.forEach((polygon) => {
      const area = Math.abs(ringAreaAndCentroid(polygon[0])?.area ?? 0);
      if (area > bestArea) {
        bestArea = area;
        bestPolygon = polygon;
      }
    });
    return bestPolygon ? polygonCentroid(bestPolygon) : undefined;
  }
  const points = firmPoints(feature);
  if (points.length === 0) {
    return undefined;
  }
  return [
    points.reduce((sum, point) => sum + point.longitude, 0) / points.length,
    points.reduce((sum, point) => sum + point.latitude, 0) / points.length,
  ] as [number, number];
}

function detectionPinCollection(collection: CivilFeatureCollection): CivilFeatureCollection {
  const pins = collection.features.flatMap((feature, index) => {
    const centroid = featureCentroid(feature);
    if (!centroid) {
      return [];
    }
    return [
      {
        type: "Feature" as const,
        id: `${feature.properties.id}-pin-${index}`,
        geometry: { type: "Point" as const, coordinates: centroid },
        properties: {
          ...feature.properties,
          id: feature.properties.id,
          properties: {
            ...feature.properties.properties,
            detection_count: Number(feature.properties.properties.detection_count ?? 1),
          },
        },
      },
    ];
  });
  return { type: "FeatureCollection", features: pins };
}

function escapeHtml(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function compactValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  return String(value);
}

function popupTitle(feature: CivilFeature) {
  const properties = feature.properties.properties;
  return (
    compactValue(properties.name) ??
    compactValue(properties.title) ??
    compactValue(properties.sensor) ??
    feature.properties.data_type
  );
}

function popupRows(feature: CivilFeature) {
  const properties = feature.properties.properties;
  const rows: Array<[string, unknown]> = [
    ["Font", feature.properties.source.name],
    ["Causa", properties.cause],
    ["Carretera", properties.road_ref],
    ["PK", properties.kilometer_range],
    ["Carril", properties.affected_lane],
    ["Sentit", properties.direction],
    ["Nivell", properties.service_level],
    ["Provincia", properties.province],
    ["Municipis", properties.municipalities],
    ["Deteccions", properties.detection_count],
    ["Mes antiga", properties.oldest_detection_at],
    ["Mes nova", properties.newest_detection_at],
    ["Area", properties.focus_area_square_meters ? `${properties.focus_area_square_meters} m2` : null],
    ["Sensor", properties.sensor],
    ["FRP", properties.frp_mw ? `${properties.frp_mw} MW` : null],
  ];
  return rows.flatMap(([label, value]) => {
    const compact = compactValue(value);
    return compact ? [[label, compact] as [string, string]] : [];
  });
}

function popupHtml(feature: CivilFeature) {
  const rows = popupRows(feature)
    .map(
      ([label, value]) =>
        `<div class="map-popup-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`,
    )
    .join("");
  return `<div class="map-popup"><h3>${escapeHtml(popupTitle(feature))}</h3>${rows}</div>`;
}

export function MapShell({
  portal,
  civilLayers,
  visibleLayers,
  bbox,
  showFirmHotspots = true,
  isLoading = false,
  onFeatureSelect,
}: MapShellProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const featureIndexRef = useRef<Map<string, CivilFeature>>(new Map());
  const onFeatureSelectRef = useRef(onFeatureSelect);
  const [mapWarning, setMapWarning] = useState<string | null>(null);
  const setViewport = useMapViewportStore((state) => state.setViewport);

  useEffect(() => {
    onFeatureSelectRef.current = onFeatureSelect;
  }, [onFeatureSelect]);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const baseStyle = {
      version: 8,
      glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
      sources: {
        "osm-basemap": {
          type: "raster",
          tiles: [MAP_TILE_URL],
          tileSize: 256,
          attribution: MAP_TILE_ATTRIBUTION,
        },
        "local-grid": {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: {},
                geometry: {
                  type: "MultiLineString",
                  coordinates: [
                    [
                      [-10, 36],
                      [4, 36],
                    ],
                    [
                      [-10, 38],
                      [4, 38],
                    ],
                    [
                      [-10, 40],
                      [4, 40],
                    ],
                    [
                      [-10, 42],
                      [4, 42],
                    ],
                    [
                      [-10, 44],
                      [4, 44],
                    ],
                    [
                      [-10, 36],
                      [-10, 44],
                    ],
                    [
                      [-6, 36],
                      [-6, 44],
                    ],
                    [
                      [-2, 36],
                      [-2, 44],
                    ],
                    [
                      [2, 36],
                      [2, 44],
                    ],
                  ],
                },
              },
            ],
          },
        },
        "civil-detections": {
          type: "geojson",
          data: emptyFeatureCollection,
        },
        "civil-detection-points": {
          type: "geojson",
          data: emptyFeatureCollection,
        },
        "civil-detection-pins": {
          type: "geojson",
          data: emptyFeatureCollection,
        },
        "civil-perimeters": {
          type: "geojson",
          data: emptyFeatureCollection,
        },
        "civil-evacuations": {
          type: "geojson",
          data: emptyFeatureCollection,
        },
        "civil-restrictions": {
          type: "geojson",
          data: emptyFeatureCollection,
        },
        "civil-roads": {
          type: "geojson",
          data: emptyFeatureCollection,
        },
        "civil-risk": {
          type: "geojson",
          data: emptyFeatureCollection,
        },
        "civil-smoke": {
          type: "geojson",
          data: emptyFeatureCollection,
        },
      },
      layers: [
        {
          id: "grid-lines",
          type: "line",
          source: "local-grid",
          paint: {
            "line-color": portal === "civil" ? "#c9d8ce" : "#283843",
            "line-width": 1,
          },
        },
        {
          id: "osm-basemap",
          type: "raster",
          source: "osm-basemap",
          paint: {
            "raster-opacity": portal === "civil" ? 0.72 : 0.35,
          },
        },
        {
          id: "risk-fill",
          type: "fill",
          source: "civil-risk",
          layout: { visibility: "visible" },
          paint: {
            "fill-color": [
              "match",
              ["get", "category", ["get", "properties"]],
              "high",
              "#b42318",
              "medium",
              "#c77700",
              "#6d8f3f",
            ],
            "fill-opacity": ["case", ["==", ["get", "is_current"], false], 0.16, 0.28],
          },
        },
        {
          id: "smoke-fill",
          type: "fill",
          source: "civil-smoke",
          layout: { visibility: "visible" },
          paint: {
            "fill-color": "#7a8791",
            "fill-opacity": ["case", ["==", ["get", "provenance"], "estimated"], 0.2, 0.12],
          },
        },
        {
          id: "perimeters-official",
          type: "line",
          source: "civil-perimeters",
          filter: ["!=", ["get", "provenance"], "estimated"],
          layout: { visibility: "visible" },
          paint: {
            "line-color": "#8a2f16",
            "line-width": 3,
            "line-opacity": ["case", ["==", ["get", "is_current"], false], 0.35, 0.9],
          },
        },
        {
          id: "perimeters-estimated",
          type: "line",
          source: "civil-perimeters",
          filter: ["==", ["get", "provenance"], "estimated"],
          layout: { visibility: "visible" },
          paint: {
            "line-color": "#8a2f16",
            "line-width": 3,
            "line-dasharray": [1.2, 1.2],
            "line-opacity": ["case", ["==", ["get", "is_current"], false], 0.25, 0.7],
          },
        },
        {
          id: "evacuations-fill",
          type: "fill",
          source: "civil-evacuations",
          layout: { visibility: "visible" },
          paint: {
            "fill-color": "#f2c14e",
            "fill-opacity": ["case", ["==", ["get", "is_current"], false], 0.18, 0.34],
          },
        },
        {
          id: "restrictions-casing",
          type: "line",
          source: "civil-restrictions",
          filter: ["!=", ["geometry-type"], "Point"],
          layout: { visibility: "visible", "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": [
              "case",
              [
                "any",
                ["in", "incendi", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "incendio", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "obstacle ambiental", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "environmentalobstruction", ["downcase", ["to-string", ["get", "cause_type", ["get", "properties"]]]]],
              ],
              "#7c2d12",
              "#3b0764",
            ],
            "line-width": ["interpolate", ["linear"], ["zoom"], 5, 5, 10, 8, 14, 12],
            "line-opacity": [
              "case",
              ["==", ["get", "is_current"], false],
              0.2,
              [
                "any",
                ["in", "incendi", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "incendio", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "obstacle ambiental", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "environmentalobstruction", ["downcase", ["to-string", ["get", "cause_type", ["get", "properties"]]]]],
              ],
              0.82,
              0.3,
            ],
          },
        },
        {
          id: "restrictions-line",
          type: "line",
          source: "civil-restrictions",
          filter: ["!=", ["geometry-type"], "Point"],
          layout: { visibility: "visible", "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": [
              "case",
              [
                "any",
                ["in", "incendi", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "incendio", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "obstacle ambiental", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "environmentalobstruction", ["downcase", ["to-string", ["get", "cause_type", ["get", "properties"]]]]],
              ],
              "#ff7a00",
              "#a855f7",
            ],
            "line-width": ["interpolate", ["linear"], ["zoom"], 5, 3, 10, 5, 14, 8],
            "line-opacity": [
              "case",
              ["==", ["get", "is_current"], false],
              0.25,
              [
                "any",
                ["in", "incendi", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "incendio", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "obstacle ambiental", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "environmentalobstruction", ["downcase", ["to-string", ["get", "cause_type", ["get", "properties"]]]]],
              ],
              0.98,
              0.5,
            ],
          },
        },
        {
          id: "restrictions-point",
          type: "circle",
          source: "civil-restrictions",
          filter: ["==", ["geometry-type"], "Point"],
          layout: { visibility: "visible" },
          paint: {
            "circle-color": [
              "case",
              [
                "any",
                ["in", "incendi", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "incendio", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "obstacle ambiental", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "environmentalobstruction", ["downcase", ["to-string", ["get", "cause_type", ["get", "properties"]]]]],
              ],
              "#ff7a00",
              "#a855f7",
            ],
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 5, 10, 8, 14, 12],
            "circle-stroke-color": [
              "case",
              [
                "any",
                ["in", "incendi", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "incendio", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "obstacle ambiental", ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]]],
                ["in", "environmentalobstruction", ["downcase", ["to-string", ["get", "cause_type", ["get", "properties"]]]]],
              ],
              "#7c2d12",
              "#3b0764",
            ],
            "circle-stroke-width": 2,
            "circle-opacity": ["case", ["==", ["get", "is_current"], false], 0.3, 0.72],
          },
        },
        {
          id: "detections-heat-area",
          type: "fill",
          source: "civil-detections",
          layout: {
            visibility: "visible",
          },
          paint: {
            "fill-color": "#b42318",
            "fill-opacity": ["case", ["==", ["get", "is_current"], false], 0.28, 0.58],
          },
        },
        {
          id: "detections-area-outline",
          type: "line",
          source: "civil-detections",
          layout: {
            visibility: "visible",
          },
          paint: {
            "line-color": "#8a1f16",
            "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.4, 12, 1.2],
            "line-opacity": ["case", ["==", ["get", "is_current"], false], 0.3, 0.68],
          },
        },
        {
          id: "detections-pin",
          type: "circle",
          source: "civil-detection-pins",
          layout: { visibility: "visible" },
          paint: {
            "circle-color": "#c81e1e",
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 8, 10, 13],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 2,
            "circle-opacity": 0.95,
          },
        },
        {
          id: "detections-pin-label",
          type: "symbol",
          source: "civil-detection-pins",
          layout: {
            visibility: "visible",
            "text-field": ["to-string", ["get", "detection_count", ["get", "properties"]]],
            "text-size": 11,
            "text-anchor": "center",
          },
          paint: {
            "text-color": "#ffffff",
          },
        },
        {
          id: "detections-point",
          type: "circle",
          source: "civil-detection-points",
          layout: { visibility: "none" },
          paint: {
            "circle-color": "#f97316",
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 2.8, 11, 5.2, 14, 6.5],
            "circle-stroke-color": "#7a1f17",
            "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 5, 0.4, 11, 0.9],
            "circle-opacity": 0.9,
            "circle-stroke-opacity": 0.95,
          },
        },
      ],
    } as StyleSpecification;

    const map = new maplibregl.Map({
      container: containerRef.current,
      center: [-3.7, 40.4],
      zoom: 5,
      style: baseStyle,
    });
    mapRef.current = map;
    setMapWarning(null);

    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");

    const resizeMap = () => map.resize();
    map.once("load", resizeMap);
    window.requestAnimationFrame(resizeMap);

    const resizeObserver = new ResizeObserver(resizeMap);
    resizeObserver.observe(containerRef.current);

    map.on("moveend", () => {
      const center = map.getCenter();
      setViewport({ longitude: center.lng, latitude: center.lat, zoom: map.getZoom() });
    });
    map.on("error", (event) => {
      const message = event.error?.message ?? "MapLibre no ha pogut pintar una capa del mapa.";
      setMapWarning(message);
    });

    selectableLayers.forEach((layerId) => {
      map.on("click", layerId, (event) => {
        const id = event.features?.[0]?.properties?.id as string | undefined;
        if (id) {
          onFeatureSelectRef.current?.(id);
          const feature = featureIndexRef.current.get(id);
          if (feature) {
            popupRef.current?.remove();
            popupRef.current = new maplibregl.Popup({
              closeButton: true,
              closeOnClick: true,
              maxWidth: "340px",
            })
              .setLngLat(event.lngLat)
              .setHTML(popupHtml(feature))
              .addTo(map);
          }
        }
      });
      map.on("mouseenter", layerId, () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", layerId, () => {
        map.getCanvas().style.cursor = "";
      });
    });

    return () => {
      resizeObserver.disconnect();
      popupRef.current?.remove();
      map.remove();
      mapRef.current = null;
    };
  }, [portal, setViewport]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const updateSources = () => {
      let missingSource = false;
      const nextFeatureIndex = new Map<string, CivilFeature>();
      (Object.keys(layerIdsBySource) as CivilLayerName[]).forEach((layer) => {
        const source = map.getSource(`civil-${layer}`) as maplibregl.GeoJSONSource | undefined;
        if (!source) {
          missingSource = true;
          return;
        }
        getLayerData(civilLayers, layer).features.forEach((feature) => {
          nextFeatureIndex.set(feature.properties.id, feature);
        });
        source?.setData(
          (isLayerVisible(visibleLayers, layer) ? getLayerData(civilLayers, layer) : emptyFeatureCollection) as unknown as Parameters<
            maplibregl.GeoJSONSource["setData"]
          >[0],
        );
      });
      const allDetections = getLayerData(civilLayers, "detections");
      const visibleDetections = isLayerVisible(visibleLayers, "detections")
        ? allDetections
        : emptyFeatureCollection;
      const pointSource = map.getSource("civil-detection-points") as maplibregl.GeoJSONSource | undefined;
      const pinSource = map.getSource("civil-detection-pins") as maplibregl.GeoJSONSource | undefined;
      if (!pointSource || !pinSource) {
        missingSource = true;
        return missingSource;
      }
      pointSource.setData(
        detectionPointCollection(allDetections) as unknown as Parameters<
          maplibregl.GeoJSONSource["setData"]
        >[0],
      );
      pinSource.setData(
        detectionPinCollection(visibleDetections) as unknown as Parameters<maplibregl.GeoJSONSource["setData"]>[0],
      );
      featureIndexRef.current = nextFeatureIndex;
      return missingSource;
    };
    if (!updateSources()) {
      return;
    }
    map.once("load", updateSources);
    return () => {
      map.off("load", updateSources);
    };
  }, [civilLayers, showFirmHotspots, visibleLayers]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const applyVisibility = () => {
      let missingLayer = false;
      (Object.keys(layerIdsBySource) as CivilLayerName[]).forEach((layer) => {
        const visibility = sourceVisibility(visibleLayers, layer);
        layerIdsBySource[layer].forEach((layerId) => {
          if (!map.getLayer(layerId)) {
            missingLayer = true;
            return;
          }
          map.setLayoutProperty(layerId, "visibility", visibility);
        });
      });
      return missingLayer;
    };
    if (!applyVisibility()) {
      return;
    }
    map.once("load", applyVisibility);
    return () => {
      map.off("load", applyVisibility);
    };
  }, [visibleLayers]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    const applyHotspotVisibility = () => {
      if (!map.getLayer("detections-point")) {
        return true;
      }
      map.setLayoutProperty(
        "detections-point",
        "visibility",
        showFirmHotspots ? "visible" : "none",
      );
      return false;
    };
    if (!applyHotspotVisibility()) {
      return;
    }
    map.once("load", applyHotspotVisibility);
    return () => {
      map.off("load", applyHotspotVisibility);
    };
  }, [showFirmHotspots]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !bbox) {
      return;
    }
    const values = bbox.split(",").map((value) => Number(value.trim()));
    if (values.length !== 4 || values.some((value) => Number.isNaN(value))) {
      return;
    }
    const [west, south, east, north] = values;
    map.fitBounds(
      [
        [west, south],
        [east, north],
      ],
      { padding: 48, duration: 700, maxZoom: 12 },
    );
  }, [bbox]);

  return (
    <div className="relative h-full min-h-[520px] overflow-hidden rounded-lg border border-[#d7ddd8] bg-[#eef3ef] shadow-sm">
      <div ref={containerRef} className="relative h-full min-h-[520px]" role="img" aria-label={`Mapa ${portal}`} />
      {mapWarning ? (
        <div className="absolute left-3 top-3 max-w-[min(420px,calc(100%-24px))] rounded-md border border-[#b42318] bg-white px-3 py-2 text-sm text-[#17201b] shadow">
          {mapWarning}
        </div>
      ) : null}
      {isLoading ? (
        <div className="pointer-events-none absolute left-3 top-3 flex max-w-[min(420px,calc(100%-24px))] items-center gap-3 rounded-md border border-[#d7ddd8] bg-white/95 px-3 py-2 text-sm font-semibold text-[#17201b] shadow">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-[#ff7a00] border-t-transparent" />
          Carregant dades al mapa...
        </div>
      ) : null}
      <style jsx global>{`
        .maplibregl-popup-content {
          border-radius: 8px;
          border: 1px solid #d7ddd8;
          box-shadow: 0 16px 40px rgba(23, 32, 27, 0.18);
          padding: 0;
          overflow: hidden;
        }
        .map-popup {
          min-width: 240px;
          max-width: 340px;
          background: #ffffff;
          color: #17201b;
        }
        .map-popup h3 {
          margin: 0;
          padding: 12px 14px;
          font-size: 14px;
          line-height: 1.35;
          border-bottom: 1px solid #edf0ed;
        }
        .map-popup-row {
          display: grid;
          grid-template-columns: 88px minmax(0, 1fr);
          gap: 10px;
          padding: 7px 14px;
          font-size: 12px;
          line-height: 1.35;
        }
        .map-popup-row span {
          color: #53605a;
        }
        .map-popup-row strong {
          min-width: 0;
          font-weight: 600;
          overflow-wrap: anywhere;
        }
      `}</style>
    </div>
  );
}
