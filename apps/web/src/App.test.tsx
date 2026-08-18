import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import { loadWebConfiguration } from "./config";

describe("Slice 2 web shell", () => {
  it("renders the persistent synthetic boundary and report-first loading state", () => {
    const html = renderToStaticMarkup(<App path="/" />);
    expect(html).toContain("Synthetic demo data");
    expect(html).toContain("No live services connected");
    expect(html).toContain("Loading synthetic review data");
    expect(html).toContain("Daily report");
  });

  it("renders the content-free health page", () => {
    const html = renderToStaticMarkup(<App path="/health" />);
    expect(html).toContain("System health");
    expect(html).toContain("content-free liveness and readiness");
  });

  it("rejects a real-data web configuration", () => {
    expect(() =>
      loadWebConfiguration({
        VITE_APP_PROFILE: "demo",
        VITE_ALLOW_REAL_CALL_DATA: "true",
      }),
    ).toThrow("refuses real call data");
  });

  it("rejects a deployment profile in the synthetic shell", () => {
    expect(() =>
      loadWebConfiguration({
        VITE_APP_PROFILE: "production",
        VITE_ALLOW_REAL_CALL_DATA: "false",
      }),
    ).toThrow("supports only test or demo");
  });
});
