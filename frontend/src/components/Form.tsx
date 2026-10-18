import { useId, type ReactNode } from "react";

export function Field({
  label,
  value,
  onChange,
  hint,
  suffix,
  invalid,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: ReactNode;
  suffix?: string;
  invalid?: boolean;
  type?: "text" | "number";
}) {
  const id = useId();
  return (
    <div className="block text-sm">
      <label htmlFor={id} className="text-slate-600">
        {label}
      </label>
      <span className="mt-1 flex items-center gap-1">
        <input
          id={id}
          type={type}
          inputMode="decimal"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={invalid || undefined}
          aria-describedby={hint ? `${id}-hint` : undefined}
          className={`w-full rounded border px-2 py-1 ${invalid ? "border-rose-500" : "border-slate-300"}`}
        />
        {suffix ? (
          <span aria-hidden="true" className="text-xs text-slate-500">
            {suffix}
          </span>
        ) : null}
      </span>
      {hint ? (
        <span id={`${id}-hint`} className="mt-0.5 block text-xs text-slate-500">
          {hint}
        </span>
      ) : null}
    </div>
  );
}

export function SubmitButton({ pending, children }: { pending: boolean; children: string }) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
    >
      {pending ? "Calculating…" : children}
    </button>
  );
}

export function IssueList({ issues }: { issues: { code: string; message: string; severity?: string }[] }) {
  if (!issues.length) return null;
  return (
    <ul className="space-y-1">
      {issues.map((issue) => (
        <li key={issue.code} role="status" className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-900">
          {issue.message}
        </li>
      ))}
    </ul>
  );
}
