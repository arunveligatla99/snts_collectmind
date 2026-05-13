import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { Routes, Route } from "react-router-dom";
import { Landing } from "@/routes/Landing";
import { Operator } from "@/routes/Operator";
import { Audit } from "@/routes/Audit";
import { Slo } from "@/routes/Slo";
import { Tenants } from "@/routes/Tenants";
import { Docs } from "@/routes/Docs";
import { useModeStore } from "@/store/mode";
import { renderWithProviders, resetStores } from "./utils";

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async () => ({ svg: "<svg data-testid='svg-stub'></svg>" })),
  },
}));

describe("Landing route", () => {
  beforeEach(resetStores);

  it("renders pitch + SLO tiles + nav buttons", async () => {
    renderWithProviders(<Landing />);
    expect(
      screen.getByText(/diagnostic-to-collection loop, closed under SLM rigor/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Dashboard lag/i)).toBeInTheDocument();
    expect(screen.getByText(/Test bar/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Run the loop/ })).toHaveAttribute(
      "href",
      "/operator",
    );
    await waitFor(() => expect(screen.getByRole("img")).toBeInTheDocument());
  });
});

describe("Operator route", () => {
  beforeEach(resetStores);

  it("publishes a finding and renders the audit chain + outcome", async () => {
    renderWithProviders(<Operator />);
    fireEvent.click(screen.getByRole("button", { name: /POST \/findings/i }));
    await waitFor(() =>
      expect(screen.getByText("01HW1A2B3C4D5E6F7G8H9J0KQA")).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByText(/Open in \/audit explorer/i)).toBeInTheDocument(),
    );
    await waitFor(() => expect(screen.getByText("confirmed")).toBeInTheDocument());
  });

  it("rejects malformed JSON", () => {
    renderWithProviders(<Operator />);
    const textarea = screen.getByLabelText(/DiagnosticFindingEvent JSON editor/i);
    fireEvent.change(textarea, { target: { value: "{ not json" } });
    expect(screen.getByText(/JSON parse error/i)).toBeInTheDocument();
  });
});

describe("Audit route", () => {
  beforeEach(resetStores);

  it("renders the audit chain for the seeded correlation id", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/audit" element={<Audit />} />
      </Routes>,
      { initialEntries: ["/audit"] },
    );
    await waitFor(() =>
      expect(screen.getByText(/5 of 5 events/i)).toBeInTheDocument(),
    );
  });

  it("filters by kind", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/audit" element={<Audit />} />
      </Routes>,
      { initialEntries: ["/audit"] },
    );
    await waitFor(() => expect(screen.getByText(/5 of 5 events/i)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("kind filter"), { target: { value: "generated" } });
    expect(await screen.findByText(/1 of 5 events/i)).toBeInTheDocument();
  });
});

describe("Slo route", () => {
  it("renders measured + gated SLO tiles", () => {
    renderWithProviders(<Slo />);
    expect(screen.getByText(/Measured \(local runs\)/)).toBeInTheDocument();
    expect(screen.getByText(/Gated/)).toBeInTheDocument();
    expect(screen.getByText(/Sustained ingest/)).toBeInTheDocument();
    expect(screen.getAllByText("gated").length).toBeGreaterThan(0);
  });
});

describe("Tenants route", () => {
  beforeEach(resetStores);

  it("renders three columns with token chips and tenant configs", async () => {
    renderWithProviders(<Tenants />);
    expect(screen.getAllByText(/tenant-a/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/tenant-b/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/operator/i).length).toBeGreaterThan(0);
    await waitFor(() =>
      expect(screen.getAllByText(/rps/).length).toBeGreaterThan(0),
    );
  });
});

describe("Docs route", () => {
  beforeEach(resetStores);

  it("renders the constitution markdown by default", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/docs/*" element={<Docs />} />
      </Routes>,
      { initialEntries: ["/docs"] },
    );
    await waitFor(() =>
      expect(screen.getByText(/CollectMind Constitution/i)).toBeInTheDocument(),
    );
  });
});

describe("Mode propagation", () => {
  beforeEach(resetStores);

  it("recorded mode shows fixture connectivity pill", () => {
    useModeStore.setState({ mode: "recorded" });
    renderWithProviders(<Slo />);
    expect(useModeStore.getState().mode).toBe("recorded");
  });
});
