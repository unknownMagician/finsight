import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";

import { Badge } from "../../components/DataBadges";
import { Field } from "../../components/Form";
import { ErrorState, Loading, Panel, Unavailable } from "../../components/States";
import { formatDate, formatNumber } from "../../lib/format";
import { useResearchStatus } from "../research/api";
import { useDeleteDocument, useDocuments, useExtractFacts, useUploadDocument, type DocumentOut } from "./api";

const UNIT_LABEL: Record<string, string> = {
  crores: "₹ crore",
  lakhs: "₹ lakh",
  millions: "million",
  thousands: "thousand",
  units: "",
  per_share: "₹ per share",
  percent: "%",
};

function DocumentCard({ doc, aiConfigured }: { doc: DocumentOut; aiConfigured: boolean }) {
  const extract = useExtractFacts();
  const del = useDeleteDocument();
  return (
    <Panel
      title={doc.title}
      actions={
        <div className="flex items-center gap-2">
          {doc.status === "ready" && aiConfigured ? (
            <button
              type="button"
              disabled={extract.isPending}
              onClick={() => extract.mutate(doc.id)}
              className="rounded border border-slate-300 px-2 py-1 text-xs"
            >
              {extract.isPending ? "Reading…" : "Extract key figures (AI)"}
            </button>
          ) : null}
          <button type="button" onClick={() => del.mutate(doc.id)} className="text-xs text-rose-700 underline" aria-label={`Delete ${doc.title}`}>
            Delete
          </button>
        </div>
      }
    >
      <p className="text-xs text-slate-500">
        {doc.filename} · {doc.page_count} pages ({doc.pages_with_text} with text) ·{" "}
        {doc.company ? `${doc.company.name} (${doc.company.ticker})` : "no company"}
        {doc.fiscal_year ? ` · FY${String(doc.fiscal_year).slice(-2)}` : ""} · uploaded {formatDate(doc.created_at)}
      </p>
      {doc.status === "no_text" ? (
        <Unavailable>This PDF has no text layer (scanned). OCR is not supported, so it cannot be searched or cited.</Unavailable>
      ) : null}
      {extract.isError ? <ErrorState error={extract.error} /> : null}
      {del.isError ? <ErrorState error={del.error} /> : null}
      {doc.facts.length ? (
        <table className="w-full text-sm" aria-label={`Figures from ${doc.title}`}>
          <thead>
            <tr className="text-left text-xs text-slate-500">
              <th className="font-medium">Metric</th>
              <th className="font-medium">Value</th>
              <th className="font-medium">Page</th>
              <th className="font-medium">Check</th>
              <th className="font-medium">Quote</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {doc.facts.map((f) => (
              <tr key={f.id}>
                <td>{f.metric}</td>
                <td className="tabular-nums">
                  {formatNumber(f.value)} {UNIT_LABEL[f.unit] ?? f.unit}
                </td>
                <td>p. {f.page_number}</td>
                <td>
                  {f.status === "verified" ? (
                    <Badge className="bg-emerald-100 text-emerald-800">Verified on page</Badge>
                  ) : (
                    <span title={f.verification_note ?? undefined}>
                      <Badge className="bg-rose-100 text-rose-800">Unverified</Badge>
                    </span>
                  )}
                </td>
                <td className="text-xs text-slate-600">“{f.quote}”</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {doc.facts.length ? (
        <p className="text-xs text-slate-500">
          Figures were read by the AI ({doc.facts[0]?.model}); “Verified” means the quote was found on that page and
          contains the value. Unverified figures are never used as data.
        </p>
      ) : null}
    </Panel>
  );
}

export function DocumentsPage() {
  const [params] = useSearchParams();
  const ticker = params.get("ticker");
  const documents = useDocuments(ticker);
  const upload = useUploadDocument();
  const status = useResearchStatus();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState(ticker ?? "");
  const [year, setYear] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !title.trim()) return;
    const form = new FormData();
    form.append("file", file);
    form.append("title", title.trim());
    if (company.trim()) {
      form.append("ticker", company.trim());
      form.append("market", "IN");
    }
    if (year.trim()) form.append("fiscal_year", year.trim());
    upload.mutate(form, { onSuccess: () => setTitle("") });
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Annual reports</h1>
      <Panel title="Upload a report (PDF)">
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
          <div className="text-sm">
            <label htmlFor="report-file" className="text-slate-600">
              PDF file
            </label>
            <input
              id="report-file"
              type="file"
              accept="application/pdf,.pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="mt-1 block w-full text-sm"
            />
          </div>
          <Field label="Title" value={title} onChange={setTitle} hint="e.g. Annual Report 2025-26" />
          <Field label="Company ticker or ISIN (optional)" value={company} onChange={setCompany} />
          <Field label="Fiscal year (optional)" value={year} onChange={setYear} hint="e.g. 2026 for FY26" />
          <div className="sm:col-span-2">
            <button type="submit" disabled={upload.isPending || !file} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
              {upload.isPending ? "Uploading…" : "Upload"}
            </button>
            <span className="ml-2 text-xs text-slate-500">
              Stored privately for your account: extracted text only, not the file. Max 20 MB.
            </span>
          </div>
        </form>
        {upload.isError ? <ErrorState error={upload.error} /> : null}
      </Panel>
      {documents.isPending ? (
        <Loading />
      ) : documents.isError ? (
        <ErrorState error={documents.error} />
      ) : documents.data.length === 0 ? (
        <Unavailable>No reports uploaded{ticker ? ` for ${ticker}` : ""} yet.</Unavailable>
      ) : (
        documents.data.map((doc) => <DocumentCard key={doc.id} doc={doc} aiConfigured={!!status.data?.configured} />)
      )}
    </div>
  );
}
