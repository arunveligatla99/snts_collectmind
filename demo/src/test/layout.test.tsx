import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { Routes, Route } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { useModeStore } from "@/store/mode";
import { renderWithProviders, resetStores } from "./utils";

vi.mock("mermaid", () => ({
  default: { initialize: vi.fn(), render: vi.fn(async () => ({ svg: "" })) },
}));

describe("Layout shell", () => {
  beforeEach(resetStores);

  it("renders header + sidebar + footer + outlet content", () => {
    renderWithProviders(
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<div data-testid="outlet">CHILD</div>} />
        </Route>
      </Routes>,
    );
    expect(screen.getByText("CollectMind")).toBeInTheDocument();
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Operator")).toBeInTheDocument();
    expect(screen.getByTestId("outlet")).toBeInTheDocument();
    expect(screen.getByText(/built per constitution/)).toBeInTheDocument();
  });
});

describe("Header recorded banner", () => {
  beforeEach(resetStores);

  it("renders the recorded snapshot banner in recorded mode", () => {
    useModeStore.setState({ mode: "recorded" });
    renderWithProviders(<Header />);
    expect(screen.getByText(/Recorded snapshot/)).toBeInTheDocument();
  });

  it("hides the recorded banner in live mode", () => {
    useModeStore.setState({ mode: "live" });
    renderWithProviders(<Header />);
    expect(screen.queryByText(/Recorded snapshot/)).toBeNull();
  });

  it("ModeToggle inside Header flips the mode", () => {
    renderWithProviders(<Header />);
    const toggle = screen.getAllByRole("button").find((b) => b.textContent?.includes("mode:"));
    expect(toggle).toBeDefined();
    fireEvent.click(toggle!);
    expect(useModeStore.getState().mode).toBe("live");
  });
});

describe("Footer", () => {
  it("shows the snapshot SHA + date", () => {
    renderWithProviders(<Footer />);
    expect(screen.getByText(/Snapshot/)).toBeInTheDocument();
    expect(screen.getByText(/OpenAPI v1\.1\.0/)).toBeInTheDocument();
  });
});
