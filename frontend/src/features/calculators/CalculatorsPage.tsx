import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { Toggle } from "../../components/States";
import { addDecimal, shiftDecimal, subtractDecimal } from "../../lib/decimal";
import { fiscalLabel } from "../../lib/format";
import { useFinancials } from "../companies/api";
import type { PeriodOut } from "../companies/types";
import { CompsCalculator } from "./CompsCalculator";
import { DcfCalculator, EMPTY_DCF, type DcfDraft } from "./DcfCalculator";
import { ForecastCalculator } from "./ForecastCalculator";
import { WaccCalculator } from "./WaccCalculator";

type Tab = "dcf" | "wacc" | "forecast" | "comps";

const SCALE_EXPONENT: Record<string, number> = { units: 0, thousands: 3, lakhs: 5, millions: 6, crores: 7, billions: 9 };

/** Balance-sheet inputs for the DCF bridge from one reported period, converted to ₹ crore. */
export function bridgeFromPeriod(period: PeriodOut): { values: Partial<DcfDraft>; missing: string[] } {
  const exponent = SCALE_EXPONENT[period.scale];
  const get = (item: string) => period.line_items.find((i) => i.statement === "balance" && i.item === item)?.value;
  const toCr = (v: string) => (exponent === undefined ? null : shiftDecimal(v, exponent - 7));
  const missing: string[] = [];
  let debt = get("total_debt");
  if (!debt) {
    const st = get("short_term_debt");
    const lt = get("long_term_debt");
    debt = st && lt ? addDecimal(st, lt) : undefined;
  }
  const cash = get("cash_and_equivalents");
  const out: Partial<DcfDraft> = {};
  if (debt && cash) out.netDebt = toCr(subtractDecimal(debt, cash)) ?? "";
  else missing.push("net debt (total debt or cash not reported)");
  const claims = [get("minority_interest"), get("preferred_equity")].filter((v): v is string => !!v);
  out.otherClaims = toCr(claims.reduce(addDecimal, "0")) ?? "0";
  const shares = get("shares_outstanding");
  if (shares) out.shares = shares;
  else missing.push("shares outstanding");
  return { values: out, missing };
}

export function CalculatorsPage() {
  const [params] = useSearchParams();
  const ticker = params.get("ticker");
  const [tab, setTab] = useState<Tab>("dcf");
  const [draft, setDraft] = useState<DcfDraft>(EMPTY_DCF);
  const annual = useFinancials(ticker ?? "", "annual", null);
  const latest = ticker ? annual.data?.periods[0] : undefined;

  // Prefill once per source period (state adjusted during render, not in an effect).
  const sourceKey = latest ? `${ticker}:${latest.fiscal_year}:${latest.basis}` : null;
  const [prefilledKey, setPrefilledKey] = useState<string | null>(null);
  const bridge = latest ? bridgeFromPeriod(latest) : null;
  if (bridge && sourceKey !== prefilledKey) {
    setPrefilledKey(sourceKey);
    setDraft((d) => ({ ...d, ...bridge.values }));
  }
  const prefillNote =
    latest && bridge
      ? `Net debt, other claims and shares were prefilled from ${ticker}'s ${fiscalLabel(latest.fiscal_year, "FY")} ` +
        `${latest.basis} statements (reported, source ${latest.source.provider}); edit freely.` +
        (bridge.missing.length ? ` Not available: ${bridge.missing.join(", ")}.` : "")
      : null;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Valuation calculators</h1>
        {ticker ? (
          <p className="text-sm text-slate-600">
            For <Link to={`/companies/${encodeURIComponent(ticker)}`} className="text-sky-700 underline">{ticker}</Link>
          </p>
        ) : null}
      </div>
      <Toggle<Tab>
        label="Calculator"
        value={tab}
        onChange={setTab}
        options={[
          { value: "dcf", label: "DCF" },
          { value: "wacc", label: "WACC" },
          { value: "forecast", label: "Forecast" },
          { value: "comps", label: "Comparables" },
        ]}
      />
      {tab === "dcf" ? <DcfCalculator draft={draft} setDraft={setDraft} ticker={ticker} prefillNote={prefillNote} /> : null}
      {tab === "wacc" ? (
        <WaccCalculator
          onUse={(wacc) => {
            setDraft((d) => ({ ...d, wacc }));
            setTab("dcf");
          }}
        />
      ) : null}
      {tab === "forecast" ? (
        <ForecastCalculator
          onUseFcf={(fcf) => {
            setDraft((d) => ({ ...d, fcf: fcf.join(", ") }));
            setTab("dcf");
          }}
        />
      ) : null}
      {tab === "comps" ? <CompsCalculator /> : null}
    </div>
  );
}
