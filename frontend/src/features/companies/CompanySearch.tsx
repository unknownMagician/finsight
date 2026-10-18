import { useEffect, useState } from "react";
import { Link } from "react-router";

import { Badge, ProviderBadge } from "../../components/DataBadges";
import { ErrorState, Loading, Toggle } from "../../components/States";
import { useCompanySearch } from "./api";
import type { Exchange } from "./types";

type ExchangeFilter = "ALL" | Exchange;

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}

export function CompanySearch() {
  const [text, setText] = useState("");
  const [exchange, setExchange] = useState<ExchangeFilter>("ALL");
  const q = useDebounced(text, 250);
  const search = useCompanySearch(q, exchange === "ALL" ? null : exchange);

  return (
    <section aria-labelledby="search-heading" className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="search-heading" className="text-sm font-semibold text-slate-700">
        Find an Indian listed company
      </h2>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Company name, NSE/BSE symbol or ISIN"
          aria-label="Search companies"
          className="min-w-64 flex-1 rounded border border-slate-300 px-2 py-1.5 text-sm"
        />
        <Toggle<ExchangeFilter>
          label="Exchange"
          value={exchange}
          onChange={setExchange}
          options={[
            { value: "ALL", label: "All" },
            { value: "NSE", label: "NSE" },
            { value: "BSE", label: "BSE" },
          ]}
        />
      </div>

      {q.trim() === "" ? null : search.isPending ? (
        <Loading label="Searching…" />
      ) : search.isError ? (
        <ErrorState error={search.error} />
      ) : search.data.length === 0 ? (
        <p className="text-sm text-slate-500">No companies match “{q}”.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {search.data.map((company) => (
            <li key={company.ticker} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div>
                <div className="font-medium">{company.name}</div>
                <div className="text-xs text-slate-500">
                  {company.ticker}
                  {company.isin ? ` · ISIN ${company.isin}` : ""}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {company.instruments
                  .filter((i) => exchange === "ALL" || i.exchange === exchange)
                  .map((instrument) => (
                    <Link
                      key={`${instrument.exchange}:${instrument.symbol}`}
                      to={`/companies/${encodeURIComponent(company.ticker)}?exchange=${instrument.exchange}`}
                      className="rounded border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-100"
                      aria-label={`${company.name} on ${instrument.exchange}`}
                    >
                      {instrument.exchange}: {instrument.symbol}
                      {instrument.listing_status !== "active" ? " (not traded in latest session)" : ""}
                    </Link>
                  ))}
                {company.instruments[0] ? <ProviderBadge provider={company.instruments[0].provider} /> : null}
                {company.instruments.length === 0 ? <Badge className="bg-slate-100">No listings</Badge> : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
