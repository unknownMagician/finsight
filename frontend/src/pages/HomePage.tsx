import { Link } from "react-router";

import { useToken } from "../features/auth/api";
import { CompanySearch } from "../features/companies/CompanySearch";
import { SystemStatus } from "../features/health/SystemStatus";

export function HomePage() {
  const token = useToken();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">FinSight</h1>
        <p className="text-slate-600">Research NSE and BSE listed companies with sourced, dated data.</p>
      </div>
      {token ? (
        <CompanySearch />
      ) : (
        <p className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <Link to="/login" className="text-sky-700 underline">
            Sign in
          </Link>{" "}
          to search Indian companies.
        </p>
      )}
      <SystemStatus />
    </div>
  );
}
