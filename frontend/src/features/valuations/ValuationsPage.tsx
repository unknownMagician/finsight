import { Link } from "react-router";

import { ErrorState, Loading, Panel, Unavailable } from "../../components/States";
import { formatCrores, formatDate, formatINR, formatPercent } from "../../lib/format";
import { useDeleteValuation, useSavedValuations } from "../calculators/api";

export function ValuationsPage() {
  const valuations = useSavedValuations();
  const del = useDeleteValuation();

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Saved valuations</h1>
      {del.isError ? <ErrorState error={del.error} /> : null}
      {valuations.isPending ? (
        <Loading />
      ) : valuations.isError ? (
        <ErrorState error={valuations.error} />
      ) : valuations.data.length === 0 ? (
        <Unavailable>
          No saved valuations. Run a DCF in the <Link to="/calculators" className="underline">calculators</Link> and save it.
        </Unavailable>
      ) : (
        valuations.data.map((v) => (
          <Panel
            key={v.id}
            title={v.name}
            actions={
              <button type="button" onClick={() => del.mutate(v.id)} className="text-xs text-rose-700 underline" aria-label={`Delete ${v.name}`}>
                Delete
              </button>
            }
          >
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
              <dt className="text-slate-500">Company</dt>
              <dd>{v.ticker ? <Link to={`/companies/${encodeURIComponent(v.ticker)}`} className="underline">{v.ticker}</Link> : "—"}</dd>
              <dt className="text-slate-500">Saved</dt>
              <dd>{formatDate(v.created_at)}</dd>
              <dt className="text-slate-500">WACC</dt>
              <dd>{formatPercent(v.inputs.wacc, 2)}</dd>
              <dt className="text-slate-500">Terminal</dt>
              <dd>
                {v.inputs.terminal_method === "perpetuity_growth"
                  ? `g = ${formatPercent(v.inputs.terminal_growth, 2)}`
                  : `${v.inputs.exit_multiple}× EBITDA`}
              </dd>
              <dt className="text-slate-500">Enterprise value</dt>
              <dd>{formatCrores(v.result.enterprise_value, v.result.scale)}</dd>
              <dt className="text-slate-500">Value per share</dt>
              <dd>{formatINR(v.result.value_per_share)}</dd>
            </dl>
            <p className="text-xs text-slate-500">
              Inputs are your assumptions; result recomputed server-side (engine {v.engine_version}).
            </p>
          </Panel>
        ))
      )}
    </div>
  );
}
