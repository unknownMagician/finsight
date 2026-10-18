import { useState } from "react";

import { ProviderBadge } from "../../components/DataBadges";
import { ErrorState, Loading, Panel, Toggle, Unavailable } from "../../components/States";
import { fiscalLabel, formatCrores, formatDate, formatINR, formatNumber } from "../../lib/format";
import { useFinancials, useIngest } from "./api";
import type { PeriodOut, ReportingBasis } from "./types";

type PeriodType = "annual" | "quarterly";

const ROWS: { statement: string; item: string; label: string; kind?: "per_share" | "count" }[] = [
  { statement: "income", item: "revenue", label: "Revenue" },
  { statement: "income", item: "gross_profit", label: "Gross profit" },
  { statement: "income", item: "operating_income", label: "Operating profit (EBIT)" },
  { statement: "income", item: "depreciation_amortization", label: "Depreciation & amortisation" },
  { statement: "income", item: "interest_expense", label: "Finance costs" },
  { statement: "income", item: "pretax_income", label: "Profit before tax" },
  { statement: "income", item: "net_income", label: "Net profit" },
  { statement: "income", item: "diluted_eps", label: "Diluted EPS (₹)", kind: "per_share" },
  { statement: "balance", item: "total_assets", label: "Total assets" },
  { statement: "balance", item: "total_liabilities", label: "Total liabilities" },
  { statement: "balance", item: "total_equity", label: "Shareholders' equity" },
  { statement: "balance", item: "cash_and_equivalents", label: "Cash & equivalents" },
  { statement: "balance", item: "total_debt", label: "Total debt (reported)" },
  { statement: "balance", item: "shares_outstanding", label: "Shares outstanding", kind: "count" },
  { statement: "cash_flow", item: "operating_cash_flow", label: "Operating cash flow" },
  { statement: "cash_flow", item: "capital_expenditures", label: "Capital expenditure" },
  { statement: "cash_flow", item: "dividends_paid", label: "Dividends paid" },
];

export const BASIS_LABEL: Record<ReportingBasis, string> = {
  consolidated: "Consolidated",
  standalone: "Standalone",
  unspecified: "Basis not stated",
};

function cell(period: PeriodOut, statement: string, item: string, kind?: string): string {
  const line = period.line_items.find((i) => i.statement === statement && i.item === item);
  if (!line) return "—";
  if (kind === "per_share") return formatINR(line.value);
  if (kind === "count") return formatNumber(line.value, { maximumFractionDigits: 0 });
  return formatCrores(line.value, period.scale, period.currency);
}

export function FinancialsPanel({
  ticker,
  basis,
  onBasisChange,
}: {
  ticker: string;
  basis: ReportingBasis | null;
  onBasisChange: (basis: ReportingBasis) => void;
}) {
  const [periodType, setPeriodType] = useState<PeriodType>("annual");
  const financials = useFinancials(ticker, periodType, basis);
  const ingest = useIngest(ticker);
  const bases = financials.data?.available_bases ?? [];
  const effectiveBasis = basis ?? bases[0] ?? null;
  const periods = (financials.data?.periods ?? []).filter((p) => p.basis === effectiveBasis).slice(0, 6);
  const source = periods[0]?.source;

  return (
    <Panel
      title="Financial statements"
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <Toggle<PeriodType>
            label="Period"
            value={periodType}
            onChange={setPeriodType}
            options={[
              { value: "annual", label: "Annual" },
              { value: "quarterly", label: "Quarterly" },
            ]}
          />
          {bases.length > 0 && effectiveBasis ? (
            <Toggle<ReportingBasis>
              label="Reporting basis"
              value={effectiveBasis}
              onChange={onBasisChange}
              options={bases.map((b) => ({ value: b, label: BASIS_LABEL[b] }))}
            />
          ) : null}
          <button
            type="button"
            onClick={() => ingest.mutate()}
            disabled={ingest.isPending}
            className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100 disabled:opacity-50"
          >
            {ingest.isPending ? "Fetching…" : bases.length ? "Refresh statements" : "Fetch statements"}
          </button>
        </div>
      }
    >
      {ingest.isError ? <ErrorState error={ingest.error} /> : null}
      {ingest.data?.warnings.length ? (
        <ul className="list-disc pl-5 text-xs text-amber-800">
          {ingest.data.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      ) : null}
      {financials.isPending ? (
        <Loading />
      ) : financials.isError ? (
        <ErrorState error={financials.error} />
      ) : periods.length === 0 ? (
        <Unavailable>
          {bases.length === 0
            ? "No statements stored yet. Use “Fetch statements” to load them from the configured free provider."
            : `No ${periodType} ${effectiveBasis ?? ""} statements are available.`}
        </Unavailable>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-right text-sm">
              <thead>
                <tr className="text-xs text-slate-500">
                  <th className="py-1 text-left font-medium">₹ crore unless stated</th>
                  {periods.map((p) => (
                    <th key={`${p.fiscal_year}${p.fiscal_period}`} className="px-2 py-1 font-medium">
                      <div>{fiscalLabel(p.fiscal_year, p.fiscal_period)}</div>
                      <div className="font-normal">to {formatDate(p.period_end)}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {ROWS.map((row) => (
                  <tr key={`${row.statement}.${row.item}`}>
                    <th scope="row" className="py-1 text-left font-normal text-slate-600">
                      {row.label}
                    </th>
                    {periods.map((p) => (
                      <td key={`${p.fiscal_year}${p.fiscal_period}`} className="px-2 py-1 tabular-nums">
                        {cell(p, row.statement, row.item, row.kind)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            {source ? <ProviderBadge provider={source.provider} /> : null}
            <span>
              {effectiveBasis ? BASIS_LABEL[effectiveBasis] : ""} · reported figures · retrieved{" "}
              {formatDate(source?.retrieved_at)} · “—” means not reported by the source (never zero)
            </span>
          </div>
        </>
      )}
    </Panel>
  );
}
