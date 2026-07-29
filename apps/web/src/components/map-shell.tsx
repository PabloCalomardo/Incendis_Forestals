"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState, type ReactNode } from "react";
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
  mapOverlay?: ReactNode;
  focusTarget?: {
    geometry?: CivilFeature["geometry"];
    bbox?: string;
    key: number;
  } | null;
  onFeatureSelect?: (featureId: string) => void;
  onFeatureDetails?: (featureId: string) => void;
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
  "perimeters-burnt-fill",
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
  perimeters: ["perimeters-burnt-fill", "perimeters-official", "perimeters-estimated"],
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
  observed_at?: string | null;
};

const FIRMS_MAX_VISIBLE_AGE_DAYS = 7;
const FIRMS_MAX_VISIBLE_AGE_MS = FIRMS_MAX_VISIBLE_AGE_DAYS * 24 * 60 * 60 * 1000;

function detectionObservedAt(feature: CivilFeature) {
  return (
    feature.properties.properties.newest_detection_at ??
    feature.properties.observed_at ??
    feature.properties.updated_at
  );
}

function firmsAgeDays(feature: CivilFeature) {
  const observedAt = detectionObservedAt(feature);
  if (typeof observedAt !== "string") {
    return 0;
  }
  const observedTime = new Date(observedAt).getTime();
  if (!Number.isFinite(observedTime)) {
    return 0;
  }
  const observedDate = new Date(observedTime);
  const now = new Date();
  const observedDay = Date.UTC(
    observedDate.getUTCFullYear(),
    observedDate.getUTCMonth(),
    observedDate.getUTCDate(),
  );
  const currentDay = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Math.max(0, Math.floor((currentDay - observedDay) / (24 * 60 * 60 * 1000)));
}

function isVisibleFirmDetection(feature: CivilFeature) {
  const observedAt = detectionObservedAt(feature);
  if (typeof observedAt !== "string") {
    return true;
  }
  const observedTime = new Date(observedAt).getTime();
  return Number.isFinite(observedTime)
    ? Date.now() - observedTime < FIRMS_MAX_VISIBLE_AGE_MS
    : true;
}

function firmVisualProperties(feature: CivilFeature) {
  const ageDays = Math.min(FIRMS_MAX_VISIBLE_AGE_DAYS, firmsAgeDays(feature));
  const ageRatio = ageDays / FIRMS_MAX_VISIBLE_AGE_DAYS;
  return {
    firms_age_days: ageDays,
    firms_age_opacity: Math.max(0.08, 1 - ageRatio * 0.86),
  };
}

const firmsAgeColor = [
  "step",
  ["to-number", ["get", "firms_age_days", ["get", "properties"]], 0],
  "#d92d20",
  1,
  "#b93824",
  2,
  "#942e20",
  3,
  "#76271c",
  4,
  "#5d2018",
  5,
  "#471814",
  6,
  "#32100d",
] as const;

function visibleFirmDetectionCollection(
  collection: CivilFeatureCollection,
): CivilFeatureCollection {
  return {
    ...collection,
    features: collection.features.filter(isVisibleFirmDetection).map((feature) => ({
      ...feature,
      properties: {
        ...feature.properties,
        properties: {
          ...feature.properties.properties,
          ...firmVisualProperties(feature),
        },
      },
    })),
  };
}

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
                observed_at:
                  typeof (point as FirmPoint).observed_at === "string"
                    ? (point as FirmPoint).observed_at
                    : feature.properties.observed_at,
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
      observed_at: feature.properties.observed_at,
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
            observed_at: point.observed_at ?? feature.properties.observed_at,
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

function popupDate(value: unknown) {
  const compact = compactValue(value);
  if (!compact) return null;
  const date = new Date(compact);
  return Number.isNaN(date.getTime())
    ? compact
    : date.toLocaleDateString("ca-ES", { day: "2-digit", month: "short", year: "numeric" });
}

function popupTitle(feature: CivilFeature) {
  const properties = feature.properties.properties;
  return (
    compactValue(properties.canonical_title) ??
    compactValue(properties.name) ??
    compactValue(properties.title) ??
    compactValue(properties.sensor) ??
    feature.properties.data_type
  );
}

const effisAttributeLabels: Record<string, string> = {
  ID: "Identificador EFFIS",
  FIREDATE: "Data del foc",
  FINALDATE: "Data final",
  LASTUPDATE: "Última actualització",
  COUNTRY: "País",
  PROVINCE: "Província",
  COMMUNE: "Municipi",
  AREA_HA: "Àrea cremada (ha)",
  BROADLEA: "Bosc de fulla ampla (%)",
  CONIFER: "Coníferes (%)",
  MIXED: "Bosc mixt (%)",
  SCLEROPH: "Vegetació esclerofil·la (%)",
  TRANSIT: "Bosc en transició (%)",
  OTHERNATLC: "Altres cobertes naturals (%)",
  AGRIAREAS: "Àrees agrícoles (%)",
  ARTIFSURF: "Superfícies artificials (%)",
  OTHERLC: "Altres cobertes (%)",
  PERCNA2K: "Xarxa Natura 2000 afectada (%)",
  CLASS: "Classe EFFIS",
};

function effisPopupRows(feature: CivilFeature): Array<[string, string]> {
  const raw = feature.properties.properties.effis_attributes_json;
  if (typeof raw !== "string" || raw.length === 0) {
    return [];
  }
  try {
    const attributes = JSON.parse(raw) as Record<string, unknown>;
    return Object.entries(attributes).flatMap(([key, value]) => {
      const compact = compactValue(value);
      return compact ? [[effisAttributeLabels[key.toUpperCase()] ?? key, compact]] : [];
    });
  } catch {
    return [];
  }
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
    ["Municipi", properties.commune],
    ["Incident", properties.canonical_summary],
    ["Hashtags", Array.isArray(properties.hashtags) ? properties.hashtags.join(", ") : null],
    ["Data del foc", properties.fire_date],
    ["Area cremada", properties.area_hectares ? `${properties.area_hectares} ha` : null],
    ["Extincio", properties.extinction_operations_note],
    ["Municipis", properties.municipalities],
    ["Deteccions", properties.detection_count],
    ["Deteccions FIRMS vinculades", properties.firms_detection_count],
    ["FRP acumulada", properties.firms_total_frp_mw ? `${properties.firms_total_frp_mw} MW` : null],
    ["Mes antiga", properties.oldest_detection_at],
    ["Mes nova", properties.newest_detection_at],
    [
      "Area",
      properties.focus_area_square_meters ? `${properties.focus_area_square_meters} m2` : null,
    ],
    ["Sensor", properties.sensor],
    ["FRP", properties.frp_mw ? `${properties.frp_mw} MW` : null],
  ];
  const standardRows = rows.flatMap(([label, value]) => {
    const compact = compactValue(value);
    return compact ? [[label, compact] as [string, string]] : [];
  });
  return [...standardRows, ...effisPopupRows(feature)];
}

function popupHtml(feature: CivilFeature) {
  const properties = feature.properties.properties;
  const isFireIncident =
    feature.properties.data_type === "incident" ||
    feature.properties.data_type === "fire_perimeter";
  if (isFireIncident) {
    const incidentId =
      feature.properties.data_type === "incident" ? feature.properties.id : properties.incident_id;
    const hashtags = Array.isArray(properties.hashtags) ? properties.hashtags.join(", ") : null;
    const summary = compactValue(properties.canonical_summary ?? properties.summary);
    const briefRows: Array<[string, unknown]> = [
      [
        "Inici",
        popupDate(properties.fire_date ?? properties.started_at ?? feature.properties.observed_at),
      ],
      ["Extinció", popupDate(properties.final_date ?? properties.ended_at)],
      ["Hashtag", properties.primary_hashtag ?? hashtags],
    ];
    const rows = briefRows
      .flatMap(([label, value]) => {
        const compact = compactValue(value);
        return compact ? [[label, compact] as [string, string]] : [];
      })
      .map(
        ([label, value]) =>
          `<div class="map-popup-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`,
      )
      .join("");
    const description = summary ? `<p class="map-popup-summary">${escapeHtml(summary)}</p>` : "";
    const detailsButton =
      typeof incidentId === "string" && incidentId
        ? `<button type="button" class="map-popup-details" data-incident-details="${escapeHtml(incidentId)}">Veure tota la informació</button>`
        : "";
    return `<div class="map-popup"><h3>${escapeHtml(popupTitle(feature))}</h3>${description}${rows}${detailsButton}</div>`;
  }
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
  showFirmHotspots = false,
  isLoading = false,
  mapOverlay,
  focusTarget,
  onFeatureSelect,
  onFeatureDetails,
}: MapShellProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const featureIndexRef = useRef<Map<string, CivilFeature>>(new Map());
  const onFeatureSelectRef = useRef(onFeatureSelect);
  const onFeatureDetailsRef = useRef(onFeatureDetails);
  const [mapWarning, setMapWarning] = useState<string | null>(null);
  const setViewport = useMapViewportStore((state) => state.setViewport);

  useEffect(() => {
    onFeatureSelectRef.current = onFeatureSelect;
  }, [onFeatureSelect]);

  useEffect(() => {
    onFeatureDetailsRef.current = onFeatureDetails;
  }, [onFeatureDetails]);

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
              "social",
              "#2563eb",
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
          id: "perimeters-burnt-fill",
          type: "fill",
          source: "civil-perimeters",
          layout: { visibility: "visible" },
          paint: {
            "fill-color": "#626966",
            "fill-opacity": [
              "match",
              ["get", "perimeter_period", ["get", "properties"]],
              "current",
              0.3,
              "year",
              0.22,
              0.15,
            ],
          },
        },
        {
          id: "perimeters-official",
          type: "line",
          source: "civil-perimeters",
          filter: ["!=", ["get", "provenance"], "estimated"],
          layout: { visibility: "visible" },
          paint: {
            "line-color": [
              "match",
              ["get", "perimeter_period", ["get", "properties"]],
              "current",
              "#b42318",
              "year",
              "#c77700",
              "#66736c",
            ],
            "line-width": [
              "match",
              ["get", "perimeter_period", ["get", "properties"]],
              "current",
              4,
              2.5,
            ],
            "line-opacity": 0.9,
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
            "fill-color": "#dc2626",
            "fill-opacity": ["case", ["==", ["get", "is_current"], false], 0.12, 0.28],
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
                [
                  "in",
                  "incendi",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "incendio",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "obstacle ambiental",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "environmentalobstruction",
                  ["downcase", ["to-string", ["get", "cause_type", ["get", "properties"]]]],
                ],
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
                [
                  "in",
                  "incendi",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "incendio",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "obstacle ambiental",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "environmentalobstruction",
                  ["downcase", ["to-string", ["get", "cause_type", ["get", "properties"]]]],
                ],
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
                [
                  "in",
                  "incendi",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "incendio",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "obstacle ambiental",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "environmentalobstruction",
                  ["downcase", ["to-string", ["get", "cause_type", ["get", "properties"]]]],
                ],
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
                [
                  "in",
                  "incendi",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "incendio",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "obstacle ambiental",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "environmentalobstruction",
                  ["downcase", ["to-string", ["get", "cause_type", ["get", "properties"]]]],
                ],
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
                [
                  "in",
                  "incendi",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "incendio",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "obstacle ambiental",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "environmentalobstruction",
                  ["downcase", ["to-string", ["get", "cause_type", ["get", "properties"]]]],
                ],
              ],
              "#ff7a00",
              "#a855f7",
            ],
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 5, 10, 8, 14, 12],
            "circle-stroke-color": [
              "case",
              [
                "any",
                [
                  "in",
                  "incendi",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "incendio",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "obstacle ambiental",
                  ["downcase", ["to-string", ["get", "cause", ["get", "properties"]]]],
                ],
                [
                  "in",
                  "environmentalobstruction",
                  ["downcase", ["to-string", ["get", "cause_type", ["get", "properties"]]]],
                ],
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
            "fill-color": firmsAgeColor,
            "fill-opacity": [
              "*",
              ["case", ["==", ["get", "is_current"], false], 0.28, 0.58],
              ["to-number", ["get", "firms_age_opacity", ["get", "properties"]], 1],
            ],
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
            "line-color": firmsAgeColor,
            "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.4, 12, 1.2],
            "line-opacity": [
              "*",
              ["case", ["==", ["get", "is_current"], false], 0.3, 0.68],
              ["to-number", ["get", "firms_age_opacity", ["get", "properties"]], 1],
            ],
          },
        },
        {
          id: "detections-pin",
          type: "circle",
          source: "civil-detection-pins",
          layout: { visibility: "visible" },
          paint: {
            "circle-color": firmsAgeColor,
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 8, 10, 13],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 2,
            "circle-opacity": [
              "*",
              0.95,
              ["to-number", ["get", "firms_age_opacity", ["get", "properties"]], 1],
            ],
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
            "text-opacity": [
              "*",
              0.95,
              ["to-number", ["get", "firms_age_opacity", ["get", "properties"]], 1],
            ],
          },
        },
        {
          id: "detections-point",
          type: "circle",
          source: "civil-detection-points",
          layout: { visibility: "none" },
          paint: {
            "circle-color": firmsAgeColor,
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 2.8, 11, 5.2, 14, 6.5],
            "circle-stroke-color": "#7a1f17",
            "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 5, 0.4, 11, 0.9],
            "circle-opacity": [
              "*",
              0.9,
              ["to-number", ["get", "firms_age_opacity", ["get", "properties"]], 1],
            ],
            "circle-stroke-opacity": [
              "*",
              0.95,
              ["to-number", ["get", "firms_age_opacity", ["get", "properties"]], 1],
            ],
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
            const popup = new maplibregl.Popup({
              closeButton: true,
              closeOnClick: true,
              maxWidth: "340px",
            })
              .setLngLat(event.lngLat)
              .setHTML(popupHtml(feature))
              .addTo(map);
            const detailsButton = popup
              .getElement()
              .querySelector<HTMLButtonElement>("[data-incident-details]");
            detailsButton?.addEventListener("click", () => {
              const incidentId = detailsButton.dataset.incidentDetails;
              if (incidentId) {
                onFeatureDetailsRef.current?.(incidentId);
                popup.remove();
              }
            });
            popupRef.current = popup;
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
        const layerData =
          layer === "detections"
            ? visibleFirmDetectionCollection(getLayerData(civilLayers, layer))
            : getLayerData(civilLayers, layer);
        if (!source) {
          missingSource = true;
          return;
        }
        layerData.features.forEach((feature) => {
          nextFeatureIndex.set(feature.properties.id, feature);
        });
        source?.setData(
          (isLayerVisible(visibleLayers, layer)
            ? layerData
            : emptyFeatureCollection) as unknown as Parameters<
            maplibregl.GeoJSONSource["setData"]
          >[0],
        );
      });
      const allDetections = visibleFirmDetectionCollection(getLayerData(civilLayers, "detections"));
      const visibleDetections = isLayerVisible(visibleLayers, "detections")
        ? allDetections
        : emptyFeatureCollection;
      const pointSource = map.getSource("civil-detection-points") as
        | maplibregl.GeoJSONSource
        | undefined;
      const pinSource = map.getSource("civil-detection-pins") as
        | maplibregl.GeoJSONSource
        | undefined;
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
        detectionPinCollection(visibleDetections) as unknown as Parameters<
          maplibregl.GeoJSONSource["setData"]
        >[0],
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

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focusTarget) {
      return;
    }
    if (focusTarget.bbox) {
      const values = focusTarget.bbox.split(",").map((value) => Number(value.trim()));
      if (values.length === 4 && values.every(Number.isFinite)) {
        map.fitBounds(
          [
            [values[0], values[1]],
            [values[2], values[3]],
          ],
          { padding: 72, duration: 800, maxZoom: 12 },
        );
      }
      return;
    }
    const geometry = focusTarget.geometry;
    if (!geometry) {
      return;
    }
    if (geometry.type === "Point") {
      map.easeTo({
        center: [geometry.coordinates[0], geometry.coordinates[1]],
        zoom: 12,
        duration: 800,
      });
      return;
    }
    const bounds = new maplibregl.LngLatBounds();
    const extendCoordinates = (coordinates: unknown): void => {
      if (!Array.isArray(coordinates)) {
        return;
      }
      if (
        coordinates.length >= 2 &&
        typeof coordinates[0] === "number" &&
        typeof coordinates[1] === "number"
      ) {
        bounds.extend([coordinates[0], coordinates[1]]);
        return;
      }
      coordinates.forEach(extendCoordinates);
    };
    extendCoordinates(geometry.coordinates);
    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, { padding: 72, duration: 800, maxZoom: 13 });
    }
  }, [focusTarget]);

  return (
    <div className="relative h-full min-h-[520px] overflow-hidden rounded-lg border border-[#d7ddd8] bg-[#eef3ef] shadow-sm">
      <div
        ref={containerRef}
        className="relative h-full min-h-[520px]"
        role="img"
        aria-label={`Mapa ${portal}`}
      />
      {mapOverlay}
      {mapWarning ? (
        <div className="absolute left-3 top-3 max-w-[min(420px,calc(100%-24px))] rounded-md border border-[#b42318] bg-white px-3 py-2 text-sm text-[#17201b] shadow">
          {mapWarning}
        </div>
      ) : null}
      {isLoading ? (
        <div
          className="pointer-events-none absolute inset-0 z-30 grid place-items-center bg-[#17201b]/20"
          role="status"
          aria-live="polite"
        >
          <div className="flex max-w-[min(420px,calc(100%-24px))] items-center gap-3 rounded-md border border-[#b8c2bc] bg-white px-5 py-4 text-sm font-semibold text-[#17201b] shadow-xl">
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-[#ff7a00] border-t-transparent" />
            Carregant Dades al Mapa
          </div>
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
        .map-popup-summary {
          display: -webkit-box;
          margin: 0;
          padding: 10px 14px 5px;
          overflow: hidden;
          color: #303b35;
          font-size: 12px;
          line-height: 1.45;
          -webkit-box-orient: vertical;
          -webkit-line-clamp: 3;
        }
        .map-popup-details {
          display: block;
          width: calc(100% - 28px);
          margin: 10px 14px 14px;
          border: 0;
          border-radius: 4px;
          background: #1f6f50;
          padding: 8px 10px;
          color: #ffffff;
          cursor: pointer;
          font-size: 12px;
          font-weight: 700;
        }
        .map-popup-details:focus-visible {
          outline: 2px solid #1d5fd0;
          outline-offset: 2px;
        }
      `}</style>
    </div>
  );
}
