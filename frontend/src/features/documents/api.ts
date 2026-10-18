import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, query } from "../../lib/api";

/** Mirrors `DocumentFactOut` / `DocumentOut` in backend/app/schemas.py. */
export interface DocumentFactOut {
  id: number;
  metric: string;
  value: string;
  unit: string;
  currency: string | null;
  period_label: string | null;
  period_end: string | null;
  basis: string;
  page_number: number;
  quote: string;
  status: "verified" | "unverified";
  verification_note: string | null;
  model: string;
  extracted_at: string;
  kind: "extracted";
}

export interface DocumentOut {
  id: string;
  title: string;
  doc_type: string;
  fiscal_year: number | null;
  filename: string;
  size_bytes: number;
  page_count: number;
  pages_with_text: number;
  status: "ready" | "no_text";
  company: { market: string; ticker: string; name: string } | null;
  facts: DocumentFactOut[];
  created_at: string;
}

export function useDocuments(ticker: string | null) {
  return useQuery({
    queryKey: ["documents", ticker],
    queryFn: () => apiFetch<DocumentOut[]>(`/documents${query({ ticker, market: ticker ? "IN" : null })}`),
  });
}

export function useUploadDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (form: FormData) => apiFetch<DocumentOut>("/documents", { method: "POST", body: form }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["documents"] }),
  });
}

export function useDeleteDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<null>(`/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["documents"] }),
  });
}

export function useExtractFacts() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<DocumentOut>(`/documents/${id}/facts/extract`, { method: "POST", body: JSON.stringify({}) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["documents"] }),
  });
}
