import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { Routes, Route } from "react-router-dom";
import App from "@/App";
import { Tenants } from "@/routes/Tenants";
import { renderWithProviders, resetStores } from "./utils";

vi.mock("mermaid", () => ({
  default: { initialize: vi.fn(), render: vi.fn(async () => ({ svg: "" })) },
}));

describe("App router", () => {
  beforeEach(resetStores);

  it("renders the landing on /", async () => {
    renderWithProviders(<App />, { initialEntries: ["/"] });
    expect(
      await screen.findByText(/diagnostic-to-collection loop/i),
    ).toBeInTheDocument();
  });

  it("renders /operator", async () => {
    renderWithProviders(<App />, { initialEntries: ["/operator"] });
    expect(
      await screen.findByText(/Operator — submit \+ watch the loop/i),
    ).toBeInTheDocument();
  });

  it("renders /audit", async () => {
    renderWithProviders(<App />, { initialEntries: ["/audit"] });
    expect(await screen.findByText("Audit chain explorer")).toBeInTheDocument();
  });

  it("renders /slo", async () => {
    renderWithProviders(<App />, { initialEntries: ["/slo"] });
    expect(await screen.findByText(/SLOs — measured \+ gated/i)).toBeInTheDocument();
  });

  it("renders /tenants", async () => {
    renderWithProviders(<App />, { initialEntries: ["/tenants"] });
    expect(
      await screen.findByText(/Tenants — isolation \+ break-glass/i),
    ).toBeInTheDocument();
  });

  it("renders /docs and a subpath", async () => {
    renderWithProviders(<App />, { initialEntries: ["/docs/adr-0001"] });
    expect(
      await screen.findByText(/Pin COVESA VSS to v6\.0/i, undefined, { timeout: 3000 }),
    ).toBeInTheDocument();
  });

  it("falls back to landing on unknown routes", async () => {
    renderWithProviders(<App />, { initialEntries: ["/nope"] });
    expect(
      await screen.findByText(/diagnostic-to-collection loop/i),
    ).toBeInTheDocument();
  });
});

describe("Tenants — interactive flows", () => {
  beforeEach(resetStores);

  it("submits as tenant-a, populates audit, then break-glass merges in the kind=break_glass row", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/" element={<Tenants />} />
      </Routes>,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /POST \/findings as tenant-a/i }),
    );
    await waitFor(() =>
      expect(screen.getAllByText(/correlation_id/i).length).toBeGreaterThan(0),
    );
    const bgButton = await screen.findByRole("button", {
      name: /POST \/audit\/break-glass\/query/i,
    });
    fireEvent.click(bgButton);
    await waitFor(() =>
      expect(screen.getAllByText(/break-glass/i).length).toBeGreaterThan(0),
    );
  });

  it("submits as tenant-b independently", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/" element={<Tenants />} />
      </Routes>,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /POST \/findings as tenant-b/i }),
    );
    await waitFor(() =>
      expect(
        screen.getByText("01HW1A2B3C4D5E6F7G8H9J0KQB"),
      ).toBeInTheDocument(),
    );
  });
});
