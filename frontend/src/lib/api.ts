/**
 * Thin fetch wrapper for the FinSight API.
 *
 * All requests go to same-origin `/api/v1/...` (proxied by Vite in dev, nginx in Docker).
 * Non-2xx responses are converted into `ApiError`, parsed from the backend error envelope
 * `{ error: { code, message, request_id, details } }` when present.
 */

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
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "network_error", "Unable to reach the FinSight API", null);
  }

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
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
