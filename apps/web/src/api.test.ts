import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("API failure boundaries", () => {
  it.each(["null", "42", "", "not-json"])("rejects invalid successful payload %s", async (body) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 200 })));
    await expect(apiRequest("/api/reports", "demo-reviewer")).rejects.toMatchObject({ status: 200 });
  });
  it("retains correlation on an interrupted response body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      status: 500, headers: new Headers({ "X-Correlation-ID": "request-1234" }),
      text: () => Promise.reject(new Error("private transport details")),
    }));
    await expect(apiRequest("/api/reports", "demo-reviewer")).rejects.toMatchObject({
      status: 500, correlationId: "request-1234",
      message: "The service response was interrupted. Check the saved state before retrying.",
    });
  });
  it("surfaces server failure with its correlation ID", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: { error: "internal_error", correlation_id: "request-1234" },
    }), { status: 500 })));
    await expect(apiRequest("/api/reports", "demo-reviewer")).rejects.toMatchObject({
      status: 500, correlationId: "request-1234", message: "internal_error",
    });
  });
});
