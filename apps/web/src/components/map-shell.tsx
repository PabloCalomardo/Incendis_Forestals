"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import type { StyleSpecification } from "maplibre-gl";
import { useMapViewportStore } from "@/lib/state/map-store";

type MapShellProps = {
  portal: "civil" | "bomber";
};

export function MapShell({ portal }: MapShellProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const setViewport = useMapViewportStore((state) => state.setViewport);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const landColor = portal === "civil" ? "#d9e8dc" : "#25352e";
    const lineColor = portal === "civil" ? "#6c8b76" : "#8bb89b";
    const pointColor = portal === "civil" ? "#b42318" : "#ffb199";
    const baseStyle = {
      version: 8,
      sources: {
        "local-reference": {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                properties: { kind: "mainland" },
                geometry: {
                  type: "Polygon",
                  coordinates: [
                    [
                      [-9.35, 43.75],
                      [-7.1, 43.7],
                      [-1.8, 43.45],
                      [3.25, 42.45],
                      [3.1, 41.2],
                      [1.2, 40.0],
                      [0.1, 38.7],
                      [-0.7, 37.3],
                      [-2.4, 36.2],
                      [-5.8, 36.0],
                      [-7.4, 37.1],
                      [-9.0, 38.8],
                      [-9.35, 43.75],
                    ],
                  ],
                },
              },
              {
                type: "Feature",
                properties: { kind: "island" },
                geometry: {
                  type: "Polygon",
                  coordinates: [
                    [
                      [1.05, 39.1],
                      [3.55, 39.1],
                      [4.25, 40.2],
                      [2.75, 40.45],
                      [1.05, 39.1],
                    ],
                  ],
                },
              },
              {
                type: "Feature",
                properties: { kind: "center" },
                geometry: { type: "Point", coordinates: [-3.7, 40.4] },
              },
            ],
          },
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
      },
      layers: [
        {
          id: "background",
          type: "background",
          paint: {
            "background-color": portal === "civil" ? "#eef3ef" : "#111820",
          },
        },
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
          id: "reference-land",
          type: "fill",
          source: "local-reference",
          filter: ["in", ["get", "kind"], ["literal", ["mainland", "island"]]],
          paint: {
            "fill-color": landColor,
            "fill-opacity": portal === "civil" ? 0.85 : 0.55,
          },
        },
        {
          id: "reference-outline",
          type: "line",
          source: "local-reference",
          filter: ["in", ["get", "kind"], ["literal", ["mainland", "island"]]],
          paint: {
            "line-color": lineColor,
            "line-width": 2,
          },
        },
        {
          id: "reference-center",
          type: "circle",
          source: "local-reference",
          filter: ["==", ["get", "kind"], "center"],
          paint: {
            "circle-color": pointColor,
            "circle-radius": 6,
            "circle-stroke-color": portal === "civil" ? "#ffffff" : "#151b20",
            "circle-stroke-width": 2,
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

    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");

    map.on("moveend", () => {
      const center = map.getCenter();
      setViewport({ longitude: center.lng, latitude: center.lat, zoom: map.getZoom() });
    });

    return () => map.remove();
  }, [portal, setViewport]);

  return (
    <div className="min-h-[520px] overflow-hidden rounded-lg border border-[#d7ddd8] bg-white shadow-sm">
      <div ref={containerRef} className="h-full min-h-[520px]" aria-label={`Mapa ${portal}`} />
    </div>
  );
}
