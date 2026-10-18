import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";
import type {
  CompanyMetrics,
  CompsResult,
  DCFInputs,
  DCFResult,
  ForecastAssumptions,
  ForecastBase,
  Multiple,
  SavedValuationOut,
  ScenarioName,
  ScenarioSetResult,
  SensitivityTable,
  WACCInputs,
  WACCResult,
} from "./types";

const post = <T>(path: string, body: unknown) =>
  apiFetch<T>(path, { method: "POST", body: JSON.stringify(body) });

export const useWacc = () =>
  useMutation({ mutationFn: (body: WACCInputs) => post<WACCResult>("/calculations/wacc", body) });

export const useDcf = () =>
  useMutation({ mutationFn: (body: DCFInputs) => post<DCFResult>("/calculations/dcf", body) });

export const useSensitivity = () =>
  useMutation({
    mutationFn: (body: { inputs: DCFInputs; wacc_values: string[]; column_values: string[] }) =>
      post<SensitivityTable>("/calculations/dcf/sensitivity", { ...body, output: "value_per_share" }),
  });

export const useForecast = () =>
  useMutation({
    mutationFn: (body: { base: ForecastBase; scenarios: Partial<Record<ScenarioName, ForecastAssumptions>> }) =>
      post<ScenarioSetResult>("/calculations/forecast", body),
  });

export const useComps = () =>
  useMutation({
    mutationFn: (body: { target: CompanyMetrics; peers: CompanyMetrics[]; multiples: Multiple[] }) =>
      post<CompsResult>("/calculations/comps", body),
  });

export function useSavedValuations() {
  return useQuery({ queryKey: ["valuations"], queryFn: () => apiFetch<SavedValuationOut[]>("/valuations") });
}

export function useSaveValuation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; ticker: string | null; market: "IN"; inputs: DCFInputs }) =>
      post<SavedValuationOut>("/valuations", body),
    onSuccess: () => client.invalidateQueries({ queryKey: ["valuations"] }),
  });
}

export function useDeleteValuation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<null>(`/valuations/${id}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["valuations"] }),
  });
}
