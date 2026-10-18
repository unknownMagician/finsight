import { useState, type FormEvent } from "react";

import { Field, IssueList, SubmitButton } from "../../components/Form";
import { ErrorState, Panel } from "../../components/States";
import { parseDecimal, percentToFraction } from "../../lib/decimal";
import { formatPercent } from "../../lib/format";
import { useWacc } from "./api";
import type { WACCInputs } from "./types";

const FIELDS = [
  ["risk_free_rate", "Risk-free rate", "%", "e.g. a dated Government of India bond yield you choose"],
  ["equity_risk_premium", "Equity risk premium", "%", "Your assumption; state its source and date"],
  ["beta", "Beta", "", "Levered equity beta"],
  ["size_premium", "Size premium", "%", "Optional, 0 if none"],
  ["pre_tax_cost_of_debt", "Pre-tax cost of debt", "%", ""],
  ["tax_rate", "Marginal tax rate", "%", "Your assumption for this company"],
  ["equity_value", "Market value of equity (₹ Cr)", "", ""],
  ["debt_value", "Market value of debt (₹ Cr)", "", ""],
] as const;

type Key = (typeof FIELDS)[number][0];
const PERCENT: ReadonlySet<Key> = new Set<Key>([
  "risk_free_rate",
  "equity_risk_premium",
  "size_premium",
  "pre_tax_cost_of_debt",
  "tax_rate",
]);

export function WaccCalculator({ onUse }: { onUse: (waccPercent: string) => void }) {
  const [values, setValues] = useState<Record<Key, string>>({
    risk_free_rate: "",
    equity_risk_premium: "",
    beta: "",
    size_premium: "0",
    pre_tax_cost_of_debt: "",
    tax_rate: "",
    equity_value: "",
    debt_value: "",
  });
  const [error, setError] = useState<string | null>(null);
  const wacc = useWacc();

  function submit(event: FormEvent) {
    event.preventDefault();
    const body: Partial<WACCInputs> = {};
    for (const [key, label] of FIELDS) {
      const parsed = PERCENT.has(key) ? percentToFraction(values[key]) : parseDecimal(values[key]);
      if (parsed === null) {
        setError(`${label} must be a number.`);
        return;
      }
      body[key] = parsed;
    }
    setError(null);
    wacc.mutate(body as WACCInputs);
  }

  return (
    <Panel title="Weighted average cost of capital">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-xs text-slate-500">
          No Indian rates are pre-filled: risk-free rate, ERP, beta and tax rate are your dated assumptions.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {FIELDS.map(([key, label, suffix, hint]) => (
            <Field
              key={key}
              label={label}
              suffix={suffix || undefined}
              hint={hint || undefined}
              value={values[key]}
              onChange={(v) => setValues({ ...values, [key]: v })}
            />
          ))}
        </div>
        {error ? (
          <p role="alert" className="text-sm text-rose-700">
            {error}
          </p>
        ) : null}
        <SubmitButton pending={wacc.isPending}>Compute WACC</SubmitButton>
      </form>
      {wacc.isError ? <ErrorState error={wacc.error} /> : null}
      {wacc.data ? (
        <div className="space-y-2 border-t border-slate-100 pt-3 text-sm">
          <p>
            WACC <strong data-testid="wacc-value">{formatPercent(wacc.data.wacc, 2)}</strong> · cost of equity{" "}
            {formatPercent(wacc.data.cost_of_equity, 2)} · after-tax cost of debt{" "}
            {formatPercent(wacc.data.after_tax_cost_of_debt, 2)} · equity weight {formatPercent(wacc.data.equity_weight)}
          </p>
          <IssueList issues={wacc.data.warnings} />
          <button
            type="button"
            className="rounded border border-slate-300 px-2 py-1 text-xs"
            onClick={() => onUse((Number(wacc.data.wacc) * 100).toFixed(4).replace(/\.?0+$/, ""))}
          >
            Use in DCF
          </button>
        </div>
      ) : null}
    </Panel>
  );
}
