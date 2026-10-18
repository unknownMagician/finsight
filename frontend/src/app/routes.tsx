import { lazy, Suspense, type ReactNode } from "react";
import type { RouteObject } from "react-router";

import { Loading } from "../components/States";
import { LoginPage } from "../features/auth/LoginPage";
import { RequireAuth } from "../features/auth/RequireAuth";
import { HomePage } from "../pages/HomePage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { Layout } from "./Layout";

// The research page pulls in the charting library; load it only when needed.
const CompanyPage = lazy(() =>
  import("../features/companies/CompanyPage").then((m) => ({ default: m.CompanyPage })),
);

const CalculatorsPage = lazy(() =>
  import("../features/calculators/CalculatorsPage").then((m) => ({ default: m.CalculatorsPage })),
);
const WatchlistsPage = lazy(() =>
  import("../features/watchlists/WatchlistsPage").then((m) => ({ default: m.WatchlistsPage })),
);
const ValuationsPage = lazy(() =>
  import("../features/valuations/ValuationsPage").then((m) => ({ default: m.ValuationsPage })),
);

function guarded(element: ReactNode) {
  return (
    <RequireAuth>
      <Suspense fallback={<Loading />}>{element}</Suspense>
    </RequireAuth>
  );
}

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "login", element: <LoginPage /> },
      { path: "companies/:ticker", element: guarded(<CompanyPage />) },
      { path: "calculators", element: guarded(<CalculatorsPage />) },
      { path: "watchlists", element: guarded(<WatchlistsPage />) },
      { path: "valuations", element: guarded(<ValuationsPage />) },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
