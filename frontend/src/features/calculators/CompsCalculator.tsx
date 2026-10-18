import { useState } from "react";

import { Field } from "../../components/Form";
import { ErrorState, Panel } from "../../components/States";
import { apiFetch, query } from "../../lib/api";
import { addDecimal, shiftDecimal, subtractDecimal } from "../../lib/decimal";
import { formatINR, formatNumber, formatTimes } from "../../lib/format";
import type { ValuationSnapshotOut } from "../companies/types";
import { useComps } from "./api";
import type { CompanyMetrics, Multiple } from "./types";

const SCALE_EXPONENT: Record<string, number> = { units: 0, thousands: 3, lakhs: 5, millions: 6, crores: 7, billions: 9 };

const MULTIPLE_LABEL: Record<Multiple, string> = {
  ev_revenue: "EV/Revenue",
  ev_ebitda: "EV/EBITDA",
  price_earnings: "P/E",
  price_book: "P/B",
};

/** Build comps metrics from FinSight's valuation snapshot (reported statements + EOD close). */
export function metricsFromSnapshot(s: ValuationSnapshotOut): CompanyMetrics | string {
  const m = s.report.metrics;
  const value = (key: string) => (m[key]?.status === "ok" ? m[key]?.value ?? null : null);
  const marketCap = value("market_cap");
  if (!marketCap) return `${s.ticker}: market cap not available (${m.market_cap?.note ?? "missing inputs"})`;
  const ev = value("enterprise_value");
  const inputs = m.enterprise_value?.inputs ?? {};
  const debt = inputs.total_debt ?? null;
  const cash = inputs.cash_and_equivalents ?? null;
  const ebitdaInputs = m.ev_to_ebitda?.inputs ?? {};
  const peInputs = m.price_to_book?.inputs ?? {};
  const claims = [inputs.minority_interest, inputs.preferred_equity].filter((v): v is string => !!v);
  const shares = m.market_cap?.inputs.shares_outstanding ?? null;
  const exponent = SCALE_EXPONENT[s.report.scale];
  return {
    company: s.ticker,
    currency: s.report.currency,
    scale: s.report.scale as CompanyMetrics["scale"],
    market_cap: marketCap,
    enterprise_value: ev,
    net_debt: debt && cash ? subtractDecimal(debt, cash) : null,
    other_claims: claims.reduce(addDecimal, "0"),
    // Share counts are absolute; comps divides amounts by shares, so express them in the scale.
    shares_outstanding: shares && exponent !== undefined ? shiftDecimal(shares, -exponent) : null,
    revenue: m.ev_to_revenue?.inputs.revenue ?? null,
    ebitda: ebitdaInputs.ebitda ?? null,
    book_equity: peInputs.total_equity ?? null,
    net_income: null, // P/E here comes from price ÷ EPS; net income is not in the snapshot
  };
}

export function CompsCalculator() {
  const [ticker, setTicker] = useState("");
  const [exchange, setExchange] = useState<"NSE" | "BSE">("NSE");
  const [target, setTarget] = useState<CompanyMetrics | null>(null);
  const [peers, setPeers] = useState<CompanyMetrics[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const comps = useComps();

  async function add(as: "target" | "peer") {
    setError(null);
    setLoading(true);
    try {
      const snap = await apiFetch<ValuationSnapshotOut>(
        `/companies/${encodeURIComponent(ticker.trim().toUpperCase())}/valuation-snapshot${query({ exchange })}`,
      );
      const metrics = metricsFromSnapshot(snap);
      if (typeof metrics === "string") setError(metrics);
      else if (as === "target") setTarget(metrics);
      else setPeers((p) => [...p.filter((x) => x.company !== metrics.company), metrics]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the company");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Panel title="Comparable companies">
      <p className="text-xs text-slate-500">
        Add companies by ticker. Metrics come from each company's stored statements and latest end-of-day close
        (fetch statements on its research page first). Multiples are calculated, not reported.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Ticker" value={ticker} onChange={setTicker} />
        <select
          aria-label="Exchange for comps"
          value={exchange}
          onChange={(e) => setExchange(e.target.value as "NSE" | "BSE")}
          className="rounded border border-slate-300 px-2 py-1 text-sm"
        >
          <option value="NSE">NSE</option>
          <option value="BSE">BSE</option>
        </select>
        <button type="button" disabled={loading || !ticker} onClick={() => add("target")} className="rounded border border-slate-300 px-2 py-1 text-sm">
          Set as target
        </button>
        <button type="button" disabled={loading || !ticker} onClick={() => add("peer")} className="rounded border border-slate-300 px-2 py-1 text-sm">
          Add peer
        </button>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-rose-700">
          {error}
        </p>
      ) : null}
      <p className="text-sm">
        Target: <strong>{target?.company ?? "—"}</strong> · Peers: {peers.map((p) => p.company).join(", ") || "—"}
      </p>
      <button
        type="button"
        disabled={!target || peers.length === 0 || comps.isPending}
        onClick={() => target && comps.mutate({ target, peers, multiples: ["ev_revenue", "ev_ebitda", "price_book"] })}
        className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        Run comparables
      </button>
      {comps.isError ? <ErrorState error={comps.error} /> : null}
      {comps.data ? (
        <table className="w-full text-right text-sm" aria-label="Comparables result">
          <thead>
            <tr className="text-xs text-slate-500">
              <th className="text-left font-medium">Multiple</th>
              <th className="font-medium">Peers used</th>
              <th className="font-medium">Median</th>
              <th className="font-medium">Implied value / share</th>
              <th className="text-left font-medium">Notes</th>
            </tr>
          </thead>
          <tbody>
            {(Object.keys(comps.data.stats) as Multiple[]).map((key) => {
              const stats = comps.data.stats[key];
              const implied = comps.data.implied[key];
              return (
                <tr key={key}>
                  <td className="text-left">{MULTIPLE_LABEL[key]}</td>
                  <td>{formatNumber(stats?.count)}</td>
                  <td>{formatTimes(stats?.median)}</td>
                  <td>{formatINR(implied?.implied_value_per_share)}</td>
                  <td className="text-left text-xs text-slate-500">
                    {[implied?.note, ...Object.entries(stats?.excluded ?? {}).map(([p, r]) => `${p}: ${r}`)]
                      .filter(Boolean)
                      .join("; ")}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}
    </Panel>
  );
}
