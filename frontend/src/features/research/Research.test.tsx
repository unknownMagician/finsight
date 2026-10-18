import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { setToken } from "../../lib/auth";
import { jsonResponse, renderRoute, stubFetch } from "../../test/utils";
import { DEMOINFO, NO_FINANCIALS } from "../companies/fixtures";
import type { DocumentOut } from "../documents/api";
import type { ResearchAnswerOut } from "./api";

const ANSWER: ResearchAnswerOut = {
  question: "What was revenue?",
  kind: "ai_explanation",
  model: "claude-opus-5-5",
  grounding: "partially_grounded",
  segments: [
    { text: "Revenue was ", citations: [] },
    {
      text: "Rs. 12,345.60 crore",
      citations: [{ source: 1, cited_text: "Revenue from operations was Rs. 12,345.60 crore", label: "AR FY26, p. 2", document_id: "d1", page_number: 2 }],
    },
    { text: " and margins were 99%.", citations: [] },
  ],
  sources: [
    { number: 1, title: "AR FY26, p. 2", kind: "document_page", document_id: "d1", page_number: 2 },
    { number: 2, title: "FinSight financial data: Demo Infotech Ltd (DEMOINFO)", kind: "financial_data", document_id: null, page_number: null },
  ],
  issues: [{ code: "uncited_figure", segment: 2, message: "This passage contains a figure without a verifiable source." }],
  input_tokens: 1000,
  output_tokens: 40,
  disclaimer: "AI-generated explanation from the cited sources only. Not investment advice.",
};

const COMPANY_PAGE = {
  "/api/v1/companies/DEMOINFO": () => jsonResponse(DEMOINFO),
  "/api/v1/companies/DEMOINFO/financials": () => jsonResponse(NO_FINANCIALS),
  "/api/v1/companies/DEMOINFO/corporate-actions": () =>
    jsonResponse({ ticker: "DEMOINFO", provider: "demo", retrieved_at: "2026-10-16T13:00:00Z", cached: false, source_urls: [], actions: [] }),
};

beforeEach(() => setToken("t"));
afterEach(() => act(() => setToken(null)));

describe("AI research assistant", () => {
  it("renders cited answers with source markers and flags unsupported figures", async () => {
    const fetchMock = stubFetch({
      ...COMPANY_PAGE,
      "/api/v1/research/status": () => jsonResponse({ configured: true, provider: "anthropic", model: "claude-opus-5-5" }),
      "POST /api/v1/research/ask": () => jsonResponse(ANSWER),
    });
    renderRoute("/companies/DEMOINFO");
    await userEvent.type(await screen.findByLabelText("Research question"), "What was revenue?");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    const answer = await screen.findByLabelText("AI answer");
    expect(within(answer).getByText("AI explanation")).toBeInTheDocument();
    expect(within(answer).getByText("Some claims unsupported")).toBeInTheDocument();
    const marker = within(answer).getByRole("link", { name: "[1]" });
    expect(marker).toHaveAttribute("href", "#source-1");
    expect(marker).toHaveAttribute("title", expect.stringContaining("12,345.60 crore"));
    expect(within(answer).getByTitle("Unsupported figure")).toHaveTextContent("margins were 99%");
    expect(within(answer).getByText(/FinSight stored data/)).toBeInTheDocument();

    const ask = fetchMock.calls.find((c) => c.path === "/api/v1/research/ask");
    const init = fetchMock.mock.calls[fetchMock.calls.indexOf(ask!)]?.[1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({ question: "What was revenue?", ticker: "DEMOINFO", market: "IN" });
  });

  it("explains when the assistant is not configured", async () => {
    stubFetch({ ...COMPANY_PAGE, "/api/v1/research/status": () => jsonResponse({ configured: false, provider: null, model: null }) });
    renderRoute("/companies/DEMOINFO");
    expect(await screen.findByText(/AI assistant is not configured/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Research question")).not.toBeInTheDocument();
  });
});

describe("annual reports", () => {
  const DOC: DocumentOut = {
    id: "d1",
    title: "Annual Report FY26",
    doc_type: "annual_report",
    fiscal_year: 2026,
    filename: "ar.pdf",
    size_bytes: 1000,
    page_count: 4,
    pages_with_text: 4,
    status: "ready",
    company: { market: "IN", ticker: "DEMOINFO", name: "Demo Infotech Ltd" },
    facts: [
      { id: 1, metric: "Revenue", value: "12345.600000", unit: "crores", currency: "INR", period_label: "FY26", period_end: null, basis: "unspecified", page_number: 2, quote: "Revenue was Rs. 12,345.60 crore", status: "verified", verification_note: null, model: "claude-opus-5-5", extracted_at: "", kind: "extracted" },
      { id: 2, metric: "EBITDA", value: "4000", unit: "crores", currency: null, period_label: null, period_end: null, basis: "unspecified", page_number: 3, quote: "EBITDA 4,000", status: "unverified", verification_note: "quote not found on the cited page", model: "claude-opus-5-5", extracted_at: "", kind: "extracted" },
    ],
    created_at: "2026-10-18T10:00:00Z",
  };

  it("uploads a PDF as multipart and shows verified and unverified figures", async () => {
    let docs: DocumentOut[] = [];
    const fetchMock = stubFetch({
      "/api/v1/research/status": () => jsonResponse({ configured: true, provider: "anthropic", model: "claude-opus-5-5" }),
      "GET /api/v1/documents": () => jsonResponse(docs),
      "POST /api/v1/documents": () => {
        docs = [DOC];
        return jsonResponse(DOC, 201);
      },
    });
    renderRoute("/documents?ticker=DEMOINFO");
    expect(await screen.findByText(/No reports uploaded for DEMOINFO/)).toBeInTheDocument();
    const file = new File(["%PDF-1.4"], "ar.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByLabelText("PDF file"), file);
    await userEvent.type(screen.getByLabelText("Title"), "Annual Report FY26");
    await userEvent.click(screen.getByRole("button", { name: "Upload" }));

    const table = await screen.findByRole("table", { name: "Figures from Annual Report FY26" });
    expect(within(table).getByText("Verified on page")).toBeInTheDocument();
    expect(within(table).getByText("Unverified")).toBeInTheDocument();
    expect(within(table).getByText("12,345.6 ₹ crore")).toBeInTheDocument();

    const post = fetchMock.calls.find((c) => c.method === "POST" && c.path === "/api/v1/documents");
    expect(post?.headers.get("Content-Type")).toBeNull(); // browser sets the multipart boundary
    const body = fetchMock.mock.calls[fetchMock.calls.indexOf(post!)]?.[1]?.body as FormData;
    expect(body.get("ticker")).toBe("DEMOINFO");
    expect(body.get("title")).toBe("Annual Report FY26");
  });
});
