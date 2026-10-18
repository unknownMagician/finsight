import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { Badge } from "../../components/DataBadges";
import { ErrorState, Loading, Panel, Unavailable } from "../../components/States";
import { apiDownload, ApiError } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { useCreateReport, useDeleteReport, useReport, useReports, type Provenance, type ReportSection } from "./api";

const KIND: Record<Provenance, { label: string; tone: string }> = {
  reported: { label: "Reported", tone: "bg-slate-100 text-slate-700" },
  calculated: { label: "Calculated", tone: "bg-sky-100 text-sky-800" },
  assumption: { label: "Assumption", tone: "bg-orange-100 text-orange-900" },
  forecast: { label: "Forecast", tone: "bg-orange-100 text-orange-900" },
  extracted: { label: "Extracted (verified)", tone: "bg-emerald-100 text-emerald-800" },
  market: { label: "Market data (EOD)", tone: "bg-slate-100 text-slate-700" },
  ai_explanation: { label: "AI explanation", tone: "bg-violet-100 text-violet-800" },
};

function KindBadge({ kind }: { kind: Provenance }) {
  return <Badge className={KIND[kind].tone}>{KIND[kind].label}</Badge>;
}

function Section({ section }: { section: ReportSection }) {
  return (
    <Panel title={section.title}>
      {section.status === "unavailable" ? (
        <Unavailable>Unavailable: {section.reason}</Unavailable>
      ) : (
        <div className="space-y-3">
          {section.paragraphs.map((p, i) => (
            <p key={i} className="whitespace-pre-wrap text-sm">
              {p}
            </p>
          ))}
          {section.figures.length ? (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-slate-100">
                {section.figures.map((f, i) => (
                  <tr key={i}>
                    <td className="py-1">{f.label}</td>
                    <td className="py-1 tabular-nums">{f.display}</td>
                    <td className="py-1">
                      <KindBadge kind={f.kind} />
                    </td>
                    <td className="py-1 text-xs text-slate-500">
                      {[f.period, f.basis, f.source, f.note].filter(Boolean).join(" · ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {section.tables.map((t, i) => (
            <div key={i} className="overflow-x-auto">
              <div className="mb-1 flex items-center gap-2 text-xs text-slate-600">
                <span className="font-semibold">{t.caption}</span>
                <KindBadge kind={t.kind} />
              </div>
              <table className="w-full text-sm" aria-label={t.caption}>
                <thead>
                  <tr className="text-left text-xs text-slate-500">
                    {t.columns.map((c) => (
                      <th key={c} className="font-medium">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {t.rows.map((row, r) => (
                    <tr key={r}>
                      {row.map((cell, c) => (
                        <td key={c} className="py-0.5 pr-2 tabular-nums">
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {t.source ? <p className="text-xs text-slate-500">Source: {t.source}</p> : null}
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

export function ReportView() {
  const { id = "" } = useParams();
  const report = useReport(id);
  const [downloadError, setDownloadError] = useState<unknown>(null);
  if (report.isPending) return <Loading />;
  if (report.isError) return <ErrorState error={report.error} />;
  const content = report.data.content;

  async function download(format: string) {
    setDownloadError(null);
    try {
      await apiDownload(`/reports/${id}/export?format=${format}`);
    } catch (e) {
      setDownloadError(e instanceof ApiError ? e : new Error("download failed"));
    }
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <Link to="/reports" className="text-xs text-sky-700 underline">
          ← Reports
        </Link>
        <h1 className="text-2xl font-semibold">{content.title}</h1>
        <p className="text-sm text-slate-600">
          {content.company.name} ({content.company.ticker}) · {content.company.listings.join(", ")} · listing{" "}
          {content.exchange ?? "—"} · basis {content.basis ?? "—"} · generated {formatDate(content.generated_at)}
        </p>
        <div className="flex flex-wrap gap-2 pt-1" role="group" aria-label="Export">
          {[
            ["html", "HTML (print to PDF)"],
            ["md", "Markdown"],
            ["csv", "CSV"],
            ["json", "JSON"],
          ].map(([format, label]) => (
            <button
              key={format}
              type="button"
              onClick={() => void download(format as string)}
              className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
            >
              Download {label}
            </button>
          ))}
        </div>
        {downloadError ? <ErrorState error={downloadError} /> : null}
      </div>
      {content.sections.map((s) => (
        <Section key={s.key} section={s} />
      ))}
      <ul className="list-disc space-y-1 pl-5 text-xs text-slate-500">
        {content.disclaimers.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
    </div>
  );
}

export function ReportsPage() {
  const reports = useReports();
  const del = useDeleteReport();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Research reports</h1>
      {del.isError ? <ErrorState error={del.error} /> : null}
      {reports.isPending ? (
        <Loading />
      ) : reports.isError ? (
        <ErrorState error={reports.error} />
      ) : reports.data.length === 0 ? (
        <Unavailable>No reports yet. Generate one from a company's research page.</Unavailable>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
          {reports.data.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm">
              <Link to={`/reports/${r.id}`} className="text-sky-700 underline">
                {r.title}
              </Link>
              <span className="text-xs text-slate-500">
                {r.ticker} · {formatDate(r.created_at)} {r.includes_ai ? "· includes AI summary" : ""}
              </span>
              <button type="button" onClick={() => del.mutate(r.id)} className="text-xs text-rose-700 underline" aria-label={`Delete ${r.title}`}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function GenerateReport({ ticker, exchange, aiAvailable }: { ticker: string; exchange: string | null; aiAvailable: boolean }) {
  const create = useCreateReport();
  const navigate = useNavigate();
  const [includeAi, setIncludeAi] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={create.isPending}
        onClick={() =>
          create.mutate(
            { ticker, market: "IN", exchange, include_ai: includeAi },
            { onSuccess: (report) => navigate(`/reports/${report.id}`) },
          )
        }
        className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100 disabled:opacity-50"
      >
        {create.isPending ? "Generating…" : "Generate research report"}
      </button>
      {aiAvailable ? (
        <label className="flex items-center gap-1 text-xs">
          <input type="checkbox" checked={includeAi} onChange={(e) => setIncludeAi(e.target.checked)} />
          include cited AI summary
        </label>
      ) : null}
      {create.isError ? <ErrorState error={create.error} /> : null}
    </div>
  );
}
