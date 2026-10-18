import { ProviderBadge } from "../../components/DataBadges";
import { ErrorState, Loading, Panel, Unavailable } from "../../components/States";
import { formatDate, formatINR } from "../../lib/format";
import { useCorporateActions } from "./api";

export function CorporateActionsPanel({ ticker }: { ticker: string }) {
  const actions = useCorporateActions(ticker);
  return (
    <Panel title="Corporate actions">
      {actions.isPending ? (
        <Loading />
      ) : actions.isError ? (
        <ErrorState error={actions.error} />
      ) : actions.data.actions.length === 0 ? (
        <Unavailable>No corporate actions reported by {actions.data.provider}.</Unavailable>
      ) : (
        <>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500">
                <th className="py-1 font-medium">Ex-date</th>
                <th className="py-1 font-medium">Exchange</th>
                <th className="py-1 font-medium">Type</th>
                <th className="py-1 font-medium">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {actions.data.actions.slice(0, 15).map((a) => (
                <tr key={`${a.exchange}-${a.ex_date}-${a.action_type}-${a.description}`}>
                  <td className="py-1">{formatDate(a.ex_date)}</td>
                  <td className="py-1">{a.exchange}</td>
                  <td className="py-1 capitalize">{a.action_type}</td>
                  <td className="py-1 text-slate-600">
                    {a.cash_amount !== null ? `${formatINR(a.cash_amount)} per share · ` : ""}
                    {a.ratio_numerator !== null && a.ratio_denominator !== null
                      ? `${a.ratio_numerator}:${a.ratio_denominator} · `
                      : ""}
                    {a.description}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <ProviderBadge provider={actions.data.provider} />
            <span>Retrieved {formatDate(actions.data.retrieved_at)}</span>
          </div>
        </>
      )}
    </Panel>
  );
}
