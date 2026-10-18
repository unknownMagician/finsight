import { useState, type FormEvent } from "react";

import { Field, IssueList, SubmitButton } from "../../components/Form";
import { ErrorState, Panel, Toggle } from "../../components/States";
import { parseDecimal, parseDecimalList, percentToFraction, shiftDecimal } from "../../lib/decimal";
import { formatCrores, formatINR, formatNumber, formatPercent } from "../../lib/format";
import { useDcf, useSaveValuation, useSensitivity } from "./api";
import type { DCFInputs, TerminalMethod } from "./types";

export interface DcfDraft {
  fcf: string;
  wacc: string; // percent
  method: TerminalMethod;
  growth: string; // percent
  exitMultiple: string;
  terminalEbitda: string;
  midYear: boolean;
  netDebt: string;
  otherClaims: string;
  shares: string;
}

export const EMPTY_DCF: DcfDraft = {
  fcf: "",
  wacc: "",
  method: "perpetuity_growth",
  growth: "",
  exitMultiple: "",
  terminalEbitda: "",
  midYear: false,
  netDebt: "",
  otherClaims: "0",
  shares: "",
};

/** Build validated DCF inputs (₹ crore) from the form; returns an error message instead. */
export function buildDcfInputs(d: DcfDraft): DCFInputs | string {
  const fcf = parseDecimalList(d.fcf);
  if (!fcf) return "Enter free cash flows as numbers separated by commas or spaces.";
  const wacc = percentToFraction(d.wacc);
  if (!wacc) return "Enter WACC as a percentage.";
  const netDebt = parseDecimal(d.netDebt);
  if (netDebt === null) return "Enter net debt (negative for net cash).";
  const otherClaims = parseDecimal(d.otherClaims || "0");
  if (otherClaims === null) return "Other claims must be a number.";
  const shares = parseDecimal(d.shares);
  if (!shares) return "Enter shares outstanding (absolute count).";
  const base: DCFInputs = {
    currency: "INR",
    scale: "crores",
    free_cash_flows: fcf,
    wacc,
    terminal_method: d.method,
    mid_year_convention: d.midYear,
    net_debt: netDebt,
    other_claims: otherClaims,
    // Amounts are in ₹ crore, so express the share count in crores too (value per share in ₹).
    shares_outstanding: shiftDecimal(shares, -7),
  };
  if (d.method === "perpetuity_growth") {
    const g = percentToFraction(d.growth);
    if (!g) return "Enter terminal growth as a percentage.";
    return { ...base, terminal_growth: g };
  }
  const multiple = parseDecimal(d.exitMultiple);
  const ebitda = parseDecimal(d.terminalEbitda);
  if (!multiple || !ebitda) return "Enter the exit multiple and terminal-year EBITDA.";
  return { ...base, exit_multiple: multiple, terminal_ebitda: ebitda };
}

function axis(center: string, step: string): string[] {
  const c = Number(center);
  const s = Number(step);
  return [-2, -1, 0, 1, 2].map((k) => (c + k * s).toFixed(6).replace(/\.?0+$/, ""));
}

export function DcfCalculator({
  draft,
  setDraft,
  ticker,
  prefillNote,
}: {
  draft: DcfDraft;
  setDraft: (d: DcfDraft) => void;
  ticker: string | null;
  prefillNote: string | null;
}) {
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const dcf = useDcf();
  const grid = useSensitivity();
  const save = useSaveValuation();
  const set = (patch: Partial<DcfDraft>) => setDraft({ ...draft, ...patch });

  function submit(event: FormEvent) {
    event.preventDefault();
    const inputs = buildDcfInputs(draft);
    if (typeof inputs === "string") {
      setError(inputs);
      return;
    }
    setError(null);
    dcf.mutate(inputs);
    const columnValues =
      inputs.terminal_method === "perpetuity_growth"
        ? axis(inputs.terminal_growth as string, "0.005")
        : axis(inputs.exit_multiple as string, "1");
    grid.mutate({ inputs, wacc_values: axis(inputs.wacc, "0.01"), column_values: columnValues });
  }

  const inputs = buildDcfInputs(draft);
  const result = dcf.data;

  return (
    <Panel title="Discounted cash flow (FCFF)">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-xs text-slate-500">
          All amounts in ₹ crore. Every input is your <strong>assumption</strong>; FinSight does not supply a
          default WACC, growth rate or tax rate.
          {prefillNote ? ` ${prefillNote}` : ""}
        </p>
        <Field label="Free cash flow by year (₹ Cr)" value={draft.fcf} onChange={(v) => set({ fcf: v })} hint="e.g. 1200, 1350, 1500" />
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="WACC" suffix="%" value={draft.wacc} onChange={(v) => set({ wacc: v })} />
          <div className="text-sm">
            <span className="text-slate-600">Terminal value</span>
            <div className="mt-1">
              <Toggle<TerminalMethod>
                label="Terminal method"
                value={draft.method}
                onChange={(m) => set({ method: m })}
                options={[
                  { value: "perpetuity_growth", label: "Perpetuity growth" },
                  { value: "exit_multiple", label: "Exit multiple" },
                ]}
              />
            </div>
          </div>
          {draft.method === "perpetuity_growth" ? (
            <Field label="Terminal growth" suffix="%" value={draft.growth} onChange={(v) => set({ growth: v })} hint="Must be below WACC" />
          ) : (
            <>
              <Field label="Exit EV/EBITDA" suffix="×" value={draft.exitMultiple} onChange={(v) => set({ exitMultiple: v })} />
              <Field label="Terminal-year EBITDA (₹ Cr)" value={draft.terminalEbitda} onChange={(v) => set({ terminalEbitda: v })} />
            </>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Net debt (₹ Cr)" value={draft.netDebt} onChange={(v) => set({ netDebt: v })} hint="Negative = net cash" />
          <Field label="Minority + preferred (₹ Cr)" value={draft.otherClaims} onChange={(v) => set({ otherClaims: v })} />
          <Field label="Shares outstanding (count)" value={draft.shares} onChange={(v) => set({ shares: v })} />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={draft.midYear} onChange={(e) => set({ midYear: e.target.checked })} />
          Mid-year discounting convention
        </label>
        {error ? (
          <p role="alert" className="text-sm text-rose-700">
            {error}
          </p>
        ) : null}
        <SubmitButton pending={dcf.isPending}>Run DCF</SubmitButton>
      </form>

      {dcf.isError ? <ErrorState error={dcf.error} /> : null}
      {result ? (
        <div className="space-y-3 border-t border-slate-100 pt-3" aria-label="DCF result">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
            <dt className="text-slate-500">Enterprise value</dt>
            <dd data-testid="dcf-ev">{formatCrores(result.enterprise_value, result.scale)}</dd>
            <dt className="text-slate-500">Equity value</dt>
            <dd>{formatCrores(result.equity_value, result.scale)}</dd>
            <dt className="text-slate-500">Value per share</dt>
            <dd data-testid="dcf-per-share">{formatINR(result.value_per_share)}</dd>
            <dt className="text-slate-500">Terminal value share of EV</dt>
            <dd>{formatPercent(result.terminal_value_share)}</dd>
          </dl>
          <IssueList issues={result.warnings} />
          <table className="w-full text-right text-xs">
            <thead>
              <tr className="text-slate-500">
                <th className="text-left font-medium">Year</th>
                <th className="font-medium">FCF</th>
                <th className="font-medium">Discount factor</th>
                <th className="font-medium">Present value</th>
              </tr>
            </thead>
            <tbody>
              {result.years.map((y) => (
                <tr key={y.year}>
                  <td className="text-left">{y.year}</td>
                  <td>{formatNumber(y.free_cash_flow)}</td>
                  <td>{formatNumber(y.discount_factor, { maximumFractionDigits: 4 })}</td>
                  <td>{formatNumber(y.present_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-slate-500">Calculated from your assumptions; not a recommendation.</p>
        </div>
      ) : null}

      {grid.data ? (
        <div className="overflow-x-auto border-t border-slate-100 pt-3">
          <h3 className="mb-1 text-xs font-semibold text-slate-600">
            Value per share (₹): WACC × {grid.data.column_axis === "terminal_growth" ? "terminal growth" : "exit multiple"}
          </h3>
          <table className="text-right text-xs" aria-label="Sensitivity table">
            <thead>
              <tr>
                <th className="px-2 text-left font-medium">WACC</th>
                {grid.data.column_values.map((c) => (
                  <th key={c} className="px-2 font-medium">
                    {grid.data.column_axis === "terminal_growth" ? formatPercent(c) : `${formatNumber(c)}×`}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.data.row_values.map((r, i) => (
                <tr key={r}>
                  <th className="px-2 text-left font-normal">{formatPercent(r)}</th>
                  {grid.data.cells[i]?.map((cell, j) => (
                    <td key={j} className="px-2" title={grid.data.invalid_reasons[`${i},${j}`]}>
                      {cell === null ? "n/a" : formatNumber(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {result && typeof inputs !== "string" ? (
        <form
          className="flex flex-wrap items-end gap-2 border-t border-slate-100 pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) save.mutate({ name: name.trim(), ticker, market: "IN", inputs });
          }}
        >
          <Field label="Save as" value={name} onChange={setName} />
          <button type="submit" disabled={save.isPending} className="rounded border border-slate-300 px-3 py-1.5 text-sm">
            Save valuation
          </button>
          {save.isSuccess ? <span className="text-xs text-emerald-700">Saved.</span> : null}
          {save.isError ? <ErrorState error={save.error} /> : null}
        </form>
      ) : null}
    </Panel>
  );
}
