import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { FreshnessLabel } from "../../components/DataBadges";
import { ErrorState, Loading, Panel, Toggle, Unavailable } from "../../components/States";
import { formatINR } from "../../lib/format";
import { usePrices } from "./api";
import type { Exchange } from "./types";

type Range = "1M" | "6M" | "1Y" | "5Y";
const RANGE_DAYS: Record<Range, number> = { "1M": 31, "6M": 183, "1Y": 366, "5Y": 1827 };

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

export function PriceChart({ ticker, exchange }: { ticker: string; exchange: Exchange }) {
  const [range, setRange] = useState<Range>("1Y");
  const { start, end } = useMemo(() => ({ start: isoDaysAgo(RANGE_DAYS[range]), end: isoDaysAgo(0) }), [range]);
  const prices = usePrices(ticker, exchange, start, end);
  const data = useMemo(
    () => (prices.data?.bars ?? []).map((bar) => ({ date: bar.date, close: Number(bar.close) })),
    [prices.data],
  );

  return (
    <Panel
      title="Price history"
      actions={
        <Toggle<Range>
          label="Range"
          value={range}
          onChange={setRange}
          options={(Object.keys(RANGE_DAYS) as Range[]).map((r) => ({ value: r, label: r }))}
        />
      }
    >
      {prices.isPending ? (
        <Loading />
      ) : prices.isError ? (
        <ErrorState error={prices.error} />
      ) : data.length === 0 ? (
        <Unavailable>No trades in this range.</Unavailable>
      ) : (
        <>
          <div className="h-64" aria-label={`Daily closing prices, ${data.length} sessions`} role="img">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                <CartesianGrid stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={40} />
                <YAxis
                  domain={["auto", "auto"]}
                  tick={{ fontSize: 11 }}
                  width={72}
                  tickFormatter={(v: number) => formatINR(v, 0)}
                />
                <Tooltip formatter={(v) => formatINR(Number(v))} labelClassName="text-xs" />
                <Line type="monotone" dataKey="close" stroke="#0f172a" dot={false} strokeWidth={1.5} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <FreshnessLabel freshness={prices.data.freshness} />
          {prices.data.warnings.map((w) => (
            <p key={w} className="text-xs text-amber-800">
              {w}
            </p>
          ))}
        </>
      )}
    </Panel>
  );
}
