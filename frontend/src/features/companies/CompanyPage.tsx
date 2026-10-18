import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { Badge, ProviderBadge } from "../../components/DataBadges";
import { ErrorState, Loading, Toggle, Unavailable } from "../../components/States";
import { RatiosPanel, ValuationPanel } from "./AnalysisPanels";
import { useAddToWatchlist, useWatchlists } from "../watchlists/api";
import { useCompany, useFinancials } from "./api";
import { CorporateActionsPanel } from "./CorporateActionsPanel";
import { DataSources } from "./DataSources";
import { FinancialsPanel } from "./FinancialsPanel";
import { PriceChart } from "./PriceChart";
import { QuoteCard } from "./QuoteCard";
import type { CompanyOut, Exchange, ReportingBasis } from "./types";

function chooseExchange(company: CompanyOut, requested: string | null): Exchange | null {
  const exchanges = company.instruments.map((i) => i.exchange);
  if (requested === "NSE" || requested === "BSE") return exchanges.includes(requested) ? requested : null;
  const active = company.instruments.filter((i) => i.listing_status === "active");
  // Never guess between two listings: only auto-select when there is exactly one.
  if (active.length === 1 && active[0]) return active[0].exchange;
  if (company.instruments.length === 1 && company.instruments[0]) return company.instruments[0].exchange;
  return null;
}

function AddToWatchlist({ ticker }: { ticker: string }) {
  const watchlists = useWatchlists();
  const add = useAddToWatchlist();
  if (!watchlists.data?.length) return null;
  return (
    <select
      aria-label="Add to watchlist"
      value=""
      onChange={(e) => e.target.value && add.mutate({ id: e.target.value, ticker })}
      className="rounded border border-slate-300 px-2 py-1 text-xs"
    >
      <option value="">{add.isSuccess ? "Added ✓" : "Add to watchlist…"}</option>
      {watchlists.data.map((w) => (
        <option key={w.id} value={w.id}>
          {w.name}
        </option>
      ))}
    </select>
  );
}

export function CompanyPage() {
  const { ticker = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const company = useCompany(ticker);
  const annual = useFinancials(ticker, "annual", null);
  const [basis, setBasis] = useState<ReportingBasis | null>(null);

  if (company.isPending) return <Loading />;
  if (company.isError) return <ErrorState error={company.error} />;

  const data = company.data;
  const exchange = chooseExchange(data, params.get("exchange"));
  const hasStatements = (annual.data?.available_bases.length ?? 0) > 0;
  const instrument = data.instruments.find((i) => i.exchange === exchange);

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <Link to="/" className="text-xs text-sky-700 underline">
          ← Search
        </Link>
        <h1 className="text-2xl font-semibold">{data.name}</h1>
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <span>{data.ticker}</span>
          {data.isin ? <span>· ISIN {data.isin}</span> : <span>· ISIN not provided by source</span>}
          {instrument?.series ? <span>· series {instrument.series}</span> : null}
          {data.instruments[0] ? <ProviderBadge provider={data.instruments[0].provider} /> : null}
          {instrument && instrument.listing_status !== "active" ? (
            <Badge className="bg-amber-100 text-amber-900">Not traded in the latest session</Badge>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Link
            to={`/calculators?ticker=${encodeURIComponent(data.ticker)}`}
            className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
          >
            Open valuation calculators
          </Link>
          <AddToWatchlist ticker={data.ticker} />
        </div>
        {instrument?.former_symbols.length ? (
          <p className="text-xs text-slate-500">Formerly: {instrument.former_symbols.join(", ")}</p>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-slate-600">Listing</span>
        <Toggle<Exchange>
          label="Listing exchange"
          value={exchange ?? ("" as Exchange)}
          onChange={(next) => setParams({ exchange: next }, { replace: true })}
          options={(["NSE", "BSE"] as Exchange[]).map((ex) => {
            const listing = data.instruments.find((i) => i.exchange === ex);
            return { value: ex, label: listing ? `${ex}: ${listing.symbol}` : `${ex} (not listed)`, disabled: !listing };
          })}
        />
      </div>

      {exchange === null ? (
        <Unavailable>
          {data.instruments.length ? "This company is listed on both NSE and BSE. Choose a listing to see prices." : "No exchange listings are known for this company."}
        </Unavailable>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <QuoteCard ticker={data.ticker} exchange={exchange} />
          <ValuationPanel ticker={data.ticker} exchange={exchange} basis={basis} enabled={hasStatements} />
          <div className="lg:col-span-2">
            <PriceChart ticker={data.ticker} exchange={exchange} />
          </div>
        </div>
      )}

      <FinancialsPanel ticker={data.ticker} basis={basis} onBasisChange={setBasis} />
      <div className="grid gap-4 lg:grid-cols-2">
        <RatiosPanel ticker={data.ticker} basis={basis} enabled={hasStatements} />
        <CorporateActionsPanel ticker={data.ticker} />
      </div>
      <DataSources />
    </div>
  );
}
