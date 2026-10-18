import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { ApiError } from "../../lib/api";
import { useLogin, useRegister } from "./api";

export function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useLogin();
  const register = useRegister();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const action = mode === "login" ? login : register;
  const next = params.get("next");
  // Only same-app paths: no scheme-relative ("//host") or backslash ("/\host") forms.
  const destination = next && next.startsWith("/") && !next.startsWith("//") && !next.includes("\\") ? next : "/";

  function submit(event: FormEvent) {
    event.preventDefault();
    action.mutate({ email, password }, { onSuccess: () => navigate(destination, { replace: true }) });
  }

  const error = action.error instanceof ApiError ? action.error.message : action.error ? "Something went wrong" : null;

  return (
    <div className="mx-auto max-w-sm space-y-4">
      <h1 className="text-xl font-semibold">{mode === "login" ? "Sign in" : "Create an account"}</h1>
      <form onSubmit={submit} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
        <label className="block text-sm">
          <span className="text-slate-600">Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
            autoComplete="email"
          />
        </label>
        <label className="block text-sm">
          <span className="text-slate-600">Password{mode === "register" ? " (12+ characters)" : ""}</span>
          <input
            type="password"
            required
            minLength={mode === "register" ? 12 : 1}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
        </label>
        {error ? (
          <p role="alert" className="text-sm text-rose-700">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={action.isPending}
          className="w-full rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {action.isPending ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
      </form>
      <button
        type="button"
        onClick={() => setMode(mode === "login" ? "register" : "login")}
        className="text-sm text-sky-700 underline"
      >
        {mode === "login" ? "New here? Create an account" : "Have an account? Sign in"}
      </button>
    </div>
  );
}
