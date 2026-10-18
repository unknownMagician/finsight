import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router";
import { vi } from "vitest";

import { routes } from "../app/routes";

export function renderRoute(path = "/") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...result, router };
}

export function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

export interface RecordedCall {
  url: string;
  path: string;
  params: URLSearchParams;
  method: string;
  headers: Headers;
}

type Handler = (call: RecordedCall) => Response;

/**
 * Stub global fetch. Handlers are keyed by path (e.g. "/api/v1/companies") or by
 * "METHOD path"; the first match wins. Unknown paths return 404. Calls are recorded.
 */
export function stubFetch(handlers: Record<string, Handler>) {
  const calls: RecordedCall[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, "http://localhost");
    const call: RecordedCall = {
      url: raw,
      path: url.pathname,
      params: url.searchParams,
      method: (init?.method ?? "GET").toUpperCase(),
      headers: new Headers(init?.headers),
    };
    calls.push(call);
    const handler = handlers[`${call.method} ${call.path}`] ?? handlers[call.path];
    return handler
      ? handler(call)
      : jsonResponse({ error: { code: "http_error", message: "Not Found" } }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return Object.assign(fetchMock, { calls });
}
