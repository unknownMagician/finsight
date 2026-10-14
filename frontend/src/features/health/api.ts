import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "../../lib/api";

/** Mirrors `LivenessResponse` in backend/app/api/health.py. */
export interface LivenessResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
}

/** Mirrors `ReadinessResponse` in backend/app/api/health.py. */
export interface ReadinessResponse {
  status: "ok" | "unavailable";
  checks: Record<string, "ok" | "error">;
}

export function useLiveness() {
  return useQuery({
    queryKey: ["health", "live"],
    queryFn: () => apiFetch<LivenessResponse>("/health/live"),
  });
}

export function useReadiness() {
  return useQuery({
    queryKey: ["health", "ready"],
    // 503 is a meaningful "not ready" answer, not a transport failure, so read the body.
    queryFn: async (): Promise<ReadinessResponse> => {
      const response = await fetch("/api/v1/health/ready", { headers: { Accept: "application/json" } });
      if (response.status !== 200 && response.status !== 503) {
        throw new Error(`Unexpected status ${response.status}`);
      }
      return (await response.json()) as ReadinessResponse;
    },
    refetchInterval: 30_000,
  });
}
