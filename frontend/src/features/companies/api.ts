import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, query } from "../../lib/api";
import type {
  CompanyOut,
  CorporateActionsOut,
  Exchange,
  FinancialsOut,
  IngestOut,
  MarketStatusOut,
  PriceHistoryOut,
  QuoteOut,
  RatioReport,
  ReportingBasis,
  ValuationSnapshotOut,
} from "./types";

const path = (ticker: string) => `/companies/${encodeURIComponent(ticker)}`;

export function useCompanySearch(q: string, exchange: Exchange | null) {
  const trimmed = q.trim();
  return useQuery({
    queryKey: ["companies", "search", trimmed, exchange],
    queryFn: () =>
      apiFetch<CompanyOut[]>(`/companies${query({ q: trimmed, exchange, market: "IN", limit: 20 })}`),
    enabled: trimmed.length >= 1,
    staleTime: 60_000,
  });
}

export function useCompany(ticker: string) {
  return useQuery({
    queryKey: ["companies", ticker],
    queryFn: () => apiFetch<CompanyOut>(`${path(ticker)}${query({ market: "IN" })}`),
  });
}

export function useQuote(ticker: string, exchange: Exchange | null) {
  return useQuery({
    queryKey: ["companies", ticker, "quote", exchange],
    queryFn: () => apiFetch<QuoteOut>(`${path(ticker)}/quote${query({ exchange })}`),
    enabled: exchange !== null,
  });
}

export function usePrices(ticker: string, exchange: Exchange | null, start: string, end: string) {
  return useQuery({
    queryKey: ["companies", ticker, "prices", exchange, start, end],
    queryFn: () => apiFetch<PriceHistoryOut>(`${path(ticker)}/prices${query({ exchange, start, end })}`),
    enabled: exchange !== null,
  });
}

export function useFinancials(
  ticker: string,
  periodType: "annual" | "quarterly",
  basis: ReportingBasis | null,
) {
  return useQuery({
    queryKey: ["companies", ticker, "financials", periodType, basis],
    queryFn: () =>
      apiFetch<FinancialsOut>(
        `${path(ticker)}/financials${query({ market: "IN", period_type: periodType, basis })}`,
      ),
  });
}

export function useRatios(ticker: string, basis: ReportingBasis | null, enabled: boolean) {
  return useQuery({
    queryKey: ["companies", ticker, "ratios", basis],
    queryFn: () => apiFetch<RatioReport>(`${path(ticker)}/ratios${query({ market: "IN", basis })}`),
    enabled,
  });
}

export function useValuationSnapshot(
  ticker: string,
  exchange: Exchange | null,
  basis: ReportingBasis | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["companies", ticker, "valuation", exchange, basis],
    queryFn: () =>
      apiFetch<ValuationSnapshotOut>(`${path(ticker)}/valuation-snapshot${query({ exchange, basis })}`),
    enabled: enabled && exchange !== null,
  });
}

export function useCorporateActions(ticker: string) {
  return useQuery({
    queryKey: ["companies", ticker, "actions"],
    queryFn: () => apiFetch<CorporateActionsOut>(`${path(ticker)}/corporate-actions`),
  });
}

export function useIngest(ticker: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<IngestOut>(`${path(ticker)}/ingest${query({ market: "IN" })}`, { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["companies", ticker] }),
  });
}

export function useMarketStatus() {
  return useQuery({
    queryKey: ["market", "status"],
    queryFn: () => apiFetch<MarketStatusOut>("/market/status"),
    staleTime: 5 * 60_000,
  });
}
