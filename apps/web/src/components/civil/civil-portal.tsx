"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { MapShell } from "@/components/map-shell";
import {
  type CivilCollection,
  type CivilFeature,
  type CivilFeatureCollection,
  type CivilFilters,
  type CivilItem,
  type CivilLayerName,
  type CivilLayerState,
  type OsintTimelineItem,
  getCivilFeatureCollection,
  getCivilIncident,
  getCivilLayer,
  getCivilNotices,
  getFirmsTimeline,
  getInstitutionalXAccounts,
  getOsintIncidentDetail,
  lookupMunicipalities,
} from "@/lib/api/civil";
import { useMapViewportStore } from "@/lib/state/map-store";

const layerLabels: Record<CivilLayerName, string> = {
  detections: "Deteccions",
  perimeters: "Perimetres",
  evacuations: "Alertes ES-Alert",
  restrictions: "Restriccions a Carreteres",
  roads: "Carreteres",
  risk: "Risc",
  smoke: "Fum",
  aircraft: "Aeronaus",
};

const layerNames = Object.keys(layerLabels) as CivilLayerName[];

type PerimeterPeriod = "current" | "year" | "historic";
type PerimeterPeriodVisibility = Record<PerimeterPeriod, boolean>;

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
const YEAR_MS = 365 * 24 * 60 * 60 * 1000;

const sourceDescriptions: Record<string, string> = {
  "NASA FIRMS":
    "Deteccions satel·litàries de punts calents. Les àrees es reconstrueixen agrupant la graella i la mida scan/track dels píxels actius; poden contenir forats on no hi ha detecció. No són perímetres oficials ni confirmació administrativa d'incendi.",
  "Municipios IGN":
    "Base municipal oficial utilitzada només per localitzar municipis i centrar el mapa.",
  AEMET:
    "Observacions i prediccions meteorològiques oficials. Serveixen per context de risc, vent i condicions ambientals.",
  "AEMET Meteoalerta":
    "Avisos meteorològics oficials en format CAP per a totes les comunitats autònomes.",
  IGN: "Cartografia i dades geogràfiques oficials de referència.",
  OpenStreetMap:
    "Cartografia col·laborativa utilitzada per capes viàries i mapa base quan no hi ha font oficial equivalent integrada.",
  EFFIS: [
    "Informació europea harmonitzada. Els perímetres d'àrea cremada són productes satel·litaris estimats d'EFFIS;",
    "no informen de les tasques operatives d'extinció.",
  ].join(" "),
  "Airplanes.live":
    "Dades ADS-B live consultades per matricula per complementar OpenSky quan el dataset OSINT no te ICAO24.",
  "OpenSky Network":
    "Vectors ADS-B live. El matching fiable requereix ICAO24; si falta, nomes es pot provar callsign/matricula.",
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
    String(
      item.properties.title ?? item.properties.name ?? item.properties.road_ref ?? item.data_type,
    ) || item.data_type
  );
}

function itemSubtitle(item: CivilItem) {
  const source = item.source.name ?? item.source.authority ?? "Font no informada";
  const updated = item.updated_at
    ? new Date(item.updated_at).toLocaleString("ca-ES")
    : "sense data";
  return `${source} · ${updated}`;
}

function incidentDescription(item: CivilItem) {
  if (item.data_type !== "incident" || item.properties.osint !== true) {
    return null;
  }
  const summary = String(item.properties.summary ?? "").trim();
  return summary && summary !== itemTitle(item) ? summary : null;
}

function isXOrNitterSource(name: unknown, url?: unknown) {
  const source = `${String(name ?? "")} ${String(url ?? "")}`.toLowerCase();
  return source.includes("nitter") || source.includes("x @") || source.includes("x.com/");
}

function isSocialOsintItem(item: CivilItem) {
  return (
    item.data_type === "incident" &&
    item.properties.osint === true &&
    item.properties.canonical_fire !== true &&
    isXOrNitterSource(item.source.name, item.source.url)
  );
}

function noticeLevel(item: CivilItem) {
  const value = String(item.properties.alert_level ?? item.properties.severity ?? "").toLowerCase();
  return value === "yellow" || value === "orange" || value === "red" ? value : null;
}

function noticeLevelClasses(item: CivilItem) {
  const level = noticeLevel(item);
  if (!level) {
    return "border-l-transparent";
  }
  return {
    yellow: "border-l-[#eab308]",
    orange: "border-l-[#f97316]",
    red: "border-l-[#dc2626]",
  }[level];
}

function noticeDotClasses(item: CivilItem) {
  const level = noticeLevel(item);
  if (!level) {
    return "border-[#7a8791] bg-white";
  }
  return {
    yellow: "border-[#a16207] bg-[#facc15]",
    orange: "border-[#c2410c] bg-[#f97316]",
    red: "border-[#991b1b] bg-[#dc2626]",
  }[level];
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

function firmsDayKey(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "unknown";
  }
  const parts = new Intl.DateTimeFormat("ca-ES", {
    timeZone: "Europe/Madrid",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? "00";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

function firmsDayLabel(day: string) {
  const date = new Date(`${day}T12:00:00Z`);
  return Number.isNaN(date.getTime())
    ? day
    : date.toLocaleDateString("ca-ES", { day: "2-digit", month: "long", year: "numeric" });
}

function areaLabel(value: unknown) {
  const area = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(area)) {
    return "No informada";
  }
  return `${Math.round(area).toLocaleString("ca-ES")} m2`;
}

function perimeterPeriod(feature: CivilFeature): PerimeterPeriod {
  const classified = feature.properties.properties.perimeter_period;
  if (classified === "current" || classified === "year" || classified === "historic") {
    return classified;
  }
  const value = feature.properties.properties.fire_date ?? feature.properties.observed_at;
  const timestamp = typeof value === "string" ? new Date(value).getTime() : Number.NaN;
  if (!Number.isFinite(timestamp)) {
    return "historic";
  }
  const age = Math.max(0, Date.now() - timestamp);
  if (age < WEEK_MS) {
    return "current";
  }
  return age < YEAR_MS ? "year" : "historic";
}

function visiblePerimeters(
  collection: CivilFeatureCollection,
  visibility: PerimeterPeriodVisibility,
): CivilFeatureCollection {
  return {
    ...collection,
    features: collection.features.flatMap((feature) => {
      const period = perimeterPeriod(feature);
      if (!visibility[period]) {
        return [];
      }
      return [
        {
          ...feature,
          properties: {
            ...feature.properties,
            properties: { ...feature.properties.properties, perimeter_period: period },
          },
        },
      ];
    }),
  };
}

function featureItem(feature: CivilFeature) {
  return { ...feature.properties, geometry: feature.geometry };
}

function flattenLayerItems(
  layers: CivilLayerState,
  visibleLayers: Record<CivilLayerName, boolean>,
) {
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
      warning:
        (current?.warning ?? false) || item.warnings.length > 0 || item.provenance === "estimated",
      description:
        current?.description ??
        sourceDescriptions[name] ??
        "Font de dades pública integrada al portal. Consulta la traçabilitat de cada element abans de prendre-la com a dada oficial.",
    });
  });
  return Array.from(rows.values()).sort((first, second) =>
    second.updated.localeCompare(first.updated),
  );
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
      {item.provenance === "estimated"
        ? "estimada"
        : item.provenance === "official"
          ? "oficial"
          : "observada"}
    </span>
  );
}

function MapMiniList({
  id,
  title,
  items,
  selectedId,
  emptyLabel,
  onSelect,
  headerControl,
  groupByDay = false,
  showArea = false,
}: {
  id: string;
  title: string;
  items: CivilItem[];
  selectedId: string | null;
  emptyLabel: string;
  onSelect: (item: CivilItem) => void;
  headerControl?: ReactNode;
  groupByDay?: boolean;
  showArea?: boolean;
}) {
  const itemDay = (item: CivilItem) => {
    const value = item.observed_at ?? item.updated_at;
    if (!value) return "Sense data";
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? "Sense data"
      : date.toLocaleDateString("ca-ES", { day: "2-digit", month: "short", year: "numeric" });
  };

  return (
    <section
      id={id}
      className="pointer-events-auto grid min-h-0 grid-rows-[auto_minmax(0,1fr)] overflow-hidden rounded-md border border-[#aeb9b1] bg-white/95 shadow-lg backdrop-blur-sm"
    >
      <div className="flex items-center justify-between gap-2 border-b border-[#d7ddd8] px-3 py-2">
        <h2 className="text-sm font-bold">{title}</h2>
        <div className="flex items-center gap-2">
          {headerControl}
          <span className="text-xs font-semibold text-[#53605a]">{items.length}</span>
        </div>
      </div>
      <div className="min-h-0 overflow-y-auto overscroll-contain">
        {items.length === 0 ? (
          <p className="px-3 py-3 text-xs text-[#53605a]">{emptyLabel}</p>
        ) : (
          items.map((item, index) => {
            const description = incidentDescription(item);
            const day = itemDay(item);
            const showDay = groupByDay && (index === 0 || itemDay(items[index - 1]) !== day);
            const isSocialNotice = isSocialOsintItem(item);
            return (
              <div key={item.id}>
                {showDay ? (
                  <div className="sticky top-0 z-10 border-b border-[#d7ddd8] bg-[#f3f6f4] px-3 py-1 text-[10px] font-bold uppercase text-[#53605a]">
                    {day}
                  </div>
                ) : null}
                <button
                  type="button"
                  aria-pressed={item.id === selectedId}
                  onClick={() => onSelect(item)}
                  className={[
                    "block w-full border-b border-l-4 border-b-[#edf0ed] px-3 py-2 text-left hover:bg-[#eef3ef] focus-visible:outline focus-visible:outline-2 focus-visible:outline-inset focus-visible:outline-[#1d5fd0]",
                    isSocialNotice
                      ? "border-l-[#2563eb] hover:bg-[#eff6ff]"
                      : item.data_type === "official_notice"
                        ? noticeLevelClasses(item)
                        : "border-l-transparent",
                    item.id === selectedId
                      ? isSocialNotice
                        ? "bg-[#dbeafe]"
                        : "bg-[#e4eee7]"
                      : "bg-transparent",
                  ].join(" ")}
                >
                  <span className="flex items-center gap-1.5">
                    {isSocialNotice ? (
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full border border-[#1d4ed8] bg-[#2563eb]" />
                    ) : item.data_type === "official_notice" ? (
                      <span
                        className={`h-2.5 w-2.5 shrink-0 rounded-full border ${noticeDotClasses(item)}`}
                      />
                    ) : null}
                    <span className="block min-w-0 flex-1 truncate text-xs font-bold">
                      {itemTitle(item)}
                    </span>
                    {showArea && Number(item.properties.area_hectares) > 0 ? (
                      <span className="shrink-0 text-[10px] font-semibold text-[#53605a]">
                        {Number(item.properties.area_hectares).toLocaleString("ca-ES")} ha
                      </span>
                    ) : null}
                  </span>
                  {description ? (
                    <span
                      className="mt-1 block line-clamp-4 text-[11px] leading-4 text-[#303b35]"
                      title={description}
                    >
                      {description}
                    </span>
                  ) : null}
                  {item.data_type === "incident" && item.properties.osint === true ? (
                    <span
                      className={`mt-1 block text-[10px] font-semibold uppercase ${isSocialNotice ? "text-[#1d4ed8]" : "text-[#53605a]"}`}
                    >
                      {osintEventLabel(String(item.properties.event_type ?? "incident"))}
                    </span>
                  ) : null}
                  <span className="mt-0.5 block truncate text-[11px] text-[#53605a]">
                    {itemSubtitle(item)}
                  </span>
                </button>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}

function durationLabel(value: unknown) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) return "No calculada";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours >= 24 ? `${Math.floor(hours / 24)} d ${hours % 24} h` : `${hours} h ${minutes} min`;
}

function osintEventLabel(event: string) {
  const labels: Record<string, string> = {
    firefighting_update: "Actualització d'extinció",
    confinement_order: "Ordre de confinament",
    confinement_expansion: "Ampliació del confinament",
    confinement_lift: "Fi del confinament",
    evacuation_order: "Ordre d'evacuació",
    evacuation_expansion: "Ampliació de l'evacuació",
    evacuation_lift: "Fi de l'evacuació",
    es_alert_announced: "ES-Alert anunciat",
    es_alert_sent: "ES-Alert enviat",
    es_alert_received: "ES-Alert rebut",
    es_alert_cancelled: "ES-Alert cancel·lat",
    emergency_activation: "Pla d'emergència activat",
    emergency_update: "Actualització de l'emergència",
    emergency_deactivation: "Pla d'emergència desactivat",
    risk_alert_update: "Actualització del risc",
  };
  return labels[event] ?? event.replaceAll("_", " ");
}

function OsintTimeline({ items }: { items: OsintTimelineItem[] }) {
  return (
    <div className="mt-4 border-t border-[#edf0ed] pt-4">
      <h3 className="text-sm font-bold">Publicacions relacionades i cronologia</h3>
      <div className="mt-2 max-h-64 space-y-3 overflow-y-auto pr-1">
        {items.length === 0 ? (
          <p className="text-xs text-[#53605a]">Sense publicacions OSINT associades.</p>
        ) : null}
        {items.map((event) => (
          <article
            key={event.id}
            className={`border-l-2 pl-3 text-xs ${isXOrNitterSource(event.source_name, event.url) ? "border-[#2563eb] bg-[#eff6ff]/60 py-2 pr-2" : "border-[#75817b]"}`}
          >
            <div className="flex justify-between gap-3">
              <strong>{osintEventLabel(event.event_type)}</strong>
              <time className="shrink-0 text-[#53605a]">
                {new Date(event.published_at).toLocaleString("ca-ES")}
              </time>
            </div>
            <p className="mt-1 font-semibold">{event.authority}</p>
            <p className="mt-0.5 text-[#53605a]">
              {event.source_name ?? event.source_type} · {confidenceLabel(event.confidence)}
            </p>
            <p className="mt-1 whitespace-pre-wrap text-[#39443f]">{event.original_text}</p>
            <a
              className="mt-1 inline-block font-semibold text-[#1d5fd0]"
              href={event.url}
              target="_blank"
              rel="noreferrer"
            >
              Font original
            </a>
          </article>
        ))}
      </div>
    </div>
  );
}

function effisAttributes(item: CivilItem) {
  const raw = item.properties.effis_attributes_json;
  if (typeof raw !== "string" || !raw) return [];
  try {
    return Object.entries(JSON.parse(raw) as Record<string, unknown>).filter(
      ([, value]) => value !== null && value !== undefined && value !== "",
    );
  } catch {
    return [];
  }
}

function DetailPanel({
  item,
  osintTimeline = [],
}: {
  item: CivilItem | null;
  osintTimeline?: OsintTimelineItem[];
}) {
  if (!item) {
    return (
      <section className="rounded-md border border-[#d7ddd8] bg-white p-4">
        <h2 className="text-base font-bold">Detall d'incident</h2>
        <p className="mt-2 text-sm text-[#53605a]">
          Selecciona un element de la llista o del mapa.
        </p>
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
          <dd>
            {item.observed_at ? new Date(item.observed_at).toLocaleString("ca-ES") : "No informat"}
          </dd>
        </div>
        <div>
          <dt className="font-semibold">Actualitzat</dt>
          <dd>
            {item.updated_at ? new Date(item.updated_at).toLocaleString("ca-ES") : "No informat"}
          </dd>
        </div>
      </dl>
      {item.source.url ? (
        <a
          className="mt-4 inline-block text-sm font-semibold text-[#1d5fd0]"
          href={item.source.url}
        >
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
      {item.data_type === "fire_perimeter" ? (
        <dl className="mt-4 grid gap-3 border-t border-[#edf0ed] pt-4 text-sm">
          <div>
            <dt className="font-semibold">Superfície cremada</dt>
            <dd>
              {item.properties.area_hectares
                ? `${Number(item.properties.area_hectares).toLocaleString("ca-ES")} ha`
                : "No informada"}
            </dd>
          </div>
          <div>
            <dt className="font-semibold">Data del foc</dt>
            <dd>{dateTimeLabel(item.properties.fire_date)}</dd>
          </div>
          <div>
            <dt className="font-semibold">Tasques d'extinció</dt>
            <dd>
              {String(
                item.properties.extinction_operations_note ?? "No informades per aquesta font",
              )}
            </dd>
          </div>
        </dl>
      ) : null}
      {item.data_type === "es_alert_restriction" ? (
        <dl className="mt-4 grid gap-3 border-t border-[#edf0ed] pt-4 text-sm">
          <div>
            <dt className="font-semibold">Instruccions</dt>
            <dd>{String(item.properties.instruction ?? "No informades")}</dd>
          </div>
          <div>
            <dt className="font-semibold">Zona afectada</dt>
            <dd>{String(item.properties.area ?? "No informada")}</dd>
          </div>
          <div>
            <dt className="font-semibold">Vigent fins</dt>
            <dd>{dateTimeLabel(item.properties.expires_at)}</dd>
          </div>
        </dl>
      ) : null}
      {item.data_type === "incident" ? (
        <div className="mt-4 border-t border-[#edf0ed] pt-4 text-sm">
          <dl className="grid gap-3">
            <div>
              <dt className="font-semibold">Inici de l'incendi</dt>
              <dd>{dateTimeLabel(item.properties.fire_date ?? item.properties.started_at)}</dd>
            </div>
            <div>
              <dt className="font-semibold">Extinció</dt>
              <dd>{dateTimeLabel(item.properties.final_date ?? item.properties.ended_at)}</dd>
            </div>
            <div>
              <dt className="font-semibold">Superfície EFFIS</dt>
              <dd>
                {item.properties.area_hectares
                  ? `${Number(item.properties.area_hectares).toLocaleString("ca-ES")} ha`
                  : "No informada"}
              </dd>
            </div>
            <div>
              <dt className="font-semibold">Ubicació EFFIS</dt>
              <dd>
                {[item.properties.commune, item.properties.province, item.properties.country]
                  .filter(Boolean)
                  .join(", ") || "No informada"}
              </dd>
            </div>
            {item.properties.summary ? (
              <div>
                <dt className="font-semibold">Última informació</dt>
                <dd className="whitespace-pre-wrap">{String(item.properties.summary)}</dd>
              </div>
            ) : null}
            {Array.isArray(item.properties.hashtags) && item.properties.hashtags.length > 0 ? (
              <div>
                <dt className="font-semibold">Identificadors</dt>
                <dd>{item.properties.hashtags.join(", ")}</dd>
              </div>
            ) : null}
            <div>
              <dt className="font-semibold">Estat de l'incident</dt>
              <dd>{String(item.properties.status ?? "No informat")}</dd>
            </div>
            <div>
              <dt className="font-semibold">Risc</dt>
              <dd>{osintEventLabel(String(item.properties.risk_type ?? "No informat"))}</dd>
            </div>
            <div>
              <dt className="font-semibold">Zones afectades</dt>
              <dd>
                {Array.isArray(item.properties.affected_locations)
                  ? item.properties.affected_locations.join(", ")
                  : "No delimitades"}
              </dd>
            </div>
            <div>
              <dt className="font-semibold">Durada</dt>
              <dd>{durationLabel(item.properties.duration_seconds)}</dd>
            </div>
            <div>
              <dt className="font-semibold">Estat ES-Alert</dt>
              <dd>
                {osintEventLabel(String(item.properties.es_alert_status ?? "not_applicable"))}
              </dd>
            </div>
            <div>
              <dt className="font-semibold">Instruccions</dt>
              <dd>{String(item.properties.instructions ?? "No informades")}</dd>
            </div>
            {Number(item.properties.firms_detection_count ?? 0) > 0 ? (
              <div>
                <dt className="font-semibold">Activitat satel·litària vinculada</dt>
                <dd>
                  {Number(item.properties.firms_detection_count).toLocaleString("ca-ES")} deteccions
                  FIRMS
                  {item.properties.firms_total_frp_mw
                    ? ` · ${Number(item.properties.firms_total_frp_mw).toLocaleString("ca-ES")} MW FRP acumulats`
                    : ""}
                </dd>
              </div>
            ) : null}
            <div>
              <dt className="font-semibold">Primera detecció FIRMS vinculada</dt>
              <dd>{dateTimeLabel(item.properties.firms_oldest_detection_at)}</dd>
            </div>
            <div>
              <dt className="font-semibold">Última detecció FIRMS vinculada</dt>
              <dd>{dateTimeLabel(item.properties.firms_newest_detection_at)}</dd>
            </div>
            {item.properties.extinction_operations_note ? (
              <div>
                <dt className="font-semibold">Informació operativa d'extinció</dt>
                <dd>{String(item.properties.extinction_operations_note)}</dd>
              </div>
            ) : null}
            {item.properties.es_alert_message ? (
              <div>
                <dt className="font-semibold">Missatge ES-Alert literal</dt>
                <dd className="whitespace-pre-wrap">{String(item.properties.es_alert_message)}</dd>
              </div>
            ) : null}
          </dl>
          {effisAttributes(item).length > 0 ? (
            <details className="mt-4 border-t border-[#edf0ed] pt-4">
              <summary className="cursor-pointer text-sm font-bold">
                Tots els camps del shapefile EFFIS
              </summary>
              <dl className="mt-3 grid gap-x-6 gap-y-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
                {effisAttributes(item).map(([key, value]) => (
                  <div key={key} className="border-t border-[#edf0ed] pt-2">
                    <dt className="font-semibold">{key}</dt>
                    <dd className="break-words text-[#39443f]">{String(value)}</dd>
                  </div>
                ))}
              </dl>
            </details>
          ) : null}
          <div className="mt-4">
            <h3 className="text-sm font-bold">Fonts consultades</h3>
            <ul className="mt-2 space-y-1 text-xs">
              {osintTimeline.map((event) => (
                <li key={`source-${event.id}`}>
                  <a
                    className="font-semibold text-[#1d5fd0]"
                    href={event.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {event.authority}
                  </a>{" "}
                  · {confidenceLabel(event.confidence)} · {event.source_type}
                </li>
              ))}
            </ul>
          </div>
          <OsintTimeline items={osintTimeline} />
        </div>
      ) : null}
    </section>
  );
}

function Legend() {
  return (
    <div className="grid gap-2 p-3 text-sm">
      <span className="flex items-center gap-2">
        <span className="h-4 w-4 border border-[#7a1f17] bg-[#b42318] opacity-70" /> Àrea
        reconstruïda NASA FIRMS
      </span>
      <span className="flex items-center gap-2">
        <span className="h-4 w-4 rounded-full border-2 border-white bg-[#c81e1e] shadow" /> Pin grup
        FIRMS
      </span>
      <span className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-full bg-[#5f120e]" /> Punt calent FIRMS
      </span>
      <span className="flex items-center gap-2">
        <span className="h-3 w-8 border-t-4 border-[#b42318]" /> Perímetre EFFIS actual
      </span>
      <span className="flex items-center gap-2">
        <span className="h-4 w-6 border border-[#4f5653] bg-[#626966] opacity-40" /> Àrea cremada
        EFFIS
      </span>
      <span className="flex items-center gap-2">
        <span className="h-3 w-8 border-t-4 border-dashed border-[#8a2f16]" /> Perimetre estimat
      </span>
      <span className="flex items-center gap-2 opacity-60">
        <span className="h-3 w-8 border-t-4 border-[#3f454d]" /> Dada antiga
      </span>
      <span className="flex items-center gap-2">
        <span className="h-3 w-8 border-t-4 border-[#c77700]" /> Incendi d'aquest any
      </span>
      <span className="flex items-center gap-2">
        <span className="h-3 w-8 border-t-4 border-[#66736c]" /> Històric d'incendis
      </span>
      <span className="flex items-center gap-2">
        <span className="h-3 w-8 border-t-4 border-[#ff7a00]" /> Carretera: incendi o obstacle
        ambiental
      </span>
      <span className="flex items-center gap-2">
        <span className="h-3 w-8 border-t-4 border-[#a855f7]" /> Carretera: altres afectacions
      </span>
      <span className="flex items-center gap-2">
        <span className="h-4 w-6 border border-[#991b1b] bg-[#dc2626] opacity-30" /> Restricció
        ES-Alert activa
      </span>
      <span className="flex items-center gap-2">
        <span className="h-4 w-6 border border-[#1d4ed8] bg-[#2563eb] opacity-35" /> Avís OSINT de X
        / Nitter
      </span>
    </div>
  );
}

export function CivilPortal() {
  const searchParams = useSearchParams();
  const viewport = useMapViewportStore();
  const lastUrlRef = useRef("");
  const incidentDetailsRef = useRef<HTMLElement | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(searchParams.get("selected"));
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(
    searchParams.get("selected"),
  );
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
    aircraft: true,
  });
  const [showFirmHotspots, setShowFirmHotspots] = useState(false);
  const [showNotices, setShowNotices] = useState(true);
  const [showLegend, setShowLegend] = useState(true);
  const [incidentOrder, setIncidentOrder] = useState<"day" | "area">("day");
  const [perimeterPeriods, setPerimeterPeriods] = useState<PerimeterPeriodVisibility>({
    current: true,
    year: false,
    historic: false,
  });
  const [selectedFirmDay, setSelectedFirmDay] = useState<string | null>(null);
  const [isTimelinePlaying, setIsTimelinePlaying] = useState(false);
  const [focusTarget, setFocusTarget] = useState<{
    geometry?: CivilFeature["geometry"];
    bbox?: string;
    key: number;
  } | null>(null);
  const incidentObservedFrom = useMemo(() => new Date(Date.now() - WEEK_MS).toISOString(), []);
  const selectedPerimeterPeriods = (Object.keys(perimeterPeriods) as PerimeterPeriod[]).filter(
    (period) => perimeterPeriods[period],
  );

  const firmsTimelineQuery = useQuery({
    queryKey: ["firms-timeline", filters.bbox, filters.minConfidence],
    queryFn: () => getFirmsTimeline(filters),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
  const firmsTimeline = firmsTimelineQuery.data?.items ?? [];
  const firmsTimelineByDay = useMemo(() => {
    const grouped = new Map<string, typeof firmsTimeline>();
    firmsTimeline.forEach((item) => {
      const day = firmsDayKey(item.observed_at);
      grouped.set(day, [...(grouped.get(day) ?? []), item]);
    });
    return grouped;
  }, [firmsTimeline]);
  const firmsTimelineDays = useMemo(() => [...firmsTimelineByDay.keys()], [firmsTimelineByDay]);
  const selectedFirmDayIndex = selectedFirmDay ? firmsTimelineDays.indexOf(selectedFirmDay) : -1;
  const selectedFirmDayMoments = selectedFirmDay
    ? (firmsTimelineByDay.get(selectedFirmDay) ?? [])
    : [];
  const selectedFirmDayCount = selectedFirmDayMoments.reduce((sum, item) => sum + item.count, 0);
  const selectedFirmWindow = useMemo(() => {
    if (!selectedFirmDay) {
      return undefined;
    }
    const moments = firmsTimelineByDay.get(selectedFirmDay) ?? [];
    const first = new Date(moments[0]?.observed_at ?? "");
    const last = new Date(moments[moments.length - 1]?.observed_at ?? "");
    if (!Number.isFinite(first.getTime()) || !Number.isFinite(last.getTime())) {
      return undefined;
    }
    return {
      observedFrom: first.toISOString(),
      observedTo: new Date(last.getTime() + 59_999).toISOString(),
    };
  }, [firmsTimelineByDay, selectedFirmDay]);

  useEffect(() => {
    if (firmsTimelineDays.length === 0) {
      setSelectedFirmDay(null);
      setIsTimelinePlaying(false);
      return;
    }
    const activeDay =
      selectedFirmDay && firmsTimelineByDay.has(selectedFirmDay)
        ? selectedFirmDay
        : firmsTimelineDays[firmsTimelineDays.length - 1];
    if (activeDay !== selectedFirmDay) {
      setSelectedFirmDay(activeDay);
    }
  }, [firmsTimelineByDay, firmsTimelineDays, selectedFirmDay]);

  useEffect(() => {
    if (!isTimelinePlaying || selectedFirmDayIndex < 0) {
      return;
    }
    if (selectedFirmDayIndex >= firmsTimelineDays.length - 1) {
      setIsTimelinePlaying(false);
      return;
    }
    const timeout = window.setTimeout(() => {
      setSelectedFirmDay(firmsTimelineDays[selectedFirmDayIndex + 1]);
    }, 1_200);
    return () => window.clearTimeout(timeout);
  }, [firmsTimelineDays, isTimelinePlaying, selectedFirmDayIndex]);

  const layerQueries = useQueries({
    queries: layerNames.map((layer) => ({
      queryKey: [
        "civil-layer",
        layer,
        filters,
        layer === "detections" ? selectedFirmWindow : null,
        layer === "perimeters" ? selectedPerimeterPeriods.join(",") : null,
      ],
      queryFn: () =>
        getCivilLayer(
          layer,
          filters,
          layer === "detections" ? selectedFirmWindow : undefined,
          layer === "perimeters" ? selectedPerimeterPeriods : undefined,
        ),
      enabled:
        layer !== "roads" &&
        (layer !== "detections" || Boolean(selectedFirmWindow)) &&
        (layer !== "perimeters" || selectedPerimeterPeriods.length > 0),
      staleTime: layer === "aircraft" ? 15 * 1000 : 5 * 60 * 1000,
      refetchInterval: () => (layer === "aircraft" && visibleLayers.aircraft ? 20 * 1000 : false),
      refetchOnWindowFocus: false,
    })),
  });

  const incidentsQuery = useQuery({
    queryKey: ["civil-incidents", filters.bbox, incidentObservedFrom],
    queryFn: () => getCivilFeatureCollection("/civil/incidents", filters, incidentObservedFrom, 50),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
  const institutionalXQuery = useQuery({
    queryKey: ["institutional-x-accounts"],
    queryFn: getInstitutionalXAccounts,
    staleTime: 24 * 60 * 60 * 1000,
  });
  const noticesQuery = useQuery({
    queryKey: ["civil-notices"],
    queryFn: getCivilNotices,
    enabled: showNotices,
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
  const displayedLayers = useMemo(
    () => ({
      ...layers,
      perimeters: visiblePerimeters(layers.perimeters, perimeterPeriods),
    }),
    [layers, perimeterPeriods],
  );
  const layerItems = useMemo(
    () => flattenLayerItems(displayedLayers, visibleLayers),
    [displayedLayers, visibleLayers],
  );
  const incidentFeatures = incidentsQuery.data?.features ?? [];
  const mapLayers = useMemo(
    () => ({
      ...displayedLayers,
      risk: {
        ...displayedLayers.risk,
        features: [
          ...displayedLayers.risk.features,
          ...incidentFeatures
            .filter(
              (feature) =>
                feature.properties.properties.osint === true &&
                feature.properties.properties.canonical_fire !== true &&
                feature.geometry,
            )
            .map((feature) => ({
              ...feature,
              properties: {
                ...feature.properties,
                properties: {
                  ...feature.properties.properties,
                  category: isSocialOsintItem(feature.properties) ? "social" : "high",
                },
              },
            })),
        ],
      },
    }),
    [displayedLayers, incidentFeatures],
  );
  const incidents = useMemo(
    () =>
      incidentFeatures.map((feature) => ({ ...feature.properties, geometry: feature.geometry })),
    [incidentFeatures],
  );
  const orderedIncidents = useMemo(
    () =>
      [...incidents].sort((first, second) => {
        if (incidentOrder === "area") {
          const areaDifference =
            Number(second.properties.area_hectares ?? 0) -
            Number(first.properties.area_hectares ?? 0);
          if (areaDifference !== 0) return areaDifference;
        }
        return String(second.observed_at ?? "").localeCompare(String(first.observed_at ?? ""));
      }),
    [incidentOrder, incidents],
  );
  const notices = useMemo(() => {
    if (!showNotices) {
      return emptyCollection.items;
    }
    const now = Date.now();
    return (noticesQuery.data?.items ?? emptyCollection.items).filter((item) => {
      const expires = item.properties.expires;
      if (typeof expires !== "string") {
        return true;
      }
      const expiresAt = new Date(expires).getTime();
      return !Number.isFinite(expiresAt) || expiresAt >= now;
    });
  }, [noticesQuery.data?.items, showNotices]);
  const allItems = useMemo(
    () => [...incidents, ...notices, ...layerItems],
    [incidents, layerItems, notices],
  );
  const selectedLayerItem = allItems.find((item) => item.id === selectedId) ?? null;
  const incidentDetailQuery = useQuery({
    queryKey: ["civil-incident-detail", selectedIncidentId],
    queryFn: () => getCivilIncident(selectedIncidentId ?? ""),
    enabled: Boolean(selectedIncidentId),
    staleTime: 60 * 1000,
  });
  const selectedItem = incidentDetailQuery.data ?? selectedLayerItem;
  const osintDetailQuery = useQuery({
    queryKey: ["osint-incident-detail", selectedIncidentId],
    queryFn: () => getOsintIncidentDetail(selectedIncidentId ?? ""),
    enabled: Boolean(selectedIncidentId),
    staleTime: 60 * 1000,
  });
  const aircraftLayerIndex = layerNames.indexOf("aircraft");
  const aircraftRefreshing =
    aircraftLayerIndex >= 0 && visibleLayers.aircraft && Boolean(layerQueries[aircraftLayerIndex]?.isFetching);
  const loading =
    firmsTimelineQuery.isFetching ||
    layerQueries.some((query, index) => index !== aircraftLayerIndex && query.isFetching) ||
    incidentsQuery.isFetching ||
    (showNotices && noticesQuery.isFetching);
  const error =
    firmsTimelineQuery.isError ||
    layerQueries.some((query) => query.isError) ||
    incidentsQuery.isError ||
    (showNotices && noticesQuery.isError);

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

  const selectMapItem = (item: CivilItem) => {
    const linkedIncidentId = item.properties.incident_id;
    const resolvedIncidentId =
      item.data_type === "incident"
        ? item.id
        : typeof linkedIncidentId === "string"
          ? linkedIncidentId
          : null;
    const linkedIncident =
      typeof linkedIncidentId === "string"
        ? incidents.find((incident) => incident.id === linkedIncidentId)
        : undefined;
    setSelectedId(resolvedIncidentId ?? item.id);
    setSelectedIncidentId(resolvedIncidentId);
    const geometry = item.geometry ?? linkedIncident?.geometry;
    if (geometry) {
      setFocusTarget({ geometry, key: Date.now() });
      return;
    }
    const noticeBbox = item.properties.area_bbox;
    if (typeof noticeBbox === "string" && noticeBbox.split(",").length === 4) {
      setFocusTarget({ bbox: noticeBbox, key: Date.now() });
      return;
    }
  };

  const selectMapFeature = (featureId: string) => {
    const item = allItems.find((candidate) => candidate.id === featureId);
    if (item) {
      selectMapItem(item);
      return;
    }
    setSelectedId(featureId);
    setSelectedIncidentId(null);
  };

  const showIncidentDetails = (incidentId: string) => {
    setSelectedId(incidentId);
    setSelectedIncidentId(incidentId);
    window.requestAnimationFrame(() => {
      incidentDetailsRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    });
  };

  return (
    <main className="min-h-screen">
      <header className="border-b border-[#d7ddd8] bg-white px-4 py-4 md:px-6">
        <p className="text-sm font-semibold uppercase text-canopy">Portal Civil</p>
        <h1 className="mt-1 text-2xl font-bold">Incendis i avisos publics</h1>
        <nav aria-label="Seccions Civil" className="mt-4 flex gap-2 overflow-x-auto text-sm">
          {[
            "mapa",
            "incidents",
            "alertes-es-alert",
            "carreteres",
            "metodologia",
            "fonts",
            "estat",
          ].map((section) => (
            <a
              key={section}
              className="rounded border border-[#d7ddd8] bg-white px-3 py-2"
              href={`#${section}`}
            >
              {section}
            </a>
          ))}
        </nav>
      </header>

      <section className="grid gap-4 p-4">
        <section className="grid gap-4">
          <section id="mapa" className="grid gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-bold">Mapa</h2>
              <p className="text-sm text-[#53605a]">
                {aircraftRefreshing
                  ? "Refrescant Aeronaus"
                  : loading
                    ? "Carregant dades..."
                    : `${allItems.length} elements publics`}
              </p>
            </div>
            {error ? (
              <div className="rounded-md border border-[#b42318] bg-white p-4 text-sm">
                No es poden carregar algunes capes ara mateix.
              </div>
            ) : null}
            <div className="grid gap-3 border-y border-[#d7ddd8] bg-white px-3 py-3 md:grid-cols-[minmax(220px,auto)_minmax(220px,1fr)_auto] md:items-center">
              <div className="min-w-[220px]">
                <p className="text-xs font-semibold uppercase text-[#53605a]">Dia FIRMS</p>
                <p className="text-sm font-bold">
                  {selectedFirmDay ? firmsDayLabel(selectedFirmDay) : "Sense dades FIRMS"}
                </p>
                {selectedFirmDayIndex >= 0 ? (
                  <p className="text-xs text-[#53605a]">
                    {selectedFirmDayCount} deteccions durant tot el dia
                  </p>
                ) : null}
              </div>
              <input
                type="range"
                min={0}
                max={Math.max(0, firmsTimelineDays.length - 1)}
                value={Math.max(0, selectedFirmDayIndex)}
                disabled={firmsTimelineDays.length === 0}
                onChange={(event) => {
                  setIsTimelinePlaying(false);
                  setSelectedFirmDay(firmsTimelineDays[Number(event.target.value)] ?? null);
                }}
                className="h-8 w-full accent-[#d92d20] disabled:opacity-40"
                aria-label="Cronologia diària de deteccions FIRMS"
              />
              <div className="grid grid-cols-3 gap-1">
                <button
                  type="button"
                  disabled={selectedFirmDayIndex <= 0}
                  onClick={() => {
                    setIsTimelinePlaying(false);
                    setSelectedFirmDay(firmsTimelineDays[selectedFirmDayIndex - 1] ?? null);
                  }}
                  className="rounded border border-[#aeb9b1] px-2 py-1.5 text-xs font-semibold disabled:opacity-40"
                >
                  Anterior
                </button>
                <button
                  type="button"
                  disabled={firmsTimelineDays.length < 2}
                  onClick={() => {
                    if (
                      !isTimelinePlaying &&
                      selectedFirmDayIndex >= firmsTimelineDays.length - 1
                    ) {
                      setSelectedFirmDay(firmsTimelineDays[0] ?? null);
                    }
                    setIsTimelinePlaying((current) => !current);
                  }}
                  className="rounded bg-[#1f6f50] px-2 py-1.5 text-xs font-bold text-white disabled:opacity-40"
                >
                  {isTimelinePlaying ? "Pausa" : "Reprodueix"}
                </button>
                <button
                  type="button"
                  disabled={
                    selectedFirmDayIndex < 0 || selectedFirmDayIndex >= firmsTimelineDays.length - 1
                  }
                  onClick={() => {
                    setIsTimelinePlaying(false);
                    setSelectedFirmDay(firmsTimelineDays[selectedFirmDayIndex + 1] ?? null);
                  }}
                  className="rounded border border-[#aeb9b1] px-2 py-1.5 text-xs font-semibold disabled:opacity-40"
                >
                  Seguent
                </button>
              </div>
            </div>
            <div className="min-h-[620px] h-[72vh] max-h-[860px]">
              <MapShell
                portal="civil"
                civilLayers={mapLayers}
                visibleLayers={visibleLayers}
                bbox={mapFocusBbox}
                showFirmHotspots={showFirmHotspots}
                isLoading={loading}
                focusTarget={focusTarget}
                mapOverlay={
                  <div className="pointer-events-none absolute inset-0 z-20">
                    <form
                      className="pointer-events-auto absolute left-3 right-3 top-3 z-30 rounded-md border border-[#aeb9b1] bg-white/95 p-2 shadow-lg backdrop-blur-sm sm:right-auto sm:w-[360px]"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void applyMunicipality();
                      }}
                    >
                      <div className="flex gap-2">
                        <label className="sr-only" htmlFor="map-municipality">
                          Municipi
                        </label>
                        <input
                          id="map-municipality"
                          value={municipality}
                          onChange={(event) => setMunicipality(event.target.value)}
                          className="min-w-0 flex-1 rounded border border-[#aeb9b1] bg-white px-2 py-1.5 text-sm"
                          placeholder="Cerca un municipi"
                        />
                        <button
                          type="submit"
                          className="rounded bg-[#1f6f50] px-3 py-1.5 text-sm font-bold text-white"
                        >
                          Cerca
                        </button>
                      </div>
                      {municipalityStatus ? (
                        <p className="mt-1 truncate text-xs text-[#1f6f50]">{municipalityStatus}</p>
                      ) : null}
                      {municipalityError ? (
                        <p className="mt-1 truncate text-xs font-semibold text-[#b42318]">
                          {municipalityError}
                        </p>
                      ) : null}
                    </form>

                    <div
                      className={`pointer-events-auto absolute right-14 z-40 flex items-start gap-2 md:top-3 ${municipalityStatus || municipalityError ? "top-[6.75rem]" : "top-[4.75rem]"}`}
                    >
                      <details className="relative">
                        <summary className="list-none cursor-pointer rounded-md border border-[#aeb9b1] bg-white/95 px-3 py-2 text-sm font-bold shadow-lg backdrop-blur-sm [&::-webkit-details-marker]:hidden">
                          Capes
                        </summary>
                        <div className="absolute right-0 mt-2 max-h-[480px] w-[min(330px,calc(100vw-24px))] overflow-y-auto rounded-md border border-[#aeb9b1] bg-white p-3 shadow-xl">
                          <div className="grid grid-cols-2 gap-1.5">
                            <label className="col-span-2 flex items-center gap-2 rounded border border-[#d7ddd8] px-2 py-1.5 text-xs font-semibold">
                              <input
                                type="checkbox"
                                checked={filters.onlyCurrent}
                                onChange={(event) =>
                                  setFilters((current) => ({
                                    ...current,
                                    onlyCurrent: event.target.checked,
                                  }))
                                }
                              />
                              Nomes dades vigents
                            </label>
                            {layerNames
                              .filter((layer) => layer !== "roads" && layer !== "perimeters")
                              .map((layer) => (
                                <label
                                  key={layer}
                                  className="flex items-center gap-2 rounded border border-[#d7ddd8] px-2 py-1.5 text-xs"
                                >
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
                            {(
                              [
                                ["current", "Incendis actuals"],
                                ["year", "Incendis d'aquest any"],
                                ["historic", "Històric d'incendis"],
                              ] as Array<[PerimeterPeriod, string]>
                            ).map(([period, label]) => (
                              <label
                                key={period}
                                className="flex items-center gap-2 rounded border border-[#d7ddd8] px-2 py-1.5 text-xs"
                              >
                                <input
                                  type="checkbox"
                                  checked={perimeterPeriods[period]}
                                  onChange={(event) => {
                                    const checked = event.target.checked;
                                    setPerimeterPeriods((current) => ({
                                      ...current,
                                      [period]: checked,
                                    }));
                                    setVisibleLayers((current) => ({
                                      ...current,
                                      perimeters: true,
                                    }));
                                  }}
                                />
                                {label}
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
                            <label className="flex items-center gap-2 rounded border border-[#d7ddd8] px-2 py-1.5 text-xs">
                              <input
                                type="checkbox"
                                checked={showNotices}
                                onChange={(event) => setShowNotices(event.target.checked)}
                              />
                              Avisos i cronologia
                            </label>
                          </div>
                        </div>
                      </details>
                    </div>

                    <div className="pointer-events-auto absolute bottom-8 right-3 z-40">
                      {showLegend ? (
                        <section className="max-h-[min(480px,calc(100vh-140px))] w-[min(330px,calc(100vw-24px))] overflow-y-auto rounded-md border border-[#aeb9b1] bg-white/95 shadow-xl backdrop-blur-sm">
                          <header className="sticky top-0 flex items-center justify-between border-b border-[#d7ddd8] bg-white px-3 py-2">
                            <h3 className="text-sm font-bold">Llegenda</h3>
                            <button
                              type="button"
                              aria-label="Tanca la llegenda"
                              title="Tanca la llegenda"
                              onClick={() => setShowLegend(false)}
                              className="grid h-7 w-7 place-items-center rounded border border-[#c7d0ca] bg-white text-base font-bold leading-none text-[#303b35] hover:bg-[#eef3ef] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#1d5fd0]"
                            >
                              X
                            </button>
                          </header>
                          <Legend />
                        </section>
                      ) : (
                        <button
                          type="button"
                          aria-label="Obre la llegenda"
                          onClick={() => setShowLegend(true)}
                          className="rounded-md border border-[#aeb9b1] bg-white/95 px-3 py-2 text-sm font-bold shadow-lg backdrop-blur-sm hover:bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#1d5fd0]"
                        >
                          Llegenda
                        </button>
                      )}
                    </div>

                    <div
                      className={`absolute bottom-3 left-3 z-20 grid w-[min(290px,calc(100%-24px))] gap-2 sm:w-[290px] md:top-[4.75rem] ${municipalityStatus || municipalityError ? "top-[10rem]" : "top-[8rem]"} ${showNotices ? "grid-rows-2" : "grid-rows-1"}`}
                    >
                      <MapMiniList
                        id="incidents"
                        title="Incidents"
                        items={orderedIncidents}
                        selectedId={selectedId}
                        emptyLabel="Sense incidents actuals."
                        onSelect={selectMapItem}
                        groupByDay={incidentOrder === "day"}
                        showArea
                        headerControl={
                          <select
                            aria-label="Ordena incidents"
                            value={incidentOrder}
                            onChange={(event) =>
                              setIncidentOrder(event.target.value as "day" | "area")
                            }
                            className="max-w-[92px] rounded border border-[#c7d0ca] bg-white px-1 py-0.5 text-[10px] font-semibold"
                          >
                            <option value="day">Per dia</option>
                            <option value="area">Per hectàrees</option>
                          </select>
                        }
                      />
                      {showNotices ? (
                        <MapMiniList
                          id="avisos"
                          title="Avisos i cronologia"
                          items={notices}
                          selectedId={selectedId}
                          emptyLabel="Sense avisos públics."
                          onSelect={selectMapItem}
                        />
                      ) : null}
                    </div>
                  </div>
                }
                onFeatureSelect={selectMapFeature}
                onFeatureDetails={showIncidentDetails}
              />
            </div>
            <section ref={incidentDetailsRef} id="detall-incident" className="scroll-mt-4">
              <DetailPanel item={selectedItem} osintTimeline={osintDetailQuery.data?.timeline} />
            </section>
          </section>

          <section className="grid gap-4 xl:grid-cols-3">
            <section
              id="alertes-es-alert"
              className="rounded-md border border-[#d7ddd8] bg-white p-4 xl:col-span-2"
            >
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-base font-bold">Alertes ES-Alert</h2>
                <span className="text-sm font-semibold text-[#53605a]">
                  {visibleLayers.evacuations ? layers.evacuations.features.length : 0} actives
                </span>
              </div>
              {!visibleLayers.evacuations || layers.evacuations.features.length === 0 ? (
                <p className="mt-2 text-sm text-[#53605a]">Cap restricció ES-Alert activa.</p>
              ) : (
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {layers.evacuations.features.map((feature) => (
                    <button
                      key={feature.id ?? feature.properties.id}
                      type="button"
                      className="border-t border-[#edf0ed] py-2 text-left"
                      onClick={() =>
                        selectMapItem({ ...feature.properties, geometry: feature.geometry })
                      }
                    >
                      <span className="block text-sm font-bold">
                        {itemTitle(feature.properties)}
                      </span>
                      <span className="mt-1 block text-xs text-[#53605a]">
                        {String(feature.properties.properties.area ?? "Zona no informada")}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </section>
            <section id="restriccions" className="rounded-md border border-[#d7ddd8] bg-white p-4">
              <h2 className="text-base font-bold">Restriccions a Carreteres</h2>
              <p className="mt-2 text-sm text-[#53605a]">
                {visibleLayers.restrictions ? layers.restrictions.features.length : 0} elements
              </p>
            </section>
          </section>

          <section id="metodologia" className="rounded-md border border-[#d7ddd8] bg-white p-4">
            <h2 className="text-base font-bold">Metodologia</h2>
            <p className="mt-2 text-sm text-[#53605a]">
              Les dades oficials, observades i estimades es mostren separades. Les estimacions
              antigues perden vigencia visual i porten advertiment.
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
                      <span
                        className={
                          source.warning ? "font-semibold text-[#8a2f16]" : "text-[#53605a]"
                        }
                      >
                        {source.count} elements
                      </span>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-[#53605a]">{source.description}</p>
                  </div>
                ))
              )}
            </div>
            <div className="mt-5 border-t border-[#d7ddd8] pt-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-bold">Perfils institucionals via Nitter</h3>
                <a
                  className="text-xs font-semibold text-[#1d5fd0]"
                  href="https://twitterviewer.net/twitter-profile-viewer"
                  target="_blank"
                  rel="noreferrer"
                >
                  Revisio alternativa
                </a>
              </div>
              <p className="mt-1 text-xs text-[#53605a]">
                Nitter es la passarel·la automatica principal. TwitterViewer queda per revisio
                manual.
              </p>
              <div className="mt-3 max-h-64 overflow-y-auto border-y border-[#edf0ed]">
                {(institutionalXQuery.data?.items ?? []).map((account) => (
                  <div
                    key={account.handle}
                    className="flex items-center justify-between gap-3 border-t border-[#edf0ed] py-2 first:border-t-0"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{account.name}</p>
                      <p className="truncate text-xs text-[#53605a]">
                        @{account.handle} · {account.region}
                      </p>
                    </div>
                    <a
                      className="shrink-0 text-xs font-semibold text-[#1d5fd0]"
                      href={account.nitter_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Nitter
                    </a>
                  </div>
                ))}
              </div>
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
