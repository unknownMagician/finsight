/** Mirrors of backend/app/domain/{wacc,dcf,forecast,comps}.py and schemas.py (valuations).
 * Decimal fields travel as strings in both directions. */

import type { Issue } from "../companies/types";

export type Scale = "units" | "thousands" | "lakhs" | "millions" | "crores" | "billions";

export interface WACCInputs {
  risk_free_rate: string;
  equity_risk_premium: string;
  beta: string;
  size_premium: string;
  pre_tax_cost_of_debt: string;
  tax_rate: string;
  equity_value: string;
  debt_value: string;
}

export interface WACCResult {
  cost_of_equity: string;
  after_tax_cost_of_debt: string;
  equity_weight: string;
  debt_weight: string;
  wacc: string;
  warnings: Issue[];
}

export type TerminalMethod = "perpetuity_growth" | "exit_multiple";

export interface DCFInputs {
  currency: string;
  scale: Scale;
  free_cash_flows: string[];
  wacc: string;
  terminal_method: TerminalMethod;
  terminal_growth?: string | null;
  exit_multiple?: string | null;
  terminal_ebitda?: string | null;
  mid_year_convention: boolean;
  net_debt: string;
  other_claims: string;
  shares_outstanding: string;
}

export interface DCFYear {
  year: number;
  free_cash_flow: string;
  discount_period: string;
  discount_factor: string;
  present_value: string;
}

export interface DCFResult {
  currency: string;
  scale: Scale;
  terminal_method: TerminalMethod;
  years: DCFYear[];
  sum_pv_fcf: string;
  terminal_value: string;
  pv_terminal_value: string;
  enterprise_value: string;
  equity_value: string;
  value_per_share: string | null;
  terminal_value_share: string;
  implied_exit_multiple: string | null;
  implied_terminal_growth: string | null;
  warnings: Issue[];
}

export interface SensitivityTable {
  output: "value_per_share" | "enterprise_value" | "equity_value";
  row_axis: "wacc";
  column_axis: "terminal_growth" | "exit_multiple";
  row_values: string[];
  column_values: string[];
  cells: (string | null)[][];
  invalid_reasons: Record<string, string>;
}

export type ScenarioName = "bull" | "base" | "bear";

export interface ForecastAssumptions {
  revenue_growth: string[];
  ebit_margin: string[];
  tax_rate: string;
  da_pct_revenue: string;
  capex_pct_revenue: string;
  nwc_pct_revenue: string;
}

export interface ForecastBase {
  base_year: number;
  base_revenue: string;
  base_nwc?: string | null;
  currency: string;
  scale: Scale;
}

export interface ForecastYear {
  year: number;
  revenue: string;
  ebit: string;
  taxes: string;
  nopat: string;
  d_and_a: string;
  capex: string;
  nwc: string;
  change_in_nwc: string;
  free_cash_flow: string;
}

export interface ForecastResult {
  scenario: ScenarioName;
  currency: string;
  scale: Scale;
  kind: string;
  years: ForecastYear[];
  notes: string[];
}

export interface ScenarioSetResult {
  scenarios: Partial<Record<ScenarioName, ForecastResult>>;
  warnings: Issue[];
}

export type Multiple = "ev_revenue" | "ev_ebitda" | "price_earnings" | "price_book";

export interface CompanyMetrics {
  company: string;
  currency: string;
  scale: Scale;
  market_cap: string;
  enterprise_value?: string | null;
  net_debt?: string | null;
  other_claims?: string;
  revenue?: string | null;
  ebitda?: string | null;
  net_income?: string | null;
  book_equity?: string | null;
  shares_outstanding?: string | null;
}

export interface MultipleStats {
  multiple: Multiple;
  values: Record<string, string>;
  excluded: Record<string, string>;
  count: number;
  minimum: string | null;
  median: string | null;
  mean: string | null;
  maximum: string | null;
}

export interface ImpliedValuation {
  multiple: Multiple;
  target_metric: string | null;
  implied_enterprise_value: string | null;
  implied_equity_value: string | null;
  implied_value_per_share: string | null;
  low_value_per_share: string | null;
  high_value_per_share: string | null;
  note: string | null;
}

export interface CompsResult {
  target: string;
  currency: string;
  scale: Scale;
  stats: Partial<Record<Multiple, MultipleStats>>;
  implied: Partial<Record<Multiple, ImpliedValuation>>;
  warnings: Issue[];
}

export interface SavedValuationOut {
  id: string;
  name: string;
  ticker: string | null;
  market: string | null;
  method: string;
  engine_version: string;
  inputs: DCFInputs;
  result: DCFResult;
  created_at: string;
}
