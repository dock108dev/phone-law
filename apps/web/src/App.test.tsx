import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import { loadWebConfiguration } from "./config";

describe("Slice 0 web shell", () => {
  it("renders a persistent synthetic-data banner", () => {
    const html = renderToStaticMarkup(<App path="/" />);
    expect(html).toContain("Synthetic demo data");
    expect(html).toContain("Real call processing is locked");
    expect(html).toContain("Calls loaded");
  });

  it("renders the health page without call content", () => {
    const html = renderToStaticMarkup(<App path="/health" />);
    expect(html).toContain("System health");
    expect(html).toContain("PostgreSQL foundation migration");
  });

  it("rejects a real-data web configuration", () => {
    expect(() =>
      loadWebConfiguration({
        VITE_APP_PROFILE: "demo",
        VITE_ALLOW_REAL_CALL_DATA: "true",
      }),
    ).toThrow("refuses real call data");
  });

  it("rejects a deployment profile in the Slice 0 shell", () => {
    expect(() =>
      loadWebConfiguration({
        VITE_APP_PROFILE: "production",
        VITE_ALLOW_REAL_CALL_DATA: "false",
      }),
    ).toThrow("supports only test or demo");
  });
});
