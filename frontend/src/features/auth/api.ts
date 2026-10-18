import { useMutation } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";

import { apiFetch } from "../../lib/api";
import { getToken, setToken, subscribe } from "../../lib/auth";

/** Mirrors `TokenResponse` in backend/app/schemas.py. */
export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface Credentials {
  email: string;
  password: string;
}

export function useToken(): string | null {
  return useSyncExternalStore(subscribe, getToken, getToken);
}

async function login(credentials: Credentials): Promise<TokenResponse> {
  const token = await apiFetch<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(credentials),
  });
  setToken(token.access_token);
  return token;
}

export function useLogin() {
  return useMutation({ mutationFn: login });
}

export function useRegister() {
  return useMutation({
    mutationFn: async (credentials: Credentials) => {
      await apiFetch("/auth/register", { method: "POST", body: JSON.stringify(credentials) });
      return login(credentials);
    },
  });
}

export function logout(): void {
  setToken(null);
}
