import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";

/** Mirrors backend/app/reports/model.py and `ReportOut` in schemas.py. */
export type Provenance = "reported" | "calculated" | "assumption" | "forecast" | "extracted" | "market" | "ai_explanation";

export interface ReportFigure {
  label: string;
  value: string | null;
  display: string;
  kind: Provenance;
  period: string | null;
  basis: string | null;
  source: string | null;
  note: string | null;
}

export interface ReportTable {
  caption: string;
  kind: Provenance;
  columns: string[];
  rows: string[][];
  source: string | null;
}

export interface ReportSection {
  key: string;
  title: string;
  status: "ok" | "unavailable";
  reason: string | null;
  figures: ReportFigure[];
  tables: ReportTable[];
  paragraphs: string[];
}

export interface ReportContent {
  title: string;
  generated_at: string;
  company: { market: string; ticker: string; name: string; isin: string | null; listings: string[] };
  exchange: string | null;
  basis: string | null;
  sections: ReportSection[];
  disclaimers: string[];
  engine_version: string;
}

export interface ReportSummary {
  id: string;
  title: string;
  ticker: string;
  includes_ai: boolean;
  engine_version: string;
  created_at: string;
}

export interface ReportOut extends ReportSummary {
  content: ReportContent;
}

export function useReports() {
  return useQuery({ queryKey: ["reports"], queryFn: () => apiFetch<ReportSummary[]>("/reports") });
}

export function useReport(id: string) {
  return useQuery({ queryKey: ["reports", id], queryFn: () => apiFetch<ReportOut>(`/reports/${id}`) });
}

export function useCreateReport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { ticker: string; market: "IN"; exchange: string | null; include_ai: boolean }) =>
      apiFetch<ReportOut>("/reports", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["reports"] }),
  });
}

export function useDeleteReport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<null>(`/reports/${id}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["reports"] }),
  });
}
