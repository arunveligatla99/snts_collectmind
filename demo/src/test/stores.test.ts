import { describe, it, expect, beforeEach } from "vitest";
import { useModeStore } from "@/store/mode";
import { useTokensStore } from "@/store/tokens";
import { resetStores } from "./utils";

describe("useModeStore", () => {
  beforeEach(resetStores);

  it("starts in recorded mode by default", () => {
    expect(useModeStore.getState().mode).toBe("recorded");
  });

  it("setMode updates the store", () => {
    useModeStore.getState().setMode("live");
    expect(useModeStore.getState().mode).toBe("live");
  });

  it("setConnectivity updates the store", () => {
    useModeStore.getState().setConnectivity("ok");
    expect(useModeStore.getState().connectivity).toBe("ok");
  });
});

describe("useTokensStore", () => {
  beforeEach(resetStores);

  it("setActive updates the active principal", () => {
    useTokensStore.getState().setActive("tenant-b");
    expect(useTokensStore.getState().active).toBe("tenant-b");
  });

  it("setToken replaces a principal token", () => {
    useTokensStore.getState().setToken("operator-alice", "new-op-token");
    expect(useTokensStore.getState().tokens["operator-alice"]).toBe("new-op-token");
  });
});
