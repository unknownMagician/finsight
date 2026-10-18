/**
 * Thin fetch wrapper for the FinSight API.
 *
 * All requests go to same-origin `/api/v1/...` (proxied by Vite in dev, nginx in Docker).
 * Non-2xx responses are converted into `ApiError`, parsed from the backend error envelope
 * `{ error: { code, message, request_id, details } }` when present. The signed-in user's
 * access token is attached automatically; a 401 clears it.
 */

import { getToken, setToken } from "./auth";

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, requestId: string | null, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

interface ErrorEnvelope {
  error?: { code?: string; message?: string; request_id?: string | null; details?: unknown };
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  const token = getToken();
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        // JSON bodies are strings; FormData (uploads) sets its own multipart boundary.
        ...(typeof init?.body === "string" ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(0, "network_error", "Unable to reach the FinSight API", null);
  }

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && token) setToken(null);
    const err = (body as ErrorEnvelope | null)?.error;
    throw new ApiError(
      response.status,
      err?.code ?? "http_error",
      err?.message ?? `Request failed with status ${response.status}`,
      err?.request_id ?? response.headers.get("x-request-id"),
      err?.details,
    );
  }
  return body as T;
}

/** Build a query string, dropping undefined/empty values. */
export function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
