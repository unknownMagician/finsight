import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { setToken } from "../../lib/auth";
import { jsonResponse, renderRoute, stubFetch } from "../../test/utils";
import { DEMOINFO, FINANCIALS, NO_FINANCIALS, quote } from "./fixtures";

const STATUS = {
  default_market: "IN",
  providers: [
    { role: "market_data", name: "demo", configured: true, capabilities: [], data_nature: "demo", usage_terms: "Synthetic data." },
    { role: "fundamentals_in", name: "demo", configured: true, capabilities: [], data_nature: "demo", usage_terms: "Synthetic data." },
  ],
  reachable: true,
  latest_trading_date: "2026-10-16",
  published_at: null,
  unavailable_capabilities: ["shareholding"],
};

const notFound = () => jsonResponse({ error: { code: "no_financial_data", message: "No data stored" } }, 404);

const common = {
  "/api/v1/health/live": () => jsonResponse({ status: "ok", service: "FinSight API", version: "0.1.0", environment: "test" }),
  "/api/v1/health/ready": () => jsonResponse({ status: "ok", checks: { database: "ok" } }),
  "/api/v1/market/status": () => jsonResponse(STATUS),
  "/api/v1/companies/DEMOINFO/corporate-actions": () =>
    jsonResponse({ ticker: "DEMOINFO", provider: "demo", retrieved_at: "2026-10-16T13:00:00Z", cached: false, source_urls: [], actions: [] }),
  "/api/v1/companies/DEMOINFO/prices": () =>
    jsonResponse({ ticker: "DEMOINFO", listing: DEMOINFO.instruments[1], currency: "INR", bars: [], freshness: quote("NSE", "1").freshness, warnings: [] }),
  "/api/v1/companies/DEMOINFO/ratios": notFound,
  "/api/v1/companies/DEMOINFO/valuation-snapshot": notFound,
};

beforeEach(() => setToken("test-token"));
afterEach(() => act(() => setToken(null)));

describe("company search", () => {
  it("searches Indian companies, filters by exchange and links to a listing", async () => {
    const fetchMock = stubFetch({ ...common, "/api/v1/companies": () => jsonResponse([DEMOINFO]) });
    renderRoute("/");
    await userEvent.type(screen.getByLabelText("Search companies"), "demo");

    const nseLink = await screen.findByRole("link", { name: "Demo Infotech Ltd on NSE" });
    expect(nseLink).toHaveAttribute("href", "/companies/DEMOINFO?exchange=NSE");
    expect(screen.getByRole("link", { name: "Demo Infotech Ltd on BSE" })).toBeInTheDocument();
    expect(screen.getAllByText("Demo data").length).toBeGreaterThan(0);

    const searchCall = fetchMock.calls.find((c) => c.path === "/api/v1/companies");
    expect(searchCall?.params.get("market")).toBe("IN");
    expect(searchCall?.headers.get("Authorization")).toBe("Bearer test-token");

    const exchangeGroup = screen.getByRole("group", { name: "Exchange" });
    await userEvent.click(within(exchangeGroup).getByRole("button", { name: "BSE" }));
    await waitFor(() =>
      expect(fetchMock.calls.some((c) => c.path === "/api/v1/companies" && c.params.get("exchange") === "BSE")).toBe(true),
    );
    await waitFor(() => expect(screen.queryByRole("link", { name: "Demo Infotech Ltd on NSE" })).not.toBeInTheDocument());
  });
});

describe("company research page", () => {
  it("asks the user to choose when a company is listed on both exchanges", async () => {
    const fetchMock = stubFetch({
      ...common,
      "/api/v1/companies/DEMOINFO": () => jsonResponse(DEMOINFO),
      "/api/v1/companies/DEMOINFO/financials": () => jsonResponse(NO_FINANCIALS),
    });
    renderRoute("/companies/DEMOINFO");
    expect(await screen.findByText(/listed on both NSE and BSE/)).toBeInTheDocument();
    expect(fetchMock.calls.some((c) => c.path.endsWith("/quote"))).toBe(false); // never guesses
  });

  it("shows the listing's end-of-day close with freshness labels and switches exchange", async () => {
    const fetchMock = stubFetch({
      ...common,
      "/api/v1/companies/DEMOINFO": () => jsonResponse(DEMOINFO),
      "/api/v1/companies/DEMOINFO/financials": () => jsonResponse(NO_FINANCIALS),
      "/api/v1/companies/DEMOINFO/quote": (call) =>
        jsonResponse(call.params.get("exchange") === "BSE" ? quote("BSE", "1969.75", true) : quote("NSE", "1967.80")),
    });
    renderRoute("/companies/DEMOINFO?exchange=NSE");
    expect(await screen.findByTestId("close-price")).toHaveTextContent("₹1,967.80");
    const panel = screen.getByRole("region", { name: "Latest close" });
    expect(within(panel).getByText("Demo data")).toBeInTheDocument();
    expect(within(panel).queryByText("Stale")).not.toBeInTheDocument();
    expect(within(panel).getByText(/Not a real-time quote/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Fetch statements" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "BSE: DEMOINFO" }));
    await waitFor(() => expect(screen.getByTestId("close-price")).toHaveTextContent("₹1,969.75"));
    expect(within(screen.getByRole("region", { name: "Latest close" })).getByText("Stale")).toBeInTheDocument();
    expect(fetchMock.calls.some((c) => c.path.endsWith("/quote") && c.params.get("exchange") === "BSE")).toBe(true);
  });

  it("renders statements in ₹ crore and switches between consolidated and standalone", async () => {
    stubFetch({
      ...common,
      "/api/v1/companies/DEMOINFO": () => jsonResponse(DEMOINFO),
      "/api/v1/companies/DEMOINFO/financials": (call) => {
        const basis = call.params.get("basis");
        return jsonResponse({ ...FINANCIALS, periods: FINANCIALS.periods.filter((p) => !basis || p.basis === basis) });
      },
      "/api/v1/companies/DEMOINFO/quote": () => jsonResponse(quote("NSE", "1967.80")),
    });
    renderRoute("/companies/DEMOINFO?exchange=NSE");
    const table = await screen.findByRole("table");
    expect(within(table).getByText("₹1,23,456.78 Cr")).toBeInTheDocument();
    expect(within(table).getByText("FY26")).toBeInTheDocument();
    expect(within(table).getByText("₹54.00")).toBeInTheDocument(); // EPS is per share, unscaled
    expect(within(table).getAllByText("—").length).toBeGreaterThan(0); // unreported items

    await userEvent.click(screen.getByRole("button", { name: "Standalone" }));
    expect(await screen.findByText("₹8,400.00 Cr")).toBeInTheDocument();
  });

  it("redirects to sign-in when not authenticated", async () => {
    act(() => setToken(null));
    stubFetch(common);
    renderRoute("/companies/DEMOINFO");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});
