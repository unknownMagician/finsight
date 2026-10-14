import { useLiveness, useReadiness } from "./api";

type Tone = "ok" | "error" | "pending";

const toneClasses: Record<Tone, string> = {
  ok: "bg-emerald-100 text-emerald-800",
  error: "bg-rose-100 text-rose-800",
  pending: "bg-slate-100 text-slate-600",
};

function Badge({ tone, children }: { tone: Tone; children: string }) {
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${toneClasses[tone]}`}>{children}</span>;
}

export function SystemStatus() {
  const live = useLiveness();
  const ready = useReadiness();

  const apiTone: Tone = live.isPending ? "pending" : live.isSuccess ? "ok" : "error";
  const dbStatus = ready.data?.checks.database;
  const dbTone: Tone = ready.isPending ? "pending" : dbStatus === "ok" ? "ok" : "error";

  return (
    <section aria-labelledby="system-status-heading" className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 id="system-status-heading" className="mb-3 text-sm font-semibold text-slate-700">
        System status
      </h2>
      <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 text-sm">
        <dt className="text-slate-500">API</dt>
        <dd>
          <Badge tone={apiTone}>
            {live.isPending ? "Checking…" : live.isSuccess ? `Online · v${live.data.version}` : "Unreachable"}
          </Badge>
        </dd>
        <dt className="text-slate-500">Database</dt>
        <dd>
          <Badge tone={dbTone}>
            {ready.isPending ? "Checking…" : dbStatus === "ok" ? "Connected" : "Unavailable"}
          </Badge>
        </dd>
      </dl>
    </section>
  );
}
