import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";
import type { CompanyOut } from "../companies/types";

/** Mirrors `WatchlistOut` in backend/app/schemas.py. */
export interface WatchlistOut {
  id: string;
  name: string;
  companies: CompanyOut[];
  created_at: string;
  updated_at: string;
}

const KEY = ["watchlists"];

export function useWatchlists() {
  return useQuery({ queryKey: KEY, queryFn: () => apiFetch<WatchlistOut[]>("/watchlists") });
}

function useWatchlistMutation<V>(fn: (vars: V) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => client.invalidateQueries({ queryKey: KEY }) });
}

const send = (path: string, method: string, body?: unknown) =>
  apiFetch<unknown>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

export const useCreateWatchlist = () => useWatchlistMutation((name: string) => send("/watchlists", "POST", { name }));
export const useRenameWatchlist = () =>
  useWatchlistMutation(({ id, name }: { id: string; name: string }) => send(`/watchlists/${id}`, "PATCH", { name }));
export const useDeleteWatchlist = () => useWatchlistMutation((id: string) => send(`/watchlists/${id}`, "DELETE"));
export const useAddToWatchlist = () =>
  useWatchlistMutation(({ id, ticker }: { id: string; ticker: string }) =>
    send(`/watchlists/${id}/items`, "POST", { ticker, market: "IN" }),
  );
export const useRemoveFromWatchlist = () =>
  useWatchlistMutation(({ id, ticker }: { id: string; ticker: string }) =>
    send(`/watchlists/${id}/items/${encodeURIComponent(ticker)}?market=IN`, "DELETE"),
  );
