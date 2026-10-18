import { useMutation, useQuery } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";

/** Mirrors `ResearchAnswerOut` / `ResearchStatusOut` in backend/app/schemas.py. */
export interface CitationOut {
  source: number;
  cited_text: string;
  label: string;
  document_id: string | null;
  page_number: number | null;
}

export interface ResearchAnswerOut {
  question: string;
  kind: "ai_explanation";
  model: string;
  grounding: "grounded" | "partially_grounded" | "ungrounded";
  segments: { text: string; citations: CitationOut[] }[];
  sources: { number: number; title: string; kind: string; document_id: string | null; page_number: number | null }[];
  issues: { code: string; segment: number | null; message: string }[];
  input_tokens: number;
  output_tokens: number;
  disclaimer: string;
}

export interface ResearchStatusOut {
  configured: boolean;
  provider: string | null;
  model: string | null;
}

export function useResearchStatus() {
  return useQuery({ queryKey: ["research", "status"], queryFn: () => apiFetch<ResearchStatusOut>("/research/status") });
}

export function useAsk() {
  return useMutation({
    mutationFn: (body: { question: string; ticker?: string; market?: "IN"; document_ids?: string[] }) =>
      apiFetch<ResearchAnswerOut>("/research/ask", { method: "POST", body: JSON.stringify(body) }),
  });
}
