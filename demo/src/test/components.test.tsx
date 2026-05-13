import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { screen, fireEvent, waitFor, act } from "@testing-library/react";
import { SloTile } from "@/components/SloTile";
import { Fr017aBadge } from "@/components/Fr017aBadge";
import { TokenChip } from "@/components/TokenChip";
import { ConnectivityDot } from "@/components/ConnectivityDot";
import { ModeToggle } from "@/components/ModeToggle";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useModeStore } from "@/store/mode";
import { useTokensStore } from "@/store/tokens";
import { renderWithProviders, resetStores } from "./utils";

describe("SloTile", () => {
  it("renders measured value with budget + headroom + source + PASS pill", () => {
    renderWithProviders(
      <SloTile label="X" value="42" unit="s" budget="100 s" headroom="~2×" source="T999" />,
    );
    expect(screen.getByText("X")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("s")).toBeInTheDocument();
    expect(screen.getByText(/budget 100 s/)).toBeInTheDocument();
    expect(screen.getByText("~2×")).toBeInTheDocument();
    expect(screen.getByText("PASS")).toBeInTheDocument();
  });

  it("renders gated tile when status=gated", () => {
    renderWithProviders(<SloTile label="Y" value="—" source="GPU-runner gate" status="gated" />);
    expect(screen.getByText("gated")).toBeInTheDocument();
  });
});

describe("Fr017aBadge", () => {
  it("renders nothing when no FR-017a fields present", () => {
    const { container } = renderWithProviders(
      <Fr017aBadge
        event={{
          event_id: "x",
          kind: "accepted",
          occurred_at: "2026-05-13T12:00:00Z",
          correlation_id: "cid-x",
        }}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders each FR-017a field when present", () => {
    renderWithProviders(
      <Fr017aBadge
        event={{
          event_id: "y",
          kind: "generated",
          occurred_at: "2026-05-13T12:00:01.347Z",
          correlation_id: "cid-x",
          slm_repo: "Qwen/Qwen2.5-7B-Instruct",
          slm_revision_sha: "a09a35458c702b33eeacc393d103063234e8bc28",
          slm_runtime: "vllm",
          slm_runtime_version: "0.20.1",
          slm_quantization: "bf16",
          slm_decoding_seed: 12648430,
          prompt_template_version: "1.0.0",
        }}
      />,
    );
    expect(screen.getByText("Qwen/Qwen2.5-7B-Instruct")).toBeInTheDocument();
    expect(screen.getByText("a09a35458c702b33eeacc393d103063234e8bc28")).toBeInTheDocument();
    expect(screen.getByText("12648430")).toBeInTheDocument();
    expect(screen.getByText("1.0.0")).toBeInTheDocument();
  });
});

describe("TokenChip", () => {
  beforeEach(resetStores);

  it("shows fixture pill in recorded mode", () => {
    renderWithProviders(<TokenChip principal="tenant-a" audience="collectmind-tenant" />);
    expect(screen.getByText("fixture")).toBeInTheDocument();
  });

  it("shows JWT loaded when in live mode with a token", () => {
    useModeStore.setState({ mode: "live" });
    useTokensStore.setState((s) => ({ ...s, tokens: { ...s.tokens, "operator-alice": "tok-op" } }));
    renderWithProviders(<TokenChip principal="operator-alice" audience="collectmind-operator" />);
    expect(screen.getByText("JWT loaded")).toBeInTheDocument();
  });

  it("shows no JWT in live mode without a token", () => {
    useModeStore.setState({ mode: "live" });
    useTokensStore.setState((s) => ({
      ...s,
      tokens: { ...s.tokens, "tenant-b": undefined },
    }));
    renderWithProviders(<TokenChip principal="tenant-b" audience="collectmind-tenant" />);
    expect(screen.getByText("no JWT")).toBeInTheDocument();
  });
});

describe("ConnectivityDot", () => {
  beforeEach(resetStores);
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("reports recorded fixtures when mode=recorded", async () => {
    renderWithProviders(<ConnectivityDot />);
    expect(await screen.findByText(/recorded fixtures/)).toBeInTheDocument();
  });

  it("probes /ready when mode=live and reports ok on 200", async () => {
    useModeStore.setState({ mode: "live", baseUrl: "/api/v1" });
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ status: "ready" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as unknown as typeof fetch;
    renderWithProviders(<ConnectivityDot />);
    await waitFor(() =>
      expect(screen.getByText(/live · \/ready 200/)).toBeInTheDocument(),
    );
  });
});

describe("ModeToggle", () => {
  beforeEach(resetStores);

  it("flips the mode on click", () => {
    renderWithProviders(<ModeToggle />);
    expect(screen.getByText("recorded")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button"));
    expect(useModeStore.getState().mode).toBe("live");
  });
});

describe("ThemeToggle", () => {
  beforeEach(() => {
    document.documentElement.className = "dark";
  });

  it("toggles the html.light class on click", () => {
    renderWithProviders(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button"));
    expect(document.documentElement.classList.contains("light")).toBe(true);
    fireEvent.click(screen.getByRole("button"));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("flushes initial theme when html starts in light", () => {
    document.documentElement.className = "light";
    renderWithProviders(<ThemeToggle />);
    // initial theme reads from the DOM; button label reflects "light"
    expect(document.documentElement.classList.contains("light")).toBe(true);
    act(() => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});
