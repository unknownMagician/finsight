import { describe, expect, it, vi } from "vitest";

import { jsonResponse, stubFetch } from "../test/utils";
import { ApiError, apiFetch } from "./api";

describe("apiFetch", () => {
  it("prefixes the API base and returns parsed JSON", async () => {
    const fetchMock = stubFetch({ "/api/v1/things": () => jsonResponse({ ok: true }) });
    await expect(apiFetch("/things")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/things", expect.anything());
  });

  it("parses the backend error envelope into ApiError", async () => {
    stubFetch({
      "/api/v1/bad": () =>
        jsonResponse(
          { error: { code: "validation_error", message: "Request validation failed", request_id: "r1", details: [1] } },
          422,
        ),
    });
    const error = await apiFetch("/bad").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 422, code: "validation_error", requestId: "r1", details: [1] });
  });

  it("falls back gracefully when the error body is not JSON", async () => {
    stubFetch({ "/api/v1/html": () => new Response("<html>", { status: 502, headers: { "x-request-id": "r2" } }) });
    const error = await apiFetch("/html").catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 502, code: "http_error", requestId: "r2" });
  });

  it("maps network failures to a network_error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await apiFetch("/x").catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 0, code: "network_error" });
  });
});
