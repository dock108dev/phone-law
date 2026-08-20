import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import { loadWebConfiguration } from "./config";

describe("Colacci Law workspace shell", () => {
  it("renders the persistent synthetic boundary and month-history loading state", () => {
    const html = renderToStaticMarkup(<App path="/" />);
    expect(html).toContain("Local / synthetic");
    expect(html).toContain("No client data or live services");
    expect(html).toContain("Loading month history");
    expect(html).toContain("Month history");
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
