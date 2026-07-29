import polygonClipping, { type MultiPolygon, type Polygon } from "polygon-clipping";

export type Geometry =
  | { type: "Point"; coordinates: number[] }
  | { type: "LineString"; coordinates: number[][] }
  | { type: "Polygon"; coordinates: number[][][] }
  | { type: "MultiPolygon"; coordinates: number[][][][] }
  | null;

export type CivilItem = {
  id: string;
  data_type: string;
  source: {
    name: string | null;
    authority: string | null;
    url: string | null;
    attribution: string | null;
  };
  observed_at: string | null;
  updated_at: string | null;
  age_seconds: number | null;
  confidence: number | null;
  confidence_category: string | null;
  provenance: string;
  is_current: boolean;
  warnings: string[];
  properties: Record<string, string | number | boolean | null | string[]>;
  geometry?: Geometry;
};

export type CivilCollection = {
  data_type: string;
  items: CivilItem[];
  pagination: {
    limit: number;
    offset: number;
    count: number;
  };
  warnings: string[];
};

export type CivilFeature = {
  type: "Feature";
  id?: string;
  geometry: Geometry;
  properties: CivilItem;
};

export type CivilFeatureCollection = {
  type: "FeatureCollection";
  features: CivilFeature[];
  pagination?: {
    limit: number;
    offset: number;
    count: number;
  };
};

export type CivilLayerName =
  | "detections"
  | "perimeters"
  | "evacuations"
  | "restrictions"
  | "roads"
  | "risk"
  | "smoke"
  | "aircraft";

export type CivilLayerState = Record<CivilLayerName, CivilFeatureCollection>;

export type CivilFilters = {
  bbox: string;
  municipality: string;
  minConfidence: number;
  onlyCurrent: boolean;
};

export type FirmsTimelineItem = {
  observed_at: string;
  count: number;
};

export type FirmsTimeline = {
  data_type: "firms_timeline";
  items: FirmsTimelineItem[];
  warnings: string[];
};

export type CivilTemporalWindow = {
  observedFrom: string;
  observedTo: string;
};

export type MunicipalityLookupItem = {
  id: string;
  name: string;
  ine_code: string | null;
  national_code: string | null;
  longitude: number;
  latitude: number;
  bbox: string;
  source: {
    name: string;
    authority: string;
    url: string;
    attribution: string;
  };
  match_rank: number;
};

export type MunicipalityLookupResponse = {
  data_type: "municipality_lookup";
  items: MunicipalityLookupItem[];
  pagination: {
    limit: number;
    offset: number;
    count: number;
  };
  warnings: string[];
};

export type OsintTimelineItem = {
  id: string;
  event_type: string;
  risk_type: string;
  action_state: string;
  es_alert_status: string;
  title: string;
  authority: string;
  published_at: string;
  starts_at: string | null;
  ends_at: string | null;
  instructions: string | null;
  es_alert_message: string | null;
  locations: Array<{ name?: string; kind?: string; official?: boolean }>;
  original_text: string;
  url: string;
  source_type: string;
  source_name: string | null;
  confidence: number;
  review_status: string;
  geometry_inference_method: string;
  spatial_precision: string;
};

export type OsintIncidentDetail = {
  id: string;
  title: string;
  summary: string | null;
  status: string;
  confidence: number | null;
  duration_seconds: number | null;
  properties: Record<string, unknown>;
  timeline: OsintTimelineItem[];
};

export type InstitutionalXAccount = {
  handle: string;
  name: string;
  authority: string;
  region: string;
  category: string;
  x_url: string;
  nitter_url: string;
  viewer_url: string;
  viewer_input: string;
};

export type InstitutionalXAccountsResponse = {
  data_type: "institutional_x_accounts";
  primary_gateway: "nitter";
  nitter_base_url: string;
  collection_mode: "human_review";
  automated_collection: false;
  reason: string;
  viewer_url: string;
  terms_url: string;
  items: InstitutionalXAccount[];
};

const API_BASE_URL =
  typeof window === "undefined"
    ? (process.env.API_INTERNAL_BASE_URL ??
      process.env.NEXT_PUBLIC_API_BASE_URL ??
      "http://localhost:8000")
    : (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000");

const emptyFeatureCollection: CivilFeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

const LAYER_PAGE_SIZE = 200;
const MAX_LAYER_FEATURES = 2_000;
const MAX_PERIMETER_FEATURES = 50_000;
const MAX_FIRMS_FEATURES = 10_000;
const MAX_DAILY_FIRMS_FEATURES = 10_000;
const MAX_AEMET_NOTICES = 1_000;

type DetectionPoint = {
  id: string;
  longitude: number;
  latitude: number;
  observation_day: string;
  sensor_family: "viirs" | "modis" | "other";
  scan_meters: number;
  track_meters: number;
  connection_distance_meters: number;
  feature: CivilFeature;
};

type LocalPoint = { x: number; y: number };

const METERS_PER_DEGREE = 111_320;

function detectionSensorFamily(feature: CivilFeature): DetectionPoint["sensor_family"] {
  const sensor = String(feature.properties.properties.sensor ?? "").toLowerCase();
  if (sensor.includes("modis")) {
    return "modis";
  }
  if (sensor.includes("viirs")) {
    return "viirs";
  }
  return "other";
}

function positiveNumber(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
}

function detectionPixelDimensions(feature: CivilFeature) {
  const sensorFamily = detectionSensorFamily(feature);
  const nominalMeters = sensorFamily === "modis" ? 1_000 : sensorFamily === "viirs" ? 375 : 500;
  const scanMeters = positiveNumber(feature.properties.properties.scan_km);
  const trackMeters = positiveNumber(feature.properties.properties.track_km);
  return {
    sensorFamily,
    scanMeters: scanMeters === null ? nominalMeters : scanMeters * 1_000,
    trackMeters: trackMeters === null ? nominalMeters : trackMeters * 1_000,
  };
}

function detectionConnectionDistanceMeters(feature: CivilFeature) {
  const sensor = String(feature.properties.properties.sensor ?? "").toLowerCase();
  const dimensions = detectionPixelDimensions(feature);
  if (sensor.includes("modis")) {
    return 1_500;
  }
  if (sensor.includes("viirs")) {
    return Math.max(650, Math.max(dimensions.scanMeters, dimensions.trackMeters) * 1.45);
  }
  return 750;
}

function detectionPoint(feature: CivilFeature): DetectionPoint | null {
  const dimensions = detectionPixelDimensions(feature);
  const longitude = Number(feature.properties.properties.longitude);
  const latitude = Number(feature.properties.properties.latitude);
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) {
    return null;
  }
  return {
    id: feature.properties.id,
    longitude,
    latitude,
    observation_day:
      typeof feature.properties.observed_at === "string"
        ? feature.properties.observed_at.slice(0, 10)
        : "unknown",
    sensor_family: dimensions.sensorFamily,
    scan_meters: dimensions.scanMeters,
    track_meters: dimensions.trackMeters,
    connection_distance_meters: detectionConnectionDistanceMeters(feature),
    feature,
  };
}

function metersBetween(first: DetectionPoint, second: DetectionPoint) {
  const meanLatitude = ((first.latitude + second.latitude) / 2) * (Math.PI / 180);
  const x = (second.longitude - first.longitude) * 111_320 * Math.cos(meanLatitude);
  const y = (second.latitude - first.latitude) * 111_320;
  return Math.hypot(x, y);
}

function pointsConnect(first: DetectionPoint, second: DetectionPoint) {
  return (
    first.observation_day === second.observation_day &&
    first.sensor_family === second.sensor_family &&
    metersBetween(first, second) <=
      Math.max(first.connection_distance_meters, second.connection_distance_meters)
  );
}

function connectedDetectionGroups(points: DetectionPoint[]) {
  const visited = new Set<number>();
  return points.flatMap((point, index) => {
    if (visited.has(index)) {
      return [];
    }
    const group = [point];
    const queue = [index];
    visited.add(index);
    while (queue.length > 0) {
      const currentIndex = queue.shift();
      if (currentIndex === undefined) {
        break;
      }
      points.forEach((candidate, candidateIndex) => {
        if (visited.has(candidateIndex)) {
          return;
        }
        if (pointsConnect(points[currentIndex], candidate)) {
          visited.add(candidateIndex);
          group.push(candidate);
          queue.push(candidateIndex);
        }
      });
    }
    return [group];
  });
}

function median(values: number[]) {
  const sorted = [...values].sort((first, second) => first - second);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle];
}

function localProjection(group: DetectionPoint[]) {
  const originLongitude = group.reduce((sum, point) => sum + point.longitude, 0) / group.length;
  const originLatitude = group.reduce((sum, point) => sum + point.latitude, 0) / group.length;
  const longitudeScale =
    METERS_PER_DEGREE * Math.max(Math.cos((originLatitude * Math.PI) / 180), 0.1);
  return {
    project(point: DetectionPoint): LocalPoint {
      return {
        x: (point.longitude - originLongitude) * longitudeScale,
        y: (point.latitude - originLatitude) * METERS_PER_DEGREE,
      };
    },
    unproject(point: LocalPoint): [number, number] {
      return [
        originLongitude + point.x / longitudeScale,
        originLatitude + point.y / METERS_PER_DEGREE,
      ];
    },
  };
}

function estimateGridAngle(group: DetectionPoint[], projected: LocalPoint[]) {
  const angles: number[] = [];
  for (let first = 0; first < projected.length; first += 1) {
    for (let second = first + 1; second < projected.length; second += 1) {
      const dx = projected[second].x - projected[first].x;
      const dy = projected[second].y - projected[first].y;
      const distance = Math.hypot(dx, dy);
      const minimumPixelSize = Math.min(group[first].scan_meters, group[first].track_meters);
      if (
        distance < minimumPixelSize * 0.55 ||
        distance >
          Math.max(
            group[first].connection_distance_meters,
            group[second].connection_distance_meters,
          )
      ) {
        continue;
      }
      const quarterTurn = Math.PI / 2;
      angles.push(((Math.atan2(dy, dx) % quarterTurn) + quarterTurn) % quarterTurn);
    }
  }
  if (angles.length === 0) {
    return 0;
  }
  const cosine = angles.reduce((sum, angle) => sum + Math.cos(angle * 4), 0);
  const sine = angles.reduce((sum, angle) => sum + Math.sin(angle * 4), 0);
  const angle = Math.atan2(sine, cosine) / 4;
  return angle < 0 ? angle + Math.PI / 2 : angle;
}

function estimateGridSpacing(
  group: DetectionPoint[],
  projected: LocalPoint[],
  angle: number,
  fallbackWidth: number,
  fallbackHeight: number,
) {
  const cosine = Math.cos(angle);
  const sine = Math.sin(angle);
  const horizontal: number[] = [];
  const vertical: number[] = [];
  for (let first = 0; first < projected.length; first += 1) {
    for (let second = first + 1; second < projected.length; second += 1) {
      const dx = projected[second].x - projected[first].x;
      const dy = projected[second].y - projected[first].y;
      const distance = Math.hypot(dx, dy);
      if (
        distance >
        Math.max(group[first].connection_distance_meters, group[second].connection_distance_meters)
      ) {
        continue;
      }
      const alongHorizontal = Math.abs(dx * cosine + dy * sine);
      const alongVertical = Math.abs(-dx * sine + dy * cosine);
      if (alongHorizontal > 100 && alongHorizontal > alongVertical * 1.8) {
        horizontal.push(alongHorizontal);
      }
      if (alongVertical > 100 && alongVertical > alongHorizontal * 1.8) {
        vertical.push(alongVertical);
      }
    }
  }
  return {
    horizontal: horizontal.length > 0 ? median(horizontal) : fallbackWidth,
    vertical: vertical.length > 0 ? median(vertical) : fallbackHeight,
  };
}

function gridCellPolygons(group: DetectionPoint[]): {
  polygons: Polygon[];
  angle: number;
  width: number;
  height: number;
  areaSquareMeters: number;
  labelCoordinate: [number, number];
} {
  const projection = localProjection(group);
  const projected = group.map(projection.project);
  const angle = estimateGridAngle(group, projected);
  const cosine = Math.cos(angle);
  const sine = Math.sin(angle);
  const nominalWidth = median(group.map((point) => point.scan_meters));
  const nominalHeight = median(group.map((point) => point.track_meters));
  const minimumCellSize =
    group[0].sensor_family === "viirs" ? 400 : group[0].sensor_family === "modis" ? 1_000 : 500;
  const spacing = estimateGridSpacing(group, projected, angle, nominalWidth, nominalHeight);
  const width = Math.max(nominalWidth, minimumCellSize, spacing.horizontal);
  const height = Math.max(nominalHeight, minimumCellSize, spacing.vertical);
  const anchor = projected[0];
  const occupiedCells = new Map<string, { column: number; row: number }>();

  projected.forEach((point) => {
    const dx = point.x - anchor.x;
    const dy = point.y - anchor.y;
    const column = Math.round((dx * cosine + dy * sine) / spacing.horizontal);
    const row = Math.round((-dx * sine + dy * cosine) / spacing.vertical);
    const key = `${column}:${row}`;
    if (!occupiedCells.has(key)) {
      occupiedCells.set(key, { column, row });
    }
  });

  const halfColumnSpan = Math.max(width / spacing.horizontal / 2, 0.5);
  const halfRowSpan = Math.max(height / spacing.vertical / 2, 0.5);
  const gridSquares = [...occupiedCells.values()].map(({ column, row }) => {
    const left = column - halfColumnSpan;
    const right = column + halfColumnSpan;
    const bottom = row - halfRowSpan;
    const top = row + halfRowSpan;
    return [
      [
        [left, bottom],
        [right, bottom],
        [right, top],
        [left, top],
        [left, bottom],
      ],
    ] as Polygon;
  });

  const dissolvedGrid =
    gridSquares.length === 0 ? [] : polygonClipping.union(gridSquares[0], ...gridSquares.slice(1));
  const gridLabelPoint = interiorGridPoint(dissolvedGrid, [...occupiedCells.values()]);
  const labelCoordinate = projection.unproject({
    x:
      anchor.x +
      gridLabelPoint.column * spacing.horizontal * cosine -
      gridLabelPoint.row * spacing.vertical * sine,
    y:
      anchor.y +
      gridLabelPoint.column * spacing.horizontal * sine +
      gridLabelPoint.row * spacing.vertical * cosine,
  });
  const polygons = dissolvedGrid.map((polygon) =>
    polygon.map((ring) =>
      ring.map(([column, row]) =>
        projection.unproject({
          x: anchor.x + column * spacing.horizontal * cosine - row * spacing.vertical * sine,
          y: anchor.y + column * spacing.horizontal * sine + row * spacing.vertical * cosine,
        }),
      ),
    ),
  ) as Polygon[];
  return {
    polygons,
    angle,
    width,
    height,
    areaSquareMeters: Math.round(occupiedCells.size * width * height),
    labelCoordinate,
  };
}

function pointInRing(point: { column: number; row: number }, ring: number[][]) {
  let inside = false;
  for (
    let currentIndex = 0, previousIndex = ring.length - 1;
    currentIndex < ring.length;
    previousIndex = currentIndex, currentIndex += 1
  ) {
    const current = ring[currentIndex];
    const previous = ring[previousIndex];
    const intersects =
      current[1] > point.row !== previous[1] > point.row &&
      point.column <
        ((previous[0] - current[0]) * (point.row - current[1])) / (previous[1] - current[1]) +
          current[0];
    if (intersects) {
      inside = !inside;
    }
  }
  return inside;
}

function pointInPolygon(point: { column: number; row: number }, polygon: Polygon) {
  if (!pointInRing(point, polygon[0])) {
    return false;
  }
  return polygon.slice(1).every((hole) => !pointInRing(point, hole));
}

function gridRingAreaAndCentroid(ring: number[][]) {
  let twiceArea = 0;
  let centroidColumn = 0;
  let centroidRow = 0;
  for (let index = 0; index < ring.length - 1; index += 1) {
    const current = ring[index];
    const next = ring[index + 1];
    const cross = current[0] * next[1] - next[0] * current[1];
    twiceArea += cross;
    centroidColumn += (current[0] + next[0]) * cross;
    centroidRow += (current[1] + next[1]) * cross;
  }
  if (twiceArea === 0) {
    return null;
  }
  return {
    area: twiceArea / 2,
    centroid: { column: centroidColumn / (3 * twiceArea), row: centroidRow / (3 * twiceArea) },
  };
}

function gridPolygonCentroid(polygon: Polygon) {
  const outer = gridRingAreaAndCentroid(polygon[0]);
  return outer?.centroid ?? { column: polygon[0][0][0], row: polygon[0][0][1] };
}

function interiorGridPoint(
  polygons: MultiPolygon,
  occupiedCells: Array<{ column: number; row: number }>,
) {
  const fallback = occupiedCells[0] ?? { column: 0, row: 0 };
  let bestPolygon = polygons[0];
  let bestArea = 0;
  polygons.forEach((polygon) => {
    const area = Math.abs(gridRingAreaAndCentroid(polygon[0])?.area ?? 0);
    if (area > bestArea) {
      bestArea = area;
      bestPolygon = polygon;
    }
  });
  if (!bestPolygon) {
    return fallback;
  }
  const target = gridPolygonCentroid(bestPolygon);
  const candidates = occupiedCells.filter((cell) => pointInPolygon(cell, bestPolygon));
  return (candidates.length > 0 ? candidates : occupiedCells).reduce((best, cell) => {
    const bestDistance = Math.hypot(best.column - target.column, best.row - target.row);
    const cellDistance = Math.hypot(cell.column - target.column, cell.row - target.row);
    return cellDistance < bestDistance ? cell : best;
  }, fallback);
}

function groupId(group: DetectionPoint[]) {
  const [first] = group;
  return `firms-group-${first.id.slice(0, 12)}-${group.length}`;
}

function finitePosition(position: number[]) {
  return (
    position.length >= 2 &&
    Number.isFinite(position[0]) &&
    Number.isFinite(position[1]) &&
    position[0] >= -180 &&
    position[0] <= 180 &&
    position[1] >= -90 &&
    position[1] <= 90
  );
}

function closedRing(ring: number[][]) {
  if (ring.length < 4 || ring.some((position) => !finitePosition(position))) {
    return null;
  }
  const first = ring[0];
  const last = ring[ring.length - 1];
  if (first[0] === last[0] && first[1] === last[1]) {
    return ring;
  }
  return [...ring, first];
}

function validPolygon(polygon: Polygon) {
  const rings = polygon.flatMap((ring) => {
    const closed = closedRing(ring);
    return closed ? [closed] : [];
  });
  return rings.length > 0 ? (rings as Polygon) : null;
}

function validMultiPolygon(polygons: MultiPolygon) {
  return polygons.flatMap((polygon) => {
    const valid = validPolygon(polygon);
    return valid ? [valid] : [];
  }) as MultiPolygon;
}

function detailedGroupGeometry(group: DetectionPoint[]) {
  const grid = gridCellPolygons(group);
  const polygons = grid.polygons.flatMap((polygon) => {
    const valid = validPolygon(polygon);
    return valid ? [valid] : [];
  });
  if (polygons.length === 0) {
    return {
      geometry: { type: "Point" as const, coordinates: [group[0].longitude, group[0].latitude] },
      grid,
    };
  }
  const coordinates = polygons as MultiPolygon;
  if (coordinates.length === 1) {
    return { geometry: { type: "Polygon" as const, coordinates: coordinates[0] }, grid };
  }
  return { geometry: { type: "MultiPolygon" as const, coordinates }, grid };
}

function detectionGroupFeature(group: DetectionPoint[]): CivilFeature {
  const [first] = group;
  const id = groupId(group);
  const { geometry, grid } = detailedGroupGeometry(group);
  const observedDates = group
    .map((point) => point.feature.properties.observed_at)
    .filter((date): date is string => typeof date === "string" && date.length > 0)
    .sort();
  return {
    ...first.feature,
    id,
    properties: {
      ...first.feature.properties,
      id,
      observed_at: observedDates[0] ?? first.feature.properties.observed_at,
      updated_at: observedDates[observedDates.length - 1] ?? first.feature.properties.updated_at,
      data_type: group.length > 1 ? "wildfire_detection_group" : first.feature.properties.data_type,
      properties: {
        ...first.feature.properties.properties,
        detection_count: group.length,
        oldest_detection_at: observedDates[0] ?? null,
        newest_detection_at: observedDates[observedDates.length - 1] ?? null,
        focus_area_square_meters: grid.areaSquareMeters,
        label_longitude: grid.labelCoordinate[0],
        label_latitude: grid.labelCoordinate[1],
        firm_points_json: JSON.stringify(
          group.map((point) => ({
            id: point.id,
            longitude: point.longitude,
            latitude: point.latitude,
            observed_at: point.feature.properties.observed_at,
            footprint_size_meters: Math.max(point.scan_meters, point.track_meters),
            connection_distance_meters: point.connection_distance_meters,
          })),
        ),
        footprint_shape: group.length > 1 ? "firms_oriented_grid_union" : "nasa_firms_pixel_square",
        footprint_width_meters: grid.width,
        footprint_height_meters: grid.height,
        footprint_grid_angle_degrees: (grid.angle * 180) / Math.PI,
      },
    },
    geometry,
  };
}

export function detectionAreas(collection: CivilFeatureCollection): CivilFeatureCollection {
  const points = collection.features
    .map(detectionPoint)
    .filter((point): point is DetectionPoint => Boolean(point));
  return {
    ...collection,
    features: connectedDetectionGroups(points).flatMap((group) => {
      try {
        return [detectionGroupFeature(group)];
      } catch {
        return group.map((point) => point.feature);
      }
    }),
  };
}

function queryString(params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  return search.toString();
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Civil API request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function getCivilCollection(path: string, limit = 50): Promise<CivilCollection> {
  return request<CivilCollection>(`${path}?${queryString({ limit, sort: "updated_desc" })}`);
}

async function getNoticeSource(source: string, limit: number, observedFrom?: string) {
  const items: CivilItem[] = [];
  for (let offset = 0; offset < limit; offset += LAYER_PAGE_SIZE) {
    const page = await request<CivilCollection>(
      `/civil/notices?${queryString({
        source,
        observed_from: observedFrom,
        limit: Math.min(LAYER_PAGE_SIZE, limit - offset),
        offset,
        sort: "updated_desc",
      })}`,
    );
    items.push(...page.items);
    if (page.items.length < LAYER_PAGE_SIZE) {
      break;
    }
  }
  return items;
}

export async function getCivilNotices(): Promise<CivilCollection> {
  const aemetObservedFrom = new Date(Date.now() - 4 * 24 * 60 * 60 * 1_000).toISOString();
  const [aemet, catalonia] = await Promise.all([
    getNoticeSource("AEMET Meteoalerta", MAX_AEMET_NOTICES, aemetObservedFrom),
    getNoticeSource("Proteccio Civil", LAYER_PAGE_SIZE),
  ]);
  const items = [...aemet, ...catalonia].sort((first, second) =>
    String(second.updated_at ?? "").localeCompare(String(first.updated_at ?? "")),
  );
  return {
    data_type: "civil_collection",
    items,
    pagination: { limit: items.length, offset: 0, count: items.length },
    warnings: [],
  };
}

export async function getCivilFeatureCollection(
  path: string,
  filters: CivilFilters,
  observedFrom?: string,
  limit = 50,
): Promise<CivilFeatureCollection> {
  return request<CivilFeatureCollection>(
    `${path}?${queryString({
      bbox: filters.bbox,
      observed_from: observedFrom,
      only_current: false,
      limit,
      sort: "observed_desc",
      format: "geojson",
    })}`,
  );
}

export async function getCivilIncident(incidentId: string): Promise<CivilItem> {
  return request<CivilItem>(`/civil/incidents/${incidentId}`);
}

export async function getCivilLayer(
  layer: CivilLayerName,
  filters: CivilFilters,
  temporalWindow?: CivilTemporalWindow,
  perimeterPeriods?: string[],
): Promise<CivilFeatureCollection> {
  const pathByLayer: Record<CivilLayerName, string> = {
    detections: "/civil/detections",
    perimeters: "/civil/perimeters",
    evacuations: "/civil/es-alerts",
    restrictions: "/civil/restrictions",
    roads: "/civil/roads",
    risk: "/civil/risk",
    smoke: "/civil/smoke",
    aircraft: "/civil/aircraft/live",
  };
  if (layer === "aircraft") {
    return request<CivilFeatureCollection>(pathByLayer[layer]).catch(() => emptyFeatureCollection);
  }
  const features: CivilFeature[] = [];
  let pagination = emptyFeatureCollection.pagination;
  const maximumFeatures =
    layer === "detections"
      ? temporalWindow
        ? MAX_DAILY_FIRMS_FEATURES
        : MAX_FIRMS_FEATURES
      : layer === "perimeters"
        ? MAX_PERIMETER_FEATURES
        : MAX_LAYER_FEATURES;
  for (let offset = 0; offset < maximumFeatures; offset += LAYER_PAGE_SIZE) {
    const page = await request<CivilFeatureCollection>(
      `${pathByLayer[layer]}?${queryString({
        bbox: filters.bbox,
        min_confidence: filters.minConfidence,
        only_current: temporalWindow || layer === "perimeters" ? false : filters.onlyCurrent,
        observed_from: temporalWindow?.observedFrom,
        observed_to: temporalWindow?.observedTo,
        perimeter_period: layer === "perimeters" ? perimeterPeriods?.join(",") : undefined,
        limit: LAYER_PAGE_SIZE,
        offset,
        format: "geojson",
        sort: "updated_desc",
      })}`,
    ).catch(() => emptyFeatureCollection);
    features.push(...page.features);
    pagination = page.pagination;
    if (page.features.length < LAYER_PAGE_SIZE) {
      break;
    }
  }
  const collection: CivilFeatureCollection = {
    type: "FeatureCollection",
    features,
    pagination: {
      ...pagination,
      limit: LAYER_PAGE_SIZE,
      offset: Math.max(0, features.length - LAYER_PAGE_SIZE),
      count: features.length,
    },
  };
  return layer === "detections" ? detectionAreas(collection) : collection;
}

export async function getFirmsTimeline(filters: CivilFilters): Promise<FirmsTimeline> {
  return request<FirmsTimeline>(
    `/civil/detections/timeline?${queryString({
      bbox: filters.bbox,
      min_confidence: filters.minConfidence,
    })}`,
  );
}

export async function searchCivilMunicipality(municipality: string): Promise<CivilCollection> {
  return request<CivilCollection>(
    `/civil/search/municipality?${queryString({ municipality, limit: 50 })}`,
  );
}

export async function lookupMunicipalities(query: string): Promise<MunicipalityLookupResponse> {
  return request<MunicipalityLookupResponse>(
    `/civil/municipalities/search?${queryString({ q: query, limit: 8 })}`,
  );
}

export async function getOsintIncidentDetail(incidentId: string): Promise<OsintIncidentDetail> {
  return request<OsintIncidentDetail>(`/civil/osint/incidents/${incidentId}`);
}

export async function getInstitutionalXAccounts(): Promise<InstitutionalXAccountsResponse> {
  return request<InstitutionalXAccountsResponse>("/civil/osint/x-accounts");
}
