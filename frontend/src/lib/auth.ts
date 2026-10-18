/**
 * Access-token store. The token is the backend's short-lived JWT; it is kept in memory and
 * mirrored to sessionStorage (cleared when the tab closes) so a reload keeps the session.
 * No API keys or provider credentials ever reach the browser.
 */

const STORAGE_KEY = "finsight.token";
type Listener = () => void;

const listeners = new Set<Listener>();
let token: string | null = readStorage();

function readStorage(): string | null {
  try {
    return globalThis.sessionStorage?.getItem(STORAGE_KEY) ?? null;
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  return token;
}

export function setToken(next: string | null): void {
  token = next;
  try {
    if (next) sessionStorage.setItem(STORAGE_KEY, next);
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage unavailable (private mode); the in-memory token still works for this tab
  }
  listeners.forEach((listener) => listener());
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
