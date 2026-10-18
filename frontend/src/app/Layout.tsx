import { NavLink, Outlet } from "react-router";

import { logout, useToken } from "../features/auth/api";

export function Layout() {
  const token = useToken();
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <nav className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
          <NavLink to="/" className="text-lg font-semibold tracking-tight">
            FinSight
          </NavLink>
          <span className="text-xs text-slate-500">India · NSE / BSE</span>
          <div className="ml-auto">
            {token ? (
              <button type="button" onClick={logout} className="text-sm text-slate-600 underline">
                Sign out
              </button>
            ) : (
              <NavLink to="/login" className="text-sm text-slate-600 underline">
                Sign in
              </NavLink>
            )}
          </div>
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
