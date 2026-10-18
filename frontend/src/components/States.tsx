import type { ReactNode } from "react";

import { ApiError } from "../lib/api";

export function Panel({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  const id = `panel-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <section aria-labelledby={id} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={id} className="text-sm font-semibold text-slate-700">
          {title}
        </h2>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <p className="text-sm text-slate-500">{label}</p>;
}

/** Explains an error in user terms; "unavailable" errors are shown as a neutral notice. */
export function ErrorState({ error }: { error: unknown }) {
  if (error instanceof ApiError) {
    if (error.code === "capability_unavailable" || error.code === "provider_not_configured") {
      return <Unavailable>{error.message}</Unavailable>;
    }
    if (error.code === "no_financial_data" || error.code === "market_data_not_found") {
      return <Unavailable>{error.message}</Unavailable>;
    }
    if (error.code === "provider_rate_limited") {
      return (
        <p role="alert" className="text-sm text-amber-800">
          The free data provider's limit was reached. Try again in a minute.
        </p>
      );
    }
    return (
      <p role="alert" className="text-sm text-rose-700">
        {error.message}
      </p>
    );
  }
  return (
    <p role="alert" className="text-sm text-rose-700">
      Something went wrong.
    </p>
  );
}

export function Unavailable({ children }: { children: ReactNode }) {
  return <p className="rounded bg-slate-50 px-3 py-2 text-sm text-slate-600">{children}</p>;
}

export function Toggle<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string; disabled?: boolean }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex overflow-hidden rounded border border-slate-300 text-xs">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          disabled={option.disabled}
          onClick={() => onChange(option.value)}
          className={`px-2 py-1 ${option.value === value ? "bg-slate-900 text-white" : "bg-white text-slate-700"} disabled:opacity-40`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
