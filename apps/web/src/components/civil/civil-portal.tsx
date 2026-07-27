"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { MapShell } from "@/components/map-shell";
import {
  type CivilCollection,
  type CivilFeature,
  type CivilFeatureCollection,
  type CivilFilters,
  type CivilItem,
  type CivilLayerName,
  type CivilLayerState,
  getCivilCollection,
  getCivilLayer,
  lookupMunicipalities,
} from "@/lib/api/civil";
import { useMapViewportStore } from "@/lib/state/map-store";

const layerLabels: Record<CivilLayerName, string> = {
  detections: "Deteccions",
  perimeters: "Perimetres",
  evacuations: "Evacuacions",
  restrictions: "Restriccions a Carreteres",
  roads: "Carreteres",
  risk: "Risc",
  smoke: "Fum",
};

const layerNames = Object.keys(layerLabels) as CivilLayerName[];

const sourceDescriptions: Record<string, string> = {
  "NASA FIRMS":
    "Deteccions satel·litàries de punts calents. Les àrees es reconstrueixen agrupant la graella i la mida scan/track dels píxels actius; poden contenir forats on no hi ha detecció. No són perímetres oficials ni confirmació administrativa d'incendi.",
  "Municipios IGN":
    "Base municipal oficial utilitzada només per localitzar municipis i centrar el mapa.",
  AEMET:
    "Observacions i prediccions meteorològiques oficials. Serveixen per context de risc, vent i condicions ambientals.",
  IGN:
    "Cartografia i dades geogràfiques oficials de referència.",
  OpenStreetMap:
    "Cartografia col·laborativa utilitzada per capes viàries i mapa base quan no hi ha font oficial equivalent integrada.",
  EFFIS:
    "Informació europea harmonitzada de focs forestals. Els perímetres i àrees cremades són productes satel·litaris estimats/verificats segons metodologia EFFIS.",
};

const emptyCollection: CivilCollection = {
  data_type: "civil_collection",
  items: [],
  pagination: { limit: 50, offset: 0, count: 0 },
  warnings: [],
};

const emptyFeatureCollection: CivilFeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

function itemTitle(item: CivilItem) {
  return (
    String(item.properties.title ?? item.properties.name ?? item.properties.road_ref ?? item.data_type) ||
    item.data_type
  );
}

function itemSubtitle(item: CivilItem) {
  const source = item.source.name ?? item.source.authority ?? "Font no informada";
  const updated = item.updated_at ? new Date(item.updated_at).toLocaleString("ca-ES") : "sense data";
  return `${source} · ${updated}`;
}

function confidenceLabel(value: number | null) {
  if (value === null) {
    return "confiança no calculada";
  }
  return `${Math.round(value * 100)}% confiança`;
}

function dateTimeLabel(value: unknown) {
  if (typeof value !== "string") {
    return "No informada";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "No informada" : date.toLocaleString("ca-ES");
}

function areaLabel(value: unknown) {
  const area = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(area)) {
    return "No informada";
  }
  return `${Math.round(area).toLocaleString("ca-ES")} m2`;
}

function featureItem(feature: CivilFeature) {
  return feature.properties;
}

function flattenLayerItems(layers: CivilLayerState, visibleLayers: Record<CivilLayerName, boolean>) {
  return layerNames.flatMap((layer) =>
    visibleLayers[layer] ? layers[layer].features.map(featureItem) : [],
  );
}

function sourceRows(items: CivilItem[]) {
  const rows = new Map<
    string,
    { name: string; updated: string; count: number; warning: boolean; description: string }
  >();
  items.forEach((item) => {
    const name = item.source.name ?? item.source.authority ?? "Font no informada";
    const updated = item.updated_at ?? "";
    const current = rows.get(name);
    rows.set(name, {
      name,
      updated: !current || updated > current.updated ? updated : current.updated,
      count: (current?.count ?? 0) + 1,
      warning: (current?.warning ?? false) || item.warnings.length > 0 || item.provenance === "estimated",
      description:
        current?.description ??
        sourceDescriptions[name] ??
        "Font de dades pública integrada al portal. Consulta la traçabilitat de cada element abans de prendre-la com a dada oficial.",
    });
  });
  return Array.from(rows.values()).sort((first, second) => second.updated.localeCompare(first.updated));
}

function StatusBadge({ item }: { item: CivilItem }) {
  return (
    <span className="inline-flex items-center gap-2 rounded border border-[#cfd8d1] bg-white px-2 py-1 text-xs font-semibold">
      <span
        className={[
          "h-2.5 w-2.5 rounded-full border",
          item.provenance === "official"
            ? "border-[#1f6f50] bg-[#1f6f50]"
            : item.provenance === "estimated"
              ? "border-[#7a8791] bg-white"
              : "border-[#b42318] bg-[#b42318]",
        ].join(" ")}
      />
      {item.provenance === "estimated" ? "estimada" : item.provenance === "official" ? "oficial" : "observada"}
    </span>
  );
}

function ItemCard({ item, selected, onSelect }: { item: CivilItem; selected?: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={[
        "w-full rounded-md border bg-white p-3 text-left shadow-sm transition focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[#1d5fd0]",
        selected ? "border-[#1d5fd0]" : "border-[#d7ddd8] hover:border-[#9aa8a0]",
        item.is_current ? "" : "opacity-60",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold">{itemTitle(item)}</h3>
          <p className="mt-1 text-xs text-[#53605a]">{itemSubtitle(item)}</p>
        </div>
        <StatusBadge item={item} />
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-[#3f454d]">
        <span>{confidenceLabel(item.confidence)}</span>
        {item.warnings.length > 0 ? <span>advertiments: {item.warnings.length}</span> : null}
        {!item.is_current ? <span>dada antiga</span> : null}
      </div>
    </button>
  );
}

function DetailPanel({ item }: { item: CivilItem | null }) {
  if (!item) {
    return (
      <section className="rounded-md border border-[#d7ddd8] bg-white p-4">
        <h2 className="text-base font-bold">Detall d'incident</h2>
        <p className="mt-2 text-sm text-[#53605a]">Selecciona un element de la llista o del mapa.</p>
      </section>
    );
  }

  return (
    <section className="rounded-md border border-[#d7ddd8] bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-bold">{itemTitle(item)}</h2>
          <p className="mt-1 text-sm text-[#53605a]">{item.data_type}</p>
        </div>
        <StatusBadge item={item} />
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="font-semibold">Font</dt>
          <dd>{item.source.name ?? item.source.authority ?? "No informada"}</dd>
        </div>
        <div>
          <dt className="font-semibold">Confiança</dt>
          <dd>{confidenceLabel(item.confidence)}</dd>
        </div>
        <div>
          <dt className="font-semibold">Observat</dt>
          <dd>{item.observed_at ? new Date(item.observed_at).toLocaleString("ca-ES") : "No informat"}</dd>
        </div>
        <div>
          <dt className="font-semibold">Actualitzat</dt>
          <dd>{item.updated_at ? new Date(item.updated_at).toLocaleString("ca-ES") : "No informat"}</dd>
        </div>
      </dl>
      {item.source.url ? (
        <a className="mt-4 inline-block text-sm font-semibold text-[#1d5fd0]" href={item.source.url}>
          Obrir font
        </a>
      ) : null}
      {item.provenance === "estimated" || item.warnings.length > 0 ? (
        <div className="mt-4 rounded-md border border-[#d2b45b] bg-[#fff8dd] p-3 text-sm">
          Estimacio o advertiment present. No tractar com a comunicat oficial.
        </div>
      ) : null}
      {item.data_type === "wildfire_detection_group" ? (
        <dl className="mt-4 grid gap-3 border-t border-[#edf0ed] pt-4 text-sm">
          <div>
            <dt className="font-semibold">Deteccio mes antiga</dt>
            <dd>{dateTimeLabel(item.properties.oldest_detection_at)}</dd>
          </div>
          <div>
            <dt className="font-semibold">Deteccio mes nova</dt>
            <dd>{dateTimeLabel(item.properties.newest_detection_at)}</dd>
          </div>
          <div>
            <dt className="font-semibold">Superficie del focus</dt>
            <dd>{areaLabel(item.properties.focus_area_square_meters)}</dd>
          </div>
        </dl>
      ) : null}
    </section>
  );
}

function Legend() {
  return (
    <section className="rounded-md border border-[#d7ddd8] bg-white p-4">
      <h2 className="text-base font-bold">Llegenda</h2>
      <div className="mt-3 grid gap-2 text-sm">
        <span className="flex items-center gap-2">
          <span className="h-4 w-4 border border-[#7a1f17] bg-[#b42318] opacity-70" /> Àrea reconstruïda NASA FIRMS
        </span>
        <span className="flex items-center gap-2">
          <span className="h-4 w-4 rounded-full border-2 border-white bg-[#c81e1e] shadow" /> Pin grup FIRMS
        </span>
        <span className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-[#5f120e]" /> Punt calent FIRMS
        </span>
        <span className="flex items-center gap-2">
          <span className="h-3 w-8 border-t-4 border-[#8a2f16]" /> Perimetre oficial
        </span>
        <span className="flex items-center gap-2">
          <span className="h-3 w-8 border-t-4 border-dashed border-[#8a2f16]" /> Perimetre estimat
        </span>
        <span className="flex items-center gap-2 opacity-60">
          <span className="h-3 w-8 border-t-4 border-[#3f454d]" /> Dada antiga
        </span>
      </div>
    </section>
  );
}

export function CivilPortal() {
  const searchParams = useSearchParams();
  const viewport = useMapViewportStore();
  const lastUrlRef = useRef("");
  const [selectedId, setSelectedId] = useState<string | null>(searchParams.get("selected"));
  const [municipality, setMunicipality] = useState(searchParams.get("municipality") ?? "");
  const [mapFocusBbox, setMapFocusBbox] = useState(
    searchParams.get("focusBbox") ?? searchParams.get("bbox") ?? "-10,35,5,44",
  );
  const [municipalityError, setMunicipalityError] = useState<string | null>(null);
  const [municipalityStatus, setMunicipalityStatus] = useState<string | null>(null);
  const [filters, setFilters] = useState<CivilFilters>({
    bbox: searchParams.get("bbox") ?? "-10,35,5,44",
    municipality: searchParams.get("municipality") ?? "",
    minConfidence: 0,
    onlyCurrent: searchParams.get("onlyCurrent") !== "false",
  });
  const [visibleLayers, setVisibleLayers] = useState<Record<CivilLayerName, boolean>>({
    detections: true,
    perimeters: true,
    evacuations: true,
    restrictions: true,
    roads: true,
    risk: true,
    smoke: true,
  });
  const [showFirmHotspots, setShowFirmHotspots] = useState(false);

  const layerQueries = useQueries({
    queries: layerNames.map((layer) => ({
      queryKey: ["civil-layer", layer, filters],
      queryFn: () => getCivilLayer(layer, filters),
      enabled: layer !== "roads",
      staleTime: 5 * 60 * 1000,
      refetchOnWindowFocus: false,
    })),
  });

  const incidentsQuery = useQuery({
    queryKey: ["civil-incidents"],
    queryFn: () => getCivilCollection("/civil/incidents", 50),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
  const noticesQuery = useQuery({
    queryKey: ["civil-notices"],
    queryFn: () => getCivilCollection("/civil/notices", 50),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
  const layers = useMemo(
    () =>
      layerNames.reduce((accumulator, layer, index) => {
        accumulator[layer] = layerQueries[index]?.data ?? emptyFeatureCollection;
        return accumulator;
      }, {} as CivilLayerState),
    [layerQueries],
  );
  const layerItems = useMemo(() => flattenLayerItems(layers, visibleLayers), [layers, visibleLayers]);
  const incidents = incidentsQuery.data?.items ?? emptyCollection.items;
  const notices = noticesQuery.data?.items ?? emptyCollection.items;
  const allItems = useMemo(() => [...incidents, ...notices, ...layerItems], [incidents, layerItems, notices]);
  const selectedItem = allItems.find((item) => item.id === selectedId) ?? null;
  const loading = layerQueries.some((query) => query.isLoading) || incidentsQuery.isLoading || noticesQuery.isLoading;
  const error = layerQueries.some((query) => query.isError) || incidentsQuery.isError || noticesQuery.isError;

  useEffect(() => {
    const params = new URLSearchParams();
    params.set("bbox", filters.bbox);
    params.set("focusBbox", mapFocusBbox);
    if (filters.municipality) {
      params.set("municipality", filters.municipality);
    }
    if (!filters.onlyCurrent) {
      params.set("onlyCurrent", "false");
    }
    if (selectedId) {
      params.set("selected", selectedId);
    }
    params.set("lng", viewport.longitude.toFixed(4));
    params.set("lat", viewport.latitude.toFixed(4));
    params.set("z", viewport.zoom.toFixed(2));
    const nextUrl = `/civil?${params.toString()}`;
    if (lastUrlRef.current === nextUrl) {
      return;
    }
    const timeout = window.setTimeout(() => {
      const currentUrl = `${window.location.pathname}${window.location.search}`;
      if (currentUrl !== nextUrl) {
        lastUrlRef.current = nextUrl;
        window.history.replaceState(window.history.state, "", nextUrl);
      }
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [filters, mapFocusBbox, selectedId, viewport.latitude, viewport.longitude, viewport.zoom]);

  const applyMunicipality = async () => {
    const query = municipality.trim();
    if (query.length < 2) {
      return;
    }
    setMunicipalityError(null);
    setMunicipalityStatus("Cercant municipi a IGN...");
    try {
      const result = await lookupMunicipalities(query);
      const bestMatch = result.items[0];
      if (!bestMatch) {
        setMunicipalityError("No he trobat aquest municipi a la font IGN.");
        setMunicipalityStatus(null);
        return;
      }
      setMunicipality(bestMatch.name);
      setFilters((current) => ({
        ...current,
        municipality: bestMatch.name,
      }));
      setMapFocusBbox(bestMatch.bbox);
      setMunicipalityStatus(`${bestMatch.name} centrat amb dades IGN.`);
    } catch {
      setMunicipalityError("No es pot consultar el cercador de municipis ara mateix.");
      setMunicipalityStatus(null);
    }
  };

  return (
    <main className="min-h-screen">
      <header className="border-b border-[#d7ddd8] bg-white px-4 py-4 md:px-6">
        <p className="text-sm font-semibold uppercase text-canopy">Portal Civil</p>
        <h1 className="mt-1 text-2xl font-bold">Incendis i avisos publics</h1>
        <nav aria-label="Seccions Civil" className="mt-4 flex gap-2 overflow-x-auto text-sm">
          {["mapa", "incidents", "evacuacions", "carreteres", "metodologia", "fonts", "estat"].map((section) => (
            <a key={section} className="rounded border border-[#d7ddd8] bg-white px-3 py-2" href={`#${section}`}>
              {section}
            </a>
          ))}
        </nav>
      </header>

      <section className="grid gap-4 p-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="order-2 grid content-start gap-3 self-start lg:order-1" aria-label="Panell Civil">
          <section className="rounded-md border border-[#d7ddd8] bg-white p-3">
            <h2 className="text-base font-bold">Filtres</h2>
            <div className="mt-2 grid gap-2">
              <label className="grid gap-1 text-sm font-semibold">
                Municipi
                <span className="flex gap-2">
                  <input
                    value={municipality}
                    onChange={(event) => setMunicipality(event.target.value)}
                    className="min-w-0 flex-1 rounded border border-[#aeb9b1] px-2 py-1.5"
                    placeholder="Nom"
                  />
                  <button
                    type="button"
                    onClick={applyMunicipality}
                    className="rounded bg-[#1f6f50] px-3 py-1.5 text-sm font-bold text-white"
                  >
                    Cerca
                  </button>
                </span>
              </label>
              {municipalityStatus ? <p className="text-xs text-[#1f6f50]">{municipalityStatus}</p> : null}
              {municipalityError ? <p className="text-xs font-semibold text-[#b42318]">{municipalityError}</p> : null}
              <label className="flex items-center gap-2 text-sm font-semibold">
                <input
                  type="checkbox"
                  checked={filters.onlyCurrent}
                  onChange={(event) =>
                    setFilters((current) => ({ ...current, onlyCurrent: event.target.checked }))
                  }
                />
                Nomes dades vigents
              </label>
            </div>
          </section>

          <section className="rounded-md border border-[#d7ddd8] bg-white p-3">
            <h2 className="text-base font-bold">Capes</h2>
            <div className="mt-2 grid grid-cols-2 gap-1.5">
              {layerNames.filter((layer) => layer !== "roads").map((layer) => (
                <label key={layer} className="flex items-center gap-2 rounded border border-[#d7ddd8] px-2 py-1.5 text-xs">
                  <input
                    type="checkbox"
                    checked={visibleLayers[layer]}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setVisibleLayers((current) => ({
                        ...current,
                        [layer]: checked,
                        ...(layer === "restrictions" ? { roads: checked } : {}),
                      }));
                    }}
                  />
                  {layerLabels[layer]}
                </label>
              ))}
              <label className="flex items-center gap-2 rounded border border-[#d7ddd8] px-2 py-1.5 text-xs">
                <input
                  type="checkbox"
                  checked={showFirmHotspots}
                  onChange={(event) => setShowFirmHotspots(event.target.checked)}
                />
                Punts FIRMS
              </label>
            </div>
          </section>

          <Legend />
          <DetailPanel item={selectedItem} />
        </aside>

        <section className="order-1 grid gap-4 lg:order-2">
          <section id="mapa" className="grid gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-bold">Mapa</h2>
              <p className="text-sm text-[#53605a]">
                {loading ? "Carregant dades..." : `${allItems.length} elements publics`}
              </p>
            </div>
            {error ? (
              <div className="rounded-md border border-[#b42318] bg-white p-4 text-sm">
                No es poden carregar algunes capes ara mateix.
              </div>
            ) : null}
            <div className="min-h-[620px] h-[72vh] max-h-[860px]">
              <MapShell
                portal="civil"
                civilLayers={layers}
                visibleLayers={visibleLayers}
                bbox={mapFocusBbox}
                showFirmHotspots={showFirmHotspots}
                onFeatureSelect={setSelectedId}
              />
            </div>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <section id="incidents" className="grid gap-3">
              <h2 className="text-lg font-bold">Incidents</h2>
              {incidents.length === 0 ? (
                <p className="rounded-md border border-[#d7ddd8] bg-white p-4 text-sm text-[#53605a]">
                  Sense incidents publics amb els filtres actuals.
                </p>
              ) : (
                incidents.map((item) => (
                  <ItemCard key={item.id} item={item} selected={item.id === selectedId} onSelect={() => setSelectedId(item.id)} />
                ))
              )}
            </section>

            <section id="avisos" className="grid gap-3">
              <h2 className="text-lg font-bold">Avisos i cronologia</h2>
              {notices.length === 0 ? (
                <p className="rounded-md border border-[#d7ddd8] bg-white p-4 text-sm text-[#53605a]">
                  Sense avisos publics disponibles.
                </p>
              ) : (
                notices.map((item) => (
                  <ItemCard key={item.id} item={item} selected={item.id === selectedId} onSelect={() => setSelectedId(item.id)} />
                ))
              )}
            </section>
          </section>

          <section className="grid gap-4 xl:grid-cols-3">
            {[
              ["evacuacions", "Evacuacions", visibleLayers.evacuations ? layers.evacuations.features : []],
              [
                "restriccions",
                "Restriccions a Carreteres",
                visibleLayers.restrictions
                  ? layers.restrictions.features
                  : [],
              ],
            ].map(([id, title, features]) => (
              <section key={String(id)} id={String(id)} className="rounded-md border border-[#d7ddd8] bg-white p-4">
                <h2 className="text-base font-bold">{String(title)}</h2>
                <p className="mt-2 text-sm text-[#53605a]">{(features as CivilFeature[]).length} elements</p>
              </section>
            ))}
          </section>

          <section id="metodologia" className="rounded-md border border-[#d7ddd8] bg-white p-4">
            <h2 className="text-base font-bold">Metodologia</h2>
            <p className="mt-2 text-sm text-[#53605a]">
              Les dades oficials, observades i estimades es mostren separades. Les estimacions antigues perden
              vigencia visual i porten advertiment.
            </p>
          </section>

          <section id="fonts" className="rounded-md border border-[#d7ddd8] bg-white p-4">
            <h2 className="text-base font-bold">Fonts</h2>
            <div className="mt-3 grid gap-2">
              {sourceRows(allItems).length === 0 ? (
                <p className="text-sm text-[#53605a]">Cap font amb dades visibles.</p>
              ) : (
                sourceRows(allItems).map((source) => (
                  <div key={source.name} className="border-t border-[#edf0ed] py-3 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-semibold">{source.name}</span>
                      <span className={source.warning ? "font-semibold text-[#8a2f16]" : "text-[#53605a]"}>
                        {source.count} elements
                      </span>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-[#53605a]">{source.description}</p>
                  </div>
                ))
              )}
            </div>
          </section>

          <section id="estat" className="rounded-md border border-[#d7ddd8] bg-white p-4">
            <h2 className="text-base font-bold">Estat de dades</h2>
            <p className="mt-2 text-sm text-[#53605a]">
              {loading
                ? "Carregant estat..."
                : error
                  ? "Alguna font no respon correctament."
                  : "Fonts consultades correctament."}
            </p>
          </section>
        </section>
      </section>
    </main>
  );
}
