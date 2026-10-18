import { FreshnessLabel } from "../../components/DataBadges";
import { ErrorState, Loading, Panel } from "../../components/States";
import { formatINR, formatNumber, formatPercent } from "../../lib/format";
import { useQuote } from "./api";
import type { Exchange } from "./types";

export function QuoteCard({ ticker, exchange }: { ticker: string; exchange: Exchange }) {
  const quote = useQuote(ticker, exchange);
  return (
    <Panel title="Latest close">
      {quote.isPending ? (
        <Loading />
      ) : quote.isError ? (
        <ErrorState error={quote.error} />
      ) : (
        <div className="space-y-2">
          <div className="flex flex-wrap items-baseline gap-3">
            <span className="text-3xl font-semibold" data-testid="close-price">
              {formatINR(quote.data.close)}
            </span>
            {quote.data.change !== null ? (
              <span className={Number(quote.data.change) >= 0 ? "text-emerald-700" : "text-rose-700"}>
                {Number(quote.data.change) >= 0 ? "+" : ""}
                {formatNumber(quote.data.change)} ({formatPercent(quote.data.change_pct, 2)})
              </span>
            ) : null}
            <span className="text-sm text-slate-500">
              {quote.data.listing.exchange}: {quote.data.listing.symbol}
            </span>
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
            <dt className="text-slate-500">Open</dt>
            <dd>{formatINR(quote.data.open)}</dd>
            <dt className="text-slate-500">High / Low</dt>
            <dd>
              {formatINR(quote.data.high)} / {formatINR(quote.data.low)}
            </dd>
            <dt className="text-slate-500">Prev. close</dt>
            <dd>{formatINR(quote.data.prev_close)}</dd>
            <dt className="text-slate-500">Volume</dt>
            <dd>{formatNumber(quote.data.volume, { maximumFractionDigits: 0 })}</dd>
          </dl>
          <FreshnessLabel freshness={quote.data.freshness} />
          <p className="text-xs text-slate-500">
            End-of-day price for the trading date shown. Not a real-time quote.
          </p>
        </div>
      )}
    </Panel>
  );
}
