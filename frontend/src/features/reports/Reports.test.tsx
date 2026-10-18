import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setToken } from "../../lib/auth";
import { jsonResponse, renderRoute, stubFetch } from "../../test/utils";
import { DEMOINFO, NO_FINANCIALS, quote } from "../companies/fixtures";
import type { ReportOut } from "./api";

const REPORT: ReportOut = {
  id: "r1",
  title: "Demo Infotech Ltd — research report",
  ticker: "DEMOINFO",
  includes_ai: false,
  engine_version: "0.1.0",
  created_at: "2026-10-18T10:00:00Z",
  content: {
    title: "Demo Infotech Ltd — research report",
    generated_at: "2026-10-18T10:00:00Z",
    company: { market: "IN", ticker: "DEMOINFO", name: "Demo Infotech Ltd", isin: null, listings: ["BSE: DEMOINFO", "NSE: DEMOINFO"] },
    exchange: "NSE",
    basis: "consolidated",
    disclaimers: ["This report is not investment advice."],
    engine_version: "0.1.0",
    sections: [
      {
        key: "market",
        title: "Market data (end of day)",
        status: "ok",
        reason: null,
        paragraphs: [],
        tables: [],
        figures: [{ label: "Close, NSE: DEMOINFO", value: "1967.80", display: "₹1,967.80", kind: "market", period: "2026-10-16", basis: null, source: "demo (demo)", note: null }],
      },
      {
        key: "financials",
        title: "Financial statements (consolidated)",
        status: "ok",
        reason: null,
        paragraphs: [],
        figures: [],
        tables: [{ caption: "Annual figures, consolidated", kind: "reported", columns: ["Item", "FY26"], rows: [["Revenue", "12,000.00"]], source: "demo" }],
      },
      { key: "ai", title: "AI summary (cited)", status: "unavailable", reason: "AI summary not requested", figures: [], tables: [], paragraphs: [] },
    ],
  },
};

beforeEach(() => setToken("t"));
afterEach(() => act(() => setToken(null)));

describe("research reports", () => {
  it("generates a report for the selected listing and shows provenance", async () => {
    const fetchMock = stubFetch({
      "/api/v1/companies/DEMOINFO": () => jsonResponse(DEMOINFO),
      "/api/v1/companies/DEMOINFO/financials": () => jsonResponse(NO_FINANCIALS),
      "/api/v1/companies/DEMOINFO/quote": () => jsonResponse(quote("NSE", "1967.80")),
      "/api/v1/research/status": () => jsonResponse({ configured: false, provider: null, model: null }),
      "POST /api/v1/reports": () => jsonResponse(REPORT, 201),
      "GET /api/v1/reports/r1": () => jsonResponse(REPORT),
    });
    renderRoute("/companies/DEMOINFO?exchange=NSE");
    await userEvent.click(await screen.findByRole("button", { name: "Generate research report" }));

    expect(await screen.findByRole("heading", { name: "Demo Infotech Ltd — research report" })).toBeInTheDocument();
    const market = screen.getByRole("region", { name: "Market data (end of day)" });
    expect(within(market).getByText("Market data (EOD)")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Financial statements (consolidated)" })).getByText("Reported")).toBeInTheDocument();
    expect(screen.getByText("Unavailable: AI summary not requested")).toBeInTheDocument();

    const post = fetchMock.calls.find((c) => c.method === "POST" && c.path === "/api/v1/reports");
    const init = fetchMock.mock.calls[fetchMock.calls.indexOf(post!)]?.[1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({ ticker: "DEMOINFO", market: "IN", exchange: "NSE", include_ai: false });
  });

  it("downloads exports with the user's token", async () => {
    const createObjectURL = vi.fn(() => "blob:x");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const fetchMock = stubFetch({
      "GET /api/v1/reports/r1": () => jsonResponse(REPORT),
      "GET /api/v1/reports/r1/export": () =>
        new Response("# report", { headers: { "content-disposition": 'attachment; filename="finsight-DEMOINFO-20261018.md"' } }),
    });
    renderRoute("/reports/r1");
    await userEvent.click(await screen.findByRole("button", { name: "Download Markdown" }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    const exportCall = fetchMock.calls.find((c) => c.path === "/api/v1/reports/r1/export");
    expect(exportCall?.params.get("format")).toBe("md");
    expect(exportCall?.headers.get("Authorization")).toBe("Bearer t");
    expect(createObjectURL).toHaveBeenCalled();
  });
});
