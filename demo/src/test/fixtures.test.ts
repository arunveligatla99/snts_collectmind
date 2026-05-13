import { describe, it, expect } from "vitest";
import { resolveFixture, listFixtureKeys } from "@/api/fixtures";

describe("fixture resolver", () => {
  it("returns a hit on exact body match", () => {
    const hit = resolveFixture({
      method: "POST",
      path: "/findings",
      principal: "tenant-a",
      body: {
        schema_version: "1.0.0",
        finding_id: "f-tenant-a-001",
        anomaly_type: "brake_wear_early_stage",
        hypothesis_class: "BrakeWearHypothesisRule",
        hypothesis_statement: "Front-left pad wear approaching threshold",
        candidate_signals: [
          "Vehicle.Chassis.Axle.Row1.Wheel.Left.Brake.PadWear",
          "Vehicle.Powertrain.CombustionEngine.EngineOil.Temperature",
        ],
        vehicle_scope: ["VIN-AAAA-0001"],
        upstream_confidence: 0.86,
      },
    });
    expect(hit?.status).toBe(202);
  });

  it("falls back to the method+path entry when body does not match", () => {
    const hit = resolveFixture({
      method: "POST",
      path: "/findings",
      principal: "tenant-a",
      body: { different: "body" },
    });
    expect(hit?.status).toBe(202);
  });

  it("returns undefined for an unknown method+path", () => {
    const hit = resolveFixture({ method: "GET", path: "/nope" });
    expect(hit).toBeUndefined();
  });

  it("listFixtureKeys returns all keys", () => {
    const keys = listFixtureKeys();
    expect(keys.length).toBeGreaterThan(5);
    expect(keys.some((k) => k.startsWith("GET /audit/"))).toBe(true);
  });
});
