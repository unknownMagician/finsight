import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { Badge } from "../../components/DataBadges";
import { ErrorState, Loading, Panel, Unavailable } from "../../components/States";
import { useAsk, useResearchStatus, type ResearchAnswerOut } from "./api";

const GROUNDING: Record<ResearchAnswerOut["grounding"], { label: string; tone: string }> = {
  grounded: { label: "All claims cited", tone: "bg-emerald-100 text-emerald-800" },
  partially_grounded: { label: "Some claims unsupported", tone: "bg-amber-100 text-amber-900" },
  ungrounded: { label: "No supporting citations", tone: "bg-rose-100 text-rose-800" },
};

export function Answer({ answer }: { answer: ResearchAnswerOut }) {
  const flagged = new Set(answer.issues.filter((i) => i.code === "uncited_figure").map((i) => i.segment));
  const grounding = GROUNDING[answer.grounding];
  return (
    <div className="space-y-3" aria-label="AI answer">
      <div className="flex flex-wrap items-center gap-2">
        <Badge className="bg-violet-100 text-violet-800">AI explanation</Badge>
        <Badge className={grounding.tone}>{grounding.label}</Badge>
        <span className="text-xs text-slate-500">model {answer.model}</span>
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed">
        {answer.segments.map((segment, i) => (
          <span key={i} className={flagged.has(i) ? "bg-amber-100" : undefined} title={flagged.has(i) ? "Unsupported figure" : undefined}>
            {segment.text}
            {segment.citations.map((c, j) => (
              <a
                key={j}
                href={`#source-${c.source}`}
                title={`${c.label}: “${c.cited_text}”`}
                className="ml-0.5 align-super text-[10px] text-sky-700"
              >
                [{c.source}]
              </a>
            ))}
          </span>
        ))}
      </p>
      {answer.issues.length ? (
        <ul className="space-y-1 text-xs text-amber-900">
          {answer.issues.map((issue, i) => (
            <li key={i}>⚠ {issue.message}</li>
          ))}
        </ul>
      ) : null}
      <ol className="space-y-1 text-xs text-slate-600">
        {answer.sources.map((s) => (
          <li key={s.number} id={`source-${s.number}`}>
            [{s.number}] {s.title}
            {s.kind === "financial_data" ? " (FinSight stored data)" : ""}
          </li>
        ))}
      </ol>
      <p className="text-xs text-slate-500">{answer.disclaimer}</p>
    </div>
  );
}

export function ResearchPanel({ ticker }: { ticker: string }) {
  const status = useResearchStatus();
  const ask = useAsk();
  const [question, setQuestion] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    if (question.trim().length >= 3) ask.mutate({ question: question.trim(), ticker, market: "IN" });
  }

  return (
    <Panel title="AI research assistant">
      {status.isPending ? (
        <Loading />
      ) : !status.data?.configured ? (
        <Unavailable>
          The AI assistant is not configured on this server (it needs a backend Anthropic API key). All other data on
          this page is unaffected.
        </Unavailable>
      ) : (
        <>
          <p className="text-xs text-slate-500">
            Answers use only this company's stored FinSight data and{" "}
            <Link to={`/documents?ticker=${encodeURIComponent(ticker)}`} className="underline">
              your uploaded reports
            </Link>
            , with citations checked by FinSight.
          </p>
          <form onSubmit={submit} className="flex flex-wrap gap-2">
            <input
              aria-label="Research question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. What drove revenue growth in FY26?"
              className="min-w-64 flex-1 rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
            <button type="submit" disabled={ask.isPending} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
              {ask.isPending ? "Thinking…" : "Ask"}
            </button>
          </form>
          {ask.isError ? <ErrorState error={ask.error} /> : null}
          {ask.data ? <Answer answer={ask.data} /> : null}
        </>
      )}
    </Panel>
  );
}
