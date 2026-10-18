import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useToken } from "./api";

export function RequireAuth({ children }: { children: ReactNode }) {
  const token = useToken();
  const location = useLocation();
  if (!token) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}
