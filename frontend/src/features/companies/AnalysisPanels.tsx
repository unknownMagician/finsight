import { ErrorState, Loading, Panel, Unavailable } from "../../components/States";
import { fiscalLabel, formatCrores, formatINR, formatPercent, formatTimes, MISSING } from "../../lib/format";
import { useRatios, useValuationSnapshot } from "./api";
import { BASIS_LABEL } from "./FinancialsPanel";
import type { Exchange, MetricResult, ReportingBasis } from "./types";

const RATIO_ORDER = [
  "revenue_growth",
  "net_income_growth",
  "gross_margin",
  "operating_margin",
  "ebitda_margin",
  "net_margin",
  "return_on_equity",
  "return_on_capital_employed",
  "return_on_assets",
  "debt_to_equity",
  "interest_coverage",
  "current_ratio",
  "net_debt_to_ebitda",
  "free_cash_flow",
];

const VALUATION_ORDER = [
  "market_cap",
  "enterprise_value",
  "price_to_earnings",
  "price_to_book",
  "ev_to_ebitda",
  "ev_to_revenue",
  "dividend_yield",
];

function MetricValue({ metric, scale }: { metric: MetricResult; scale: string }) {
  if (metric.status !== "ok" || metric.value === null) {
    const why = metric.status === "missing_inputs" ? `missing: ${metric.missing.join(", ")}` : metric.note;
    return (
      <span className="text-slate-400" title={why ?? undefined}>
        {MISSING} <span className="text-xs">({metric.status === "missing_inputs" ? "missing inputs" : "not meaningful"})</span>
      </span>
    );
  }
  if (metric.unit === "ratio") return <>{formatPercent(metric.value)}</>;
  if (metric.unit === "times") return <>{formatTimes(metric.value)}</>;
  return <>{formatCrores(metric.value, scale)}</>;
}

function MetricTable({ metrics, order, scale }: { metrics: Record<string, MetricResult>; order: string[]; scale: string }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
      {order
        .filter((key) => metrics[key])
        .map((key) => {
          const metric = metrics[key] as MetricResult;
          return (
            <div key={key} className="flex justify-between gap-2 border-b border-slate-100 py-1">
              <dt className="text-slate-600" title={metric.formula}>
                {metric.name}
              </dt>
              <dd className="tabular-nums">
                <MetricValue metric={metric} scale={scale} />
              </dd>
            </div>
          );
        })}
    </dl>
  );
}

export function RatiosPanel({ ticker, basis, enabled }: { ticker: string; basis: ReportingBasis | null; enabled: boolean }) {
  const ratios = useRatios(ticker, basis, enabled);
  return (
    <Panel title="Ratios">
      {!enabled ? (
        <Unavailable>Ratios need stored annual statements.</Unavailable>
      ) : ratios.isPending ? (
        <Loading />
      ) : ratios.isError ? (
        <ErrorState error={ratios.error} />
      ) : (
        <>
          <p className="text-xs text-slate-500">
            {fiscalLabel(ratios.data.period.fiscal_year, "FY")} · {BASIS_LABEL[ratios.data.basis]} · calculated from
            reported figures (growth vs the prior year on the same basis)
          </p>
          <MetricTable metrics={ratios.data.metrics} order={RATIO_ORDER} scale={ratios.data.scale} />
        </>
      )}
    </Panel>
  );
}

export function ValuationPanel({
  ticker,
  exchange,
  basis,
  enabled,
}: {
  ticker: string;
  exchange: Exchange;
  basis: ReportingBasis | null;
  enabled: boolean;
}) {
  const snapshot = useValuationSnapshot(ticker, exchange, basis, enabled);
  return (
    <Panel title="Valuation multiples">
      {!enabled ? (
        <Unavailable>Valuation multiples need stored annual statements and a closing price.</Unavailable>
      ) : snapshot.isPending ? (
        <Loading />
      ) : snapshot.isError ? (
        <ErrorState error={snapshot.error} />
      ) : (
        <>
          <p className="text-xs text-slate-500">
            {exchange} close {formatINR(snapshot.data.report.price.price)} on {snapshot.data.report.price.price_date} ×{" "}
            {fiscalLabel(snapshot.data.report.period.fiscal_year, "FY")} {BASIS_LABEL[snapshot.data.basis].toLowerCase()}{" "}
            statements · calculated
          </p>
          {snapshot.data.report.issues.map((issue) => (
            <p key={issue.code} role="status" className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-900">
              {issue.message}
            </p>
          ))}
          <MetricTable metrics={snapshot.data.report.metrics} order={VALUATION_ORDER} scale={snapshot.data.report.scale} />
        </>
      )}
    </Panel>
  );
}
