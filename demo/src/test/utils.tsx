import { type ReactNode } from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useModeStore } from "@/store/mode";
import { useTokensStore } from "@/store/tokens";

export function makeWrapper(options?: {
  initialEntries?: string[];
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={options?.initialEntries ?? ["/"]}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </MemoryRouter>
    );
  };
}

export function renderWithProviders(
  ui: ReactNode,
  options?: RenderOptions & { initialEntries?: string[] },
) {
  const Wrapper = makeWrapper({ initialEntries: options?.initialEntries });
  return render(ui, { wrapper: Wrapper, ...options });
}

export function resetStores() {
  useModeStore.setState({
    mode: "recorded",
    baseUrl: "/api/v1",
    connectivity: "unknown",
  });
  useTokensStore.setState({
    tokens: {
      "tenant-a": "fixture-a",
      "tenant-b": "fixture-b",
      "operator-alice": "fixture-op",
    },
    active: "tenant-a",
  });
}
