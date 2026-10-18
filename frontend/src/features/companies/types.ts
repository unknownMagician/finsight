/** Mirrors of backend/app/schemas.py (companies, market data) and domain report models. */

export type Market = "IN" | "US";
export type Exchange = "NSE" | "BSE";
export type ReportingBasis = "consolidated" | "standalone" | "unspecified";
export type DataNature = "end_of_day" | "delayed" | "live" | "demo";

export interface InstrumentOut {
  exchange: Exchange;
  symbol: string;
  isin: string | null;
  series: string | null;
  name: string;
  currency: string;
  listing_status: "active" | "not_in_latest_snapshot" | string;
  provider: string;
  last_traded_on: string | null;
  former_symbols: string[];
  retrieved_at: string;
}

export interface CompanyOut {
  market: Market;
  ticker: string;
  name: string;
  isin: string | null;
  cik: string | null;
  exchange: string | null;
  last_ingested_at: string | null;
  instruments: InstrumentOut[];
}

export interface FreshnessOut {
  provider: string;
  nature: DataNature;
  as_of: string | null;
  retrieved_at: string;
  cached: boolean;
  stale: boolean;
  adjusted: boolean | null;
  source_url: string | null;
}

export interface PriceBarOut {
  date: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: number | null;
  prev_close: string | null;
}

export interface PriceHistoryOut {
  ticker: string;
  listing: InstrumentOut;
  currency: string;
  bars: PriceBarOut[];
  freshness: FreshnessOut;
  warnings: string[];
}

export interface QuoteOut {
  ticker: string;
  listing: InstrumentOut;
  currency: string;
  trade_date: string;
  open: string;
  high: string;
  low: string;
  close: string;
  prev_close: string | null;
  change: string | null;
  change_pct: string | null;
  volume: number | null;
  freshness: FreshnessOut;
}

export interface LineItemOut {
  statement: "income" | "balance" | "cash_flow";
  item: string;
  value: string;
  source_concept: string | null;
  source_accession: string | null;
}

export interface SourceOut {
  provider: string;
  url: string | null;
  retrieved_at: string;
}

export interface PeriodOut {
  fiscal_year: number;
  fiscal_period: string;
  basis: ReportingBasis;
  period_start: string | null;
  period_end: string;
  currency: string;
  scale: string;
  kind: string;
  source: SourceOut;
  line_items: LineItemOut[];
}

export interface FinancialsOut {
  company: CompanyOut;
  available_bases: ReportingBasis[];
  periods: PeriodOut[];
}

export interface IngestOut {
  company: CompanyOut;
  provider: string;
  periods_ingested: number;
  fiscal_years: number[];
  warnings: string[];
}

export type MetricStatus = "ok" | "missing_inputs" | "not_meaningful";

export interface MetricResult {
  name: string;
  value: string | null;
  unit: "ratio" | "times" | "currency";
  kind: string;
  formula: string;
  inputs: Record<string, string | null>;
  status: MetricStatus;
  missing: string[];
  note: string | null;
}

export interface ReportingPeriod {
  fiscal_year: number;
  fiscal_period: string;
  period_start: string | null;
  period_end: string;
}

export interface RatioReport {
  company: string;
  period: ReportingPeriod;
  currency: string;
  scale: string;
  basis: ReportingBasis;
  metrics: Record<string, MetricResult>;
}

export interface Issue {
  code: string;
  severity: "info" | "warning";
  message: string;
}

export interface MarketMultiplesReport {
  company: string;
  period: ReportingPeriod;
  price: { price: string; price_date: string; currency: string; source: string };
  currency: string;
  scale: string;
  metrics: Record<string, MetricResult>;
  issues: Issue[];
}

export interface ValuationSnapshotOut {
  ticker: string;
  listing: InstrumentOut;
  basis: ReportingBasis;
  period_source: SourceOut;
  quote: QuoteOut;
  report: MarketMultiplesReport;
}

export interface CorporateActionOut {
  exchange: Exchange;
  symbol: string;
  isin: string | null;
  ex_date: string;
  record_date: string | null;
  action_type: string;
  ratio_numerator: number | null;
  ratio_denominator: number | null;
  cash_amount: string | null;
  description: string;
}

export interface CorporateActionsOut {
  ticker: string;
  provider: string;
  retrieved_at: string;
  cached: boolean;
  source_urls: string[];
  actions: CorporateActionOut[];
}

export interface ProviderInfoOut {
  role: string;
  name: string | null;
  configured: boolean;
  capabilities: string[];
  data_nature: string | null;
  usage_terms: string;
}

export interface MarketStatusOut {
  default_market: Market;
  providers: ProviderInfoOut[];
  reachable: boolean;
  latest_trading_date: string | null;
  published_at: string | null;
  unavailable_capabilities: string[];
}
