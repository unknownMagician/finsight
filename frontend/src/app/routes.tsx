import { lazy, Suspense } from "react";
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

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "login", element: <LoginPage /> },
      {
        path: "companies/:ticker",
        element: (
          <RequireAuth>
            <Suspense fallback={<Loading />}>
              <CompanyPage />
            </Suspense>
          </RequireAuth>
        ),
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
