import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CivilPortal } from "./civil-portal";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/map-shell", () => ({
  MapShell: () => <div aria-label="Mapa civil">mapa civil</div>,
}));

vi.mock("@/lib/api/civil", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/civil")>();
  return {
    ...actual,
    getCivilLayer: async () => ({ type: "FeatureCollection", features: [] }),
    getCivilCollection: async () => ({
      data_type: "civil_collection",
      items: [],
      pagination: { limit: 50, offset: 0, count: 0 },
      warnings: [],
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
    expect(screen.getByLabelText("Mapa civil")).toBeInTheDocument();
    expect(screen.getByText("Llegenda")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Sense incidents publics amb els filtres actuals.")).toBeInTheDocument();
    });
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
