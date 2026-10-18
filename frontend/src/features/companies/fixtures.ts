/** Test fixtures shaped like the backend's demo-provider responses. */
import type { CompanyOut, FinancialsOut, InstrumentOut, QuoteOut } from "./types";

export function instrument(exchange: "NSE" | "BSE", symbol = "DEMOINFO"): InstrumentOut {
  return {
    exchange,
    symbol,
    isin: null,
    series: exchange === "NSE" ? "EQ" : "A",
    name: "Demo Infotech Ltd",
    currency: "INR",
    listing_status: "active",
    provider: "demo",
    last_traded_on: "2026-10-16",
    former_symbols: [],
    retrieved_at: "2026-10-16T13:00:00Z",
  };
}

export const DEMOINFO: CompanyOut = {
  market: "IN",
  ticker: "DEMOINFO",
  name: "Demo Infotech Ltd",
  isin: null,
  cik: null,
  exchange: null,
  last_ingested_at: null,
  instruments: [instrument("BSE"), instrument("NSE")],
};

export function quote(exchange: "NSE" | "BSE", close: string, stale = false): QuoteOut {
  return {
    ticker: "DEMOINFO",
    listing: instrument(exchange),
    currency: "INR",
    trade_date: "2026-10-16",
    open: "1993.60",
    high: "2000.75",
    low: "1960.75",
    close,
    prev_close: "1993.60",
    change: String(Number(close) - 1993.6),
    change_pct: "-0.0129",
    volume: 1842237,
    freshness: {
      provider: "demo",
      nature: "demo",
      as_of: "2026-10-16",
      retrieved_at: "2026-10-16T13:00:00Z",
      cached: false,
      stale,
      adjusted: false,
      source_url: null,
    },
  };
}

export const NO_FINANCIALS: FinancialsOut = { company: DEMOINFO, available_bases: [], periods: [] };

export const FINANCIALS: FinancialsOut = {
  company: DEMOINFO,
  available_bases: ["consolidated", "standalone"],
  periods: (["consolidated", "standalone"] as const).map((basis) => ({
    fiscal_year: 2026,
    fiscal_period: "FY",
    basis,
    period_start: null,
    period_end: "2026-03-31",
    currency: "INR",
    scale: "crores",
    kind: "reported",
    source: { provider: "demo", url: "demo://synthetic", retrieved_at: "2026-10-16T13:00:00Z" },
    line_items: [
      {
        statement: "income",
        item: "revenue",
        value: basis === "consolidated" ? "123456.78" : "8400.00",
        source_concept: "demo:revenue",
        source_accession: null,
      },
      { statement: "income", item: "diluted_eps", value: "54.00", source_concept: "demo:diluted_eps", source_accession: null },
    ],
  })),
};
