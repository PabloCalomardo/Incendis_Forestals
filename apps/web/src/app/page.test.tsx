import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import HomePage from "./page";

vi.mock("@/lib/api/client", () => ({
  getApiStatus: async () => ({ ok: true, version: "0.1.0" }),
}));

describe("HomePage", () => {
  it("shows entry points for both portals", async () => {
    render(await HomePage());

    expect(screen.getByText("Portal Civil")).toBeInTheDocument();
    expect(screen.getByText("Portal Bomber")).toBeInTheDocument();
    expect(screen.getByText("connectada")).toBeInTheDocument();
  });
});
