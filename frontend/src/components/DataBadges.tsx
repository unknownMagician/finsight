import type { DataNature, FreshnessOut } from "../features/companies/types";
import { formatDate } from "../lib/format";

const NATURE_LABEL: Record<DataNature, string> = {
  demo: "Demo data",
  end_of_day: "End of day",
  delayed: "Delayed",
  live: "Live",
};

const NATURE_TONE: Record<DataNature, string> = {
  demo: "bg-amber-100 text-amber-900",
  end_of_day: "bg-slate-100 text-slate-700",
  delayed: "bg-sky-100 text-sky-800",
  live: "bg-emerald-100 text-emerald-800",
};

export function Badge({ className, children }: { className: string; children: string }) {
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${className}`}>{children}</span>;
}

/** Data-nature, cache and staleness labels plus the source and timestamps. */
export function FreshnessLabel({ freshness }: { freshness: FreshnessOut }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
      <Badge className={NATURE_TONE[freshness.nature]}>{NATURE_LABEL[freshness.nature]}</Badge>
      {freshness.stale ? <Badge className="bg-rose-100 text-rose-800">Stale</Badge> : null}
      {freshness.cached ? <Badge className="bg-slate-100 text-slate-600">Cached</Badge> : null}
      {freshness.adjusted === false ? <span>Unadjusted prices</span> : null}
      <span>
        As of {formatDate(freshness.as_of)} · source {freshness.provider} · retrieved{" "}
        {formatDate(freshness.retrieved_at)}
      </span>
    </div>
  );
}

export function ProviderBadge({ provider }: { provider: string }) {
  return provider === "demo" ? (
    <Badge className="bg-amber-100 text-amber-900">Demo data</Badge>
  ) : (
    <Badge className="bg-slate-100 text-slate-700">{`Source: ${provider}`}</Badge>
  );
}
