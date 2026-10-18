import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { setToken } from "../../lib/auth";
import { jsonResponse, renderRoute, stubFetch, type RecordedCall } from "../../test/utils";
import { DEMOINFO, FINANCIALS } from "../companies/fixtures";

const DCF_RESULT = {
  currency: "INR",
  scale: "crores",
  terminal_method: "perpetuity_growth",
  years: [{ year: 1, free_cash_flow: "100", discount_period: "1", discount_factor: "0.909", present_value: "90.9" }],
  sum_pv_fcf: "300",
  terminal_value: "1700",
  pv_terminal_value: "1200",
  enterprise_value: "1431.82",
  equity_value: "1231.82",
  value_per_share: "123.18",
  terminal_value_share: "0.81",
  implied_exit_multiple: null,
  implied_terminal_growth: null,
  warnings: [{ code: "terminal_value_dominant", severity: "warning", message: "Terminal value is over 75% of EV." }],
};

const GRID = { output: "value_per_share", row_axis: "wacc", column_axis: "terminal_growth", row_values: ["0.1"], column_values: ["0.02"], cells: [["123.18"]], invalid_reasons: {} };

function bodyOf(call: RecordedCall | undefined, fetchMock: ReturnType<typeof stubFetch>) {
  const index = fetchMock.calls.indexOf(call as RecordedCall);
  const init = fetchMock.mock.calls[index]?.[1] as RequestInit | undefined;
  return JSON.parse(String(init?.body));
}

beforeEach(() => setToken("t"));
afterEach(() => act(() => setToken(null)));

async function type(label: string, value: string) {
  const input = await screen.findByLabelText(label);
  await userEvent.clear(input);
  await userEvent.type(input, value);
}

describe("DCF calculator", () => {
  it("sends exact decimal strings in ₹ crore and shows the result with warnings", async () => {
    const fetchMock = stubFetch({
      "POST /api/v1/calculations/dcf": () => jsonResponse(DCF_RESULT),
      "POST /api/v1/calculations/dcf/sensitivity": () => jsonResponse(GRID),
    });
    renderRoute("/calculators");
    await type("Free cash flow by year (₹ Cr)", "100, 110, 121");
    await type("WACC", "10");
    await type("Terminal growth", "2");
    await type("Net debt (₹ Cr)", "200");
    await type("Shares outstanding (count)", "100000000");
    await userEvent.click(screen.getByRole("button", { name: "Run DCF" }));

    expect(await screen.findByTestId("dcf-per-share")).toHaveTextContent("₹123.18");
    expect(screen.getByText("Terminal value is over 75% of EV.")).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "Sensitivity table" })).toBeInTheDocument();

    const call = fetchMock.calls.find((c) => c.path === "/api/v1/calculations/dcf");
    expect(bodyOf(call, fetchMock)).toEqual({
      currency: "INR",
      scale: "crores",
      free_cash_flows: ["100", "110", "121"],
      wacc: "0.1",
      terminal_method: "perpetuity_growth",
      terminal_growth: "0.02",
      mid_year_convention: false,
      net_debt: "200",
      other_claims: "0",
      shares_outstanding: "10", // 10 crore shares, so value per share is in rupees
    });
  });

  it("rejects incomplete input locally", async () => {
    const fetchMock = stubFetch({});
    renderRoute("/calculators");
    await userEvent.click(await screen.findByRole("button", { name: "Run DCF" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/free cash flows/);
    expect(fetchMock.calls).toHaveLength(0);
  });

  it("prefills the equity bridge from a company's reported statements", async () => {
    const period = FINANCIALS.periods[0];
    if (!period) throw new Error("fixture");
    const withBalance = {
      ...FINANCIALS,
      periods: [
        {
          ...period,
          line_items: [
            ...period.line_items,
            { statement: "balance", item: "total_debt", value: "500.00", source_concept: null, source_accession: null },
            { statement: "balance", item: "cash_and_equivalents", value: "120.50", source_concept: null, source_accession: null },
            { statement: "balance", item: "shares_outstanding", value: "400000000", source_concept: null, source_accession: null },
          ],
        },
      ],
    };
    stubFetch({ "/api/v1/companies/DEMOINFO/financials": () => jsonResponse(withBalance) });
    renderRoute("/calculators?ticker=DEMOINFO");
    await waitFor(async () => expect(await screen.findByLabelText("Net debt (₹ Cr)")).toHaveValue("379.5"));
    expect(screen.getByLabelText("Shares outstanding (count)")).toHaveValue("400000000");
    expect(screen.getByText(/prefilled from DEMOINFO's FY26 consolidated statements/)).toBeInTheDocument();
  });

  it("passes a computed WACC into the DCF form", async () => {
    stubFetch({
      "POST /api/v1/calculations/wacc": () =>
        jsonResponse({ cost_of_equity: "0.13", after_tax_cost_of_debt: "0.06", equity_weight: "0.8", debt_weight: "0.2", wacc: "0.1160", warnings: [] }),
    });
    renderRoute("/calculators");
    await userEvent.click(within(await screen.findByRole("group", { name: "Calculator" })).getByRole("button", { name: "WACC" }));
    for (const [label, value] of [
      ["Risk-free rate", "7"],
      ["Equity risk premium", "6"],
      ["Beta", "1"],
      ["Pre-tax cost of debt", "8"],
      ["Marginal tax rate", "25"],
      ["Market value of equity (₹ Cr)", "800"],
      ["Market value of debt (₹ Cr)", "200"],
    ] as const) {
      await type(label, value);
    }
    await userEvent.click(screen.getByRole("button", { name: "Compute WACC" }));
    expect(await screen.findByTestId("wacc-value")).toHaveTextContent("11.60%");
    await userEvent.click(screen.getByRole("button", { name: "Use in DCF" }));
    expect(screen.getByLabelText("WACC")).toHaveValue("11.6");
  });
});

describe("watchlists and saved valuations", () => {
  it("creates a watchlist and adds an Indian company", async () => {
    let lists: unknown[] = [];
    const fetchMock = stubFetch({
      "GET /api/v1/watchlists": () => jsonResponse(lists),
      "POST /api/v1/watchlists": () => {
        lists = [{ id: "w1", name: "Banks", companies: [], created_at: "", updated_at: "" }];
        return jsonResponse(lists[0], 201);
      },
      "POST /api/v1/watchlists/w1/items": () => {
        lists = [{ id: "w1", name: "Banks", companies: [DEMOINFO], created_at: "", updated_at: "" }];
        return jsonResponse(lists[0]);
      },
    });
    renderRoute("/watchlists");
    expect(await screen.findByText("You have no watchlists yet.")).toBeInTheDocument();
    await type("New watchlist", "Banks");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    await type("Add by ticker or ISIN", "demoinfo");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByRole("link", { name: "Demo Infotech Ltd (DEMOINFO)" })).toBeInTheDocument();
    const add = fetchMock.calls.find((c) => c.path === "/api/v1/watchlists/w1/items");
    expect(bodyOf(add, fetchMock)).toEqual({ ticker: "demoinfo", market: "IN" });
  });

  it("lists and deletes saved valuations", async () => {
    let saved = [
      {
        id: "v1",
        name: "Base case",
        ticker: "DEMOINFO",
        market: "IN",
        method: "dcf",
        engine_version: "0.1.0",
        inputs: { wacc: "0.1", terminal_method: "perpetuity_growth", terminal_growth: "0.02" },
        result: DCF_RESULT,
        created_at: "2026-10-18T10:00:00Z",
      },
    ];
    stubFetch({
      "GET /api/v1/valuations": () => jsonResponse(saved),
      "DELETE /api/v1/valuations/v1": () => {
        saved = [];
        return new Response(null, { status: 204 });
      },
    });
    renderRoute("/valuations");
    expect(await screen.findByText("₹1,431.82 Cr")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete Base case" }));
    expect(await screen.findByText(/No saved valuations/)).toBeInTheDocument();
  });
});
