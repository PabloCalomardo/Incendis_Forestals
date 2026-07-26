import { create } from "zustand";

type Viewport = {
  longitude: number;
  latitude: number;
  zoom: number;
};

type MapViewportStore = Viewport & {
  setViewport: (viewport: Viewport) => void;
};

export const useMapViewportStore = create<MapViewportStore>((set) => ({
  longitude: -3.7,
  latitude: 40.4,
  zoom: 5,
  setViewport: (viewport) => set(viewport),
}));
