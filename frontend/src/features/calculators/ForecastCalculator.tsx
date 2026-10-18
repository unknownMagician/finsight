import { useState, type FormEvent } from "react";

import { Field, IssueList, SubmitButton } from "../../components/Form";
import { ErrorState, Panel } from "../../components/States";
import { parseDecimal, parseDecimalList, percentToFraction } from "../../lib/decimal";
import { formatNumber } from "../../lib/format";
import { useForecast } from "./api";
import type { ForecastAssumptions, ScenarioName } from "./types";

interface ScenarioDraft {
  growth: string;
  margin: string;
}

const SCENARIOS: ScenarioName[] = ["bear", "base", "bull"];

export function ForecastCalculator({ onUseFcf }: { onUseFcf: (fcf: string[]) => void }) {
  const [baseYear, setBaseYear] = useState("");
  const [baseRevenue, setBaseRevenue] = useState("");
  const [shared, setShared] = useState({ tax: "", da: "", capex: "", nwc: "" });
  const [drafts, setDrafts] = useState<Record<ScenarioName, ScenarioDraft>>({
    bear: { growth: "", margin: "" },
    base: { growth: "", margin: "" },
    bull: { growth: "", margin: "" },
  });
  const [error, setError] = useState<string | null>(null);
  const forecast = useForecast();

  function submit(event: FormEvent) {
    event.preventDefault();
    const year = Number(baseYear);
    const revenue = parseDecimal(baseRevenue);
    const tax = percentToFraction(shared.tax);
    const da = percentToFraction(shared.da);
    const capex = percentToFraction(shared.capex);
    const nwc = percentToFraction(shared.nwc);
    if (!Number.isInteger(year) || !revenue || !tax || !da || !capex || !nwc) {
      setError("Fill in the base year, base revenue and all shared assumptions.");
      return;
    }
    const scenarios: Partial<Record<ScenarioName, ForecastAssumptions>> = {};
    for (const name of SCENARIOS) {
      const d = drafts[name];
      if (!d.growth.trim() && !d.margin.trim() && name !== "base") continue;
      const growth = parseDecimalList(d.growth, { percent: true });
      const margin = parseDecimalList(d.margin, { percent: true });
      if (!growth || !margin) {
        setError(`Enter growth and EBIT margin (%) per year for the ${name} case.`);
        return;
      }
      scenarios[name] = {
        revenue_growth: growth,
        ebit_margin: margin,
        tax_rate: tax,
        da_pct_revenue: da,
        capex_pct_revenue: capex,
        nwc_pct_revenue: nwc,
      };
    }
    setError(null);
    forecast.mutate({ base: { base_year: year, base_revenue: revenue, currency: "INR", scale: "crores" }, scenarios });
  }

  const base = forecast.data?.scenarios.base;

  return (
    <Panel title="Scenario forecast (bear / base / bull)">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-xs text-slate-500">Outputs are forecasts derived only from the assumptions you enter (₹ crore).</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Base fiscal year" value={baseYear} onChange={setBaseYear} hint="e.g. 2026 for FY26" />
          <Field label="Base-year revenue (₹ Cr)" value={baseRevenue} onChange={setBaseRevenue} />
        </div>
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Tax rate" suffix="%" value={shared.tax} onChange={(v) => setShared({ ...shared, tax: v })} />
          <Field label="D&A % revenue" suffix="%" value={shared.da} onChange={(v) => setShared({ ...shared, da: v })} />
          <Field label="Capex % revenue" suffix="%" value={shared.capex} onChange={(v) => setShared({ ...shared, capex: v })} />
          <Field label="NWC % revenue" suffix="%" value={shared.nwc} onChange={(v) => setShared({ ...shared, nwc: v })} />
        </div>
        {SCENARIOS.map((name) => (
          <div key={name} className="grid gap-3 sm:grid-cols-2">
            <Field
              label={`${name[0]?.toUpperCase()}${name.slice(1)}: revenue growth by year (%)`}
              value={drafts[name].growth}
              onChange={(v) => setDrafts({ ...drafts, [name]: { ...drafts[name], growth: v } })}
              hint={name === "base" ? "Required, e.g. 12 11 10" : "Optional"}
            />
            <Field
              label={`${name[0]?.toUpperCase()}${name.slice(1)}: EBIT margin by year (%)`}
              value={drafts[name].margin}
              onChange={(v) => setDrafts({ ...drafts, [name]: { ...drafts[name], margin: v } })}
            />
          </div>
        ))}
        {error ? (
          <p role="alert" className="text-sm text-rose-700">
            {error}
          </p>
        ) : null}
        <SubmitButton pending={forecast.isPending}>Run forecast</SubmitButton>
      </form>
      {forecast.isError ? <ErrorState error={forecast.error} /> : null}
      {forecast.data ? (
        <div className="space-y-3 border-t border-slate-100 pt-3">
          <IssueList issues={forecast.data.warnings} />
          {SCENARIOS.filter((n) => forecast.data.scenarios[n]).map((name) => (
            <table key={name} className="w-full text-right text-xs" aria-label={`${name} forecast`}>
              <caption className="text-left text-xs font-semibold capitalize text-slate-600">{name} case (forecast)</caption>
              <thead>
                <tr className="text-slate-500">
                  <th className="text-left font-medium">Year</th>
                  <th className="font-medium">Revenue</th>
                  <th className="font-medium">EBIT</th>
                  <th className="font-medium">FCF</th>
                </tr>
              </thead>
              <tbody>
                {forecast.data.scenarios[name]?.years.map((y) => (
                  <tr key={y.year}>
                    <td className="text-left">FY{String(y.year).slice(-2)}</td>
                    <td>{formatNumber(y.revenue)}</td>
                    <td>{formatNumber(y.ebit)}</td>
                    <td>{formatNumber(y.free_cash_flow)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
          {base ? (
            <button
              type="button"
              className="rounded border border-slate-300 px-2 py-1 text-xs"
              onClick={() => onUseFcf(base.years.map((y) => y.free_cash_flow))}
            >
              Use base-case FCF in DCF
            </button>
          ) : null}
        </div>
      ) : null}
    </Panel>
  );
}
