import { afterEach, describe, expect, it, vi } from "vitest";
import { detectionAreas, getCivilLayer, type CivilFeature, type CivilFeatureCollection } from "./civil";

const METERS_PER_DEGREE = 111_320;

function viirsFeature(id: string, x: number, y: number, angleDegrees: number): CivilFeature {
  const angle = (angleDegrees * Math.PI) / 180;
  const rotatedX = x * Math.cos(angle) - y * Math.sin(angle);
  const rotatedY = x * Math.sin(angle) + y * Math.cos(angle);
  const latitude = 40 + rotatedY / METERS_PER_DEGREE;
  const longitude = -3 + rotatedX / (METERS_PER_DEGREE * Math.cos((40 * Math.PI) / 180));
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [longitude, latitude] },
    properties: {
      id,
      data_type: "wildfire_detection",
      source: { name: "NASA FIRMS", authority: "NASA", url: null, attribution: null },
      observed_at: "2026-07-26T12:00:00Z",
      updated_at: "2026-07-26T12:00:00Z",
      age_seconds: 0,
      confidence: 0.8,
      confidence_category: "nominal",
      provenance: "observed",
      is_current: true,
      warnings: [],
      properties: {
        sensor: "VIIRS",
        latitude,
        longitude,
        scan_km: 0.4,
        track_km: 0.4,
      },
    },
  };
}

describe("detectionAreas", () => {
  it("creates one oriented polygon and preserves an inactive cell as a hole", () => {
    const features: CivilFeature[] = [];
    for (let row = -1; row <= 1; row += 1) {
      for (let column = -1; column <= 1; column += 1) {
        if (row === 0 && column === 0) {
          continue;
        }
        features.push(viirsFeature(`${column}:${row}`, column * 400, row * 400, 12));
      }
    }
    const collection: CivilFeatureCollection = { type: "FeatureCollection", features };

    const result = detectionAreas(collection);

    expect(result.features).toHaveLength(1);
    expect(result.features[0].geometry?.type).toBe("Polygon");
    if (result.features[0].geometry?.type === "Polygon") {
      expect(result.features[0].geometry.coordinates).toHaveLength(2);
    }
    expect(result.features[0].properties.properties.detection_count).toBe(8);
    expect(Number(result.features[0].properties.properties.focus_area_square_meters)).toBeGreaterThan(0);
    expect(result.features[0].properties.properties.oldest_detection_at).toBe("2026-07-26T12:00:00Z");
    expect(result.features[0].properties.properties.newest_detection_at).toBe("2026-07-26T12:00:00Z");
    expect(
      Number(result.features[0].properties.properties.footprint_grid_angle_degrees),
    ).toBeCloseTo(12, 1);
  });

  it("keeps generated group ids compact enough for map renderers", () => {
    const features: CivilFeature[] = [];
    for (let index = 0; index < 50; index += 1) {
      features.push(viirsFeature(`550e8400-e29b-41d4-a716-${String(index).padStart(12, "0")}`, index * 400, 0, 0));
    }
    const collection: CivilFeatureCollection = { type: "FeatureCollection", features };

    const result = detectionAreas(collection);

    expect(String(result.features[0].id).length).toBeLessThan(40);
    expect(result.features[0].properties.id).toBe(result.features[0].id);
  });

  it("dissolves adjacent grid cells before projecting them to the map", () => {
    const collection: CivilFeatureCollection = {
      type: "FeatureCollection",
      features: [
        viirsFeature("first", 0, 0, 9),
        viirsFeature("second", 400, 0, 9),
      ],
    };

    const result = detectionAreas(collection);

    expect(result.features).toHaveLength(1);
    expect(result.features[0].geometry?.type).toBe("Polygon");
    if (result.features[0].geometry?.type === "Polygon") {
      expect(result.features[0].geometry.coordinates).toHaveLength(1);
      expect(result.features[0].geometry.coordinates[0].length).toBeLessThanOrEqual(7);
    }
  });

  it("groups diagonal VIIRS grid neighbours into the same reconstructed area", () => {
    const collection: CivilFeatureCollection = {
      type: "FeatureCollection",
      features: [
        viirsFeature("first", 0, 0, 9),
        viirsFeature("second", 400, 400, 9),
      ],
    };

    const result = detectionAreas(collection);

    expect(result.features).toHaveLength(1);
    expect(result.features[0].properties.properties.detection_count).toBe(2);
  });
});

describe("getCivilLayer", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads paginated map layers beyond the first 200 features", async () => {
    const feature = viirsFeature("restriction", 0, 0, 0);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = new URL(String(input));
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const count = offset === 0 ? 200 : 17;
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            type: "FeatureCollection",
            features: Array.from({ length: count }, (_, index) => ({
              ...feature,
              id: `${offset + index}`,
              properties: { ...feature.properties, id: `${offset + index}` },
            })),
            pagination: { limit: 200, offset, count },
          }),
      } as Response);
    });

    const result = await getCivilLayer("restrictions", {
      bbox: "-10,35,5,45",
      municipality: "",
      minConfidence: 0,
      onlyCurrent: true,
    });

    expect(result.features).toHaveLength(217);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
