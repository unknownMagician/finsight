import { ErrorState, Loading, Panel } from "../../components/States";
import { formatDate } from "../../lib/format";
import { useMarketStatus } from "./api";

const CAPABILITY_LABEL: Record<string, string> = {
  announcements: "Disclosures & announcements",
  shareholding: "Shareholding patterns",
  intraday_prices: "Intraday / live prices",
  financial_statements: "Financial statements",
  corporate_actions: "Corporate actions",
  eod_prices: "End-of-day prices",
  instrument_directory: "Instrument directory",
};

export function DataSources() {
  const status = useMarketStatus();
  return (
    <Panel title="Data sources">
      {status.isPending ? (
        <Loading />
      ) : status.isError ? (
        <ErrorState error={status.error} />
      ) : (
        <div className="space-y-2 text-xs text-slate-600">
          <p>
            Latest published trading date: <strong>{formatDate(status.data.latest_trading_date)}</strong>
            {status.data.reachable ? "" : " · provider unreachable"}
          </p>
          <ul className="space-y-1">
            {status.data.providers
              .filter((p) => p.role !== "fundamentals_us")
              .map((p) => (
                <li key={p.role}>
                  <strong>{p.role === "market_data" ? "Prices & actions" : "Statements"}:</strong>{" "}
                  {p.configured ? p.name : "not configured"} — {p.usage_terms}
                </li>
              ))}
          </ul>
          {status.data.unavailable_capabilities.length ? (
            <p>
              Not available from the configured free providers:{" "}
              {status.data.unavailable_capabilities.map((c) => CAPABILITY_LABEL[c] ?? c).join(", ")}.
            </p>
          ) : null}
        </div>
      )}
    </Panel>
  );
}
