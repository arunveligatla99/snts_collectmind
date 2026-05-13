import { apiCall, ApiError } from "../client";

export async function readyCheck(): Promise<"ok" | "down"> {
  try {
    await apiCall({ method: "GET", path: "/ready" });
    return "ok";
  } catch (e) {
    if (e instanceof ApiError) return "down";
    return "down";
  }
}
