import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CivilPortal } from "./civil-portal";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/map-shell", () => ({
  MapShell: ({
    mapOverlay,
    focusTarget,
    onFeatureDetails,
    onFeatureSelect,
  }: {
    mapOverlay?: ReactNode;
    focusTarget?: { geometry?: { type?: string }; bbox?: string };
    onFeatureDetails?: (featureId: string) => void;
    onFeatureSelect?: (featureId: string) => void;
  }) => (
    <div aria-label="Mapa civil">
      mapa civil
      <span data-testid="map-focus">
        {focusTarget?.geometry ? "geometry" : (focusTarget?.bbox ?? "none")}
      </span>
      <span data-testid="map-focus-geometry">{focusTarget?.geometry?.type ?? "none"}</span>
      <button type="button" onClick={() => onFeatureDetails?.("incident-1")}>
        Veure tota la informació
      </button>
      <button type="button" onClick={() => onFeatureSelect?.("restriction-1")}>
        Selecciona restricció del mapa
      </button>
      {mapOverlay}
    </div>
  ),
}));

vi.mock("@/lib/api/civil", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/civil")>();
  return {
    ...actual,
    getCivilFeatureCollection: async () => ({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          id: "incident-1",
          geometry: { type: "Point", coordinates: [2.1, 41.4] },
          properties: {
            id: "incident-1",
            data_type: "incident",
            source: {
              name: "X @bomberscat via Nitter",
              authority: "Generalitat de Catalunya",
              url: "https://nitter.net/bomberscat/status/1",
              attribution: null,
            },
            observed_at: "2026-07-27T12:00:00Z",
            updated_at: "2026-07-27T12:00:00Z",
            age_seconds: 0,
            confidence: 0.85,
            confidence_category: null,
            provenance: "official",
            is_current: true,
            warnings: [],
            properties: {
              title: "Incendi prova",
              status: "reported",
              osint: true,
              event_type: "firefighting_update",
              area_hectares: 128.4,
              summary: "S'han mobilitzat 12 dotacions de Bombers per consolidar el perímetre.",
            },
          },
        },
      ],
    }),
    getCivilLayer: async (layer: string) => ({
      type: "FeatureCollection",
      features:
        layer === "restrictions"
          ? [
              {
                type: "Feature",
                id: "restriction-1",
                geometry: {
                  type: "LineString",
                  coordinates: [
                    [2.02, 41.4],
                    [2.08, 41.43],
                  ],
                },
                properties: {
                  id: "restriction-1",
                  data_type: "restriction_zone",
                  source: {
                    name: "DGT",
                    authority: "Dirección General de Tráfico",
                    url: null,
                    attribution: null,
                  },
                  observed_at: "2026-07-27T12:00:00Z",
                  updated_at: "2026-07-27T12:00:00Z",
                  age_seconds: 0,
                  confidence: 0.95,
                  confidence_category: null,
                  provenance: "official",
                  is_current: true,
                  warnings: [],
                  properties: {
                    title: "C-25 tallada per incendi",
                    cause: "incendi",
                  },
                },
              },
            ]
          : [],
    }),
    getCivilIncident: async () => ({
      id: "incident-1",
      data_type: "incident",
      source: {
        name: "EFFIS",
        authority: "Copernicus",
        url: "https://effis.jrc.ec.europa.eu",
        attribution: null,
      },
      observed_at: "2026-07-27T12:00:00Z",
      updated_at: "2026-07-27T13:00:00Z",
      age_seconds: 0,
      confidence: 0.85,
      confidence_category: null,
      provenance: "official",
      is_current: true,
      warnings: [],
      properties: {
        title: "Incendi prova",
        status: "active",
        osint: true,
        summary: "S'han mobilitzat 12 dotacions de Bombers per consolidar el perímetre.",
        fire_date: "2026-07-27T10:00:00Z",
        final_date: null,
        area_hectares: 128.4,
        commune: "Municipi prova",
        province: "Barcelona",
        hashtags: ["#IFProva"],
        firms_detection_count: 40,
        firms_oldest_detection_at: "2026-07-27T10:30:00Z",
        firms_newest_detection_at: "2026-07-27T13:00:00Z",
        firms_total_frp_mw: 55.2,
        effis_attributes_json: '{"AREA_HA":128.4,"CLASS":"Forest"}',
      },
    }),
    getFirmsTimeline: async () => ({
      data_type: "firms_timeline",
      items: [
        { observed_at: "2026-07-26T12:00:00Z", count: 20 },
        { observed_at: "2026-07-27T12:00:00Z", count: 35 },
        { observed_at: "2026-07-27T13:00:00Z", count: 5 },
      ],
      warnings: [],
    }),
    getCivilNotices: async () => ({
      data_type: "civil_collection",
      items: [
        {
          id: "notice-1",
          data_type: "official_notice",
          source: {
            name: "Proteccio Civil active plans",
            authority: "Generalitat de Catalunya",
            url: null,
            attribution: null,
          },
          observed_at: "2026-07-27T12:00:00Z",
          updated_at: "2026-07-27T12:00:00Z",
          age_seconds: 0,
          confidence: 0.95,
          confidence_category: null,
          provenance: "official",
          is_current: true,
          warnings: [],
          properties: {
            title: "INFOCAT ALERTA",
            incident_id: null,
            alert_level: "orange",
            area_bbox: "0.15,40.5,3.35,42.9",
          },
        },
      ],
      pagination: { limit: 50, offset: 0, count: 1 },
      warnings: [],
    }),
    getOsintIncidentDetail: async () => ({
      id: "incident-1",
      title: "Incendi prova",
      summary: "S'han mobilitzat 12 dotacions de Bombers per consolidar el perímetre.",
      status: "reported",
      confidence: 0.85,
      duration_seconds: null,
      properties: {},
      timeline: [
        {
          id: "post-1",
          event_type: "firefighting_update",
          risk_type: "wildfire",
          action_state: "active",
          es_alert_status: "not_applicable",
          title: "Actualització Bombers",
          authority: "Bombers de la Generalitat",
          published_at: "2026-07-27T12:30:00Z",
          starts_at: null,
          ends_at: null,
          instructions: null,
          es_alert_message: null,
          locations: [],
          original_text: "12 dotacions treballen en l'incendi.",
          url: "https://nitter.net/bomberscat/status/1",
          source_type: "social",
          source_name: "Nitter @bomberscat",
          confidence: 0.9,
          review_status: "accepted",
          geometry_inference_method: "municipality",
          spatial_precision: "municipality",
        },
      ],
    }),
    searchCivilMunicipality: async () => ({
      data_type: "civil_collection",
      items: [],
      pagination: { limit: 50, offset: 0, count: 0 },
      warnings: [],
    }),
    lookupMunicipalities: async () => ({
      data_type: "municipality_lookup",
      items: [
        {
          id: "5205",
          name: "Molins de Rei",
          ine_code: "08123",
          national_code: "34090808123",
          longitude: 2.0344,
          latitude: 41.4207,
          bbox: "2.005604,41.389777,2.064185,41.445562",
          source: {
            name: "Municipios IGN",
            authority: "Instituto Geográfico Nacional",
            url: "https://www.ign.es",
            attribution: "Municipios IGN CC-BY 4.0 ign.es",
          },
          match_rank: 0,
        },
      ],
      pagination: { limit: 8, offset: 0, count: 1 },
      warnings: [],
    }),
  };
});

function renderWithClient(children: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{children}</QueryClientProvider>);
}

afterEach(() => cleanup());

describe("CivilPortal", () => {
  it("renders the public sections without relying on the map only", async () => {
    renderWithClient(<CivilPortal />);

    expect(screen.getByRole("heading", { name: "Incendis i avisos publics" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Seccions Civil" })).toBeInTheDocument();
    const map = screen.getByLabelText("Mapa civil");
    expect(map).toBeInTheDocument();
    expect(within(map).getByLabelText("Municipi")).toBeInTheDocument();
    expect(within(map).getByText("Capes")).toBeInTheDocument();
    expect(within(map).getByText("Llegenda")).toBeInTheDocument();
    expect(screen.queryByLabelText("Panell Civil")).not.toBeInTheDocument();
    expect(screen.getByText("Llegenda")).toBeInTheDocument();
    expect(screen.getByText("Carretera: incendi o obstacle ambiental")).toBeInTheDocument();
    expect(screen.getByText("Carretera: altres afectacions")).toBeInTheDocument();
    expect(screen.getByText("Àrea cremada EFFIS")).toBeInTheDocument();
    expect(screen.getByText(/Avís OSINT de/)).toBeInTheDocument();
    fireEvent.click(within(map).getByRole("button", { name: "Tanca la llegenda" }));
    expect(screen.queryByText("Àrea cremada EFFIS")).not.toBeInTheDocument();
    fireEvent.click(within(map).getByRole("button", { name: "Obre la llegenda" }));
    expect(screen.getByText("Àrea cremada EFFIS")).toBeInTheDocument();
    expect(screen.getAllByText("Alertes ES-Alert").length).toBeGreaterThan(0);
    expect(screen.queryByText("Evacuacions")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Incendis actuals")).toBeChecked();
    expect(screen.getByLabelText("Incendis d'aquest any")).not.toBeChecked();
    expect(screen.getByLabelText("Històric d'incendis")).not.toBeChecked();
    expect(screen.getByLabelText("Cronologia diària de deteccions FIRMS")).toBeInTheDocument();
    expect(screen.getByLabelText("Avisos i cronologia")).toBeChecked();
    expect(screen.getByLabelText("Punts FIRMS")).not.toBeChecked();
    expect(screen.getByLabelText("Ordena incidents")).toHaveValue("day");
    expect(await screen.findByText("128,4 ha")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("1 elements").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("button", { name: "Selecciona restricció del mapa" }));
    expect(screen.getByTestId("map-focus-geometry")).toHaveTextContent("LineString");

    await waitFor(() => {
      expect(screen.getByText("40 deteccions durant tot el dia")).toBeInTheDocument();
    });
    expect(
      screen.getByText("S'han mobilitzat 12 dotacions de Bombers per consolidar el perímetre."),
    ).toBeInTheDocument();
    expect(screen.getByText("Actualització d'extinció")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Cronologia diària de deteccions FIRMS"), {
      target: { value: "0" },
    });
    fireEvent.change(screen.getByLabelText("Ordena incidents"), { target: { value: "area" } });
    expect(screen.getByLabelText("Ordena incidents")).toHaveValue("area");

    await waitFor(() => {
      expect(screen.getByText("20 deteccions durant tot el dia")).toBeInTheDocument();
    });

    const socialIncidentButton = await screen.findByRole("button", { name: /Incendi prova/ });
    expect(socialIncidentButton).toHaveClass("border-l-[#2563eb]");
    fireEvent.click(socialIncidentButton);
    expect(screen.getByTestId("map-focus")).toHaveTextContent("geometry");
    const details = document.getElementById("detall-incident");
    expect(details).not.toBeNull();
    expect(
      await within(details as HTMLElement).findByText("Inici de l'incendi"),
    ).toBeInTheDocument();
    expect(
      await within(details as HTMLElement).findByText("Municipi prova, Barcelona"),
    ).toBeInTheDocument();
    expect(within(details as HTMLElement).getByText(/40 deteccions\s*FIRMS/)).toBeInTheDocument();
    expect(
      await within(details as HTMLElement).findByText("12 dotacions treballen en l'incendi."),
    ).toBeInTheDocument();
    expect(
      within(details as HTMLElement)
        .getByText("12 dotacions treballen en l'incendi.")
        .closest("article"),
    ).toHaveClass("border-[#2563eb]");
    expect(
      within(details as HTMLElement).getByText("Tots els camps del shapefile EFFIS"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Veure tota la informació" }));
    expect(
      within(details as HTMLElement).getByRole("heading", { name: "Incendi prova" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /INFOCAT ALERTA/ }));
    expect(screen.getByTestId("map-focus")).toHaveTextContent("0.15,40.5,3.35,42.9");

    fireEvent.click(screen.getByLabelText("Avisos i cronologia"));
    expect(screen.queryByRole("button", { name: /INFOCAT ALERTA/ })).not.toBeInTheDocument();
  });

  it("keeps the municipality search keyboard accessible", async () => {
    renderWithClient(<CivilPortal />);

    fireEvent.change(screen.getByLabelText("Municipi"), { target: { value: "Molins" } });
    fireEvent.click(screen.getByRole("button", { name: "Cerca" }));

    await waitFor(() => {
      expect(screen.getByDisplayValue("Molins de Rei")).toBeInTheDocument();
    });
    expect(screen.getByText("Molins de Rei centrat amb dades IGN.")).toBeInTheDocument();
  });
});
