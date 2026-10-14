import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { jsonResponse, renderRoute, stubFetch } from "../../test/utils";

const live = { status: "ok", service: "FinSight API", version: "0.1.0", environment: "test" };

describe("SystemStatus on the home page", () => {
  it("shows API online and database connected", async () => {
    stubFetch({
      "/api/v1/health/live": () => jsonResponse(live),
      "/api/v1/health/ready": () => jsonResponse({ status: "ok", checks: { database: "ok" } }),
    });
    renderRoute("/");
    expect(await screen.findByText("Online · v0.1.0")).toBeInTheDocument();
    expect(await screen.findByText("Connected")).toBeInTheDocument();
  });

  it("shows database unavailable when readiness returns 503", async () => {
    stubFetch({
      "/api/v1/health/live": () => jsonResponse(live),
      "/api/v1/health/ready": () => jsonResponse({ status: "unavailable", checks: { database: "error" } }, 503),
    });
    renderRoute("/");
    expect(await screen.findByText("Unavailable")).toBeInTheDocument();
  });

  it("shows API unreachable when liveness fails", async () => {
    stubFetch({});
    renderRoute("/");
    expect(await screen.findByText("Unreachable")).toBeInTheDocument();
  });
});

describe("routing", () => {
  it("renders the not-found page for unknown routes", async () => {
    stubFetch({});
    renderRoute("/nope");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
